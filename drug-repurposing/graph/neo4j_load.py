import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from neo4j import Driver, GraphDatabase

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
RESERVED = {"disease_node", "drug_node", "score", "rank"}
BATCH = 20000


@dataclass(frozen=True)
class LoadStats:
    nodes: int
    edges: int
    predictions: int


def rel_type(etype: str) -> str:
    parts = etype.split("-")
    if len(parts) != 3 or not all(NAME.match(p) for p in parts):
        raise ValueError(f"malformed edge type: {etype}")
    return parts[1].upper()


def endpoint_kinds(etype: str) -> tuple[str, str]:
    parts = etype.split("-")
    return parts[0], parts[2]


def clean(frame: pd.DataFrame) -> list[dict]:
    return frame.astype(object).where(frame.notna(), None).to_dict("records")


def batches(rows: list[dict]):
    for i in range(0, len(rows), BATCH):
        yield rows[i : i + BATCH]


def check_edges(nodes: pd.DataFrame, edges: pd.DataFrame) -> None:
    known = set(nodes["node_id"].astype(int))
    used = set(edges["src"].astype(int)) | set(edges["dst"].astype(int))
    missing = sorted(used - known)
    if missing:
        raise ValueError(f"edges reference unknown node ids: {missing[:10]}")


def reset(driver: Driver) -> None:
    with driver.session() as s:
        s.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS").consume()


def create_schema(driver: Driver, kinds: list[str]) -> None:
    with driver.session() as s:
        for kind in kinds:
            if not NAME.match(kind):
                raise ValueError(f"unsafe node kind: {kind}")
            s.run(
                f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{kind}) REQUIRE n.ext_id IS UNIQUE"
            ).consume()
            s.run(f"CREATE INDEX IF NOT EXISTS FOR (n:{kind}) ON (n.node_id)").consume()


def load_nodes(driver: Driver, nodes: pd.DataFrame) -> None:
    cols = ["node_id", "ext_id", "name"]
    with driver.session() as s:
        for kind, group in nodes.groupby("kind"):
            rows = clean(group[cols])
            for chunk in batches(rows):
                s.run(
                    f"UNWIND $rows AS row CREATE (n:{kind}) "
                    "SET n.node_id = row.node_id, n.ext_id = row.ext_id, n.name = row.name",
                    rows=chunk,
                ).consume()


def load_edges(driver: Driver, edges: pd.DataFrame) -> None:
    with driver.session() as s:
        for etype, group in edges.groupby("etype"):
            etype = str(etype)
            rel = rel_type(etype)
            src_kind, dst_kind = endpoint_kinds(etype)
            rows = clean(group[["src", "dst", "weight"]])
            for chunk in batches(rows):
                s.run(
                    f"UNWIND $rows AS row "
                    f"MATCH (a:{src_kind} {{node_id: row.src}}) "
                    f"MATCH (b:{dst_kind} {{node_id: row.dst}}) "
                    f"CREATE (a)-[:{rel} {{etype: $etype, weight: row.weight}}]->(b)",
                    rows=chunk,
                    etype=etype,
                ).consume()


def load_predictions(driver: Driver, candidates: pd.DataFrame) -> None:
    if candidates.empty:
        return
    ranked = candidates.copy()
    ranked["rank"] = (
        ranked.groupby("disease_node")["score"].rank(ascending=False, method="first").astype(int)
    )
    methods = [
        c for c in ranked.columns if c not in RESERVED and pd.api.types.is_numeric_dtype(ranked[c])
    ]
    for c in methods:
        if not NAME.match(c):
            raise ValueError(f"unsafe method column: {c}")
    props = ", ".join(f"{c}: row.{c}" for c in ["score", "rank", *methods])
    rows = clean(ranked[["disease_node", "drug_node", "score", "rank", *methods]])
    with driver.session() as s:
        for chunk in batches(rows):
            s.run(
                "UNWIND $rows AS row "
                "MATCH (c:Compound {node_id: row.drug_node}) "
                "MATCH (d:Disease {node_id: row.disease_node}) "
                f"CREATE (c)-[:PREDICTED_TREATS {{{props}}}]->(d)",
                rows=chunk,
            ).consume()


def load_graph(
    driver: Driver, nodes: pd.DataFrame, edges: pd.DataFrame, candidates: pd.DataFrame
) -> LoadStats:
    check_edges(nodes, edges)
    reset(driver)
    create_schema(driver, sorted(nodes["kind"].astype(str).unique()))
    load_nodes(driver, nodes)
    load_edges(driver, edges)
    load_predictions(driver, candidates)
    return LoadStats(len(nodes), len(edges), len(candidates))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default="data/graph")
    ap.add_argument("--candidates", default="data/results/candidates.parquet")
    args = ap.parse_args()
    uri = os.environ.get("DR_NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.environ.get("DR_NEO4J_USER", "neo4j")
    password = os.environ.get("DR_NEO4J_PASSWORD")
    if not password:
        raise SystemExit("set DR_NEO4J_PASSWORD")
    graph = Path(args.graph)
    nodes = pd.read_parquet(graph / "nodes.parquet")
    edges = pd.read_parquet(graph / "edges.parquet")
    candidates = pd.read_parquet(args.candidates)
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        stats = load_graph(driver, nodes, edges, candidates)
    print(f"loaded nodes={stats.nodes} edges={stats.edges} predictions={stats.predictions}")


if __name__ == "__main__":
    main()
