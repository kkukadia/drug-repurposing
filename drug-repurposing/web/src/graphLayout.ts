import type { GraphLink, GraphNode } from "./types";

export interface Point {
  x: number;
  y: number;
}

export interface Layout {
  width: number;
  height: number;
  positions: Record<string, Point>;
}

const MARGIN = 90;
const START = -Math.PI / 2;
const TAU = 2 * Math.PI;
const MIN_GAP = 0.32;
const GENE_RADII = [0.46, 0.7];

function circularMean(angles: number[]): number {
  const s = angles.reduce((a, t) => a + Math.sin(t), 0);
  const c = angles.reduce((a, t) => a + Math.cos(t), 0);
  if (Math.abs(s) < 1e-9 && Math.abs(c) < 1e-9) return angles[0];
  return Math.atan2(s, c);
}

function normalize(angle: number): number {
  const a = (angle - START) % TAU;
  return (a < 0 ? a + TAU : a) + START;
}

export function layoutGraph(
  nodes: GraphNode[],
  links: GraphLink[],
  width = 720,
  height = 560,
): Layout {
  const cx = width / 2;
  const cy = height / 2;
  const outer = Math.min(width, height) / 2 - MARGIN;
  const positions: Record<string, Point> = {};
  const at = (angle: number, radius: number): Point => ({
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  });

  for (const n of nodes) {
    if (n.role === "disease") positions[n.id] = { x: cx, y: cy };
  }

  const drugs = nodes.filter((n) => n.kind === "Compound");
  const angles = new Map<string, number>();
  drugs.forEach((d, i) => {
    const angle = START + (TAU * i) / drugs.length;
    angles.set(d.id, angle);
    positions[d.id] = at(angle, outer);
  });

  const genes = nodes.filter((n) => n.kind === "Gene");
  const geneIds = new Set(genes.map((g) => g.id));
  const adjacency = new Map<string, Set<string>>();
  for (const l of links) {
    if (l.kind !== "evidence") continue;
    for (const [a, b] of [
      [l.source, l.target],
      [l.target, l.source],
    ]) {
      if (!adjacency.has(a)) adjacency.set(a, new Set());
      adjacency.get(a)!.add(b);
    }
  }

  const geneAngle = new Map<string, number>();
  let pending = genes.map((g) => g.id);
  while (pending.length > 0) {
    const resolved: [string, number][] = [];
    for (const id of pending) {
      const known: number[] = [];
      for (const nb of adjacency.get(id) ?? []) {
        const a = angles.get(nb) ?? (geneIds.has(nb) ? geneAngle.get(nb) : undefined);
        if (a !== undefined) known.push(a);
      }
      if (known.length > 0) resolved.push([id, circularMean(known)]);
    }
    if (resolved.length === 0) break;
    for (const [id, a] of resolved) geneAngle.set(id, a);
    const done = new Set(resolved.map(([id]) => id));
    pending = pending.filter((id) => !done.has(id));
  }
  for (const id of pending) geneAngle.set(id, START);

  const ordered = genes
    .map((g) => ({ id: g.id, angle: normalize(geneAngle.get(g.id) ?? START) }))
    .sort((a, b) => a.angle - b.angle || a.id.localeCompare(b.id));
  const gap = Math.min(MIN_GAP, TAU / Math.max(ordered.length, 1));
  ordered.forEach((g, i) => {
    if (i > 0 && g.angle - ordered[i - 1].angle < gap) g.angle = ordered[i - 1].angle + gap;
  });
  ordered.forEach((g, i) => {
    positions[g.id] = at(g.angle, outer * GENE_RADII[i % GENE_RADII.length]);
  });

  return { width, height, positions };
}
