from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from eval.run_benchmark import DEFAULT_CFG, build_scorers
from models.ensemble import EnsembleScorer, normalize
from models.graph_data import GraphData, load_graph, load_indications

METHOD_COLUMNS = ["proximity", "signature", "transe", "complex", "gnn"]


def load_weights(path: Path) -> dict[str, float]:
    if path.exists():
        res = json.loads(path.read_text())
        rows = res.get("stages", {}).get("random", {}).get("ensemble_weights", [])
        if rows:
            return {m: float(np.mean([r[m] for r in rows])) for m in METHOD_COLUMNS}
    return {m: 1.0 / len(METHOD_COLUMNS) for m in METHOD_COLUMNS}


def export(
    graph: GraphData,
    ind: pd.DataFrame,
    weights: dict[str, float],
    top_k: int,
    seed: int,
    cfg: dict,
    exclude_known: bool = True,
) -> pd.DataFrame:
    scorers = build_scorers(cfg)
    ens = EnsembleScorer(scorers, weights)
    ens.fit(graph, ind, seed)
    known: dict[int, set[int]] = {}
    for d, c in zip(ind["disease_node"], graph.comp_index[ind["drug_node"].to_numpy()]):
        known.setdefault(int(d), set()).add(int(c))
    names = graph.nodes.set_index("node_id")["name"]
    frames = []
    for d in graph.disease_nodes:
        comps = {m: normalize(scorers[m].score(int(d))) for m in METHOD_COLUMNS}
        total = np.zeros(graph.n_compounds)
        for m in METHOD_COLUMNS:
            total += weights[m] * comps[m]
        mask = np.ones(len(total), dtype=bool)
        if exclude_known and int(d) in known:
            mask[list(known[int(d)])] = False
        idx = np.flatnonzero(mask)
        top = idx[np.argsort(-total[idx], kind="stable")[:top_k]]
        df = pd.DataFrame(
            {
                "disease_node": np.full(len(top), int(d), dtype=np.int64),
                "drug_node": graph.compound_nodes[top],
                "score": total[top],
                **{m: comps[m][top] for m in METHOD_COLUMNS},
                "rank": np.arange(1, len(top) + 1),
            }
        )
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["drug_name"] = out["drug_node"].map(names)
    out["disease_name"] = out["disease_node"].map(names)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="data/graph")
    ap.add_argument("--benchmark", default="data/results/benchmark.json")
    ap.add_argument("--out", default="data/results/candidates.parquet")
    ap.add_argument("--top-k", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--kge-epochs", type=int, default=DEFAULT_CFG["kge_epochs"])
    args = ap.parse_args()
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    cfg["kge_epochs"] = args.kge_epochs
    graph = load_graph(args.graph)
    ind = load_indications(args.graph)
    weights = load_weights(Path(args.benchmark))
    out = export(graph, ind, weights, args.top_k, args.seed, cfg)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    print(f"wrote {len(out)} rows for {out['disease_node'].nunique()} diseases to {args.out}")


if __name__ == "__main__":
    main()
