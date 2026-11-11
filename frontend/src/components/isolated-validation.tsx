"use client";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Play, ShieldCheck } from "lucide-react";
import { api, post } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, ErrorBox } from "@/components/common";
import { useAuth } from "@/components/auth";
import { specificationInput, VerificationSpecificationSummary } from "@/components/verification-specification";
import type { BoundJsonContract, BoundVerificationSpecification, SpecificationAssessment } from "@/types";

type Run = {
  id: string;
  status: string;
  plan_hash: string;
  expires_at: string;
  manifest: { path: string; sha256: string; bytes: number }[];
  policy: {
    image: string;
    profile: string;
    timeout_seconds: number;
    memory_mb: number;
  };
  result: {
    verification_spec?: BoundVerificationSpecification | BoundJsonContract;
    specification_assessment?: SpecificationAssessment;
    error?: string;
    before?: {
      status: string;
      output: string;
      exit_code: number | null;
      timed_out?: boolean;
      output_limited?: boolean;
      cleanup_succeeded?: boolean;
    };
    after?: {
      status: string;
      output: string;
      exit_code: number | null;
      timed_out?: boolean;
      output_limited?: boolean;
      cleanup_succeeded?: boolean;
    };
  };
};

export function IsolatedValidation({
  id,
  repository,
  pending,
  running,
}: {
  id: string;
  repository: string;
  pending: boolean;
  running: boolean;
}) {
  const client = useQueryClient();
  const { user } = useAuth();
  const [selected, setSelected] = useState<string[]>([]);
  const [profile, setProfile] = useState("python-unittest");
  const [consent, setConsent] = useState(false);
  const [plan, setPlan] = useState<Run | null>(null);
  const [specEnabled, setSpecEnabled] = useState(false);
  const [specReviewed, setSpecReviewed] = useState(false);
  const [reproduction, setReproduction] = useState("");
  const [regressions, setRegressions] = useState("");
  const [rationale, setRationale] = useState("");
  const [contractText, setContractText] = useState("");
  const [contractReviewed, setContractReviewed] = useState(false);
  const runner = useQuery({
    queryKey: ["sandbox"],
    queryFn: () => api<{ available: boolean; reason: string }>("/sandbox"),
  });
  const files = useQuery({
    queryKey: ["files", repository],
    queryFn: () =>
      api<{ items: string[] }>(`/repositories/${repository}/files`),
    enabled: pending && !!runner.data?.available,
  });
  const runs = useQuery({
    queryKey: ["validation-runs", id],
    queryFn: () => api<{ items: Run[] }>(`/incidents/${id}/validation-runs`),
    refetchInterval: (q) =>
      q.state.data?.items.some((r) => r.status === "running") || running
        ? 1500
        : false,
  });
  useEffect(() => {
    if (runs.data) {
      void client.invalidateQueries({ queryKey: ["incident", id] });
    }
  }, [runs.dataUpdatedAt, client, id]);
  const prepare = useMutation({
    mutationFn: () => {
      let jsonContract;
      if (profile === "python-json-stdio") {
        if (!contractReviewed) throw new Error("Review the JSON contract first.");
        try { jsonContract = JSON.parse(contractText); } catch { throw new Error("Enter valid JSON for the behavior contract."); }
        if (!jsonContract || Array.isArray(jsonContract) || typeof jsonContract !== "object") throw new Error("The contract must be a JSON object.");
        jsonContract = { ...jsonContract, version: 1, reviewed: true };
      }
      return post<Run>(`/incidents/${id}/validation-plans`, {
        files: selected,
        profile,
        verification_spec: specEnabled && profile === "python-unittest"
          ? specificationInput(reproduction, regressions, rationale, specReviewed) : undefined,
        json_contract: jsonContract,
      });
    },
    onSuccess: (r) => {
      setPlan(r);
      setConsent(false);
      void client.invalidateQueries({ queryKey: ["validation-runs", id] });
    },
  });
  const authorize = useMutation({
    mutationFn: () =>
      post(`/incidents/${id}/validation-runs/${plan!.id}/authorize`, {
        authorized: true,
        plan_hash: plan!.plan_hash,
      }),
    onSuccess: () => {
      setPlan(null);
      setConsent(false);
      void client.invalidateQueries({ queryKey: ["validation-runs", id] });
      void client.invalidateQueries({ queryKey: ["incident", id] });
    },
  });
  const cleanup = useMutation({
    mutationFn: (runId: string) => post(`/incidents/${id}/validation-runs/${runId}/cleanup`, {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["validation-runs", id] });
      void client.invalidateQueries({ queryKey: ["incident", id] });
    },
  });
  return (
    <section className="panel panel-body review-validation">
      <div className="section-heading">
        <h3>
          <Box size={16} className="inline" /> Isolated repository tests
        </h3>
        <Badge
          value={
            running
              ? "running"
              : runner.data?.available
                ? "available"
                : "unavailable"
          }
        />
      </div>
      <ErrorBox
        error={
          runner.error ||
          files.error ||
          runs.error ||
          prepare.error ||
          authorize.error || cleanup.error
        }
      />
      <p className="fine-print">
        Run a fixed Python test profile before and after the patch. JSON behavior contracts run each input in a fresh environment for both versions. No network, credentials, or host mounts are
        supplied. Only the selected snapshot is included.
      </p>
      {!runner.data?.available && (
        <p className="fine-print">
          {runner.data?.reason || "Checking runner availability…"}
        </p>
      )}
      {pending && runner.data?.available && !running && (
        <>
          <label>
            Test framework
            <select
              value={profile}
              onChange={(e) => {
                setProfile(e.target.value);
                setPlan(null);
                setConsent(false);
              }}
            >
              <option value="python-unittest">unittest</option>
              <option value="python-pytest">pytest</option>
              <option value="python-json-stdio">JSON behavior contract (Docker)</option>
            </select>
          </label>
          <details className="file-picker" open={!plan}>
            <summary>
              Select Python source and tests <span>{selected.length} / 32</span>
            </summary>
            <div className="file-options">
              {files.data?.items
                .filter((f) => f.endsWith(".py"))
                .map((path) => (
                  <label key={path}>
                    <input
                      type="checkbox"
                      checked={selected.includes(path)}
                      disabled={
                        !!plan ||
                        (!selected.includes(path) && selected.length >= 32)
                      }
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, path]
                            : selected.filter((p) => p !== path),
                        )
                      }
                    />
                    <span>{path}</span>
                  </label>
                ))}
            </div>
          </details>
          {!plan && profile === "python-json-stdio" && <div className="hypothesis">
            <p className="fine-print">Select source files only, including the entrypoint. The program reads one JSON value from stdin and returns one JSON value with no diagnostics. Expected answers remain outside the container.</p>
            <label htmlFor="json-contract">JSON behavior contract</label>
            <textarea id="json-contract" rows={12} value={contractText}
              placeholder={'{"entrypoint":"main.py","rationale":"Explain the incident behavior","cases":[{"id":"bug","role":"reproduction","input":2,"baseline":1,"expected":3},{"id":"zero","role":"regression","input":0,"baseline":0,"expected":0}]}'}
              onChange={(e) => { setContractText(e.target.value); setContractReviewed(false); }} />
            <p className="fine-print">Include 2–4 cases with both reproduction and regression roles. Each value is limited to 4 KiB. Matching cases do not independently establish test authorship or qualify generic repairs as VERIFIED.</p>
            <label className="checkbox-label"><input type="checkbox" checked={contractReviewed} onChange={(e) => setContractReviewed(e.target.checked)} />
              I reviewed the inputs, known baseline behavior, and expected answers against the incident.
            </label>
          </div>}
          {!plan && profile === "python-unittest" && <div className="hypothesis">
            <label className="checkbox-label"><input type="checkbox" checked={specEnabled}
              onChange={(e) => { setSpecEnabled(e.target.checked); setSpecReviewed(false); }} />
              Add reviewed reproduction and regression expectations
            </label>
            {specEnabled && <>
              <p className="fine-print">Use tests already present in the incident snapshot. Name the expected failures and the regressions that must pass. Matching repository output does not independently verify a generic repair.</p>
              <label htmlFor="reproduction-tests">Expected reproduction failures</label>
              <textarea id="reproduction-tests" rows={4} value={reproduction}
                placeholder="test_checkout.DiscountTests.test_zero_discount | ZeroDivisionError"
                onChange={(e) => { setReproduction(e.target.value); setSpecReviewed(false); }} />
              <p className="fine-print">One dotted unittest ID | ExpectedException per line. Every baseline failure must be declared.</p>
              <label htmlFor="required-regressions">Required regression tests</label>
              <textarea id="required-regressions" rows={4} value={regressions}
                placeholder="test_checkout.DiscountTests.test_zero_discount"
                onChange={(e) => { setRegressions(e.target.value); setSpecReviewed(false); }} />
              <p className="fine-print">One dotted unittest ID per line. These tests must all pass after the patch; reproduction tests must also pass.</p>
              <label htmlFor="specification-rationale">Why these tests cover the incident</label>
              <textarea id="specification-rationale" rows={3} maxLength={1000} value={rationale}
                onChange={(e) => { setRationale(e.target.value); setSpecReviewed(false); }} />
              <label className="checkbox-label"><input type="checkbox" checked={specReviewed}
                onChange={(e) => setSpecReviewed(e.target.checked)} />
                I reviewed these existing tests and their expected behavior against the incident.
              </label>
            </>}
          </div>}
          {!plan && (
            <Button
              variant="outline"
              className="full-width"
              disabled={!selected.length || prepare.isPending || (specEnabled && profile === "python-unittest" && !specReviewed) || (profile === "python-json-stdio" && !contractReviewed)}
              onClick={() => prepare.mutate()}
            >
              <ShieldCheck size={15} />
              {prepare.isPending
                ? "Preparing snapshot…"
                : "Prepare isolated test plan"}
            </Button>
          )}
          {plan && (
            <div className="hypothesis">
              <h3>Review this execution plan</h3>
              <p>
                Profile: {plan.policy.profile} · {plan.policy.timeout_seconds}s
                per run · {plan.policy.memory_mb} MB
              </p>
              <p className="fine-print">
                Expires: {new Date(plan.expires_at).toLocaleString()}. Changing
                a source or test file invalidates this plan.
              </p>
              <ul className="risk-list">
                {plan.manifest.map((f) => (
                  <li key={f.path}>
                    <code>{f.path}</code> · {f.bytes} bytes · SHA-256{" "}
                    {f.sha256.slice(0, 12)}…
                  </li>
                ))}
              </ul>
              <VerificationSpecificationSummary spec={plan.result.verification_spec} />
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                <span>
                  I authorize executing these source and test snapshots before
                  and after this patch in the restricted runner.
                </span>
              </label>
              <Button
                disabled={!consent || authorize.isPending}
                onClick={() => authorize.mutate()}
              >
                <Play size={15} />
                {authorize.isPending ? "Authorizing…" : "Run isolated tests"}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setPlan(null);
                  setConsent(false);
                }}
              >
                Change selection
              </Button>
            </div>
          )}
        </>
      )}
      {runs.data?.items
        .filter((r) => r.status !== "planned")
        .map((run) => (
          <details
            key={run.id}
            className="evidence-card"
            open={run.status === "running"}
          >
            <summary>
              <span>Isolated run {run.id.slice(0, 8)}</span>
              <Badge value={run.status} />
            </summary>
            {run.result.error && (
              <p className="error-text">{run.result.error}</p>
            )}
            <VerificationSpecificationSummary spec={run.result.verification_spec} assessment={run.result.specification_assessment} />
            {run.status === "cleanup_failed" && user?.role !== "viewer" && (
              <Button variant="outline" disabled={cleanup.isPending} onClick={() => cleanup.mutate(run.id)}>
                {cleanup.isPending ? "Cleaning up…" : "Retry sandbox cleanup"}
              </Button>
            )}
            {(["before", "after"] as const).map((phase) => {
              const result = run.result[phase];
              return (
                result && (
                  <div key={phase}>
                    <h4>
                      {phase === "before" ? "Before patch" : "After patch"} ·{" "}
                      {result.status} · exit {result.exit_code ?? "unavailable"}
                    </h4>
                    <p className="fine-print">
                      {result.timed_out && "Time limit exceeded. "}
                      {result.output_limited && "Output limit exceeded. "}
                      {result.cleanup_succeeded === false &&
                        "Sandbox cleanup failed; retry cleanup before running more tests."}
                    </p>
                    <pre>{result.output || "No process output recorded."}</pre>
                  </div>
                )
              );
            })}
          </details>
        ))}
    </section>
  );
}
