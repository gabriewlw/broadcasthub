"""Optional equipment CSV/location/found workflow check with Playwright."""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temp:
    app.DB_PATH = Path(temp) / 'inventory.sqlite3'
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            page.locator('#equipment-tab').click()
            page.locator('#equipment-empty').wait_for(state='visible')
            csv_file = Path(temp) / 'equipment.csv'
            csv_file.write_text('Item,Brand,Model,Serial number,Quantity,Location,Notes\n'
                                'HDMI switcher,Blackmagic Design,ATEM Mini Pro,ATEM-01,1,Broadcast center,With PSU\n'
                                'Handheld microphone,Shure,SM58,MIC-01,1,Main lounge,With cable\n'
                                'Audio cable,Neutrik,XLR,,20,Main lounge,Spare stock\n')
            page.locator('#import-file').set_input_files(str(csv_file))
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            assert page.locator('#map-description').input_value() == '0'
            page.locator('#confirm-import').click()
            for index in range(3):
                page.locator('#row-review-dialog').wait_for(state='visible')
                progress = page.locator('#row-review-progress').inner_text()
                page.locator('#accept-review-row').click()
                if index < 2:
                    page.wait_for_function('previous => document.getElementById("row-review-progress").textContent !== previous', arg=progress)
                else:
                    page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            page.wait_for_function("() => document.querySelectorAll('#equipment-rows tr').length === 3")
            assert all(row['item_confirmed'] == 0 for row in app.equipment_inventory())
            assert page.locator('#equipment-table th').all_text_contents() == ['Item','Brand','Model','Serial number','Quantity','Location','Found','Notes','Actions']
            page.locator('#equipment-location-filter').select_option('Main lounge')
            assert page.locator('#equipment-rows tr').count() == 2
            microphone = page.locator('#equipment-rows tr').filter(has_text='Handheld microphone')
            microphone.locator('.equipment-confirm').check()
            page.wait_for_function("() => document.getElementById('equipment-found').textContent === '1'")
            assert microphone.locator('.equipment-confirm-label').get_attribute('class').endswith('confirmed')
            assert page.locator('#equipment-rows .row-select:checked').count() == 0
            page.locator('#equipment-refresh').click()
            page.wait_for_function("() => !document.getElementById('equipment-refresh').disabled")
            assert microphone.locator('.equipment-confirm').is_checked()
            page.locator('#equipment-status-buttons').get_by_role('button', name='To find', exact=True).click()
            assert page.locator('#equipment-rows tr').count() == 1
            assert 'Audio cable' in page.locator('#equipment-rows').inner_text()
            page.locator('#equipment-status-buttons').get_by_role('button', name='Found', exact=True).click()
            assert page.locator('#equipment-rows tr').count() == 1
            microphone.locator('.equipment-confirm').click()
            page.wait_for_function("() => document.getElementById('equipment-found').textContent === '0'")
            assert page.locator('#equipment-no-results').is_visible()
            page.locator('#equipment-clear').click()
            page.locator('#equipment-location-filter').select_option('Main lounge')
            microphone.get_by_role('button', name='Edit equipment Shure SM58', exact=True).click()
            page.locator('#equipment-form [name=notes]').fill('Located beside the stage')
            page.locator('#save-equipment').click()
            page.locator('#equipment-dialog').wait_for(state='hidden')
            # Hold the confirmation request to prove that an immediate export
            # waits for the save and includes the completed found state.
            page.evaluate("""() => {
                const original = window.fetch;
                window.fetch = async (...args) => {
                    if (String(args[0]).endsWith('/confirm')) {
                        await new Promise(resolve => { window.releaseConfirmation = resolve; });
                    }
                    return original(...args);
                };
            }""")
            microphone.locator('.equipment-confirm').check()
            page.locator('#equipment-panel .export-dropdown summary').click()
            page.locator('#equipment-export-scope').select_option('filtered')
            with page.expect_download() as download:
                page.locator('#equipment-panel').get_by_role('link', name='JSON ↓', exact=True).click()
                page.evaluate('window.releaseConfirmation()')
            exported = json.loads(Path(download.value.path()).read_text())['equipment']
            assert len(exported) == 2
            assert {row['location'] for row in exported} == {'Main lounge'}
            assert next(row for row in exported if row['model'] == 'SM58')['item_confirmed'] == 1
            page.locator('#equipment-panel .export-dropdown summary').click()
            page.locator('#equipment-export-scope').select_option('filtered')
            with page.expect_download() as download:
                page.locator('#equipment-panel').get_by_role('link', name='PDF ↓', exact=True).click()
            pdf = Path(download.value.path()).read_bytes()
            if shutil.which('pdftotext'):
                text = subprocess.run(['pdftotext','-','-'],input=pdf,capture_output=True,check=True).stdout.decode()
                assert 'Location: Main lounge' in text
                assert 'Broadcast center' not in text
                assert 'Found' in text and 'To find' in text
            page.reload()
            page.locator('#equipment-tab').click()
            page.wait_for_function("() => !document.getElementById('equipment-refresh').disabled")
            assert microphone.locator('.equipment-confirm').is_checked()
            microphone.get_by_role('button', name='Edit equipment Shure SM58', exact=True).click()
            page.locator('#equipment-form [name=location]').fill('Broadcast center')
            page.locator('#save-equipment').click()
            page.locator('#equipment-dialog').wait_for(state='hidden')
            page.wait_for_function("() => document.getElementById('equipment-found').textContent === '0'")
            assert not microphone.locator('.equipment-confirm').is_checked()
            for width in [1440,900,390,320]:
                page.set_viewport_size({'width':width,'height':1000})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                assert microphone.locator('.equipment-confirm').is_visible()
                if width > 900:
                    assert page.locator('.equipment-filters').evaluate('node => { const location=node.querySelector("#equipment-location-filter-label").getBoundingClientRect(), search=node.querySelector(".search").getBoundingClientRect(); return location.left < search.left && Math.abs(location.top-search.top)<1; }')
            assert not errors, errors
            browser.close()
            print('PASS: one CSV across locations, Item/Model/Serial order, persistent/reversible found checkboxes, filters, export waits for confirmation, location PDFs, desktop/mobile layouts.')
    finally:
        server.shutdown()
        server.server_close()
