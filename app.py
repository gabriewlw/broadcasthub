"""broadcasthub server. Python 3.12+; install requirements.txt for Excel import."""
import csv
import io
import ipaddress
import json
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from spreadsheets import preview as spreadsheet_preview
from exports import network_xlsx, equipment_xlsx, network_pdf, equipment_pdf

ROOT = Path(__file__).resolve().parent
# Keep existing hosted database configurations working during the project rename.
DB_PATH = Path(os.environ.get('BROADCASTHUB_DB') or os.environ.get('AVTRACK_DB') or os.environ.get('IPTRACKING_DB') or ROOT / 'data' / 'inventory.sqlite3')
DISCIPLINES = {'Video', 'Audio', 'Lighting', 'Control', 'Network', 'Other'}
SYSTEM_NAME_RULES = (
    ('audio', 'Audio'), ('amx', 'Control'), ('scheduler', 'Control'), ('dsp', 'Audio'),
    ('yamaha', 'Audio'), ('behringer', 'Audio'), ('shure', 'Audio'),
    ('clickshare', 'Video'), ('pixera', 'Video'), ('tv', 'Video'),
    ('video', 'Video'), ('led', 'Video'), ('light', 'Lighting'), ('cam', 'Video'),
    ('camera', 'Video'), ('bgm', 'Audio'), ('decoder', 'Video'),
    ('encoder', 'Video'), ('multiview', 'Video'), ('scala', 'Video'),
    ('blackmagic', 'Video'), ('castus', 'Video'),
    ('switch', 'Network'), ('dante', 'Audio'), ('cctv', 'Video'), ('iem', 'Audio'),
)
FIELDS = ('name', 'category', 'venue', 'discipline', 'ip', 'vlan', 'notes')
ALL_FIELDS = FIELDS + ('record_type', 'channel_source', 'port')
EQUIPMENT_FIELDS = ('brand', 'model', 'description', 'serial_number', 'quantity', 'location', 'notes')
EQUIPMENT_CONFIRM_FIELDS = EQUIPMENT_FIELDS[:-1]


