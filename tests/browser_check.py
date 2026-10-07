"""Optional end-to-end check: requires Playwright and Chromium."""
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import Workbook
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temp:
    app.DB_PATH = Path(temp) / 'inventory.sqlite3'
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which("chromium") or None)
            context = browser.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True, device_scale_factor=2)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            page.get_by_role('button', name='Fill ATEM example').click()
            page.get_by_role('button', name='Save device', exact=True).click()
            page.locator('.device-name').filter(has_text='ATEM video switcher').wait_for()
            assert app.inventory()[0]['ip'] == '10.24.176.66'
            assert page.locator('#total').inner_text() == '1'
            page.locator('#system-buttons').get_by_role('button', name='Audio', exact=True).click()
            assert page.locator('#no-results').is_visible()
            page.get_by_role('button', name='Clear', exact=True).click()
            page.locator('#venue-buttons').get_by_role('button', name='Liquid Lounge', exact=True).click()
            page.locator('#category-filter').select_option('Video switcher')
            page.locator('#vlan-filter').select_option('1500')
            assert page.locator('.device-row').count() == 1
            page.locator('#search').fill('not found')
            assert page.locator('#no-results').is_visible()
            page.locator('#search').fill('10.24.176.66')
            assert page.locator('.device-row').count() == 1
            page.get_by_role('button', name='Edit ATEM video switcher', exact=True).click()
            page.locator('[name=ip]').fill('10.24.176.999')
            page.get_by_role('button', name='Save changes').click()
            page.locator('#form-error').wait_for(state='visible')
            assert 'valid IPv4' in page.locator('#form-error').inner_text()
            page.locator('[name=ip]').fill('10.24.176.66')
            page.locator('[name=name]').fill('ATEM main')
            page.get_by_role('button', name='Save changes').click()
            page.get_by_role('button', name='Edit ATEM main').wait_for()
            with page.expect_download() as download:
                page.get_by_role('link',name='JSON ↓').click()
            payload = json.loads(Path(download.value.path()).read_text())
            assert payload['devices'][0]['name'] == 'ATEM main'
            page.get_by_role('button',name='Delete ATEM main').click()
            page.get_by_role('button',name='Delete device',exact=True).click()
            page.locator('#empty').wait_for(state='visible')
            path = Path(temp) / 'inventory.json'
            path.write_text(json.dumps(payload))
            page.locator('#import-file').set_input_files(str(path))
            page.get_by_role('button',name='Edit ATEM main').wait_for()
            page.reload()
            page.get_by_role('button',name='Edit ATEM main').wait_for()
            # A second venue verifies combined button filters and form choices.
            page.get_by_role('button', name='Add device', exact=True).click()
            page.locator('[name=name]').fill('Audio console')
            page.locator('[name=category]').fill('Audio console')
            page.locator('#form-system-buttons').get_by_role('button', name='Audio', exact=True).click()
            page.locator('#form-venue-buttons').get_by_role('button', name='Liquid Lounge', exact=True).click()
            assert page.locator('[name=venue]').input_value() == 'Liquid Lounge'
            page.locator('[name=venue]').fill('Theater')
            assert page.locator('#form-venue-buttons button').get_attribute('aria-pressed') == 'false'
            page.locator('[name=ip]').fill('10.24.176.67')
            page.locator('[name=vlan]').fill('1500')
            page.get_by_role('button', name='Save device', exact=True).click()
            theater = page.locator('#venue-buttons').get_by_role('button', name='Theater', exact=True)
            theater.wait_for()
            theater.click()
            page.locator('#system-buttons').get_by_role('button', name='Audio', exact=True).click()
            assert theater.get_attribute('aria-pressed') == 'true'
            assert page.locator('.device-row').count() == 1
            assert page.locator('.device-name').inner_text() == 'Audio console'
            page.locator('#system-buttons').get_by_role('button', name='Video', exact=True).click()
            assert page.locator('#no-results').is_visible()
            page.locator('#venue-buttons').get_by_role('button', name='All venues', exact=True).click()
            assert page.locator('.device-name').inner_text() == 'ATEM main'
            page.get_by_role('button', name='Clear', exact=True).click()
            assert page.locator('.device-row').count() == 2
            assert page.locator('#system-buttons').get_by_role('button', name='All systems', exact=True).get_attribute('aria-pressed') == 'true'
            # Editing reflects the stored selection in both form button groups.
            page.get_by_role('button', name='Edit ATEM main').click()
            assert page.locator('#form-system-buttons').get_by_role('button', name='Video', exact=True).get_attribute('aria-pressed') == 'true'
            assert page.locator('#form-venue-buttons').get_by_role('button', name='Liquid Lounge', exact=True).get_attribute('aria-pressed') == 'true'
            page.get_by_role('button', name='Cancel', exact=True).click()
            # Import an existing-style workbook with a cover sheet and custom columns.
            book = Workbook()
            book.active.title = 'Cover'
            book.active.append(['AV list'])
            sheet = book.create_sheet('Network')
            sheet.append(['Equipment list'])
            sheet.append(['Equipment', 'Address on network', 'VLAN ID', 'Room', 'Department'])
            sheet.append(['Excel camera', '10.24.176.68', 1500, 'Liquid Lounge', 'video'])
            path = Path(temp) / 'devices.xlsx'
            book.save(path)
            page.locator('#import-file').set_input_files(str(path))
            page.locator('#sheet-choice').get_by_role('option', name='Network').wait_for(state='attached')
            page.locator('#sheet-choice').select_option('Network')
            page.locator('#header-row').fill('2')
            assert page.locator('#confirm-import').is_disabled()
            page.get_by_role('button', name='Reload preview').click()
            page.locator('#map-ip').get_by_role('option', name='2. Address on network', exact=True).wait_for(state='attached')
            page.locator('#map-ip').select_option('1')
            page.locator('#default-category').fill('Camera')
            assert 'Excel camera' in page.locator('#spreadsheet-preview').inner_text()
            assert len(app.inventory()) == 2  # Preview never writes.
            page.screenshot(path='/tmp/iptracking-excel-mobile.png', full_page=True)
            page.locator('#confirm-import').click()
            page.get_by_role('button', name='Edit Excel camera').wait_for()
            assert len(app.inventory()) == 3
            assert next(d for d in app.inventory() if d['name'] == 'Excel camera')['category'] == 'Camera'
            # CSV defaults and an invalid address must leave all existing records intact.
            path = Path(temp) / 'extra.csv'
            path.write_text('Device,IP Address,VLAN\nCSV device,invalid,1500\n')
            page.locator('#import-file').set_input_files(str(path))
            page.locator('#default-venue').wait_for()
            page.locator('#default-venue').fill('Theater')
            page.locator('#confirm-import').click()
            page.locator('#spreadsheet-error').wait_for(state='visible')
            assert 'valid IPv4' in page.locator('#spreadsheet-error').inner_text()
            assert len(app.inventory()) == 3
            page.get_by_role('button', name='Cancel', exact=True).click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path='/tmp/iptracking-mobile.png', full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path='/tmp/iptracking-desktop.png', full_page=True)
            assert not errors, errors
            browser.close()
            print('PASS: mobile create, all filters, validation, edit, export, delete, import, reload persistence; desktop/mobile overflow; no JS errors.')
    finally:
        server.shutdown()
        server.server_close()
