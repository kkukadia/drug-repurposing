# Drug repurposing

Ranks approved drugs as candidates for new diseases. It builds a knowledge graph from Hetionet, STRING and DrugCentral, scores drug-disease pairs with five methods plus an ensemble, and serves the ranked list through a FastAPI backend and a React web app. Each candidate comes with the graph paths behind it and links to related trials and papers.

Predictions are computational hypotheses for researchers, not medical advice.

## Run it

With Neo4j and the web app, in Docker:

```
cd drug-repurposing/infra
cp .env.example .env
```

Set `NEO4J_PASSWORD` in `.env`, then:

```
docker compose up -d --build
docker compose --profile load run --rm loader
```

The loader writes the graph (47,031 nodes, 2,476,659 edges) and the 6,850 predictions into Neo4j in about 40 seconds. Open http://127.0.0.1:8080, search a disease, and you get a graph of the disease, its top predicted drugs, known treatments, and the genes that connect them. Click a drug for its score.

Neo4j Browser is at http://127.0.0.1:7474. Predictions are `PREDICTED_TREATS` relationships:

```
MATCH (c:Compound)-[r:PREDICTED_TREATS]->(d:Disease {name: "type 2 diabetes mellitus"})
RETURN c, r, d ORDER BY r.score DESC LIMIT 10
```

Without Neo4j, the API falls back to loading the parquet files in memory:

```
cd drug-repurposing
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
make serve
```

To point the API at a Neo4j you run yourself, set `DR_NEO4J_URI`, `DR_NEO4J_USER` and `DR_NEO4J_PASSWORD`, run `make neo4j-load`, then `make serve`.

```
curl "http://127.0.0.1:8000/diseases?q=diabetes"
curl "http://127.0.0.1:8000/diseases/DOID:9352/candidates?k=5"
curl "http://127.0.0.1:8000/diseases/DOID:9352/graph?k=8"
```

`DR_OFFLINE=1` skips the live trial and paper lookups. For the web dev server, run `npm ci && npm run dev` in `web/`.

To rebuild from raw data (about 1.4 GB of downloads): `make graph`, `make benchmark`, `make train`, then reload Neo4j. Tests: `make test` (the Neo4j tests start a throwaway container and skip if Docker isn't running), `make lint`, `make lint-ml`.

## Layout

All under `drug-repurposing/`:

- `ingest/`, `graph/`: download sources and build the graph (47,031 nodes, 2,476,659 edges, 755 labelled indications)
- `models/`, `eval/`: proximity, signature reversal, TransE, ComplEx, GNN, ensemble, and the benchmark
- `graph/neo4j_load.py`: loads the graph and predictions into Neo4j
- `api/`, `web/`: backend (Neo4j or in-memory) and frontend
- `infra/`: Dockerfiles, Compose, Terraform
- `docs/`: data dictionary, ADRs, full benchmark report

## Results

On the random hold-out split, the GNN reaches AUPRC 0.421 [0.228, 0.614] against 0.166 for the best baseline (TransE). On the cold-start and known-repurposings splits the intervals overlap. With only 755 labelled indications, test sets are small. Runs used 3 to 4 seeds, not 5. The time split measures drug age, not indication age. Details are in `drug-repurposing/docs/benchmark-report.md`.

## Data and licences

| Source | Licence |
| --- | --- |
| Hetionet v1.0 | CC0 1.0 |
| STRING v12.0 | CC BY 4.0 |
| DrugCentral 2023-11-01 | CC BY-SA 4.0 |
| ClinicalTrials.gov, PubMed | Public, queried on demand |

DrugCentral is share-alike, so the derived files in `data/graph/` and `data/results/` are also CC BY-SA 4.0. DrugBank is used for IDs only.
