import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from portfolio import MARKER, next_review


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.queue = Mock()
        self.queue.gh.r = "/repos/owner/project"
        self.now = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
        self.review = {
            "number": 8, "body": MARKER, "author": "github-actions[bot]",
            "created_at": "2026-11-25T03:00:00Z",
        }
        self.queue.gh.request.return_value = {"number": 9}

    def test_open_review_prevents_duplicates(self):
        self.queue.gh.list_issues.return_value = [self.review]
        self.assertIn("#8", next_review(self.queue, self.now, "Guidance"))
        self.queue.gh.request.assert_not_called()

    def test_weekly_review_preview_does_not_write(self):
        self.queue.gh.list_issues.return_value = []
        self.assertIn("weekly review", next_review(self.queue, self.now, "Guidance", dry_run=True))
        self.queue.gh.request.assert_not_called()

    def test_current_review_waits(self):
        self.queue.gh.list_issues.side_effect = [[], [self.review], []]
        self.assertIn("current", next_review(self.queue, self.now, "Guidance"))
        self.queue.gh.request.assert_not_called()

    def test_new_completion_opens_prioritized_ready_review(self):
        job = {"number": 4, "body": "<!-- atlas:track ndm -->", "closed_at": "2026-11-26T01:00:00Z"}
        self.queue.gh.list_issues.side_effect = [[], [self.review], [job]]
        self.assertIn("#9", next_review(self.queue, self.now, "Guidance"))
        payload = self.queue.gh.request.call_args.args[2]
        self.assertIn("#4", payload["body"])
        self.assertIn('"priority":7', payload["body"].replace(" ", ""))
        self.assertIn("ws:ready", payload["labels"])
