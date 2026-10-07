import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import app

EXAMPLE = dict(name='ATEM video switcher', category='Video switcher', venue='Liquid Lounge', discipline='Video', ip='10.24.176.66', vlan=1500, notes='Rack 2')


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app.DB_PATH = Path(self.temp.name) / 'inventory.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        req = Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, method=method, headers=headers or {'Content-Type': 'application/json'})
        try:
            response = urlopen(req)
        except HTTPError as error:
            response = error
        with response:
            content = response.read()
            return response.status, json.loads(content) if response.headers['Content-Type'].startswith('application/json') else content

    def test_full_lifecycle_and_persistence(self):
        status, saved = self.request('/api/devices', 'POST', EXAMPLE)
        self.assertEqual(status, 201)
        self.assertEqual(saved['ip'], '10.24.176.66')
        self.assertEqual(app.inventory()[0]['venue'], 'Liquid Lounge')
        self.assertEqual(self.request('/api/devices')[1]['devices'][0]['id'], saved['id'])
        updated = dict(EXAMPLE, name='ATEM main')
        self.assertEqual(self.request(f"/api/devices/{saved['id']}", 'PUT', updated)[0], 200)
        self.assertEqual(app.inventory()[0]['name'], 'ATEM main')
        self.assertEqual(self.request(f"/api/devices/{saved['id']}", 'DELETE', {})[0], 200)
        self.assertEqual(app.inventory(), [])
        self.assertEqual(self.request(f"/api/devices/{saved['id']}", 'DELETE', {})[0], 404)

    def test_validation(self):
        for ip in ('10.24.176.999', 'hello', '127.0.0.1', '224.0.0.1', '0.0.0.0', '255.255.255.255', '10.24.176.066'):
            with self.subTest(ip=ip):
                self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, ip=ip))[0], 400)
        for vlan in (0, 4095, 1.5, True, '1e3', 'text'):
            with self.subTest(vlan=vlan):
                self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, vlan=vlan))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, name=123))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, discipline='invalid'))[0], 400)

    def test_duplicate_scope(self):
        self.assertEqual(self.request('/api/devices', 'POST', EXAMPLE)[0], 201)
        self.assertEqual(self.request('/api/devices', 'POST', EXAMPLE)[0], 409)
        self.assertEqual(self.request('/api/devices', 'POST', dict(EXAMPLE, vlan=1501))[0], 409)

    def test_export_import_roundtrip_and_idempotence(self):
        self.request('/api/devices', 'POST', EXAMPLE)
        status, payload = self.request('/api/export')
        self.assertEqual(status, 200)
        self.assertEqual(payload['version'], 1)
        with app.connect() as con:
            con.execute('DELETE FROM devices')
        self.assertEqual(self.request('/api/import', 'POST', payload)[1], {'added': 1, 'skipped': 0})
        self.assertEqual(self.request('/api/import', 'POST', payload)[1], {'added': 0, 'skipped': 1})
        self.assertEqual(app.inventory()[0]['ip'], EXAMPLE['ip'])

    def test_import_is_atomic(self):
        payload = {'version': 1, 'devices': [EXAMPLE, dict(EXAMPLE, ip='not valid')]}
        self.assertEqual(self.request('/api/import', 'POST', payload)[0], 400)
        self.assertEqual(app.inventory(), [])
        payload['devices'] = [EXAMPLE, EXAMPLE]
        status, result = self.request('/api/import', 'POST', payload)
        self.assertEqual(status, 200)
        self.assertEqual((result['added'], result['skipped']), (1, 1))
        self.assertIn(EXAMPLE['ip'], result['warnings'][0])
        self.assertEqual(len(app.inventory()), 1)

    def test_csv_formula_protection(self):
        self.request('/api/devices', 'POST', dict(EXAMPLE, name='=HYPERLINK("evil")'))
        status, content = self.request('/api/export.csv')
        self.assertEqual(status, 200)
        self.assertIn(b"'=HYPERLINK", content)

    def test_cross_origin_and_assets(self):
        status, _ = self.request('/api/devices', 'POST', EXAMPLE, {'Content-Type': 'application/json', 'Origin':'https://other.example'})
        self.assertEqual(status, 403)
        for path in ('/', '/app.js', '/style.css', '/icon.svg'):
            self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(self.request('/../app.py')[0], 404)


if __name__ == '__main__':
    unittest.main()
