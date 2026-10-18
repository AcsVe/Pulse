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

from pulse_agent import browser_history, db, netinfo, uploader

DEFAULT_INTERVAL_S = 30


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
        try:
            browser_history.collect()
        except Exception:
            servicemanager.LogErrorMsg('Pulse: browser_history.collect() failed')
        try:
            totals = self.net.delta()
            result = uploader.sync_once(net_totals=totals)
            if isinstance(result, dict) and result.get('pollIntervalS'):
                return max(10, int(result['pollIntervalS']))
        except Exception:
            servicemanager.LogErrorMsg('Pulse: sync_once() failed')
        return DEFAULT_INTERVAL_S

    def main(self):
        while self.running:
            interval = self._cycle()
            rc = win32event.WaitForSingleObject(self.hWaitStop, interval * 1000)
            if rc == win32event.WAIT_OBJECT_0:
                break


if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(PulseService)
