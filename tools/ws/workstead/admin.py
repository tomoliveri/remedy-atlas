"""Maintainer and GitHub Actions commands."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from . import config as C
from .engine import Queue
from .gh import GitHub
from .protocol import L, write_block

JOIN_START, JOIN_END = "<!-- ws:join:start -->", "<!-- ws:join:end -->"
CREDIT_START, CREDIT_END = "<!-- ws:credit:start -->", "<!-- ws:credit:end -->"
BADGES_START, BADGES_END = "<!-- ws:badges:start -->", "<!-- ws:badges:end -->"
TEMPLATE_START, TEMPLATE_END = "<!-- ws:template:start -->", "<!-- ws:template:end -->"


def badges(repo: str, upstream: str) -> str:
    return "\n".join([
        f'<a href="https://github.com/{repo}/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/{repo}/actions/workflows/ci.yml/badge.svg"></a>',
        f'<a href="https://github.com/{repo}/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://github.com/{repo}/actions/workflows/codeql.yml/badge.svg"></a>',
        f'<a href="https://github.com/{repo}/blob/HEAD/LICENSE"><img alt="MIT licence" src="https://img.shields.io/badge/licence-MIT-3fb950"></a>',
        '<img alt="Python 3.9+" src="https://img.shields.io/badge/python-3.9%2B-58a6ff">',
        '<img alt="Zero dependencies" src="https://img.shields.io/badge/dependencies-zero-a371f7">',
        f'<a href="https://github.com/{upstream}"><img alt="Built with Workstead" src="https://img.shields.io/badge/built%20with-Workstead-d29922"></a>',
    ])
ATTRIBUTION_MARK = "<!-- ws:attribution-request -->"


def join_prompt(repo: str, branch: str) -> str:
    return (f"Read https://raw.githubusercontent.com/{repo}/{branch}/JOIN.md and follow it to contribute to this "
            "project. Ask me once before you install or post anything, then keep working until the project is "
            "finished or I say stop.")


def _region(text: str, start: str, end: str, inner: str) -> str:
    if start not in text or end not in text:
        return text
    return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _m: f"{start}\n{inner}\n{end}", text, flags=re.S)


def render_join(root: Path, repo: str, branch: str, upstream: Optional[str] = None) -> bool:
    """Write this repository's join prompt (and the credit line) into README.md."""
    f = root / "README.md"
    if not f.is_file():
        return False
    text = f.read_text()
    new = _region(text, JOIN_START, JOIN_END, f"```text\n{join_prompt(repo, branch)}\n```")
    new = _region(new, BADGES_START, BADGES_END, badges(repo, upstream or repo))
    new = _region(new, TEMPLATE_START, TEMPLATE_END,
                  f'<a href="https://github.com/{upstream or repo}/generate"><img alt="Use this template" '
                  'src="https://img.shields.io/badge/Use%20this%20template-2ea44f?style=for-the-badge&logo=github"></a>')
    new = _region(new, CREDIT_START, CREDIT_END,
                  f"```markdown\nCoordinated by [Workstead](https://github.com/{upstream or repo}), a fleet of AI agents "
                  "working through GitHub issues.\n```")
    if new != text:
        f.write_text(new)
        return True
    return False


def attribution_text(upstream: Optional[str]) -> str:
    link = f"https://github.com/{upstream}" if upstream else "https://github.com/ (the Workstead template you used)"
    return (f"{ATTRIBUTION_MARK}\n**A small request (not a requirement).** If Workstead helps this project, please "
            f"credit it in your README, for example:\n\n```markdown\nCoordinated by [Workstead]({link}), "
            "a fleet of AI agents working through GitHub issues.\n```\n\n"
            "Optionally, set `give_back.enabled` to `true` in `workstead.json` to give 0.1% of your fleet's time back "
            "to improving Workstead. Joiners are told about it before they agree, and anyone can opt out. "
            "Neither is required, and nothing checks for it.")


