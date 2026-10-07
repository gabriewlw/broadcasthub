"""Optional end-to-end check: requires Playwright and Chromium."""
import json
import shutil
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
            page.locator('#system-filter').select_option('Audio')
            assert page.locator('#no-results').is_visible()
            page.get_by_role('button', name='Clear', exact=True).click()
            page.locator('#venue-filter').select_option('Liquid Lounge')
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
