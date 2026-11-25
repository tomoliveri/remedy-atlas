# Cervical tumour response

This starter studies how a simple Hill viability model behaves when anchored to published drug-response measurements from cervical tumour organoids. The pipeline compares model responses to cisplatin, carboplatin and paclitaxel across the organoids as the unknown response-curve steepness varies. These assumptions generate a sensitivity analysis. CC50 values alone cannot identify the steepness or validate the simulated curves.

The CSV transcribes the three chemotherapy rows from Figure 3B of Seol et al. in *Journal of Gynecologic Oncology*. It contains reported CC50 values in µM. Blank cells preserve missing measurements. The file contains only organoid aliases, compound names and published aggregate endpoints. [Primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10157333/) · [Figure 3](https://www.ejgo.org/ViewImage.php?Type=F&afn=1114_JGO_34_3_e35&aid=760459&fn=jgo-34-e35-g003_1114JGO&id=F3)

From the repository root, run the starter on your machine:

```sh
python3 research/run.py research/studies/cervical/response.py \
  --input research/studies/cervical/cc50.csv \
  --output .ws/results/cervical-42.json --seed 42
```

Each pair reports how often its left or right drug had lower *simulated organoid viability* across the model grid. The counts describe draws from the stated assumptions. They carry no clinical probability or treatment recommendation. A proper next step uses independent published viability curves, one held-out model at a time, to compare prediction error against this baseline.

[Baseline output for seed 42](baseline.json) · [Run receipt](baseline.json.run.json)
