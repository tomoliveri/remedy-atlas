# Operators' guide

For maintainers running a fleet: setup, configuration, steering, and fixing
things.

## Setup

1. Create the repository from the template. The **Workstead setup** workflow runs on the first push. It creates the labels and the pinned board, and writes the repository's own join prompt into the README. If it didn't run (Actions off for new repositories), enable Actions and run it from the Actions tab.
2. Fill in `PROJECT.md` and set `validate.command` in `workstead.json`. Add any toolchain setup the command needs to `.github/workflows/ci.yml`.
3. Recommended repository settings:
   - **Branch protection** on the default branch: require the *CI* checks to pass. Don't require GitHub's own pull request reviews if `review.merge` is `fleet`, because fleet reviews are comments and the queue merges with the Actions token. Require them if you want a person to approve every merge (then set `review.merge: maintainer`).
   - *Settings → Actions → General → Workflow permissions:* "Read and write permissions" is not required (each workflow declares its own), but organisation policies must allow workflows to request `contents: write`, `issues: write`, `pull-requests: write` and `actions: write`.
   - **Private vulnerability reporting** on.
   - For a public repository, consider *Settings → Moderation* (interaction limits) if spam appears.
4. Open a Job and share the join prompt.

`./ws setup` does step 1 from your own machine, using your `gh` login.

## Configuration

`workstead.json` is merged over the defaults below. Unknown keys are errors, so
typos fail loudly. Keys starting with `$` are comments.

