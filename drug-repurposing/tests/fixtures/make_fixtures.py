from pathlib import Path

import pandas as pd

OUT = Path(__file__).parent
GRAPH = OUT / "graph"
RESULTS = OUT / "results"

NODES = [
    (0, "Compound", "DB001", "Metformin"),
    (1, "Compound", "DB002", "Sildenafil"),
    (2, "Compound", "DB003", "Aspirin"),
    (3, "Gene", "G1", "PRKAA1"),
    (4, "Gene", "G2", "PDE5A"),
    (5, "Gene", "G3", "MTOR"),
    (6, "Gene", "G4", "PTGS2"),
    (7, "Disease", "MONDO:1", "Type 2 diabetes"),
    (8, "Disease", "MONDO:2", "Pulmonary hypertension"),
    (9, "Disease", "MONDO:3", "Orphan syndrome"),
    (10, "Disease", "MONDO:4", "Breast cancer"),
]
EDGES = [
    (0, 3, "Compound-binds-Gene"),
    (3, 7, "Gene-associates-Disease"),
    (3, 5, "Gene-interacts-Gene"),
    (5, 10, "Gene-associates-Disease"),
    (1, 4, "Compound-binds-Gene"),
    (4, 8, "Gene-associates-Disease"),
    (2, 6, "Compound-binds-Gene"),
    (6, 5, "Gene-interacts-Gene"),
    (0, 7, "Compound-treats-Disease"),
]
CANDS = [
    (7, 0, 0.9, 0.8, 0.7),
    (7, 1, 0.4, 0.3, 0.5),
    (7, 2, 0.2, 0.1, 0.3),
    (8, 1, 0.95, 0.9, 0.9),
    (8, 0, 0.3, 0.2, 0.4),
    (10, 0, 0.6, 0.5, 0.6),
    (10, 2, 0.5, 0.4, 0.5),
    (9, 2, 0.1, 0.1, 0.2),
]


def main() -> None:
    GRAPH.mkdir(exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    nodes = pd.DataFrame(NODES, columns=["node_id", "kind", "ext_id", "name"])
    nodes["source"] = "fixture"
    nodes["source_version"] = "0"
    nodes.to_parquet(GRAPH / "nodes.parquet", index=False)
    edges = pd.DataFrame(EDGES, columns=["src", "dst", "etype"])
    edges["source"] = "fixture"
    edges["source_version"] = "0"
    edges["weight"] = 1.0
    edges.to_parquet(GRAPH / "edges.parquet", index=False)
    cands = pd.DataFrame(CANDS, columns=["disease_node", "drug_node", "score", "proximity", "gnn"])
    cands.to_parquet(RESULTS / "candidates.parquet", index=False)


if __name__ == "__main__":
    main()
