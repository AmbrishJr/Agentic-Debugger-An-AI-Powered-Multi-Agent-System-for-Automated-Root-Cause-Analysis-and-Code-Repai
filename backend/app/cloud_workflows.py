"""Vercel registry: orchestration carries identifiers, never source or credentials."""
from vercel import workflow

wf = workflow.Workflows()


@wf.step(max_retries=2)
async def investigation_stage(job_id: str, token: str, stage: str) -> bool:
    import asyncio
    from app.services.cloud_jobs import run_stage
    return await asyncio.to_thread(run_stage, job_id, token, workflow.get_step_metadata().run_id, stage)


@wf.step(max_retries=0)
async def isolated_validation(job_id: str, token: str) -> bool:
    import asyncio
    from app.services.cloud_jobs import run_stage
    # Consumed authorizations are never automatically replayed after interruption.
    return await asyncio.to_thread(run_stage, job_id, token, workflow.get_step_metadata().run_id, 'isolated')


@wf.step(max_retries=2)
async def record_failure(job_id: str, token: str) -> None:
    import asyncio
    from app.services.cloud_jobs import fail_job
    await asyncio.to_thread(fail_job, job_id, token, run_id=workflow.get_step_metadata().run_id)


@wf.workflow
async def execute_job(job_id: str, token: str, kind: str) -> None:
    try:
        if kind == 'investigation':
            for stage in ('triage', 'evidence', 'memory', 'analysis', 'fix', 'validation', 'report', 'finish'):
                if not await investigation_stage(job_id, token, stage):
                    return
        elif kind == 'validation':
            await isolated_validation(job_id, token)
    except Exception:
        await record_failure(job_id, token)

