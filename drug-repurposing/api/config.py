import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    graph_dir: Path
    candidates_path: Path
    cache_dir: Path
    offline: bool
    http_timeout: float
    max_paths: int
    max_path_search_nodes: int

    @classmethod
    def from_env(cls) -> "Settings":
        data = Path(os.environ.get("DR_DATA_DIR", ROOT / "data"))
        return cls(
            graph_dir=Path(os.environ.get("DR_GRAPH_DIR", data / "graph")),
            candidates_path=Path(
                os.environ.get("DR_CANDIDATES", data / "results" / "candidates.parquet")
            ),
            cache_dir=Path(os.environ.get("DR_CACHE_DIR", data / "cache" / "evidence")),
            offline=os.environ.get("DR_OFFLINE", "0") == "1",
            http_timeout=float(os.environ.get("DR_HTTP_TIMEOUT", "6")),
            max_paths=int(os.environ.get("DR_MAX_PATHS", "3")),
            max_path_search_nodes=int(os.environ.get("DR_MAX_PATH_NODES", "5000")),
        )
