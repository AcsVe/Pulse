# Pulse

Pulse is a device-monitoring system with two parts:

- **server/** — a Flask dashboard (deploy to Render, Neon/Postgres or any host) that
  stores events and shows reports, comparisons and sortable tables, with a kiosk
  mode (`/screen?key=...`) meant for a wall-mounted smart screen.
- **android-app/** — a visible, disclosed Android app that collects app-usage
  sessions, browsing history (via an Accessibility service reading the browser's
  address bar, and via a local DNS-monitoring VPN that sees every app's lookups),
  and network outage periods (no-internet / connection-failed / disconnected),
  and uploads them to the server.

This is a disclosed monitoring tool, not spyware: the app keeps its icon, shows a
persistent notification while running, and requires an explicit on-device consent
screen before anything is collected. Using it on a device you don't own or without
the device user's knowledge may be illegal where you are — that's on you to check.

## Server

```
cd server
pip install -r requirements.txt
cp .env.example .env   # set SECRET_KEY, ADMIN_USER, ADMIN_PASS, SCREEN_KEY, DATABASE_URL
python app.py          # http://localhost:5000
```

Deploy to Render with `server/render.yaml` (Blueprint deploy), or anywhere that
runs `gunicorn app:app`. Set `DATABASE_URL` to a Postgres connection string in
production (SQLite is the local-dev default).

Environment variables:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing key |
| `ADMIN_USER` / `ADMIN_PASS` | the very first login, created once on first run as the bootstrap "superadmin" account (see "Users & permissions" below) — only read when the `users` table is empty, so changing them later has no effect once that account exists |
| `SCREEN_KEY` | read-only key for `/screen?key=...` (the kiosk view) — leave blank to disable kiosk access |
| `DATABASE_URL` | Postgres (or `sqlite:///...`) connection string |
| `APK_DOWNLOAD_URL` | where the Devices tab's "Download the Pulse app" link points (defaults to this repo's latest release) |

### Seed demo data

```
cd server
python3 tests/seed.py        # 2 fake devices, 14 days of data, SQLite file pulse_dev.db
```

### Tests

```
cd server
python3 -m unittest tests.test_app -v
```

## Android app

`android-app/` is a thin Capacitor shell around a small local setup screen
(`www/`); all the real work is hand-written Java under `android-app/native-src/`,
injected into the Capacitor-generated Android project by
`scripts/inject-native.js` during the CI build (there's no Android SDK in this
dev environment, so the Gradle build itself only runs in GitHub Actions —
`.github/workflows/build-apk.yml`). Push to `main` under `android-app/**`, or
run the workflow manually, to build and publish `Pulse.apk` as the repo's
`apk-latest` GitHub release — the same stable URL the dashboard's download
button and `APK_DOWNLOAD_URL` point at.

Optional signing secrets (so app updates install over the old one instead of
needing an uninstall first) — see the comment at the top of the workflow file.

### Self-protection features (for the device owner's own peace of mind)

- **Auto-start on boot** — `BootReceiver` restarts the collector after a
  reboot if monitoring was left on.
- **Survives the setup screen being swiped away** — `onTaskRemoved` restarts
  the collector service immediately if an OEM launcher kills it when the app
  (the setup UI, not the monitoring itself) is removed from Recents.
- **Local PIN lock** — a 4–6 digit passcode (salted hash, stored only on the
  device) is required every time the app is opened, and again before "Stop
  monitoring" actually takes effect.
- **Hidden launcher icon** — optional, toggled from the Status screen. The
  persistent running notification (which Android requires and this app can't
  remove) always reopens the app when tapped, regardless of the icon's
  hidden state, so this can never lock the owner out.
- **Uninstall protection** — an optional Device Admin registration. While
  active, Android's own "Uninstall" button is disabled for this app; removing
  it requires first deactivating device admin access from Settings >
  Security > "Apps with device admin access". This is the only uninstall
  friction a normal (non-MDM-enrolled) Android app can add — there is no
  platform API for putting a custom passcode in front of the system's own
  uninstall/deactivate dialogs.

### What it collects, and how

| Data | How | Android permission/service |
|---|---|---|
| App usage sessions | `UsageStatsManager` events, polled every ~60s and reassembled into foreground sessions | Usage Access (special access screen, not a manifest permission) |
| Browser URLs | An `AccessibilityService` reads the address-bar view of common browsers (Chrome, Firefox, Samsung Internet, Edge, Opera, Brave, …) | Accessibility settings |
| Visited domains (all apps) | A local, DNS-only `VpnService` — it does **not** tunnel general traffic, it only advertises itself as the device's DNS resolver and intercepts port-53 lookups, forwarding them to a real resolver (1.1.1.1) so normal browsing keeps working | VPN permission (one-time system dialog) |
| Network outages | `ConnectivityManager` network callbacks + an active HTTP probe (`generate_204`) classify each period as `connected` / `no_internet` (network up, probe fails) / `failed` (a very short-lived connection attempt that bounced) / `disconnected` (no network at all) | Internet, Access Network State |
| Data usage (download/upload) | `TrafficStats` per-UID counters, sampled every 15 min and diffed into per-interval deltas (one row per app, plus a `__device__` row for the whole-device total) | None (public API) |
| Memory usage | `ActivityManager.getMemoryInfo()`, sampled every 5 min | None (public API) |
| Device IP address | Local interface lookup (`NetworkInterface`), sent with each sync | None |

Known limitations:
- DNS-over-HTTPS (used by Chrome/Firefox by default on some networks) bypasses
  the port-53 interception, so for those the Accessibility-based URL capture is
  the one that still works.
- Aggressive manufacturer battery managers (MIUI, some Samsung/Huawei builds)
  can still kill the background service despite the "ignore battery
  optimization" exemption; there's no fully reliable workaround from the app
  side beyond asking the device owner to also whitelist it manually in the
  phone's own battery settings.
- `failed` vs `disconnected` is a heuristic (a disconnect within 10s of a
  connected/no-internet state is logged as `failed`), since Android doesn't
  expose "association failed" as a distinct signal to apps.
- Per-app **CPU usage** has had no public Android API since Android 8
  (`ActivityManager#getProcessMemoryInfo`-style per-process stats were locked
  down for privacy reasons); the Settings tab shows device-level memory only,
  with a note explaining why CPU isn't there.
- Per-UID `TrafficStats` can return 0 for some apps on some OEM builds/Android
  versions (the counter is still a public API, but a few manufacturers
  restrict it further); the device-level total row is unaffected since it
  comes from a separate, always-available counter.

### Users & permissions

Multi-user logins with three roles, managed from the "المستخدمون" / Users
tab (superadmin only):

- **Full admin (superadmin)** — everything, including managing other users
  and the email-report settings, and always sees every device regardless of
  any device list.
- **Admin** — full admin actions (rename, remote control, poll interval,
  delete data, add/delete devices) but only on the devices assigned to
  them; an empty device list means every device. Cannot manage users or
  email settings.
- **Viewer** — read-only, same per-device scoping as Admin. No write
  buttons are shown, and the server also rejects write requests
  independently of what the UI hides.

The very first run creates one superadmin account from `ADMIN_USER` /
`ADMIN_PASS` (default `admin` / `pulse2026`) — change its password from the
Users tab after logging in for the first time. New users are created with a
username, password, role, and (for Admin/Viewer) a device checklist; an
existing user's role, device list, active flag, or password can be changed
later, and users can be bulk-deleted like any other list in the dashboard.
The system always keeps at least one superadmin — the last one can't be
demoted, deactivated, or deleted, and no one can delete or deactivate their
own account from this screen. The kiosk `/screen?key=...` view is unchanged
by this: it stays fully read-only and unrestricted by device, same as
before.

### Dashboard features

- **Data usage tab** — total download/upload per app over the selected time
  range, an hourly download/upload chart, and a top-apps-by-data bar list.
- **Pie charts** (Overview tab) — visited websites by domain, and connection
  type (Wi-Fi vs. cellular) as a practical stand-in for "internet protocol"
  breakdown — Android has no public API for per-connection L4 protocol
  statistics (TCP/UDP/etc.) outside of root/VPN-level packet inspection,
  which this project deliberately avoids (see the DNS-only VPN design above).
- **Email reports** — configurable in the Settings tab: SMTP server, hourly,
  daily or weekly cadence, which sections to include (or an "unrestricted"
  mode that ignores the picker and sends every available section), an
  optional extra report sent separately per enrolled device, and a "send
  test now" button. Runs in-process via APScheduler when the server process
  stays alive; for hosts that sleep (e.g. a free-tier deploy), call
  `GET/POST /api/cron/send-reports?key=<CRON_KEY>` from an external
  scheduler (e.g. a cron-job.org ping or GitHub Actions schedule) instead —
  set `CRON_KEY` in the server's environment to enable that endpoint.
- **Renaming** — both device names and per-app labels can be edited inline
  from the dashboard (✎ buttons in the Devices and Apps/Data tables).
- **Device IP address and Wi-Fi link speed** — shown in the Devices table
  (link speed is the OS's reported association speed, not a measured
  throughput test, and only populates while the device is on Wi-Fi).
- **Configurable update interval** — each device's "how often it reports"
  cadence (5s–1h) is editable per device from the Devices table (✎ next to
  the interval). A lower value is closer to real-time but uses more battery
  and data; there is no fixed "realtime" mode because true second-by-second
  streaming would need a different transport (push/WebSocket) and would
  noticeably drain the phone — this makes the trade-off the device owner's
  own call instead of a hardcoded default.
- **Remote screen view + control** — a 📱 button per device in the Devices
  table opens a live view of that phone's screen with tap/swipe/text/back/
  home/recents control, run from the dashboard. See the dedicated section
  below for how it works and its platform limits.

### Remote screen view + control

Started/stopped per device from the dashboard (Devices tab → 📱 button).
While a session is active:
- The phone captures its screen (`MediaProjection`) roughly every 800ms,
  downsized to ~720p-equivalent JPEGs, and posts each frame to the server,
  which keeps only the latest one per device. The dashboard polls that frame
  about once a second — this is a simple "refresh the image" loop, not a
  real video stream, which keeps it on the same plain-HTTP infrastructure as
  the rest of the app instead of adding a WebSocket/WebRTC stack. Expect
  roughly 1fps-equivalent responsiveness, not game-quality mirroring.
- Clicking/dragging on the dashboard's image sends tap/swipe commands; a
  text box sends text to whatever field is focused on the phone; Back/Home/
  Recents buttons send those global actions. All of this is carried out by
  the same `AccessibilityService` already used for browser-URL capture
  (`dispatchGesture` for tap/swipe, `ACTION_SET_TEXT` on the focused node for
  text, `performGlobalAction` for Back/Home/Recents) — so it needs that
  permission enabled, same as URL capture does.

**Platform limits, not implementation gaps:**
- Android requires the device owner to grant screen-capture consent through
  an on-device system dialog (triggered from the app's own setup screen,
  "Enable remote control") — this cannot be granted remotely, in advance, or
  silently; it is a hard OS security boundary with no workaround.
- That consent does not survive the app process dying (reboot, force-stop,
  the OS killing it under memory pressure) — the device owner needs to open
  the app and re-grant it once after any of those. The setup screen says so.
- Because of the point above, remote control cannot be "always ready" the
  way the rest of the monitoring is — it needs that one-time local step
  first. Everything after that (starting/stopping a session, sending
  commands) is fully remote from the dashboard.

### Explicitly out of scope

Requested but not built, for the reasons below:

- **Shutdown / restart the Android system from the app** — not possible for a
  normal (non-rooted, non-Device-Owner) app. Android only exposes this to
  apps provisioned as the device's MDM/Device Owner (a factory-reset
  enrollment flow, not something an app can request from its own install) or
  on rooted devices. This would be a materially heavier, separate project if
  wanted later.
- **Per-app CPU usage** — no public Android API since Android 8; see above.
- **True second-by-second "realtime" telemetry** — see "Configurable update
  interval" above; the interval is tunable instead of fixed, which covers
  the same need without a hardcoded always-on fast-poll mode.

### Enrollment

1. In the dashboard's **Devices** tab, add a device — it shows a one-time code
   valid 24 hours.
2. Install the APK, accept the consent screen, enter the server URL and the
   code.
3. Grant the permission checklist (Usage Access, Accessibility, battery
   exemption, notifications, VPN) and tap **Start monitoring**.

## Repo layout

```
server/            Flask app, dashboard, stats
android-app/       Capacitor shell + native-src/ (hand-written Java)
.github/workflows/ CI: builds and releases the APK
```
