import copy
import json
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.records import ProposedFix, ValidationRun
from app.services import sandbox
from app.services.verification_specs import observations, assess_spec
from app.services.validation_runs import execute_validation
from tests.test_workflow import investigate
from tests.test_sandbox import ready
from tests.test_repair_outcomes import consistent

PREFIX = 'test_checkout.DiscountTests.'
EXCEPTIONS = {'test_full_discount': 'AssertionError', 'test_invalid_inputs': 'ZeroDivisionError',
              'test_percentage_discount': 'AssertionError', 'test_zero_discount': 'ZeroDivisionError'}


def declaration():
    return {'version': 1, 'reviewed': True, 'rationale': 'Reviewed the percentage arithmetic and boundary expectations against the incident.',
            'reproduction': [{'test_id': PREFIX + method, 'expected_exception': exception} for method, exception in EXCEPTIONS.items()],
            'regressions': [PREFIX + method for method in EXCEPTIONS]}


def phase_result(before=False, failures=None, modern=False):
    failures = (EXCEPTIONS if before else {}) if failures is None else failures
    lines = []
    for method in EXCEPTIONS:
        status = ('FAIL' if failures[method] == 'AssertionError' else 'ERROR') if method in failures else 'ok'
        owner = 'test_checkout.DiscountTests' + ('.' + method if modern else '')
        lines.append(f'{method} ({owner}) ... {status}')
    for method, exception in failures.items():
        status = 'FAIL' if exception == 'AssertionError' else 'ERROR'
        lines.extend(['=' * 70, f'{status}: {method} (test_checkout.DiscountTests)', '-' * 70,
                      'Traceback (most recent call last):', f'{exception}: expected example message'])
    summary = {'discovered': 4, 'run': 4, 'failures': sum(e == 'AssertionError' for e in failures.values()),
               'errors': sum(e != 'AssertionError' for e in failures.values()), 'skipped': 0}
    lines.extend(['-' * 70, 'Ran 4 tests in 0.001s', 'AUTORCA_UNITTEST_SUMMARY=' + json.dumps(summary)])
    return {'status': 'failed' if failures else 'passed', 'exit_code': 1 if failures else 0,
            'output': '\n'.join(lines), 'cleanup_succeeded': True}


def prepare(client, identifier, spec=None, **kwargs):
    return client.post(f'/api/incidents/{identifier}/validation-plans', json={
        'files': ['checkout.py', 'test_checkout.py'], 'verification_spec': spec or declaration(), **kwargs})


def authorize(client, identifier, planned):
    return client.post(f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize',
        json={'authorized': True, 'plan_hash': planned['plan_hash']})


def test_plan_records_reviewer_snapshot_hashes_without_executing(client, ready, monkeypatch):
    identifier, detail = investigate(client)
    monkeypatch.setattr(sandbox, 'run_snapshot', lambda *a: pytest.fail('Planning cannot execute'))
    response = prepare(client, identifier)
    assert response.status_code == 201, response.text
    spec = response.json()['result']['verification_spec']
    assert spec['reviewer'] == 'local developer'
    assert spec['snapshot_id'] == detail['repository_snapshot']['snapshot_id']
    assert spec['independence'] == 'reviewer_declared_not_proven'
    assert {test['sha256'] for test in spec['tests']} == {detail['repository_snapshot']['files']['test_checkout.py']}
    assert 'snapshot' not in response.json()


@pytest.mark.parametrize('mutation', ['unreviewed', 'duplicate', 'missing_method', 'missing_file', 'no_regressions', 'pytest', 'extra_field'])
def test_invalid_or_unreviewed_specifications_rejected(client, ready, mutation):
    identifier, _ = investigate(client)
    spec = declaration()
    kwargs = {}
    if mutation == 'unreviewed': spec['reviewed'] = False
    elif mutation == 'duplicate': spec['reproduction'].append(spec['reproduction'][0])
    elif mutation == 'missing_method': spec['regressions'] = [PREFIX + 'test_nonexistent']
    elif mutation == 'missing_file': spec['regressions'] = ['test_missing.Tests.test_one']
    elif mutation == 'no_regressions': spec['regressions'] = []
    elif mutation == 'pytest': kwargs['profile'] = 'python-pytest'
    else: spec['reviewer'] = 'forged reviewer'
    assert prepare(client, identifier, spec, **kwargs).status_code in (400, 422)
    assert client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'] == []


@pytest.mark.parametrize('when', ['before_authorization', 'queued', 'during_execution'])
def test_specification_tampering_cannot_execute_or_retain_proof(client, ready, monkeypatch, when):
    identifier, _ = investigate(client)
    planned = prepare(client, identifier).json()
    def tamper():
        with SessionLocal() as db:
            run = db.get(ValidationRun, planned['id'])
            changed = copy.deepcopy(run.result)
            changed['verification_spec']['declaration']['rationale'] = 'A changed expected behavior after review.'
            run.result = changed
            db.commit()
    if when == 'before_authorization':
        tamper()
        monkeypatch.setattr(sandbox, 'run_snapshot', lambda *a: pytest.fail('Tampered plan must not run'))
        assert authorize(client, identifier, planned).status_code == 400
        return
    if when == 'queued':
        monkeypatch.setattr(settings, 'job_execution', 'external')
        assert authorize(client, identifier, planned).status_code == 202
        tamper()
        monkeypatch.setattr(sandbox, 'run_snapshot', lambda *a: pytest.fail('Tampered plan must not run'))
        execute_validation(planned['id'])
    else:
        def execute(rid, phase, files, policy):
            if phase == 'after': tamper()
            return phase_result(phase == 'before')
        monkeypatch.setattr(sandbox, 'run_snapshot', execute)
        assert authorize(client, identifier, planned).status_code == 202
    consistent(client, identifier, 'VALIDATION_FAILED')
    result = client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'][0]['result']
    assert 'proof' not in result and 'specification_assessment' not in result


