import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.records import ProposedFix, ValidationRun
from app.services.repair_outcomes import resolve_outcome
from app.services.validation_runs import protected_test_path
from tests.test_workflow import investigate, create
from tests.test_sandbox import ready, plan


def consistent(client, identifier, expected):
    detail = client.get(f'/api/incidents/{identifier}').json()
    outcome = detail['repair_outcome']
    assert outcome['status'] == expected
    assert client.get(f'/api/incidents/{identifier}/patch').json()['repair_outcome'] == outcome
    assert client.get(f'/api/incidents/{identifier}/report').json()['repair_outcome'] == outcome
    assert detail['fix']['repair_outcome'] == outcome
    return outcome


def test_demo_and_approval_never_imply_verified(client):
    identifier, _ = investigate(client)
    outcome = consistent(client, identifier, 'PATCH_UNVERIFIED')
    assert client.post(f'/api/incidents/{identifier}/approve', json={}).status_code == 200
    assert consistent(client, identifier, 'PATCH_UNVERIFIED') == outcome


def test_queued_failed_and_insufficient_are_distinct(client):
    identifier = create(client)
    assert client.get(f'/api/incidents/{identifier}').json()['repair_outcome'] is None
    identifier, data = investigate(client, error_log='Unknown failure, more diagnostics needed')
    assert data['repair_outcome']['status'] == 'INSUFFICIENT_EVIDENCE'
    incident = SimpleNamespace(status='failed')
    inv = SimpleNamespace(agent_status='completed', analysis_results={'errors': [{'agent': 'analysis'}], 'analysis': {}})
    assert resolve_outcome(incident, inv, None) is None


@pytest.mark.parametrize('before,after,expected', [
    ('passed','passed','NOT_REPRODUCED'), ('failed','failed','VALIDATION_FAILED'),
    ('passed','failed','VALIDATION_FAILED'), ('error','passed','VALIDATION_FAILED'),
    ('failed','passed','PATCH_UNVERIFIED'),
])
def test_generic_exit_codes_are_not_proof(client, ready, monkeypatch, before, after, expected):
    def execute(run_id, phase, files, policy):
        status = before if phase == 'before' else after
        return {'status': status, 'exit_code': 0 if status == 'passed' else 1, 'output': 'unrelated test output', 'cleanup_succeeded': True}
    monkeypatch.setattr('app.services.sandbox.run_snapshot', execute)
    identifier, _ = investigate(client)
    planned = plan(client, identifier)
    client.post(f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize', json={'authorized': True, 'plan_hash': planned['plan_hash']})
    consistent(client, identifier, expected)


def controlled_result(phase):
    summary = {'discovered': 4, 'run': 4, 'failures': 2 if phase == 'before' else 0, 'errors': 2 if phase == 'before' else 0, 'skipped': 0}
    return {'status': 'failed' if phase == 'before' else 'passed', 'exit_code': 1 if phase == 'before' else 0,
            'output': 'ZeroDivisionError\nAUTORCA_UNITTEST_SUMMARY=' + json.dumps(summary), 'cleanup_succeeded': True}


def test_controlled_fixture_proof_and_active_run_invalidation(client, ready, monkeypatch):
    # Mock adapter validates classification only, never reported as measured repair.
    monkeypatch.setattr('app.services.sandbox.run_snapshot', lambda rid, phase, files, policy: controlled_result(phase))
    identifier, _ = investigate(client)
    planned = plan(client, identifier)
    client.post(f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize', json={'authorized': True, 'plan_hash': planned['plan_hash']})
    consistent(client, identifier, 'VERIFIED')
    with SessionLocal() as db:
        fix = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == identifier))
        fix.validation_result = {**fix.validation_result, 'status': 'running'}
        db.commit()
    consistent(client, identifier, 'PATCH_UNVERIFIED')


@pytest.mark.parametrize('fault', ['timed_out', 'output_limited', 'cleanup_succeeded'])
def test_execution_integrity_overrides_success(client, ready, monkeypatch, fault):
    def execute(rid, phase, files, policy):
        value = controlled_result(phase)
        value[fault] = fault != 'cleanup_succeeded'
        return value
    monkeypatch.setattr('app.services.sandbox.run_snapshot', execute)
    identifier, _ = investigate(client)
    planned = plan(client, identifier)
    client.post(f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize', json={'authorized': True, 'plan_hash': planned['plan_hash']})
    consistent(client, identifier, 'VALIDATION_FAILED')


@pytest.mark.parametrize('path', ['test_checkout.py', 'checkout_test.py', 'tests/helper.py', 'fixtures/data.py', 'conftest.py', 'pyproject.toml', 'sitecustomize.py'])
def test_test_support_paths_are_protected(path):
    assert protected_test_path(path)


def test_test_patch_rejected_at_planning(client, ready):
    identifier, _ = investigate(client)
    with SessionLocal() as db:
        fix = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == identifier))
        fix.files = [{**fix.files[0], 'path': 'test_checkout.py'}]
        db.commit()
    response = client.post(f'/api/incidents/{identifier}/validation-plans', json={'files': ['checkout.py', 'test_checkout.py']})
    assert response.status_code == 400
    assert 'test support' in response.text


@pytest.mark.parametrize('tamper', ['snapshot', 'manifest', 'patch'])
def test_execution_rechecks_after_authorization(client, ready, monkeypatch, tamper):
    from app.core.config import settings
    from app.services.validation_runs import execute_validation
    monkeypatch.setattr(settings, 'job_execution', 'external')
    # Investigation must complete inline before queueing only the validation.
    monkeypatch.setattr(settings, 'job_execution', 'inline')
    identifier, _ = investigate(client)
    planned = plan(client, identifier)
    monkeypatch.setattr(settings, 'job_execution', 'external')
    response = client.post(f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize', json={'authorized': True, 'plan_hash': planned['plan_hash']})
    assert response.status_code == 202
    with SessionLocal() as db:
        run = db.get(ValidationRun, planned['id'])
        if tamper == 'snapshot':
            run.snapshot = {**run.snapshot, 'test_checkout.py': 'pass'}
        elif tamper == 'manifest':
            run.manifest = [{**m, 'sha256': '0' * 64} for m in run.manifest]
        else:
            fix = db.get(ProposedFix, run.fix_id)
            fix.proposed_code = 'pass'
        db.commit()
    monkeypatch.setattr('app.services.sandbox.run_snapshot', lambda *a: pytest.fail('Tampered plans must not execute'))
    execute_validation(planned['id'])
    consistent(client, identifier, 'VALIDATION_FAILED')


def test_forged_output_with_nonfixture_tests_is_not_independent_proof():
    from app.services.validation_runs import fixture_proof
    from app.services.sample import BUGGY, FIXED
    original = {'checkout.py': BUGGY, 'test_checkout.py': 'print("forged output")'}
    proof = fixture_proof(original, {**original, 'checkout.py': FIXED}, {'profile':'python-unittest'},
                          controlled_result('before'), controlled_result('after'), 'patch-hash', [])
    assert proof['independent_tests'] is False
    assert proof['expected_failure'] is False
    assert proof['regressions_passed'] is False
