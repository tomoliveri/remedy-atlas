"""Hill response model of published SVMP-inhibitor IC50 endpoints, against a single-agent baseline."""

import argparse
import csv
from itertools import combinations
import json
from math import isfinite
from pathlib import Path
from random import Random

# Assay-only concentration grid in micromolar, log-spaced around the published
# endpoints. It carries no clinical dose meaning.
GRID = tuple(round(10 ** (-3 + step * 0.1), 6) for step in range(51))
COVERAGE = 0.9


def load_endpoints(path):
    """Read published IC50 values into {toxin: {inhibitor: (ic50, spread, hill)}}."""
    toxins = {}
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            toxin = toxins.setdefault(row["toxin"], {})
            inhibitor = row["inhibitor"]
            ic50, spread, hill = (float(row["ic50_um"]), float(row["ic50_pm_um"]),
                                  float(row["hill"]))
            if inhibitor in toxin:
                raise ValueError(f"Duplicate endpoint for {row['toxin']} / {inhibitor}")
            if not all(isfinite(value) for value in (ic50, spread, hill)):
                raise ValueError(f"Non-finite endpoint for {row['toxin']} / {inhibitor}")
            if ic50 <= 0 or hill <= 0 or spread < 0:
                raise ValueError(f"Invalid endpoint for {row['toxin']} / {inhibitor}")
            toxin[inhibitor] = (ic50, spread, hill)
    if not toxins:
        raise ValueError("The data contains no toxins")
    return toxins


def inhibition(dose, ic50, hill):
    """Fraction of enzyme activity inhibited at a dose, under the Hill model."""
    return 1 / (1 + (ic50 / dose) ** hill)


def covering_dose(curve, toxins):
    """Lowest grid dose inhibiting every toxin by COVERAGE, or None within the grid."""
    for dose in GRID:
        if all(curve(dose, toxin) >= COVERAGE for toxin in toxins):
            return dose
    return None


def single_agent(draw, inhibitor, toxins):
    """A single agent gives its whole dose to one drug."""
    def curve(dose, toxin):
        ic50, hill = draw[toxin][inhibitor]
        return inhibition(dose, ic50, hill)
    return covering_dose(curve, toxins)


def bliss_pair(draw, pair, toxins):
    """A pair splits the same total dose, combining under Bliss independence."""
    def curve(dose, toxin):
        remaining = 1.0
        for inhibitor in pair:
            ic50, hill = draw[toxin][inhibitor]
            remaining *= 1 - inhibition(dose / len(pair), ic50, hill)
        return 1 - remaining
    return covering_dose(curve, toxins)


def sample(rng, toxins):
    """Draw one IC50 per toxin and inhibitor from its reported spread."""
    draw = {}
    for toxin, endpoints in toxins.items():
        drawn = draw.setdefault(toxin, {})
        for inhibitor, (ic50, spread, hill) in endpoints.items():
            value = rng.gauss(ic50, spread)
            # The reported spread can reach zero or below; a concentration cannot.
            drawn[inhibitor] = (max(value, ic50 / 100), hill)
    return draw


def better(left, right):
    """A dose that achieves coverage beats one that never does within the grid."""
    if left is None:
        return False
    return right is None or left < right


def study(toxins, seed, samples):
    names = sorted(toxins)
    shared = sorted(set.intersection(*(set(toxins[name]) for name in names)))
    if len(shared) < 2:
        raise ValueError("Fewer than two inhibitors are matched across every toxin")
    pairs = list(combinations(shared, 2))
    rng = Random(seed)

    single_wins = {inhibitor: 0 for inhibitor in shared}
    single_covers = dict(single_wins)
    pair_beats_best_single = {" + ".join(pair): 0 for pair in pairs}
    per_toxin = {name: {inhibitor: 0 for inhibitor in shared} for name in names}

    for _ in range(samples):
        draw = sample(rng, toxins)
        doses = {inhibitor: single_agent(draw, inhibitor, names) for inhibitor in shared}
        for inhibitor, dose in doses.items():
            if dose is not None:
                single_covers[inhibitor] += 1
        best = None
        for inhibitor in shared:
            if better(doses[inhibitor], best):
                best = doses[inhibitor]
        for inhibitor in shared:
            if doses[inhibitor] is not None and doses[inhibitor] == best:
                single_wins[inhibitor] += 1
        for name in names:
            single = {inhibitor: single_agent(draw, inhibitor, [name]) for inhibitor in shared}
            leader = None
            for inhibitor in shared:
                if better(single[inhibitor], leader):
                    leader = single[inhibitor]
            for inhibitor in shared:
                if single[inhibitor] is not None and single[inhibitor] == leader:
                    per_toxin[name][inhibitor] += 1
        for pair in pairs:
            if better(bliss_pair(draw, pair, names), best):
                pair_beats_best_single[" + ".join(pair)] += 1

    return {
        "model": "Hill inhibition of published SVMP IC50 endpoints",
        "seed": seed,
        "samples": samples,
        "toxins": names,
        "matched_inhibitors": shared,
        "coverage_threshold": COVERAGE,
        "dose_grid_um": [GRID[0], GRID[-1]],
        "combination_assumption": "Bliss independence at an equal split of one total dose",
        "reported": {toxin: {inhibitor: {"ic50_um": ic50, "reported_spread_um": spread,
                                         "hill": hill}
                             for inhibitor, (ic50, spread, hill) in sorted(endpoints.items())}
                     for toxin, endpoints in sorted(toxins.items())},
        "single_agent_covers_all_toxins": single_covers,
        "lowest_dose_single_agent": single_wins,
        "lowest_dose_single_agent_per_toxin": per_toxin,
        "pair_below_best_single_agent": pair_beats_best_single,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--samples", type=int, default=2000)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    result = study(load_endpoints(args.input), args.seed, args.samples)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
