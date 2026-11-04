# Verification record

Verified locally with Python 3.10.14, Node.js 24.7.0, and Chromium through Playwright.

| Check | Observed result |
| --- | --- |
| Backend pytest suite | 51 passing tests, including plan authorization, stale/expired plans, snapshot purging, one-use execution, policy changes, cleanup failure blocking, and existing workflows |
| Frontend Vitest suite | 4 passing component tests |
| TypeScript check | Passed |
| Next.js production build | Passed using Webpack; all six UI screens and API proxy compiled |
| Playwright | 5 passing browser workflows, including the real isolated Docker execution and review flow, desktop approval, mobile rejection, history, settings and dashboard |
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

The initial administrator must be created locally using the command in [workspace operations](security.md). No production password was generated, no OpenAI key was changed, and no provider call was made. Synthetic integration credentials exist only in disposable verification environments.
