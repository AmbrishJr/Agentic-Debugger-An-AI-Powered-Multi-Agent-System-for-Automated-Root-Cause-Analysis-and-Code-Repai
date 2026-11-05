# Vercel deployment

The repository supports a Vercel frontend, a Vercel FastAPI backend, durable Python workflows, and Vercel Sandbox test execution. PostgreSQL is supplied by a database provider such as Neon through Vercel Marketplace. This document describes deployment preparation; it is not evidence of a successful hosted deployment.

## Project layout

Create two Vercel projects from this repository:

| Project | Root directory | Framework | Configuration |
| --- | --- | --- | --- |
| Frontend | `frontend` | Next.js | `frontend/vercel.json` |
| Backend | `backend` | FastAPI, Python 3.13 | `backend/vercel.json`, `backend/pyproject.toml`, `backend/uv.lock` |

The frontend proxies `/api/*` to the backend and keeps login cookies on the frontend domain. Users visit the frontend URL. Set its `BACKEND_URL` to the backend's stable URL. Both projects need the same randomly generated `AUTORCA_API_TOKEN` (at least 32 characters). Database, Gemini, and GitHub credentials belong only to the backend.

Enable Vercel System Environment Variables and Fluid compute for the backend. Vercel discovers `app.cloud_workflows:wf` from `[[tool.vercel.workflows]]` and generates its workflow functions. Do not expose a custom unauthenticated job execution endpoint. The public API retains account roles, CSRF checks, and the server API token. If Vercel Deployment Protection protects the backend, set the corresponding automation bypass secret on the frontend; it is forwarded only to the configured backend, and redirects are rejected.

The server fails startup on Vercel if it is configured with SQLite, an embedded worker, automatic startup migrations, disabled authentication, insecure cookies, an invalid frontend origin, or a local repository/Docker runner. These checks prevent an apparently successful deployment with temporary data or unprotected access.

## Environment variables

Use these templates as the exact variable checklist:

- [Backend variables](../backend/.env.vercel.example)
- [Frontend variables](../frontend/.env.vercel.example)

Set Preview and Production separately, with separate databases and matching frontend/backend pairs. `PUBLIC_ORIGIN` is the exact frontend HTTPS origin, without a trailing slash. Set Gemini's existing key as `GEMINI_API_KEY`; no OpenAI key is required. GitHub credentials are needed for GitHub source and draft PRs, but not the bundled demo. No secret should use the `NEXT_PUBLIC_` prefix.

Local `.env`, credentials, virtual environments, workflow state, and databases are excluded from deployment uploads. The existing local/Docker requirements remain separate; the Vercel backend uses the cloud `pyproject.toml` and `uv.lock`.

## Database and existing administrator

Provision PostgreSQL through the Vercel Marketplace and connect it to the backend. Use its SSL-enabled pooled URL at runtime. Use a direct connection URL for operator migrations when the provider supplies one. Migration and application URLs must point to the same database.

Install the cloud environment with Python 3.13 and uv, without replacing the existing local virtual environment:

```bash
UV_PROJECT_ENVIRONMENT=.venv-cloud uv sync --project backend --locked
```

Save the migration target's `DATABASE_URL` in a separate ignored root file such as `.env.vercel`. Do not overwrite the local `.env`. Apply migrations explicitly before deploying a version that requires them:

```bash
backend/.venv-cloud/bin/python scripts/migrate_cloud.py --target-env .env.vercel --execute
```

To carry over the existing administrator and incident history, first stop the local application and its worker, finish or cancel active jobs, and back up the SQLite database. Then, instead of starting a fresh workspace:

```bash
backend/.venv-cloud/bin/python scripts/migrate_cloud.py --target-env .env.vercel --source data/autorca.db --execute
```

Without `--execute`, this script only checks its inputs. It opens the SQLite source read-only, refuses an occupied PostgreSQL target, and copies records in one transaction. Existing account password hashes and roles are preserved. Sessions and login throttles are not copied; sign in again. Planned test authorizations expire and snapshot bodies are removed. Active jobs and unconfirmed sandbox cleanup block a copy. The original database remains intact.

Historical local-repository incidents remain readable, but their laptop source paths are unavailable in the cloud. Start a new incident with the GitHub source before new source checks or publishing. For a genuinely new empty workspace, run the existing `app.manage create-admin` operator command locally with the cloud `DATABASE_URL` configured; there is no public administrator-creation endpoint.

## Investigations and repository source

