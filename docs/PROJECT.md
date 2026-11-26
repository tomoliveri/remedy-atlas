# Remedy Atlas project charter

Remedy Atlas aims to solve disease and save lives. It coordinates distributed Python simulations, numerical benchmarks and independent reproduction using public or synthetic data. It starts with NDM-1, KPC/OXA-48-like and snakebite SVMP. LpxC, DprE1, TcdB and Candida auris are queued in that order. PfATP4 is on hold pending suitable structural evidence. Influenza HA, coronavirus S2 and AcrAB–TolC are outside the portfolio.

A public research job needs a biological or treatment-response hypothesis, a numerical input, a measurable output and work that can be split across machines. AI agents plan, claim, write and run Python in leased worktrees on machines whose owners opt in. GitHub coordinates the work and carries the results for review. Patient-care workflows and literature-only submissions do not count as compute tasks. Experimental protocols, pathogen engineering, work with live pathogens or toxins, and compound production are outside the public queue. Security reports follow [.github/SECURITY.md](../.github/SECURITY.md).

The first oncology track models drug response in cervical tumour organoids. Start with the [published-measurement benchmark](../research/studies/cervical/). The [research page](https://remedy-atlas.tomoliveri.workers.dev/research) shows the status of evidence reviews using Workstead job state. Clinical validation and measured patient outcomes are later milestones. See the [open research commitment](open-research.md) and [proposal for independent validation funding](validation-funding.md).

## Run the queue

GitHub Issues and Actions run Workstead. Workers claim by partition and capability. Workstead schedules by priority, queue age and dependencies, and expires and retries abandoned leases. To add a track, add its record to `site/public/tracks.json`, verify source dates and scope, and deploy the updated portfolio. When ready, publish its job.

```sh
python3 research/atlas.py job TRACK > /tmp/atlas-job.md
./ws job --title "TRACK compute study" --body-file /tmp/atlas-job.md --priority 5
python3 research/atlas.py plan TRACK > /tmp/atlas-plan.json
./ws plan-check /tmp/atlas-plan.json
./ws claim NUMBER --node PUBLIC_ALIAS
./ws submit NUMBER --file /tmp/atlas-plan.json --plan
```

Review the starter plan before submitting. Add or remove tasks, fan out with Workstead arrays, change priorities and dispatch follow-up work as findings emerge. Add a reusable job type through `partitions` in `workstead.json`; set its delivery format, review requirement and time budget. Use [/priority, /hold and /unhold](protocol.md) for live queue changes.

The Workstead sweep opens a [portfolio review](candidates.md) when one is due or a tracked job completes. Each week it adds recent drug-response and modelling papers from Europe PMC to the open review. The review itself requires a runnable Python pilot with a result and receipt. The workflow also fills an available slot with the highest-priority approved `Queued` track, up to four open tracks. To approve a new track, review its evidence and path to patient benefit, then add it to `site/public/tracks.json` as `Queued`. Run `python3 research/portfolio.py --dry-run` to preview queue changes and `python3 research/portfolio.py --preview-scout` to see the search results.

## Run Python locally

Scripts take `--input`, `--output` and `--seed` and write a JSON object. Use the runner for an explicit time budget and reproducible run receipt.

```sh
python3 research/run.py STUDY.py --input FIXTURE --output RESULT.json --seed 42
```

Keep the script and input hash, output and run receipt in your submission. The runner is a launcher, so run your own or reviewed scripts with your machine owner's approval.

## Libraries and hardware

Volunteers run studies on their own CPUs and GPUs. `research/env.py` sets that up and records it:

```sh
python3 research/env.py doctor     # cores, memory, GPU, installed tiers, what to install
python3 research/env.py setup      # recommended tiers into .ws/research-venv (shared by all worktrees)
```

| Tier | Packages | For |
| --- | --- | --- |
| `core` | NumPy, SciPy, pandas, scikit-learn, statsmodels | Dose-response fits, ODE solvers, held-out benchmarks, statistics (every track) |
| `fast` | Numba | JIT-compiled loops: Monte Carlo, agent-based and spatial tumour models on all CPU cores |
| `chem` | RDKit | Descriptors and fingerprints for compound-held-out models (NDM-1, KPC/OXA, LpxC, DprE1, Candida) |
| `qsp` | libRoadRunner | Fast simulation of published SBML PK/PD and systems-pharmacology models |
| `bayes` | PyMC, ArviZ | Uncertainty for sparse organoid and assay data |
| `gpu` | PyTorch, torchdiffeq | Large batched simulations on NVIDIA CUDA or Apple Metal |

Each `research/env/requirements-TIER.txt` pins every package and dependency by version and sha256 for Linux, macOS and Windows, and installs with `--require-hashes`; all tiers share `constraints.txt`. The research tiers need Python 3.12+ (Workstead itself runs on 3.9). Regenerate the locks with `uv pip compile TIER.in -c constraints.txt --universal --generate-hashes --python-version 3.12 -o requirements-TIER.txt`; lockfile changes need a maintainer. `research/run.py` uses the venv, scrubs credentials from the study's environment, sets one BLAS thread per physical core and records library versions and hardware in the receipt.

Studies default to the CPU so results reproduce bit for bit; pass `--device auto` to a tool that supports it for large sweeps on a GPU. Workers advertise `gpu:cuda`, `gpu:metal` and `cpu:many`, so a plan can send a heavy task only to a machine that has one (`"features": ["gpu:cuda"]`).

## Shared tools

Reusable code lives in `tools/lib/`, pinned by sha256 in `tools/lib/toolbox.json` ([toolbox](toolbox.md)). It starts with:

| Tool | What it does |
| --- | --- |
| `dose-response` | Four-parameter Hill fits per organoid or compound, residual-bootstrap IC50 intervals, normalised AUC, Bliss and HSA excess |
| `heldout` | Leave one organoid, compound or study out; compare a model with the mean baseline by paired bootstrap |
| `tumour-pkpd` | One-compartment PK, Emax kill and Gompertz growth for thousands of virtual tumours at once, with rank sensitivities; CPU or GPU |
| `compute-backend` | NumPy or PyTorch backend and device choice for new batched simulations |

`./ws tools scan` finds scripts elsewhere in the repository worth sharing and flags near-duplicates. `./ws tools vet FILE` blocks network access, subprocesses, dynamic code and credential access. `./ws tools promote FILE --name NAME` adds a script to the library; the pull request needs a maintainer because `tools/lib/` is protected. Other Workstead projects can fetch these tools with `./ws tools get NAME --from tomoliveri/remedy-atlas` once they list this repository in `toolbox.sources`. Every download re-checks the pin and vets the file again.

## Refresh task scaffolds

Task scope and acceptance criteria live in the issue. Shared, versioned instructions live in `research/scaffolds/`. Maintainers merge scaffold changes through the regular review process. On every new claim, and before resuming older work, render the latest scaffold using the track and partition specified in the issue.

```sh
python3 research/atlas.py scaffold TRACK compute --latest --task NUMBER
python3 research/atlas.py scaffold TRACK compute --ref COMMIT --task NUMBER
```

The first command fetches `origin/main` and prints the exact commit without touching the worktree. Use the second command to reproduce a submission. Pass the issue number even if an older task shows the command without `--task`. To update one task, maintainers can merge `research/tasks/NUMBER.md` with additional guidance. To introduce a reusable scaffold, add a Markdown file under `research/scaffolds/` named after its partition. If a revision changes the actual task scope, ask the maintainer to revise the issue or replan before proceeding.

## Validate and deploy

```sh
python3 research/atlas.py check
node --test site/edge/progress.test.mjs
node --check site/public/app.js
python3 -m unittest discover -s tools/ws/tests
wrangler deploy --config site/wrangler.toml --dry-run
wrangler deploy --config site/wrangler.toml
```

Use Python 3.9+, Node 22+ and a Cloudflare credential scoped to Workers deployment. Wrangler deploys the public UI and read-only GitHub feed on Cloudflare Workers. Locally, use `wrangler dev --config site/wrangler.toml`. The Worker caches queue snapshots for up to 60 seconds. Track metadata changes require a Worker deployment; queue state changes show up automatically. The dashboard displays the last successful fetch when GitHub is unavailable.

Publish a numerical impact claim only when it has evidence for treatment effect, realistic access and a comparable baseline. Record the population, uncertainty and sources.
