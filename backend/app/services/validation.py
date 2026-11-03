import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from app.services.sample import BUGGY, FIXED, REGRESSION_TEST
from app.services.security import digest, read_source


def run_trusted_fixture(code: str) -> dict:
    if code not in (BUGGY, FIXED):
        raise ValueError('Only the exact bundled fixture is permitted for host execution.')
    with tempfile.TemporaryDirectory(prefix='autorca-fixture-') as tmp:
        Path(tmp, 'checkout.py').write_text(code)
        Path(tmp, 'test_checkout.py').write_text(REGRESSION_TEST)
        result = subprocess.run(
            [sys.executable, '-E', '-s', '-m', 'unittest', '-v', 'test_checkout'],
            cwd=tmp, capture_output=True, text=True, timeout=15,
            env={'PATH': os.defpath, 'PYTHONIOENCODING': 'utf-8'},
        )
        return {'passed': result.returncode == 0, 'exit_code': result.returncode,
                'output': (result.stdout + result.stderr)[-12000:]}


def validate(source: str, path: str, original_hash: str, proposed: str, mode: str) -> dict:
    checks = []
    current = read_source(source, path)
    matches = digest(current) == original_hash
    checks.append({'name': 'Source version matches', 'status': 'passed' if matches else 'failed',
                   'detail': 'SHA-256 compared with the evidence snapshot.'})
    if path.endswith('.py'):
        try:
            ast.parse(proposed)
            checks.append({'name': 'Python syntax', 'status': 'passed', 'detail': 'Parsed the AST without executing the source.'})
        except (SyntaxError, ValueError, RecursionError):
            checks.append({'name': 'Python syntax', 'status': 'failed', 'detail': 'Proposed code does not parse.'})
    else:
        checks.append({'name': 'Syntax validation', 'status': 'skipped', 'detail': 'Only Python syntax validation is supported.'})
    fixture = {}
    if mode == 'demo' and source == 'sample' and current == BUGGY and proposed == FIXED and matches:
        before, after = run_trusted_fixture(BUGGY), run_trusted_fixture(FIXED)
        fixture = {'before': before, 'after': after}
        checks.extend([
            {'name': 'Original bug reproduced', 'status': 'passed' if not before['passed'] else 'failed', 'detail': 'Bundled regression suite must fail before the fix.'},
            {'name': 'Four regression tests after fix', 'status': 'passed' if after['passed'] else 'failed', 'detail': 'Zero, partial, full discount, and invalid input cases.'},
        ])
    else:
        checks.append({'name': 'Repository tests', 'status': 'skipped', 'detail': 'Not executed: prepare and explicitly authorize an isolated test plan in the review screen.'})
    status = 'failed' if any(c['status'] == 'failed' for c in checks) else ('partial' if any(c['status'] == 'skipped' for c in checks) else 'passed')
    return {'status': status, 'checks': checks, 'fixture': fixture,
            'limitations': 'Trusted demo tests run in a temporary fixture directory. Arbitrary repository or AI-generated code is never executed on the host. Syntax checks cannot establish behavioral correctness.'}
