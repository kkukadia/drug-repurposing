# Benchmark report

Graph build: 2026-11-24T22:26:51Z. All values are mean over seeds with a 95% t-interval in brackets. Per-seed raw numbers are in `data/results/benchmark.json`.

## Protocol

Every scorer ranks all compounds for a disease. Test pairs are ranked with filtered ranking: every other known indication of the same disease (train, validation, test) is removed from the candidate list, and ties are broken by mean rank.

AUROC and AUPRC are computed on pooled (disease, compound) pairs: each test positive is paired with 10 sampled negatives for the same disease.

### Negative sampling

- `popularity` (headline): the replacement compound is drawn with probability proportional to its number of training indications plus one, never a known positive for that disease. This removes most of the advantage of simply predicting drugs that treat many diseases.
- `uniform` (reported for comparison): replacement compound drawn uniformly, never a known positive. Random negatives overstate performance, so these numbers are secondary.
- Unlabelled pairs are treated as negatives; some are undiscovered true indications, which biases all methods equally.
- Sampling is seeded and independent of any model.

### Leakage controls

- Every validation and test pair is removed from the training graph in every edge type and both directions (treats, palliates, reverse treated-by and any other Compound-Disease edge between the pair).
- Indirect duplicates: non-label Compound-Disease edges linking a held-out drug to a disease adjacent (Disease-Disease edge, e.g. resembles) to the held-out disease are removed.
- Cold-start: all Compound-Disease edges of held-out diseases are removed. The GNN also zeroes the free embedding of any disease absent from the training labels.
- Time split: test pairs are the pairs with the latest `year`; pairs without a year stay in training. Held-out years are never seen in training.
- Ensemble weights are fit on validation pairs only; test pairs are never used for weights, early stopping or any selection.
- GNN early stopping uses a 10% inner subset of the training pairs, not validation or test.
- During GNN training, training Compound-treats-Disease edges are split each step into message-passing edges and supervision targets so a positive is never in its own receptive field.

## Stage 1: random hold-out

train/val/test pairs (seed 0): 528/76/151; test diseases: 57, test drugs: 121; leaking edges removed per run (mean): 233. Seeds: [0, 1, 2, 3, 4].

| Method | AUROC (pop. neg.) | AUPRC (pop. neg.) | AUPRC (uniform neg.) | Hits@20 | MRR | Recall@50 |
|---|---|---|---|---|---|---|
| proximity | 0.641 [0.624, 0.657] | 0.135 [0.124, 0.146] | 0.136 [0.130, 0.142] | 0.013 [0.005, 0.021] | 0.007 [0.006, 0.007] | 0.052 [0.045, 0.059] |
| signature | 0.496 [0.470, 0.522] | 0.094 [0.084, 0.104] | 0.103 [0.086, 0.119] | 0.008 [0.001, 0.015] | 0.003 [0.002, 0.004] | 0.016 [0.003, 0.028] |
| transe | 0.675 [0.638, 0.712] | 0.167 [0.144, 0.190] | 0.226 [0.184, 0.267] | 0.087 [0.053, 0.122] | 0.025 [0.015, 0.036] | 0.168 [0.116, 0.221] |
| complex | 0.647 [0.622, 0.672] | 0.137 [0.124, 0.150] | 0.160 [0.139, 0.180] | 0.029 [0.010, 0.048] | 0.010 [0.005, 0.015] | 0.077 [0.045, 0.109] |
| gnn | 0.855 [0.827, 0.882] | 0.501 [0.439, 0.563] | 0.644 [0.588, 0.700] | 0.453 [0.372, 0.534] | 0.173 [0.137, 0.208] | 0.572 [0.495, 0.649] |
| ensemble | 0.841 [0.820, 0.861] | 0.423 [0.379, 0.468] | 0.589 [0.533, 0.645] | 0.366 [0.306, 0.426] | 0.125 [0.091, 0.159] | 0.514 [0.447, 0.580] |

GNN minus best baseline (transe) on AUPRC (pop. neg.): +33.4 points [+25.8, +41.0].

