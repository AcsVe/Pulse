"""
CPU/RAM snapshot — the other half of what netinfo.py's primary_interface()
covers for connection type/speed. Together these fill in dashboard columns
and chart data that already existed (built for the Android app's own
equivalents) but windows-client never actually populated.
"""
import psutil

# psutil.cpu_percent(interval=None) measures the average since the PREVIOUS
# call, not an instant snapshot — its own docs call the very first call
# after import "meaningless" (nothing to measure since). Priming it once
# here, at import time (service_main.py imports this module well before its
# first real cycle), means sync_once()'s first real reading already covers
# real elapsed time instead of returning 0.0. Not calling interval=1 here
# or in cpu_percent() below: that blocks the calling thread for a full
# second every single cycle, which there's no need to pay given the
# ~10s cycle this runs on already provides a representative window.
psutil.cpu_percent(interval=None)


def cpu_percent():
    return psutil.cpu_percent(interval=None)


def memory_mb():
    """(used_mb, total_mb) — 'used' here is total-available (matches what
    Windows' own Task Manager shows), not psutil's raw .used, which counts
    reclaimable cache/buffers as "used" and reads much higher than what a
    person watching this number would expect."""
    m = psutil.virtual_memory()
    used_mb = int((m.total - m.available) / (1024 * 1024))
    total_mb = int(m.total / (1024 * 1024))
    return used_mb, total_mb
