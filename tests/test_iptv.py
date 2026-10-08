import sqlite3
import unittest
import app
import test_app

CHANNEL = dict(name='Ship information', record_type='iptv', channel_source='Onboard', ip='239.1.1.10', port=1234)


class IPTVTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def test_bundled_satellite_reference_available_without_external_requests(self):
        status, catalog = self.request('/satellite-channels.json')
        self.assertEqual(status, 200)
        self.assertEqual(catalog['version'], 1)
        channels = {row['name']: row for row in catalog['channels']}
        for name in ['Sport 24', 'CNN International', 'BBC News', 'National Geographic']:
            self.assertIn(name, channels)
        self.assertIn('BBC World News', channels['BBC News']['aliases'])
        self.assertEqual(len(channels), len(catalog['channels']))
        for channel in catalog['channels']:
            if channel['logo']:
                status, image = self.request(channel['logo'])
                self.assertEqual(status, 200)
                self.assertTrue(image.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(self.request('/channel-logos/missing.us.png')[0], 404)
        self.assertEqual(self.request('/channel-logos/../satellite-channels.json')[0], 404)

    def test_only_galaxy_31_logos_are_stored_and_regional_names_match(self):
        catalog = self.request('/satellite-channels.json')[1]
        scope = catalog['logo_scope']
        expected_names = {
            'CBS News', 'HGTV East', 'Food Network East', 'Travel Channel East',
            'Nickelodeon East', 'ESPNU', 'ESPN US', 'ESPN 2 US', 'SEC Network',
            'CruiseSat test card', 'Sky News International', 'Sky Sports News',
            'ESPN Caribbean', 'ESPN 2 Caribbean', 'Rai Italia Nord America',
            'RTL Deutschland', 'TVE Internacional América', 'National Geographic East',
            'National Geographic Wild', 'MS Now', 'CNBC US', 'MLB Network',
        }
        self.assertEqual(scope['satellite'], 'Galaxy 31')
        self.assertEqual({row['name'] for row in scope['channels']}, expected_names)
        scoped_ids = {row['channel_id'] for row in scope['channels']}
        channels = {row['id']: row for row in catalog['channels']}
        for row in scope['channels']:
            channel = channels[row['channel_id']]
            self.assertIn(row['name'], [channel['name'], *channel['aliases']])
        for channel in channels.values():
            if channel['id'] not in scoped_ids:
                self.assertIsNone(channel['logo'])
                self.assertNotIn('logo_reference', channel)
        self.assertEqual(channels['ESPNCaribbean.us']['logo'], channels['ESPN.us']['logo'])
        self.assertEqual(channels['ESPN2Caribbean.us']['logo'], channels['ESPN2.us']['logo'])
        self.assertIsNone(channels['RaiItalia.it']['logo'])
        self.assertIsNone(channels['CruiseSatTestCard.local']['logo'])
        used = {row['logo'].rsplit('/', 1)[1] for row in channels.values() if row['logo']}
        stored = {path.name for path in (app.ROOT / 'static/channel-logos').glob('*.png')}
        self.assertEqual(stored, used)
        self.assertEqual(len(stored), 18)
        self.assertEqual(self.request('/channel-logos/CNNInternational.us.png')[0], 404)

    def test_channel_source_multicast_and_no_confirmation(self):
        status, channel = self.request('/api/devices', 'POST', CHANNEL)
        self.assertEqual(status, 201)
        self.assertEqual(channel['channel_source'], 'Onboard')
        path = f"/api/devices/{channel['id']}"
        status, channel = self.request(path+'/confirm', 'POST', dict(ip=channel['ip'], vlan=channel['vlan']))
        self.assertEqual(status, 400)
        status, channel = self.request(path, 'PUT', dict(CHANNEL, channel_source='Satellite'))
        self.assertEqual(status, 200)
        self.assertEqual(channel['channel_source'], 'Satellite')
        self.assertEqual(app.inventory()[0]['record_type'], 'iptv')
        self.assertEqual(channel['port'], 1234)
        self.assertIsNone(channel['vlan'])
        self.assertEqual(channel['venue'], '')

    def test_source_and_address_validation(self):
        for source in ('Cable', 123):
            self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, channel_source=source))[0], 400)
        for ip in ('127.0.0.1', '0.0.0.0', '255.255.255.255', '239.1.1.999'):
            self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, ip=ip))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', dict(test_app.EXAMPLE, ip='239.1.1.10'))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, record_type='unknown'))[0], 400)

    def test_port_validation_and_endpoint_uniqueness(self):
        for port in (0, 65536, 1.5, True, '1e3'):
            with self.subTest(port=port):
                self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, port=port))[0], 400)
        self.assertEqual(self.request('/api/devices', 'POST', CHANNEL)[0], 201)
        self.assertEqual(self.request('/api/devices', 'POST', CHANNEL)[0], 409)
        self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, port=1235))[0], 201)
        self.assertEqual(self.request('/api/devices', 'POST', dict(test_app.EXAMPLE, ip='10.24.176.66'))[0], 201)
        self.assertEqual(self.request('/api/devices', 'POST', dict(CHANNEL, ip='10.24.176.66', port=5000))[0], 201)

    def test_legacy_channels_preserved_without_inventing_ports(self):
        with sqlite3.connect(app.DB_PATH) as con:
            con.execute("""CREATE TABLE devices (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                category TEXT NOT NULL, venue TEXT NOT NULL, discipline TEXT NOT NULL, ip TEXT NOT NULL,
                vlan INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT '', record_type TEXT NOT NULL DEFAULT 'device',
                channel_source TEXT NOT NULL DEFAULT '', ip_confirmed INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(ip,vlan))""")
            row = dict(test_app.EXAMPLE, name='Old channel', record_type='iptv', channel_source='Satellite', ip='239.1.1.10')
            fields = app.FIELDS + ('record_type','channel_source')
            con.execute('INSERT INTO devices (' + ','.join(fields) + ') VALUES (?,?,?,?,?,?,?,?,?)', [row[f] for f in fields])
        channel = app.inventory()[0]
        self.assertEqual(channel['name'], 'Old channel')
        self.assertIsNone(channel['port'])
        self.assertIsNone(channel['vlan'])
        self.assertEqual(channel['venue'], '')
        with app.connect() as con:
            self.assertEqual(con.execute('SELECT venue FROM devices').fetchone()['venue'], 'Liquid Lounge')
        channel['port'] = 1234
        status, saved = self.request(f"/api/devices/{channel['id']}", 'PUT', channel)
        self.assertEqual(status, 200)
        self.assertEqual(saved['port'], 1234)
        self.assertEqual(len(app.inventory()), 1)

    def test_import_skips_repeated_endpoints_and_continues(self):
        self.request('/api/devices', 'POST', dict(CHANNEL, notes='Keep this note'))
        rows = [dict(CHANNEL, name='Existing endpoint', notes='Do not overwrite'),
                dict(CHANNEL, name='New endpoint', ip='239.1.1.20', notes='Imported note'),
                dict(CHANNEL, name='Repeated endpoint', ip='239.1.1.20'),
                dict(CHANNEL, name='Next endpoint', ip='239.1.1.21')]
        status, result = self.request('/api/import', 'POST', dict(version=1, devices=rows))
        self.assertEqual(status, 200)
        self.assertEqual((result['added'], result['skipped']), (2, 2))
        self.assertEqual({row['name'] for row in app.inventory()}, {'Ship information', 'New endpoint', 'Next endpoint'})
        self.assertEqual(next(row['notes'] for row in app.inventory() if row['name'] == 'Ship information'), 'Keep this note')
        self.assertEqual(next(row['notes'] for row in app.inventory() if row['name'] == 'New endpoint'), 'Imported note')

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
