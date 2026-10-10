"""Scala status/serial visibility and deleting configured columns without data loss."""
import shutil
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from inventory_profiles import DEFAULT_PROFILE
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'inventory.sqlite3'
    app.save_equipment({'description':'Stock item','serial_number':'STOCK-1'})
    # An existing Scala inventory can still have the original stock column layout.
    scala=app.save_equipment_inventory({'name':'Scala inventory','layout':DEFAULT_PROFILE})
    saved=app.save_equipment({'inventory_id':scala['id'],'description':'Scala screen','brand':'LG','model':'55','serial_number':'OLD-SERIAL','location':'Lobby','notes':'Retain these notes'})
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            assert page.locator('.equipment-status-group').is_visible()
            page.locator('#equipment-inventory-select').select_option(str(scala['id']))
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled && document.getElementById('equipment-inventory-title').textContent==='Scala inventory'")
            headers=page.locator('#equipment-table th').all_text_contents()
            assert 'Status' not in headers and 'Serial number' not in headers
            assert not page.locator('.equipment-status-group').is_visible()
            assert not page.locator('#equipment-found').is_visible()
            assert page.locator('#equipment-rows .equipment-confirm').count()==0
            page.locator('#equipment-configure-columns').click()
            page.locator('#inventory-columns-dialog').wait_for(state='visible')
            page.get_by_role('button',name='Delete Notes column',exact=True).click()
            page.locator('#save-inventory-columns').click()
            page.locator('#inventory-columns-dialog').wait_for(state='hidden')
            page.wait_for_function("() => ![...document.querySelectorAll('#equipment-table th')].some(cell=>cell.textContent==='Notes')")
            page.reload();page.locator('#equipment-rows tr').wait_for()
            headers=page.locator('#equipment-table th').all_text_contents()
            assert 'Notes' not in headers and 'Serial number' not in headers and 'Status' not in headers
            record=app.equipment_inventory(scala['id'])[0]
            assert record['serial_number']=='OLD-SERIAL' and record['notes']=='Retain these notes' and record['id']==saved['id']
            assert page.evaluate('''() => {const headings=[...document.querySelectorAll('#equipment-table th')],cells=[...document.querySelector('#equipment-rows tr').children];return headings.length===cells.length&&headings.every((heading,index)=>Math.abs(heading.getBoundingClientRect().x-cells[index].getBoundingClientRect().x)<1)}''')
            page.locator('#equipment-inventory-select').select_option('1')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled && document.getElementById('equipment-inventory-select').value==='1'")
            assert page.locator('.equipment-status-group').is_visible()
            assert 'Serial number' in page.locator('#equipment-table th').all_text_contents()
            assert 'Status' in page.locator('#equipment-table th').all_text_contents()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
print('Delete-column persistence/data retention and existing Scala serial/status removal passed; stock controls remain available.')
