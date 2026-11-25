import type { Candidate } from "../types";

export function EvidenceLinks({ candidate }: { candidate: Candidate }) {
  const { trials, papers } = candidate;
  return (
    <div className="evidence">
      <h4>Clinical trials</h4>
      {trials.length === 0 ? (
        <p className="muted">
          No trials retrieved.{" "}
          <a href={candidate.trials_search_url} target="_blank" rel="noreferrer">
            Search ClinicalTrials.gov
          </a>
        </p>
      ) : (
        <ul>
          {trials.map((t) => (
            <li key={t.nct_id}>
              <a href={t.url} target="_blank" rel="noreferrer">
                {t.nct_id}
              </a>{" "}
              {t.title} <span className="muted">({t.status})</span>
            </li>
          ))}
        </ul>
      )}
      <h4>Papers</h4>
      {papers.length === 0 ? (
        <p className="muted">
          No papers retrieved.{" "}
          <a href={candidate.papers_search_url} target="_blank" rel="noreferrer">
            Search PubMed
          </a>
        </p>
      ) : (
        <ul>
          {papers.map((p) => (
            <li key={p.pmid}>
              <a href={p.url} target="_blank" rel="noreferrer">
                PMID {p.pmid}
              </a>{" "}
              {p.title}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
