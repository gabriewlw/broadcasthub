import csv
import io
import sqlite3
import unittest
import app
import test_app


class MissingInformationTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def test_partial_devices_keep_blanks_and_only_known_ips_are_duplicates(self):
        rows = [dict(name='Camera', venue='RD MAIN LOUNGE'), dict(name='Spare camera'),
                dict(ip='10.24.176.90'), dict(ip='10.24.176.90', vlan='1500')]
        status, result = self.request('/api/import', 'POST', dict(version=1, source='spreadsheet', devices=rows, row_numbers=[2, 3, 4, 5]))
        self.assertEqual(status, 200)
        self.assertEqual((result['added'], result['skipped']), (3, 1))
        self.assertIn('Row 5:', result['warnings'][0])
        records = app.inventory()
        self.assertEqual(sum(row['ip'] == '' for row in records), 2)
        camera = next(row for row in records if row['name'] == 'Camera')
        self.assertEqual(camera['venue'], 'MAIN LOUNGE')
        self.assertEqual((camera['category'], camera['discipline'], camera['notes']), ('', 'Video', ''))
        self.assertIsNone(camera['vlan'])
        raw = self.request('/api/export.csv')[1].decode('utf-8-sig')
        exported = next(row for row in csv.DictReader(io.StringIO(raw)) if row['name'] == 'Camera')
        self.assertEqual((exported['ip'], exported['vlan'], exported['category']), ('', '', ''))

    def test_fill_partial_device_later_confirm_and_transfer(self):
        _, result = self.request('/api/import', 'POST', dict(version=1, devices=[dict(name='Camera'), dict(venue='Pool')]))
        self.assertEqual(result, dict(added=2, skipped=0))
        camera = next(row for row in app.inventory() if row['name'] == 'Camera')
        path = f"/api/devices/{camera['id']}"
        self.assertEqual(self.request(path + '/confirm', 'POST', dict(ip='', vlan=None))[0], 400)
        status, saved = self.request(path, 'PUT', dict(camera, ip='10.24.176.90'))
        self.assertEqual(status, 200)
        self.assertEqual((saved['venue'], saved['category'], saved['discipline']), ('', '', 'Video'))
        self.assertEqual(self.request(path + '/confirm', 'POST', dict(ip=saved['ip'], vlan=None))[1]['ip_confirmed'], 1)
        payload = self.request('/api/export')[1]
        with app.connect() as con:
            con.execute('DELETE FROM devices')
        self.assertEqual(self.request('/api/import', 'POST', payload)[1], dict(added=2, skipped=0))
        self.assertEqual(next(row for row in app.inventory() if row['name'] == 'Camera')['category'], '')

    def test_partial_iptv_channels_do_not_invent_source_or_port(self):
        payload = dict(version=1, devices=[dict(record_type='iptv', name='Channel A', ip='239.1.1.10'),
                                          dict(record_type='iptv', name='Channel B', ip='239.1.1.10'),
                                          dict(record_type='iptv', name='Channel C', port=1234)])
        self.assertEqual(self.request('/api/import', 'POST', payload)[1], dict(added=3, skipped=0))
        records = {row['name']: row for row in app.inventory()}
        self.assertEqual((records['Channel A']['category'], records['Channel A']['discipline'], records['Channel A']['channel_source']), ('', '', ''))
        self.assertIsNone(records['Channel A']['port'])
        self.assertEqual(records['Channel C']['ip'], '')
        first, second = records['Channel A'], records['Channel B']
        self.assertEqual(self.request(f"/api/devices/{first['id']}", 'PUT', dict(first, port=1234, channel_source='Onboard'))[0], 200)
        self.assertEqual(self.request(f"/api/devices/{second['id']}", 'PUT', dict(second, port=1234))[0], 409)

    def test_partial_equipment_keeps_unknown_quantity_and_all_rows(self):
        payload = dict(version=1, equipment=[dict(description='Spare camera'), dict(description='Spare camera'), dict(description='Out of stock', quantity=0)])
        self.assertEqual(self.request('/api/equipment/import', 'POST', payload)[1], dict(added=3, skipped=0))
        records = app.equipment_inventory()
        self.assertEqual(sum(row['quantity'] is None for row in records), 2)
        self.assertEqual(sum(row['quantity'] == 0 for row in records), 1)
        self.assertTrue(all(row['brand'] == row['model'] == row['location'] == '' for row in records))
        first = records[0]
        status, saved = self.request(f"/api/equipment/{first['id']}", 'PUT', dict(first, brand='Sony', quantity=2))
        self.assertEqual(status, 200)
        self.assertEqual(saved['model'], '')
        raw = self.request('/api/equipment/export.csv')[1].decode('utf-8-sig')
        self.assertEqual(sum(row['quantity'] == '' for row in csv.DictReader(io.StringIO(raw))), 1)
        exported = self.request('/api/equipment/export')[1]
        with app.connect() as con:
            con.execute('DELETE FROM equipment')
        self.assertEqual(self.request('/api/equipment/import', 'POST', exported)[1], dict(added=3, skipped=0))

    def test_existing_equipment_migration_preserves_ids_and_quantities(self):
        with sqlite3.connect(app.DB_PATH) as con:
            con.execute("""CREATE TABLE equipment (id INTEGER PRIMARY KEY, brand TEXT NOT NULL,
                model TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL, location TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("INSERT INTO equipment (id,brand,model,quantity,location,updated_at) VALUES (42,'Sony','Camera',3,'Store','2025-01-01')")
        before = app.equipment_inventory()[0]
        self.assertEqual((before['id'], before['quantity'], before['updated_at']), (42, 3, '2025-01-01'))
        self.assertEqual(app.equipment_inventory()[0], before)
        status, partial = self.request('/api/equipment', 'POST', dict(description='Imported spare'))
        self.assertEqual(status, 201)
        self.assertIsNone(partial['quantity'])
        self.assertEqual(next(row for row in app.equipment_inventory() if row['id'] == 42), before)

    def test_blank_import_rows_skip_without_errors_and_keep_source_numbers(self):
        payload = dict(version=1, source='spreadsheet', row_numbers=[2, 3, 4, 5],
                       devices=[dict(name=' '), dict(ip='10.24.176.90'), {}, dict(ip='10.24.176.90')])
        status, result = self.request('/api/import', 'POST', payload)
        self.assertEqual(status, 200)
        self.assertEqual((result['added'], result['skipped']), (1, 1))
        self.assertIn('Row 5:', result['warnings'][0])
        self.assertEqual(self.request('/api/import', 'POST', dict(version=1, devices=[{}, dict(record_type='iptv', port=None)]))[1], dict(added=0, skipped=0))
        self.assertEqual(self.request('/api/equipment/import', 'POST', dict(version=1, equipment=[{}, dict(brand=' ', quantity=None)]))[1], dict(added=0, skipped=0))

    def test_system_dropdown_changes_only_system_and_preserves_confirmation(self):
        _, device = self.request('/api/devices', 'POST', dict(test_app.EXAMPLE, discipline=''))
        path = f"/api/devices/{device['id']}"
        self.request(path + '/confirm', 'POST', dict(ip=device['ip'], vlan=device['vlan']))
        # Simulate a separate browser editing other fields before the dropdown saves.
        self.request(path, 'PUT', dict(device, name='Updated name', notes='Updated notes'))
        status, updated = self.request(path + '/system', 'POST', dict(discipline='Audio', notes='stale notes', ip='10.24.176.99'))
        self.assertEqual(status, 200)
        self.assertEqual((updated['name'], updated['notes'], updated['ip']), ('Updated name', 'Updated notes', device['ip']))
        self.assertEqual(updated['discipline'], 'Audio')
        self.assertEqual(updated['ip_confirmed'], 1)
        self.assertEqual(self.request(path + '/system', 'POST', dict(discipline=''))[1]['discipline'], '')
        self.assertEqual(self.request(path + '/system', 'POST', dict(discipline='invalid'))[0], 400)
        self.assertEqual(self.request('/api/devices/999/system', 'POST', dict(discipline='Video'))[0], 404)

    def test_notes_edit_accepts_blank_and_preserves_other_fields(self):
        _, device = self.request('/api/devices', 'POST', test_app.EXAMPLE)
        path = f"/api/devices/{device['id']}"
        self.request(path + '/confirm', 'POST', dict(ip=device['ip'], vlan=device['vlan']))
        self.request(path + '/system', 'POST', dict(discipline='Lighting'))
        status, updated = self.request(path + '/notes', 'POST', dict(notes='New notes', discipline='stale'))
        self.assertEqual(status, 200)
        self.assertEqual((updated['notes'], updated['discipline'], updated['ip_confirmed']), ('New notes', 'Lighting', 1))
        self.assertEqual(self.request(path + '/notes', 'POST', dict(notes=''))[1]['notes'], '')
        self.assertEqual(self.request(path + '/notes', 'POST', dict(notes='x' * 2001))[0], 400)
        _, channel = self.request('/api/devices', 'POST', dict(record_type='iptv', name='Channel'))
        self.assertEqual(self.request(f"/api/devices/{channel['id']}/notes", 'POST', dict(notes='IPTV note'))[1]['notes'], 'IPTV note')


if __name__ == '__main__':
    unittest.main()
