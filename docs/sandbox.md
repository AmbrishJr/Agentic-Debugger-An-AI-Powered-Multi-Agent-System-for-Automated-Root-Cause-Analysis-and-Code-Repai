# Isolated repository validation

The application supports explicitly authorized **before/after Python unittest or pytest runs in restricted Docker containers**. The bundled deterministic demo still works without Docker. Repository code never falls back to host execution.

## Local setup completed

Docker CLI and Colima are installed. A dedicated `autorca` Linux VM uses 2 CPUs and 2 GB memory; the existing default Docker context was not changed. The trusted runner image was built and its immutable image ID configured in the ignored root `.env`.

Restart the backend to load this configuration. In **Review fix → Isolated repository tests**, select every patch target and required Python source/test files, prepare a plan, inspect its file hashes and limits, and explicitly authorize execution. Both runs finish before approval/rejection becomes available again.

Manage the VM independently of the app:

```bash
colima start --profile autorca --cpu 2 --memory 2 --disk 10 --vm-type vz --mount-type virtiofs --activate=false
docker --context colima-autorca ps -a
colima stop --profile autorca
```

Stop the backend before stopping the VM if a test run is active. The VM can remain stopped whenever you are not using isolated tests; the UI then reports the runner unavailable.

## Fresh installation

On Apple Silicon macOS:

```bash
brew install docker colima
colima start --profile autorca --cpu 2 --memory 2 --disk 10 --vm-type vz --mount-type virtiofs --activate=false
docker --context colima-autorca build -t autorca-runner:local runner
docker --context colima-autorca image inspect autorca-runner:local --format '{{.Id}}'
```

Set the following in the backend `.env`, using the returned image ID, then restart FastAPI:

```dotenv
SANDBOX_ENABLED=true
SANDBOX_IMAGE=sha256:<64 hexadecimal characters from image inspect>
SANDBOX_DOCKER_CONTEXT=colima-autorca
SANDBOX_TIMEOUT_SECONDS=30
```

Docker Desktop or a local Linux Docker daemon can also be configured by selecting its local Unix-socket context. Remote network Docker endpoints are rejected. The daemon must support memory, CPU quota, and PID limits. Images with declared volumes are rejected, and execution uses `--pull=never`. Build only the application-owned `runner/Dockerfile`, never a repository-supplied Dockerfile. Rebuilding requires updating the image ID and invalidates outstanding plans.

This adapter supports the **native local backend**. The application Compose stack intentionally contains neither Docker CLI nor a mounted Docker socket. A separate runner service is needed for that deployment; do not mount the host Docker socket into untrusted test containers.

## Fixed execution profile

The trusted bootstrap runs with Python isolated mode, reads the bounded source snapshot from stdin, writes it into ephemeral `/workspace`, and discovers `test*.py`. No tests discovered means a nonzero exit. Include required package `__init__.py` files when selecting nested tests. The trusted image includes the standard library and pinned pytest 8.3.5. Pytest disables automatic third-party plugin loading. Select the profile before preparing a plan; the authorization hash binds it. Installing dependencies or selecting arbitrary shell commands is not supported; dependency-heavy projects need an independently reviewed image.

Each before/after phase gets a fresh container with:

- No network, host mounts, Docker socket, or application credentials.
- Non-root UID/GID 65534, all Linux capabilities dropped, and no-new-privileges.
- Read-only root, no healthcheck, and no persistent container log.
- Two 16 MB `noexec,nosuid,nodev` tmpfs areas for source and temporary files.
- 256 MB RAM including swap, 0.5 CPU, 32 processes, and 128 open files.
- A 5–120 second configurable deadline and 64 KiB combined raw output budget.
- Forced removal after success, failure, timeout, or excessive output.

