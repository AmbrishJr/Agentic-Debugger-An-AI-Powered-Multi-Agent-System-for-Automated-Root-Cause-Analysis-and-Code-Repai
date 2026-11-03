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
    text = re.sub(r'\b(?:sk-[a-zA-Z0-9_-]{12,}|gh[pousr]_[a-zA-Z0-9_]{12,}|github_pat_[a-zA-Z0-9_]+|AKIA[A-Z0-9]{16})\b', '[REDACTED]', text)
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----', '[REDACTED PRIVATE KEY]', text)
    return text


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def repository_root(source: str) -> Path:
    if source == 'sample':
        return ROOT / 'examples' / 'buggy-python-app'
    if source != 'local' or not settings.repository_root:
        raise ValueError('Configure REPOSITORY_ROOT on the backend to use a local repository.')
    root = Path(settings.repository_root).resolve()
    if not root.is_dir():
        raise ValueError('Configured repository is not a directory.')
    return root


def safe_path(source: str, relative: str) -> Path:
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or '\\' in relative or not path.parts or any(ord(c) < 32 or ord(c) == 127 for c in relative):
        raise ValueError('Only repository-relative file paths are permitted.')
    if any(p.startswith('.') or p in IGNORED for p in path.parts):
        raise ValueError('Hidden and ignored files cannot be read.')
    if path.suffix not in ALLOWED or any(re.search(r'(?i)(secret|credential|private.?key|package-lock|pnpm-lock)', part) for part in path.parts):
        raise ValueError('This file is not on the source allowlist.')
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
    text = safe_path(source, path).read_text(encoding='utf-8')
    if len(text.encode()) > 80000:
        raise ValueError('File exceeds the evidence limit.')
    return text


def list_files(source: str) -> list[str]:
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
