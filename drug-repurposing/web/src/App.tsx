import { useEffect, useState } from "react";
import { fetchCandidates } from "./api";
import { CandidateTable } from "./components/CandidateTable";
import { DisclaimerBanner } from "./components/DisclaimerBanner";
import { DiseaseSearch } from "./components/DiseaseSearch";
import type { CandidatesResponse, Disease } from "./types";

export default function App() {
  const [selected, setSelected] = useState<Disease | null>(null);
  const [outcome, setOutcome] = useState<{
    id: string;
    data: CandidatesResponse | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    if (!selected) return;
    const id = selected.disease_id;
    const ctrl = new AbortController();
    fetchCandidates(id, 20, ctrl.signal)
      .then((d) => setOutcome({ id, data: d, error: null }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setOutcome({ id, data: null, error: e instanceof Error ? e.message : "Request failed" });
      });
    return () => ctrl.abort();
  }, [selected]);

  const current = selected && outcome?.id === selected.disease_id ? outcome : null;
  const loading = selected !== null && current === null;
  const error = current?.error ?? null;
  const data = current?.data ?? null;


  return (
    <>
      <DisclaimerBanner text={data?.disclaimer} />
      <main>
        <h1>Drug Repurposing Explorer</h1>
        <DiseaseSearch onSelect={setSelected} />
        {selected && <h2>Candidates for {selected.name}</h2>}
        {loading && <p className="status">Loading candidates and evidence...</p>}
        {error && (
          <p className="status error" role="alert">
            Could not load candidates: {error}
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
