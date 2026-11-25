import json
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from ingest import common

NAME = "ClinicalTrials.gov"
VERSION = "api-v2"
API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = "NCTId,BriefTitle,OverallStatus,StartDate"
STUDY_URL = "https://clinicaltrials.gov/study/"


def download(dest_dir: Path) -> Path:
    target = dest_dir / "clinicaltrials"
    target.mkdir(parents=True, exist_ok=True)
    return target


def start_year(study: dict[str, Any]) -> int | None:
    date = study.get("protocolSection", {}).get("statusModule", {}).get("startDateStruct", {})
    text = date.get("date")
    if not text:
        return None
    return int(text[:4])


def parse(path: Path) -> pd.DataFrame:
    studies = json.loads(path.read_text()).get("studies", [])
    rows = []
    for study in studies:
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        nct = ident.get("nctId", "")
        rows.append(
            {
                "nct_id": nct,
                "title": ident.get("briefTitle", ""),
                "status": proto.get("statusModule", {}).get("overallStatus", ""),
                "start_year": start_year(study),
                "url": STUDY_URL + nct,
            }
        )
    df = pd.DataFrame(rows, columns=["nct_id", "title", "status", "start_year", "url"])
    df["start_year"] = df.start_year.astype("Int64")
    return df


class ClinicalTrialsClient:
    def __init__(
        self,
        cache_dir: Path,
        client: httpx.Client | None = None,
        limiter: common.RateLimiter | None = None,
    ) -> None:
        self.cache = common.DiskCache(cache_dir)
        self.client = client or httpx.Client(timeout=60.0, follow_redirects=True)
        self.limiter = limiter or common.RateLimiter(0.4)

    def query(self, params: dict[str, str]) -> dict[str, Any]:
        key = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cached = self.cache.get(key)
        if cached is not None:
            return dict(cached)
        self.limiter.wait()
        response = self.client.get(API, params=params)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        self.cache.put(key, payload)
        return payload

    def search(
        self, drug: str, condition: str | None = None, page_size: int = 20
    ) -> dict[str, Any]:
        params = {"query.intr": drug, "pageSize": str(page_size), "fields": FIELDS}
        if condition:
            params["query.cond"] = condition
        return self.query(params)

    def earliest_start_year(self, drug: str) -> int | None:
        params = {
            "query.intr": drug,
            "pageSize": "1",
            "fields": "NCTId,StartDate",
            "sort": "StartDate:asc",
            "filter.advanced": "AREA[StartDate]RANGE[1900-01-01,MAX]",
        }
        studies = self.query(params).get("studies", [])
        if not studies:
            return None
        return start_year(studies[0])
