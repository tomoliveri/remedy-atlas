# KPC / OXA-48 inhibitor potency transfer

This study asks whether a β-lactamase inhibitor's published potency against KPC tells you anything about its potency against OXA-48 when the two were measured in the same publication. It compares five predictors on held-out publications: two baselines that ignore the compound (a **pooled** mean over both enzymes, and an **enzyme-specific** mean for the target enzyme), and three that transfer the compound's measured potency from the other enzyme (unchanged, shifted by a fixed offset, or through a fitted line).

**Hypothesis, fixed before the run:** a compound's KPC potency carries information about its OXA-48 potency beyond the enzyme mean, so linear transfer beats the enzyme-specific baseline in leave-one-publication-out RMSE. **It is disproved** if the 95% publication-bootstrap interval of RMSE(linear) − RMSE(enzyme mean) does not lie entirely below zero.

## Input

`matched.csv` holds 254 IC50 and Ki measurements from ChEMBL 37 (released 2026-05-01, [CC BY-SA 3.0](https://chembl.gitbook.io/chembl-interface-documentation/about#data-licensing)). Each row is one published measurement with its ChEMBL activity, assay and document IDs and the DOI of the source paper. They cover 126 compound–endpoint pairs from 15 publications (2014–2024), including avibactam, vaborbactam, relebactam, taniborbactam, xeruborbactam and tazobactam alongside series compounds. A measurement is kept when:

- its assay description names exactly one of KPC or OXA-48;
- it is an IC50 or Ki in nM, reported as `=` or `>`;
- ChEMBL has not flagged its validity;
- the same compound (matched by its parent, so salts pair with parents), with the same endpoint, was measured against the other enzyme family in the same publication.

Replicates are averaged as p = 9 − log10(nM). Two documents are compiled reviews ([10.1021/acs.jmedchem.8b00091](https://doi.org/10.1021/acs.jmedchem.8b00091), [10.1016/j.ejmech.2022.114677](https://doi.org/10.1016/j.ejmech.2022.114677)). Their values come from other laboratories, so they are flagged `compiled_review` and used only in a sensitivity check.

To rebuild the input (curl and python3; network access to www.ebi.ac.uk only):

```sh
sh research/studies/kpc-oxa/fetch_chembl.sh chembl-raw
python3 research/studies/kpc-oxa/build_input.py chembl-raw research/studies/kpc-oxa/matched.csv
```

A later ChEMBL release may add rows. Compare against the input hash in the run receipt.

## Run

```sh
python3 research/run.py research/studies/kpc-oxa/transfer.py \
  --input research/studies/kpc-oxa/matched.csv \
  --output .ws/results/kpc-oxa-42.json --seed 42
```

It runs on the CPU in under a second. The seed drives a 2000-resample cluster bootstrap over held-out publications.

## What the seed 42 run found

Primary analysis: 108 pairs with exact values on both enzymes, from 13 primary publications, each held out in turn. RMSE is in log10 units (1.0 is a tenfold error).

| Predict OXA-48 from KPC | RMSE | MAE | RMSE − enzyme mean, 95% interval |
| --- | --- | --- | --- |
| pooled mean | 1.15 | 0.89 | −0.11 to +0.23 |
| enzyme mean (baseline) | 1.10 | 0.80 | — |
| identity (same potency) | 1.24 | 1.04 | −0.31 to +0.56 |
| offset | 1.08 | 0.91 | −0.43 to +0.39 |
| linear | 0.96 | 0.74 | −0.37 to +0.12 |

- **The hypothesis is not supported.** Linear transfer had the lowest error, and in 88% of bootstrap resamples it beat the enzyme-specific baseline. But the 95% interval crosses zero, so by the rule above the result does not establish transfer. Predicting KPC from OXA-48 gave the same picture: linear 1.03 against 1.20, interval −0.37 to +0.02.
- **The enzyme-specific baseline barely beats the pooled one** (1.10 against 1.15, interval crossing zero). Across all pairs, compounds were on average 0.72 log units (about fivefold) less potent against OXA-48 than against KPC. That shift is small next to the spread between compounds and papers.
- **Assuming equal potency is the worst predictor.** The identity model (RMSE 1.24) was worse than either baseline.
- **Ranks agree overall but not reliably within a paper.** The Spearman correlation between KPC and OXA-48 potency was 0.57 across all pairs. Within the eight publications with at least five pairs it ranged from −0.42 to 0.81. The pooled correlation is partly carried by differences between papers and series, not by compounds within a series.

Sensitivity checks, all in `baseline.json`:

| Check | Pairs (pubs) | Linear vs enzyme mean, OXA-48 target | 95% interval |
| --- | --- | --- | --- |
| Add compiled reviews | 111 (15) | 0.95 vs 1.09 | −0.37 to +0.11 |
| Add censored values at their bound | 120 (13) | 0.98 vs 1.21 | −0.44 to +0.08 |
| IC50 only | 83 (9) | 0.78 vs 0.95 | −0.34 to +0.01 |
| Ki only | 25 (4) | 1.58 vs 1.76 | −0.70 to +0.80 |

- **IC50 data come closest to supporting transfer.** Both directions sit at the edge of zero (−0.34 to +0.01, and −0.47 to +0.00 predicting KPC). Only one interval in the whole run falls fully below zero: predicting KPC from OXA-48 with censored values included (−0.44 to −0.01). That was one of several post hoc checks, so treat it as a lead, not a finding.
- **Ki data are too thin to say anything.** Four publications is not enough.
- **Censored values push the error up.** Including `>` values at their bound raised the baseline error (1.10 to 1.21) much more than the transfer error (0.96 to 0.98). Using the bound overstates the potency of weak compounds.

## What this cannot establish

- **Matched means same publication, not same conditions.** Two of the larger publications ([10.1021/acs.jmedchem.9b01518](https://doi.org/10.1021/acs.jmedchem.9b01518), [10.1021/acs.jmedchem.1c00437](https://doi.org/10.1021/acs.jmedchem.1c00437)) used imipenem as the KPC substrate and nitrocefin for OXA-48. Pre-incubation times differ between papers. IC50 depends on substrate and its concentration, so between-paper IC50s are not directly comparable, which is why the benchmark only pairs values within a paper.
- **The selection is not random.** Compounds were chosen for synthesis and reported by medicinal chemists, mostly from inhibitor series built to cover both enzymes. Inactive compounds are under-reported and often censored. This is not a random sample of chemistry.
- **Assays may be misattributed.** Enzyme labels come from assay description text. A wrongly described or wrongly assigned assay in ChEMBL would enter the data. One flagged class (ChEMBL data-validity comments) is excluded, and nothing else was hand-checked against the papers.
- **Variants are collapsed.** Every matched KPC measurement is against KPC-2. OXA-48-like variants such as OXA-181 and OXA-232 are not included, so the result says nothing about them.
- **This says nothing about patients.** These are purified-enzyme measurements. Nothing here bears on bacterial killing, combination with a β-lactam, pharmacokinetics or clinical outcome. Nothing here is a treatment recommendation.
- **The models are deliberately simple.** The linear model has one input. A structure-based or descriptor-based model might transfer better, and this benchmark is the baseline it should be judged against.

A useful next step is a held-out test on publications added after ChEMBL 37, plus the OXA-48-like variants, with the same leave-one-publication-out split.

[Baseline output for seed 42](baseline.json) · [Run receipt](baseline.json.run.json) · [Input](matched.csv)
