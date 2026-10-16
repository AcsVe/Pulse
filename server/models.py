import hashlib
import secrets
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def now_ms():
    # BUG FIX: datetime.utcnow() returns a "naive" datetime — it holds the
    # correct UTC wall-clock value but carries no timezone tag. Calling
    # .timestamp() on a naive datetime makes Python assume it's LOCAL time
    # and convert it to epoch using the SYSTEM's local UTC offset. On any
    # server whose OS timezone isn't UTC (e.g. Asia/Amman, UTC+3), that
    # silently shifted every timestamp in the whole app (last_seen, all
    # stats windows, "Live now", Data Usage filtering, ...) back by exactly
    # that offset — which is exactly the 3-hour gap that made devices look
    # perpetually "Offline" and recent windows look empty, even while the
    # device was actively reporting.
    # datetime.now(timezone.utc) is timezone-AWARE, so .timestamp() computes
    # the real epoch correctly no matter what timezone the server OS is set
    # to.
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def sha256(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


class Device(db.Model):
    __tablename__ = 'devices'
    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(120), nullable=False)
    token_hash   = db.Column(db.String(64), unique=True)       # set once enrolled
    enroll_code  = db.Column(db.String(16), unique=True)       # one-time, cleared on use
    enroll_until = db.Column(db.BigInteger)                    # ms epoch
    model        = db.Column(db.String(120))
    os_version   = db.Column(db.String(40))
    app_version  = db.Column(db.String(40))
    enrolled_at  = db.Column(db.BigInteger)
    last_seen    = db.Column(db.BigInteger)
    ip_address   = db.Column(db.String(64))
    wifi_mbps    = db.Column(db.Integer)                       # last-known Wi-Fi link speed
    connection_type     = db.Column(db.String(20))             # wifi | cellular | ethernet | none
    wifi_band    = db.Column(db.String(10))                    # 2.4GHz | 5GHz | 6GHz — only meaningful while on wifi
    accessibility_enabled = db.Column(db.Boolean)               # None = unknown (older app build / never synced)
    created_at   = db.Column(db.BigInteger, default=now_ms)
    # remote screen view/control
    remote_active   = db.Column(db.Boolean, default=False)
    remote_screen_w = db.Column(db.Integer)
    remote_screen_h = db.Column(db.Integer)
    remote_frame_at = db.Column(db.BigInteger)                 # ms epoch of the last frame received
    poll_interval_s = db.Column(db.Integer, default=5)        # device-configurable "realtime" cadence
    apps_json       = db.Column(db.Text)                       # cached [{pkg,label}] for the remote "open app" picker
    apps_at         = db.Column(db.BigInteger)                 # ms epoch the device last reported its app list

    @staticmethod
    def new_enroll_code():
        # unambiguous alphabet (no 0/O/1/I) — typed by hand on a phone
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        return ''.join(secrets.choice(alphabet) for _ in range(8))

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'model': self.model or '',
            'osVersion': self.os_version or '', 'appVersion': self.app_version or '',
            'enrolled': bool(self.token_hash), 'enrollCode': self.enroll_code or '',
            'enrollUntil': self.enroll_until, 'enrolledAt': self.enrolled_at,
            'lastSeen': self.last_seen, 'createdAt': self.created_at,
            'ipAddress': self.ip_address or '', 'wifiMbps': self.wifi_mbps,
            'connectionType': self.connection_type or '', 'wifiBand': self.wifi_band or '',
            'accessibilityEnabled': self.accessibility_enabled,
            'remoteActive': bool(self.remote_active),
            'remoteScreenW': self.remote_screen_w, 'remoteScreenH': self.remote_screen_h,
            'remoteFrameAt': self.remote_frame_at,
            'pollIntervalS': self.poll_interval_s or 5,
        }


class UsageSession(db.Model):
    """One continuous foreground stretch of one app."""
    __tablename__ = 'usage_sessions'
    id        = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False)
    package   = db.Column(db.String(200), nullable=False)
    app_label = db.Column(db.String(200))
    start_ts  = db.Column(db.BigInteger, nullable=False)
    end_ts    = db.Column(db.BigInteger, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('device_id', 'package', 'start_ts', name='uq_usage'),
        db.Index('ix_usage_dev_start', 'device_id', 'start_ts'),
    )


