"""Desktop layout regression check. Run with Python and Playwright/Chromium installed."""
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory() as temporary:
        app.DB_PATH = Path(temporary) / 'layout.sqlite3'
        for index in range(3):
            app.save_device(dict(name=f'Camera {index}', venue='Control room', discipline='Video', ip=f'10.1.1.{index+1}', vlan=100))
            app.save_device(dict(record_type='iptv', name=f'Channel {index}', channel_source='Onboard', ip=f'239.1.1.{index+1}', port=1234))
            app.save_equipment(dict(description='Spare camera', brand='Sony', model='PXW', serial_number=f'SN-{index}', quantity=1, location='Store'))
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=shutil.which('chromium'))
                page = browser.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                for width in (1920, 1440, 1280, 1024):
                    page.set_viewport_size(dict(width=width, height=1080))
                    for route in ('/', '/#av', '/#iptv', '/inventory'):
                        page.goto(f'http://127.0.0.1:{server.server_port}{route}')
                        page.locator('#equipment-rows tr' if route == '/inventory' else '.device-row').first.wait_for()
                        page.evaluate('document.fonts.ready')
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, route)
                        assert page.evaluate('''() => [...document.querySelectorAll('.device-row,#equipment-rows tr')]
                            .filter(row => row.getBoundingClientRect().width).every(row => Math.abs(row.getBoundingClientRect().height-47)<1)'''), (width, route)
                        if route == '/inventory':
                            assert page.evaluate('''() => {const headings=[...document.querySelectorAll('#equipment-table th')];
                                const cells=[...document.querySelector('#equipment-rows tr').children];
                                return headings.every((heading,index) => Math.abs(heading.getBoundingClientRect().x-cells[index].getBoundingClientRect().x)<1 && Math.abs(heading.getBoundingClientRect().width-cells[index].getBoundingClientRect().width)<1)}''')
                            assert page.evaluate('''() => {const controls=['#equipment-location-filter','#equipment-status-buttons','#equipment-search'].map(selector=>document.querySelector(selector).getBoundingClientRect());return controls.every(rect=>Math.abs(rect.y-controls[0].y)<1&&rect.height===44)}'''), width
                            if width >= 1280:
                                assert page.evaluate('''() => {const table=document.querySelector('#equipment-table'),wrap=document.querySelector('.equipment-table-wrap');return table.getBoundingClientRect().width<=wrap.clientWidth+1}''')
                                assert page.evaluate('''() => [...document.querySelectorAll('#equipment-table th')].every(cell=>cell.scrollWidth<=cell.clientWidth+1)''')
                            page.locator('#add-device').click()
                            page.locator('#equipment-dialog').wait_for(state='visible')
                            assert abs(page.locator('#equipment-brand').bounding_box()['y']-page.locator('#equipment-model').bounding_box()['y'])<1
                            page.locator('#cancel-equipment').click()
                            page.locator('#equipment-configure-columns').click()
                            page.locator('#inventory-columns-dialog').wait_for(state='visible')
                            assert page.evaluate('''() => [...document.querySelectorAll('.inventory-column-editor')].every(card=> {const inputs=[...card.querySelectorAll('input,select')].slice(0,3);return inputs.every(input=>Math.abs(input.getBoundingClientRect().y-inputs[0].getBoundingClientRect().y)<1)})''')
                            page.locator('#inventory-columns-dialog').evaluate('(dialog)=>dialog.close()')
                        else:
                            assert page.evaluate('''() => {const head=document.querySelector('.directory-head'),row=document.querySelector('.device-row');return getComputedStyle(head).gridTemplateColumns===getComputedStyle(row).gridTemplateColumns && head.getBoundingClientRect().height===48}''')
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
    print('Desktop layout passed: 4 viewports, 4 views, column geometry, row heights, filters, forms and setup cards.')


if __name__ == '__main__':
    main()
