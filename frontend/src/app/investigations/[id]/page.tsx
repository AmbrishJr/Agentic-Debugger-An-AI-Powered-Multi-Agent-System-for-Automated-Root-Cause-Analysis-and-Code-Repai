"use client";
import { use, useEffect, useRef } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Circle,
  Download,
  FileCode2,
  FlaskConical,
  GitPullRequest,
  LoaderCircle,
  Play,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { useIncident } from "@/hooks/use-incident";
import { post } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge, ErrorBox, Loading, ValidationPanel } from "@/components/common";
import { date, label } from "@/lib/utils";

const agents = [
  ["triage", "Triage", "Understand the failure"],
  ["evidence", "Evidence collection", "Locate verifiable source context"],
  ["memory", "Incident memory", "Retrieve historical context"],
  ["analysis", "Root cause analysis", "Rank evidence-backed hypotheses"],
  ["fix", "Fix generation", "Propose a minimal change"],
  ["validation", "Validation", "Check the patch and test limits"],
  ["report", "Report", "Prepare a reviewable conclusion"],
];
export default function Investigation({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data, error, isPending } = useIncident(id);
  const client = useQueryClient();
  const started = useRef(false);
  const start = useMutation({
    mutationFn: () => post(`/incidents/${id}/investigate`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["incident", id] }),
  });
  useEffect(() => {
    if (
      data?.status === "submitted" &&
      !started.current &&
      new URLSearchParams(window.location.search).has("start")
    ) {
      started.current = true;
      start.mutate();
    }
  }, [data?.status]); // One start per mounted incident; backend enforces atomic claiming.
  if (isPending) return <Loading />;
  if (!data) return <ErrorBox error={error} />;
  const results = data.investigation?.analysis_results;
  const report = results?.report;
  const completed = data.executions.filter(
    (e) => e.execution_status === "completed",
  ).length;
  return (
    <>
      <Link href="/history" className="back-link">
        <ArrowLeft size={14} /> All incidents
      </Link>
      <div className="page-heading detail-heading">
        <div>
          <div className="eyebrow">
            INC-{id.slice(0, 8).toUpperCase()}{" "}
            <span className="eyebrow-separator">/</span>{" "}
            {data.mode === "demo"
              ? "DETERMINISTIC DEMO"
              : "LIVE AI INVESTIGATION"}
          </div>
          <h1>{data.title}</h1>
          <div className="heading-meta">
            <Badge value={data.severity} />
            <Badge value={data.status} />
            <span>{date(data.created_at)}</span>
          </div>
        </div>
        <div className="heading-actions">
          {report && (
            <Button asChild variant="outline">
              <a
                href={`/api/incidents/${id}/report`}
                download={`autorca-${id}.json`}
              >
                <Download size={15} /> Report
              </a>
            </Button>
          )}
          {data.fix && (
            <Button asChild>
              <Link href={`/investigations/${id}/review`}>
                <GitPullRequest size={16} /> Review fix <ArrowRight size={15} />
              </Link>
            </Button>
          )}
          {data.status === "submitted" && (
            <Button onClick={() => start.mutate()} disabled={start.isPending}>
              <Play size={15} /> Run investigation
            </Button>
          )}
        </div>
      </div>
      <ErrorBox error={error || start.error} />
      {data.mode === "demo" && (
        <div className="inline-notice">
          <FlaskConical size={16} />
          <span>
            Demo Mode · This investigation uses deterministic logic, not LLM
            inference. Validation outcomes are measured test results.
          </span>
        </div>
      )}
      {["partial", "failed"].includes(data.status) && (
        <div className="error-box" role="alert">
          The investigation did not fully complete. Available results are
          preserved below. Review failed agent details and submit a new incident
          after correcting configuration.
        </div>
      )}
      <div className="investigation-layout">
        <aside className="panel agent-panel">
          <div className="panel-heading">
            <div>
              <h2>Agent workflow</h2>
              <p>{completed} of 7 completed</p>
            </div>
            <span className="live-dot" />
          </div>
          <div className="agent-list">
            {agents.map(([key, title, description], i) => {
              const execution = data.executions.find(
                (e) => e.agent_name === key,
              );
              return (
                <details
                  key={key}
                  className={`agent-step ${execution?.execution_status || "queued"}`}
                >
                  <summary>
                    <span className="agent-step-icon">
                      {execution?.execution_status === "completed" ? (
                        <Check size={15} />
                      ) : execution?.execution_status === "running" ? (
                        <LoaderCircle size={15} className="spin" />
                      ) : execution?.execution_status === "failed" ? (
                        <X size={15} />
                      ) : (
                        <span>{i + 1}</span>
                      )}
                    </span>
                    <div>
                      <strong>{title}</strong>
                      <small>{description}</small>
                    </div>
                    <span className="agent-duration">
                      {execution ? (
                        `${execution.duration.toFixed(1)}s`
                      ) : (
                        <Circle size={8} />
                      )}
                    </span>
                  </summary>
                  <div className="agent-output">
                    {execution ? (
                      <>
                        <Badge value={execution.execution_status} />
                        {execution.error_details && (
                          <p className="error-text">
                            {execution.error_details}
                          </p>
                        )}
                        <pre>
                          {JSON.stringify(execution.output_summary, null, 2)}
                        </pre>
                      </>
                    ) : (
                      <p>This agent has not started.</p>
                    )}
                  </div>
                </details>
              );
            })}
          </div>
          <div className="agent-footer">
            <ShieldCheck size={16} />
            <span>Concise outputs & verifiable evidence</span>
          </div>
        </aside>
        <div className="investigation-main">
          <section className="panel summary-panel">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">THE FINDING</span>
                <h2>Root cause analysis</h2>
              </div>
              <Search size={19} />
            </div>
            <div className="panel-body">
              {results?.analysis ? (
                <>
                  <p className="root-summary">{results.analysis.summary}</p>
                  <div className="facts">
                    <h3>Observed facts</h3>
                    {results.analysis.observed_facts.map((fact, i) => (
                      <p key={i}>
                        <Check size={15} />
                        {fact}
                      </p>
                    ))}
                  </div>
                  {results.analysis.hypotheses.map((h, i) => (
                    <div className="hypothesis" key={i}>
                      <div className="section-heading">
                        <h3>
                          {i + 1}. {h.title}
                        </h3>
                        <span className="confidence">
                          {h.confidence} confidence
                        </span>
                      </div>
                      <p>{h.explanation}</p>
                      <div className="evidence-chips">
                        {h.evidence_ids.map((e) => (
                          <a key={e} href={`#evidence-${e}`}>
                            {e}
                          </a>
                        ))}
                      </div>
                      <p className="fine-print">Uncertainty: {h.uncertainty}</p>
                    </div>
                  ))}
                </>
              ) : (
                <div className="quiet-state">
                  <Search size={25} />
                  <p>
                    {data.status === "investigating"
                      ? "Agents are gathering evidence. Findings will appear here."
                      : "Run the investigation to generate a root cause report."}
                  </p>
                </div>
              )}
            </div>
          </section>
          {results?.evidence && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>
                    Evidence trail{" "}
                    <span className="count-pill">
                      {results.evidence.length}
                    </span>
                  </h2>
                  <p>Source snapshots and the submitted log.</p>
                </div>
                <FileCode2 size={18} />
              </div>
              <div className="evidence-list">
                {results.evidence.map((e) => (
                  <details
                    className="evidence-card"
                    id={`evidence-${e.id}`}
                    key={e.id}
                  >
                    <summary>
                      <span className="evidence-tag">{e.id}</span>
                      <div>
                        <strong>{e.path}</strong>
                        <small>
                          Lines {e.line_start}–{e.line_end} · {e.kind}
                        </small>
                      </div>
                      <span className="source-label">View source</span>
                    </summary>
                    <pre className="numbered-code">
                      {e.content.split("\n").map((line, i) => (
                        <span key={i}>
                          <i>{e.line_start + i}</i>
                          {line}
                          {"\n"}
                        </span>
                      ))}
                    </pre>
                    <p className="hash-label">SHA-256 {e.sha256}</p>
                  </details>
                ))}
              </div>
            </section>
          )}
          {results?.validation && (
            <section className="panel panel-body">
              <ValidationPanel validation={results.validation} />
            </section>
          )}
          {results?.fix && !results.fix.available && (
            <div className="inline-notice">{results.fix.reason}</div>
          )}
          {results?.memory && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Historical context</h2>
                  <p>Keyword retrieval · past hypotheses are not proof</p>
                </div>
              </div>
              <div className="panel-body">
                {results.memory.length ? (
                  results.memory.map((m) => (
                    <Link
                      className="memory-card"
                      href={`/investigations/${m.incident_id}`}
                      key={m.incident_id}
                    >
                      <strong>{m.root_cause}</strong>
                      <p>{m.resolution_summary}</p>
                      <small>{m.retrieval}</small>
                    </Link>
                  ))
                ) : (
                  <p className="muted">
                    No similar previous incidents found. Memory grows as
                    investigations complete.
                  </p>
                )}
              </div>
            </section>
          )}
          {report && (
            <section className="panel">
              <div className="panel-heading">
                <h2>Recommended next steps</h2>
              </div>
              <div className="panel-body">
                <p className="muted">{report.risk_assessment}</p>
                <ol className="next-steps">
                  {report.next_steps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
                <span className="fine-print">
                  Review status:{" "}
                  {label(data.fix?.approval_status || "not_applicable")}
                </span>
              </div>
            </section>
          )}
        </div>
      </div>
    </>
  );
}
