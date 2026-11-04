"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Detail } from "@/types";
import { post } from "@/lib/api";
import { useAuth } from "./auth";
import { Button } from "./ui/button";
import { ErrorBox, Badge } from "./common";
import { date } from "@/lib/utils";

export function Lifecycle({ data }: { data: Detail }) {
  const client = useQueryClient();
  const { user } = useAuth();
  const editable = user?.role !== "viewer";
  const [note, setNote] = useState("");
  const [evidence, setEvidence] = useState("");
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) =>
      post(path, body || {}),
    onSuccess: () => {
      setNote("");
      setEvidence("");
      void client.invalidateQueries();
    },
  });
  const job = data.jobs?.find((j) => j.kind === "investigation");
  return (
    <section className="panel panel-body">
      <h2>Incident lifecycle</h2>
      <ErrorBox error={action.error} />
      {job && (
        <div className="account-row">
          <Badge value={job.status} />
          <span>Investigation attempt {job.attempts} of 3</span>
          {editable && ["queued", "running"].includes(job.status) && (
            <Button
              variant="outline"
              disabled={action.isPending || job.cancel_requested}
              onClick={() => action.mutate({ path: `/jobs/${job.id}/cancel` })}
            >
              {job.cancel_requested
                ? "Cancellation requested"
                : "Cancel investigation"}
            </Button>
          )}
          {editable &&
            ["failed", "cancelled"].includes(job.status) &&
            job.attempts < 3 &&
            data.fix?.approval_status !== "approved" &&
            data.fix?.approval_status !== "rejected" && (
              <Button
                disabled={action.isPending}
                onClick={() => action.mutate({ path: `/jobs/${job.id}/retry` })}
              >
                Retry incomplete steps
              </Button>
            )}
        </div>
      )}
      {job?.cancel_requested && job.status === "running" && (
        <p>Cancellation takes effect after the current agent call returns.</p>
      )}
      {editable &&
        ["approved", "reopened", "resolved"].includes(data.status) && (
          <form
            className="account-form"
            onSubmit={(e) => {
              e.preventDefault();
              action.mutate({
                path: `/incidents/${data.id}/${data.status === "resolved" ? "reopen" : "resolve"}`,
                body:
                  data.status === "resolved" ? { note } : { note, evidence },
              });
            }}
          >
            <label htmlFor="resolution-note">
              {data.status === "resolved"
                ? "Reason for reopening"
                : "Resolution summary"}
            </label>
            <textarea
              id="resolution-note"
              required
              minLength={10}
              maxLength={2000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            {data.status !== "resolved" && (
              <>
                <label htmlFor="resolution-evidence">
                  Verification evidence
                </label>
                <textarea
                  id="resolution-evidence"
                  required
                  minLength={10}
                  maxLength={2000}
                  placeholder="CI run, deployment reference, and how recovery was confirmed"
                  value={evidence}
                  onChange={(e) => setEvidence(e.target.value)}
                />
                <p className="fine-print">
                  Your confirmation is recorded with this evidence. AutoRCA does
                  not independently verify deployment.
                </p>
              </>
            )}
            <Button disabled={action.isPending}>
              {data.status === "resolved"
                ? "Reopen incident"
                : "Confirm resolved"}
            </Button>
          </form>
        )}
      {data.audit?.map((event) => (
        <div className="memory-card" key={event.id}>
          <Badge value={event.action} />
          <strong> {event.actor}</strong>
          <small> · {date(event.created_at)}</small>
          <p>{event.note}</p>
          {event.evidence && <p>Evidence: {event.evidence}</p>}
        </div>
      ))}
    </section>
  );
}
