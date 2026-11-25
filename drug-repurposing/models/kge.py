from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from pykeen.models import ComplEx, TransE
from pykeen.training import SLCWATrainingLoop
from pykeen.triples import TriplesFactory

from models.graph_data import TREATS, GraphData

MODELS = {"TransE": TransE, "ComplEx": ComplEx}


class KGEScorer:
    def __init__(
        self,
        model: str = "TransE",
        dim: int = 64,
        epochs: int = 30,
        batch_size: int = 8192,
        lr: float = 5e-3,
        num_negs: int = 8,
        treats_repeat: int = 1,
        device: str = "cpu",
    ):
        if model not in MODELS:
            raise ValueError(f"unknown KGE model {model}")
        self.model_name = model
        self.name = model.lower()
        self.dim = dim
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.num_negs = num_negs
        self.treats_repeat = treats_repeat
        self.device = device
        self.losses: list[float] = []

    def fit(self, graph: GraphData, train_pairs: pd.DataFrame, seed: int) -> KGEScorer:
        torch.manual_seed(seed)
        np.random.seed(seed)
        e = graph.edges
        etypes = sorted(set(e["etype"]) | {TREATS})
        rel_to_id = {r: i for i, r in enumerate(etypes)}
        rel = e["etype"].map(rel_to_id).to_numpy()
        triples = np.stack([e["src"].to_numpy(), rel, e["dst"].to_numpy()], axis=1)
        if self.treats_repeat > 1:
            t = triples[rel == rel_to_id[TREATS]]
            triples = np.concatenate([triples] + [t] * (self.treats_repeat - 1))
        ent_to_id = {str(i): i for i in range(graph.n_nodes)}
        tf = TriplesFactory(
            mapped_triples=torch.as_tensor(triples, dtype=torch.long),
            entity_to_id=ent_to_id,
            relation_to_id=rel_to_id,
            create_inverse_triples=False,
        )
        model = MODELS[self.model_name](
            triples_factory=tf, embedding_dim=self.dim, random_seed=seed
        ).to(self.device)
        opt = torch.optim.Adam(model.get_grad_params(), lr=self.lr)
        loop = SLCWATrainingLoop(
            model=model,
            triples_factory=tf,
            optimizer=opt,
            negative_sampler_kwargs={"num_negs_per_pos": self.num_negs},
        )
        losses = loop.train(
            triples_factory=tf,
            num_epochs=self.epochs,
            batch_size=self.batch_size,
            use_tqdm=False,
            use_tqdm_batch=False,
        )
        self.losses = [float(x) for x in (losses or [])]
        model.eval()
        self.model = model
        self.rel_id = rel_to_id[TREATS]
        self.comp_nodes = torch.as_tensor(graph.compound_nodes, dtype=torch.long)
        return self

    def score(self, disease_node: int) -> np.ndarray:
        rt = torch.tensor([[self.rel_id, int(disease_node)]], device=self.device)
        with torch.no_grad():
            s = self.model.score_h(rt).reshape(-1)
        return s[self.comp_nodes.to(s.device)].detach().cpu().numpy().astype(float)
