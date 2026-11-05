import asyncio
import base64
import hashlib
from types import SimpleNamespace
from pathlib import Path
import pytest
from sqlalchemy import select, func
from app.core.config import settings, Settings, validate_hosted_settings
from app.db.session import SessionLocal, engine
from app.models.records import Job, Incident, ValidationRun, ProposedFix, User
from app.services import cloud_jobs, github_source, sandbox, vercel_sandbox
from app.agents.workflow import AGENTS
from tests.test_workflow import create, investigate


def queued(client, monkeypatch):
    monkeypatch.setattr(settings, 'job_execution', 'external')
    incident = create(client)
    job_id = client.post(f'/api/incidents/{incident}/investigate', json={}).json()['job_id']
    with SessionLocal() as db:
        token = db.get(Job, job_id).dispatch_token
    return incident, job_id, token


def test_cloud_steps_resume_and_reject_duplicate_runs(client, monkeypatch):
    incident, job_id, token = queued(client, monkeypatch)
    assert cloud_jobs.run_stage(job_id, token, 'run-one', 'triage')
    cloud_jobs.fail_job(job_id, token, run_id='duplicate-run')
    assert not cloud_jobs.run_stage(job_id, token, 'duplicate-run', 'evidence')
    assert cloud_jobs.run_stage(job_id, token, 'run-one', 'triage')
    for stage in [*AGENTS[1:], 'finish']:
        assert cloud_jobs.run_stage(job_id, token, 'run-one', stage)
    data = client.get(f'/api/incidents/{incident}').json()
    assert data['status'] == 'awaiting_review'
    assert len(data['executions']) == 7
    assert data['jobs'][0]['attempts'] == 1
    assert client.post(f'/api/incidents/{incident}/approve', json={}).status_code == 200
    assert not cloud_jobs.run_stage(job_id, token, 'run-one', 'finish')
    assert client.get(f'/api/incidents/{incident}').json()['status'] == 'approved'


def test_cloud_cancel_retry_fences_old_steps(client, monkeypatch):
    incident, job_id, token = queued(client, monkeypatch)
    cloud_jobs.run_stage(job_id, token, 'run-one', 'triage')
    assert client.post(f'/api/jobs/{job_id}/cancel', json={}).status_code == 200
    assert not cloud_jobs.run_stage(job_id, token, 'run-one', 'evidence')
    result = client.post(f'/api/jobs/{job_id}/retry', json={})
    assert result.status_code == 202
    new_token = result.json()['dispatch_token']
    assert new_token != token
    assert not cloud_jobs.run_stage(job_id, token, 'run-one', 'evidence')
    cloud_jobs.fail_job(job_id, token)  # Late failure from the old run must not poison the retry.
    for stage in [*AGENTS, 'finish']:
        cloud_jobs.run_stage(job_id, new_token, 'run-two', stage)
    data = client.get(f'/api/incidents/{incident}').json()
    assert data['status'] == 'awaiting_review'
    assert len(data['executions']) == 7
    assert data['jobs'][0]['attempts'] == 2


def test_cloud_dispatch_failure_is_visible_and_retryable(client, monkeypatch):
    sdk = pytest.importorskip('vercel.workflow')
    monkeypatch.setattr(settings, 'job_execution', 'vercel')
    async def broken(*args, **kwargs):
        raise RuntimeError('provider secret must not escape')
    monkeypatch.setattr(sdk, 'start', broken)
    incident = create(client)
    response = client.post(f'/api/incidents/{incident}/investigate', json={})
    assert response.status_code == 503 and 'secret' not in response.text
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.incident_id == incident))
        assert job.status == 'failed'
        identifier, old_token = job.id, job.dispatch_token
    async def started(*args, **kwargs):
        assert args[1] == identifier and args[2] != old_token
        return SimpleNamespace(run_id='test-run')
    monkeypatch.setattr(sdk, 'start', started)
    response = client.post(f'/api/jobs/{identifier}/retry', json={})
    assert response.status_code == 202
    assert response.json()['workflow_run_id'] == 'test-run'


