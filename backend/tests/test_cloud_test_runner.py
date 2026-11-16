import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('failure', [None, 'tests', 'launch', 'cleanup', 'remote'])
def test_runner_limits_database_to_local_and_always_cleans_up(monkeypatch, capsys, failure):
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'test_cloud.py'
    spec = importlib.util.spec_from_file_location('cloud_test_runner', path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(sys, 'argv', [str(path), '--docker-context', 'test-local'])
    calls, secrets = [], {}

    def run(command, **kwargs):
        calls.append(command)
        if command[:3] == ['docker', '--context', 'test-local']:
            args = command[3:]
            if args[:2] == ['context', 'inspect']:
                endpoint = 'ssh://remote' if failure == 'remote' else 'unix:///local/docker.sock'
                output = json.dumps([{'Endpoints': {'docker': {'Host': endpoint}}}])
            elif args[0] == 'run':
                assert '--pull=never' in args
                assert args[args.index('--publish') + 1] == '127.0.0.1::5432'
                assert '--mount' not in args and '--volume' not in args
                assert args[-1] == 'postgres:17-alpine'
                name = args[args.index('--name') + 1]
                assert name.startswith('autorca-tests-')
                secrets['container'] = name
                file = Path(args[args.index('--env-file') + 1])
                assert file.stat().st_mode & 0o777 == 0o600
                secrets['file'] = file
                secrets['password'] = file.read_text().split('POSTGRES_PASSWORD=', 1)[1].strip()
                if failure == 'launch':
                    raise subprocess.TimeoutExpired(command, 30)
                output = 'container-id'
            elif args[0] == 'port':
                output = '127.0.0.1:15432\n'
            elif args[0] == 'exec':
                output = 'ready'
            elif args[0] == 'rm':
                assert args == ['rm', '--force', '--volumes', secrets['container']]
                return subprocess.CompletedProcess(command, 1 if failure == 'cleanup' else 0, '', 'failed' if failure == 'cleanup' else '')
            else:
                pytest.fail(f'Unexpected Docker command: {args[0]}')
            return subprocess.CompletedProcess(command, 0, output, '')
        assert command == [sys.executable, '-m', 'pytest', 'backend/tests', '-q']
        url = kwargs['env']['AUTORCA_TEST_POSTGRES_URL']
        assert url.endswith('@127.0.0.1:15432/autorca_test')
        assert not secrets['file'].exists()
        return subprocess.CompletedProcess(command, 1 if failure == 'tests' else 0, url, secrets['password'])

    monkeypatch.setattr(runner.subprocess, 'run', run)
    if failure in ('launch', 'cleanup', 'remote'):
        with pytest.raises((subprocess.TimeoutExpired, RuntimeError)):
            runner.main()
    else:
        assert runner.main() == (1 if failure == 'tests' else 0)
    cleaned = [call for call in calls if call[3:4] == ['rm']]
    assert len(cleaned) == (0 if failure == 'remote' else 1)
    if failure != 'remote':
        output = capsys.readouterr()
        assert secrets['password'] not in output.out + output.err
        assert not secrets['file'].exists()
