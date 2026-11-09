import hashlib
import os
import re
from pathlib import Path, PurePosixPath
from app.core.config import ROOT, settings

ALLOWED = {'.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.md', '.toml', '.yaml', '.yml'}
IGNORED = {'.git', '.env', '.aws', '.ssh', '.venv', 'venv', 'node_modules', '__pycache__', '.next', 'dist', 'data'}


def redact(text: str) -> str:
    text = re.sub(r'(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|password|passwd|secret|token)\s*["\']?\s*[:=]\s*["\']?)[^\s"\',;]+', r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:sk-[a-zA-Z0-9_-]{12,}|gh[pousr]_[a-zA-Z0-9_]{12,}|github_pat_[a-zA-Z0-9_]+|AKIA[A-Z0-9]{16}|AIza[a-zA-Z0-9_-]{30,})\b', '[REDACTED]', text)
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----', '[REDACTED PRIVATE KEY]', text)
    return text


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def repository_root(source: str) -> Path:
    if source == 'sample':
        local = ROOT / 'examples' / 'buggy-python-app'
        return local if local.is_dir() else Path(__file__).resolve().parents[1] / 'fixtures' / 'sample'
    if source != 'local' or not settings.repository_root:
        raise ValueError('Configure REPOSITORY_ROOT on the backend to use a local repository.')
    root = Path(settings.repository_root).resolve()
    if not root.is_dir():
        raise ValueError('Configured repository is not a directory.')
    return root


def allowed_path(relative: str):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative or not path.parts or any(ord(c) < 32 or ord(c) == 127 for c in relative):
        raise ValueError('Only repository-relative file paths are permitted.')
    if any(p.startswith('.') or p in IGNORED for p in path.parts):
        raise ValueError('Hidden and ignored files cannot be read.')
    if path.suffix not in ALLOWED or any(re.search(r'(?i)(secret|credential|private.?key|package-lock|pnpm-lock)', part) for part in path.parts):
        raise ValueError('This file is not on the source allowlist.')
    if path.as_posix() != relative:
        raise ValueError('Use a canonical repository-relative path.')
    return path


def safe_path(source: str, relative: str) -> Path:
    path = allowed_path(relative)
    root = repository_root(source).resolve()
    candidate = root.joinpath(*path.parts)
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symbolic links cannot be read.')
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('File is unavailable inside the configured repository.')
    if resolved.stat().st_size > 80000:
        raise ValueError('File exceeds the 80 KB evidence limit.')
    return resolved


def read_source(source: str, path: str) -> str:
    if source.startswith(('local@', 'sample@')):
        from app.services.repository_snapshots import read_pinned
        return read_pinned(source, path)
    if source == 'github' or source.startswith('github@'):
        from app.services.github_source import read_file
        return read_file(source, path)
    text = safe_path(source, path).read_bytes().decode('utf-8')
    if len(text.encode()) > 80000:
        raise ValueError('File exceeds the evidence limit.')
    return text


def list_files(source: str) -> list[str]:
    if source.startswith(('local@', 'sample@')):
        from app.services.repository_snapshots import pinned_files
        return pinned_files(source)
    if source == 'github' or source.startswith('github@'):
        from app.services.github_source import files
        return files(source)
    root = repository_root(source)
    result = []
    examined = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED and not d.startswith('.') and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            examined += 1
            if examined > 10000 or len(result) >= 500:
                return result
            relative = (Path(directory) / name).relative_to(root).as_posix()
            try:
                safe_path(source, relative)
                result.append(relative)
            except ValueError:
                continue
    return result


def incident_source(incident):
    if incident.repository == 'github':
        if incident.repository_name != settings.github_repository:
            raise ValueError('The configured GitHub repository changed. Restore the incident repository before continuing.')
        if not re.fullmatch(r'[a-f0-9]{40}', incident.repository_commit):
            raise ValueError('GitHub incident has no pinned source revision.')
        return 'github@' + incident.repository_commit
    if incident.repository in ('local', 'sample') and getattr(incident, 'repository_snapshot', None):
        return incident.repository + '@' + incident.id
    return incident.repository


def redact_source(text: str) -> str:
    # Preserve original line numbers when removing a multiline private key.
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----',
                  lambda m: '[REDACTED PRIVATE KEY]' + '\n' * m.group().count('\n'), text)
    return redact(text)
