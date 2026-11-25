from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp

from models.graph_data import COMPOUND, DISEASE, GraphData


def _signed(graph: GraphData, kind: str, node_index: np.ndarray, n_rows: int, n_genes: int):
    s, g, sign = graph.signed_edges(kind)
    gene_index = np.full(graph.n_nodes, -1, dtype=np.int64)
    gene_index[graph.gene_nodes] = np.arange(len(graph.gene_nodes))
    rows = node_index[s]
    ok = rows >= 0
    mat = sp.csr_matrix((sign[ok], (rows[ok], gene_index[g[ok]])), shape=(n_rows, n_genes))
    mat.sum_duplicates()
    mat.data = np.sign(mat.data)
    mat.eliminate_zeros()
    return mat


class SignatureScorer:
    name = "signature"

    def fit(self, graph: GraphData, train_pairs: pd.DataFrame, seed: int) -> SignatureScorer:
        ng = len(graph.gene_nodes)
        disease_index = np.full(graph.n_nodes, -1, dtype=np.int64)
        disease_index[graph.disease_nodes] = np.arange(len(graph.disease_nodes))
        self.disease_index = disease_index
        comp = _signed(graph, COMPOUND, graph.comp_index, graph.n_compounds, ng)
        dis = _signed(graph, DISEASE, disease_index, len(graph.disease_nodes), ng)
        df = np.asarray((comp != 0).sum(axis=0)).ravel()
        idf = np.log((1.0 + graph.n_compounds) / (1.0 + df)) + 1.0
        scale = sp.diags(np.sqrt(idf))
        comp_w = (comp @ scale).tocsr()
        dis_w = (dis @ scale).tocsr()
        cn = np.sqrt(np.asarray(comp_w.multiply(comp_w).sum(axis=1)).ravel())
        dn = np.sqrt(np.asarray(dis_w.multiply(dis_w).sum(axis=1)).ravel())
        self.comp = sp.diags(1.0 / np.maximum(cn, 1e-12)) @ comp_w
        self.dis = sp.diags(1.0 / np.maximum(dn, 1e-12)) @ dis_w
        self.n_compounds = graph.n_compounds
        return self

    def has_signature(self, disease_node: int) -> bool:
        i = self.disease_index[int(disease_node)]
        return bool(i >= 0 and self.dis[i].nnz > 0)

    def score(self, disease_node: int) -> np.ndarray:
        i = self.disease_index[int(disease_node)]
        if i < 0 or self.dis[i].nnz == 0:
            return np.zeros(self.n_compounds)
        cos = self.comp @ self.dis[i].T
        return -np.asarray(cos.todense()).ravel()
