import json
from pathlib import PurePosixPath
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.records import Incident, ProposedFix, ValidationRun, now, uid
from app.services.security import read_source, digest, redact, incident_source
from app.services import sandbox
from app.services.patches import fix_files
from app.services.sample import BUGGY, FIXED, REGRESSION_TEST
from app.services.verification_specs import bind_spec, assess_spec


def patch_digest(fix):
    return digest(json.dumps({'files': fix_files(fix), 'primary': fix.proposed_code}, sort_keys=True))


# This digest pins the reviewed packaged test, not a mutable repository lookup.
BUNDLED_TEST_SHA = 'eb7546d4b5e2628153844cfe4e4774f567b0570871ac9619e8326a3c7baba064'


def protected_test_path(path):
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    return (any(p.lower() in ('test', 'tests', 'testing', 'fixtures', '__tests__') for p in parts[:-1])
            or name.startswith('test') or name.endswith(('_test.py', '_tests.py'))
            or name in ('conftest.py', 'pytest.ini', 'tox.ini', 'setup.cfg', 'pyproject.toml',
                        'setup.py', 'sitecustomize.py', 'usercustomize.py')
            or name.startswith(('pytest', 'unittest')))


def plan_digest(run_id, manifest, patch_hash, policy, specification=None):
    value = {'id': run_id, 'files': manifest, 'patch': patch_hash, 'policy': policy}
    if specification is not None:
        value['verification_spec'] = specification
    return digest(json.dumps(value, sort_keys=True))


def check_integrity(incident, fix, run):
    if run.policy != sandbox.policy(run.policy['profile']) or patch_digest(fix) != run.proposed_sha256:
        raise ValueError('Runner policy or proposed code changed. Prepare a new plan.')
    specification = run.result.get('verification_spec')
    if plan_digest(run.id, run.manifest, run.proposed_sha256, run.policy, specification) != run.plan_hash:
        raise ValueError('Validation manifest changed. Prepare a new plan.')
    if specification is not None:
        if run.policy['profile'] != 'python-unittest' or specification != bind_spec(specification['declaration'], run.snapshot,
                incident.repository_snapshot, specification['reviewer'], specification['reviewed_at']):
            raise ValueError('Verification specification changed. Prepare a new plan.')
    if {item['path'] for item in run.manifest} != set(run.snapshot) or len(run.manifest) != len(run.snapshot):
        raise ValueError('Snapshot manifest does not match its files.')
    for item in run.manifest:
        path = item['path']
        role = 'test' if protected_test_path(path) else 'source'
        if item.get('role') != role:
            raise ValueError('Test manifest is missing or changed. Prepare a new plan.')
        content = run.snapshot[path]
        if digest(content) != item['sha256'] or len(content.encode()) != item['bytes']:
            raise ValueError('Snapshot contents changed. Prepare a new plan.')
        if digest(read_source(incident_source(incident), path)) != item['sha256']:
            raise ValueError('A source or test file changed after planning. Prepare a new snapshot.')
    for f in fix_files(fix):
        if protected_test_path(f['path']):
            raise ValueError('Validation tests and test support files cannot be patch targets.')
        if f['path'] not in run.snapshot or digest(run.snapshot[f['path']]) != f['original_sha256']:
            raise ValueError('Patch does not match the original snapshot.')


def fixture_proof(original, proposed, policy, before, after, patch_hash, manifest):
    test = original.get('test_checkout.py', '')
    trusted = (set(original) == {'checkout.py', 'test_checkout.py'}
               and original['checkout.py'] == BUGGY and proposed.get('checkout.py') == FIXED
               and proposed.get('test_checkout.py') == test
               and digest(test) in (BUNDLED_TEST_SHA, digest(REGRESSION_TEST))
               and policy['profile'] == 'python-unittest')
    def summary(phase):
        try:
            lines = phase.get('output', '').splitlines()
            return json.loads(next(line.split('=', 1)[1] for line in lines if line.startswith('AUTORCA_UNITTEST_SUMMARY=')))
        except (ValueError, StopIteration):
            return {}
    expected = {'discovered': 4, 'run': 4, 'failures': 2, 'errors': 2, 'skipped': 0}
    passing = {'discovered': 4, 'run': 4, 'failures': 0, 'errors': 0, 'skipped': 0}
    clean = all(p.get('cleanup_succeeded') is True and not p.get('timed_out') and not p.get('output_limited') for p in (before, after))
    return {'version': 1, 'scope': 'bundled-checkout-v1' if trusted else 'repository-tests',
            'integrity': clean, 'independent_tests': trusted, 'isolated': clean,
            'expected_failure': trusted and before.get('status') == 'failed' and before.get('exit_code') == 1
                and summary(before) == expected and 'ZeroDivisionError' in before.get('output', ''),
            'regressions_passed': trusted and after.get('status') == 'passed' and after.get('exit_code') == 0 and summary(after) == passing,
            'patch_sha256': patch_hash, 'source_manifest': manifest,
            'test_sha256': digest(test) if trusted else None, 'environment': policy}


