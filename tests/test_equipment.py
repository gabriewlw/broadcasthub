import sqlite3
import unittest
import app
import test_app

ITEM = dict(brand='Blackmagic Design', model='ATEM Mini Pro', description='HDMI switcher', serial_number='ATEM-001', quantity=1, location='Broadcast center', notes='With PSU')


class EquipmentTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def test_crud_quantity_and_persistence(self):
        status, item = self.request('/api/equipment', 'POST', ITEM)
        self.assertEqual(status, 201)
        self.assertEqual(app.equipment_inventory()[0]['serial_number'], 'ATEM-001')
        path = f"/api/equipment/{item['id']}"
        status, item = self.request(path, 'PUT', dict(ITEM, quantity=0, location='Repair bench'))
        self.assertEqual(status, 200)
        self.assertEqual(item['quantity'], 0)
        self.assertEqual(self.request('/api/equipment')[1]['equipment'][0]['location'], 'Repair bench')
        self.assertEqual(self.request(path, 'DELETE', {})[0], 200)
        self.assertEqual(app.equipment_inventory(), [])
        self.assertEqual(self.request(path, 'DELETE', {})[0], 404)
        self.assertEqual(self.request('/api/devices')[1]['devices'], [])

    def test_validation_and_serial_duplicates(self):
        for quantity in (-1, 1.5, True, 'lots', 1000001):
            self.assertEqual(self.request('/api/equipment', 'POST', dict(ITEM, quantity=quantity))[0], 400)
        for field in ('brand','model','location'):
            self.assertEqual(self.request('/api/equipment', 'POST', dict(ITEM, **{field:123}))[0], 400)
        self.assertEqual(self.request('/api/equipment', 'POST', ITEM)[0], 201)
        self.assertEqual(self.request('/api/equipment', 'POST', dict(ITEM, serial_number='atem-001', location='Theater'))[0], 409)

    def test_import_roundtrip_and_atomic_errors(self):
        payload = {'version':1,'equipment':[ITEM, dict(ITEM, serial_number='', brand='Neutrik', model='XLR', quantity=20)]}
        self.assertEqual(self.request('/api/equipment/import', 'POST', payload)[1], {'added':2,'skipped':0})
        self.assertEqual(self.request('/api/equipment/import', 'POST', payload)[1], {'added':0,'skipped':2})
        exported = self.request('/api/equipment/export')[1]
        self.assertEqual(sum(i['quantity'] for i in exported['equipment']), 21)
        self.assertEqual(self.request('/api/equipment/import','POST', {'version':1,'equipment':[dict(ITEM,serial_number='new'),dict(ITEM,serial_number='other',quantity=-1)]})[0], 400)
        self.assertEqual(len(app.equipment_inventory()), 2)
        self.assertEqual(self.request('/api/equipment/import','POST', {'version':1,'equipment':[ITEM,ITEM]})[0], 400)
        self.assertEqual(self.request('/api/equipment', 'POST', dict(payload['equipment'][1], notes='Different note'))[0], 409)

    def test_csv_escape_and_cross_origin(self):
        self.request('/api/equipment', 'POST', dict(ITEM, description='=FORMULA()'))
        status, raw = self.request('/api/equipment/export.csv')
        self.assertEqual(status, 200)
        self.assertIn(b"'=FORMULA()", raw)
        self.assertIn(b'description,brand,model,serial_number,quantity,location,item_confirmed,notes', raw)
        self.assertEqual(self.request('/api/equipment', 'POST', ITEM, {'Content-Type':'application/json','Origin':'https://other.example'})[0], 403)

    def test_found_status_persists_and_resets_after_item_changes(self):
        item = self.request('/api/equipment', 'POST', ITEM)[1]
        path = f"/api/equipment/{item['id']}"
        self.assertEqual(item['item_confirmed'], 0)
        status, confirmed = self.request(path+'/confirm', 'POST', dict(item, item_confirmed=True))
        self.assertEqual(status, 200)
        self.assertEqual(app.equipment_inventory()[0]['item_confirmed'], 1)
        self.assertEqual(self.request(path, 'PUT', dict(item, notes='Located in the cabinet'))[1]['item_confirmed'], 1)
        self.assertEqual(self.request(path+'/confirm', 'POST', dict(item, item_confirmed=False))[1]['item_confirmed'], 0)
        for field, value in [('brand','Sony'), ('model','Other model'), ('description','Camera'),
                             ('serial_number','OTHER-01'), ('quantity',2), ('location','Theater')]:
            with self.subTest(field=field):
                current = self.request(path, 'PUT', ITEM)[1]
                self.assertEqual(self.request(path+'/confirm', 'POST', dict(current, item_confirmed=True))[0], 200)
                self.assertEqual(self.request(path, 'PUT', dict(ITEM, **{field:value}))[1]['item_confirmed'], 0)

    def test_confirmation_rejects_stale_or_invalid_items(self):
        item = self.request('/api/equipment', 'POST', ITEM)[1]
        path = f"/api/equipment/{item['id']}"
        self.request(path, 'PUT', dict(ITEM, location='Theater'))
        self.assertEqual(self.request(path+'/confirm', 'POST', dict(item, item_confirmed=True))[0], 400)
        self.assertEqual(app.equipment_inventory()[0]['item_confirmed'], 0)
        for payload in [dict(item, item_confirmed='yes'), dict(item, item_confirmed=1), dict(item_confirmed=True)]:
            self.assertEqual(self.request(path+'/confirm', 'POST', payload)[0], 400)
        self.assertEqual(self.request('/api/equipment/999/confirm', 'POST', dict(item, item_confirmed=True))[0], 404)

    def test_found_status_json_and_csv_transfers(self):
        item = self.request('/api/equipment', 'POST', ITEM)[1]
        self.request(f"/api/equipment/{item['id']}/confirm", 'POST', dict(item, item_confirmed=True))
        exported = self.request('/api/equipment/export')[1]
        self.assertEqual(exported['equipment'][0]['item_confirmed'], 1)
        with app.connect() as con:
            con.execute('DELETE FROM equipment')
        self.assertEqual(self.request('/api/equipment/import', 'POST', exported)[1], {'added':1,'skipped':0})
        self.assertEqual(app.equipment_inventory()[0]['item_confirmed'], 1)
        payload = dict(version=1, equipment=[dict(ITEM, serial_number='OTHER', item_confirmed='Found')])
        self.assertEqual(self.request('/api/equipment/import', 'POST', payload)[0], 200)
        self.assertEqual(self.request('/api/equipment/import', 'POST', dict(version=1,equipment=[dict(ITEM,serial_number='INVALID',item_confirmed='maybe')]))[0], 400)
        self.assertEqual(len(app.equipment_inventory()), 2)

    def test_migration_preserves_equipment_and_defaults_to_unchecked(self):
        with sqlite3.connect(app.DB_PATH) as con:
            con.execute("""CREATE TABLE equipment (id INTEGER PRIMARY KEY, brand TEXT NOT NULL,
                model TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL DEFAULT '',
                quantity INTEGER, location TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("INSERT INTO equipment VALUES (42,'Sony','Camera','Studio camera','SER-42',3,'Store','Keep note','2025-01-01')")
        row = app.equipment_inventory()[0]
        self.assertEqual((row['id'], row['quantity'], row['notes'], row['updated_at'], row['item_confirmed']), (42,3,'Keep note','2025-01-01',0))
