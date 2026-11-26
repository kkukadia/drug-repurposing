import type { Candidate, CandidatesResponse, GraphViewResponse } from "../types";

export const candidate: Candidate = {
  drug_id: "DB001",
  drug_name: "Metformin",
  score: 0.9,
  method_scores: { proximity: 0.8, gnn: 0.7 },
  paths: [
    {
      nodes: [
        { kind: "Compound", name: "Metformin" },
        { kind: "Gene", name: "PRKAA1" },
        { kind: "Disease", name: "Type 2 diabetes" },
      ],
      edges: ["Compound-binds-Gene", "Gene-associates-Disease"],
    },
  ],
  trials: [
    { nct_id: "NCT0001", title: "A trial", status: "RECRUITING", url: "https://ct.example/NCT0001" },
  ],
  papers: [{ pmid: "111", title: "A paper", url: "https://pm.example/111" }],
  trials_search_url: "https://ct.example/search",
  papers_search_url: "https://pm.example/search",
};

export const response: CandidatesResponse = {
  disease: { disease_id: "MONDO:1", name: "Type 2 diabetes" },
  disclaimer: "API disclaimer text.",
  evidence_live: true,
  candidates: [candidate, { ...candidate, drug_id: "DB002", drug_name: "Sildenafil", score: 0.4 }],
};

export const graphView: GraphViewResponse = {
  disease: { disease_id: "MONDO:1", name: "Type 2 diabetes" },
  disclaimer: "API disclaimer text.",
  nodes: [
    { id: "Disease:MONDO:1", kind: "Disease", name: "Type 2 diabetes", role: "disease" },
    { id: "Compound:DB001", kind: "Compound", name: "Metformin", role: "known" },
    { id: "Compound:DB002", kind: "Compound", name: "Sildenafil", role: "predicted" },
    { id: "Compound:DB003", kind: "Compound", name: "Aspirin", role: "predicted" },
    { id: "Gene:G1", kind: "Gene", name: "PRKAA1", role: "gene" },
    { id: "Gene:G4", kind: "Gene", name: "PTGS2", role: "gene" },
  ],
  links: [
    { source: "Compound:DB001", target: "Disease:MONDO:1", kind: "predicted", label: "predicted", score: 0.9 },
    { source: "Compound:DB001", target: "Disease:MONDO:1", kind: "known", label: "treats" },
    { source: "Compound:DB002", target: "Disease:MONDO:1", kind: "predicted", label: "predicted", score: 0.4 },
    { source: "Compound:DB003", target: "Disease:MONDO:1", kind: "predicted", label: "predicted", score: 0.2 },
    { source: "Compound:DB001", target: "Gene:G1", kind: "evidence", label: "Compound-binds-Gene" },
    { source: "Gene:G1", target: "Disease:MONDO:1", kind: "evidence", label: "Gene-associates-Disease" },
    { source: "Compound:DB003", target: "Gene:G4", kind: "evidence", label: "Compound-binds-Gene" },
    { source: "Gene:G4", target: "Disease:MONDO:1", kind: "evidence", label: "Gene-associates-Disease" },
  ],
};
