## Run the study locally

Write the Python script in your leased worktree. State the hypothesis, baseline, input source and version, and what result would disprove it. Use published or clearly labelled synthetic numerical data. Keep patient records, credentials and unpublished data out of the repository.

Set up once per machine with `python3 research/env.py doctor`, then `python3 research/env.py setup` (it installs the hash-locked tiers this machine can use into a venv shared by all your worktrees). Check the shared tools first: `./ws tools list` shows the vetted library in `tools/lib/` (Hill dose-response fits with bootstrap intervals, leave-one-group-out benchmarks against a baseline, batched tumour PK/PD sensitivity on CPU or GPU). Import or run one instead of rewriting it, and name it in your summary. If you write a helper other tracks could reuse, say so; a maintainer may promote it.

Use the agreed compute budget. A starter run should use the CPU and finish in five minutes. Run the script through `research/run.py` with explicit input, output and seed arguments. Commit the script, small shareable inputs or download instructions, result JSON, run receipt and a short account of what the result means. Include failed comparisons and missing data. Submit through `./ws submit NUMBER`.
