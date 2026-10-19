"""
Pulse-Setup — the one-time setup tool for the Windows client. Run elevated
(as Administrator) once per machine:

    Pulse-Setup.exe enroll <serverUrl> <code>
    Pulse-Setup.exe install
    Pulse-Setup.exe status
    Pulse-Setup.exe uninstall

`install` does three things:
  1. Grants the local Users group write access to C:\\ProgramData\\Pulse,
     via icacls, by SID (S-1-5-32-545) rather than the localized name
     "Users" — so this also works on non-English Windows installs. Needed
     because PulseHelper runs as a plain logged-in user, not an admin, and
     has to be able to queue rows into the shared sqlite file there.
  2. Installs and starts PulseService (the Session-0 half) via its own
     pywin32 service verbs.
  3. Drops a shortcut to PulseHelper.exe into the ALL-USERS Startup folder
     (not a per-user one, and not a Scheduled Task) — the simplest reliable
     way to have it launch inside EVERY user's own desktop session at
     logon, which is what PulseHelper actually needs (see its docstring).
"""
import ctypes
import os
import subprocess
import sys

# A frozen --onefile exe's __file__ resolves into a throwaway temp
# extraction folder (sys._MEIxxxxx), not the folder the .exe actually sits
# in — the exact same PyInstaller onefile pitfall server/app.py's
# RESOURCE_DIR/DATA_DIR comment already covers for the server .exe.
# sys.executable's directory is the stable one: where Pulse-Setup.exe,
# PulseService.exe and PulseHelper.exe actually live side by side.
HERE = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) \
    else os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pulse_agent import db, license, uploader
# PulseService/PulseHelper are built --onedir (a folder, not a single .exe) —
# see service_main.py's module docstring for why onefile mode is wrong for
# a service specifically. Pulse-Setup.exe itself stays --onefile; it's a
# one-shot CLI tool with no startup-time budget to blow.
SERVICE_EXE = os.path.join(HERE, 'PulseService', 'PulseService.exe')
HELPER_EXE = os.path.join(HERE, 'PulseHelper', 'PulseHelper.exe')
USERS_SID = 'S-1-5-32-545'
STARTUP_DIR = os.path.join(os.environ.get('ProgramData', r'C:\ProgramData'),
                            r'Microsoft\Windows\Start Menu\Programs\StartUp')
SHORTCUT_PATH = os.path.join(STARTUP_DIR, 'PulseHelper.lnk')


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def require_admin():
    if not is_admin():
        print('This needs to run from an elevated (Administrator) prompt.')
        sys.exit(1)


def cmd_enroll(args):
    if len(args) != 2:
        print('Usage: Pulse-Setup.exe enroll <serverUrl> <code>')
        sys.exit(1)
    require_admin()
    server_url, code = args
    # Only cmd_install() used to call this — fine for the installer's own
    # enroll-then-install sequence, since that whole sequence already runs
    # under the installer's own full elevation (Administrators have
    # implicit full control of ProgramData regardless of this ACL). But
    # enroll can also run standalone later (relink.bat, or "enroll" typed
    # by hand to re-link a device), on a folder whose ACL was never granted
    # to begin with — a device enrolled by an older build before this
    # icacls step existed, say. ProgramData's own default ACL gives
    # standard Users only READ access, not write, so sqlite then fails with
    # "attempt to write a readonly database" — a confusing error for
    # something that's really just a missing permission grant. Doing this
    # here too, defensively, makes enroll self-sufficient regardless of
    # install order or a device's ACL history. (Needs require_admin() above
    # it, same as install — granting an ACL generally needs elevation too.)
    _grant_programdata_access()
    try:
        res = uploader.enroll(server_url, code)
        print(f"Enrolled as '{res.get('name')}' (device id {res.get('deviceId')}).")
    except Exception as e:
        print(f'Enrollment failed: {e}')
        sys.exit(1)


def _grant_programdata_access():
    from pulse_agent import paths
    paths.ensure_dirs()
    subprocess.run(['icacls', paths.DATA_DIR, '/grant', f'*{USERS_SID}:(OI)(CI)M', '/T'],
                   check=False, capture_output=True)


def _install_startup_shortcut():
    os.makedirs(STARTUP_DIR, exist_ok=True)
    import win32com.client
    shell = win32com.client.Dispatch('WScript.Shell')
    sc = shell.CreateShortcut(SHORTCUT_PATH)
    sc.TargetPath = HELPER_EXE
    sc.WorkingDirectory = os.path.dirname(HELPER_EXE)  # so it finds its own onedir-bundled DLLs
    sc.Description = 'Pulse device-monitoring helper (runs per logged-in user)'
    sc.save()


