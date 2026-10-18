import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text

import stats
import mailer
from models import (db, now_ms, sha256, Device, UsageSession, NetEvent, BrowseEvent,
                    DataUsage, DeviceSample, AppLabelOverride, EmailSettings, ReportSchedule, RemoteCommand, User)

# Two different "where am I" questions, both only interesting when this is
# running as a PyInstaller-built standalone .exe rather than `python app.py`:
#
# RESOURCE_DIR — where the bundled, READ-ONLY templates/ and static/ folders
# live. PyInstaller's --onefile mode unpacks everything named in --add-data
# into a throwaway temp directory on every launch (sys._MEIPASS), which is
# NOT where the .exe itself sits — os.path.dirname(__file__) would silently
# resolve inside that temp dir and still work, right up until something
# tries to treat it as a stable path.
#
# DATA_DIR — where pulse.db and the captured-screen files should actually
# live: next to the .exe itself (sys.executable's own folder), so they
# persist across runs/restarts. Using __file__ here (as a plain `python
# app.py` run correctly does) would instead point inside that same
# wiped-on-every-launch temp directory under a frozen .exe — every restart
# would find an empty database, with no error, just silently "lost" all
# devices and history each time.
if getattr(sys, 'frozen', False):
    RESOURCE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    DATA_DIR = os.path.dirname(sys.executable)
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = RESOURCE_DIR


def _migrate_columns(db, table, columns):
    """Adds any of `columns` ({name: SQL type}) to `table` that aren't there yet.
    Safe to call on every startup — a no-op once the columns exist. Works on
    both SQLite and Postgres, the two engines this app is deployed on."""
    inspector = inspect(db.engine)
    if table not in inspector.get_table_names():
        return  # create_all() will make it fresh with every column already defined
    existing = {c['name'] for c in inspector.get_columns(table)}
    for name, coltype in columns.items():
        if name not in existing:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {coltype}'))
    db.session.commit()


