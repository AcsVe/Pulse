"""Unit tests for mailer.is_due — the local-time, multi-session scheduling
logic — and transport_ready. No network calls."""
import os
import sys
from datetime import datetime
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mailer  # noqa: E402
from models import EmailSettings, ReportSchedule  # noqa: E402


def sched(**kw):
    defaults = dict(enabled=True, recipient='a@b.com', frequency='daily', local_time='08:00',
                     weekday=None, once_date=None, last_sent=None)
    defaults.update(kw)
    return ReportSchedule(**defaults)


class IsDueTests(unittest.TestCase):
    def test_daily_fires_within_window(self):
        s = sched(local_time='08:00')
        self.assertTrue(mailer.is_due(s, datetime(2026, 1, 1, 8, 0)))
        self.assertTrue(mailer.is_due(s, datetime(2026, 1, 1, 8, 9)))
        self.assertFalse(mailer.is_due(s, datetime(2026, 1, 1, 8, 20)))

    def test_disabled_never_due(self):
        s = sched(enabled=False)
        self.assertFalse(mailer.is_due(s, datetime(2026, 1, 1, 8, 0)))

    def test_weekly_only_on_its_weekday(self):
        # 2026-01-05 is a Monday (weekday()==0)
        s = sched(frequency='weekly', weekday=0, local_time='09:00')
        self.assertTrue(mailer.is_due(s, datetime(2026, 1, 5, 9, 0)))
        self.assertFalse(mailer.is_due(s, datetime(2026, 1, 6, 9, 0)))  # Tuesday

    def test_once_only_on_its_date_and_not_after(self):
        s = sched(frequency='once', once_date='2026-02-01', local_time='10:00')
        self.assertTrue(mailer.is_due(s, datetime(2026, 2, 1, 10, 0)))
        self.assertFalse(mailer.is_due(s, datetime(2026, 2, 2, 10, 0)))

    def test_recent_last_sent_blocks_resend(self):
        s = sched(local_time='08:00', last_sent=int(datetime(2026, 1, 1, 8, 0).timestamp() * 1000))
        self.assertFalse(mailer.is_due(s, datetime(2026, 1, 1, 8, 5)))

    def test_old_last_sent_allows_next_day(self):
        s = sched(local_time='08:00', last_sent=int(datetime(2026, 1, 1, 8, 0).timestamp() * 1000))
        self.assertTrue(mailer.is_due(s, datetime(2026, 1, 2, 8, 0)))


class TransportReadyTests(unittest.TestCase):
    def test_smtp_needs_host(self):
        self.assertFalse(mailer.transport_ready(EmailSettings(provider='smtp')))
        self.assertTrue(mailer.transport_ready(EmailSettings(provider='smtp', smtp_host='smtp.example.com')))

    def test_graph_needs_all_four_fields(self):
        s = EmailSettings(provider='graph', graph_tenant_id='t', graph_client_id='c')
        self.assertFalse(mailer.transport_ready(s))
        s.graph_client_secret = 'secret'
        s.graph_sender = 'a@b.com'
        self.assertTrue(mailer.transport_ready(s))

    def test_none_settings_not_ready(self):
        self.assertFalse(mailer.transport_ready(None))


if __name__ == '__main__':
    unittest.main()
