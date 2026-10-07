import sqlite3
import unittest
import app
import test_app


class ConfirmationTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def test_confirm_persists_and_assignment_edits_reset(self):
        _, device = self.request('/api/devices', 'POST', test_app.EXAMPLE)
        self.assertEqual(device['ip_confirmed'], 0)
        path = f"/api/devices/{device['id']}"
        identity = dict(ip=device['ip'], vlan=device['vlan'])
        status, confirmed = self.request(path + '/confirm', 'POST', identity)
        self.assertEqual(status, 200)
        self.assertEqual(confirmed['ip_confirmed'], 1)
        self.assertEqual(app.inventory()[0]['ip_confirmed'], 1)
        self.assertEqual(self.request(path+'/confirm', 'POST', identity)[1]['ip_confirmed'], 1)
        self.assertEqual(self.request(path, 'PUT', dict(test_app.EXAMPLE, notes='Reviewed'))[1]['ip_confirmed'], 1)
        changed = dict(test_app.EXAMPLE, ip='10.24.176.67')
        self.assertEqual(self.request(path, 'PUT', changed)[1]['ip_confirmed'], 0)
        self.assertEqual(self.request(path+'/confirm', 'POST', identity)[0], 400)
        self.assertEqual(self.request(path+'/confirm', 'POST', dict(ip=changed['ip'], vlan=changed['vlan']))[1]['ip_confirmed'], 1)
        self.assertEqual(self.request(path, 'PUT', dict(changed, vlan=1501))[1]['ip_confirmed'], 0)
        self.assertEqual(self.request('/api/devices/999/confirm', 'POST', identity)[0], 404)

    def test_existing_database_migration_and_import_status(self):
        # Create the exact legacy schema, with a real device, before new code connects.
        with sqlite3.connect(app.DB_PATH) as con:
            con.execute('''CREATE TABLE devices (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                category TEXT NOT NULL, venue TEXT NOT NULL, discipline TEXT NOT NULL,
                ip TEXT NOT NULL, vlan INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(ip,vlan))''')
            con.execute('INSERT INTO devices (name,category,venue,discipline,ip,vlan,notes) VALUES (?,?,?,?,?,?,?)', [test_app.EXAMPLE[f] for f in app.FIELDS])
        rows = app.inventory()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['name'], test_app.EXAMPLE['name'])
        self.assertEqual(rows[0]['ip_confirmed'], 0)
        self.assertEqual(app.inventory()[0]['ip_confirmed'], 0)  # Migration is repeatable.
        payload = {'version':1,'devices':[dict(test_app.EXAMPLE, ip='10.24.176.68', ip_confirmed=1)]}
        self.assertEqual(self.request('/api/import', 'POST', payload)[0], 200)
        self.assertTrue(all(row['ip_confirmed'] == 0 for row in app.inventory()))
