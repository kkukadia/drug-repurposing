from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

TREATS = "Compound-treats-Disease"
COMPOUND = "Compound"
DISEASE = "Disease"
GENE = "Gene"


@dataclass
class GraphData:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    kinds: np.ndarray
    compound_nodes: np.ndarray
    disease_nodes: np.ndarray
    gene_nodes: np.ndarray
    comp_index: np.ndarray

    @property
    def n_nodes(self) -> int:
        return len(self.kinds)

    @property
    def n_compounds(self) -> int:
        return len(self.compound_nodes)

    def with_edges(self, edges: pd.DataFrame) -> GraphData:
        return GraphData(
            self.nodes,
            edges.reset_index(drop=True),
            self.kinds,
            self.compound_nodes,
            self.disease_nodes,
            self.gene_nodes,
            self.comp_index,
        )

    def kind_pair_edges(
        self, kind_a: str, kind_b: str, include_regulation: bool = False
    ) -> tuple[np.ndarray, np.ndarray]:
        e = self.edges
        if not include_regulation:
            e = e[~e["etype"].str.contains("-(?:up|down)regulates-", regex=True)]
        src = e["src"].to_numpy()
        dst = e["dst"].to_numpy()
        fwd = (self.kinds[src] == kind_a) & (self.kinds[dst] == kind_b)
        rev = (self.kinds[dst] == kind_a) & (self.kinds[src] == kind_b)
        a = np.concatenate([src[fwd], dst[rev]])
        b = np.concatenate([dst[fwd], src[rev]])
        if len(a) == 0:
            return a.astype(np.int64), b.astype(np.int64)
        pairs = np.unique(np.stack([a, b], axis=1), axis=0)
        return pairs[:, 0].astype(np.int64), pairs[:, 1].astype(np.int64)

    def signed_edges(self, kind: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        parts = []
        for sign, verb in ((1.0, "upregulates"), (-1.0, "downregulates")):
            e = self.edges[self.edges["etype"] == f"{kind}-{verb}-Gene"]
            parts.append((e["src"].to_numpy(), e["dst"].to_numpy(), np.full(len(e), sign)))
        return (
            np.concatenate([p[0] for p in parts]).astype(np.int64),
            np.concatenate([p[1] for p in parts]).astype(np.int64),
            np.concatenate([p[2] for p in parts]),
        )


class Scorer(Protocol):
    name: str

    def fit(self, graph: GraphData, train_pairs: pd.DataFrame, seed: int) -> Scorer: ...

    def score(self, disease_node: int) -> np.ndarray: ...


def build_graph(nodes: pd.DataFrame, edges: pd.DataFrame) -> GraphData:
    nodes = nodes.sort_values("node_id").reset_index(drop=True)
    kinds = nodes["kind"].to_numpy(dtype=object)
    ids = nodes["node_id"].to_numpy()
    comp = ids[kinds == COMPOUND]
    comp_index = np.full(len(kinds), -1, dtype=np.int64)
    comp_index[comp] = np.arange(len(comp))
    e = edges.copy()
    e["src"] = e["src"].astype(np.int64)
    e["dst"] = e["dst"].astype(np.int64)
    return GraphData(
        nodes,
        e.reset_index(drop=True),
        kinds,
        comp.astype(np.int64),
        ids[kinds == DISEASE].astype(np.int64),
        ids[kinds == GENE].astype(np.int64),
        comp_index,
    )


def load_graph(path: str | Path) -> GraphData:
    path = Path(path)
    return build_graph(
        pd.read_parquet(path / "nodes.parquet"), pd.read_parquet(path / "edges.parquet")
    )


def load_indications(path: str | Path) -> pd.DataFrame:
    df = pd.read_parquet(Path(path) / "indications.parquet")
    df = df.drop_duplicates(["drug_node", "disease_node"]).reset_index(drop=True)
    df["drug_node"] = df["drug_node"].astype(np.int64)
    df["disease_node"] = df["disease_node"].astype(np.int64)
    df["year"] = pd.array(df["year"], dtype="Int64") if "year" in df else pd.NA
    return df


def graph_ready(path: str | Path) -> bool:
    return (Path(path) / "manifest.json").exists()


def read_manifest(path: str | Path) -> dict:
    return json.loads((Path(path) / "manifest.json").read_text())
