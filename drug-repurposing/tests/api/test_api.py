from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from api.schemas import DISCLAIMER
from tests.api.conftest import make_settings


def test_health(offline_client):
    r = offline_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["disclaimer"] == DISCLAIMER


def test_diseases_search(offline_client):
    r = offline_client.get("/diseases", params={"q": "diab"})
    assert r.json() == [{"disease_id": "MONDO:1", "name": "Type 2 diabetes"}]
    assert len(offline_client.get("/diseases").json()) == 4
    assert offline_client.get("/diseases", params={"q": "zzz"}).json() == []


def test_candidates_ranked_with_paths(offline_client):
    r = offline_client.get("/diseases/MONDO:1/candidates", params={"k": 2})
    body = r.json()
    assert r.status_code == 200
    assert body["disclaimer"] == DISCLAIMER
    assert body["disease"]["name"] == "Type 2 diabetes"
    cands = body["candidates"]
    assert [c["drug_name"] for c in cands] == ["Metformin", "Sildenafil"]
    assert cands[0]["method_scores"] == {"proximity": 0.8, "gnn": 0.7}
    first = cands[0]["paths"][0]
    assert [n["kind"] for n in first["nodes"]] == ["Compound", "Gene", "Disease"]
    assert first["edges"] == ["Compound-binds-Gene", "Gene-associates-Disease"]
    assert cands[0]["trials_search_url"].startswith("https://clinicaltrials.gov/")
    assert cands[0]["papers_search_url"].startswith("https://pubmed.ncbi.nlm.nih.gov/")


def test_four_hop_path_found(offline_client):
    body = offline_client.get("/diseases/MONDO:4/candidates").json()
    aspirin = next(c for c in body["candidates"] if c["drug_name"] == "Aspirin")
    kinds = [n["kind"] for n in aspirin["paths"][0]["nodes"]]
    assert kinds == ["Compound", "Gene", "Gene", "Disease"]
    assert len(aspirin["paths"][0]["edges"]) == 3


def test_paths_prefer_short_and_bounded(offline_client):
    body = offline_client.get("/diseases/MONDO:4/candidates").json()
    metformin = next(c for c in body["candidates"] if c["drug_name"] == "Metformin")
    assert len(metformin["paths"][0]["nodes"]) == 4
    assert len(metformin["paths"]) <= 3


def test_no_evidence_candidate(offline_client):
    body = offline_client.get("/diseases/MONDO:3/candidates").json()
    cand = body["candidates"][0]
    assert cand["paths"] == []
    assert cand["trials"] == [] and cand["papers"] == []
    assert body["disclaimer"] == DISCLAIMER


def test_unknown_disease_404_has_disclaimer(offline_client):
    r = offline_client.get("/diseases/NOPE/candidates")
    assert r.status_code == 404
    assert r.json()["disclaimer"] == DISCLAIMER


def test_k_validation(offline_client):
    assert offline_client.get("/diseases/MONDO:1/candidates", params={"k": 0}).status_code == 422
    assert offline_client.get("/diseases/MONDO:1/candidates", params={"k": 101}).status_code == 422


def test_live_evidence_and_cache(tmp_path: Path, mock_network):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as c:
        body = c.get("/diseases/MONDO:1/candidates", params={"k": 1}).json()
        assert body["evidence_live"] is True
        cand = body["candidates"][0]
        assert cand["trials"][0] == {
            "nct_id": "NCT0001",
            "title": "A trial",
            "status": "RECRUITING",
            "url": "https://clinicaltrials.gov/study/NCT0001",
        }
        assert cand["papers"][0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/111/"
        n_calls = len(mock_network)
        again = c.get("/diseases/MONDO:1/candidates", params={"k": 1}).json()
        assert len(mock_network) == n_calls
        assert again["candidates"][0]["trials"] == cand["trials"]
        assert again["evidence_live"] is False


def test_network_failure_degrades(tmp_path: Path, block_network):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        r = c.get("/diseases/MONDO:1/candidates")
        assert r.status_code == 200
        body = r.json()
        assert body["evidence_live"] is False
        assert body["candidates"][0]["trials"] == []
        assert body["candidates"][0]["paths"]


def test_network_failure_serves_stale_cache(tmp_path: Path, monkeypatch, mock_network):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as c:
        c.get("/diseases/MONDO:1/candidates", params={"k": 1})
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", boom)
    with TestClient(create_app(settings)) as c:
        body = c.get("/diseases/MONDO:1/candidates", params={"k": 1}).json()
        assert body["candidates"][0]["trials"][0]["nct_id"] == "NCT0001"


def test_missing_artifacts_degrade(tmp_path: Path):
    with TestClient(create_app(make_settings(tmp_path, offline=True, graph=False))) as c:
        h = c.get("/health").json()
        assert h["status"] == "degraded"
        assert c.get("/diseases").json() == []
        r = c.get("/diseases/MONDO:1/candidates")
        assert r.status_code == 503
        assert "disclaimer" in r.json()
