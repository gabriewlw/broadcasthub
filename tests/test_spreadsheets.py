import base64
import io
import unittest
from openpyxl import Workbook
from spreadsheets import preview
import test_app


def encoded(raw, filename='inventory.xlsx', **extra):
    return dict(filename=filename, content=base64.b64encode(raw).decode(), **extra)


def workbook_bytes():
    book = Workbook()
    book.active.title = 'Cover'
    book.active.append(['AV inventory'])
    sheet = book.create_sheet('Devices')
    sheet.append(['Shipboard devices'])
    sheet.append(['Equipment', 'Location', 'IP Address', 'VLAN ID', 'System'])
    sheet.append(['ATEM', 'Liquid Lounge', '10.24.176.66', 1500, 'video'])
    sheet.append([None] * 5)
    sheet.append(['Console', 'Theater', '10.24.176.67', 1500, 'audio'])
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


class SpreadsheetParserTests(unittest.TestCase):
    def test_xlsx_sheet_header_and_numeric_cells(self):
        result = preview(encoded(workbook_bytes(), sheet='Devices', header_row=2))
        self.assertEqual(result['sheets'], ['Cover', 'Devices'])
        self.assertEqual(result['headers'][2], 'IP Address')
        self.assertEqual(result['rows'][0][3], '1500')
        self.assertEqual(result['row_numbers'], [3, 5])
        self.assertEqual(len(result['rows']), 2)

    def test_csv_bom_semicolon_quotes_blank_rows(self):
        raw = '\ufeffDevice;IP;VLAN\r\n"ATEM; main";10.24.176.66;1500\r\n;;\r\n'.encode()
        result = preview(encoded(raw, 'devices.csv'))
        self.assertEqual(result['headers'], ['Device', 'IP', 'VLAN'])
        self.assertEqual(result['rows'], [['ATEM; main', '10.24.176.66', '1500']])

    def test_unreadable_and_empty_files(self):
        for payload in (encoded(b'not excel'), encoded(b'name,ip\n', 'empty.csv'), encoded(b'data', 'old.xls'), encoded(b'a\nb', 'a.csv', header_row=0)):
            with self.subTest(payload=payload['filename']):
                with self.assertRaises(ValueError):
                    preview(payload)


class SpreadsheetHTTPTests(test_app.AppTests):
    # Reuse the isolated HTTP fixture; run only new cases in this subclass.
    test_cross_origin_and_assets = None
    test_csv_formula_protection = None
    test_duplicate_scope = None
    test_export_import_roundtrip_and_idempotence = None
    test_full_lifecycle_and_persistence = None
    test_import_is_atomic = None
    test_validation = None

    def test_preview_does_not_write_and_mapped_import_roundtrip(self):
        status, data = self.request('/api/spreadsheet-preview', 'POST', encoded(workbook_bytes(), sheet='Devices', header_row=2))
        self.assertEqual(status, 200)
        self.assertEqual(self.request('/api/devices')[1]['devices'], [])
        mapped = [dict(name=r[0], category='AV device', venue=r[1], ip=r[2], vlan=r[3], discipline=r[4].title(), notes='') for r in data['rows']]
        self.assertEqual(self.request('/api/import', 'POST', {'version':1,'devices':mapped})[1], {'added':2,'skipped':0})
        self.assertEqual(self.request('/api/import', 'POST', {'version':1,'devices':mapped})[1], {'added':0,'skipped':2})
        status, export = self.request('/api/export.csv')
        self.assertEqual(status, 200)
        data = self.request('/api/spreadsheet-preview', 'POST', encoded(export, 'export.csv'))[1]
        self.assertEqual(data['headers'], ['name','category','venue','discipline','ip','vlan','notes'])
        self.assertEqual(len(data['rows']), 2)

    def test_invalid_excel_http(self):
        self.assertEqual(self.request('/api/spreadsheet-preview', 'POST', encoded(b'invalid'))[0], 400)
