# Reviewed reproduction and regression specifications

An isolated test suite can fail for a reason unrelated to an incident. A reviewed verification specification records which tests should reproduce the incident, the exception each should report, and which regressions must pass after the patch. The backend compares those expectations with the before/after observations and keeps the result separate from independent proof.

This feature does **not** broaden VERIFIED eligibility. Generic repository code can forge unittest output. Even a matching specification records `independent_proof: false`; generic proposals remain PATCH_UNVERIFIED when the other checks pass. Only the existing exact application-owned fixture can qualify as VERIFIED under its separate proof gate. Human review of a specification is an attestation, not proof that its author was independent of the patch author.

## Review workflow

1. Open a pending patch's review page and select its source files and existing tests.
2. Choose `unittest` and enable **Add reviewed reproduction and regression expectations**.
3. Enter each expected baseline failure as `module.Class.test_method | ExpectedException`, one per line. Declare every baseline failure; unrelated failures are not accepted as reproduction evidence.
4. Enter required regression IDs, one per line, and explain why the tests cover the incident. Reproduction tests must also pass after the patch, whether or not repeated in the regression list.
5. Review the tests and acknowledge the specification. Prepare the plan, inspect its expectations and file hashes, then separately authorize isolated execution using the existing consent control.

The reviewer account and review timestamp come from the server. The server binds each test ID to a file hash and the incident's source snapshot. Tests must already belong to that pinned snapshot, captured before patch generation. Changed tests require a new incident. Legacy incidents without a snapshot cannot use this feature. There is no model-generated test/specification path.

Reviewing a specification does not authorize execution or approve the patch. The plan retains the existing ten-minute expiry, one-use authorization, fixed runner profiles and isolation policy. Missing isolation never starts repository code on the host.

## API example

`POST /api/incidents/{id}/validation-plans` accepts an optional `verification_spec`:

```json
{
  "files": ["pricing.py", "test_pricing.py"],
  "profile": "python-unittest",
  "verification_spec": {
    "version": 1,
    "reviewed": true,
    "rationale": "The zero-rate test reproduces the reported division error; ordinary rates must remain correct.",
    "reproduction": [
      {
        "test_id": "test_pricing.PricingTests.test_zero_rate",
        "expected_exception": "ZeroDivisionError"
      }
    ],
    "regressions": [
      "test_pricing.PricingTests.test_zero_rate",
      "test_pricing.PricingTests.test_ordinary_rate"
    ]
  }
}
```

The example assumes those files/classes/methods exist in the incident snapshot. Expected exceptions are exact names, not regular expressions or substring matches. The rationale is bounded and rejects secret-like content. A specification allows at most 20 reproduction tests and 40 regression IDs; IDs must be unique within each role. All existing file/byte limits still apply.

The returned `result.verification_spec` contains the declaration, authenticated reviewer, review time, snapshot ID and test path/hash bindings. The authorization hash covers this entire artifact alongside the source manifest, patch and runner policy. Authorization and execution recheck the binding. A post-execution plan/patch change discards positive proof and observations. Worker-restart errors preserve the declaration for audit; consumed authorization is never replayed.

After execution, `result.specification_assessment` records per-test reproduction/regression observations, reasons, and the explicit proof limitation. The same artifacts appear in incident details and patch responses under `validation_result.isolated`, and report downloads under `validation.isolated`.

## Observation and outcome rules

| Assessment | Interpretation | Effect on repair outcome |
| --- | --- | --- |
| `matched` | Every declared baseline failure reports its expected exception; reproduction and regression tests pass after the patch; no extra baseline failures or changed discovery | Does not grant VERIFIED; the existing independent proof gate still applies |
| `not_reproduced` | Complete original and patched suites pass, including every required ID | NOT_REPRODUCED unless another explicit check failed |
| `mismatch` | Wrong/missing expected failure, unrelated baseline failure, or a patched test failure | VALIDATION_FAILED |
| `inconclusive` | Missing/ambiguous observations, skipped tests, inconsistent counts/exit status, changed discovery, or incomplete execution/cleanup | Required specification check errors; VALIDATION_FAILED |

The evaluator requires a complete verbose unittest result and exactly one matching suite summary. Duplicate test records, duplicate summaries, missing IDs, skips, expected failures and unexpected successes cannot satisfy the specification. Every observed patched test must pass, including tests beyond the declared minimum. Failure details must identify the reported exception for the corresponding failing test. Before/after suites must report the same IDs. Timeouts, truncated output and uncertain cleanup are never accepted as positive evidence.

## Compatibility and limits

Specifications are optional; existing clients, plans without specifications, pytest execution, repair-outcome fields and review workflows remain supported. No database migration, runner image rebuild, dependency, external service or environment variable is required. Artifacts use the existing JSON result field. Historical results are not rewritten. Rolling code back retains data; a pending specification-bound plan must be recreated because older code cannot validate its authorization hash.

Version 1 supports directly declared methods in top-level Python unittest classes under selected `test*.py` modules. It parses source without importing it. Inherited/dynamically generated tests, parametrized subtest failure formats, test docstrings that change verbose output, custom runners and pytest specifications are unsupported; incomplete observations fail closed. This is conservative evidence collection, not authenticated test telemetry or semantic validation that the test actually represents the incident. The full test suite still runs in each phase; IDs describe expectations rather than changing the runner command.

Next work toward generic VERIFIED repairs requires an oracle whose observations repository code cannot forge, independent test provenance, and separately reviewed failure-attribution/regression policy. These requirements cannot be replaced by matching stdout or a review checkbox. See [sandbox operations](sandbox.md) and the fourth checkpoint in [implementation progress](IMPLEMENTATION_PROGRESS.md).

The fifth slice adds a separate [controller-owned JSON behavioral oracle](json-behavior-contracts.md) for Python CLI interfaces. It compares actual responses with withheld answers rather than interpreting candidate test reports. Unittest observations described here retain their original trust limitation; independent test provenance and attribution are still required for generic VERIFIED outcomes.