Flags follow the [Docker run reference](https://docs.docker.com/reference/cli/docker/container/run/). Real checks verified non-root execution, dropped capabilities, no outbound connection, read-only root, absent credentials/socket, memory/PID limits, timeout, bounded output, and cleanup. See [sandbox-validation.json](sandbox-validation.json).

## Plans, consent, and audit

Plans include at most 32 allowlisted Python files and 1 MiB including every proposed file. Secret-like content is rejected. The authorization hash binds the run ID, source manifest, proposed code, and runner policy. Plans expire after ten minutes and are usable once. Changed source/test files, changed image/policy, reused plans, and authorization after the final review are rejected. One isolated run may execute at a time.

The `validation_runs` table stores manifests, hashes, policy, authorization time, and measured results. Snapshot bodies are discarded after execution. Expired unused bodies are purged on startup or when validation records are accessed. Reports read the latest validation results. Approval is blocked during execution or after infrastructure failure. Startup marks interrupted runs failed and attempts cleanup; it does not silently rerun code.

## Security limits

Docker does not prove safety against container or kernel escapes. Linux containers share a kernel; Colima adds a Linux VM on macOS, and the VM's own shared directories remain part of the threat model. Use dedicated disposable infrastructure for hostile repositories.

The backend controller enforces the deadline. If it or the Docker daemon becomes unavailable, containers may need operator cleanup; startup retries cleanup and records failure. An unresolved cleanup failure blocks subsequent runs until cleanup succeeds on restart. Resource limits remain in force. Test output and counts originate in repository code and can be forged. A zero exit is not proof of coverage or correctness, and a nonzero baseline is not proof that the intended business bug was reproduced. Inspect the output and code.

## Repeat the real checks

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/validate_sandbox.py --execute
cd frontend
CI=1 AUTORCA_E2E_SANDBOX=1 npm run test:e2e
```

These use synthetic source and isolated test databases. Normal pytest tests mock the Docker adapter and do not launch containers.

The output-limit verification exposed a blocked attach-stream cleanup timeout. The controller now closes that stream before removing the container; the repeated real timeout/output checks passed and left no test containers.

## Independent proof gate

Repair outcomes now distinguish isolated process results from verified repair. Test filenames, test-directory contents and known test configuration/support paths cannot be patched in a validation plan. All selected files, including tests, are hashed and checked again when the worker starts. Changed or expired queued plans fail without execution.

The bundled proof gate requires the exact application-owned checkout fixture. Source, proposed replacement and independent test digest must match the reviewed fixture; unittest must report the expected two failures/two errors before, four passing tests after, and successful bounded execution/cleanup. The proof retains content provenance and runner policy. Generic repository output is never trusted as equivalent proof. A separate registered JSON contract gate is described below. Pytest remains supported for measured execution but cannot earn either proof scope.

The existing host-run demo is explicitly labeled and stays PATCH_UNVERIFIED. Test process errors, timeouts, truncated output and failed cleanup block positive outcomes. No additional code executes on the host if isolation is unavailable.

No database migration is required: artifacts use existing JSON columns. Roll back application code without dropping data; old clients ignore additive outcome fields. Recreate pending plans after changing versions because test-manifest policy changed. Rollback removes the stricter verification presentation/guards, so do not treat old `passed` labels as repair verification.

## Reviewed test expectations

The review page can now attach a versioned reproduction/regression specification to a unittest plan. It names expected failing tests and exception types, required regressions, and a reviewed rationale. The server binds these to existing incident test hashes, records the reviewer, and includes the declaration in authorization and execution integrity checks. Existing runner images work without rebuilding: the evaluator reads their bounded verbose unittest output and summary.

Wrong exceptions, unrelated failures, missing or skipped tests, inconsistent discovery and incomplete observations fail the required specification check. Matching output remains an untrusted observation and does not qualify generic repairs as VERIFIED. The exact bundled proof remains a separate requirement. Execution consent, isolation, expiry and cleanup behavior are unchanged. [Verification specification operations](verification-specifications.md) documents the API, supported unittest formats and remaining independent-oracle work.

## JSON behavioral oracle

The Docker-only `python-json-stdio` profile uses an application-owned driver command in the existing pinned image. It stages approved source-only files and invokes the entrypoint once per input/version in fresh containers. The controller retains expected answers and compares returned JSON; test result messages from candidate code are not accepted as telemetry. The authorization hash includes the driver and full reviewed contract. The existing resource, network and cleanup boundaries apply, with at most eight sequential invocations per plan and an expiry check before each invocation.

Failed/malformed observations stop further execution. Redacted or invalid UTF-8 output cannot match an expected response. Per-invocation process exits are retained separately from aggregate semantic results. Vercel is unsupported for this profile and fails closed. No new image, migration or external service is needed. See [JSON contract operations](json-behavior-contracts.md) for the interface and explicit real-check command. Independent test provenance remains required before broadening VERIFIED.

Docker output capture now drains stdout and stderr separately under one 64 KiB budget, preserving each stream's order. Displayed legacy test output concatenates stderr then stdout; it is not a chronological transcript across streams. JSON contracts reject any stderr bytes. The capture policy is included in the authorization hash; recreate pending plans made before this change.

## Registered JSON contract proof

A JSON contract can qualify for scoped VERIFIED when its declaration and sources were registered before investigation, reviewed by a different authenticated account, frozen at investigation startup, and then satisfied under the normal one-use isolated plan. The controller rechecks the provenance ledger, plan/patch binding and actual recorded responses; a match flag or approval alone is insufficient. No new runtime permissions, image or execution profile is introduced. Expected answers stay outside candidate execution. See [contract provenance](contract-provenance.md) for the API, account-level trust boundary, synthetic integration command and limitations.
