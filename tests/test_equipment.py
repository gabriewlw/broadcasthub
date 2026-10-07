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
        self.assertIn(b'brand,model,description,serial_number,quantity,location,notes', raw)
        self.assertEqual(self.request('/api/equipment', 'POST', ITEM, {'Content-Type':'application/json','Origin':'https://other.example'})[0], 403)
