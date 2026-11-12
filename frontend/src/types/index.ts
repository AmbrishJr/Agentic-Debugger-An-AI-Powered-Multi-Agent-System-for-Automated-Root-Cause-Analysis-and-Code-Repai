export type RepositorySnapshot = {
  version?: number;
  kind?: string;
  commit_sha?: string | null;
  snapshot_id?: string;
  modified?: boolean | null;
  coverage?: string;
  files?: Record<string, string>;
};
export type Citation = {
  evidence_id: string;
  kind: "source" | "log";
  path: string;
  line_start: number;
  line_end: number;
  quote: string;
  sha256: string;
  snapshot_id: string;
  commit_sha: string | null;
};
export type RepairOutcome = {
  status: "VERIFIED" | "PATCH_UNVERIFIED" | "NOT_REPRODUCED" | "VALIDATION_FAILED" | "INSUFFICIENT_EVIDENCE";
  reasons: string[];
  validation_run_id: string | null;
};
export type Incident = {
  id: string;
  title: string;
  error_log: string;
  severity: string;
  status: string;
  mode: "demo" | "live";
  repository: string;
  repository_commit?: string;
  repository_snapshot?: RepositorySnapshot;
  created_at: string;
  updated_at: string;
};
export type VerificationSpecification = {
  version: 1;
  reviewed: true;
  rationale: string;
  reproduction: { test_id: string; expected_exception: string }[];
  regressions: string[];
};
export type BoundVerificationSpecification = {
  kind?: "unittest";
  declaration: VerificationSpecification;
  reviewer: string;
  reviewed_at: string;
  snapshot_id: string;
  tests: { test_id: string; path: string; sha256: string }[];
  independence: string;
  limitations: string;
};
export type JsonContract = {
  version: 1; reviewed: true; entrypoint: string; rationale: string;
  cases: { id: string; role: "reproduction" | "regression"; input: unknown; baseline: unknown; expected: unknown }[];
};
export type BoundJsonContract = {
  kind: "json-stdio"; declaration: JsonContract; reviewer: string; reviewed_at: string;
  snapshot_id: string; source_hashes: Record<string, string>; oracle_version: number; limitations: string;
  provenance?: { policy: string; registration_id: string; registration_sha256: string; review_id: string; review_sha256: string; locked_at: string };
};
export type RegisteredContract = {
  registration: { id: string; sha256: string; actor: { id: string; username: string }; created_at: string;
    source_hashes: Record<string, string>; declaration: JsonContract } | null;
  review: { id: string; sha256: string; actor: { id: string; username: string }; created_at: string; rationale: string } | null;
};
export type SpecificationAssessment = {
  status: "matched" | "not_reproduced" | "mismatch" | "inconclusive";
  independent_proof: false;
  limitations: string;
  reasons: string[];
  reproduction?: { test_id: string; expected_exception: string; observed_match: boolean }[];
  regressions?: { test_id: string; observed_pass: boolean }[];
  cases?: { id: string; role: string; before_matches_baseline?: boolean; after_matches_expected?: boolean }[];
};
export type SourceRetrieval = {
  strategy?: "stack" | "symbols";
  rank?: number;
  reasons?: string[];
  symbols?: { name: string; kind: string; line_start: number; line_end: number }[];
  indexed_files?: number;
  skipped_count?: number;
  index_limited?: boolean;
  cache_hit?: boolean;
  limitations?: string;
  notices?: string[];
};
export type Evidence = {
  retrieval?: SourceRetrieval;
  id: string;
  kind: string;
  path: string;
  line_start: number;
  line_end: number;
  content: string;
  sha256: string;
  content_sha256?: string;
  snapshot_id?: string;
  commit_sha?: string | null;
};
export type Analysis = {
  disposition?: "supported" | "insufficient_evidence";
  observations?: { statement: string; citations: Citation[] }[];
  citation_validation?: { version: number; status: string; limitation: string };
  summary: string;
  observed_facts: string[];
  hypotheses: {
    title: string;
    explanation: string;
    confidence: string;
    evidence_ids: string[];
    uncertainty: string;
    supporting_evidence?: Citation[];
    contradicting_evidence?: Citation[];
    missing_checks?: string[];
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
  repair_outcome?: RepairOutcome | null;
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
  repair_outcome?: RepairOutcome | null;
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
  repair_outcome?: RepairOutcome | null;
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
  source_retrieval: "stack" | "symbols";
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
