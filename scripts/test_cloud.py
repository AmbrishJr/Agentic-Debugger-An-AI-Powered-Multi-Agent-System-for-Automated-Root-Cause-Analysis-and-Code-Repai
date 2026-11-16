#!/usr/bin/env python3
"""Run backend tests on disposable local PostgreSQL with the current Python environment.

Uses an already-installed postgres:17-alpine Docker image; never pulls an image,
connects to a hosted database, or mounts project files inside the database container.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker-context', help='Local Docker context (defaults to the current context)')
    args = parser.parse_args()
    context = args.docker_context or subprocess.run(
        ['docker', 'context', 'show'], check=True, capture_output=True, text=True, timeout=15).stdout.strip()
    docker = ['docker', '--context', context]

    def run(*arguments, check=True):
        return subprocess.run([*docker, *arguments], check=check, capture_output=True, text=True, timeout=30)

    metadata = json.loads(run('context', 'inspect', context).stdout)
    if not metadata[0]['Endpoints']['docker']['Host'].startswith('unix://'):
        raise RuntimeError('Tests require a local Docker socket.')
    name = 'autorca-tests-' + uuid.uuid4().hex[:12]
    password = secrets.token_urlsafe(32)
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix='autorca-test-env-') as temporary:
            env_file = Path(temporary) / 'postgres.env'
            descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as handle:
                handle.write(f'POSTGRES_DB=autorca_test\nPOSTGRES_USER=autorca_test\nPOSTGRES_PASSWORD={password}\n')
            # Mark cleanup as necessary before launch: the daemon can create a
            # container even if the CLI times out before returning its ID.
            created = True
            run('run', '--detach', '--pull=never', '--name', name, '--publish', '127.0.0.1::5432',
                '--tmpfs', '/var/lib/postgresql/data:rw', '--env-file', str(env_file), 'postgres:17-alpine')
        port = run('port', name, '5432/tcp').stdout.strip()
        if not port.startswith('127.0.0.1:') or not port.removeprefix('127.0.0.1:').isdigit():
            raise RuntimeError('Database port must be bound to local loopback only.')
        for attempt in range(60):
            if run('exec', name, 'pg_isready', '-U', 'autorca_test', '-d', 'autorca_test', check=False).returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('Disposable database did not become ready.')
        environment = {**os.environ,
                       'PYTHONPATH': str(ROOT / 'backend'),
                       'AUTORCA_TEST_POSTGRES_URL': f'postgresql+psycopg://autorca_test:{password}@{port}/autorca_test'}
        print('Running backend suite against disposable local PostgreSQL.', flush=True)
        result = subprocess.run([sys.executable, '-m', 'pytest', 'backend/tests', '-q'],
                                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=600)
        # Test/driver errors may include their synthetic connection URL.
        for output in (result.stdout, result.stderr):
            print(output.replace(environment['AUTORCA_TEST_POSTGRES_URL'], '[test database]')
                  .replace(password, '[redacted]'), end='')
        return result.returncode
    finally:
        if created:
            removed = run('rm', '--force', '--volumes', name, check=False)
            if removed.returncode and 'No such container' not in removed.stderr:
                print(f'Cleanup could not be confirmed for temporary container {name}.', file=sys.stderr)
                raise RuntimeError(f'Cleanup could not be confirmed for {name}.')
            print('Disposable test database removed.', flush=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('Cloud tests could not complete. Check the local Docker context, installed postgres:17-alpine image, Python dependencies and test-container cleanup.', file=sys.stderr)
        raise SystemExit(1)
