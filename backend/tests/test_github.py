import base64
from types import SimpleNamespace
import httpx
import pytest
from app.core.config import settings
from app.services import github
from app.services.sample import BUGGY, FIXED


def test_github_draft_checks_base_and_does_not_repeat_existing_pr(monkeypatch):
    monkeypatch.setattr(settings, 'github_token', 'test-token')
    monkeypatch.setattr(settings, 'github_repository', 'example/checkout')
    incident = SimpleNamespace(id='incident-123', repository='local', title='Zero discount crash')
    fix = SimpleNamespace(path='checkout.py', original_code=BUGGY, proposed_code=FIXED,
                          explanation='Use percentage reduction.', validation_result={'status':'partial'})
    calls = []
    existing = False
    branch_exists = False
    def handle(request):
        nonlocal existing, branch_exists
        calls.append((request.method, request.url.path))
        assert request.headers['Authorization'] == 'Bearer test-token'
        path = request.url.path.removeprefix('/repos/example/checkout/')
        if path == 'pulls' and request.method == 'GET':
            data = [{'html_url':'https://github.com/example/checkout/pull/1'}] if existing else []
        elif path == 'git/ref/heads/main':
            data = {'object':{'sha':'base-sha'}}
        elif path.startswith('git/ref/heads/autorca'):
            if not branch_exists:
                return httpx.Response(404, json={'message':'Not Found'})
            data = {'object':{'sha':'branch-sha'}}
        elif path == 'git/refs':
            branch_exists = True
            data = {'ref':'refs/heads/autorca/incident-123'}
        elif path == 'contents/checkout.py' and request.method == 'GET':
            data = {'encoding':'base64','content':base64.b64encode(BUGGY.encode()).decode(),'sha':'blob-sha'}
        elif path == 'contents/checkout.py' and request.method == 'PUT':
            assert b'blob-sha' in request.content
            data = {'commit':{'sha':'fix-sha'}}
        elif path == 'pulls' and request.method == 'POST':
            assert b'"draft":true' in request.content
            existing = True
            data = {'html_url':'https://github.com/example/checkout/pull/1'}
        else:
            raise AssertionError(f'Unexpected request: {request.method} {path}')
        return httpx.Response(200, json=data)
    real_client = httpx.Client
    monkeypatch.setattr(github.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    assert github.create_pull_request(incident,fix).endswith('/pull/1')
    writes = [c for c in calls if c[0] != 'GET']
    assert [method for method,_ in writes] == ['POST','PUT','POST']
    assert github.create_pull_request(incident,fix).endswith('/pull/1')
    assert [c for c in calls if c[0] != 'GET'] == writes


def test_github_rejects_stale_remote_without_writes(monkeypatch):
    monkeypatch.setattr(settings, 'github_token', 'test-token')
    monkeypatch.setattr(settings, 'github_repository', 'example/checkout')
    incident = SimpleNamespace(id='incident-123',repository='local',title='Failure')
    fix = SimpleNamespace(path='checkout.py',original_code=BUGGY,proposed_code=FIXED)
    def handle(request):
        assert request.method == 'GET'
        path = request.url.path
        data = [] if path.endswith('/pulls') else {'object':{'sha':'base-sha'}} if '/git/ref/' in path else {'encoding':'base64','content':base64.b64encode(b'changed').decode()}
        return httpx.Response(200,json=data)
    real_client = httpx.Client
    monkeypatch.setattr(github.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    with pytest.raises(ValueError,match='differs'):
        github.create_pull_request(incident,fix)
