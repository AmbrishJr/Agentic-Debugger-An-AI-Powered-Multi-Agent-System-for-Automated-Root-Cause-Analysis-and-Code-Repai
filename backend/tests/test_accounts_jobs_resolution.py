from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.records import User, Job, Investigation, AgentExecution, IncidentMemory, ProposedFix, Incident
from app.services.auth import password_hash
from app.services.jobs import recover, run_job
from app.agents import workflow
from tests.test_workflow import create, investigate


def test_auth_roles_csrf_revocation_and_last_admin(client, monkeypatch):
    monkeypatch.setattr(settings, 'auth_enabled', True)
    assert client.get('/api/incidents').status_code == 401
    assert client.get('/api/auth/me').json()['setup_required']
    with SessionLocal() as db:
        user = User(username='admin', password_hash=password_hash('long-test-password'), role='admin')
        db.add(user); db.commit(); admin_id = user.id
    login = client.post('/api/auth/login', json={'username':'admin','password':'long-test-password'})
    assert login.status_code == 200
    assert 'HttpOnly' in login.headers['set-cookie'] and 'SameSite=strict' in login.headers['set-cookie']
    assert client.put('/api/settings', json={}).status_code == 403
    client.headers['x-csrf-token'] = login.json()['csrf_token']
    assert client.put(f'/api/users/{admin_id}', json={'role':'viewer','active':True}).status_code == 409
    viewer = client.post('/api/users', json={'username':'reader','password':'another-long-password','role':'viewer'})
    assert viewer.status_code == 201 and 'password_hash' not in viewer.text
    client.post('/api/auth/logout', json={})
    assert client.get('/api/incidents').status_code == 401
    login = client.post('/api/auth/login', json={'username':'reader','password':'another-long-password'})
    client.headers['x-csrf-token'] = login.json()['csrf_token']
    assert client.get('/api/incidents').status_code == 200
    assert client.get('/api/users').status_code == 403
    assert client.post('/api/incidents', json={}).status_code == 403
    assert client.post('/api/auth/password', json={'current_password':'another-long-password','new_password':'replacement-password'}).status_code == 200
    assert client.get('/api/incidents').status_code == 401


