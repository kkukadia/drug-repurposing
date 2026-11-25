import shutil
from pathlib import Path

import pytest

from ingest import approvals, common

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def raw_dir(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    shutil.copytree(FIX / "hetionet", raw / "hetionet")
    shutil.copytree(FIX / "stringdb", raw / "stringdb")
    (raw / "drugcentral").mkdir(parents=True)
    approvals.extract(
        FIX / "drugcentral" / "mini_dump.sql.gz", raw / "drugcentral" / "approvals.tsv"
    )
    for sub in ("hetionet", "stringdb", "drugcentral"):
        for f in sorted((raw / sub).iterdir()):
            common.write_meta(f, f"https://example.org/{f.name}")
    return raw
