import pytest
from app.core.config import settings
from app.services.security import safe_path, redact, list_files, digest
from app.services.validation import run_trusted_fixture, validate
from app.services.sample import SAMPLE_LOG, BUGGY, FIXED
from tests.test_workflow import investigate


@pytest.mark.parametrize('path', ['../README.md','/etc/passwd','..\\checkout.py','.env','node_modules/a.py','.git/config','credentials.json', 'secrets/config.py', 'bad\nname.py'])
def test_path_boundaries(path):
    with pytest.raises(ValueError):
        safe_path('sample', path)


def test_symlinks_and_file_limits(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    root.mkdir()
    outside = tmp_path / 'outside.py'
    outside.write_text('private = True')
    (root / 'link.py').symlink_to(outside)
    (root / 'large.py').write_text('x' * 80001)
    (root / 'safe.py').write_text('x = 1')
    monkeypatch.setattr(settings, 'repository_root', str(root))
    assert list_files('local') == ['safe.py']
    for name in ('link.py','large.py'):
        with pytest.raises(ValueError):
            safe_path('local', name)


def test_redaction_before_storage(client):
    secret = 'sk-1234567890abcdefghijkl'
    log = SAMPLE_LOG + f'\napi_key={secret}\npassword=hunter2\nAuthorization: Bearer ghp_1234567890abcdefgh'
    response = client.post('/api/incidents', json={'title':'Secret test','error_log':log})
    assert response.status_code == 201
    assert secret not in response.text and 'hunter2' not in response.text
    assert '[REDACTED]' in response.json()['error_log']


def test_input_size_and_content_type(client):
    assert client.post('/api/incidents', json={'title':'Large input','error_log':'x' * 50001}).status_code == 422
    assert client.post('/api/incidents', content='x' * 100001, headers={'Content-Type':'application/json'}).status_code == 413
    assert client.post('/api/incidents', content='plain text').status_code == 415
    response = client.post('/api/incidents', json={'title':'x','error_log':'password=private'})
    assert 'password=private' not in response.text


def test_api_authentication(client, monkeypatch):
    monkeypatch.setattr(settings, 'autorca_api_token', 'test-token')
    assert client.get('/api/health').status_code == 401
    assert client.get('/api/health', headers={'X-AutoRCA-Token':'test-token'}).status_code == 200


def test_arbitrary_fixture_code_is_never_executed():
    with pytest.raises(ValueError):
        run_trusted_fixture("import os; os.system('echo unsafe')")
    result = validate('sample','checkout.py',digest(BUGGY),FIXED + '# AI-generated variation\n','demo')
    assert result['status'] == 'partial'
    assert result['fixture'] == {}
    assert result['checks'][-1]['status'] == 'skipped'


def test_syntax_and_stale_hash_fail_validation():
    result = validate('sample','checkout.py','wrong-hash','def broken(:','live')
    assert result['status'] == 'failed'
    assert [c['status'] for c in result['checks'][:2]] == ['failed','failed']


def test_changed_source_cannot_be_approved(client, monkeypatch):
    incident_id, _ = investigate(client)
    monkeypatch.setattr('app.api.routes.read_source', lambda *args: 'modified since review')
    assert client.post(f'/api/incidents/{incident_id}/approve', json={}).status_code == 409
    assert client.get(f'/api/incidents/{incident_id}').json()['fix']['approval_status'] == 'pending'
