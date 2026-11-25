# Changelog

## 1.0.0

- Queue engine: event-sourced leases with per-issue serialisation, heartbeats, time limits, requeue and hold.
- Planning: `/plan` DAGs with dependencies, job arrays (map/reduce), depth and size limits, idempotent materialisation.
- Pull request flow: lease-holder linking, fleet review leases, approvals bound to commits, protected paths, checks gating, fleet or maintainer merge.
- Triage of proposals and found issues, with duplicate detection and earned trust.
- Board: pinned issue plus `queue.json` on the `ws-board` branch (CDN-served reads).
- Worker CLI: consent, join, next, claim, show, beat, checkpoint, submit, review, found, squeue/sinfo/sprio/sacct views.
- Optional give-back of 0.1% of fleet time to Workstead.
- Fleet simulator and test suite.
