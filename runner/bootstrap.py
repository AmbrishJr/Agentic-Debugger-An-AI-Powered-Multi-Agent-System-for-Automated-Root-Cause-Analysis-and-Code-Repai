"""Runs inside the restricted container only. No application secrets or Docker socket."""
import json
import os
from pathlib import Path, PurePosixPath
import sys
import unittest


def main():
    raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Snapshot is too large')
    files = json.loads(raw)['files']
    if not 1 <= len(files) <= 32:
        raise ValueError('Invalid file count')
    for name, content in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.suffix != '.py' or any(p.startswith('.') for p in path.parts) or '\\' in name or any(ord(c) < 32 for c in name):
            raise ValueError('Invalid snapshot path')
        destination = Path('/workspace').joinpath(*path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding='utf-8')
    os.chdir('/workspace')
    sys.path.insert(0, '/workspace')
    profile = sys.argv[1] if len(sys.argv) > 1 else 'python-unittest'
    if profile == 'python-pytest':
        os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
        import pytest
        return int(pytest.main(['-q', '-p', 'no:cacheprovider', '/workspace']))
    if profile != 'python-unittest':
        raise ValueError('Unsupported test profile')
    suite = unittest.defaultTestLoader.discover('/workspace', pattern='test*.py')
    count = suite.countTestCases()
    if count == 0:
        print('No unittest tests discovered.', file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    # Counts/output are evidence supplied by repository code, not a trusted coverage oracle.
    print('AUTORCA_UNITTEST_SUMMARY=' + json.dumps({'discovered': count, 'run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped)}), flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
