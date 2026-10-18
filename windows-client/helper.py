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
import sys
import time

sys.path.insert(0, __file__.rsplit('\\', 1)[0] if '\\' in __file__ else __file__.rsplit('/', 1)[0])

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