def test_terminal_workflow_failure_reconciles_job(client, monkeypatch):
    sdk = pytest.importorskip('vercel.workflow')
    incident, job_id, token = queued(client, monkeypatch)
    cloud_jobs.run_stage(job_id, token, 'run-one', 'triage')
    async def status():
        return 'failed'
    monkeypatch.setattr(sdk, 'get_run', lambda identifier: SimpleNamespace(status=status))
    asyncio.run(cloud_jobs.refresh(job_id))
    data = client.get(f'/api/incidents/{incident}').json()
    assert data['status'] == 'failed' and len(data['executions']) == 1


@pytest.mark.parametrize('saved_result', [False, True])
def test_consumed_cloud_validation_is_not_replayed(client, monkeypatch, saved_result):
    incident, data = investigate(client)
    monkeypatch.setattr(settings, 'job_execution', 'external')
    monkeypatch.setattr(sandbox, 'availability', lambda: {'available': True})
    monkeypatch.setattr(sandbox, 'cleanup', lambda name: True)
    plan = client.post(f'/api/incidents/{incident}/validation-plans', json={
        'files': ['checkout.py', 'test_checkout.py']}).json()
    assert client.post(f'/api/incidents/{incident}/validation-runs/{plan["id"]}/authorize', json={
        'authorized': True, 'plan_hash': plan['plan_hash']}).status_code == 202
    from app.services import validation_runs
    calls = []
    def interrupted(run_id):
        calls.append(run_id)
        if saved_result:
            with SessionLocal() as db:
                run = db.get(ValidationRun, run_id)
                run.status, run.snapshot, run.result = 'completed', {}, {'measured': True}
                db.commit()
        raise RuntimeError('function interrupted')
    monkeypatch.setattr(validation_runs, 'execute_validation', interrupted)
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.kind == 'validation'))
        identifier, token = job.id, job.dispatch_token
    with pytest.raises(RuntimeError):
        cloud_jobs.run_stage(identifier, token, 'run-tests', 'isolated')
    assert not cloud_jobs.run_stage(identifier, token, 'run-tests', 'isolated')
    assert calls == [plan['id']]
    with SessionLocal() as db:
        assert db.get(ValidationRun, plan['id']).status == ('completed' if saved_result else 'error')
        assert db.get(ValidationRun, plan['id']).snapshot == {}
        if saved_result:
            assert db.get(ValidationRun, plan['id']).result == {'measured':True}
            assert db.get(Job, identifier).status == 'completed'


def test_cloud_sdk_registers_identifier_only_steps():
    pytest.importorskip('vercel.workflow')
    from app.cloud_workflows import isolated_validation, investigation_stage, execute_job
    assert isolated_validation.max_retries == 0
    assert investigation_stage.max_retries == 2
    assert list(execute_job._signature.parameters) == ['job_id', 'token', 'kind']


def mock_github(monkeypatch):
    commit = 'a' * 40
    source = 'answer = 42\n'
    raw = source.encode()
    blob_sha = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    calls = []
    def request(path, **kwargs):
        calls.append(path)
        if path.startswith('git/ref/'):
            return {'object': {'sha': commit}}
        if path.startswith('git/trees/'):
            return {'tree': [
                {'path':'app.py','sha':blob_sha,'mode':'100644','type':'blob','size':len(raw)},
                {'path':'link.py','sha':blob_sha,'mode':'120000','type':'blob','size':len(raw)},
                {'path':'.env','sha':blob_sha,'mode':'100644','type':'blob','size':len(raw)},
                {'path':'secret.py','sha':blob_sha,'mode':'100644','type':'blob','size':len(raw)}]}
        assert path == 'git/blobs/' + blob_sha
        return {'encoding':'base64','content':base64.b64encode(raw).decode()}
    monkeypatch.setattr(github_source, 'request', request)
    return commit, source, calls


