import difflib


def unified_patch(path: str, original: str, proposed: str) -> str:
    """Preserve missing final newlines in a standard, reviewable unified diff."""
    records = difflib.unified_diff(
        original.splitlines(keepends=True), proposed.splitlines(keepends=True),
        fromfile='a/' + path, tofile='b/' + path,
    )
    return ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in records)


def fix_files(fix):
    return getattr(fix, 'files', None) or [{'path': fix.path, 'original_code': fix.original_code, 'proposed_code': fix.proposed_code,
                          'original_sha256': getattr(fix, 'original_sha256', ''), 'diff': getattr(fix, 'proposed_patch', '')}]
