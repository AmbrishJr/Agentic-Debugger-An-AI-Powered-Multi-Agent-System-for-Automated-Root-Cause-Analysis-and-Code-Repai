"""Database fencing for at-least-once workflow delivery and manual retries."""
from contextlib import contextmanager
from sqlalchemy import select
from app.db.session import SessionLocal, serialize_write
from app.models.records import Job, Incident, Investigation, AgentExecution, ValidationRun, ProposedFix, now


@contextmanager
def execution_lock(job_id):
    with SessionLocal() as guard:
        if guard.get_bind().dialect.name == 'postgresql':
            serialize_write(guard, 'execution:' + job_id)
        yield
        # PostgreSQL transaction lock releases on rollback/close, also after crashes.


def run_stage(job_id, token, run_id, stage):
    from app.agents import workflow as agents
    from app.services.jobs import JobCancelled
    with execution_lock(job_id):
        with SessionLocal() as db:
            serialize_write(db, 'job:' + job_id)
            job = db.get(Job, job_id)
            if not job or job.dispatch_token != token or job.status not in ('queued', 'running'):
                return False
            if job.workflow_run_id and job.workflow_run_id != run_id:
                return False
            if job.cancel_requested:
                job.status = 'cancelled'
                db.get(Incident, job.incident_id).status = 'cancelled'
                db.commit()
                return False
            if job.status == 'queued':
                job.attempts += 1
            elif stage == 'isolated':
                # A duplicate delivery of an interrupted test must not execute it twice.
                db.rollback()
                fail_job(job_id, token, locked=True)
                return False
            job.status, job.workflow_run_id, job.updated_at = 'running', run_id, now()
            target, kind = job.target_id, job.kind
            db.commit()
        try:
            if kind == 'investigation':
                state = agents.load_state(target, job_id)
                if stage == 'finish':
                    agents.finish_investigation(state, job_id)
                    return True
                else:
                    if stage not in agents.AGENTS:
                        raise ValueError('Unknown investigation stage.')
                    with SessionLocal() as db:
                        inv = db.scalar(select(Investigation).where(Investigation.incident_id == target))
                        for execution in db.scalars(select(AgentExecution).where(
                                AgentExecution.investigation_id == inv.id, AgentExecution.agent_name == stage,
                                AgentExecution.execution_status == 'running')):
                            execution.execution_status = 'interrupted'
                            execution.error_details = 'Step interrupted; retry uses saved completed results.'
                        db.commit()
                    agents.tracked(stage, getattr(agents, stage))(state)
                    return True
            elif stage == 'isolated' and kind == 'validation':
                from app.services.validation_runs import execute_validation
                execute_validation(target)
            else:
                raise ValueError('Job kind does not match the requested step.')
        except JobCancelled:
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                job.status, job.updated_at = 'cancelled', now()
                db.get(Incident, job.incident_id).status = 'cancelled'
                db.commit()
            return False
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            outcome = db.get(Incident, target).status if kind == 'investigation' else db.get(ValidationRun, target).status
            job.status = 'failed' if outcome in ('partial', 'failed', 'error', 'cleanup_failed') else 'completed'
            job.error = 'Inspect the saved results before retrying.' if job.status == 'failed' else None
            job.updated_at = now()
            db.commit()
        return True


def fail_job(job_id, token, locked=False, run_id=None):
    if not locked:
        with execution_lock(job_id):
            return fail_job(job_id, token, locked=True, run_id=run_id)
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job or job.dispatch_token != token or job.status not in ('queued', 'running'):
            return
        if run_id and job.workflow_run_id and job.workflow_run_id != run_id:
            return
        job.status, job.error, job.updated_at = 'failed', 'Cloud execution interrupted. Inspect saved results before retrying.', now()
        if job.kind == 'investigation':
            job.status = 'cancelled' if job.cancel_requested else 'failed'
            db.get(Incident, job.incident_id).status = job.status
        else:
            from app.services import sandbox
            run = db.get(ValidationRun, job.target_id)
            if run.status in ('completed', 'error'):
                # The result committed before the worker stopped. Never erase it or replay its authorization.
                job.status = 'completed' if run.status == 'completed' else 'failed'
                job.error = None if job.status == 'completed' else job.error
                db.commit()
                return
            cleaned = all([sandbox.cleanup(sandbox.container_name(run.id, phase)) for phase in ('before', 'after')])
            run.status, run.finished_at, run.snapshot = ('error' if cleaned else 'cleanup_failed'), now(), {}
            run.result = {**({'verification_spec': run.result['verification_spec']} if 'verification_spec' in run.result else {}),
                'error': 'Test execution interrupted. Prepare a new authorization.', 'cleanup_succeeded': cleaned}
            fix = db.get(ProposedFix, run.fix_id)
            fix.validation_result = {**fix.validation_result, 'status': 'error', 'isolated': run.result}
        db.commit()


async def dispatch(job_id):
    from vercel import workflow
    from app.cloud_workflows import execute_job
    from fastapi import HTTPException
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job or job.status != 'queued':
            return
        token, kind = job.dispatch_token, job.kind
    try:
        run = await workflow.start(execute_job, job_id, token, kind)
    except Exception:
        # The request may have reached Vercel. Fence its token before any manual retry.
        fail_job(job_id, token)
        raise HTTPException(503, 'Cloud job dispatch failed. The incident is saved; retry it after checking Vercel configuration.') from None
    with SessionLocal() as db:
        serialize_write(db, 'job:' + job_id)
        job = db.get(Job, job_id)
        if job.dispatch_token == token and job.workflow_run_id is None:
            job.workflow_run_id = run.run_id
            db.commit()


async def refresh(job_id):
    """Reconcile terminal platform failures without replaying consumed tests."""
    from vercel import workflow
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job or job.status not in ('queued', 'running'):
            return
        token, run_id = job.dispatch_token, job.workflow_run_id
        if not run_id:
            from datetime import datetime, timezone
            if (datetime.now(timezone.utc) - datetime.fromisoformat(job.updated_at)).total_seconds() < 120:
                return
    if not run_id:
        import asyncio
        await asyncio.to_thread(fail_job, job_id, token, run_id=run_id)
        return
    try:
        import asyncio
        status = await asyncio.wait_for(workflow.get_run(run_id).status(), timeout=5)
    except Exception:
        return  # A monitoring outage is not evidence that the job failed.
    if status in ('failed', 'cancelled', 'completed'):
        import asyncio
        await asyncio.to_thread(fail_job, job_id, token, run_id=run_id)
