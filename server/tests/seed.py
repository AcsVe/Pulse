"""Seed the dev DB with ~14 days of fake data for 2 devices, posted through
the real /api/v1/ingest endpoint (exercises enroll + ingest end to end)."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import db, Device, now_ms  # noqa: E402

APPS = [
    ('com.whatsapp', 'WhatsApp'), ('com.android.chrome', 'Chrome'),
    ('com.instagram.android', 'Instagram'), ('com.google.android.youtube', 'YouTube'),
    ('com.twitter.android', 'X'), ('com.tiktok', 'TikTok'),
    ('com.spotify.music', 'Spotify'), ('com.android.settings', 'Settings'),
]
DOMAINS = ['google.com', 'youtube.com', 'whatsapp.com', 'instagram.com', 'wikipedia.org',
           'github.com', 'x.com', 'news.ycombinator.com', 'amazon.com']


def seed(app):
    with app.app_context():
        db.drop_all()
        db.create_all()
        now = now_ms()
        DAY = 86400000
        devices = []
        for name in ('هاتف أحمد', 'جهاز الاستقبال'):
            d = Device(name=name)
            d.enroll_code = None
            d.enrolled_at = now - 14 * DAY
            d.last_seen = now - random.randint(0, 20 * 60000)
            d.model = random.choice(['Samsung Galaxy A54', 'Xiaomi Redmi Note 12', 'Pixel 7'])
            d.os_version = random.choice(['13', '14'])
            d.app_version = '1.0.0'
            d.ip_address = f'192.168.1.{random.randint(10,99)}'
            import hashlib
            d.token_hash = hashlib.sha256(f'seed-{name}'.encode()).hexdigest()
            db.session.add(d)
            devices.append(d)
        db.session.commit()

        from models import UsageSession, NetEvent, BrowseEvent, DataUsage, DeviceSample
        for d in devices:
            for day in range(14):
                day_start = now - (14 - day) * DAY
                # usage sessions
                for _ in range(random.randint(15, 30)):
                    pkg, label = random.choice(APPS)
                    start = day_start + random.randint(0, DAY - 60000)
                    dur = random.randint(10_000, 25 * 60_000)
                    db.session.add(UsageSession(device_id=d.id, package=pkg, app_label=label,
                                                 start_ts=start, end_ts=start + dur))
                # net events: mostly connected, a few outages
                t = day_start
                while t < day_start + DAY:
                    kind = random.choices(['connected', 'no_internet', 'failed', 'disconnected'],
                                           weights=[85, 5, 5, 5])[0]
                    dur = random.randint(5 * 60_000, 90 * 60_000) if kind == 'connected' else random.randint(30_000, 15 * 60_000)
                    db.session.add(NetEvent(device_id=d.id, kind=kind, transport=random.choice(['wifi', 'cellular']),
                                             start_ts=t, end_ts=t + dur,
                                             detail='' if kind == 'connected' else random.choice(['DNS timeout', 'لا يوجد اتصال بالراوتر', ''])))
                    t += dur
                # browse events
                for _ in range(random.randint(10, 25)):
                    dom = random.choice(DOMAINS)
                    ts = day_start + random.randint(0, DAY - 1000)
                    db.session.add(BrowseEvent(device_id=d.id, ts=ts, source=random.choice(['accessibility', 'dns']),
                                                app='Chrome', url=f'https://{dom}/path{random.randint(1,50)}',
                                                domain=dom, title=f'{dom} — page', uniq=os.urandom(8).hex()))
                # data usage: a few hourly samples per app + a device-total row
                for h in range(0, 24, 3):
                    ts = day_start + h * 3600000
                    day_rx = day_tx = 0
                    for pkg, label in random.sample(APPS, k=random.randint(3, 6)):
                        rx = random.randint(500_000, 80_000_000)
                        tx = random.randint(50_000, 15_000_000)
                        day_rx += rx; day_tx += tx
                        db.session.add(DataUsage(device_id=d.id, package=pkg, label=label, ts=ts,
                                                 rx_bytes=rx, tx_bytes=tx, transport=random.choice(['wifi', 'cellular'])))
                    db.session.add(DataUsage(device_id=d.id, package='__device__', ts=ts,
                                             rx_bytes=int(day_rx * 1.1), tx_bytes=int(day_tx * 1.1)))
                    db.session.add(DeviceSample(device_id=d.id, ts=ts,
                                                mem_used_mb=random.randint(1800, 3200), mem_total_mb=4096))
            db.session.commit()
        print(f'seeded {len(devices)} devices')


if __name__ == '__main__':
    app = create_app({'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pulse_dev.db'),
                       'SCREEN_KEY': 'screen123'})
    seed(app)
