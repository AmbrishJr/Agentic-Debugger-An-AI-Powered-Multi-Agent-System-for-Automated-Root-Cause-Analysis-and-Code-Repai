i n# Workspace access and operations

Authentication is enabled by default. There is no default administrator password or public registration endpoint. Create the first administrator from the project root:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.manage create-admin --username admin
```

Passwords are entered with a private terminal prompt. The command uses the same root `.env` and database as a backend launched from the root. To recover a forgotten password, use `reset-password --username admin` instead; it revokes the account's sessions. Docker operators run the same module through `docker compose exec backend`.

All accounts share incident data. Administrators manage settings and accounts; editors investigate, authorize tests, review, publish explicitly authorized draft PRs, and confirm resolution; viewers read records and can change their own password or sign out. This is workspace role control, not tenant isolation or SSO. The final active administrator cannot be removed or demoted. Changing an account's role or active state revokes its sessions.

Passwords use per-account random salts with PBKDF2-SHA256 at 600,000 iterations. Login failures are throttled per normalized username. Opaque session tokens are hashed before database storage, expire after the configured lifetime, and use HttpOnly/SameSite=Strict cookies. Mutations require a session-bound CSRF token. Password changes revoke all sessions for that account. No secrets belong in frontend public environment variables.

Keep the default loopback bindings. For externally reachable deployment, configure an HTTPS reverse proxy, `SECURE_COOKIES=true`, `PUBLIC_ORIGIN`, operator-level network/rate controls, backups, and an appropriate retention policy. The current local verification does not certify a public production deployment. `AUTH_ENABLED=false` is only for isolated development; the Compose stack always enables authentication.

Investigation jobs are durable SQLite records, consumed by one process holding a database-specific file lock. Native development embeds the consumer; Compose has a separate worker. Completed agent outputs are checkpoints. Incomplete agent calls can repeat after a crash, including a potentially paid provider call. Automatic recovery and manual retries share a three-attempt ceiling. Cancellation waits for the active agent call to finish. Retrying an earlier failed step invalidates and regenerates its downstream pending proposal.

Test authorizations are different: interrupted isolated runs are cleaned up and marked failed, never silently replayed. Prepare and authorize a fresh plan. The Docker controller is available with the native backend; app containers do not receive a Docker socket. See [runner boundaries](sandbox.md).

Approving a patch never marks an incident resolved. Resolution requires a separate human summary and evidence reference; reopening preserves both confirmations and reasons in the audit history. These are human assertions, not independent verification by a deployment or monitoring integration.