def cmd_install(_args):
    require_admin()
    if not db.get_str('device_token'):
        print('Not enrolled yet — run "Pulse-Setup.exe enroll <serverUrl> <code>" first.')
        sys.exit(1)
    if not os.path.exists(SERVICE_EXE) or not os.path.exists(HELPER_EXE):
        print(f'Expected {SERVICE_EXE} and {HELPER_EXE} — keep the PulseService/ and PulseHelper/ '
              f'folders next to Pulse-Setup.exe, exactly as the zip extracted them.')
        sys.exit(1)

    print('Granting local Users write access to the shared data folder...')
    _grant_programdata_access()

    print('Installing and starting PulseService...')
    subprocess.run([SERVICE_EXE, '--startup=auto', 'install'], check=True)
    subprocess.run([SERVICE_EXE, 'start'], check=True)

    print('Registering PulseHelper to start for every user at logon...')
    _install_startup_shortcut()

    print('Done. The service is running, and PulseHelper will start the next time anyone logs in')
    print('(sign out/in now, or just reboot, to have it pick up the current session immediately).')


def cmd_uninstall(_args):
    require_admin()
    if os.path.exists(SERVICE_EXE):
        subprocess.run([SERVICE_EXE, 'stop'], check=False)
        subprocess.run([SERVICE_EXE, 'remove'], check=False)
    if os.path.exists(SHORTCUT_PATH):
        os.remove(SHORTCUT_PATH)
    subprocess.run(['taskkill', '/IM', 'PulseHelper.exe', '/F'], check=False, capture_output=True)
    print('PulseService and the startup entry have been removed. Local data in '
          f'{os.environ.get("ProgramData")}\\Pulse was left in place.')


def cmd_status(_args):
    url = db.get_str('server_url')
    name = db.get_str('device_name')
    if not url:
        print('Not enrolled.')
        return
    print(f"Server: {url}\nDevice: {name or '(unnamed)'}")
    try:
        r = uploader.ping()
        print(f"Reachable: yes (server time {r.get('now')})" if r else 'Reachable: no')
    except Exception as e:
        print(f'Reachable: no ({e})')

    licensed, state, exp = license.status()
    if licensed:
        when = 'never (permanent)' if exp == 'PERMANENT' else exp
        print(f'License: valid, expires {when}')
    elif state == 'expired':
        print(f'License: EXPIRED on {exp} — device fingerprint: {license.fingerprint()} '
              f'(send this to the developer for a new key, then run "license <key>")')
    elif state == 'invalid':
        print(f'License: INVALID key on file — device fingerprint: {license.fingerprint()}')
    else:
        print(f'License: not activated — device fingerprint: {license.fingerprint()} '
              f'(send this to the developer, then run "license <key>")')


def cmd_fingerprint(_args):
    print(license.fingerprint())


def cmd_license(args):
    if len(args) != 1:
        print('Usage: Pulse-Setup.exe license <key>')
        sys.exit(1)
    ok, exp, err = license.activate(args[0])
    if err and err != 'EXPIRED':
        print({
            'bad_format': 'That key is not in the right format.',
            'bad_encoding': "That key's signature couldn't be decoded.",
            'invalid_signature': "That key doesn't match this device's fingerprint "
                                  f'({license.fingerprint()}) — check it was issued for this exact PC.',
            'bad_expiration': 'That key has a malformed expiration date.',
        }.get(err, f'Invalid license key ({err}).'))
        sys.exit(1)
    if err == 'EXPIRED':
        print(f'License saved, but it already expired on {exp}. Send the fingerprint below to the '
              f'developer for a new key: {license.fingerprint()}')
        sys.exit(1)
    when = 'permanent — never expires' if exp == 'PERMANENT' else f'valid until {exp}'
    print(f'License activated ({when}). The service will start reporting data on its next cycle.')


COMMANDS = {
    'enroll': cmd_enroll, 'install': cmd_install, 'uninstall': cmd_uninstall, 'status': cmd_status,
    'fingerprint': cmd_fingerprint, 'license': cmd_license,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f'Usage: Pulse-Setup.exe <{"|".join(COMMANDS)}> [args]')
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    main()
