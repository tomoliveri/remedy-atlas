"""Sensitivity analysis of a Hill response model around published organoid CC50 values."""

import argparse
import csv
from itertools import combinations
import json
from math import isfinite
from pathlib import Path
from random import Random


def load_cc50(path):
    models = {}
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            model = models.setdefault(row["model"], {})
            drug = row["drug"]
            value = float(row["cc50_um"]) if row["cc50_um"].strip() else None
            if drug in model or (value is not None and (not isfinite(value) or value <= 0)):
                raise ValueError(f"Invalid or duplicate CC50 for {row['model']} / {drug}")
            model[drug] = value
    if not models:
        raise ValueError("The data contains no organoids")
    return models


def sensitivity(models, seed, samples):
    rng = Random(seed)
    relative_doses = (0.25, 0.5, 1.0, 2.0, 4.0)
    model_results = {}
    for name, drugs in sorted(models.items()):
        observed = {drug: value for drug, value in sorted(drugs.items()) if value is not None}
        pairs = list(combinations(observed, 2))
        comparisons = {
            f"{left} vs {right}": {"left": 0, "right": 0, "tie": 0}
            for left, right in pairs
        }
        if pairs:
            # This assay-only concentration grid is centred on the recorded
            # endpoints for the organoid. It carries no clinical dose meaning.
            centre = sorted(observed.values())[len(observed) // 2]
            for _ in range(samples):
                slopes = {drug: rng.uniform(0.5, 3.0) for drug in observed}
                for multiplier in relative_doses:
                    dose = centre * multiplier
                    viability = {drug: 1 / (1 + (dose / cc50) ** slopes[drug])
                                 for drug, cc50 in observed.items()}
                    for left, right in pairs:
                        delta = viability[left] - viability[right]
                        winner = "tie" if abs(delta) < 1e-10 else "left" if delta < 0 else "right"
                        comparisons[f"{left} vs {right}"][winner] += 1
        model_results[name] = {"missing": sorted(drug for drug, value in drugs.items() if value is None),
                               "pair_counts": comparisons}
    return {"model": "Hill viability sensitivity", "seed": seed, "samples": samples,
            "assumed_slope_bounds": [0.5, 3.0], "dose_multipliers": relative_doses,
            "results": model_results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--samples", type=int, default=2000)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    result = sensitivity(load_cc50(args.input), args.seed, args.samples)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
