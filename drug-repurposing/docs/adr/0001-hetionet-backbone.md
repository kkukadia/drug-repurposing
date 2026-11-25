# ADR 0001: Hetionet v1.0 as the primary open graph backbone

Status: accepted, 2026-11-24

## Context

The outline lists ChEMBL, DrugBank, Open Targets, DisGeNET and STRING as sources. A first graph must rebuild in minutes, redistribute cleanly and already carry the edge types the scorers need: Compound-binds-Gene, Compound-treats/palliates-Disease, LINCS-derived Compound up/downregulates Gene, Disease up/downregulates Gene, Gene-interacts-Gene.

## Decision

Use Hetionet v1.0 (CC0, 47,031 nodes, 2,250,197 edges, 24 edge types) as the backbone and add STRING v12.0 (CC BY 4.0, combined_score >= 700) as an extra Gene-interacts-Gene layer. Hetionet Compound-treats-Disease edges (755) become the ground-truth indications. Compound-palliates-Disease stays as an ordinary edge.

## Consequences

- Compounds are DrugBank IDs, diseases are Disease Ontology IDs, genes are Entrez IDs; no cross-vocabulary disease mapping is needed.
- Hetionet is a 2017 snapshot, so recent drugs and indications are absent. Time-split results are limited by this; see docs/adr/0002-approval-year-source.md.
- Hetionet Gene-associates-Disease edges (from GWAS Catalog, DISEASES, DisGeNET-derived curation inside Hetionet) cover the disease-gene role without a separate DisGeNET download.
- STRING proteins map to Hetionet genes through STRING aliases (UniProt_DR_GeneID, an Entrez ID) first and preferred symbol second. Unmapped proteins are listed in data/graph/unmapped/ and counted in manifest.json.
- Hetionet Gene-associates-Disease is stored with the gene as src to match the contract edge name; the source file lists the disease first.
- STRING and Hetionet may both state the same gene pair. Both rows are kept, distinguished by source; STRING rows carry weight = combined_score / 1000.
- The Hetionet download redirects to Git LFS media storage; the pinned URL is the raw path from the contract.
