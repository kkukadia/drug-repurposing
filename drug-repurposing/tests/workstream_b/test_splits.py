import numpy as np
import pandas as pd
import pytest

from eval.splits import (
    KINDS,
    apply_split,
    known_positives,
    make_split,
    pair_keys,
    popularity,
    sample_negatives,
)
from models.graph_data import TREATS


def keyset(df, n):
    return set(pair_keys(df["drug_node"].to_numpy(), df["disease_node"].to_numpy(), n).tolist())


@pytest.mark.parametrize("kind", KINDS)
def test_partition_disjoint_and_complete(ind, graph, kind):
    s = make_split(ind, kind, 1)
    n = graph.n_nodes
    a, b, c = keyset(s.train, n), keyset(s.val, n), keyset(s.test, n)
    assert not (a & b) and not (a & c) and not (b & c)
    assert len(a) + len(b) + len(c) == len(ind)
    assert len(s.test) > 0 and len(s.val) > 0


@pytest.mark.parametrize("kind", KINDS)
def test_deterministic_by_seed(ind, kind):
    a = make_split(ind, kind, 3)
    b = make_split(ind, kind, 3)
    pd.testing.assert_frame_equal(a.test, b.test)
    if kind in ("random", "cold_disease", "repurposing"):
        c = make_split(ind, kind, 4)
        assert not a.test.equals(c.test)


def test_random_fractions(ind):
    s = make_split(ind, "random", 0)
    assert abs(len(s.test) / len(ind) - 0.2) < 0.02


def test_time_split_orders_years(ind):
    s = make_split(ind, "time", 0)
    assert s.cutoff_year is not None
    assert s.test["year"].notna().all()
    assert (s.test["year"] >= s.cutoff_year).all()
    assert (s.train["year"].dropna() < s.cutoff_year).all()
    assert s.val["year"].max() < s.cutoff_year
    assert s.val["year"].min() >= s.train["year"].dropna().max() or s.val["year"].min() > 0
    assert s.train["year"].isna().sum() > 0


def test_cold_disease_disjoint_diseases(ind):
    s = make_split(ind, "cold_disease", 0)
    held = set(s.held_out_diseases.tolist())
    assert not (set(s.train["disease_node"]) & held)
    assert set(s.test["disease_node"]) <= held
    assert set(s.val["disease_node"]) <= held
    assert not (set(s.test["disease_node"]) & set(s.val["disease_node"]))


def test_repurposing_keeps_a_train_indication_per_drug(ind):
    s = make_split(ind, "repurposing", 0)
    held_drugs = set(s.test["drug_node"]) | set(s.val["drug_node"])
    assert held_drugs <= set(s.train["drug_node"])
    assert s.test["drug_node"].is_unique


def test_unknown_kind(ind):
    with pytest.raises(ValueError):
        make_split(ind, "nope", 0)


@pytest.mark.parametrize("kind", KINDS)
def test_leakage_removed(graph, ind, kind):
    s = make_split(ind, kind, 2)
    g = apply_split(graph, s)
    n = graph.n_nodes
    held = keyset(pd.concat([s.val, s.test]), n)
    e = g.edges
    k_fwd = pair_keys(e["src"].to_numpy(), e["dst"].to_numpy(), n)
    k_rev = pair_keys(e["dst"].to_numpy(), e["src"].to_numpy(), n)
    assert not (set(k_fwd.tolist()) & held)
    assert not (set(k_rev.tolist()) & held)
    treats = e[e["etype"] == TREATS]
    assert keyset(s.train.rename(columns={}), n) <= set(
        pair_keys(treats["src"].to_numpy(), treats["dst"].to_numpy(), n).tolist()
    )
    assert s.removal_stats["removed_total"] > 0
    if kind == "cold_disease":
        cd = e[(g.kinds[e["src"]] == "Compound") & (g.kinds[e["dst"]] == "Disease")]
        assert not (set(cd["dst"]) & set(s.held_out_diseases.tolist()))


def test_indirect_reverse_etype_removed(graph, ind):
    s = make_split(ind, "random", 5)
    rev_before = graph.edges["etype"].eq("Disease-treated_by-Compound").sum()
    g = apply_split(graph, s)
    assert rev_before > 0
    t = s.test.iloc[0]
    e = g.edges
    hit = e[(e["src"] == t["disease_node"]) & (e["dst"] == t["drug_node"])]
    assert hit.empty


def test_hierarchy_indirect_edges_removed(graph, ind):
    e = graph.edges
    isa = e[e["etype"] == "Disease-isa-Disease"].iloc[0]
    parent, child = int(isa["src"]), int(isa["dst"])
    drug = int(graph.compound_nodes[0])
    extra = pd.DataFrame(
        {
            "src": [drug],
            "dst": [child],
            "etype": ["Compound-palliates-Disease"],
            "source": ["x"],
            "source_version": ["0"],
            "weight": [np.nan],
        }
    )
    g2 = graph.with_edges(pd.concat([graph.edges, extra], ignore_index=True))
    base = make_split(ind, "random", 0)
    from eval.splits import Split

    s = Split(
        "random",
        0,
        base.train,
        base.val,
        pd.DataFrame({"drug_node": [drug], "disease_node": [parent], "year": [2000]}),
    )
    out = apply_split(g2, s)
    assert not ((out.edges["src"] == drug) & (out.edges["dst"] == child)).any()
    assert s.removal_stats["removed_indirect_hierarchy_edges"] >= 1


def test_negatives_never_known_positive(graph, ind):
    s = make_split(ind, "random", 0)
    known = known_positives(graph, ind)
    pop = popularity(graph, s.train)
    for strat in ("uniform", "popularity"):
        neg = sample_negatives(graph, s.test, known, 5, strat, pop, 0)
        assert len(neg) == 5 * len(s.test)
        ci = graph.comp_index[neg["drug_node"].to_numpy()]
        for d, c in zip(neg["disease_node"], ci):
            assert c not in known[int(d)]
        per = neg.groupby("pos_index")["drug_node"].nunique()
        assert (per == 5).all()


def test_popularity_negatives_skew_to_popular_drugs(graph, ind):
    s = make_split(ind, "random", 0)
    known = known_positives(graph, ind)
    pop = popularity(graph, s.train)
    big = pd.concat([s.test] * 30, ignore_index=True)
    u = sample_negatives(graph, big, known, 10, "uniform", pop, 1)
    p = sample_negatives(graph, big, known, 10, "popularity", pop, 1)
    pu = pop[graph.comp_index[u["drug_node"].to_numpy()]].mean()
    pp = pop[graph.comp_index[p["drug_node"].to_numpy()]].mean()
    assert pp > pu * 1.05


def test_negative_strategy_validated(graph, ind):
    s = make_split(ind, "random", 0)
    with pytest.raises(ValueError):
        sample_negatives(graph, s.test, {}, 1, "bad", popularity(graph, s.train), 0)
