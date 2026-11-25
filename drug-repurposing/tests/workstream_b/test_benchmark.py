import json

from eval.run_benchmark import STAGES, aggregate, run_one, write_report

CFG = {
    "kge_epochs": 2,
    "kge_dim": 8,
    "gnn": {"hidden": 16, "max_epochs": 20, "patience": 2, "device": "cpu", "lr": 1e-2},
}


def test_run_one_and_report(graph, ind, tmp_path):
    parts = [run_one(graph, ind, st, 0, CFG) for st in STAGES]
    parts += [run_one(graph, ind, "random", 1, CFG)]
    for p in parts:
        json.dumps(p, default=float)
        assert set(p["metrics"]) == {
            "proximity",
            "signature",
            "transe",
            "complex",
            "gnn",
            "ensemble",
        }
        assert abs(sum(p["ensemble_weights"].values()) - 1) < 1e-9
        assert p["split"]["removal"]["removed_total"] > 0
    res = aggregate(parts, CFG, {"build_timestamp": "x"})
    assert res["stages"]["random"]["seeds"] == [0, 1]
    assert "auprc_popularity" in res["stages"]["random"]["metrics"]["gnn"]
    out = tmp_path / "r.md"
    pro = {
        "n_pairs": 1,
        "n_evaluated": 1,
        "n_supported": 1,
        "share_supported": 1.0,
        "n_with_trials": 1,
        "n_with_papers": 0,
        "criteria": {"min_papers": 3, "min_trials": 1},
        "disclaimer": "not evidence of clinical validity",
        "pairs": [
            {
                "disease": "dz",
                "drug": "rx",
                "rank": 1,
                "trials": 1,
                "papers": 0,
                "supported": True,
                "review_status": "needs manual review",
            }
        ],
    }
    write_report(res, out, pro)
    text = out.read_text()
    assert "## Run notes" in text
    assert "Seed counts" in text and "random: 2" in text and "time: 1" in text
    assert "below the required 5" in text
    assert "## Stage 5: prospective check" in text and "needs manual review" in text
    assert "unseen compounds" in text
    assert "Leakage controls" in text and "Negative sampling" in text
    assert "Stage 4" in text
