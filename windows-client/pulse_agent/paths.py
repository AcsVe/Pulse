"""
Where the Windows client keeps its files.

Everything lives under C:\\ProgramData\\Pulse rather than any one user's
profile, because two separate processes share it:

  - PulseService.exe runs as LocalSystem (Session 0) with no profile of its
    own worth using.
  - PulseHelper.exe runs once per logged-in user, in THAT user's session —
    required for anything session-bound (see helper.py's module docstring).

Both need read/write to the same local sqlite file (pulse.db — the config
and the local upload queue) and to the screen-capture scratch file. The
installer (install.py) grants the local "Users" group write access to this
folder with icacls right after creating it, since C:\\ProgramData is
writable by admins/SYSTEM only by default — without that, the per-user
helper (running as a standard, non-admin user on most of these machines)
could read pulse.db but never write a queued usage row or a captured frame
into it.
"""
import os

DATA_DIR = os.path.join(os.environ.get('ProgramData', r'C:\ProgramData'), 'Pulse')
DB_PATH = os.path.join(DATA_DIR, 'pulse.db')
FRAME_PATH = os.path.join(DATA_DIR, 'frame.jpg')
LOG_DIR = os.path.join(DATA_DIR, 'logs')


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