class NetEvent(db.Model):
    """A stretch of time in one connectivity state.
    kind: connected | no_internet | disconnected | failed"""
    __tablename__ = 'net_events'
    id        = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False)
    kind      = db.Column(db.String(20), nullable=False)
    transport = db.Column(db.String(20))      # wifi | cellular | ethernet | none
    start_ts  = db.Column(db.BigInteger, nullable=False)
    end_ts    = db.Column(db.BigInteger)      # NULL while still ongoing
    detail    = db.Column(db.String(300))
    __table_args__ = (
        db.UniqueConstraint('device_id', 'start_ts', 'kind', name='uq_net'),
        db.Index('ix_net_dev_start', 'device_id', 'start_ts'),
    )


class DataUsage(db.Model):
    """One short interval's data use for one app, from Android's TrafficStats
    (per-UID byte counters, sampled and diffed on-device every ~5 min).
    package '__device__' is the whole-device total for that interval, so the
    overview's download/upload KPIs don't miss background/system traffic that
    isn't attributed to any single app's UID."""
    __tablename__ = 'data_usage'
    id         = db.Column(db.Integer, primary_key=True)
    device_id  = db.Column(db.Integer, db.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False)
    package    = db.Column(db.String(200), nullable=False)
    label      = db.Column(db.String(200))
    ts         = db.Column(db.BigInteger, nullable=False)   # interval start, ms
    rx_bytes   = db.Column(db.BigInteger, default=0)        # download
    tx_bytes   = db.Column(db.BigInteger, default=0)        # upload
    transport  = db.Column(db.String(20))                   # wifi | cellular | mixed
    __table_args__ = (
        db.UniqueConstraint('device_id', 'package', 'ts', name='uq_data_usage'),
        db.Index('ix_datausage_dev_ts', 'device_id', 'ts'),
    )


class DeviceSample(db.Model):
    """Periodic device-level telemetry: memory. (Per-app CPU/memory isn't
    readable by a normal Android app since API 26 — see README.)"""
    __tablename__ = 'device_samples'
    id          = db.Column(db.Integer, primary_key=True)
    device_id   = db.Column(db.Integer, db.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False)
    ts          = db.Column(db.BigInteger, nullable=False)
    mem_used_mb = db.Column(db.Integer)
    mem_total_mb = db.Column(db.Integer)
    __table_args__ = (
        db.UniqueConstraint('device_id', 'ts', name='uq_device_sample'),
        db.Index('ix_devsample_dev_ts', 'device_id', 'ts'),
    )


class RemoteCommand(db.Model):
    """A single remote-control action queued by the dashboard for a device's
    AccessibilityService to execute (tap / swipe / text / a global action like
    back/home/recents). The device polls for its own pending commands and
    marks each consumed once run — this is a plain queue, not a 2-way RPC,
    so the dashboard doesn't block waiting for a per-command result."""
    __tablename__ = 'remote_commands'
    id        = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False)
    action    = db.Column(db.String(20), nullable=False)   # tap | swipe | text | back | home | recents
    params    = db.Column(db.Text)                          # JSON string: {x,y,x2,y2,duration,text}
    created_at = db.Column(db.BigInteger, default=now_ms)
    consumed  = db.Column(db.Boolean, default=False)
    __table_args__ = (db.Index('ix_remotecmd_dev_consumed', 'device_id', 'consumed'),)

    def to_dict(self):
        import json
        try:
            params = json.loads(self.params) if self.params else {}
        except Exception:
            params = {}
        return {'id': self.id, 'action': self.action, 'params': params}


class AppLabelOverride(db.Model):
    """A custom display name for a package, set from the dashboard (e.g. to
    rename a package that reports no friendly label)."""
    __tablename__ = 'app_label_overrides'
    package = db.Column(db.String(200), primary_key=True)
    label   = db.Column(db.String(200), nullable=False)


class EmailSettings(db.Model):
    """Singleton row (id=1): the mail *transport* only — how outgoing mail is
    sent (SMTP or Microsoft Graph). The actual report schedules (when, what,
    to whom) live in ReportSchedule, so several report "sessions" can share
    this one transport."""
    __tablename__ = 'email_settings'
    id          = db.Column(db.Integer, primary_key=True)
    provider    = db.Column(db.String(10), default='smtp')    # smtp | graph
    smtp_host   = db.Column(db.String(200))
    smtp_port   = db.Column(db.Integer, default=587)
    smtp_user   = db.Column(db.String(200))
    smtp_pass   = db.Column(db.String(200))
    use_tls     = db.Column(db.Boolean, default=True)
    # Microsoft Graph (app-only / client-credentials): an Entra ID app
    # registration with Mail.Send application permission, admin-consented.
    graph_tenant_id     = db.Column(db.String(100))
    graph_client_id     = db.Column(db.String(100))
    graph_client_secret = db.Column(db.String(300))
    graph_sender        = db.Column(db.String(200))           # mailbox UPN to send as

    def to_dict(self, include_secrets=False):
        d = {
            'provider': self.provider or 'smtp',
            'smtpHost': self.smtp_host or '', 'smtpPort': self.smtp_port or 587,
            'smtpUser': self.smtp_user or '', 'useTls': self.use_tls if self.use_tls is not None else True,
            'hasPassword': bool(self.smtp_pass),
            'graphTenantId': self.graph_tenant_id or '', 'graphClientId': self.graph_client_id or '',
            'graphSender': self.graph_sender or '', 'hasGraphSecret': bool(self.graph_client_secret),
        }
        if include_secrets:
            d['smtpPass'] = self.smtp_pass or ''
            d['graphClientSecret'] = self.graph_client_secret or ''
        return d


