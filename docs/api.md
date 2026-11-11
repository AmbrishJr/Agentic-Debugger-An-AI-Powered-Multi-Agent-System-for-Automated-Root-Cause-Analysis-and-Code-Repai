# API overview

FastAPI exposes OpenAPI at `/openapi.json` and interactive docs at `/docs`. JSON requests and responses use snake_case. List responses contain `items` and pagination metadata. Errors use `{"error":{"code":"...","message":"..."}}`; validation errors also include field names without echoing sensitive input.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/api/incidents` | Create with title, error_log, mode, repository, optional selected_files |
| GET | `/api/incidents` | Search `q`; filter severity/status; limit 1–100 and offset |
| GET | `/api/incidents/{id}` | Incident, investigation, agent outputs, proposed fix |
| POST | `/api/incidents/{id}/investigate` | Atomically claim a submitted incident; return 202 |
| GET | `/api/incidents/{id}/status` | Persisted status and agent execution list |
| GET | `/api/incidents/{id}/events` | SSE `progress` snapshots, heartbeat, terminal `complete` event |
| GET | `/api/incidents/{id}/report` | Structured report; review status read from the latest fix |
| GET | `/api/incidents/{id}/patch` | Original/proposed code, unified diff, validation and approval |
| POST | `/api/incidents/{id}/approve` | Immutable decision; accepts optional note |
| POST | `/api/incidents/{id}/reject` | Immutable decision; accepts optional note |
| POST | `/api/incidents/{id}/pull-request` | Requires approved patch and `{"authorized":true}` |
| GET | `/api/dashboard/stats` | Aggregated stored records, recent incidents, activity |
| GET | `/api/health` | Database connectivity and live-provider availability |
| GET | `/api/samples` | Labeled bundled deterministic example |
| GET | `/api/repositories` | Available source identifiers; no arbitrary browser-supplied root |
| GET | `/api/repositories/{source}/files` | Bounded allowlisted files |
| GET | `/api/repositories/{source}/file?path=...` | Read-only redacted contents |
| GET, PUT | `/api/settings` | Credential-free configuration and persisted preferences |
| GET | `/api/sandbox` | Runtime availability and fixed execution policy |
| POST | `/api/incidents/{id}/validation-plans` | Prepare a bounded immutable snapshot from `files` and optional `profile` (`python-unittest` or `python-pytest`) |
| GET | `/api/incidents/{id}/validation-runs` | Credential-free manifests, authorization, and results |
| POST | `/api/incidents/{id}/validation-runs/{run_id}/authorize` | Require `authorized: true` and the exact `plan_hash`; return 202 |
| POST | `/api/incidents/{id}/validation-runs/{run_id}/cleanup` | Retry destruction for a `cleanup_failed` run; never rerun tests |

All mutation requests require `Content-Type: application/json`, including empty `{}` bodies. Request bodies are limited to 100 KB; error logs to 50,000 characters and source files to 80 KB. If `AUTORCA_API_TOKEN` is configured, supply `X-AutoRCA-Token` from trusted server callers. The frontend proxy attaches its matching server-only token. Use loopback binding; workspace sessions and roles are enforced by default. Login with `/api/auth/login`; send its HttpOnly cookie and `X-CSRF-Token` on mutations. `/api/auth/me` returns the current session and CSRF token.

Incident transitions: `submitted → investigating → awaiting_review | needs_evidence | partial | failed`, then eligible review states may move to `approved | rejected`. An approval is a review decision, not proof of production resolution. Duplicate starts or decisions return 409. SSE connections are bounded and reconnectable snapshots, not an event journal.


| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/auth/me` | Session and initial-setup status; public |
| POST | `/api/auth/login` | Username/password; sets session cookie and returns CSRF token |
| POST | `/api/auth/logout` | Revokes current session |
| POST | `/api/auth/password` | Current/new password; revokes all sessions for this account |
| GET, POST | `/api/users` | Admin-only list/create accounts |
| PUT | `/api/users/{id}` | Admin-only role/active update; revokes affected sessions; retains last admin |
| POST | `/api/jobs/{id}/cancel` | Request boundary cancellation or immediately cancel a queued investigation |
| POST | `/api/jobs/{id}/retry` | Retry failed/cancelled unreviewed investigation, maximum three attempts |
| POST | `/api/incidents/{id}/resolve` | Approved/reopened → resolved; requires note and evidence, 10–2000 characters each |
| POST | `/api/incidents/{id}/reopen` | Resolved → reopened; requires reason in note |

