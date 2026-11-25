from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from ingest import common
from ingest.clinicaltrials import ClinicalTrialsClient
from ingest.pubmed import PubMedClient

REVIEW = "needs manual review"
DISCLAIMER = (
    "Automated literature and trial hits are not evidence of clinical validity. A hit means a "
    "registered trial or papers mentioning both terms exist; it says nothing about efficacy, "
    "direction of effect or safety. Every pair needs manual review."
)


def select_pairs(
    candidates: pd.DataFrame, ind: pd.DataFrame, n_diseases: int, per_disease: int
) -> pd.DataFrame:
    known = set(zip(ind["drug_node"].astype(int), ind["disease_node"].astype(int)))
    keep = [
        (int(c), int(d)) not in known
        for c, d in zip(candidates["drug_node"], candidates["disease_node"])
    ]
    new = candidates[keep]
    n_known = ind.groupby("disease_node").size()
    diseases = sorted(
        new["disease_node"].unique(),
        key=lambda d: (-int(n_known.get(d, 0)), int(d)),
    )[:n_diseases]
    parts = []
    for d in diseases:
        sub = new[new["disease_node"] == d].sort_values("rank").head(per_disease)
        parts.append(sub)
    return pd.concat(parts, ignore_index=True)


def with_retry(fn: Callable[[], Any], retries: int, backoff: float) -> Any:
    for attempt in range(retries):
        try:
            return fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (429, 500, 502, 503) or attempt == retries - 1:
                raise
            time.sleep(backoff * (attempt + 1))


def evaluate_pairs(
    pairs: pd.DataFrame,
    trials: ClinicalTrialsClient,
    papers: PubMedClient,
    min_papers: int = 3,
    min_trials: int = 1,
    retries: int = 5,
    backoff: float = 15.0,
) -> list[dict[str, Any]]:
    out = []
    for row in pairs.itertuples():
        drug, disease = str(row.drug_name), str(row.disease_name)
        rec: dict[str, Any] = {
            "disease": disease,
            "drug": drug,
            "disease_node": int(row.disease_node),
            "drug_node": int(row.drug_node),
            "rank": int(row.rank),
            "score": float(row.score),
            "trials": None,
            "papers": None,
            "nct_ids": [],
            "supported": None,
            "error": None,
            "review_status": REVIEW,
        }
        try:
            payload = with_retry(partial(trials.search, drug, disease), retries, backoff)
            studies = payload.get("studies", [])
            rec["trials"] = len(studies)
            rec["nct_ids"] = [
                s["protocolSection"]["identificationModule"]["nctId"] for s in studies[:5]
            ]
            rec["papers"] = with_retry(
                partial(papers.comention_count, drug, disease), retries, backoff
            )
            rec["supported"] = bool(rec["trials"] >= min_trials or rec["papers"] >= min_papers)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            rec["error"] = f"{type(exc).__name__}: {exc}"
            rec["supported"] = None
        out.append(rec)
    return out


def summarise(records: list[dict[str, Any]], min_papers: int, min_trials: int) -> dict[str, Any]:
    ok = [r for r in records if r["supported"] is not None]
    n_sup = sum(1 for r in ok if r["supported"])
    return {
        "n_pairs": len(records),
        "n_evaluated": len(ok),
        "n_supported": n_sup,
        "share_supported": n_sup / len(ok) if ok else float("nan"),
        "n_with_trials": sum(1 for r in ok if r["trials"] >= min_trials),
        "n_with_papers": sum(1 for r in ok if r["papers"] >= min_papers),
        "criteria": {
            "min_trials": min_trials,
            "min_papers": min_papers,
            "trial_query": "ClinicalTrials.gov v2, intervention=drug and condition=disease",
            "paper_query": "PubMed title/abstract co-mention of drug and disease",
        },
        "review_status": REVIEW,
        "disclaimer": DISCLAIMER,
        "pairs": records,
    }


def run(
    candidates_path: Path,
    graph_dir: Path,
    out: Path,
    trials: ClinicalTrialsClient,
    papers: PubMedClient,
    n_diseases: int = 10,
    per_disease: int = 3,
    min_papers: int = 3,
    min_trials: int = 1,
) -> dict[str, Any]:
    cands = pd.read_parquet(candidates_path)
    ind = pd.read_parquet(Path(graph_dir) / "indications.parquet")
    pairs = select_pairs(cands, ind, n_diseases, per_disease)
    records = evaluate_pairs(pairs, trials, papers, min_papers, min_trials)
    summary = summarise(records, min_papers, min_trials)
    summary["selection"] = {
        "n_diseases": n_diseases,
        "per_disease": per_disease,
        "rule": "diseases with the most known indications; top-ranked non-known candidates",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1))
    return summary


def render_table(data: dict[str, Any]) -> str:
    lines = [
        f"Pairs checked: {data['n_evaluated']} of {data['n_pairs']}. Pairs with a trial or "
        f"{data['criteria']['min_papers']}+ co-mentioning papers: {data['n_supported']} "
        f"({100 * data['share_supported']:.0f}%). Trials alone: {data['n_with_trials']}, "
        f"papers alone: {data['n_with_papers']}.",
        "",
        data["disclaimer"],
        "",
        "| Disease | Candidate | Rank | Trials | PubMed co-mentions | Hit | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in data["pairs"]:
        hit = "n/a" if r["supported"] is None else ("yes" if r["supported"] else "no")
        trials = "n/a" if r["trials"] is None else r["trials"]
        papers = "n/a" if r["papers"] is None else r["papers"]
        lines.append(
            f"| {r['disease']} | {r['drug']} | {r['rank']} | {trials} | {papers} | {hit} | "
            f"{r['review_status']} |"
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default="data/results/candidates.parquet")
    ap.add_argument("--graph", default="data/graph")
    ap.add_argument("--out", default="data/results/prospective.json")
    ap.add_argument("--cache", default="data/cache/prospective")
    ap.add_argument("--n-diseases", type=int, default=10)
    ap.add_argument("--per-disease", type=int, default=3)
    args = ap.parse_args()
    cache = Path(args.cache)
    summary = run(
        Path(args.candidates),
        Path(args.graph),
        Path(args.out),
        ClinicalTrialsClient(cache / "ct", limiter=common.RateLimiter(2.0)),
        PubMedClient(cache / "pm"),
        args.n_diseases,
        args.per_disease,
    )
    print(
        f"{summary['n_supported']}/{summary['n_evaluated']} pairs with supporting hits "
        f"(needs manual review)"
    )


if __name__ == "__main__":
    main()
