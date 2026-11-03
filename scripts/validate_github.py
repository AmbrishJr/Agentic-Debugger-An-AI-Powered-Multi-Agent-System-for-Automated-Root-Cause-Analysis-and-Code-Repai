"""Explicit opt-in real integration check against a NEW private disposable repository.

Loads a token from the backend environment or `gh auth token` into process memory only.
No credential is printed, stored, or sent anywhere except api.github.com. This script
does not modify an existing repository and deliberately retains artifacts for review.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', help='Authorize private repo, fixture commit, and draft PR creation')
    parser.add_argument('--output', default='docs/github-validation.json')
    args = parser.parse_args()
    if not args.execute:
        parser.error('Pass --execute to authorize creation of a NEW private validation repository.')
    with tempfile.TemporaryDirectory(prefix='autorca-github-check-') as directory:
        os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(directory) / 'validation.db')
        os.environ['AUTORCA_API_TOKEN'] = ''
        os.environ['SANDBOX_ENABLED'] = 'false'
        from app.core.config import settings
        from app.services.sample import BUGGY, FIXED, REGRESSION_TEST
        from app.services.security import digest
        from app.services.patches import unified_patch
        from app.services.validation import validate
        from app.models.records import Incident, ProposedFix
        from app.db.session import SessionLocal
        from app.main import app
        from fastapi.testclient import TestClient

        token = settings.github_token
        if not token:
            auth = subprocess.run(['gh', 'auth', 'token', '--hostname', 'github.com'], capture_output=True, text=True, timeout=15)
            if auth.returncode or not auth.stdout.strip():
                raise RuntimeError('No usable GitHub credentials. Run gh auth login or configure GITHUB_TOKEN.')
            token = auth.stdout.strip()
        report = {'status': 'started', 'scope': 'Real app approval and GitHub REST flow with a deterministic fixture; not an LLM investigation.'}
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        def save():
            output.write_text(json.dumps(report, indent=2) + '\n')
        save()
        try:
            with httpx.Client(base_url='https://api.github.com', timeout=30,
                headers={'Authorization': 'Bearer ' + token, 'Accept':'application/vnd.github+json', 'X-GitHub-Api-Version':'2022-11-28'}) as github:
                def call(method, path, **kwargs):
                    response = github.request(method, path, **kwargs)
                    response.raise_for_status()
                    return response.json()
                login = call('GET', '/user')['login']
                name = 'autorca-x-validation-' + uuid.uuid4().hex[:12]
                repo = call('POST', '/user/repos', json={'name':name,'private':True,'auto_init':True,
                    'description':'Disposable AutoRCA-X credentialed integration validation. Synthetic test fixture only.',
                    'has_issues':False,'has_wiki':False,'has_projects':False})
                if not repo['private'] or repo['owner']['login'] != login:
                    raise RuntimeError('Unexpected repository ownership or visibility.')
                report.update(repository=repo['full_name'], repository_url=repo['html_url'], private=True)
                save()
                prefix = '/repos/' + repo['full_name']
                branch = repo['default_branch']
                # The new repo contains no workflow files, repository hooks, or third-party dependencies.
                fixture = {'checkout.py': BUGGY, 'test_checkout.py': REGRESSION_TEST}
                for filename, content in fixture.items():
                    call('PUT', prefix + '/contents/' + filename, json={'message':'Add synthetic regression fixture',
                         'content':base64.b64encode(content.encode()).decode(),'branch':branch})
                    Path(directory, filename).write_text(content)
                settings.github_token, settings.github_repository, settings.github_base_branch = token, repo['full_name'], branch
                settings.repository_root = directory
                with TestClient(app) as client:
                    with SessionLocal() as db:
                        incident = Incident(title='Integration check: zero discount', error_log='Synthetic integration validation only.',
                            repository='local', mode='demo', status='awaiting_review')
                        db.add(incident)
                        db.flush()
                        fix = ProposedFix(incident_id=incident.id, path='checkout.py', original_code=BUGGY, proposed_code=FIXED,
                            original_sha256=digest(BUGGY), proposed_patch=unified_patch('checkout.py',BUGGY,FIXED),
                            explanation='Synthetic fixture validates the app GitHub publishing transport.', risks=['Integration test only.'],
                            validation_result=validate('local','checkout.py',digest(BUGGY),FIXED,'demo'))
                        db.add(fix)
                        db.commit()
                        incident_id = incident.id
                    path = f'/api/incidents/{incident_id}'
                    assert client.post(path + '/pull-request', json={'authorized':True}).status_code == 409
                    assert client.post(path + '/approve', json={'note':'User-authorized disposable integration validation.'}).status_code == 200
                    assert client.post(path + '/pull-request', json={}).status_code == 422
                    response = client.post(path + '/pull-request', json={'authorized':True})
                    if response.status_code != 200:
                        raise RuntimeError('App PR creation failed with HTTP ' + str(response.status_code))
                    pr_url = response.json()['url']
                    report['pull_request_url'] = pr_url
                    save()
                    assert client.post(path + '/pull-request', json={'authorized':True}).json()['url'] == pr_url
                number = int(pr_url.rsplit('/',1)[-1])
                pr = call('GET', prefix + f'/pulls/{number}')
                changed = call('GET', prefix + f'/pulls/{number}/files')
                assert pr['draft'] and pr['base']['ref'] == branch
                assert [f['filename'] for f in changed] == ['checkout.py']
                baseline = call('GET', prefix + '/contents/checkout.py', params={'ref':branch})
                patched = call('GET', prefix + '/contents/checkout.py', params={'ref':pr['head']['sha']})
                assert base64.b64decode(baseline['content']).decode() == BUGGY
                assert base64.b64decode(patched['content']).decode() == FIXED
                report.update(status='passed', checks=['Approval gate','Explicit PR authorization','Private repository',
                    'Draft PR','Exactly one changed file','Patched content matches reviewed proposal','Base unchanged','Retry returns same PR'],
                    head_sha=pr['head']['sha'], base_branch=branch, cleanup='Private repository and draft PR retained for inspection; no merge or deployment.')
                save()
        except Exception as exc:
            report.update(status='failed', error_type=type(exc).__name__)
            save()
            raise RuntimeError('Integration check failed; inspect the credential-free report for retained artifact URLs.') from None
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
