import type { BoundJsonContract, BoundVerificationSpecification, SpecificationAssessment, VerificationSpecification } from "@/types";

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
  spec?: BoundVerificationSpecification | BoundJsonContract;
  assessment?: SpecificationAssessment;
}) {
  if (!spec) return null;
  if (spec.kind === "json-stdio") return <div className="hypothesis">
    <h4>Reviewed JSON behavior contract</h4>
    <p>{spec.declaration.rationale}</p>
    <p className="fine-print">Reviewed by {spec.reviewer} · {spec.declaration.entrypoint} · {spec.declaration.cases.length * 2} fresh isolated invocations</p>
    {spec.provenance && <p className="fine-print">Registered before investigation with separate-account review · Contract {spec.provenance.registration_sha256.slice(0, 12)}…</p>}
    {spec.declaration.cases.map((item) => <details key={item.id}><summary>{item.id} · {item.role}</summary>
      <pre>{JSON.stringify({ input: item.input, baseline: item.baseline, expected: item.expected }, null, 2)}</pre>
    </details>)}
    {assessment && <><h4>Contract observations: {assessment.status.replaceAll("_", " ")}</h4>
      <ul>{assessment.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      <ul>{assessment.cases?.map((item) => <li key={item.id}>{item.id}: baseline {item.before_matches_baseline === undefined ? "unavailable" : item.before_matches_baseline ? "matched" : "different"}; patched {item.after_matches_expected === undefined ? "unavailable" : item.after_matches_expected ? "matched" : "different"}</li>)}</ul></>}
    <p className="fine-print">{assessment?.limitations ?? spec.limitations}</p>
  </div>;
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
