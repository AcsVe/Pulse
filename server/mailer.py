"""Scheduled email reports: a small HTML summary of chosen sections (overview
KPIs / apps / network), sent via one shared mail transport (SMTP or
Microsoft Graph, see EmailSettings) across any number of independent
ReportSchedule "sessions" — each with its own local time/date, recipient
and content. Two ways a report actually gets sent — use whichever fits the host:
  1. An in-process APScheduler loop (started from app.py) — simplest, but a
     free-tier host that sleeps on inactivity may miss a scheduled time.
  2. GET/POST /api/cron/send-reports?key=... — call this from any external
     cron (cron-job.org, GitHub Actions schedule, etc.) every 5-10 min; it's
     a no-op unless a report is actually due, so calling it often is fine.

All schedule times are the *server's own local clock* (datetime.now()), not
UTC — simplest for a self-hosted/local server where "8am" should mean 8am
where it runs.
"""
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from models import db, now_ms, EmailSettings, ReportSchedule, Device
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


def _graph_token(settings: EmailSettings):
    url = f'https://login.microsoftonline.com/{settings.graph_tenant_id}/oauth2/v2.0/token'
    r = requests.post(url, data={
        'client_id': settings.graph_client_id,
        'client_secret': settings.graph_client_secret,
        'scope': 'https://graph.microsoft.com/.default',
        'grant_type': 'client_credentials',
    }, timeout=20)
    r.raise_for_status()
    return r.json()['access_token']


def _send_via_graph(settings: EmailSettings, recipient, subject, html):
    token = _graph_token(settings)
    url = f'https://graph.microsoft.com/v1.0/users/{settings.graph_sender}/sendMail'
    body = {
        'message': {
            'subject': subject,
            'body': {'contentType': 'HTML', 'content': html},
            'toRecipients': [{'emailAddress': {'address': a.strip()}} for a in recipient.split(',') if a.strip()],
        },
        'saveToSentItems': 'true',
    }
    r = requests.post(url, json=body, headers={'Authorization': f'Bearer {token}'}, timeout=20)
    if r.status_code >= 300:
        raise RuntimeError(f'graph sendMail failed: {r.status_code} {r.text[:300]}')


def _send_via_smtp(settings: EmailSettings, recipient, subject, html):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = settings.smtp_user
    msg['To'] = recipient
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587, timeout=20) as server:
        if settings.use_tls:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_pass or '')
        server.sendmail(settings.smtp_user, [a.strip() for a in recipient.split(',') if a.strip()], msg.as_string())


def send_email(settings: EmailSettings, recipient, subject, html):
    if settings.provider == 'graph':
        _send_via_graph(settings, recipient, subject, html)
    else:
        _send_via_smtp(settings, recipient, subject, html)


def transport_ready(settings: EmailSettings):
    if not settings:
        return False
    if settings.provider == 'graph':
        return bool(settings.graph_tenant_id and settings.graph_client_id and settings.graph_client_secret and settings.graph_sender)
    return bool(settings.smtp_host)


def _time_to_minutes(hhmm):
    try:
        h, m = (hhmm or '08:00').split(':')
        return int(h) * 60 + int(m)
    except Exception:
        return 8 * 60


# A scheduler/cron tick within this many minutes of a session's target time
# counts as "due" — wide enough to survive a slow tick interval, narrow
# enough that two ticks in the same window don't double-send (last_sent is
# also checked below as a second guard).
DUE_WINDOW_MIN = 10

FREQ_LABELS = {'daily': 'يومي', 'weekly': 'أسبوعي', 'once': 'لمرة واحدة'}


def is_due(sch: ReportSchedule, now_dt):
    if not sch.enabled or not sch.recipient:
        return False
    if abs((now_dt.hour * 60 + now_dt.minute) - _time_to_minutes(sch.local_time)) > DUE_WINDOW_MIN:
        return False
    if sch.frequency == 'once':
        if sch.once_date != now_dt.strftime('%Y-%m-%d'):
            return False
    elif sch.frequency == 'weekly':
        if sch.weekday is None or now_dt.weekday() != sch.weekday:
            return False
    if sch.last_sent:
        last = datetime.fromtimestamp(sch.last_sent / 1000)
        if now_dt - last < timedelta(hours=1):
            return False
    return True


def run_due_reports(app):
    """Call periodically (scheduler tick or cron endpoint). Checks every
    ReportSchedule session and sends whichever are due, using local server
    time — each sends one combined email, plus one extra per enrolled device
    when that session's "per_device" is on."""
    with app.app_context():
        settings = db.session.get(EmailSettings, 1)
        if not transport_ready(settings):
            return {'sent': False, 'reason': 'transport_not_configured'}
        now_dt = datetime.now()
        due = [s for s in ReportSchedule.query.all() if is_due(s, now_dt)]
        if not due:
            return {'sent': False, 'reason': 'not_due'}
        total_sent, errors = 0, []
        for sch in due:
            sections = ALL_SECTIONS if sch.unrestricted else ([s for s in (sch.sections or '').split(',') if s] or ['overview'])
            label = sch.name or FREQ_LABELS.get(sch.frequency, 'يومي')
            dev_ids = sch.dev_id_list() or None
            try:
                html = build_report_html(sections, label, dev_ids=dev_ids)
                send_email(settings, sch.recipient, f'تقرير Pulse ({label})', html)
                total_sent += 1
                if sch.per_device:
                    devs = Device.query.filter(Device.id.in_(dev_ids)) if dev_ids else Device.query
                    for d in devs.filter(Device.token_hash.isnot(None)).all():
                        dev_html = build_report_html(sections, f'{label} — {d.name}', dev_ids=[d.id])
                        send_email(settings, sch.recipient, f'تقرير Pulse — {d.name} ({label})', dev_html)
                        total_sent += 1
                sch.last_sent = now_ms()
                if sch.frequency == 'once':
                    sch.enabled = False  # one-shot: don't fire again
                db.session.commit()
            except Exception as e:
                errors.append(f'{sch.id}: {e}')
        return {'sent': total_sent > 0, 'count': total_sent, 'errors': errors}


def start_scheduler(app):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return None
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(lambda: run_due_reports(app), 'interval', minutes=10, id='pulse_report_tick', replace_existing=True)
    sched.start()
    return sched
