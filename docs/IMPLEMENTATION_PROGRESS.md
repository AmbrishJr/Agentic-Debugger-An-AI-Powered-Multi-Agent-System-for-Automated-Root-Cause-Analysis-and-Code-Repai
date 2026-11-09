# First upgrade checkpoint

Date: 2026-11-10 (Asia/Kolkata). Implemented measurement and conservative repair outcomes in the existing application. No production database migration, publication, deployment, or live provider call was performed. The pre-existing edit to `docs/security.md` is preserved.

## Delivered behavior

- One typed backend resolver supplies consistent additive repair outcomes to incident details, patch responses and exported reports. The frontend separates repair conclusions from check results and approval. Historical passed results remain unverified; queued work and provider failures are not mislabeled as evidence-based abstention.
- Test/config/support targets are rejected for isolated validation. Authorized manifests freeze roles and content hashes. The worker rechecks manifest, snapshot, patch, live source, policy and expiry before executing. Proof artifacts retain independent-test identity, expected reproduction, regressions, environment and integrity separately from exit codes.
- VERIFIED is restricted to exact controlled checkout source, fixed code and independently pinned tests under the unittest profile in authorized isolation. Generic red-to-green runs remain unverified. The existing host demo remains available and clearly labeled.
- An offline-first CLI runs eight versioned synthetic cases through the production pipeline in a disposable database. Oracle answers/reference patches/independent tests are not passed to models. Reviewed RCA decisions bind to prediction hashes. JSON/Markdown retain provenance, predictions, authorization manifests, validation outputs, metrics, failures and exclusions.

## Changed files

Backend/API: `backend/app/api/routes.py`, `backend/app/schemas/contracts.py`, `backend/app/services/repair_outcomes.py`, `backend/app/services/validation_runs.py`.

Evaluation: `backend/app/evaluation/__init__.py`, `backend/app/evaluation/contracts.py`, `backend/app/evaluation/metrics.py`, `backend/app/evaluation/runner.py`; `scripts/evaluate.py`; `benchmarks/v1/inputs.json`, `benchmarks/v1/oracles.json`, `benchmarks/README.md`.

Frontend: `frontend/src/types/index.ts`, `frontend/src/components/common.tsx`, `frontend/src/app/investigations/[id]/page.tsx`, `frontend/src/app/investigations/[id]/review/page.tsx`.

Tests: `backend/tests/test_repair_outcomes.py`, `backend/tests/test_evaluation.py`, `frontend/src/components/common.test.tsx`, `frontend/e2e/demo.spec.ts`, `frontend/e2e/sandbox.spec.ts`.

Documentation: `README.md`, `docs/ACCURACY_AUDIT.md`, `docs/api.md`, `docs/sandbox.md`, this checkpoint. No new environment variables. Build-generated `frontend/next-env.d.ts` changes were restored.

## Executed verification

| Command | Result |
| --- | --- |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q` | **104 passed, 10 skipped**, 2 existing deprecation warnings. |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_evaluation.py -q` | **6 passed** after adding full validation artifact retention. |
| `cd frontend && npm test` | **10 passed**. |
| `cd frontend && npm run typecheck` | Passed, including final recheck. |
| `cd frontend && npm run build` | Passed production build. |
| `cd frontend && npm run test:e2e` | **5 passed, 1 opt-in sandbox test skipped**. |
| `cd frontend && AUTORCA_E2E_SANDBOX=1 npm run test:e2e -- e2e/sandbox.spec.ts` | **1 passed**, real Docker execution; VERIFIED visible in UI, persists after approval and matches report export. |
| `backend/.venv/bin/python scripts/evaluate.py --output data/evaluations/offline` | Eight completed demo investigations; zero model calls. |
| `SANDBOX_PROVIDER=docker backend/.venv/bin/python scripts/evaluate.py --authorize-isolated --check-fixtures --output data/evaluations/isolated` | Eight completed demo investigations; six independent reference pairs passed; one proposed repair verified. |
| `git diff --check` | Passed. |

The first Playwright attempt could not bind loopback port 18000 inside the execution sandbox. Approved execution outside that restriction passed. Docker availability similarly reported unavailable inside the sandbox; an approved readiness check found the existing pinned image and daemon available. No runner was installed or started. An initial frontend npm invocation from the repository root found no test script; rerunning from `frontend` passed.

Skipped backend tests require unavailable Vercel SDKs or a disposable PostgreSQL database. The local environment uses Python 3.10 despite the project's newer declared deployment range. Existing warnings concern Starlette/AnyIO and LangGraph deprecations. Next reports its existing standalone/start-command warning during browser tests; the servers and tests completed. Hosted compatibility was not measured.

## Measured benchmark

Artifacts: [offline JSON](../data/evaluations/offline.json), [offline Markdown](../data/evaluations/offline.md), [isolated JSON](../data/evaluations/isolated.json), [isolated Markdown](../data/evaluations/isolated.md). Generated artifacts live under ignored `data/` and can be regenerated with the commands above. Full JSON preserves actual run authorization, manifest and proof evidence after removal of the disposable database.

| Metric | Offline demo | Demo with authorized isolation |
| --- | --- | --- |
| Completed cases | 8/8 | 8/8 |
| Retrieved-file Top-1 | 5/6 | 5/6 |
| Retrieved-file Top-3 | 6/6 | 6/6 |
| Valid citation references | 10/10 | 10/10 |
| Patch application | 1/1 | 1/1 |
| Independently verified proposed repairs | 0/6 | 1/6 |
| Abstention precision | 2/7 | 2/7 |
| Abstention recall | 2/2 | 2/2 |
| Executed required validation phases | 0/12 | 2/12 |
| RCA correctness among scored cases | 0/5 | 0/5 |
| RCA scoring coverage | 5/6; one diagnosis unreviewed | 5/6; one diagnosis unreviewed |
| Model cost | $0; no calls | $0; no calls |

Five judgeable incidents were abstained by the deliberately limited demo, so they count as incorrect. The bundled free-text diagnosis remains unscored pending reviewed adjudication. This is not a live-model accuracy result or a claim of accuracy improvement. Source-selection hints are supplied; localization is not blind diagnosis. Citation-reference validity does not establish semantic support for claims. Actual median/p95 latencies are in the generated artifacts.

All **six** executable reference fixtures produced nonzero baseline exits and zero patched exits in restricted containers. Those checks validate the fixture corpus only and are excluded from the **1/6** proposed-repair metric. The positive proposal proof uses the real controlled checkout run, not a mock adapter. Mocked tests separately exercise negative and state-transition cases.

## Compatibility, rollback and remaining limits

Existing lifecycle fields, approval gates, authentication and draft-PR behavior remain intact. Additions use existing JSON storage; no data backfill or schema migration is needed. Historical records resolve conservatively. Unconsumed old validation plans require replanning because test-role manifests are incomplete. Rollback code without dropping records; old code ignores additive fields but loses the stronger guards and outcome labels.

Generic independent reproduction, arbitrary test dependency integrity, line-level causal evidence, local commit pinning, symbol-aware retrieval and calibrated live accuracy remain future work. Arbitrary test output is never a trusted coverage oracle. Pytest can execute but does not earn the restricted checkout proof. Live provider token/cost telemetry is not implemented; live costs stay unknown. The two held-out cases test uncertainty only, not diagnosis generalization.

Next prioritized slice: pin local source revisions and introduce validated line-level hypotheses; then independent reproduction/regression specifications for general repositories. Require stale-revision, fabricated-citation, contradictory-evidence and generic test-tampering acceptance tests before broadening VERIFIED eligibility.
