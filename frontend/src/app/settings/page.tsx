"use client";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Check,
  Database,
  GitBranch,
  LockKeyhole,
  Save,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { Settings } from "@/types";
import { Button } from "@/components/ui/button";
import { ErrorBox, Loading } from "@/components/common";
import { UserManagement, useAuth } from "@/components/auth";
export default function SettingsPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const { data, error, isPending } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("/settings"),
  });
  const [form, setForm] = useState({
    model: "",
    provider: "openai" as "openai" | "gemini",
    retrieval_limit: 5,
    retrieval_mode: "hybrid" as "keyword" | "hybrid",
    max_evidence_files: 5,
    default_mode: "demo" as "demo" | "live",
  });
  useEffect(() => {
    if (data)
      setForm({
        model: data.model,
        provider: data.provider,
        retrieval_limit: data.retrieval_limit,
        retrieval_mode: data.retrieval_mode,
        max_evidence_files: data.max_evidence_files,
        default_mode: data.default_mode,
      });
  }, [data]);
  const save = useMutation({
    mutationFn: () =>
      api<Settings>("/settings", { method: "PUT", body: JSON.stringify(form) }),
    onSuccess: (result) => client.setQueryData(["settings"], result),
  });
  if (isPending) return <Loading />;
  const selectedProvider = data?.providers.find((p) => p.id === form.provider);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">MAKE THE WORKSPACE YOURS</div>
          <h1>Configuration, with clear boundaries.</h1>
          <p>Configure the agents. Keep credentials on the server.</p>
        </div>
        <Settings2 size={29} className="muted" />
      </div>
      <ErrorBox error={error || save.error} />
      {data && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="settings-grid">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>AI provider</h2>
                  <p>Structured responses from your selected provider</p>
                </div>
                <Bot size={22} />
              </div>
              <div className="panel-body">
                <label htmlFor="provider">AI provider</label>
                <select
                  id="provider"
                  value={form.provider}
                  onChange={(e) => {
                    const provider = e.target.value as "openai" | "gemini";
                    const option = data.providers.find(
                      (p) => p.id === provider,
                    )!;
                    setForm({
                      ...form,
                      provider,
                      model: option.default_model,
                      default_mode: option.available
                        ? form.default_mode
                        : "demo",
                    });
                  }}
                >
                  {data.providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <div className="connection-row">
                  <span>{selectedProvider?.name} API key</span>
                  <span
                    className={`connection ${selectedProvider?.available ? "connected" : ""}`}
                  >
                    {selectedProvider?.available
                      ? "Configured"
                      : "Not configured"}
                  </span>
                </div>
                <label htmlFor="retrieval-mode">Incident retrieval</label>
                <select
                  id="retrieval-mode"
                  value={form.retrieval_mode}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      retrieval_mode: e.target.value as "keyword" | "hybrid",
                    })
                  }
                >
                  <option value="hybrid">
                    Hybrid keyword + concept vectors
                  </option>
                  <option value="keyword">Keyword only</option>
                </select>
                <label htmlFor="model">Model</label>
                <input
                  id="model"
                  required
                  pattern="[a-zA-Z0-9._:\-]+"
                  maxLength={100}
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                />
                <p className="field-hint">
                  Use a model available to your account that supports structured
                  outputs.
                </p>
                <label htmlFor="default-mode">Default investigation mode</label>
                <select
                  id="default-mode"
                  value={form.default_mode}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      default_mode: e.target.value as "demo" | "live",
                    })
                  }
                >
                  <option value="demo">
                    Demo · deterministic, no API calls
                  </option>
                  <option value="live" disabled={!selectedProvider?.available}>
                    Live AI · {selectedProvider?.name}
                  </option>
                </select>
                <p className="fine-print">
                  Set{" "}
                  {form.provider === "gemini"
                    ? "GEMINI_API_KEY"
                    : "OPENAI_API_KEY"}{" "}
                  in the root .env file and restart the backend. The browser
                  never receives the key.
                </p>
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Evidence & retrieval</h2>
                  <p>Control the investigation context</p>
                </div>
                <Database size={21} />
              </div>
              <div className="panel-body">
                <div className="connection-row">
                  <span>Memory engine</span>
                  <span className="connection connected">SQLite FTS5</span>
                </div>
                <label htmlFor="retrieval">Maximum historical matches</label>
                <input
                  id="retrieval"
                  type="number"
                  min={1}
                  max={10}
                  value={form.retrieval_limit}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      retrieval_limit: Number(e.target.value),
                    })
                  }
                />
                <label htmlFor="evidence-limit">Maximum evidence files</label>
                <input
                  id="evidence-limit"
                  type="number"
                  min={1}
                  max={10}
                  value={form.max_evidence_files}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      max_evidence_files: Number(e.target.value),
                    })
                  }
                />
                <p className="fine-print">
                  Keyword matching uses BM25 ranking. Evidence is limited to
                  allowlisted text files of up to 80 KB each. Settings apply to
                  new investigations.
                </p>
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>GitHub integration</h2>
                  <p>Explicitly authorized draft pull requests</p>
                </div>
                <GitBranch size={21} />
              </div>
              <div className="panel-body">
                <div className="connection-row">
                  <span>Fine-grained access token</span>
                  <span
                    className={`connection ${data.github_configured ? "connected" : ""}`}
                  >
                    {data.github_configured ? "Configured" : "Not configured"}
                  </span>
                </div>
                <div className="connection-row">
                  <span>Local source repository</span>
                  <span
                    className={`connection ${data.local_repository_configured ? "connected" : ""}`}
                  >
                    {data.local_repository_configured
                      ? "Configured"
                      : "Not configured"}
                  </span>
                </div>
                {data.github_repository && (
                  <p className="mono">{data.github_repository}</p>
                )}
                <p className="fine-print">
                  Configure GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_BASE_BRANCH,
                  in the backend environment. Local development can also use REPOSITORY_ROOT. The reviewed
                  file must match the GitHub base version before publishing.
                </p>
              </div>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Validation boundaries</h2>
                  <p>Honest results, explicit limitations</p>
                </div>
                <ShieldCheck size={22} />
              </div>
              <div className="panel-body">
                <div className="safety-check">
                  <Check size={16} /> Trusted demo regression tests
                </div>
                <div className="safety-check">
                  <Check size={16} /> Source version and Python syntax checks
                </div>
                <div className="safety-check">
                  <LockKeyhole size={16} /> Host execution of repository code
                  disabled
                </div>
                <p className="fine-print">
                  {data.sandbox_available
                    ? "The isolated runner is configured. Prepare a source snapshot and authorize its test plan in the fix review screen."
                    : "The isolated runner is unavailable. Repository tests remain skipped until it is configured and a test plan is authorized."}{" "}
                  See docs/sandbox.md for setup, resource limits, and the
                  isolation boundary.
                </p>
              </div>
            </section>
          </div>
          <div className="settings-footer">
            <span role="status">
              {save.isSuccess
                ? "Configuration saved. New investigations will use these settings."
                : "Credentials are managed only through backend environment variables."}
            </span>
            <Button
              type="submit"
              disabled={save.isPending || user?.role !== "admin"}
            >
              <Save size={16} />
              {save.isPending ? "Saving…" : "Save configuration"}
            </Button>
          </div>
        </form>
      )}
      <UserManagement />
    </>
  );
}
