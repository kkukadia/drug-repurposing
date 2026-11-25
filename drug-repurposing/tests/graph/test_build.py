import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from graph import build


def run(
    raw: Path, tmp_path: Path, year_fallback: Callable[[str], int | None] | None = None
) -> tuple[Path, dict]:
    out = tmp_path / "graph"
    manifest = build.build_graph(raw, out, year_fallback=year_fallback)
    return out, manifest


def test_artifact_files_and_columns(raw_dir: Path, tmp_path: Path) -> None:
    out, _ = run(raw_dir, tmp_path)
    for name in ("nodes.parquet", "edges.parquet", "indications.parquet", "manifest.json"):
        assert (out / name).exists()
    nodes = pd.read_parquet(out / "nodes.parquet")
    edges = pd.read_parquet(out / "edges.parquet")
    inds = pd.read_parquet(out / "indications.parquet")
    assert list(nodes.columns) == [
        "node_id",
        "kind",
        "ext_id",
        "name",
        "source",
        "source_version",
    ]
    assert list(edges.columns) == ["src", "dst", "etype", "source", "source_version", "weight"]
    assert list(inds.columns) == ["drug_node", "disease_node", "year", "label_source"]


def test_nodes_dense_ids_and_kinds(raw_dir: Path, tmp_path: Path) -> None:
    out, _ = run(raw_dir, tmp_path)
    nodes = pd.read_parquet(out / "nodes.parquet")
    assert nodes.node_id.tolist() == list(range(13))
    assert set(nodes.kind) == {
        "Compound",
        "Disease",
        "Gene",
        "Anatomy",
        "SideEffect",
        "PharmacologicClass",
    }
    gene = nodes[(nodes.kind == "Gene") & (nodes.name == "TP53")].iloc[0]
    assert gene.ext_id == "7157"
    comp = nodes[nodes.name == "Aspirin"].iloc[0]
    assert comp.ext_id == "DB00945"


def test_every_node_and_edge_has_source_and_version(raw_dir: Path, tmp_path: Path) -> None:
    out, _ = run(raw_dir, tmp_path)
    nodes = pd.read_parquet(out / "nodes.parquet")
    edges = pd.read_parquet(out / "edges.parquet")
    for df in (nodes, edges):
        assert df.source.notna().all() and (df.source != "").all()
        assert df.source_version.notna().all() and (df.source_version != "").all()
    assert set(edges.source) == {"Hetionet", "STRING"}
    assert set(edges[edges.source == "STRING"].source_version) == {"v12.0"}


def test_edges_types_and_unmapped_dropped(raw_dir: Path, tmp_path: Path) -> None:
    out, _ = run(raw_dir, tmp_path)
    nodes = pd.read_parquet(out / "nodes.parquet")
    edges = pd.read_parquet(out / "edges.parquet")
    assert len(edges) == 18
    assert edges.src.between(0, 12).all() and edges.dst.between(0, 12).all()
    assert {
        "Compound-binds-Gene",
        "Compound-treats-Disease",
        "Compound-palliates-Disease",
        "Compound-upregulates-Gene",
        "Compound-downregulates-Gene",
        "Disease-upregulates-Gene",
        "Gene-associates-Disease",
        "Gene-interacts-Gene",
        "Compound-causes-SideEffect",
        "Anatomy-expresses-Gene",
        "PharmacologicClass-includes-Compound",
    } <= set(edges.etype)
    kinds = dict(zip(nodes.node_id, nodes.kind))
    assoc = edges[edges.etype == "Gene-associates-Disease"].iloc[0]
    assert kinds[assoc.src] == "Gene" and kinds[assoc.dst] == "Disease"


def test_string_edges_weighted_and_hetionet_unweighted(raw_dir: Path, tmp_path: Path) -> None:
    out, _ = run(raw_dir, tmp_path)
    edges = pd.read_parquet(out / "edges.parquet")
    s = edges[edges.source == "STRING"]
    assert len(s) == 2
    assert sorted(s.weight.round(3).tolist()) == [0.7, 0.9]
    assert (s.etype == "Gene-interacts-Gene").all()
    assert edges[edges.source == "Hetionet"].weight.isna().all()


def test_indications_from_treats_with_year(raw_dir: Path, tmp_path: Path) -> None:
    out, _ = run(raw_dir, tmp_path)
    nodes = pd.read_parquet(out / "nodes.parquet").set_index("node_id")
    inds = pd.read_parquet(out / "indications.parquet")
    assert len(inds) == 4
    assert str(inds.year.dtype) == "Int64"
    inds = inds.assign(
        drug=inds.drug_node.map(nodes.ext_id), disease=inds.disease_node.map(nodes.ext_id)
    ).set_index(["drug", "disease"])
    assert inds.loc[("DB00945", "DOID:1612"), "year"] == 1950
    assert inds.loc[("DB00316", "DOID:9351"), "year"] == 1998
    assert inds.loc[("DB01050", "DOID:1612"), "year"] == 1999
    assert pd.isna(inds.loc[("DB09999", "DOID:9351"), "year"])
    assert inds.label_source.notna().all()
    assert (nodes.loc[inds.drug_node, "kind"] == "Compound").all()
    assert (nodes.loc[inds.disease_node, "kind"] == "Disease").all()


def test_year_fallback_fills_missing(raw_dir: Path, tmp_path: Path) -> None:
    out, manifest = run(raw_dir, tmp_path, year_fallback=lambda name: 2000)
    inds = pd.read_parquet(out / "indications.parquet")
    assert inds.year.notna().all()
    assert (inds.year == 2000).sum() == 1
    assert inds.label_source.nunique() == 3
    assert manifest["counts"]["indications_with_year"] == 4


def test_manifest_contents(raw_dir: Path, tmp_path: Path) -> None:
    out, manifest = run(raw_dir, tmp_path)
    assert json.loads((out / "manifest.json").read_text()) == manifest
    assert "build_timestamp" in manifest
    assert set(manifest["sources"]) == {"hetionet", "stringdb", "drugcentral"}
    for src in manifest["sources"].values():
        assert src["version"] and src["files"]
        for f in src["files"].values():
            assert len(f["sha256"]) == 64 and f["url"].startswith("https://")
    counts = manifest["counts"]
    assert counts["nodes"] == 13 and counts["edges"] == 18 and counts["indications"] == 4
    assert counts["indications_with_year"] == 3
    assert counts["year_coverage"] == 0.75
    assert counts["edges_by_type"]["Gene-interacts-Gene"] == 3
    assert counts["nodes_by_kind"]["Compound"] == 4
    mapping = manifest["id_mapping"]
    assert mapping["string_protein_to_gene"]["unmapped_unique"] == 1
    assert mapping["string_protein_to_gene"]["total_unique"] == 4
    assert mapping["drugbank_to_compound"]["unmapped_unique"] == 1
    assert mapping["hetionet_edge_endpoints"]["unmapped_unique"] == 1
    for entry in mapping.values():
        assert 0 <= entry["coverage"] <= 1
        assert (Path(entry["unmapped_file"])).exists()


def test_build_is_deterministic(raw_dir: Path, tmp_path: Path) -> None:
    a, _ = run(raw_dir, tmp_path / "a")
    b, _ = run(raw_dir, tmp_path / "b")
    for name in ("nodes.parquet", "edges.parquet", "indications.parquet"):
        pd.testing.assert_frame_equal(pd.read_parquet(a / name), pd.read_parquet(b / name))
