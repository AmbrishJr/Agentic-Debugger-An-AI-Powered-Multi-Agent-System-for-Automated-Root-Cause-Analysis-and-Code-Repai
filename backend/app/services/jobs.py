"""SQLite-backed jobs, with one consumer per database and persisted agent checkpoints."""
import fcntl
import threading
from pathlib import Path
from sqlalchemy import select, update
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.records import Job, WorkerState, Incident, Investigation, AgentExecution, ProposedFix, ValidationRun, now


class JobCancelled(Exception):
    pass


def checkpoint(job_id):
    if job_id:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job or job.cancel_requested:
                raise JobCancelled()


def enqueue(db, kind, target_id, incident_id, tasks):
    job = Job(kind=kind, target_id=target_id, incident_id=incident_id)
    db.add(job)
    db.flush()
    if settings.job_execution == 'inline':
        tasks.add_task(run_job, job.id)
    return job


def run_job(job_id):
    with SessionLocal() as db:
        claimed = db.execute(update(Job).where(Job.id == job_id, Job.status == 'queued').values(
            status='running', attempts=Job.attempts + 1, updated_at=now()))
        if claimed.rowcount != 1:
            db.rollback()
            return
        db.commit()
        job = db.get(Job, job_id)
        kind, target = job.kind, job.target_id
    try:
        checkpoint(job_id)
        if kind == 'investigation':
            from app.agents.workflow import run_investigation
            run_investigation(target, job_id)
        else:
            from app.services.validation_runs import execute_validation
            execute_validation(target)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            outcome = db.get(Incident, target).status if kind == 'investigation' else db.get(ValidationRun, target).status
            job.status = 'failed' if outcome in ('failed', 'partial', 'error', 'cleanup_failed') else 'completed'
            job.error = 'Inspect the saved results before retrying.' if job.status == 'failed' else None
            job.updated_at = now()
            db.commit()
    except JobCancelled:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status, job.updated_at = 'cancelled', now()
            incident = db.get(Incident, job.incident_id)
            incident.status, incident.updated_at = 'cancelled', now()
            db.commit()
    except Exception:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status, job.error, job.updated_at = 'failed', 'Worker interrupted; saved results are available.', now()
            if kind == 'investigation':
                db.get(Incident, job.incident_id).status = 'failed'
            db.commit()


def recover():
    # Called only while holding the exclusive worker lock, never by web replicas.
    from app.services import sandbox
    with SessionLocal() as db:
        for incident in db.scalars(select(Incident).where(Incident.status == 'investigating')):
            if not db.scalar(select(Job.id).where(Job.kind == 'investigation', Job.target_id == incident.id)):
                db.add(Job(kind='investigation', target_id=incident.id, incident_id=incident.id))
        for run in db.scalars(select(ValidationRun).where(ValidationRun.status.in_(('running', 'cleanup_failed')))):
            cleaned = all([sandbox.cleanup(sandbox.container_name(run.id, phase)) for phase in ('before', 'after')])
            run.status, run.finished_at, run.snapshot = ('error' if cleaned else 'cleanup_failed'), now(), {}
            run.result = {'error': 'Worker restarted during isolated validation. Prepare a new authorization.', 'cleanup_succeeded': cleaned}
            fix = db.get(ProposedFix, run.fix_id)
            fix.validation_result = {**fix.validation_result, 'status': 'error', 'isolated': run.result}
        for job in db.scalars(select(Job).where(Job.status.in_(('queued', 'running')))):
            if job.kind == 'validation':
                # A consumed authorization is never replayed automatically after a restart.
                job.status, job.error = 'failed', 'Validation interrupted. Prepare a new authorization.'
            elif job.cancel_requested:
                job.status = 'cancelled'
                db.get(Incident, job.incident_id).status = 'cancelled'
            elif job.attempts >= 3:
                job.status, job.error = 'failed', 'Three execution attempts exhausted.'
                db.get(Incident, job.incident_id).status = 'failed'
            else:
                job.status = 'queued'
            job.updated_at = now()
        for execution in db.scalars(select(AgentExecution).where(AgentExecution.execution_status == 'running')):
            execution.execution_status, execution.error_details = 'interrupted', 'Worker restarted; completed steps are retained.'
        for fix in db.scalars(select(ProposedFix).where(ProposedFix.pr_status == 'creating')):
            fix.pr_status = 'failed'
        db.commit()


def worker_loop(stop):
    lock_path = Path(engine.url.database).with_suffix('.worker.lock')
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return  # Another process owns this database's consumer.
        recover()
        while not stop.is_set():
            with SessionLocal() as db:
                heartbeat = db.get(WorkerState, 'default')
                if not heartbeat:
                    heartbeat = WorkerState(id='default')
                    db.add(heartbeat)
                heartbeat.heartbeat_at = now()
                job_id = db.scalar(select(Job.id).where(Job.status == 'queued').order_by(Job.created_at).limit(1))
                db.commit()
            if job_id:
                run_job(job_id)
            else:
                stop.wait(0.5)


def start_worker():
    stop = threading.Event()
    threading.Thread(target=worker_loop, args=(stop,), daemon=True, name='autorca-worker').start()
    return stop
