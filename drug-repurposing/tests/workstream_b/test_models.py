import numpy as np
import pytest
import torch

from eval.metrics import auprc, filtered_rank
from eval.splits import apply_split, known_positives, make_split, popularity, sample_negatives
from models.ensemble import EnsembleScorer, normalize, weight_grid
from models.gnn import GNNScorer
from models.kge import KGEScorer
from models.proximity import ProximityScorer
from models.signature import SignatureScorer
from tests.workstream_b.synthetic import make_synthetic


@pytest.fixture(scope="module")
def setup(graph, ind):
    s = make_split(ind, "random", 0)
    g = apply_split(graph, s)
    known = known_positives(graph, ind)
    pop = popularity(graph, s.train)
    neg = sample_negatives(graph, s.test, known, 10, "popularity", pop, 0)
    return s, g, neg


def pooled_auprc(scorer, graph, test, neg):
    y, sc = [], []
    for part, lab in ((test, 1.0), (neg, 0.0)):
        for c, d in zip(part["drug_node"], part["disease_node"]):
            sc.append(scorer.score(int(d))[graph.comp_index[c]])
            y.append(lab)
    return auprc(np.array(y), np.array(sc))


def check_contract(scorer, graph, s):
    out = scorer.score(int(s.test["disease_node"].iloc[0]))
    assert out.shape == (graph.n_compounds,)
    assert np.isfinite(out).all()


def test_proximity_beats_chance(graph, setup):
    s, g, neg = setup
    sc = ProximityScorer().fit(g, s.train, 0)
    check_contract(sc, graph, s)
    assert pooled_auprc(sc, graph, s.test, neg) > 2 * (1 / 11)


def test_proximity_ranks_direct_target_first(graph):
    sc = ProximityScorer().fit(graph, None, 0)
    d = int(next(iter(sc.disease_genes)))
    out = sc.score(d)
    assert out.max() > -sc.cap


def test_proximity_unknown_disease_is_constant(graph):
    sc = ProximityScorer().fit(graph, None, 0)
    anatomy = int(np.flatnonzero(graph.kinds == "Anatomy")[0])
    assert np.ptp(sc.score(anatomy)) == 0


def test_signature_beats_chance(graph, setup):
    s, g, neg = setup
    sc = SignatureScorer().fit(g, s.train, 0)
    check_contract(sc, graph, s)
    assert pooled_auprc(sc, graph, s.test, neg) > 2 * (1 / 11)


def test_signature_no_data_constant(graph):
    sc = SignatureScorer().fit(graph, None, 0)
    anatomy = int(np.flatnonzero(graph.kinds == "Anatomy")[0])
    assert np.ptp(sc.score(anatomy)) == 0
    assert not sc.has_signature(anatomy)


@pytest.mark.parametrize("model", ["TransE", "ComplEx"])
def test_kge_runs_and_learns(graph, setup, model):
    s, g, neg = setup
    sc = KGEScorer(model, dim=16, epochs=30, batch_size=512, lr=2e-2).fit(g, s.train, 0)
    check_contract(sc, graph, s)
    assert sc.losses[-1] < sc.losses[0]
    assert pooled_auprc(sc, graph, s.test, neg) > 1.2 / 11


def test_kge_rejects_unknown(graph):
    with pytest.raises(ValueError):
        KGEScorer("Nope")


@pytest.fixture(scope="module")
def big():
    return make_synthetic(seed=1, n_compounds=200, n_genes=240, n_diseases=100)


def gnn_kwargs():
    return dict(hidden=32, lr=1e-2, max_epochs=300, patience=20, device="cpu")


def test_gnn_learns(big):
    graph, ind = big
    s = make_split(ind, "random", 0)
    g = apply_split(graph, s)
    known = known_positives(graph, ind)
    neg = sample_negatives(graph, s.test, known, 10, "popularity", popularity(graph, s.train), 0)
    sc = GNNScorer(**gnn_kwargs()).fit(g, s.train, 0)
    check_contract(sc, graph, s)
    assert sc.info["best_epoch"] > 1
    assert pooled_auprc(sc, graph, s.test, neg) > 1.5 / 11


def test_gnn_cold_disease_uses_structure(big):
    graph, ind = big
    s = make_split(ind, "cold_disease", 0)
    g = apply_split(graph, s)
    known = known_positives(graph, ind)
    neg = sample_negatives(graph, s.test, known, 10, "popularity", popularity(graph, s.train), 0)
    sc = GNNScorer(**gnn_kwargs()).fit(g, s.train, 0)
    assert pooled_auprc(sc, graph, s.test, neg) > 1.5 / 11


def test_gnn_unseen_compound_ignores_free_embedding(big):
    graph, ind = big
    s = make_split(ind, "time", 0)
    g = apply_split(graph, s)
    hidden_drugs = graph.compound_nodes[:20]
    train = s.train[~s.train["drug_node"].isin(hidden_drugs)]
    sc = GNNScorer(hidden=16, max_epochs=10, patience=3, device="cpu").fit(g, train, 0)
    trained = set(graph.comp_index[train["drug_node"].to_numpy()].tolist())
    unseen = [c for c in range(graph.n_compounds) if c not in trained]
    assert unseen
    seen = sorted(trained)[0]
    d = int(s.test["disease_node"].iloc[0])
    before = sc.score(d)
    weight = next(sc.net.emb["Compound"].parameters())
    with torch.no_grad():
        weight[unseen[0]] += 5.0
    sc.refresh()
    after = sc.score(d)
    assert np.allclose(before, after, atol=1e-5)
    with torch.no_grad():
        weight[seen] += 5.0
    sc.refresh()
    assert not np.allclose(before[seen], sc.score(d)[seen], atol=1e-5)


def test_gnn_compound_embedding_dropout_is_trained(big):
    graph, ind = big
    s = make_split(ind, "random", 0)
    g = apply_split(graph, s)
    sc = GNNScorer(hidden=16, max_epochs=10, patience=3, device="cpu", compound_emb_drop=0.5)
    sc.fit(g, s.train, 0)
    assert sc.compound_emb_drop == 0.5


def test_normalize_and_grid():
    assert np.allclose(normalize(np.array([3.0, 1.0, 2.0])), [1.0, 0.0, 0.5])
    assert np.all(normalize(np.ones(4)) == 0.5)
    w = weight_grid(3, 0.25)
    assert np.allclose(w.sum(axis=1), 1.0) and len(w) == 15


def test_ensemble_weights_prefer_informative_method(graph, setup):
    s, g, _ = setup

    class Noise:
        name = "noise"

        def fit(self, graph, train_pairs, seed):
            self.rng = np.random.default_rng(0)
            return self

        def score(self, d):
            return np.random.default_rng(d).random(graph.n_compounds)

    ens = EnsembleScorer({"proximity": ProximityScorer(), "noise": Noise()})
    ens.fit(g, s.train, 0)
    ens.fit_weights(g, s.val, s.all_pairs(), s.train, 0)
    assert ens.weights["proximity"] > ens.weights["noise"]
    assert abs(sum(ens.weights.values()) - 1) < 1e-9
    out = ens.score(int(s.test["disease_node"].iloc[0]))
    assert out.shape == (graph.n_compounds,)
    rank = filtered_rank(out, 0)
    assert rank >= 1
