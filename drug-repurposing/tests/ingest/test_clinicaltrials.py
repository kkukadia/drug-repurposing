import json
from pathlib import Path

import httpx

from ingest import clinicaltrials, common

FIX = Path(__file__).parent.parent / "fixtures" / "clinicaltrials" / "studies.json"


def test_parse_extracts_fields() -> None:
    df = clinicaltrials.parse(FIX)
    assert list(df.columns) == ["nct_id", "title", "status", "start_year", "url"]
    assert len(df) == 3
    row = df.iloc[0]
    assert row.nct_id == "NCT00000001"
    assert row.start_year == 2009
    assert row.url == "https://clinicaltrials.gov/study/NCT00000001"
    assert df.start_year.isna().sum() == 1


def make_client(payload: dict, counter: list[int]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        counter.append(1)
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_search_uses_disk_cache(tmp_path: Path) -> None:
    payload = json.loads(FIX.read_text())
    counter: list[int] = []
    api = clinicaltrials.ClinicalTrialsClient(
        tmp_path, client=make_client(payload, counter), limiter=common.RateLimiter(0)
    )
    first = api.search("aspirin")
    second = api.search("aspirin")
    assert first == second == payload
    assert len(counter) == 1
    api2 = clinicaltrials.ClinicalTrialsClient(
        tmp_path, client=make_client({}, counter), limiter=common.RateLimiter(0)
    )
    assert api2.search("aspirin") == payload
    assert len(counter) == 1


def test_earliest_start_year(tmp_path: Path) -> None:
    payload = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT1"},
                    "statusModule": {"startDateStruct": {"date": "1998-04"}},
                }
            }
        ]
    }
    api = clinicaltrials.ClinicalTrialsClient(
        tmp_path, client=make_client(payload, []), limiter=common.RateLimiter(0)
    )
    assert api.earliest_start_year("aspirin") == 1998


def test_earliest_start_year_none_when_no_studies(tmp_path: Path) -> None:
    api = clinicaltrials.ClinicalTrialsClient(
        tmp_path, client=make_client({"studies": []}, []), limiter=common.RateLimiter(0)
    )
    assert api.earliest_start_year("nothing") is None


def test_download_creates_cache_dir(tmp_path: Path) -> None:
    out = clinicaltrials.download(tmp_path)
    assert out.is_dir() and out.parent == tmp_path
