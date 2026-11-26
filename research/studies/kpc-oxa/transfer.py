"""Benchmark how published inhibitor potency transfers between KPC and OXA-48.

Each row of the input is one published IC50 or Ki from ChEMBL. Measurements of the
same compound, with the same endpoint, in the same publication against both enzyme
families form a matched pair. Leaving one publication out at a time, the study
predicts a compound's potency on one enzyme from training publications and compares:

  pooled_mean    mean potency of all training measurements, both enzymes together
  enzyme_mean    mean potency of training measurements on the target enzyme
  identity       the compound's measured potency on the other enzyme, unchanged
  offset         the other-enzyme potency plus the mean training difference
  linear         ordinary least squares of target on other-enzyme potency

Potency is p = 9 - log10(value in nM), the pIC50 or pKi. A cluster bootstrap over
held-out publications, driven by --seed, gives intervals for RMSE differences.
"""

import argparse
import csv
import json
from math import isfinite, log10, sqrt
from pathlib import Path
from random import Random
from statistics import fmean

MODELS = ("pooled_mean", "enzyme_mean", "identity", "offset", "linear")
DIRECTIONS = (("KPC", "OXA-48"), ("OXA-48", "KPC"))


def load(path):
    rows = []
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            value = float(row["value_nm"])
            if not isfinite(value) or value <= 0:
                raise ValueError(f"Invalid value for activity {row['activity_id']}")
            if row["family"] not in ("KPC", "OXA-48") or row["relation"] not in ("=", ">"):
                raise ValueError(f"Unexpected family or relation for activity {row['activity_id']}")
            rows.append({**row, "p": 9 - log10(value), "compiled_review": row["compiled_review"] == "1"})
    if not rows:
        raise ValueError("The input contains no measurements")
    return rows


def pairs(rows, include_reviews, include_censored, endpoint=None):
    """Combine replicate measurements and return matched (document, compound) pairs.

    Exact values are averaged in p (a geometric mean of concentrations). A family with
    only censored values ('> X nM', so p < 9 - log10 X) is kept at its bound only when
    include_censored is set; the bound overstates potency, which the output reports.
    """
    groups = {}
    for row in rows:
        if (row["compiled_review"] and not include_reviews) or (endpoint and row["endpoint"] != endpoint):
            continue
        key = (row["document_chembl_id"], row["molecule_chembl_id"], row["endpoint"])
        groups.setdefault(key, {}).setdefault(row["family"], []).append(row)
    result = []
    for (document, molecule, kind), families in sorted(groups.items()):
        if len(families) != 2:
            continue
        pair = {"document": document, "molecule": molecule, "endpoint": kind, "censored": False}
        for family, measured in families.items():
            exact = [m["p"] for m in measured if m["relation"] == "="]
            if exact:
                pair[family] = fmean(exact)
            elif include_censored:
                pair[family] = min(m["p"] for m in measured)  # the tightest '>' bound
                pair["censored"] = True
            else:
                break
        else:
            result.append(pair)
    return result


def fit(train, source, target):
    """Fit every model on training pairs; return {model: predict(pair)}."""
    xs, ys = [p[source] for p in train], [p[target] for p in train]
    pooled = fmean(xs + ys)
    mean_y, mean_x = fmean(ys), fmean(xs)
    shift = fmean(y - x for x, y in zip(xs, ys))
    spread = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread if spread else 0.0
    return {
        "pooled_mean": lambda p: pooled,
        "enzyme_mean": lambda p: mean_y,
        "identity": lambda p: p[source],
        "offset": lambda p: p[source] + shift,
        "linear": lambda p: mean_y + slope * (p[source] - mean_x),
    }


def leave_one_document_out(data, source, target):
    """Squared and absolute errors per held-out document, for every model."""
    documents = sorted({p["document"] for p in data})
    errors = {}
    for held in documents:
        train = [p for p in data if p["document"] != held]
        test = [p for p in data if p["document"] == held]
        if len(train) < 3 or len({p["document"] for p in train}) < 2:
            continue
        models = fit(train, source, target)
        errors[held] = {name: [models[name](p) - p[target] for p in test] for name in MODELS}
    return errors


