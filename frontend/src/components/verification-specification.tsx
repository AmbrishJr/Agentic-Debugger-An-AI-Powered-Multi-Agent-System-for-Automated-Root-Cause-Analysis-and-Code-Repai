import type { BoundVerificationSpecification, SpecificationAssessment, VerificationSpecification } from "@/types";

export function specificationInput(reproduction: string, regressions: string, rationale: string, reviewed: boolean): VerificationSpecification {
  if (!reviewed) throw new Error("Review the tests and acknowledge the verification specification first.");
  const lines = (value: string) => value.split("\n").map((line) => line.trim()).filter(Boolean);
  return {
    version: 1,
    reviewed: true,
    rationale: rationale.trim(),
    reproduction: lines(reproduction).map((line) => {
      const parts = line.split("|").map((part) => part.trim());
      if (parts.length !== 2 || parts.some((part) => !part)) throw new Error("Use one test ID | ExpectedException per reproduction line.");
      return { test_id: parts[0], expected_exception: parts[1] };
    }),
    regressions: lines(regressions),
  };
}

export function VerificationSpecificationSummary({ spec, assessment }: {
  spec?: BoundVerificationSpecification;
  assessment?: SpecificationAssessment;
}) {
  if (!spec) return null;
  return <div className="hypothesis">
    <h4>Reviewed verification specification</h4>
    <p>{spec.declaration.rationale}</p>
    <p className="fine-print">Reviewed by {spec.reviewer} · {new Date(spec.reviewed_at).toLocaleString()}</p>
    <p>Expected baseline failures</p>
    <ul>{spec.declaration.reproduction.map((test) => <li key={test.test_id}><code>{test.test_id}</code> · {test.expected_exception}</li>)}</ul>
    <p>Required regressions after the patch</p>
    <ul>{spec.declaration.regressions.map((id) => <li key={id}><code>{id}</code></li>)}</ul>
    {assessment && <>
      <h4>Specification observations: {assessment.status.replaceAll("_", " ")}</h4>
      <ul>{assessment.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
    </>}
    <p className="fine-print">{assessment?.limitations ?? spec.limitations}</p>
  </div>;
}
