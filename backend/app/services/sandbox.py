"""Docker isolation adapter. No host-code fallback, shell, bind mounts, or user command strings."""
import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from app.core.config import settings
from app.services.security import redact

OUTPUT_LIMIT = 65536


def docker_env():
    # Docker needs its own context/Keychain config, never provider credentials.
    result = {k: os.environ[k] for k in ('PATH', 'HOME', 'DOCKER_CONTEXT', 'DOCKER_CONFIG') if k in os.environ}
    if settings.sandbox_docker_context:
        result['DOCKER_CONTEXT'] = settings.sandbox_docker_context
    return result


def control(args, timeout=10):
    docker = shutil.which('docker')
    if not docker:
        raise ValueError('Docker CLI is not installed.')
    return subprocess.run([docker, *args], capture_output=True, timeout=timeout, env=docker_env())


def availability():
    if not settings.sandbox_enabled:
        return {'available': False, 'reason': 'Set SANDBOX_ENABLED=true and configure a trusted image ID.'}
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', settings.sandbox_image):
        return {'available': False, 'reason': 'SANDBOX_IMAGE must be an immutable local sha256 image ID.'}
    try:
        context = control(['context', 'inspect', '--format', '{{json .Endpoints.docker.Host}}'])
        if context.returncode or not json.loads(context.stdout).startswith('unix://'):
            raise ValueError('Only a local Unix-socket Docker context is supported.')
        info = control(['info', '--format', '{{json .}}'])
        if info.returncode:
            raise ValueError('Docker daemon is unavailable.')
        daemon = json.loads(info.stdout)
        if daemon.get('OSType') != 'linux' or not all(daemon.get(k) for k in ('MemoryLimit', 'CpuCfsQuota', 'PidsLimit')):
            raise ValueError('The Docker daemon must enforce Linux memory, CPU, and process limits.')
        inspected = control(['image', 'inspect', settings.sandbox_image])
        if inspected.returncode:
            raise ValueError('Trusted runner image is not installed; build it explicitly first.')
        image = json.loads(inspected.stdout)[0]
        if image['Id'] != settings.sandbox_image or image['Config'].get('Volumes'):
            raise ValueError('Runner image must match the pinned ID and declare no volumes.')
        return {'available': True, 'reason': 'Docker and the pinned trusted runner image are ready.', 'image': settings.sandbox_image}
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        return {'available': False, 'reason': str(exc) if isinstance(exc, ValueError) else 'Docker readiness check failed.'}


def policy():
    return {'version': 1, 'image': settings.sandbox_image, 'docker_context': settings.sandbox_docker_context,
            'profile': 'python-unittest',
            'command': ['python', '-I', '-B', '/opt/autorca/bootstrap.py'],
            'network': 'none', 'user': '65534:65534', 'read_only_root': True,
            'memory_mb': 256, 'cpus': 0.5, 'pids': 32, 'output_limit_bytes': OUTPUT_LIMIT,
            'timeout_seconds': min(120, max(5, settings.sandbox_timeout_seconds)),
            'mounts': 'No host mounts; /workspace and /tmp are bounded ephemeral tmpfs.'}


def container_name(run_id, phase):
    if not re.fullmatch(r'[a-f0-9-]{36}', run_id) or phase not in ('before', 'after'):
        raise ValueError('Invalid container identity.')
    return f'autorca-test-{run_id}-{phase}'


def cleanup(name):
    try:
        result = control(['rm', '--force', name])
        # A missing container is already clean, but daemon/permission errors are not.
        return result.returncode == 0 or b'No such container' in result.stderr
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def run_snapshot(run_id: str, phase: str, files: dict, approved_policy: dict) -> dict:
    if approved_policy != policy():
        raise ValueError('Runner policy changed after authorization.')
    ready = availability()
    if not ready['available']:
        raise ValueError(ready['reason'])
    name = container_name(run_id, phase)
    args = ['create', '--name', name, '--interactive', '--pull=never', '--network=none',
            '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--user=65534:65534', '--pids-limit=32', '--memory=256m', '--memory-swap=256m',
            '--cpus=0.5', '--ulimit=nofile=128:128', '--init', '--no-healthcheck',
            '--log-driver=none', '--ipc=none', '--workdir=/workspace',
            '--tmpfs=/workspace:rw,nosuid,nodev,noexec,size=16m,mode=1777',
            '--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777',
            '--entrypoint=/usr/local/bin/python', approved_policy['image'],
            '-I', '-B', '/opt/autorca/bootstrap.py']
    start = time.monotonic()
    result = {'phase': phase, 'status': 'error', 'exit_code': None, 'output': '', 'container': name,
              'timed_out': False, 'output_limited': False, 'cleanup_succeeded': False}
    process = None
    try:
        created = control(args)
        if created.returncode:
            raise ValueError('Docker could not create a restricted container.')
        # Disk-backed stdin avoids a pipe deadlock when tests emit output early.
        with tempfile.TemporaryFile() as payload:
            payload.write(json.dumps({'files': files}, ensure_ascii=False).encode())
            payload.seek(0)
            process = subprocess.Popen([shutil.which('docker'), 'start', '--attach', '--interactive', name],
                stdin=payload, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=docker_env())
            output = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = approved_policy['timeout_seconds'] - (time.monotonic() - start)
                    if remaining <= 0:
                        result['timed_out'] = True
                        break
                    events = selector.select(min(0.2, remaining))
                    if events:
                        chunk = os.read(process.stdout.fileno(), 8192)
                        if not chunk:
                            break
                        room = OUTPUT_LIMIT - len(output)
                        output.extend(chunk[:room])
                        if len(chunk) > room:
                            result['output_limited'] = True
                            break
                result['output'] = redact(output.decode('utf-8', errors='replace'))
            if not result['timed_out'] and not result['output_limited']:
                process.wait(timeout=max(0.1, approved_policy['timeout_seconds'] - (time.monotonic() - start)))
                inspected = control(['inspect', '--format', '{{json .State}}', name])
                state = json.loads(inspected.stdout) if inspected.returncode == 0 else {}
                if state.get('Status') == 'exited' and not state.get('OOMKilled'):
                    result['exit_code'] = state['ExitCode']
                    result['status'] = 'passed' if state['ExitCode'] == 0 else 'failed'
                else:
                    result['error'] = 'Container did not exit normally or was killed by its memory limit.'
    except subprocess.TimeoutExpired:
        result['timed_out'] = True
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        result['error'] = 'Isolated runner operation failed; no host execution was attempted.'
    finally:
        result['cleanup_succeeded'] = cleanup(name)
        if process:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            process.stdout.close()
    if not result['cleanup_succeeded']:
        result['status'] = 'error'
        result['error'] = 'Container cleanup failed. Stop the recorded container before continuing.'
    result['duration_seconds'] = round(time.monotonic() - start, 3)
    return result
