# Implementation checkpoints

The latest work is recorded under **Sixth upgrade: preregistered contract provenance** below. Earlier checkpoints are retained as historical evidence.

## First upgrade checkpoint

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

## Second upgrade: pinned source and citation grounding

Implemented after the first checkpoint, preserving its work and the user's original `docs/security.md` changes.

### Delivered

- New local incidents capture Git HEAD plus a bounded file-hash manifest. Captured working-tree differences are labeled separately; non-Git and unborn repositories use content snapshots. A separate repository-binding digest catches root switches. File reads preserve exact UTF-8 bytes, including CRLF differences.
- Investigation reads validate manifest identity, repository root, revision and requested file bytes. Collected sources are rechecked before/after analysis, before patch generation, and at approval/initial PR publication. Changed source requires a new incident; retry never silently repins it.
- Typed citations validate evidence ID, path, kind, original hash, content integrity, snapshot, revision, line range and exact full-line quotation. Source redaction preserves line positions. Empty citation lists explicitly report `no_citations`.
- Observations carry citations; hypotheses retain supporting and contradicting evidence and missing diagnostics. Unresolved primary-hypothesis diagnostics or absent source/log support block patch generation. This checks provenance, not the semantic truth of a model explanation.
- The investigation/review UI shows source provenance, working-tree differences, cited quotations and uncertainty. Historical records are visibly legacy, with no invented snapshot or retroactive precise-citation claim.
- The evaluation harness pins independent test hashes without including their contents in model evidence; stack traces referencing those hidden tests are rejected. It retains snapshots and reports exact-citation validity separately from ID-reference validity.

### Files added or extended in this slice

New: `backend/app/services/repository_snapshots.py`, `backend/app/services/grounding.py`, `backend/migrations/versions/005_source_snapshots.py`, `backend/tests/test_grounding.py`, `docs/source-grounding.md`.

Extended: `backend/app/models/records.py`, `backend/app/schemas/contracts.py`, `backend/app/services/security.py`, `backend/app/services/validation.py`, `backend/app/agents/workflow.py`, `backend/app/api/routes.py`, `backend/app/evaluation/runner.py`, `backend/app/evaluation/metrics.py`, `backend/tests/test_workflow.py`, `backend/tests/test_multifile_retrieval.py`, `frontend/src/types/index.ts`, `frontend/src/components/common.tsx`, `frontend/src/components/common.test.tsx`, both investigation/review pages, `frontend/e2e/demo.spec.ts`, `README.md`, `benchmarks/README.md`, `docs/api.md`, `docs/ACCURACY_AUDIT.md`, this checkpoint.

### Verification

| Command | Measured result |
| --- | --- |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q` | **134 passed, 10 skipped**, two existing deprecation warnings. |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_grounding.py -q` | **31 passed** after the final Git transport/helper hardening. |
| `cd frontend && npm test` | **13 passed**. |
| `cd frontend && npm run typecheck` | Passed. |
| `cd frontend && npm run build` | Passed production build. |
| `cd frontend && AUTORCA_E2E_SANDBOX=1 npm run test:e2e` | Five scenarios passed, including real isolated repair. One new assertion matched both visible text and raw agent JSON and was corrected. |
| `cd frontend && npm run test:e2e -- e2e/demo.spec.ts -g 'complete demo'` | Corrected scenario passed; all six browser scenarios now have passing results. |
| `backend/.venv/bin/python scripts/evaluate.py --output data/evaluations/grounding-offline` | Eight cases completed, zero provider calls, no isolated repair claims. |
| `SANDBOX_PROVIDER=docker backend/.venv/bin/python scripts/evaluate.py --authorize-isolated --check-fixtures --output data/evaluations/grounding-isolated` | Eight cases completed; bundled proposed repair VERIFIED; all six reference pairs failed before/passed after. |

The grounding suite covers local Git/subdirectory/non-Git sources, dirty content, new HEAD with identical file bytes, CRLF edits, root switches, source changes mid-investigation, forged citation components, redaction/line mapping, contradictions, abstention without patch generation, empty-citation status, and SQLite migration upgrade/downgrade with existing data. Fixed Git reads disable fsmonitor/hooks, lazy fetch, transport protocols, credential helpers and terminal prompting, and discard injected Git environment variables.

