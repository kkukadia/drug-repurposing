# Data dictionary

Produced by `make graph` (ingest, then `python -m graph.build`). Files live in `data/graph/`. Raw downloads live in `data/raw/<source>/`, each with a `<file>.meta.json` sidecar (url, sha256, bytes, download time). Counts below are from the build recorded in `data/graph/manifest.json`.

## nodes.parquet (47,031 rows)

| Column | Type | Meaning |
| --- | --- | --- |
| node_id | int64 | Dense id 0..N-1, follows Hetionet file order |
| kind | string | Anatomy, BiologicalProcess, CellularComponent, Compound, Disease, Gene, MolecularFunction, Pathway, PharmacologicClass, SideEffect, Symptom |
| ext_id | string | Source id without the kind prefix: DrugBank ID (Compound, e.g. DB00945), Disease Ontology ID (Disease, e.g. DOID:1612), Entrez Gene ID (Gene), UBERON, GO, UMLS CUI, Reactome/WikiPathways ids for the rest |
| name | string | Display name from Hetionet |
| source | string | Always `Hetionet` |
| source_version | string | `v1.0` |

Compound order for scorers is the order of Compound rows in this table.

## edges.parquet (2,476,659 rows)

| Column | Type | Meaning |
| --- | --- | --- |
| src, dst | int64 | node_id of the endpoints; direction follows the etype name (source kind first) |
| etype | string | Edge type, see below |
| source | string | `Hetionet` (2,250,197) or `STRING` (226,462) |
| source_version | string | `v1.0` or `v12.0` |
| weight | float64, nullable | STRING combined_score / 1000 (0.7 to 1.0); null for Hetionet edges |

Edge types and counts (Hetionet edge abbreviation in brackets):

- Compound-binds-Gene [CbG] 11,571
- Compound-treats-Disease [CtD] 755 (also the label set)
- Compound-palliates-Disease [CpD] 390
- Compound-upregulates-Gene [CuG] 18,756 and Compound-downregulates-Gene [CdG] 21,102 (LINCS L1000)
- Compound-resembles-Compound [CrC] 6,486
- Compound-causes-SideEffect [CcSE] 138,944
- Disease-upregulates-Gene [DuG] 7,731 and Disease-downregulates-Gene [DdG] 7,623
- Gene-associates-Disease [DaG] 12,623; stored with gene as src, reversed from Hetionet
- Disease-localizes-Anatomy [DlA] 3,602, Disease-presents-Symptom [DpS] 3,357, Disease-resembles-Disease [DrD] 543
- Gene-interacts-Gene [GiG] 373,626 total: Hetionet 147,164 and STRING 226,462 (a pair present in both sources appears twice, once per source)
- Gene-covaries-Gene [GcG] 61,690, Gene-regulates-Gene [Gr>G] 265,672
- Gene-participates-BiologicalProcess [GpBP] 559,504, -CellularComponent [GpCC] 73,566, -MolecularFunction [GpMF] 97,222, -Pathway [GpPW] 84,372
- Anatomy-expresses-Gene [AeG] 526,407, Anatomy-upregulates-Gene [AuG] 97,848, Anatomy-downregulates-Gene [AdG] 102,240
- PharmacologicClass-includes-Compound [PCiC] 1,029

STRING rows: human (taxon 9606) links with combined_score >= 700, one row per unordered gene pair (src < dst), after mapping proteins to Hetionet genes.

Hetionet undirected types (GiG, GcG, CrC, DrD) are stored once, not in both directions. Compound-treats-Disease edges are present in the graph; the eval split code removes them for held-out pairs.

## indications.parquet (755 rows)

| Column | Type | Meaning |
| --- | --- | --- |
| drug_node | int64 | node_id of a Compound |
| disease_node | int64 | node_id of a Disease |
| year | Int64, nullable | Proxy approval year: the drug's first approval, not the indication's (see ADR 0002). 754 of 755 non-null; range 1869 to 2024; 18 rows are 2010 or later |
| label_source | string | `hetionet_treats|year=<origin>` where origin is `drugcentral_first_fda_approval` (744), `drugcentral_first_year_introduced_approval` (4), `clinicaltrials_first_start` (6) or `missing` (1) |

Labels are Hetionet Compound-treats-Disease edges (387 distinct drugs, 77 distinct diseases).

## manifest.json

- `build_timestamp`: UTC build time.
- `sources.<name>`: `name`, `version`, `license`, `files` (per file: url, sha256, bytes, downloaded_utc) and `rows` (parsed and used row counts). Sources: hetionet, stringdb, drugcentral.
- `counts`: nodes, edges, nodes_by_kind, edges_by_type, edges_by_source, indications, indications_with_year, year_coverage, indication_year_sources.
- `id_mapping.<name>`: total_unique, mapped_unique, unmapped_unique, coverage, unmapped_file (one id per line under `data/graph/unmapped/`).

| Mapping | Coverage | Note |
| --- | --- | --- |
| hetionet_edge_endpoints | 1.0000 | every edge endpoint exists in the node table |
| string_protein_to_gene | 0.9814 (15,900 of 16,201) | Entrez via STRING aliases, then symbol; unmapped proteins have no Entrez or symbol match among Hetionet's 20,945 genes (list in unmapped file) |
| drugbank_to_compound | 0.4745 (1,376 of 2,900) | DrugCentral approved drugs not in Hetionet's 1,552 compounds are ignored; only Hetionet compounds matter |

## Evidence connectors (not part of the artifact)

- `ingest/clinicaltrials.py`: `ClinicalTrialsClient(cache_dir).search(drug, condition)`, `.earliest_start_year(drug)`; `parse(json_path)` returns nct_id, title, status, start_year, url. Responses cached on disk under `data/raw/clinicaltrials/cache` for the build and any directory you pass; 0.4 s between live calls.
- `ingest/pubmed.py`: `PubMedClient(cache_dir).comention_count(drug, disease)`, `.search_ids(...)`, `.fetch_abstracts(pmids)` returns pmid, title, abstract, year, url. No API key, 0.35 s between live calls, disk cached.
