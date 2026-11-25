import gzip
from pathlib import Path

import pandas as pd

from ingest import common

NAME = "DrugCentral"
VERSION = "2023-11-01"
DUMP_URL = "https://unmtid-dbs.net/download/DrugCentral/2023-11-01/drugcentral.dump.11012023.sql.gz"
DUMP_FILE = "drugcentral.dump.11012023.sql.gz"
APPROVALS_FILE = "approvals.tsv"
LICENSE = "CC BY-SA 4.0"
NULL = "\\N"


def collect_copy_blocks(dump: Path, tables: set[str]) -> dict[str, list[list[str]]]:
    blocks: dict[str, list[list[str]]] = {name: [] for name in tables}
    current: str | None = None
    with gzip.open(dump, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if current is None:
                if line.startswith("COPY public."):
                    name = line.split()[1].removeprefix("public.")
                    if name in tables:
                        current = name
                continue
            if line.startswith("\\."):
                current = None
                if all(blocks[name] for name in tables):
                    break
                continue
            blocks[current].append(line.rstrip("\n").split("\t"))
    return blocks


def extract(dump: Path, dest: Path) -> Path:
    blocks = collect_copy_blocks(dump, {"approval", "identifier"})
    ids: dict[str, list[str]] = {}
    for row in blocks["identifier"]:
        if row[2] == "DRUGBANK_ID":
            ids.setdefault(row[3], []).append(row[1])
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w") as out:
        out.write("drugbank_id\tagency\tapproval_date\n")
        for row in blocks["approval"]:
            for drugbank_id in ids.get(row[1], []):
                out.write(f"{drugbank_id}\t{row[3]}\t{row[2]}\n")
    return dest


def download(dest_dir: Path) -> Path:
    target = dest_dir / "drugcentral"
    dump = common.download_file(DUMP_URL, target / DUMP_FILE)
    out = target / APPROVALS_FILE
    if not out.exists() or not common.meta_path(out).exists():
        extract(dump, out)
        common.write_meta(out, DUMP_URL)
    return out


def parse(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    df["approval_date"] = pd.to_datetime(df.approval_date.replace(NULL, None), errors="coerce")
    return df


def first_approval_year(df: pd.DataFrame) -> pd.DataFrame:
    dated = df.dropna(subset=["approval_date"]).assign(year=lambda d: d.approval_date.dt.year)
    dated = dated.assign(priority=(dated.agency != "FDA").astype(int))
    dated = dated.sort_values(["drugbank_id", "priority", "year"])
    best = dated.drop_duplicates("drugbank_id")
    out = best[["drugbank_id", "year", "agency"]].reset_index(drop=True)
    out["year"] = out.year.astype("int64")
    return out
