import argparse
import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from graph import schema
from ingest import approvals, clinicaltrials, common, hetionet, idmap, stringdb

log = logging.getLogger("graph.build")

YearFallback = Callable[[str], int | None]


def build_nodes(raw: pd.DataFrame) -> pd.DataFrame:
    kinds = raw.kind.map(schema.KIND_NAMES)
    if kinds.isna().any():
        raise ValueError(f"unknown node kinds: {sorted(raw.kind[kinds.isna()].unique())}")
    return pd.DataFrame(
        {
            "node_id": np.arange(len(raw), dtype="int64"),
            "kind": kinds.to_numpy(),
            "ext_id": raw.id.str.split("::", n=1).str[1].to_numpy(),
            "name": raw.name.to_numpy(),
            "source": hetionet.NAME,
            "source_version": hetionet.VERSION,
        }
    )


def build_hetionet_edges(
    raw_edges: pd.DataFrame, key_to_id: dict[str, int]
) -> tuple[pd.DataFrame, idmap.MappingReport]:
    unknown = set(raw_edges.metaedge) - set(schema.METAEDGE_NAMES)
    if unknown:
        raise ValueError(f"unknown metaedges: {sorted(unknown)}")
    endpoints = pd.concat([raw_edges.source, raw_edges.target], ignore_index=True)
    _, report = idmap.map_values("hetionet_edge_endpoints", endpoints, key_to_id)
    src = raw_edges.source.map(key_to_id).astype("Int64")
    dst = raw_edges.target.map(key_to_id).astype("Int64")
    keep = src.notna() & dst.notna()
    frame = pd.DataFrame(
        {"src": src[keep], "dst": dst[keep], "metaedge": raw_edges.metaedge[keep]}
    ).reset_index(drop=True)
    flip = frame.metaedge.isin(schema.FLIPPED_METAEDGES)
    s = frame.src.where(~flip, frame.dst)
    d = frame.dst.where(~flip, frame.src)
    out = pd.DataFrame(
        {
            "src": s.astype("int64"),
            "dst": d.astype("int64"),
            "etype": frame.metaedge.map(schema.METAEDGE_NAMES),
            "source": hetionet.NAME,
            "source_version": hetionet.VERSION,
            "weight": np.nan,
        }
    )
    return out, report


def map_proteins(
    proteins: pd.Series,
    info: pd.DataFrame,
    aliases: pd.DataFrame,
    gene_by_entrez: dict[str, int],
    gene_by_symbol: dict[str, int],
) -> tuple[dict[str, int], idmap.MappingReport]:
    by_alias = aliases.assign(node=aliases.entrez.map(gene_by_entrez)).dropna(subset=["node"])
    by_alias = by_alias.drop_duplicates("protein")
    protein_node = dict(zip(by_alias.protein, by_alias.node.astype("int64")))
    symbol_node = info.assign(node=info.symbol.map(gene_by_symbol)).dropna(subset=["node"])
    for protein, node in zip(symbol_node.protein, symbol_node.node.astype("int64")):
        protein_node.setdefault(protein, node)
    _, report = idmap.map_values("string_protein_to_gene", proteins, protein_node)
    return protein_node, report


def build_string_edges(links: pd.DataFrame, protein_node: dict[str, int]) -> pd.DataFrame:
    a = links.protein1.map(protein_node)
    b = links.protein2.map(protein_node)
    keep = a.notna() & b.notna() & (a != b)
    lo = np.minimum(a[keep].astype("int64"), b[keep].astype("int64"))
    hi = np.maximum(a[keep].astype("int64"), b[keep].astype("int64"))
    frame = pd.DataFrame({"src": lo, "dst": hi, "weight": links.combined_score[keep] / 1000.0})
    frame = (
        frame.sort_values(["src", "dst", "weight"], ascending=[True, True, False])
        .drop_duplicates(["src", "dst"])
        .reset_index(drop=True)
    )
    out = pd.DataFrame(
        {
            "src": frame.src.astype("int64"),
            "dst": frame.dst.astype("int64"),
            "etype": schema.STRING_ETYPE,
            "source": stringdb.NAME,
            "source_version": stringdb.VERSION,
            "weight": frame.weight.astype("float64"),
        }
    )
    return out


def build_indications(
    edges: pd.DataFrame,
    nodes: pd.DataFrame,
    years: pd.DataFrame,
    year_fallback: YearFallback | None,
) -> pd.DataFrame:
    treats = edges[edges.etype == schema.TREATS_ETYPE][["src", "dst"]].drop_duplicates()
    treats = treats.sort_values(["src", "dst"]).reset_index(drop=True)
    ext = nodes.set_index("node_id").ext_id
    names = nodes.set_index("node_id").name
    drug_ext = treats.src.map(ext)
    year_map = dict(zip(years.drugbank_id, years.year))
    agency_map = dict(zip(years.drugbank_id, years.agency))
    year = drug_ext.map(year_map).astype("Int64")
    label = pd.Series("hetionet_treats|year=missing", index=treats.index)
    has = year.notna()
    label[has] = (
        "hetionet_treats|year=drugcentral_first_"
        + drug_ext[has].map(agency_map).astype(str).str.lower().str.replace(" ", "_")
        + "_approval"
    )
    if year_fallback is not None:
        cache: dict[int, int | None] = {}
        for idx in treats.index[~has]:
            drug = int(treats.src[idx])
            if drug not in cache:
                cache[drug] = year_fallback(str(names[drug]))
            value = cache[drug]
            if value is not None:
                year[idx] = value
                label[idx] = "hetionet_treats|year=clinicaltrials_first_start"
    return pd.DataFrame(
        {
            "drug_node": treats.src.astype("int64"),
            "disease_node": treats.dst.astype("int64"),
            "year": year.astype("Int64"),
            "label_source": label,
        }
    )


