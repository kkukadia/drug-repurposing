from pathlib import Path

import pandas as pd

from ingest import approvals

FIX = Path(__file__).parent.parent / "fixtures" / "drugcentral" / "mini_dump.sql.gz"


def test_extract_joins_drugbank_ids(tmp_path: Path) -> None:
    out = approvals.extract(FIX, tmp_path / "approvals.tsv")
    df = approvals.parse(out)
    assert list(df.columns) == ["drugbank_id", "agency", "approval_date"]
    assert set(df.drugbank_id) == {"DB00945", "DB01050", "DB00316", "DB07777"}
    assert len(df) == 6


def test_parse_null_dates_become_nat(tmp_path: Path) -> None:
    df = approvals.parse(approvals.extract(FIX, tmp_path / "approvals.tsv"))
    assert df[df.drugbank_id == "DB07777"].approval_date.isna().all()


def test_first_approval_year_prefers_fda_then_other_agency(tmp_path: Path) -> None:
    df = approvals.parse(approvals.extract(FIX, tmp_path / "approvals.tsv"))
    years = approvals.first_approval_year(df)
    assert list(years.columns) == ["drugbank_id", "year", "agency"]
    by = years.set_index("drugbank_id")
    assert by.loc["DB00945", "year"] == 1950 and by.loc["DB00945", "agency"] == "FDA"
    assert by.loc["DB00316", "year"] == 1998
    assert by.loc["DB01050", "year"] == 1999 and by.loc["DB01050", "agency"] == "EMA"
    assert "DB07777" not in by.index


def test_first_approval_year_dtype() -> None:
    df = pd.DataFrame(
        {
            "drugbank_id": ["A"],
            "agency": ["FDA"],
            "approval_date": pd.to_datetime(["2001-02-03"]),
        }
    )
    assert approvals.first_approval_year(df).year.iloc[0] == 2001