def test_github_source_pins_commit_and_excludes_links_and_secrets(client, monkeypatch):
    commit, source, calls = mock_github(monkeypatch)
    incident = create(client, repository='github', selected_files=['app.py'])
    assert client.get(f'/api/incidents/{incident}').json()['repository_commit'] == commit
    assert github_source.files('github@' + commit) == ['app.py']
    assert github_source.read_file('github@' + commit, 'app.py') == source
    assert 'git/trees/' + commit in calls
    for path in ('link.py', '.env', 'secret.py', '../app.py', '/app.py'):
        with pytest.raises(ValueError):
            github_source.read_file('github@' + commit, path)
    from app.services.security import incident_source
    monkeypatch.setattr(settings, 'github_repository', 'different/repository')
    with SessionLocal() as db, pytest.raises(ValueError, match='repository changed'):
        incident_source(db.get(Incident, incident))


def test_github_rejects_incomplete_tree_and_wrong_blob(monkeypatch):
    monkeypatch.setattr(github_source, 'request', lambda *a, **k: {'truncated':True, 'tree':[]})
    with pytest.raises(ValueError, match='limit'):
        github_source.files('github@' + 'a'*40)
    monkeypatch.setattr(github_source, 'tree', lambda source: {'app.py':'b'*40})
    monkeypatch.setattr(github_source, 'request', lambda *a, **k: {'encoding':'base64','content':'eA=='})
    with pytest.raises(ValueError, match='hash'):
        github_source.read_file('github@' + 'a'*40, 'app.py')


def test_hosted_configuration_fails_closed():
    config = Settings(_env_file=None, database_url='sqlite:///:memory:')
    with pytest.raises(ValueError, match='PostgreSQL'):
        validate_hosted_settings(config)
    config.database_url='postgresql://localhost/test'
    config.job_execution='vercel'
    config.migrate_on_startup=False
    config.auth_enabled=True
    config.secure_cookies=True
    config.autorca_api_token='x'*32
    config.public_origin='https://workspace.example'
    config.repository_root=''
    config.sandbox_enabled=False
    validate_hosted_settings(config)
    config.auth_enabled=False
    with pytest.raises(ValueError, match='authentication'):
        validate_hosted_settings(config)


@pytest.mark.parametrize('exit_code,noisy,cleaned,expected', [(0,False,True,'passed'),(1,False,True,'failed'),(0,True,True,'error'),(0,False,False,'error')])
def test_vercel_runner_policy_output_and_cleanup(monkeypatch, exit_code, noisy, cleaned, expected):
    sdk = pytest.importorskip('vercel.sandbox')
    from vercel.sandbox import sync
    monkeypatch.setattr(settings, 'sandbox_provider', 'vercel')
    monkeypatch.setattr(settings, 'sandbox_enabled', True)
    monkeypatch.setattr(settings, 'sandbox_vercel_image', 'owner/runner@sha256:'+'a'*64)
    monkeypatch.setenv('VERCEL_OIDC_TOKEN', 'test-only')
    created = []
    class Box:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run_command(self, command, args, **kwargs):
            assert command == 'python' and args[:3] == ['-I','-B','/opt/autorca/cloud_bootstrap.py']
            assert kwargs['env'] == {} and not kwargs['sudo']
            assert callable(kwargs['on_start'])  # SDK must not replay a process after it starts.
            assert kwargs['stdout'].writable() and kwargs['stderr'].writable()
            kwargs['stdout'].write('x' * (70000 if noisy else 12))
            return SimpleNamespace(returncode=exit_code)
    def create_box(**kwargs):
        created.append(kwargs)
        assert kwargs['network_policy'] == sdk.NetworkPolicy.deny_all()
        assert kwargs['persistent'] is False and kwargs['ports'] == [] and kwargs['mounts'] == {}
        assert kwargs['env'] == {}
        return Box()
    monkeypatch.setattr(sync, 'create_sandbox', create_box)
    monkeypatch.setattr(vercel_sandbox, 'cleanup', lambda name: cleaned)
    result = sandbox.run_snapshot('00000000-0000-0000-0000-000000000001', 'before', {'test_app.py':'pass'}, sandbox.policy())
    assert result['status'] == expected
    assert result['cleanup_succeeded'] == cleaned
    assert result['output_limited'] == noisy
    assert len(result['output'].encode()) <= 65536
    assert len(created) == 1


