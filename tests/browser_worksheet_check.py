"""Worksheet selection must work even when the first sheet cannot be previewed."""
import io
import shutil
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from inventory_profiles import SCALA_PROFILE
from openpyxl import Workbook
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as temporary:
    app.DB_PATH=Path(temporary)/'inventory.sqlite3'
    inventory=app.save_equipment_inventory({'name':'Scala','layout':SCALA_PROFILE})
    book=Workbook();book.active.title='Cover'
    book.active.append(['Cover title']);book.active.append(['Owner','Department'])
    sheet=book.create_sheet('Scala assets');sheet.append(['Inventory title'])
    sheet.append(['ID','Location','Monitor model','Orientation','Notes'])
    sheet.append(['SC-55','Lobby','LG','','Original record'])
    output=io.BytesIO();book.save(output)
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
            page.locator('#import-file').set_input_files({'name':'cover-first.xlsx','mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':output.getvalue()})
            page.locator('#spreadsheet-error').wait_for(state='visible')
            assert page.locator('#sheet-choice option').all_text_contents()==['Cover','Scala assets']
            assert page.locator('#sheet-choice').is_enabled()
            assert page.locator('#confirm-import').is_disabled()
            page.locator('#sheet-choice').select_option('Scala assets')
            page.locator('#header-row').fill('2');page.locator('#reload-sheet').click()
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            assert page.locator('#map-asset_id option').all_text_contents()==['Leave blank','1. ID','2. Location','3. Monitor model','4. Orientation','5. Notes']
            assert page.locator('#sheet-choice').input_value()=='Scala assets'
            page.locator('#confirm-import').click();page.locator('#spreadsheet-dialog').wait_for(state='hidden')
            assert app.equipment_inventory(inventory['id'])[0]['custom_values']['asset_id']=='SC-55'
            page.locator('#import-file').set_input_files({'name':'simple.csv','mimeType':'text/csv','buffer':b'ID,Location,Monitor model,Orientation,Notes\nSC-56,Lobby,LG,,note\n'})
            page.wait_for_function("() => !document.getElementById('confirm-import').disabled")
            assert not page.locator('#sheet-label').is_visible()
            assert page.locator('#worksheet-note').is_visible()
            page.locator('#cancel-spreadsheet').click()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
print('Worksheet list survives preview/header errors; sheet selection, mappings, import and CSV message passed.')
