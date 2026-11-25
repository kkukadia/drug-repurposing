import pandas as pd

from api.paths import GraphIndex, extract_paths


def build(n_hubs: int) -> GraphIndex:
    nodes = [(0, "Compound", "d", "D"), (1, "Disease", "x", "X")]
    edges = []
    for i in range(n_hubs):
        nodes.append((2 + i, "Gene", f"g{i}", f"G{i}"))
        edges.append((0, 2 + i, "Compound-binds-Gene"))
        edges.append((2 + i, 1, "Gene-associates-Disease"))
    n = pd.DataFrame(nodes, columns=["node_id", "kind", "ext_id", "name"])
    e = pd.DataFrame(edges, columns=["src", "dst", "etype"])
    return GraphIndex.build(n, e)


def test_max_paths_cap():
    assert len(extract_paths(build(10), 0, 1, max_paths=2)) == 2


def build_chains(n: int) -> GraphIndex:
    nodes = [(0, "Compound", "d", "D"), (1, "Disease", "x", "X"), (2, "Gene", "h", "H")]
    edges = [(0, 2, "Compound-binds-Gene")]
    for i in range(n):
        gid = 3 + i
        nodes.append((gid, "Gene", f"g{i}", f"G{i:03d}"))
        edges.append((2, gid, "Gene-interacts-Gene"))
        edges.append((gid, 1, "Gene-associates-Disease"))
    return GraphIndex.build(
        pd.DataFrame(nodes, columns=["node_id", "kind", "ext_id", "name"]),
        pd.DataFrame(edges, columns=["src", "dst", "etype"]),
    )


def test_visit_budget_bounds_search():
    idx = build_chains(50)
    assert len(extract_paths(idx, 0, 1, max_paths=100, max_visits=10)) < 50
    assert len(extract_paths(idx, 0, 1, max_paths=100, max_visits=1000)) == 50


def test_no_path():
    idx = build(0)
    assert extract_paths(idx, 0, 1) == []


def test_disease_must_be_disease_kind():
    idx = build(1)
    assert extract_paths(idx, 0, 2) == []
