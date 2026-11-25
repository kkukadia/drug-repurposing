from __future__ import annotations

import numpy as np
from scipy import stats
from sklearn.metrics import average_precision_score, roc_auc_score


def auroc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, y_score))


def auprc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if y_true.sum() == 0:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def filtered_rank(scores: np.ndarray, target: int, exclude: np.ndarray | None = None) -> float:
    s = scores.astype(float).copy()
    t = s[target]
    keep = np.ones(len(s), dtype=bool)
    if exclude is not None and len(exclude):
        keep[exclude] = False
    keep[target] = False
    others = s[keep]
    return float(1.0 + (others > t).sum() + 0.5 * (others == t).sum())


def hits_at_k(ranks: np.ndarray, k: int) -> float:
    if len(ranks) == 0:
        return float("nan")
    return float((np.asarray(ranks) <= k).mean())


def recall_at_k(ranks: np.ndarray, k: int) -> float:
    return hits_at_k(ranks, k)


def mrr(ranks: np.ndarray) -> float:
    if len(ranks) == 0:
        return float("nan")
    return float((1.0 / np.asarray(ranks, dtype=float)).mean())


def ranking_summary(ranks: np.ndarray, ks: tuple[int, ...] = (1, 10, 20, 50)) -> dict[str, float]:
    out = {
        "mrr": mrr(ranks),
        "median_rank": float(np.median(ranks)) if len(ranks) else float("nan"),
    }
    for k in ks:
        out[f"hits@{k}"] = hits_at_k(ranks, k)
    out["recall@50"] = recall_at_k(ranks, 50)
    return out


def seed_ci(values: list[float] | np.ndarray, confidence: float = 0.95) -> dict[str, float]:
    v = np.asarray([x for x in values if not np.isnan(x)], dtype=float)
    n = len(v)
    if n == 0:
        return {
            "mean": float("nan"),
            "std": float("nan"),
            "lo": float("nan"),
            "hi": float("nan"),
            "n": 0,
        }
    mean = float(v.mean())
    if n == 1:
        return {"mean": mean, "std": 0.0, "lo": mean, "hi": mean, "n": 1}
    sd = float(v.std(ddof=1))
    half = float(stats.t.ppf(0.5 + confidence / 2, n - 1) * sd / np.sqrt(n))
    return {"mean": mean, "std": sd, "lo": mean - half, "hi": mean + half, "n": n}


def bootstrap_ci(
    values: np.ndarray, n_boot: int = 1000, confidence: float = 0.95, seed: int = 0
) -> dict[str, float]:
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_boot, len(v)))
    means = v[idx].mean(axis=1)
    a = (1 - confidence) / 2
    return {
        "mean": float(v.mean()),
        "lo": float(np.quantile(means, a)),
        "hi": float(np.quantile(means, 1 - a)),
    }
