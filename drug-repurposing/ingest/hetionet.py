from pathlib import Path

import pandas as pd

from ingest import common

NAME = "Hetionet"
VERSION = "v1.0"
BASE = "https://github.com/hetio/hetionet/raw/main/hetnet/tsv/"
NODES_FILE = "hetionet-v1.0-nodes.tsv"
EDGES_FILE = "hetionet-v1.0-edges.sif.gz"
LICENSE = "CC0 1.0"


def download(dest_dir: Path) -> Path:
    target = dest_dir / "hetionet"
    for name in (NODES_FILE, EDGES_FILE):
        common.download_file(BASE + name, target / name)
    return target


def parse(path: Path) -> pd.DataFrame:
    edges = path / EDGES_FILE if path.is_dir() else path
    return pd.read_csv(edges, sep="\t", dtype=str, keep_default_na=False)


def parse_nodes(path: Path) -> pd.DataFrame:
    nodes = path / NODES_FILE if path.is_dir() else path
    return pd.read_csv(nodes, sep="\t", dtype=str, keep_default_na=False)
