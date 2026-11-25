from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from models.graph_data import DISEASE, TREATS, GraphData

KINDS = ("random", "time", "cold_disease", "repurposing")
PAIR_COLS = ["drug_node", "disease_node"]


@dataclass
class Split:
    kind: str
    seed: int
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    held_out_diseases: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    cutoff_year: int | None = None
    removal_stats: dict[str, int] = field(default_factory=dict)

    def all_pairs(self) -> pd.DataFrame:
        return pd.concat([self.train, self.val, self.test])[PAIR_COLS].reset_index(drop=True)


def pair_keys(drug: np.ndarray, disease: np.ndarray, n_nodes: int) -> np.ndarray:
    return drug.astype(np.int64) * np.int64(n_nodes) + disease.astype(np.int64)


def _frames(ind: pd.DataFrame, tr: np.ndarray, va: np.ndarray, te: np.ndarray):
    return (
        ind[tr].reset_index(drop=True),
        ind[va].reset_index(drop=True),
        ind[te].reset_index(drop=True),
    )


def _random(ind: pd.DataFrame, seed: int, test_frac: float, val_frac: float) -> Split:
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(ind))
    n_te = max(1, int(round(len(ind) * test_frac)))
    n_va = max(1, int(round(len(ind) * val_frac)))
    role = np.zeros(len(ind), dtype=np.int8)
    role[perm[:n_te]] = 2
    role[perm[n_te : n_te + n_va]] = 1
    return Split("random", seed, *_frames(ind, role == 0, role == 1, role == 2))


def _year_cutoff(years: np.ndarray, frac: float) -> int:
    uniq = np.unique(years)
    n = len(years)
    best = int(uniq[-1])
    for y in uniq[::-1]:
        if (years >= y).sum() <= frac * n:
            best = int(y)
        else:
            break
    return best


def _time(ind: pd.DataFrame, seed: int, test_frac: float, val_frac: float) -> Split:
    year = ind["year"].astype("Float64").to_numpy(dtype=float, na_value=np.nan)
    dated = ~np.isnan(year)
    if dated.sum() < 3:
        raise ValueError("time split needs dated indications")
    dy = year[dated]
    cut_test = _year_cutoff(dy, test_frac)
    below = dy[dy < cut_test]
    cut_val = _year_cutoff(below, val_frac / max(1e-9, 1 - test_frac)) if len(below) else cut_test
    te = dated & (year >= cut_test)
    va = dated & (year >= cut_val) & (year < cut_test)
    tr = ~(te | va)
    s = Split("time", seed, *_frames(ind, tr, va, te))
    s.cutoff_year = cut_test
    return s


def _cold(ind: pd.DataFrame, seed: int, test_frac: float, val_frac: float) -> Split:
    rng = np.random.default_rng(seed)
    diseases = np.sort(ind["disease_node"].unique())
    perm = rng.permutation(diseases)
    n_te = max(1, int(round(len(diseases) * test_frac)))
    n_va = max(1, int(round(len(diseases) * val_frac)))
    te_d = perm[:n_te]
    va_d = perm[n_te : n_te + n_va]
    d = ind["disease_node"].to_numpy()
    te = np.isin(d, te_d)
    va = np.isin(d, va_d)
    s = Split("cold_disease", seed, *_frames(ind, ~(te | va), va, te))
    s.held_out_diseases = np.sort(np.concatenate([te_d, va_d])).astype(np.int64)
    return s


def _repurposing(ind: pd.DataFrame, seed: int, val_share: float = 0.25) -> Split:
    rng = np.random.default_rng(seed)
    year = ind["year"].astype("Float64").to_numpy(dtype=float, na_value=np.nan)
    jitter = rng.random(len(ind))
    order_key = np.where(np.isnan(year), -1.0, year) + jitter * 1e-3
    frame = pd.DataFrame(
        {"i": np.arange(len(ind)), "drug": ind["drug_node"].to_numpy(), "k": order_key}
    )
    counts = frame.groupby("drug")["i"].transform("size")
    multi = frame[counts >= 2]
    pick = multi.sort_values("k").groupby("drug").tail(1)["i"].to_numpy()
    pick = rng.permutation(pick)
    n_va = int(round(len(pick) * val_share))
    role = np.zeros(len(ind), dtype=np.int8)
    role[pick[:n_va]] = 1
    role[pick[n_va:]] = 2
    return Split("repurposing", seed, *_frames(ind, role == 0, role == 1, role == 2))


def make_split(
    indications: pd.DataFrame,
    kind: str,
    seed: int,
    test_frac: float = 0.2,
    val_frac: float = 0.1,
) -> Split:
    if kind not in KINDS:
        raise ValueError(f"unknown split kind {kind}")
    ind = indications.drop_duplicates(PAIR_COLS).reset_index(drop=True)
    if "year" not in ind:
        ind["year"] = pd.array([pd.NA] * len(ind), dtype="Int64")
    if kind == "random":
        return _random(ind, seed, test_frac, val_frac)
    if kind == "time":
        return _time(ind, seed, test_frac, val_frac)
    if kind == "cold_disease":
        return _cold(ind, seed, test_frac, val_frac)
    return _repurposing(ind, seed)


