import unittest
import app
import test_app

CHANNEL = dict(test_app.EXAMPLE, name='Ship information', category='IPTV channel', record_type='iptv', channel_source='Onboard', ip='239.1.1.10')


class IPTVTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def test_channel_source_multicast_and_confirmation(self):
        status, channel = self.request('/api/devices', 'POST', CHANNEL)
        self.assertEqual(status, 201)
        self.assertEqual(channel['channel_source'], 'Onboard')
        path = f"/api/devices/{channel['id']}"
        status, channel = self.request(path+'/confirm', 'POST', dict(ip=channel['ip'], vlan=channel['vlan']))
        self.assertEqual(status, 200)
        self.assertEqual(channel['ip_confirmed'], 1)
        status, channel = self.request(path, 'PUT', dict(CHANNEL, channel_source='Satellite'))
        self.assertEqual(status, 200)
        self.assertEqual(channel['channel_source'], 'Satellite')
        self.assertEqual(app.inventory()[0]['record_type'], 'iptv')

    def test_source_and_address_validation(self):
        for source in ('', 'Cable', None):
            self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, channel_source=source))[0], 400)
        for ip in ('127.0.0.1', '0.0.0.0', '255.255.255.255', '239.1.1.999'):
            self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, ip=ip))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', dict(test_app.EXAMPLE, ip='239.1.1.10'))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, record_type='unknown'))[0], 400)

    def test_mixed_export_import_and_old_record_defaults(self):
        self.request('/api/devices', 'POST', test_app.EXAMPLE)
        self.request('/api/devices', 'POST', CHANNEL)
        payload = self.request('/api/export')[1]
        self.assertEqual({r['record_type'] for r in payload['devices']}, {'device', 'iptv'})
        with app.connect() as con:
            con.execute('DELETE FROM devices')
        self.assertEqual(self.request('/api/import', 'POST', payload)[1], {'added':2, 'skipped':0})
        self.assertEqual(next(r for r in app.inventory() if r['record_type'] == 'iptv')['channel_source'], 'Onboard')
        self.assertEqual(next(r for r in app.inventory() if r['record_type'] == 'device')['channel_source'], '')