def public_run(run):
    # Source snapshots stay server-side; the review plan exposes bounded manifests only.
    return {c.name: getattr(run, c.name) for c in run.__table__.columns if c.name != 'snapshot'}


def expire_plans(db):
    expired = db.scalars(select(ValidationRun).where(ValidationRun.status == 'planned', ValidationRun.expires_at < now())).all()
    for run in expired:
        run.status, run.snapshot = 'expired', {}
    if expired:
        db.commit()


def prepare_plan(incident, fix, paths, profile='python-unittest', verification_spec=None, reviewer='local developer'):
    if fix.approval_status != 'pending' or incident.status not in ('awaiting_review', 'partial'):
        raise ValueError('Prepare and run tests before recording the final review decision.')
    if any(protected_test_path(f['path']) for f in fix_files(fix)):
        raise ValueError('Validation tests and test support files cannot be patch targets.')
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
        manifest.append({'path': path, 'sha256': digest(source), 'bytes': len(source.encode()), 'role': 'test' if protected_test_path(path) else 'source'})
    if any(digest(snapshot[f['path']]) != f['original_sha256'] for f in fix_files(fix)):
        raise ValueError('Patch target changed since investigation. Submit a new incident.')
    if sum(item['bytes'] for item in manifest) + sum(len(f['proposed_code'].encode()) for f in fix_files(fix)) > 1024 * 1024:
        raise ValueError('Snapshot and patch exceed the 1 MiB limit.')
    identifier = uid()
    policy = sandbox.policy(profile)
    if verification_spec is not None and profile != 'python-unittest':
        raise ValueError('Reviewed verification specifications currently require unittest.')
    specification = bind_spec(verification_spec, snapshot, incident.repository_snapshot, reviewer, now()) if verification_spec is not None else None
    patch_hash = patch_digest(fix)
    plan_hash = plan_digest(identifier, manifest, patch_hash, policy, specification)
    return ValidationRun(id=identifier, incident_id=incident.id, fix_id=fix.id, status='planned',
        plan_hash=plan_hash, manifest=manifest, snapshot=snapshot, policy=policy,
        proposed_sha256=patch_hash, expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        result={'verification_spec': specification} if specification is not None else {})


def check_plan(incident, fix, run, expected_hash):
    if run.status != 'planned' or run.plan_hash != expected_hash:
        raise ValueError('Validation plan was already used or does not match the reviewed plan.')
    if datetime.fromisoformat(run.expires_at) < datetime.now(timezone.utc):
        raise ValueError('Authorization plan expired. Prepare a new snapshot.')
    if fix.approval_status != 'pending' or incident.status not in ('awaiting_review', 'partial'):
        raise ValueError('Tests must be authorized before the final review decision.')
    check_integrity(incident, fix, run)


