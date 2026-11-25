from __future__ import annotations

import copy
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import HeteroConv, SAGEConv

from eval.metrics import auprc
from models.graph_data import COMPOUND, DISEASE, TREATS, GraphData


def pick_device(name: str | None) -> torch.device:
    if name:
        return torch.device(name)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class Net(nn.Module):
    def __init__(
        self,
        counts: dict[str, int],
        feat_dim: dict[str, int],
        edge_types: list[tuple[str, str, str]],
        hidden: int,
        layers: int,
        dropout: float,
    ):
        super().__init__()
        embs = {k: nn.Embedding(n, hidden) for k, n in counts.items()}
        for e in embs.values():
            nn.init.normal_(e.weight, std=0.1)
        self.emb = nn.ModuleDict(embs)
        self.lin = nn.ModuleDict({k: nn.Linear(feat_dim[k], hidden) for k in counts})
        self.convs = nn.ModuleList(
            [
                HeteroConv({et: SAGEConv((-1, -1), hidden) for et in edge_types}, aggr="sum")
                for _ in range(layers)
            ]
        )
        self.norms = nn.ModuleList(
            [nn.ModuleDict({k: nn.LayerNorm(hidden) for k in counts}) for _ in range(layers)]
        )
        self.dropout = dropout
        self.dec = nn.Sequential(
            nn.Linear(hidden * 3, hidden), nn.ReLU(), nn.Dropout(dropout), nn.Linear(hidden, 1)
        )

    def encode(self, feats, edge_index, disease_keep, compound_keep):
        x = {}
        for k, emb in self.emb.items():
            e = emb.weight
            if k == DISEASE:
                e = e * disease_keep.unsqueeze(1)
            elif k == COMPOUND:
                e = e * compound_keep.unsqueeze(1)
            x[k] = self.lin[k](feats[k]) + e
        for conv, norm in zip(self.convs, self.norms):
            norm_d: nn.ModuleDict = norm  # type: ignore[assignment]
            out = conv(x, edge_index)
            nxt = {}
            for k in x:
                h = out.get(k)
                if h is None:
                    nxt[k] = x[k]
                else:
                    h = F.dropout(F.relu(norm_d[k](h)), self.dropout, self.training)
                    nxt[k] = x[k] + h
            x = nxt
        return x

    def decode(self, hc, hd):
        return self.dec(torch.cat([hc * hd, hc, hd], dim=-1)).squeeze(-1)


