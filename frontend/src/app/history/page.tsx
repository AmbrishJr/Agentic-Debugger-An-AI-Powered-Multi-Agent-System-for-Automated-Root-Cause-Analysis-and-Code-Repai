"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, History, Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { Incident } from "@/types";
import { Button } from "@/components/ui/button";
import { ErrorBox, IncidentTable, Loading } from "@/components/common";
import { label } from "@/lib/utils";
export default function IncidentHistory() {
  const [q, setQ] = useState("");
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, isPending } = useQuery({
    queryKey: ["incidents", q, severity, status, offset],
    queryFn: () =>
      api<{ items: Incident[]; total: number }>(
        `/incidents?${new URLSearchParams({ q, severity, status, offset: String(offset), limit: "20" })}`,
      ),
  });
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR INVESTIGATION MEMORY</div>
          <h1>Every incident tells a story.</h1>
          <p>
            Revisit findings, trace decisions, and build on what you’ve learned.
          </p>
        </div>
        <Button asChild>
          <Link href="/investigations/new">
            <Plus size={16} /> New investigation
          </Link>
        </Button>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>
              Incident history{" "}
              <span className="count-pill">{data?.total || 0}</span>
            </h2>
            <p>All stored investigations, including labeled demo records.</p>
          </div>
          <History size={19} />
        </div>
        <div className="filter-bar">
          <div className="search-input">
            <Search size={17} />
            <input
              aria-label="Search incidents"
              placeholder="Search titles or error logs…"
              value={q}
              maxLength={200}
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
              }}
            />
          </div>
          <select
            aria-label="Filter by severity"
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All severities</option>
            {["critical", "high", "medium", "low"].map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
          <select
            aria-label="Filter by status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            {[
              "submitted",
              "investigating",
              "awaiting_review",
              "approved",
              "rejected",
              "partial",
              "failed",
              "needs_evidence",
            ].map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
        </div>
        <ErrorBox error={error} />
        {isPending ? (
          <Loading />
        ) : (
          data && <IncidentTable incidents={data.items} />
        )}
        <div className="pagination">
          <span>
            {data?.total
              ? `${offset + 1}–${Math.min(offset + 20, data.total)} of ${data.total}`
              : "0 results"}
          </span>
          <div>
            <Button
              variant="outline"
              size="sm"
              aria-label="Previous page"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              <ChevronLeft size={16} />
            </Button>
            <Button
              variant="outline"
              size="sm"
              aria-label="Next page"
              disabled={!data || offset + 20 >= data.total}
              onClick={() => setOffset(offset + 20)}
            >
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