Incident details include `jobs` and `audit`. Patch records include `files` (per-file snapshots, hashes, and diffs); legacy primary-file fields remain for compatibility. Admins manage accounts/settings; editors can mutate investigations and decisions; viewers can only read and manage their own session/password. All roles share the workspace. `/api/health`, `/api/auth/me`, and `/api/auth/login` do not require a session; the optional server API token remains independent. Initial administrator creation is local-only via `python -m app.manage`.


Provider configuration: `/api/settings` accepts `provider: "openai" | "gemini"` and the matching `model`. Its response includes credential-free `providers` availability/default-model records; `live_available` reflects the selected provider. Initial values come from `LLM_PROVIDER`, `OPENAI_MODEL`, and `GEMINI_MODEL`. Environment keys stay server-side. Investigation config and live reports identify their snapshotted provider/model. Gemini quota/access failures appear as safe agent errors; no provider fallback occurs.

## Repair outcomes (additive)

`GET /api/incidents/{id}`, `/patch`, and `/report` now return `repair_outcome`, independent of lifecycle, check execution and human approval. Incident detail also includes the same object inside `fix`. Existing status fields remain compatible.

```json
{"repair_outcome":{"status":"PATCH_UNVERIFIED","reasons":["Independent isolated proof is incomplete."],"validation_run_id":null}}
```

Statuses are `VERIFIED`, `PATCH_UNVERIFIED`, `NOT_REPRODUCED`, `VALIDATION_FAILED`, and `INSUFFICIENT_EVIDENCE`. Unassessed work returns null. Provider/workflow failure is not scored as evidence-based abstention. Explicit check/execution failures override non-reproduction; non-reproduction overrides incomplete proof. An active validation invalidates any prior positive conclusion until the new run finishes.

All views resolve the same latest stored artifacts. Historical `passed` checks are not promoted to VERIFIED. Only the exact controlled checkout fixture can currently qualify, after immutable independent tests reproduce the expected failure and pass all four regressions in authorized isolation. Generic repository test suites remain unverified even when red-to-green. Approval and draft-PR eligibility continue to follow the existing check/status gates and never alter this outcome.

Validation manifests add `role: "test" | "source"`. Test/config/support patch targets are rejected. Manifest, content, current source, patch and runner-policy checks run at authorization and execution. Persisted `isolated.proof` records scoped reproduction/regression booleans, test hash, source manifest, patch digest and environment separately from exit statuses. Legacy unconsumed plans without test roles require replanning; completed historical runs remain readable.

## Source snapshots and precise citations

New incidents include `repository_snapshot` (migration `005`) with a snapshot ID, capture kind, repository-binding digest, optional commit SHA, bounded path/SHA-256 manifest, and coverage description. Local Git sources pin HEAD plus captured working-tree bytes; `modified: true` means captured files differ from that commit. The flag is scoped to captured files, not the entire Git repository. Non-Git folders, unborn repositories and bundled fixtures use an explicitly labeled content snapshot without an invented commit. GitHub continues to use its pinned commit.

Local/sample file reads during investigation, validation and review use incident-scoped references (`local@{incident_id}` / `sample@{incident_id}`). The configured root, current HEAD and requested file hash must match the captured values. Stale evidence blocks analysis/patch generation and approval. The source snapshot is never silently refreshed on retry. Existing historical incidents retain an empty manifest and are not relabeled as revision-pinned.

Source evidence adds `content_sha256` (the redacted text), `snapshot_id` and nullable `commit_sha` while retaining `sha256` for original bytes. Source redaction preserves line numbers, including multiline private keys. Citations carry:

```json
{
  "evidence_id": "E2",
  "kind": "source",
  "path": "checkout.py",
  "line_start": 3,
  "line_end": 3,
  "quote": "    return price / discount",
  "sha256": "original-file-sha256",
  "snapshot_id": "captured-snapshot-sha256",
  "commit_sha": null
}
```

