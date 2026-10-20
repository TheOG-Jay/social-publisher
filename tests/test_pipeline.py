import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from publisher.ai import RewriteError
from publisher.linkedin import LinkedInError, TokenExpiredError
from publisher.models import FAILED, PENDING, POSTED, POSTING, PostRow
from publisher.pipeline import parse_schedule, run_pipeline
from publisher.sheets import parse_rows

TZ = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=TZ)


class FakeSheet:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def fetch_rows(self):
        return self.rows

    def update_row(self, row_number, status, urn="", error="", published_text=""):
        self.updates.append((row_number, status, urn, error, published_text))

    def statuses(self, row_number):
        return [u[1] for u in self.updates if u[0] == row_number]


class FakeLinkedIn:
    def __init__(self, behaviour=None):
        self.posted = []
        self.behaviour = behaviour or {}

    def create_post(self, text):
        err = self.behaviour.get(text)
        if err:
            raise err
        self.posted.append(text)
        return f"urn:li:share:{len(self.posted)}"


class FakeRewriter:
    def __init__(self, fail=False):
        self.fail = fail

    def rewrite(self, text):
        if self.fail:
            raise RewriteError("boom")
        return f"REWRITTEN: {text}"


def row(n, text="hello", when="2026-10-25 09:00", status=PENDING, ai=False):
    return PostRow(row_number=n, id=str(n), text=text, scheduled_raw=when, status=status, ai_rewrite=ai)


def run(sheet, li, **kw):
    return run_pipeline(sheet, li, TZ, now=NOW, **kw)


class PipelineTests(unittest.TestCase):
    def test_posts_due_pending_row_and_records_result(self):
        sheet, li = FakeSheet([row(2)]), FakeLinkedIn()
        summary = run(sheet, li)
        self.assertEqual(summary.posted, [2])
        self.assertEqual(sheet.statuses(2), [POSTING, POSTED])
        self.assertEqual(sheet.updates[-1][2], "urn:li:share:1")
        self.assertEqual(sheet.updates[-1][4], "hello")

    def test_skips_future_and_non_pending_rows(self):
        sheet = FakeSheet([row(2, when="2026-10-26 09:00"), row(3, status=POSTED), row(4, status="FAILED")])
        li = FakeLinkedIn()
        summary = run(sheet, li)
        self.assertEqual(li.posted, [])
        self.assertEqual(sheet.updates, [])
        self.assertEqual(summary.skipped, 3)

    def test_status_match_is_case_insensitive(self):
        sheet, li = FakeSheet([row(2, status=" pending ")]), FakeLinkedIn()
        run(sheet, li)
        self.assertEqual(li.posted, ["hello"])

    def test_invalid_date_marks_failed_without_posting(self):
        sheet, li = FakeSheet([row(2, when="tomorrow-ish")]), FakeLinkedIn()
        summary = run(sheet, li)
        self.assertEqual(summary.failed, [2])
        self.assertEqual(sheet.statuses(2), [FAILED])
        self.assertEqual(li.posted, [])

    def test_api_error_marks_failed_and_continues(self):
        sheet = FakeSheet([row(2, text="bad"), row(3, text="good")])
        li = FakeLinkedIn({"bad": LinkedInError("422 nope")})
        summary = run(sheet, li)
        self.assertEqual(summary.failed, [2])
        self.assertEqual(summary.posted, [3])
        self.assertEqual(sheet.statuses(2), [POSTING, FAILED])

    def test_unexpected_error_does_not_leave_row_stuck_in_posting(self):
        sheet = FakeSheet([row(2, text="x")])
        li = FakeLinkedIn({"x": RuntimeError("kaboom")})
        run(sheet, li)
        self.assertEqual(sheet.statuses(2), [POSTING, FAILED])

    def test_expired_token_reverts_row_and_stops_run(self):
        sheet = FakeSheet([row(2, text="a", when="2026-10-25 08:00"), row(3, text="b")])
        li = FakeLinkedIn({"a": TokenExpiredError("401")})
        summary = run(sheet, li)
        self.assertTrue(summary.token_expired)
        self.assertEqual(sheet.statuses(2), [POSTING, PENDING])
        self.assertEqual(sheet.statuses(3), [])  # untouched
        self.assertEqual(li.posted, [])

    def test_oldest_first_and_max_posts_limit(self):
        sheet = FakeSheet([
            row(2, text="late", when="2026-10-25 11:00"),
            row(3, text="early", when="2026-10-25 08:00"),
            row(4, text="mid", when="2026-10-25 09:00"),
        ])
        li = FakeLinkedIn()
        run(sheet, li, max_posts=2)
        self.assertEqual(li.posted, ["early", "mid"])
        self.assertEqual(sheet.statuses(2), [])  # left for next run

    def test_dry_run_changes_nothing(self):
        sheet, li = FakeSheet([row(2)]), FakeLinkedIn()
        summary = run(sheet, li, dry_run=True)
        self.assertEqual(summary.would_post, [2])
        self.assertEqual(sheet.updates, [])
        self.assertEqual(li.posted, [])

    def test_ai_rewrite_used_when_flagged(self):
        sheet, li = FakeSheet([row(2, ai=True), row(3, text="plain")]), FakeLinkedIn()
        run(sheet, li, rewriter=FakeRewriter())
        self.assertEqual(li.posted, ["REWRITTEN: hello", "plain"])

    def test_ai_failure_falls_back_to_original_text(self):
        sheet, li = FakeSheet([row(2, ai=True)]), FakeLinkedIn()
        summary = run(sheet, li, rewriter=FakeRewriter(fail=True))
        self.assertEqual(li.posted, ["hello"])
        self.assertEqual(summary.posted, [2])


class ParsingTests(unittest.TestCase):
    def test_parse_schedule_formats(self):
        self.assertEqual(parse_schedule("2026-10-25 09:00", TZ).hour, 9)
        self.assertEqual(parse_schedule("2026-10-25T09:30", TZ).minute, 30)
        self.assertEqual(parse_schedule("2026-10-25", TZ).hour, 0)
        with self.assertRaises(ValueError):
            parse_schedule("25/10/2026", TZ)

    def test_parse_rows_pads_short_rows_and_numbers_from_two(self):
        rows = parse_rows([["1", "Hi", "2026-10-25 09:00", "Pending"], ["2", "Yo", "x", "Posted", "urn", "TRUE"]])
        self.assertEqual([r.row_number for r in rows], [2, 3])
        self.assertFalse(rows[0].ai_rewrite)
        self.assertTrue(rows[1].ai_rewrite)
        self.assertEqual(rows[0].urn, "")


if __name__ == "__main__":
    unittest.main()
