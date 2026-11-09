"use client";
import { use, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  Download,
  ExternalLink,
  FileCode2,
  GitPullRequest,
  ShieldCheck,
  X,
} from "lucide-react";
import { useIncident } from "@/hooks/use-incident";
import { api, post } from "@/lib/api";
import { Settings } from "@/types";
import { Button } from "@/components/ui/button";
import { Badge, ErrorBox, Loading, ValidationPanel } from "@/components/common";
import { date } from "@/lib/utils";
import { RepairOutcomePanel, SourceProvenance } from "@/components/common";
import { IsolatedValidation } from "@/components/isolated-validation";
import { Lifecycle } from "@/components/lifecycle";
import { useAuth } from "@/components/auth";

export default function Review({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { user } = useAuth();
  const { data, error, isPending } = useIncident(id);
  const client = useQueryClient();
  const [fileIndex, setFileIndex] = useState(0);
  const [note, setNote] = useState("");
  const [view, setView] = useState<"unified" | "split">("unified");
  const [authorized, setAuthorized] = useState(false);
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("/settings"),
  });
  const decision = useMutation({
    mutationFn: (action: "approve" | "reject") =>
      post(`/incidents/${id}/${action}`, { note }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["incident", id] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      void client.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
  const pr = useMutation({
    mutationFn: () =>
      post<{ url: string }>(`/incidents/${id}/pull-request`, {
        authorized: true,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["incident", id] }),
  });
  if (isPending) return <Loading />;
  if (!data) return <ErrorBox error={error} />;
  const fix = data.fix;
  if (!fix)
    return (
      <>
        <Link href={`/investigations/${id}`} className="back-link">
          <ArrowLeft size={14} /> Back to investigation
        </Link>
        <div className="empty-state">
          <h1>No patch available</h1>
          <p>The investigation has not produced a supported fix.</p>
        </div>
      </>
    );
  const selectedFile = fix.files?.[fileIndex] || {
    ...fix,
    diff: fix.proposed_patch,
  };
  const pending = fix.approval_status === "pending" && user?.role !== "viewer";
  const canApprove =
    ["passed", "partial"].includes(fix.validation_result.status) &&
    ["awaiting_review", "partial"].includes(data.status);
  return (
    <>
      <Link href={`/investigations/${id}`} className="back-link">
        <ArrowLeft size={14} /> Back to investigation
      </Link>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            HUMAN REVIEW / INC-{id.slice(0, 8).toUpperCase()}
          </div>
          <h1>A small change. A clear explanation.</h1>
          <p>
            Review the proposal, understand its limits, and record your
            decision.
          </p>
        </div>
        <Badge value={fix.approval_status} />
      </div>
      <ErrorBox error={error || decision.error || pr.error} />
      <div className="review-layout">
        <div>
          <section className="panel diff-panel">
            <div className="panel-heading">
              <div className="file-heading">
                <FileCode2 size={18} />
                <select
                  aria-label="Patch file"
                  value={fileIndex}
                  onChange={(e) => setFileIndex(Number(e.target.value))}
                >
                  {(fix.files?.length ? fix.files : [fix]).map((f, i) => (
                    <option key={f.path} value={i}>
                      {f.path}
                    </option>
                  ))}
                </select>
                <span className="diff-stat">
                  +
                  {
                    selectedFile.diff
                      .split("\n")
                      .filter((l) => l.startsWith("+") && !l.startsWith("+++"))
                      .length
                  }{" "}
                  <i>
                    −
                    {
                      selectedFile.diff
                        .split("\n")
                        .filter(
                          (l) => l.startsWith("-") && !l.startsWith("---"),
                        ).length
                    }
                  </i>
                </span>
              </div>
              <div className="segmented-control" aria-label="Diff display">
                <button
                  onClick={() => setView("unified")}
                  aria-pressed={view === "unified"}
                >
                  Unified
                </button>
                <button
                  onClick={() => setView("split")}
                  aria-pressed={view === "split"}
                >
                  Split
                </button>
              </div>
            </div>
            {view === "unified" ? (
              <pre className="diff-code" aria-label="Proposed unified diff">
                {selectedFile.diff.split("\n").map((line, i) => (
                  <span
                    className={
                      line.startsWith("@@")
                        ? "diff-hunk"
                        : line.startsWith("+")
                          ? "diff-add"
                          : line.startsWith("-")
                            ? "diff-remove"
                            : ""
                    }
                    key={i}
                  >
                    <i>{i + 1}</i>
                    {line}
                    {"\n"}
                  </span>
                ))}
              </pre>
            ) : (
              <div className="split-diff">
                <div>
                  <h3>Original code</h3>
                  <pre>{selectedFile.original_code}</pre>
                </div>
                <div>
                  <h3>Proposed code</h3>
                  <pre>{selectedFile.proposed_code}</pre>
                </div>
              </div>
            )}
          </section>
          <SourceProvenance snapshot={data.repository_snapshot} />
          <RepairOutcomePanel outcome={data.repair_outcome} />
          <section className="panel panel-body review-validation">
            <ValidationPanel validation={fix.validation_result} />
          </section>
          <IsolatedValidation
            id={id}
            repository={data.repository === "github" ? `github@${data.repository_commit}` : data.repository_snapshot?.version === 1 ? `${data.repository}@${data.id}` : data.repository}
            pending={pending}
            running={fix.validation_result.status === "running"}
          />
          <section className="panel panel-body">
            <h2>Why this change</h2>
            <p className="explanation">{fix.explanation}</p>
            <h3>Regression risks</h3>
            <ul className="risk-list">
              {fix.risks.map((risk, i) => (
                <li key={i}>{risk}</li>
              ))}
            </ul>
          </section>
        </div>
        <aside>
          <Lifecycle data={data} />
          <section className="panel decision-panel">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">THE FINAL GATE</span>
                <h2>Your review</h2>
              </div>
              <ShieldCheck size={21} />
            </div>
            <div className="panel-body">
              {pending ? (
                <>
                  <p>
                    Approval records your decision. It does not edit the
                    repository, commit code, or deploy a change.
                  </p>
                  <label htmlFor="review-note">
                    Review note <span className="muted">(optional)</span>
                  </label>
                  <textarea
                    id="review-note"
                    rows={4}
                    maxLength={2000}
                    placeholder="Document your reasoning for the team…"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                  <Button
                    className="full-width"
                    disabled={!canApprove || decision.isPending}
                    onClick={() => decision.mutate("approve")}
                  >
                    <Check size={17} />
                    {decision.isPending ? "Saving decision…" : "Approve fix"}
                  </Button>
                  <Button
                    className="full-width"
                    variant="destructive"
                    disabled={
                      decision.isPending ||
                      fix.validation_result.status === "running" ||
                      !["awaiting_review", "partial"].includes(data.status)
                    }
                    onClick={() => decision.mutate("reject")}
                  >
                    <X size={16} /> Reject fix
                  </Button>
                  {!canApprove && (
                    <p className="fine-print">
                      Approval is available after validation finishes without
                      failed checks.
                    </p>
                  )}
                </>
              ) : fix.approval_status === "pending" ? (
                <p>Viewer access. An editor or administrator must review this proposal.</p>
              ) : (
                <>
                  <div className="decision-saved">
                    <ShieldCheck size={30} />
                    <h3>Decision recorded</h3>
                    <Badge value={fix.approval_status} />
                    <p>{fix.decided_at && date(fix.decided_at)}</p>
                  </div>
                  {fix.decision_note && (
                    <blockquote>{fix.decision_note}</blockquote>
                  )}
                  <p className="fine-print">
                    This decision is persisted with the incident. The source
                    repository remains unchanged.
                  </p>
                </>
              )}
              <Button asChild variant="outline" className="full-width">
                <a
                  href={`/api/incidents/${id}/patch`}
                  download={`patch-${id}.json`}
                >
                  <Download size={15} /> Download patch record
                </a>
              </Button>
            </div>
          </section>
          {fix.approval_status === "approved" && user?.role !== "viewer" && (
            <section className="panel github-panel">
              <div className="panel-heading">
                <h2>Draft pull request</h2>
                <GitPullRequest size={18} />
              </div>
              <div className="panel-body">
                {fix.pr_url ? (
                  <Button asChild variant="outline">
                    <a href={fix.pr_url} target="_blank" rel="noreferrer">
                      Open pull request <ExternalLink size={14} />
                    </a>
                  </Button>
                ) : settings.data?.github_configured &&
                  ["local", "github"].includes(data.repository) ? (
                  <>
                    <p>
                      Publish this reviewed change to{" "}
                      <strong>{settings.data.github_repository}</strong> as a
                      draft pull request.
                    </p>
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={authorized}
                        onChange={(e) => setAuthorized(e.target.checked)}
                      />
                      <span>
                        I authorize creating a branch, commit, and draft pull
                        request in this repository.
                      </span>
                    </label>
                    <Button
                      disabled={!authorized || pr.isPending}
                      onClick={() => pr.mutate()}
                    >
                      <GitPullRequest size={15} />
                      {pr.isPending
                        ? "Creating draft…"
                        : "Create draft pull request"}
                    </Button>
                  </>
                ) : (
                  <p className="muted">
                    Available for a configured GitHub repository or a local
                    repository with a matching GitHub target.
                  </p>
                )}
              </div>
            </section>
          )}
        </aside>
      </div>
    </>
  );
}
