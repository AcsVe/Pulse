"""
Keeps PulseHelper running in every logged-in interactive session by
relaunching it within a few seconds if it isn't there.

This does NOT, and cannot, stop someone from ending PulseHelper.exe
themselves — Windows has no mechanism to deny a user the right to
terminate their own unprivileged process running under their own account
(unlike PulseService, which runs as LocalSystem and a standard user simply
has no permission to touch at all). What this buys instead is the same
thing most monitoring/parental-control tools rely on: ending it stops
doing anything useful, because it's back within one watchdog cycle. Only
PulseService (LocalSystem) can do the relaunch, because starting a process
inside someone ELSE's logged-in session from a service requires duplicating
that session's own user token (WTSQueryUserToken) plus two privileges a
plain user account doesn't hold — SeTcbPrivilege is NOT required here (that
would need the service account itself to BE a trusted part of the OS,
which LocalSystem already is), but SeIncreaseQuotaPrivilege and
SeAssignPrimaryTokenPrivilege do need to be explicitly enabled on this
process's own token first; see _enable_privilege() below.

Call ensure_helper_running() periodically from PulseService's cycle
(service_main.py). Every failure path is swallowed — a session with no
one logged in yet, a session that's locked, a privilege that didn't
enable — because this is a convenience respawn, not something that should
ever be allowed to crash the sync loop it rides alongside.
"""
import os
import sys

import psutil
import win32con
import win32process
import win32security
import win32ts
import win32profile

HERE = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) \
    else os.path.dirname(os.path.abspath(__file__))
# service_main.py runs from PulseService\PulseService.exe, so PulseHelper's
# own onedir folder is a sibling one level up — same layout pulse_cli.py's
# HELPER_EXE already assumes.
HELPER_EXE = os.path.join(os.path.dirname(HERE), 'PulseHelper', 'PulseHelper.exe')


def _enable_privilege(name):
    htoken = win32security.OpenProcessToken(
        win32process.GetCurrentProcess(),
        win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY)
    try:
        luid = win32security.LookupPrivilegeValue(None, name)
        win32security.AdjustTokenPrivileges(htoken, False, [(luid, win32security.SE_PRIVILEGE_ENABLED)])
    finally:
        win32security.CloseHandle(htoken)


def _privileges_enabled():
    for name in ('SeIncreaseQuotaPrivilege', 'SeAssignPrimaryTokenPrivilege'):
        try:
            _enable_privilege(name)
        except Exception:
            return False
    return True


def _active_session_ids():
    """Only genuinely logged-in, unlocked desktop sessions — WTSActive, not
    WTSDisconnected/WTSConnectQuery/etc. Launching into a disconnected
    session's token still technically works but just wastes a relaunch on
    a desktop nobody can see yet."""
    ids = []
    for session in win32ts.WTSEnumerateSessions():
        if session.get('State') == win32ts.WTSActive:
            ids.append(session['SessionId'])
    return ids


def _helper_running_in_session(session_id):
    for p in psutil.process_iter(['name', 'pid']):
        try:
            if (p.info['name'] or '').lower() != 'pulsehelper.exe':
                continue
            if win32ts.ProcessIdToSessionId(p.info['pid']) == session_id:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _launch_in_session(session_id):
    token = win32ts.WTSQueryUserToken(session_id)
    try:
        env = win32profile.CreateEnvironmentBlock(token, False)
        startup = win32process.STARTUPINFO()
        startup.dwFlags = win32con.STARTF_USESHOWWINDOW
        startup.wShowWindow = win32con.SW_HIDE
        win32process.CreateProcessAsUser(
            token, HELPER_EXE, None, None, None, False,
            win32con.CREATE_UNICODE_ENVIRONMENT | win32con.NORMAL_PRIORITY_CLASS,
            env, os.path.dirname(HELPER_EXE), startup)
    finally:
        token.Close()


def ensure_helper_running():
    if not os.path.exists(HELPER_EXE) or not _privileges_enabled():
        return
    for session_id in _active_session_ids():
        try:
            if not _helper_running_in_session(session_id):
                _launch_in_session(session_id)
        except Exception:
            continue  # e.g. session switched away mid-check — try again next cycle
