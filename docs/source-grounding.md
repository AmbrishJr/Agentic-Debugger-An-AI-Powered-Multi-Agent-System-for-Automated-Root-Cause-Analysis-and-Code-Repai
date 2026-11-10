# Source grounding operations

This slice adds local revision pinning and precise citation validation to the existing workflow. It does not introduce new integrations, model calls, environment variables or parser dependencies.

## Snapshot contract

At submission, allowlisted local/sample paths are enumerated using existing traversal, symlink, hidden-file and file-size restrictions. At most 500 files and 16 MiB of UTF-8 source are hashed. Only hashes, revision and metadata enter the new `incidents.repository_snapshot` JSON column; raw source is not stored there. Evidence subsequently stores bounded redacted source as before.

Git is read through fixed `rev-parse` and `ls-tree` commands with a restricted environment, literal pathspecs, disabled fsmonitor/hooks, lazy fetching and transport protocols, and no global/system config. Credential helpers and terminal prompting are disabled as well. No checkout, status hook, external diff, filter or repository code runs. For Git sources, HEAD and captured-file modifications are recorded separately. Untracked captured files count as modified. A clean flag does not describe omitted/ignored/deleted files elsewhere in the repository. Subdirectory roots are supported.

Content snapshot IDs derive from the capture metadata and file hashes, independent of the physical root. A separate repository-binding digest prevents silently switching roots. Non-Git folders and repositories without a first commit use content snapshots; they do not receive fake commit identifiers. GitHub sources retain their immutable remote revision behavior.

Reads check the saved manifest integrity, repository binding, HEAD and requested file bytes. The workflow rechecks collected sources before and after analysis and before patch generation. Review approval and initial PR publication also recheck collected source. Pinned source errors preserve partial workflow results and require a new incident. Saved historical evidence stays readable even if the live source later changes. No mutable root is silently repinned on retry.

## Citations and uncertainty

Source text redaction preserves line numbering. A citation must match a known evidence ID, kind, path, original hash, snapshot ID, commit ID and exact full lines from the redacted evidence. Quotes may cover at most 50 lines and 8,000 characters. Log references point to the canonical saved redacted log, not an external logging service.

New model outputs include bounded observation citations and up to three structured hypotheses. Supporting evidence, contradicting evidence and missing diagnostic checks are stored separately. The first-ranked hypothesis is the repair candidate; unresolved contradictions or diagnostic checks prevent its repair proposal. References remain untrusted data and confer no tool capability. Invalid references fail analysis instead of silently disappearing from a successful report.

The UI calls these reported observations and evidence-support labels. Exact quotations are checked, but causal interpretation, semantic entailment and confidence calibration are not. A model can still misinterpret a valid quotation. Runtime/provider failures remain different from a deliberate insufficient-evidence result. This slice does not broaden VERIFIED beyond the independent controlled-fixture gate.

## Migration and rollback

Migration `005_source_snapshots.py` adds a non-null JSON column with an empty-object default. Existing rows retain their data and are displayed as legacy without a pinned manifest. SQLite upgrade and downgrade were tested against a pre-existing incident. PostgreSQL uses the same additive JSON migration; no live PostgreSQL migration was run in this environment.

Local startup continues to migrate through the existing app mechanism. Hosted startup has migration disabled; use the established hosted migration procedure before deploying new code. Stop workers during an application rollback. Old code can run with the extra column retained, which preserves provenance. Downgrading to `004` removes snapshot metadata but preserves other incident data; back up provenance before an explicit schema downgrade. Recreate in-flight incidents that lack precise citations rather than retroactively claiming new validation for old model output.

## Evaluation

Independent fixture tests are now staged before incident submission so their file hashes are pinned. They remain excluded from selected evidence and provider payloads; the loader rejects input stack frames that reference those test filenames. Expected causes and reference patches remain outside the source tree. The evaluator records the incident snapshot and an additional exact-citation metric. Its existing reference-ID metric has a changed denominator because unsupported legacy ID-only references are no longer retained as citations; comparisons must account for that convention change.

No provider calls are required for these checks. Live-model accuracy and provider compatibility of the expanded schema need a separately authorized live run with a selected model and spending limit.
