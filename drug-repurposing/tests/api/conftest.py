from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def make_settings(tmp_path: Path, offline: bool = False, graph: bool = True) -> Settings:
    return Settings(
        graph_dir=FIX / "graph" if graph else tmp_path / "nograph",
        candidates_path=FIX / "results" / "candidates.parquet",
        cache_dir=tmp_path / "cache",
        offline=offline,
        http_timeout=1.0,
        max_paths=3,
        max_path_search_nodes=5000,
    )


@pytest.fixture
def offline_client(tmp_path: Path):
    with TestClient(create_app(make_settings(tmp_path, offline=True))) as c:
        yield c


@pytest.fixture
def block_network(monkeypatch: pytest.MonkeyPatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(httpx, "get", boom)


@pytest.fixture
def mock_network(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        req = httpx.Request("GET", url)
        body: dict[str, Any]
        if "clinicaltrials.gov" in url:
            body = {
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {"nctId": "NCT0001", "briefTitle": "A trial"},
                            "statusModule": {"overallStatus": "RECRUITING"},
                        }
                    }
                ]
            }
        elif "esearch" in url:
            body = {"esearchresult": {"idlist": ["111"]}}
        else:
            body = {"result": {"111": {"title": "A paper"}}}
        return httpx.Response(200, json=body, request=req)

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls
