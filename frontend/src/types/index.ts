export type Incident = {
  id: string;
  title: string;
  error_log: string;
  severity: string;
  status: string;
  mode: "demo" | "live";
  repository: string;
  created_at: string;
  updated_at: string;
};
export type Evidence = {
  id: string;
  kind: string;
  path: string;
  line_start: number;
  line_end: number;
  content: string;
  sha256: string;
};
export type Analysis = {
  summary: string;
  observed_facts: string[];
  hypotheses: {
    title: string;
    explanation: string;
    confidence: string;
    evidence_ids: string[];
    uncertainty: string;
  }[];
};
export type Validation = {
  status: string;
  checks: { name: string; status: string; detail: string }[];
  limitations: string;
  fixture?: {
    before: { passed: boolean; output: string };
    after: { passed: boolean; output: string };
  };
};
export type Fix = {
  files: {
    path: string;
    original_code: string;
    proposed_code: string;
    diff: string;
  }[];
  id: string;
  path: string;
  original_code: string;
  proposed_code: string;
  proposed_patch: string;
  explanation: string;
  risks: string[];
  validation_result: Validation;
  approval_status: string;
  decision_note: string;
  decided_at: string | null;
  pr_url: string | null;
  pr_status: string;
};
export type Execution = {
  id: string;
  agent_name: string;
  execution_status: string;
  duration: number;
  output_summary: Record<string, unknown>;
  error_details: string | null;
};
export type Report = {
  summary: string;
  risk_assessment: string;
  next_steps: string[];
  approval_status: string;
};
export type Results = {
  triage?: { exception: string; service: string; message: string };
  evidence?: Evidence[];
  analysis?: Analysis;
  validation?: Validation;
  report?: Report;
  memory?: {
    incident_id: string;
    root_cause: string;
    resolution_summary: string;
    retrieval: string;
  }[];
  errors?: { agent: string; message: string }[];
  fix?: { available: boolean; reason?: string };
};
export type Detail = Incident & {
  jobs: {
    id: string;
    kind: string;
    status: string;
    attempts: number;
    cancel_requested: boolean;
    error: string | null;
  }[];
  audit: {
    id: string;
    action: string;
    actor: string;
    note: string;
    evidence: string;
    created_at: string;
  }[];
  investigation: { agent_status: string; analysis_results: Results } | null;
  executions: Execution[];
  fix: Fix | null;
};
export type Settings = {
  retrieval_mode: "keyword" | "hybrid";
  model: string;
  retrieval_limit: number;
  max_evidence_files: number;
  default_mode: "demo" | "live";
  provider: "openai" | "gemini";
  providers: {
    id: "openai" | "gemini";
    name: string;
    available: boolean;
    default_model: string;
  }[];
  live_available: boolean;
  github_configured: boolean;
  github_repository: string;
  local_repository_configured: boolean;
  sandbox_available: boolean;
};
export type Stats = {
  total: number;
  open: number;
  resolved: number;
  approved: number;
  pending_approvals: number;
  success_rate: number | null;
  demo_count: number;
  recent: Incident[];
  severity: { name: string; value: number }[];
  activity: { id: string; title: string; status: string; time: string }[];
  note: string;
};
