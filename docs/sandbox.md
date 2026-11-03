# Validation and the sandbox boundary

The MVP validates Python syntax with `ast.parse` without importing or executing proposed code. It compares the current repository file against the original SHA-256 snapshot. Non-Python syntax checks and arbitrary repository tests are marked skipped.

The deterministic demo is different: the validator accepts only byte-exact `BUGGY` or `FIXED` constants owned by the application, writes those and fixed regression tests to a fresh temporary directory, and invokes `python -E -s -m unittest` with a clean environment and 15-second timeout. An AI-generated variation, changed sample, or user-provided source never reaches this runner. This is a controlled trusted fixture, **not a sandbox for untrusted code**.

## Optional trusted sample container

The bundled Dockerfile permits running the intentionally failing sample tests inside a container:

```bash
docker build -t autorca-trusted-sample examples/buggy-python-app
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 32 --memory 128m --cpus 0.5 autorca-trusted-sample
```

The run intentionally exits nonzero. No Docker command is triggered automatically by the web app, and Docker verification was not performed in this workspace.

## Future arbitrary-repository runner

Connect a dedicated runner service through an explicit interface accepting an immutable source snapshot, reviewed patch, allowlisted test command, resource policy, and expiring human authorization. Return exit code, bounded stdout/stderr, passed/failed/skipped counts, and runner identity. Record authorization and artifact hashes in the report.

The worker must have no production credentials, host repository write access, Docker socket access from user containers, host network, or unrestricted mounts. Use a trusted prebuilt image, non-root UID, read-only filesystem, separate temporary storage, resource/process/time limits, output limits, and a network-deny policy. Treat container escape and shared-kernel risk as unresolved until the deployment threat model is assessed; use stronger VM isolation for hostile repositories. Dependency installation needs its own reviewed network policy. Do not turn the current host fixture runner into an arbitrary command runner.
