"""Read-only revision and content pinning. No checkout, hooks or repository code execution."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from app.services.security import digest, list_files, read_source, repository_root


class StaleSnapshotError(ValueError):
    pass


def git_read(root, *args):
    git = shutil.which('git')
    if not git:
        if (root / '.git').exists():
            raise ValueError('Git is required to pin this repository.')
        return None
    # Ignore injected GIT_* environment and global/system config; never invoke status,
    # filters, diffs, hooks, or a repository-defined executable.
    env = {'PATH': os.defpath, 'HOME': str(root), 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1'}
    try:
        result = subprocess.run([git, '--literal-pathspecs', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', '-C', str(root), *args],
                                capture_output=True, timeout=10, env=env)
    except (OSError, subprocess.SubprocessError):
        raise ValueError('Repository revision could not be read safely.') from None
    if result.returncode:
        return None
    return result.stdout


def revision(root):
    inside = git_read(root, 'rev-parse', '--is-inside-work-tree')
    if inside != b'true\n':
        if (root / '.git').exists():
            raise ValueError('Git repository metadata is unavailable.')
        return None
    raw = git_read(root, 'rev-parse', '--verify', 'HEAD^{commit}')
    if raw is None:
        # A repository without a first commit is explicitly content-pinned.
        return None
    sha = raw.decode('ascii').strip()
    if not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', sha):
        raise ValueError('Git returned an invalid commit identifier.')
    return sha


def identity(source):
    return digest(str(repository_root(source).resolve()))


def capture(source, commit=None):
    if source == 'github':
        from app.core.config import settings
        value = {'version': 1, 'kind': 'github_commit', 'repository_id': digest(settings.github_repository),
                 'commit_sha': commit, 'files': {}, 'modified': False, 'coverage': 'Pinned GitHub commit; file hashes accompany evidence.'}
    else:
        root = repository_root(source)
        commit = revision(root) if source == 'local' else None
        paths = list_files(source)
        manifest, blobs, total = {}, {}, 0
        for path in paths:
            raw = read_source(source, path)
            total += len(raw.encode())
            if total > 16 * 1024 * 1024:
                raise ValueError('Source snapshot exceeds 16 MiB; configure a smaller repository root.')
            manifest[path] = digest(raw)
            blob = b'blob ' + str(len(raw.encode())).encode() + b'\0' + raw.encode()
            blobs[path] = hashlib.new('sha256' if commit and len(commit) == 64 else 'sha1', blob).hexdigest()
        modified = None
        if commit:
            tree = git_read(root, 'ls-tree', '-r', '-z', commit, '--', *paths) if paths else b''
            if tree is None:
                raise ValueError('Pinned Git tree could not be read.')
            tracked = {}
            for item in tree.split(b'\0'):
                if item:
                    metadata, path = item.split(b'\t', 1)
                    tracked[path.decode('utf-8')] = metadata.split()[2].decode('ascii')
            modified = any(tracked.get(path) != sha for path, sha in blobs.items())
        # Prevent a mixed snapshot if the working tree changes during capture.
        if (source == 'local' and revision(root) != commit) or any(digest(read_source(source, p)) != h for p, h in manifest.items()):
            raise StaleSnapshotError('Source changed while pinning the snapshot. Submit again after edits finish.')
        value = {'version': 1, 'kind': 'git_worktree' if commit else ('bundled' if source == 'sample' else 'content'),
                 'repository_id': identity(source), 'commit_sha': commit, 'files': manifest,
                 'modified': modified, 'coverage': 'Up to 500 allowlisted files; modified compares captured files with HEAD only.'}
    value['snapshot_id'] = digest(json.dumps({k: v for k, v in value.items() if k != 'repository_id'}, sort_keys=True))
    return value


def verify_snapshot(snapshot, source):
    if not snapshot or snapshot.get('version') != 1:
        raise StaleSnapshotError('No pinned source snapshot is available. Submit a new incident.')
    payload = {k: v for k, v in snapshot.items() if k not in ('snapshot_id', 'repository_id')}
    if digest(json.dumps(payload, sort_keys=True)) != snapshot.get('snapshot_id'):
        raise StaleSnapshotError('Stored snapshot manifest is invalid. Submit a new incident.')
    if source in ('local', 'sample'):
        if identity(source) != snapshot['repository_id']:
            raise StaleSnapshotError('Configured repository changed since submission. Restore it or submit a new incident.')
        if source == 'local' and revision(repository_root(source)) != snapshot['commit_sha']:
            raise StaleSnapshotError('Repository revision changed since submission. Submit a new incident.')


def pinned(source):
    from app.db.session import SessionLocal
    from app.models.records import Incident
    kind, identifier = source.split('@', 1)
    with SessionLocal() as db:
        incident = db.get(Incident, identifier)
        if not incident or incident.repository != kind:
            raise ValueError('Pinned repository is unavailable.')
        snapshot = incident.repository_snapshot
    verify_snapshot(snapshot, kind)
    return kind, snapshot


def read_pinned(source, path):
    kind, snapshot = pinned(source)
    if path not in snapshot['files']:
        raise StaleSnapshotError('File was not captured at submission. Submit a new incident with the current source.')
    content = read_source(kind, path)
    if digest(content) != snapshot['files'][path]:
        raise StaleSnapshotError('Source file changed since submission. Submit a new incident.')
    return content


def pinned_files(source):
    _, snapshot = pinned(source)
    return sorted(snapshot['files'])
