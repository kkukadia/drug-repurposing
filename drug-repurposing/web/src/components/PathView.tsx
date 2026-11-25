import type { GraphPath } from "../types";

export function PathView({ paths }: { paths: GraphPath[] }) {
  if (paths.length === 0) {
    return <p className="muted">No graph path found between this drug and disease.</p>;
  }
  return (
    <ol className="paths" aria-label="Graph paths">
      {paths.map((p, i) => (
        <li key={i} className="path">
          {p.nodes.map((n, j) => (
            <span key={j}>
              <span className={`node kind-${n.kind.toLowerCase()}`} title={n.kind}>
                {n.name}
              </span>
              {j < p.edges.length && (
                <span className="edge" aria-label="edge">
                  {" "}
                  &mdash;{p.edges[j]}&rarr;{" "}
                </span>
              )}
            </span>
          ))}
        </li>
      ))}
    </ol>
  );
}
