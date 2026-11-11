import copy
import json
from datetime import datetime, timedelta, timezone
import pytest
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.records import ValidationRun
from app.services import sandbox
from app.services.json_contracts import observe, execute_contract, DRIVER
from app.services.validation_runs import execute_validation
from tests.test_sandbox import ready
from tests.test_workflow import investigate
from tests.test_repair_outcomes import consistent


def contract():
    return {'version': 1, 'reviewed': True, 'entrypoint': 'checkout.py', 'rationale': 'Reviewed the program interface against independently specified arithmetic behavior.',
            'cases': [{'id': 'bug', 'role': 'reproduction', 'input': 2, 'baseline': 1, 'expected': 3},
                      {'id': 'zero', 'role': 'regression', 'input': 0, 'baseline': 0, 'expected': 0}]}


def phase(value):
    return {'status': 'passed', 'exit_code': 0, 'output': json.dumps(value), 'cleanup_succeeded': True}


def prepare(client, identifier, value=None, **extra):
    return client.post(f'/api/incidents/{identifier}/validation-plans', json={
        'files': ['checkout.py'], 'profile': 'python-json-stdio', 'json_contract': value or contract(), **extra})


def authorize(client, identifier, planned):
    return client.post(f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize',
        json={'authorized': True, 'plan_hash': planned['plan_hash']})


@pytest.mark.parametrize('behavior,outcome,assessment', [('match','PATCH_UNVERIFIED','matched'), ('correct','NOT_REPRODUCED','not_reproduced'),
    ('wrong_baseline','VALIDATION_FAILED','mismatch'), ('wrong_after','VALIDATION_FAILED','mismatch'), ('fake_report','VALIDATION_FAILED','inconclusive')])
def test_controller_comparison_and_consistent_outcomes(client, ready, monkeypatch, behavior, outcome, assessment):
    identifier, _ = investigate(client)
    invocations = []
    def execute(rid, stage, files, policy, invocation=None):
        invocations.append(copy.deepcopy(invocation))
        assert set(invocation) == {'entrypoint', 'input'}
        assert set(files) == {'checkout.py'}
        x = invocation['input']
        value = 0 if x == 0 else 1 if stage == 'before' else 3
        if behavior == 'correct' and x: value = 3
        if behavior == 'wrong_baseline' and stage == 'before' and x: value = 99
        if behavior == 'wrong_after' and stage == 'after': value = 99
        if behavior == 'fake_report': return {**phase(0), 'output': 'AUTORCA_UNITTEST_SUMMARY={"failures":0}'}
        return phase(value)
    monkeypatch.setattr(sandbox, 'run_snapshot', execute)
    response = prepare(client, identifier)
    assert response.status_code == 201, response.text
    planned = response.json()
    assert planned['result']['verification_spec']['oracle_version'] == 1
    assert authorize(client, identifier, planned).status_code == 202
    consistent(client, identifier, outcome)
    saved = client.get(f'/api/incidents/{identifier}/report').json()['validation']['isolated']
    assert saved['specification_assessment']['status'] == assessment
    assert saved['specification_assessment']['independent_proof'] is False
    assert len(invocations) == (1 if behavior == 'fake_report' else 4)
    if behavior == 'match':
        assert all(c[p]['exit_code'] == 0 for c in saved['specification_assessment']['cases'] for p in ('before','after'))
        assert saved['before']['exit_code'] is None  # Semantic comparison is not a process exit.
        assert client.post(f'/api/incidents/{identifier}/approve', json={}).status_code == 200
        consistent(client, identifier, 'PATCH_UNVERIFIED')


@pytest.mark.parametrize('output', ['NaN', 'Infinity', '1e1000', '{"x":1,"x":2}', '1\n2', 'PASSED', '{', '{"__proto__":1}\nnoise'])
def test_non_json_or_ambiguous_output_rejected(output):
    with pytest.raises(ValueError): observe({**phase(None), 'output': output})


@pytest.mark.parametrize('flag', ['timed_out', 'output_limited', 'output_redacted', 'output_decoding_error', 'stderr_present', 'cleanup_succeeded'])
def test_damaged_execution_never_becomes_behavioral_success(flag):
    result = phase('[REDACTED]')
    result[flag] = flag != 'cleanup_succeeded'
    with pytest.raises(ValueError): observe(result)


@pytest.mark.parametrize('fault', ['unreviewed','no_regression','same_baseline','duplicate','large','path','tests','missing_contract','wrong_profile'])
def test_invalid_contracts_and_source_boundaries(client, ready, fault):
    identifier, _ = investigate(client)
    value, extra = contract(), {}
    if fault == 'unreviewed': value['reviewed'] = False
    elif fault == 'no_regression': value['cases'] = value['cases'][:1]
    elif fault == 'same_baseline': value['cases'][0]['baseline'] = 3
    elif fault == 'duplicate': value['cases'][1]['id'] = 'bug'
    elif fault == 'large': value['cases'][0]['input'] = 'x' * 5000
    elif fault == 'path': value['entrypoint'] = '../checkout.py'
    elif fault == 'tests': extra['files'] = ['checkout.py','test_checkout.py']
    elif fault == 'missing_contract': extra['json_contract'] = None
    else: extra['profile'] = 'python-unittest'
    assert prepare(client, identifier, value, **extra).status_code in (400,422)


@pytest.mark.parametrize('queued', [False, True])
def test_changed_contract_is_rejected_before_execution(client, ready, monkeypatch, queued):
    identifier, _ = investigate(client)
    planned = prepare(client, identifier).json()
    if queued:
        monkeypatch.setattr(settings, 'job_execution', 'external')
        assert authorize(client, identifier, planned).status_code == 202
    with SessionLocal() as db:
        run = db.get(ValidationRun, planned['id'])
        changed = copy.deepcopy(run.result)
        changed['verification_spec']['declaration']['cases'][0]['expected'] = 999
        run.result = changed
        db.commit()
    monkeypatch.setattr(sandbox, 'run_snapshot', lambda *a, **k: pytest.fail('Changed contract cannot execute'))
    if queued:
        execute_validation(planned['id'])
        consistent(client, identifier, 'VALIDATION_FAILED')
    else:
        assert authorize(client, identifier, planned).status_code == 400


def test_expired_contract_and_cleanup_failure_stop_further_invocations(ready, monkeypatch):
    spec = {'declaration': contract()}
    calls = []
    def execute(*args, **kwargs):
        calls.append(kwargs)
        return {**phase(1), 'cleanup_succeeded': False}
    monkeypatch.setattr(sandbox, 'run_snapshot', execute)
    before, after, assessment = execute_contract('id', {}, {}, {}, spec, (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    assert not calls and assessment['status'] == 'inconclusive'
    before, after, assessment = execute_contract('id', {}, {}, {}, spec, (datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat())
    assert len(calls) == 1 and before['cleanup_succeeded'] is False


def test_json_driver_is_pinned_and_cloud_has_no_fallback(ready, monkeypatch):
    compile(DRIVER, '<isolated-driver>', 'exec')  # Parse only, never execute snapshot code on host.
    policy = sandbox.policy('python-json-stdio')
    assert policy['command'] == ['python','-I','-B','-c',DRIVER]
    changed = {**policy, 'command': ['python','-c','untrusted override']}
    with pytest.raises(ValueError, match='policy changed'):
        sandbox.run_snapshot('unused','before',{},changed,invocation={'entrypoint':'a.py','input':0})
    monkeypatch.setattr(settings, 'sandbox_provider', 'vercel')
    with pytest.raises(ValueError, match='Docker'):
        sandbox.policy('python-json-stdio')