def execute_validation(run_id):
    with SessionLocal() as db:
        run = db.get(ValidationRun, run_id)
        if not run or run.status != 'running' or not run.authorized_at:
            return
        fix = db.get(ProposedFix, run.fix_id)
        incident = db.get(Incident, run.incident_id)
        integrity_error = False
        try:
            if datetime.fromisoformat(run.expires_at) < datetime.now(timezone.utc):
                raise ValueError('Authorization expired before execution.')
            check_integrity(incident, fix, run)
        except (ValueError, KeyError, TypeError):
            integrity_error = True
        original, proposed = dict(run.snapshot), dict(run.snapshot)
        for f in fix_files(fix):
            proposed[f['path']] = f['proposed_code']
        policy = run.policy
        specification = run.result.get('verification_spec')
        checks = [c for c in fix.validation_result.get('checks', []) if c['name'] not in ('Repository tests', 'Isolated tests before fix', 'Isolated tests after fix', 'Reviewed verification specification')]
    try:
        if integrity_error:
            raise ValueError('Execution integrity check failed.')
        before = sandbox.run_snapshot(run_id, 'before', original, policy)
        if before['status'] == 'error':
            after = {'status': 'skipped', 'output': '', 'exit_code': None, 'error': 'Baseline runner failed; patched run not started.'}
        else:
            after = sandbox.run_snapshot(run_id, 'after', proposed, policy)
        result = {'before': before, 'after': after, 'policy': policy,
                  'proof': fixture_proof(original, proposed, policy, before, after, run.proposed_sha256, run.manifest),
                  'interpretation': 'Isolated process exit status is measured. Repository test output and counts are untrusted evidence, not proof of correctness or coverage.'}
        if specification is not None:
            assessment = assess_spec(specification, before, after)
            result.update(verification_spec=specification, specification_assessment=assessment)
            checks.append({'name': 'Reviewed verification specification',
                'status': {'matched': 'passed', 'not_reproduced': 'skipped', 'mismatch': 'failed', 'inconclusive': 'error'}[assessment['status']],
                'detail': ' '.join(assessment['reasons']) + ' ' + assessment['limitations']})
        state = 'completed' if after['status'] in ('passed', 'failed') else 'error'
        status = after['status'] if state == 'completed' else 'error'
        if any(p.get('timed_out') or p.get('output_limited') for p in (before, after)):
            state, status = 'error', 'error'
        if before.get('cleanup_succeeded') is False or after.get('cleanup_succeeded') is False:
            state, status = 'cleanup_failed', 'error'
        checks.extend([
            {'name': 'Isolated tests before fix', 'status': 'passed' if before['status'] == 'failed' else 'skipped',
             'detail': 'Original suite exited nonzero; inspect output for the actual cause.' if before['status'] == 'failed' else 'The original failure was not reproduced; inspect the baseline output.'},
            {'name': 'Isolated tests after fix', 'status': after['status'], 'detail': policy['profile'] + '; no network, host mounts, or application credentials.'},
        ])
        if any(c['status'] == 'error' for c in checks):
            status = 'error'
        elif status == 'passed' and any(c['status'] == 'failed' for c in checks):
            status = 'failed'
        elif status == 'passed' and any(c['status'] == 'skipped' for c in checks):
            status = 'partial'
    except Exception:
        cleaned = integrity_error or all([sandbox.cleanup(sandbox.container_name(run_id, phase)) for phase in ('before', 'after')])
        state, status = ('error' if cleaned else 'cleanup_failed'), 'error'
        result = {'error': 'Runner failed. No repository code was executed on the host.', 'cleanup_succeeded': cleaned}
        if specification is not None:
            result['verification_spec'] = specification
    with SessionLocal() as db:
        run, fix = db.get(ValidationRun, run_id), db.get(ProposedFix, run.fix_id)
        if (patch_digest(fix) != run.proposed_sha256
                or plan_digest(run.id, run.manifest, run.proposed_sha256, run.policy, run.result.get('verification_spec')) != run.plan_hash
                or run.result.get('verification_spec') != specification):
            state, status = 'error', 'error'
            result['error'] = 'Patch or authorized plan changed during validation; proof discarded.'
            result.pop('proof', None)
            result.pop('specification_assessment', None)
        run.status, run.finished_at, run.result = state, now(), result
        # Drop snapshot bodies after execution; keep audit manifest and hash.
        run.snapshot = {}
        boundary = ('Vercel microVM with denied network access and no application credentials. ' if policy.get('provider') == 'vercel'
                    else 'Resource-limited Docker containers are not a VM security boundary on Linux. ')
        fix.validation_result = {**fix.validation_result, 'status': status, 'checks': checks, 'isolated_run_id': run_id,
            'isolated': result, 'limitations': boundary + 'Repository tests and their outputs can be misleading; independent code review remains required.'}
        db.commit()
