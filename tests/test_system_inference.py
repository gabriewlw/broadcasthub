import unittest

import app
import test_app


class SystemInferenceTests(unittest.TestCase):
    setUpClass = test_app.AppTests.__dict__['setUpClass']
    tearDownClass = test_app.AppTests.__dict__['tearDownClass']
    setUp = test_app.AppTests.setUp
    tearDown = test_app.AppTests.tearDown
    request = test_app.AppTests.request

    def import_rows(self, rows, spreadsheet=True):
        payload = dict(version=1, devices=rows)
        if spreadsheet:
            payload.update(source='spreadsheet', row_numbers=list(range(2, len(rows) + 2)))
        return self.request('/api/import', 'POST', payload)

    def test_every_requested_keyword_persists_after_import(self):
        rules = [('audio','Audio'), ('AMX','Control'), ('DSP','Audio'), ('Clickshare','Video'),
                 ('Pixera','Video'), ('TV','Video'), ('Video','Video'), ('Light','Lighting'),
                 ('CAM','Video'), ('Camera','Video'), ('Cam','Video'), ('BGM','Audio'),
                 ('Decoder','Video'), ('Encoder','Video'), ('Multiview','Video'), ('Scala','Video'),
                 ('Blackmagic','Video'), ('Castus','Video'),
                 ('Switch','Network'), ('Dante','Audio'), ('CCTV','Video'), ('IEM','Audio')]
        rows = [dict(name=f'Rack {keyword} {index}', ip='DHCP') for index, (keyword, _) in enumerate(rules)]
        self.assertEqual(self.import_rows(rows)[1], dict(added=len(rules), skipped=0, warnings=[]))
        stored = {row['name']:row['discipline'] for row in app.inventory()}
        for row, (_, expected) in zip(rows, rules):
            self.assertEqual(stored[row['name']], expected)
        exported = self.request('/api/export')[1]
        self.assertEqual({row['name']:row['discipline'] for row in exported['devices']}, stored)

    def test_case_insensitive_contains_and_first_rule_priority(self):
        names = {'rACK-aUdIo-04':'Audio', 'Audio Video Switcher':'Audio',
                 'AMX DSP controller':'Control', 'Pixera Switch':'Video',
                 'Dante Switch':'Network', 'LIGHTING console':'Lighting',
                 'Rack bLaCkMaGiC Design':'Video', 'Rack cAsTuS server':'Video',
                 'Blackmagic Switcher':'Video', 'Castus Switch':'Video'}
        self.assertEqual(self.import_rows([dict(name=name) for name in names])[0], 200)
        self.assertEqual({row['name']:row['discipline'] for row in app.inventory()}, names)

    def test_blank_unknown_and_explicit_systems_preserve_imported_information(self):
        rows = [dict(name='Camera', discipline='Control'), dict(name='Unknown spare'),
                dict(venue='Storage'), dict(name='CAM 01')]
        self.assertEqual(self.import_rows(rows, False)[1], dict(added=4, skipped=0))
        stored = {row['name']:row for row in app.inventory()}
        self.assertEqual(stored['Camera']['discipline'], 'Control')
        self.assertEqual(stored['Unknown spare']['discipline'], '')
        self.assertEqual(stored['']['discipline'], '')
        self.assertEqual(stored['CAM 01']['discipline'], 'Video')
        # A later dropdown choice remains authoritative and keeps all other fields.
        row = stored['CAM 01']
        changed = self.request(f"/api/devices/{row['id']}/system", 'POST', dict(discipline='Audio'))[1]
        self.assertEqual(changed['discipline'], 'Audio')
        self.assertEqual(changed['name'], 'CAM 01')

    def test_manual_iptv_and_existing_assignments_are_not_reclassified(self):
        self.request('/api/devices', 'POST', dict(name='Camera manual'))
        self.import_rows([dict(name='Audio channel', record_type='iptv')])
        fixed = self.request('/api/devices', 'POST', dict(name='Old device', ip='10.24.176.20', discipline='Control'))[1]
        self.assertEqual(self.import_rows([dict(name='Camera replacement', ip=fixed['ip'])])[1]['skipped'], 1)
        stored = {row['name']:row for row in app.inventory()}
        self.assertEqual(stored['Camera manual']['discipline'], '')
        self.assertEqual(stored['Audio channel']['discipline'], '')
        self.assertEqual(stored['Old device']['discipline'], 'Control')


if __name__ == '__main__':
    unittest.main()