class ReportSchedule(db.Model):
    """One scheduled-report "session": its own time/date, recipient and
    content — several of these can run independently off the one shared
    mail transport above."""
    __tablename__ = 'report_schedules'
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100))                    # optional label, e.g. "تقرير الصباح"
    enabled     = db.Column(db.Boolean, default=True)
    recipient   = db.Column(db.String(300))
    frequency   = db.Column(db.String(10), default='daily')    # daily | weekly | once
    local_time  = db.Column(db.String(5), default='08:00')     # "HH:MM" in the server's own local time
    weekday     = db.Column(db.Integer)                        # 0=Mon..6=Sun, used when frequency='weekly'
    once_date   = db.Column(db.String(10))                     # "YYYY-MM-DD", used when frequency='once'
    sections    = db.Column(db.String(200), default='overview,apps,net')
    unrestricted = db.Column(db.Boolean, default=False)
    per_device  = db.Column(db.Boolean, default=False)
    device_ids  = db.Column(db.String(300), default='')        # comma-separated device ids, '' = all devices
    last_sent   = db.Column(db.BigInteger)
    created_at  = db.Column(db.BigInteger, default=now_ms)

    def dev_id_list(self):
        return [int(x) for x in (self.device_ids or '').split(',') if x.strip().isdigit()]

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name or '', 'enabled': bool(self.enabled),
            'recipient': self.recipient or '', 'frequency': self.frequency or 'daily',
            'localTime': self.local_time or '08:00', 'weekday': self.weekday,
            'onceDate': self.once_date or '',
            'sections': (self.sections or '').split(',') if self.sections else [],
            'unrestricted': bool(self.unrestricted), 'perDevice': bool(self.per_device),
            'deviceIds': self.dev_id_list(), 'lastSent': self.last_sent,
        }


class User(db.Model):
    """A dashboard login. role is one of:
      superadmin — everything, including managing users and email settings,
                   and always sees every device regardless of device_ids.
      admin      — full admin actions (rename, remote control, delete, poll
                   interval) but only on the devices in device_ids (empty
                   list = every device).
      viewer     — read-only, same device scoping as admin.
    device_ids is a comma-separated list of Device.id; empty means
    unrestricted (within whatever the role itself allows)."""
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.String(16), nullable=False, default='viewer')
    device_ids    = db.Column(db.Text, default='')
    active        = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.BigInteger, default=now_ms)

    def device_id_list(self):
        return [int(x) for x in (self.device_ids or '').split(',') if x.strip().isdigit()]

    def allowed_ids(self):
        """None = unrestricted (every device); otherwise a set of allowed ids."""
        if self.role == 'superadmin' or not self.device_ids:
            return None
        return set(self.device_id_list())

    def to_dict(self):
        return {
            'id': self.id, 'username': self.username, 'role': self.role,
            'deviceIds': self.device_id_list(), 'active': bool(self.active),
            'createdAt': self.created_at,
        }


class BrowseEvent(db.Model):
    __tablename__ = 'browse_events'
    id        = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False)
    ts        = db.Column(db.BigInteger, nullable=False)
    source    = db.Column(db.String(20), nullable=False)    # accessibility | dns
    app       = db.Column(db.String(200))                   # browser package (accessibility) or empty
    url       = db.Column(db.Text)
    domain    = db.Column(db.String(255), index=True)
    title     = db.Column(db.String(300))
    uniq      = db.Column(db.String(40), nullable=False)
    __table_args__ = (
        db.UniqueConstraint('device_id', 'uniq', name='uq_browse'),
        db.Index('ix_browse_dev_ts', 'device_id', 'ts'),
    )
