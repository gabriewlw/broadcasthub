"""Optional browser check for inventory deletion, all-column search and filter controls."""
import copy
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
    app.save_equipment({'description':'Keep this camera','serial_number':'KEEP-1'})
    profile=copy.deepcopy(DEFAULT_PROFILE)
    profile['columns'].append({'key':'custom_asset_tag','label':'Asset tag','type':'text','important':False,'filter':'none','options':[]})
    target=app.save_equipment_inventory({'name':'Spare TVs','layout':profile})
    app.save_equipment(dict(inventory_id=target['id'],description='Studio display',brand='ViewBrand',model='ModelQ',serial_number='ABC123',quantity=7,location='Store room',notes='Remote included',custom_values={'custom_asset_tag':'TAG-44'}))
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(target['id']))
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled && document.getElementById('equipment-inventory-title').textContent === 'Spare TVs'")
            assert page.locator('#equipment-status-buttons button').all_text_contents()==['All items','Located','Not located']
            assert page.locator('#equipment-location-buttons button').all_text_contents()==['Store room']
            assert page.locator('#equipment-location-filter option').first.inner_text()=='All locations'
            for query in ['studio','viewbrand','modelq','abc123','7','store','remote','tag-44','not located','check record']:
                page.locator('#equipment-search').fill(query)
                assert page.locator('#equipment-rows tr').count()==1,query
            page.locator('#equipment-search').fill('no such item')
            assert page.locator('#equipment-rows tr').count()==0
            page.locator('#equipment-clear').click()
            page.locator('#equipment-status-buttons button[data-value=found]').click()
            assert page.locator('#equipment-rows tr').count()==0
            page.locator('#equipment-status-buttons button[data-value=pending]').click()
            assert page.locator('#equipment-rows tr').count()==1
            page.locator('#delete-equipment-inventory').click()
            assert 'Spare TVs' in page.locator('#delete-inventory-description').inner_text()
            assert 'all 1 item' in page.locator('#delete-inventory-description').inner_text()
            page.locator('#cancel-delete-inventory').click()
            assert len(app.equipment_inventory(target['id']))==1
            page.locator('#delete-equipment-inventory').click()
            page.locator('#confirm-delete-inventory').click()
            page.locator('#delete-inventory-dialog').wait_for(state='hidden')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled && document.getElementById('equipment-inventory-title').textContent === 'Equipment inventory'")
            assert page.locator('#equipment-rows').inner_text().find('Keep this camera')>=0
            page.reload();page.locator('#equipment-rows tr').wait_for()
            page.locator('#equipment-search').fill('no match')
            page.locator('#equipment-review-summary a').click()
            assert page.locator('#equipment-review-filter').input_value()=='flagged'
            assert page.locator('#equipment-search').input_value()==''
            assert page.locator('#equipment-rows tr').count()==1
            assert page.locator('#equipment-inventory-select option').count()==1
            page.locator('#delete-equipment-inventory').click()
            assert page.locator('#delete-inventory-last').is_visible()
            page.locator('#confirm-delete-inventory').click()
            page.locator('#delete-inventory-dialog').wait_for(state='hidden')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled && document.getElementById('equipment-inventory-select').value !== '1'")
            assert page.locator('#equipment-rows tr').count()==0
            page.reload();page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            assert page.locator('#equipment-inventory-select option').count()==1
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
print('Inventory deletion/cancel/reload, last-inventory replacement, all-column search and filters passed.')
