"""Read bounded, regular source files from the configured GitHub repository only."""
import base64
import hashlib
import re
from urllib.parse import quote
import httpx
from app.core.config import settings
from app.services.security import allowed_path


def request(path, limit=8 * 1024 * 1024, **params):
    repository = settings.github_repository
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not settings.github_token:
        raise ValueError('Configure GITHUB_REPOSITORY and GITHUB_TOKEN to read GitHub source.')
    try:
        with httpx.Client(base_url=f'https://api.github.com/repos/{repository}/', timeout=10,
                          follow_redirects=False, headers={'Authorization': 'Bearer ' + settings.github_token,
                          'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}) as client:
            with client.stream('GET', path, params=params) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError('GitHub response exceeds the source limit.')
                import json
                return json.loads(data)
    except (httpx.HTTPError, UnicodeError) as exc:
        raise ValueError('GitHub source is unavailable. Check the configured repository, branch, and token permissions.') from None


def revision(source='github'):
    if source == 'github':
        value = request('git/ref/heads/' + quote(settings.github_base_branch, safe=''))['object']['sha']
    elif source.startswith('github@'):
        value = source.removeprefix('github@')
    else:
        raise ValueError('Unsupported repository source.')
    if not re.fullmatch(r'[a-f0-9]{40}', value):
        raise ValueError('GitHub did not return a valid commit.')
    return value


def tree(source):
    result = request('git/trees/' + revision(source), recursive='1')
    if result.get('truncated') or len(result.get('tree', [])) > 10000:
        raise ValueError('Repository tree exceeds the supported source limit.')
    items = {}
    for item in result.get('tree', []):
        if item.get('type') != 'blob' or item.get('mode') not in ('100644', '100755') or item.get('size', 80001) > 80000:
            continue
        try:
            allowed_path(item['path'])
        except ValueError:
            continue
        items[item['path']] = item['sha']
    return items


def files(source):
    return sorted(tree(source))[:500]


def read_file(source, path):
    allowed_path(path)
    sha = tree(source).get(path)
    return read_blob(sha)


def read_blob(sha):
    # Only hashes obtained from the allowlisted immutable tree reach this helper.
    if not sha or not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise ValueError('File is unavailable or is not a regular allowed source file.')
    blob = request('git/blobs/' + sha, limit=150000)
    if blob.get('encoding') != 'base64':
        raise ValueError('Unsupported GitHub file encoding.')
    raw = base64.b64decode(blob['content'])
    if len(raw) > 80000 or hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != sha:
        raise ValueError('GitHub source size or content hash is invalid.')
    try:
        return raw.decode('utf-8')
    except UnicodeError:
        raise ValueError('Only UTF-8 source files are supported.') from None
