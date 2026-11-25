# ADR 0003: Sources deliberately not downloaded

Status: accepted, 2026-11-24

The connector interface (`download(dest_dir) -> Path`, `parse(path) -> DataFrame`, one module per source in ingest/) stays the same for every source, so any of these can be added as a new module and a new edge layer in graph/build.py without changing the artifact contract.

| Source | Reason not downloaded now |
| --- | --- |
| ChEMBL | Full release is multi-GB (SQLite dump about 5 GB compressed) and mapping bioactivity thresholds to binding edges is its own project. CC BY-SA is compatible, but Hetionet already supplies Compound-binds-Gene (11,571 edges). Its first_approval field is also not used for years. |
| DrugBank | Licence: free for academic use only, redistribution of the data is restricted, and download needs a login. The graph uses DrugBank IDs as identifiers only, as Hetionet does, with no DrugBank content. |
| Open Targets | Platform releases are tens of GB of parquet with evidence-level scoring; target-disease edges are already covered by Hetionet Gene-associates-Disease for this first graph. Candidate for a later layer. |
| DisGeNET | Licence: academic use requires registration and the data is not freely redistributable (CC BY-NC-SA for the curated set). Hetionet already includes DisGeNET-derived associations through its own build. |
| FAERS | Optional per the outline. Quarterly raw reports need drug-name normalisation, deduplication and disproportionality statistics before they are usable, which is out of scope for the first graph. Hetionet already has Compound-causes-SideEffect (SIDER). |

Used instead: Hetionet v1.0 (CC0), STRING v12.0 (CC BY 4.0), DrugCentral 2023-11-01 approvals (CC BY-SA 4.0), ClinicalTrials.gov and PubMed (public, queried on demand with disk caches).
