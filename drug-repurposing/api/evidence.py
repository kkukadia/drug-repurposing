import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from api.schemas import PaperOut, TrialOut

log = logging.getLogger(__name__)

CT_URL = "https://clinicaltrials.gov/api/v2/studies"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def trials_search_url(drug: str, disease: str) -> str:
    return (
        "https://clinicaltrials.gov/search?cond=" f"{quote_plus(disease)}&intr={quote_plus(drug)}"
    )


def papers_search_url(drug: str, disease: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(f'{drug} AND {disease}')}"


class EvidenceClient:
    def __init__(self, cache_dir: Path, offline: bool = False, timeout: float = 6.0) -> None:
        self.cache_dir = cache_dir
        self.offline = offline
        self.timeout = timeout
        self.live_hits = 0
        self._eutils_lock = threading.Lock()
        self._eutils_last = 0.0
        self.eutils_interval = 0.4

    def _eutils_get(self, url: str, params: dict[str, Any]) -> httpx.Response:
        with self._eutils_lock:
            wait = self.eutils_interval - (time.monotonic() - self._eutils_last)
            if wait > 0:
                time.sleep(wait)
            try:
                return httpx.get(url, params=params, timeout=self.timeout)
            finally:
                self._eutils_last = time.monotonic()

    def _cache_file(self, kind: str, drug: str, disease: str) -> Path:
        digest = hashlib.sha256(f"{kind}|{drug.lower()}|{disease.lower()}".encode()).hexdigest()
        return self.cache_dir / f"{kind}-{digest[:24]}.json"

    def _read(self, path: Path) -> list[dict[str, Any]] | None:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return None
        return data if isinstance(data, list) else None

    def _write(self, path: Path, items: list[dict[str, Any]]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(items))
        except OSError as exc:
            log.warning("evidence cache write failed: %s", exc)

    def _cached_or_fetch(
        self, kind: str, drug: str, disease: str, fetch: Any
    ) -> list[dict[str, Any]]:
        path = self._cache_file(kind, drug, disease)
        cached = self._read(path)
        if cached is not None:
            return cached
        if self.offline:
            return []
        try:
            items: list[dict[str, Any]] = fetch()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("%s lookup failed for %s/%s: %s", kind, drug, disease, exc)
            return []
        self.live_hits += 1
        self._write(path, items)
        return items

    def trials(self, drug: str, disease: str, limit: int = 5) -> list[TrialOut]:
        def fetch() -> list[dict[str, Any]]:
            resp = httpx.get(
                CT_URL,
                params={
                    "query.cond": disease,
                    "query.intr": drug,
                    "pageSize": limit,
                    "format": "json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            out = []
            for study in resp.json().get("studies", []):
                ident = study["protocolSection"]["identificationModule"]
                status = study["protocolSection"].get("statusModule", {})
                nct = ident["nctId"]
                out.append(
                    {
                        "nct_id": nct,
                        "title": ident.get("briefTitle", nct),
                        "status": status.get("overallStatus", "UNKNOWN"),
                        "url": f"https://clinicaltrials.gov/study/{nct}",
                    }
                )
            return out

        return [TrialOut(**t) for t in self._cached_or_fetch("trials", drug, disease, fetch)]

    def papers(self, drug: str, disease: str, limit: int = 5) -> list[PaperOut]:
        def fetch() -> list[dict[str, Any]]:
            search = self._eutils_get(
                f"{EUTILS}/esearch.fcgi",
                {
                    "db": "pubmed",
                    "term": f'"{drug}" AND "{disease}"',
                    "retmax": limit,
                    "retmode": "json",
                },
            )
            search.raise_for_status()
            ids = search.json()["esearchresult"]["idlist"]
            if not ids:
                return []
            summ = self._eutils_get(
                f"{EUTILS}/esummary.fcgi",
                {"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            )
            summ.raise_for_status()
            result = summ.json()["result"]
            return [
                {
                    "pmid": pid,
                    "title": result.get(pid, {}).get("title", pid),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                }
                for pid in ids
            ]

        return [PaperOut(**p) for p in self._cached_or_fetch("papers", drug, disease, fetch)]