Signature coverage of test diseases: 67%.

GNN: mean best epoch 331, mean epochs run 379, early-stopped (converged) in 4/5 runs.

## Stage 2: time split

train/val/test pairs (seed 0): 587/42/126; test diseases: 45, test drugs: 91; leaking edges removed per run (mean): 174. Test cutoff year: 1999 (test = year >= cutoff). Seeds: [0, 1, 2, 3, 4].

| Method | AUROC (pop. neg.) | AUPRC (pop. neg.) | AUPRC (uniform neg.) | Hits@20 | MRR | Recall@50 |
|---|---|---|---|---|---|---|
| proximity | 0.703 [0.692, 0.714] | 0.173 [0.162, 0.183] | 0.175 [0.169, 0.180] | 0.032 [0.032, 0.032] | 0.010 [0.010, 0.010] | 0.079 [0.079, 0.079] |
| signature | 0.526 [0.521, 0.530] | 0.110 [0.105, 0.115] | 0.117 [0.111, 0.123] | 0.032 [0.032, 0.032] | 0.007 [0.007, 0.007] | 0.056 [0.056, 0.056] |
| transe | 0.584 [0.542, 0.625] | 0.119 [0.096, 0.142] | 0.157 [0.122, 0.193] | 0.037 [0.005, 0.068] | 0.009 [0.004, 0.015] | 0.078 [0.017, 0.139] |
| complex | 0.612 [0.566, 0.658] | 0.127 [0.103, 0.151] | 0.149 [0.124, 0.175] | 0.010 [0.001, 0.018] | 0.006 [0.004, 0.007] | 0.059 [0.023, 0.095] |
| gnn | 0.660 [0.641, 0.679] | 0.137 [0.121, 0.153] | 0.220 [0.180, 0.261] | 0.056 [0.011, 0.100] | 0.015 [0.008, 0.023] | 0.162 [0.108, 0.216] |
| ensemble | 0.781 [0.762, 0.800] | 0.251 [0.224, 0.278] | 0.305 [0.243, 0.366] | 0.103 [0.061, 0.145] | 0.036 [0.022, 0.049] | 0.206 [0.140, 0.273] |

GNN minus best baseline (proximity) on AUPRC (pop. neg.): -3.5 points [-5.4, -1.7].

Signature coverage of test diseases: 71%.

GNN: mean best epoch 331, mean epochs run 362, early-stopped (converged) in 2/5 runs.

## Stage 3: cold-start disease

train/val/test pairs (seed 0): 512/103/140; test diseases: 15, test drugs: 102; leaking edges removed per run (mean): 295. Seeds: [0, 1, 2, 3, 4].

| Method | AUROC (pop. neg.) | AUPRC (pop. neg.) | AUPRC (uniform neg.) | Hits@20 | MRR | Recall@50 |
|---|---|---|---|---|---|---|
| proximity | 0.647 [0.613, 0.681] | 0.140 [0.112, 0.169] | 0.140 [0.117, 0.163] | 0.017 [-0.001, 0.035] | 0.007 [0.004, 0.010] | 0.045 [0.030, 0.061] |
| signature | 0.517 [0.488, 0.547] | 0.103 [0.087, 0.119] | 0.112 [0.087, 0.136] | 0.012 [-0.005, 0.030] | 0.004 [0.001, 0.008] | 0.032 [0.009, 0.055] |
| transe | 0.681 [0.628, 0.733] | 0.181 [0.134, 0.228] | 0.239 [0.178, 0.299] | 0.096 [0.046, 0.147] | 0.030 [0.013, 0.047] | 0.183 [0.146, 0.221] |
| complex | 0.629 [0.556, 0.702] | 0.139 [0.117, 0.162] | 0.168 [0.142, 0.193] | 0.021 [0.011, 0.031] | 0.009 [0.005, 0.012] | 0.060 [0.032, 0.088] |
| gnn | 0.786 [0.711, 0.860] | 0.337 [0.255, 0.419] | 0.526 [0.434, 0.618] | 0.324 [0.263, 0.385] | 0.107 [0.086, 0.129] | 0.463 [0.327, 0.598] |
| ensemble | 0.770 [0.686, 0.855] | 0.315 [0.211, 0.419] | 0.504 [0.370, 0.637] | 0.300 [0.207, 0.392] | 0.089 [0.050, 0.128] | 0.425 [0.298, 0.552] |

