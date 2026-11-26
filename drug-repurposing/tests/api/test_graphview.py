from pathlib import Path

import pytest

from api.backend import MemoryBackend
from api.config import Settings
from api.graphview import build_graph_view as build
from api.store import Store
from tests.api.conftest import make_settings


@pytest.fixture
def backend(tmp_path: Path) -> MemoryBackend:
    cfg: Settings = make_settings(tmp_path, offline=True)
    return MemoryBackend(Store.load(cfg), cfg)


def build_graph_view(backend, disease_id, k, max_paths):
    view = build(backend, disease_id, k, max_paths)
    assert view is not None
    return view


def link_set(view):
    return {(link.source, link.target, link.kind, link.label) for link in view.links}


def test_two_hop_evidence_and_known_flag(backend):
    view = build_graph_view(backend, "MONDO:1", k=3, max_paths=3)
    ids = {n.id: n for n in view.nodes}
    assert view.disease.disease_id == "MONDO:1"
    assert ids["Disease:MONDO:1"].role == "disease"
    assert ids["Compound:DB001"].role == "known"
    assert ids["Compound:DB002"].role == "predicted"
    assert ids["Compound:DB003"].role == "predicted"
    assert ids["Gene:G1"].role == "gene"
    assert "Gene:G2" not in ids
    links = link_set(view)
    assert ("Compound:DB001", "Disease:MONDO:1", "predicted", "predicted") in links
    assert ("Compound:DB001", "Disease:MONDO:1", "known", "treats") in links
    assert ("Compound:DB001", "Gene:G1", "evidence", "Compound-binds-Gene") in links
    assert ("Gene:G1", "Disease:MONDO:1", "evidence", "Gene-associates-Disease") in links


def test_prediction_links_carry_scores(backend):
    view = build_graph_view(backend, "MONDO:1", k=3, max_paths=3)
    scores = {link.source: link.score for link in view.links if link.kind == "predicted"}
    assert scores == {"Compound:DB001": 0.9, "Compound:DB002": 0.4, "Compound:DB003": 0.2}


def test_three_hop_chain_and_link_dedupe(backend):
    view = build_graph_view(backend, "MONDO:4", k=2, max_paths=3)
    links = [
        (link.source, link.target, link.label) for link in view.links if link.kind == "evidence"
    ]
    assert ("Gene:G1", "Gene:G3", "Gene-interacts-Gene") in links
    assert ("Gene:G4", "Gene:G3", "Gene-interacts-Gene") in links or (
        "Gene:G3",
        "Gene:G4",
        "Gene-interacts-Gene",
    ) in links
    assert links.count(("Gene:G3", "Disease:MONDO:4", "Gene-associates-Disease")) == 1
    assert len(links) == len(set(links))


def test_k_limits_drugs(backend):
    view = build_graph_view(backend, "MONDO:1", k=1, max_paths=3)
    drugs = [n for n in view.nodes if n.kind == "Compound"]
    assert [d.name for d in drugs] == ["Metformin"]


def test_nodes_are_unique(backend):
    view = build_graph_view(backend, "MONDO:4", k=2, max_paths=3)
    ids = [n.id for n in view.nodes]
    assert len(ids) == len(set(ids))


def test_top_candidate_for_other_disease(backend):
    view = build_graph_view(backend, "MONDO:2", k=1, max_paths=3)
    ids = {n.id: n for n in view.nodes}
    assert ids["Compound:DB002"].role == "predicted"
    assert view.disease.name == "Pulmonary hypertension"


def test_unknown_disease_returns_none(backend):
    assert build(backend, "nope", k=3, max_paths=3) is None