`JOB_EXECUTION=vercel` dispatches a durable workflow before the request returns. Each of the seven agents runs as a separate step; source, provider credentials, and agent results stay in the application database, while workflow arguments contain identifiers only. Completed agent checkpoints are reused. A PostgreSQL transaction lock serializes duplicate deliveries, and the job's dispatch generation and workflow owner reject stale executions after retry.

Provider calls interrupted before their result is saved may repeat. Completed steps do not repeat their provider work. Cancellation takes effect at agent boundaries; it does not claim to abort an already-running provider request. Manual investigation retry retains the existing three-attempt limit. Failed dispatches and terminal platform failures become visible saved job failures; opening an incident reconciles platform state. A queued job whose dispatch never recorded a run ID is marked failed after two minutes, allowing a manual retry.

Select **Configured GitHub repository** for cloud investigations. Each incident pins the configured repository and a commit SHA. Evidence, patch validation, and isolated test plans use that revision. Only regular allowlisted UTF-8 files are read; symlinks, hidden paths, secrets, oversized blobs, and truncated/oversized repository trees are rejected. Blob hashes are verified. Publishing still requires an approved fix plus separate human authorization. A changed repository or advanced base branch blocks a GitHub-source PR and requires a fresh investigation.

## Isolated tests

Build the application-owned runner, not a Dockerfile from the investigated repository. Use Docker Buildx, including on Apple Silicon:

```bash
docker buildx build --platform linux/amd64 --load -f runner/Dockerfile.vercel -t autorca-runner-vercel runner
```

Publish that image to [Vercel Container Registry](https://vercel.com/docs/container-registry), using the backend project's account, and set `SANDBOX_VERCEL_IMAGE` to its immutable `vcr.vercel.com/TEAM/PROJECT/IMAGE@sha256:...` reference. Wait for VCR to report the image as **Ready**. Sandbox requires an optimized `linux/amd64` image; an ARM-only image built on an Apple Silicon laptop is insufficient. Confirm the account's resource availability and billing before provisioning or publishing. Local Docker image IDs are not Vercel registry references.

With `SANDBOX_PROVIDER=vercel` and `SANDBOX_ENABLED=true`, each approved before/after phase gets a fresh nonpersistent microVM. It has no application credentials, exposed ports, persistent drives, or network access. The trusted image runs as UID 65534. The VM has one vCPU and 2048 MB; its test process has a 256 MB address-space limit, 32-process limit, bounded file size, and a fixed unittest/pytest entrypoint. The API retains the 1 MiB snapshot/patch budget and ten-minute authorization expiry. Output is capped at 64 KiB, execution at the configured deadline (5–120 seconds), and the VM has a separate hard session deadline.

An authorized validation step has zero automatic retries. The SDK is instructed not to replay a process after it starts. Interrupted tests require a new plan and authorization. If results were saved before an interruption, recovery preserves them. Cleanup is attempted on every exit; unconfirmed cleanup blocks new runs. **Retry sandbox cleanup** retries destruction only and never executes the tests again.

Sandbox availability in the UI means configuration is present; actual project permission and image access are confirmed only by an authorized run. Keep `SANDBOX_ENABLED=false` until the trusted registry image is ready if deploying the investigation workflow first. The full feature set requires enabling and validating Sandbox.

## Verification before production

Local verification covers SQLite and real disposable PostgreSQL, workflow fencing/cancellation, a real Vercel Workflow SDK run using its local embedded queues, the trusted runner image's before/after tests, frontend compilation, and browser flows. These do not substitute for hosted checks.

For a Preview deployment, verify:

1. Database migrations and account transfer or initialization; restart/deploy without losing incidents.
2. Sign-in, cookie security, CSRF, viewer restrictions, and rejection of direct backend requests without the shared token.
3. A bundled investigation completing all seven hosted workflow steps, with cancellation and retry visible in the UI.
4. A Gemini investigation against the bundled sample, then read-only source access to a disposable GitHub repository.
5. An explicitly approved before/after Vercel Sandbox test run and confirmed cleanup, including a deliberately failing test.
6. Draft PR publishing only in a disposable repository after separate approval and publication consent.

Production deployment follows successful Preview checks and correct Production resources. No hosted deployment, database provisioning, registry upload, or real Sandbox execution is performed merely by installing the code changes in this repository.

## References

- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
- [Python durable workflows](https://vercel.com/kb/guide/python-and-durable-workflows) — currently a beta SDK; versions are pinned.
- [Vercel storage integrations](https://vercel.com/docs/storage)
- [Sandbox Python SDK](https://vercel.com/docs/sandbox/python-sdk-reference)
