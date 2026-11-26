"""Stress-test whether a pooled ranking of NDM-1 inhibitors survives cross-study calibration."""

import argparse
import csv
from itertools import combinations
import json
from math import isfinite, log, exp
from pathlib import Path
from random import Random

ANCHOR = "D-captopril"
# Assay-to-assay error applied to every reported endpoint, as a fold change. The
# published reports give no common error model, so this is a stated assumption.
FOLD_ERROR = 2.0


def load(path):
    """Read reported endpoints into per-study records."""
    studies = {}
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            ic50 = float(row["ic50_um"])
            alt = float(row["alt_ic50_um"]) if row["alt_ic50_um"].strip() else None
            if not isfinite(ic50) or ic50 <= 0 or (alt is not None and alt <= 0):
                raise ValueError(f"Invalid endpoint for {row['study']} / {row['compound']}")
            if row["relation"] not in ("eq", "gt"):
                raise ValueError(f"Unknown relation {row['relation']!r}")
            record = {"study": row["study"], "reference": row["reference"],
                      "assay_group": row["assay_group"], "assay": row["assay"],
                      "compound": row["compound"], "ic50_um": ic50,
                      "censored": row["relation"] == "gt", "alt_ic50_um": alt}
            entries = studies.setdefault(row["study"], [])
            if any(e["compound"] == record["compound"] for e in entries):
                raise ValueError(f"Duplicate compound {record['compound']} in {row['study']}")
            entries.append(record)
    if not studies:
        raise ValueError("The data contains no studies")
    return studies


def anchors(studies):
    """The anchor compound's reported value in each study that measured it."""
    found = {}
    for study, entries in studies.items():
        for entry in entries:
            if entry["compound"] == ANCHOR and not entry["censored"]:
                found[study] = entry["ic50_um"]
    if len(found) < 2:
        raise ValueError(f"{ANCHOR} is not reported by at least two studies")
    return found


def jitter(rng, value, fold):
    """Multiply a value by a log-uniform factor within the given fold range."""
    return value * exp(rng.uniform(-log(fold), log(fold)))


def label(entry):
    return f"{entry['compound']} [{entry['study']}]"


def ranking(values):
    """Compound labels ordered most to least potent, lowest value first."""
    return [name for name, _ in sorted(values.items(), key=lambda item: (item[1], item[0]))]


def kendall_tau(left, right):
    """Rank correlation between two orderings of the same labels."""
    position = {name: index for index, name in enumerate(right)}
    concordant = discordant = 0
    for first, second in combinations(left, 2):
        if position[first] < position[second]:
            concordant += 1
        else:
            discordant += 1
    total = concordant + discordant
    return (concordant - discordant) / total if total else 0.0


def study_anchor(rng, study, measured, spread):
    """A study's anchor value: its own if it measured one, otherwise imputed."""
    if study in measured:
        return jitter(rng, measured[study], FOLD_ERROR), False
    low, high = spread
    return exp(rng.uniform(log(low), log(high))), True


def analyse(studies, seed, samples):
    measured = anchors(studies)
    spread = (min(measured.values()), max(measured.values()))
    comparable = [e for entries in studies.values() for e in entries if not e["censored"]]
    censored = [label(e) for entries in studies.values() for e in entries if e["censored"]]
    unanchored = sorted(study for study in studies if study not in measured)

    naive = ranking({label(e): e["ic50_um"] for e in comparable})
    rng = Random(seed)
    taus, null_taus = [], []
    leaders, positions = {}, {name: [] for name in naive}

    for _ in range(samples):
        drawn = {}
        study_scale = {study: study_anchor(rng, study, measured, spread)[0] for study in studies}
        for entry in comparable:
            if entry["compound"] == ANCHOR and entry["study"] in measured:
                # The anchor is the same single measurement as its study's scale,
                # so after calibration it is 1 by construction, not an independent draw.
                drawn[label(entry)] = 1.0
                continue
            reported = entry["ic50_um"]
            if entry["alt_ic50_um"] is not None:
                # The review reports two values for this compound; neither is preferred.
                reported = rng.choice([reported, entry["alt_ic50_um"]])
            drawn[label(entry)] = jitter(rng, reported, FOLD_ERROR) / study_scale[entry["study"]]
        order = ranking(drawn)
        taus.append(kendall_tau(naive, order))
        leaders[order[0]] = leaders.get(order[0], 0) + 1
        for index, name in enumerate(order):
            positions[name].append(index + 1)
        shuffled = list(naive)
        rng.shuffle(shuffled)
        null_taus.append(kendall_tau(naive, shuffled))

    mean = lambda values: sum(values) / len(values)
    return {
        "model": "cross-study calibration of pooled NDM-1 inhibitor endpoints",
        "seed": seed,
        "samples": samples,
        "anchor": ANCHOR,
        "anchor_reported_um": measured,
        "anchor_fold_disagreement": round(spread[1] / spread[0], 3),
        "assumed_fold_error": FOLD_ERROR,
        "studies": {study: {"reference": entries[0]["reference"],
                            "assay_group": entries[0]["assay_group"],
                            "assay": entries[0]["assay"],
                            "compounds": len(entries),
                            "anchored": study in measured}
                    for study, entries in sorted(studies.items())},
        "studies_without_anchor": unanchored,
        "censored_excluded": sorted(censored),
        "naive_pooled_ranking": naive,
        "naive_top": naive[0],
        "kendall_tau_vs_naive": {"mean": round(mean(taus), 4),
                                 "min": round(min(taus), 4),
                                 "max": round(max(taus), 4)},
        "permutation_null_tau": {"mean": round(mean(null_taus), 4),
                                 "min": round(min(null_taus), 4),
                                 "max": round(max(null_taus), 4)},
        "top_rank_frequency": dict(sorted(leaders.items(), key=lambda kv: -kv[1])),
        "naive_top_stays_top": leaders.get(naive[0], 0),
        "rank_interval": {name: [min(seen), max(seen), round(mean(seen), 2)]
                          for name, seen in sorted(positions.items())},
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
    result = analyse(load(args.input), args.seed, args.samples)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