class GNNScorer:
    name = "gnn"

    def __init__(
        self,
        hidden: int = 64,
        layers: int = 2,
        lr: float = 3e-3,
        weight_decay: float = 1e-5,
        dropout: float = 0.2,
        max_epochs: int = 400,
        patience: int = 12,
        eval_every: int = 5,
        neg_ratio: int = 5,
        mp_frac: float = 0.5,
        disease_emb_drop: float = 0.3,
        compound_emb_drop: float = 0.3,
        inner_val_frac: float = 0.1,
        device: str | None = None,
        verbose: bool = False,
    ):
        self.hidden = hidden
        self.layers = layers
        self.lr = lr
        self.weight_decay = weight_decay
        self.dropout = dropout
        self.max_epochs = max_epochs
        self.patience = patience
        self.eval_every = eval_every
        self.neg_ratio = neg_ratio
        self.mp_frac = mp_frac
        self.disease_emb_drop = disease_emb_drop
        self.compound_emb_drop = compound_emb_drop
        self.inner_val_frac = inner_val_frac
        self.device = pick_device(device)
        self.verbose = verbose
        self.info: dict = {}

    def _build(self, graph: GraphData):
        kinds = sorted(set(graph.kinds.tolist()))
        local = np.zeros(graph.n_nodes, dtype=np.int64)
        counts = {}
        for k in kinds:
            idx = np.flatnonzero(graph.kinds == k)
            local[idx] = np.arange(len(idx))
            counts[k] = len(idx)
        self.local = local
        self.counts = counts
        e = graph.edges
        e = e[e["etype"] != TREATS]
        s, d = e["src"].to_numpy(), e["dst"].to_numpy()
        sk, dk = graph.kinds[s], graph.kinds[d]
        ei: dict[tuple[str, str, str], torch.Tensor] = {}
        key = pd.Series(list(zip(sk, e["etype"].to_numpy(), dk)))
        for et, idx in key.groupby(key).groups.items():
            idx = np.asarray(idx)
            a, b = local[s[idx]], local[d[idx]]
            ei[et] = torch.as_tensor(np.stack([a, b]), dtype=torch.long)
            rev = (et[2], "rev_" + et[1], et[0])
            ei[rev] = ei[et].flip(0)
        self.static_ei = ei
        feat_cols = sorted({et[1] for et in ei})
        feats = {k: np.zeros((counts[k], len(feat_cols)), dtype=np.float32) for k in kinds}
        for et, t in ei.items():
            j = feat_cols.index(et[1])
            np.add.at(feats[et[2]][:, j], t[1].numpy(), 1.0)
        self.feats = {k: torch.log1p(torch.as_tensor(v)).to(self.device) for k, v in feats.items()}
        self.feat_dim = {k: len(feat_cols) for k in kinds}
        self.edge_types = list(ei.keys()) + [
            (COMPOUND, "treats", DISEASE),
            (DISEASE, "rev_treats", COMPOUND),
        ]

    def _edge_index(self, mp_pairs: np.ndarray):
        ei = {k: v.to(self.device) for k, v in self.static_ei.items()}
        t = torch.as_tensor(mp_pairs.T.copy(), dtype=torch.long).reshape(2, -1).to(self.device)
        ei[(COMPOUND, "treats", DISEASE)] = t
        ei[(DISEASE, "rev_treats", COMPOUND)] = t.flip(0)
        return ei

    def _sample_neg(self, pos_c, pop_p, rng, known_keys, n_dis):
        n = len(pos_c) * self.neg_ratio
        half = n // 2
        nc = len(pop_p)
        neg = np.concatenate([rng.integers(0, nc, half), rng.choice(nc, n - half, p=pop_p)])
        return neg

    def fit(self, graph: GraphData, train_pairs: pd.DataFrame, seed: int) -> GNNScorer:
        t0 = time.time()
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        self._build(graph)
        dev = self.device
        nc, nd = graph.n_compounds, self.counts[DISEASE]
        disease_local = self.local
        ci = graph.comp_index[train_pairs["drug_node"].to_numpy()]
        di = disease_local[train_pairs["disease_node"].to_numpy()]
        pairs = np.stack([ci, di], axis=1)
        perm = rng.permutation(len(pairs))
        n_inner = max(1, int(len(pairs) * self.inner_val_frac))
        inner = pairs[perm[:n_inner]]
        fit_pairs = pairs[perm[n_inner:]]
        all_keys = np.sort(pairs[:, 0] * nd + pairs[:, 1])
        pop = np.bincount(fit_pairs[:, 0], minlength=nc).astype(float) + 1.0
        pop_p = pop / pop.sum()

        seen = np.zeros(nd, dtype=np.float32)
        seen[pairs[:, 1]] = 1.0
        seen_t = torch.as_tensor(seen, device=dev)
        seen_c = np.zeros(nc, dtype=np.float32)
        seen_c[pairs[:, 0]] = 1.0
        seen_ct = torch.as_tensor(seen_c, device=dev)

        net = Net(
            self.counts, self.feat_dim, self.edge_types, self.hidden, self.layers, self.dropout
        ).to(dev)
        with torch.no_grad():
            net.encode(self.feats, self._edge_index(fit_pairs), seen_t, seen_ct)
        opt = torch.optim.AdamW(net.parameters(), lr=self.lr, weight_decay=self.weight_decay)

        def neg_for(pos_d: np.ndarray, r: np.random.Generator):
            reps = np.repeat(pos_d, self.neg_ratio)
            neg_c = self._sample_neg(pos_d, pop_p, r, None, nd)
            k = neg_c * nd + reps
            hit = np.isin(k, all_keys)
            neg_c[hit] = r.integers(0, nc, hit.sum())
            return neg_c, reps

        val_neg_c, val_neg_d = neg_for(inner[:, 1], np.random.default_rng(seed + 1))
        val_y = np.concatenate([np.ones(len(inner)), np.zeros(len(val_neg_c))])
        val_c = np.concatenate([inner[:, 0], val_neg_c])
        val_d = np.concatenate([inner[:, 1], val_neg_d])
        drop = self.disease_emb_drop
        drop_c = self.compound_emb_drop

        def evaluate() -> float:
            net.eval()
            with torch.no_grad():
                h = net.encode(self.feats, self._edge_index(fit_pairs), seen_t, seen_ct)
                s = net.decode(
                    h[COMPOUND][torch.as_tensor(val_c, device=dev)],
                    h[DISEASE][torch.as_tensor(val_d, device=dev)],
                )
            return auprc(val_y, s.cpu().numpy())

        best, best_state, best_ep, bad = -1.0, None, 0, 0
        history = []
        for ep in range(1, self.max_epochs + 1):
            net.train()
            msk = rng.random(len(fit_pairs)) < self.mp_frac
            mp, sup = fit_pairs[msk], fit_pairs[~msk]
            if len(sup) == 0:
                sup = fit_pairs
            keep = seen_t * (torch.rand(nd, device=dev) >= drop).float()
            keep_c = seen_ct * (torch.rand(nc, device=dev) >= drop_c).float()
            h = net.encode(self.feats, self._edge_index(mp), keep, keep_c)
            neg_c, neg_d = neg_for(sup[:, 1], rng)
            cs = torch.as_tensor(np.concatenate([sup[:, 0], neg_c]), device=dev)
            ds = torch.as_tensor(np.concatenate([sup[:, 1], neg_d]), device=dev)
            y = torch.cat([torch.ones(len(sup)), torch.zeros(len(neg_c))]).to(dev)
            logit = net.decode(h[COMPOUND][cs], h[DISEASE][ds])
            loss = F.binary_cross_entropy_with_logits(logit, y)
            opt.zero_grad()
            loss.backward()
            opt.step()
            if ep % self.eval_every == 0:
                v = evaluate()
                history.append((ep, float(loss.item()), v))
                if self.verbose:
                    print(f"ep {ep} loss {loss.item():.4f} val_auprc {v:.4f}", flush=True)
                if v > best + 1e-4:
                    best, best_ep, bad = v, ep, 0
                    best_state = copy.deepcopy(net.state_dict())
                else:
                    bad += 1
                    if bad >= self.patience:
                        break
        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()
        self.net = net
        self._final = (self._edge_index(pairs), seen_t, seen_ct)
        self.refresh()
        self.info = {
            "epochs_run": ep,
            "best_epoch": best_ep,
            "best_inner_val_auprc": best,
            "converged": bad >= self.patience,
            "history": history,
            "fit_seconds": time.time() - t0,
            "device": str(dev),
        }
        return self

    def refresh(self) -> None:
        ei, seen_d, seen_c = self._final
        self.net.eval()
        with torch.no_grad():
            h = self.net.encode(self.feats, ei, seen_d, seen_c)
        self.hc = h[COMPOUND].detach()
        self.hd = h[DISEASE].detach()

    def score(self, disease_node: int) -> np.ndarray:
        d = int(self.local[int(disease_node)])
        with torch.no_grad():
            hd = self.hd[d].unsqueeze(0).expand(self.hc.shape[0], -1)
            s = self.net.decode(self.hc, hd)
        return s.cpu().numpy().astype(float)
