import logging
from dataclasses import dataclass, field

import pandas as pd

from api.config import Settings
from api.paths import GraphIndex

log = logging.getLogger(__name__)

RESERVED = {"disease_node", "drug_node", "score", "rank", "method_scores"}


@dataclass
class Store:
    index: GraphIndex | None = None
    candidates: pd.DataFrame = field(default_factory=pd.DataFrame)
    method_columns: list[str] = field(default_factory=list)
    disease_by_ext: dict[str, int] = field(default_factory=dict)
    diseases: list[tuple[str, str, int]] = field(default_factory=list)

    @classmethod
    def load(cls, settings: Settings) -> "Store":
        store = cls()
        nodes_path = settings.graph_dir / "nodes.parquet"
        edges_path = settings.graph_dir / "edges.parquet"
        if nodes_path.exists() and edges_path.exists():
            store.index = GraphIndex.build(pd.read_parquet(nodes_path), pd.read_parquet(edges_path))
        else:
            log.warning("graph artifacts not found in %s", settings.graph_dir)
        if settings.candidates_path.exists():
            cands = pd.read_parquet(settings.candidates_path)
            cands["disease_node"] = cands["disease_node"].astype(int)
            cands["drug_node"] = cands["drug_node"].astype(int)
            store.candidates = cands
            store.method_columns = [
                c
                for c in cands.columns
                if c not in RESERVED and pd.api.types.is_numeric_dtype(cands[c])
            ]
        else:
            log.warning("candidates not found at %s", settings.candidates_path)
        if store.index is not None and not store.candidates.empty:
            present = set(store.candidates["disease_node"].unique())
            for nid in sorted(present):
                if store.index.kind(nid) == "Disease":
                    ext = store.index.ext_ids[nid]
                    store.diseases.append((ext, store.index.names[nid], nid))
                    store.disease_by_ext[ext] = nid
        return store
