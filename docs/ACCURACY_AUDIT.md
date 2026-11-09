# Accuracy audit — first upgrade

Audit date: 2026-11-10 (Asia/Kolkata). The supplied Agentic Debugger blueprint and upgrade prompt describe target behavior, not implementation evidence. This audit inspected the existing FastAPI/SQLAlchemy/LangGraph backend and Next.js frontend. No production integrations were exercised.

## Baseline evidence

Before changes: `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q` reported **75 passed, 10 skipped**; frontend `npm test` reported **4 passed**; `npm run typecheck` and `npm run build` passed. The local Python virtual environment is 3.10 although `backend/pyproject.toml` specifies 3.12–3.13. Cloud SDK and PostgreSQL coverage was skipped; local passes do not establish hosted compatibility.

| Capability | Initial classification | Inspected evidence and limitation |
| --- | --- | --- |
| Seven-stage diagnosis workflow | IMPLEMENTED | `backend/app/agents/workflow.py`: persisted stage outputs, errors, demo/live branches, bounded source selection. |
| Deterministic diagnosis | DEMO/MOCK | `workflow.is_sample`, `services/sample.py`: only the exact bundled discount incident receives a deterministic diagnosis and fix. Other demo incidents abstain. |
| Live structured diagnosis | PARTIAL | `services/llm.py`, `schemas/contracts.py`: OpenAI/Gemini structured outputs, failure handling, untrusted-data policy. Current verification uses provider mocks, not paid calls. |
| Source localization | PARTIAL | `workflow.evidence`, `services/security.py`: selected files and unambiguous stack-frame matches; bounded allowlisted reads. No symbol/call index or measured accuracy. |
| Revision provenance | PARTIAL | `api/routes.py:create_incident`, `services/github_source.py`: GitHub SHA pinning; local/sample sources rely on content hashes. |
| Evidence verification | PARTIAL | `workflow.analysis`: rejects unknown evidence IDs. Whole-file references do not establish the validity of free-text line claims or causal conclusions. |
| Competing hypotheses | PARTIAL | `schemas/contracts.py:Hypothesis`: support IDs, confidence labels and uncertainty exist; contradiction and independent diagnostic checks are not structured. |
| Patch construction and review | IMPLEMENTED | `workflow.fix`, `services/patches.py`, `api/routes.py:decide`: collected targets, original hashes, secret filtering, persisted decisions. Approval does not edit source. |
| Independent repair verification | PARTIAL | `services/validation.py`: exact host demo only. `validation_runs.py`, `sandbox.py`, `vercel_sandbox.py`: authorized snapshots and bounded before/after execution. Exit status alone did not establish expected failure or immutable tests. |
| Repair outcome vocabulary | MISSING | `passed/partial/failed/error` described checks, without the five independent repair outcomes. |
| Historical retrieval | PARTIAL | `services/memory.py`: FTS/BM25 and local concept/TF-IDF hybrid retrieval, review/resolution metadata. No measured retrieval gains or neural embeddings. |
| Durable orchestration | IMPLEMENTED | `services/jobs.py`, `cloud_jobs.py`, `cloud_workflows.py`: persisted checkpoints, retry/cancel, cloud dispatch ownership; hosted SDK tests unavailable locally. |
| Authentication and permissions | IMPLEMENTED | `services/auth.py`, API guards, `models/records.py`: users, sessions, roles, mutation protection, review authorization. Shared workspace, not tenant isolation. |
| Draft PR integration | IMPLEMENTED | `services/github.py`, authenticated API authorization: separate explicit action, version checks, no auto-merge. Transport mocked during this change. |
| Benchmark and adjudication | MISSING | No case dataset, denominator convention, or repeatable evaluation CLI existed. |
| Follow-up assistant/editor/telemetry integrations | MISSING | No implementation found in inspected routes and services; deferred. |

## Prioritized risks and reproducible checks

| Priority | Finding before this change | Risk | Reproduction / acceptance coverage |
| --- | --- | --- | --- |
| P0 | `validation_runs.prepare_plan` allowed patch/test overlap | A changed test can turn a failure into a pass without fixing behavior | Change a proposed target to `test_checkout.py`; planning must reject. Test directories, conftest and test configuration are protected too. |
| P0 | Before/after success inferred from process statuses | Unrelated baseline failures or passing tests can imply repair | Simulate passing baseline, arbitrary nonzero baseline, bad patched result, timeout and cleanup failure; none may earn VERIFIED. |
| P0 | Authorization checks lacked a second manifest/snapshot integrity check at execution | Queued content changes could invalidate reviewed consent | Queue an authorized run, alter snapshot/manifest/patch, execute worker; no runner call is allowed. |
| P0 | Old `passed` result conflated check success and proof | Misleading UI/API interpretation | Demo passes four checks but remains PATCH_UNVERIFIED through approval and report export. |
| P1 | Investigation page used initial workflow validation after later isolated runs | Stale presentation | Read latest fix validation and shared outcome in details, review and exported report. |
| P1 | No benchmark / denominator discipline | Unmeasured accuracy claims | Eight-case CLI separates demo/live and reviewed/unscored predictions; no host execution of additional fixture code. |
| Deferred P0 | Local revisions and causal citations remain incomplete | Stale source attribution / unsupported narrative | Future commit-aware source snapshots and line-level evidence verification; current VERIFIED scope stays restricted to exact bundled content. |

## Changes in this slice

A shared outcome resolver, protected test manifest, execution-time checks, narrowly scoped fixture proof, and an eight-case CLI now address the first six findings. See `IMPLEMENTATION_PROGRESS.md` for executed checks. `VERIFIED` remains intentionally unavailable for generic repository test suites. Test-output parsing is trusted only after every source/test byte matches the controlled fixture and its fixed counterpart.

No runtime claim is inferred from historical integration reports. The initial sandboxed Docker readiness check was denied socket access; an approved check outside that restriction found the configured pinned runner ready. All six executable reference fixtures subsequently reproduced failures and passed their reference patches in isolation, and the bundled proposed repair earned VERIFIED. Vercel execution and live model calls were not attempted. Existing `docs/security.md` user edits were preserved.

## Second slice: source grounding

Local commit plus content pinning and precise citation validation are now implemented for new incidents. Migration 005 preserves legacy rows without inventing provenance. The workflow checks collected source across analysis and patch stages; approval and initial publication check it again. Structured observations/hypotheses retain support, contradictions and diagnostic gaps. Malformed citations fail analysis; unsupported primary hypotheses abstain before fix generation.

The initial table above records the pre-upgrade audit. Remaining gaps include semantic claim verification, symbol/call indexing, broader independent verification, calibrated confidence and measured live-model accuracy. Snapshot coverage remains bounded, and local non-Git sources are content-pinned explicitly. See `source-grounding.md` and the second-slice checkpoint in `IMPLEMENTATION_PROGRESS.md`.
