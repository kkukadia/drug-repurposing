import { useEffect, useState } from "react";
import { searchDiseases } from "../api";
import type { Disease } from "../types";
import { useDebounced } from "../useDebounced";

interface Props {
  onSelect: (disease: Disease) => void;
  delayMs?: number;
}

export function DiseaseSearch({ onSelect, delayMs = 300 }: Props) {
  const [query, setQuery] = useState("");
  const debounced = useDebounced(query, delayMs);
  const term = debounced.trim();
  const [outcome, setOutcome] = useState<{
    term: string;
    results: Disease[];
    error: string | null;
  } | null>(null);

  useEffect(() => {
    if (term === "") return;
    const ctrl = new AbortController();
    searchDiseases(term, ctrl.signal)
      .then((d) => setOutcome({ term, results: d, error: null }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setOutcome({
          term,
          results: [],
          error: e instanceof Error ? e.message : "Search failed",
        });
      });
    return () => ctrl.abort();
  }, [term]);

  const current = term !== "" && outcome?.term === term ? outcome : null;
  const loading = term !== "" && current === null;
  const error = current?.error ?? null;
  const results = current?.results ?? [];
  const settled = current !== null && debounced === query;


  return (
    <section className="search">
      <label htmlFor="disease-q">Search for a disease</label>
      <input
        id="disease-q"
        type="search"
        value={query}
        placeholder="e.g. diabetes"
        onChange={(e) => setQuery(e.target.value)}
        autoComplete="off"
      />
      {loading && <p className="status">Searching...</p>}
      {error && (
        <p className="status error" role="alert">
          Search failed: {error}
        </p>
      )}
      {!loading && !error && settled && results.length === 0 && (
        <p className="status">No diseases match "{debounced.trim()}".</p>
      )}
      {results.length > 0 && (
        <ul className="results" aria-label="Disease results">
          {results.map((d) => (
            <li key={d.disease_id}>
              <button type="button" onClick={() => onSelect(d)}>
                {d.name} <span className="muted">{d.disease_id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
