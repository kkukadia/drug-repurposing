import json
from pathlib import Path

import httpx

from ingest import common, pubmed

FIX = Path(__file__).parent.parent / "fixtures" / "pubmed"


def test_parse_efetch_xml() -> None:
    df = pubmed.parse(FIX / "efetch.xml")
    assert list(df.columns) == ["pmid", "title", "abstract", "year", "url"]
    assert len(df) == 2
    first = df.iloc[0]
    assert first.pmid == "111"
    assert first.abstract == "Aspirin may help. It works."
    assert first.year == 2015
    assert first.url == "https://pubmed.ncbi.nlm.nih.gov/111/"
    second = df.iloc[1]
    assert second.abstract == ""
    assert second.year == 2010


def make_api(tmp_path: Path, counter: list[str]) -> pubmed.PubMedClient:
    esearch = json.loads((FIX / "esearch.json").read_text())
    efetch = (FIX / "efetch.xml").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        counter.append(request.url.path)
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json=esearch)
        return httpx.Response(200, text=efetch)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return pubmed.PubMedClient(tmp_path, client=client, limiter=common.RateLimiter(0))


def test_comention_count_and_cache(tmp_path: Path) -> None:
    calls: list[str] = []
    api = make_api(tmp_path, calls)
    assert api.comention_count("aspirin", "breast cancer") == 42
    assert api.comention_count("aspirin", "breast cancer") == 42
    assert len(calls) == 1


def test_search_ids(tmp_path: Path) -> None:
    api = make_api(tmp_path, [])
    assert api.search_ids("aspirin", "breast cancer", retmax=2) == ["111", "222"]


def test_fetch_abstracts_cached(tmp_path: Path) -> None:
    calls: list[str] = []
    api = make_api(tmp_path, calls)
    df = api.fetch_abstracts(["111", "222"])
    assert len(df) == 2
    api.fetch_abstracts(["111", "222"])
    assert sum(c.endswith("efetch.fcgi") for c in calls) == 1


def test_download_creates_cache_dir(tmp_path: Path) -> None:
    out = pubmed.download(tmp_path)
    assert out.is_dir() and out.parent == tmp_path
