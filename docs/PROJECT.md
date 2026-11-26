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

Keep the script and input hash, output and run receipt in your submission. The runner runs the script in the sandbox, never on your machine.

## Libraries, hardware and the sandbox

Volunteers run studies on their own machines, but never directly on them: every study, shared tool and check runs in Workstead's [sandbox](sandbox.md).

```sh
python3 research/env.py doctor     # cores, memory, GPUs, and which sandbox backends are ready
python3 research/env.py setup      # fetch Pyodide (hash-checked) and build the project's container image
```

- **WebAssembly first.** Studies that need only the standard library, NumPy, SciPy, pandas, scikit-learn or statsmodels run in Pyodide inside Deno: offline, with no network or access to your files, reading `/input` and writing `/output`, under hard memory and time limits. The cervical starter runs this way in about a second and reproduces its baseline exactly.
- **A rootless container for the rest.** RDKit, Numba, libRoadRunner and the project's checks (git, node, the research tests) run in an image built from `research/env/Dockerfile`, with no network, a read-only root filesystem, no capabilities and an unprivileged user. The image installs the hash-locked tiers below with `--require-hashes`.

| Tier | Packages | For | Where |
| --- | --- | --- | --- |
| `core` | NumPy, SciPy, pandas, scikit-learn, statsmodels | Dose-response fits, ODE solvers, held-out benchmarks, statistics (every track) | WebAssembly and the image |
| `fast` | Numba | JIT-compiled loops: Monte Carlo, agent-based and spatial tumour models | image |
| `chem` | RDKit | Descriptors and fingerprints for compound-held-out models (NDM-1, KPC/OXA, LpxC, DprE1, Candida) | image |
| `qsp` | libRoadRunner | Simulation of published SBML PK/PD and systems-pharmacology models | image (x86-64 only: no Linux ARM wheels) |
| `bayes` | PyMC, ArviZ | Uncertainty for sparse organoid and assay data | add to the image when a track needs it |
| `gpu` | PyTorch, torchdiffeq | Large batched simulations | add to the image; NVIDIA GPUs on Linux with `sandbox.gpus` |

Each `research/env/requirements-TIER.txt` pins every package and dependency by version and sha256; all tiers share `constraints.txt`. Regenerate the locks with `uv pip compile TIER.in -c constraints.txt --universal --generate-hashes --python-version 3.12 -o requirements-TIER.txt`; lockfile and Dockerfile changes need a maintainer. `research/run.py` records the sandbox backend, limits, peak memory and this machine's hardware in every receipt.

Studies default to the CPU so results reproduce bit for bit. Apple GPUs can't be reached from a sandbox, so GPU sweeps belong on Linux machines with NVIDIA cards; workers advertise `gpu:cuda`, `sandbox:wasm` and `sandbox:container`, so a plan can send a task only to a machine that can run it (`"features": ["gpu:cuda", "sandbox:container"]`).

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
