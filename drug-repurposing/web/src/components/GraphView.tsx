import { useMemo, useState } from "react";
import { layoutGraph } from "../graphLayout";
import type { GraphLink, GraphNode, GraphViewResponse } from "../types";

const WIDTH = 720;
const HEIGHT = 560;
const RADIUS: Record<string, number> = { disease: 28, predicted: 15, known: 15, gene: 9 };

interface Props {
  view: GraphViewResponse;
  onSelectDrug?: (drugId: string) => void;
}

function rawId(node: GraphNode): string {
  return node.id.slice(node.kind.length + 1);
}

function describe(node: GraphNode, score: number | null): string {
  if (node.role === "known") {
    return score === null
      ? `${node.name}, known treatment`
      : `${node.name}, known treatment, predicted score ${score.toFixed(3)}`;
  }
  return `${node.name}, predicted drug, score ${(score ?? 0).toFixed(3)}`;
}

function strokeWidth(link: GraphLink, lo: number, hi: number): number {
  if (link.kind === "predicted") {
    const t = hi > lo ? ((link.score ?? lo) - lo) / (hi - lo) : 0.5;
    return 1.5 + t * 4.5;
  }
  return link.kind === "known" ? 2.5 : 1.2;
}

export function GraphView({ view, onSelectDrug }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const layout = useMemo(
    () => layoutGraph(view.nodes, view.links, WIDTH, HEIGHT),
    [view.nodes, view.links],
  );
  const scores = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of view.links) {
      if (l.kind === "predicted" && l.score != null) m.set(l.source, l.score);
    }
    return m;
  }, [view.links]);

  const range = useMemo(() => {
    const values = Array.from(scores.values());
    return values.length > 0
      ? { lo: Math.min(...values), hi: Math.max(...values) }
      : { lo: 0, hi: 0 };
  }, [scores]);

  const drugs = view.nodes.filter((n) => n.kind === "Compound");
  if (drugs.length === 0) {
    return <p className="muted">No predictions to draw for this disease.</p>;
  }

  const byId = new Map(view.nodes.map((n) => [n.id, n]));
  const chosen = selected ? byId.get(selected) : undefined;
  const cx = WIDTH / 2;

  const choose = (node: GraphNode) => {
    setSelected(node.id);
    onSelectDrug?.(rawId(node));
  };

  return (
    <figure className="graph-view">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="group"
        aria-label="Disease and drug relationship graph"
      >
        {view.links.map((l, i) => {
          const a = layout.positions[l.source];
          const b = layout.positions[l.target];
          if (!a || !b) return null;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const len = Math.hypot(dx, dy) || 1;
          const off = l.kind === "known" ? 5 : 0;
          const ox = (-dy / len) * off;
          const oy = (dx / len) * off;
          return (
            <line
              key={i}
              className={`link link-${l.kind}`}
              x1={a.x + ox}
              y1={a.y + oy}
              x2={b.x + ox}
              y2={b.y + oy}
              strokeWidth={strokeWidth(l, range.lo, range.hi)}
              strokeDasharray={l.kind === "predicted" ? "6 4" : undefined}
            >
              <title>{l.label}</title>
            </line>
          );
        })}
        {view.nodes.map((n) => {
          const p = layout.positions[n.id];
          if (!p) return null;
          const isDrug = n.kind === "Compound";
          const score = scores.get(n.id) ?? null;
          const anchor = p.x > cx + 12 ? "start" : p.x < cx - 12 ? "end" : "middle";
          const r = RADIUS[n.role] ?? 10;
          const lx = anchor === "start" ? r + 5 : anchor === "end" ? -r - 5 : 0;
          const ly = n.role === "disease" ? -r - 8 : anchor === "middle" ? r + 14 : 4;
          const interactive = isDrug
            ? {
                role: "button",
                tabIndex: 0,
                "aria-label": describe(n, score),
                onClick: () => choose(n),
                onKeyDown: (e: React.KeyboardEvent) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    choose(n);
                  }
                },
              }
            : {};
          return (
            <g
              key={n.id}
              transform={`translate(${p.x} ${p.y})`}
              className={`gnode role-${n.role}${selected === n.id ? " selected" : ""}`}
              {...interactive}
            >
              <circle r={r} />
              <text x={lx} y={ly} textAnchor={anchor}>
                {n.name}
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="legend" aria-label="Legend">
        <li className="legend-predicted">Predicted drug (thicker line = higher score)</li>
        <li className="legend-known">Known treatment</li>
        <li className="legend-gene">Gene</li>
        <li className="legend-disease">Disease</li>
      </ul>
      <figcaption className="muted" data-testid="graph-detail">
        {chosen
          ? `${describe(chosen, scores.get(chosen.id) ?? null)} for ${view.disease.name}.`
          : "Select a drug to see its score."}
      </figcaption>
    </figure>
  );
}
