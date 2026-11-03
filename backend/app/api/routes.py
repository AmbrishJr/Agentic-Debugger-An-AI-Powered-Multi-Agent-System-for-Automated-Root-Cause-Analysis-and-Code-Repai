import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update, func, or_, text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db, SessionLocal
from app.models.records import Incident, Investigation, ProposedFix, AgentExecution, IncidentMemory, AppPreference, ValidationRun, now
from app.schemas.contracts import IncidentCreate, Decision, Preferences, PullRequestRequest, ValidationPlanRequest, ValidationAuthorization
from app.services.security import redact, list_files, read_source, digest
from app.services.sample import SAMPLE_LOG
from app.services.preferences import preferences
from app.services.github import create_pull_request
from app.agents.workflow import run_investigation, AGENTS
from app.services import sandbox
from app.services.validation_runs import public_run, prepare_plan, check_plan, execute_validation

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
    return {**serialized(incident), 'investigation': serialized(inv), 'executions': [serialized(e) for e in executions], 'fix': serialized(fix)}


@router.get('/health')
def health(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'service': 'AutoRCA-X', 'live_available': bool(settings.openai_api_key)}


@router.get('/samples')
def samples():
    return {'items': [{'id': 'checkout-zero', 'title': 'Checkout fails on a zero-percent discount', 'error_log': SAMPLE_LOG,
                       'repository': 'sample', 'mode': 'demo', 'label': 'Deterministic demo · bundled application'}]}


@router.get('/repositories')
def repositories():
    return {'items': [{'id': 'sample', 'name': 'Bundled checkout application', 'available': True},
                      {'id': 'local', 'name': 'Configured local repository', 'available': bool(settings.repository_root)}]}


@router.get('/repositories/{source}/files')
def repository_files(source: str):
    return {'items': list_files(source)}


@router.get('/repositories/{source}/file')
def repository_file(source: str, path: str = Query(max_length=500)):
    return {'path': path, 'content': redact(read_source(source, path))}


@router.post('/incidents', status_code=201)
def create_incident(body: IncidentCreate, db: Session = Depends(get_db)):
    if body.mode == 'live' and not settings.openai_api_key:
        raise HTTPException(409, 'Live mode requires OPENAI_API_KEY in the backend environment.')
    if body.repository == 'local' and not settings.repository_root:
        raise HTTPException(409, 'Configure REPOSITORY_ROOT before selecting a local repository.')
    for path in body.selected_files:
        read_source(body.repository, path)
    record = Incident(**{**body.model_dump(), 'title': redact(body.title.strip()), 'error_log': redact(body.error_log)})
    if len(record.title) < 3:
        raise HTTPException(422, 'Title must contain at least three non-whitespace characters.')
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
def incident_detail(incident_id: str, db: Session = Depends(get_db)):
    return details(db, incident_id)


@router.post('/incidents/{incident_id}/investigate', status_code=202)
def investigate(incident_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    incident_or_404(db, incident_id)
    # Compare-and-swap prevents concurrent starts even with multiple request threads.
    claimed = db.execute(update(Incident).where(Incident.id == incident_id, Incident.status == 'submitted').values(status='investigating', updated_at=now()))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'This incident has already started. Submit a new incident to investigate again.')
    db.add(Investigation(incident_id=incident_id, config=preferences(db)))
    db.commit()
    tasks.add_task(run_investigation, incident_id)
    return {'incident_id': incident_id, 'status': 'investigating'}


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
    return {**report, 'validation': data['fix']['validation_result'] if data['fix'] else report.get('validation', {}),
            'title': data['title'], 'severity': data['severity'], 'status': data['status'],
            'approval_status': (data['fix'] or {}).get('approval_status', 'not_applicable')}


@router.get('/incidents/{incident_id}/patch')
def patch(incident_id: str, db: Session = Depends(get_db)):
    return serialized(get_fix(db, incident_id))


def decide(incident_id, decision, body, db):
    incident = incident_or_404(db, incident_id)
    fix = get_fix(db, incident_id)
    if fix.validation_result.get('status') == 'running':
        raise HTTPException(409, 'Wait for the authorized isolated test run to finish before reviewing.')
    if incident.status not in ('awaiting_review', 'partial'):
        raise HTTPException(409, 'This incident is not awaiting a review decision.')
    if decision == 'approved':
        if fix.validation_result.get('status') not in ('passed', 'partial'):
            raise HTTPException(409, 'Approval requires completed validation without failed checks.')
        if digest(read_source(incident.repository, fix.path)) != fix.original_sha256:
            raise HTTPException(409, 'Source changed since investigation. Submit a new incident.')
    changed = db.execute(update(ProposedFix).where(ProposedFix.id == fix.id, ProposedFix.approval_status == 'pending',
        ProposedFix.validation_result['status'].as_string() != 'running').values(
        approval_status=decision, decision_note=redact(body.note), decided_at=now()))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'A review decision has already been recorded.')
    incident.status, incident.updated_at = decision, now()
    memory = db.scalar(select(IncidentMemory).where(IncidentMemory.incident_id == incident_id))
    if memory:
        memory.retrieval_metadata = {**memory.retrieval_metadata, 'approval': decision}
        memory.resolution_summary = f'Human {decision}; not deployed. ' + fix.explanation
        db.execute(text('UPDATE memory_fts SET resolution_summary=:summary WHERE incident_id=:id'), {'summary': memory.resolution_summary, 'id': incident_id})
    db.commit()
    return details(db, incident_id)


