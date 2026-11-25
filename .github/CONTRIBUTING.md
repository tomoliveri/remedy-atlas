# Contribute to Remedy Atlas

1. Browse the [public queue](https://github.com/tomoliveri/remedy-atlas/issues). Pick work marked `ws:ready`, or use the [task form](https://github.com/tomoliveri/remedy-atlas/issues/new/choose) to propose a new evidence question.
2. Clone the repo, sign in to the GitHub CLI, and run `./ws claim NUMBER --node PUBLIC_ALIAS`. Pick a public alias for your worker. Workstead confirms the lease and creates a worktree where needed. Run `./ws show NUMBER` to see the acceptance criteria. For an automated worker, follow [the agent guide](../docs/JOIN.md).
3. Run the scaffold command from the task. Record its revision and work in the leased worktree. Cite dated primary sources, include the population and endpoint, and disclose conflicts, uncertainty and limitations. Use public datasets and publish aggregate data.
4. Submit a written result with `./ws submit NUMBER --file result.md` or code and data changes with `./ws submit NUMBER`. Use `./ws release NUMBER no_time` to return a lease you cannot finish. For independent review, follow the steps in [the Workstead guide](../docs/JOIN.md#review).
5. Check the linked issue for review feedback. Maintainers approve publication changes and resolve discrepancies. Corrections should link to the original finding and explain the change.

## Interpreting a finding

- A literature review establishes what was reported and where the gaps lie. A computational prediction is a hypothesis. A preclinical result requires independent replication. A patient benefit claim needs clinical evidence against relevant current care.
- A clinical finding may justify a follow-up study or referral to a qualified partner. Treatment and procurement decisions remain with clinicians and health authorities. Credit original sources and contributors and flag any limits on redistribution.
- Estimate annual deaths averted by multiplying baseline deaths by the fraction eligible, achievable treatment reach and incremental relative mortality reduction versus current care. Use comparable populations, dates and geographies. Report the sources, separate uncertainty in each input, and deduplicate patients across overlapping tracks. Leave the impact unestimated when inputs are missing.

## Open findings

Publish original findings you have rights to share under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Code uses the repository’s [MIT license](../LICENSE). See the [open research commitment](../docs/open-research.md).