The ten skipped tests still concern unavailable cloud SDKs and disposable PostgreSQL; hosted migration and live provider calls were not performed. Existing Python-version, deprecation and Next standalone/start warnings remain as recorded above.

### Benchmark artifacts and interpretation

Artifacts: [offline report](../data/evaluations/grounding-offline.md), [offline JSON](../data/evaluations/grounding-offline.json), [isolated report](../data/evaluations/grounding-isolated.md), [isolated JSON](../data/evaluations/grounding-isolated.json). Generated artifacts remain under ignored `data/`.

Both runs recorded **6/6 exact structured references** and **2/2 unique hypothesis ID references**, Top-1 **5/6**, Top-3 **6/6**, patch application **1/1**, abstention precision **2/7**, and abstention recall **2/2**. The earlier ID-reference denominator was 10; unsupported ID-only mentions are now removed, so this denominator change is not an accuracy gain. Six references include repeated citations across observation/hypothesis claims.

The offline run verified **0/6** repair-eligible cases; the authorized isolated run verified **1/6**. All **6/6 reference-patch pairs** passed separately and are excluded from proposed-repair scoring. One free-text diagnosis remains unreviewed; five judgeable demo abstentions remain incorrect (**0/5 scored**, coverage **5/6**). No live-model improvement is claimed.

### Migration and next boundary

Migration **005** adds `incidents.repository_snapshot` with an empty-object default; existing incident data is preserved. It was applied to disposable test/evaluation databases only. Local startup uses the existing migration mechanism. Hosted environments must migrate before deploying the new code. Keep the column when rolling back code to retain provenance; explicit schema downgrade removes only that metadata. Detailed operations are in `source-grounding.md`.

This slice is complete. Remaining work is symbol/dependency-aware retrieval and independent reproduction specifications for generic repositories. Live-model evaluation needs an explicitly selected provider/model and budget. Exact citation validity is a prerequisite for diagnosis quality, not proof of causality or repair correctness.

## Third upgrade: Python symbol and dependency retrieval

Implemented a bounded Python AST index and deterministic multi-file expansion. This checkpoint supersedes the earlier deferred symbol-indexing status; earlier test counts and measurements remain historical. Pre-existing grounding changes were preserved.

### Delivered

- `backend/app/services/source_index.py` indexes definitions, line ranges, static direct calls and imports without importing/executing source. It resolves aliases and relative imports conservatively, avoids ambiguous module/name guesses, expands callers/callees two hops and import neighbors one hop, and preserves explicit selection and stack order.
- Indexes contain metadata only and use an eight-entry per-process cache bound to repository, snapshot, revision and parser version. Local cache reads recheck source bytes. GitHub cold reads are bounded; warm immutable-revision indexes avoid repeated blob downloads. File/node/byte/time limits and skipped syntax are exposed.
- Protected tests/support files are excluded from automatic indexing/expansion. Evaluation fixtures must place independent tests under those protected paths, preventing retrieval from exposing oracle bodies.
- Settings adds `source_retrieval: symbols | stack`, snapshotted per investigation. New work defaults to symbols; old stored configurations without the field retain stack behavior. Source evidence shows selection reasons and symbol ranges. Report JSON includes the coverage summary and per-file metadata.
- The evaluation CLI adds `--source-retrieval` and `--without-file-hints`. It preserves the same isolated/live authorization boundary, reports configuration and retrieval metadata, and uses the real pipeline for both strategies. A paired CLI regression test verifies localization and hidden-test separation.

No dependency, database migration, execution authorization, deployment or external publishing step was added. Complete bounded source files remain evidence, preserving existing patch-generation compatibility and citation hashes.

### Executed verification

