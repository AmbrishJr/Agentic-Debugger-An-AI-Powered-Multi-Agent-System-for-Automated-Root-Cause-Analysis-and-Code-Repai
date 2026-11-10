# Source retrieval operations

New investigations default to `source_retrieval: "symbols"`. Administrators can choose **Source retrieval** in Settings, or update `/api/settings` with `"stack"` to retain selected-file and stack-frame retrieval. Each investigation snapshots this preference; changing settings does not alter completed investigations. Historical configurations without the field use `stack` when resumed.

`backend/app/services/source_index.py` parses Python with the runtime's standard-library AST parser. It never imports or executes repository code. Indexed metadata includes functions, async functions, classes, definition ranges, imports, and statically resolved direct calls. Comments, string literals and source bodies are not retained in the index. Existing redaction applies before parsing and before sending collected source to a provider.

## Selection and evidence

Explicit selections come first, followed by unambiguous stack paths. Stack lines, selected files, and uniquely located symbol names in logs seed dependency expansion. Direct callers/callees expand up to two hops; file imports and reverse imports expand one hop. Ties preserve original stack order, then lexical path order. Ambiguous basenames, module roots and symbol definitions are not guessed. Shadowed imports are not treated as reliable call bindings.

Automatic indexing and expansion exclude protected test, test-directory, and test-support paths. Users can still explicitly select an allowed test file as investigation evidence. Benchmark oracle tests must use protected paths and cannot be selected or appear in submitted stack frames.

The final evidence list still obeys the saved 1–10 file limit and existing 80 KB per-file limit. It contains bounded full files, preserving complete-file patch generation. Every source retains its existing snapshot, original/redacted hashes and line numbering. A file's `retrieval` metadata explains its rank and selection reasons and shows up to 20 indexed symbol ranges. The log evidence item carries retrieval coverage, cache status, parser version, skipped-file count, notices and limitations. Reports preserve both the summary and per-file metadata.

These relationships help find relevant code. They do not establish causality, citation entailment, or independent repair verification. The repair-outcome rules and approval gates are unchanged.

## Bounds and cache

| Bound | Current value |
| --- | --- |
| Repository discovery | Existing allowlist, at most 500 files |
| Python files indexed | First 200 eligible paths locally, first 40 on GitHub, sorted lexically |
| Total source read for indexing | 4 MiB; a bounded file may be read before detecting the total limit |
| AST size | 20,000 nodes/file, 200,000 nodes/index |
| Symbol count | 5,000/index |
| GitHub blob-read budget | 20 seconds, checked between requests; existing per-request timeout still applies |
| Cache | Eight indexes per process, least recently used |

Cache keys include repository identity, source snapshot, commit and parser/runtime version. Warm local requests recheck snapshot identity and the indexed bytes before reusing parsed metadata; parsing is cached, integrity checks are not skipped. GitHub cache hits avoid repeated index blob downloads at the immutable commit after the normal source-access check. Selected evidence is read and verified through the existing source reader.

The cache is in memory only, separate in each process, and cleared on restart. There is no new database migration, dependency, service, environment variable or persistent index to operate. To disable expansion, choose `stack`; to clear the index, restart the backend. Keep migration 005 from the earlier grounding upgrade applied.

## Explicit limits

Other languages, unsupported Python syntax, legacy incidents without pinned manifests, and unresolved dynamic calls retain path-based retrieval. Skipped files and exhausted index budgets are visible. The AST grammar follows the backend's Python version. This is a partial static index: dynamic dispatch, re-exports, higher-order calls, module-level call attribution and complete nested-scope resolution are not implemented. Bounds can omit useful files; this is not whole-repository analysis. Source integrity failures remain failures and do not silently repin source.

GitHub transport/cache behavior is covered by mocked contract tests. Live GitHub indexing, cloud execution and production-sized repository latency were not measured in this slice.

## Reproduce the retrieval comparison

Run both commands against the same unchanged application tree:

```bash
backend/.venv/bin/python scripts/evaluate.py --source-retrieval stack --without-file-hints --output data/evaluations/retrieval-stack
backend/.venv/bin/python scripts/evaluate.py --source-retrieval symbols --without-file-hints --output data/evaluations/retrieval-symbols
```

These are offline demo investigations using disposable databases and sources, without provider calls or additional fixture execution. `--without-file-hints` removes selected-file hints; incident stack traces remain inputs. Compare matching `dataset_sha256` and `application_source_sha256` values. The artifacts report retrieval order, not model diagnosis ranking. See the third-upgrade checkpoint in [IMPLEMENTATION_PROGRESS.md](IMPLEMENTATION_PROGRESS.md) for measured fractions and remaining gaps.
