import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j import GraphDatabase

from api.backend import CandidateRow, GraphBackend, MemoryBackend, Neo4jBackend
from api.config import Settings
from api.evidence import EvidenceClient, papers_search_url, trials_search_url
from api.graphview import build_graph_view
from api.schemas import (
    DISCLAIMER,
    CandidateOut,
    CandidatesResponse,
    DiseaseOut,
    GraphViewOut,
    HealthOut,
)
from api.store import Store

log = logging.getLogger(__name__)


def make_backend(cfg: Settings) -> GraphBackend:
    if cfg.neo4j_uri:
        auth = (cfg.neo4j_user, cfg.neo4j_password) if cfg.neo4j_password else None
        return Neo4jBackend(GraphDatabase.driver(cfg.neo4j_uri, auth=auth))
    return MemoryBackend(Store.load(cfg), cfg)


def require_ready(backend: GraphBackend) -> None:
    if not backend.ready():
        raise HTTPException(status_code=503, detail="graph or candidates not loaded")


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = cfg
        app.state.backend = make_backend(cfg)
        app.state.evidence = EvidenceClient(cfg.cache_dir, cfg.offline, cfg.http_timeout)
        try:
            yield
        finally:
            app.state.backend.close()

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
        backend: GraphBackend = request.app.state.backend
        ok = backend.ready()
        return HealthOut(
            status="ok" if ok else "degraded",
            graph_loaded=ok,
            candidates_loaded=ok,
            n_diseases=backend.disease_count() if ok else 0,
            backend=backend.name,
        )

    @app.get("/diseases", response_model=list[DiseaseOut])
    def diseases(
        request: Request, q: str = "", limit: int = Query(50, ge=1, le=500)
    ) -> list[DiseaseOut]:
        backend: GraphBackend = request.app.state.backend
        if not backend.ready():
            return []
        return backend.search_diseases(q, limit)

    @app.get("/diseases/{disease_id}/candidates", response_model=CandidatesResponse)
    def candidates(
        request: Request, disease_id: str, k: int = Query(20, ge=1, le=100)
    ) -> CandidatesResponse:
        backend: GraphBackend = request.app.state.backend
        evidence: EvidenceClient = request.app.state.evidence
        cfg_: Settings = request.app.state.settings
        require_ready(backend)
        disease = backend.get_disease(disease_id)
        if disease is None:
            raise HTTPException(status_code=404, detail=f"unknown disease {disease_id}")
        rows = backend.candidates(disease_id, k)

        def build(row: CandidateRow) -> CandidateOut:
            return CandidateOut(
                drug_id=row.drug_id,
                drug_name=row.drug_name,
                score=row.score,
                method_scores=row.method_scores,
                paths=backend.paths(row.drug_id, disease_id, cfg_.max_paths),
                trials=evidence.trials(row.drug_name, disease.name),
                papers=evidence.papers(row.drug_name, disease.name),
                trials_search_url=trials_search_url(row.drug_name, disease.name),
                papers_search_url=papers_search_url(row.drug_name, disease.name),
            )

        before = evidence.live_hits
        with ThreadPoolExecutor(max_workers=4) as pool:
            out = list(pool.map(build, rows))
        return CandidatesResponse(
            disease=disease, evidence_live=evidence.live_hits > before, candidates=out
        )

    @app.get("/diseases/{disease_id}/graph", response_model=GraphViewOut)
    def graph(request: Request, disease_id: str, k: int = Query(8, ge=1, le=25)) -> GraphViewOut:
        backend: GraphBackend = request.app.state.backend
        cfg_: Settings = request.app.state.settings
        require_ready(backend)
        view = build_graph_view(backend, disease_id, k, cfg_.max_paths)
        if view is None:
            raise HTTPException(status_code=404, detail=f"unknown disease {disease_id}")
        return view

    return app


app = create_app()