GNN minus best baseline (transe) on AUPRC (pop. neg.): +15.6 points [+8.0, +23.2].

Signature coverage of test diseases: 61%.

GNN: mean best epoch 186, mean epochs run 246, early-stopped (converged) in 5/5 runs.

## Stage 4: known repurposings

train/val/test pairs (seed 0): 626/32/97; test diseases: 37, test drugs: 97; leaking edges removed per run (mean): 131. Seeds: [0, 1, 2, 3, 4].

| Method | AUROC (pop. neg.) | AUPRC (pop. neg.) | AUPRC (uniform neg.) | Hits@20 | MRR | Recall@50 |
|---|---|---|---|---|---|---|
| proximity | 0.631 [0.606, 0.655] | 0.130 [0.119, 0.142] | 0.129 [0.113, 0.145] | 0.012 [0.002, 0.023] | 0.006 [0.004, 0.007] | 0.041 [0.026, 0.057] |
| signature | 0.502 [0.475, 0.529] | 0.108 [0.101, 0.114] | 0.116 [0.105, 0.127] | 0.012 [-0.002, 0.026] | 0.004 [0.003, 0.005] | 0.035 [0.020, 0.050] |
| transe | 0.698 [0.672, 0.724] | 0.179 [0.143, 0.216] | 0.246 [0.178, 0.315] | 0.087 [0.040, 0.133] | 0.022 [0.013, 0.032] | 0.165 [0.122, 0.207] |
| complex | 0.682 [0.661, 0.704] | 0.154 [0.146, 0.163] | 0.192 [0.177, 0.207] | 0.041 [0.021, 0.061] | 0.011 [0.006, 0.015] | 0.101 [0.053, 0.149] |
| gnn | 0.850 [0.811, 0.890] | 0.439 [0.402, 0.475] | 0.625 [0.564, 0.686] | 0.396 [0.340, 0.452] | 0.147 [0.135, 0.158] | 0.538 [0.501, 0.575] |
| ensemble | 0.837 [0.792, 0.882] | 0.371 [0.328, 0.413] | 0.579 [0.492, 0.667] | 0.309 [0.284, 0.335] | 0.110 [0.100, 0.119] | 0.511 [0.468, 0.554] |

GNN minus best baseline (transe) on AUPRC (pop. neg.): +25.9 points [+20.3, +31.6].

Signature coverage of test diseases: 70%.

GNN: mean best epoch 240, mean epochs run 300, early-stopped (converged) in 5/5 runs.

## Caveats

- `year` is each drug's first FDA approval, not the indication's year (ADR 0002). The time split therefore measures drug age: held-out drugs are mostly unseen in training. It is a cold-drug split, not a pure repurposing time split.
- Hetionet has few labelled indications (755), so test sets are small and intervals wide, especially for cold-start diseases.
- Hetionet side-effect, similarity and pharmacologic-class edges can partly encode indication information; they are kept as legitimate graph structure.
- Stage 4 holds out, for each drug with two or more indications, its latest-year (else random) indication, and measures recall of that second indication within the top 50.
- Stage 5 (prospective check) lives in `eval/prospective.py`.

## Run notes