| Command | Result |
| --- | --- |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q` | **154 passed, 10 skipped**, two existing deprecation warnings. |
| `cd frontend && npm test` | **15 passed**. |
| `cd frontend && npm run typecheck` | Passed. |
| `cd frontend && npm run build` | Passed production build. |
| `cd frontend && AUTORCA_E2E_SANDBOX=1 npm run test:e2e` | **6 passed**, including retrieval reasons, saved strategy, review/approval/report consistency, roles, lifecycle and real isolated repair. |
| `backend/.venv/bin/python scripts/evaluate.py --source-retrieval stack --without-file-hints --output data/evaluations/retrieval-stack` | Eight completed demo cases, zero provider calls. |
| `backend/.venv/bin/python scripts/evaluate.py --source-retrieval symbols --without-file-hints --output data/evaluations/retrieval-symbols` | Eight completed demo cases, zero provider calls. |
| `git diff --check` | Passed. |

The new source-index tests cover relative/aliased imports, async/class ranges, incoming/outgoing calls, source/file limits, invalid syntax and other-language fallback, trace-line attribution, shadowed names, ambiguous basenames/modules, cache/source changes, renamed symbols, parser-version invalidation, GitHub cache/read budgets, oracle exclusion and configuration snapshots. GitHub behavior uses transport mocks. The browser suite used approved access to loopback servers and the existing pinned Docker runner.

The ten backend skips still require unavailable cloud SDKs or disposable PostgreSQL. Live GitHub indexing, hosted environments and paid model calls were not exercised. Python 3.10 versus the newer declared deployment range, Starlette/LangGraph deprecations and the existing Next standalone/start warning remain as noted in prior checkpoints.

### Matched retrieval benchmark

Artifacts: [stack Markdown](../data/evaluations/retrieval-stack.md), [stack JSON](../data/evaluations/retrieval-stack.json), [symbols Markdown](../data/evaluations/retrieval-symbols.md), [symbols JSON](../data/evaluations/retrieval-symbols.json). Files remain in ignored `data/` and are reproducible with the commands above.

Both runs have dataset SHA-256 `c02b861288cb9f9ccac1a89a74990d9d03d57c79b700e5f24d03966c0552e57e` and application-source SHA-256 `4d45d3dc63bd2e9894cbf06b38aeca140230b66ca2b58193832a5ce823a333c2`. The working tree was dirty; artifacts retain base commit `d52a053139035270f92c12dbdee9cae077d35acf` separately from the actual source digest. Selected-file hints were removed from both; submitted stack traces remained.

| Metric | Stack paths | Symbols/dependencies |
| --- | --- | --- |
| Completed cases | 8/8 | 8/8 |
| Top-1 retrieved-file localization | 5/6 | 5/6 |
| Top-3 retrieved-file localization | 5/6 | 6/6 |
| Exact citation validity | 6/6 | 6/6 |
| Citation ID-reference validity | 2/2 | 2/2 |
| Patch application | 1/1 | 1/1 |
| Verified proposed repairs | 0/6 | 0/6 |
| Abstention precision / recall | 2/7; 2/2 | 2/7; 2/2 |
| Scored RCA correctness / scoring coverage | 0/5; 5/6 | 0/5; 5/6 |
| Median / p95 latency (seconds) | 0.15095 / 0.1841 | 0.19095 / 0.2526 |
| Provider cost | $0; no calls | $0; no calls |

For `cross-file`, stack retrieval returned only `pricing.py`; symbols additionally returned the faulty caller `invoice.py` at rank two. That is the sole localization change. The two held-out cases concern missing evidence, so this is not evidence of held-out diagnosis generalization. One diagnosis remains unreviewed; five judgeable demo abstentions are still incorrect. No live diagnosis improvement is claimed. Latencies are descriptive single-run observations on this machine (browser checks were also active), not a production performance benchmark. Offline runs did not authorize fixture execution and therefore verified no repairs; the separate browser test confirmed the controlled fixture still qualifies in real isolation.

### Remaining work

This retrieval slice is complete. Static Python relationships cannot resolve all runtime dispatch, re-exports, higher-order calls or nested scopes. Non-Python symbol indexing, scalable persistent indexes and production-sized performance evaluation remain open. Generic repositories still need independent failure attribution and regression specifications before their patches can earn VERIFIED. Semantic claim verification, calibrated confidence and broader held-out/live evaluation remain separate work. Live evaluation requires explicit provider, model and case/budget choices.

Operations, cache behavior, rollback to stack retrieval, bounds and reproduction instructions are in [source-retrieval.md](source-retrieval.md). Earlier approval/authentication behavior and the user's security-document changes remain intact.

## Fourth upgrade: reviewed reproduction and regression specifications

Added the declaration and observation layer needed before broader independent repair verification. This slice is complete within that boundary; generic independent proof remains open. Existing work and the user's security-document changes were preserved.

### Delivered

- Optional versioned `verification_spec` on unittest validation plans, with reviewed rationale, reproduction test IDs/exceptions and required regression IDs. The server records the authenticated reviewer/time and binds IDs to existing incident test hashes and snapshot identity. It parses test definitions without importing or executing them.
- Authorization hashes include the complete bound specification. Authorization and execution recheck its integrity; plan/patch changes during execution discard positive proof and observations. Existing expiry, one-use consent, test immutability and fixed isolation policies remain intact. Interrupted workers retain the declaration for audit.
- `services/verification_specs.py` checks complete verbose unittest observations against the declared expectation. Wrong exceptions, unrelated baseline failures, patched failures, missing/skipped tests, duplicate records/summaries, changed discovery, inconsistent process results and incomplete cleanup cannot produce a match.
- Explicit assessment statuses (`matched`, `not_reproduced`, `mismatch`, `inconclusive`) and per-test observations persist separately from process exit status. Mismatch/inconclusive required checks fail validation; baseline passing results remain NOT_REPRODUCED when no explicit failure overrides them.
- The review UI collects and displays expectations before execution consent. Incident, patch and report responses retain the same latest specification and assessment. Matching observations explicitly carry `independent_proof: false`; generic repair outcomes remain conservative.

Existing clients can omit the specification, and ordinary pytest runs remain supported. No new database migration, dependency, image rebuild, service, deployment or paid provider call was added. The existing exact bundled fixture retains its separate VERIFIED proof gate; a failed specification overrides that positive fixture proof too.

### Executed verification

| Command | Result |
| --- | --- |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_sandbox.py backend/tests/test_repair_outcomes.py -q` | **32 passed** after the plan integration. |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_verification_specs.py -q` | **31 passed**, using mocked runner observations. |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q` | **185 passed, 10 skipped**, two existing deprecation warnings. |
| `cd frontend && npm test` | **19 passed**. |
| `cd frontend && npm run typecheck` | Passed. |
| `cd frontend && npm run build` | Passed production build. |
| `cd frontend && AUTORCA_E2E_SANDBOX=1 npm run test:e2e` | **7 passed**, including two real isolated execution scenarios. |
| `backend/.venv/bin/python scripts/evaluate.py --output data/evaluations/verification-specs-offline` | Eight completed offline demo cases; zero provider calls and no additional fixture execution. |
| `git diff --check` | Passed. |

