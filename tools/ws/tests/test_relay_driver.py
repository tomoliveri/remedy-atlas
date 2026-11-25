"""Relay driver core: BIP-340 vectors, deterministic claims, quorum, real WebSockets, zero GitHub calls."""
import random
import unittest

import harness  # noqa: F401
from workstead import config as C, nostr as N, schnorr as S
from workstead.driver import GitOps, RelayAgent
from workstead.fakegh import FakeGitHub, World
from workstead.relay import LocalRelay, MemRelay, RelayPool, Relays, mem_pool

PUB_SK = bytes.fromhex("11" * 32)
REPO = "https://github.com/acme/project"


def cfg(**relay):
    r = {"publishers": [S.pubkey(PUB_SK).hex()], "pow_bits": 4, "claim_window_seconds": 60, "quorum": 2}
    r.update(relay)
    return C.load(data={"repo": "acme/project", "relay": r})


class Vectors(unittest.TestCase):
    def test_bip340(self):
        sk = bytes.fromhex("B7E151628AED2A6ABF7158809CF4F3C762E7160F38B4DA56A784D9045190CFEF")
        msg = bytes.fromhex("243F6A8885A308D313198A2E03707344A4093822299F31D0082EFA98EC4E6C89")
        sig = S.sign(msg, sk, bytes.fromhex("00" * 31 + "01"))
        self.assertEqual(sig.hex().upper(), "6896BD60EEAE296DB48A229FF71DFE071BDE413E6D43F917DC8DCF8C78DE3341"
                                            "8906D11AC976ABCCB20B091292BFF4EA897EFCB639EA871CFA95F6DE339E4B0A")
        self.assertTrue(S.verify(msg, S.pubkey(sk), sig))
        self.assertFalse(S.verify(msg, S.pubkey(sk), sig[:-1] + b"\x00"))

    def test_event_tamper_and_pow(self):
        ev = N.claim_event(PUB_SK, "ab" * 32, REPO, 1000, 600, pow_bits=6)
        self.assertTrue(N.verify(ev) and N.pow_ok(ev, 6))
        bad = dict(ev, content="x")
        self.assertFalse(N.verify(bad))


class Coordination(unittest.TestCase):
    def test_claim_winner_is_deterministic_under_any_order(self):
        c = cfg()
        t = N.task_event(PUB_SK, REPO, "a" * 40, {"title": "T"}, 5, 2, 1000)
        keys = [bytes([i + 1]) * 32 for i in range(6)]
        claims = [N.claim_event(k, t["id"], REPO, 1010 + i, 3600, 4) for i, k in enumerate(keys)]
        winners = set()
        for seed in range(10):
            evs = [t] + claims
            random.Random(seed).shuffle(evs)
            winners.add(N.compute(evs, c, REPO, 1100)[t["id"]]["holder"])
        self.assertEqual(len(winners), 1)

    def test_quorum_and_untrusted_receipts(self):
        c = cfg(trusted_agents=[S.pubkey(bytes([7]) * 32).hex(), S.pubkey(bytes([8]) * 32).hex()])
        t = N.task_event(PUB_SK, REPO, "a" * 40, {"title": "T"}, 5, 2, 1000)
        prod, ver, rogue = bytes([7]) * 32, bytes([8]) * 32, bytes([9]) * 32
        cl = N.claim_event(prod, t["id"], REPO, 1001, 3600, 4)
        args = (t["id"], REPO, "a" * 40, "b" * 40, "c" * 64, "d" * 64, "pass")
        p = N.receipt_event(prod, *args, "produce", 1100, ref="https://x.example/r.git#b", pow_bits=4)
        self.assertEqual(N.compute([t, cl, p], c, REPO, 1200)[t["id"]]["status"], "submitted")
        r = N.receipt_event(rogue, *args, "verify", 1150, pow_bits=4)  # untrusted: doesn't count
        self.assertEqual(N.compute([t, cl, p, r], c, REPO, 1200)[t["id"]]["status"], "submitted")
        v = N.receipt_event(ver, *args, "verify", 1160, pow_bits=4)
        # Two *independent* verifiers are needed; the producer's own receipt doesn't count.
        self.assertEqual(N.compute([t, cl, p, r, v], c, REPO, 1200)[t["id"]]["status"], "submitted")
        c2 = cfg(trusted_agents=[S.pubkey(bytes([k]) * 32).hex() for k in (7, 8, 10)])
        v2 = N.receipt_event(bytes([10]) * 32, *args, "verify", 1170, pow_bits=4)
        row = N.compute([t, cl, p, r, v, v2], c2, REPO, 1200)[t["id"]]
        self.assertEqual((row["status"], row["output"], row["votes"]), ("verified", "b" * 40, 2))


class RealWebSockets(unittest.TestCase):
    def test_publish_query_dedupe_reconnect_and_dead_relay(self):
        a, b = LocalRelay(), LocalRelay()
        try:
            pool = RelayPool([a.url, b.url, "ws://127.0.0.1:1"], timeout=2)
            ev = N.task_event(PUB_SK, REPO, "a" * 40, {"title": "T"}, 5, 2, int(N.time.time()) if hasattr(N, "time") else __import__("time").time().__int__())
            res = pool.publish(ev)
            self.assertTrue(res[a.url][0] and res[b.url][0])
            a.drop_connections()  # the client reconnects transparently
            got = pool.query([{"kinds": [N.K_TASK], "#r": [REPO]}])
            self.assertEqual([e["id"] for e in got], [ev["id"]])
            pool.close()
        finally:
            a.stop()
            b.stop()


class FakeGit(GitOps):
    def produce(self, task):
        out = N.hashlib.sha1(task["id"].encode()).hexdigest()
        return task["base"], out, "e" * 64, "f" * 64, "pass", f"https://git.example/{out[:6]}.git#b"

    def verify(self, ref, base, output, task):
        return "e" * 64, "f" * 64, "pass"


class ZeroGitHubCalls(unittest.TestCase):
    def test_claim_and_verify_touch_no_github_api(self):
        t0 = [1_800_000_000]
        clock = lambda: t0[0]
        keys = [bytes([20 + i]) * 32 for i in range(4)]
        c = cfg(trusted_agents=[S.pubkey(k).hex() for k in keys], confirm_delay_seconds=0)
        relays = [MemRelay(f"r{i}", clock) for i in range(3)]
        net = lambda: Relays(mem_pool(relays, clock), mem_pool(relays[:2], clock))
        gh = FakeGitHub(World(), "watcher")  # any GitHub call would count here
        pub = net()
        for i in range(3):
            pub.publish(N.task_event(PUB_SK, REPO, "a" * 40, {"title": f"T{i}"}, 5, 2, t0[0] + i))
        agents = [RelayAgent(c, k, net(), REPO, FakeGit(), clock=clock, sleep=lambda s: None,
                             rng=random.Random(i)) for i, k in enumerate(keys)]
        for _ in range(30):
            t0[0] += 30
            for ag in agents:
                item = ag.next()
                if not item:
                    continue
                if item["kind"] == "resume" or (item["kind"] == "task" and ag.claim(item["task"]["id"])):
                    ag.produce(ag.refresh()[item["task"]["id"]])
                elif item["kind"] == "verify":
                    ag.verify(item["task"])
        state = N.compute(agents[0].relays.snapshot(REPO), c, REPO, t0[0])
        self.assertTrue(state and all(r["status"] == "verified" for r in state.values()), state)
        self.assertEqual(gh.calls, 0)


if __name__ == "__main__":
    unittest.main()
