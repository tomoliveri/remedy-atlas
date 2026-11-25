"""Keep one Workstead task open for finding and ranking the next research candidates."""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ws"))

from workstead import config  # noqa: E402
from workstead.admin import queue_from_env  # noqa: E402
from workstead.protocol import L, now_iso, parse_ts, partition_label, write_block  # noqa: E402

MARKER = "<!-- atlas:portfolio-review -->"
TITLE = "Portfolio review: find the next opportunity to save lives"
REVIEW_INTERVAL = timedelta(days=7)
PARTITION = "research"


def next_review(queue, now, guidance, dry_run=False):
    gh = queue.gh
    task_labels = [L["task"], partition_label(PARTITION)]

    def managed_reviews(state, since=None):
        return [
            issue for issue in gh.list_issues(labels=task_labels, state=state, since=since)
            if MARKER in issue["body"] and queue.is_bot(issue["author"])
        ]

    open_reviews = managed_reviews("open")
    if open_reviews:
        return f"Portfolio review already open at #{open_reviews[-1]['number']}."

    week_start = now - REVIEW_INTERVAL
    recent = managed_reviews("closed", since=now_iso(week_start.timestamp()))
    last_review = max((parse_ts(issue["created_at"]) for issue in recent), default=0)
    cutoff = max(last_review, week_start.timestamp())
    finished = [
        job for job in gh.list_issues(labels=[L["job"], L["done"]], state="closed", since=now_iso(cutoff))
        if "<!-- atlas:track " in job["body"] and queue.authored_by_trusted(job)
        and parse_ts(job["closed_at"]) > cutoff
    ]
    if last_review >= week_start.timestamp() and not finished:
        return "Portfolio review is current."

    trigger = ", ".join(f"#{issue['number']}" for issue in finished)
    if dry_run:
        return f"Would open a portfolio review. Trigger: {trigger or 'weekly review'}."

    body = f"{guidance.strip()}\n\n"
    if trigger:
        body += f"Research jobs recently completed: {trigger}. Review their dispositions.\n\n"
    meta = {"partition": PARTITION, "priority": 7 if finished else 5, "est_hours": 2}
    body += f"{MARKER}\n\n{write_block('meta', meta)}\n"
    # A failed POST may have reached GitHub. Let the next sweep recheck before retrying.
    issue = gh.request("POST", f"{gh.r}/issues", {
        "title": TITLE, "body": body, "labels": [*task_labels, L["ready"]],
    }, tries=1)
    return f"Opened portfolio review #{issue['number']}."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    queue = queue_from_env(config.load(ROOT))
    guidance = (ROOT / "research/portfolio-review.md").read_text(encoding="utf-8")
    print(next_review(queue, datetime.now(timezone.utc), guidance, args.dry_run))


if __name__ == "__main__":
    main()
