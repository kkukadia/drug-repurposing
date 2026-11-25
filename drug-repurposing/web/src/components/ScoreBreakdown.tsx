export function ScoreBreakdown({ scores }: { scores: Record<string, number> }) {
  const entries = Object.entries(scores);
  if (entries.length === 0) return <span className="muted">no method scores</span>;
  return (
    <ul className="breakdown" aria-label="Method scores">
      {entries.map(([name, value]) => (
        <li key={name}>
          <span className="method">{name}</span>
          <span className="bar" aria-hidden="true">
            <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
          </span>
          <span className="value">{value.toFixed(3)}</span>
        </li>
      ))}
    </ul>
  );
}
