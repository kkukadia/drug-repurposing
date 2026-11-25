from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from models.graph_data import GraphData, build_graph


def make_synthetic(
    out_dir: Path | None = None,
    seed: int = 0,
    n_compounds: int = 80,
    n_genes: int = 160,
    n_diseases: int = 50,
    n_modules: int = 8,
) -> tuple[GraphData, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n_side, n_anat = 6, 4
    kinds = (
        ["Compound"] * n_compounds
        + ["Gene"] * n_genes
        + ["Disease"] * n_diseases
        + ["SideEffect"] * n_side
        + ["Anatomy"] * n_anat
    )
    n = len(kinds)
    nodes = pd.DataFrame(
        {
            "node_id": np.arange(n),
            "kind": kinds,
            "ext_id": [f"X{i}" for i in range(n)],
            "name": [f"node{i}" for i in range(n)],
            "source": "synthetic",
            "source_version": "0",
        }
    )
    c0, g0, d0 = 0, n_compounds, n_compounds + n_genes
    s0 = d0 + n_diseases
    a0 = s0 + n_side
    gene_mod = rng.integers(0, n_modules, n_genes)
    comp_mod = [rng.choice(n_modules, size=2, replace=False) for _ in range(n_compounds)]
    dis_mod = rng.integers(0, n_modules, n_diseases)
    rows: list[tuple[int, int, str]] = []
    for c in range(n_compounds):
        pool = np.where(np.isin(gene_mod, comp_mod[c]))[0]
        for g in rng.choice(pool, size=min(len(pool), 5), replace=False):
            rows.append((c0 + c, g0 + int(g), "Compound-binds-Gene"))
    for d in range(n_diseases):
        pool = np.where(gene_mod == dis_mod[d])[0]
        for g in rng.choice(pool, size=min(len(pool), 8), replace=False):
            rows.append((g0 + int(g), d0 + d, "Gene-associates-Disease"))
    for i in range(n_genes):
        for j in range(i + 1, n_genes):
            p = 0.25 if gene_mod[i] == gene_mod[j] else 0.01
            if rng.random() < p:
                rows.append((g0 + i, g0 + j, "Gene-interacts-Gene"))
    for c in range(n_compounds):
        rows.append((c0 + c, s0 + int(rng.integers(0, n_side)), "Compound-causes-SideEffect"))
    for d in range(n_diseases):
        rows.append((d0 + d, a0 + int(rng.integers(0, n_anat)), "Disease-localizes-Anatomy"))
    inds = []
    for c in range(n_compounds):
        for d in range(n_diseases):
            overlap = dis_mod[d] in comp_mod[c]
            if rng.random() < (0.35 if overlap else 0.01):
                year = np.nan if rng.random() < 0.15 else float(rng.integers(1985, 2025))
                inds.append((c0 + c, d0 + d, year))
    ind = pd.DataFrame(inds, columns=["drug_node", "disease_node", "year"])
    ind["year"] = ind["year"].astype("Int64")
    ind["label_source"] = "synthetic"
    for dn, dd, _ in inds:
        rows.append((dn, dd, "Compound-treats-Disease"))
    for dn, dd, _ in inds[::5]:
        rows.append((dd, dn, "Disease-treated_by-Compound"))
    for d in range(0, n_diseases - 1, 7):
        rows.append((d0 + d, d0 + d + 1, "Disease-isa-Disease"))
    for d in range(n_diseases):
        genes = np.where(gene_mod == dis_mod[d])[0]
        for g in rng.choice(genes, size=min(len(genes), 6), replace=False):
            up = rng.random() < 0.5
            rows.append((d0 + d, g0 + int(g), f"Disease-{'up' if up else 'down'}regulates-Gene"))
            for c in range(n_compounds):
                if dis_mod[d] in comp_mod[c] and rng.random() < 0.5:
                    rows.append(
                        (c0 + c, g0 + int(g), f"Compound-{'down' if up else 'up'}regulates-Gene")
                    )
    edges = pd.DataFrame(rows, columns=["src", "dst", "etype"])
    edges["source"] = "synthetic"
    edges["source_version"] = "0"
    edges["weight"] = np.nan
    edges = edges.drop_duplicates(["src", "dst", "etype"]).reset_index(drop=True)
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        nodes.to_parquet(out_dir / "nodes.parquet")
        edges.to_parquet(out_dir / "edges.parquet")
        ind.to_parquet(out_dir / "indications.parquet")
        (out_dir / "manifest.json").write_text(json.dumps({"synthetic": True}))
    return build_graph(nodes, edges), ind
