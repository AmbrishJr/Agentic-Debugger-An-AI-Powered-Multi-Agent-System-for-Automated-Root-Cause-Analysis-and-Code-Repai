"use client";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, Play, ShieldCheck } from "lucide-react";
import { api, post } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, ErrorBox } from "@/components/common";

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
  const [selected, setSelected] = useState<string[]>([]);
  const [profile, setProfile] = useState("python-unittest");
  const [consent, setConsent] = useState(false);
  const [plan, setPlan] = useState<Run | null>(null);
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
    mutationFn: () =>
      post<Run>(`/incidents/${id}/validation-plans`, {
        files: selected,
        profile,
      }),
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
          authorize.error
        }
      />
      <p className="fine-print">
        Run a fixed Python unittest or pytest profile in two fresh containers,
        before and after the patch. No network, credentials, or host mounts are
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
          {!plan && (
            <Button
              variant="outline"
              className="full-width"
              disabled={!selected.length || prepare.isPending}
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
                        "Container cleanup failed; operator action required."}
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
