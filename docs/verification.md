# Verification record

## Hosted Vercel release — November 6, 2026 (Asia/Kolkata)

Production frontend: [autorca-frontend.vercel.app](https://autorca-frontend.vercel.app). Backend: [autorca-backend.vercel.app](https://autorca-backend.vercel.app); direct requests require the server API token. Both final production builds reached Ready. [Deployment report](vercel-deployment.json).

Separate Neon databases on the free plan were provisioned for Preview and Production. The existing workspace was copied into each empty target; account password hashes and roles match the original SQLite database. The original database and `.env` remain intact. Temporary verification accounts and their sessions were removed from Preview; no temporary account was created in Production.

| Hosted check | Observed result |
| --- | --- |
| Preview authentication and proxy | Sign-in, Secure/HttpOnly/SameSite cookies, CSRF rejection, logout, existing-account initialization, unauthenticated incident rejection, and backend API-token enforcement passed |
| Demo investigation | All seven agents completed through hosted Vercel Workflows |
| Authorized Sandbox workflow | Original bundled source failed, fixed source passed, cleanup confirmed; reusing authorization returned HTTP 400 and created no new job |
| Runner image | Private AMD64 VCR image reached Ready; real SDK before/after checks and cleanup passed |
| Gemini investigation | Completed through hosted Workflows after two manual retries resumed saved checkpoints; the initial analysis and subsequent report calls encountered provider errors |
| GitHub | Deployed backend read source from the disposable validation repository using real credentials |
| Browser | Hosted Chromium sign-in, dashboard, review, 390-pixel mobile layout, and logout passed |
| Production | Public frontend, API health, live-provider availability, initialized workspace, and unauthenticated access protections passed |

Hosted checks exposed and fixed two integration issues: the Sandbox output stream must implement `writable()`, and the frontend must use `AUTORCA_BACKEND_BYPASS_SECRET` because Vercel supplies its own project-specific `VERCEL_AUTOMATION_BYPASS_SECRET`. Targeted cloud tests and TypeScript checks passed after the respective fixes.

Preview uses the disposable GitHub repository; Production targets the AutoRCA application repository selected by the owner. No draft PR was created, merged, or published during this deployment pass. Earlier local draft-PR tests remain recorded below; hosted draft-PR publication and hosted cancellation/viewer-role checks were not repeated. Provider availability can still vary; successful saved steps are retained for manual investigation retries.

The following sections record earlier verification stages and their status at that time.

## Vercel migration — November 5–6, 2026 (Asia/Kolkata)

Cloud adapters are implemented; hosted deployment is still pending. The existing `.env`, administrator account, and local database were not replaced. See [deployment configuration and remaining hosted checks](vercel.md).

| Check | Observed result |
| --- | --- |
| PostgreSQL regression suite | 84 tests passed against a fresh disposable PostgreSQL 17 database, Python 3.13.2, and the cloud lockfile |
| Final cloud/GitHub recovery checks | 24 tests passed after adding interrupted-PR recovery; the suite now contains 85 backend cases |
| Existing Python 3.10/SQLite environment | 75 passed, 9 cloud/SDK-specific skips before the final PostgreSQL-only PR test; all 5 affected local GitHub tests also passed |
| Real Workflow SDK | All seven demo agents completed through the SDK's local embedded queue transport; no hosted workflow or AI provider was called |
| Cloud runner image | Buildx built the required linux/amd64 image; architecture inspection passed. Both unittest and pytest reproduced the original bug (exit 1) and passed the fixed bundled source (exit 0) in network-disabled local containers |
| Frontend | TypeScript, 4 component tests, and production build passed |
| Browser workflows | 6 passed, including real local Docker before/after execution |
| Vercel connection | MCP documentation search and authenticated team-list request succeeded |

Tests cover PostgreSQL migrations/search/account transactions, duplicate cloud deliveries, cancellation and generation fencing, stale failure rejection, preserving completed validation results, authorization non-replay, sandbox output and cleanup failures, repository/commit pinning, unsafe GitHub paths, and read-only transfer of an administrator into an empty database. The real SDK check is reproducible with `backend/.venv-cloud/bin/python scripts/validate_cloud_workflow.py` and isolates its database, queue state, and credentials.

No Vercel project deployment, PostgreSQL provider provisioning, registry upload, or hosted Sandbox execution has occurred in this migration pass. The existing real Gemini/GitHub checks below predate the cloud adapters. They do not establish hosted operation.

The Mac's legacy Docker builder failed during cross-architecture image assembly. Installing Docker Buildx and rebuilding resolved that local tooling issue. The validated AMD64 image is retained locally as `autorca-runner-vercel:amd64-test`; it must still be published to Vercel Container Registry and reach Ready status before hosted use.

## Earlier local release verification

Verified locally with Python 3.10.14, Node.js 24.7.0, and Chromium through Playwright.

| Check | Observed result |
| --- | --- |
| Backend pytest suite | 66 passing tests, including plan authorization, stale/expired plans, snapshot purging, one-use execution, policy changes, cleanup failure blocking, and existing workflows |
| Frontend Vitest suite | 4 passing component tests |
| TypeScript check | Passed |
| Next.js production build | Passed using Webpack; all six UI screens and API proxy compiled |
| Playwright | 6 passing browser workflows, including account creation and viewer restrictions, resolution/reopening/logout, real isolated Docker execution, desktop approval, mobile rejection, history, settings and dashboard |
| Trusted sample before patch | Four tests executed: two failures and two errors, including the zero-discount exception (expected) |
| Trusted sample after patch | Four tests passed |
| npm dependency audit | Zero reported advisories after dependency updates |
| Screenshot inspection | Desktop dashboard and 390-pixel mobile review inspected; mobile overflow corrected |

Backend tests use a temporary SQLite database. Browser tests launch both app servers with an isolated test database and verify frontend requests reaching FastAPI through the Next.js proxy. Review decisions are reloaded from storage in the browser. The original sample remains buggy and unchanged. The app supports a blank database as well as actual stored demo investigations.

The first frontend build attempt hit a restricted Turbopack worker-port operation. The supported Webpack build completed successfully. Two initial browser failures (an ambiguous test selector and real mobile grid overflow) were corrected before the passing run. Backend execution emits two upstream deprecation warnings (Starlette/AnyIO and LangGraph serialization defaults); no test failures remain.

Real GitHub validation passed against a newly created private repository: [draft PR #1](https://github.com/AmbrishJr/autorca-x-validation-6ff238177e55/pull/1). The app enforced approval and separate PR authorization, created a one-file draft, preserved the original base, and returned the same PR on retry. Artifacts are retained for inspection. [Detailed report](github-validation.json).

The isolated runner was built and tested in the dedicated `colima-autorca` Docker context. The baseline suite failed as expected and the patched suite passed all 11 synthetic tests, including seven isolation checks. Additional runaway tests verified deadline termination, the output cap, and container cleanup. [Detailed report](sandbox-validation.json). The real transport checks used synthetic fixtures, not LLM-produced patches.

OpenAI remains unverified with real credentials: the user explicitly chose to continue without a key. Provider contract/failure tests are mocked. No PR was merged, no production deployment occurred, and no public deployment has been made. The application Compose stack passed real verification with a disposable volume, authenticated frontend proxy, viewer enforcement, durable queued-work recovery, and session/resolution persistence across service restarts. [Compose report](compose-validation.json). The current native-backend runner is documented in [sandbox.md](sandbox.md).


The latest changes add authentication/CSRF/role tests, login throttling, resolution/reopen history, durable queue cancellation/retry, completed-step recovery, retry attempt limits, downstream patch regeneration, multi-file source consistency, atomic GitHub commits, and local concept-vector retrieval. Browser workflows now sign in with an account confined to the isolated e2e database and verify resolution, reopening, and logout through the UI.

Real multi-file publishing also passed: [two-file draft PR](https://github.com/AmbrishJr/autorca-x-validation-464ff2e77dd6/pull/1), with an unchanged base and a retry returning the same PR. [Report](github-multifile-validation.json). The trusted runner now passes both unittest and pytest fixtures. A noisy-output cleanup timeout was fixed by closing the attach stream before removal, and the repeated real checks passed. The browser suite exposed an off-screen sign-out control; moving it into the toolbar fixed the interaction and preserved mobile layout.

The initial administrator must be created locally using the command in [workspace operations](security.md). No production password was generated and no OpenAI key was changed. Provider calls were deferred in that release; the later Gemini check below uses only bundled synthetic evidence. Synthetic integration credentials exist only in disposable verification environments.


## Gemini integration — November 5, 2026 (Asia/Kolkata)

The user-supplied Gemini key passed a real seven-agent investigation using `gemini-3.5-flash-lite` and only the bundled synthetic checkout log/source. Structured triage, analysis, patch generation, and report narration completed; evidence references, allowed file paths, original hashes, and Python syntax were checked. The result reached `awaiting_review`. Validation remained `partial` because live generated code is not executed on the host; isolated tests require separate authorization. No approval, PR, or deployment occurred. [Credential-free Gemini report](gemini-validation.json).

Additional backend tests cover provider preference migration, selected-provider availability, key isolation, Google-key redaction, schema-constrained requests, quota/access errors, refusal/truncation/invalid output handling, and preserving Gemini error details without raw provider responses. Both API keys are cleared in ordinary unit/browser tests. The production frontend and TypeScript checks pass with the new provider selector. All six browser workflows passed again, including switching to Gemini, persisting its model/provider settings, and switching back; four component tests also passed.
