"""
Talks to the same Pulse server API the Android app uses
(server/app.py's /api/v1/* routes) — nothing on the server changes for this
client; it is just another device type speaking the same HTTP+JSON
protocol with its own OS string ("os": "Windows 10/11 build ...").
"""
import platform
import socket

import requests

from . import db

TIMEOUT = 15


def _server():
    url = db.get_str('server_url')
    token = db.get_str('device_token')
    return url, token


def enroll(server_url, code):
    server_url = server_url.rstrip('/')
    res = requests.post(f'{server_url}/api/v1/enroll', json={
        'code': code,
        'model': platform.node() or 'Windows PC',
        'os': f'Windows {platform.release()} ({platform.version()})',
        'app': 'windows-client/1.0',
    }, timeout=TIMEOUT)
    res.raise_for_status()
    data = res.json()
    if not data.get('token'):
        raise RuntimeError(data.get('error', 'enroll_failed'))
    db.put('server_url', server_url)
    db.put('device_token', data['token'])
    db.put('device_id', data['deviceId'])
    db.put('device_name', data.get('name', ''))
    return data


def check_server(server_url, token):
    """Same idea as the Android app's setServerUrl check: confirm the new
    address accepts this device's EXISTING token before committing to it,
    without touching enrollment at all."""
    try:
        r = requests.get(f'{server_url.rstrip("/")}/api/v1/ping',
                          headers={'Authorization': f'Bearer {token}'}, timeout=TIMEOUT)
        return r.ok
    except requests.RequestException:
        return False


def _local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ''


def sync_once(net_totals=None):
    """Drains the local queues into one /api/v1/ingest call. net_totals, if
    given, is {'rx': int, 'tx': int} of bytes moved since the last call —
    posted as a single '__device__' dataUsage row, mirroring the fallback
    the dashboard/server already use for a device with no per-app breakdown
    (stats.py's data_usage_table — see Pulse's Android-side history)."""
    server_url, token = _server()
    if not server_url or not token:
        return False

    usage_rows = db.pending('usage_q')
    browse_rows = db.pending('browse_q')
    data_rows = db.pending('data_q')

    body = {
        'usage': [{'package': r['package'], 'label': r['label'], 'start': r['start_ts'], 'end': r['end_ts']}
                  for r in usage_rows],
        'browse': [{'ts': r['ts'], 'source': r['source'], 'app': r['app'], 'url': r['url'],
                    'domain': r['domain'], 'title': r['title']} for r in browse_rows],
        'dataUsage': [{'package': r['package'], 'label': r['label'], 'ts': r['ts'], 'rx': r['rx'], 'tx': r['tx'],
                       'transport': r['transport']} for r in data_rows],
        'ip': _local_ip(),
        'connType': 'Ethernet/WiFi',
        'model': platform.node() or 'Windows PC',
        'os': f'Windows {platform.release()}',
        'app': 'windows-client/1.0',
        # There's no Android-style "accessibility service" here; browser
        # history comes straight from each browser's own History file
        # instead, so this is always true once the client is running at all
        # — it's here mainly so the dashboard's existing warning badge logic
        # (built for the Android app) has something to read.
        'accessibilityEnabled': True,
    }
    if net_totals:
        body['dataUsage'].append({'package': '__device__', 'label': '__device__', 'ts': db.now_ms(),
                                   'rx': int(net_totals.get('rx') or 0), 'tx': int(net_totals.get('tx') or 0),
                                   'transport': ''})

    res = requests.post(f'{server_url}/api/v1/ingest', json=body,
                         headers={'Authorization': f'Bearer {token}'}, timeout=TIMEOUT)
    res.raise_for_status()

    db.mark_synced('usage_q', [r['id'] for r in usage_rows])
    db.mark_synced('browse_q', [r['id'] for r in browse_rows])
    db.mark_synced('data_q', [r['id'] for r in data_rows])
    return res.json()


def ping():
    server_url, token = _server()
    if not server_url or not token:
        return None
    r = requests.get(f'{server_url}/api/v1/ping', headers={'Authorization': f'Bearer {token}'}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def remote_state():
    server_url, token = _server()
    if not server_url or not token:
        return None
    r = requests.get(f'{server_url}/api/v1/remote-state', headers={'Authorization': f'Bearer {token}'},
                      timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def upload_frame(jpeg_bytes, w, h):
    server_url, token = _server()
    if not server_url or not token:
        return False
    r = requests.post(f'{server_url}/api/v1/screen?w={w}&h={h}', data=jpeg_bytes,
                       headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/octet-stream'},
                       timeout=TIMEOUT)
    return r.ok


def poll_commands():
    server_url, token = _server()
    if not server_url or not token:
        return []
    r = requests.get(f'{server_url}/api/v1/commands', headers={'Authorization': f'Bearer {token}'}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get('commands', [])
