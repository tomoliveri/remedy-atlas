"""Batched tumour growth under drug exposure: one-compartment PK, Emax kill, Gompertz growth.

A sensitivity study over uncertain parameters, run as many virtual tumours
at once on the CPU (NumPy) or a GPU (PyTorch: CUDA, ROCm or Apple Metal).

    concentration  C(t) = sum over doses of (dose / volume) * exp(-k_el * (t - t_dose))
    growth         dV/dt = alpha * V * ln(capacity / V) - kill_max * C^h / (ec50^h + C^h) * V

The input JSON gives the schedule and a prior per parameter, either a number
(fixed) or [low, high] (sampled log-uniformly):

    {"days": 42, "dt": 0.05, "draws": 20000,
     "schedule": {"dose": 75, "every_days": 7, "doses": 6},
     "priors": {"volume_l": [10, 40], "k_el_per_day": [0.5, 5], "alpha_per_day": [0.01, 0.1],
                "capacity_mm3": 3000, "v0_mm3": 200, "kill_max_per_day": [0.05, 1.0],
                "ec50_mg_l": [0.1, 10], "hill": [0.5, 3]}}

These are assay-scale assumptions for comparing scenarios, not dosing
advice. The output reports the final volume relative to the start
(quantiles), the share of virtual tumours that shrank, and each sampled
parameter's rank correlation with the outcome (which assumptions matter).
Parameters are drawn with NumPy from the seed, so every device simulates the
same draws; the CPU default is bit-for-bit reproducible.

    python3 research/run.py tools/lib/tumour_pkpd.py --input scenario.json --output out.json --seed 7
"""
import argparse
import json
from pathlib import Path

import platform

import numpy as np

PARAMS = ("volume_l", "k_el_per_day", "alpha_per_day", "capacity_mm3", "v0_mm3", "kill_max_per_day", "ec50_mg_l",
          "hill")


class _Backend:
    """NumPy (CPU, float64) or PyTorch on a GPU. Self-contained so this file can be shared on its own."""

    def __init__(self, device):
        if device == "auto":
            device = next((d for d in _gpus()), "cpu")
        self.device = device
        if device == "cpu":
            self.xp, self.dtype = np, np.float64
        else:
            if device not in _gpus():
                raise ValueError(f"device {device} isn't available here")
            import torch
            self.xp, self.dtype = torch, (torch.float32 if device == "mps" else torch.float64)

    def asarray(self, x):
        if self.xp is np:
            return np.asarray(x, dtype=self.dtype)
        return self.xp.as_tensor(np.asarray(x), dtype=self.dtype, device=self.device)

    def to_numpy(self, x):
        return np.asarray(x) if self.xp is np else x.detach().to("cpu").double().numpy()

    def zeros(self, n):
        return np.zeros(n) if self.xp is np else self.xp.zeros(n, dtype=self.dtype, device=self.device)

    def clip(self, x, lo, hi):
        return np.clip(x, lo, hi) if self.xp is np else self.xp.clamp(x, lo, hi)

    def describe(self):
        return {"backend": "numpy" if self.xp is np else "torch", "device": self.device,
                "dtype": str(self.dtype).replace("torch.", "").replace("<class 'numpy.", "").rstrip("'>"),
                "machine": platform.machine()}


def _gpus():
    try:
        import torch
    except ImportError:
        return []
    found = ["cuda"] if torch.cuda.is_available() else []
    mps = getattr(torch.backends, "mps", None)
    return found + (["mps"] if mps is not None and mps.is_available() else [])


def backend(device="cpu"):
    return _Backend(device)


def draw(priors, draws, rng):
    """Fixed numbers stay fixed; [low, high] is sampled log-uniformly. Returns {name: array}."""
    out = {}
    for name in PARAMS:
        p = priors.get(name)
        if isinstance(p, (int, float)) and p > 0:
            out[name] = np.full(draws, float(p))
        elif isinstance(p, list) and len(p) == 2 and 0 < p[0] <= p[1]:
            out[name] = np.exp(rng.uniform(np.log(p[0]), np.log(p[1]), draws))
        else:
            raise ValueError(f"prior {name}: a positive number or [low, high]")
    if np.any(out["v0_mm3"] >= out["capacity_mm3"]):
        raise ValueError("v0_mm3 must be below capacity_mm3")
    return out


def dose_times(schedule):
    every, n = float(schedule["every_days"]), int(schedule["doses"])
    if every <= 0 or not 1 <= n <= 1000 or float(schedule["dose"]) < 0:
        raise ValueError("schedule: dose >= 0, every_days > 0, 1-1000 doses")
    return [i * every for i in range(n)]


def simulate(params, schedule, days, dt, be):
    """Fixed-step RK4 over all draws at once. Returns final volume / initial volume (NumPy array)."""
    xp = be.xp
    p = {k: be.asarray(v) for k, v in params.items()}
    times, dose = dose_times(schedule), float(schedule["dose"])
    steps = int(round(days / dt))
    if not 1 <= steps <= 2_000_000:
        raise ValueError("days / dt must give 1 to 2,000,000 steps")
    log_cap = xp.log(p["capacity_mm3"])

    def conc(t):
        c = be.zeros(p["volume_l"].shape[0])
        for td in times:
            if td <= t:
                c = c + dose / p["volume_l"] * xp.exp(-p["k_el_per_day"] * (t - td))
        return c

    def rate(logv, c):  # on log volume: d(ln V)/dt = alpha * ln(K/V) - kill(C)
        ch = c ** p["hill"]
        kill = p["kill_max_per_day"] * ch / (p["ec50_mg_l"] ** p["hill"] + ch)
        return p["alpha_per_day"] * (log_cap - logv) - kill

    logv = xp.log(p["v0_mm3"])
    log0 = logv
    for i in range(steps):
        t = i * dt
        c0, ch, c1 = conc(t), conc(t + dt / 2), conc(t + dt)
        k1 = rate(logv, c0)
        k2 = rate(logv + dt / 2 * k1, ch)
        k3 = rate(logv + dt / 2 * k2, ch)
        k4 = rate(logv + dt * k3, c1)
        logv = be.clip(logv + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4), -50.0, 50.0)
    return be.to_numpy(xp.exp(logv - log0))


def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def run(scenario, seed, device="cpu"):
    draws = int(scenario.get("draws", 10000))
    if not 1 <= draws <= 5_000_000:
        raise ValueError("draws: 1 to 5,000,000")
    rng = np.random.default_rng(seed)
    params = draw(scenario["priors"], draws, rng)
    be = backend(device)
    rel = simulate(params, scenario["schedule"], float(scenario.get("days", 42)), float(scenario.get("dt", 0.05)), be)
    q = np.percentile(rel, [5, 25, 50, 75, 95])
    sampled = [k for k in PARAMS if isinstance(scenario["priors"].get(k), list)]
    return {"model": "one-compartment PK, Emax kill, Gompertz growth", "seed": seed, "draws": draws,
            "compute": be.describe(),
            "relative_volume": dict(zip(["p5", "p25", "median", "p75", "p95"], map(float, q))),
            "share_shrinking": float(np.mean(rel < 1.0)),
            "sensitivity_spearman": {k: spearman(params[k], rel) for k in sampled}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--seed", required=True, type=int)
    ap.add_argument("--device", default="cpu", help="cpu (reproducible), auto, cuda, mps")
    a = ap.parse_args()
    result = run(json.loads(a.input.read_text()), a.seed, a.device)
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