The real positive browser scenario reviewed four expected failures and four regression IDs, produced `matched` observations, and retained the exact controlled fixture's VERIFIED outcome after approval and report download. The real negative scenario declared ValueError where the fixture raises ZeroDivisionError: patched tests passed, but the specification reported `mismatch` and the UI/API showed VALIDATION_FAILED. Neither browser result is a generic-repository accuracy measurement.

Backend tests cover declaration rejection, server-assigned reviewer identity, snapshot/test bindings, changes before authorization/while queued/during execution, historical requests, unsupported profiles, both known unittest ID display forms, exact exceptions, missing/duplicated/skipped/contradictory observations, cleanup/time/output failures, report consistency, restart retention, and forged matching output on a patch outside the controlled fixture. The forged-output case remains PATCH_UNVERIFIED.

Ten tests still require unavailable cloud SDKs or disposable PostgreSQL. Live providers, live GitHub indexing and hosted execution were not exercised. The existing Python deployment-version discrepancy, Starlette/LangGraph deprecations and Next standalone/start warning remain. Browser verification used the already configured pinned Docker image and approved loopback access; no image or runner installation occurred.

### Offline compatibility measurement

Artifacts: [Markdown](../data/evaluations/verification-specs-offline.md), [JSON](../data/evaluations/verification-specs-offline.json), under ignored `data/`. Default symbol retrieval with selected-file hints recorded Top-1 **5/6**, Top-3 **6/6**, exact citations **6/6**, patch application **1/1**, and verified repairs **0/6**. RCA scoring remains **0/5** with coverage **5/6** and one unreviewed diagnosis. Cost is **$0**, with no provider calls. These unchanged demo metrics are a compatibility check, not evidence of live-model accuracy improvement or specification execution in the benchmark.

