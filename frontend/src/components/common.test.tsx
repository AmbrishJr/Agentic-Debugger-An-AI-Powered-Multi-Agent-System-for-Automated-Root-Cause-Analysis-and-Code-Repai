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
