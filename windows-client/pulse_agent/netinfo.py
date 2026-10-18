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
import psutil


class NetTotals:
    def __init__(self):
        c = psutil.net_io_counters()
        self._last_rx = c.bytes_recv
        self._last_tx = c.bytes_sent

    def delta(self):
        """Bytes moved since the previous call. Resets its baseline each
        time so repeated calls report non-overlapping windows, matching how
        the Android app's TrafficStats-based '__device__' rows work."""
        c = psutil.net_io_counters()
        rx = max(0, c.bytes_recv - self._last_rx)
        tx = max(0, c.bytes_sent - self._last_tx)
        self._last_rx, self._last_tx = c.bytes_recv, c.bytes_sent
        return {'rx': rx, 'tx': tx}