### Remaining proof boundary

Reviewing existing tests does not establish independent authorship, causal relevance or trustworthy runtime telemetry. Generic repository code can forge stdout, so even perfectly matching observations remain untrusted. Before broadening VERIFIED, implement a separately trusted oracle/observation channel with independent test provenance and reviewed attribution/regression rules. Version 1 does not support inherited/dynamic tests, altered verbose output, subtest failure formats or pytest specifications. Multi-language retrieval, semantic claim support, calibrated confidence and live/held-out diagnosis evaluation remain open as previously recorded.

See [verification specification operations](verification-specifications.md) for the API, UI workflow, limits and rollback behavior. No external publication was performed.

## Fifth upgrade: controller-owned JSON behavior checks

Implemented a narrow behavioral oracle for Python command-line JSON interfaces. Expected answers stay in the controller, and actual isolated program responses are compared there. This completes the controller-comparison slice; independent test provenance and broader VERIFIED eligibility remain open.

### Delivered

- Optional `python-json-stdio` validation profile with a reviewed JSON contract: entrypoint, rationale and 2–4 reproduction/regression cases. Known incorrect baseline outputs distinguish reproduction from an unrelated failure. Values are bounded to 4 KiB; both test roles and distinct IDs are required.
- Server-bound reviewer, timestamp, incident snapshot, source hashes and oracle version. The authorization hash covers the contract, full fixed driver command, source manifest, patch and runtime policy. No expected values, case roles, IDs or other cases enter candidate execution.
- Source-only snapshots run through an application-owned driver in the existing immutable Docker image. Each input/version receives a fresh restricted container. Expiry is checked before each invocation; invalid output, runtime errors or uncertain cleanup stop subsequent invocations. No host fallback, new dependency, image installation or schema migration was added.
- Strict controller JSON comparisons reject duplicate keys, non-finite/overflowing numbers, multiple values, invalid UTF-8, redacted output and stderr diagnostics. Semantic outcomes are stored separately from actual per-invocation exit codes. A zero-exit program that returns no JSON fails the required contract.
- Review UI for declarations, maximum invocation count and per-case comparison results. Existing incident, patch and report endpoints retain the same contract and latest assessment. Generic matches remain PATCH_UNVERIFIED; already-correct baselines produce NOT_REPRODUCED; mismatches/inconclusive checks produce VALIDATION_FAILED.
- Docker stdout and stderr are captured separately with a shared output budget, then rendered in stable stream order. This avoids corrupting unittest records through cross-stream interleaving. JSON contracts require stderr to be empty. The capture policy is authorization-bound, so pending plans created under the prior policy require replanning.

No deployment, external publication, paid provider call or rewrite of historical records occurred. Existing user changes were preserved. This profile is Docker-only; Vercel explicitly rejects it without fallback.

### Executed verification

| Command | Result |
| --- | --- |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_sandbox.py backend/tests/test_verification_specs.py backend/tests/test_repair_outcomes.py -q` | **63 passed** after the initial integration. |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q` | **217 passed, 10 skipped**, two existing deprecation warnings. |
| `cd frontend && npm test` | **20 passed**. |
| `cd frontend && npm run typecheck` | Passed. |
| `cd frontend && npm run build` | Passed production build. |
| `cd frontend && AUTORCA_E2E_SANDBOX=1 npm run test:e2e` | **8 passed** on the final full run. |
| `backend/.venv/bin/python scripts/validate_json_contract.py --execute` | **5/5 real isolated adapter scenarios passed**, 14 fresh container invocations. |
| `PYTHONPATH=backend backend/.venv/bin/python scripts/validate_sandbox.py --execute --output data/evaluations/json-contract-sandbox-checks.json` | **15/15 existing isolation/authorization checks passed**, including unittest, pytest, time/output limits, cleanup and resource/security boundaries. |
| `backend/.venv/bin/python scripts/evaluate.py --output data/evaluations/json-contract-offline` | Eight completed offline demo cases, no provider calls or additional fixture execution. |
| `git diff --check` | Passed. |