- Seed counts: random: 5, time: 5, cold_disease: 5, repurposing: 5. Every stage meets the required 5 seeds.
- KGE: TransE and ComplEx, dim 64, 20 epochs, CPU. The candidate export uses the same epochs.
- GNN: 2-layer heterogeneous GraphSAGE, hidden 64, lr 0.003, dropout 0.2, mp_frac 0.5. Hyperparameters are identical across stages and no configuration was tuned on test pairs. Early stopping uses an inner subset of the training pairs.
- GNN unseen compounds: the free compound embedding is zeroed for compounds with no training indications and randomly dropped (p=0.3) for seen compounds during training, mirroring the unseen-disease handling. Unseen compounds are represented by structural degree features and message passing only. All parts in this report were generated with this model code.
- Time split: with unseen-compound masking the GNN does not clearly beat the best baseline (proximity): -3.5 AUPRC points [-5.4, -1.7]. Before masking it was -8.6 points on 4 seeds.
- Stage 1: GNN minus best baseline is +33.4 points [+25.8, +41.0], which meets the 5-point AUPRC target.

## Stage 5: prospective check

Pairs checked: 30 of 30. Pairs with a trial or 3+ co-mentioning papers: 24 (80%). Trials alone: 18, papers alone: 19.

Automated literature and trial hits are not evidence of clinical validity. A hit means a registered trial or papers mentioning both terms exist; it says nothing about efficacy, direction of effect or safety. Every pair needs manual review.

| Disease | Candidate | Rank | Trials | PubMed co-mentions | Hit | Status |
|---|---|---|---|---|---|---|
| hypertension | Bisoprolol | 1 | 20 | 503 | yes | needs manual review |
| hypertension | Methyclothiazide | 2 | 0 | 46 | yes | needs manual review |
| hypertension | Acetylsalicylic acid | 3 | 20 | 421 | yes | needs manual review |
| hematologic cancer | Docetaxel | 1 | 20 | 1 | yes | needs manual review |
| hematologic cancer | Paclitaxel | 2 | 20 | 1 | yes | needs manual review |
| hematologic cancer | Topotecan | 3 | 20 | 0 | yes | needs manual review |
| asthma | Fluocinolone Acetonide | 1 | 0 | 0 | no | needs manual review |
| asthma | Cetirizine | 2 | 5 | 136 | yes | needs manual review |
| asthma | Desonide | 3 | 0 | 1 | no | needs manual review |
| breast cancer | Topotecan | 1 | 5 | 266 | yes | needs manual review |
| breast cancer | Busulfan | 2 | 6 | 34 | yes | needs manual review |
| breast cancer | Erlotinib | 3 | 20 | 392 | yes | needs manual review |
| coronary artery disease | Betaxolol | 1 | 0 | 6 | yes | needs manual review |
| coronary artery disease | Bisoprolol | 2 | 20 | 77 | yes | needs manual review |
| coronary artery disease | Fluvastatin | 3 | 10 | 78 | yes | needs manual review |
| epilepsy syndrome | Glyburide | 1 | 1 | 0 | yes | needs manual review |
| epilepsy syndrome | Amitriptyline | 2 | 2 | 0 | yes | needs manual review |
| epilepsy syndrome | Ethotoin | 3 | 0 | 0 | no | needs manual review |
| type 2 diabetes mellitus | Betaxolol | 1 | 0 | 1 | no | needs manual review |
| type 2 diabetes mellitus | Lisinopril | 2 | 14 | 36 | yes | needs manual review |
| type 2 diabetes mellitus | Bisoprolol | 3 | 3 | 13 | yes | needs manual review |
| prostate cancer | Procarbazine | 1 | 0 | 1 | no | needs manual review |
| prostate cancer | Idarubicin | 2 | 0 | 4 | yes | needs manual review |
| prostate cancer | Dexamethasone | 3 | 20 | 319 | yes | needs manual review |
| glaucoma | Irbesartan | 1 | 0 | 5 | yes | needs manual review |
| glaucoma | Lisinopril | 2 | 0 | 1 | no | needs manual review |
| glaucoma | Propranolol | 3 | 0 | 59 | yes | needs manual review |
| psoriasis | Methylprednisolone | 1 | 5 | 83 | yes | needs manual review |
| psoriasis | Mesalazine | 2 | 1 | 7 | yes | needs manual review |
| psoriasis | Budesonide | 3 | 0 | 17 | yes | needs manual review |
