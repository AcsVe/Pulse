"""Scheduled email reports: a small HTML summary of chosen sections (overview
KPIs / apps / network), sent by SMTP using the server's stored EmailSettings.
Two ways a report actually gets sent — use whichever fits the host:
  1. An in-process APScheduler loop (started from app.py) — simplest, but a
     free-tier host that sleeps on inactivity may miss a scheduled time.
  2. GET/POST /api/cron/send-reports?key=... — call this from any external
     cron (cron-job.org, GitHub Actions schedule, etc.) every 15-30 min; it's
     a no-op unless a report is actually due, so calling it often is fine.
"""
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from models import db, now_ms, EmailSettings, Device
import stats

SECTION_LABELS = {'overview': 'نظرة عامة', 'apps': 'التطبيقات', 'net': 'الشبكة', 'data': 'استهلاك الإنترنت',
                   'devices': 'الأجهزة'}
ALL_SECTIONS = list(SECTION_LABELS.keys())


def _fmt_ms(ms):
    if not ms:
        return '0د'
    s = ms // 1000
    h, m = s // 3600, (s % 3600) // 60
    return f'{h}س {m}د' if h else f'{m}د'


def _fmt_bytes(n):
    if not n:
        return '0 MB'
    mb = n / (1024 * 1024)
    return f'{mb/1024:.2f} GB' if mb >= 1024 else f'{mb:.1f} MB'


def build_report_html(sections, period_label, dev_ids=None):
    dev_ids = dev_ids or [d.id for d in Device.query.all()]
    now = now_ms()
    a = now - 24 * 3600 * 1000
    ov = stats.overview(dev_ids, a, now, 0, now)
    parts = [f'<h2 style="font-family:sans-serif">تقرير Pulse — {period_label}</h2>']

    if 'overview' in sections:
        rows = ''.join(f'<tr><td style="padding:4px 10px">{k["key"]}</td>'
                        f'<td style="padding:4px 10px"><b>{_fmt_ms(k["value"]) if k["unit"]=="ms" else (_fmt_bytes(k["value"]) if k["unit"]=="bytes" else k["value"])}</b></td></tr>'
                        for k in ov['kpis'])
        parts.append(f'<h3 style="font-family:sans-serif">نظرة عامة (آخر 24 ساعة)</h3>'
                     f'<table style="font-family:sans-serif;border-collapse:collapse">{rows}</table>')

    if 'apps' in sections:
        rows = ''.join(f'<tr><td style="padding:4px 10px">{a["label"]}</td>'
                        f'<td style="padding:4px 10px"><b>{_fmt_ms(a["ms"])}</b></td></tr>' for a in ov['topApps'][:8])
        parts.append(f'<h3 style="font-family:sans-serif">الأكثر استخداماً</h3>'
                     f'<table style="font-family:sans-serif;border-collapse:collapse">{rows}</table>')

    if 'data' in sections:
        rows = ''.join(f'<tr><td style="padding:4px 10px">{a["label"]}</td>'
                        f'<td style="padding:4px 10px">⬇ {_fmt_bytes(a["rx"])} / ⬆ {_fmt_bytes(a["tx"])}</td></tr>'
                        for a in ov['topDataApps'][:8])
        parts.append(f'<h3 style="font-family:sans-serif">استهلاك الإنترنت حسب التطبيق</h3>'
                     f'<table style="font-family:sans-serif;border-collapse:collapse">{rows}</table>')

    if 'net' in sections:
        n = ov['net']
        rows = ''.join(f'<tr><td style="padding:4px 10px">{k}</td><td style="padding:4px 10px">{_fmt_ms(v)} ({n["count"][k]})</td></tr>'
                        for k, v in n['ms'].items())
        parts.append(f'<h3 style="font-family:sans-serif">الشبكة</h3>'
                     f'<table style="font-family:sans-serif;border-collapse:collapse">{rows}</table>')

    if 'devices' in sections:
        devs = Device.query.filter(Device.id.in_(dev_ids)).all() if dev_ids else Device.query.all()
        rows = ''.join(f'<tr><td style="padding:4px 10px">{d.name}</td>'
                        f'<td style="padding:4px 10px">{d.model or ""}</td>'
                        f'<td style="padding:4px 10px" dir="ltr">{d.ip_address or "—"}</td></tr>' for d in devs)
        parts.append(f'<h3 style="font-family:sans-serif">الأجهزة</h3>'
                     f'<table style="font-family:sans-serif;border-collapse:collapse">{rows}</table>')

    return ''.join(parts)


def send_email(settings: EmailSettings, subject, html):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = settings.smtp_user
    msg['To'] = settings.recipient
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587, timeout=20) as server:
        if settings.use_tls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_pass or '')
        server.sendmail(settings.smtp_user, [settings.recipient], msg.as_string())


def is_due(settings: EmailSettings, now_dt):
    if not settings.enabled or not settings.recipient or not settings.smtp_host:
        return False
    if settings.last_sent:
        last = datetime.utcfromtimestamp(settings.last_sent / 1000)
        min_gap = {'hourly': timedelta(minutes=50), 'daily': timedelta(hours=20),
                   'weekly': timedelta(days=6)}.get(settings.frequency, timedelta(hours=20))
        if now_dt - last < min_gap:
            return False
    if settings.frequency == 'hourly':
        return True  # the min-gap check above already keeps this to ~once/hour
    return now_dt.hour == (settings.hour_utc if settings.hour_utc is not None else 6)


FREQ_LABELS = {'hourly': 'كل ساعة', 'daily': 'يومي', 'weekly': 'أسبوعي'}


def run_due_reports(app):
    """Call periodically (scheduler tick or cron endpoint). Sends at most one
    combined email per configured report when due, plus one extra email per
    enrolled device when "per_device" is on (each filtered to that device)."""
    with app.app_context():
        settings = db.session.get(EmailSettings, 1)
        if not settings:
            return {'sent': False, 'reason': 'not_configured'}
        now_dt = datetime.utcnow()
        if not is_due(settings, now_dt):
            return {'sent': False, 'reason': 'not_due'}
        sections = ALL_SECTIONS if settings.unrestricted else ([s for s in (settings.sections or '').split(',') if s] or ['overview'])
        label = FREQ_LABELS.get(settings.frequency, 'يومي')
        sent = 0
        try:
            html = build_report_html(sections, label)
            send_email(settings, f'تقرير Pulse ({label})', html)
            sent += 1
            if settings.per_device:
                for d in Device.query.filter(Device.token_hash.isnot(None)).all():
                    dev_html = build_report_html(sections, f'{label} — {d.name}', dev_ids=[d.id])
                    send_email(settings, f'تقرير Pulse — {d.name} ({label})', dev_html)
                    sent += 1
            settings.last_sent = now_ms()
            db.session.commit()
            return {'sent': True, 'count': sent}
        except Exception as e:
            return {'sent': sent > 0, 'reason': str(e), 'count': sent}


def start_scheduler(app):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return None
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(lambda: run_due_reports(app), 'interval', minutes=30, id='pulse_report_tick', replace_existing=True)
    sched.start()
    return sched
