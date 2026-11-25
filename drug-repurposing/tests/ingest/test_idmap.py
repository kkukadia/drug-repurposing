from pathlib import Path

import pandas as pd

from ingest import idmap


def test_map_values_records_unmapped() -> None:
    values = pd.Series(["a", "b", "c", "a"])
    mapped, report = idmap.map_values("demo", values, {"a": 1, "b": 2})
    assert mapped.isna().tolist() == [False, False, True, False]
    assert mapped.dropna().astype(int).tolist() == [1, 2, 1]
    assert report.total == 3
    assert report.mapped == 2
    assert report.unmapped_ids == ["c"]
    assert abs(report.coverage - 2 / 3) < 1e-9


def test_report_as_dict_and_write(tmp_path: Path) -> None:
    _, report = idmap.map_values("demo", pd.Series(["x", "y"]), {"x": 1})
    path = report.write_unmapped(tmp_path)
    assert path.read_text().splitlines() == ["y"]
    d = report.as_dict(path)
    assert d["total_unique"] == 2 and d["mapped_unique"] == 1 and d["unmapped_unique"] == 1
    assert d["coverage"] == 0.5
    assert d["unmapped_file"].endswith("demo.txt")


def test_empty_report_coverage_is_one() -> None:
    _, report = idmap.map_values("empty", pd.Series([], dtype=str), {})
    assert report.coverage == 1.0
