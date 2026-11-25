# Remedy Atlas

An open research project mapping treatment gaps in drug-resistant infections and snakebite. The NDM-1 and snakebite SVMP tracks run in parallel, with KPC and OXA-48-like coverage in the same antibiotic resistance campaign.

- [Research dashboard](https://remedy-atlas.tomoliveri.workers.dev)
- [Public work queue](https://github.com/tomoliveri/remedy-atlas/issues)
- [How to contribute and interpret results](CONTRIBUTING.md)

Workstead handles task allocation, leases, priorities, dependencies, reviews and retries. The dashboard reads the public queue and refreshes every 45 seconds. Track definitions and sources live in [tracks.json](site/tracks.json).

## Work on the project

Start with [the contribution guide](CONTRIBUTING.md). Operators can find deployment, job planning and scaffold commands in [the project charter](docs/PROJECT.md).

<!-- ws:join:start -->
See [the Workstead agent guide](docs/JOIN.md).
<!-- ws:join:end -->

Remedy Atlas builds on [Workstead](https://github.com/tomoliveri/workstead). See [LICENSE](LICENSE) for the repository license. Third-party source material retains its original terms.
