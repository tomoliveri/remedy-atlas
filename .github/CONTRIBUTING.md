# Contribute a computation

1. Read [the charter](../docs/PROJECT.md). Start with a [ready compute or replication task](https://github.com/tomoliveri/remedy-atlas/issues?q=is%3Aissue+is%3Aopen+label%3Aws%3Aready) or propose a question with a public numerical dataset and a result someone can check.
2. Clone the repository, sign in to GitHub CLI and run `./ws claim NUMBER --node PUBLIC_ALIAS`. Work in the leased worktree and run `./ws show NUMBER` for the requirements. AI workers can follow [the join guide](../docs/JOIN.md).
3. Write the Python study. Pick a baseline, input version, seed and stopping condition. Run it locally through `research/run.py`. Keep a starter CPU run to five minutes unless the machine’s owner approves a larger budget. Only run code you wrote or have reviewed.
4. Commit the script, the input source or small shareable fixture, the result JSON, and the run receipt with hashes. Include negative results and uncertainty. Run the project checks, then use `./ws submit NUMBER` to open a pull request.
5. Independent reviewers rerun the result. Use `./ws release NUMBER no_time` if you need to return the task.

Try the [cervical tumour-response study](../research/studies/cervical/) to see what a small run looks like. A simulation can help decide what to test next. Independent biological and clinical validation is needed to establish a treatment effect.

Publish original findings you have rights to share under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Code uses the [MIT license](../LICENSE). See the [open research commitment](../docs/open-research.md).
