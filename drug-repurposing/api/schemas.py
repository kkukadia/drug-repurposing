from pydantic import BaseModel, Field

DISCLAIMER = (
    "Predictions are computational hypotheses for researchers, not medical advice or "
    "treatment recommendations. Do not use them to make decisions about patient care."
)


class DiseaseOut(BaseModel):
    disease_id: str
    name: str


class PathNode(BaseModel):
    kind: str
    name: str


class PathOut(BaseModel):
    nodes: list[PathNode]
    edges: list[str]


class TrialOut(BaseModel):
    nct_id: str
    title: str
    status: str
    url: str


class PaperOut(BaseModel):
    pmid: str
    title: str
    url: str


class CandidateOut(BaseModel):
    drug_id: str
    drug_name: str
    score: float
    method_scores: dict[str, float] = Field(default_factory=dict)
    paths: list[PathOut] = Field(default_factory=list)
    trials: list[TrialOut] = Field(default_factory=list)
    papers: list[PaperOut] = Field(default_factory=list)
    trials_search_url: str
    papers_search_url: str


class CandidatesResponse(BaseModel):
    disease: DiseaseOut
    disclaimer: str = DISCLAIMER
    evidence_live: bool = False
    candidates: list[CandidateOut]


class HealthOut(BaseModel):
    status: str
    graph_loaded: bool
    candidates_loaded: bool
    n_diseases: int
    disclaimer: str = DISCLAIMER
