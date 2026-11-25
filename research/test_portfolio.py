import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from portfolio import MARKER, next_review, next_track


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
        self.queue.gh.list_comments.return_value = []

    def test_open_review_gets_at_most_one_literature_update_per_week(self):
        self.queue.gh.list_issues.return_value = [self.review]
        with patch("portfolio.shortlist", return_value="PubMed evidence"):
            self.assertIn("#8", next_review(self.queue, self.now, "Guidance"))
        payload = self.queue.gh.request.call_args.args[2]
        self.assertIn("PubMed evidence", payload["body"])
        self.queue.gh.list_comments.return_value = [{"author": "github-actions[bot]", "body": payload["body"]}]
        self.queue.gh.request.reset_mock()
        self.assertIn("already", next_review(self.queue, self.now, "Guidance"))
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
        with patch("portfolio.shortlist", return_value=None):
            self.assertIn("#9", next_review(self.queue, self.now, "Guidance"))
        payload = self.queue.gh.request.call_args.args[2]
        self.assertIn("#4", payload["body"])
        self.assertIn('"priority":7', payload["body"].replace(" ", ""))
        self.assertIn("ws:ready", payload["labels"])

    def test_capacity_and_starting_next_approved_track(self):
        def candidate(name, priority, phase="Queued"):
            return {"id": name, "name": name, "priority": priority,
                    "phase": phase, "question": "Published evidence?", "next": "Review it."}

        def job(name, state="open"):
            return {"body": f"<!-- atlas:track {name} -->", "state": state}

        tracks = [candidate("low", 3), candidate("next", 7), candidate("completed", 8),
                  candidate("held", 9, "On hold")]
        active = [job(name) for name in ("a", "b", "c", "d")]
        self.queue.gh.list_issues.return_value = active
        self.assertIn("capacity", next_track(self.queue, tracks))
        self.queue.gh.request.assert_not_called()
        self.queue.gh.list_issues.return_value = [*active[:3], job("completed", "closed")]
        self.assertIn("Opened next", next_track(self.queue, tracks))
        payload = self.queue.gh.request.call_args.args[2]
        self.assertIn("<!-- atlas:track next -->", payload["body"])
        self.assertIn("p:plan", payload["labels"])
