"""Fit four-parameter Hill (log-logistic) curves to dose-response data, with bootstrap intervals.

Viability at dose d:  bottom + (top - bottom) / (1 + (d / ic50) ** slope)

Input CSV columns: group (an organoid, cell line or compound), dose (> 0),
response (viability as a fraction, or percent with --percent). Output JSON:
per group the fitted parameters, RMSE, a residual-bootstrap interval for the
IC50 and the normalised area under the curve. Fits that don't converge or hit
a bound are reported as such, never silently kept.

    python3 research/run.py tools/lib/dose_response.py --input data.csv --output fit.json --seed 1
"""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

SLOPE_BOUNDS = (0.1, 10.0)


def hill(dose, top, bottom, ic50, slope):
    dose = np.asarray(dose, dtype=float)
    return bottom + (top - bottom) / (1.0 + (dose / ic50) ** slope)


def fit_hill(doses, responses, top=None, bottom=None):
    """Least-squares fit on log10(IC50). Fix top or bottom by passing a number."""
    d, r = np.asarray(doses, float), np.asarray(responses, float)
    if len(d) < 3 or np.any(d <= 0) or not np.all(np.isfinite(r)):
        raise ValueError("needs at least three positive doses with finite responses")
    free = [top is None, bottom is None, True, True]
    lo_d, hi_d = math.log10(d.min()) - 2, math.log10(d.max()) + 2
    start = np.array([r.max() if top is None else top, r.min() if bottom is None else bottom,
                      math.log10(np.median(d)), 1.0])
    lower = np.array([0.0, -0.5, lo_d, SLOPE_BOUNDS[0]])
    upper = np.array([1.5, 1.0, hi_d, SLOPE_BOUNDS[1]])
    idx = [i for i, f in enumerate(free) if f]

    def unpack(p):
        full = start.copy()
        full[idx] = p
        return full

    def resid(p):
        t, b, lic, s = unpack(p)
        return hill(d, t, b, 10 ** lic, s) - r

    x0 = np.clip(start[idx], lower[idx] + 1e-9, upper[idx] - 1e-9)
    sol = least_squares(resid, x0, bounds=(lower[idx], upper[idx]), method="trf")
    t, b, lic, s = unpack(sol.x)
    at_bound = bool(np.any(np.isclose(sol.x, lower[idx], atol=1e-6) | np.isclose(sol.x, upper[idx], atol=1e-6)))
    rmse = float(np.sqrt(np.mean(sol.fun ** 2)))
    return {"top": float(t), "bottom": float(b), "ic50": float(10 ** lic), "slope": float(s), "rmse": rmse,
            "converged": bool(sol.success), "at_bound": at_bound, "n": int(len(d))}


def normalised_auc(params, dmin, dmax, points=200):
    """Area under the viability curve over log10 dose, scaled to [0, 1] for a curve between 0 and 1."""
    x = np.linspace(math.log10(dmin), math.log10(dmax), points)
    y = hill(10 ** x, params["top"], params["bottom"], params["ic50"], params["slope"])
    return float(np.trapezoid(y, x) / (x[-1] - x[0])) if hasattr(np, "trapezoid") else \
        float(np.trapz(y, x) / (x[-1] - x[0]))


def bootstrap_ic50(doses, responses, params, samples, rng, top=None, bottom=None):
    """Residual bootstrap: refit on fitted curve + resampled residuals. Returns the 2.5/50/97.5 percentiles."""
    d, r = np.asarray(doses, float), np.asarray(responses, float)
    fitted = hill(d, params["top"], params["bottom"], params["ic50"], params["slope"])
    res = r - fitted
    vals = []
    for _ in range(samples):
        try:
            vals.append(fit_hill(d, fitted + rng.choice(res, size=len(res), replace=True), top, bottom)["ic50"])
        except ValueError:
            continue
    if len(vals) < max(10, samples // 2):
        return None
    lo, mid, hi = np.percentile(np.log10(vals), [2.5, 50, 97.5])
    return {"low": float(10 ** lo), "median": float(10 ** mid), "high": float(10 ** hi), "samples": len(vals)}


def bliss_excess(effect_a, effect_b, effect_ab):
    """Observed combined effect minus Bliss independence (effects are fractions inhibited, 0-1)."""
    return float(effect_ab - (effect_a + effect_b - effect_a * effect_b))


def hsa_excess(effect_a, effect_b, effect_ab):
    """Observed combined effect minus the better single agent."""
    return float(effect_ab - max(effect_a, effect_b))


def load(path, percent=False):
    groups = {}
    with Path(path).open(newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("dose", "").strip() or not row.get("response", "").strip():
                continue
            dose, resp = float(row["dose"]), float(row["response"])
            if not (math.isfinite(dose) and math.isfinite(resp)) or dose <= 0:
                raise ValueError(f"bad row: {row}")
            groups.setdefault(row["group"], ([], []))
            groups[row["group"]][0].append(dose)
            groups[row["group"]][1].append(resp / 100 if percent else resp)
    if not groups:
        raise ValueError("no rows with a dose and a response")
    return groups


def analyse(groups, seed, samples=200, top=None, bottom=None):
    rng = np.random.default_rng(seed)
    out = {}
    for name in sorted(groups):
        d, r = groups[name]
        try:
            p = fit_hill(d, r, top, bottom)
        except ValueError as e:
            out[name] = {"error": str(e), "n": len(d)}
            continue
        p["auc"] = normalised_auc(p, min(d), max(d))
        p["ic50_interval"] = bootstrap_ic50(d, r, p, samples, rng, top, bottom) if samples else None
        p["extrapolated"] = not (min(d) <= p["ic50"] <= max(d))
        out[name] = p
    return {"model": "four-parameter Hill", "seed": seed, "bootstrap_samples": samples,
            "fixed": {"top": top, "bottom": bottom}, "groups": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--seed", required=True, type=int)
    ap.add_argument("--samples", type=int, default=200, help="bootstrap resamples per group (0: none)")
    ap.add_argument("--percent", action="store_true", help="responses are percentages")
    ap.add_argument("--top", type=float, help="fix the top plateau (for example 1.0)")
    ap.add_argument("--bottom", type=float, help="fix the bottom plateau (for example 0.0)")
    a = ap.parse_args()
    result = analyse(load(a.input, a.percent), a.seed, a.samples, a.top, a.bottom)
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
