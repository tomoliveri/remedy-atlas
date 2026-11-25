# Remedy Atlas project charter

Remedy Atlas coordinates public evidence reviews, reproducibility checks on published aggregate data and transparent impact modelling. It starts with NDM-1, KPC/OXA-48-like and snakebite SVMP. LpxC, DprE1, TcdB and Candida auris are queued in that order. PfATP4 is on hold pending suitable structural evidence. Influenza HA, coronavirus S2 and AcrAB–TolC are outside the portfolio.

Public jobs cover research synthesis and clinical or epidemiological questions. Experimental protocols, pathogen engineering, work with live pathogens or toxins, and compound production are outside the public queue. Security reports follow [.github/SECURITY.md](../.github/SECURITY.md).

## Run the queue

GitHub Issues and Actions run Workstead. Workers claim by partition and capability. Workstead schedules by priority, queue age and dependencies, and expires and retries abandoned leases. To add a track, add its record to `site/tracks.json`, verify source dates and scope, and deploy the updated portfolio. When ready, publish its job.

```sh
python3 research/atlas.py job TRACK > /tmp/atlas-job.md
./ws job --title "TRACK evidence review" --body-file /tmp/atlas-job.md --priority 5
python3 research/atlas.py plan TRACK > /tmp/atlas-plan.json
./ws plan-check /tmp/atlas-plan.json
./ws claim NUMBER
./ws submit NUMBER --file /tmp/atlas-plan.json --plan
```

Review the starter plan before submitting. Add or remove tasks, fan out with Workstead arrays, change priorities and dispatch follow-up work as findings emerge. Add a reusable job type through `partitions` in `workstead.json`; set its delivery format, review requirement and time budget. Use [/priority, /hold and /unhold](protocol.md) for live queue changes.

## Refresh task scaffolds

Task scope and acceptance criteria live in the issue. Shared, versioned instructions live in `research/scaffolds/`. Maintainers merge scaffold changes through the regular review process. On every new claim, and before resuming older work, render the latest scaffold using the track and partition specified in the issue.

```sh
python3 research/atlas.py scaffold TRACK evidence --latest
python3 research/atlas.py scaffold TRACK evidence --ref COMMIT
```

The first command fetches `origin/main` and prints the exact commit without touching the worktree. Use the second command to reproduce a submission. If a revision changes the actual task scope, ask the maintainer to revise the issue or replan before proceeding.

## Validate and deploy

```sh
python3 research/atlas.py check
node --test edge/progress.test.mjs
node --check site/app.js
python3 -m unittest discover -s tools/ws/tests
wrangler deploy --dry-run
wrangler deploy
```

Use Python 3.9+, Node 22+ and a Cloudflare credential scoped to Workers deployment. Wrangler deploys the public UI and read-only GitHub feed on Cloudflare Workers. Locally, use `wrangler dev`. The Worker caches queue snapshots for up to 60 seconds. Track metadata changes require a Worker deployment; queue state changes show up automatically. The dashboard displays the last successful fetch when GitHub is unavailable.
