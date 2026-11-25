import numpy as np

from models.export_candidates import METHOD_COLUMNS, export, load_weights

CFG = {
    "kge_epochs": 2,
    "kge_dim": 8,
    "gnn": {"hidden": 16, "max_epochs": 10, "patience": 2, "device": "cpu"},
}


def test_export_layout(graph, ind):
    w = {m: 0.2 for m in METHOD_COLUMNS}
    out = export(graph, ind, w, 5, 0, CFG)
    assert {"disease_node", "drug_node", "score", "rank", *METHOD_COLUMNS} <= set(out.columns)
    assert out["disease_node"].nunique() == len(graph.disease_nodes)
    assert (out.groupby("disease_node").size() <= 5).all()
    assert set(out["drug_node"]) <= set(graph.compound_nodes.tolist())
    known = set(zip(ind["disease_node"], ind["drug_node"]))
    assert not (set(zip(out["disease_node"], out["drug_node"])) & known)
    s = out[out["disease_node"] == out["disease_node"].iloc[0]]
    assert np.all(np.diff(s["score"].to_numpy()) <= 1e-12)
    assert list(s["rank"]) == list(range(1, len(s) + 1))


def test_load_weights_default(tmp_path):
    w = load_weights(tmp_path / "none.json")
    assert abs(sum(w.values()) - 1) < 1e-9
