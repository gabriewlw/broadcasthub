"""AV inventory server. Python 3.12+; install requirements.txt for Excel import."""
import csv
import io
import ipaddress
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from spreadsheets import preview as spreadsheet_preview

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('IPTRACKING_DB', ROOT / 'data' / 'inventory.sqlite3'))
DISCIPLINES = {'Video', 'Audio', 'Lighting', 'Control', 'Network', 'Other'}
FIELDS = ('name', 'category', 'venue', 'discipline', 'ip', 'vlan', 'notes')


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('''CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
        venue TEXT NOT NULL, discipline TEXT NOT NULL, ip TEXT NOT NULL,
        vlan INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT '',
        ip_confirmed INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(ip, vlan))''')
    # Upgrade existing inventories without replacing or deleting their records.
    if 'ip_confirmed' not in {row['name'] for row in con.execute('PRAGMA table_info(devices)')}:
        con.execute('ALTER TABLE devices ADD COLUMN ip_confirmed INTEGER NOT NULL DEFAULT 0')
    return con


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('Each device must be an object.')
    result = {}
    for field in ('name', 'category', 'venue', 'discipline', 'ip', 'notes'):
        raw = value.get(field, '')
        if not isinstance(raw, str):
            raise ValueError(f'{field.capitalize()} must be text.')
        result[field] = raw.strip()
        if len(result[field]) > (2000 if field == 'notes' else 120):
            raise ValueError(f'{field.capitalize()} is too long.')
    for field in ('name', 'category', 'venue', 'discipline', 'ip'):
        if not result[field]:
            raise ValueError(f'{field.capitalize()} is required.')
    if result['discipline'] not in DISCIPLINES:
        raise ValueError('Choose a valid system: Video, Audio, Lighting, Control, Network, or Other.')
    try:
        address = ipaddress.IPv4Address(result['ip'])
    except ipaddress.AddressValueError:
        raise ValueError('Enter a valid IPv4 address, such as 10.24.176.66.') from None
    if address.is_unspecified or address.is_loopback or address.is_multicast or int(address) == 0xffffffff:
        raise ValueError('Use a unicast device address, not loopback, multicast, or broadcast.')
    result['ip'] = str(address)
    vlan = value.get('vlan')
    if isinstance(vlan, bool) or not isinstance(vlan, (str, int)) or not str(vlan).isascii() or not str(vlan).isdigit():
        raise ValueError('VLAN must be a whole number from 1 to 4094.')
    result['vlan'] = int(vlan)
    if not 1 <= result['vlan'] <= 4094:
        raise ValueError('VLAN must be between 1 and 4094.')
    return result


def inventory():
    with connect() as con:
        return [dict(row) for row in con.execute('SELECT * FROM devices ORDER BY venue COLLATE NOCASE, name COLLATE NOCASE')]


