from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from eval.evaluate import evaluate_scorer
from eval.metrics import seed_ci
from eval.splits import (
    apply_split,
    known_positives,
    make_split,
    popularity,
    sample_negatives,
)
from models.ensemble import EnsembleScorer
from models.gnn import GNNScorer
from models.graph_data import GraphData, load_graph, load_indications, read_manifest
from models.kge import KGEScorer
from models.proximity import ProximityScorer
from models.signature import SignatureScorer

STAGES = {
    "random": ("random", "Stage 1: random hold-out"),
    "time": ("time", "Stage 2: time split"),
    "cold_disease": ("cold_disease", "Stage 3: cold-start disease"),
    "repurposing": ("repurposing", "Stage 4: known repurposings"),
}
BASELINES = ["proximity", "signature", "transe", "complex"]
METHODS = BASELINES + ["gnn"]
NEG_RATIO = 10
REQUIRED_SEEDS = 5
DEFAULT_CFG: dict[str, Any] = {
    "kge_epochs": 20,
    "kge_dim": 64,
    "gnn": {"hidden": 64, "layers": 2, "lr": 3e-3, "dropout": 0.2, "mp_frac": 0.5},
}


def build_scorers(cfg: dict) -> dict:
    return {
        "proximity": ProximityScorer(),
        "signature": SignatureScorer(),
        "transe": KGEScorer("TransE", dim=cfg["kge_dim"], epochs=cfg["kge_epochs"]),
        "complex": KGEScorer("ComplEx", dim=cfg["kge_dim"], epochs=cfg["kge_epochs"]),
        "gnn": GNNScorer(**cfg["gnn"]),
    }


def run_one(graph: GraphData, ind: pd.DataFrame, stage: str, seed: int, cfg: dict) -> dict:
    kind = STAGES[stage][0]
    split = make_split(ind, kind, seed)
    train_graph = apply_split(graph, split)
    known = known_positives(graph, ind)
    pop = popularity(graph, split.train)
    negatives = {
        s: sample_negatives(graph, split.test, known, NEG_RATIO, s, pop, 1000 + seed)
        for s in ("popularity", "uniform")
    }
    scorers = build_scorers(cfg)
    fit_seconds = {}
    for name, sc in scorers.items():
        t = time.time()
        sc.fit(train_graph, split.train, seed)
        fit_seconds[name] = time.time() - t
        print(f"[{stage} s{seed}] fit {name} {fit_seconds[name]:.1f}s", flush=True)
    ens = EnsembleScorer(scorers)
    ens.fit_weights(graph, split.val, split.all_pairs(), split.train, seed, ratio=NEG_RATIO)
    scorers_all = dict(scorers)
    scorers_all["ensemble"] = ens
    metrics = {}
    for name, sc in scorers_all.items():
        metrics[name] = evaluate_scorer(sc, graph, split.test, known, negatives)
    gnn = scorers["gnn"]
    return {
        "stage": stage,
        "seed": seed,
        "metrics": metrics,
        "ensemble_weights": ens.weights,
        "ensemble_val_auprc": ens.val_auprc,
        "fit_seconds": fit_seconds,
        "gnn": {k: v for k, v in gnn.info.items() if k != "history"},
        "kge_final_loss": {n: float(scorers[n].losses[-1]) for n in ("transe", "complex")},
        "split": {
            "n_train": len(split.train),
            "n_val": len(split.val),
            "n_test": len(split.test),
            "n_test_diseases": int(split.test["disease_node"].nunique()),
            "n_test_drugs": int(split.test["drug_node"].nunique()),
            "cutoff_year": split.cutoff_year,
            "removal": split.removal_stats,
        },
        "signature_coverage_test": float(
            np.mean(
                [scorers["signature"].has_signature(int(d)) for d in split.test["disease_node"]]
            )
        ),
    }


