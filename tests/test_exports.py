import io
import re
import shutil
import subprocess
import unittest
from urllib.request import urlopen

from openpyxl import load_workbook

import app
import test_app


class ExportTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def download(self, path, mime, filename):
        with urlopen(self.url + path) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['Content-Type'], mime)
            self.assertIn(filename, response.headers['Content-Disposition'])
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            return response.read()

    def xlsx(self, equipment=False):
        scope = '/api/equipment/export' if equipment else '/api/export'
        filename = 'broadcast-equipment.xlsx' if equipment else 'broadcast-network.xlsx'
        raw = self.download(scope + '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename)
        return load_workbook(io.BytesIO(raw), data_only=False)

    def test_network_workbook_latest_fields_status_and_literal_formulas(self):
        device = self.request('/api/devices', 'POST', test_app.EXAMPLE)[1]
        path = f"/api/devices/{device['id']}"
        self.request(path + '/confirm', 'POST', dict(ip=device['ip'], vlan=device['vlan']))
        self.request(path + '/system', 'POST', dict(discipline='Audio'))
        self.request(path + '/notes', 'POST', dict(notes='=SUM(1,2)\nAçúcar <&>'))
        self.request('/api/devices', 'POST', dict(name='Dynamic', ip='DHCP'))
        self.request('/api/devices', 'POST', dict(name='Unassigned'))
        self.request('/api/devices', 'POST', dict(record_type='iptv', name='News', ip='239.1.1.5', port=5000, channel_source='Satellite', notes='Current channel notes'))
        before = app.inventory()
        book = self.xlsx()
        self.assertEqual(book.sheetnames, ['AV devices','IPTV channels'])
        sheet = book['AV devices']
        self.assertEqual([cell.value for cell in sheet[1]], ['Venue','Device name','IP Address','VLAN','System','Notes','IP confirmation','Category'])
        rows = {cells[1].value: cells for cells in list(sheet)[1:]}
        cells = rows['ATEM video switcher']
        self.assertEqual([cell.value for cell in cells], ['Liquid Lounge','ATEM video switcher','10.24.176.66',1500,'Audio','=SUM(1,2)\nAçúcar <&>','Confirmed','Video switcher'])
        self.assertEqual(cells[5].data_type, 's')
        self.assertEqual(cells[4].fill.fgColor.rgb, '00CFEADB')
        self.assertEqual(rows['Dynamic'][2].value, 'DHCP')
        self.assertIsNone(rows['Dynamic'][6].value)
        self.assertIsNone(rows['Unassigned'][2].value)
        self.assertEqual(sheet.freeze_panes, 'A2')
        self.assertEqual(sheet.auto_filter.ref, 'A1:H4')
        self.assertEqual(list(book['IPTV channels'].values)[1], ('News','239.1.1.5',5000,'Satellite','Current channel notes',None))
        self.assertEqual(app.inventory(), before)

    def test_equipment_workbook_preserves_blank_zero_and_all_fields(self):
        self.request('/api/equipment', 'POST', dict(brand='Sony', model='X', description='Spare', serial_number='SER-1', quantity=0, location='Store', notes='After inspection'))
        self.request('/api/equipment', 'POST', dict(description='Unknown spare'))
        book = self.xlsx(True)
        self.assertEqual(book.sheetnames, ['Equipment'])
        values = list(book.active.values)
        self.assertEqual(values[0], ('Brand','Model','Description','Serial number','Quantity','Location','Notes'))
        self.assertIn(('Sony','X','Spare','SER-1',0,'Store','After inspection'), values)
        self.assertIn((None,None,'Unknown spare',None,None,None,None), values)

    def test_empty_reports_download_without_inventing_records(self):
        self.assertEqual(self.xlsx()['AV devices'].max_row, 1)
        self.assertEqual(self.xlsx(True).active.max_row, 1)
        for scope, filename in [('/api/export','broadcast-network.pdf'), ('/api/equipment/export','broadcast-equipment.pdf')]:
            raw = self.download(scope + '.pdf', 'application/pdf', filename)
            self.assertTrue(raw.startswith(b'%PDF-'))
            self.assertIn(b'%%EOF', raw)
        self.assertEqual(app.inventory(), [])
        self.assertEqual(app.equipment_inventory(), [])

    def test_pdf_ipv4_links_include_channels_without_linking_blank_or_dhcp(self):
        self.request('/api/devices', 'POST', dict(name='Fixed', ip='10.24.176.99', vlan=1500))
        self.request('/api/devices', 'POST', dict(name='Dynamic', ip='DHCP'))
        self.request('/api/devices', 'POST', dict(name='Blank'))
        self.request('/api/devices', 'POST', dict(record_type='iptv', name='Channel', ip='239.1.1.1', port=1234))
        raw = self.download('/api/export.pdf', 'application/pdf', 'broadcast-network.pdf')
        self.assertIn(b'http://10.24.176.99', raw)
        self.assertIn(b'http://239.1.1.1', raw)
        self.assertNotIn(b'http://DHCP', raw)
        self.assertIn(b'/S /URI', raw)

    @unittest.skipUnless(shutil.which('pdftotext'), 'PDF text validation needs optional pdftotext')
    def test_pdf_saved_information_pagination_and_long_notes(self):
        notes = 'Açúcar <&> ' + 'Long note ' * 195 + 'END_NOTE'
        rows = [dict(name=f'Camera {i}', venue='MAIN LOUNGE', discipline='Video', ip='DHCP', notes=notes if i == 0 else 'Reviewed') for i in range(75)]
        self.assertEqual(self.request('/api/import', 'POST', dict(version=1, devices=rows))[0], 200)
        device = self.request('/api/devices', 'POST', test_app.EXAMPLE)[1]
        self.request(f"/api/devices/{device['id']}/confirm", 'POST', dict(ip=device['ip'], vlan=device['vlan']))
        self.request('/api/devices', 'POST', dict(record_type='iptv', name='BBC News', ip='239.1.1.1', port=1234, channel_source='Onboard'))
        raw = self.download('/api/export.pdf', 'application/pdf', 'broadcast-network.pdf')
        text = subprocess.run(['pdftotext','-','-'], input=raw, stdout=subprocess.PIPE, check=True).stdout.decode()
        self.assertTrue(max(int(n) for n in re.findall(rb'/Count (\d+)', raw)) > 1)
        for value in ['Açúcar <&>', 'END_NOTE', 'Camera 74','Confirmed','1500','BBC News','Onboard','1234','REPORT GENERATED BY BROADCASTHUB','broadcastgab.com']:
            self.assertIn(value, text)
        self.assertGreater(text.count('VENUE'), 1)
        self.assertIn('VLAN', text)
        self.assertIn('CONFIRMATION', text)
        self.assertNotIn('IP / VLAN / CONFIRMATION', text)
        self.assertIn(b'https://broadcastgab.com', raw)
        self.request('/api/equipment', 'POST', dict(brand='Neutrik', model='XLR', quantity=0, notes='Equipment notes'))
        raw = self.download('/api/equipment/export.pdf', 'application/pdf', 'broadcast-equipment.pdf')
        text = subprocess.run(['pdftotext','-','-'], input=raw, stdout=subprocess.PIPE, check=True).stdout.decode()
        for value in ['Neutrik','XLR','QUANTITY','Equipment notes']:
            self.assertIn(value, text)


if __name__ == '__main__':
    unittest.main()
