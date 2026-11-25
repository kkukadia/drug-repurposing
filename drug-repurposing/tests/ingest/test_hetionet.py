from pathlib import Path

import pytest

from ingest import hetionet

FIX = Path(__file__).parent.parent / "fixtures" / "hetionet"


def test_parse_edges_columns_and_rows() -> None:
    df = hetionet.parse(FIX)
    assert list(df.columns) == ["source", "metaedge", "target"]
    assert len(df) == 17
    assert set(df.metaedge) >= {"CbG", "CtD", "CpD", "CuG", "CdG", "DaG", "DuG", "GiG"}


def test_parse_nodes_columns_and_rows() -> None:
    df = hetionet.parse_nodes(FIX)
    assert list(df.columns) == ["id", "name", "kind"]
    assert len(df) == 13
    assert df.id.is_unique
    assert "Side Effect" in set(df.kind)


def test_download_fetches_both_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path]] = []

    def fake(url: str, dest: Path, client: object = None) -> Path:
        calls.append((url, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("x")
        return dest

    monkeypatch.setattr(hetionet.common, "download_file", fake)
    out = hetionet.download(tmp_path)
    assert out == tmp_path / "hetionet"
    assert {Path(d).name for _, d in calls} == {
        "hetionet-v1.0-nodes.tsv",
        "hetionet-v1.0-edges.sif.gz",
    }
    assert all(u.startswith("https://github.com/hetio/hetionet/raw/main/") for u, _ in calls)
