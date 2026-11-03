import base64
from urllib.parse import quote
import httpx
from app.core.config import settings


def create_pull_request(incident, fix) -> str:
    if not settings.github_token or not settings.github_repository:
        raise ValueError('Configure GITHUB_TOKEN and GITHUB_REPOSITORY on the backend.')
    if incident.repository != 'local':
        raise ValueError('GitHub publishing is limited to the configured local repository.')
    repository = settings.github_repository
    if len(repository.split('/')) != 2 or any(not p or not all(c.isalnum() or c in '._-' for c in p) for p in repository.split('/')):
        raise ValueError('GITHUB_REPOSITORY must be owner/repository.')
    with httpx.Client(base_url=f'https://api.github.com/repos/{repository}/', timeout=30,
                      headers={'Authorization': f'Bearer {settings.github_token}', 'Accept': 'application/vnd.github+json',
                               'X-GitHub-Api-Version': '2022-11-28'}) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        branch = 'autorca/' + incident.id
        owner = repository.split('/')[0]
        existing = request('GET', 'pulls', params={'state': 'all', 'head': f'{owner}:{branch}'})
        if existing:
            return existing[0]['html_url']
        base = request('GET', 'git/ref/heads/' + quote(settings.github_base_branch, safe=''))
        sha = base['object']['sha']
        content = request('GET', 'contents/' + quote(fix.path, safe='/'), params={'ref': sha})
        if content.get('encoding') != 'base64' or base64.b64decode(content['content']).decode() != fix.original_code:
            raise ValueError('GitHub source differs from the reviewed original; investigate the current version.')
        # Retry-safe deterministic branch; never overwrite a branch modified by another actor.
        ref = client.get('git/ref/heads/' + quote(branch, safe=''))
        if ref.status_code == 404:
            request('POST', 'git/refs', json={'ref': 'refs/heads/' + branch, 'sha': sha})
        else:
            ref.raise_for_status()
        branch_content = request('GET', 'contents/' + quote(fix.path, safe='/'), params={'ref': branch})
        actual = base64.b64decode(branch_content['content']).decode()
        if actual != fix.proposed_code:
            if actual != fix.original_code:
                raise ValueError('The AutoRCA branch changed; manual review is required.')
            request('PUT', 'contents/' + quote(fix.path, safe='/'), json={
                'message': f'fix: {incident.title}', 'branch': branch, 'sha': branch_content['sha'],
                'content': base64.b64encode(fix.proposed_code.encode()).decode()})
        body = (f'## Problem\n{incident.title}\n\n## Proposed change\n{fix.explanation}\n\n'
                f'## Validation\nStatus: {fix.validation_result.get("status", "unknown")}. '
                'See the local AutoRCA-X report for individual checks. Untrusted repository tests were not executed on the host.\n\n'
                f'Incident: {incident.id}\nHuman approval recorded. This draft requires independent review before merging.')
        result = request('POST', 'pulls', json={'title': f'fix: {incident.title}', 'head': branch,
                         'base': settings.github_base_branch, 'body': body, 'draft': True})
        return result['html_url']
