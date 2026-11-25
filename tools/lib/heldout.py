"""Held-out benchmarks: leave one group out, compare a model to a baseline, with a paired bootstrap.

Every Remedy Atlas track asks the same question: does a model predict
published measurements it wasn't fitted to better than a simple baseline?
Hold out one group at a time (an organoid, a compound, a study), fit on the
rest, predict the held-out group, and compare errors pairwise.

    from heldout import leave_one_group_out, compare, mean_baseline
    model = leave_one_group_out(rows, "compound", fit, predict, "pic50")
    base = leave_one_group_out(rows, "compound", *mean_baseline("pic50"), "pic50")
    compare(model, base, seed=1)
"""
import math

import numpy as np


def leave_one_group_out(rows, group_key, fit, predict, target):
    """rows: list of dicts. fit(train_rows) -> model; predict(model, rows) -> predictions.

    Returns {group: {"n", "mae", "rmse"}} for every group with at least one finite target.
    """
    groups = sorted({r[group_key] for r in rows})
    if len(groups) < 2:
        raise ValueError("needs at least two groups to hold one out")
    out = {}
    for g in groups:
        test = [r for r in rows if r[group_key] == g and _finite(r.get(target))]
        train = [r for r in rows if r[group_key] != g and _finite(r.get(target))]
        if not test or not train:
            continue
        model = fit(train)
        pred = np.asarray(predict(model, test), dtype=float)
        err = pred - np.asarray([float(r[target]) for r in test])
        out[g] = {"n": len(test), "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2)))}
    return out


def mean_baseline(target):
    """The baseline every model must beat: predict the training mean."""
    def fit(train):
        return float(np.mean([float(r[target]) for r in train]))

    def predict(mean, rows):
        return [mean] * len(rows)
    return fit, predict


def compare(model, baseline, seed, metric="mae", samples=2000):
    """Paired bootstrap over held-out groups of (model - baseline) error. Negative means the model is better."""
    common = sorted(set(model) & set(baseline))
    if not common:
        raise ValueError("no held-out groups in common")
    diff = np.array([model[g][metric] - baseline[g][metric] for g in common])
    rng = np.random.default_rng(seed)
    boots = np.array([rng.choice(diff, size=len(diff), replace=True).mean() for _ in range(samples)])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"metric": metric, "groups": len(common), "mean_difference": float(diff.mean()),
            "interval": [float(lo), float(hi)], "model_better_in": int(np.sum(diff < 0)),
            "baseline_better_in": int(np.sum(diff > 0)),
            "verdict": ("model beats baseline" if hi < 0 else "baseline beats model" if lo > 0
                        else "no clear difference")}


def _finite(x):
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
