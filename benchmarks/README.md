# Controlled accuracy evaluation

`v1/inputs.json` contains eight synthetic incidents (six development, two held-out). `v1/oracles.json` contains expected causes, localizations, independent tests and reference patches. Only public sources, incident logs and selected paths enter the existing investigation pipeline. Independent tests are staged before submission so their hashes are pinned, but are excluded from selected evidence and provider payloads. Input stack frames naming those independent tests are rejected. Ground truth never enters prompts or incident memory.

Run from the project root:

```bash
backend/.venv/bin/python scripts/evaluate.py --output data/evaluations/offline
```

The CLI creates and removes a disposable SQLite database and source tree. It disables GitHub credentials, uses inline jobs, and disables model credentials and sandbox execution by default. Ordinary demo validation can execute only the application's existing exact trusted constants on the host. Additional fixture code is parsed in tests, never executed on the host.

The bundled demo case produces a proposed patch. Other cases exercise the real demo abstention path; this dataset does not expand demo diagnosis capabilities. A blank diagnostic log is represented by `[No diagnostic logs supplied.]` to satisfy the existing intake contract. Source ordering follows the chosen retrieval strategy; localization scores measure retrieval order, not model ranking. Independent test files must use protected test filenames/directories so symbol expansion cannot expose their contents.

## Source retrieval comparison

The default is `--source-retrieval symbols`, matching new application investigations. Use `--source-retrieval stack` for the previous path-based strategy. Selected-file hints remain enabled unless explicitly removed. Compare both without those hints:

```bash
backend/.venv/bin/python scripts/evaluate.py --source-retrieval stack --without-file-hints --output data/evaluations/retrieval-stack
backend/.venv/bin/python scripts/evaluate.py --source-retrieval symbols --without-file-hints --output data/evaluations/retrieval-symbols
```

The dataset and application source hashes must match before comparing results. JSON records both settings, each case's coverage summary, and per-file selection reasons in evidence. Submitted stack traces remain available. This experiment measures localization with stack input, not blind diagnosis. Initial Top-3 results are 5/6 versus 6/6: symbol retrieval adds `invoice.py`, the static caller of the function in the cross-file case's stack. Top-1 remains 5/6. Neither mode improves demo diagnosis or establishes live-model accuracy. See [retrieval limits](../docs/source-retrieval.md) and the latest [verification checkpoint](../docs/IMPLEMENTATION_PROGRESS.md).

## Isolation and live runs

To explicitly authorize isolated tests using an already configured runner:

```bash
backend/.venv/bin/python scripts/evaluate.py --authorize-isolated --check-fixtures --output data/evaluations/isolated
```

`--authorize-isolated` permits generated proposals to use the normal one-use validation plan flow. `--check-fixtures` additionally executes original/reference fixture pairs through the same restricted runner. Reference-patch results never count as agent repairs. Unavailable runners produce recorded skips. No host fallback, image installation, VM startup, GitHub publication or deployment occurs. The runner uses existing `SANDBOX_*` configuration; no new environment variables are required.

Live evaluation is a separate explicit action, incurs provider usage, and requires all of:

```bash
backend/.venv/bin/python scripts/evaluate.py --mode live --allow-live --provider openai --model MODEL_ID --max-cases 2 --split development --output data/evaluations/live
```

Use an available model for the selected provider and configure its existing backend API key. This command was not run during implementation. Case limits are not monetary budgets. Provider usage/cost telemetry is currently unavailable and recorded as unknown; demo cost is zero because no provider calls occur. Existing provider timeout/retry behavior applies. Demo, live and mocked contract tests are never pooled.

## Scoring and adjudication

Results are JSON plus Markdown, including dataset hash, application commit, dirty-tree flag, application source digest, configuration, predictions, errors, and explicit exclusions. The source digest covers backend application and frontend source, not secrets or environment files.

Free-text diagnoses remain unscored until reviewed. A judgeable case that fails or abstains is incorrect, not excluded. `rca_accuracy_scored` reports correct/scored cases alongside scoring coverage and unscored judgeable counts; it must not be advertised as full-dataset accuracy while coverage is incomplete. Missing-evidence cases are scored separately through abstention precision/recall.

A reviewer can supply `--adjudications decisions.json`, a JSON list:

```json
[
  {
    "case_id": "percentage",
    "prediction_sha256": "COPY_EXACT_HASH_FROM_RESULT",
    "correct": true,
    "reviewer": "reviewer identifier",
    "rationale": "Explain the independent comparison with the expected cause."
  }
]
```

The hash binds decisions to exact analysis, collected evidence and patch output. Mismatched hashes or duplicate decisions fail rather than silently scoring different predictions. Do not tune prompts on held-out answers. The two held-out cases are both uncertainty cases; this small starter set does not establish held-out diagnosis accuracy across bug categories.

Metrics:

- Top-1/Top-3: correct source in the first one/three collected source references, divided by file-localizable cases. Selected paths are explicit inputs; this is not blind localization.
- Citation-reference validity: resolvable IDs with matching content hash and in-bounds ranges / all hypothesis citation references. It does not measure semantic support for claims.
- Patch application: diffs successfully applied by `git apply` and matching saved proposed contents / attempted patches. Missing Git is an explicit exclusion.
- Verified repairs: independently verified proposed repairs / all repair-eligible cases, including unavailable-runner cases in the denominator.
- Validation phase coverage: executed before/after phases / two required phases per repair-eligible case. This is not a test-count or code-coverage claim; arbitrary repository test counts are untrusted.
- Latency: median and nearest-rank p95 investigation, validation and patch-check duration. Separate reference checks are excluded.
- Zero denominators and unavailable monetary costs are `null`, rendered as not available.

No accuracy threshold is asserted for this initial demo baseline. Harness integrity, honest denominators and fail-closed outcomes are the first acceptance gates.

The grounding upgrade adds `exact_citation_validity`: exact structured quotations that match identity, revision, hash and line range / all structured observation and hypothesis citations. Repeated citations in different claims count separately; this still does not measure semantic entailment. Incident snapshot metadata is retained in each result.
