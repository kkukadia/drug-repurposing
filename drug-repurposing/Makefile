
.PHONY: serve test lint graph ingest

serve:
	.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000

test:
	.venv/bin/pytest -q
	cd web && npm test

lint:
	.venv/bin/black --check api tests/api ingest graph tests/ingest tests/graph
	.venv/bin/ruff check api tests/api ingest graph tests/ingest tests/graph
	.venv/bin/mypy api tests/api ingest graph tests/ingest tests/graph
	cd web && npm run lint

ingest:
	../tools/timed.sh ingest .venv/bin/python -m ingest.run --raw data/raw

graph: ingest
	../tools/timed.sh graph-build .venv/bin/python -m graph.build --raw data/raw --out data/graph

.PHONY: train benchmark prospective lint-ml

benchmark:
	../tools/timed.sh benchmark .venv/bin/python -m eval.run_benchmark --graph data/graph --out data/results --report docs/benchmark-report.md --kge-epochs 20

prospective:
	../tools/timed.sh prospective .venv/bin/python -m eval.prospective --graph data/graph

train:
	../tools/timed.sh train .venv/bin/python -m models.export_candidates --graph data/graph --benchmark data/results/benchmark.json --out data/results/candidates.parquet

lint-ml:
	.venv/bin/black --check eval models tests/workstream_b
	.venv/bin/ruff check eval models tests/workstream_b
	.venv/bin/mypy eval models tests/workstream_b
