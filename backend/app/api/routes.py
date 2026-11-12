import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update, func, or_, text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db, SessionLocal, serialize_write
from app.models.records import Incident, Investigation, ProposedFix, AgentExecution, IncidentMemory, AppPreference, ValidationRun, Job, IncidentEvent, now, uid
from app.schemas.contracts import IncidentCreate, Decision, Preferences, PullRequestRequest, ValidationPlanRequest, ValidationAuthorization
from app.services.security import redact, list_files, read_source, digest, incident_source
from app.services.sample import SAMPLE_LOG
from app.services.preferences import preferences
from app.services.github import create_pull_request
from app.agents.workflow import run_investigation, AGENTS
from app.services import sandbox
from app.services.validation_runs import public_run, prepare_plan, check_plan, execute_validation, expire_plans
from app.services.jobs import enqueue
from app.services.memory import update_memory_index
from app.schemas.contracts import Resolution, Reopen
from app.services.patches import fix_files
from app.services import llm
from app.services.repair_outcomes import resolve_outcome
from app.services.repository_snapshots import capture, StaleSnapshotError
from app.services import contract_registry
from app.schemas.contracts import ContractRegistration, ContractReview

router = APIRouter(prefix='/api')


def serialized(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns} if row else None


def incident_or_404(db, incident_id):
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(404, 'Incident not found.')
    return incident


def get_fix(db, incident_id):
    incident_or_404(db, incident_id)
    fix = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == incident_id))
    if not fix:
        raise HTTPException(404, 'No proposed fix is available.')
    return fix


def details(db, incident_id):
    incident = incident_or_404(db, incident_id)
    inv = db.scalar(select(Investigation).where(Investigation.incident_id == incident_id))
    executions = db.scalars(select(AgentExecution).where(AgentExecution.investigation_id == inv.id).order_by(AgentExecution.created_at)).all() if inv else []
    fix = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == incident_id))
    jobs = db.scalars(select(Job).where(Job.incident_id == incident_id).order_by(Job.created_at)).all()
    audit = db.scalars(select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(IncidentEvent.created_at)).all()
    run_id = fix.validation_result.get('isolated_run_id') if fix else None
    run = db.get(ValidationRun, run_id) if run_id else None
    outcome = resolve_outcome(incident, inv, fix, run, contract_registry.provenance_valid(db, incident, inv, run))
    fix_data = {**serialized(fix), 'repair_outcome': outcome} if fix else None
    return {**serialized(incident), 'repair_outcome': outcome, 'investigation': serialized(inv), 'executions': [serialized(e) for e in executions], 'fix': fix_data,
            'jobs': [serialized(j) for j in jobs], 'audit': [serialized(e) for e in audit]}


@router.get('/health')
def health(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'service': 'AutoRCA-X', 'live_available': llm.available(preferences(db)['provider'])}


@router.get('/samples')
def samples():
    return {'items': [{'id': 'checkout-zero', 'title': 'Checkout fails on a zero-percent discount', 'error_log': SAMPLE_LOG,
                       'repository': 'sample', 'mode': 'demo', 'label': 'Deterministic demo · bundled application'}]}


@router.get('/repositories')
def repositories():
    return {'items': [{'id': 'sample', 'name': 'Bundled checkout application', 'available': True},
                      {'id': 'local', 'name': 'Configured local repository', 'available': bool(settings.repository_root)},
                      {'id': 'github', 'name': 'Configured GitHub repository', 'available': bool(settings.github_repository and settings.github_token)}]}


@router.get('/repositories/{source}/files')
def repository_files(source: str):
    return {'items': list_files(source)}


@router.get('/repositories/{source}/file')
def repository_file(source: str, path: str = Query(max_length=500)):
    return {'path': path, 'content': redact(read_source(source, path))}


