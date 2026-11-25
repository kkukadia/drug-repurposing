import numpy as np

from eval.metrics import (
    auprc,
    auroc,
    bootstrap_ci,
    filtered_rank,
    hits_at_k,
    mrr,
    ranking_summary,
    seed_ci,
)


def test_auc_perfect_and_random():
    y = np.array([1, 1, 0, 0, 0])
    assert auroc(y, np.array([5, 4, 3, 2, 1.0])) == 1.0
    assert auprc(y, np.array([5, 4, 3, 2, 1.0])) == 1.0
    assert auroc(np.zeros(3), np.arange(3)) != auroc(np.zeros(3), np.arange(3))


def test_filtered_rank_with_ties_and_exclusion():
    s = np.array([0.9, 0.5, 0.5, 0.1])
    assert filtered_rank(s, 1) == 2.5
    assert filtered_rank(s, 1, np.array([0])) == 1.5
    assert filtered_rank(s, 3) == 4.0
    assert filtered_rank(s, 0) == 1.0


def test_hits_mrr():
    r = np.array([1.0, 2.0, 10.0, 100.0])
    assert hits_at_k(r, 2) == 0.5
    assert abs(mrr(r) - np.mean([1, 0.5, 0.1, 0.01])) < 1e-12
    out = ranking_summary(r)
    assert out["hits@20"] == 0.75 and out["recall@50"] == 0.75


def test_seed_ci_contains_mean():
    ci = seed_ci([0.5, 0.6, 0.55, 0.52, 0.58])
    assert ci["lo"] < ci["mean"] < ci["hi"] and ci["n"] == 5
    assert seed_ci([0.4])["lo"] == 0.4
    assert np.isnan(seed_ci([])["mean"])


def test_bootstrap_ci():
    ci = bootstrap_ci(np.arange(100.0), n_boot=200)
    assert ci["lo"] < 49.5 < ci["hi"]
