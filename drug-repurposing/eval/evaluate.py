from __future__ import annotations

import numpy as np
import pandas as pd

from eval.metrics import auprc, auroc, filtered_rank, ranking_summary
from models.graph_data import GraphData, Scorer


def evaluate_scorer(
    scorer: Scorer,
    graph: GraphData,
    test: pd.DataFrame,
    known: dict[int, np.ndarray],
    negatives: dict[str, pd.DataFrame],
) -> dict[str, float]:
    cache: dict[int, np.ndarray] = {}

    def scores(d: int) -> np.ndarray:
        if d not in cache:
            cache[d] = np.asarray(scorer.score(d), dtype=float)
        return cache[d]

    tc = graph.comp_index[test["drug_node"].to_numpy()]
    td = test["disease_node"].to_numpy()
    ranks = np.array(
        [filtered_rank(scores(int(d)), int(c), known.get(int(d))) for c, d in zip(tc, td)]
    )
    out = ranking_summary(ranks)
    out["n_test_pairs"] = float(len(test))
    out["n_test_diseases"] = float(len(np.unique(td)))
    pos = np.array([scores(int(d))[c] for c, d in zip(tc, td)])
    for name, neg in negatives.items():
        nc = graph.comp_index[neg["drug_node"].to_numpy()]
        nd = neg["disease_node"].to_numpy()
        ns = np.array([scores(int(d))[c] for c, d in zip(nc, nd)])
        y = np.concatenate([np.ones(len(pos)), np.zeros(len(ns))])
        s = np.concatenate([pos, ns])
        out[f"auroc_{name}"] = auroc(y, s)
        out[f"auprc_{name}"] = auprc(y, s)
    return out