def source_entry(
    directory: Path, name: str, version: str, license_: str, **rows: int
) -> dict[str, Any]:
    return {
        "name": name,
        "version": version,
        "license": license_,
        "files": common.read_meta(directory),
        "rows": rows,
    }


def build_graph(
    raw_dir: Path,
    out_dir: Path,
    string_min_score: int = stringdb.MIN_SCORE,
    year_fallback: YearFallback | None = None,
) -> dict[str, Any]:
    het_dir = raw_dir / "hetionet"
    string_dir = raw_dir / "stringdb"
    dc_dir = raw_dir / "drugcentral"
    out_dir.mkdir(parents=True, exist_ok=True)
    unmapped_dir = out_dir / "unmapped"

    raw_nodes = hetionet.parse_nodes(het_dir)
    raw_edges = hetionet.parse(het_dir)
    nodes = build_nodes(raw_nodes)
    key_to_id = dict(zip(raw_nodes.id, nodes.node_id))

    het_edges, het_report = build_hetionet_edges(raw_edges, key_to_id)

    genes = nodes[nodes.kind == "Gene"]
    gene_by_symbol = dict(zip(genes.name[::-1], genes.node_id[::-1]))
    gene_by_entrez = dict(zip(genes.ext_id, genes.node_id))
    links = stringdb.parse(string_dir, stringdb.MIN_SCORE)
    links = links[links.combined_score >= string_min_score]
    info = stringdb.parse_info(string_dir)
    aliases = stringdb.parse_aliases(string_dir)
    proteins = pd.concat([links.protein1, links.protein2], ignore_index=True)
    protein_node, str_report = map_proteins(proteins, info, aliases, gene_by_entrez, gene_by_symbol)
    str_edges = build_string_edges(links, protein_node)

    edges = pd.concat([het_edges, str_edges], ignore_index=True)

    approval_rows = approvals.parse(dc_dir / approvals.APPROVALS_FILE)
    years = approvals.first_approval_year(approval_rows)
    compounds = nodes[nodes.kind == "Compound"]
    compound_ids = dict(zip(compounds.ext_id, compounds.node_id))
    _, drug_report = idmap.map_values(
        "drugbank_to_compound", pd.Series(approval_rows.drugbank_id.unique()), compound_ids
    )
    years = years[years.drugbank_id.isin(compound_ids)]
    indications = build_indications(edges, nodes, years, year_fallback)

    reports = {
        "hetionet_edge_endpoints": het_report,
        "string_protein_to_gene": str_report,
        "drugbank_to_compound": drug_report,
    }
    id_mapping = {
        name: report.as_dict(report.write_unmapped(unmapped_dir))
        for name, report in reports.items()
    }

    nodes.to_parquet(out_dir / "nodes.parquet", index=False)
    edges.to_parquet(out_dir / "edges.parquet", index=False)
    indications.to_parquet(out_dir / "indications.parquet", index=False)

    with_year = int(indications.year.notna().sum())
    manifest: dict[str, Any] = {
        "build_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {
            "hetionet": source_entry(
                het_dir,
                hetionet.NAME,
                hetionet.VERSION,
                hetionet.LICENSE,
                nodes_parsed=len(raw_nodes),
                edges_parsed=len(raw_edges),
                edges_used=len(het_edges),
            ),
            "stringdb": source_entry(
                string_dir,
                stringdb.NAME,
                stringdb.VERSION,
                stringdb.LICENSE,
                links_at_threshold=len(links),
                edges_used=len(str_edges),
                min_combined_score=string_min_score,
            ),
            "drugcentral": source_entry(
                dc_dir,
                approvals.NAME,
                approvals.VERSION,
                approvals.LICENSE,
                approval_rows=len(approval_rows),
                drugs_with_year=len(years),
            ),
        },
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "nodes_by_kind": {k: int(v) for k, v in nodes.kind.value_counts().sort_index().items()},
            "edges_by_type": {
                k: int(v) for k, v in edges.etype.value_counts().sort_index().items()
            },
            "edges_by_source": {k: int(v) for k, v in edges.source.value_counts().items()},
            "indications": len(indications),
            "indications_with_year": with_year,
            "year_coverage": round(with_year / len(indications), 6) if len(indications) else 1.0,
            "indication_year_sources": {
                k: int(v) for k, v in indications.label_source.value_counts().sort_index().items()
            },
        },
        "id_mapping": id_mapping,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/graph"))
    parser.add_argument("--min-string-score", type=int, default=stringdb.MIN_SCORE)
    parser.add_argument("--no-trial-year-fallback", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    fallback: YearFallback | None = None
    if not args.no_trial_year_fallback:
        client = clinicaltrials.ClinicalTrialsClient(args.raw / "clinicaltrials" / "cache")
        fallback = client.earliest_start_year
    manifest = build_graph(args.raw, args.out, args.min_string_score, fallback)
    print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
