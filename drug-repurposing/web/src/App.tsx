import { useEffect, useState } from "react";
import { fetchCandidates, fetchGraph } from "./api";
import { CandidateTable } from "./components/CandidateTable";
import { DisclaimerBanner } from "./components/DisclaimerBanner";
import { DiseaseSearch } from "./components/DiseaseSearch";
import { GraphView } from "./components/GraphView";
import type { CandidatesResponse, Disease, GraphViewResponse } from "./types";

interface Outcome<T> {
  id: string;
  data: T | null;
  error: string | null;
}

function useForDisease<T>(
  selected: Disease | null,
  load: (id: string, signal: AbortSignal) => Promise<T>,
) {
  const [outcome, setOutcome] = useState<Outcome<T> | null>(null);

  useEffect(() => {
    if (!selected) return;
    const id = selected.disease_id;
    const ctrl = new AbortController();
    load(id, ctrl.signal)
      .then((d) => setOutcome({ id, data: d, error: null }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setOutcome({ id, data: null, error: e instanceof Error ? e.message : "Request failed" });
      });
    return () => ctrl.abort();
  }, [selected, load]);

  const current = selected && outcome?.id === selected.disease_id ? outcome : null;
  return {
    loading: selected !== null && current === null,
    error: current?.error ?? null,
    data: current?.data ?? null,
  };
}

const loadCandidates = (id: string, signal: AbortSignal) => fetchCandidates(id, 20, signal);
const loadGraph = (id: string, signal: AbortSignal) => fetchGraph(id, 8, signal);

export default function App() {
  const [selected, setSelected] = useState<Disease | null>(null);
  const candidates = useForDisease<CandidatesResponse>(selected, loadCandidates);
  const graph = useForDisease<GraphViewResponse>(selected, loadGraph);
  const data = candidates.data;

  return (
    <>
      <DisclaimerBanner text={data?.disclaimer ?? graph.data?.disclaimer} />
      <main>
        <h1>Drug Repurposing Explorer</h1>
        <DiseaseSearch onSelect={setSelected} />
        {selected && <h2>Relationships for {selected.name}</h2>}
        {graph.loading && <p className="status">Loading relationship graph...</p>}
        {graph.error && (
          <p className="status error" role="alert">
            Could not load graph: {graph.error}
          </p>
        )}
        {graph.data && <GraphView view={graph.data} />}
        {selected && <h2>Candidates for {selected.name}</h2>}
        {candidates.loading && <p className="status">Loading candidates and evidence...</p>}
        {candidates.error && (
          <p className="status error" role="alert">
            Could not load candidates: {candidates.error}
          </p>
        )}
        {data && <CandidateTable candidates={data.candidates} />}
        {data && !data.evidence_live && (
          <p className="muted">Live trial and paper lookups unavailable or served from cache.</p>
        )}
      </main>
    </>
  );
}