| Key | Default | Meaning |
| --- | --- | --- |
| `project.name` | `""` | Shown on the board and in the consent message (default: the repository name) |
| `project.charter` | `PROJECT.md` | The file every worker reads first |
| `repo` | `""` | `owner/name`; empty uses `GITHUB_REPOSITORY` or the git remote |
| `default_branch` | `main` | Branch tasks start from and pull requests target |
| `maintainers` | `[]` | Extra logins with maintainer rights (anyone with write access already has them) |
| `bots` | `["github-actions[bot]"]` | Logins whose comments are the queue's own. Add your App's `slug[bot]`, or set the `WS_BOT_LOGIN` variable |
| `trust.mode` | `auto` | `auto` (open when private, earned when public), `open`, or `earned` |
| `trust.trusted_after_merged` | `2` | Merged `ws:pr` pull requests that make an account trusted |
| `trust.allow` | `[]` | Logins trusted outright |
| `partitions.<name>` | see below | `deliver` (`pr`, `comment`, `plan`, `review`), `review` (bool), `max_hours`, `about` |
| `default_partition` | `code` | For tasks that don't name one |
| `leases.heartbeat_minutes` | `120` | Silence after which a lease ends |
| `leases.time_factor`, `leases.min_hours` | `3`, `1` | Time limit = clamp(factor × estimate, min, factor × partition `max_hours`) |
| `leases.max_per_account` | `8` | Concurrent task leases per GitHub account |
| `leases.max_attempts` | `3` | Requeues before a task is held |
| `scheduler.weights` | priority 1000, age 500, critical_path 100, fairshare 50, review 6000, rework 100000, affinity 3000 | Multifactor priority weights (affinity: give-back tasks on this fleet's weak spots) |
| `scheduler.age_cap_hours` | `72` | Age stops adding priority after this |
| `scheduler.top_k` | `8` | Herd spreading: preferred candidates within the best priority band |
| `plans.max_children` / `max_depth` / `max_tasks_per_job` | `60` / `4` / `600` | Plan limits |
| `plans.split_above_hours` | `4` | Tasks estimated above this are flagged for splitting |
| `review.approvals_required` | `1` | Fleet approvals per submission |
| `review.merge` | `fleet` | `fleet`: the queue merges; `maintainer`: labels `ws:ready-to-merge` |
| `review.merge_method` | `squash` | `merge`, `squash` or `rebase` |
| `review.require_checks` | `true` | Wait for green checks (and for at least one check to exist) |
| `review.max_rounds` | `5` | Rework rounds before the task is held |
| `review.protected_paths` | `.github/`, `tools/ws/`, `workstead.json`, `JOIN.md`, `AGENTS.md`, `CLAUDE.md`, `SECURITY.md` | Pull requests touching these need a maintainer's approval |
| `dedup.similarity` | `0.72` | Threshold for flagging proposals as possible duplicates |
| `validate.command`, `validate.timeout_minutes` | `""`, `30` | The check run by `ws submit` and by CI |
| `drain.expiries`, `drain.window_hours`, `drain.pause_hours` | `3`, `168`, `24` | Pause accounts whose leases keep expiring (0 turns it off) |
| `give_back.enabled` | `false` | Give `share` of fleet time to Workstead |
| `give_back.share` | `0.001` | 0.1%; at most 0.05 |
| `give_back.upstream` | `""` | `owner/name`; empty uses the template this repository came from |
| `give_back.min_owed_hours` | `0.5` | Owed time before a give-back task is served |
| `give_back.learnings` | `true` | Give-back turns also share this fleet's anonymous queue statistics upstream ([concepts](concepts.md#fleet-learnings)) |
| `board.title`, `board.branch` | `Workstead board`, `ws-board` | Board issue title and snapshot branch |
| `limits.result_chars`, `plan_chars`, `body_chars` | `60000`, `120000`, `20000` | Size limits |

Default partitions: `plan` (plan, 2 h), `code` (pull request, reviewed, 4 h),
`test` (pull request, reviewed, 4 h), `docs` (pull request, reviewed, 3 h),
`research` (written result, 3 h), plus the system partitions `review` and
`triage`. Add your own, for example:

```json
"partitions": { "design": { "deliver": "comment", "review": true, "max_hours": 2, "about": "UX proposals" } }
```

Repository **variables** (*Settings → Secrets and variables → Actions*):
`WS_APP_ID` and secret `WS_APP_PRIVATE_KEY` for a GitHub App token, and
`WS_BOT_LOGIN` for the App's bot login (for example `my-fleet[bot]`).

## Steering the fleet

| You want to… | Do |
| --- | --- |
| Start work | Open a Job, or `./ws job --title T --body-file F` |
| Add one task | The Task form (yours start at once), or a plan on an existing task |
| Make something urgent | `/priority 9` on it |
| Pause a task | `/hold reason`; resume with `/unhold` |
| Take a task back from a worker | `/requeue` |
| Stop a whole job | `/cancel reason` on the job (cascades to children) |
| See the queue | The board issue, or `./ws queue`, `./ws nodes`, `./ws prio` |
| See how the queue works for you | `./ws learnings`: rates, medians and this fleet's weak spots |
| Approve a protected change | `/approve` on the pull request |
| Merge by hand | Merge normally; the task completes through `Closes #N` |

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Claims never confirm (`ws claim` times out) | The *Workstead queue* workflow isn't running. Check the Actions tab: workflows enabled, organisation permissions allow the declared scopes. |
| Board never updates | Scheduled workflows are paused after 60 days without activity on public repositories, and schedules can lag. Run *Workstead sweep* by hand or push a commit. |
| Approved pull requests don't merge | CI hasn't reported (the queue never merges with no checks), checks failed, branch protection requires human reviews, or a protected path needs a maintainer `/approve`. The pull request's status comment says which. |
| Tasks stay `ws:pending` | A dependency is still open; the status comment lists them. If one was cancelled, the task becomes `ws:held`: fix the plan and `/unhold`. |
| Many `ws:held` tasks | Workers keep failing them: read the history in the status comment. Usually the task is unclear or impossible; edit or cancel it. |
| API rate limit errors in workflow logs | See [scaling.md](scaling.md): add a GitHub App token. |
| A label or state looks wrong | Wait for the next sweep (it repairs labels), or run *Workstead queue* by hand with the issue number and reason `refresh`. |

## Upgrading

Workstead lives in `tools/ws/`, `.github/workflows/ws-*.yml`, `JOIN.md` and
`docs/`. To upgrade, copy those from a newer template release in a pull
request. The protocol is versioned (`"v": 1` in every block); new versions
keep reading old blocks.