def aggregate(parts: list[dict], cfg: dict, manifest: dict) -> dict:
    out: dict = {
        "config": cfg,
        "negative_ratio": NEG_RATIO,
        "graph_build": manifest.get("build_timestamp"),
    }
    stages: dict = {}
    for stage in STAGES:
        runs = sorted([p for p in parts if p["stage"] == stage], key=lambda p: p["seed"])
        if not runs:
            continue
        methods = list(runs[0]["metrics"])
        agg = {}
        for m in methods:
            keys = runs[0]["metrics"][m].keys()
            agg[m] = {k: seed_ci([r["metrics"][m][k] for r in runs]) for k in keys}
        best = max(BASELINES, key=lambda m: agg[m]["auprc_popularity"]["mean"])
        diffs = [
            100 * (r["metrics"]["gnn"]["auprc_popularity"] - r["metrics"][best]["auprc_popularity"])
            for r in runs
        ]
        stages[stage] = {
            "seeds": [r["seed"] for r in runs],
            "metrics": agg,
            "per_seed": {m: [r["metrics"][m] for r in runs] for m in methods},
            "best_baseline_auprc": best,
            "gnn_minus_best_baseline_auprc_points": seed_ci(diffs),
            "ensemble_weights": [r["ensemble_weights"] for r in runs],
            "fit_seconds": {
                m: seed_ci([r["fit_seconds"][m] for r in runs])["mean"] for m in METHODS
            },
            "gnn_info": [r["gnn"] for r in runs],
            "kge_final_loss": [r["kge_final_loss"] for r in runs],
            "split": [r["split"] for r in runs],
            "signature_coverage_test": seed_ci([r["signature_coverage_test"] for r in runs])[
                "mean"
            ],
        }
    out["stages"] = stages
    return out


def fmt(ci: dict, scale: float = 1.0) -> str:
    if np.isnan(ci["mean"]):
        return "n/a"
    return f"{ci['mean'] * scale:.3f} [{ci['lo'] * scale:.3f}, {ci['hi'] * scale:.3f}]"


def run_notes(res: dict) -> list[str]:
    cfg = res["config"]
    g = {**DEFAULT_CFG["gnn"], **cfg["gnn"]}
    counts = {st: len(v["seeds"]) for st, v in res["stages"].items()}
    counts_txt = ", ".join(f"{st}: {n}" for st, n in counts.items())
    short = [st for st, n in counts.items() if n < REQUIRED_SEEDS]
    L = ["## Run notes", ""]
    if short:
        L.append(
            f"- Seed counts: {counts_txt}. Stages {short} are below the required "
            f"{REQUIRED_SEEDS} seeds, so their intervals are wider than intended."
        )
    else:
        L.append(
            f"- Seed counts: {counts_txt}. Every stage meets the required {REQUIRED_SEEDS} seeds."
        )
    L += [
        f"- KGE: TransE and ComplEx, dim {cfg['kge_dim']}, {cfg['kge_epochs']} epochs, CPU. "
        "The candidate export uses the same epochs.",
        f"- GNN: {g['layers']}-layer heterogeneous GraphSAGE, hidden {g['hidden']}, lr "
        f"{g['lr']}, dropout {g['dropout']}, mp_frac {g['mp_frac']}. Hyperparameters are "
        "identical across stages and no configuration was tuned on test pairs. Early "
        "stopping uses an inner subset of the training pairs.",
        "- GNN unseen compounds: the free compound embedding is zeroed for compounds with no "
        "training indications and randomly dropped (p=0.3) for seen compounds during "
        "training, mirroring the unseen-disease handling. Unseen compounds are represented "
        "by structural degree features and message passing only. All parts in this report "
        "were generated with this model code.",
    ]
    if "time" in res["stages"]:
        d = res["stages"]["time"]["gnn_minus_best_baseline_auprc_points"]
        verdict = "beats" if d["lo"] > 0 else "does not clearly beat"
        L.append(
            f"- Time split: with unseen-compound masking the GNN {verdict} the best baseline "
            f"({res['stages']['time']['best_baseline_auprc']}): {d['mean']:+.1f} AUPRC points "
            f"[{d['lo']:+.1f}, {d['hi']:+.1f}]. Before masking it was -8.6 points on 4 seeds."
        )
    if "random" in res["stages"]:
        d = res["stages"]["random"]["gnn_minus_best_baseline_auprc_points"]
        ok = "meets" if d["mean"] >= 5 else "does not meet"
        L.append(
            f"- Stage 1: GNN minus best baseline is {d['mean']:+.1f} points "
            f"[{d['lo']:+.1f}, {d['hi']:+.1f}], which {ok} the 5-point AUPRC target."
        )
    L.append("")
    return L