@router.post('/incidents/{incident_id}/approve')
def approve(incident_id: str, body: Decision, db: Session = Depends(get_db)):
    return decide(incident_id, 'approved', body, db)


@router.post('/incidents/{incident_id}/reject')
def reject(incident_id: str, body: Decision, db: Session = Depends(get_db)):
    return decide(incident_id, 'rejected', body, db)


@router.post('/incidents/{incident_id}/pull-request')
def pull_request(incident_id: str, body: PullRequestRequest, db: Session = Depends(get_db)):
    incident, fix = incident_or_404(db, incident_id), get_fix(db, incident_id)
    if fix.approval_status != 'approved':
        raise HTTPException(409, 'Approve the reviewed fix before authorizing a pull request.')
    if fix.pr_url:
        return {'url': fix.pr_url}
    if not settings.github_token or not settings.github_repository or incident.repository != 'local':
        raise HTTPException(409, 'A configured GitHub target and local repository are required.')
    claimed = db.execute(update(ProposedFix).where(ProposedFix.id == fix.id, ProposedFix.pr_status != 'creating').values(pr_status='creating'))
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
    counts = {status: sum(i.status == status for i in rows) for status in ('submitted', 'investigating', 'awaiting_review', 'approved', 'rejected', 'failed', 'partial', 'needs_evidence')}
    completed = sum(counts[s] for s in ('awaiting_review', 'approved', 'rejected', 'needs_evidence'))
    attempted = len(rows) - counts['submitted'] - counts['investigating']
    return {'total': len(rows), 'open': sum(counts[s] for s in ('submitted', 'investigating', 'awaiting_review', 'partial', 'needs_evidence', 'failed')),
            'resolved': 0, 'approved': counts['approved'], 'pending_approvals': counts['awaiting_review'],
            'success_rate': round(completed / attempted * 100) if attempted else None,
            'demo_count': sum(i.mode == 'demo' for i in rows), 'recent': [serialized(i) for i in rows[:6]],
            'severity': [{'name': s, 'value': sum(i.severity == s for i in rows)} for s in ('critical', 'high', 'medium', 'low')],
            'activity': [{'id': i.id, 'title': i.title, 'status': i.status, 'time': i.updated_at} for i in sorted(rows, key=lambda i: i.updated_at, reverse=True)[:6]],
            'note': 'Approved means reviewed, not deployed or resolved. Analytics include stored demo incidents; no seeded records.'}


@router.get('/settings')
def read_settings(db: Session = Depends(get_db)):
    return {**preferences(db), 'provider': 'OpenAI', 'live_available': bool(settings.openai_api_key),
            'github_configured': bool(settings.github_token and settings.github_repository), 'github_repository': settings.github_repository,
            'local_repository_configured': bool(settings.repository_root), 'sandbox_available': sandbox.availability()['available']}


@router.get('/sandbox')
def sandbox_status():
    return {**sandbox.availability(), 'policy': sandbox.policy()}


@router.get('/incidents/{incident_id}/validation-runs')
def validation_runs(incident_id: str, db: Session = Depends(get_db)):
    incident_or_404(db, incident_id)
    rows = db.scalars(select(ValidationRun).where(ValidationRun.incident_id == incident_id).order_by(ValidationRun.created_at.desc())).all()
    return {'items': [public_run(r) for r in rows]}


@router.post('/incidents/{incident_id}/validation-plans', status_code=201)
def validation_plan(incident_id: str, body: ValidationPlanRequest, db: Session = Depends(get_db)):
    run = prepare_plan(incident_or_404(db, incident_id), get_fix(db, incident_id), body.files)
    db.add(run)
    db.commit()
    return public_run(run)


@router.post('/incidents/{incident_id}/validation-runs/{run_id}/authorize', status_code=202)
def authorize_validation(incident_id: str, run_id: str, body: ValidationAuthorization, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    incident, fix = incident_or_404(db, incident_id), get_fix(db, incident_id)
    run = db.get(ValidationRun, run_id)
    if not run or run.incident_id != incident_id:
        raise HTTPException(404, 'Validation plan not found.')
    check_plan(incident, fix, run, body.plan_hash)
    ready = sandbox.availability()
    if not ready['available']:
        raise HTTPException(409, ready['reason'])
    claimed = db.execute(update(ProposedFix).where(ProposedFix.id == fix.id, ProposedFix.approval_status == 'pending',
        ProposedFix.validation_result['status'].as_string() != 'running').values(validation_result={**fix.validation_result, 'status': 'running'}))
    if claimed.rowcount != 1 or db.scalar(select(func.count()).select_from(ValidationRun).where(ValidationRun.status == 'running')):
        db.rollback()
        raise HTTPException(409, 'Another isolated run is active. Try after it finishes.')
    claimed_run = db.execute(update(ValidationRun).where(ValidationRun.id == run_id, ValidationRun.status == 'planned').values(status='running', authorized_at=now()))
    if claimed_run.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'This plan has already been authorized.')
    db.commit()
    tasks.add_task(execute_validation, run_id)
    return {'id': run_id, 'status': 'running'}


@router.put('/settings')
def save_settings(body: Preferences, db: Session = Depends(get_db)):
    if body.default_mode == 'live' and not settings.openai_api_key:
        raise HTTPException(409, 'Configure OPENAI_API_KEY before making Live AI the default.')
    row = db.get(AppPreference, 'default')
    if not row:
        row = AppPreference(id='default')
        db.add(row)
    row.values = body.model_dump()
    db.commit()
    return read_settings(db)
