# NDM-1 inhibitor ranking across publications

This study stress-tests a ranking that nobody measured. Six independent publications report IC50 values for captopril-derived NDM-1 inhibitors, each using its own assay. Pooling those numbers and sorting them is the obvious thing to do, and it is the baseline here. The question is whether the resulting order survives the fact that the publications disagree about the one compound they all have in common.

D-captopril is that compound. Three of the six studies report it, at **7.9, 20.1 and 21.8 µM** — a 2.76-fold disagreement about the same molecule. Any apparent potency difference smaller than that is indistinguishable from which paper you happened to read.

The hypothesis is that the pooled ranking is not stable under cross-study calibration. A result where the naive order survived nearly every draw, or where compounds held narrow rank intervals, would disprove it.

## Method

Each draw rescales every study by an anchor value, so potency is expressed relative to D-captopril rather than in raw µM:

- A study that reports D-captopril is divided by its own reported value, jittered within an assumed 2-fold assay error. The anchor compound is that same single measurement, so after calibration it is exactly 1 by construction, not an independent draw.
- A study that never reports D-captopril cannot be calibrated at all. Its anchor is imputed log-uniformly across the observed 7.9–21.8 µM range, which is the honest width of that ignorance.
- Where the source reports two values for one compound, the draw picks between them.

Rankings are then compared to the naive pooled order by Kendall tau. The control is a permutation null: the same comparison against a random shuffle, which shows what agreement looks like by chance.

## Source

Values are transcribed from the tables and results text of Jarrar, *ADMET & DMPK* 14 (2026) (doi [10.5599/admet.3304](https://doi.org/10.5599/admet.3304), [PMC13499674](https://pmc.ncbi.nlm.nih.gov/articles/PMC13499674/), CC BY), a review that collected IC50 values for captopril-derived NDM-1 inhibitors and grouped the studies by assay format. The six primary studies it compiles are Ma et al. 2021 (ref 38, imipenem spectrophotometric), Brem et al. (39, kinetic), Li et al. (40, prescreen then dose response), Meng et al. (41, fluorocillin fluorogenic), Alfano et al. (42, fluorocillin fluorogenic) and Kondratieva et al. (43, meropenem spectrophotometric).

```sh
python3 research/run.py research/studies/ndm-ranking/sensitivity.py \
  --input research/studies/ndm-ranking/ic50_by_study.csv \
  --output .ws/results/ndm-ranking-42.json --seed 42
```

## What the seed 42 run found

The ranking is better than chance but not stable. Kendall tau against the naive order averaged 0.72 across 2000 draws (range 0.50 to 0.89), while the permutation null averaged 0.00 (range -0.41 to 0.44). So the published numbers do carry real signal — they are nowhere near random — but they do not support a fixed order.

**The top is robust, the middle is not.** Compounds 14a and 14m (Meng) and (2R,2'R)-5aC (Kondratieva) never left the top four in any draw. The naive winner, 14a at 0.10 µM, kept first place in 1208 of 2000 draws; 14m took it in 743 and 5aC in 49. That contest is an artefact of precision: 14a and 14m are reported at 0.10 and 0.12 µM, a difference far below any plausible assay error.

Mid-table ordering carries almost no information. Compound 7 (Ma) ranged from 4th to 20th across draws, compound 21 (Li) from 5th to 21st, and compound 32 (Li) from 7th to 22nd. A reader of the pooled table would see these as settled positions; they are not.

**The most uncomfortable finding is which studies cannot be calibrated.** The three studies reporting the most potent compounds — Meng, Alfano and Kondratieva — are exactly the three that never report D-captopril. Their position in any pooled ranking rests entirely on an imputed anchor. The compounds that look best are the ones whose calibration is least knowable.

## What this cannot establish

This is a stress test of published numbers, not new measurement. It cannot say which compound is actually most potent, and nothing here is evidence about treating an infection. Rank instability means the literature does not settle an ordering; it does not mean any particular compound is weak.

The endpoints come from a review's compilation rather than re-extraction from each primary paper, so transcription errors in the review propagate here. The review is already internally inconsistent in one place, reporting Ma's compound 3 at both 6.9 and 6.8 µM; the model samples between the two rather than picking one. The 2-fold assay error is a stated assumption, not a measured error model — the sources give no common one, and a different choice would widen or narrow every interval. Treating the anchor spread as the range for imputation assumes unanchored studies resemble anchored ones, which is unverifiable and probably optimistic, since differing assay formats are the reason the anchor disagrees in the first place.

Censored endpoints (reported only as greater than a bound: Ma compound 10, Kondratieva 5bE, Brem epi-L-captopril, Li compounds 9 and 26) are excluded from ranking rather than imputed, so the analysis covers the 22 compounds with point estimates.

A proper next step is to re-extract the endpoints from the six primary papers, recording each assay's substrate, enzyme concentration and preincubation time, and to test whether a shared reference compound measured under one protocol reproduces the ordering.

[Baseline output for seed 42](baseline.json) · [Run receipt](baseline.json.run.json)
