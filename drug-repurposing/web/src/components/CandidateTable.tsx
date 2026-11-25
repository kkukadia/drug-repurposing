import { useState } from "react";
import type { Candidate } from "../types";
import { EvidenceLinks } from "./EvidenceLinks";
import { PathView } from "./PathView";
import { ScoreBreakdown } from "./ScoreBreakdown";

export function CandidateTable({ candidates }: { candidates: Candidate[] }) {
  const [open, setOpen] = useState<string | null>(null);

  if (candidates.length === 0) {
    return <p className="status">No candidate drugs were ranked for this disease.</p>;
  }

  return (
    <table className="candidates">
      <thead>
        <tr>
          <th>#</th>
          <th>Drug</th>
          <th>Score</th>
          <th>Methods</th>
          <th>Evidence</th>
        </tr>
      </thead>
      <tbody>
        {candidates.map((c, i) => {
          const expanded = open === c.drug_id;
          return (
            <FragmentRow
              key={c.drug_id}
              rank={i + 1}
              candidate={c}
              expanded={expanded}
              onToggle={() => setOpen(expanded ? null : c.drug_id)}
            />
          );
        })}
      </tbody>
    </table>
  );
}

interface RowProps {
  rank: number;
  candidate: Candidate;
  expanded: boolean;
  onToggle: () => void;
}

function FragmentRow({ rank, candidate: c, expanded, onToggle }: RowProps) {
  return (
    <>
      <tr>
        <td>{rank}</td>
        <td>
          {c.drug_name} <span className="muted">{c.drug_id}</span>
        </td>
        <td>{c.score.toFixed(3)}</td>
        <td>
          <ScoreBreakdown scores={c.method_scores} />
        </td>
        <td>
          <button type="button" aria-expanded={expanded} onClick={onToggle}>
            {expanded ? "Hide" : "Show"} paths ({c.paths.length}), trials ({c.trials.length}),
            papers ({c.papers.length})
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="detail">
          <td colSpan={5}>
            <h4>Why: graph paths</h4>
            <PathView paths={c.paths} />
            <EvidenceLinks candidate={c} />
          </td>
        </tr>
      )}
    </>
  );
}
