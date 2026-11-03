import difflib


def unified_patch(path: str, original: str, proposed: str) -> str:
    """Preserve missing final newlines in a standard, reviewable unified diff."""
    records = difflib.unified_diff(
        original.splitlines(keepends=True), proposed.splitlines(keepends=True),
        fromfile='a/' + path, tofile='b/' + path,
    )
    return ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in records)
