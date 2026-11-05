"""One ephemeral microVM per authorized test phase; never execute source on the host."""
import io
import json
import os
import re
import time
from app.core.config import settings
from app.services.security import redact

OUTPUT_LIMIT = 65536


def availability():
    if not settings.sandbox_enabled:
        return {'available': False, 'reason': 'Isolated tests are disabled by the administrator.'}
    if not re.fullmatch(r'[A-Za-z0-9._/-]+@sha256:[a-f0-9]{64}', settings.sandbox_vercel_image):
        return {'available': False, 'reason': 'Configure a trusted Vercel runner image pinned by sha256 digest.'}
    if not (os.getenv('VERCEL') == '1' or os.getenv('VERCEL_OIDC_TOKEN') or all(os.getenv(k) for k in ('VERCEL_TOKEN', 'VERCEL_TEAM_ID', 'VERCEL_PROJECT_ID'))):
        return {'available': False, 'reason': 'Vercel project authentication is required for isolated tests.'}
    try:
        from vercel.sandbox import sync
    except ImportError:
        return {'available': False, 'reason': 'Install the cloud Python dependencies to use Vercel Sandbox.'}
    return {'available': True, 'reason': 'Vercel runner is configured; access and image availability are checked when an authorized run starts.',
            'image': settings.sandbox_vercel_image}


def policy(profile='python-unittest'):
    if profile not in ('python-unittest', 'python-pytest'):
        raise ValueError('Unsupported test profile.')
    return {'version': 1, 'provider': 'vercel', 'image': settings.sandbox_vercel_image, 'profile': profile,
            'command': ['python', '-I', '-B', '/opt/autorca/cloud_bootstrap.py', profile],
            'network': 'none', 'user': '65534:65534', 'read_only_root': False,
            'memory_mb': 2048, 'process_memory_mb': 256, 'cpus': 1, 'pids': 32,
            'output_limit_bytes': OUTPUT_LIMIT,
            'timeout_seconds': min(120, max(5, settings.sandbox_timeout_seconds)),
            'mounts': 'Ephemeral microVM filesystem; no host mounts, persistent drives, or application credentials.'}


def cleanup(name):
    from vercel.sandbox import sync, SandboxApiError
    try:
        box = sync.get_sandbox(name=name)
        box.destroy(delete_orphan_snapshots=True)
        return True
    except SandboxApiError as exc:
        return exc.status_code == 404
    except Exception:
        return False


class OutputLimit(Exception):
    pass


class BoundedOutput(io.TextIOBase):
    def __init__(self):
        self.data = bytearray()
        self.limited = False

    def write(self, value):
        raw = value.encode('utf-8', errors='replace')
        room = OUTPUT_LIMIT - len(self.data)
        self.data.extend(raw[:room])
        if len(raw) > room:
            self.limited = True
            raise OutputLimit()
        return len(value)

    def flush(self):
        pass


def run_snapshot(run_id, phase, files, approved_policy):
    from vercel.sandbox import sync, NetworkPolicy, SandboxResources
    from app.services.sandbox import container_name
    if approved_policy != policy(approved_policy['profile']):
        raise ValueError('Runner policy changed after authorization.')
    ready = availability()
    if not ready['available']:
        raise ValueError(ready['reason'])
    name = container_name(run_id, phase)
    output = BoundedOutput()
    start = time.monotonic()
    result = {'phase': phase, 'status': 'error', 'exit_code': None, 'output': '', 'container': name,
              'provider': 'vercel', 'timed_out': False, 'output_limited': False, 'cleanup_succeeded': False}
    try:
        with sync.create_sandbox(name=name, image=approved_policy['image'], persistent=False,
                execution_time_limit=approved_policy['timeout_seconds'] + 15,
                resources=SandboxResources(vcpus=1, memory=2048), network_policy=NetworkPolicy.deny_all(),
                env={}, ports=[], mounts={}) as box:
            command = box.run_command('python', ['-I', '-B', '/opt/autorca/cloud_bootstrap.py', approved_policy['profile']],
                input=json.dumps({'files': files}), env={}, sudo=False,
                kill_after=approved_policy['timeout_seconds'], stdout=output, stderr=output,
                on_start=lambda command: None)
            result['exit_code'] = command.returncode
            result['status'] = 'passed' if command.returncode == 0 else ('error' if command.returncode < 0 or command.returncode >= 128 else 'failed')
    except OutputLimit:
        result['output_limited'] = True
    except TimeoutError:
        result['timed_out'] = True
    except Exception:
        result['error'] = 'Vercel isolated runner failed. Check image access and project configuration.'
    finally:
        result['output'] = redact(output.data.decode('utf-8', errors='replace'))
        result['output_limited'] = output.limited
        result['cleanup_succeeded'] = cleanup(name)
        result['duration_seconds'] = round(time.monotonic() - start, 3)
    if not result['cleanup_succeeded']:
        result['status'] = 'error'
        result['error'] = 'Sandbox cleanup could not be confirmed. Check the recorded sandbox before another run.'
    return result
