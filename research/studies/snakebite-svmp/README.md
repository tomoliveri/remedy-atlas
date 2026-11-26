# Snakebite SVMP inhibitor response

This study fits a Hill inhibition model to published IC50 endpoints for six metalloproteinase inhibitors against two snake venom metalloproteinases, and asks which single agent reaches 90% inhibition of *both* toxins at the lowest concentration. That best single agent is the baseline. Each inhibitor pair is then compared against it under Bliss independence at an equal split of one total concentration, so the pair never gets more drug than the baseline.

The hypothesis is that no single agent is the most potent against both toxins, because the two enzymes rank the inhibitors differently. A result where one agent gave the lowest covering concentration for both toxins in most draws, or where no pair fell below the best single agent, would disprove it.

The CSV transcribes Table 1 of de Souza et al. in *ACS Omega*: IC50 values in µM with their reported ± spread, and the Hill coefficients from the same kinetic assays. The two toxins are Atroxlysin-I (Atr-I, hemorrhagic) and Leucurolysin-a (Leuc-a, non-hemorrhagic). The file contains only toxin names, inhibitor names and published aggregate endpoints. [Primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11684173/) (doi [10.1021/acsomega.4c08439](https://doi.org/10.1021/acsomega.4c08439), CC BY) · [Table 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC11684173/table/tbl1/)

From the repository root, run the study on your machine:

```sh
python3 research/run.py research/studies/snakebite-svmp/response.py \
  --input research/studies/snakebite-svmp/ic50.csv \
  --output .ws/results/snakebite-svmp-42.json --seed 42
```

Each run draws 2000 IC50 sets from the reported spreads and counts, per draw, which agent and which pair reached the threshold at the lowest concentration on a log-spaced grid from 0.001 to 100 µM.

## What the seed 42 run found

The two toxins do rank the inhibitors differently: CP471474 gave the lowest 90% concentration against Atr-I in 1882 of 2000 draws, while prinomastat did so against Leuc-a in 1969. Neither led on both. Covering both toxins at once, the mmp-III inhibitor gave the lowest concentration in 1757 draws, ahead of prinomastat (456) and CP471474 (117). Marimastat, the inhibitor furthest along in snakebite development, never led on either toxin or on both.

Ranking by IC50 alone reverses here. CP471474 has a lower IC50 than the mmp-III inhibitor against both toxins, but its Hill coefficient against Leuc-a is 0.55, so its curve is shallow and the concentration needed for 90% inhibition is far above its IC50. At the 50% threshold the ranking would differ. This is a property of the fitted curves, not a new measurement.

Pairs beat the best single agent often: CP471474 with prinomastat fell below it in 1958 of 2000 draws, marimastat with prinomastat in 1830, and batimastat with prinomastat in 1806. Pairs of two agents that are both weak against the same toxin did not (CP471474 with batimastat, 0 draws).

## What this cannot establish

These are IC50 values against two purified, isolated enzymes in a fluorogenic peptide assay. They are not measurements of whole venom neutralisation, and nothing here is evidence that any of these drugs helps an envenomed person. The counts describe draws from the stated assumptions and carry no clinical probability or treatment recommendation.

Bliss independence is an assumption, not a measurement: the paper reports no combination data, so every pair result is a prediction from two single-agent curves. Real combinations can be synergistic or antagonistic. The Hill model is extrapolated past the published endpoint to the 90% threshold, where the fit is least constrained, and the reported ± spread is treated as a Gaussian standard deviation, which is a stand-in for the confidence intervals the paper reports. Two toxins from two species cannot speak for venom variation across snakes or regions.

A proper next step uses measured two-drug checkerboard data against the same toxins to test the Bliss predictions directly, one pair at a time.

[Baseline output for seed 42](baseline.json) · [Run receipt](baseline.json.run.json)
