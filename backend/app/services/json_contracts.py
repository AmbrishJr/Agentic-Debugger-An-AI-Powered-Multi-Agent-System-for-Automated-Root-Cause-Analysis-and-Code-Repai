"""Controller-owned behavioral comparisons. Expected values never enter the sandbox."""
import json
from datetime import datetime, timezone
from app.services.security import allowed_path, digest, redact

# Application-owned driver passed directly to isolated Python, never a shell or host execution.
DRIVER = '''import io,json,os,runpy,sys
from pathlib import Path,PurePosixPath
raw=sys.stdin.buffer.read(2*1024*1024+1)
if len(raw)>2*1024*1024: raise ValueError("Payload limit")
payload=json.loads(raw)
files=payload["files"]
if not 1<=len(files)<=32: raise ValueError("File limit")
for name,content in files.items():
    p=PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\\\\" in name or p.suffix!=".py" or any(x.startswith(".") for x in p.parts): raise ValueError("Invalid path")
    target=Path("/workspace").joinpath(*p.parts)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(content,encoding="utf-8")
entry=payload["invocation"]["entrypoint"]
if entry not in files: raise ValueError("Missing entrypoint")
request=json.dumps(payload["invocation"]["input"],allow_nan=False)+"\\n"
os.chdir("/workspace")
sys.path.insert(0,"/workspace")
sys.argv=[entry]
sys.stdin=io.TextIOWrapper(io.BytesIO(request.encode()),encoding="utf-8")
del payload,raw,files,request
runpy.run_path(entry,run_name="__main__")
'''
LIMITATION = ('The controller compared actual JSON behavior against withheld expected values. '
              'Test authorship and incident relevance remain reviewer-declared; generic VERIFIED eligibility is unchanged.')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, ensure_ascii=True)


def bind_contract(declaration, snapshot, repository_snapshot, reviewer, reviewed_at):
    from app.schemas.contracts import JsonContract
    from app.services.validation_runs import protected_test_path
    declaration = JsonContract.model_validate(declaration).model_dump()
    path = declaration['entrypoint']
    allowed_path(path)
    if not path.endswith('.py') or path not in snapshot or any(protected_test_path(p) for p in snapshot):
        raise ValueError('JSON contracts require an included Python entrypoint and source-only snapshots, without test/support files.')
    if repository_snapshot.get('version') != 1:
        raise ValueError('JSON contracts require a pinned incident snapshot.')
    serialized = canonical(declaration)
    if redact(serialized) != serialized:
        raise ValueError('Remove secret-like content from the JSON contract.')
    return {'kind': 'json-stdio', 'declaration': declaration, 'reviewer': reviewer, 'reviewed_at': reviewed_at,
            'snapshot_id': repository_snapshot['snapshot_id'], 'source_hashes': {p: digest(v) for p,v in snapshot.items()},
            'oracle_version': 1, 'independence': 'reviewer_declared_not_proven', 'limitations': LIMITATION}


def observe(phase):
    if (phase.get('status') != 'passed' or phase.get('exit_code') != 0 or phase.get('cleanup_succeeded') is not True
            or any(phase.get(k) for k in ('timed_out', 'output_limited', 'output_redacted', 'output_decoding_error', 'stderr_present'))):
        raise ValueError('Program did not return clean, complete JSON in isolation.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('Duplicate JSON keys.')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite JSON number.')
    value = json.loads(phase['output'], object_pairs_hook=pairs, parse_constant=invalid)
    canonical(value)  # Reject overflow to infinity, not only literal NaN/Infinity.
    return value


def execute_contract(run_id, original, proposed, policy, spec, expires_at):
    from app.services import sandbox
    cases = []
    error = None
    for case in spec['declaration']['cases']:
        row = {'id': case['id'], 'role': case['role']}
        for phase, files in (('before', original), ('after', proposed)):
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                error = 'Authorization expired before the next isolated invocation.'
                break
            # Only program inputs cross the boundary, never IDs, roles, expected answers or other cases.
            invocation = {'entrypoint': spec['declaration']['entrypoint'], 'input': case['input']}
            measured = sandbox.run_snapshot(run_id, phase, files, policy, invocation=invocation)
            row[phase] = measured
            try:
                actual = observe(measured)
                row[phase + '_matches_expected'] = canonical(actual) == canonical(case['expected'])
                row[phase + '_matches_baseline'] = canonical(actual) == canonical(case['baseline'])
            except (ValueError, KeyError, TypeError, RecursionError):
                error = 'An invocation did not produce a single valid JSON value with successful execution and cleanup.'
                break
        cases.append(row)
        if error:
            break  # Never start another container after uncertain cleanup or malformed execution.
    unexpected = any(not c.get('before_matches_baseline') and not (c['role'] == 'reproduction' and c.get('before_matches_expected')) for c in cases)
    after_failed = any(not c.get('after_matches_expected') for c in cases)
    reproduced = all(c.get('before_matches_baseline') for c in cases if c['role'] == 'reproduction')
    already_passed = all(c.get('before_matches_expected') for c in cases if c['role'] == 'reproduction')
    status = ('inconclusive' if error else 'mismatch' if unexpected or after_failed or not (reproduced or already_passed)
              else 'not_reproduced' if already_passed else 'matched')
    reasons = {'matched': 'Declared incorrect baseline behavior reproduced; repaired behavior and regressions matched the withheld answers.',
               'not_reproduced': 'All reproduction inputs already produced the expected behavior before the patch.',
               'mismatch': 'Observed behavior differed from the declared baseline or required repaired/regression behavior.',
               'inconclusive': error}
    assessment = {'status': status, 'comparison': 'controller-json-equality-v1', 'independent_proof': False,
                  'reasons': [reasons[status]], 'limitations': LIMITATION, 'cases': cases}
    # Aggregate semantic checks, separate from each invocation's actual process exit code.
    clean = all(p.get('cleanup_succeeded') is True for c in cases for p in (c.get('before'),c.get('after')) if p)
    before = {'status': 'error' if error else 'passed' if already_passed and not unexpected else 'failed',
              'exit_code': None, 'cleanup_succeeded': clean, 'output': reasons[status], 'measurement': 'contract_comparison'}
    after = {'status': 'error' if error else 'failed' if after_failed else 'passed',
             'exit_code': None, 'cleanup_succeeded': clean, 'output': reasons[status], 'measurement': 'contract_comparison'}
    return before, after, assessment
