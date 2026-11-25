"""Fleet simulator: many agents against the real queue on a fake GitHub.

Agents choose work with the real worker code (``worker.pick``), speak the real
protocol (comments, heartbeat edits, pull requests) and the real queue
processes every event. Time is simulated in ticks. The simulator checks the
properties that matter at fleet scale:

* no task is ever worked by two agents at once (exclusive leases);
* no task is merged or completed twice (no duplicated work);
* dead agents' leases are recovered and their work requeued;
* the project finishes.

Run it: ``python3 tools/ws/ws.py sim --agents 200`` (or ``python3 -m
workstead.sim`` from tools/ws).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config as C
from . import worker as W
from .engine import Queue
from .fakegh import FakeGitHub, World
from .protocol import L, now_iso, read_block, write_block

BOT = "github-actions[bot]"
TICK = 300  # seconds of simulated time per tick


class Agent:
    def __init__(self, sim: Sim, login: str, node: str, trusted: bool, die_p: float):
        self.sim, self.login, self.node = sim, login, node
        self.gh = FakeGitHub(sim.w, login)
        self.ctx = W.Ctx(Path("."), repo=sim.w.repo, cfg=sim.cfg, gh=self.gh)
        self.ctx.node = lambda: self.node  # type: ignore[assignment]
        self.ctx._me = login
        self.trusted = trusted
        self.die_p = die_p
        self.dead = False
        self.phase = "idle"
        self.item: Optional[Dict[str, Any]] = None
        self.claim_id: Optional[int] = None
        self.until = 0.0
        self.last_beat = 0.0
        self.pr: Optional[int] = None
        self.done = 0
        self.lost = 0
        self.avoid: Dict[int, float] = {}
        self.submitted: Dict[int, int] = {}  # task -> claim comment, beaten until closed

    @property
    def now(self) -> float:
        return self.sim.w.clock()

    def step(self) -> None:
        if self.dead:
            return
        getattr(self, f"on_{self.phase}")()

    # idle: pick work and claim it
    def on_idle(self) -> None:
        if self.now - self.last_beat >= 1800:
            self.beat_submitted()
            self.last_beat = self.now
        if self.now < self.until:
            return
        choice, _ = W.pick(self.ctx, rng=self.sim.rng, avoid={n for n, t in self.avoid.items() if t > self.now})
        if not choice:
            self.until = self.now + self.sim.rng.choice([1, 2, 3]) * TICK
            return
        self.item = choice
        n = choice["number"]
        if choice["kind"] == "resume":
            self.resume(n)
            return
        # Like `ws claim`: check the live labels before posting a claim.
        live = self.sim.w.issues[n]["labels"]
        want = L["ready"] if choice["kind"] == "task" else None
        busy = choice["kind"] != "task" and bool((self.sim.state(n) or {}).get("review_lease"))
        if want and want not in live or busy:
            self.sim.stats["stale_skips"] += 1
            self.item = None
            return
        c = self.gh.create_comment(n, f"/claim node={self.node}")
        self.claim_id = c["id"]
        self.phase = "claiming"

    def resume(self, n: int) -> None:
        st = self.sim.state(n) or {}
        lease = st.get("lease") or st.get("review_lease") or {}
        self.claim_id = lease.get("comment")
        self.sim.believe(self, n)
        if self.item.get("review"):
            self.item = dict(self.item, kind="triage" if L["triage"] in self.sim.w.issues[n]["labels"] else "review")
            self.phase = "reviewing"
            self.until = self.now + 0.3 * 3600
            return
        self.start_work(n, rework=bool(st.get("pr")))

    def on_claiming(self) -> None:
        n = self.item["number"]
        st = self.sim.state(n) or {}
        if st.get("cursor", 0) < self.claim_id:
            return
        key = "review_lease" if self.item["kind"] in ("review", "triage") else "lease"
        if (st.get(key) or {}).get("comment") != self.claim_id:
            self.lost += 1
            self.avoid[n] = self.now + 3600
            self.sim.stats["claims_lost"] += 1
            self.phase, self.item = "idle", None
            return
        self.sim.believe(self, n)
        if self.item["kind"] in ("review", "triage"):
            self.phase = "reviewing"
            self.until = self.now + self.sim.rng.uniform(0.2, 1.0) * 3600
        else:
            self.start_work(n)

    def start_work(self, n: int, rework: bool = False) -> None:
        meta = read_block(self.sim.w.issues[n]["body"], "meta") or {}
        est = float(meta.get("est_hours", 1))
        self.phase = "working"
        self.pr = (self.sim.state(n) or {}).get("pr")
        self.until = self.now + est * self.sim.rng.uniform(0.4, 1.3) * 3600 * (0.4 if rework else 1)
        self.last_beat = self.now

    def maybe_die(self) -> bool:
        if self.sim.rng.random() < self.die_p:
            self.dead = True
            self.sim.stats["agents_died"] += 1
            if self.item:
                self.sim.disbelieve(self, self.item["number"])
            return True
        return False

    def on_working(self) -> None:
        n = self.item["number"]
        if self.maybe_die():
            return
        if self.now - self.last_beat >= 1800 and self.claim_id:
            self.gh.edit_comment(self.claim_id, f"/claim node={self.node}\n<!-- ws:beat {now_iso(self.now)} -->")
            self.beat_submitted()
            self.last_beat = self.now
        if self.now < self.until:
            return
        issue = self.sim.w.issues[n]
        st = self.sim.state(n) or {}
        if (st.get("lease") or {}).get("comment") != self.claim_id or st.get("status") != "running":
            self.sim.stats["work_lost_to_expiry"] += 1
            self.finish(n)
            return
        meta = read_block(issue["body"], "meta") or {}
        part = C.partition(self.sim.cfg, meta.get("partition", "code"))
        if part["deliver"] == "plan":
            self.gh.create_comment(n, "/plan\n```json\n" + json.dumps(self.sim.make_plan(meta)) + "\n```")
        elif part["deliver"] == "comment":
            self.gh.create_comment(n, "/done\nFindings: everything checked out.")
        else:
            if self.pr and self.sim.w.issues[self.pr]["state"] == "open":
                sha = f"{self.sim.rng.getrandbits(40):010x}"
                self.sim.w.checks[sha] = "failure" if self.sim.rng.random() < self.sim.ci_fail else "success"
                self.gh.push_pr(self.pr, sha)
            else:
                sha = f"{self.sim.rng.getrandbits(40):010x}"
                self.sim.w.checks[sha] = "failure" if self.sim.rng.random() < self.sim.ci_fail else "success"
                self.gh.open_pr(issue["title"], f"Closes #{n}\n\nDone.\n\n" + write_block("pr", {"task": n}),
                                f"ws/{n}-{self.login}", ["src/module.py"], sha=sha)
                self.sim.stats["prs_opened"] += 1
            self.submitted[n] = self.claim_id
        if self.sim.rng.random() < self.sim.found_p and meta.get("depth", 0) >= 1:
            self.gh.create_issue(f"Edge case discovered in {issue['title'][:40]} {self.sim.rng.getrandbits(24):x}",
                                 f"While working on #{n} I found an edge case worth its own task ({self.sim.rng.random()}).\n\n"
                                 + write_block("meta", {"origin": "found", "found_in": n, "partition": "code",
                                                        "est_hours": 0.5}), [L["proposed"]])
            self.sim.stats["found_filed"] += 1
        self.done += 1
        self.finish(n)

    def beat_submitted(self) -> None:
        """`ws beat` with no argument: every lease this agent still holds."""
        for t, cid in list(self.submitted.items()):
            if self.sim.w.issues[t]["state"] == "closed":
                del self.submitted[t]
            elif t != (self.item or {}).get("number"):
                self.gh.edit_comment(cid, f"/claim node={self.node}\n<!-- ws:beat {now_iso(self.now)} -->")

    def on_reviewing(self) -> None:
        n = self.item["number"]
        if self.maybe_die():
            return
        if self.now < self.until:
            return
        st = self.sim.state(n) or {}
        if (st.get("review_lease") or {}).get("comment") != self.claim_id:
            self.finish(n)
            return
        if self.item["kind"] == "triage":
            self.gh.create_comment(n, "/admit")
        elif self.sim.rng.random() < self.sim.reject_p:
            self.gh.create_comment(n, "/request-changes\nPlease handle the error path.")
        else:
            self.gh.create_comment(n, "/approve\nVerified against the acceptance criteria.")
        self.finish(n)

    def finish(self, n: int) -> None:
        self.sim.disbelieve(self, n)
        self.phase, self.item, self.claim_id, self.pr = "idle", None, None, None


class Sim:
    def __init__(self, agents: int = 50, accounts: Optional[int] = None, seed: int = 1, jobs: int = 2,
                 die_p: float = 0.002, ci_fail: float = 0.05, reject_p: float = 0.1, found_p: float = 0.03,
                 trusted_share: float = 0.4, sweep_every: int = 3, async_p: float = 0.3):
        os.environ.setdefault("WS_HOME", tempfile.mkdtemp(prefix="ws-sim-"))
        W.HOME = Path(os.environ["WS_HOME"])
        self.rng = random.Random(seed)
        self.cfg = C.load(data={"repo": "acme/project", "maintainers": ["boss"],
                                "leases": {"max_per_account": 50}})
        self.w = World()
        self.w.perms["boss"] = "admin"
        self.bot = FakeGitHub(self.w, BOT)
        self.ci_fail, self.reject_p, self.found_p, self.sweep_every = ci_fail, reject_p, found_p, sweep_every
        self.async_p = async_p
        accounts = accounts or max(1, agents * 2 // 3)
        self.agents: List[Agent] = []
        for i in range(agents):
            login = f"user{i % accounts}"
            trusted = (i % accounts) < accounts * trusted_share
            if trusted:
                self.w.merged_by_login[login] = 10
            self.agents.append(Agent(self, login, f"node{i}", trusted, die_p))
        self.holders: Dict[int, Agent] = {}
        self.stats = {k: 0 for k in ("claims_lost", "agents_died", "work_lost_to_expiry", "prs_opened",
                                     "found_filed", "stale_skips", "events", "ticks")}
        self.violations: List[str] = []
        self.jobs = [self.submit_job(j) for j in range(jobs)]

    def submit_job(self, j: int) -> int:
        boss = FakeGitHub(self.w, "boss")
        names = ["payments service", "search indexer", "mobile onboarding", "billing reports", "audit logging",
                 "image pipeline", "chat moderation", "data export"]
        i = boss.create_issue(f"Build the {names[j % len(names)]}", f"Deliver the {names[j % len(names)]} end to end, "
                              f"with tests and documentation ({j}).", [L["job"]])
        self.pump()
        return i["number"]

    def make_plan(self, meta: Dict[str, Any]) -> Dict[str, Any]:
        depth = meta.get("depth", 0)
        k = self.rng.randint(3, 7)
        tasks = []
        for i in range(k):
            part = self.rng.choice(["code", "code", "code", "docs", "research", "test"] + (["plan"] if depth == 0 else []))
            t = {"key": f"t{i}", "title": f"Step {i} of #{meta.get('job')} at depth {depth} ({self.rng.getrandbits(20):x})",
                 "partition": part, "est_hours": round(self.rng.uniform(0.3, 2.5), 1),
                 "body": "Do the step.", "acceptance": ["It works."]}
            if i and self.rng.random() < 0.4:
                t["deps"] = [f"t{self.rng.randrange(i)}"]
            if part != "plan" and self.rng.random() < 0.1:
                t["array"] = [f"part {x}" for x in range(self.rng.randint(2, 4))]
                t["title"] += " for {item}"
            tasks.append(t)
        return {"tasks": tasks}

    def state(self, n: int) -> Optional[Dict[str, Any]]:
        for cid in sorted(self.w.comments):
            c = self.w.comments[cid]
            if c["issue"] == n and c["author"] == BOT:
                st = read_block(c["body"], "state")
                if st is not None:
                    return st
        return None

    def believe(self, a: Agent, n: int) -> None:
        other = self.holders.get(n)
        if other is not None and other is not a and not other.dead:
            self.violations.append(f"#{n} held by {other.node} and {a.node} at once")
        self.holders[n] = a

    def disbelieve(self, a: Agent, n: int) -> None:
        if self.holders.get(n) is a:
            del self.holders[n]

    def pump(self) -> None:
        while self.w.events:
            name, payload = self.w.events.pop(0)
            Queue(self.bot, self.cfg, clock=self.w.clock).handle_event(name, payload)
            self.stats["max_events_per_tick"] = max(self.stats.get("max_events_per_tick", 0), len(self.w.events))
            self.stats["events"] += 1

    def check(self) -> None:
        merged: Dict[int, int] = {}
        for n, p in self.w.prs.items():
            if p["merged"]:
                t = None
                m = read_block(self.w.issues[n]["body"], "pr")
                t = m.get("task") if m else None
                merged[t] = merged.get(t, 0) + 1
        for t, k in merged.items():
            if k > 1:
                self.violations.append(f"#{t} merged {k} times")

    def finished(self) -> bool:
        return all(self.w.issues[j]["state"] == "closed" for j in self.jobs)

    def run(self, max_ticks: int = 3000) -> Dict[str, Any]:
        tick = 0
        while tick < max_ticks and not self.finished():
            tick += 1
            if tick % self.sweep_every == 1:
                Queue(self.bot, self.cfg, clock=self.w.clock).sweep()
                self.pump()
            order = list(self.agents)
            self.rng.shuffle(order)
            for a in order:
                a.step()
                # The queue answers in about 30 s, so it runs between agents
                # rather than once per 5-minute tick (agents are asynchronous).
                if self.rng.random() < self.async_p:
                    self.pump()
            self.pump()
            self.w.advance(TICK)
            if tick % 10 == 0:
                self.check()
        self.check()
        self.stats["ticks"] = tick
        tasks = [i for i, x in self.w.issues.items() if L["task"] in x["labels"] and not x["is_pr"]]
        done = [i for i in tasks if L["done"] in self.w.issues[i]["labels"]]
        held = [i for i in tasks if L["held"] in self.w.issues[i]["labels"]]
        return {"finished": self.finished(), "sim_hours": round(tick * TICK / 3600, 1), "tasks": len(tasks),
                "done": len(done), "held": len(held), "api_calls": self.w.calls,
                "api_calls_per_task": round(self.w.calls / max(1, len(done)), 1),
                "queue_calls_per_task": round(self.bot.calls / max(1, len(done)), 1),
                "agents": len(self.agents), **self.stats, "violations": self.violations[:10]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Simulate a fleet against the real queue.")
    ap.add_argument("--agents", type=int, default=100)
    ap.add_argument("--accounts", type=int)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--die", type=float, default=0.002, help="chance per tick that a working agent dies")
    ap.add_argument("--ticks", type=int, default=3000)
    a = ap.parse_args(argv)
    res = Sim(agents=a.agents, accounts=a.accounts, seed=a.seed, jobs=a.jobs, die_p=a.die).run(a.ticks)
    print(json.dumps(res, indent=1))
    return 0 if res["finished"] and not res["violations"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