def create_app(test_config=None):
    # Explicit folders (RESOURCE_DIR, not __file__) so a frozen .exe finds
    # the bundled templates/static that PyInstaller's --add-data unpacked
    # into its temp dir — see the RESOURCE_DIR/DATA_DIR comment above.
    app = Flask(__name__, template_folder=os.path.join(RESOURCE_DIR, 'templates'),
                static_folder=os.path.join(RESOURCE_DIR, 'static'))
    app.secret_key = os.environ.get('SECRET_KEY', 'pulse-dev-secret-change-me')
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
    url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(DATA_DIR, 'pulse.db'))
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    app.config['SQLALCHEMY_DATABASE_URI'] = url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
    app.config['ADMIN_USER'] = os.environ.get('ADMIN_USER', 'admin')
    app.config['ADMIN_PASS'] = os.environ.get('ADMIN_PASS', 'pulse2026')
    app.config['SCREEN_KEY'] = os.environ.get('SCREEN_KEY', '')   # read-only kiosk key for the smart screen
    app.config['APK_URL'] = os.environ.get('APK_DOWNLOAD_URL',
                                           'https://github.com/AcsVe/Pulse/releases/latest/download/Pulse.apk')
    app.config['CRON_KEY'] = os.environ.get('CRON_KEY', '')
    app.config['SCREENS_DIR'] = os.environ.get('SCREENS_DIR', os.path.join(DATA_DIR, 'instance', 'screens'))
    if test_config:
        app.config.update(test_config)
    db.init_app(app)

    @app.template_global()
    def static_v(filename):
        """url_for('static', ...) alone lets browsers (and any CDN/proxy in
        front of the deploy) keep serving a cached app.css/app.js from
        before the last update — "I pushed and redeployed but the fix still
        isn't showing" is almost always this, not the fix itself being
        wrong. Appending the file's own mtime as a query string makes the
        URL itself change on every deploy that actually touches the file,
        so there's nothing stale left to serve."""
        path = os.path.join(app.static_folder, filename)
        try:
            v = int(os.path.getmtime(path))
        except OSError:
            v = 0
        return url_for('static', filename=filename) + f'?v={v}'
    os.makedirs(app.config['SCREENS_DIR'], exist_ok=True)
    with app.app_context():
        db.create_all()
        # db.create_all() only creates missing tables, not missing columns on a
        # table that already existed from an earlier version of this app (e.g.
        # an already-deployed devices.db) — add any new columns by hand.
        _migrate_columns(db, 'devices', {
            'connection_type': 'VARCHAR(20)',
            'accessibility_enabled': 'BOOLEAN',
            'wifi_band': 'VARCHAR(10)',
            'apps_json': 'TEXT',
            'apps_at': 'BIGINT',
            'remote_capable': 'BOOLEAN',
        })
        if not db.session.get(EmailSettings, 1):
            db.session.add(EmailSettings(id=1))
            db.session.commit()
        if User.query.count() == 0:
            # One-time migration/bootstrap from the old single-admin env vars:
            # the first superadmin account, which should have its password
            # changed from the "المستخدمون" tab once logged in.
            db.session.add(User(username=app.config['ADMIN_USER'],
                                 password_hash=generate_password_hash(app.config['ADMIN_PASS']),
                                 role='superadmin', device_ids=''))
            db.session.commit()
    if not app.config.get('TESTING') and os.environ.get('DISABLE_SCHEDULER') != '1':
        mailer.start_scheduler(app)

    # ── helpers ────────────────────────────────────────────────────────────
    def current_user():
        uid = session.get('user_id')
        if not uid:
            return None
        u = db.session.get(User, uid)
        return u if (u and u.active) else None

    def allowed_ids_for(user):
        """None = every device is visible/usable; otherwise a set of ids."""
        return user.allowed_ids() if user else None

    def device_allowed(user, did):
        ids = allowed_ids_for(user)
        return ids is None or int(did) in ids

    def viewer_ok():
        if session.get('user_id') and current_user():
            return True
        key = app.config['SCREEN_KEY']
        return bool(key) and request.method == 'GET' and hmac.compare_digest(request.args.get('key', ''), key)

    def viewer_required(f):
        @wraps(f)
        def w(*a, **kw):
            if not viewer_ok():
                return jsonify({'error': 'unauthorized'}), 401
            return f(*a, **kw)
        return w

    def viewer_device_required(f):
        """Like viewer_required, but also checks the <did> kwarg against the
        logged-in user's device scope (the screen-key kiosk path is always
        unrestricted, same as the rest of the kiosk view)."""
        @wraps(f)
        def w(*a, **kw):
            if not viewer_ok():
                return jsonify({'error': 'unauthorized'}), 401
            u = current_user()
            if u and 'did' in kw and not device_allowed(u, kw['did']):
                return jsonify({'error': 'unauthorized'}), 401
            return f(*a, **kw)
        return w

    def admin_required(f):
        @wraps(f)
        def w(*a, **kw):
            u = current_user()
            if not u or u.role not in ('admin', 'superadmin'):
                return jsonify({'error': 'unauthorized'}), 401
            return f(*a, **kw)
        return w

    def device_admin_required(f):
        """admin_required, plus the <did> kwarg must be in the user's scope."""
        @wraps(f)
        def w(*a, **kw):
            u = current_user()
            if not u or u.role not in ('admin', 'superadmin'):
                return jsonify({'error': 'unauthorized'}), 401
            if 'did' in kw and not device_allowed(u, kw['did']):
                return jsonify({'error': 'unauthorized'}), 401
            return f(*a, **kw)
        return w

    def superadmin_required(f):
        @wraps(f)
        def w(*a, **kw):
            u = current_user()
            if not u or u.role != 'superadmin':
                return jsonify({'error': 'unauthorized'}), 401
            return f(*a, **kw)
        return w

    def device_from_token():
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return None
        return Device.query.filter_by(token_hash=sha256(auth[7:].strip())).first()

    def params():
        """from/to (ms), tz (minutes east of UTC), device ids."""
        now = now_ms()
        try:
            b = int(request.args.get('to') or now)
            a = int(request.args.get('from') or (b - 86400000))
            tz = int(request.args.get('tz') or 0)
        except ValueError:
            a, b, tz = now - 86400000, now, 0
        if b <= a:
            a = b - 86400000
        ids = [int(x) for x in (request.args.get('devices') or '').split(',') if x.strip().isdigit()]
        if not ids:
            ids = [d.id for d in Device.query.all()]
        allowed = allowed_ids_for(current_user())
        if allowed is not None:
            ids = [i for i in ids if i in allowed]
        return a, b, tz, ids, now

    # ── pages ─────────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        if not current_user():
            return redirect(url_for('login'))
        return render_template('dashboard.html', kiosk=False, screen_key='', apk_url=app.config['APK_URL'])

    @app.route('/screen')
    def screen():
        """Read-only kiosk view for a smart screen: /screen?key=<SCREEN_KEY>."""
        key = app.config['SCREEN_KEY']
        if not current_user() and not (key and hmac.compare_digest(request.args.get('key', ''), key)):
            return redirect(url_for('login'))
        return render_template('dashboard.html', kiosk=True, screen_key=request.args.get('key', ''),
                               apk_url=app.config['APK_URL'])

    @app.route('/report/print')
    @viewer_required
    def report_print():
        """A plain, print-optimized HTML page covering every dashboard section
        for the given filter — the person hits Ctrl+P / the browser's own
        "Save as PDF" to get a PDF. Deliberately not server-rendered to PDF:
        that would mean shipping a PDF/Arabic-text-shaping library and its
        system dependencies (fonts, cairo/pango, ...) that may not exist on
        every host this app gets deployed to, where the browser's own print
        engine already renders Arabic/RTL correctly for free."""
        a, b, tz, ids, now = params()
        ov = stats.overview(ids, a, b, tz, now)
        kpi_labels = {'screenTime': 'وقت الاستخدام', 'avgPerDay': 'المتوسط اليومي', 'sessions': 'جلسات الاستخدام',
                      'appsUsed': 'تطبيقات مستخدمة', 'sites': 'صفحات مفتوحة', 'domains': 'مواقع مختلفة',
                      'outages': 'عدد الانقطاعات', 'outageTime': 'مدة الانقطاع', 'availability': 'نسبة الاتصال',
                      'download': 'تنزيل', 'upload': 'رفع'}
        for k in ov['kpis']:
            k['key'] = kpi_labels.get(k['key'], k['key'])
        devs = Device.query.filter(Device.id.in_(ids)).all() if ids else []
        fmt = lambda ms: datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M') if ms else '—'
        browse_rows = stats.browse_table(ids, a, b, limit=200)
        for r in browse_rows:
            r['ts'] = fmt(r['ts'])
        return render_template('report_print.html', ov=ov, devices=devs, browse_rows=browse_rows,
                               period_label=f'{fmt(a)} → {fmt(b)}', generated_at=fmt(now))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        err = False
        if request.method == 'POST':
            uname, p = request.form.get('username', ''), request.form.get('password', '')
            u = User.query.filter_by(username=uname).first()
            if u and u.active and check_password_hash(u.password_hash, p):
                session.permanent = True
                session['user_id'] = u.id
                return redirect(url_for('index'))
            err = True
        return render_template('login.html', error=err)

    @app.route('/api/me', methods=['GET'])
    def me():
        u = current_user()
        if not u:
            return jsonify({'error': 'unauthorized'}), 401
        return jsonify(u.to_dict())

    @app.route('/api/me/password', methods=['POST'])
    def me_password():
        u = current_user()
        if not u:
            return jsonify({'error': 'unauthorized'}), 401
        data = request.get_json(silent=True) or {}
        old, new = data.get('oldPassword') or '', data.get('newPassword') or ''
        if not check_password_hash(u.password_hash, old):
            return jsonify({'error': 'bad_password'}), 400
        if len(new) < 6:
            return jsonify({'error': 'password_too_short'}), 400
        u.password_hash = generate_password_hash(new)
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/healthz')
    def healthz():
        return 'ok'

    # ── device-facing API (Bearer token) ──────────────────────────────────
    @app.route('/api/v1/enroll', methods=['POST'])
    def enroll():
        data = request.get_json(silent=True) or {}
        code = (data.get('code') or '').strip().upper().replace('-', '').replace(' ', '')
        dev = Device.query.filter_by(enroll_code=code).first() if code else None
        if not dev or not dev.enroll_until or dev.enroll_until < now_ms():
            return jsonify({'error': 'invalid_or_expired_code'}), 403
        import secrets
        token = secrets.token_urlsafe(32)
        dev.token_hash = sha256(token)
        dev.enroll_code = None
        dev.enroll_until = None
        dev.enrolled_at = now_ms()
        dev.last_seen = now_ms()
        dev.model = (data.get('model') or '')[:120]
        dev.os_version = (data.get('os') or '')[:40]
        dev.app_version = (data.get('app') or '')[:40]
        db.session.commit()
        return jsonify({'token': token, 'deviceId': dev.id, 'name': dev.name})

    @app.route('/api/v1/ping')
    def ping():
        dev = device_from_token()
        if not dev:
            return jsonify({'error': 'unauthorized'}), 401
        dev.last_seen = now_ms()
        db.session.commit()
        return jsonify({'ok': True, 'now': now_ms(), 'name': dev.name})

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @app.route('/api/v1/ingest', methods=['POST'])
    def ingest():
        dev = device_from_token()
        if not dev:
            return jsonify({'error': 'unauthorized'}), 401
        data = request.get_json(silent=True) or {}
        added = {'usage': 0, 'net': 0, 'browse': 0, 'data': 0, 'memory': 0}
        lim = 3000

        usage = [u for u in (data.get('usage') or [])[:lim]
                 if _int(u.get('start')) is not None and _int(u.get('end')) is not None
                 and u.get('package') and _int(u['end']) >= _int(u['start'])]
        if usage:
            lo, hi = min(_int(u['start']) for u in usage), max(_int(u['start']) for u in usage)
            have = {(r.package, r.start_ts): r for r in UsageSession.query.filter(
                UsageSession.device_id == dev.id, UsageSession.start_ts >= lo, UsageSession.start_ts <= hi)}
            for u in usage:
                key, end = (u['package'][:200], _int(u['start'])), _int(u['end'])
                row = have.get(key)
                if row:
                    row.end_ts = max(row.end_ts, end)
                    if u.get('label'):
                        row.app_label = u['label'][:200]
                else:
                    row = UsageSession(device_id=dev.id, package=key[0], app_label=(u.get('label') or '')[:200],
                                       start_ts=key[1], end_ts=end)
                    db.session.add(row)
                    have[key] = row
                    added['usage'] += 1

        net = [n for n in (data.get('net') or [])[:lim]
               if _int(n.get('start')) is not None and n.get('kind') in stats.KINDS]
        if net:
            lo, hi = min(_int(n['start']) for n in net), max(_int(n['start']) for n in net)
            have = {(r.start_ts, r.kind): r for r in NetEvent.query.filter(
                NetEvent.device_id == dev.id, NetEvent.start_ts >= lo, NetEvent.start_ts <= hi)}
            for n in net:
                key, end = (_int(n['start']), n['kind']), _int(n.get('end'))
                row = have.get(key)
                if row:
                    row.end_ts = end if end is not None else row.end_ts
                    row.transport = (n.get('transport') or row.transport or '')[:20]
                    row.detail = (n.get('detail') or row.detail or '')[:300]
                else:
                    row = NetEvent(device_id=dev.id, kind=n['kind'], transport=(n.get('transport') or '')[:20],
                                   start_ts=key[0], end_ts=end, detail=(n.get('detail') or '')[:300])
                    db.session.add(row)
                    have[key] = row
                    added['net'] += 1

        browse = [x for x in (data.get('browse') or [])[:lim] if _int(x.get('ts')) is not None]
        if browse:
            seen = set()
            for x in browse:
                ts, src = _int(x['ts']), (x.get('source') or 'accessibility')[:20]
                url = (x.get('url') or '')[:2000]
                domain = (x.get('domain') or '').lower()
                if not domain and url:
                    domain = (urlparse(url if '://' in url else '//' + url).hostname or '').lower()
                uniq = hashlib.sha1(f'{ts}|{src}|{url}|{domain}'.encode()).hexdigest()
                if uniq in seen:
                    continue
                seen.add(uniq)
                if BrowseEvent.query.filter_by(device_id=dev.id, uniq=uniq).first():
                    continue
                db.session.add(BrowseEvent(device_id=dev.id, ts=ts, source=src, app=(x.get('app') or '')[:200],
                                           url=url, domain=domain[:255], title=(x.get('title') or '')[:300], uniq=uniq))
                added['browse'] += 1

        data_usage = [u for u in (data.get('dataUsage') or [])[:lim]
                      if _int(u.get('ts')) is not None and u.get('package')]
        if data_usage:
            lo, hi = min(_int(u['ts']) for u in data_usage), max(_int(u['ts']) for u in data_usage)
            have = {(r.package, r.ts): r for r in DataUsage.query.filter(
                DataUsage.device_id == dev.id, DataUsage.ts >= lo, DataUsage.ts <= hi)}
            for u in data_usage:
                key = (u['package'][:200], _int(u['ts']))
                row = have.get(key)
                if row:
                    row.rx_bytes = (row.rx_bytes or 0) + (_int(u.get('rx')) or 0)
                    row.tx_bytes = (row.tx_bytes or 0) + (_int(u.get('tx')) or 0)
                else:
                    row = DataUsage(device_id=dev.id, package=key[0], label=(u.get('label') or '')[:200],
                                    ts=key[1], rx_bytes=_int(u.get('rx')) or 0, tx_bytes=_int(u.get('tx')) or 0,
                                    transport=(u.get('transport') or '')[:20])
                    db.session.add(row)
                    have[key] = row
                    added['data'] += 1

        memory = [m for m in (data.get('memory') or [])[:lim] if _int(m.get('ts')) is not None]
        if memory:
            lo, hi = min(_int(m['ts']) for m in memory), max(_int(m['ts']) for m in memory)
            existing = {r.ts for r in DeviceSample.query.filter(
                DeviceSample.device_id == dev.id, DeviceSample.ts >= lo, DeviceSample.ts <= hi)}
            for m in memory:
                ts = _int(m['ts'])
                if ts in existing:
                    continue
                db.session.add(DeviceSample(device_id=dev.id, ts=ts, mem_used_mb=_int(m.get('usedMb')),
                                            mem_total_mb=_int(m.get('totalMb'))))
                existing.add(ts)
                added['memory'] += 1

        dev.last_seen = now_ms()
        if data.get('ip'):
            dev.ip_address = str(data['ip'])[:64]
        if data.get('wifiMbps') is not None:
            dev.wifi_mbps = _int(data['wifiMbps'])
        if data.get('wifiBand') is not None:
            dev.wifi_band = str(data['wifiBand'])[:10]
        if data.get('connType') is not None:
            dev.connection_type = str(data['connType'])[:20]
        if data.get('accessibilityEnabled') is not None:
            dev.accessibility_enabled = bool(data['accessibilityEnabled'])
        if data.get('remoteCapable') is not None:
            dev.remote_capable = bool(data['remoteCapable'])
        for k in ('model', 'os', 'app'):
            if data.get(k):
                setattr(dev, {'model': 'model', 'os': 'os_version', 'app': 'app_version'}[k], str(data[k])[:120])
        db.session.commit()
        return jsonify({'ok': True, 'added': added, 'pollIntervalS': dev.poll_interval_s or 5,
                         'remoteActive': bool(dev.remote_active)})

    # ── dashboard API ─────────────────────────────────────────────────────
    @app.route('/api/devices', methods=['GET'])
    @viewer_required
    def devices_list():
        # Alphabetical by name, not insertion order — the Devices *table* already
        # re-sorts itself client-side, but every other place a device list is
        # built from this endpoint (the header's device filter popover, the
        # report-schedule device picker, the new-user device picker) just used
        # whatever order came back here, i.e. creation order.
        q = Device.query.order_by(Device.name)
        allowed = allowed_ids_for(current_user())
        if allowed is not None:
            q = q.filter(Device.id.in_(allowed))
        return jsonify([d.to_dict() for d in q.all()])

    @app.route('/api/devices', methods=['POST'])
    @admin_required
    def devices_create():
        name = ((request.get_json(silent=True) or {}).get('name') or '').strip()[:120]
        if not name:
            return jsonify({'error': 'name_required'}), 400
        d = Device(name=name)
        _new_code(d)
        db.session.add(d)
        db.session.commit()
        u = current_user()
        if u and u.role == 'admin' and u.device_ids:  # keep it usable to a device-scoped admin right away
            ids = set(u.device_id_list()); ids.add(d.id)
            u.device_ids = ','.join(str(x) for x in sorted(ids))
            db.session.commit()
        return jsonify(d.to_dict()), 201

    def _new_code(d):
        for _ in range(10):
            c = Device.new_enroll_code()
            if not Device.query.filter_by(enroll_code=c).first():
                d.enroll_code, d.enroll_until = c, now_ms() + 24 * 3600 * 1000
                return
        raise RuntimeError('could not allocate enroll code')

    @app.route('/api/devices/<int:did>/code', methods=['POST'])
    @device_admin_required
    def devices_code(did):
        d = db.session.get(Device, did) or ('', 404)
        if isinstance(d, tuple):
            return jsonify({'error': 'not_found'}), 404
        _new_code(d)
        d.token_hash = None       # re-enrolling invalidates the old token
        db.session.commit()
        return jsonify(d.to_dict())

    @app.route('/api/devices/<int:did>', methods=['PATCH'])
    @device_admin_required
    def devices_rename(did):
        d = db.session.get(Device, did)
        if not d:
            return jsonify({'error': 'not_found'}), 404
        data = request.get_json(silent=True) or {}
        if 'name' in data:
            name = (data.get('name') or '').strip()[:120]
            if not name:
                return jsonify({'error': 'name_required'}), 400
            d.name = name
        if 'pollIntervalS' in data:
            try:
                v = int(data['pollIntervalS'])
            except (TypeError, ValueError):
                return jsonify({'error': 'bad_poll_interval'}), 400
            d.poll_interval_s = max(5, min(v, 3600))  # 5s..1h — "realtime" is caller-chosen, not fixed
        db.session.commit()
        return jsonify(d.to_dict())

    @app.route('/api/app-labels', methods=['GET'])
    @viewer_required
    def app_labels_list():
        return jsonify({r.package: r.label for r in AppLabelOverride.query.all()})

    @app.route('/api/app-labels', methods=['PUT'])
    @admin_required
    def app_labels_set():
        data = request.get_json(silent=True) or {}
        package = (data.get('package') or '').strip()[:200]
        label = (data.get('label') or '').strip()[:200]
        if not package:
            return jsonify({'error': 'package_required'}), 400
        row = db.session.get(AppLabelOverride, package)
        if not label:
            if row:
                db.session.delete(row)
                db.session.commit()
            return jsonify({'ok': True, 'cleared': True})
        if row:
            row.label = label
        else:
            db.session.add(AppLabelOverride(package=package, label=label))
        db.session.commit()
        return jsonify({'ok': True, 'package': package, 'label': label})

    # ── user management (superadmin only) ──────────────────────────────────
    def _device_ids_field(data):
        return ','.join(str(int(x)) for x in (data.get('deviceIds') or []) if str(x).strip().lstrip('-').isdigit())

    @app.route('/api/users', methods=['GET'])
    @superadmin_required
    def users_list():
        return jsonify([u.to_dict() for u in User.query.order_by(User.id).all()])

    @app.route('/api/users', methods=['POST'])
    @superadmin_required
    def users_create():
        data = request.get_json(silent=True) or {}
        username = (data.get('username') or '').strip()[:64]
        password = data.get('password') or ''
        role = data.get('role') or 'viewer'
        if not username or not password:
            return jsonify({'error': 'username_password_required'}), 400
        if len(password) < 6:
            return jsonify({'error': 'password_too_short'}), 400
        if role not in ('superadmin', 'admin', 'viewer'):
            return jsonify({'error': 'bad_role'}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'username_taken'}), 400
        u = User(username=username, password_hash=generate_password_hash(password), role=role,
                 device_ids=_device_ids_field(data))
        db.session.add(u)
        db.session.commit()
        return jsonify(u.to_dict()), 201

    @app.route('/api/users/<int:uid>', methods=['PATCH'])
    @superadmin_required
    def users_update(uid):
        u = db.session.get(User, uid)
        if not u:
            return jsonify({'error': 'not_found'}), 404
        data = request.get_json(silent=True) or {}
        is_self = (uid == session.get('user_id'))
        if 'password' in data and data['password']:
            if len(data['password']) < 6:
                return jsonify({'error': 'password_too_short'}), 400
            u.password_hash = generate_password_hash(data['password'])
        if 'role' in data:
            if data['role'] not in ('superadmin', 'admin', 'viewer'):
                return jsonify({'error': 'bad_role'}), 400
            if u.role == 'superadmin' and data['role'] != 'superadmin' \
                    and User.query.filter_by(role='superadmin').count() <= 1:
                return jsonify({'error': 'last_superadmin'}), 400
            u.role = data['role']
        if 'deviceIds' in data:
            u.device_ids = _device_ids_field(data)
        if 'active' in data:
            if is_self and not data['active']:
                return jsonify({'error': 'cannot_deactivate_self'}), 400
            u.active = bool(data['active'])
        db.session.commit()
        return jsonify(u.to_dict())

    @app.route('/api/users/<int:uid>', methods=['DELETE'])
    @superadmin_required
    def users_delete(uid):
        u = db.session.get(User, uid)
        if not u:
            return jsonify({'error': 'not_found'}), 404
        if uid == session.get('user_id'):
            return jsonify({'error': 'cannot_delete_self'}), 400
        if u.role == 'superadmin' and User.query.filter_by(role='superadmin').count() <= 1:
            return jsonify({'error': 'last_superadmin'}), 400
        db.session.delete(u)
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/email-settings', methods=['GET'])
    @superadmin_required
    def email_settings_get():
        s = db.session.get(EmailSettings, 1)
        if not s:
            s = EmailSettings(id=1)
            db.session.add(s)
            db.session.commit()
        return jsonify(s.to_dict(include_secrets=True))

    @app.route('/api/email-settings', methods=['PUT'])
    @superadmin_required
    def email_settings_set():
        data = request.get_json(silent=True) or {}
        s = db.session.get(EmailSettings, 1) or EmailSettings(id=1)
        provider = data.get('provider') or s.provider or 'smtp'
        s.provider = provider if provider in ('smtp', 'graph') else 'smtp'
        s.smtp_host = (data.get('smtpHost') or s.smtp_host or '')[:200]
        s.smtp_port = int(data.get('smtpPort') or s.smtp_port or 587)
        s.smtp_user = (data.get('smtpUser') or s.smtp_user or '')[:200]
        if data.get('smtpPass'):
            s.smtp_pass = data['smtpPass'][:200]
        s.use_tls = bool(data.get('useTls', s.use_tls if s.use_tls is not None else True))
        s.graph_tenant_id = (data.get('graphTenantId') or s.graph_tenant_id or '')[:100]
        s.graph_client_id = (data.get('graphClientId') or s.graph_client_id or '')[:100]
        if data.get('graphClientSecret'):
            s.graph_client_secret = data['graphClientSecret'][:300]
        s.graph_sender = (data.get('graphSender') or s.graph_sender or '')[:200]
        db.session.add(s)
        db.session.commit()
        return jsonify(s.to_dict())

    @app.route('/api/email-settings/test', methods=['POST'])
    @superadmin_required
    def email_settings_test():
        s = db.session.get(EmailSettings, 1)
        data = request.get_json(silent=True) or {}
        recipient = (data.get('recipient') or '').strip()
        if not s or not mailer.transport_ready(s):
            return jsonify({'ok': False, 'error': 'not_configured'}), 400
        if not recipient:
            return jsonify({'ok': False, 'error': 'recipient_required'}), 400
        try:
            html = mailer.build_report_html(mailer.ALL_SECTIONS, 'تجريبي')
            mailer.send_email(s, recipient, 'تقرير Pulse (تجريبي)', html)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 400

    # ── report schedules (multiple independent "sessions") ───────────────
    @app.route('/api/report-schedules', methods=['GET'])
    @superadmin_required
    def report_schedules_list():
        return jsonify([s.to_dict() for s in ReportSchedule.query.order_by(ReportSchedule.id).all()])

    def _apply_schedule_fields(s, data):
        s.name = (data.get('name') or '')[:100]
        s.enabled = bool(data.get('enabled', True))
        s.recipient = (data.get('recipient') or '')[:300]
        freq = data.get('frequency') or 'daily'
        s.frequency = freq if freq in ('daily', 'weekly', 'once') else 'daily'
        s.local_time = (data.get('localTime') or '08:00')[:5]
        s.weekday = data.get('weekday') if data.get('weekday') in range(0, 7) else None
        s.once_date = (data.get('onceDate') or '')[:10] or None
        if isinstance(data.get('sections'), list):
            s.sections = ','.join(data['sections'])
        s.unrestricted = bool(data.get('unrestricted', False))
        s.per_device = bool(data.get('perDevice', False))
        if isinstance(data.get('deviceIds'), list):
            s.device_ids = ','.join(str(int(x)) for x in data['deviceIds'] if str(x).isdigit())

    @app.route('/api/report-schedules', methods=['POST'])
    @superadmin_required
    def report_schedules_create():
        data = request.get_json(silent=True) or {}
        s = ReportSchedule()
        _apply_schedule_fields(s, data)
        db.session.add(s)
        db.session.commit()
        return jsonify(s.to_dict())

    @app.route('/api/report-schedules/<int:sid>', methods=['PUT'])
    @superadmin_required
    def report_schedules_update(sid):
        s = db.session.get(ReportSchedule, sid)
        if not s:
            return jsonify({'error': 'not_found'}), 404
        data = request.get_json(silent=True) or {}
        _apply_schedule_fields(s, data)
        db.session.commit()
        return jsonify(s.to_dict())

    @app.route('/api/report-schedules/<int:sid>', methods=['DELETE'])
    @superadmin_required
    def report_schedules_delete(sid):
        s = db.session.get(ReportSchedule, sid)
        if s:
            db.session.delete(s)
            db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/cron/send-reports', methods=['GET', 'POST'])
    def cron_send_reports():
        key = app.config['CRON_KEY']
        if not key or not hmac.compare_digest(request.args.get('key', ''), key):
            return jsonify({'error': 'unauthorized'}), 401
        return jsonify(mailer.run_due_reports(app))

    # ── remote screen view + control ────────────────────────────────────────
    # The phone only captures/streams its screen and accepts commands while
    # `remote_active` is set — started/stopped explicitly from the dashboard,
    # never silently, and it's the device owner's own phone (see README).
    def _screen_path(did):
        return os.path.join(app.config['SCREENS_DIR'], f'{did}.jpg')

    @app.route('/api/v1/remote-state', methods=['GET'])
    def remote_state():
        dev = device_from_token()
        if not dev:
            return jsonify({'error': 'unauthorized'}), 401
        # This (and screen_upload/commands_poll below) is polled on its own
        # cadence by ScreenCaptureService independently of the regular
        # CollectorService sync — a device could be live and fully reachable
        # through remote control while its last_seen (set only by ingest/ping)
        # goes stale and the dashboard wrongly shows it "Offline".
        dev.last_seen = now_ms()
        db.session.commit()
        # needApps tells the device whether to also (re-)upload its installed
        # app list this session — only while remote control is actually
        # active, and not on every single poll: once per fresh session, or
        # if what we have is old enough it's probably stale (apps installed/
        # removed since).
        need_apps = bool(dev.remote_active) and (not dev.apps_at or now_ms() - dev.apps_at > 30 * 60 * 1000)
        return jsonify({'active': bool(dev.remote_active), 'pollIntervalS': dev.poll_interval_s or 5, 'needApps': need_apps})

    @app.route('/api/v1/apps', methods=['POST'])
    def apps_upload():
        dev = device_from_token()
        if not dev:
            return jsonify({'error': 'unauthorized'}), 401
        data = request.get_json(silent=True) or {}
        apps = data.get('apps')
        if not isinstance(apps, list):
            return jsonify({'error': 'bad_payload'}), 400
        # Cap both the list size and each field's length — this comes from
        # PackageManager on the device, not something adversarial, but it's
        # still unauthenticated-by-content input landing in a TEXT column.
        cleaned = []
        for a in apps[:600]:
            if not isinstance(a, dict):
                continue
            pkg = str(a.get('pkg') or '')[:150]
            label = str(a.get('label') or '')[:150]
            if pkg:
                cleaned.append({'pkg': pkg, 'label': label or pkg})
        dev.apps_json = json.dumps(cleaned)
        dev.apps_at = now_ms()
        db.session.commit()
        return jsonify({'ok': True, 'count': len(cleaned)})

    @app.route('/api/devices/<int:did>/apps', methods=['GET'])
    @viewer_device_required
    def apps_list(did):
        d = db.session.get(Device, did)
        if not d:
            return jsonify({'error': 'not_found'}), 404
        try:
            apps = json.loads(d.apps_json) if d.apps_json else []
        except (TypeError, ValueError):
            apps = []
        return jsonify({'apps': apps, 'appsAt': d.apps_at})

    @app.route('/api/v1/screen', methods=['POST'])
    def screen_upload():
        dev = device_from_token()
        if not dev:
            return jsonify({'error': 'unauthorized'}), 401
        if not dev.remote_active:
            return jsonify({'ok': False, 'reason': 'not_active'}), 200
        raw = request.get_data()
        w = request.args.get('w', type=int)
        h = request.args.get('h', type=int)
        if not raw:
            data = request.get_json(silent=True) or {}
            b64 = data.get('jpeg')
            w = w or _int(data.get('w'))
            h = h or _int(data.get('h'))
            if b64:
                try:
                    raw = base64.b64decode(b64)
                except Exception:
                    raw = None
        if not raw:
            return jsonify({'error': 'no_frame'}), 400
        with open(_screen_path(dev.id), 'wb') as f:
            f.write(raw)
        dev.remote_frame_at = now_ms()
        dev.last_seen = dev.remote_frame_at
        if w:
            dev.remote_screen_w = w
        if h:
            dev.remote_screen_h = h
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/devices/<int:did>/screen.jpg', methods=['GET'])
    @viewer_device_required
    def screen_latest(did):
        path = _screen_path(did)
        if not os.path.exists(path):
            return jsonify({'error': 'no_frame'}), 404
        resp = send_file(path, mimetype='image/jpeg')
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.route('/api/devices/<int:did>/remote/start', methods=['POST'])
    @device_admin_required
    def remote_start(did):
        d = db.session.get(Device, did)
        if not d:
            return jsonify({'error': 'not_found'}), 404
        d.remote_active = True
        db.session.commit()
        return jsonify(d.to_dict())

    @app.route('/api/devices/<int:did>/remote/stop', methods=['POST'])
    @device_admin_required
    def remote_stop(did):
        d = db.session.get(Device, did)
        if not d:
            return jsonify({'error': 'not_found'}), 404
        d.remote_active = False
        RemoteCommand.query.filter_by(device_id=did, consumed=False).delete()
        db.session.commit()
        return jsonify(d.to_dict())

    @app.route('/api/devices/<int:did>/remote/command', methods=['POST'])
    @device_admin_required
    def remote_command(did):
        d = db.session.get(Device, did)
        if not d or not d.remote_active:
            return jsonify({'error': 'not_active'}), 400
        data = request.get_json(silent=True) or {}
        action = (data.get('action') or '').strip()
        if action not in ('tap', 'swipe', 'pinch', 'text', 'back', 'home', 'recents', 'launch', 'close'):
            return jsonify({'error': 'bad_action'}), 400
        if action in ('launch', 'close') and not (data.get('pkg') or '').strip():
            return jsonify({'error': 'pkg_required'}), 400
        params = {k: data[k] for k in ('x', 'y', 'x2', 'y2', 'duration', 'text', 'pkg') if k in data}
        # 'pinch' (two-finger zoom/pan) carries its two finger paths as a
        # nested list rather than flat x/y keys — validated just enough to
        # keep garbage out of the queue the device polls (a handful of
        # numeric 4-tuples, not arbitrary JSON).
        if action == 'pinch':
            touches = data.get('touches')
            if (isinstance(touches, list) and 1 <= len(touches) <= 2
                    and all(isinstance(t, list) and len(t) == 4 and all(isinstance(v, (int, float)) for v in t)
                            for t in touches)):
                params['touches'] = touches
            else:
                return jsonify({'error': 'bad_touches'}), 400
        # Keep the queue from piling up if the dashboard sends faster than the
        # device can poll — commands are discrete UI actions, so only the
        # newest handful matter.
        pending = RemoteCommand.query.filter_by(device_id=did, consumed=False).count()
        if pending > 20:
            return jsonify({'error': 'queue_full'}), 429
        db.session.add(RemoteCommand(device_id=did, action=action, params=json.dumps(params)))
        db.session.commit()
        return jsonify({'ok': True})

    @app.route('/api/v1/commands', methods=['GET'])
    def commands_poll():
        dev = device_from_token()
        if not dev:
            return jsonify({'error': 'unauthorized'}), 401
        rows = RemoteCommand.query.filter_by(device_id=dev.id, consumed=False).order_by(RemoteCommand.id).limit(20).all()
        for r in rows:
            r.consumed = True
        dev.last_seen = now_ms()
        db.session.commit()
        return jsonify({'commands': [r.to_dict() for r in rows]})

    def _wipe_device(did):
        for M in (UsageSession, NetEvent, BrowseEvent, DataUsage, DeviceSample, RemoteCommand):
            M.query.filter_by(device_id=did).delete()
        try:
            os.remove(_screen_path(did))
        except OSError:
            pass

    @app.route('/api/overview')
    @viewer_required
    def api_overview():
        a, b, tz, ids, now = params()
        return jsonify(stats.overview(ids, a, b, tz, now))

    @app.route('/api/live')
    @viewer_required
    def api_live():
        # A short recent window, not the dashboard's from/to period — this is
        # the "what's happening right now" feed (per-app bandwidth, recently
        # visited sites), meant to be polled every few seconds on its own.
        # Only useful once the phone itself is actually sampling that often
        # (DataUsageCollector's cadence follows the same live-sync setting as
        # the rest of the sync pipeline) — with the old fixed 15-minute
        # sampling this would have sat empty between polls almost always.
        ids = [int(x) for x in (request.args.get('devices') or '').split(',') if x.strip().isdigit()]
        if not ids:
            ids = [d.id for d in Device.query.all()]
        allowed = allowed_ids_for(current_user())
        if allowed is not None:
            ids = [i for i in ids if i in allowed]
        window_ms = min(max(_int(request.args.get('window')) or 90000, 10000), 600000)
        since = now_ms() - window_ms
        if not ids:
            return jsonify({'apps': [], 'deviceTotal': {'rx': 0, 'tx': 0}, 'sites': [], 'windowMs': window_ms})

        rows = DataUsage.query.filter(DataUsage.device_id.in_(ids), DataUsage.ts >= since).all()
        per_app = {}
        dev_total = {'rx': 0, 'tx': 0}
        for r in rows:
            if r.package == '__device__':
                dev_total['rx'] += r.rx_bytes or 0
                dev_total['tx'] += r.tx_bytes or 0
                continue
            key = r.package
            agg = per_app.setdefault(key, {'package': r.package, 'label': r.label or r.package, 'rx': 0, 'tx': 0})
            agg['rx'] += r.rx_bytes or 0
            agg['tx'] += r.tx_bytes or 0
        apps = sorted(per_app.values(), key=lambda x: x['rx'] + x['tx'], reverse=True)[:12]

        names = {d.id: d.name for d in Device.query.filter(Device.id.in_(ids)).all()}
        site_rows = (BrowseEvent.query.filter(BrowseEvent.device_id.in_(ids), BrowseEvent.ts >= since)
                     .order_by(BrowseEvent.ts.desc()).limit(15).all())
        sites = [{'domain': s.domain or '', 'title': s.title or '', 'ts': s.ts,
                   'device': names.get(s.device_id, '')} for s in site_rows]

        return jsonify({'apps': apps, 'deviceTotal': dev_total, 'sites': sites, 'windowMs': window_ms})

    @app.route('/api/table/<name>')
    @viewer_required
    def api_table(name):
        a, b, tz, ids, now = params()
        if name == 'apps':
            return jsonify(stats.apps_table(ids, a, b, tz))
        if name == 'browse':
            return jsonify(stats.browse_table(ids, a, b))
        if name == 'net':
            return jsonify(stats.net_table(ids, a, b, now))
        if name == 'data':
            return jsonify(stats.data_usage_table(ids, a, b))
        return jsonify({'error': 'unknown_table'}), 404

    @app.route('/api/memory')
    @viewer_required
    def api_memory():
        a, b, tz, ids, now = params()
        return jsonify(stats.memory_stats(ids, a, b, tz))

    @app.route('/api/delete', methods=['POST'])
    @admin_required
    def api_delete():
        u = current_user()
        allowed = allowed_ids_for(u)   # None = unrestricted
        data = request.get_json(silent=True) or {}
        table, ids = data.get('table'), data.get('ids') or []
        if not isinstance(ids, list) or not ids:
            return jsonify({'deleted': 0})
        n = 0
        if table == 'browse':
            q = BrowseEvent.query.filter(BrowseEvent.id.in_([int(i) for i in ids]))
            if allowed is not None:
                q = q.filter(BrowseEvent.device_id.in_(allowed))
            n = q.delete(synchronize_session=False)
        elif table == 'net':
            q = NetEvent.query.filter(NetEvent.id.in_([int(i) for i in ids]))
            if allowed is not None:
                q = q.filter(NetEvent.device_id.in_(allowed))
            n = q.delete(synchronize_session=False)
        elif table == 'apps':
            a, b = _int(data.get('from')), _int(data.get('to'))
            dev_ids = [int(x) for x in (data.get('devices') or [])] or [d.id for d in Device.query.all()]
            if allowed is not None:
                dev_ids = [i for i in dev_ids if i in allowed]
            q = UsageSession.query.filter(UsageSession.package.in_([str(i) for i in ids]),
                                          UsageSession.device_id.in_(dev_ids))
            if a is not None and b is not None:
                q = q.filter(UsageSession.end_ts > a, UsageSession.start_ts < b)
            n = q.delete(synchronize_session=False)
        elif table == 'data':
            a, b = _int(data.get('from')), _int(data.get('to'))
            dev_ids = [int(x) for x in (data.get('devices') or [])] or [d.id for d in Device.query.all()]
            if allowed is not None:
                dev_ids = [i for i in dev_ids if i in allowed]
            q = DataUsage.query.filter(DataUsage.package.in_([str(i) for i in ids]),
                                       DataUsage.device_id.in_(dev_ids))
            if a is not None and b is not None:
                q = q.filter(DataUsage.ts >= a, DataUsage.ts < b)
            n = q.delete(synchronize_session=False)
        elif table == 'devices':
            for i in ids:
                iid = int(i)
                if allowed is not None and iid not in allowed:
                    continue
                _wipe_device(iid)
                n += Device.query.filter_by(id=iid).delete()
        elif table == 'users':
            if not u or u.role != 'superadmin':
                return jsonify({'error': 'unauthorized'}), 401
            my_id = session.get('user_id')
            to_delete = [int(i) for i in ids if int(i) != my_id]
            supers_left = User.query.filter_by(role='superadmin').filter(~User.id.in_(to_delete)).count()
            if supers_left < 1:
                to_delete = [i for i in to_delete if db.session.get(User, i).role != 'superadmin']
            n = User.query.filter(User.id.in_(to_delete)).delete(synchronize_session=False) if to_delete else 0
        elif table == 'report_schedules':
            if not u or u.role != 'superadmin':
                return jsonify({'error': 'unauthorized'}), 401
            n = ReportSchedule.query.filter(ReportSchedule.id.in_([int(i) for i in ids])).delete(synchronize_session=False)
        else:
            return jsonify({'error': 'unknown_table'}), 400
        db.session.commit()
        return jsonify({'deleted': n})

    return app


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    if getattr(sys, 'frozen', False):
        # debug=True's auto-reloader re-execs sys.argv[0] on every code
        # change it detects — harmless for `python app.py`, but inside a
        # frozen PyInstaller .exe that means re-launching (and re-extracting
        # a --onefile build) itself, which is pointless for someone just
        # double-clicking a packaged .exe and can misbehave depending on how
        # it was built. Print the URL plainly instead of relying on the
        # debug console, since a double-clicked .exe's window may close
        # before anyone reads a crash underneath it.
        print(f'Pulse server starting — open http://localhost:{port} (or this computer\'s LAN IP) in a browser.')
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    else:
        app.run(host='0.0.0.0', port=port, debug=True)
