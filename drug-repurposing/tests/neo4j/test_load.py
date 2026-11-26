import pandas as pd
import pytest
from neo4j.exceptions import ConstraintError

from graph.neo4j_load import load_graph, rel_type
from tests.neo4j.conftest import FIX


@pytest.fixture
def frames():
    nodes = pd.read_parquet(FIX / "graph" / "nodes.parquet")
    edges = pd.read_parquet(FIX / "graph" / "edges.parquet")
    cands = pd.read_parquet(FIX / "results" / "candidates.parquet")
    return nodes, edges, cands


def scalar(driver, query, **params):
    with driver.session() as s:
        return s.run(query, **params).single()[0]


def test_rel_type_uses_the_verb():
    assert rel_type("Compound-binds-Gene") == "BINDS"
    assert rel_type("Gene-associates-Disease") == "ASSOCIATES"
    assert rel_type("Compound-treats-Disease") == "TREATS"


def test_rel_type_rejects_malformed():
    with pytest.raises(ValueError):
        rel_type("nonsense")


def test_nodes_loaded_with_kind_labels(driver, frames):
    nodes, edges, cands = frames
    load_graph(driver, nodes, edges, cands)
    assert scalar(driver, "MATCH (n) RETURN count(n)") == len(nodes)
    for kind, group in nodes.groupby("kind"):
        assert scalar(driver, f"MATCH (n:{kind}) RETURN count(n)") == len(group)


def test_node_properties(driver, frames):
    nodes, edges, cands = frames
    load_graph(driver, nodes, edges, cands)
    rec = scalar(
        driver,
        "MATCH (n:Disease {ext_id: $e}) RETURN n {.node_id, .ext_id, .name}",
        e="MONDO:1",
    )
    assert rec == {"node_id": 7, "ext_id": "MONDO:1", "name": "Type 2 diabetes"}


def test_structural_edges_loaded(driver, frames):
    nodes, edges, cands = frames
    stats = load_graph(driver, nodes, edges, cands)
    assert scalar(driver, "MATCH ()-[r]->() WHERE r.etype IS NOT NULL RETURN count(r)") == len(
        edges
    )
    assert stats.edges == len(edges)
    assert (
        scalar(
            driver,
            "MATCH (:Compound {ext_id:'DB001'})-[r:BINDS]->(:Gene {ext_id:'G1'}) " "RETURN r.etype",
        )
        == "Compound-binds-Gene"
    )


def test_edge_direction_preserved(driver, frames):
    nodes, edges, cands = frames
    load_graph(driver, nodes, edges, cands)
    assert (
        scalar(
            driver,
            "MATCH (:Disease)-[r:ASSOCIATES]->(:Gene) RETURN count(r)",
        )
        == 0
    )
    assert scalar(driver, "MATCH (:Gene)-[r:ASSOCIATES]->(:Disease) RETURN count(r)") == 3


def test_predictions_loaded_with_scores(driver, frames):
    nodes, edges, cands = frames
    stats = load_graph(driver, nodes, edges, cands)
    assert stats.predictions == len(cands)
    assert scalar(driver, "MATCH ()-[r:PREDICTED_TREATS]->() RETURN count(r)") == len(cands)
    props = scalar(
        driver,
        "MATCH (:Compound {ext_id:'DB002'})-[r:PREDICTED_TREATS]->(:Disease {ext_id:'MONDO:2'}) "
        "RETURN r {.score, .proximity, .gnn}",
    )
    assert props == {"score": 0.95, "proximity": 0.9, "gnn": 0.9}


def test_prediction_rank_is_per_disease_descending(driver, frames):
    nodes, edges, cands = frames
    load_graph(driver, nodes, edges, cands)
    rows = (
        driver.session()
        .run(
            "MATCH (c:Compound)-[r:PREDICTED_TREATS]->(:Disease {ext_id:'MONDO:1'}) "
            "RETURN c.ext_id AS drug, r.rank AS rank ORDER BY r.rank"
        )
        .data()
    )
    assert rows == [
        {"drug": "DB001", "rank": 1},
        {"drug": "DB002", "rank": 2},
        {"drug": "DB003", "rank": 3},
    ]


def test_load_is_idempotent(driver, frames):
    nodes, edges, cands = frames
    load_graph(driver, nodes, edges, cands)
    load_graph(driver, nodes, edges, cands)
    assert scalar(driver, "MATCH (n) RETURN count(n)") == len(nodes)
    assert scalar(driver, "MATCH ()-[r]->() RETURN count(r)") == len(edges) + len(cands)


def test_reload_replaces_stale_predictions(driver, frames):
    nodes, edges, cands = frames
    load_graph(driver, nodes, edges, cands)
    load_graph(driver, nodes, edges, cands.iloc[:3])
    assert scalar(driver, "MATCH ()-[r:PREDICTED_TREATS]->() RETURN count(r)") == 3


def test_uniqueness_constraint_blocks_duplicate_ext_id(driver, frames):
    nodes, edges, cands = frames
    load_graph(driver, nodes, edges, cands)
    with pytest.raises(ConstraintError):
        with driver.session() as s:
            s.run("CREATE (:Compound {ext_id:'DB001', node_id: 999, name:'dup'})").consume()


def test_unknown_node_in_edges_is_reported(driver, frames):
    nodes, edges, cands = frames
    bad = pd.concat(
        [edges, pd.DataFrame([{"src": 0, "dst": 999, "etype": "Compound-binds-Gene"}])],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="999"):
        load_graph(driver, nodes, bad, cands)
