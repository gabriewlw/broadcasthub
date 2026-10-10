"""Optional browser check of automatic complete rows and multi-row location review."""
import shutil
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from inventory_profiles import SCALA_PROFILE
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'inventory.sqlite3'
    inventory=app.save_equipment_inventory({'name':'Scala','layout':SCALA_PROFILE})
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/inventory')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled")
            page.locator('#equipment-inventory-select').select_option(str(inventory['id']))
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled && document.getElementById('equipment-inventory-title').textContent==='Scala'")
            data=b'ID,Location,Monitor model,Orientation,Notes\nS1,Room A,LG,,note\nS2,Room A,LG,Horizontal,note\nM1,Room A,,,note\nM2,Room A,LG,,\nM3,Room A,LG,Diagonal,note\nM4,Room A,,,note\nB1,Room B,LG,,note\nB2,Room B,,,note\n'
            page.locator('#import-file').set_input_files({'name':'scala.csv','mimeType':'text/csv','buffer':data})
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            assert page.locator('#map-serial_number').count()==0
            assert page.locator('#import-complete-rows').is_checked()
            page.locator('#confirm-import').click()
            dialog=page.locator('#inventory-import-review');dialog.wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==4
            page.screenshot(path=str(Path(temporary)/'batch-review.png'),full_page=True)
            saved=app.equipment_inventory(inventory['id']);assert len(saved)==2
            assert all(row['location']=='Room A' for row in saved)
            assert page.locator('#inventory-import-review-title').inner_text()=='Review Room A'
            assert not page.locator('#inventory-import-review-rows').get_by_role('button',name='Clear',exact=True).count()
            assert 'Missing Orientation' not in dialog.inner_text()
            m1=page.locator('tr[data-source-row="4"]');m2=page.locator('tr[data-source-row="5"]');m3=page.locator('tr[data-source-row="6"]');m4=page.locator('tr[data-source-row="7"]')
            assert m2.get_by_role('checkbox').is_checked()
            assert not m1.get_by_role('checkbox').is_checked()
            m3.get_by_role('checkbox').check()
            page.locator('#inventory-import-review-save').click()
            page.wait_for_function("() => document.querySelector('tr[data-source-row=\"6\"] .batch-row-result').classList.contains('error')")
            assert m2.locator('.batch-row-result').inner_text()=='Imported'
            assert len(app.equipment_inventory(inventory['id']))==3
            m1.get_by_label('Monitor model, row 4',exact=True).fill('Sony')
            m1.get_by_role('checkbox').check()
            m3.locator('button[data-value="Horizontal"]').click()
            page.locator('#inventory-import-review-save').click()
            page.wait_for_function("() => document.querySelector('tr[data-source-row=\"6\"] .batch-row-result').textContent==='Imported'")
            assert len(app.equipment_inventory(inventory['id']))==5
            assert not m4.get_by_role('checkbox').is_checked()
            m4.get_by_role('checkbox').check();page.locator('#inventory-import-review-skip').click()
            page.wait_for_function("() => document.getElementById('inventory-import-review-title').textContent==='Review Room B'")
            assert len(app.equipment_inventory(inventory['id']))==6
            assert page.locator('#inventory-import-review-rows tr').count()==1
            page.locator('#inventory-import-review-stop').click()
            page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            assert len(app.equipment_inventory(inventory['id']))==6
            assert page.locator('#equipment-import-report').is_visible()
            page.locator('#equipment-import-report summary').click()
            assert 'Skipped by user' in page.locator('#equipment-import-report').inner_text()
            page.locator('#equipment-rows button[data-value="Vertical"]').first.click()
            page.wait_for_function("() => document.querySelector('#equipment-rows button[data-value=Vertical]').getAttribute('aria-pressed')==='true'")
            page.reload();page.locator('#equipment-rows tr').first.wait_for()
            assert page.locator('#equipment-rows tr').count()==6
            # The same workflow also reviews the stock inventory's own columns.
            page.locator('#equipment-inventory-select').select_option('1')
            page.wait_for_function("() => !document.getElementById('equipment-inventory-select').disabled && document.getElementById('equipment-inventory-select').value==='1'")
            stock=b'Item,Brand,Model,Serial number,Quantity,Location,Notes\nCamera,Sony,X,ST-1,1,Store,note\nCamera,Sony,X,ST-2,,Store,note\n'
            page.locator('#import-file').set_input_files({'name':'stock.csv','mimeType':'text/csv','buffer':stock})
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            page.locator('#confirm-import').click();dialog.wait_for(state='visible')
            assert len(app.equipment_inventory(1))==1
            assert page.locator('#inventory-import-review-rows tr').count()==1
            page.get_by_label('Quantity, row 3',exact=True).fill('2')
            page.get_by_label('Select row 3',exact=True).check()
            page.locator('#inventory-import-review-save').click()
            page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            assert len(app.equipment_inventory(1))==2
            # Turning off automatic import keeps even complete rows on the review screen.
            page.locator('#import-file').set_input_files({'name':'manual.csv','mimeType':'text/csv','buffer':stock.replace(b'ST-1',b'ST-3').replace(b'ST-2',b'ST-4')})
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            page.locator('#import-complete-rows').uncheck();page.locator('#confirm-import').click();dialog.wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==2
            assert len(app.equipment_inventory(1))==2
            page.locator('#inventory-import-review-stop').click();page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            # Larger locations use eight-row screens, with bulk selection on each screen.
            many=('Item,Brand,Model,Serial number,Quantity,Location,Notes\n'+''.join(f'Camera,Sony,X,BULK-{index},,Store,note\n' for index in range(10))).encode()
            page.locator('#import-file').set_input_files({'name':'many.csv','mimeType':'text/csv','buffer':many})
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            page.locator('#confirm-import').click();dialog.wait_for(state='visible')
            assert page.locator('#inventory-import-review-rows tr').count()==8
            page.locator('#inventory-import-review-rows input[type=number]').evaluate_all('(inputs)=>inputs.forEach(input=>{input.value="1";input.dispatchEvent(new Event("input",{bubbles:true}));})')
            page.locator('#inventory-import-review-all').check()
            page.locator('#inventory-import-review-save').click()
            page.wait_for_function("() => document.querySelectorAll('#inventory-import-review-rows tr').length===2")
            assert len(app.equipment_inventory(1))==10
            page.locator('#inventory-import-review-all').check();page.locator('#inventory-import-review-skip').click()
            page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            assert len(app.equipment_inventory(1))==10
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
print('Automatic complete rows, multi-row editing, validation/retry, skip/stop, location order, optional orientation and persistence passed.')
