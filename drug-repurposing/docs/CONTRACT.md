# Interface contract (shared by all workstreams)

Project root: `/Users/kk/Downloads/000-dev/0-drug-repurposing/drug-repurposing`. Python venv: `.venv` (3.11, torch, pykeen, fastapi, sklearn installed; PyG may need install). Run long commands via `../tools/timed.sh <label> <cmd...>` so build time is logged to `../BUILD_TIME.csv`.

Rules: no code comments or docstrings in code; tests first (pytest); black line-length 100, ruff, mypy clean; never commit or push; no secrets in code.

## Graph artifact (produced by `graph/`, consumed by everything else)

Directory `data/graph/` containing:

- `nodes.parquet`: columns `node_id` (int, dense 0..N-1), `kind` (Compound|Gene|Disease|Anatomy|SideEffect|...), `ext_id` (string, source id), `name`, `source`, `source_version`
- `edges.parquet`: columns `src` (int), `dst` (int), `etype` (string e.g. `Compound-binds-Gene`, `Gene-interacts-Gene`, `Compound-treats-Disease`, `Gene-associates-Disease`, `Compound-upregulates-Gene`, `Compound-downregulates-Gene`, `Disease-upregulates-Gene`, `Disease-downregulates-Gene`), `source`, `source_version`, `weight` (float, nullable)
- `manifest.json`: source name, url, version/date, sha256, row counts, build timestamp, unmapped-ID counts and coverage
- Ground truth labels: `data/graph/indications.parquet` with `drug_node`, `disease_node`, `year` (nullable int, proxy approval year), `label_source`

Graph build is one command: `make graph` (runs ingest then build). Source modules in `ingest/`, one per source, each exposing `download(dest_dir) -> Path` and `parse(path) -> DataFrame`. Every source has a small checked-in fixture under `tests/fixtures/` for unit tests.

## Splits and scorers (produced by `eval/` and `models/`)

- `eval/splits.py`: `make_split(indications, kind, seed)` for kind in `random`, `time`, `cold_disease`; returns train/val/test frames of (drug_node, disease_node) and removes leaking edges (treats edges for test pairs, plus indirect ones) from the training graph.
- Every scorer implements `fit(graph, train_pairs, seed)` and `score(disease_node) -> np.ndarray` of length n_compounds (higher = better), compounds indexed by compound order in nodes table.
- Scorers in `models/`: `proximity.py` (network proximity), `kge.py` (TransE, ComplEx via PyKEEN), `gnn.py` (PyG heterogeneous link predictor), `signature.py` (signature reversal), `ensemble.py` (per-disease normalized weighted average, weights fit on val only).
- Metrics in `eval/metrics.py`: AUROC, AUPRC, Hits@k, MRR, recall@k, bootstrap/seed CIs.
- Benchmark runner `eval/run_benchmark.py` writes `data/results/benchmark.json` and `docs/benchmark-report.md`, 5 seeds, stages 1 to 4 from the outline; stage 5 in `eval/prospective.py`.

## API (`api/`, FastAPI)

- `GET /health`
- `GET /diseases?q=` returns `[{disease_id, name}]`
- `GET /diseases/{disease_id}/candidates?k=20` returns `{disease, disclaimer, candidates:[{drug_id, drug_name, score, method_scores:{...}, paths:[{nodes:[{kind,name}], edges:[etype]}], trials:[{nct_id,title,status,url}], papers:[{pmid,title,url}]}]}`
- Every candidate has at least one path and one trial or paper link where evidence exists; `disclaimer` is always present.
- Reads precomputed `data/results/candidates.parquet` (and graph) at startup; live trial/paper lookups cached on disk and degrade gracefully offline.

## Web (`web/`, React + Vite + TypeScript)

Disease search, ranked table, path view, persistent not-medical-advice banner. Talks to API at `VITE_API_URL`.

## Infra

`infra/docker-compose.yml` (api, web), `infra/terraform/` (EC2 skeleton, validated with `terraform validate` only if terraform is installed), Makefile targets: `setup`, `graph`, `train`, `benchmark`, `serve`, `test`, `lint`.
