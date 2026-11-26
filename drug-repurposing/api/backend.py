from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd
from neo4j import Driver

from api.config import Settings
from api.paths import extract_paths
from api.schemas import DiseaseOut, PathNode, PathOut
from api.store import Store

RESERVED_REL_PROPS = {"score", "rank"}


@dataclass(frozen=True)
class CandidateRow:
    drug_id: str
    drug_name: str
    score: float
    method_scores: dict[str, float]


class GraphBackend(Protocol):
    name: str

    def ready(self) -> bool: ...

    def disease_count(self) -> int: ...

    def search_diseases(self, q: str, limit: int) -> list[DiseaseOut]: ...

    def get_disease(self, disease_id: str) -> DiseaseOut | None: ...

    def candidates(self, disease_id: str, k: int) -> list[CandidateRow]: ...

    def paths(self, drug_id: str, disease_id: str, max_paths: int) -> list[PathOut]: ...

    def known_drugs(self, disease_id: str, limit: int) -> list[tuple[str, str]]: ...

    def close(self) -> None: ...


def rank_diseases(hits: list[DiseaseOut], needle: str, limit: int) -> list[DiseaseOut]:
    hits.sort(key=lambda d: (not d.name.lower().startswith(needle), d.name.lower()))
    return hits[:limit]


class MemoryBackend:
    name = "memory"

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        index = store.index
        self.drug_by_ext: dict[str, int] = {}
        if index is not None:
            self.drug_by_ext = {
                index.ext_ids[n]: n for n in index.by_kind.get("Compound", []) if n in index.ext_ids
            }

    def ready(self) -> bool:
        return self.store.index is not None and not self.store.candidates.empty

    def disease_count(self) -> int:
        return len(self.store.diseases)

    def search_diseases(self, q: str, limit: int) -> list[DiseaseOut]:
        needle = q.strip().lower()
        hits = [
            DiseaseOut(disease_id=ext, name=name)
            for ext, name, _ in self.store.diseases
            if not needle or needle in name.lower() or needle in ext.lower()
        ]
        return rank_diseases(hits, needle, limit)

    def get_disease(self, disease_id: str) -> DiseaseOut | None:
        node = self.store.disease_by_ext.get(disease_id)
        if node is None or self.store.index is None:
            return None
        return DiseaseOut(disease_id=disease_id, name=self.store.index.names[node])

    def candidates(self, disease_id: str, k: int) -> list[CandidateRow]:
        node = self.store.disease_by_ext.get(disease_id)
        index = self.store.index
        if node is None or index is None:
            return []
        rows = self.store.candidates[self.store.candidates["disease_node"] == node]
        out = []
        for _, row in rows.iterrows():
            drug = int(row["drug_node"])
            methods = {c: float(row[c]) for c in self.store.method_columns if pd.notna(row[c])}
            out.append(
                CandidateRow(
                    drug_id=index.ext_ids.get(drug, str(drug)),
                    drug_name=index.names.get(drug, str(drug)),
                    score=float(row["score"]),
                    method_scores=methods,
                )
            )
        out.sort(key=lambda r: (-r.score, r.drug_name))
        return out[:k]

    def paths(self, drug_id: str, disease_id: str, max_paths: int) -> list[PathOut]:
        index = self.store.index
        drug = self.drug_by_ext.get(drug_id)
        disease = self.store.disease_by_ext.get(disease_id)
        if index is None or drug is None or disease is None:
            return []
        return extract_paths(index, drug, disease, max_paths, self.settings.max_path_search_nodes)

    def known_drugs(self, disease_id: str, limit: int) -> list[tuple[str, str]]:
        index = self.store.index
        disease = self.store.disease_by_ext.get(disease_id)
        if index is None or disease is None:
            return []
        found = {
            (index.ext_ids[n], index.names[n])
            for n, etype in index.adj.get(disease, [])
            if etype == "Compound-treats-Disease" and index.kind(n) == "Compound"
        }
        return sorted(found, key=lambda t: (t[1], t[0]))[:limit]

    def close(self) -> None:
        return None


TWO_HOP = (
    "MATCH (c:Compound {ext_id: $drug})-[r1]-(g:Gene)-[r2]-(d:Disease {ext_id: $dis}) "
    "WITH g, min(r1.etype) AS e1, min(r2.etype) AS e2 "
    "RETURN g.ext_id AS g1id, g.name AS g1name, e1, e2 "
    "ORDER BY g1name, g1id LIMIT $n"
)