@router.post('/incidents', status_code=201)
def create_incident(body: IncidentCreate, db: Session = Depends(get_db)):
    provider = preferences(db)['provider']
    if body.mode == 'live' and not llm.available(provider):
        raise HTTPException(409, f'Live mode requires {"GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"} in the backend environment.')
    if body.repository == 'local' and not settings.repository_root:
        raise HTTPException(409, 'Configure REPOSITORY_ROOT before selecting a local repository.')
    commit = ''
    if body.repository == 'github':
        from app.services.github_source import revision
        commit = revision()
    source = 'github@' + commit if commit else body.repository
    for path in body.selected_files:
        read_source(source, path)
    record = Incident(**{**body.model_dump(), 'title': redact(body.title.strip()), 'error_log': redact(body.error_log)})
    if len(record.title) < 3:
        raise HTTPException(422, 'Title must contain at least three non-whitespace characters.')
    record.repository_snapshot = capture(body.repository, commit or None)
    if body.repository in ('local', 'sample') and not set(body.selected_files).issubset(record.repository_snapshot['files']):
        raise HTTPException(422, 'A selected file is outside the bounded source snapshot. Configure a smaller repository root.')
    record.repository_commit = record.repository_snapshot.get('commit_sha') or ''
    record.repository_name = settings.github_repository if body.repository == 'github' else ''
    db.add(record)
    db.commit()
    return serialized(record)


