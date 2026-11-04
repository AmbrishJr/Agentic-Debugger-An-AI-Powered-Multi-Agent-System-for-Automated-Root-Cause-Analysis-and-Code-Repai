"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  FileCode2,
  FlaskConical,
  LockKeyhole,
  Play,
  ScanLine,
  ShieldCheck,
} from "lucide-react";
import { api, post } from "@/lib/api";
import { Incident, Settings } from "@/types";
import { Button } from "@/components/ui/button";
import { ErrorBox } from "@/components/common";
import { useAuth } from "@/components/auth";

type Sample = { title: string; error_log: string };
export default function NewInvestigation() {
  const { user } = useAuth();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [log, setLog] = useState("");
  const [mode, setMode] = useState<"demo" | "live">("demo");
  const [repository, setRepository] = useState("sample");
  const [files, setFiles] = useState<string[]>([]);
  const [autoLoaded, setAutoLoaded] = useState(false);
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("/settings"),
  });
  const samples = useQuery({
    queryKey: ["samples"],
    queryFn: () => api<{ items: Sample[] }>("/samples"),
  });
  const sourceFiles = useQuery({
    queryKey: ["files", repository],
    queryFn: () =>
      api<{ items: string[] }>(`/repositories/${repository}/files`),
  });
  function loadSample(sample: Sample) {
    setTitle(sample.title);
    setLog(sample.error_log);
    setMode("demo");
    setRepository("sample");
    setFiles(["checkout.py"]);
  }
  useEffect(() => {
    if (samples.data && !autoLoaded) {
      setAutoLoaded(true);
      if (new URLSearchParams(window.location.search).has("sample"))
        loadSample(samples.data.items[0]);
      else if (settings.data) setMode(settings.data.default_mode);
    }
  }, [samples.data, settings.data, autoLoaded]);
  const submit = useMutation({
    mutationFn: async () => {
      const incident = await post<Incident>("/incidents", {
        title,
        error_log: log,
        mode,
        repository,
        selected_files: files,
      });
      return incident;
    },
    onSuccess: (incident) =>
      router.push(`/investigations/${incident.id}?start=1`),
  });
  if (user?.role === "viewer") return <div className="panel panel-body"><h1>Read-only access</h1><p>An editor or administrator can start investigations. You can browse existing incidents and reports.</p></div>;
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">INVESTIGATE WITH CONTEXT</div>
          <h1>Let’s find the root cause.</h1>
          <p>Bring an error log. The agents will connect the evidence.</p>
        </div>
        <span className="header-icon">
          <ScanLine size={29} />
        </span>
      </div>
      <div className="form-layout">
        <form
          className="panel investigation-form"
          onSubmit={(e) => {
            e.preventDefault();
            submit.mutate();
          }}
        >
          <div className="panel-heading">
            <div>
              <h2>New investigation</h2>
              <p>Start with the failure you want to understand.</p>
            </div>
            <span className="step-label">01 / INPUT</span>
          </div>
          <div className="form-body">
            <ErrorBox
              error={
                submit.error ||
                settings.error ||
                samples.error ||
                sourceFiles.error
              }
            />
            <label htmlFor="title">Incident title</label>
            <input
              id="title"
              required
              minLength={3}
              maxLength={180}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Checkout fails when applying a discount"
            />
            <div className="label-row">
              <label htmlFor="log">Error log & stack trace</label>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={!samples.data}
                onClick={() =>
                  samples.data && loadSample(samples.data.items[0])
                }
              >
                <FlaskConical size={14} /> Load sample incident
              </Button>
            </div>
            <textarea
              id="log"
              className="code-input"
              required
              minLength={10}
              maxLength={50000}
              rows={12}
              value={log}
              onChange={(e) => setLog(e.target.value)}
              placeholder={
                'Paste your error log here…\n\nTraceback (most recent call last):\n  File "checkout.py", line 3, in calculate_discount\n    return price / discount\nZeroDivisionError: division by zero'
              }
            />
            <div className="field-hint">
              <span>Common secret patterns are redacted before storage.</span>
              <span>{log.length.toLocaleString()} / 50,000</span>
            </div>
            <div className="two-fields">
              <div>
                <label htmlFor="repository">Repository source</label>
                <select
                  id="repository"
                  value={repository}
                  onChange={(e) => {
                    setRepository(e.target.value);
                    setFiles([]);
                  }}
                >
                  <option value="sample">Bundled checkout application</option>
                  <option
                    value="local"
                    disabled={!settings.data?.local_repository_configured}
                  >
                    Configured local repository
                    {!settings.data?.local_repository_configured
                      ? " · not configured"
                      : ""}
                  </option>
                </select>
              </div>
              <div>
                <label htmlFor="mode">Investigation mode</label>
                <select
                  id="mode"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as "demo" | "live")}
                >
                  <option value="demo">Demo · deterministic</option>
                  <option
                    value="live"
                    disabled={!settings.data?.live_available}
                  >
                    Live AI · OpenAI
                    {!settings.data?.live_available ? " · key required" : ""}
                  </option>
                </select>
              </div>
            </div>
            <details className="file-picker">
              <summary>
                <FileCode2 size={15} /> Select additional evidence files{" "}
                <span>{files.length} selected</span>
              </summary>
              <div className="file-options">
                {sourceFiles.data?.items.map((path) => (
                  <label key={path}>
                    <input
                      type="checkbox"
                      checked={files.includes(path)}
                      disabled={!files.includes(path) && files.length >= 10}
                      onChange={(e) =>
                        setFiles(
                          e.target.checked
                            ? [...files, path]
                            : files.filter((f) => f !== path),
                        )
                      }
                    />
                    <span>{path}</span>
                  </label>
                ))}
              </div>
            </details>
            <div className="mode-notice">
              <FlaskConical size={17} />
              <p>
                {mode === "demo"
                  ? "Demo Mode uses predefined logic for the bundled incident. No LLM calls are made. Other inputs produce a limited evidence report."
                  : "Live AI sends redacted logs and selected source evidence to the configured OpenAI model. Review inputs before starting."}
              </p>
            </div>
          </div>
          <div className="form-footer">
            <span>
              <LockKeyhole size={14} /> Read-only investigation
            </span>
            <Button
              disabled={submit.isPending || !title.trim() || log.length < 10}
              type="submit"
            >
              <Play size={15} />
              {submit.isPending ? "Creating incident…" : "Start investigation"}
              <ArrowRight size={16} />
            </Button>
          </div>
        </form>
        <aside className="form-aside">
          <span className="aside-eyebrow">FROM SIGNAL TO SOLUTION</span>
          <h2>
            A clear path
            <br />
            through the noise.
          </h2>
          <p>
            Each agent has a focused job. Every conclusion comes back to
            evidence you can inspect.
          </p>
          <div className="vertical-steps">
            {[
              [
                "Understand",
                "Classify the error and identify the affected component.",
              ],
              [
                "Investigate",
                "Connect source evidence with similar past incidents.",
              ],
              [
                "Propose",
                "Explain the root cause and generate a minimal change.",
              ],
              [
                "Validate & review",
                "Inspect checks, compare the diff, and make the call.",
              ],
            ].map(([name, description], i) => (
              <div key={name}>
                <span>{i + 1}</span>
                <div>
                  <strong>{name}</strong>
                  <p>{description}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="safety-note">
            <ShieldCheck size={20} />
            <div>
              <strong>You stay in control.</strong>
              <p>
                Agents cannot modify your repository or deploy changes.
                Publishing a draft PR requires separate authorization.
              </p>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}