Hash examples above are placeholders; real references require 64-character SHA-256 values. The backend validates identity, path, original hash, snapshot/revision, redacted-content integrity, bounded line range (1–50 lines), and the exact full quoted lines. Quotes preserve indentation and join lines with LF. Log citations use the saved redacted log digest as snapshot ID and a null commit SHA.

Analysis adds citation-backed `observations`, at most three hypotheses with `supporting_evidence`, `contradicting_evidence`, `missing_checks`, and `disposition: supported | insufficient_evidence`. Compatibility `observed_facts` and `evidence_ids` are derived from validated structured references. Uncited factual claims are not retained as observations. Invalid references fail the analysis stage. Missing support or unresolved primary-hypothesis checks/contradictions force insufficient evidence and prevent patch generation. A code patch additionally requires both source and log support.

`citation_validation` records a checked-reference count and reports `no_citations` when that count is zero; an empty reference list is never labeled validated. It describes quotation/provenance checks only. It does not prove that the quoted code caused the incident or that a model's interpretation is true. Historical analysis is shown as legacy, without a claim that precise citations were validated.

## Source retrieval metadata

`GET, PUT /api/settings` includes `source_retrieval: "symbols" | "stack"`, defaulting to `symbols` for new investigations. It is snapshotted in investigation config separately from historical `retrieval_mode`. Old investigation configs without the field use `stack` when resumed.

Evidence adds a `retrieval` object. Source items include `strategy`, one-based `rank`, selection `reasons`, and up to 20 `symbols` with `name`, `kind`, `line_start`, and `line_end`. The log item holds the summary: `strategy`, nullable `parser_version`, `cache_hit`, `indexed_files`, `skipped_count`, up to ten `skipped` path/reason entries, `index_limited`, `notices`, and `limitations`. Downloaded reports expose this summary as `source_retrieval` and preserve per-file metadata in `evidence`.

Metadata describes bounded static retrieval, not proof of a root cause. No extra endpoints or schema migration are added. Existing source hashes/citations, file limits, repair outcomes and authorization checks remain in force. [Operational bounds and fallback behavior](source-retrieval.md) describe the Python-only scope.

## Reviewed verification specifications

`POST /api/incidents/{id}/validation-plans` optionally accepts `verification_spec` for the unittest profile. Version 1 requires `reviewed: true`, a rationale, `reproduction: [{test_id, expected_exception}]`, and `regressions: [test_id]`. IDs identify directly declared `module.Class.test_method` methods in selected test files pinned by the incident. The authenticated reviewer and review time are assigned server-side; clients cannot supply a reviewer identity.

The plan's `result.verification_spec` binds the declaration to the incident snapshot and test hashes. It is included in the one-use authorization hash and rechecked before execution. `result.specification_assessment` records `matched`, `not_reproduced`, `mismatch`, or `inconclusive`, per-test observations and `independent_proof: false`. Mismatches and incomplete required observations fail validation; matches do not broaden VERIFIED eligibility. Incident/patch/report responses retain these artifacts through the existing latest-validation fields. Specifications are preserved after interruption and snapshot-body cleanup.

Existing requests without specifications retain their behavior; pytest specifications are rejected while ordinary pytest execution remains supported. See [request example, outcome rules and limits](verification-specifications.md).

## Controller-owned JSON contracts

Validation plans additionally accept `profile: "python-json-stdio"` with a required `json_contract` (mutually exclusive with unittest specifications). The contract contains `version: 1`, `reviewed: true`, `entrypoint`, `rationale`, and 2–4 `{id, role, input, baseline, expected}` cases. Include both reproduction and regression roles; select source-only Python files. This profile currently requires Docker.

The bound artifact uses `result.verification_spec.kind: "json-stdio"`. Its assessment uses `comparison: "controller-json-equality-v1"` and preserves actual process results under `cases[].before/after`. The enclosing before/after fields represent semantic contract comparisons with null exit codes, explicitly labeled `measurement: "contract_comparison"`. Expected values never enter the candidate execution payload. Matches do not broaden VERIFIED eligibility. [Full schema example, comparison rules and limits](json-behavior-contracts.md).
