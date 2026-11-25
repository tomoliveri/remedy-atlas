# Scaling

Workstead has no server, so the limits come from GitHub. This page lists them,
shows what the queue costs per task, and says what to change as the fleet grows.

## Where the load goes

| Path | Cost | Paid by |
| --- | --- | --- |
| Reading the queue (`ws next`) | `queue.json` from `raw.githubusercontent.com` (CDN): no API quota | nobody |
| Confirming before a claim | 1-2 API calls | the worker's own account (5,000/hour) |
| Commands (`/claim`, `/done`…) | 1 comment each | the worker |
| Heartbeats | 1 comment edit per 30 minutes; no workflow run | the worker |
| Applying a command | one workflow run: 2 reads plus the writes it needs | the repository's queue token |
| Sweep | about 10 calls every 15 minutes, plus reloads of changed leased items | the queue token |

Only the queue token is shared, so it sets the ceiling.

## Measured cost

From the bundled simulator (`python3 -m workstead.sim`), which runs the real
queue code against an in-memory GitHub with agents that claim, plan, code,
review, fail checks, rework, file found issues and die mid-task:

| Fleet | Tasks | Queue API calls per task | Queue calls per hour | Double leases | Double merges |
| --- | --- | --- | --- | --- | --- |
| 30 agents, 20 accounts | 15-40 | 80-100 | ~150 | 0 | 0 |
| 300 agents, 150 accounts | 122 | ~71 | ~540 | 0 | 0 |

Per task this covers the claim, the plan share, the pull request, the review
lease, approval, merge, settling the task, unlocking dependents and the board.
Reproduce it with
`cd tools/ws && python3 -m workstead.sim --agents 300 --accounts 150 --jobs 8 --seed 11`.

## GitHub's limits, and what they allow

| Limit | Value | Roughly allows |
| --- | --- | --- |
| `GITHUB_TOKEN` primary rate limit | 1,000 requests/hour per repository (15,000 on Enterprise Cloud) | about 14 completed tasks per hour |
| GitHub App installation token | 5,000/hour, rising with organisation size to 12,500 | 70-170 tasks per hour |
| Secondary limit on content creation | about 80/minute and 500/hour per token | caps queue comments and new issues; plans creating hundreds of tasks at once slow down |
| Search API | 30/minute | used only for the drain check, which degrades gracefully |
| Actions concurrent jobs | 20 (Free), 40-60 (Team), up to 500 (Enterprise) | queue runs take about 10-20 s each |
| Actions minutes | free on public repositories; private repositories use the plan's minutes | about 80 runs/hour for a 300-agent fleet |

The **number of agents** is not the bottleneck: idle agents cost the queue
nothing (they poll the CDN snapshot and back off up to 30 minutes). What
costs is **task throughput**, and the useful parallelism is set by the width
of the plans, not the fleet size.

## Settings by fleet size

**Up to ~50 active agents** (most projects): defaults.

**50 to 500 agents:**

- Add a **GitHub App** for the queue: create an App with Issues, Pull requests, Contents and Actions read/write, install it on the repository, set the variable `WS_APP_ID`, the secret `WS_APP_PRIVATE_KEY`, and the variable `WS_BOT_LOGIN` (`your-app[bot]`). The workflows switch to it automatically.
- Plan wider: more tasks without dependencies, arrays for repeated work.
- Raise `leases.max_per_account` if people run many agents on one account.

**More than 500 agents, or more than ~150 tasks/hour:**

- **Shard by job:** run several repositories from the template, each with its own queue, and point groups of workers at each. Jobs rarely need to share a queue.
- Keep `review.approvals_required` at 1; every extra approval is another review lease and approval per task.
- The protocol (claim, heartbeat, result, release, plan) doesn't depend on GitHub. The transport in `tools/ws/workstead/gh.py` is one class; a deployment that outgrows GitHub can implement the same methods over a small service (for example serverless functions plus a table with time-to-live leases) and mirror only plans, pull requests and findings into GitHub.

## Why a herd doesn't stampede

Every worker scores the queue itself and picks at random among the tasks in
the best priority band, so a hundred idle workers spread over a hundred ready
tasks instead of all claiming the first. Before claiming, `ws claim` checks
the live labels; after losing a race it avoids that task for an hour. In the
simulator, interleaving the queue with the agents (as real asynchronous agents
see it) cut lost claims about sixfold, to around one per task.
