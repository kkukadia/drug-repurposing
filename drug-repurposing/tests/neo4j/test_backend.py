from pathlib import Path

import pandas as pd
import pytest

from api.backend import MemoryBackend, Neo4jBackend
from api.store import Store
from tests.api.conftest import make_settings

DISEASES = ["MONDO:1", "MONDO:2", "MONDO:3", "MONDO:4"]
DRUGS = ["DB001", "DB002", "DB003"]


@pytest.fixture
def mem(tmp_path: Path) -> MemoryBackend:
    cfg = make_settings(tmp_path, offline=True)
    return MemoryBackend(Store.load(cfg), cfg)


@pytest.fixture
def neo(loaded) -> Neo4jBackend:
    return Neo4jBackend(loaded)


def test_ready_and_counts(neo, mem):
    assert neo.ready() is True
    assert neo.disease_count() == mem.disease_count() == 4


def test_not_ready_when_empty(driver):
    assert Neo4jBackend(driver).ready() is False


@pytest.mark.parametrize("q", ["", "diab", "TYPE", "MONDO:3", "zzz", "cancer"])
def test_search_matches_memory(neo, mem, q):
    assert neo.search_diseases(q, 50) == mem.search_diseases(q, 50)


def test_search_limit(neo):
    assert len(neo.search_diseases("", 2)) == 2


def test_search_prefers_prefix_matches(neo):
    names = [d.name for d in neo.search_diseases("o", 10)]
    assert names[0] == "Orphan syndrome"


def test_get_disease(neo):
    assert neo.get_disease("MONDO:2").name == "Pulmonary hypertension"
    assert neo.get_disease("nope") is None


@pytest.mark.parametrize("disease", DISEASES)
def test_candidates_match_memory(neo, mem, disease):
    assert neo.candidates(disease, 10) == mem.candidates(disease, 10)


def test_candidates_sorted_and_limited(neo):
    rows = neo.candidates("MONDO:1", 2)
    assert [r.drug_id for r in rows] == ["DB001", "DB002"]
    assert rows[0].score >= rows[1].score
    assert set(rows[0].method_scores) == {"proximity", "gnn"}


def test_candidates_unknown_disease(neo):
    assert neo.candidates("nope", 5) == []


@pytest.mark.parametrize("disease", DISEASES)
@pytest.mark.parametrize("drug", DRUGS)
def test_paths_match_memory(neo, mem, disease, drug):
    assert neo.paths(drug, disease, 3) == mem.paths(drug, disease, 3)


def test_three_hop_path_found(neo):
    paths = neo.paths("DB001", "MONDO:4", 3)
    assert len(paths) == 1
    assert [n.name for n in paths[0].nodes] == ["Metformin", "PRKAA1", "MTOR", "Breast cancer"]
    assert paths[0].edges == [
        "Compound-binds-Gene",
        "Gene-interacts-Gene",
        "Gene-associates-Disease",
    ]


def test_path_nodes_carry_ids(neo):
    path = neo.paths("DB001", "MONDO:1", 3)[0]
    assert [n.id for n in path.nodes] == ["DB001", "G1", "MONDO:1"]


def test_two_hop_listed_before_three_hop(neo):
    paths = neo.paths("DB001", "MONDO:1", 5)
    assert [len(p.nodes) for p in paths] == sorted(len(p.nodes) for p in paths)


def test_max_paths_cap(neo):
    assert len(neo.paths("DB001", "MONDO:4", 0)) == 0


def test_paths_unknown_ids(neo):
    assert neo.paths("nope", "MONDO:1", 3) == []
    assert neo.paths("DB001", "nope", 3) == []


@pytest.mark.parametrize("disease", DISEASES)
def test_known_drugs_match_memory(neo, mem, disease):
    assert neo.known_drugs(disease, 10) == mem.known_drugs(disease, 10)


def test_known_drugs_content(neo):
    assert neo.known_drugs("MONDO:1", 10) == [("DB001", "Metformin")]


def test_larger_hub_graph_is_bounded(driver):
    from graph.neo4j_load import load_graph

    nodes = [(0, "Compound", "D", "Drug"), (1, "Disease", "X", "Dis")]
    edges = []
    for i in range(60):
        nodes.append((2 + i, "Gene", f"g{i}", f"G{i:03d}"))
        edges.append((0, 2 + i, "Compound-binds-Gene"))
        edges.append((2 + i, 1, "Gene-associates-Disease"))
    load_graph(
        driver,
        pd.DataFrame(nodes, columns=["node_id", "kind", "ext_id", "name"]),
        pd.DataFrame(
            [(s, d, e, 1.0) for s, d, e in edges], columns=["src", "dst", "etype", "weight"]
        ),
        pd.DataFrame({"disease_node": [1], "drug_node": [0], "score": [0.5]}),
    )
    backend = Neo4jBackend(driver)
    assert len(backend.paths("D", "X", 4)) == 4
    names = [p.nodes[1].name for p in backend.paths("D", "X", 4)]
    assert names == sorted(names)


def test_tied_scores_break_by_name_in_both_backends(driver, tmp_path):
    from api.config import Settings
    from graph.neo4j_load import load_graph

    nodes = pd.DataFrame(
        [
            (0, "Compound", "DB9", "Zeta"),
            (1, "Compound", "DB8", "Alpha"),
            (2, "Compound", "DB7", "Mid"),
            (3, "Disease", "X", "Dis"),
        ],
        columns=["node_id", "kind", "ext_id", "name"],
    )
    edges = pd.DataFrame(
        {"src": [0], "dst": [3], "etype": ["Compound-treats-Disease"], "weight": [1.0]}
    )
    cands = pd.DataFrame(
        {"disease_node": [3, 3, 3], "drug_node": [0, 1, 2], "score": [0.5, 0.5, 0.5]}
    )
    gdir = tmp_path / "g"
    gdir.mkdir()
    nodes.to_parquet(gdir / "nodes.parquet")
    edges.to_parquet(gdir / "edges.parquet")
    cpath = tmp_path / "c.parquet"
    cands.to_parquet(cpath)
    cfg = Settings(
        graph_dir=gdir,
        candidates_path=cpath,
        cache_dir=tmp_path / "cache",
        offline=True,
        http_timeout=1.0,
        max_paths=3,
        max_path_search_nodes=5000,
    )
    mem = MemoryBackend(Store.load(cfg), cfg)
    load_graph(driver, nodes, edges, cands)
    neo = Neo4jBackend(driver)
    expected = ["Alpha", "Mid", "Zeta"]
    assert [r.drug_name for r in mem.candidates("X", 3)] == expected
    assert [r.drug_name for r in neo.candidates("X", 3)] == expected
    assert [r.drug_name for r in mem.candidates("X", 2)] == expected[:2]
    assert [r.drug_name for r in neo.candidates("X", 2)] == expected[:2]
