# ADR 0002: Proxy approval year for indications

Status: accepted, 2026-11-24

## Context

The time split needs a year per (drug, disease) label. Hetionet has none. The outline asks for DrugCentral's open approvals file, with fallbacks of earliest ClinicalTrials.gov start year or ChEMBL first_approval.

## Findings

- https://unmtid-dbs.net/download/DrugCentral/static/FDA_Approved.csv lists only structure id and name, no dates.
- The dated approvals live in the `approval` table of the PostgreSQL dump https://unmtid-dbs.net/download/DrugCentral/2023-11-01/drugcentral.dump.11012023.sql.gz (1.4 GB, CC BY-SA 4.0). The `identifier` table maps structures to DrugBank IDs, which are Hetionet's compound IDs.
- psql is not required: ingest/approvals.py streams the gzip, keeps only the `approval` and `identifier` COPY blocks and writes a 90 KB approvals.tsv.

## Decision

1. Year = earliest FDA approval date of the drug in DrugCentral (agency FDA preferred; if a drug has no FDA row, the earliest date of another agency row, recorded in label_source).
2. If DrugCentral has no dated row, fall back to the earliest ClinicalTrials.gov start year for the drug name (v2 API, `query.intr`, sorted by StartDate ascending, disk-cached). Recorded in label_source as clinicaltrials_first_start.
3. If both are missing the year stays null.
4. ChEMBL first_approval is not used (see ADR 0003).

Result on the built graph: 744 indications from FDA, 4 from another agency row, 6 from trials, 1 null (of 755).

## Consequences

- The year is the drug's first approval, not the year of the specific indication. A drug approved in 1950 for one disease and repurposed in 2010 is labelled 1950 for both. Time splits therefore measure drug age, not indication age, and understate repurposing recency. The model card must say so.
- Only 18 of 755 labelled pairs have year >= 2010 (Hetionet predates most recent approvals). A recent-cutoff time split will have a small test set; choose cutoffs accordingly.
- Some DrugCentral dates are historical introduction years (minimum 1869), not regulatory approvals.
- The DrugCentral dump is 1.4 GB and is kept under data/raw/drugcentral/ so rebuilds skip the download; delete it to reclaim space, approvals.tsv is enough to build.
