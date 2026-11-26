"""Baseline prediction of NDM-1 inhibitor potency, with and without separating assay readouts."""

import argparse
import csv
import json
from math import isfinite, log10
from pathlib import Path
from random import Random
from statistics import median


def load(path):
    """Read reported point endpoints; censored rows carry no value to predict."""
    rows, censored = [], 0
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            if row["relation"] == "gt":
                censored += 1
                continue
            if row["relation"] != "eq":
                raise ValueError(f"Unknown relation {row['relation']!r}")
            ic50 = float(row["ic50_um"])
            if not isfinite(ic50) or ic50 <= 0:
                raise ValueError(f"Invalid endpoint for {row['study']} / {row['compound']}")
            rows.append({"study": row["study"], "assay_group": row["assay_group"],
                         "assay": row["assay"], "compound": row["compound"],
                         "log_ic50": log10(ic50)})
    if len(rows) < 3:
        raise ValueError("Too few point endpoints to cross-validate")
    return rows, censored


def predict(train, row, key):
    """Median log IC50 of the training rows sharing this row's group, else of all."""
    if key is None:
        pool = train
    else:
        pool = [other for other in train if other[key] == row[key]] or train
    return median(other["log_ic50"] for other in pool)


def leave_one_out(rows, key):
    """Absolute held-out error in log10 units for each endpoint in turn."""
    errors = []
    for index, row in enumerate(rows):
        train = rows[:index] + rows[index + 1:]
        errors.append(abs(row["log_ic50"] - predict(train, row, key)))
    return errors


def summarise(errors):
    ordered = sorted(errors)
    return {"mae_log10": round(sum(errors) / len(errors), 4),
            "median_log10": round(median(ordered), 4),
            "worst_log10": round(ordered[-1], 4),
            "fold_error_at_mae": round(10 ** (sum(errors) / len(errors)), 3)}


def permutation_control(rows, key, seed, samples):
    """Held-out error when the grouping labels are shuffled, breaking any real structure."""
    rng = Random(seed)
    labels = [row[key] for row in rows]
    means = []
    for _ in range(samples):
        rng.shuffle(labels)
        shuffled = [dict(row, **{key: label}) for row, label in zip(rows, labels)]
        errors = leave_one_out(shuffled, key)
        means.append(sum(errors) / len(errors))
    means.sort()
    return {"mae_log10_mean": round(sum(means) / len(means), 4),
            "mae_log10_p05": round(means[int(0.05 * len(means))], 4),
            "mae_log10_p95": round(means[int(0.95 * len(means))], 4)}


def analyse(rows, censored, seed, samples):
    models = {"pooled_ignoring_assay": None, "by_assay_group": "assay_group", "by_study": "study"}
    scores = {name: summarise(leave_one_out(rows, key)) for name, key in models.items()}
    baseline = scores["pooled_ignoring_assay"]["mae_log10"]
    counts = {}
    for row in rows:
        counts.setdefault(row["study"], {"assay_group": row["assay_group"],
                                         "assay": row["assay"], "endpoints": 0})
        counts[row["study"]]["endpoints"] += 1
    return {
        "model": "leave-one-out median baseline for NDM-1 inhibitor potency",
        "seed": seed,
        "samples": samples,
        "endpoints": len(rows),
        "censored_excluded": censored,
        "units": "log10 micromolar IC50",
        "studies": dict(sorted(counts.items())),
        "held_out_error": scores,
        "improvement_over_pooled": {
            name: round(baseline - score["mae_log10"], 4)
            for name, score in scores.items() if name != "pooled_ignoring_assay"
        },
        "shuffled_label_control": {
            "by_assay_group": permutation_control(rows, "assay_group", seed, samples),
            "by_study": permutation_control(rows, "study", seed + 1, samples),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--samples", type=int, default=500)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    rows, censored = load(args.input)
    result = analyse(rows, censored, args.seed, args.samples)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
