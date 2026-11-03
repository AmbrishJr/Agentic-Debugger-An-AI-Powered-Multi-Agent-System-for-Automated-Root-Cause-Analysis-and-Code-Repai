# Verification record

Verified locally with Python 3.10.14, Node.js 24.7.0, and Chromium through Playwright.

| Check | Observed result |
| --- | --- |
| Backend pytest suite | 32 passing tests: workflows, persistence, FTS retrieval, safe paths, redaction, version guards, authorization, provider failures, mocked GitHub and diff newline handling |
| Frontend Vitest suite | 4 passing component tests |
| TypeScript check | Passed |
| Next.js production build | Passed using Webpack; all six UI screens and API proxy compiled |
| Playwright | 3 passing browser workflows, including desktop approval, mobile rejection, history, settings and dashboard |
| Trusted sample before patch | Four tests executed: two failures and two errors, including the zero-discount exception (expected) |
| Trusted sample after patch | Four tests passed |
| npm dependency audit | Zero reported advisories after dependency updates |
| Screenshot inspection | Desktop dashboard and 390-pixel mobile review inspected; mobile overflow corrected |

Backend tests use a temporary SQLite database. Browser tests launch both app servers with an isolated test database and verify frontend requests reaching FastAPI through the Next.js proxy. Review decisions are reloaded from storage in the browser. The original sample remains buggy and unchanged. The app supports a blank database as well as actual stored demo investigations.

The first frontend build attempt hit a restricted Turbopack worker-port operation. The supported Webpack build completed successfully. Two initial browser failures (an ambiguous test selector and real mobile grid overflow) were corrected before the passing run. Backend execution emits two upstream deprecation warnings (Starlette/AnyIO and LangGraph serialization defaults); no test failures remain.

External-service boundaries: no real OpenAI credentialed request, GitHub write, Docker build/run, or remote deployment has been verified. Those implementations must be validated in a disposable environment before operational use. Live-mode tests exercise structured response handling and failure paths with mocked providers.
