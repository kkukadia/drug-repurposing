from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from tests.api.conftest import make_settings


def neo_settings(tmp_path: Path, server: dict[str, str]) -> Settings:
    base = make_settings(tmp_path, offline=True, graph=False)
    return Settings(
        graph_dir=base.graph_dir,
        candidates_path=base.candidates_path,
        cache_dir=base.cache_dir,
        offline=True,
        http_timeout=base.http_timeout,
        max_paths=base.max_paths,
        max_path_search_nodes=base.max_path_search_nodes,
        neo4j_uri=server["uri"],
        neo4j_user=server["user"],
        neo4j_password=server["password"],
    )


@pytest.fixture
def client(tmp_path, neo4j_server, loaded):
    with TestClient(create_app(neo_settings(tmp_path, neo4j_server))) as c:
        yield c


@pytest.fixture
def memory_client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path, offline=True))) as c:
        yield c


def test_health_reports_neo4j(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["backend"] == "neo4j"
    assert body["n_diseases"] == 4


def test_diseases_match_memory(client, memory_client):
    assert client.get("/diseases?q=a").json() == memory_client.get("/diseases?q=a").json()


def test_candidates_match_memory(client, memory_client):
    a = client.get("/diseases/MONDO:4/candidates?k=5").json()
    b = memory_client.get("/diseases/MONDO:4/candidates?k=5").json()
    assert a == b
    assert a["candidates"][0]["paths"]


def test_candidates_404(client):
    r = client.get("/diseases/nope/candidates")
    assert r.status_code == 404
    assert "disclaimer" in r.json()


def test_graph_endpoint_matches_memory(client, memory_client):
    a = client.get("/diseases/MONDO:4/graph?k=2").json()
    b = memory_client.get("/diseases/MONDO:4/graph?k=2").json()
    assert a == b
    assert a["disclaimer"]
    roles = {n["role"] for n in a["nodes"]}
    assert {"disease", "predicted", "gene"} <= roles


def test_graph_endpoint_404(client):
    assert client.get("/diseases/nope/graph").status_code == 404


def test_graph_endpoint_validates_k(client):
    assert client.get("/diseases/MONDO:1/graph?k=0").status_code == 422
    assert client.get("/diseases/MONDO:1/graph?k=999").status_code == 422


def test_unreachable_neo4j_degrades(tmp_path, neo4j_server):
    broken = neo_settings(tmp_path, {**neo4j_server, "uri": "bolt://127.0.0.1:1"})
    with TestClient(create_app(broken)) as c:
        body = c.get("/health").json()
        assert body["status"] == "degraded"
        assert c.get("/diseases/MONDO:1/candidates").status_code == 503
