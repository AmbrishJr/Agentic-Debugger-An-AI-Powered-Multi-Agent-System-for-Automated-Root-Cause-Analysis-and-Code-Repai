import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ErrorBox, IncidentTable, ValidationPanel } from "./common";

describe("investigation output", () => {
  it("renders an actionable empty state instead of invented records", () => {
    render(<IncidentTable incidents={[]} />);
    expect(screen.getByText("No incidents yet")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/investigations/new",
    );
  });
  it("distinguishes skipped checks from passed validation", () => {
    render(
      <ValidationPanel
        validation={{
          status: "partial",
          checks: [
            {
              name: "Repository tests",
              status: "skipped",
              detail: "No isolated runner is configured.",
            },
          ],
          limitations: "Syntax checks do not prove correctness.",
        }}
      />,
    );
    expect(screen.getByText("Skipped")).toBeInTheDocument();
    expect(screen.getByText("Partial")).toBeInTheDocument();
    expect(screen.queryByText("Passed")).not.toBeInTheDocument();
  });
  it("announces API errors accessibly", () => {
    render(<ErrorBox error={new Error("Backend unavailable")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Backend unavailable");
  });
  it("labels demo incidents and links to their persisted report", () => {
    render(
      <IncidentTable
        incidents={[
          {
            id: "abc123",
            title: "Checkout failed",
            error_log: "ZeroDivisionError",
            severity: "high",
            status: "approved",
            mode: "demo",
            repository: "sample",
            created_at: "2026-01-15T00:00:00Z",
            updated_at: "2026-01-15T00:00:00Z",
          },
        ]}
      />,
    );
    expect(screen.getByText("Demo")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Checkout failed").closest("a")).toHaveAttribute(
      "href",
      "/investigations/abc123",
    );
  });
});

describe("repair outcome", () => {
  it("does not turn human review or legacy passed checks into verification", async () => {
    const { RepairOutcomePanel } = await import("./common");
    render(<RepairOutcomePanel outcome={{ status: "PATCH_UNVERIFIED", reasons: ["Independent isolation is missing."], validation_run_id: null }} />);
    expect(screen.getByRole("heading", { name: "Patch unverified" })).toBeInTheDocument();
    expect(screen.getByText(/does not verify or deploy/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Verified repair" })).not.toBeInTheDocument();
  });
  it("keeps unassessed work unclassified", async () => {
    const { RepairOutcomePanel } = await import("./common");
    const { container } = render(<RepairOutcomePanel outcome={null} />);
    expect(container).toBeEmptyDOMElement();
  });
  it.each([
    ["VERIFIED", "Verified repair"],
    ["NOT_REPRODUCED", "Issue not reproduced"],
    ["VALIDATION_FAILED", "Validation failed"],
    ["INSUFFICIENT_EVIDENCE", "Insufficient evidence"],
  ] as const)("renders %s independently from checks", async (status, title) => {
    const { RepairOutcomePanel } = await import("./common");
    render(<RepairOutcomePanel outcome={{ status, reasons: ["Measured evidence."], validation_run_id: "run-1" }} />);
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    expect(screen.getByText("Validation run: run-1")).toBeInTheDocument();
  });
});

describe("source grounding", () => {
  it("labels content snapshots without inventing a commit", async () => {
    const { SourceProvenance } = await import("./common");
    render(<SourceProvenance snapshot={{ version: 1, kind: "content", snapshot_id: "a".repeat(64), commit_sha: null }} />);
    expect(screen.getByText("Content snapshot; no Git commit recorded.")).toBeInTheDocument();
  });
  it("distinguishes a dirty working tree from its commit", async () => {
    const { SourceProvenance } = await import("./common");
    render(<SourceProvenance snapshot={{ version: 1, snapshot_id: "a".repeat(64), commit_sha: "b".repeat(40), modified: true }} />);
    expect(screen.getByText(/commit alone does not identify/)).toBeInTheDocument();
  });
  it("renders quoted source as text and shows its provenance", async () => {
    const { EvidenceCitations } = await import("./common");
    render(<EvidenceCitations title="Contradicting evidence" citations={[{
      evidence_id: "E2", kind: "source", path: "app.py", line_start: 3, line_end: 3,
      quote: "<script>doNotExecute()</script>", sha256: "c".repeat(64), snapshot_id: "a".repeat(64), commit_sha: "b".repeat(40),
    }]} />);
    expect(screen.getByText("Contradicting evidence")).toBeInTheDocument();
    expect(screen.getByText("<script>doNotExecute()</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByRole("link", { hidden: true })).toHaveAttribute("href", "#evidence-E2");
  });
});

describe("retrieval explanations", () => {
  it("shows why a caller was included without claiming a root cause", async () => {
    const { RetrievalDetails } = await import("./common");
    render(<RetrievalDetails retrieval={{ strategy: "symbols", rank: 2, reasons: ["Static caller of calculate in pricing.py."], symbols: [{ name: "invoice", kind: "function", line_start: 2, line_end: 3 }] }} />);
    expect(screen.getByText("Why this file")).toBeInTheDocument();
    expect(screen.getByText("Static caller of calculate in pricing.py.")).toBeInTheDocument();
    expect(screen.getByText("invoice · lines 2–3")).toBeInTheDocument();
  });
  it("makes partial index coverage explicit", async () => {
    const { RetrievalDetails } = await import("./common");
    render(<RetrievalDetails retrieval={{ strategy: "symbols", indexed_files: 10, skipped_count: 2, index_limited: true }} />);
    expect(screen.getByText(/coverage is partial/)).toBeInTheDocument();
    expect(screen.getByText(/2 files could not be indexed/)).toBeInTheDocument();
  });
});
