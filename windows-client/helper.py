"""
PulseHelper — runs once per logged-in user, started at logon (the installer
registers it as a Scheduled Task with an "at log on" trigger; see
install.py). This is deliberately NOT a Windows Service: a Session-0
service cannot see this user's desktop, foreground window, or screen at
all (Windows' session isolation, enforced regardless of privilege level —
see pulse_agent/usage_tracker.py and pulse_agent/remote.py for exactly
where that matters). Everything that needs the logged-in user's own
session lives here; everything else (sync to the server, network totals,
browser-history reading across all users) lives in PulseService instead.

This process does its own waiting if the device isn't enrolled yet — it's
started unconditionally at every logon, before anyone necessarily ran the
one-time `pulse enroll` step.
"""
import ctypes
import sys
import time

sys.path.insert(0, __file__.rsplit('\\', 1)[0] if '\\' in __file__ else __file__.rsplit('/', 1)[0])


def _make_dpi_aware():
    """Remote control's "click lands in the wrong place" / "needs
    calibration" symptom traces to this: pulse_agent/remote.py's
    ImageGrab.grab() (what actually gets captured and uploaded, with its
    own w/h sent alongside each frame) and pulse_agent/input_sim.py's
    GetSystemMetrics(0/1) (what click()/move_to() scale taps into) both
    report screen dimensions — but on a non-DPI-aware process, Windows
    transparently virtualizes/scales BOTH of those APIs' results against
    whatever the system DPI setting is (125%/150% scaling is the Windows
    default on most modern laptop/monitor combos), and in practice the two
    don't always end up agreeing on a PyInstaller-frozen exe, whose
    default DPI-awareness manifest setting isn't guaranteed the way a
    normal Python.exe's is. The dashboard's own tap-coordinate math (see
    app.js's toDevX/toDevY) assumes capture resolution and click-injection
    resolution are the SAME coordinate space — any mismatch between them
    shows up as an offset that gets worse toward the edges of the screen,
    exactly like "needs calibration".
    Explicitly opting into Per-Monitor-v2 DPI awareness (the officially
    recommended fix for exactly this class of bug) makes every GDI/Win32
    call in this process — capture AND click injection alike — agree on
    TRUE PHYSICAL pixel coordinates, with Windows no longer virtualizing
    either of them. Falls through older, less precise APIs for Windows
    versions before the 2017 Creators Update, and gives up silently if
    none of them exist (odd/locked-down environment) rather than crashing
    PulseHelper over a coordinate-precision nicety.
    """
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 — Windows 10 1703+.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE — Windows 8.1+.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Vista+, system-DPI-aware only.
    except Exception:
        pass


# Must run before anything in this process touches the display (screen
# capture, GetSystemMetrics, mouse injection) — see _make_dpi_aware()'s
# docstring. Deliberately before the pulse_agent imports below, which pull
# in PIL.ImageGrab and ctypes.windll.user32 calls the moment RemoteControl
# is used.
_make_dpi_aware()

from pulse_agent import db
from pulse_agent.remote import RemoteControl
from pulse_agent.usage_tracker import UsageTracker


def main():
    while not db.get_str('device_token'):
        time.sleep(10)  # enrolled from PulseService/CLI; just wait until that's done

    usage = UsageTracker()
    usage.start()

    remote = RemoteControl()
    remote.start_watcher()

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        usage.stop()
        remote.stop()


if __name__ == '__main__':
    main()