@router.get('/incidents')
def list_incidents(q: str = Query('', max_length=200), severity: str = '', status: str = '',
                   limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = select(Incident)
    if q:
        query = query.where(or_(Incident.title.contains(q, autoescape=True), Incident.error_log.contains(q, autoescape=True)))
    if severity:
        query = query.where(Incident.severity == severity)
    if status:
        query = query.where(Incident.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Incident.created_at.desc()).offset(offset).limit(limit)).all()
    return {'items': [serialized(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset}


@router.get('/incidents/{incident_id}')
async def incident_detail(incident_id: str, db: Session = Depends(get_db)):
    if settings.job_execution == 'vercel':
        from app.services.cloud_jobs import refresh
        for job_id in db.scalars(select(Job.id).where(Job.incident_id == incident_id, Job.status.in_(('queued', 'running')))):
            await refresh(job_id)
        db.expire_all()
    return details(db, incident_id)


@router.post('/incidents/{incident_id}/investigate', status_code=202)
async def investigate(incident_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    serialize_write(db, 'contract:' + incident_id)
    incident = incident_or_404(db, incident_id)
    binding = contract_registry.lock_for_investigation(db, incident)
    # Compare-and-swap prevents concurrent starts even with multiple request threads.
    claimed = db.execute(update(Incident).where(Incident.id == incident_id, Incident.status == 'submitted').values(status='investigating', updated_at=now()))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'This incident has already started. Submit a new incident to investigate again.')
    config = preferences(db)
    if binding:
        config = {**config, 'verification_contract': binding}
    db.add(Investigation(incident_id=incident_id, config=config))
    job = enqueue(db, 'investigation', incident_id, incident_id, tasks)
    db.commit()
    if settings.job_execution == 'vercel':
        from app.services.cloud_jobs import dispatch
        await dispatch(job.id)
    return {'incident_id': incident_id, 'status': 'investigating', 'job_id': job.id}


@router.get('/incidents/{incident_id}/status')
def status(incident_id: str, db: Session = Depends(get_db)):
    data = details(db, incident_id)
    return {'incident_id': incident_id, 'status': data['status'], 'executions': data['executions'], 'agents': AGENTS}


@router.get('/incidents/{incident_id}/events')
def events(incident_id: str, request: Request, db: Session = Depends(get_db)):
    incident_or_404(db, incident_id)
    async def stream():
        last = ''
        # Each connection is bounded; EventSource reconnects if the run takes longer.
        for _ in range(180):
            if await request.is_disconnected():
                break
            with SessionLocal() as session:
                data = details(session, incident_id)
                snapshot = json.dumps({'status': data['status'], 'executions': data['executions']})
            if snapshot != last:
                yield f'event: progress\ndata: {snapshot}\n\n'
                last = snapshot
            else:
                yield ': heartbeat\n\n'
            if data['status'] not in ('submitted', 'investigating'):
                yield 'event: complete\ndata: {}\n\n'
                break
            await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@router.get('/incidents/{incident_id}/report')
def get_report(incident_id: str, db: Session = Depends(get_db)):
    data = details(db, incident_id)
    results = (data['investigation'] or {}).get('analysis_results', {})
    report = results.get('report')
    if not report:
        raise HTTPException(409, 'Report is not available yet. Inspect individual agent outputs for partial results.')
    return {**report, 'repair_outcome': data['repair_outcome'], 'repository_snapshot': data.get('repository_snapshot', {}), 'validation': data['fix']['validation_result'] if data['fix'] else report.get('validation', {}),
            'title': data['title'], 'severity': data['severity'], 'status': data['status'],
            'approval_status': (data['fix'] or {}).get('approval_status', 'not_applicable')}


@router.get('/incidents/{incident_id}/patch')
def patch(incident_id: str, db: Session = Depends(get_db)):
    get_fix(db, incident_id)
    return details(db, incident_id)['fix']


def check_review_evidence(db, incident):
    inv = db.scalar(select(Investigation).where(Investigation.incident_id == incident.id))
    for item in inv.evidence_references if inv else []:
        if item['kind'] == 'source' and digest(read_source(incident_source(incident), item['path'])) != item['sha256']:
            raise StaleSnapshotError('Cited source changed since investigation. Submit a new incident.')


def decide(incident_id, decision, body, db, actor='local developer'):
    serialize_write(db, 'validation-slot')
    incident = incident_or_404(db, incident_id)
    fix = get_fix(db, incident_id)
    if fix.validation_result.get('status') == 'running':
        raise HTTPException(409, 'Wait for the authorized isolated test run to finish before reviewing.')
    if incident.status not in ('awaiting_review', 'partial'):
        raise HTTPException(409, 'This incident is not awaiting a review decision.')
    if decision == 'approved':
        if fix.validation_result.get('status') not in ('passed', 'partial'):
            raise HTTPException(409, 'Approval requires completed validation without failed checks.')
        try:
            check_review_evidence(db, incident)
            changed_source = any(digest(read_source(incident_source(incident), f['path'])) != f['original_sha256'] for f in fix_files(fix))
        except StaleSnapshotError as exc:
            raise HTTPException(409, str(exc)) from None
        if changed_source:
            raise HTTPException(409, 'Source changed since investigation. Submit a new incident.')
    changed = db.execute(update(ProposedFix).where(ProposedFix.id == fix.id, ProposedFix.approval_status == 'pending',
        ProposedFix.validation_result['status'].as_string() != 'running').values(
        approval_status=decision, decision_note=redact(body.note), decided_at=now()))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'A review decision has already been recorded.')
    incident.status, incident.updated_at = decision, now()
    db.add(IncidentEvent(incident_id=incident_id, action=decision, actor=actor, note=redact(body.note)))
    memory = db.scalar(select(IncidentMemory).where(IncidentMemory.incident_id == incident_id))
    if memory:
        memory.retrieval_metadata = {**memory.retrieval_metadata, 'approval': decision}
        memory.resolution_summary = f'Human {decision}; not deployed. ' + fix.explanation
        update_memory_index(db, memory)
    db.commit()
    return details(db, incident_id)


@router.post('/incidents/{incident_id}/approve')
def approve(incident_id: str, body: Decision, request: Request, db: Session = Depends(get_db)):
    return decide(incident_id, 'approved', body, db, request.state.user['username'])


@router.post('/incidents/{incident_id}/reject')
def reject(incident_id: str, body: Decision, request: Request, db: Session = Depends(get_db)):
    return decide(incident_id, 'rejected', body, db, request.state.user['username'])


@router.post('/incidents/{incident_id}/resolve')
def resolve_incident(incident_id: str, body: Resolution, request: Request, db: Session = Depends(get_db)):
    incident = incident_or_404(db, incident_id)
    if len(body.note.strip()) < 10 or len(body.evidence.strip()) < 10:
        raise HTTPException(422, 'Provide a resolution summary and verification evidence.')
    changed = db.execute(update(Incident).where(Incident.id == incident_id, Incident.status.in_(('approved', 'reopened'))).values(
        status='resolved', resolution_note=redact(body.note), resolution_evidence=redact(body.evidence),
        resolved_at=now(), resolved_by=request.state.user['username'], updated_at=now()))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Only an approved or reopened incident can be resolved.')
    db.add(IncidentEvent(incident_id=incident_id, action='resolved', actor=request.state.user['username'], note=redact(body.note), evidence=redact(body.evidence)))
    memory = db.scalar(select(IncidentMemory).where(IncidentMemory.incident_id == incident_id))
    if memory:
        memory.resolution_summary = 'Human-confirmed resolution: ' + redact(body.note)
        memory.retrieval_metadata = {**memory.retrieval_metadata, 'resolved': True, 'evidence': redact(body.evidence)}
        update_memory_index(db, memory)
    db.commit()
    db.expire_all()
    return details(db, incident_id)


@router.post('/incidents/{incident_id}/reopen')
def reopen_incident(incident_id: str, body: Reopen, request: Request, db: Session = Depends(get_db)):
    incident_or_404(db, incident_id)
    if len(body.note.strip()) < 10:
        raise HTTPException(422, 'Explain why the incident is being reopened.')
    changed = db.execute(update(Incident).where(Incident.id == incident_id, Incident.status == 'resolved').values(status='reopened', updated_at=now()))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Only a resolved incident can be reopened.')
    db.add(IncidentEvent(incident_id=incident_id, action='reopened', actor=request.state.user['username'], note=redact(body.note)))
    memory = db.scalar(select(IncidentMemory).where(IncidentMemory.incident_id == incident_id))
    if memory:
        memory.resolution_summary = 'Reopened; previous resolution is no longer confirmed. ' + redact(body.note)
        memory.retrieval_metadata = {**memory.retrieval_metadata, 'resolved': False}
        update_memory_index(db, memory)
    db.commit()
    db.expire_all()
    return details(db, incident_id)


@router.post('/jobs/{job_id}/cancel')
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    serialize_write(db, 'job:' + job_id)
    job = db.get(Job, job_id)
    if not job or job.kind != 'investigation' or job.status not in ('queued', 'running'):
        raise HTTPException(409, 'Only an active investigation can be cancelled. Isolated tests have a bounded deadline.')
    job.cancel_requested, job.updated_at = True, now()
    if job.status == 'queued':
        job.status = 'cancelled'
        db.get(Incident, job.incident_id).status = 'cancelled'
    db.commit()
    return serialized(job)


@router.post('/jobs/{job_id}/retry', status_code=202)
async def retry_job(job_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    serialize_write(db, 'job:' + job_id)
    job = db.get(Job, job_id)
    if not job or job.kind != 'investigation' or job.status not in ('failed', 'cancelled') or job.attempts >= 3:
        raise HTTPException(409, 'Only failed or cancelled investigations below three attempts can be retried.')
    fix = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == job.incident_id))
    if fix and (fix.approval_status != 'pending' or fix.validation_result.get('status') == 'running'):
        raise HTTPException(409, 'Reviewed fixes or active isolated tests cannot be retried.')
    inv = db.scalar(select(Investigation).where(Investigation.incident_id == job.incident_id))
    errors = inv.analysis_results.get('errors', [])
    first = min([AGENTS.index(e['agent']) for e in errors if e['agent'] in AGENTS], default=len(AGENTS))
    if fix and first <= AGENTS.index('fix'):
        fix.validation_result = {'status': 'regenerate', 'checks': [], 'limitations': 'Upstream analysis is being retried. This proposal cannot be approved until regenerated and validated.'}
    inv.analysis_results = {k: v for k, v in inv.analysis_results.items() if k in AGENTS[:first]}
    job.status, job.cancel_requested, job.error, job.updated_at = 'queued', False, None, now()
    job.dispatch_token, job.workflow_run_id = uid(), None
    db.get(Incident, job.incident_id).status = 'investigating'
    if settings.job_execution == 'inline':
        from app.services.jobs import run_job
        tasks.add_task(run_job, job.id)
    db.commit()
    if settings.job_execution == 'vercel':
        from app.services.cloud_jobs import dispatch
        await dispatch(job.id)
        db.refresh(job)
    return serialized(job)


