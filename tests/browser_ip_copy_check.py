"""Optional IP-only clipboard check for website rows and plain-address exports."""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temp:
    app.DB_PATH = Path(temp) / 'inventory.sqlite3'
    bridge = app.save_device(dict(name='Bridge Cam', ip='200.200.200.200', venue='Bridge', discipline='Video'))
    app.save_device(dict(name='BGM PC', ip='DHCP', venue='Main lounge', discipline='Audio'))
    app.save_device(dict(name='Spare display', venue='Storeroom', discipline='Video'))
    app.save_device(dict(name='News channel', record_type='iptv', ip='239.252.2.122', port=1234))
    server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=shutil.which('chromium') or None)
            context = browser.new_context(viewport={'width':1440,'height':1000}, permissions=['clipboard-read','clipboard-write'])
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            page.wait_for_function("() => document.querySelectorAll('.device-row').length === 3")
            row = page.locator('.device-row').filter(has_text='Bridge Cam')
            copy = row.get_by_role('button', name='Copy IP address for Bridge Cam', exact=True)
            copy.click()
            page.wait_for_function("() => document.getElementById('toast').textContent === 'IP address copied.'")
            assert page.evaluate('navigator.clipboard.readText()') == bridge['ip']
            assert page.locator('.device-row').filter(has_text='BGM PC').locator('.ip-copy').count() == 0
            assert page.locator('.device-row').filter(has_text='Spare display').locator('.ip-copy').count() == 0
            page.evaluate("""async () => {
                await navigator.clipboard.writeText('before fallback');
                window.originalWriteText = navigator.clipboard.writeText;
                window.originalExecCommand = document.execCommand;
                navigator.clipboard.writeText = async () => { throw new Error('Denied'); };
            }""")
            copy.click()
            page.wait_for_function("() => document.getElementById('toast').textContent === 'IP address copied.'")
            assert page.evaluate('navigator.clipboard.readText()') == bridge['ip']
            page.evaluate('document.execCommand = () => false')
            copy.click()
            page.wait_for_function("() => document.getElementById('toast').textContent.includes('browser’s Copy')")
            assert page.evaluate('window.getSelection().toString()') == bridge['ip']
            assert page.locator('.clipboard-copy-buffer').count() == 0
            page.evaluate("() => { navigator.clipboard.writeText = window.originalWriteText; document.execCommand = window.originalExecCommand; }")
            for width in [1440,1100,390,320]:
                page.set_viewport_size({'width':width,'height':1000})
                copy.click()
                page.wait_for_function("() => document.getElementById('toast').textContent === 'IP address copied.'")
                assert page.evaluate('navigator.clipboard.readText()') == bridge['ip']
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                geometry = row.locator('.ip-address-value').evaluate('node => {const text=node.querySelector(".device-ip").getBoundingClientRect(), button=node.querySelector(".ip-copy").getBoundingClientRect(), field=node.getBoundingClientRect();return {textRight:text.right,buttonLeft:button.left,buttonRight:button.right,fieldRight:field.right};}')
                assert geometry['textRight'] <= geometry['buttonLeft'] and geometry['buttonRight'] <= geometry['fieldRight'] + 0.5, (width, geometry)
                if width >= 1100:
                    assert page.locator('#device-directory').evaluate('node => node.scrollWidth <= node.clientWidth'), width
            if not page.locator('#iptv-tab').is_visible():
                page.locator('#nav-toggle').click()
            page.locator('#iptv-tab').click()
            page.get_by_role('button', name='Copy IP address for News channel', exact=True).click()
            page.wait_for_function("() => document.getElementById('toast').textContent === 'IP address copied.'")
            assert page.evaluate('navigator.clipboard.readText()') == '239.252.2.122'
            assert page.locator('.udp-copy').count() == 1
            # Exports come from saved data, not the website controls.
            for suffix in ['', '.csv', '.xlsx', '.pdf']:
                response = context.request.get(f'http://127.0.0.1:{server.server_port}/api/export{suffix}?record_type=device')
                assert response.ok
                data = response.body()
                if suffix == '':
                    assert next(item for item in json.loads(data)['devices'] if item['id'] == bridge['id'])['ip'] == bridge['ip']
                    text = data.decode()
                elif suffix == '.xlsx':
                    text = str(list(load_workbook(io.BytesIO(data)).active.values))
                elif suffix == '.pdf':
                    if not shutil.which('pdftotext'):
                        continue
                    text = subprocess.run(['pdftotext','-','-'], input=data, capture_output=True, check=True).stdout.decode()
                else:
                    text = data.decode('utf-8-sig')
                assert bridge['ip'] in text
                assert 'Copy IP' not in text and 'ip-copy' not in text and '<svg' not in text
            assert not errors, errors
            browser.close()
            print('PASS: exact AV/IPTV clipboard contents, browser fallback, selected manual copy, no DHCP/blank controls, compact desktop/mobile layouts, and plain IPs in every export format.')
    finally:
        server.shutdown()
        server.server_close()
