"""Smoke tests against the Flask test client (no network, no real DB needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import db  # noqa: E402


class PulseApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'TESTING': True,
            'ADMIN_USER': 'admin',
            'ADMIN_PASS': 'secret',
            'SCREEN_KEY': 'screenkey',
        })
        self.client = self.app.test_client()

    def login(self):
        return self.client.post('/login', data={'username': 'admin', 'password': 'secret'})

    def test_login_required_for_api(self):
        r = self.client.get('/api/devices')
        self.assertEqual(r.status_code, 401)

    def test_login_and_create_device(self):
        self.login()
        r = self.client.post('/api/devices', json={'name': 'Test Phone'})
        self.assertEqual(r.status_code, 201)
        body = r.get_json()
        self.assertEqual(body['name'], 'Test Phone')
        self.assertTrue(body['enrollCode'])

    def test_enroll_and_ingest_roundtrip(self):
        self.login()
        d = self.client.post('/api/devices', json={'name': 'Phone'}).get_json()
        r = self.client.post('/api/v1/enroll', json={'code': d['enrollCode']})
        self.assertEqual(r.status_code, 200)
        token = r.get_json()['token']

        ingest = self.client.post('/api/v1/ingest', headers={'Authorization': f'Bearer {token}'}, json={
            'usage': [{'package': 'com.test.app', 'label': 'Test', 'start': 1000, 'end': 5000}],
            'net': [{'kind': 'connected', 'transport': 'wifi', 'start': 1000, 'end': 5000}],
            'browse': [{'ts': 2000, 'source': 'dns', 'domain': 'example.com'}],
            'dataUsage': [{'package': 'com.test.app', 'label': 'Test', 'ts': 1000, 'rx': 2000, 'tx': 500},
                          {'package': '__device__', 'ts': 1000, 'rx': 3000, 'tx': 900}],
            'memory': [{'ts': 1000, 'usedMb': 1200, 'totalMb': 4000}],
            'ip': '192.168.1.50',
        })
        self.assertEqual(ingest.status_code, 200)
        self.assertEqual(ingest.get_json()['added'], {'usage': 1, 'net': 1, 'browse': 1, 'data': 2, 'memory': 1})

        overview = self.client.get('/api/overview?from=0&to=99999999999&tz=0')
        self.assertEqual(overview.status_code, 200)
        kpis = {k['key']: k['value'] for k in overview.get_json()['kpis']}
        self.assertEqual(kpis['sessions'], 1)
        self.assertEqual(kpis['download'], 3000)
        self.assertEqual(kpis['upload'], 900)

        data_table = self.client.get('/api/table/data?from=0&to=99999999999')
        self.assertEqual(data_table.status_code, 200)
        self.assertEqual(data_table.get_json()[0]['rx'], 2000)

        mem = self.client.get('/api/memory?from=0&to=99999999999')
        self.assertEqual(mem.get_json()['latest']['usedMb'], 1200)

        self.login()
        devs = self.client.get('/api/devices').get_json()
        self.assertEqual(devs[0]['ipAddress'], '192.168.1.50')

    def test_device_rename(self):
        self.login()
        d = self.client.post('/api/devices', json={'name': 'Old'}).get_json()
        r = self.client.patch(f'/api/devices/{d["id"]}', json={'name': 'New Name'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['name'], 'New Name')

    def test_app_label_override(self):
        self.login()
        r = self.client.put('/api/app-labels', json={'package': 'com.test.app', 'label': 'My App'})
        self.assertEqual(r.get_json()['label'], 'My App')
        listing = self.client.get('/api/app-labels').get_json()
        self.assertEqual(listing['com.test.app'], 'My App')

    def test_email_settings_roundtrip(self):
        self.login()
        r = self.client.put('/api/email-settings', json={
            'enabled': True, 'smtpHost': 'smtp.example.com', 'smtpUser': 'me@example.com',
            'smtpPass': 'secret', 'recipient': 'owner@example.com', 'frequency': 'daily', 'hourUtc': 6,
            'sections': ['overview', 'apps'],
        })
        body = r.get_json()
        self.assertTrue(body['hasPassword'])
        self.assertNotIn('smtpPass', body)
        g = self.client.get('/api/email-settings').get_json()
        self.assertEqual(g['recipient'], 'owner@example.com')
        self.assertEqual(g['sections'], ['overview', 'apps'])

    def test_cron_endpoint_requires_key(self):
        r = self.client.get('/api/cron/send-reports')
        self.assertEqual(r.status_code, 401)

    def test_enroll_bad_code_rejected(self):
        r = self.client.post('/api/v1/enroll', json={'code': 'NOPE'})
        self.assertEqual(r.status_code, 403)

    def test_poll_interval_and_wifi_mbps(self):
        self.login()
        d = self.client.post('/api/devices', json={'name': 'Phone'}).get_json()
        r = self.client.patch(f'/api/devices/{d["id"]}', json={'pollIntervalS': 10})
        self.assertEqual(r.get_json()['pollIntervalS'], 10)
        # clamp: too small/too large both get clamped, not rejected
        r2 = self.client.patch(f'/api/devices/{d["id"]}', json={'pollIntervalS': 999999})
        self.assertEqual(r2.get_json()['pollIntervalS'], 3600)

        token = self.client.post('/api/v1/enroll', json={'code': d['enrollCode']}).get_json()['token']
        ingest = self.client.post('/api/v1/ingest', headers={'Authorization': f'Bearer {token}'},
                                   json={'wifiMbps': 433})
        self.assertEqual(ingest.status_code, 200)
        devs = self.client.get('/api/devices').get_json()
        self.assertEqual(devs[0]['wifiMbps'], 433)

    def test_remote_control_flow(self):
        self.login()
        d = self.client.post('/api/devices', json={'name': 'Phone'}).get_json()
        token = self.client.post('/api/v1/enroll', json={'code': d['enrollCode']}).get_json()['token']
        auth = {'Authorization': f'Bearer {token}'}

        # not active yet: device sees inactive, dashboard can't queue a command
        state = self.client.get('/api/v1/remote-state', headers=auth).get_json()
        self.assertFalse(state['active'])
        bad = self.client.post(f'/api/devices/{d["id"]}/remote/command', json={'action': 'tap', 'x': 1, 'y': 2})
        self.assertEqual(bad.status_code, 400)

        # admin starts a remote session
        started = self.client.post(f'/api/devices/{d["id"]}/remote/start')
        self.assertTrue(started.get_json()['remoteActive'])
        state2 = self.client.get('/api/v1/remote-state', headers=auth).get_json()
        self.assertTrue(state2['active'])

        # device uploads a frame
        up = self.client.post('/api/v1/screen?w=1080&h=2280', headers=auth, data=b'\xff\xd8\xff fake jpeg bytes')
        self.assertEqual(up.get_json()['ok'], True)
        img = self.client.get(f'/api/devices/{d["id"]}/screen.jpg?key=screenkey')
        self.assertEqual(img.status_code, 200)
        self.assertEqual(img.data, b'\xff\xd8\xff fake jpeg bytes')

        # dashboard queues a tap, device polls and consumes it once
        q = self.client.post(f'/api/devices/{d["id"]}/remote/command', json={'action': 'tap', 'x': 10, 'y': 20})
        self.assertEqual(q.status_code, 200)
        poll1 = self.client.get('/api/v1/commands', headers=auth).get_json()
        self.assertEqual(len(poll1['commands']), 1)
        self.assertEqual(poll1['commands'][0]['action'], 'tap')
        self.assertEqual(poll1['commands'][0]['params'], {'x': 10, 'y': 20})
        poll2 = self.client.get('/api/v1/commands', headers=auth).get_json()
        self.assertEqual(poll2['commands'], [])  # already consumed

        # admin stops the session
        stopped = self.client.post(f'/api/devices/{d["id"]}/remote/stop')
        self.assertFalse(stopped.get_json()['remoteActive'])
        state3 = self.client.get('/api/v1/remote-state', headers=auth).get_json()
        self.assertFalse(state3['active'])

    def test_email_settings_unrestricted_and_per_device(self):
        self.login()
        r = self.client.put('/api/email-settings', json={
            'enabled': True, 'smtpHost': 'smtp.example.com', 'recipient': 'owner@example.com',
            'frequency': 'hourly', 'unrestricted': True, 'perDevice': True,
        })
        body = r.get_json()
        self.assertEqual(body['frequency'], 'hourly')
        self.assertTrue(body['unrestricted'])
        self.assertTrue(body['perDevice'])

    def test_screen_key_grants_readonly_access(self):
        r = self.client.get('/api/devices?key=screenkey')
        self.assertEqual(r.status_code, 200)
        # but not write access
        r2 = self.client.post('/api/devices?key=screenkey', json={'name': 'x'})
        self.assertEqual(r2.status_code, 401)

    def test_bootstrap_superadmin_from_env(self):
        self.login()
        me = self.client.get('/api/me').get_json()
        self.assertEqual(me['username'], 'admin')
        self.assertEqual(me['role'], 'superadmin')
        self.assertEqual(me['deviceIds'], [])

    def test_only_superadmin_manages_users_and_email_settings(self):
        self.login()
        self.client.post('/api/users', json={'username': 'viewer1', 'password': 'viewerpass', 'role': 'viewer'})
        self.client.get('/logout')
        self.client.post('/login', data={'username': 'viewer1', 'password': 'viewerpass'})
        # viewer can read devices but not manage users or email settings
        self.assertEqual(self.client.get('/api/devices').status_code, 200)
        self.assertEqual(self.client.get('/api/users').status_code, 401)
        self.assertEqual(self.client.get('/api/email-settings').status_code, 401)
        self.assertEqual(self.client.post('/api/devices', json={'name': 'x'}).status_code, 401)

    def test_scoped_admin_sees_only_assigned_devices(self):
        self.login()
        d1 = self.client.post('/api/devices', json={'name': 'Phone A'}).get_json()
        d2 = self.client.post('/api/devices', json={'name': 'Phone B'}).get_json()
        self.client.post('/api/users', json={
            'username': 'scopedadmin', 'password': 'scopedpass', 'role': 'admin', 'deviceIds': [d1['id']],
        })
        self.client.get('/logout')
        self.client.post('/login', data={'username': 'scopedadmin', 'password': 'scopedpass'})

        listed = self.client.get('/api/devices').get_json()
        self.assertEqual([d['id'] for d in listed], [d1['id']])

        # can rename/administer the assigned device...
        ok = self.client.patch(f'/api/devices/{d1["id"]}', json={'name': 'Renamed A'})
        self.assertEqual(ok.status_code, 200)
        # ...but not the out-of-scope one
        blocked = self.client.patch(f'/api/devices/{d2["id"]}', json={'name': 'Nope'})
        self.assertEqual(blocked.status_code, 401)

        overview = self.client.get('/api/overview?from=0&to=99999999999&tz=0')
        self.assertEqual(overview.status_code, 200)  # scoping degrades to "nothing visible", never a crash

    def test_cannot_delete_or_demote_last_superadmin(self):
        self.login()
        me = self.client.get('/api/me').get_json()
        r = self.client.delete(f'/api/users/{me["id"]}')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()['error'], 'cannot_delete_self')
        self.client.post('/api/users', json={'username': 'second', 'password': 'secondpass', 'role': 'viewer'})
        r2 = self.client.patch(f'/api/users/{me["id"]}', json={'role': 'viewer'})
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(r2.get_json()['error'], 'last_superadmin')

    def test_username_must_be_unique_and_password_min_length(self):
        self.login()
        r1 = self.client.post('/api/users', json={'username': 'admin', 'password': 'whatever1'})
        self.assertEqual(r1.get_json()['error'], 'username_taken')
        r2 = self.client.post('/api/users', json={'username': 'short', 'password': '123'})
        self.assertEqual(r2.get_json()['error'], 'password_too_short')

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()


if __name__ == '__main__':
    unittest.main()
