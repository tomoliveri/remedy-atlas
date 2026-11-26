"""Shared tools in tools/lib: checked against known answers. Needs the core tier (research/env.py setup)."""
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "tools/lib"
sys.path.insert(0, str(LIB))
HAVE_CORE = all(importlib.util.find_spec(m) for m in ("numpy", "scipy"))
HAVE_TORCH = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(HAVE_CORE, "needs the core tier: python3 research/env.py setup core")
class DoseResponse(unittest.TestCase):
    def test_recovers_a_known_curve(self):
        import numpy as np
        import dose_response as D
        doses = np.logspace(-2, 2, 9)
        resp = D.hill(doses, 1.0, 0.05, 1.7, 1.3)
        p = D.fit_hill(doses, resp)
        self.assertAlmostEqual(p["ic50"], 1.7, places=3)
        self.assertAlmostEqual(p["slope"], 1.3, places=3)
        self.assertTrue(p["converged"])
        self.assertLess(p["rmse"], 1e-6)

    def test_bootstrap_interval_covers_the_truth_under_noise(self):
        import numpy as np
        import dose_response as D
        rng = np.random.default_rng(3)
        doses = np.repeat(np.logspace(-2, 2, 8), 3)
        resp = D.hill(doses, 1.0, 0.0, 0.8, 1.0) + rng.normal(0, 0.03, len(doses))
        p = D.fit_hill(doses, resp, top=1.0, bottom=0.0)
        ci = D.bootstrap_ic50(doses, resp, p, 150, rng, top=1.0, bottom=0.0)
        self.assertLess(ci["low"], 0.8)
        self.assertGreater(ci["high"], 0.8)
        self.assertAlmostEqual(D.bliss_excess(0.5, 0.5, 0.75), 0.0)
        self.assertAlmostEqual(D.hsa_excess(0.4, 0.6, 0.7), 0.1)

    def test_command_line_through_the_runner(self):
        rows = ["group,dose,response"] + [f"A,{d},{1 / (1 + (d / 2.0) ** 1.5):.6f}" for d in (0.1, 0.3, 1, 3, 10, 30)]
        with TemporaryDirectory() as w:
            src, out = Path(w) / "d.csv", Path(w) / "fit.json"
            src.write_text("\n".join(rows) + "\n")
            subprocess.run([sys.executable, str(ROOT / "research/run.py"), str(LIB / "dose_response.py"), "--input",
                            str(src), "--output", str(out), "--seed", "1"], check=True, capture_output=True)
            fit = json.loads(out.read_text())["groups"]["A"]
            self.assertAlmostEqual(fit["ic50"], 2.0, places=2)
            receipt = json.loads(out.with_name("fit.json.run.json").read_text())
            self.assertIn("numpy", receipt["libraries"])


@unittest.skipUnless(HAVE_CORE, "needs the core tier")
class HeldOut(unittest.TestCase):
    def test_a_real_signal_beats_the_mean_baseline(self):
        import numpy as np
        import heldout as H
        rng = np.random.default_rng(0)
        rows = [{"compound": f"c{i}", "x": x, "y": 2 * x + rng.normal(0, 0.1)}
                for i, x in enumerate(rng.uniform(0, 5, 30))]

        def fit(train):
            return np.polyfit([r["x"] for r in train], [r["y"] for r in train], 1)

        def predict(coef, rows):
            return np.polyval(coef, [r["x"] for r in rows])
        model = H.leave_one_group_out(rows, "compound", fit, predict, "y")
        base = H.leave_one_group_out(rows, "compound", *H.mean_baseline("y"), "y")
        res = H.compare(model, base, seed=1)
        self.assertEqual(res["verdict"], "model beats baseline")
        self.assertEqual(res["groups"], 30)
        self.assertRaises(ValueError, H.leave_one_group_out, rows[:1], "compound", fit, predict, "y")


@unittest.skipUnless(HAVE_CORE, "needs the core tier")
class TumourPKPD(unittest.TestCase):
    BASE = {"volume_l": 20, "k_el_per_day": 1.0, "alpha_per_day": 0.05, "capacity_mm3": 3000, "v0_mm3": 200,
            "kill_max_per_day": 0.5, "ec50_mg_l": 1.0, "hill": 1.0}

    def test_untreated_growth_matches_the_gompertz_solution(self):
        import tumour_pkpd as T
        sc = {"days": 30, "dt": 0.1, "draws": 3, "schedule": {"dose": 0, "every_days": 7, "doses": 1},
              "priors": self.BASE}
        rel = T.run(sc, seed=1)["relative_volume"]["median"]
        a, k, v0, t = 0.05, 3000, 200, 30
        exact = math.exp(math.log(k) + (math.log(v0) - math.log(k)) * math.exp(-a * t)) / v0
        self.assertAlmostEqual(rel, exact, places=6)

    def test_treatment_shrinks_and_sensitivity_points_at_the_drug(self):
        import tumour_pkpd as T
        sc = {"days": 28, "dt": 0.05, "draws": 2000, "schedule": {"dose": 100, "every_days": 7, "doses": 4},
              "priors": dict(self.BASE, kill_max_per_day=[0.01, 2.0], alpha_per_day=[0.02, 0.06])}
        r = T.run(sc, seed=4)
        self.assertGreater(r["share_shrinking"], 0.2)
        sens = r["sensitivity_spearman"]
        self.assertLess(sens["kill_max_per_day"], -0.8)  # more kill, smaller tumours
        self.assertEqual(T.run(sc, seed=4), r)  # reproducible on the CPU

    @unittest.skipUnless(HAVE_TORCH, "needs the gpu tier")
    def test_gpu_or_torch_matches_the_cpu(self):
        import tumour_pkpd as T
        dev = (T._gpus() or [None])[0]
        if dev is None:
            self.skipTest("no GPU here")
        sc = {"days": 14, "dt": 0.05, "draws": 500, "schedule": {"dose": 100, "every_days": 7, "doses": 2},
              "priors": dict(self.BASE, kill_max_per_day=[0.01, 2.0])}
        cpu, gpu = T.run(sc, 2, "cpu"), T.run(sc, 2, dev)
        self.assertAlmostEqual(cpu["relative_volume"]["median"], gpu["relative_volume"]["median"], places=3)


class Vetting(unittest.TestCase):
    def test_every_shared_tool_passes_vetting_and_matches_its_pin(self):
        sys.path.insert(0, str(ROOT / "tools/ws"))
        from workstead import config as C, toolbox as T
        cfg = C.load(ROOT)
        rows = T.check_library(ROOT, cfg)
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r["status"], "ok", r)


if __name__ == "__main__":
    unittest.main()