@pytest.mark.parametrize('modern', [False, True])
def test_known_unittest_formats_and_exact_exceptions(modern):
    baseline, patched = phase_result(True, modern=modern), phase_result(modern=modern)
    assert len(observations(baseline)) == 4
    result = assess_spec({'declaration': declaration()}, baseline, patched)
    assert result['status'] == 'matched' and result['independent_proof'] is False
    assert all(item['observed_match'] for item in result['reproduction'])


@pytest.mark.parametrize('fault', ['wrong_exception', 'unrelated_failure', 'patched_failure', 'missing_record', 'duplicate_record',
                                   'forged_summary', 'skipped', 'timeout', 'cleanup', 'truncated', 'exit_mismatch', 'no_output'])
def test_incomplete_or_contradictory_observations_never_match(fault):
    spec, baseline, patched = declaration(), phase_result(True), phase_result()
    if fault == 'wrong_exception': baseline = phase_result(failures={**EXCEPTIONS, 'test_zero_discount': 'ImportError'})
    elif fault == 'unrelated_failure': spec['reproduction'] = spec['reproduction'][:1]
    elif fault == 'patched_failure': patched = phase_result(failures={'test_zero_discount': 'AssertionError'})
    elif fault == 'missing_record': patched['output'] = '\n'.join(patched['output'].splitlines()[1:])
    elif fault == 'duplicate_record': patched['output'] += '\n' + patched['output'].splitlines()[0]
    elif fault == 'forged_summary': patched['output'] += '\nAUTORCA_UNITTEST_SUMMARY={}'
    elif fault == 'skipped': patched['output'] = patched['output'].replace('... ok', "... skipped 'disabled'", 1)
    elif fault == 'timeout': patched['timed_out'] = True
    elif fault == 'cleanup': patched['cleanup_succeeded'] = False
    elif fault == 'truncated': patched['output_limited'] = True
    elif fault == 'exit_mismatch': baseline['exit_code'] = 0
    else: baseline['output'] = ''
    result = assess_spec({'declaration': spec}, baseline, patched)
    assert result['status'] in ('mismatch', 'inconclusive')
    assert result['independent_proof'] is False


@pytest.mark.parametrize('behavior,expected', [('matched', 'VERIFIED'), ('wrong_exception', 'VALIDATION_FAILED'),
                                            ('passed', 'NOT_REPRODUCED'), ('missing', 'VALIDATION_FAILED')])
def test_outcomes_and_report_consistency(client, ready, monkeypatch, behavior, expected):
    identifier, _ = investigate(client)
    def execute(rid, phase, files, policy):
        result = phase_result(phase == 'before' and behavior != 'passed')
        if phase == 'before' and behavior == 'wrong_exception':
            result = phase_result(failures={**EXCEPTIONS, 'test_zero_discount': 'ImportError'})
        if behavior == 'missing': result['output'] = ''
        return result
    monkeypatch.setattr(sandbox, 'run_snapshot', execute)
    planned = prepare(client, identifier).json()
    assert authorize(client, identifier, planned).status_code == 202
    consistent(client, identifier, expected)
    runs = client.get(f'/api/incidents/{identifier}/validation-runs').json()['items']
    report = client.get(f'/api/incidents/{identifier}/report').json()
    assert report['validation']['isolated']['verification_spec'] == planned['result']['verification_spec']
    assert report['validation']['isolated']['specification_assessment'] == runs[0]['result']['specification_assessment']


def test_even_forged_matching_output_cannot_verify_nonfixture_patch(client, ready, monkeypatch):
    identifier, _ = investigate(client)
    with SessionLocal() as db:
        fix = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == identifier))
        fix.proposed_code += '\n# A proposal outside the exact controlled fixture.\n'
        fix.files = [{**item, 'proposed_code': fix.proposed_code} for item in fix.files]
        db.commit()
    monkeypatch.setattr(sandbox, 'run_snapshot', lambda rid, phase, files, policy: phase_result(phase == 'before'))
    planned = prepare(client, identifier).json()
    assert authorize(client, identifier, planned).status_code == 202
    consistent(client, identifier, 'PATCH_UNVERIFIED')
    result = client.get(f'/api/incidents/{identifier}/report').json()['validation']['isolated']
    assert result['specification_assessment']['status'] == 'matched'
    assert result['specification_assessment']['independent_proof'] is False


def test_restart_retains_reviewed_specification(client, ready, monkeypatch):
    from app.services.jobs import recover
    identifier, _ = investigate(client)
    planned = prepare(client, identifier).json()
    monkeypatch.setattr(settings, 'job_execution', 'external')
    authorize(client, identifier, planned)
    monkeypatch.setattr(sandbox, 'cleanup', lambda *a: True)
    recover()
    result = client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'][0]['result']
    assert result['verification_spec'] == planned['result']['verification_spec']
    consistent(client, identifier, 'VALIDATION_FAILED')
