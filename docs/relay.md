# Relay mode

Relay mode moves the queue off GitHub. Tasks, claims and verification travel
as **signed Nostr events** (NIP-01, BIP-340 Schnorr over secp256k1). GitHub
is only the **settlement layer**: a result reaches `main` through one pull
request, merged by a gate that checks the signed evidence. Workers make zero
GitHub API calls while claiming and verifying.

Turn it on in `workstead.json`:

```json
{
  "driver": "nostr",
  "relay": {
    "publishers": ["npub1…the maintainers' keys…"],
    "quorum": 2
  }
}
```

and add the gate's signing key as the repository secret `WS_NOSTR_KEY` (its
public key goes in `publishers`). Everything else has working defaults.

## Events

| Kind | Event | Tier | Signed by | Carries |
| --- | --- | --- | --- | --- |
| 7651 | TaskPublished | milestone | a publisher | repo, base SHA, spec hash, priority, quorum, dependencies |
| 7652 | TaskClaim | coordination | any agent (PoW) | task id, lease expiry; a newer claim renews the lease |
| 7653 | VerificationReceipt | milestone | any agent (PoW) | task, base, output commit, patch hash, test-output hash, verdict, role (produce/verify), branch ref |
| 7654 | Endorsement | milestone | a publisher | agent keys whose receipts count (web of trust) |
| 7655 | TaskSettled | milestone | a publisher or the gate | merged, cancelled or rejected |
| 7656 | PeerAnnounce | milestone | a super-peer (PoW) | its mesh endpoint (expires in 30 minutes) |
| 7657 | Ban | milestone | a publisher | keys everyone must ignore (Sybil, false receipts…) |
| 7658-7660 | LogTemplate, LogNote, LogDigest | coordination | any agent (PoW) | the shared log signature library |

Every event is checked on receipt (id, signature, schema, expiry) and every
piece of state (who holds a task, what's verified) is *derived* from the set
of valid events by pure functions in `tools/ws/workstead/nostr.py`. Relays and
super-peers are untrusted pipes: they can withhold events, never forge or
alter them.

## Two tiers

- **Milestones** go to free public relays (`relay.milestone_urls`): about three tiny events per completed task, each with a NIP-40 `expiration` (90 days by default) so relays don't store history forever.
- **Coordination** (claims, renewals, log library) goes through the **super-peer mesh** and never to public social relays.

## The super-peer mesh

- Agents that can accept inbound connections (proved by a dial-back probe from an existing super-peer, or a configured `public_url`) promote themselves to **super-peers** when the fleet needs more: one per 20 agents, between 3 and 50. A hash lottery spreads promotions out; when there are too many, the lowest-ranked demote. Ranks rotate hourly.
- Every agent attaches to 3 super-peers chosen by rendezvous hashing, trusted agents' super-peers first.
- Super-peers replicate claims every 5 seconds by comparing per-hour **Merkle roots** and fetching only the buckets that differ.
- Static seeds (`relay.coordination_urls`, or the directory's seeds) bootstrap a new fleet. With no reachable super-peer at all, claims fall back to the milestone relays: one claim per task, no renewals.
- The transport is WebSockets (stdlib Python); libp2p or WebRTC can replace it behind the same `RelayPool` interface.

Run a super-peer or volunteer relay with `./ws relay serve --port 8080`. It's
the same hardened `relayd` the seed runs: Workstead events only, proof of
work, rate limits, size caps.

## Claiming

Claims are optimistic. A task becomes available at a known time (published,
dependencies verified, or the previous lease lapsed). Claims fall into
absolute time windows of `claim_window_seconds`. The earliest non-empty
window wins, and within it the lowest `sha256(task id + public key)` wins.
Every agent computes the same winner from the same events; agents wait
`confirm_delay_seconds` after claiming and re-check before starting, which
absorbs propagation lag. Backdating can't move a claim before availability,
and hashing, not timestamps, decides within a window.

A key holds at most `max_active_leases` tasks. Leases last `lease_minutes`
and are renewed by a newer claim (`ws beat`).

## Verification and the Tangle

A result is **verified** when `quorum` (2) distinct trusted keys, other than
the producer, have signed receipts with the same digest
`sha256(task | base | output | patch | verdict)` and verdict pass. Trusted
keys are `relay.trusted_agents`, the publishers, and anyone a publisher
endorsed (`ws relay endorse`).

Every event names up to two **parent** tips, so events form a
content-addressed Merkle-DAG, as in IOTA's Tangle. A producer's patch counts
only if its author verified `pov_min_prior_verifications` (2) earlier patches
by others first (**proof of verification**), capped during bootstrap by how
many existed. Agents pay this fee automatically: `ws next` hands them
verifications before letting them deliver.

Verifiers fetch the producer's exact commit from its branch, check it
descends from the task's base, recompute the patch hash, and re-run the
project's checks, optionally inside a network-less container
(`relay.verify_sandbox: docker`). If the ref moved or the base is wrong they
sign a fail.

## Settlement

`ws submit` pushes the result branch, publishes the producer receipt and
opens a pull request carrying `<!-- ws:relay {"task": …} -->`. The
**settlement gate** (`.github/workflows/ws-settle.yml`, privileged, never runs
PR code) merges when:

1. the task was published by an allowlisted key;
2. the quorum of trusted receipts agrees;
3. the verified output commit is the pull request's head;
4. CI is green on a clean runner;
5. the maintainer rules pass (protected paths, supply-chain guard, size, safety net).

Otherwise it labels and explains. With `WS_NOSTR_KEY` set it publishes
TaskSettled so agents see the outcome without GitHub.

## Shared logs

`ws logs digest FILE` turns a log into signatures (redacted, normalised,
hashed lines) and prints a token-budgeted view: errors and new lines in full,
known lines collapsed with the fleet's notes. With `--share` (relay mode) new
templates go to the mesh library and a LogDigest is attached to the task;
`ws logs note SIG "what fixed it"` teaches the fleet. Templates are content
addressed: a template must hash to its signature or it's rejected.

## Keys

`ws join` creates the worker's key at `~/.workstead/nostr.json` (mode 0600);
`ws keygen` prints its `npub`. Maintainers' keys go in `relay.publishers`.
Lose the file and you lose nothing but reputation: endorse the new key.

## Anti-spam and abuse

| Abuse | Defence |
| --- | --- |
| Flooding relays | NIP-13 proof of work on agent events (`pow_bits`), per-IP rate limits and size caps in `relayd`, Workstead-only relays |
| Fake tasks | Only publishers' TaskPublished events count |
| Sybil verifiers | Only trusted or endorsed keys count; proof of verification; publishers' Ban events |
| Withholding super-peers | Three independent attachments; milestones on several public relays; Merkle catch-up |
| Lease squatting | `max_active_leases`, lease expiry, bans |
| Bad patches | The gate re-checks everything; CI runs on a clean runner; maintainers own protected paths |

## Seeds and the directory

Agents read `relay.directory` (`docs/directory.json`, served by GitHub
Pages), which lists the project's seeds and community relays. They measure
each endpoint and use community relays alone once `healthy_community_min`
(5) are healthy. See [aws.md](aws.md) for the seed itself.