The first full browser run had two failures: a demo approval response timed out even though the stored incident was approved, and the controlled unittest fixture became inconclusive because stdout's summary was interleaved inside stderr's final test line. The output collector was fixed without relaxing the parser/proof checks. The final complete browser rerun passed all eight scenarios, including the unchanged controlled VERIFIED fixture, wrong-exception rejection, and a JSON program that exits zero without returning a value. The final resource/cleanup checks also passed after the collector change.

New backend cases verify contract/schema/source boundaries, absence of oracle answers from invocation payloads, authorization/queued tampering, expiry, cleanup failure, malformed/ambiguous JSON, non-finite values, redaction/decoding/stderr rejection, fixed driver policy, no cloud fallback, shared API/report outcomes, approval without verification, and forged test-report rejection. Mocked runner tests are contract tests, not accuracy measurements.

Ten skips still require unavailable cloud SDKs or disposable PostgreSQL. Live providers, live GitHub indexing and hosted execution were not exercised. The Python deployment-version discrepancy, Starlette/LangGraph deprecations and existing Next standalone/start warning remain. Browser and adapter checks used approved local loopback/Docker access and the already configured immutable image.

### Artifacts and interpretation

- [Real JSON oracle checks](../data/evaluations/json-contract-isolated.json): correct repair → matched; wrong repair → mismatch; already-correct baseline → not_reproduced; stderr masquerading as a response → inconclusive; forged unittest summary → inconclusive. Artifact kind is `isolated_adapter_checks`, explicitly not an accuracy benchmark.
- [Isolation regression checks](../data/evaluations/json-contract-sandbox-checks.json): existing security/resource/timeout/output/cleanup coverage after the collector change.
- [Offline benchmark Markdown](../data/evaluations/json-contract-offline.md) and [JSON](../data/evaluations/json-contract-offline.json): Top-1 **5/6**, Top-3 **6/6**, verified repairs **0/6**, no provider calls and **$0** provider cost. This compatibility run retains selected-file hints and does not execute JSON contracts or measure live-model improvement.

Generated artifacts remain under ignored `data/` and can be reproduced with the listed commands. A matching synthetic contract establishes only the tested behavior, not general correctness, independent authorship or model accuracy.

### Remaining work

The oracle now owns comparison and withholds expected answers, but independent provenance of the contract and its causal relevance to the incident are still reviewer-declared. Those guarantees and a reviewed policy for the scope of verification are required before generic repairs can earn VERIFIED. Supported interfaces remain Python CLI JSON on Docker; other languages/frameworks, service/exception contracts and Vercel execution need separate adapters. Semantic citation support, confidence calibration, broader held-out diagnosis cases and explicitly configured live evaluation remain unimplemented or unmeasured.

Operational details, API examples and limitations are in [JSON behavior contracts](json-behavior-contracts.md). Existing unittest/pytest profiles and approval rules remain available; the exact controlled fixture remains the only VERIFIED repair scope.

## Sixth upgrade: preregistered contract provenance

Date: 2026-11-12 (Asia/Kolkata). Added immutable contract registration before investigation, review by a different authenticated account, and a narrowly scoped VERIFIED outcome for those registered JSON cases. This extends the fifth checkpoint's proof boundary without promoting old or ad hoc results.

### Delivered