THREE_HOP = (
    "MATCH (c:Compound {ext_id: $drug})-[r1]-(a:Gene)-[r2]-(b:Gene)-[r3]-"
    "(d:Disease {ext_id: $dis}) "
    "WHERE a <> b "
    "WITH a, b, min(r1.etype) AS e1, min(r2.etype) AS e2, min(r3.etype) AS e3 "
    "RETURN a.ext_id AS g1id, a.name AS g1name, b.ext_id AS g2id, b.name AS g2name, "
    "e1, e2, e3 ORDER BY g1name, g2name, g1id, g2id LIMIT $n"
)


class Neo4jBackend:
    name = "neo4j"

    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def run(self, query: str, **params: Any) -> list[dict]:
        with self.driver.session() as s:
            return s.run(query, **params).data()

    def ready(self) -> bool:
        try:
            rows = self.run("MATCH ()-[r:PREDICTED_TREATS]->() RETURN r.score AS s LIMIT 1")
        except Exception:
            return False
        return bool(rows)

    def disease_count(self) -> int:
        rows = self.run(
            "MATCH (d:Disease) WHERE EXISTS { ()-[:PREDICTED_TREATS]->(d) } RETURN count(d) AS n"
        )
        return int(rows[0]["n"])

    def search_diseases(self, q: str, limit: int) -> list[DiseaseOut]:
        needle = q.strip().lower()
        rows = self.run(
            "MATCH (d:Disease) WHERE EXISTS { ()-[:PREDICTED_TREATS]->(d) } "
            "AND ($q = '' OR toLower(d.name) CONTAINS $q OR toLower(d.ext_id) CONTAINS $q) "
            "RETURN d.ext_id AS id, d.name AS name",
            q=needle,
        )
        hits = [DiseaseOut(disease_id=r["id"], name=r["name"]) for r in rows]
        return rank_diseases(hits, needle, limit)

    def get_disease(self, disease_id: str) -> DiseaseOut | None:
        rows = self.run(
            "MATCH (d:Disease {ext_id: $id}) WHERE EXISTS { ()-[:PREDICTED_TREATS]->(d) } "
            "RETURN d.name AS name",
            id=disease_id,
        )
        if not rows:
            return None
        return DiseaseOut(disease_id=disease_id, name=rows[0]["name"])

    def candidates(self, disease_id: str, k: int) -> list[CandidateRow]:
        rows = self.run(
            "MATCH (c:Compound)-[r:PREDICTED_TREATS]->(:Disease {ext_id: $id}) "
            "RETURN c.ext_id AS id, c.name AS name, properties(r) AS props "
            "ORDER BY r.score DESC, c.name LIMIT $k",
            id=disease_id,
            k=k,
        )
        out = []
        for r in rows:
            props = r["props"]
            methods = {
                key: float(val)
                for key, val in props.items()
                if key not in RESERVED_REL_PROPS and val is not None
            }
            out.append(
                CandidateRow(
                    drug_id=r["id"],
                    drug_name=r["name"],
                    score=float(props["score"]),
                    method_scores=methods,
                )
            )
        return out

    def paths(self, drug_id: str, disease_id: str, max_paths: int) -> list[PathOut]:
        if max_paths <= 0:
            return []
        ends = self.run(
            "MATCH (c:Compound {ext_id: $drug}), (d:Disease {ext_id: $dis}) "
            "RETURN c.name AS drug, d.name AS dis",
            drug=drug_id,
            dis=disease_id,
        )
        if not ends:
            return []
        drug = PathNode(kind="Compound", name=ends[0]["drug"], id=drug_id)
        dis = PathNode(kind="Disease", name=ends[0]["dis"], id=disease_id)
        out: list[PathOut] = []
        for r in self.run(TWO_HOP, drug=drug_id, dis=disease_id, n=max_paths):
            gene = PathNode(kind="Gene", name=r["g1name"], id=r["g1id"])
            out.append(PathOut(nodes=[drug, gene, dis], edges=[r["e1"], r["e2"]]))
        remaining = max_paths - len(out)
        if remaining > 0:
            for r in self.run(THREE_HOP, drug=drug_id, dis=disease_id, n=remaining):
                g1 = PathNode(kind="Gene", name=r["g1name"], id=r["g1id"])
                g2 = PathNode(kind="Gene", name=r["g2name"], id=r["g2id"])
                out.append(PathOut(nodes=[drug, g1, g2, dis], edges=[r["e1"], r["e2"], r["e3"]]))
        return out

    def known_drugs(self, disease_id: str, limit: int) -> list[tuple[str, str]]:
        rows = self.run(
            "MATCH (c:Compound)-[:TREATS]->(:Disease {ext_id: $id}) "
            "RETURN DISTINCT c.ext_id AS id, c.name AS name ORDER BY name, id LIMIT $limit",
            id=disease_id,
            limit=limit,
        )
        return [(r["id"], r["name"]) for r in rows]

    def close(self) -> None:
        self.driver.close()