@router.post('/incidents/{incident_id}/pull-request')
def pull_request(incident_id: str, body: PullRequestRequest, db: Session = Depends(get_db)):
    from app.services.cloud_jobs import execution_lock
    # The separate PostgreSQL transaction holds this lock across GitHub requests
    # and releases it automatically if the Vercel function is interrupted.
    with execution_lock('pull-request:' + incident_id):
        return publish_reviewed_fix(incident_id, db)


def publish_reviewed_fix(incident_id, db):
    incident, fix = incident_or_404(db, incident_id), get_fix(db, incident_id)
    if fix.approval_status != 'approved':
        raise HTTPException(409, 'Approve the reviewed fix before authorizing a pull request.')
    if fix.pr_url:
        return {'url': fix.pr_url}
    if not settings.github_token or not settings.github_repository or incident.repository not in ('local', 'github'):
        raise HTTPException(409, 'A configured GitHub target and a local or GitHub source are required.')
    try:
        check_review_evidence(db, incident)
    except StaleSnapshotError as exc:
        raise HTTPException(409, str(exc)) from None
    available = True if db.get_bind().dialect.name == 'postgresql' else ProposedFix.pr_status != 'creating'
    claimed = db.execute(update(ProposedFix).where(ProposedFix.id == fix.id, available).values(pr_status='creating'))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'A pull request operation is already in progress.')
    db.commit()
    try:
        url = create_pull_request(incident, fix)
        fix.pr_url, fix.pr_status = url, 'created'
        db.commit()
        return {'url': url}
    except ValueError as exc:
        fix.pr_status = 'failed'
        db.commit()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        fix.pr_status = 'failed'
        db.commit()
        raise HTTPException(502, 'GitHub operation failed. Check permissions and connectivity. Retrying reuses the incident branch; a branch or commit may already exist.') from None


