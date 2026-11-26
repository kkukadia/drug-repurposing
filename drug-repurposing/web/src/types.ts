export interface Disease {
  disease_id: string;
  name: string;
}

export interface PathNode {
  kind: string;
  name: string;
  id?: string | null;
}

export interface GraphPath {
  nodes: PathNode[];
  edges: string[];
}

export interface Trial {
  nct_id: string;
  title: string;
  status: string;
  url: string;
}

export interface Paper {
  pmid: string;
  title: string;
  url: string;
}

export interface Candidate {
  drug_id: string;
  drug_name: string;
  score: number;
  method_scores: Record<string, number>;
  paths: GraphPath[];
  trials: Trial[];
  papers: Paper[];
  trials_search_url: string;
  papers_search_url: string;
}

export interface CandidatesResponse {
  disease: Disease;
  disclaimer: string;
  evidence_live: boolean;
  candidates: Candidate[];
}

export type NodeRole = "disease" | "predicted" | "known" | "gene";

export interface GraphNode {
  id: string;
  kind: string;
  name: string;
  role: NodeRole;
}

export interface GraphLink {
  source: string;
  target: string;
  kind: "predicted" | "known" | "evidence";
  label: string;
  score?: number | null;
}

export interface GraphViewResponse {
  disease: Disease;
  disclaimer: string;
  nodes: GraphNode[];
  links: GraphLink[];
}
