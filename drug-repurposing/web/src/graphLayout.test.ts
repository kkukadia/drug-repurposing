import { describe, expect, it } from "vitest";
import { layoutGraph } from "./graphLayout";
import { graphView } from "./test/fixtures";

const W = 720;
const H = 560;

function dist(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

describe("layoutGraph", () => {
  const layout = layoutGraph(graphView.nodes, graphView.links, W, H);
  const pos = layout.positions;
  const center = { x: W / 2, y: H / 2 };

  it("places every node inside the canvas", () => {
    for (const n of graphView.nodes) {
      const p = pos[n.id];
      expect(p).toBeDefined();
      expect(Number.isFinite(p.x) && Number.isFinite(p.y)).toBe(true);
      expect(p.x).toBeGreaterThan(0);
      expect(p.x).toBeLessThan(W);
      expect(p.y).toBeGreaterThan(0);
      expect(p.y).toBeLessThan(H);
    }
  });

  it("centers the disease", () => {
    expect(pos["Disease:MONDO:1"]).toEqual(center);
  });

  it("puts drugs on one outer ring and genes inside it", () => {
    const drugR = graphView.nodes
      .filter((n) => n.kind === "Compound")
      .map((n) => dist(pos[n.id], center));
    const geneR = graphView.nodes
      .filter((n) => n.kind === "Gene")
      .map((n) => dist(pos[n.id], center));
    expect(Math.max(...drugR) - Math.min(...drugR)).toBeLessThan(0.001);
    expect(Math.max(...geneR)).toBeLessThan(Math.min(...drugR));
    expect(Math.min(...geneR)).toBeGreaterThan(0);
  });

  it("gives every node a distinct position", () => {
    const seen = new Set(graphView.nodes.map((n) => `${pos[n.id].x.toFixed(2)},${pos[n.id].y.toFixed(2)}`));
    expect(seen.size).toBe(graphView.nodes.length);
  });

  it("is deterministic", () => {
    expect(layoutGraph(graphView.nodes, graphView.links, W, H)).toEqual(layout);
  });

  it("keeps a gene angularly closer to its own drug than to the other drugs", () => {
    const angle = (p: { x: number; y: number }) => Math.atan2(p.y - center.y, p.x - center.x);
    const gap = (a: number, b: number) => {
      const d = Math.abs(a - b) % (2 * Math.PI);
      return Math.min(d, 2 * Math.PI - d);
    };
    const g1 = angle(pos["Gene:G1"]);
    expect(gap(g1, angle(pos["Compound:DB001"]))).toBeLessThan(
      gap(g1, angle(pos["Compound:DB003"])),
    );
    const g4 = angle(pos["Gene:G4"]);
    expect(gap(g4, angle(pos["Compound:DB003"]))).toBeLessThan(
      gap(g4, angle(pos["Compound:DB001"])),
    );
  });

  it("places genes reached only through other genes", () => {
    const nodes = [
      ...graphView.nodes,
      { id: "Gene:G9", kind: "Gene", name: "MTOR", role: "gene" as const },
    ];
    const links = [
      ...graphView.links,
      { source: "Gene:G1", target: "Gene:G9", kind: "evidence" as const, label: "Gene-interacts-Gene" },
    ];
    const l = layoutGraph(nodes, links, W, H);
    expect(Number.isFinite(l.positions["Gene:G9"].x)).toBe(true);
    expect(Object.keys(l.positions)).toHaveLength(nodes.length);
  });

  it("handles a disease with no candidates", () => {
    const l = layoutGraph([graphView.nodes[0]], [], W, H);
    expect(l.positions["Disease:MONDO:1"]).toEqual(center);
  });
});
