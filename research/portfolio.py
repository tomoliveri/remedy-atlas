"""Keep one Workstead task open for finding and ranking the next research candidates."""

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/ws"))

from scout import shortlist  # noqa: E402
from workstead import config  # noqa: E402
from workstead.admin import queue_from_env  # noqa: E402
from workstead.protocol import L, now_iso, parse_ts, partition_label, write_block  # noqa: E402

MARKER = "<!-- atlas:portfolio-review -->"
TITLE = "Portfolio review: find the next opportunity to save lives"
REVIEW_INTERVAL = timedelta(days=7)
PARTITION = "research"
ACTIVE_JOB_LIMIT = 4
TRACK_MARKER = re.compile(r"<!-- atlas:track ([a-z0-9-]+) -->")


def scout_update(queue, issue, now, dry_run):
    tag = now.strftime("<!-- atlas:scout:%G-W%V -->")
    gh = queue.gh
    if tag in issue["body"] or any(
        tag in comment["body"] and queue.is_bot(comment["author"])
        for comment in gh.list_comments(issue["number"])
    ):
        return "This week’s literature scan is already on the portfolio review."
    if dry_run:
        return f"Would add this week’s literature scan to #{issue['number']}."
    report = shortlist(now.date())
    if report is None:
        return "Literature sources are temporarily unavailable. The next sweep will retry."
    gh.request("POST", f"{gh.r}/issues/{issue['number']}/comments", {"body": f"{report}\n\n{tag}"}, tries=1)
    return f"Added fresh literature leads to #{issue['number']}."


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
        return scout_update(queue, open_reviews[-1], now, dry_run)

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
    report = shortlist(now.date())
    if report is not None:
        body += f"{report}\n\n" + now.strftime("<!-- atlas:scout:%G-W%V -->") + "\n\n"
    meta = {"partition": PARTITION, "priority": 7 if finished else 5, "est_hours": 2}
    body += f"{MARKER}\n\n{write_block('meta', meta)}\n"
    # A failed POST may have reached GitHub. Let the next sweep recheck before retrying.
    issue = gh.request("POST", f"{gh.r}/issues", {
        "title": TITLE, "body": body, "labels": [*task_labels, L["ready"]],
    }, tries=1)
    return f"Opened portfolio review #{issue['number']}."


def next_track(queue, tracks, dry_run=False):
    gh = queue.gh
    known = set()
    active = set()
    for issue in gh.list_issues(labels=[L["job"]], state="all"):
        marker = TRACK_MARKER.search(issue["body"])
        if not marker or not queue.authored_by_trusted(issue):
            continue
        track = marker[1]
        known.add(track)
        if issue["state"] == "open":
            active.add(track)

    if len(active) >= ACTIVE_JOB_LIMIT:
        return f"Research queue is at capacity ({len(active)} open tracks)."
    queued = sorted((track for track in tracks if track["phase"] == "Queued" and track["id"] not in known),
                    key=lambda track: -track["priority"])
    if not queued:
        return "No approved backlog track is ready to open."
    track = queued[0]
    if dry_run:
        return f"Would open the next approved track: {track['name']}."

    meta = {"partition": "plan", "origin": "job", "priority": track["priority"], "depth": 0}
    body = (
        f"{track['question']}\n\n{track['next']}\n\n"
        f"Starter plan: `python3 research/atlas.py plan {track['id']}`. "
        "The public work covers published evidence and impact analysis. See docs/PROJECT.md."
        f"\n\n<!-- atlas:track {track['id']} -->\n\n{write_block('meta', meta)}\n"
    )
    issue = gh.request("POST", f"{gh.r}/issues", {
        "title": f"{track['name']}: evidence and impact",
        "body": body, "labels": [L["job"], L["task"], L["ready"], partition_label("plan")],
    }, tries=1)
    return f"Opened {track['name']} as #{issue['number']}."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preview-scout", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.preview_scout:
        print(shortlist(now.date()) or "Literature sources are temporarily unavailable.")
        return
    queue = queue_from_env(config.load(ROOT))
    guidance = (ROOT / "research/portfolio-review.md").read_text(encoding="utf-8")
    tracks = json.loads((ROOT / "site/public/tracks.json").read_text(encoding="utf-8"))
    print(next_track(queue, tracks, args.dry_run))
    print(next_review(queue, now, guidance, args.dry_run))


if __name__ == "__main__":
    main()
