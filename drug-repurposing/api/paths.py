from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from api.schemas import PathNode, PathOut


@dataclass
class GraphIndex:
    kinds: dict[int, str]
    names: dict[int, str]
    ext_ids: dict[int, str]
    adj: dict[int, list[tuple[int, str]]]
    by_kind: dict[str, list[int]]

    @classmethod
    def build(cls, nodes: pd.DataFrame, edges: pd.DataFrame) -> "GraphIndex":
        kinds = dict(zip(nodes["node_id"].astype(int), nodes["kind"].astype(str)))
        names = dict(zip(nodes["node_id"].astype(int), nodes["name"].astype(str)))
        ext_ids = dict(zip(nodes["node_id"].astype(int), nodes["ext_id"].astype(str)))
        adj: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for src, dst, etype in zip(
            edges["src"].astype(int), edges["dst"].astype(int), edges["etype"].astype(str)
        ):
            adj[src].append((dst, etype))
            adj[dst].append((src, etype))
        by_kind: dict[str, list[int]] = defaultdict(list)
        for nid, kind in kinds.items():
            by_kind[kind].append(nid)
        return cls(kinds, names, ext_ids, dict(adj), dict(by_kind))

    def kind(self, node: int) -> str:
        return self.kinds.get(node, "Unknown")

    def to_path(self, nodes: list[int], etypes: list[str]) -> PathOut:
        return PathOut(
            nodes=[
                PathNode(kind=self.kind(n), name=self.names.get(n, str(n)), id=self.ext_ids.get(n))
                for n in nodes
            ],
            edges=etypes,
        )


def extract_paths(
    index: GraphIndex, drug: int, disease: int, max_paths: int = 3, max_visits: int = 5000
) -> list[PathOut]:
    if index.kind(disease) != "Disease":
        return []
    disease_genes: dict[int, str] = {}
    for gene, etype in index.adj.get(disease, []):
        if index.kind(gene) == "Gene":
            disease_genes.setdefault(gene, etype)
    drug_genes: dict[int, str] = {}
    for gene, etype in index.adj.get(drug, []):
        if index.kind(gene) == "Gene":
            drug_genes.setdefault(gene, etype)
    found: list[tuple[int, list[int], list[str]]] = []
    for g1, e1 in drug_genes.items():
        if g1 in disease_genes:
            found.append((2, [drug, g1, disease], [e1, disease_genes[g1]]))
    visits = 0
    seen: set[tuple[int, int]] = set()
    for g1, e1 in drug_genes.items():
        if visits > max_visits:
            break
        for g2, e2 in index.adj.get(g1, []):
            visits += 1
            if visits > max_visits:
                break
            if g2 == g1 or g2 == drug or g2 not in disease_genes or (g1, g2) in seen:
                continue
            if index.kind(g2) != "Gene":
                continue
            seen.add((g1, g2))
            found.append((3, [drug, g1, g2, disease], [e1, e2, disease_genes[g2]]))
    found.sort(key=lambda item: (item[0], tuple(index.names.get(n, "") for n in item[1])))
    return [index.to_path(n, e) for _, n, e in found[:max_paths]]
