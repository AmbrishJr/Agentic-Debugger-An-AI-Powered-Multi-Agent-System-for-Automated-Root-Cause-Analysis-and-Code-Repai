import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { specificationInput, VerificationSpecificationSummary } from "./verification-specification";

describe("reviewed verification specifications", () => {
  it("requires review and rejects malformed reproduction lines", () => {
    expect(() => specificationInput("test_a.Tests.test_one | ValueError", "test_a.Tests.test_one", "Reviewed incident", false)).toThrow(/Review the tests/);
    expect(() => specificationInput("test_a.Tests.test_one", "test_a.Tests.test_one", "Reviewed incident", true)).toThrow(/ExpectedException/);
  });
  it("normalizes the user declarations without inventing tests", () => {
    const spec = specificationInput(" test_a.Tests.test_one | ValueError \n", "test_a.Tests.test_one\n\ntest_a.Tests.test_two", " Reviewed against incident ", true);
    expect(spec.reproduction).toEqual([{ test_id: "test_a.Tests.test_one", expected_exception: "ValueError" }]);
    expect(spec.regressions).toEqual(["test_a.Tests.test_one", "test_a.Tests.test_two"]);
    expect(spec.rationale).toBe("Reviewed against incident");
  });
  it("shows matched observations with their explicit proof limitation", () => {
    render(<VerificationSpecificationSummary spec={{
      declaration: specificationInput("test_a.Tests.test_one | ValueError", "test_a.Tests.test_one", "Reviewed against incident", true),
      reviewer: "editor", reviewed_at: "2026-11-10T00:00:00Z", snapshot_id: "snapshot", tests: [],
      independence: "reviewer_declared_not_proven", limitations: "Declared expectations only.",
    }} assessment={{ status: "matched", independent_proof: false, reasons: ["Expected failure was reported."],
      reproduction: [], regressions: [], limitations: "Repository output does not independently verify a generic repair." }} />);
    expect(screen.getByRole("heading", { name: "Specification observations: matched" })).toBeInTheDocument();
    expect(screen.getByText(/does not independently verify/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Verified repair" })).not.toBeInTheDocument();
  });
  it("retains compatibility when an older run has no specification", () => {
    const { container } = render(<VerificationSpecificationSummary />);
    expect(container).toBeEmptyDOMElement();
  });
  it("shows JSON cases and controller observations without claiming generic verification", () => {
    render(<VerificationSpecificationSummary spec={{ kind: "json-stdio", declaration: {
      version: 1, reviewed: true, entrypoint: "main.py", rationale: "Reviewed interface behavior", cases: [
        { id: "bug", role: "reproduction", input: 2, baseline: 1, expected: 3 },
        { id: "zero", role: "regression", input: 0, baseline: 0, expected: 0 }],
    }, reviewer: "editor", reviewed_at: "2026-11-11T00:00:00Z", snapshot_id: "snapshot", source_hashes: {}, oracle_version: 1,
      limitations: "Generic VERIFIED eligibility is unchanged." }} assessment={{ status: "matched", independent_proof: false,
      reasons: ["Controller compared withheld answers."], limitations: "Generic VERIFIED eligibility is unchanged.",
      cases: [{ id: "bug", role: "reproduction", before_matches_baseline: true, after_matches_expected: true }] }} />);
    expect(screen.getByRole("heading", { name: "Contract observations: matched" })).toBeInTheDocument();
    expect(screen.getByText(/4 fresh isolated invocations/)).toBeInTheDocument();
    expect(screen.getByText(/eligibility is unchanged/)).toBeInTheDocument();
  });
});
