from pathlib import Path

from ingest import stringdb

FIX = Path(__file__).parent.parent / "fixtures" / "stringdb"


def test_parse_filters_threshold_and_dedupes() -> None:
    df = stringdb.parse(FIX, min_score=700)
    assert list(df.columns) == ["protein1", "protein2", "combined_score"]
    pairs = {(r.protein1, r.protein2, r.combined_score) for r in df.itertuples()}
    assert len(df) == 3
    assert all(p1 < p2 for p1, p2, _ in pairs)
    assert all(not p.startswith("9606.") for p, _, _ in pairs)
    assert min(s for _, _, s in pairs) == 700


def test_parse_default_threshold_is_700() -> None:
    assert stringdb.MIN_SCORE == 700
    assert len(stringdb.parse(FIX)) == 3


def test_parse_info_maps_protein_to_symbol() -> None:
    df = stringdb.parse_info(FIX)
    assert list(df.columns) == ["protein", "symbol"]
    row = df[df.protein == "ENSP00000269305"].iloc[0]
    assert row.symbol == "TP53"


def test_parse_aliases_entrez_only() -> None:
    df = stringdb.parse_aliases(FIX)
    assert list(df.columns) == ["protein", "entrez"]
    assert len(df) == 3
    assert dict(zip(df.protein, df.entrez))["ENSP00000269305"] == "7157"
