# Controller-owned JSON behavior checks

The `python-json-stdio` profile checks a Python command-line interface using a controller-owned oracle. For each reviewed input, the program runs in a fresh restricted Docker container. The controller compares the returned JSON with expected values kept outside the container. Repository code never receives the contract's expected answers, case roles, IDs, rationale or other cases through the runner payload.

The response is the behavior under test, not a claim that a test passed. Printing a unittest summary or a forged success report does not satisfy a numeric/string/object contract. Returning the required value for a supplied input does satisfy that case, even if the implementation is overfitted; finite tests cannot establish correctness for all inputs.

Ad hoc JSON contracts do not grant VERIFIED. A separate [registered-contract workflow](contract-provenance.md) can establish account-level provenance before investigation and qualify a matching isolated run for verification of those registered cases only. Comparison alone does not establish independent repair proof or diagnosis causality.

## Using the review page

Select **JSON behavior contract (Docker)** as the execution profile. Select Python source files only, including the entrypoint; test and known test-support files are excluded. Enter a contract such as:

```json
{
  "entrypoint": "main.py",
  "rationale": "The increment request reproduces the observed off-by-two result; zero remains unchanged.",
  "cases": [
    {"id": "increment", "role": "reproduction", "input": 2, "baseline": 1, "expected": 3},
    {"id": "zero", "role": "regression", "input": 0, "baseline": 0, "expected": 0}
  ]
}
```

The program must read one JSON value from stdin and emit exactly one JSON value to stdout, with no stderr diagnostics or extra values. The adapter captures stdout and stderr separately; any stderr output invalidates a JSON observation. For example, `main.py` can read with `json.load(sys.stdin)` and serialize its result with `json.dumps`. No interface adapter or candidate code is generated automatically. A module that only defines functions and prints nothing fails this profile, even if it exits with code zero.

Review the inputs, known incorrect baseline outputs and expected results, acknowledge review, and prepare the plan. The plan shows the contract and the maximum number of fresh invocations before the existing separate execution-consent step. Each case runs on original and patched source. The controller stops after malformed output, execution failure, expired authorization or uncertain cleanup.

## API and integrity

`POST /api/incidents/{id}/validation-plans` accepts:

```json
{
  "files": ["main.py", "logic.py"],
  "profile": "python-json-stdio",
  "json_contract": {
    "version": 1,
    "reviewed": true,
    "entrypoint": "main.py",
    "rationale": "Reviewed increment and zero behavior against the incident.",
    "cases": [
      {"id": "increment", "role": "reproduction", "input": 2, "baseline": 1, "expected": 3},
      {"id": "zero", "role": "regression", "input": 0, "baseline": 0, "expected": 0}
    ]
  }
}
```

JSON contracts and unittest `verification_spec` declarations cannot be combined. A JSON profile requires its contract; other profiles reject it. Version 1 requires 2–4 distinct case IDs, both reproduction and regression roles, and values no larger than 4 KiB each. Reproduction baseline and expected values must differ. Regression baseline and expected values must match. Secret-like contract content is rejected.

The bound declaration is stored in `result.verification_spec` with `kind: "json-stdio"`, oracle version, server-assigned reviewer/time, source hashes and incident snapshot identity. Its content, the complete application-owned driver command, source manifest, patch and runtime policy are bound into the authorization hash. Existing expiry, authorization reuse, source/patch immutability and execution-time checks still apply. Expected answers are available to reviewers in the API/UI; they are withheld from candidate execution and are not added to investigation/model evidence.

The fixed driver stages only the approved sources and receives one invocation containing `entrypoint` and `input`. It executes inside the existing pinned Docker image using Python directly, with no shell, host mounts, network or application credentials. The source allowlist, 32-file/1 MiB snapshot limit, non-root identity, resource limits, output cap and cleanup policy remain unchanged. No image rebuild or installation is required. Container names are reused sequentially only after the preceding invocation has been removed.

## Comparison and outcomes

The host controller accepts observations only after exit zero, complete output and confirmed cleanup. It rejects duplicate JSON keys, non-finite/overflowing numbers, multiple values, invalid JSON, redacted output and invalid UTF-8. Comparison uses canonical JSON: object key order and whitespace do not matter, array order does, and boolean/integer/float representations are distinguished (`false`, `0`, and `0.0` are different).

| Assessment | Condition |
| --- | --- |
| `matched` | Every reproduction has the declared incorrect original value and required patched value; all regressions match before and after |
| `not_reproduced` | All reproduction inputs already return their expected values on original source; regressions and patched behavior also pass |
| `mismatch` | Unexpected baseline behavior, partial reproduction across declared cases, wrong patched results or a regression failure |
| `inconclusive` | Invalid/absent JSON, nonzero process exit, resource/output failure, expired authorization or uncertain cleanup |

Mismatch/inconclusive required checks produce VALIDATION_FAILED. Not-reproduced produces NOT_REPRODUCED unless another explicit check fails. A matching ad hoc contract remains PATCH_UNVERIFIED. The assessment always has `independent_proof: false` and `comparison: "controller-json-equality-v1"`: the resolver must additionally validate immutable pre-investigation provenance, authorization and integrity before a registered contract can qualify.

`specification_assessment.cases` retains each actual before/after process result and comparison booleans. The enclosing before/after objects describe aggregate **semantic contract checks**, with `measurement: "contract_comparison"` and null exit codes. A wrong baseline JSON value can therefore reproduce the incident while the actual process exits zero; the artifact never invents a nonzero process exit. Reports and incident/patch responses preserve the same latest artifacts.

## Operations and reproduction

This first version supports Docker only. Selecting it with Vercel fails closed; no alternative runner or host execution is attempted. The existing unittest/pytest profiles continue to work unchanged. No database migration, service or new environment variable is added. Rolling back preserves completed artifacts but specification-bound pending plans must be recreated.

Run the real synthetic adapter checks explicitly with an already configured immutable runner image:

```bash
backend/.venv/bin/python scripts/validate_json_contract.py --execute
```

The command makes no provider calls, installs nothing and writes an ignored JSON artifact at `data/evaluations/json-contract-isolated.json`. It checks correct repair, wrong repair, already-correct baseline, stderr masquerading as a response, and forged test output. Missing isolation is recorded as skipped. These adapter checks are kept separate from accuracy benchmark results. Normal backend tests mock execution and do not execute repository code on the host.

Remaining limits: Python CLI JSON interfaces only; no exception-output, network-service, interactive or arbitrary framework contract. Comparisons do not authenticate test authorship, establish semantic causal relevance, prevent test overfitting, or measure live-model diagnosis accuracy. The registered-contract policy establishes separate-account sequencing; it cannot prove separate human identities or rule out collusion.
