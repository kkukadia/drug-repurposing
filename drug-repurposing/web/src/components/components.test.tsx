import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { candidate } from "../test/fixtures";
import { CandidateTable } from "./CandidateTable";
import { DisclaimerBanner } from "./DisclaimerBanner";
import { EvidenceLinks } from "./EvidenceLinks";
import { PathView } from "./PathView";
import { ScoreBreakdown } from "./ScoreBreakdown";

describe("DisclaimerBanner", () => {
  it("always shows not-medical-advice", () => {
    render(<DisclaimerBanner />);
    expect(screen.getByRole("alert")).toHaveTextContent(/not medical advice/i);
  });
});

describe("ScoreBreakdown", () => {
  it("lists each method score", () => {
    render(<ScoreBreakdown scores={{ proximity: 0.8, gnn: 0.7 }} />);
    expect(screen.getByText("proximity")).toBeInTheDocument();
    expect(screen.getByText("0.800")).toBeInTheDocument();
  });
  it("handles empty", () => {
    render(<ScoreBreakdown scores={{}} />);
    expect(screen.getByText(/no method scores/i)).toBeInTheDocument();
  });
});

describe("PathView", () => {
  it("renders nodes and edge types", () => {
    render(<PathView paths={candidate.paths} />);
    expect(screen.getByText("PRKAA1")).toBeInTheDocument();
    expect(screen.getByText(/Compound-binds-Gene/)).toBeInTheDocument();
  });
  it("shows empty state", () => {
    render(<PathView paths={[]} />);
    expect(screen.getByText(/no graph path/i)).toBeInTheDocument();
  });
});

describe("EvidenceLinks", () => {
  it("links trials and papers", () => {
    render(<EvidenceLinks candidate={candidate} />);
    expect(screen.getByRole("link", { name: "NCT0001" })).toHaveAttribute(
      "href",
      "https://ct.example/NCT0001",
    );
    expect(screen.getByRole("link", { name: /PMID 111/ })).toBeInTheDocument();
  });
  it("falls back to search links when empty", () => {
    render(<EvidenceLinks candidate={{ ...candidate, trials: [], papers: [] }} />);
    expect(screen.getByRole("link", { name: /Search ClinicalTrials/ })).toHaveAttribute(
      "href",
      "https://ct.example/search",
    );
    expect(screen.getByRole("link", { name: /Search PubMed/ })).toBeInTheDocument();
  });
});

describe("CandidateTable", () => {
  it("renders ranked rows and expands detail", async () => {
    render(<CandidateTable candidates={[candidate, { ...candidate, drug_id: "X", drug_name: "Other" }]} />);
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(screen.queryByText("PRKAA1")).not.toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button")[0]);
    expect(screen.getByText("PRKAA1")).toBeInTheDocument();
  });
  it("shows empty state", () => {
    render(<CandidateTable candidates={[]} />);
    expect(screen.getByText(/no candidate drugs/i)).toBeInTheDocument();
  });
});
