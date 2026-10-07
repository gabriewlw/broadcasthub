# IP Tracking

A responsive AV device inventory for shipboard venues. Use the same web app in iPhone Safari and on a computer; all connected browsers share one SQLite database. No offline mode or App Store installation is required.

## Run

Requires Python 3.12 or newer. Install the pinned Excel-reading dependencies once; no frontend build is needed.

```sh
cd /path/to/iptracking
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

On Windows, open a terminal in the extracted project folder and run `py -m pip install -r requirements.txt`, then `py app.py`. On Mac/Linux, replace `/path/to/iptracking` above with the actual downloaded folder path. In the cloud workspace it is `/workspace/iptracking`.

The default bind address is `127.0.0.1`, port `8000`. For a computer or private server reachable by your iPhone on the same network:

```sh
HOST=0.0.0.0 PORT=8000 .venv/bin/python app.py
```

Open the server's actual IP address or hostname and port in Safari, for example `http://YOUR-SERVER-IP:8000`. On an iPhone, Safari → Share → Add to Home Screen provides quick access. Localhost on your phone points to the phone, not the server. The server must remain running and both clients need network access to it. Ship network VLAN isolation may prevent phone-to-server access; coordinate routing/firewall rules with the ship's network team.

This first version has no user authentication. Run it on a trusted private network for evaluation. Before Internet deployment, place it behind HTTPS and an authenticated reverse proxy/access gateway. The included Python HTTP server is intended for development or private evaluation, not direct public hosting. Cross-origin writes are rejected, but this does not replace access control.

## Workflow

- Use the **AV devices** tab for equipment and the **IPTV channels** tab for channel addresses. Existing inventory remains in AV devices.
- Add a device's name, category, venue, system, IPv4 address, VLAN, and optional notes.
- In IPTV, click **Add channel**, enter its name, IPv4 address, and stream port (1–65535), then choose **Onboard** or **Satellite**. Filter the lineup by source or search. IPTV does not use venue, VLAN, or manual confirmation. Each IP/port endpoint is unique; one IP can use multiple ports. Existing channels are preserved without inventing a port; edit any record marked Port not set to complete it. Channel addresses may be unicast or multicast (for example `239.1.1.10`); ordinary AV devices still require unicast. This tracks addresses, not stream playback or reception. The yellow/green manual confirmation applies only to AV devices.
- Search device names, addresses, categories, venues, systems, VLANs, or notes. Tap venue and system buttons to combine filters with category and VLAN. In the device form, select a system button and choose a saved venue button or type a new venue.
- Edit records or delete them with confirmation.
- Each AV device starts with a yellow **Confirm IP** button. Click it after reviewing the assignment to save a green **IP confirmed** status. This is manual review, not a ping or reachability test. Confirmation persists in the database. Editing the IP address or VLAN resets it to yellow; other edits preserve it. Existing databases upgrade automatically, and newly imported records start unconfirmed even if the export contains confirmation metadata.
- Use **Fill ATEM example** on an empty inventory to populate the form with `10.24.176.66`, Liquid Lounge, Video switcher, Video, VLAN `1500`. This does not insert sample data until you click Save.
- IP validation checks IPv4 format and rejects loopback, unspecified, and limited broadcast addresses. Multicast is supported for IPTV channels only. VLANs must be integers from 1 to 4094. An IP/VLAN pair must be unique; the same address is allowed in different VLANs.
- Validation does not ping devices, infer subnets, verify a gateway, or detect directed broadcast/network addresses without a subnet mask. A stored device may be powered off or unreachable.

## Files and backup

**JSON ↓** exports the entire inventory in the app's version-1 transfer format. On either phone or computer, **Import data** restores records from that export. Imports validate the complete file before inserting; existing IP/VLAN pairs are skipped and never overwritten. Duplicate pairs inside an import file or invalid records reject the whole file. IDs are assigned by the receiving database. Imports accept at most 10,000 records and 5 MB per file.

**Import data** also accepts Excel **.xlsx** and UTF-8 **.csv** files from your phone or computer. Choose a worksheet and header row (1–50), then click **Reload preview**. Match columns to device name, category, venue, system, IP, VLAN, and notes. Common headers such as Equipment, IP Address, Location, and VLAN ID are matched automatically. Defaults fill missing columns or blank cells; provide a venue/VLAN default if your sheet does not have one. The first three mapped rows are shown before confirmation. Previewing never writes to the database. System names are case-insensitive; “Lights” maps to Lighting. Imported records must pass the same validation as manual entries. IPTV requires a channel name, IP, port and source; venue and VLAN are ignored for IPTV. Existing assignments are skipped; invalid rows and duplicate assignments inside the file reject the complete import.

Save older **.xls** files as **.xlsx** in Excel first. Password-protected files are unsupported. The chosen header row must contain column names, with device rows below it; completely blank rows are ignored. Limits: 5 MB upload, 10,000 devices, 50 columns, and 30 MB expanded workbook size. Excel formulas are never evaluated; only Excel's cached values are read. Recalculate and save the workbook in Excel if formula-derived cells are empty. Uploaded spreadsheets are parsed in memory and not retained as files.

**CSV ↓** exports the entire inventory for spreadsheet use and can also be imported through column mapping. Formula-like text is escaped for spreadsheet safety. Exports include both AV devices and IPTV channels, regardless of the current tab or filters. JSON and CSV include `record_type` (`device` or `iptv`) , `channel_source` (`Onboard` or `Satellite` for IPTV), and `port` (IPTV only). Old JSON exports default to AV devices. When importing a spreadsheet in the IPTV tab, the inventory type defaults to `iptv`, category to IPTV channel, and system to Video; map channel source and port columns or supply defaults. Legacy IPTV JSON exports lacking ports need ports added before re-import. Imports skip existing AV IP/VLAN assignments and IPTV IP/port endpoints. Identical IP addresses can exist in separate inventories.

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
.venv/bin/python -m unittest discover -s tests -v
node --check static/app.js
```

Nineteen backend and spreadsheet tests cover HTTP CRUD, persistence, invalid IPs/VLANs, duplicate assignments, atomic import, export round trips, CSV formula escaping, static routes, cross-origin write rejection, multi-sheet Excel parsing, header rows, numeric VLANs, CSV parsing, spreadsheet preview/import, confirmation persistence, assignment resets, legacy database migration, IPTV source validation, multicast support, mixed-inventory transfers, IPTV port ranges and endpoint uniqueness, and migration of legacy channels without ports. Node is only needed for the optional JavaScript syntax check.

Optional browser check (requires Python Playwright and Chromium):

```sh
.venv/bin/python tests/browser_check.py
```

Install Playwright in the virtual environment (`.venv/bin/python -m pip install playwright`) and use system Chromium or install it through Playwright.

The browser check uses an isolated temporary database and exercises the example device, every filter, validation errors, edit/delete, JSON download/upload, reload persistence, mobile/desktop layouts, Excel worksheet selection, manual column mapping, defaults, rejected CSV imports, and JavaScript errors. It uses system Chromium when available. Its mobile viewport check is not a physical iPhone/Safari test.
