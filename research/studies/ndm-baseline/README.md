# NDM-1 inhibitor potency baseline

How well do published NDM-1 inhibitor endpoints predict each other? This study builds the simplest honest baseline — predict a held-out compound's potency from the median of the others — and asks whether separating incompatible assay readouts improves it.

The hypothesis is that pooling endpoints across publications inflates held-out error, because the studies use different assays, and that grouping by the assay taxonomy the source review defines will recover accuracy. A result where separating by assay gave no improvement over pooling would disprove the second half of that.

It did. Grouping by assay readout made predictions slightly worse.

## Method

Every reported IC50 is converted to log10 µM. Three baselines are compared by leave-one-out cross-validation over the 22 point endpoints:

- **pooled, ignoring assay** — predict the median of all other endpoints. This is the control: what you get treating the literature as one pile of numbers.
- **by assay group** — predict the median of other endpoints sharing the source review's assay group (A fluorogenic, B spectrophotometric, C other).
- **by study** — predict the median of other endpoints from the same publication.

Error is mean absolute error in log10 units, which reads directly as a fold error. Where a held-out row's group would otherwise be empty, the prediction falls back to the full pool; this affects Alfano, the one study contributing a single endpoint.

Each grouped model is checked against a shuffled-label control: the same cross-validation with group labels randomly permuted 500 times, which shows what apparent improvement looks like when the grouping carries no information.

## Source

The 27 endpoints (22 point values, 5 censored and excluded) are transcribed from Jarrar, *ADMET & DMPK* 14 (2026) (doi [10.5599/admet.3304](https://doi.org/10.5599/admet.3304), [PMC13499674](https://pmc.ncbi.nlm.nih.gov/articles/PMC13499674/), CC BY), which compiles six primary studies of captopril-derived NDM-1 inhibitors: Ma et al. 2021 (imipenem spectrophotometric), Brem et al. (kinetic), Li et al. (prescreen then dose response), Meng et al. and Alfano et al. (fluorocillin fluorogenic), and Kondratieva et al. (meropenem spectrophotometric). The same transcription is used by the sensitivity study for this track, which asks a different question of it.

```sh
python3 research/run.py research/studies/ndm-baseline/baseline_model.py \
  --input research/studies/ndm-baseline/ic50_by_study.csv \
  --output .ws/results/ndm-baseline-42.json --seed 42
```

## What the seed 42 run found

**Published endpoints predict each other poorly.** The pooled baseline misses by 0.63 log10 on average — a factor of 4.2. The best model tested still misses by a factor of 3.4. Whatever else is true, a potency difference smaller than about three-fold between compounds measured in different papers is not distinguishable from the noise of the literature itself.

**The review's assay taxonomy does not explain the variance.** Grouping by assay group scored 0.69 log10, slightly *worse* than ignoring assay altogether (0.63), and sits inside its own shuffled-label control (mean 0.62, 5th-95th percentile 0.54-0.71). Random labels do about as well. Whatever separates these measurements, the three-way A/B/C readout split does not capture it.

**Study identity does carry signal.** Grouping by publication scored 0.53 log10, below the 5th percentile of its shuffled control (0.55), so the improvement is unlikely to be chance. Knowing which paper a number came from is worth roughly a 1.3-fold reduction in error.

## What this cannot establish

The study-level signal has a confound I cannot separate with this data: each publication tests its own series of structurally related analogues, so "same study" also means "similar chemistry". The error reduction may reflect that the compounds resemble each other, not that the assay calibration is shared. Distinguishing the two needs the same compounds measured across studies, which this dataset has for only one compound.

A median baseline is deliberately weak — it uses no structural information at all. A model with chemistry in it could do better, and the numbers here are a floor to beat, not a ceiling on what is knowable.

Twenty-two endpoints across six studies is small, and three studies contribute three or fewer. Leave-one-out error on that is noisy, and the shuffled control is what keeps the comparisons honest rather than any single number being precise. Endpoints come from a review's compilation, not re-extraction from the primary papers. Censored values (reported only as above a bound) are dropped rather than imputed, which discards the weakest compounds and so understates the full spread of potency.

Nothing here is evidence about treating an infection, and none of it identifies a better inhibitor.

[Baseline output for seed 42](baseline.json) · [Run receipt](baseline.json.run.json)