SCHEMA = """CREATE TABLE {table} (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    venue TEXT NOT NULL, discipline TEXT NOT NULL, ip TEXT NOT NULL,
    vlan INTEGER, notes TEXT NOT NULL DEFAULT '',
    record_type TEXT NOT NULL DEFAULT 'device', channel_source TEXT NOT NULL DEFAULT '',
    port INTEGER, ip_confirmed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
EQUIPMENT_SCHEMA = """CREATE TABLE {table} (
    id INTEGER PRIMARY KEY, brand TEXT NOT NULL, model TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL DEFAULT '',
    quantity INTEGER, location TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
    item_confirmed INTEGER NOT NULL DEFAULT 0,
    inventory_id INTEGER NOT NULL DEFAULT 1 REFERENCES equipment_inventories(id),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute(SCHEMA.format(table='IF NOT EXISTS devices'))
    columns = {row['name']: row for row in con.execute('PRAGMA table_info(devices)')}
    for column, definition in [('ip_confirmed', 'INTEGER NOT NULL DEFAULT 0'),
                               ('record_type', "TEXT NOT NULL DEFAULT 'device'"),
                               ('channel_source', "TEXT NOT NULL DEFAULT ''"), ('port', 'INTEGER')]:
        if column not in columns:
            con.execute(f'ALTER TABLE devices ADD COLUMN {column} {definition}')
    if columns['vlan']['notnull']:
        # Rebuild the old table atomically to make VLAN optional for IPTV.
        # Copy every existing record, ID, timestamp, and confirmation without inventing ports.
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute(SCHEMA.format(table='devices_upgrade'))
            names = 'id,' + ','.join(ALL_FIELDS) + ',ip_confirmed,updated_at'
            con.execute(f'INSERT INTO devices_upgrade ({names}) SELECT {names} FROM devices')
            con.execute('DROP TABLE devices')
            con.execute('ALTER TABLE devices_upgrade RENAME TO devices')
            con.commit()
        except Exception:
            con.rollback()
            con.close()
            raise
    con.execute('DROP INDEX IF EXISTS device_assignment')
    con.execute('DROP INDEX IF EXISTS device_assignment_known')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS device_assignment_static ON devices(ip,vlan) WHERE record_type='device' AND ip NOT IN ('','DHCP')")
    con.execute('DROP TRIGGER IF EXISTS device_unique_ip_insert')
    con.execute('DROP TRIGGER IF EXISTS device_unique_ip_update')
    con.execute('DROP TRIGGER IF EXISTS device_known_ip_insert')
    con.execute('DROP TRIGGER IF EXISTS device_known_ip_update')
    # Preserve old records that share an IP across VLANs, but prevent new collisions.
    con.execute("""CREATE TRIGGER IF NOT EXISTS device_static_ip_insert
        BEFORE INSERT ON devices WHEN NEW.record_type='device' AND NEW.ip NOT IN ('','DHCP') AND EXISTS
        (SELECT 1 FROM devices WHERE record_type='device' AND ip=NEW.ip)
        BEGIN SELECT RAISE(ABORT, 'Duplicate AV IP address'); END""")
    con.execute("""CREATE TRIGGER IF NOT EXISTS device_static_ip_update
        BEFORE UPDATE OF ip, record_type ON devices
        WHEN NEW.record_type='device' AND NEW.ip NOT IN ('','DHCP') AND (OLD.ip!=NEW.ip OR OLD.record_type!=NEW.record_type)
        AND EXISTS (SELECT 1 FROM devices WHERE record_type='device' AND ip=NEW.ip AND id!=NEW.id)
        BEGIN SELECT RAISE(ABORT, 'Duplicate AV IP address'); END""")
    con.execute('DROP INDEX IF EXISTS channel_endpoint')
    con.execute('DROP INDEX IF EXISTS channel_endpoint_known')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS channel_endpoint_static ON devices(ip,port) WHERE record_type='iptv' AND ip NOT IN ('','DHCP') AND port IS NOT NULL")
    con.execute('CREATE TABLE IF NOT EXISTS equipment_inventories (id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE)')
    if not con.execute('SELECT 1 FROM equipment_inventories WHERE id=1').fetchone():
        con.execute("INSERT OR IGNORE INTO equipment_inventories (id,name) VALUES (1,'Equipment inventory')")
        con.commit()
    con.execute(EQUIPMENT_SCHEMA.format(table='IF NOT EXISTS equipment'))
    equipment_columns = {row['name']: row for row in con.execute('PRAGMA table_info(equipment)')}
    if 'item_confirmed' not in equipment_columns:
        con.execute('ALTER TABLE equipment ADD COLUMN item_confirmed INTEGER NOT NULL DEFAULT 0')
    if 'inventory_id' not in equipment_columns:
        con.execute('ALTER TABLE equipment ADD COLUMN inventory_id INTEGER NOT NULL DEFAULT 1 REFERENCES equipment_inventories(id)')
    if next(row for row in con.execute('PRAGMA table_info(equipment)') if row['name'] == 'quantity')['notnull']:
        # Preserve existing quantities; missing quantities are unknown, not zero or one.
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute(EQUIPMENT_SCHEMA.format(table='equipment_upgrade'))
            names = 'id,' + ','.join(EQUIPMENT_FIELDS) + ',item_confirmed,inventory_id,updated_at'
            con.execute(f'INSERT INTO equipment_upgrade ({names}) SELECT {names} FROM equipment')
            con.execute('DROP TABLE equipment')
            con.execute('ALTER TABLE equipment_upgrade RENAME TO equipment')
            con.commit()
        except Exception:
            con.rollback()
            con.close()
            raise
    con.execute('DROP INDEX IF EXISTS equipment_serial')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS equipment_inventory_serial ON equipment(inventory_id, serial_number COLLATE NOCASE) WHERE serial_number != ''")
    con.execute('DROP INDEX IF EXISTS equipment_stock')
    con.execute('DROP INDEX IF EXISTS equipment_stock_known')
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS equipment_inventory_stock ON equipment(inventory_id, brand COLLATE NOCASE, model COLLATE NOCASE, description, location COLLATE NOCASE) WHERE serial_number='' AND brand!='' AND model!='' AND location!=''")
    return con


def serialize(record):
    row = dict(record)
    if row['record_type'] == 'iptv':
        row.update(venue='', vlan=None, ip_confirmed=0)
    else:
        row['venue'] = clean_venue(row['venue'])
    return row


def clean_venue(value):
    return re.sub(r'^RD\s+', '', value.strip(), flags=re.IGNORECASE).strip()


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('Each device must be an object.')
    record_type = value.get('record_type') or 'device'
    if record_type not in ('device', 'iptv'):
        raise ValueError('Inventory type must be device or iptv.')
    channel_source = value.get('channel_source') or ''
    if record_type == 'iptv' and channel_source not in ('', 'Onboard', 'Satellite'):
        raise ValueError('Choose Onboard or Satellite for the IPTV channel source.')
    result = {'record_type': record_type, 'channel_source': channel_source if record_type == 'iptv' else ''}
    for field in ('name', 'category', 'venue', 'discipline', 'ip', 'notes'):
        raw = value.get(field, '')
        if raw is None:
            raw = ''
        if not isinstance(raw, str):
            raise ValueError(f'{field.capitalize()} must be text.')
        result[field] = raw.strip()
        if len(result[field]) > (2000 if field == 'notes' else 120):
            raise ValueError(f'{field.capitalize()} is too long.')
    if record_type == 'iptv':
        result.update(venue='')
    else:
        result['venue'] = clean_venue(result['venue'])
    if result['discipline'] and result['discipline'] not in DISCIPLINES:
        raise ValueError('Choose a valid system: Video, Audio, Lighting, Control, Network, or Other.')
    if result['ip'].upper() == 'DHCP':
        result['ip'] = 'DHCP'
    elif result['ip']:
        try:
            address = ipaddress.IPv4Address(result['ip'])
        except ipaddress.AddressValueError:
            raise ValueError('Enter a valid IPv4 address, such as 10.24.176.66.') from None
        if address.is_unspecified or address.is_loopback or (address.is_multicast and record_type != 'iptv') or int(address) == 0xffffffff:
            raise ValueError('Use a valid device address; multicast addresses are only allowed for IPTV channels.')
        result['ip'] = str(address)
    if record_type == 'iptv':
        port = value.get('port')
        if port is None or port == '':
            result.update(port=None, vlan=None)
        elif isinstance(port, bool) or not isinstance(port, (str, int)) or not str(port).isascii() or not str(port).isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError('Port must be a whole number from 1 to 65535.')
        else:
            result.update(port=int(port), vlan=None)
    else:
        vlan = value.get('vlan')
        if vlan is None or vlan == '':
            result.update(vlan=None, port=None)
        elif isinstance(vlan, bool) or not isinstance(vlan, (str, int)) or not str(vlan).isascii() or not str(vlan).isdigit():
            raise ValueError('VLAN must be a whole number from 1 to 4094.')
        else:
            result['vlan'] = int(vlan)
            if not 1 <= result['vlan'] <= 4094:
                raise ValueError('VLAN must be between 1 and 4094.')
        result['port'] = None
    if not any(result[f] is not None and result[f] != '' for f in ALL_FIELDS if f != 'record_type'):
        raise ValueError('Provide at least one device or channel detail.')
    return result


def inventory():
    with connect() as con:
        return [serialize(row) for row in con.execute('SELECT * FROM devices ORDER BY venue COLLATE NOCASE, name COLLATE NOCASE')]


def save_device(value, device_id=None):
    row = validate(value)
    with connect() as con:
        if device_id is None:
            cursor = con.execute('INSERT INTO devices (' + ','.join(ALL_FIELDS) + ') VALUES (' + ','.join('?' for _ in ALL_FIELDS) + ')', [row[f] for f in ALL_FIELDS])
            device_id = cursor.lastrowid
        else:
            cursor = con.execute('UPDATE devices SET ' + ','.join(f + '=?' for f in ALL_FIELDS) + ', ip_confirmed=CASE WHEN ip=? AND vlan IS ? THEN ip_confirmed ELSE 0 END, updated_at=CURRENT_TIMESTAMP WHERE id=?', [row[f] for f in ALL_FIELDS] + [row['ip'], row['vlan'], device_id])
            if cursor.rowcount == 0:
                raise LookupError('Device not found.')
        return serialize(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def confirm_ip(device_id, value):
    if not isinstance(value, dict):
        raise ValueError('Provide the IP and VLAN being confirmed.')
    with connect() as con:
        record = con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if record is None:
            raise LookupError('Device not found.')
        if record['record_type'] == 'iptv':
            raise ValueError('IPTV channels do not require IP confirmation.')
        # Check the stored address and assignment, not just a stale browser value.
        row = validate(dict(record))
        if not row['ip']:
            raise ValueError('Add an IP address before confirming it.')
        if row['ip'] == 'DHCP':
            raise ValueError('DHCP does not have a fixed IP address to confirm.')
        if value.get('ip') != row['ip'] or value.get('vlan') != row['vlan']:
            raise ValueError('The IP or VLAN has changed. Refresh the inventory before confirming.')
        cursor = con.execute('UPDATE devices SET ip_confirmed=1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND ip=? AND vlan IS ?', (device_id, row['ip'], row['vlan']))
        if not cursor.rowcount:
            raise ValueError('The assignment has changed. Refresh before confirming.')
        return serialize(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def device_identity(row):
    if row['ip'] in ('', 'DHCP') or (row['record_type'] == 'iptv' and row['port'] is None):
        return None
    return (row['record_type'], row['ip'], row['port'] if row['record_type'] == 'iptv' else None)


def blank_import_row(value, fields):
    return isinstance(value, dict) and all(value.get(f) is None or (isinstance(value.get(f), str) and not value[f].strip()) for f in fields)


def set_device_system(device_id, value):
    if not isinstance(value, dict) or not isinstance(value.get('discipline', ''), str):
        raise ValueError('System must be text.')
    discipline = value.get('discipline', '').strip()
    if discipline and discipline not in DISCIPLINES:
        raise ValueError('Choose a valid system.')
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        record = con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
        if record is None:
            raise LookupError('Device not found.')
        if record['record_type'] != 'device':
            raise ValueError('System dropdowns apply to AV devices.')
        con.execute('UPDATE devices SET discipline=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (discipline, device_id))
        return serialize(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def set_device_notes(device_id, value):
    if not isinstance(value, dict) or not isinstance(value.get('notes', ''), str):
        raise ValueError('Notes must be text.')
    notes = value.get('notes', '').strip()
    if len(notes) > 2000:
        raise ValueError('Notes are too long.')
    with connect() as con:
        if not con.execute('UPDATE devices SET notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (notes, device_id)).rowcount:
            raise LookupError('Device not found.')
        return serialize(con.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone())


def system_from_name(name):
    # Follow the user's rule order when several keywords match the same name.
    name = name.casefold()
    return next((system for keyword, system in SYSTEM_NAME_RULES if keyword in name), '')


def import_devices(payload):
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('devices'), list):
        raise ValueError('Choose an avtrack network JSON export (version 1).')
    if len(payload['devices']) > 10000:
        raise ValueError('Import supports up to 10,000 devices per file.')
    spreadsheet = payload.get('source') == 'spreadsheet'
    row_numbers = payload.get('row_numbers') if spreadsheet else None
    if row_numbers is not None and (not isinstance(row_numbers, list) or len(row_numbers) != len(payload['devices']) or any(type(n) is not int or not 1 <= n <= 20050 for n in row_numbers)):
        raise ValueError('Invalid spreadsheet row numbers.')
    rows, numbers = [], []
    for index, value in enumerate(payload['devices'], 1):
        number = row_numbers[index - 1] if row_numbers else index
        if blank_import_row(value, FIELDS + ('channel_source', 'port')):
            continue
        try:
            if spreadsheet and isinstance(value, dict) and value.get('record_type', 'device') == 'device':
                value = dict(value)
                vlan = value.get('vlan')
                if isinstance(vlan, str):
                    vlan = vlan.strip()
                # Ignore text or decimal VLAN values; never invent a VLAN number.
                value['vlan'] = vlan if type(vlan) is int or (isinstance(vlan, str) and vlan.isascii() and vlan.isdigit()) else None
            row = validate(value)
            if row['record_type'] == 'device' and not row['discipline']:
                row['discipline'] = system_from_name(row['name'])
            rows.append(row)
            numbers.append(number)
        except ValueError as exc:
            raise ValueError(f'Device row {number}: {exc} Nothing was imported.') from None
    # A single transaction makes imports atomic. Existing records are never overwritten.
    with connect() as con:
        con.execute('BEGIN IMMEDIATE')
        existing = {identity for row in con.execute('SELECT record_type, ip, port FROM devices') if (identity := device_identity(row)) is not None}
        added = 0
        warnings = []
        seen = set()
        for index, row in enumerate(rows, 1):
            identity = device_identity(row)
            if identity is not None and identity in existing:
                if row['record_type'] == 'device' and (spreadsheet or identity in seen):
                    number = numbers[index - 1]
                    reason = 'already appears earlier in this file' if identity in seen else 'already exists in the inventory'
                    warnings.append(f"Row {number}: {row['name']} · {row['venue']} · duplicate IP {row['ip']} {reason}. Skipped; the first record was kept.")
                seen.add(identity)
                continue
            con.execute('INSERT INTO devices (' + ','.join(ALL_FIELDS) + ') VALUES (' + ','.join('?' for _ in ALL_FIELDS) + ')', [row[f] for f in ALL_FIELDS])
            if identity is not None:
                existing.add(identity)
                seen.add(identity)
            added += 1
    result = {'added': added, 'skipped': len(rows) - added}
    if spreadsheet or warnings:
        result['warnings'] = warnings
    return result


def validate_equipment(value):
    if not isinstance(value, dict):
        raise ValueError('Each inventory item must be an object.')
    row = {}
    for field in EQUIPMENT_FIELDS:
        if field == 'quantity':
            continue
        raw = value.get(field, '')
        if raw is None:
            raw = ''
        if not isinstance(raw, str):
            raise ValueError(f'{field.replace("_", " ").title()} must be text.')
        row[field] = raw.strip()
        if len(row[field]) > (2000 if field in ('description', 'notes') else 120):
            raise ValueError(f'{field.replace("_", " ").title()} is too long.')
    quantity = value.get('quantity')
    if quantity is None or quantity == '':
        row['quantity'] = None
    elif isinstance(quantity, bool) or not isinstance(quantity, (str, int)) or not str(quantity).isascii() or not str(quantity).isdigit() or not 0 <= int(quantity) <= 1000000:
        raise ValueError('Quantity must be a whole number from 0 to 1,000,000.')
    else:
        row['quantity'] = int(quantity)
    if not any(v is not None and v != '' for v in row.values()):
        raise ValueError('Provide at least one equipment detail.')
    return row


def equipment_inventory_id(value=1):
    if type(value) is int and 0 < value <= 9223372036854775807:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and 0 < int(value) <= 9223372036854775807:
        return int(value)
    raise ValueError('Choose an inventory using a positive whole number.')


def equipment_inventory_details(con, inventory_id):
    record = con.execute('SELECT * FROM equipment_inventories WHERE id=?', (equipment_inventory_id(inventory_id),)).fetchone()
    if record is None:
        raise LookupError('Inventory not found.')
    return dict(record)


def equipment_inventories():
    with connect() as con:
        return [dict(row) for row in con.execute('SELECT * FROM equipment_inventories ORDER BY name COLLATE NOCASE')]


def workspace_overview():
    with connect() as con:
        # One query keeps all three cards on the same database snapshot.
        row = con.execute("""SELECT
            (SELECT COUNT(*) FROM devices WHERE record_type='device') AS av_total,
            (SELECT COUNT(*) FROM devices WHERE record_type='device' AND ip_confirmed=1 AND ip NOT IN ('','DHCP')) AS av_validated,
            (SELECT COUNT(*) FROM devices WHERE record_type='iptv') AS iptv_total,
            (SELECT COUNT(*) FROM devices WHERE record_type='iptv' AND channel_source='Onboard') AS iptv_onboard,
            (SELECT COUNT(*) FROM devices WHERE record_type='iptv' AND channel_source='Satellite') AS iptv_satellite,
            (SELECT COUNT(*) FROM equipment) AS inventory_total,
            (SELECT COUNT(DISTINCT NULLIF(location,'')) FROM equipment) AS inventory_locations,
            (SELECT COUNT(*) FROM equipment_inventories) AS inventory_count""").fetchone()
        return dict(row)


def save_equipment_inventory(value, inventory_id=None):
    name = value.get('name') if isinstance(value, dict) else None
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ValueError('Enter an inventory name from 1 to 120 characters.')
    with connect() as con:
        if inventory_id is None:
            inventory_id = con.execute('INSERT INTO equipment_inventories (name) VALUES (?)', (name.strip(),)).lastrowid
        else:
            equipment_inventory_details(con, inventory_id)
            con.execute('UPDATE equipment_inventories SET name=? WHERE id=?', (name.strip(), inventory_id))
        return equipment_inventory_details(con, inventory_id)


def equipment_inventory(inventory_id=1):
    with connect() as con:
        equipment_inventory_details(con, inventory_id)
        return [dict(row) for row in con.execute('SELECT * FROM equipment WHERE inventory_id=? ORDER BY location COLLATE NOCASE, brand COLLATE NOCASE, model COLLATE NOCASE', (inventory_id,))]


def save_equipment(value, item_id=None):
    row = validate_equipment(value)
    inventory_id = equipment_inventory_id(value.get('inventory_id', 1))
    with connect() as con:
        equipment_inventory_details(con, inventory_id)
        if item_id is None:
            cursor = con.execute('INSERT INTO equipment (' + ','.join(EQUIPMENT_FIELDS) + ',inventory_id) VALUES (?,?,?,?,?,?,?,?)', [row[f] for f in EQUIPMENT_FIELDS] + [inventory_id])
            item_id = cursor.lastrowid
        else:
            unchanged = ' AND '.join(f'{field} IS ?' for field in EQUIPMENT_CONFIRM_FIELDS)
            cursor = con.execute('UPDATE equipment SET item_confirmed=CASE WHEN ' + unchanged +
                ' THEN item_confirmed ELSE 0 END, ' + ','.join(f+'=?' for f in EQUIPMENT_FIELDS) +
                ', updated_at=CURRENT_TIMESTAMP WHERE id=? AND inventory_id=?',
                [row[f] for f in EQUIPMENT_CONFIRM_FIELDS] + [row[f] for f in EQUIPMENT_FIELDS] + [item_id, inventory_id])
            if not cursor.rowcount:
                raise LookupError('Inventory item not found.')
        return dict(con.execute('SELECT * FROM equipment WHERE id=?', (item_id,)).fetchone())


def set_equipment_confirmation(item_id, value):
    if not isinstance(value, dict) or type(value.get('item_confirmed')) is not bool:
        raise ValueError('Choose whether this item has been located.')
    if any(field not in value for field in EQUIPMENT_CONFIRM_FIELDS):
        raise ValueError('Provide the current item details being confirmed.')
    row = validate_equipment(value)
    inventory_id = equipment_inventory_id(value.get('inventory_id', 1))
    with connect() as con:
        equipment_inventory_details(con, inventory_id)
        current = con.execute('SELECT * FROM equipment WHERE id=? AND inventory_id=?', (item_id, inventory_id)).fetchone()
        if current is None:
            raise LookupError('Inventory item not found.')
        matches = ' AND '.join(f'{field} IS ?' for field in EQUIPMENT_CONFIRM_FIELDS)
        cursor = con.execute('UPDATE equipment SET item_confirmed=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND ' + matches,
            [int(value['item_confirmed']), item_id] + [row[f] for f in EQUIPMENT_CONFIRM_FIELDS])
        if not cursor.rowcount:
            raise ValueError('This item changed. Refresh the inventory before confirming it.')
        return dict(con.execute('SELECT * FROM equipment WHERE id=?', (item_id,)).fetchone())


def equipment_import_confirmation(value):
    status = value.get('item_confirmed', 0)
    if status is None or status == '':
        return 0
    if type(status) in (bool, int) and status in (0, 1):
        return int(status)
    if isinstance(status, str) and status.strip().lower() in ('0', '1', 'true', 'false', 'located', 'not located', 'found', 'to find', 'pending'):
        return int(status.strip().lower() in ('1', 'true', 'located', 'found'))
    raise ValueError('Located status must be Located or Not located.')

def manage_equipment_location(payload):
    if not isinstance(payload, dict):
        raise ValueError('Choose a location action.')
    inventory_id = equipment_inventory_id(payload.get('inventory_id', 1))
    action = payload.get('action')
    source = payload.get('source')
    target = payload.get('target', '')
    if action not in ('delete', 'merge') or not isinstance(source, str) or not source.strip():
        raise ValueError('Choose a location and Delete or Merge.')
    if not isinstance(target, str) or len(target) > 120:
        raise ValueError('Choose a valid destination location.')
    if action == 'delete':
        target = ''
    elif not target.strip() or target == source:
        raise ValueError('Choose a different destination location.')
    with connect() as con:
        equipment_inventory_details(con, inventory_id)
        if not con.execute('SELECT 1 FROM equipment WHERE inventory_id=? AND location=?', (inventory_id, source)).fetchone():
            raise LookupError('Location no longer exists. Refresh and try again.')
        if action == 'merge' and not con.execute('SELECT 1 FROM equipment WHERE inventory_id=? AND location=?', (inventory_id, target)).fetchone():
            raise LookupError('Destination location no longer exists.')
        sources = [dict(row) for row in con.execute('SELECT * FROM equipment WHERE inventory_id=? AND location=?', (inventory_id, source))]
        count = len(sources)
        for row in sources:
            row['location'] = target
            identity = equipment_identity(row)
            matching = None
            if action == 'merge' and identity is not None and identity[0] == 'stock':
                matching = con.execute("SELECT * FROM equipment WHERE inventory_id=? AND id!=? AND serial_number='' AND brand=? COLLATE NOCASE AND model=? COLLATE NOCASE AND description=? AND location=? COLLATE NOCASE", (inventory_id, row['id'], row['brand'], row['model'], row['description'], target)).fetchone()
            if matching:
                # Unknown quantities remain unknown rather than implying a complete count.
                quantity = None if row['quantity'] is None or matching['quantity'] is None else row['quantity'] + matching['quantity']
                if quantity is not None and quantity > 1000000:
                    raise ValueError('Combined stock quantity exceeds 1,000,000. Nothing was changed.')
                notes = '\n'.join(dict.fromkeys(note for note in (matching['notes'], row['notes']) if note))
                con.execute('DELETE FROM equipment WHERE id=?', (row['id'],))
                con.execute('UPDATE equipment SET item_confirmed=0, location=?, quantity=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (target, quantity, notes, matching['id']))
            else:
                con.execute('UPDATE equipment SET item_confirmed=0, location=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (target, row['id']))
    return {'updated': count}


def equipment_identity(row):
    if row['serial_number']:
        return ('serial', row['serial_number'].casefold())
    if all(row[f] for f in ('brand', 'model', 'location')):
        return ('stock', row['brand'].casefold(), row['model'].casefold(), row['description'], row['location'].casefold())
    return None


def import_equipment(payload):
    if not isinstance(payload, dict) or payload.get('version') != 1 or not isinstance(payload.get('equipment'), list):
        raise ValueError('Choose an avtrack equipment JSON export.')
    if len(payload['equipment']) > 10000:
        raise ValueError('Import supports up to 10,000 inventory items.')
    inventory_id = equipment_inventory_id(payload.get('inventory_id', 1))
    rows = []
    for index, value in enumerate(payload['equipment'], 1):
        if blank_import_row(value, EQUIPMENT_FIELDS):
            continue
        try:
            rows.append(dict(validate_equipment(value), item_confirmed=equipment_import_confirmation(value)))
        except ValueError as exc:
            raise ValueError(f'Inventory row {index}: {exc} Nothing was imported.') from None
    identities = [identity for row in rows if (identity := equipment_identity(row)) is not None]
    if len(set(identities)) != len(identities):
        raise ValueError('Duplicate serial numbers or stock records in this file. Nothing was imported.')
    with connect() as con:
        equipment_inventory_details(con, inventory_id)
        existing = {identity for row in con.execute('SELECT * FROM equipment WHERE inventory_id=?', (inventory_id,)) if (identity := equipment_identity(dict(row))) is not None}
        added = 0
        for row in rows:
            identity = equipment_identity(row)
            if identity is not None and identity in existing:
                continue
            fields = EQUIPMENT_FIELDS + ('item_confirmed',)
            con.execute('INSERT INTO equipment (' + ','.join(fields) + ',inventory_id) VALUES (?,?,?,?,?,?,?,?,?)', [row[f] for f in fields] + [inventory_id])
            added += 1
            if identity is not None:
                existing.add(identity)
    return {'added': added, 'skipped': len(rows)-added}


def equipment_csv(rows=None):
    output = io.StringIO(newline='')
    fields = ('description', 'brand', 'model', 'serial_number', 'quantity', 'location', 'item_confirmed', 'notes')
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in equipment_inventory() if rows is None else rows:
        writer.writerow({f: ("'"+str(row[f]) if str(row[f]).startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else row[f]) for f in fields})
    return output.getvalue().encode('utf-8-sig')


def network_csv(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=ALL_FIELDS, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({f: ("'" + str(row[f]) if str(row[f]).startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else row[f]) for f in ALL_FIELDS})
    return output.getvalue().encode('utf-8-sig')


def selected_export_rows(rows, payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('ids'), list):
        raise ValueError('Choose the records to export using an IDs list.')
    ids = payload['ids']
    if len(ids) > 100000 or any(type(value) is not int or value < 1 for value in ids):
        raise ValueError('Export IDs must be positive whole numbers; choose up to 100,000 records.')
    by_id = {row['id']: row for row in rows}
    # Preserve the displayed order, ignore deleted records, and include each ID once.
    return [by_id[value] for value in dict.fromkeys(ids) if value in by_id]


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
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        exports = {
            '/api/export': (lambda rows: {'version':1, 'devices':rows}, inventory, 'application/json; charset=utf-8', 'broadcasthub-network.json'),
            '/api/export.csv': (network_csv, inventory, 'text/csv; charset=utf-8', 'broadcasthub-network.csv'),
            '/api/export.xlsx': (network_xlsx, inventory, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'broadcasthub-network.xlsx'),
            '/api/export.pdf': (network_pdf, inventory, 'application/pdf', 'broadcasthub-network.pdf'),
            '/api/equipment/export': (lambda rows: {'version':1, 'equipment':rows}, equipment_inventory, 'application/json; charset=utf-8', 'broadcasthub-equipment.json'),
            '/api/equipment/export.csv': (equipment_csv, equipment_inventory, 'text/csv; charset=utf-8', 'broadcasthub-equipment.csv'),
            '/api/equipment/export.xlsx': (equipment_xlsx, equipment_inventory, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'broadcasthub-equipment.xlsx'),
            '/api/equipment/export.pdf': (equipment_pdf, equipment_inventory, 'application/pdf', 'broadcasthub-equipment.pdf'),
        }
        if self.command in ('GET', 'POST') and path in exports:
            payload = self.body() if self.command == 'POST' else None
            generate, read, mime, filename = exports[path]
            equipment_export = path.startswith('/api/equipment/')
            named_inventory = None
            if equipment_export:
                inventory_id = equipment_inventory_id(payload.get('inventory_id', 1) if isinstance(payload, dict) else query.get('inventory_id', [1])[0])
                with connect() as con:
                    named_inventory = equipment_inventory_details(con, inventory_id)
                rows = read(inventory_id)
            else:
                rows = read()
            record_type = None
            if self.command == 'GET' and path.startswith('/api/export'):
                if 'record_type' in query:
                    record_type = query['record_type'][0]
                    if record_type not in ('device', 'iptv'):
                        raise ValueError('Choose AV devices or IPTV channels for this export.')
                    rows = [row for row in rows if row['record_type'] == record_type]
            if self.command == 'POST':
                if path.startswith('/api/export') and isinstance(payload, dict) and 'record_type' in payload:
                    record_type = payload['record_type']
                    if record_type not in ('device', 'iptv'):
                        raise ValueError('Choose AV devices or IPTV channels for this export.')
                    rows = [row for row in rows if row['record_type'] == record_type]
                    if 'ids' in payload:
                        rows = selected_export_rows(rows, payload)
                else:
                    rows = selected_export_rows(rows, payload)
            if record_type:
                suffix = filename.rsplit('.', 1)[1]
                filename = f'broadcasthub-{"av-devices" if record_type == "device" else "iptv-channels"}.{suffix}'
            if record_type and generate in (network_pdf, network_xlsx):
                return self.send(200, generate(rows, record_type=record_type), mime, filename)
            if named_inventory:
                suffix = filename.rsplit('.', 1)[1]
                slug = re.sub(r'[^a-z0-9]+', '-', named_inventory['name'].lower()).strip('-') or 'equipment'
                if named_inventory['id'] != 1 or named_inventory['name'] != 'Equipment inventory':
                    filename = f'broadcasthub-{slug}.{suffix}'
                if generate in (equipment_pdf, equipment_xlsx):
                    return self.send(200, generate(rows, inventory_name=named_inventory['name']), mime, filename)
                if path == '/api/equipment/export':
                    return self.send(200, {'version':1, 'inventory_name':named_inventory['name'], 'equipment':rows}, mime, filename)
            return self.send(200, generate(rows), mime, filename)
        if self.command == 'GET':
            if path == '/api/overview':
                return self.send(200, workspace_overview())
            if path == '/satellite-channels.json':
                return self.send(200, json.loads((ROOT / 'static' / 'satellite-channels.json').read_text()))
            if re.fullmatch(r'/channel-logos/[A-Za-z0-9_-]+\.[a-z]{2}\.png', path):
                logo = ROOT / 'static' / 'channel-logos' / path.rsplit('/', 1)[1]
                if logo.is_file():
                    return self.send(200, logo.read_bytes(), 'image/png')
            if path == '/api/equipment':
                return self.send(200, {'equipment': equipment_inventory(equipment_inventory_id(query.get('inventory_id', [1])[0]))})
            if path == '/api/equipment/inventories':
                return self.send(200, {'inventories': equipment_inventories()})
            if path == '/api/devices':
                return self.send(200, {'devices': inventory()})
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/equipment.js': ('equipment.js', 'text/javascript'), '/icon.svg': ('icon.svg', 'image/svg+xml'), '/favicon.svg': ('favicon.svg', 'image/svg+xml'), '/example-switcher.png': ('example-switcher.png', 'image/png'), '/fonts/Poppins-Regular.woff2': ('fonts/Poppins-Regular.woff2', 'font/woff2'), '/fonts/Poppins-Medium.woff2': ('fonts/Poppins-Medium.woff2', 'font/woff2'), '/fonts/Poppins-SemiBold.woff2': ('fonts/Poppins-SemiBold.woff2', 'font/woff2'), '/fonts/Poppins-Bold.woff2': ('fonts/Poppins-Bold.woff2', 'font/woff2')}
            assets.update({f'/fonts/{family}-Variable.woff2': (f'fonts/{family}-Variable.woff2', 'font/woff2')
                           for family in ('SpaceGrotesk', 'DMSans', 'JetBrainsMono')})
            if path in assets:
                file, mime = assets[path]
                return self.send(200, (ROOT / 'static' / file).read_bytes(), mime + '; charset=utf-8' if mime.startswith('text/') or mime == 'image/svg+xml' else mime)
        elif self.command == 'POST' and path == '/api/equipment/inventories':
            return self.send(201, save_equipment_inventory(self.body()))
        elif self.command == 'PUT' and path.startswith('/api/equipment/inventories/'):
            inventory_id = equipment_inventory_id(path.removeprefix('/api/equipment/inventories/'))
            return self.send(200, save_equipment_inventory(self.body(), inventory_id))
        elif self.command == 'POST' and path == '/api/equipment':
            return self.send(201, save_equipment(self.body()))
        elif self.command == 'POST' and path == '/api/equipment/locations':
            return self.send(200, manage_equipment_location(self.body()))
        elif self.command == 'POST' and path == '/api/equipment/import':
            return self.send(200, import_equipment(self.body()))
        elif self.command == 'POST' and path.startswith('/api/equipment/') and path.endswith('/confirm'):
            try:
                item_id = int(path.removeprefix('/api/equipment/').removesuffix('/confirm'))
            except ValueError:
                raise LookupError('Inventory item not found.') from None
            return self.send(200, set_equipment_confirmation(item_id, self.body()))
        elif self.command == 'POST' and path == '/api/devices/batch-delete':
            payload = self.body()
            ids = payload.get('ids') if isinstance(payload, dict) else None
            if not isinstance(ids, list) or not ids or len(ids) > 10000 or any(type(value) is not int or value < 1 for value in ids):
                raise ValueError('Choose between 1 and 10,000 device IDs, using positive whole numbers.')
            with connect() as con:
                deleted = con.executemany('DELETE FROM devices WHERE id=?', ((value,) for value in dict.fromkeys(ids))).rowcount
            return self.send(200, {'deleted': deleted})
        elif self.command in ('PUT','DELETE') and path.startswith('/api/equipment/'):
            try:
                item_id = int(path.removeprefix('/api/equipment/'))
            except ValueError:
                raise LookupError('Inventory item not found.') from None
            if self.command == 'PUT':
                return self.send(200, save_equipment(self.body(), item_id))
            payload = self.body()
            if not isinstance(payload, dict):
                raise ValueError('Choose the inventory item to delete.')
            inventory_id = equipment_inventory_id(payload.get('inventory_id', 1))
            with connect() as con:
                equipment_inventory_details(con, inventory_id)
                if not con.execute('DELETE FROM equipment WHERE id=? AND inventory_id=?', (item_id, inventory_id)).rowcount:
                    raise LookupError('Inventory item not found.')
            return self.send(200, {'deleted':item_id})
        elif self.command == 'POST' and path == '/api/devices':
            return self.send(201, save_device(self.body()))
        elif self.command == 'POST' and path == '/api/spreadsheet-preview':
            return self.send(200, spreadsheet_preview(self.body()))
        elif self.command == 'POST' and path == '/api/import':
            return self.send(200, import_devices(self.body()))
        elif self.command == 'POST' and path.startswith('/api/devices/') and path.endswith('/notes'):
            try:
                device_id = int(path.removeprefix('/api/devices/').removesuffix('/notes'))
            except ValueError:
                raise LookupError('Device not found.') from None
            return self.send(200, set_device_notes(device_id, self.body()))
        elif self.command == 'POST' and path.startswith('/api/devices/') and path.endswith('/system'):
            try:
                device_id = int(path.removeprefix('/api/devices/').removesuffix('/system'))
            except ValueError:
                raise LookupError('Device not found.') from None
            return self.send(200, set_device_system(device_id, self.body()))
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
        except sqlite3.IntegrityError as exc:
            if 'equipment_inventories.name' in str(exc):
                message = 'An inventory with this name already exists.'
            elif 'Duplicate AV IP' in str(exc):
                message = 'This IP address already exists in AV devices. Each AV IP must be unique, even across VLANs.'
            else:
                message = 'This assignment, serial number, or stock record already exists in the inventory.'
            self.send(409, {'error': message})
        except Exception:
            self.log_error('Internal request error')
            self.send(500, {'error': 'Could not complete the request. Check server storage and try again.'})

    do_GET = do_POST = do_PUT = do_DELETE = handle_request


if __name__ == '__main__':
    with connect():
        pass
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8000'))
    print(f'broadcasthub listening on {host}:{port}', flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
