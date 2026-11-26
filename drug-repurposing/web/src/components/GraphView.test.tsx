import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { graphView } from "../test/fixtures";
import { GraphView } from "./GraphView";

describe("GraphView", () => {
  it("renders the disease, drugs and genes by name", () => {
    render(<GraphView view={graphView} />);
    const svg = screen.getByRole("group", { name: /relationship graph/i });
    for (const name of ["Type 2 diabetes", "Metformin", "Sildenafil", "Aspirin", "PRKAA1", "PTGS2"]) {
      expect(within(svg).getByText(name)).toBeInTheDocument();
    }
  });

  it("distinguishes predicted from known drugs", () => {
    render(<GraphView view={graphView} />);
    expect(screen.getByRole("button", { name: /Metformin.*known treatment/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sildenafil.*predicted.*0\.400/i })).toBeInTheDocument();
  });

  it("draws one line per link with its label", () => {
    const { container } = render(<GraphView view={graphView} />);
    expect(container.querySelectorAll("line.link")).toHaveLength(graphView.links.length);
    expect(container.querySelectorAll("line.link-predicted")).toHaveLength(3);
    expect(container.querySelectorAll("line.link-known")).toHaveLength(1);
    expect(container.querySelectorAll("line.link-evidence")).toHaveLength(4);
    expect(screen.getAllByText("Compound-binds-Gene").length).toBeGreaterThan(0);
  });

  it("scales predicted line width with score", () => {
    const { container } = render(<GraphView view={graphView} />);
    const widths = Array.from(container.querySelectorAll("line.link-predicted")).map((l) =>
      Number(l.getAttribute("stroke-width")),
    );
    expect(widths[0]).toBeGreaterThan(widths[1]);
    expect(widths[1]).toBeGreaterThan(widths[2]);
  });

  it("spreads line widths across tightly clustered scores", () => {
    const clustered = {
      ...graphView,
      links: graphView.links.map((l) =>
        l.kind === "predicted"
          ? { ...l, score: { "Compound:DB001": 0.99, "Compound:DB002": 0.97, "Compound:DB003": 0.95 }[l.source] }
          : l,
      ),
    };
    const { container } = render(<GraphView view={clustered} />);
    const widths = Array.from(container.querySelectorAll("line.link-predicted")).map((l) =>
      Number(l.getAttribute("stroke-width")),
    );
    expect(widths[0] - widths[2]).toBeGreaterThan(2);
    expect(widths[2]).toBeGreaterThan(0);
  });

  it("draws equal widths when all scores are equal", () => {
    const flat = {
      ...graphView,
      links: graphView.links.map((l) => (l.kind === "predicted" ? { ...l, score: 0.5 } : l)),
    };
    const { container } = render(<GraphView view={flat} />);
    const widths = new Set(
      Array.from(container.querySelectorAll("line.link-predicted")).map((l) =>
        l.getAttribute("stroke-width"),
      ),
    );
    expect(widths.size).toBe(1);
  });

  it("puts the disease label above its node so it does not cover the genes", () => {
    const { container } = render(<GraphView view={graphView} />);
    const text = container.querySelector("g.role-disease text");
    expect(Number(text?.getAttribute("y"))).toBeLessThan(0);
  });

  it("shows a legend", () => {
    render(<GraphView view={graphView} />);
    const legend = screen.getByRole("list", { name: /legend/i });
    expect(within(legend).getByText(/predicted drug/i)).toBeInTheDocument();
    expect(within(legend).getByText(/known treatment/i)).toBeInTheDocument();
    expect(within(legend).getByText(/gene/i)).toBeInTheDocument();
  });

  it("reports clicks on a drug", async () => {
    const onSelect = vi.fn();
    render(<GraphView view={graphView} onSelectDrug={onSelect} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /Sildenafil/ }));
    expect(onSelect).toHaveBeenCalledWith("DB002");
  });

  it("supports keyboard activation", async () => {
    const onSelect = vi.fn();
    render(<GraphView view={graphView} onSelectDrug={onSelect} />);
    const user = userEvent.setup();
    screen.getByRole("button", { name: /Aspirin/ }).focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("DB003");
  });

  it("shows details for the selected drug", async () => {
    render(<GraphView view={graphView} />);
    await userEvent.setup().click(screen.getByRole("button", { name: /Sildenafil/ }));
    expect(screen.getByTestId("graph-detail")).toHaveTextContent(/Sildenafil/);
    expect(screen.getByTestId("graph-detail")).toHaveTextContent(/0\.400/);
  });

  it("does not make genes or the disease clickable", () => {
    render(<GraphView view={graphView} />);
    expect(screen.queryByRole("button", { name: /PRKAA1/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Type 2 diabetes/ })).toBeNull();
  });

  it("shows an empty state when nothing was predicted", () => {
    render(
      <GraphView view={{ ...graphView, nodes: [graphView.nodes[0]], links: [] }} />,
    );
    expect(screen.getByText(/no predictions to draw/i)).toBeInTheDocument();
  });
});
