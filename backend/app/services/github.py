import base64
from urllib.parse import quote
import httpx
from app.core.config import settings
from app.services.patches import fix_files


def commit_multiple(client, request, branch, sha, incident, files):
    base_commit = request('GET', 'git/commits/' + sha)
    entries = []
    for f in files:
        content = request('GET', 'contents/' + quote(f['path'], safe='/'), params={'ref': sha})
        if content.get('encoding') != 'base64' or base64.b64decode(content['content']).decode() != f['original_code']:
            raise ValueError('GitHub source differs from the reviewed original; investigate the current version.')
        blob = request('POST', 'git/blobs', json={'content': f['proposed_code'], 'encoding': 'utf-8'})
        # Preserve each tracked file mode; symlinks and non-files cannot be patched.
        parent, _, name = f['path'].rpartition('/')
        tree_sha = base_commit['tree']['sha']
        for part in [*filter(None, parent.split('/')), name]:
            tree = request('GET', 'git/trees/' + tree_sha)
            item = next((e for e in tree['tree'] if e['path'] == part), None)
            if not item: raise ValueError('Reviewed file is absent from the base tree.')
            tree_sha = item['sha']
        if item['mode'] not in ('100644', '100755'):
            raise ValueError('Only regular tracked files can be patched.')
        entries.append({'path':f['path'], 'mode':item['mode'], 'type':'blob', 'sha':blob['sha']})
    tree = request('POST', 'git/trees', json={'base_tree':base_commit['tree']['sha'], 'tree':entries})
    ref = client.get('git/ref/heads/' + quote(branch, safe=''))
    if ref.status_code == 404:
        request('POST', 'git/refs', json={'ref':'refs/heads/'+branch, 'sha':sha})
        branch_sha = sha
    else:
        ref.raise_for_status()
        branch_sha = ref.json()['object']['sha']
    if branch_sha != sha:
        current = request('GET', 'git/commits/' + branch_sha)
        if current['tree']['sha'] == tree['sha']:
            return  # Exact reviewed tree already committed by an earlier attempt.
        raise ValueError('The AutoRCA branch changed; manual review is required.')
    commit = request('POST', 'git/commits', json={'message':f'fix: {incident.title}', 'tree':tree['sha'], 'parents':[sha]})
    request('PATCH', 'git/refs/heads/' + quote(branch, safe=''), json={'sha':commit['sha'], 'force':False})


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
        if len(fix_files(fix)) > 1:
            commit_multiple(client, request, branch, sha, incident, fix_files(fix))
        else:
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
