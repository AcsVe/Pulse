"""Report math. All timestamps are epoch milliseconds (UTC); `tz` is the
viewer's UTC offset in minutes so "a day" / "an hour" mean the viewer's."""
from datetime import datetime, timedelta

from sqlalchemy import and_, or_

from models import db, UsageSession, NetEvent, BrowseEvent, Device, DataUsage, DeviceSample, AppLabelOverride
from site_categories import categorize_domain

DAY = 86400000
HOUR = 3600000
KINDS = ('connected', 'no_internet', 'failed', 'disconnected')


def _chunks(start, end, unit, tz):
    """Split [start, end) at viewer-local `unit` boundaries -> (bucket_index, ms)."""
    off = tz * 60000
    cur = start
    while cur < end:
        idx = (cur + off) // unit
        nxt = min(end, (idx + 1) * unit - off)
        yield idx, nxt - cur
        cur = nxt


def day_label(idx):
    return (datetime(1970, 1, 1) + timedelta(days=idx)).strftime('%Y-%m-%d')


def day_range(a, b, tz):
    off = tz * 60000
    first = (a + off) // DAY
    last = (max(a, b - 1) + off) // DAY
    return list(range(first, last + 1))


def usage_stats(dev_ids, a, b, tz):
    rows = UsageSession.query.filter(
        UsageSession.device_id.in_(dev_ids), UsageSession.end_ts > a, UsageSession.start_ts < b).all()
    overrides = label_overrides()
    total = 0
    per_app, per_day, per_hour = {}, {}, [0] * 24
    for r in rows:
        s, e = max(r.start_ts, a), min(r.end_ts, b)
        if e <= s:
            continue
        ms = e - s
        total += ms
        d = per_app.setdefault(r.package, {'package': r.package, 'label': apply_label(overrides, r.package, r.app_label),
                                           'ms': 0, 'sessions': 0, 'last': 0})
        d['ms'] += ms
        d['sessions'] += 1
        d['last'] = max(d['last'], r.end_ts)
        if overrides.get(r.package):
            d['label'] = overrides[r.package]
        elif r.app_label:
            d['label'] = r.app_label
        for idx, m in _chunks(s, e, DAY, tz):
            per_day[idx] = per_day.get(idx, 0) + m
        for idx, m in _chunks(s, e, HOUR, tz):
            per_hour[idx % 24] += m
    return {'totalMs': total, 'sessions': len(rows), 'apps': per_app, 'perDay': per_day, 'perHour': per_hour}


def net_stats(dev_ids, a, b, tz, now):
    rows = NetEvent.query.filter(NetEvent.device_id.in_(dev_ids), NetEvent.start_ts < b,
                                 or_(NetEvent.end_ts.is_(None), NetEvent.end_ts > a)).all()
    last_seen = {d.id: (d.last_seen or 0) for d in Device.query.filter(Device.id.in_(dev_ids)).all()}
    ms = {k: 0 for k in KINDS}
    count = {k: 0 for k in KINDS}
    longest = {k: 0 for k in KINDS}
    per_day = {}
    transport_ms = {}
    for r in rows:
        end = r.end_ts
        if end is None:   # still open: cap at the last time the device reported in
            end = min(now, max(last_seen.get(r.device_id, 0), r.start_ts))
        s, e = max(r.start_ts, a), min(end, b)
        if e <= s or r.kind not in ms:
            continue
        ms[r.kind] += e - s
        if r.start_ts >= a:
            count[r.kind] += 1
        longest[r.kind] = max(longest[r.kind], end - r.start_ts)
        for idx, m in _chunks(s, e, DAY, tz):
            per_day.setdefault(idx, {k: 0 for k in KINDS})[r.kind] += m
        tr = (r.transport or 'unknown').lower()
        transport_ms[tr] = transport_ms.get(tr, 0) + (e - s)
    monitored = sum(ms.values())
    outage_ms = ms['no_internet'] + ms['failed'] + ms['disconnected']
    return {'ms': ms, 'count': count, 'longest': longest, 'perDay': per_day, 'monitoredMs': monitored,
            'outageMs': outage_ms, 'outageCount': count['no_internet'] + count['failed'] + count['disconnected'],
            'availability': (ms['connected'] / monitored * 100.0) if monitored else None,
            'transportMs': transport_ms}


def browse_stats(dev_ids, a, b):
    rows = BrowseEvent.query.filter(BrowseEvent.device_id.in_(dev_ids),
                                    BrowseEvent.ts >= a, BrowseEvent.ts < b).all()
    domains = {}
    for r in rows:
        if r.domain:
            domains[r.domain] = domains.get(r.domain, 0) + 1
    return {'count': len(rows), 'distinct': len(domains), 'domains': domains}


def label_overrides():
    return {r.package: r.label for r in AppLabelOverride.query.all()}


