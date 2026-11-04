import json
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.records import ValidationRun
from app.services import sandbox
from tests.test_workflow import investigate


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(settings, 'sandbox_enabled', True)
    monkeypatch.setattr(settings, 'sandbox_image', 'sha256:' + 'a' * 64)
    monkeypatch.setattr(sandbox, 'availability', lambda: {'available':True, 'reason':'Test adapter'})


def plan(client, identifier):
    response = client.post(f'/api/incidents/{identifier}/validation-plans',json={'files':['checkout.py','test_checkout.py']})
    assert response.status_code == 201, response.text
    return response.json()


def test_missing_runtime_fails_closed(client):
    identifier, _ = investigate(client)
    assert client.get('/api/sandbox').json()['available'] is False
    response = client.post(f'/api/incidents/{identifier}/validation-plans',json={'files':['checkout.py','test_checkout.py']})
    assert response.status_code == 400
    assert client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'] == []


def test_planning_does_not_execute_and_requires_exact_consent(client, ready, monkeypatch):
    identifier, _ = investigate(client)
    monkeypatch.setattr(sandbox,'run_snapshot',lambda *args: pytest.fail('Planning must not execute code'))
    planned = plan(client, identifier)
    assert 'snapshot' not in planned
    assert planned['policy']['network'] == 'none'
    assert len(planned['manifest']) == 2
    path = f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize'
    assert client.post(path,json={'plan_hash':planned['plan_hash']}).status_code == 422
    assert client.post(path,json={'authorized':False,'plan_hash':planned['plan_hash']}).status_code == 422
    assert client.post(path,json={'authorized':True,'plan_hash':'b'*64}).status_code == 400


def test_expired_and_stale_plans_cannot_execute(client, ready, monkeypatch):
    identifier, _ = investigate(client)
    planned = plan(client,identifier)
    path = f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize'
    with SessionLocal() as db:
        db.get(ValidationRun,planned['id']).expires_at = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        db.commit()
    assert 'expired' in client.post(path,json={'authorized':True,'plan_hash':planned['plan_hash']}).json()['error']['message']
    planned = plan(client,identifier)
    monkeypatch.setattr('app.services.validation_runs.read_source',lambda *args:'changed')
    path = f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize'
    assert 'changed' in client.post(path,json={'authorized':True,'plan_hash':planned['plan_hash']}).json()['error']['message']


def test_authorized_before_after_run_is_audited_and_one_use(client, ready, monkeypatch):
    calls=[]
    def execute(run_id,phase,files,policy):
        calls.append((phase,files['checkout.py']))
        return {'status':'failed' if phase=='before' else 'passed','exit_code':1 if phase=='before' else 0,'output':'test output','cleanup_succeeded':True}
    monkeypatch.setattr(sandbox,'run_snapshot',execute)
    identifier,_=investigate(client)
    planned=plan(client,identifier)
    path=f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize'
    body={'authorized':True,'plan_hash':planned['plan_hash']}
    assert client.post(path,json=body).status_code==202
    assert [x[0] for x in calls]==['before','after']
    assert calls[0][1]!=calls[1][1]
    assert client.post(path,json=body).status_code==400
    run=client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'][0]
    assert run['status']=='completed' and run['authorized_at'] and run['finished_at']
    with SessionLocal() as db:
        assert db.get(ValidationRun,run['id']).snapshot=={}
    fix=client.get(f'/api/incidents/{identifier}/patch').json()
    assert fix['validation_result']['isolated']['after']['status']=='passed'
    assert client.get(f'/api/incidents/{identifier}/report').json()['validation']['isolated_run_id']==run['id']


def test_runner_error_does_not_preserve_old_pass_or_allow_approval(client,ready,monkeypatch):
    monkeypatch.setattr(sandbox,'run_snapshot',lambda *args: {'status':'error','exit_code':None,'output':'','cleanup_succeeded':True,'timed_out':True})
    identifier,_=investigate(client)
    planned=plan(client,identifier)
    assert client.post(f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize',json={'authorized':True,'plan_hash':planned['plan_hash']}).status_code==202
    assert client.get(f'/api/incidents/{identifier}/patch').json()['validation_result']['status']=='error'
    assert client.post(f'/api/incidents/{identifier}/approve',json={}).status_code==409


def test_no_shell_mount_credentials_or_unpinned_image(ready,monkeypatch):
    calls=[]
    def control(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1,stderr=b'create failed',stdout=b'')
    monkeypatch.setattr(sandbox,'control',control)
    monkeypatch.setenv('OPENAI_API_KEY','never-forward')
    monkeypatch.setenv('GITHUB_TOKEN','never-forward')
    assert 'OPENAI_API_KEY' not in sandbox.docker_env()
    assert 'GITHUB_TOKEN' not in sandbox.docker_env()
    result=sandbox.run_snapshot('a'*8+'-'+'b'*4+'-'+'c'*4+'-'+'d'*4+'-'+'e'*12,'before',{'test_a.py':'pass'},sandbox.policy())
    command=calls[0]
    for flag in ('--read-only','--network=none','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=32','--memory=256m','--pull=never','--log-driver=none'):
        assert flag in command
    assert not any(arg.startswith(('--volume','--mount','--env')) for arg in command)
    assert command[-4:]==['-I','-B','/opt/autorca/bootstrap.py','python-unittest']
    assert calls[-1][:2]==['rm','--force']
    assert result['status']=='error'


def test_policy_change_prevents_execution(ready,monkeypatch):
    previous=sandbox.policy()
    monkeypatch.setattr(settings,'sandbox_timeout_seconds',60)
    with pytest.raises(ValueError,match='policy changed'):
        sandbox.run_snapshot('irrelevant','after',{},previous)


def test_failed_cleanup_blocks_subsequent_execution(client, ready, monkeypatch):
    monkeypatch.setattr(sandbox,'run_snapshot',lambda *args: {'status':'error','exit_code':None,'output':'','cleanup_succeeded':False})
    identifier,_=investigate(client)
    planned=plan(client,identifier)
    path=f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize'
    assert client.post(path,json={'authorized':True,'plan_hash':planned['plan_hash']}).status_code==202
    assert client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'][0]['status']=='cleanup_failed'
    second=plan(client,identifier)
    path=f'/api/incidents/{identifier}/validation-runs/{second["id"]}/authorize'
    assert client.post(path,json={'authorized':True,'plan_hash':second['plan_hash']}).status_code==409


def test_expired_snapshot_bodies_are_purged(client, ready):
    identifier,_=investigate(client)
    planned=plan(client,identifier)
    with SessionLocal() as db:
        db.get(ValidationRun,planned['id']).expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        db.commit()
    assert client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'][0]['status']=='expired'
    with SessionLocal() as db:
        assert db.get(ValidationRun,planned['id']).snapshot=={}
