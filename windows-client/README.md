# Pulse — Windows client

The Windows counterpart to `android-app/`: talks to the same server
(`server/`), the same `/api/v1/*` endpoints, no server-side changes needed.
Covers the three features asked for: app usage, browser history, and
remote control (screen + mouse/keyboard) — network usage is reported as a
whole-device total rather than per-app (see `pulse_agent/netinfo.py` for
why).

## Why three executables, not one

Windows enforces **session isolation**: a process running as a Windows
*Service* lives in Session 0, which has no desktop of its own — it can
never see a logged-in user's foreground window, capture their screen, or
inject mouse/keyboard input into their session, no matter how high its
privileges are. This isn't a bug to work around; it's the same kind of
hard platform wall the Android app hit with MediaProjection consent not
surviving a reboot.

So the work is split by which side of that wall it needs to be on:

- **PulseService/** (a folder, containing `PulseService.exe`) — a real
  Windows Service (Session 0). Syncs to the server, reads browser history
  files (across every local user profile), measures device-wide network
  totals, and drains the local upload queue.
- **PulseHelper/** (same: a folder, containing `PulseHelper.exe`) — runs
  once per logged-in user, in *that* user's own session (started via a
  Startup-folder shortcut, not a service). Tracks the foreground app, and
  — only while the dashboard has remote control turned on for this device
  — captures the screen and executes incoming tap/swipe/text/etc. commands.
- **Pulse-Setup.exe** — the one-time setup tool that ties the other two
  together (see below). Not something that keeps running, so it's a single
  file rather than a folder.

PulseService and PulseHelper are each a *folder* rather than a single
`.exe` — deliberately: Windows' Service Control Manager only waits ~30
seconds for a service to report itself started, and a single-file
("onefile") build has to re-extract its entire bundle to a temp folder on
every launch, which can itself take longer than that wait on a slower disk
or under antivirus scanning. A folder build pays that unpacking cost once,
at build time, not on every start. Keep each folder's contents together
exactly as the zip extracted them — moving just the `.exe` out on its own
will not work.

Both PulseService and PulseHelper read/write the same local sqlite file
under `C:\ProgramData\Pulse\pulse.db` — PulseHelper queues rows into it
(usage sessions), PulseService is what actually uploads them.

## Setting it up

From an elevated (Administrator) Command Prompt, in the folder you
unzipped `Pulse-Windows-Client.zip` into:

```
Pulse-Setup.exe enroll https://your-server.example.com XXXXXXXX
Pulse-Setup.exe install
```

`enroll` takes the same server URL + one-time linking code the dashboard
generates for any device. `install` grants the local Users group write
access to `C:\ProgramData\Pulse` (icacls), installs and starts
PulseService, and drops a shortcut to `PulseHelper\PulseHelper.exe` into
the all-users Startup folder. Sign out and back in (or reboot) once
afterward so PulseHelper picks up the currently logged-in session.

To remove everything: `Pulse-Setup.exe uninstall` (also elevated). Local
data under `C:\ProgramData\Pulse` is left in place; delete that folder by
hand if you want it gone too.

## Known gaps, as of this first build

- **Not yet tested on real Windows hardware** — built and type-checked,
  but this environment has no Windows machine to actually run it on.
  PyInstaller + pywin32 services in particular are known to need small
  per-machine fixes (missing DLL, a hidden import); report back whatever
  error comes up on first install/start.
- **Per-app network usage** isn't available — only a device-wide total.
- **Browser history** currently covers Chrome and Edge (both Chromium,
  same `History` file format). Firefox uses a different format and isn't
  read yet.
- **Remote control's `pinch`/zoom action** has no desktop equivalent and
  is ignored; `tap`/`swipe`/`text`/`back`/`home`/`recents`/`launch`/`close`
  all work, mapped to the closest Windows equivalent (e.g. `home` → Win+D,
  `recents` → Win+Tab). A press-and-hold (≥0.5s) on the remote screen sends
  a real right-click (`rightclick`), and the dashboard's ⌨ button (shown
  only for Windows devices) opens a live keyboard — typed characters and
  named keys (Enter/Backspace/Tab/Escape/arrows/Win, plus Ctrl/Alt combos)
  go through as `key` commands instead of the old batch-a-string-then-send
  box, which couldn't do either.
- **Unsigned executables**: Windows SmartScreen or antivirus software may
  flag first-run of an unsigned `.exe` downloaded from the internet — same
  situation the Android APK and server `.exe` are already in.
