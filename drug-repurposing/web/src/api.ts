import type { CandidatesResponse, Disease, GraphViewResponse } from "./types";

const BASE: string = import.meta.env.VITE_API_URL ?? "/api";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { signal });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      detail = res.statusText;
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export function searchDiseases(q: string, signal?: AbortSignal): Promise<Disease[]> {
  return getJson<Disease[]>(`/diseases?q=${encodeURIComponent(q)}`, signal);
}

export function fetchCandidates(
  diseaseId: string,
  k = 20,
  signal?: AbortSignal,
): Promise<CandidatesResponse> {
  return getJson<CandidatesResponse>(
    `/diseases/${encodeURIComponent(diseaseId)}/candidates?k=${k}`,
    signal,
  );
}

export function fetchGraph(
  diseaseId: string,
  k = 8,
  signal?: AbortSignal,
): Promise<GraphViewResponse> {
  return getJson<GraphViewResponse>(
    `/diseases/${encodeURIComponent(diseaseId)}/graph?k=${k}`,
    signal,
  );
}
