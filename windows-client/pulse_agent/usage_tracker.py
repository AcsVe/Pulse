"""
Foreground-app usage tracking — the Windows counterpart to Android's
UsageStatsManager-based UsageCollector.

This MUST run inside PulseHelper (the per-user process), never inside the
Session-0 service: GetForegroundWindow() only ever returns a window from
the caller's own session, and a Session-0 service has no desktop session of
its own to have a foreground window in at all — it would just see nothing,
silently, forever. This is the same category of platform wall the Android
app ran into with MediaProjection surviving a reboot: not a bug to work
around, a boundary Windows enforces for every process regardless of
privilege level.
"""
import threading
import time

import psutil
import win32gui
import win32process

from . import db

POLL_S = 2


class UsageTracker:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._cur_exe = None
        self._cur_start = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name='pulse-usage')
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._close_current()

    def _exe_for_foreground(self):
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return None, None
            p = psutil.Process(pid)
            exe = (p.name() or '').strip()
            title = win32gui.GetWindowText(hwnd) or exe
            return exe, title
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            return None, None

    def _close_current(self):
        if self._cur_exe and self._cur_start:
            db.add_usage(self._cur_exe, self._cur_exe, self._cur_start, db.now_ms())
        self._cur_exe = None
        self._cur_start = None

    def _run(self):
        FLUSH_MS = 5 * 60 * 1000  # cap a single session's length so a long-foregrounded
        while not self._stop.is_set():  # app (e.g. a browser left open all afternoon) still
            exe, _title = self._exe_for_foreground()  # gets synced well before the user switches away
            now = db.now_ms()
            if exe != self._cur_exe:
                self._close_current()
                if exe:
                    self._cur_exe = exe
                    self._cur_start = now
            elif exe and self._cur_start and now - self._cur_start > FLUSH_MS:
                db.add_usage(exe, exe, self._cur_start, now)
                self._cur_start = now
            time.sleep(POLL_S)
        self._close_current()