- Registration and review are append-only audit events in existing JSON evidence fields. The server assigns account identity, hashes and timestamps. No schema migration, account changes or historical rewrite is required.
- Registration, review and investigation startup share a database lock. Contracts cannot be added after investigation or proposal creation; startup waits for a separate account's review. Only references and hashes enter investigation configuration, with expected answers excluded from model evidence.
- Validation plans reference the exact registration hash and source set. Authorization, worker startup, completion and outcome resolution recheck provenance. The controller rechecks actual saved before/after responses, rather than accepting stored match flags.
- The new proof scope is `registered-json-contract-v1`. VERIFIED covers only the preregistered reproduction and regression cases under authorized isolation. It does not establish diagnosis causality, correctness for untested inputs, separate human identities behind accounts, or resistance to a privileged database administrator rewriting history.
- New-incident and investigation screens support saving before analysis, registering a contract and review by another account. The review screen selects the registered contract and still requires separate execution consent. Existing approvals, ad hoc contracts and bundled fixture behavior remain available.
- A reproducible disposable-database integration script exercises actual registration, review, investigation, plan, authorization, Docker execution, report and approval APIs. Its proposal is a seeded synthetic reference patch, explicitly separated from accuracy measurements.

### Executed verification

| Command | Result |
| --- | --- |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_contract_registry.py -q` | **16 passed**, including concurrent registration/startup. |
| `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q` | **233 passed, 10 skipped**, two existing deprecation warnings. |
| `cd frontend && npm test` | **21 passed**. |
| `cd frontend && npm run typecheck` | Passed. |
| `cd frontend && npm run build` | Passed production build. |
| `cd frontend && AUTORCA_E2E_SANDBOX=1 npm run test:e2e` | **9 passed**, including the new separate-account workflow and existing isolated scenarios. |
| `backend/.venv/bin/python scripts/validate_contract_provenance.py --execute` | Passed with real isolated reproduction/regression results; four fresh Docker invocations. |
| `backend/.venv/bin/python scripts/evaluate.py --output data/evaluations/registered-contract-offline` | **8/8 completed** offline demo cases; zero provider calls. |
| `git diff --check` | Passed. |

New tests cover self-review, role and lifecycle restrictions, duplicate/replayed review, forged actor fields, withheld answers, provenance tampering before authorization/while queued/during execution/after completion, changed stored observations, exact source sets, consistent API/report outcomes and approval preserving the result. Mocked runner tests verify contracts, not model accuracy.

Frontend commands initially aborted inside the execution sandbox with the macOS `SecItemCopyMatching failed -50` runtime error. Approved execution outside that restriction passed unit tests, type checking, production build and all browser workflows. Real Docker checks used the existing pinned image. Ten backend skips still concern unavailable cloud SDKs and disposable PostgreSQL. Live providers, live GitHub indexing and hosted execution were not exercised. Existing Python deployment-version, dependency deprecation and Next standalone/start warnings remain.

### Artifacts and remaining work

- [Isolated integration artifact](../data/evaluations/registered-contract-isolated.json): `status: passed`, scoped VERIFIED, identical detail/patch/report outcomes and unchanged outcome after approval. Explicitly labeled `accuracy_benchmark: false` and `proposal_origin: seeded_synthetic_reference`.
- [Offline Markdown](../data/evaluations/registered-contract-offline.md) and [JSON](../data/evaluations/registered-contract-offline.json): Top-1 **5/6**, Top-3 **6/6**, citation references **2/2**, exact citations **6/6**, patch application **1/1**, verified repairs **0/6**. RCA accuracy is **0/5**, with scoring coverage **5/6** and one unreviewed diagnosis. Median latency **0.7538 s**, p95 **0.9879 s**, no provider calls and **$0** provider cost. These demo compatibility results do not measure live-model improvement.

Generated artifacts remain under ignored `data/`. No deployment, external publication or paid model request occurred, and `docs/security.md` was not modified.

The new policy supplies account-level provenance and sequencing; human independence and causal attribution remain outside its guarantees. Other languages/interfaces, service and exception contracts, JSON execution on Vercel, semantic citation support, confidence calibration and broader held-out diagnosis evaluation remain open. A live benchmark still requires an explicit provider, model, case limit and usage-budget choice. Operations, trust limits and rollback behavior are documented in [contract provenance](contract-provenance.md).