def save_device(value, device_id=None):
    row = validate(value)
    with connect() as con:
        if device_id is None:
            cursor = con.execute('INSERT INTO devices (' + ','.join(FIELDS) + ') VALUES (?,?,?,?,?,?,?)', [row[f] for f in FIELDS])
            device_id = cursor.lastrowid
        else:
            cursor = con.execute('UPDATE devices SET ' + ','.join(f + '=?' for f in FIELDS) + ', ip_confirmed=CASE WHEN ip=? AND vlan=? THEN ip_confirmed ELSE 0 END, updated_at=CURRENT_TIMESTAMP WHERE id=?', [row[f] for f in FIELDS] + [row['ip'], row['vlan'], device_id])
            if cursor.rowcount == 0:
                raise LookupError('Device not found.')
        return dict(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def confirm_ip(device_id, value):
    if not isinstance(value, dict):
        raise ValueError('Provide the IP and VLAN being confirmed.')
    with connect() as con:
        record = con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if record is None:
            raise LookupError('Device not found.')
        # Check the stored address and assignment, not just a stale browser value.
        row = validate(dict(record))
        if value.get('ip') != row['ip'] or value.get('vlan') != row['vlan']:
            raise ValueError('The IP or VLAN has changed. Refresh the inventory before confirming.')
        cursor = con.execute('UPDATE devices SET ip_confirmed=1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND ip=? AND vlan=?', (device_id, row['ip'], row['vlan']))
        if not cursor.rowcount:
            raise ValueError('The assignment has changed. Refresh before confirming.')
        return dict(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def import_devices(payload):
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('devices'), list):
        raise ValueError('Choose an IP Tracking JSON export (version 1).')
    if len(payload['devices']) > 10000:
        raise ValueError('Import supports up to 10,000 devices per file.')
    rows = []
    for index, value in enumerate(payload['devices'], 1):
        try:
            rows.append(validate(value))
        except ValueError as exc:
            raise ValueError(f'Device row {index}: {exc} Nothing was imported.') from None
    identities = [(row['ip'], row['vlan']) for row in rows]
    if len(set(identities)) != len(identities):
        raise ValueError('The file contains duplicate IP addresses within a VLAN. Nothing was imported.')
    # A single transaction makes imports atomic. Existing records are never overwritten.
    with connect() as con:
        existing = {(row['ip'], row['vlan']) for row in con.execute('SELECT ip, vlan FROM devices')}
        added = 0
        for row in rows:
            if (row['ip'], row['vlan']) in existing:
                continue
            con.execute('INSERT INTO devices (' + ','.join(FIELDS) + ') VALUES (?,?,?,?,?,?,?)', [row[f] for f in FIELDS])
            added += 1
    return {'added': added, 'skipped': len(rows) - added}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, data, content_type='application/json; charset=utf-8', filename=None):
        body = json.dumps(data).encode() if content_type.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        # Reject cross-origin writes, including simple requests from other websites.
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            raise PermissionError('Cross-origin writes are not allowed.')
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ValueError('Use application/json.')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise ValueError('Invalid request size.') from None
        if size < 1 or size > 8_000_000:
            raise ValueError('Request must be between 1 byte and 8 MB.')
        return json.loads(self.rfile.read(size))

    def dispatch(self):
        path = urlsplit(self.path).path
        if self.command == 'GET':
            if path == '/api/devices':
                return self.send(200, {'devices': inventory()})
            if path == '/api/export':
                return self.send(200, {'version': 1, 'devices': inventory()}, filename='ip-tracking.json')
            if path == '/api/export.csv':
                output = io.StringIO(newline='')
                writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction='ignore')
                writer.writeheader()
                for row in inventory():
                    # Prevent spreadsheet formula injection in user-supplied strings.
                    writer.writerow({f: ("'" + str(row[f]) if str(row[f]).startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else row[f]) for f in FIELDS})
                return self.send(200, output.getvalue().encode('utf-8-sig'), 'text/csv; charset=utf-8', 'ip-tracking.csv')
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/icon.svg': ('icon.svg', 'image/svg+xml')}
            if path in assets:
                file, mime = assets[path]
                return self.send(200, (ROOT / 'static' / file).read_bytes(), mime + '; charset=utf-8')
        elif self.command == 'POST' and path == '/api/devices':
            return self.send(201, save_device(self.body()))
        elif self.command == 'POST' and path == '/api/spreadsheet-preview':
            return self.send(200, spreadsheet_preview(self.body()))
        elif self.command == 'POST' and path == '/api/import':
            return self.send(200, import_devices(self.body()))
        elif self.command == 'POST' and path.startswith('/api/devices/') and path.endswith('/confirm'):
            try:
                device_id = int(path.removeprefix('/api/devices/').removesuffix('/confirm'))
            except ValueError:
                raise LookupError('Device not found.') from None
            return self.send(200, confirm_ip(device_id, self.body()))
        elif self.command in ('PUT', 'DELETE') and path.startswith('/api/devices/'):
            try:
                device_id = int(path.removeprefix('/api/devices/'))
            except ValueError:
                raise LookupError('Device not found.') from None
            if self.command == 'PUT':
                return self.send(200, save_device(self.body(), device_id))
            self.body()
            with connect() as con:
                if con.execute('DELETE FROM devices WHERE id=?', (device_id,)).rowcount == 0:
                    raise LookupError('Device not found.')
            return self.send(200, {'deleted': device_id})
        self.send(404, {'error': 'Not found.'})

    def handle_request(self):
        try:
            self.dispatch()
        except PermissionError as exc:
            self.send(403, {'error': str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send(400, {'error': str(exc)})
        except LookupError as exc:
            self.send(404, {'error': str(exc)})
        except sqlite3.IntegrityError:
            self.send(409, {'error': 'This IP address is already assigned to a device in this VLAN.'})
        except Exception:
            self.log_error('Internal request error')
            self.send(500, {'error': 'Could not complete the request. Check server storage and try again.'})

    do_GET = do_POST = do_PUT = do_DELETE = handle_request


if __name__ == '__main__':
    with connect():
        pass
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8000'))
    print(f'IP Tracking listening on {host}:{port}', flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
