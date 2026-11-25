from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra

from models.graph_data import COMPOUND, DISEASE, GENE, GraphData


def _incidence(rows: np.ndarray, cols: np.ndarray, shape: tuple[int, int]) -> sp.csr_matrix:
    return sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=shape)


class ProximityScorer:
    name = "proximity"

    def __init__(self, cap: int = 6):
        self.cap = cap

    def fit(self, graph: GraphData, train_pairs: pd.DataFrame, seed: int) -> ProximityScorer:
        gene_index = np.full(graph.n_nodes, -1, dtype=np.int64)
        gene_index[graph.gene_nodes] = np.arange(len(graph.gene_nodes))
        ng = len(graph.gene_nodes)
        a, b = graph.kind_pair_edges(GENE, GENE)
        ppi = _incidence(gene_index[a], gene_index[b], (ng, ng))
        self.ppi = ((ppi + ppi.T) > 0).astype(np.float32).tocsr()
        c, g = graph.kind_pair_edges(COMPOUND, GENE)
        tgt = _incidence(graph.comp_index[c], gene_index[g], (graph.n_compounds, ng))
        tgt.data[:] = 1.0
        self.targets = tgt.tocsr()
        self.n_targets = np.asarray(self.targets.sum(axis=1)).ravel()
        d, g2 = graph.kind_pair_edges(DISEASE, GENE)
        self.disease_genes: dict[int, np.ndarray] = {}
        if len(d):
            order = np.argsort(d, kind="stable")
            d, g2 = d[order], g2[order]
            cuts = np.flatnonzero(np.diff(d)) + 1
            for dd, gg in zip(np.split(d, cuts), np.split(g2, cuts)):
                self.disease_genes[int(dd[0])] = gene_index[gg]
        self.n_compounds = graph.n_compounds
        return self

    def score(self, disease_node: int) -> np.ndarray:
        genes = self.disease_genes.get(int(disease_node))
        if genes is None or len(genes) == 0:
            return np.zeros(self.n_compounds)
        dist = dijkstra(
            self.ppi,
            directed=False,
            indices=genes,
            unweighted=True,
            limit=self.cap,
            min_only=True,
        )
        dist = np.where(np.isfinite(dist), dist, self.cap + 1.0)
        mean = (self.targets @ dist) / np.maximum(self.n_targets, 1.0)
        mean = np.where(self.n_targets > 0, mean, self.cap + 2.0)
        return -mean