@router.get('/dashboard/stats')
def dashboard(db: Session = Depends(get_db)):
    rows = db.scalars(select(Incident).order_by(Incident.created_at.desc())).all()
    counts = {status: sum(i.status == status for i in rows) for status in ('submitted', 'investigating', 'awaiting_review', 'approved', 'rejected', 'failed', 'partial', 'needs_evidence', 'resolved', 'reopened', 'cancelled')}
    completed = sum(counts[s] for s in ('awaiting_review', 'approved', 'rejected', 'needs_evidence', 'resolved', 'reopened'))
    attempted = len(rows) - counts['submitted'] - counts['investigating']
    return {'total': len(rows), 'open': len(rows) - counts['resolved'] - counts['rejected'],
            'resolved': counts['resolved'], 'approved': counts['approved'] + counts['resolved'] + counts['reopened'], 'pending_approvals': counts['awaiting_review'],
            'success_rate': round(completed / attempted * 100) if attempted else None,
            'demo_count': sum(i.mode == 'demo' for i in rows), 'recent': [serialized(i) for i in rows[:6]],
            'severity': [{'name': s, 'value': sum(i.severity == s for i in rows)} for s in ('critical', 'high', 'medium', 'low')],
            'activity': [{'id': i.id, 'title': i.title, 'status': i.status, 'time': i.updated_at} for i in sorted(rows, key=lambda i: i.updated_at, reverse=True)[:6]],
            'note': 'Approved means reviewed, not deployed or resolved. Analytics include stored demo incidents; no seeded records.'}


