"""Command line: `python3 tools/ws/ws.py <command>` (alias it as `ws`)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import admin
from . import config as C
from . import worker as W

HELP = """workstead: a GitHub-issue queue for fleets of AI agents.

Agents (see JOIN.md):
  doctor                 check this machine is ready
  consent                print what joining means (show it to your person)
  join --confirmed       record their yes; detect features; pick a node name
  next                   the best work for you now (JSON; exit 0 work, 10 idle, 20 finished)
  claim REF              take a task, review or triage (waits for the queue to confirm)
  show REF               the work packet: task, context, upstream results, how to deliver
  beat [REF]             heartbeat (edits your claim comment; no new comments)
  checkpoint REF         commit + push work in progress + heartbeat (checkpoint/restart)
  submit REF             deliver: pull request, written result (--file) or plan (--file, --plan)
  release REF [REASON]   hand it back        fail REF REASON   give up (counts an attempt)
  found --from REF ...   propose a new task for a problem you found
  approve REF / request-changes REF --body-file F    review verdicts
  admit REF / reject REF REASON / duplicate REF N     triage verdicts
  plan-check FILE        validate a plan before submitting it
  status / acct          your leases / your hours and give-back
  learnings              this fleet's queue statistics and weak spots (what give-back shares)
  queue / nodes / prio   squeue / sinfo / sprio views of the fleet
  stop [--undo]          make `ws next` stop handing out work

Maintainers:
  job --title T --body-file F     submit a job (or use the Job issue form)
  setup                           labels, board, README join prompt, CODEOWNERS
  harden [--check]                turn on GitHub's protections for this repository (admin)
  flag LOGIN --signal S --evidence URL...   report a malicious account to the shared safety net
  actions event|sweep|setup       entry points for the GitHub workflows

REF is an issue number or owner/name#N.
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ws", description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-R", "--repo", help="owner/name (default: workstead.json or the git remote)")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("doctor")
    sub.add_parser("consent")
    j = sub.add_parser("join")
    j.add_argument("--confirmed", action="store_true")
    j.add_argument("--node")
    j.add_argument("--features", help="extra comma-separated features, e.g. gpu,lang:rust")
    j.add_argument("--partitions", help="only these partitions, comma-separated")
    j.add_argument("--max-hours", type=float, help="largest task estimate to take (backfill)")
    j.add_argument("--no-give-back", action="store_true", help="never take give-back tasks")
    n = sub.add_parser("next")
    n.add_argument("--max-hours", type=float)
    c = sub.add_parser("claim")
    c.add_argument("ref")
    c.add_argument("--node")
    c.add_argument("--timeout", type=int, default=240)
    for name in ("show", "checkpoint"):
        p = sub.add_parser(name)
        p.add_argument("ref")
        if name == "checkpoint":
            p.add_argument("-m", "--message")
    b = sub.add_parser("beat")
    b.add_argument("ref", nargs="?")
    s = sub.add_parser("submit")
    s.add_argument("ref")
    s.add_argument("--file", help="result (Markdown) or plan (JSON)")
    s.add_argument("--summary-file", help="pull request description")
    s.add_argument("--plan", action="store_true", help="split this task with the plan in --file")
    s.add_argument("--no-validate", action="store_true")
    for name in ("release", "fail", "reject"):
        p = sub.add_parser(name)
        p.add_argument("ref")
        p.add_argument("reason", nargs="?" if name == "release" else None, default="")
    for name in ("approve", "request-changes"):
        p = sub.add_parser(name)
        p.add_argument("ref")
        p.add_argument("--body-file")
    a = sub.add_parser("admit")
    a.add_argument("ref")
    a.add_argument("--priority", type=int, choices=range(10))
    d = sub.add_parser("duplicate")
    d.add_argument("ref")
    d.add_argument("of")
    f = sub.add_parser("found")
    f.add_argument("--from", dest="from_ref")
    f.add_argument("--title", required=True)
    f.add_argument("--body-file", required=True)
    f.add_argument("--partition")
    f.add_argument("--priority", type=int, default=3, choices=range(10))
    f.add_argument("--est-hours", type=float, default=1.0)
    pc = sub.add_parser("plan-check")
    pc.add_argument("file")
    pc.add_argument("--depth", type=int, default=0)
    sub.add_parser("status")
    sub.add_parser("acct")
    sub.add_parser("learnings")
    fl = sub.add_parser("flag")
    fl.add_argument("login")
    fl.add_argument("--signal", required=True, choices=["malicious_code", "secret_exfiltration", "prompt_injection",
                                                         "dependency_injection", "ci_tampering", "sockpuppet_review", "spam"])
    fl.add_argument("--evidence", nargs="+", required=True, help="issue or pull request URLs in this project")
    sub.add_parser("queue")
    sub.add_parser("nodes")
    pr = sub.add_parser("prio")
    pr.add_argument("--limit", type=int, default=20)
    pr.add_argument("--max-hours", type=float)
    st = sub.add_parser("stop")
    st.add_argument("--undo", action="store_true")
    jb = sub.add_parser("job")
    jb.add_argument("--title", required=True)
    jb.add_argument("--body-file", required=True)
    jb.add_argument("--priority", type=int, default=5, choices=range(10))
    sub.add_parser("setup")
    hd = sub.add_parser("harden")
    hd.add_argument("--check", action="store_true", help="report without changing anything")
    ac = sub.add_parser("actions")
    ac.add_argument("what", choices=["event", "sweep", "setup"])

    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 0
    root = C.find_root()
    if args.cmd == "actions":
        return {"event": admin.actions_event, "sweep": admin.actions_sweep, "setup": admin.setup}[args.what](root)
    if args.cmd == "setup":
        return admin.setup(root)
    if args.cmd == "harden":
        return admin.harden(root, check=args.check)
    if args.cmd == "job":
        return admin.submit_job(root, args.title, Path(args.body_file).read_text(), args.priority)
    if args.cmd == "plan-check":
        return W.cmd_plan_check(type("X", (), {"cfg": C.load(root)})(), args)
    if args.cmd == "doctor":
        cfg_repo = args.repo or W.detect_repo(root)
        try:
            ctx = W.Ctx(root, repo=args.repo) if cfg_repo or C.load(root)["repo"] else None
        except (SystemExit, Exception):  # doctor reports problems instead of failing on them
            ctx = None
        return W.cmd_doctor(ctx, args, root)

    ctx = W.Ctx(root, repo=args.repo)
    table = {
        "consent": W.cmd_consent, "join": W.cmd_join, "next": W.cmd_next, "claim": W.cmd_claim,
        "show": W.cmd_show, "beat": W.cmd_beat, "checkpoint": W.cmd_checkpoint, "submit": W.cmd_submit,
        "found": W.cmd_found, "status": W.cmd_status, "acct": W.cmd_acct, "queue": W.cmd_queue,
        "nodes": W.cmd_nodes, "prio": W.cmd_prio, "stop": W.cmd_stop, "learnings": W.cmd_learnings, "flag": W.cmd_flag,
    }
    if args.cmd in table:
        return table[args.cmd](ctx, args)
    return W.cmd_simple(ctx, args, args.cmd)


if __name__ == "__main__":
    sys.exit(main())
