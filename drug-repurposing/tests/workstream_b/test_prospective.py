import json

import httpx
import pandas as pd

from eval.prospective import evaluate_pairs, render_table, run, select_pairs
from ingest import common
from ingest.clinicaltrials import ClinicalTrialsClient
from ingest.pubmed import PubMedClient


def make_candidates() -> pd.DataFrame:
    rows = []
    for d in range(4):
        for r in range(1, 9):
            rows.append(
                {
                    "disease_node": 100 + d,
                    "drug_node": 10 * d + r,
                    "score": 1.0 - 0.1 * r,
                    "rank": r,
                    "drug_name": f"drug{10 * d + r}",
                    "disease_name": f"disease{d}",
                }
            )
    return pd.DataFrame(rows)


def make_ind() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "drug_node": [1, 2, 11, 21, 22, 23, 31],
            "disease_node": [100, 100, 101, 102, 102, 102, 103],
        }
    )


def test_select_pairs_excludes_known_and_picks_busiest_diseases():
    cands = make_candidates()
    ind = make_ind()
    sel = select_pairs(cands, ind, n_diseases=2, per_disease=3)
    assert set(sel["disease_node"]) == {102, 100}
    assert (sel.groupby("disease_node").size() == 3).all()
    known = set(zip(ind["drug_node"], ind["disease_node"]))
    assert not (set(zip(sel["drug_node"], sel["disease_node"])) & known)
    first = sel[sel["disease_node"] == 100]
    assert list(first["drug_node"]) == [3, 4, 5]


def make_clients(tmp_path, trial_hits, paper_counts):
    def handler(request: httpx.Request) -> httpx.Response:
        if "clinicaltrials" in request.url.host:
            drug = request.url.params["query.intr"]
            n = trial_hits.get(drug, 0)
            studies = [
                {
                    "protocolSection": {
                        "identificationModule": {"nctId": f"NCT{i}", "briefTitle": "t"},
                        "statusModule": {"overallStatus": "RECRUITING"},
                    }
                }
                for i in range(n)
            ]
            return httpx.Response(200, json={"studies": studies})
        term = request.url.params["term"]
        drug = term.split('"')[1]
        count = paper_counts.get(drug, 0)
        return httpx.Response(200, json={"esearchresult": {"count": str(count), "idlist": []}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    limiter = common.RateLimiter(0)
    return (
        ClinicalTrialsClient(tmp_path / "ct", client=http, limiter=limiter),
        PubMedClient(tmp_path / "pm", client=http, limiter=limiter),
    )


def test_evaluate_pairs_flags_evidence(tmp_path):
    sel = select_pairs(make_candidates(), make_ind(), n_diseases=1, per_disease=3)
    ct, pm = make_clients(tmp_path, {"drug25": 2}, {"drug26": 7, "drug24": 1})
    res = evaluate_pairs(sel, ct, pm, min_papers=3)
    by = {r["drug"]: r for r in res}
    assert len(res) == 3
    assert by["drug24"]["supported"] is False
    assert by["drug25"]["trials"] == 2 and by["drug25"]["supported"] is True
    assert by["drug26"]["papers"] == 7 and by["drug26"]["supported"] is True
    assert all(r["review_status"] == "needs manual review" for r in res)


def test_evaluate_pairs_records_errors(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    limiter = common.RateLimiter(0)
    ct = ClinicalTrialsClient(tmp_path / "ct", client=http, limiter=limiter)
    pm = PubMedClient(tmp_path / "pm", client=http, limiter=limiter)
    sel = select_pairs(make_candidates(), make_ind(), n_diseases=1, per_disease=1)
    res = evaluate_pairs(sel, ct, pm, retries=2, backoff=0)
    assert res[0]["error"] is not None and res[0]["supported"] is None


def test_run_writes_json_and_table(tmp_path):
    cands = tmp_path / "c.parquet"
    make_candidates().to_parquet(cands)
    ind_dir = tmp_path / "graph"
    ind_dir.mkdir()
    make_ind().to_parquet(ind_dir / "indications.parquet")
    ct, pm = make_clients(tmp_path, {"drug3": 1}, {})
    out = tmp_path / "p.json"
    summary = run(cands, ind_dir, out, ct, pm, n_diseases=2, per_disease=3)
    data = json.loads(out.read_text())
    assert data["n_pairs"] == 6 and data["n_supported"] == summary["n_supported"] == 1
    assert abs(data["share_supported"] - 1 / 6) < 1e-9
    assert "not evidence of clinical validity" in data["disclaimer"].lower()
    table = render_table(data)
    assert "needs manual review" in table
    assert table.count("\n") >= 7


def test_evaluate_pairs_retries_rate_limit(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "clinicaltrials" in request.url.host:
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(429)
            return httpx.Response(200, json={"studies": []})
        return httpx.Response(200, json={"esearchresult": {"count": "0", "idlist": []}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    limiter = common.RateLimiter(0)
    ct = ClinicalTrialsClient(tmp_path / "ct", client=http, limiter=limiter)
    pm = PubMedClient(tmp_path / "pm", client=http, limiter=limiter)
    sel = select_pairs(make_candidates(), make_ind(), n_diseases=1, per_disease=1)
    res = evaluate_pairs(sel, ct, pm, retries=4, backoff=0)
    assert res[0]["error"] is None and res[0]["trials"] == 0 and calls["n"] == 3
