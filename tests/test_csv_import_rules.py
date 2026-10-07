import sqlite3
import unittest
import app
import test_app


class CSVImportRulesTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def import_rows(self, rows, numbers=None):
        return self.request('/api/import', 'POST', dict(version=1, source='spreadsheet', devices=rows,
                                                     row_numbers=numbers or list(range(2, len(rows) + 2))))

    def test_clean_venues_ignore_nonnumeric_vlans_and_confirm_blank(self):
        rows = [dict(test_app.EXAMPLE, venue='  RD MAIN LOUNGE  ', vlan='1500'),
                dict(test_app.EXAMPLE, name='Camera', ip='10.24.176.67', venue='rd POOL DECK', vlan='AV network'),
                dict(test_app.EXAMPLE, name='Lights', ip='10.24.176.68', venue='FORWARD ROOM', vlan='1.5')]
        status, result = self.import_rows(rows)
        self.assertEqual(status, 200)
        self.assertEqual(result, dict(added=3, skipped=0, warnings=[]))
        stored = {row['ip']: row for row in app.inventory()}
        self.assertEqual(stored['10.24.176.66']['venue'], 'MAIN LOUNGE')
        self.assertEqual(stored['10.24.176.66']['vlan'], 1500)
        self.assertEqual(stored['10.24.176.67']['venue'], 'POOL DECK')
        self.assertEqual(stored['10.24.176.68']['venue'], 'FORWARD ROOM')
        self.assertIsNone(stored['10.24.176.67']['vlan'])
        self.assertIsNone(stored['10.24.176.68']['vlan'])
        camera = stored['10.24.176.67']
        path = f"/api/devices/{camera['id']}"
        self.assertEqual(self.request(path + '/confirm', 'POST', dict(ip=camera['ip'], vlan=None))[1]['ip_confirmed'], 1)
        self.assertEqual(self.request(path, 'PUT', dict(camera, notes='New note'))[1]['ip_confirmed'], 1)
        self.assertEqual(self.request(path, 'PUT', dict(camera, vlan=1500))[1]['ip_confirmed'], 0)
        payload = self.request('/api/export')[1]
        with app.connect() as con:
            con.execute('DELETE FROM devices')
        self.assertEqual(self.request('/api/import', 'POST', payload)[1], dict(added=3, skipped=0))

    def test_duplicate_ips_in_file_and_inventory_skip_across_vlans(self):
        self.request('/api/devices', 'POST', test_app.EXAMPLE)
        rows = [dict(test_app.EXAMPLE, name='Existing collision', vlan='1501'),
                dict(test_app.EXAMPLE, name='First camera', ip='10.24.176.67', venue='RD MAIN LOUNGE', vlan=''),
                dict(test_app.EXAMPLE, name='Repeated camera', ip='10.24.176.67', venue='RD POOL', vlan='1502')]
        status, result = self.import_rows(rows, [4, 6, 9])
        self.assertEqual(status, 200)
        self.assertEqual((result['added'], result['skipped']), (1, 2))
        self.assertIn('Row 4:', result['warnings'][0])
        self.assertIn('already exists', result['warnings'][0])
        self.assertIn('Row 9:', result['warnings'][1])
        self.assertIn('earlier in this file', result['warnings'][1])
        records = app.inventory()
        self.assertEqual({row['name'] for row in records}, {'ATEM video switcher', 'First camera'})
        # Editing cannot introduce a repeated IP either.
        camera = next(row for row in records if row['name'] == 'First camera')
        self.assertEqual(self.request(f"/api/devices/{camera['id']}", 'PUT', dict(camera, ip=test_app.EXAMPLE['ip']))[0], 409)

    def test_numeric_vlan_out_of_range_and_bad_ip_reject_atomically(self):
        for changes in (dict(vlan='4095'), dict(ip='not an IP')):
            second = dict(test_app.EXAMPLE, ip='10.24.176.67')
            second.update(changes)
            status, result = self.import_rows([test_app.EXAMPLE, second])
            self.assertEqual(status, 400)
            self.assertIn('Nothing was imported', result['error'])
            self.assertEqual(app.inventory(), [])

    def test_legacy_duplicates_preserved_new_duplicates_blocked(self):
        # Emulate an existing database from the version allowing one IP in different VLANs.
        with sqlite3.connect(app.DB_PATH) as con:
            con.execute(app.SCHEMA.format(table='devices'))
            for vlan in (1500, 1501):
                row = app.validate(dict(test_app.EXAMPLE, vlan=vlan))
                con.execute('INSERT INTO devices (' + ','.join(app.ALL_FIELDS) + ') VALUES (' + ','.join('?' for _ in app.ALL_FIELDS) + ')', [row[f] for f in app.ALL_FIELDS])
        self.assertEqual(len(app.inventory()), 2)
        self.assertEqual(self.request('/api/devices', 'POST', dict(test_app.EXAMPLE, vlan=1502))[0], 409)
        # Users can still edit notes or repair an old collision without deleting their data.
        first = app.inventory()[0]
        self.assertEqual(self.request(f"/api/devices/{first['id']}", 'PUT', dict(first, notes='Reviewed'))[0], 200)
        self.assertEqual(self.request(f"/api/devices/{first['id']}", 'PUT', dict(first, ip='10.24.176.67'))[0], 200)


if __name__ == '__main__':
    unittest.main()
