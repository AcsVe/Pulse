"""
Browser history, read straight from each browser's own History sqlite file
instead of the Android app's approach (an Accessibility service reading the
address bar live, screen by screen). Reading the file directly is actually
MORE complete here — it catches every visit between polls, not just
whatever happened to be on-screen — and needs no special Windows
permission beyond ordinary file access to the profile folder.

Covers Chrome and Edge (both Chromium, identical History schema) across
every local user profile under C:\\Users — a Session-0 service can see all
of them (unlike the per-user PulseHelper), so this runs there.
"""
import glob
import os
import shutil
import sqlite3
import tempfile
import time

from . import db

# Chrome/Edge timestamps are microseconds since 1601-01-01 UTC, not Unix epoch.
_CHROME_EPOCH_OFFSET_US = 11644473600 * 1000 * 1000


def _chrome_to_unix_ms(chrome_us):
    return (chrome_us - _CHROME_EPOCH_OFFSET_US) // 1000


def _profile_dirs():
    patterns = [
        r'C:\Users\*\AppData\Local\Google\Chrome\User Data\*\History',
        r'C:\Users\*\AppData\Local\Microsoft\Edge\User Data\*\History',
    ]
    found = []
    for pat in patterns:
        for path in glob.glob(pat):
            # Only the numbered/"Default" profile folders hold real History
            # files; "System Profile" etc also match the glob but don't.
            if os.path.isfile(path):
                found.append(path)
    return found


def _read_new_visits(history_path, since_unix_ms):
    """Copies the (likely locked, actively-written-to) History file before
    reading it — the standard safe way to read a browser's live sqlite
    database without risking a lock conflict with the browser itself, or
    corrupting anything by opening the original file."""
    tmp = os.path.join(tempfile.gettempdir(), f'pulse_hist_{os.getpid()}_{int(time.time()*1000)}.sqlite')
    try:
        shutil.copy2(history_path, tmp)
    except Exception:
        return []  # browser may hold an exclusive lock at this instant — just skip this cycle
    rows = []
    try:
        conn = sqlite3.connect(tmp)
        since_chrome = since_unix_ms * 1000 + _CHROME_EPOCH_OFFSET_US
        cur = conn.execute(
            """SELECT v.visit_time, u.url, u.title FROM visits v
               JOIN urls u ON u.id = v.url
               WHERE v.visit_time > ? ORDER BY v.visit_time ASC LIMIT 2000""",
            (since_chrome,))
        for visit_time, url, title in cur.fetchall():
            rows.append((_chrome_to_unix_ms(visit_time), url, title or ''))
        conn.close()
    except sqlite3.Error:
        pass
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return rows


def collect():
    """Reads every local Chrome/Edge profile and queues new visits since
    each profile's own last-seen checkpoint (kept per profile path, since
    different profiles/browsers advance independently)."""
    added = 0
    for path in _profile_dirs():
        key = 'hist_ck:' + path
        since = int(db.get_str(key, '0') or '0')
        rows = _read_new_visits(path, since)
        if not rows:
            continue
        browser = 'Edge' if 'Microsoft\\Edge' in path or 'Microsoft/Edge' in path else 'Chrome'
        max_ts = since
        for ts, url, title in rows:
            domain = ''
            try:
                from urllib.parse import urlparse
                domain = (urlparse(url).hostname or '').lower()
            except Exception:
                pass
            db.add_browse(ts, 'history', browser, url[:2000], domain[:255], title[:300])
            max_ts = max(max_ts, ts)
            added += 1
        db.put(key, str(max_ts))
    return added
