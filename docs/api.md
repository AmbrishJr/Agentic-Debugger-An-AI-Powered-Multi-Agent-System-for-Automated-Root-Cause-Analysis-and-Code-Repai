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
