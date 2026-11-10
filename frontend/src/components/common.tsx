"use client";
import {
  AlertCircle,
  LoaderCircle,
  Search,
  Check,
  Minus,
  X,
} from "lucide-react";
import Link from "next/link";
import { label, date } from "@/lib/utils";
import { Incident, Validation, RepairOutcome, Citation, RepositorySnapshot, SourceRetrieval } from "@/types";

export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge badge-${value}`}>
      <span />
      {label(value)}
    </span>
  );
}
export function Loading() {
  return (
    <div className="empty-state" role="status">
      <LoaderCircle className="spin" />
      <h3>Loading workspace…</h3>
    </div>
  );
}
export function ErrorBox({ error }: { error: Error | null }) {
  return error ? (
    <div className="error-box" role="alert">
      <AlertCircle size={18} />
      <span>{error.message}</span>
    </div>
  ) : null;
}
export function Empty({
  title = "No incidents yet",
  description = "Start an investigation to turn an error log into an actionable report.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Search size={24} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      <Link href="/investigations/new" className="text-link">
        Start an investigation →
      </Link>
    </div>
  );
}
export function IncidentTable({ incidents }: { incidents: Incident[] }) {
  if (!incidents.length) return <Empty />;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Incident</th>
            <th>Severity</th>
            <th>Status</th>
            <th>Mode</th>
            <th>Created</th>
            <th>
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((i) => (
            <tr key={i.id}>
              <td>
                <Link
                  href={`/investigations/${i.id}`}
                  className="incident-link"
                >
                  <span className="incident-id">
                    INC-{i.id.slice(0, 6).toUpperCase()}
                  </span>
                  <strong>{i.title}</strong>
                </Link>
              </td>
              <td>
                <Badge value={i.severity} />
              </td>
              <td>
                <Badge value={i.status} />
              </td>
              <td>
                <span className="muted">
                  {i.mode === "demo" ? "Demo" : "Live AI"}
                </span>
              </td>
              <td className="nowrap muted">{date(i.created_at)}</td>
              <td>
                <Link
                  href={`/investigations/${i.id}`}
                  aria-label={`Open ${i.title}`}
                  className="row-arrow"
                >
                  ↗
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function RepairOutcomePanel({ outcome }: { outcome?: RepairOutcome | null }) {
  if (!outcome) return null;
  const titles: Record<RepairOutcome["status"], string> = {
    VERIFIED: "Verified repair",
    PATCH_UNVERIFIED: "Patch unverified",
    NOT_REPRODUCED: "Issue not reproduced",
    VALIDATION_FAILED: "Validation failed",
    INSUFFICIENT_EVIDENCE: "Insufficient evidence",
  };
  return (
    <section className="panel panel-body" aria-label="Repair outcome">
      <h3>{titles[outcome.status]}</h3>
      {outcome.reasons.map((reason) => <p key={reason}>{reason}</p>)}
      {outcome.validation_run_id && <p className="fine-print">Validation run: {outcome.validation_run_id}</p>}
      <p className="fine-print">Human approval records a review decision; it does not verify or deploy a repair.</p>
    </section>
  );
}
export function ValidationPanel({ validation }: { validation: Validation }) {
  return (
    <div className="validation">
      <div className="section-heading">
        <h3>Validation checks</h3>
        <Badge value={validation.status || "pending"} />
      </div>
      {validation.checks?.map((c) => (
        <div className="check-row" key={c.name}>
          <span className={`check-icon ${c.status}`}>
            {c.status === "passed" ? (
              <Check size={15} />
            ) : c.status === "failed" ? (
              <X size={15} />
            ) : (
              <Minus size={15} />
            )}
          </span>
          <div>
            <strong>{c.name}</strong>
            <p>{c.detail}</p>
          </div>
          <Badge value={c.status} />
        </div>
      ))}
      <p className="fine-print">{validation.limitations}</p>
      {validation.fixture?.before && (
        <details>
          <summary>View demo before / after test output</summary>
          <p className="fine-print">Measured trusted demo on the host; not isolated repair verification.</p>
          <h4>Before fix · expected failure</h4>
          <pre>{validation.fixture.before.output}</pre>
          <h4>After fix</h4>
          <pre>{validation.fixture.after.output}</pre>
        </details>
      )}
    </div>
  );
}

export function SourceProvenance({ snapshot }: { snapshot?: RepositorySnapshot }) {
  if (!snapshot?.snapshot_id) return <p className="fine-print">Legacy investigation: no pinned source manifest.</p>;
  return <details className="panel panel-body">
    <summary>Source provenance</summary>
    <p className="fine-print" style={{ overflowWrap: "anywhere" }}>
      {snapshot.commit_sha ? `Commit: ${snapshot.commit_sha}` : "Content snapshot; no Git commit recorded."}
    </p>
    <p className="fine-print" style={{ overflowWrap: "anywhere" }}>Snapshot: {snapshot.snapshot_id}</p>
    {snapshot.modified === true && <p>Captured files include working-tree changes; the commit alone does not identify these contents.</p>}
    <p className="fine-print">{snapshot.coverage}</p>
  </details>;
}

export function EvidenceCitations({ citations, title }: { citations?: Citation[]; title: string }) {
  if (!citations?.length) return null;
  return <div>
    <h4>{title}</h4>
    {citations.map((c, index) => <details key={`${c.evidence_id}-${c.line_start}-${index}`}>
      <summary style={{ overflowWrap: "anywhere" }}>
        {c.evidence_id} · {c.path}:{c.line_start}–{c.line_end}
      </summary>
      <pre className="numbered-code">{c.quote}</pre>
      <p className="fine-print" style={{ overflowWrap: "anywhere" }}>
        {c.commit_sha ? `Commit ${c.commit_sha}` : "Content-pinned reference"} · SHA-256 {c.sha256}
      </p>
      <a href={`#evidence-${c.evidence_id}`}>Open collected evidence</a>
    </details>)}
  </div>;
}

export function RetrievalDetails({ retrieval }: { retrieval?: SourceRetrieval }) {
  if (!retrieval?.strategy) return null;
  return <div className="fine-print">
    {!!retrieval.reasons?.length && <div><strong>Why this file</strong><ul>{retrieval.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></div>}
    {!!retrieval.symbols?.length && <details><summary>Indexed symbols</summary><ul>{retrieval.symbols.map((symbol) => <li key={`${symbol.name}-${symbol.line_start}`}>{symbol.name} · lines {symbol.line_start}–{symbol.line_end}</li>)}</ul></details>}
    {retrieval.indexed_files !== undefined && <p>Source retrieval: {retrieval.strategy === "symbols" ? "Python symbols and dependencies" : "Selected files and stack frames"} · {retrieval.indexed_files} indexed files</p>}
    {retrieval.index_limited && <p>Index budget reached; source coverage is partial.</p>}
    {!!retrieval.skipped_count && <p>{retrieval.skipped_count} files could not be indexed; path-based retrieval remains available.</p>}
    {retrieval.notices?.map((notice) => <p key={notice}>{notice}</p>)}
    {retrieval.limitations && <p>{retrieval.limitations}</p>}
  </div>;
}
