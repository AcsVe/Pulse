"""
Whole-device network totals. Windows has no single, reliable, low-privilege
API for PER-APP network usage the way Android's NetworkStatsManager does
(the real per-process numbers live behind ETW tracing, which is heavier to
set up than this client needs) — so, like the Android app's own fallback
for when per-app attribution isn't available, this client only ever reports
a device-wide total. See uploader.sync_once()'s '__device__' row and
server/stats.py's data_usage_table() fallback, which already exists for
exactly this shape of data.
"""
import socket
import time

import psutil


class NetTotals:
    def __init__(self):
        c = psutil.net_io_counters()
        self._last_rx = c.bytes_recv
        self._last_tx = c.bytes_sent
        self._last_t = time.monotonic()

    def delta(self):
        """Bytes moved (and the equivalent kbps, from the real elapsed time
        between calls rather than assuming the nominal cycle interval —
        a cycle running late shouldn't look like a speed change) since the
        previous call. Resets its baseline each time so repeated calls
        report non-overlapping windows, matching how the Android app's
        TrafficStats-based '__device__' rows work."""
        c = psutil.net_io_counters()
        now = time.monotonic()
        elapsed = max(0.001, now - self._last_t)
        rx = max(0, c.bytes_recv - self._last_rx)
        tx = max(0, c.bytes_sent - self._last_tx)
        self._last_rx, self._last_tx, self._last_t = c.bytes_recv, c.bytes_sent, now
        return {'rx': rx, 'tx': tx,
                'downKbps': round(rx * 8 / 1024 / elapsed), 'upKbps': round(tx * 8 / 1024 / elapsed)}


def primary_interface():
    """Which interface is actually carrying traffic (the one with a route
    to the internet, found the same way uploader._local_ip() picks the
    local IP to report) and its link type/speed — the dashboard's
    "Connection type"/"Wi-Fi speed" columns already exist (built for the
    Android app's equivalent), windows-client just never filled them in
    (connType was a hardcoded 'Ethernet/WiFi' placeholder). Windows has no
    cleaner "media type" through psutil, so Wi-Fi vs Ethernet is read off
    the interface's own name."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = None

    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    iface_name = None
    if local_ip:
        for name, alist in addrs.items():
            if any(a.family == socket.AF_INET and a.address == local_ip for a in alist):
                iface_name = name
                break
    if not iface_name:
        up = [(n, st) for n, st in stats.items() if st.isup and st.speed > 0]
        if not up:
            return None, None
        iface_name = max(up, key=lambda ns: ns[1].speed)[0]

    st = stats.get(iface_name)
    if not st:
        return None, None
    name_lower = iface_name.lower()
    conn_type = 'wifi' if any(k in name_lower for k in ('wi-fi', 'wireless', 'wlan')) else 'ethernet'
    return conn_type, (st.speed or None)
