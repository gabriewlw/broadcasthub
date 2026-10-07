import sqlite3
import unittest

import app
import test_app


class DHCPTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def test_repeated_dhcp_assignments_and_fixed_ip_conflicts(self):
        rows = [dict(name='Camera A', ip=' dhcp ', vlan=1500, venue='RD MAIN LOUNGE'),
                dict(name='Camera B', ip='DHCP', vlan=1500, venue='RD MAIN LOUNGE'),
                dict(name='Camera C', ip='DhCp')]
        status, result = self.request('/api/import', 'POST', dict(
            version=1, source='spreadsheet', devices=rows, row_numbers=[2, 3, 5]))
        self.assertEqual(status, 200)
        self.assertEqual(result, dict(added=3, skipped=0, warnings=[]))
        self.assertEqual([d['ip'] for d in app.inventory()], ['DHCP'] * 3)
        self.assertEqual(next(d for d in app.inventory() if d['name'] == 'Camera A')['venue'], 'MAIN LOUNGE')
        self.assertEqual(self.request('/api/devices', 'POST', dict(name='Camera D', ip='DHCP', vlan=1500))[0], 201)
        self.assertEqual(self.request('/api/devices', 'POST', test_app.EXAMPLE)[0], 201)
        self.assertEqual(self.request('/api/devices', 'POST', dict(test_app.EXAMPLE, vlan=1501))[0], 409)

    def test_confirmation_and_changes_between_static_and_dhcp(self):
        device = self.request('/api/devices', 'POST', test_app.EXAMPLE)[1]
        path = f"/api/devices/{device['id']}"
        self.assertEqual(self.request(path + '/confirm', 'POST', dict(ip=device['ip'], vlan=device['vlan']))[0], 200)
        status, changed = self.request(path, 'PUT', dict(device, ip='dhcp'))
        self.assertEqual(status, 200)
        self.assertEqual((changed['ip'], changed['ip_confirmed']), ('DHCP', 0))
        self.assertEqual(self.request(path + '/confirm', 'POST', dict(ip='DHCP', vlan=device['vlan']))[0], 400)
        fixed = self.request('/api/devices', 'POST', test_app.EXAMPLE)[1]
        self.assertEqual(self.request(path, 'PUT', dict(changed, ip=fixed['ip']))[0], 409)
        changed = self.request(path, 'PUT', dict(changed, ip='10.24.176.67'))[1]
        self.assertEqual(self.request(path + '/confirm', 'POST', dict(ip=changed['ip'], vlan=changed['vlan']))[0], 200)

    def test_iptv_and_export_preserve_repeated_dhcp_markers(self):
        rows = [dict(record_type='iptv', name=name, ip='DHCP', port=1234, channel_source='Onboard')
                for name in ('Channel A', 'Channel B')]
        self.assertEqual(self.request('/api/import', 'POST', dict(version=1, devices=rows))[1], dict(added=2, skipped=0))
        exported = self.request('/api/export')[1]
        self.assertEqual([d['ip'] for d in exported['devices']], ['DHCP', 'DHCP'])
        csv = self.request('/api/export.csv')[1].decode()
        self.assertEqual(csv.count('DHCP'), 2)
        with app.connect() as con:
            con.execute('DELETE FROM devices')
        self.assertEqual(self.request('/api/import', 'POST', exported)[1], dict(added=2, skipped=0))
        self.assertEqual(len(app.inventory()), 2)

    def test_upgrade_previous_constraints_without_erasing_devices(self):
        with sqlite3.connect(app.DB_PATH) as con:
            con.execute(app.SCHEMA.format(table='devices'))
            con.execute("CREATE UNIQUE INDEX device_assignment_known ON devices(ip,vlan) WHERE record_type='device' AND ip!=''")
            con.execute("CREATE UNIQUE INDEX channel_endpoint_known ON devices(ip,port) WHERE record_type='iptv' AND ip!='' AND port IS NOT NULL")
            con.execute("""CREATE TRIGGER device_known_ip_insert BEFORE INSERT ON devices
                WHEN NEW.record_type='device' AND NEW.ip!='' AND EXISTS
                (SELECT 1 FROM devices WHERE record_type='device' AND ip=NEW.ip)
                BEGIN SELECT RAISE(ABORT, 'Duplicate AV IP address'); END""")
            data = app.validate(test_app.EXAMPLE)
            con.execute('INSERT INTO devices (' + ','.join(app.ALL_FIELDS) + ') VALUES (' + ','.join('?' for _ in app.ALL_FIELDS) + ')', [data[f] for f in app.ALL_FIELDS])
        for name in ('One', 'Two'):
            self.assertEqual(self.request('/api/devices', 'POST', dict(name=name, ip='DHCP', vlan=1500))[0], 201)
        self.assertEqual(len(app.inventory()), 3)
        self.assertEqual(self.request('/api/devices', 'POST', dict(test_app.EXAMPLE, vlan=1501))[0], 409)


if __name__ == '__main__':
    unittest.main()