@router.get('/settings')
def read_settings(db: Session = Depends(get_db)):
    current = preferences(db)
    return {**current, 'live_available': llm.available(current['provider']),
            'providers': [{'id': 'openai', 'name': 'OpenAI', 'available': llm.available('openai'), 'default_model': settings.openai_model},
                          {'id': 'gemini', 'name': 'Google Gemini', 'available': llm.available('gemini'), 'default_model': settings.gemini_model}],
            'github_configured': bool(settings.github_token and settings.github_repository), 'github_repository': settings.github_repository,
            'job_execution': settings.job_execution, 'sandbox_provider': settings.sandbox_provider,
            'local_repository_configured': bool(settings.repository_root), 'sandbox_available': sandbox.availability()['available']}


@router.get('/sandbox')
def sandbox_status():
    return {**sandbox.availability(), 'policy': sandbox.policy()}


@router.get('/incidents/{incident_id}/validation-runs')
def validation_runs(incident_id: str, db: Session = Depends(get_db)):
    incident_or_404(db, incident_id)
    expire_plans(db)
    rows = db.scalars(select(ValidationRun).where(ValidationRun.incident_id == incident_id).order_by(ValidationRun.created_at.desc())).all()
    return {'items': [public_run(r) for r in rows]}


@router.get('/incidents/{incident_id}/verification-contract')
def registered_contract(incident_id: str, db: Session = Depends(get_db)):
    registration, review = contract_registry.records(db, incident_or_404(db, incident_id))
    return {'registration': registration, 'review': review}


@router.post('/incidents/{incident_id}/verification-contract', status_code=201)
def register_contract(incident_id: str, body: ContractRegistration, request: Request, db: Session = Depends(get_db)):
    serialize_write(db, 'contract:' + incident_id)
    document = contract_registry.register(db, incident_or_404(db, incident_id), request.state.user, body.contract.model_dump(), body.files)
    db.commit()
    return document


@router.post('/incidents/{incident_id}/verification-contract/review', status_code=201)
def review_contract(incident_id: str, body: ContractReview, request: Request, db: Session = Depends(get_db)):
    serialize_write(db, 'contract:' + incident_id)
    document = contract_registry.review(db, incident_or_404(db, incident_id), request.state.user, body.registration_sha256, body.rationale)
    db.commit()
    return document


@router.post('/incidents/{incident_id}/validation-plans', status_code=201)
def validation_plan(incident_id: str, body: ValidationPlanRequest, request: Request, db: Session = Depends(get_db)):
    expire_plans(db)
    incident = incident_or_404(db, incident_id)
    declaration = body.json_contract.model_dump() if body.json_contract else None
    provenance = None
    if body.registered_contract_sha256:
        registration, review = contract_registry.records(db, incident)
        inv = db.scalar(select(Investigation).where(Investigation.incident_id == incident_id))
        if not registration or not review or registration['sha256'] != body.registered_contract_sha256 or not inv:
            raise ValueError('Choose the exact reviewed contract registered before investigation.')
        provenance = inv.config.get('verification_contract')
        contract_registry.validate_binding(db, incident, inv, {'kind': 'json-stdio', 'declaration': registration['declaration'],
            'source_hashes': registration['source_hashes'], 'snapshot_id': registration['snapshot_id'], 'provenance': provenance})
        if set(body.files) != set(registration['source_hashes']):
            raise ValueError('Registered contract plans require exactly the registered source files.')
        declaration = registration['declaration']
    run = prepare_plan(incident, get_fix(db, incident_id), body.files, body.profile,
        body.verification_spec.model_dump() if body.verification_spec else None, request.state.user['username'],
        declaration, provenance)
    db.add(run)
    db.commit()
    return public_run(run)


