## Run the study locally

Write the study code in your leased worktree. State the hypothesis, baseline, input source and version, and what result would disprove it. Use published or clearly labelled synthetic numerical data. Keep patient records, credentials and unpublished data out of the repository.

Use the [local compute budget](../../docs/compute-budget.md). Start with a short CPU reference run. Add native code or GPU acceleration only when the benchmark supports it and the volunteer opts in. Run the study through `research/run.py` with explicit input, output and seed arguments. Commit the script, small shareable inputs or download instructions, result JSON, run receipt and a short account of what the result means. Include failed comparisons and missing data. Submit through `./ws submit NUMBER`.
