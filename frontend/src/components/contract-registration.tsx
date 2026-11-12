"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post } from "@/lib/api";
import { useAuth } from "./auth";
import { Button } from "./ui/button";
import { ErrorBox } from "./common";
import type { RegisteredContract } from "@/types";

export function ContractRegistration({ id, status }: { id: string; status: string }) {
  const { user, enabled } = useAuth();
  const client = useQueryClient();
  const [files, setFiles] = useState("");
  const [contract, setContract] = useState("");
  const [rationale, setRationale] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const query = useQuery({ queryKey: ["contract-registration", id], queryFn: () => api<RegisteredContract>(`/incidents/${id}/verification-contract`),
    refetchInterval: status === "submitted" ? 3000 : false });
  const refresh = () => { setConfirmed(false); void client.invalidateQueries({ queryKey: ["contract-registration", id] }); void client.invalidateQueries({ queryKey: ["incident", id] }); };
  const register = useMutation({ mutationFn: () => {
    let value;
    try { value = JSON.parse(contract); } catch { throw new Error("Enter valid JSON for the contract."); }
    if (!value || Array.isArray(value) || typeof value !== "object") throw new Error("The contract must be a JSON object.");
    return post(`/incidents/${id}/verification-contract`, { files: files.split("\n").map((p) => p.trim()).filter(Boolean),
      contract: { ...value, version: 1, reviewed: true } });
  }, onSuccess: refresh });
  const review = useMutation({ mutationFn: () => post(`/incidents/${id}/verification-contract/review`, {
    registration_sha256: query.data!.registration!.sha256, reviewed: true, rationale,
  }), onSuccess: refresh });
  const registration = query.data?.registration;
  if (status !== "submitted" && !registration && !query.error) return null;
  return <section className="panel panel-body">
    <h3>Contract provenance before investigation</h3>
    <ErrorBox error={query.error || register.error || review.error} />
    {!registration && status === "submitted" && <>
      <p>Optionally register a JSON behavior contract before generating a patch. A different authenticated account must review it before investigation starts. Registered contracts cannot be edited; changes require a new incident.</p>
      {enabled && user?.role !== "viewer" ? <details><summary>Register an immutable JSON contract</summary>
        <label htmlFor="registered-source-files">Registered source files</label>
        <textarea id="registered-source-files" rows={3} value={files} placeholder={"main.py\nlogic.py"} onChange={(e) => { setFiles(e.target.value); setConfirmed(false); }} />
        <p className="fine-print">One pinned Python source path per line. Include the entrypoint and all dependencies; exclude tests.</p>
        <label htmlFor="registered-json">Contract to register</label>
        <textarea id="registered-json" rows={10} value={contract} placeholder={'{"entrypoint":"main.py","rationale":"Explain the incident","cases":[{"id":"bug","role":"reproduction","input":2,"baseline":1,"expected":3},{"id":"zero","role":"regression","input":0,"baseline":0,"expected":0}]}'} onChange={(e) => { setContract(e.target.value); setConfirmed(false); }} />
        <label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I reviewed the contract and understand it will be immutable.</label>
        <Button disabled={!confirmed || register.isPending} onClick={() => register.mutate()}>Register contract</Button>
      </details> : <p className="fine-print">An authenticated editor or administrator account is required to register a contract.</p>}
    </>}
    {registration && <>
      <p>Registered by {registration.actor.username} · {new Date(registration.created_at).toLocaleString()}</p>
      <p className="fine-print">Contract SHA-256: {registration.sha256}</p>
      <details><summary>Inspect registered inputs, answers, and source hashes</summary><pre>{JSON.stringify({ contract: registration.declaration, sources: registration.source_hashes }, null, 2)}</pre></details>
      {query.data?.review ? <p>Reviewed by {query.data.review.actor.username}: {query.data.review.rationale}</p> : <>
        <p>A different account must review this exact contract before investigation can start.</p>
        {status === "submitted" && enabled && user?.role !== "viewer" && user?.id !== registration.actor.id && <>
          <label htmlFor="contract-review-rationale">Independent review rationale</label>
          <textarea id="contract-review-rationale" rows={3} minLength={10} maxLength={1000} value={rationale} onChange={(e) => { setRationale(e.target.value); setConfirmed(false); }} />
          <label className="checkbox-label"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I reviewed these answers and their relevance to the incident.</label>
          <Button disabled={!confirmed || rationale.trim().length < 10 || review.isPending} onClick={() => review.mutate()}>Record separate-account review</Button>
        </>}
      </>}
      <p className="fine-print">Two accounts establish recorded process separation, not separate human identities. Successful verification covers only the registered cases; it does not prove diagnosis causality or all program behavior.</p>
    </>}
  </section>;
}
