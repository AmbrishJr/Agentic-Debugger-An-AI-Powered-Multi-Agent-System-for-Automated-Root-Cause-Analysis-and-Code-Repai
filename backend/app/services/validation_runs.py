import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.records import Incident, ProposedFix, ValidationRun, now, uid
from app.services.security import read_source, digest, redact, incident_source
from app.services import sandbox
from app.services.patches import fix_files


def patch_digest(fix):
    return digest(json.dumps({'files': fix_files(fix), 'primary': fix.proposed_code}, sort_keys=True))


def public_run(run):
    # Source snapshots stay server-side; the review plan exposes bounded manifests only.
    return {c.name: getattr(run, c.name) for c in run.__table__.columns if c.name != 'snapshot'}


def expire_plans(db):
    expired = db.scalars(select(ValidationRun).where(ValidationRun.status == 'planned', ValidationRun.expires_at < now())).all()
    for run in expired:
        run.status, run.snapshot = 'expired', {}
    if expired:
        db.commit()


def prepare_plan(incident, fix, paths, profile='python-unittest'):
    if fix.approval_status != 'pending' or incident.status not in ('awaiting_review', 'partial'):
        raise ValueError('Prepare and run tests before recording the final review decision.')
    ready = sandbox.availability()
    if not ready['available']:
        raise ValueError(ready['reason'])
    paths = list(dict.fromkeys(paths))
    if any(f['path'] not in paths for f in fix_files(fix)):
        raise ValueError('Include every proposed patch target in the source snapshot.')
    if not any(p.rsplit('/', 1)[-1].startswith('test') and p.endswith('.py') for p in paths):
        raise ValueError('Include at least one test*.py file.')
    snapshot, manifest = {}, []
    for path in paths:
        if not path.endswith('.py'):
            raise ValueError('This runner profile accepts Python source and test files only.')
        source = read_source(incident_source(incident), path)
        if redact(source) != source:
            raise ValueError('Secret-like content in a selected file prevents creating a test snapshot.')
        snapshot[path] = source
        manifest.append({'path': path, 'sha256': digest(source), 'bytes': len(source.encode())})
    if any(digest(snapshot[f['path']]) != f['original_sha256'] for f in fix_files(fix)):
        raise ValueError('Patch target changed since investigation. Submit a new incident.')
    if sum(item['bytes'] for item in manifest) + sum(len(f['proposed_code'].encode()) for f in fix_files(fix)) > 1024 * 1024:
        raise ValueError('Snapshot and patch exceed the 1 MiB limit.')
    identifier = uid()
    policy = sandbox.policy(profile)
    patch_hash = patch_digest(fix)
    plan_hash = digest(json.dumps({'id': identifier, 'files': manifest, 'patch': patch_hash, 'policy': policy}, sort_keys=True))
    return ValidationRun(id=identifier, incident_id=incident.id, fix_id=fix.id, status='planned',
        plan_hash=plan_hash, manifest=manifest, snapshot=snapshot, policy=policy,
        proposed_sha256=patch_hash, expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), result={})


def check_plan(incident, fix, run, expected_hash):
    if run.status != 'planned' or run.plan_hash != expected_hash:
        raise ValueError('Validation plan was already used or does not match the reviewed plan.')
    if datetime.fromisoformat(run.expires_at) < datetime.now(timezone.utc):
        raise ValueError('Authorization plan expired. Prepare a new snapshot.')
    if run.policy != sandbox.policy(run.policy['profile']) or patch_digest(fix) != run.proposed_sha256:
        raise ValueError('Runner policy or proposed code changed. Prepare a new plan.')
    if fix.approval_status != 'pending' or incident.status not in ('awaiting_review', 'partial'):
        raise ValueError('Tests must be authorized before the final review decision.')
    for item in run.manifest:
        if digest(read_source(incident_source(incident), item['path'])) != item['sha256']:
            raise ValueError('A source or test file changed after planning. Prepare a new snapshot.')


def execute_validation(run_id):
    with SessionLocal() as db:
        run = db.get(ValidationRun, run_id)
        if not run or run.status != 'running' or not run.authorized_at:
            return
        fix = db.get(ProposedFix, run.fix_id)
        original, proposed = dict(run.snapshot), dict(run.snapshot)
        for f in fix_files(fix):
            proposed[f['path']] = f['proposed_code']
        policy = run.policy
        checks = [c for c in fix.validation_result.get('checks', []) if c['name'] not in ('Repository tests', 'Isolated tests before fix', 'Isolated tests after fix')]
    try:
        before = sandbox.run_snapshot(run_id, 'before', original, policy)
        if before['status'] == 'error':
            after = {'status': 'skipped', 'output': '', 'exit_code': None, 'error': 'Baseline runner failed; patched run not started.'}
        else:
            after = sandbox.run_snapshot(run_id, 'after', proposed, policy)
        result = {'before': before, 'after': after, 'policy': policy,
                  'interpretation': 'Isolated process exit status is measured. Repository test output and counts are untrusted evidence, not proof of correctness or coverage.'}
        state = 'completed' if after['status'] in ('passed', 'failed') else 'error'
        status = after['status'] if state == 'completed' else 'error'
        if before.get('cleanup_succeeded') is False or after.get('cleanup_succeeded') is False:
            state, status = 'cleanup_failed', 'error'
        checks.extend([
            {'name': 'Isolated tests before fix', 'status': 'passed' if before['status'] == 'failed' else 'skipped',
             'detail': 'Original suite exited nonzero; inspect output for the actual cause.' if before['status'] == 'failed' else 'The original failure was not reproduced; inspect the baseline output.'},
            {'name': 'Isolated tests after fix', 'status': after['status'], 'detail': policy['profile'] + '; no network, host mounts, or application credentials.'},
        ])
        if status == 'passed' and any(c['status'] == 'failed' for c in checks):
            status = 'failed'
        elif status == 'passed' and any(c['status'] == 'skipped' for c in checks):
            status = 'partial'
    except Exception:
        cleaned = all([sandbox.cleanup(sandbox.container_name(run_id, phase)) for phase in ('before', 'after')])
        state, status = ('error' if cleaned else 'cleanup_failed'), 'error'
        result = {'error': 'Runner failed. No repository code was executed on the host.', 'cleanup_succeeded': cleaned}
    with SessionLocal() as db:
        run, fix = db.get(ValidationRun, run_id), db.get(ProposedFix, run.fix_id)
        run.status, run.finished_at, run.result = state, now(), result
        # Drop snapshot bodies after execution; keep audit manifest and hash.
        run.snapshot = {}
        boundary = ('Vercel microVM with denied network access and no application credentials. ' if policy.get('provider') == 'vercel'
                    else 'Resource-limited Docker containers are not a VM security boundary on Linux. ')
        fix.validation_result = {**fix.validation_result, 'status': status, 'checks': checks, 'isolated_run_id': run_id,
            'isolated': result, 'limitations': boundary + 'Repository tests and their outputs can be misleading; independent code review remains required.'}
        db.commit()
