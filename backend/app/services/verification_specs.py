"""Reviewed expectations over untrusted unittest observations; never independent proof."""
import ast
import json
import re
from app.schemas.contracts import VerificationSpecification
from app.services.security import allowed_path, digest, redact

LIMITATION = ('Reported unittest output can be forged by repository code. Matching a reviewed specification '
              'does not establish independent failure attribution or qualify a generic repair as VERIFIED.')


def bind_spec(spec, snapshot, repository_snapshot, reviewer, reviewed_at):
    declaration = VerificationSpecification.model_validate(spec).model_dump()
    if redact(declaration['rationale']) != declaration['rationale']:
        raise ValueError('Remove secret-like content from the verification rationale.')
    if repository_snapshot.get('version') != 1:
        raise ValueError('Verification specifications require a pinned incident. Submit a new incident.')
    identifiers = sorted(set([item['test_id'] for item in declaration['reproduction']] + declaration['regressions']))
    tests = []
    for identifier in identifiers:
        module, class_name, method = identifier.rsplit('.', 2)
        path = module.replace('.', '/') + '.py'
        allowed_path(path)
        if not path.rsplit('/', 1)[-1].startswith('test') or path not in snapshot:
            raise ValueError('Every specified test must belong to a selected test*.py file.')
        # Only direct statically declared unittest methods are supported. No imports.
        try:
            tree = ast.parse(snapshot[path])
        except (SyntaxError, ValueError, RecursionError):
            raise ValueError('A specified test file could not be parsed.') from None
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name]
        methods = [node for node in classes[0].body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method] if len(classes) == 1 else []
        if len(methods) != 1 or not method.startswith('test'):
            raise ValueError('Specified tests must be unambiguous directly declared test methods.')
        sha = digest(snapshot[path])
        if repository_snapshot.get('kind') != 'github_commit' and repository_snapshot.get('files', {}).get(path) != sha:
            raise ValueError('Specified tests must match the incident snapshot captured before patch generation.')
        tests.append({'test_id': identifier, 'path': path, 'sha256': sha})
    return {'declaration': declaration, 'reviewer': reviewer, 'reviewed_at': reviewed_at,
            'snapshot_id': repository_snapshot['snapshot_id'], 'tests': tests,
            'independence': 'reviewer_declared_not_proven', 'limitations': LIMITATION}


def test_identifier(method, owner):
    # unittest formatting differs between Python versions.
    return owner if owner.endswith('.' + method) else owner + '.' + method


def observations(phase):
    """Parse a complete, consistent verbose unittest run; ambiguous output fails closed."""
    output = phase.get('output', '')
    records, exceptions, summaries = {}, {}, []
    current = None
    for line in output.splitlines():
        match = re.fullmatch(r'(test\w*) \(([\w.]+)\) \.\.\. (ok|FAIL|ERROR|skipped .+|expected failure|unexpected success)', line)
        if match:
            identifier = test_identifier(match[1], match[2])
            if identifier in records:
                raise ValueError('Duplicate test result.')
            records[identifier] = match[3]
        header = re.fullmatch(r'(?:FAIL|ERROR): (test\w*) \(([\w.]+)\)', line)
        if header:
            current = test_identifier(header[1], header[2])
            if current in exceptions:
                raise ValueError('Duplicate failure detail.')
            exceptions[current] = []
        elif current and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:: .*)?', line):
            exceptions[current].append(line.split(':', 1)[0])
        elif line.startswith('----------------------------------------------------------------------'):
            # The separator immediately after a failure header precedes its traceback.
            pass
        elif line.startswith('======================================================================') or line.startswith('Ran '):
            current = None
        if line.startswith('AUTORCA_UNITTEST_SUMMARY='):
            summaries.append(json.loads(line.split('=', 1)[1]))
    if len(summaries) != 1 or not records:
        raise ValueError('Complete per-test output and one summary are required.')
    summary = summaries[0]
    expected = {'discovered': len(records), 'run': len(records),
                'failures': sum(s == 'FAIL' for s in records.values()),
                'errors': sum(s == 'ERROR' for s in records.values()),
                'skipped': sum(s.startswith('skipped ') for s in records.values())}
    if not isinstance(summary, dict) or summary != expected or any(type(value) is not int for value in summary.values()):
        raise ValueError('Test records do not match the suite summary.')
    failed = {identifier for identifier, status in records.items() if status in ('FAIL', 'ERROR')}
    if set(exceptions) != failed or any(not types for types in exceptions.values()):
        raise ValueError('Failure details are missing or ambiguous.')
    if any(s not in ('ok', 'FAIL', 'ERROR') for s in records.values()):
        raise ValueError('Skipped or expected-failure tests cannot satisfy a specification.')
    expected_exit = 1 if failed else 0
    if phase.get('exit_code') != expected_exit or phase.get('status') != ('failed' if failed else 'passed'):
        raise ValueError('Suite output contradicts the process result.')
    return {identifier: {'status': status, 'exception': exceptions.get(identifier, [None])[-1]}
            for identifier, status in records.items()}


def assess_spec(spec, before, after):
    result = {'status': 'inconclusive', 'independent_proof': False, 'limitations': LIMITATION,
              'reproduction': [], 'regressions': [], 'reasons': []}
    if any(p.get('cleanup_succeeded') is not True or p.get('timed_out') or p.get('output_limited') for p in (before, after)):
        result['reasons'] = ['Both isolated phases require clean, complete execution and confirmed cleanup.']
        return result
    try:
        baseline, patched = observations(before), observations(after)
    except (ValueError, TypeError, KeyError):
        result['reasons'] = ['Complete, unambiguous unittest observations are unavailable or contradict process results.']
        return result
    expected = {item['test_id']: item['expected_exception'] for item in spec['declaration']['reproduction']}
    required = set(expected) | set(spec['declaration']['regressions'])
    if not required.issubset(baseline) or not required.issubset(patched) or set(baseline) != set(patched):
        result['reasons'] = ['Required test IDs are missing or discovery changed between phases.']
        return result
    for identifier, exception in expected.items():
        result['reproduction'].append({'test_id': identifier, 'expected_exception': exception,
            'before': baseline[identifier], 'after': patched[identifier],
            'observed_match': baseline[identifier]['status'] in ('FAIL', 'ERROR') and baseline[identifier]['exception'] == exception
                and patched[identifier]['status'] == 'ok'})
    result['regressions'] = [{'test_id': identifier, 'after': patched[identifier], 'observed_pass': patched[identifier]['status'] == 'ok'}
                             for identifier in spec['declaration']['regressions']]
    unexpected = [identifier for identifier, value in baseline.items() if value['status'] != 'ok' and identifier not in expected]
    if any(value['status'] != 'ok' for value in patched.values()) or unexpected:
        result['status'], result['reasons'] = 'mismatch', ['Patched tests failed or baseline failures occurred outside the reproduction specification.']
    elif all(value['status'] == 'ok' for value in baseline.values()):
        result['status'], result['reasons'] = 'not_reproduced', ['The declared reproduction tests passed on the original source.']
    elif all(item['observed_match'] for item in result['reproduction']):
        result['status'], result['reasons'] = 'matched', ['Reported expected failures passed after the patch and all required regressions reported success.']
    else:
        result['status'], result['reasons'] = 'mismatch', ['The baseline did not report every declared failure with its expected exception.']
    return result
