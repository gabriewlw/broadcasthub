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
            confirm = page.get_by_role('button', name='Confirm IP for ATEM video switcher', exact=True)
            assert 'pending' in confirm.get_attribute('class')
            confirm.click()
            green = page.get_by_role('button', name='IP confirmed for ATEM video switcher', exact=True)
            green.wait_for()
            assert 'confirmed' in green.get_attribute('class')
            assert green.is_disabled()
            page.reload()
            page.get_by_role('button', name='IP confirmed for ATEM video switcher', exact=True).wait_for()
            assert app.inventory()[0]['ip_confirmed'] == 1

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
            assert page.get_by_role('button', name='IP confirmed for ATEM main', exact=True).is_visible()
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
            # IPTV has separate records, source choices, and multicast support.
            page.get_by_role('tab', name='IPTV channels', exact=True).click()
            assert page.locator('#total').inner_text() == '0'
            page.get_by_role('button', name='Add channel', exact=True).click()
            page.locator('[name=name]').fill('Ship information')
            page.locator('[name=ip]').fill('239.1.1.10')
            page.locator('[name=port]').fill('1234')
            page.get_by_role('button', name='Save channel', exact=True).click()
            assert 'Choose Onboard or Satellite' in page.locator('#form-error').inner_text()
            page.locator('#form-source-buttons').get_by_role('button', name='Onboard', exact=True).click()
            page.get_by_role('button', name='Save channel', exact=True).click()
            page.get_by_role('button', name='Edit Ship information').wait_for()
            assert page.locator('.device-row').count() == 1
            assert page.locator('.ip-confirm').count() == 0
            assert page.locator('#venue-filter-group').is_hidden()
            assert page.locator('#vlan-filter-label').is_hidden()
            assert 'Port 1234' in page.locator('.device-row').inner_text()
            page.locator('#source-buttons').get_by_role('button', name='Satellite', exact=True).click()
            assert page.locator('#no-results').is_visible()
            page.get_by_role('button', name='Clear', exact=True).click()
            page.get_by_role('button', name='Add channel', exact=True).click()
            page.locator('[name=name]').fill('BBC News')
            page.locator('[name=ip]').fill('239.1.1.11')
            page.locator('[name=port]').fill('1234')
            page.locator('#form-source-buttons').get_by_role('button', name='Satellite', exact=True).click()
            page.get_by_role('button', name='Save channel', exact=True).click()
            page.get_by_role('button', name='Edit BBC News').wait_for()
            assert page.locator('#system-count').inner_text() == '1 / 1'
            page.get_by_role('button', name='Edit BBC News').click()
            assert page.locator('#form-source-buttons').get_by_role('button', name='Satellite', exact=True).get_attribute('aria-pressed') == 'true'
            assert page.locator('[name=port]').input_value() == '1234'
            assert page.locator('#venue-field').is_hidden()
            assert page.locator('#vlan-field').is_hidden()
            page.get_by_role('button', name='Cancel', exact=True).click()
            path = Path(temp) / 'iptv.csv'
            path.write_text('Channel,IP Address,Port,Source\nMovie channel,239.1.1.12,5000,Onboard\n')
            page.locator('#import-file').set_input_files(str(path))
            page.locator('#map-channel_source').wait_for()
            assert page.locator('#default-record_type').input_value() == 'iptv'
            page.locator('#confirm-import').click()
            page.get_by_role('button', name='Edit Movie channel').wait_for()
            assert page.locator('.device-row').count() == 3
            page.screenshot(path='/tmp/iptracking-iptv-mobile.png', full_page=True)
            page.get_by_role('tab', name='AV devices', exact=True).click()
            assert page.locator('.device-row').count() == 3
            assert page.get_by_role('button', name='Edit Ship information').count() == 0
            page.get_by_role('tab', name='IPTV channels', exact=True).click()
            assert page.get_by_role('button', name='Edit Ship information').is_visible()
            assert page.locator('.ip-confirm').count() == 0
            # General equipment inventory is separate and has no network fields.
            page.get_by_role('tab', name='Equipment inventory', exact=True).click()
            page.locator('#equipment-empty').wait_for(state='visible')
            page.locator('#add-device').click()
            page.locator('#equipment-form [name=brand]').fill('Blackmagic Design')
            page.locator('#equipment-form [name=model]').fill('ATEM Mini Pro')
            page.locator('#equipment-form [name=description]').fill('HDMI switcher')
            page.locator('#equipment-form [name=serial_number]').fill('ATEM-001')
            page.locator('#equipment-form [name=quantity]').fill('1')
            page.locator('#equipment-form [name=location]').fill('Broadcast center')
            page.locator('#equipment-form [name=notes]').fill('With PSU')
            page.get_by_role('button', name='Save equipment', exact=True).click()
            page.get_by_role('button', name='Edit equipment Blackmagic Design ATEM Mini Pro').wait_for()
            assert page.locator('#equipment-units').inner_text() == '1'
            assert page.locator('#equipment-rows tr').count() == 1
            assert page.locator('#inventory').is_hidden()
            page.locator('#equipment-search').fill('missing')
            assert page.locator('#equipment-no-results').is_visible()
            page.locator('#equipment-clear').click()
            page.get_by_role('button', name='Edit equipment Blackmagic Design ATEM Mini Pro').click()
            page.locator('#equipment-form [name=quantity]').fill('2')
            page.locator('#equipment-dialog').get_by_role('button', name='Save changes', exact=True).click()
            page.locator('#equipment-dialog').wait_for(state='hidden')
            page.wait_for_function("() => document.getElementById('equipment-units').textContent === '2'")
            path = Path(temp) / 'equipment.csv'
            path.write_text('BRAND,MODEL,DESCRIPTION,SERIAL NUMBER,QUANTITY,LOCATION,NOTES\nNeutrik,XLR,Audio cable,,20,Storeroom,Spare stock\n')
            page.locator('#import-file').set_input_files(str(path))
            page.locator('#map-brand').wait_for()
            page.locator('#confirm-import').click()
            page.get_by_role('button', name='Edit equipment Neutrik XLR').wait_for()
            assert page.locator('#equipment-units').inner_text() == '22'
            page.locator('#equipment-location-filter').select_option('Storeroom')
            assert page.locator('#equipment-rows tr').count() == 1
            page.locator('#equipment-clear').click()
            with page.expect_download() as download:
                page.locator('#equipment-panel').get_by_role('link', name='JSON ↓').click()
            equipment_export = json.loads(Path(download.value.path()).read_text())
            assert len(equipment_export['equipment']) == 2
            page.get_by_role('button', name='Delete equipment Neutrik XLR').click()
            page.get_by_role('button', name='Delete equipment', exact=True).click()
            page.wait_for_function("() => document.getElementById('equipment-units').textContent === '2'")
            path = Path(temp) / 'equipment.json'
            path.write_text(json.dumps(equipment_export))
            page.locator('#import-file').set_input_files(str(path))
            page.get_by_role('button', name='Edit equipment Neutrik XLR').wait_for()
            page.get_by_role('tab', name='IPTV channels', exact=True).click()
            assert page.locator('.device-row').count() == 3
            page.get_by_role('tab', name='AV devices', exact=True).click()
            assert page.locator('.device-row').count() == 3
            page.get_by_role('tab', name='Equipment inventory', exact=True).click()
            page.get_by_role('button', name='Edit equipment Neutrik XLR').wait_for()
            assert page.locator('#equipment-rows tr').count() == 2
            assert 'Broadcast Hub' in page.title()
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
