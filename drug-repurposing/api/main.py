import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncIterator

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import Settings
from api.evidence import EvidenceClient, papers_search_url, trials_search_url
from api.paths import extract_paths
from api.schemas import (
    DISCLAIMER,
    CandidateOut,
    CandidatesResponse,
    DiseaseOut,
    HealthOut,
)
from api.store import Store

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = cfg
        app.state.store = Store.load(cfg)
        app.state.evidence = EvidenceClient(cfg.cache_dir, cfg.offline, cfg.http_timeout)
        yield

    app = FastAPI(title="Drug repurposing API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "disclaimer": DISCLAIMER},
        )

    @app.get("/health", response_model=HealthOut)
    def health(request: Request) -> HealthOut:
        store: Store = request.app.state.store
        return HealthOut(
            status="ok" if store.index is not None and not store.candidates.empty else "degraded",
            graph_loaded=store.index is not None,
            candidates_loaded=not store.candidates.empty,
            n_diseases=len(store.diseases),
        )

    @app.get("/diseases", response_model=list[DiseaseOut])
    def diseases(
        request: Request, q: str = "", limit: int = Query(50, ge=1, le=500)
    ) -> list[DiseaseOut]:
        store: Store = request.app.state.store
        needle = q.strip().lower()
        hits = [
            DiseaseOut(disease_id=ext, name=name)
            for ext, name, _ in store.diseases
            if not needle or needle in name.lower() or needle in ext.lower()
        ]
        hits.sort(key=lambda d: (not d.name.lower().startswith(needle), d.name.lower()))
        return hits[:limit]

    @app.get("/diseases/{disease_id}/candidates", response_model=CandidatesResponse)
    def candidates(
        request: Request, disease_id: str, k: int = Query(20, ge=1, le=100)
    ) -> CandidatesResponse:
        store: Store = request.app.state.store
        evidence: EvidenceClient = request.app.state.evidence
        cfg_: Settings = request.app.state.settings
        if store.index is None or store.candidates.empty:
            raise HTTPException(status_code=503, detail="graph or candidates not loaded")
        node = store.disease_by_ext.get(disease_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"unknown disease {disease_id}")
        index = store.index
        rows = store.candidates[store.candidates["disease_node"] == node]
        rows = rows.sort_values("score", ascending=False).head(k)
        disease = DiseaseOut(disease_id=disease_id, name=index.names[node])

        def build(row: pd.Series) -> CandidateOut:
            drug = int(row["drug_node"])
            name = index.names.get(drug, str(drug))
            methods = {c: float(row[c]) for c in store.method_columns if pd.notna(row[c])}
            return CandidateOut(
                drug_id=index.ext_ids.get(drug, str(drug)),
                drug_name=name,
                score=float(row["score"]),
                method_scores=methods,
                paths=extract_paths(index, drug, node, cfg_.max_paths, cfg_.max_path_search_nodes),
                trials=evidence.trials(name, disease.name),
                papers=evidence.papers(name, disease.name),
                trials_search_url=trials_search_url(name, disease.name),
                papers_search_url=papers_search_url(name, disease.name),
            )

        before = evidence.live_hits
        records = [r for _, r in rows.iterrows()]
        with ThreadPoolExecutor(max_workers=4) as pool:
            out = list(pool.map(build, records))
        return CandidatesResponse(
            disease=disease, evidence_live=evidence.live_hits > before, candidates=out
        )

    return app


app = create_app()
