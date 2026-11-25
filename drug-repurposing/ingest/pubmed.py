import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from ingest import common

NAME = "PubMed"
VERSION = "e-utilities"
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
ARTICLE_URL = "https://pubmed.ncbi.nlm.nih.gov/"
INTERVAL = 0.35
BATCH = 100


def download(dest_dir: Path) -> Path:
    target = dest_dir / "pubmed"
    target.mkdir(parents=True, exist_ok=True)
    return target


def article_year(article: ET.Element) -> int | None:
    year = article.findtext(".//Article/Journal/JournalIssue/PubDate/Year")
    if year:
        return int(year)
    medline = article.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate")
    match = re.search(r"\d{4}", medline or "")
    return int(match.group()) if match else None


def parse_xml(text: str) -> pd.DataFrame:
    root = ET.fromstring(text)
    rows = []
    for article in root.iter("PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID") or ""
        title_node = article.find(".//Article/ArticleTitle")
        title = "".join(title_node.itertext()) if title_node is not None else ""
        parts = [
            "".join(node.itertext()).strip() for node in article.findall(".//Abstract/AbstractText")
        ]
        rows.append(
            {
                "pmid": pmid,
                "title": title,
                "abstract": " ".join(p for p in parts if p),
                "year": article_year(article),
                "url": ARTICLE_URL + pmid + "/",
            }
        )
    df = pd.DataFrame(rows, columns=["pmid", "title", "abstract", "year", "url"])
    df["year"] = df.year.astype("Int64")
    return df


def parse(path: Path) -> pd.DataFrame:
    return parse_xml(path.read_text())


def build_term(drug: str, disease: str) -> str:
    return f'"{drug}"[tiab] AND "{disease}"[tiab]'


class PubMedClient:
    def __init__(
        self,
        cache_dir: Path,
        client: httpx.Client | None = None,
        limiter: common.RateLimiter | None = None,
    ) -> None:
        self.cache = common.DiskCache(cache_dir)
        self.client = client or httpx.Client(timeout=60.0, follow_redirects=True)
        self.limiter = limiter or common.RateLimiter(INTERVAL)

    def esearch(self, term: str, retmax: int) -> dict[str, Any]:
        key = f"esearch|{term}|{retmax}"
        cached = self.cache.get(key)
        if cached is not None:
            return dict(cached)
        self.limiter.wait()
        response = self.client.get(
            BASE + "esearch.fcgi",
            params={"db": "pubmed", "term": term, "retmode": "json", "retmax": retmax},
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()["esearchresult"]
        self.cache.put(key, result)
        return result

    def comention_count(self, drug: str, disease: str) -> int:
        return int(self.esearch(build_term(drug, disease), 0)["count"])

    def search_ids(self, drug: str, disease: str, retmax: int = 20) -> list[str]:
        return list(self.esearch(build_term(drug, disease), retmax)["idlist"])

    def fetch_abstracts(self, pmids: list[str]) -> pd.DataFrame:
        frames = []
        for start in range(0, len(pmids), BATCH):
            batch = pmids[start : start + BATCH]
            key = "efetch|" + ",".join(batch)
            text = self.cache.get_text(key)
            if text is None:
                self.limiter.wait()
                response = self.client.get(
                    BASE + "efetch.fcgi",
                    params={"db": "pubmed", "id": ",".join(batch), "retmode": "xml"},
                )
                response.raise_for_status()
                text = response.text
                self.cache.put_text(key, text)
            frames.append(parse_xml(text))
        if not frames:
            return parse_xml("<PubmedArticleSet/>")
        return pd.concat(frames, ignore_index=True)