def rmse(values):
    return sqrt(fmean(v * v for v in values))


def summarise(errors):
    flat = {name: [e for doc in errors.values() for e in doc[name]] for name in MODELS}
    return {name: {"rmse": round(rmse(values), 4), "mae": round(fmean(abs(v) for v in values), 4)}
            for name, values in flat.items()}


def bootstrap(errors, rng, resamples, baseline="enzyme_mean"):
    """Cluster bootstrap over held-out documents: RMSE(model) - RMSE(baseline)."""
    documents = sorted(errors)
    draws = {name: [] for name in MODELS if name != baseline}
    for _ in range(resamples):
        chosen = [rng.choice(documents) for _ in documents]
        base = rmse([e for doc in chosen for e in errors[doc][baseline]])
        for name in draws:
            draws[name].append(rmse([e for doc in chosen for e in errors[doc][name]]) - base)
    result = {}
    for name, values in draws.items():
        values.sort()
        result[name] = {"interval_95": [round(values[int(0.025 * resamples)], 4),
                                        round(values[int(0.975 * resamples) - 1], 4)],
                        "share_below_zero": round(sum(v < 0 for v in values) / resamples, 4)}
    return result


def rank_correlation(xs, ys):
    """Spearman correlation with average ranks for ties; None when undefined."""
    def ranks(values):
        order = sorted(range(len(values)), key=values.__getitem__)
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2
            i = j + 1
        return out
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = fmean(rx), fmean(ry)
    sx = sqrt(sum((r - mx) ** 2 for r in rx))
    sy = sqrt(sum((r - my) ** 2 for r in ry))
    if not sx or not sy:
        return None
    return round(sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy), 4)


def analysis(rows, rng, resamples, include_reviews, include_censored, endpoint=None):
    data = pairs(rows, include_reviews, include_censored, endpoint)
    documents = sorted({p["document"] for p in data})
    out = {"pairs": len(data), "documents": len(documents),
           "censored_pairs": sum(p["censored"] for p in data),
           "spearman_kpc_vs_oxa48": rank_correlation([p["KPC"] for p in data], [p["OXA-48"] for p in data]),
           "mean_oxa48_minus_kpc": round(fmean(p["OXA-48"] - p["KPC"] for p in data), 4) if data else None}
    within = {}
    for doc in documents:
        sub = [p for p in data if p["document"] == doc]
        rho = rank_correlation([p["KPC"] for p in sub], [p["OXA-48"] for p in sub])
        if len(sub) >= 5 and rho is not None:
            within[doc] = {"pairs": len(sub), "spearman": rho}
    out["within_document_spearman"] = within
    for source, target in DIRECTIONS:
        errors = leave_one_document_out(data, source, target)
        out[f"predict_{target}_from_{source}"] = {
            "held_out_documents": len(errors),
            "metrics_pIC50_or_pKi": summarise(errors) if errors else None,
            "rmse_minus_enzyme_mean": bootstrap(errors, rng, resamples) if len(errors) >= 2 else None,
        }
    return out


def study(rows, seed, resamples):
    rng = Random(seed)
    return {
        "model": "Leave-one-publication-out transfer of KPC and OXA-48 inhibitor potency",
        "seed": seed,
        "bootstrap_resamples": resamples,
        "potency_scale": "p = 9 - log10(nM); pIC50 or pKi",
        "models": list(MODELS),
        "measurements": len(rows),
        "primary": analysis(rows, rng, resamples, include_reviews=False, include_censored=False),
        "sensitivity": {
            "with_compiled_reviews": analysis(rows, rng, resamples, True, False),
            "with_censored_at_bound": analysis(rows, rng, resamples, False, True),
            "ic50_only": analysis(rows, rng, resamples, False, False, "IC50"),
            "ki_only": analysis(rows, rng, resamples, False, False, "Ki"),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args()
    if args.resamples < 40:
        parser.error("--resamples must be at least 40")
    result = study(load(args.input), args.seed, args.resamples)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