def queue_from_env(cfg: Dict[str, Any]) -> Queue:
    repo = os.environ.get("GITHUB_REPOSITORY") or cfg["repo"]
    if not repo:
        raise SystemExit("ws: GITHUB_REPOSITORY is not set")
    gh = GitHub(repo, min_remaining=int(os.environ.get("WS_MIN_REMAINING", "100")))
    ref = os.environ.get("GITHUB_REF_NAME") or cfg["default_branch"]
    if os.environ.get("GITHUB_EVENT_NAME") in ("pull_request_target", "issue_comment", "issues", "workflow_run"):
        ref = cfg["default_branch"]
    return Queue(gh, cfg, workflow=os.environ.get("WS_WORKFLOW", "ws-queue.yml"), ref=ref)


def actions_event(root: Path) -> int:
    cfg = C.load(root)
    q = queue_from_env(cfg)
    name = os.environ.get("GITHUB_EVENT_NAME", "")
    path = os.environ.get("GITHUB_EVENT_PATH")
    payload = json.loads(Path(path).read_text()) if path else {}
    q.handle_event(name, payload)
    print(f"handled {name}; dispatched {len(q.dispatched)}; API calls {q.gh.calls}; remaining {q.gh.remaining}")
    return 0


def actions_sweep(root: Path) -> int:
    cfg = C.load(root)
    q = queue_from_env(cfg)
    snap = q.sweep()
    st = snap["stats"]
    summary = (f"### Workstead sweep\n\nopen tasks {st['open_tasks']} · done in 24 h {st['done_24h']} · "
               f"dispatched {len(q.dispatched)} · API calls {q.gh.calls} · rate limit remaining {q.gh.remaining}\n")
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a") as f:
            f.write(summary)
    print(summary)
    return 0


def setup(root: Path, write_files: bool = True) -> int:
    """Labels, the board, the README join prompt and a one-time attribution request."""
    cfg = C.load(root)
    q = queue_from_env(cfg) if os.environ.get("GITHUB_ACTIONS") else Queue(GitHub(cfg["repo"] or _repo(root)), cfg)
    for line in q.setup():
        print(line)
    info = q.gh.repo_info()
    upstream = cfg["give_back"]["upstream"] or info.get("template")
    if write_files and render_join(root, q.gh.repo, info.get("default_branch") or cfg["default_branch"], upstream):
        print("README.md: join prompt updated for", q.gh.repo)
    if not info.get("template") and not q.gh.list_issues(labels=[L["learnings"]]):
        # An original Workstead repository receives other fleets' learnings.
        from .engine import LEARNINGS_INTRO
        q.gh.create_issue("Fleet learnings", LEARNINGS_INTRO + "\nNo reports yet.\n", [L["learnings"]])
        print("created the Fleet learnings issue")
    snap = q.sweep()
    boards = q.gh.list_issues(labels=[L["board"]])
    if boards and info.get("template"):
        b = boards[0]["number"]
        if not any(ATTRIBUTION_MARK in c["body"] for c in q.gh.list_comments(b)):
            q.gh.create_comment(b, attribution_text(upstream))
    print(f"board: {len(snap['tasks'])} open tasks")
    if not cfg["give_back"]["enabled"]:
        print("tip: set give_back.enabled to true in workstead.json to give 0.1% of fleet time back to Workstead (optional).")
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a") as f:
            f.write("### Workstead is set up\n\nLabels and the board are ready. Open a **Job** issue to start work, then share "
                    "the join prompt from the README.\n\n" + attribution_text(upstream).replace(ATTRIBUTION_MARK, "") + "\n")
    return 0


def _repo(root: Path) -> str:
    from .worker import detect_repo
    r = detect_repo(root)
    if not r:
        raise SystemExit("ws: can't tell which repository this is; set \"repo\" in workstead.json")
    return r


def submit_job(root: Path, title: str, body: str, priority: int) -> int:
    cfg = C.load(root)
    gh = GitHub(cfg["repo"] or _repo(root))
    meta = {"partition": "plan", "priority": priority, "origin": "job", "depth": 0}
    issue = gh.create_issue(title, body.strip() + "\n\n" + write_block("meta", meta) + "\n", [L["job"]])
    print(json.dumps({"status": "submitted", "job": issue["number"],
                      "message": "The queue admits it; a worker claims it and plans the work."}))
    return 0