def test_login_throttles_and_origin(client, monkeypatch):
    monkeypatch.setattr(settings, 'auth_enabled', True)
    for _ in range(10):
        assert client.post('/api/auth/login', json={'username':'missing','password':'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'username':'missing','password':'wrong'}).status_code == 429
    assert client.post('/api/auth/login', json={}, headers={'Origin':'https://evil.example'}).status_code == 403


def test_resolution_reopen_audit_memory_and_counts(client):
    identifier, _ = investigate(client)
    path = f'/api/incidents/{identifier}'
    body = {'note':'Checkout recovered after the release.', 'evidence':'CI run 123 and monitored zero-discount checkout.'}
    assert client.post(path+'/resolve', json=body).status_code == 409
    client.post(path+'/approve', json={})
    assert client.get('/api/dashboard/stats').json()['resolved'] == 0
    assert client.post(path+'/resolve', json={'note':'too short','evidence':'short'}).status_code == 422
    resolved = client.post(path+'/resolve', json=body).json()
    assert resolved['resolved_at'] and resolved['resolved_by'] == 'local developer'
    assert [e['action'] for e in resolved['audit']] == ['approved','resolved']
    assert client.get('/api/dashboard/stats').json()['resolved'] == 1
    assert client.post(path+'/resolve', json=body).status_code == 409
    reopened = client.post(path+'/reopen', json={'note':'Checkout errors returned in monitoring.'}).json()
    assert reopened['status'] == 'reopened' and len(reopened['audit']) == 3
    assert client.get('/api/dashboard/stats').json()['resolved'] == 0
    with SessionLocal() as db:
        memory = db.scalar(select(IncidentMemory).where(IncidentMemory.incident_id == identifier))
        assert not memory.retrieval_metadata['resolved']
    assert client.post(path+'/resolve', json=body).status_code == 200


def test_persistent_queue_cancel_and_retry(client, monkeypatch):
    monkeypatch.setattr(settings, 'job_execution', 'external')
    identifier = create(client)
    result = client.post(f'/api/incidents/{identifier}/investigate', json={}).json()
    job_id = result['job_id']
    assert client.get(f'/api/incidents/{identifier}').json()['executions'] == []
    assert client.post(f'/api/jobs/{job_id}/cancel', json={}).json()['status'] == 'cancelled'
    run_job(job_id)
    assert client.get(f'/api/incidents/{identifier}').json()['status'] == 'cancelled'
    assert client.post(f'/api/jobs/{job_id}/retry', json={}).status_code == 202
    recover()
    run_job(job_id)
    run_job(job_id)  # Duplicate deliveries cannot execute a completed job.
    result = client.get(f'/api/incidents/{identifier}').json()
    assert result['status'] == 'awaiting_review' and len(result['executions']) == 7
    assert result['jobs'][0]['attempts'] == 1


def test_restart_reuses_completed_checkpoints(client, monkeypatch):
    identifier, data = investigate(client)
    with SessionLocal() as db:
        job = db.get(Job, data['jobs'][0]['id'])
        job.status = 'running'
        inv = db.scalar(select(Investigation).where(Investigation.incident_id == identifier))
        inv.analysis_results = {k:v for k,v in inv.analysis_results.items() if k != 'report'}
        db.commit()
    recover()
    run_job(data['jobs'][0]['id'])
    result = client.get(f'/api/incidents/{identifier}').json()
    assert len(result['executions']) == 8
    assert result['jobs'][0]['attempts'] == 2
    assert result['status'] == 'awaiting_review'


def test_running_cancellation_preserves_completed_step(client, monkeypatch):
    monkeypatch.setattr(settings, 'job_execution', 'external')
    identifier = create(client)
    job_id = client.post(f'/api/incidents/{identifier}/investigate', json={}).json()['job_id']
    original = workflow.graph
    class CancelAtBoundary:
        def invoke(self, state):
            with SessionLocal() as db:
                db.get(Job, job_id).cancel_requested = True
                db.commit()
            return original.invoke(state)
    monkeypatch.setattr(workflow, 'graph', CancelAtBoundary())
    run_job(job_id)
    result = client.get(f'/api/incidents/{identifier}').json()
    assert result['status'] == 'cancelled' and result['executions'] == []


def test_retry_regenerates_downstream_patch_and_enforces_attempt_limit(client):
    identifier, data = investigate(client)
    job_id = data['jobs'][0]['id']
    with SessionLocal() as db:
        db.get(Job, job_id).status = 'failed'
        db.get(Incident, identifier).status = 'partial'
        inv = db.scalar(select(Investigation).where(Investigation.incident_id == identifier))
        inv.analysis_results = {**inv.analysis_results, 'errors':[{'agent':'memory','message':'Transient retrieval failure'}]}
        fix = db.get(ProposedFix, data['fix']['id'])
        fix.proposed_code = 'obsolete = True\n'
        db.commit()
    assert client.post(f'/api/jobs/{job_id}/retry',json={}).status_code == 202
    result = client.get(f'/api/incidents/{identifier}').json()
    assert result['fix']['id'] == data['fix']['id']
    assert result['fix']['proposed_code'] == data['fix']['proposed_code']
    assert result['fix']['validation_result']['status'] == 'passed'
    assert result['jobs'][0]['attempts'] == 2
    assert len(result['executions']) == 12  # Only memory and its downstream steps repeated.
    with SessionLocal() as db:
        job = db.get(Job,job_id)
        job.status,job.attempts = 'failed',3
        db.commit()
    assert client.post(f'/api/jobs/{job_id}/retry',json={}).status_code == 409