def test_bundled_cloud_sample_matches_local():
    root = Path(__file__).resolve().parents[1]
    for file in (root/'app/fixtures/sample').iterdir():
        if file.is_file():
            assert file.read_bytes() == (root.parent/'examples/buggy-python-app'/file.name).read_bytes()


def test_postgres_transfer_preserves_admin_and_refuses_overwrite(client, tmp_path):
    if engine.dialect.name != 'postgresql':
        pytest.skip('Requires disposable PostgreSQL')
    from sqlalchemy import create_engine
    from app.db.session import Base
    from app.db.transfer import transfer
    source = tmp_path/'source.db'
    old = create_engine('sqlite:///' + str(source))
    Base.metadata.create_all(old)
    with old.begin() as connection:
        connection.execute(User.__table__.insert().values(username='existing-admin', password_hash='original-password-hash', role='admin'))
    old.dispose()
    before = source.read_bytes()
    counts = transfer(source, engine)
    assert counts['users'] == 1
    assert source.read_bytes() == before
    with SessionLocal() as db:
        user = db.scalar(select(User))
        assert user.role == 'admin' and user.password_hash == 'original-password-hash'
    with pytest.raises(ValueError, match='empty'):
        transfer(source, engine)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_postgres_cloud_duplicate_delivery_is_serialized(client, monkeypatch):
    if engine.dialect.name != 'postgresql':
        pytest.skip('Requires disposable PostgreSQL')
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from app.agents import workflow
    incident, job_id, token = queued(client, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    original = workflow.triage
    calls = []
    def delayed(state):
        calls.append(state['incident_id'])
        entered.set()
        assert release.wait(10)
        return original(state)
    monkeypatch.setattr(workflow, 'triage', delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cloud_jobs.run_stage, job_id, token, 'one', 'triage')
        assert entered.wait(10)
        duplicate = pool.submit(cloud_jobs.run_stage, job_id, token, 'two', 'triage')
        release.set()
        assert first.result(timeout=10)
        assert not duplicate.result(timeout=10)
    assert calls == [incident]


def test_failed_cleanup_can_be_retried_without_executing_tests(client, monkeypatch):
    incident, data = investigate(client)
    monkeypatch.setattr(sandbox, 'availability', lambda: {'available':True})
    plan = client.post(f'/api/incidents/{incident}/validation-plans', json={'files':['checkout.py','test_checkout.py']}).json()
    path = f'/api/incidents/{incident}/validation-runs/{plan["id"]}/cleanup'
    assert client.post(path, json={}).status_code == 409  # Cannot stop a planned or running run.
    with SessionLocal() as db:
        db.get(ValidationRun, plan['id']).status = 'cleanup_failed'
        db.commit()
    monkeypatch.setattr(sandbox, 'cleanup', lambda name: False)
    assert client.post(path, json={}).status_code == 503
    calls = []
    monkeypatch.setattr(sandbox, 'cleanup', lambda name: calls.append(name) or True)
    result = client.post(path, json={})
    assert result.status_code == 200 and result.json()['status'] == 'error'
    assert result.json()['result']['cleanup_succeeded']
    assert len(calls) == 2
    assert client.post(path, json={}).status_code == 409


def test_postgres_recovers_interrupted_pr_without_duplicate_publication(client, monkeypatch):
    if engine.dialect.name != 'postgresql':
        pytest.skip('Requires disposable PostgreSQL')
    from app.api import routes
    incident, data = investigate(client)
    assert client.post(f'/api/incidents/{incident}/approve', json={}).status_code == 200
    with SessionLocal() as db:
        db.get(Incident, incident).repository = 'github'
        db.get(ProposedFix, data['fix']['id']).pr_status = 'creating'
        db.commit()
    monkeypatch.setattr(settings, 'github_token', 'test-only')
    monkeypatch.setattr(settings, 'github_repository', 'owner/disposable')
    calls = []
    def published(*args):
        calls.append(True)
        return 'https://github.com/owner/disposable/pull/1'
    monkeypatch.setattr(routes, 'create_pull_request', published)
    path = f'/api/incidents/{incident}/pull-request'
    assert client.post(path, json={'authorized':True}).status_code == 200
    assert client.post(path, json={'authorized':True}).status_code == 200
    assert calls == [True]
