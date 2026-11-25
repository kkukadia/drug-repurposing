from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from eval.metrics import auprc
from eval.splits import known_positives, popularity, sample_negatives
from models.graph_data import GraphData, Scorer


def normalize(scores: np.ndarray) -> np.ndarray:
    n = len(scores)
    if n < 2 or np.ptp(scores) == 0:
        return np.full(n, 0.5)
    return (rankdata(scores, method="average") - 1.0) / (n - 1.0)


def weight_grid(n: int, step: float = 0.1) -> np.ndarray:
    k = int(round(1 / step))
    combos = [c for c in itertools.product(range(k + 1), repeat=n) if sum(c) == k]
    return np.array(combos, dtype=float) / k


class EnsembleScorer:
    name = "ensemble"

    def __init__(self, scorers: dict[str, Scorer], weights: dict[str, float] | None = None):
        self.scorers = scorers
        self.names = list(scorers)
        self.weights = weights or {n: 1.0 / len(scorers) for n in self.names}
        self._cache: dict[int, dict[str, np.ndarray]] = {}

    def fit(self, graph: GraphData, train_pairs: pd.DataFrame, seed: int) -> EnsembleScorer:
        for s in self.scorers.values():
            s.fit(graph, train_pairs, seed)
        return self

    def components(self, disease_node: int) -> dict[str, np.ndarray]:
        key = int(disease_node)
        if key not in self._cache:
            self._cache[key] = {n: normalize(s.score(key)) for n, s in self.scorers.items()}
        return self._cache[key]

    def clear_cache(self) -> None:
        self._cache.clear()

    def score(self, disease_node: int) -> np.ndarray:
        comp = self.components(disease_node)
        total = np.zeros(len(next(iter(comp.values()))))
        for n in self.names:
            total += self.weights[n] * comp[n]
        return total

    def fit_weights(
        self,
        graph: GraphData,
        val_pairs: pd.DataFrame,
        known_pairs: pd.DataFrame,
        train_pairs: pd.DataFrame,
        seed: int,
        ratio: int = 10,
        step: float = 0.1,
    ) -> dict[str, float]:
        known = known_positives(graph, known_pairs)
        pop = popularity(graph, train_pairs)
        neg = sample_negatives(graph, val_pairs, known, ratio, "popularity", pop, seed)
        pos_c = graph.comp_index[val_pairs["drug_node"].to_numpy()]
        pos_d = val_pairs["disease_node"].to_numpy()
        neg_c = graph.comp_index[neg["drug_node"].to_numpy()]
        neg_d = neg["disease_node"].to_numpy()
        feats: dict[str, np.ndarray] = {}
        y = np.concatenate([np.ones(len(pos_c)), np.zeros(len(neg_c))])
        cs = np.concatenate([pos_c, neg_c])
        ds = np.concatenate([pos_d, neg_d])
        for n in self.names:
            col = np.empty(len(cs))
            for d in np.unique(ds):
                m = ds == d
                col[m] = self.components(int(d))[n][cs[m]]
            feats[n] = col
        x = np.stack([feats[n] for n in self.names], axis=1)
        grid = weight_grid(len(self.names), step)
        best, best_w = -1.0, grid[0]
        for w in grid:
            val = auprc(y, x @ w)
            if val > best + 1e-12:
                best, best_w = val, w
        self.weights = {n: float(w) for n, w in zip(self.names, best_w)}
        self.val_auprc = best
        return self.weights
