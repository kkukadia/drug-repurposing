import type { Candidate, CandidatesResponse } from "../types";

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