def apply_label(label_map, package, fallback_label):
    return label_map.get(package) or fallback_label or package


def data_usage_stats(dev_ids, a, b, tz):
    rows = DataUsage.query.filter(DataUsage.device_id.in_(dev_ids), DataUsage.ts >= a, DataUsage.ts < b).all()
    overrides = label_overrides()
    total_rx = total_tx = 0
    per_app, per_day, per_hour = {}, {}, [{'rx': 0, 'tx': 0} for _ in range(24)]
    for r in rows:
        if r.package == '__device__':
            total_rx += r.rx_bytes or 0
            total_tx += r.tx_bytes or 0
            idx = (r.ts + tz * 60000) // DAY
            d = per_day.setdefault(idx, {'rx': 0, 'tx': 0})
            d['rx'] += r.rx_bytes or 0
            d['tx'] += r.tx_bytes or 0
            hidx = ((r.ts + tz * 60000) // HOUR) % 24
            per_hour[hidx]['rx'] += r.rx_bytes or 0
            per_hour[hidx]['tx'] += r.tx_bytes or 0
            continue
        d = per_app.setdefault(r.package, {'package': r.package, 'label': apply_label(overrides, r.package, r.label),
                                           'rx': 0, 'tx': 0})
        d['rx'] += r.rx_bytes or 0
        d['tx'] += r.tx_bytes or 0
        if overrides.get(r.package):
            d['label'] = overrides[r.package]
    return {'totalRx': total_rx, 'totalTx': total_tx, 'apps': per_app, 'perDay': per_day, 'perHour': per_hour}


def data_usage_table(dev_ids, a, b):
    stats = data_usage_stats(dev_ids, a, b, 0)
    total = stats['totalRx'] + stats['totalTx']
    rows = []
    for pkg, d in stats['apps'].items():
        t = d['rx'] + d['tx']
        rows.append({'id': pkg, 'package': pkg, 'label': d['label'], 'rx': d['rx'], 'tx': d['tx'],
                     'total': t, 'share': (t / total * 100) if total else 0})
    # Per-app attribution needs NetworkStatsManager.queryDetailsForUid per app,
    # which can legitimately come back empty on some OEM/Android-version
    # combinations (DataUsageCollector.queryStatsForUid skips a uid rather
    # than report a false zero when that query fails) even while the
    # whole-device total (plain TrafficStats, no per-UID API involved) keeps
    # recording fine. Since stats['apps'] is the only thing this table ever
    # listed, a device stuck in that state showed "No data in this period"
    # here forever — real traffic was being recorded the whole time, just
    # never surfaced because it couldn't be split by app. Fall back to one
    # row for the device total so real usage is never hidden entirely.
    if not rows and total:
        rows.append({'id': '__device__', 'package': '__device__', 'label': None,
                     'rx': stats['totalRx'], 'tx': stats['totalTx'], 'total': total, 'share': 100.0})
    return rows


def memory_stats(dev_ids, a, b, tz, limit=2000):
    q = DeviceSample.query.filter(DeviceSample.device_id.in_(dev_ids), DeviceSample.ts >= a, DeviceSample.ts < b) \
        .order_by(DeviceSample.ts.asc()).limit(limit)
    rows = [{'ts': r.ts, 'usedMb': r.mem_used_mb, 'totalMb': r.mem_total_mb} for r in q]
    latest = rows[-1] if rows else None
    return {'samples': rows, 'latest': latest}


def delta_pct(cur, prev):
    if prev in (None, 0):
        return None if not cur else 100.0
    return (cur - prev) / prev * 100.0


def overview(dev_ids, a, b, tz, now):
    span = b - a
    pa, pb = a - span, a
    cu, pu = usage_stats(dev_ids, a, b, tz), usage_stats(dev_ids, pa, pb, tz)
    cn, pn = net_stats(dev_ids, a, b, tz, now), net_stats(dev_ids, pa, pb, tz, now)
    cb, pb_ = browse_stats(dev_ids, a, b), browse_stats(dev_ids, pa, pb)
    cd, pd_ = data_usage_stats(dev_ids, a, b, tz), data_usage_stats(dev_ids, pa, pb, tz)
    days = day_range(a, b, tz)
    pdays = day_range(pa, pb, tz)
    n_days = max(1, len(days))

    def top_apps():
        out = []
        for pkg, d in sorted(cu['apps'].items(), key=lambda kv: -kv[1]['ms'])[:10]:
            prev_ms = pu['apps'].get(pkg, {}).get('ms', 0)
            out.append({**d, 'prevMs': prev_ms, 'delta': delta_pct(d['ms'], prev_ms)})
        return out

    def top_domains():
        return [{'domain': k, 'count': v, 'prev': pb_['domains'].get(k, 0)}
                for k, v in sorted(cb['domains'].items(), key=lambda kv: -kv[1])[:10]]

    def top_data_apps():
        out = []
        for pkg, d in sorted(cd['apps'].items(), key=lambda kv: -(kv[1]['rx'] + kv[1]['tx']))[:10]:
            prev = pd_['apps'].get(pkg, {'rx': 0, 'tx': 0})
            out.append({**d, 'prevRx': prev['rx'], 'prevTx': prev['tx']})
        return out

    kpis = [
        ('screenTime', cu['totalMs'], pu['totalMs'], 'ms', 'neutral'),
        ('avgPerDay', cu['totalMs'] / n_days, pu['totalMs'] / max(1, len(pdays)), 'ms', 'neutral'),
        ('sessions', cu['sessions'], pu['sessions'], 'n', 'neutral'),
        ('appsUsed', len(cu['apps']), len(pu['apps']), 'n', 'neutral'),
        ('sites', cb['count'], pb_['count'], 'n', 'neutral'),
        ('domains', cb['distinct'], pb_['distinct'], 'n', 'neutral'),
        ('outages', cn['outageCount'], pn['outageCount'], 'n', 'bad'),
        ('outageTime', cn['outageMs'], pn['outageMs'], 'ms', 'bad'),
        ('availability', cn['availability'], pn['availability'], 'pct', 'good'),
        ('download', cd['totalRx'], pd_['totalRx'], 'bytes', 'neutral'),
        ('upload', cd['totalTx'], pd_['totalTx'], 'bytes', 'neutral'),
    ]
    return {
        'range': {'from': a, 'to': b, 'prevFrom': pa, 'prevTo': pb},
        'kpis': [{'key': k, 'value': v, 'prev': p, 'unit': u, 'tone': t,
                  'delta': (None if (v is None or p is None) else delta_pct(v, p))} for k, v, p, u, t in kpis],
        'daily': [{'day': day_label(i), 'ms': cu['perDay'].get(i, 0),
                   'net': cn['perDay'].get(i, {k: 0 for k in KINDS}),
                   'data': cd['perDay'].get(i, {'rx': 0, 'tx': 0})} for i in days],
        'prevDaily': [{'day': day_label(i), 'ms': pu['perDay'].get(i, 0)} for i in pdays],
        'hourly': cu['perHour'],
        'hourlyData': cd['perHour'],
        'topApps': top_apps(),
        'topDomains': top_domains(),
        'topDataApps': top_data_apps(),
        'net': {'ms': cn['ms'], 'count': cn['count'], 'longest': cn['longest'], 'transportMs': cn['transportMs']},
    }


def apps_table(dev_ids, a, b, tz):
    span = b - a
    cu, pu = usage_stats(dev_ids, a, b, tz), usage_stats(dev_ids, a - span, a, tz)
    rows = []
    for pkg, d in cu['apps'].items():
        prev_ms = pu['apps'].get(pkg, {}).get('ms', 0)
        rows.append({'id': pkg, 'package': pkg, 'label': d['label'], 'ms': d['ms'], 'sessions': d['sessions'],
                     'avgMs': d['ms'] / d['sessions'], 'share': (d['ms'] / cu['totalMs'] * 100) if cu['totalMs'] else 0,
                     'last': d['last'], 'prevMs': prev_ms, 'delta': delta_pct(d['ms'], prev_ms)})
    return rows


def browse_table(dev_ids, a, b, limit=5000):
    q = BrowseEvent.query.filter(BrowseEvent.device_id.in_(dev_ids), BrowseEvent.ts >= a, BrowseEvent.ts < b) \
        .order_by(BrowseEvent.ts.desc()).limit(limit)
    names = {d.id: d.name for d in Device.query.all()}
    return [{'id': r.id, 'ts': r.ts, 'device': names.get(r.device_id, ''), 'domain': r.domain or '',
             'url': r.url or '', 'title': r.title or '', 'source': r.source, 'app': r.app or '',
             'category': categorize_domain(r.domain)} for r in q]


def net_table(dev_ids, a, b, now, limit=5000):
    q = NetEvent.query.filter(NetEvent.device_id.in_(dev_ids), NetEvent.start_ts < b,
                              or_(NetEvent.end_ts.is_(None), NetEvent.end_ts > a)) \
        .order_by(NetEvent.start_ts.desc()).limit(limit)
    devs = {d.id: d for d in Device.query.all()}
    out = []
    for r in q:
        d = devs.get(r.device_id)
        end = r.end_ts
        ongoing = end is None
        if ongoing:
            end = min(now, max((d.last_seen or 0) if d else 0, r.start_ts))
        out.append({'id': r.id, 'start': r.start_ts, 'end': None if ongoing else r.end_ts,
                    'durationMs': max(0, end - r.start_ts), 'kind': r.kind, 'transport': r.transport or '',
                    'detail': r.detail or '', 'device': d.name if d else '', 'ongoing': ongoing})
    return out