@router.post('/incidents/{incident_id}/validation-runs/{run_id}/authorize', status_code=202)
async def authorize_validation(incident_id: str, run_id: str, body: ValidationAuthorization, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    serialize_write(db, 'validation-slot')
    incident, fix = incident_or_404(db, incident_id), get_fix(db, incident_id)
    run = db.get(ValidationRun, run_id)
    if not run or run.incident_id != incident_id:
        raise HTTPException(404, 'Validation plan not found.')
    check_plan(incident, fix, run, body.plan_hash, db)
    ready = sandbox.availability()
    if not ready['available']:
        raise HTTPException(409, ready['reason'])
    claimed = db.execute(update(ProposedFix).where(ProposedFix.id == fix.id, ProposedFix.approval_status == 'pending',
        ProposedFix.validation_result['status'].as_string() != 'running').values(validation_result={**fix.validation_result, 'status': 'running'}))
    if claimed.rowcount != 1 or db.scalar(select(func.count()).select_from(ValidationRun).where(ValidationRun.status.in_(('running', 'cleanup_failed')))):
        db.rollback()
        raise HTTPException(409, 'Another isolated run is active or needs cleanup. Finish it or retry its cleanup before authorizing another test.')
    claimed_run = db.execute(update(ValidationRun).where(ValidationRun.id == run_id, ValidationRun.status == 'planned').values(status='running', authorized_at=now()))
    if claimed_run.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'This plan has already been authorized.')
    job = enqueue(db, 'validation', run_id, incident_id, tasks)
    db.commit()
    if settings.job_execution == 'vercel':
        from app.services.cloud_jobs import dispatch
        await dispatch(job.id)
    return {'id': run_id, 'status': 'running'}


@router.post('/incidents/{incident_id}/validation-runs/{run_id}/cleanup')
def cleanup_validation(incident_id: str, run_id: str, db: Session = Depends(get_db)):
    serialize_write(db, 'validation-slot')
    run = db.get(ValidationRun, run_id)
    if not run or run.incident_id != incident_id:
        raise HTTPException(404, 'Validation run not found.')
    if run.status != 'cleanup_failed':
        raise HTTPException(409, 'Only a run with failed cleanup can be cleaned again.')
    if run.policy.get('provider', 'docker') != settings.sandbox_provider:
        raise HTTPException(409, 'Restore the original sandbox provider before retrying cleanup.')
    cleaned = all([sandbox.cleanup(sandbox.container_name(run.id, phase)) for phase in ('before', 'after')])
    if not cleaned:
        raise HTTPException(503, 'Cleanup still cannot be confirmed. Check the sandbox provider before retrying.')
    run.status, run.snapshot, run.finished_at = 'error', {}, now()
    run.result = {**run.result, 'cleanup_succeeded': True, 'cleanup_retried_at': now()}
    for phase in ('before', 'after'):
        if phase in run.result:
            run.result = {**run.result, phase: {**run.result[phase], 'cleanup_succeeded': True}}
    fix = db.get(ProposedFix, run.fix_id)
    fix.validation_result = {**fix.validation_result, 'status': 'error', 'isolated': run.result}
    db.commit()
    return public_run(run)


@router.put('/settings')
def save_settings(body: Preferences, db: Session = Depends(get_db)):
    if body.default_mode == 'live' and not llm.available(body.provider):
        raise HTTPException(409, 'Configure the selected provider API key before making Live AI the default.')
    row = db.get(AppPreference, 'default')
    if not row:
        row = AppPreference(id='default')
        db.add(row)
    row.values = body.model_dump()
    db.commit()
    return read_settings(db)
