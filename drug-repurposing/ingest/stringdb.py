from pathlib import Path

import pandas as pd

from ingest import common

NAME = "STRING"
VERSION = "v12.0"
LINKS_URL = (
    "https://stringdb-downloads.org/download/protein.links.v12.0/9606.protein.links.v12.0.txt.gz"
)
INFO_URL = (
    "https://stringdb-downloads.org/download/protein.info.v12.0/9606.protein.info.v12.0.txt.gz"
)
LINKS_FILE = "9606.protein.links.v12.0.txt.gz"
INFO_FILE = "9606.protein.info.v12.0.txt.gz"
ALIASES_URL = "https://stringdb-downloads.org/download/protein.aliases.v12.0/9606.protein.aliases.v12.0.txt.gz"
ALIASES_FILE = "9606.protein.aliases.v12.0.txt.gz"
ENTREZ_SOURCE = "UniProt_DR_GeneID"
MIN_SCORE = 700
PREFIX = "9606."
LICENSE = "CC BY 4.0"


def download(dest_dir: Path) -> Path:
    target = dest_dir / "stringdb"
    common.download_file(LINKS_URL, target / LINKS_FILE)
    common.download_file(INFO_URL, target / INFO_FILE)
    common.download_file(ALIASES_URL, target / ALIASES_FILE)
    return target


def parse(path: Path, min_score: int = MIN_SCORE) -> pd.DataFrame:
    links = path / LINKS_FILE if path.is_dir() else path
    parts = []
    for chunk in pd.read_csv(links, sep=" ", chunksize=2_000_000):
        kept = chunk[chunk.combined_score >= min_score]
        kept = kept.assign(
            protein1=kept.protein1.str.removeprefix(PREFIX),
            protein2=kept.protein2.str.removeprefix(PREFIX),
        )
        kept = kept[kept.protein1 < kept.protein2]
        parts.append(kept)
    if not parts:
        return pd.DataFrame(columns=["protein1", "protein2", "combined_score"])
    merged = pd.concat(parts, ignore_index=True)
    return merged.drop_duplicates(["protein1", "protein2"]).reset_index(drop=True)


def parse_info(path: Path) -> pd.DataFrame:
    info = path / INFO_FILE if path.is_dir() else path
    df = pd.read_csv(info, sep="\t", usecols=[0, 1], dtype=str, keep_default_na=False)
    df.columns = ["protein", "symbol"]
    df["protein"] = df.protein.str.removeprefix(PREFIX)
    return df


def parse_aliases(path: Path) -> pd.DataFrame:
    aliases = path / ALIASES_FILE if path.is_dir() else path
    df = pd.read_csv(aliases, sep="\t", dtype=str, keep_default_na=False)
    df.columns = ["protein", "alias", "source"]
    df = df[df.source == ENTREZ_SOURCE]
    out = pd.DataFrame(
        {"protein": df.protein.str.removeprefix(PREFIX), "entrez": df.alias.to_numpy()}
    )
    return out.drop_duplicates().reset_index(drop=True)
