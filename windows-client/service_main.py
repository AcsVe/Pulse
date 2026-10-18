"""
PulseService — the Session-0 Windows Service half of the Windows client.
Handles everything that does NOT need a logged-in user's own desktop
session: talking to the Pulse server, device-wide network totals, and
reading browser history files across every local user profile.

Session-bound work (foreground-app tracking, screen capture, simulated
input) lives in helper.py/PulseHelper instead — see its module docstring
for why a service can't do that part itself. Both processes share the same
local sqlite file (pulse_agent/db.py) under C:\\ProgramData\\Pulse;
PulseHelper queues rows into it, and this service is what actually uploads
them on its regular cycle.

Install/manage like any pywin32 service, e.g. from an elevated prompt:
    PulseService.exe install
    PulseService.exe start
    PulseService.exe stop
    PulseService.exe remove
(pulse_cli.py's `install` command wraps this plus the PulseHelper logon
shortcut and the one-time enrollment step into one call.)

Built --onedir (a folder, not PyInstaller's --onefile) rather than a single
.exe, specifically because of this role: Windows' Service Control Manager
only waits ~30s for a newly-started service to report itself running, and
--onefile re-extracts its entire bundle (interpreter, pywin32, psutil,
Pillow) to a fresh temp folder on EVERY launch before any of this code even
starts — on a slower disk, or with antivirus scanning that extraction, that
alone can blow past 30s and the service start fails with "did not respond
in a timely fashion" despite the service being perfectly healthy once
running. --onedir pays that unpacking cost once, at build time, not on
every service start.
"""
import sys
import time

sys.path.insert(0, __file__.rsplit('\\', 1)[0] if '\\' in __file__ else __file__.rsplit('/', 1)[0])

import servicemanager
import win32event
import win32service
import win32serviceutil

from pulse_agent import browser_history, db, license, netinfo, uploader

# Was 30 — the dashboard's own refresh is already faster than that (8s, see
# app.js's init()), so the service itself was the bottleneck on "why hasn't
# this number updated yet". The server can still slow a device back down via
# sync_once()'s pollIntervalS if that ever matters.
DEFAULT_INTERVAL_S = 10


class PulseService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'PulseService'
    _svc_display_name_ = 'Pulse Monitoring Service'
    _svc_description_ = ('Collects app usage, browser history, and network totals for the Pulse '
                          'dashboard, and relays remote-control sessions. Part of Pulse '
                          '(github.com/AcsVe/Pulse).')

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.net = netinfo.NetTotals()
        self._warned_unlicensed = False

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.running = False

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                               servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, ''))
        self.main()

    def _cycle(self):
        if not db.get_str('device_token'):
            return DEFAULT_INTERVAL_S  # not enrolled yet — nothing to sync; just keep idling

        # No data leaves this device until a valid activation key is on
        # file — see pulse_agent/license.py and pulse_cli.py's `license`
        # command. Logged once (not every cycle) so the event log doesn't
        # fill up with the same line every 10 seconds.
        if not license.is_licensed():
            if not self._warned_unlicensed:
                servicemanager.LogErrorMsg(
                    f'Pulse: not licensed yet — device fingerprint {license.fingerprint()}. '
                    f'Send it to the developer, then run "Pulse-Setup.exe license <key>".')
                self._warned_unlicensed = True
            return DEFAULT_INTERVAL_S
        self._warned_unlicensed = False

        try:
            browser_history.collect()
        except Exception as e:
            servicemanager.LogErrorMsg(f'Pulse: browser_history.collect() failed: {e!r}')
        try:
            totals = self.net.delta()
            result = uploader.sync_once(net_totals=totals)
            if isinstance(result, dict) and result.get('pollIntervalS'):
                return max(10, int(result['pollIntervalS']))
        except Exception as e:
            servicemanager.LogErrorMsg(f'Pulse: sync_once() failed: {e!r}')
        return DEFAULT_INTERVAL_S

    def main(self):
        while self.running:
            interval = self._cycle()
            rc = win32event.WaitForSingleObject(self.hWaitStop, interval * 1000)
            if rc == win32event.WAIT_OBJECT_0:
                break


if __name__ == '__main__':
    if len(sys.argv) == 1:
        # Launched by the Service Control Manager itself (no arguments at
        # all — exactly how SCM starts any service) rather than from a
        # console. win32serviceutil.HandleCommandLine()'s own detection of
        # this case is unreliable inside a PyInstaller-frozen exe
        # specifically — it works fine for `PulseService.exe debug` (a
        # genuine command-line argument, so HandleCommandLine's explicit
        # verb handling kicks in and runs fine), but silently fails to ever
        # call StartServiceCtrlDispatcher for the real no-argument SCM
        # launch, so the process just sits there and SCM eventually gives
        # up with "service did not respond" (Windows error 1053) — even
        # though the exact same code runs perfectly under `debug`. Driving
        # servicemanager directly sidesteps HandleCommandLine's detection
        # entirely for this one case; `install`/`start`/`stop`/`remove`/
        # `debug` all still go through HandleCommandLine as normal.
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PulseService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PulseService)
