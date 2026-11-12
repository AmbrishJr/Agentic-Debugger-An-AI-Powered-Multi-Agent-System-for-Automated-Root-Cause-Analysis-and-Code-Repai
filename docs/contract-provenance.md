# Contract provenance and scoped verification

A Python JSON repair can now earn VERIFIED against a contract registered **before investigation starts**, reviewed by a different authenticated account, and then satisfied in authorized isolation. This is a narrow process and behavior guarantee: verification covers the registered inputs and regressions, not all possible behavior or the causal truth of the diagnosis.

Ordinary repository unittest/pytest output and ad hoc JSON contracts retain their conservative outcomes. Historical records are not backfilled or promoted. The existing exact bundled checkout fixture retains its own proof gate.

## Workflow

1. On the new-investigation form, choose **Save incident first to register a JSON contract for separate-account review**. This captures the source snapshot without starting agents.
2. On the saved incident, register the source paths and JSON contract. Include the entrypoint and its Python source dependencies. Registration freezes the expected answers, known baseline outputs, incident-log hash, source hashes, author account and timestamp.
3. A different authenticated editor/administrator signs in, inspects the exact declaration and hashes, and records a review rationale addressing incident relevance and regression coverage. The author cannot review their own registration. Viewer accounts and authentication-disabled local mode cannot supply provenance.
4. Start investigation. Registration, review and startup share a database lock, preventing late registration or review from racing with patch generation. Startup is blocked while a registered contract lacks its separate-account review. The investigation stores only references/hashes and a lock timestamp, never contract answers in its model inputs.
5. After a proposal exists, choose the JSON profile and **Use the immutable contract reviewed before investigation**. The backend loads the registered declaration and requires exactly its registered source set. Review the resulting plan and separately authorize execution through the existing one-use consent flow.
6. Every reproduction case must return its declared incorrect value before the patch and its expected value afterward; regressions must match before and after. All execution, output, policy, source, patch and cleanup checks must pass. The controller re-evaluates saved JSON observations when resolving the outcome, rather than trusting a stored `matched` flag.

Registration and review cannot be amended, replaced or deleted through the API. To change a contract, abandon that incident and submit a new one. Completed and retried investigations cannot acquire new provenance retroactively. Accounts share the existing workspace; contract answers remain inspectable by authorized workspace users even though they are excluded from model/execution payloads.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/incidents/{id}/verification-contract` | Return the registration and review, or null values |
| POST | `/api/incidents/{id}/verification-contract` | Register `{files, contract}` before investigation; `contract` uses the existing JSON contract schema |
| POST | `/api/incidents/{id}/verification-contract/review` | Record `{registration_sha256, reviewed: true, rationale}` from a different authenticated account |

Actor IDs, usernames, roles and timestamps are assigned by the server. Clients cannot supply actor identity. Existing session, CSRF and workspace-role controls apply. A review must reference the exact registration hash. Duplicate registrations/reviews and lifecycle violations return validation errors without changing records.

Use a registered contract when planning execution:

```json
{
  "files": ["main.py", "logic.py"],
  "profile": "python-json-stdio",
  "registered_contract_sha256": "64-character-hash-returned-by-registration"
}
```

The hash above is a placeholder. Do not also provide an ad hoc `json_contract`; those options are mutually exclusive. Existing requests without the new reference continue to work and do not gain registered-contract proof.

## Records and proof checks

The existing `incident_events` table stores append-only registration/review events with canonical JSON evidence and content hashes. No database migration is added. `Investigation.config.verification_contract` freezes registration/review IDs, hashes, policy and the timestamp at which investigation started. Expected values stay out of investigation state/evidence and candidate execution.

The validation plan's specification includes this provenance binding. Authorization, worker startup and completion validate it against the original ledger, incident snapshot/log, review and source manifest. Changed/missing/duplicate records, same-account review, absent or changed investigation binding, changed source sets and altered plans cannot qualify. Snapshot bodies are still removed after execution while audit records, declarations, hashes and observations remain.

The outcome resolver checks both current saved provenance and the saved run: correct incident/fix IDs, completed authorized status, plan/patch hashes, matching validation artifact, and every actual JSON response/exit/cleanup result. It recognizes `proof.version: 2` with `scope: "registered-json-contract-v1"`. Reproduction, regression and environment checks are still required; registration or human patch approval alone cannot grant VERIFIED. Running validation invalidates an earlier positive outcome until completion.

Incident details, patch responses and report downloads use the same resolver and expose the same scoped reason and run reference. Registry IDs/hashes in the exported specification link back to the immutable author/reviewer records. The low-level comparison assessment retains `independent_proof: false`: the comparison alone is not sufficient; the resolver combines it with registered provenance, authorization and integrity evidence.

## Trust boundary and compatibility

This policy establishes **separate authenticated accounts** and sequencing before application-generated patches. It cannot prove those accounts belong to different humans, prevent collusion, or prove a reviewer interpreted the incident correctly. Administrative database access is trusted: hashes detect inconsistent/tampered artifacts, but the ledger is not an external signature service or an independently secured audit log. A privileged database administrator can rewrite stored history. This limitation also applies to the application's existing approvals and run records.

Verification is finite behavioral coverage under the pinned source and runner policy. It does not prove diagnosis causality, production readiness, safety of untested paths, or model accuracy. It does not deploy anything. JSON contracts still support Python CLI interfaces on Docker only; all earlier resource, secret, output and isolation bounds apply.

Local authentication-disabled development can continue using ordinary/ad hoc validation, but cannot register an independent account identity. No existing users or roles are changed. New provenance is opt-in. Rollback preserves audit/result JSON; older code cannot grant the new scope and registered pending plans must be recreated. Avoid mixing old/new application versions during this workflow because older code does not enforce the pre-investigation review gate.

## Reproduce the integration check

```bash
backend/.venv/bin/python scripts/validate_contract_provenance.py --execute
```

This uses a disposable database, temporary source tree, two synthetic accounts, the actual registration/review/start/plan/authorization/report/approval APIs and the existing immutable Docker runner. The demo workflow intentionally abstains on the generic incident; a known reference proposal is seeded **after** registration, review and investigation. The artifact explicitly labels that proposal as synthetic reference data, not model output or an accuracy benchmark. Four fresh container invocations test reproduction and regression behavior.

The ignored artifact is `data/evaluations/registered-contract-isolated.json`. Unavailable isolation is recorded as skipped, with no host fallback or installation. No provider calls, external publication or production-database changes occur. See the sixth checkpoint in [implementation progress](IMPLEMENTATION_PROGRESS.md) for actual results and remaining upgrades.