def write_report(res: dict, path: Path, prospective: dict | None = None) -> None:
    L = ["# Benchmark report", ""]
    L += [
        f"Graph build: {res.get('graph_build')}. "
        "All values are mean over seeds with a 95% t-interval in brackets. Per-seed raw numbers "
        "are in `data/results/benchmark.json`.",
        "",
        "## Protocol",
        "",
        "Every scorer ranks all compounds for a disease. Test pairs are ranked with filtered "
        "ranking: every other known indication of the same disease (train, validation, test) is "
        "removed from the candidate list, and ties are broken by mean rank.",
        "",
        "AUROC and AUPRC are computed on pooled (disease, compound) pairs: each test positive "
        f"is paired with {res['negative_ratio']} sampled negatives for the same disease.",
        "",
        "### Negative sampling",
        "",
        "- `popularity` (headline): the replacement compound is drawn with probability "
        "proportional to its number of training indications plus one, never a known positive for "
        "that disease. This removes most of the advantage of simply predicting drugs that treat "
        "many diseases.",
        "- `uniform` (reported for comparison): replacement compound drawn uniformly, never a "
        "known positive. Random negatives overstate performance, so these numbers are secondary.",
        "- Unlabelled pairs are treated as negatives; some are undiscovered true indications, "
        "which biases all methods equally.",
        "- Sampling is seeded and independent of any model.",
        "",
        "### Leakage controls",
        "",
        "- Every validation and test pair is removed from the training graph in every edge type "
        "and both directions (treats, palliates, reverse treated-by and any other Compound-Disease "
        "edge between the pair).",
        "- Indirect duplicates: non-label Compound-Disease edges linking a held-out drug "
        "to a "
        "disease adjacent (Disease-Disease edge, e.g. resembles) to the held-out disease "
        "are removed.",
        "- Cold-start: all Compound-Disease edges of held-out diseases are removed. "
        "The GNN also "
        "zeroes the free embedding of any disease absent from the training labels.",
        "- Time split: test pairs are the pairs with the latest `year`; pairs without a "
        "year stay in "
        "training. Held-out years are never seen in training.",
        "- Ensemble weights are fit on validation pairs only; test pairs are never "
        "used for "
        "weights, early stopping or any selection.",
        "- GNN early stopping uses a 10% inner subset of the training pairs, not "
        "validation or test.",
        "- During GNN training, training Compound-treats-Disease edges are split each step into "
        "message-passing edges and supervision targets so a positive is never in its "
        "own receptive "
        "field.",
        "",
    ]
    for stage, (_, title) in STAGES.items():
        if stage not in res["stages"]:
            continue
        s = res["stages"][stage]
        sp = s["split"]
        L += [f"## {title}", ""]
        rem = int(np.mean([x["removal"]["removed_total"] for x in sp]))
        desc = (
            f"train/val/test pairs (seed 0): {sp[0]['n_train']}/{sp[0]['n_val']}/"
            f"{sp[0]['n_test']}; "
            f"test diseases: {sp[0]['n_test_diseases']}, test drugs: {sp[0]['n_test_drugs']}; "
            f"leaking edges removed per run (mean): {rem}."
        )
        if sp[0]["cutoff_year"] is not None:
            cut = sp[0]["cutoff_year"]
            desc += f" Test cutoff year: {cut} (test = year >= cutoff)."
        desc += f" Seeds: {s['seeds']}."
        L += [desc, ""]
        L += [
            "| Method | AUROC (pop. neg.) | AUPRC (pop. neg.) | AUPRC (uniform neg.) | Hits@20 | "
            "MRR | Recall@50 |",
            "|---|---|---|---|---|---|---|",
        ]
        for m, v in s["metrics"].items():
            L.append(
                f"| {m} | {fmt(v['auroc_popularity'])} | {fmt(v['auprc_popularity'])} | "
                f"{fmt(v['auprc_uniform'])} | {fmt(v['hits@20'])} | {fmt(v['mrr'])} | "
                f"{fmt(v['recall@50'])} |"
            )
        d = s["gnn_minus_best_baseline_auprc_points"]
        L += [
            "",
            f"GNN minus best baseline ({s['best_baseline_auprc']}) on AUPRC (pop. neg.): "
            f"{d['mean']:+.1f} points [{d['lo']:+.1f}, {d['hi']:+.1f}].",
            "",
            f"Signature coverage of test diseases: {100 * s['signature_coverage_test']:.0f}%.",
            "",
        ]
        gi = s["gnn_info"]
        L += [
            f"GNN: mean best epoch {np.mean([g['best_epoch'] for g in gi]):.0f}, mean epochs run "
            f"{np.mean([g['epochs_run'] for g in gi]):.0f}, early-stopped (converged) in "
            f"{sum(bool(g['converged']) for g in gi)}/{len(gi)} runs.",
            "",
        ]
    L += [
        "## Caveats",
        "",
        "- `year` is each drug's first FDA approval, not the indication's year (ADR 0002). "
        "The time split therefore measures drug age: held-out drugs are mostly unseen in "
        "training. "
        "It is a cold-drug split, not a pure repurposing time split.",
        "- Hetionet has few labelled indications (755), so test sets are small and intervals wide, "
        "especially for cold-start diseases.",
        "- Hetionet side-effect, similarity and pharmacologic-class edges can partly encode "
        "indication information; they are kept as legitimate graph structure.",
        "- Stage 4 holds out, for each drug with two or more indications, its latest-year (else "
        "random) indication, and measures recall of that second indication within the top 50.",
        "- Stage 5 (prospective check) lives in `eval/prospective.py`.",
        "",
    ]
    L += run_notes(res)
    if prospective is not None:
        from eval.prospective import render_table

        L += ["## Stage 5: prospective check", "", render_table(prospective), ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="data/graph")
    ap.add_argument("--out", default="data/results")
    ap.add_argument("--report", default="docs/benchmark-report.md")
    ap.add_argument("--stages", nargs="+", default=list(STAGES))
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    ap.add_argument("--aggregate-only", action="store_true")
    ap.add_argument("--kge-epochs", type=int, default=DEFAULT_CFG["kge_epochs"])
    args = ap.parse_args()
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    cfg["kge_epochs"] = args.kge_epochs
    out = Path(args.out)
    parts_dir = out / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    if not args.aggregate_only:
        graph = load_graph(args.graph)
        ind = load_indications(args.graph)
        for stage in args.stages:
            for seed in args.seeds:
                f = parts_dir / f"{stage}_{seed}.json"
                if f.exists():
                    continue
                res = run_one(graph, ind, stage, seed, cfg)
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(res, default=float))
                tmp.replace(f)
    parts = [json.loads(f.read_text()) for f in sorted(parts_dir.glob("*.json"))]
    manifest = read_manifest(args.graph)
    res = aggregate(parts, cfg, manifest)
    (out / "benchmark.json").write_text(json.dumps(res, indent=1, default=float))
    pro_path = out / "prospective.json"
    pro = json.loads(pro_path.read_text()) if pro_path.exists() else None
    write_report(res, Path(args.report), pro)


if __name__ == "__main__":
    main()
