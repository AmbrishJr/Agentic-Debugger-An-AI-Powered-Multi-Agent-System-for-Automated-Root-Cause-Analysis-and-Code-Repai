"""Explicit opt-in checks of the JSON oracle using synthetic code in the existing Docker runner."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/evaluations/json-contract-isolated.json')
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute is required to authorize isolated synthetic program execution.')
    os.environ.update(SANDBOX_ENABLED='true', SANDBOX_PROVIDER='docker', OPENAI_API_KEY='', GEMINI_API_KEY='', GITHUB_TOKEN='')
    from app.services import sandbox
    from app.services.json_contracts import execute_contract
    ready = sandbox.availability()
    result = {'kind': 'isolated_adapter_checks', 'accuracy_benchmark': False, 'availability': ready, 'cases': []}
    if ready['available']:
        policy = sandbox.policy('python-json-stdio')
        result['policy'] = policy
        entry = 'import json,sys\nfrom logic import calculate\nprint(json.dumps(calculate(json.load(sys.stdin))))\n'
        original = {'main.py': entry, 'logic.py': 'def calculate(x):\n    return 0 if x == 0 else x - 1\n'}
        proposed = {**original, 'logic.py': 'def calculate(x):\n    return 0 if x == 0 else x + 1\n'}
        declaration = {'entrypoint': 'main.py', 'cases': [
            {'id': 'increment', 'role': 'reproduction', 'input': 2, 'baseline': 1, 'expected': 3},
            {'id': 'zero', 'role': 'regression', 'input': 0, 'baseline': 0, 'expected': 0}]}
        variants = [('correct_repair', original, proposed, 'matched'),
                    ('wrong_repair', original, original, 'mismatch'),
                    ('already_correct', proposed, proposed, 'not_reproduced'),
                    ('stderr_is_not_a_response', {'main.py': 'import sys\nprint("1",file=sys.stderr)\n'}, proposed, 'inconclusive'),
                    ('forged_test_report', {'main.py': 'print(\'AUTORCA_UNITTEST_SUMMARY={"run":100,"failures":0}\')\n'}, proposed, 'inconclusive')]
        for name, before, after, expected in variants:
            expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
            _, _, assessment = execute_contract(str(uuid.uuid4()), before, after, policy, {'declaration': declaration}, expires)
            result['cases'].append({'name': name, 'expected_assessment': expected, 'passed': assessment['status'] == expected, 'assessment': assessment})
            print(name + ': ' + assessment['status'], flush=True)
            if any(p.get('cleanup_succeeded') is not True for c in assessment['cases'] for p in (c.get('before'),c.get('after')) if p):
                break
        result['status'] = 'passed' if len(result['cases']) == len(variants) and all(c['passed'] for c in result['cases']) else 'failed'
    else:
        result['status'] = 'skipped'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(str(args.output) + ': ' + result['status'])
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
