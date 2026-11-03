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
import { Incident, Validation } from "@/types";

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
export function ValidationPanel({ validation }: { validation: Validation }) {
  return (
    <div className="validation">
      <div className="section-heading">
        <h3>Validation results</h3>
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
          <summary>View before / after test output</summary>
          <h4>Before fix · expected failure</h4>
          <pre>{validation.fixture.before.output}</pre>
          <h4>After fix</h4>
          <pre>{validation.fixture.after.output}</pre>
        </details>
      )}
    </div>
  );
}
