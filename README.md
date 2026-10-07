# IP Tracking

A responsive AV device inventory for shipboard venues. Use the same web app in iPhone Safari and on a computer; all connected browsers share one SQLite database. No offline mode or App Store installation is required.

## Run

Requires Python 3.12 or newer. There are no third-party runtime dependencies or build steps.

```sh
cd /workspace/iptracking
python3 app.py
```

The default bind address is `127.0.0.1`, port `8000`. For a computer or private server reachable by your iPhone on the same network:

```sh
HOST=0.0.0.0 PORT=8000 python3 app.py
```

Open the server's actual IP address or hostname and port in Safari, for example `http://YOUR-SERVER-IP:8000`. On an iPhone, Safari → Share → Add to Home Screen provides quick access. Localhost on your phone points to the phone, not the server. The server must remain running and both clients need network access to it. Ship network VLAN isolation may prevent phone-to-server access; coordinate routing/firewall rules with the ship's network team.

This first version has no user authentication. Run it on a trusted private network for evaluation. Before Internet deployment, place it behind HTTPS and an authenticated reverse proxy/access gateway. The included Python HTTP server is intended for development or private evaluation, not direct public hosting. Cross-origin writes are rejected, but this does not replace access control.

## Workflow

- Add a device's name, category, venue, system, IPv4 address, VLAN, and optional notes.
- Search device names, addresses, categories, venues, systems, VLANs, or notes. Combine venue, system, category, and VLAN filters.
- Edit records or delete them with confirmation.
- Use **Fill ATEM example** on an empty inventory to populate the form with `10.24.176.66`, Liquid Lounge, Video switcher, Video, VLAN `1500`. This does not insert sample data until you click Save.
- IP validation checks IPv4 format and rejects loopback, multicast, unspecified, and limited broadcast addresses. VLANs must be integers from 1 to 4094. An IP/VLAN pair must be unique; the same address is allowed in different VLANs.
- Validation does not ping devices, infer subnets, verify a gateway, or detect directed broadcast/network addresses without a subnet mask. A stored device may be powered off or unreachable.

## Files and backup

**JSON ↓** exports the entire inventory in the app's version-1 transfer format. On either phone or computer, **Import JSON** restores records from that export. Imports validate the complete file before inserting; existing IP/VLAN pairs are skipped and never overwritten. Duplicate pairs inside an import file or invalid records reject the whole file. IDs are assigned by the receiving database. Imports accept at most 10,000 records and 5 MB per file.

**CSV ↓** exports the entire inventory for spreadsheet use. CSV is not an import format. Formula-like text is escaped for spreadsheet safety. Exports include all devices, regardless of the current filters.

The database defaults to `data/inventory.sqlite3`, excluded from Git. Set `IPTRACKING_DB` to a persistent database location when hosting. Do not use temporary container storage for your only copy. For a consistent live backup, use SQLite's backup API rather than copying an active WAL database:

```sh
python3 - <<'PY'
import sqlite3
from app import connect
with connect() as source, sqlite3.connect('/tmp/iptracking-backup.sqlite3') as backup:
    source.backup(backup)
PY
```

Download the backup to safe storage or routinely export JSON. Startup is idempotent and does not seed or erase inventory.

## Validation

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

Seven backend integration tests cover HTTP CRUD, persistence, invalid IPs/VLANs, duplicate assignments, atomic import, export round trips, CSV formula escaping, static routes, and cross-origin write rejection. Node is only needed for the optional JavaScript syntax check.

Optional browser check (requires Python Playwright and Chromium):

```sh
python3 tests/browser_check.py
```

The browser check uses an isolated temporary database and exercises the example device, every filter, validation errors, edit/delete, JSON download/upload, reload persistence, mobile/desktop layouts, and JavaScript errors. It uses system Chromium when available. Its mobile viewport check is not a physical iPhone/Safari test.