def leaking_edge_mask(graph: GraphData, split: Split) -> tuple[np.ndarray, dict[str, int]]:
    n = graph.n_nodes
    e = graph.edges
    src = e["src"].to_numpy()
    dst = e["dst"].to_numpy()
    ks, kd = graph.kinds[src], graph.kinds[dst]
    cd_fwd = (ks == "Compound") & (kd == DISEASE)
    cd_rev = (ks == DISEASE) & (kd == "Compound")
    drug = np.where(cd_fwd, src, dst)
    dis = np.where(cd_fwd, dst, src)
    is_cd = cd_fwd | cd_rev
    keys = pair_keys(drug, dis, n)

    held = pd.concat([split.val, split.test])
    held_keys = pair_keys(held["drug_node"].to_numpy(), held["disease_node"].to_numpy(), n)
    train_keys = pair_keys(
        split.train["drug_node"].to_numpy(), split.train["disease_node"].to_numpy(), n
    )
    direct = is_cd & np.isin(keys, held_keys)
    cold = is_cd & np.isin(dis, split.held_out_diseases)

    dd = (ks == DISEASE) & (kd == DISEASE)
    related: set[int] = set()
    if dd.any() and len(held):
        nbr: dict[int, list[int]] = {}
        for a, b in zip(src[dd], dst[dd]):
            nbr.setdefault(int(a), []).append(int(b))
            nbr.setdefault(int(b), []).append(int(a))
        for c, d in zip(held["drug_node"].to_numpy(), held["disease_node"].to_numpy()):
            for m in nbr.get(int(d), ()):
                related.add(int(c) * n + m)
    indirect = np.zeros(len(e), dtype=bool)
    if related:
        indirect = (
            is_cd
            & np.isin(keys, np.fromiter(related, dtype=np.int64, count=len(related)))
            & ~np.isin(keys, train_keys)
        )
    mask = direct | cold | indirect
    stats = {
        "removed_direct_pair_edges": int(direct.sum()),
        "removed_cold_disease_edges": int((cold & ~direct).sum()),
        "removed_indirect_hierarchy_edges": int((indirect & ~direct & ~cold).sum()),
        "removed_total": int(mask.sum()),
    }
    return mask, stats


def apply_split(graph: GraphData, split: Split) -> GraphData:
    mask, stats = leaking_edge_mask(graph, split)
    split.removal_stats = stats
    kept = graph.edges[~mask]
    n = graph.n_nodes
    e = kept
    src = e["src"].to_numpy()
    dst = e["dst"].to_numpy()
    have = pair_keys(src, dst, n)
    want = pair_keys(split.train["drug_node"].to_numpy(), split.train["disease_node"].to_numpy(), n)
    missing = ~np.isin(want, have)
    if missing.any():
        add = pd.DataFrame(
            {
                "src": split.train["drug_node"].to_numpy()[missing],
                "dst": split.train["disease_node"].to_numpy()[missing],
                "etype": TREATS,
                "source": "train_pairs",
                "source_version": "",
                "weight": np.nan,
            }
        )
        kept = pd.concat([kept, add], ignore_index=True)
    return graph.with_edges(kept)


def known_positives(graph: GraphData, pairs: pd.DataFrame) -> dict[int, np.ndarray]:
    ci = graph.comp_index[pairs["drug_node"].to_numpy()]
    out: dict[int, np.ndarray] = {}
    for d, g in pd.DataFrame({"d": pairs["disease_node"].to_numpy(), "c": ci}).groupby("d"):
        out[int(d)] = np.unique(g["c"].to_numpy())  # type: ignore[call-overload]
    return out


def popularity(graph: GraphData, train: pd.DataFrame) -> np.ndarray:
    ci = graph.comp_index[train["drug_node"].to_numpy()]
    ci = ci[ci >= 0]
    return np.bincount(ci, minlength=graph.n_compounds).astype(float) + 1.0


def sample_negatives(
    graph: GraphData,
    positives: pd.DataFrame,
    known: dict[int, np.ndarray],
    ratio: int,
    strategy: str,
    pop: np.ndarray,
    seed: int,
) -> pd.DataFrame:
    if strategy not in ("uniform", "popularity"):
        raise ValueError(f"unknown negative strategy {strategy}")
    rng = np.random.default_rng(seed)
    nc = graph.n_compounds
    p = np.full(nc, 1.0 / nc) if strategy == "uniform" else pop / pop.sum()
    rows_c, rows_d, rows_i = [], [], []
    for i, d in enumerate(positives["disease_node"].to_numpy()):
        banned = known.get(int(d), np.zeros(0, dtype=np.int64))
        if len(banned) >= nc:
            continue
        need = min(ratio, nc - len(banned))
        got: list[int] = []
        while len(got) < need:
            draw = rng.choice(nc, size=ratio * 2, p=p)
            ok = [int(x) for x in dict.fromkeys(draw[~np.isin(draw, banned)]) if x not in got]
            got.extend(ok[: need - len(got)])
        rows_c.extend(got)
        rows_d.extend([int(d)] * need)
        rows_i.extend([i] * need)
    return pd.DataFrame(
        {
            "drug_node": graph.compound_nodes[np.array(rows_c, dtype=np.int64)],
            "disease_node": np.array(rows_d, dtype=np.int64),
            "pos_index": np.array(rows_i, dtype=np.int64),
        }
    )
