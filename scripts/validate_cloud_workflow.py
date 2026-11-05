#!/usr/bin/env python3
"""Exercise the real Vercel Workflow SDK locally with a disposable database and demo."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


async def exercise():
    from app.db.migrate import migrate
    from app.db.session import SessionLocal, engine
    from app.models.records import Incident, Investigation, Job, AgentExecution
    from app.services.sample import SAMPLE_LOG
    from app.services.preferences import preferences
    from app.cloud_workflows import execute_job
    from vercel import workflow
    from sqlalchemy import select
    migrate()
    with SessionLocal() as db:
        incident = Incident(title='Local cloud workflow verification', error_log=SAMPLE_LOG, status='investigating')
        db.add(incident)
        db.flush()
        db.add(Investigation(incident_id=incident.id, config=preferences(db)))
        job = Job(kind='investigation', target_id=incident.id, incident_id=incident.id)
        db.add(job)
        db.commit()
        job_id, token, incident_id = job.id, job.dispatch_token, incident.id
    try:
        run = await workflow.start(execute_job, job_id, token, 'investigation')
        async def finish():
            while await run.status() in ('pending', 'running'):
                await asyncio.sleep(0.2)
            await run.return_value()
        await asyncio.wait_for(finish(), timeout=90)
        with SessionLocal() as db:
            inv = db.scalar(select(Investigation).where(Investigation.incident_id == incident_id))
            executions = list(db.scalars(select(AgentExecution).where(AgentExecution.investigation_id == inv.id)))
            assert db.get(Job, job_id).status == 'completed'
            assert db.get(Incident, incident_id).status == 'awaiting_review'
            assert len(executions) == 7 and all(item.execution_status == 'completed' for item in executions)
        print(json.dumps({'transport':'Vercel SDK local embedded queues', 'agents':7, 'status':'passed',
                          'hosted_verification':False}))
    finally:
        # The pinned SDK's local test transport owns an embedded queue service.
        from vercel.workflow._internal.world import get_world
        await get_world().aclose()
        engine.dispose()


def main():
    with tempfile.TemporaryDirectory(prefix='autorca-cloud-workflow-') as temporary:
        for name in list(os.environ):
            if name.startswith(('VERCEL_', 'WORKFLOW_')) or name == 'VERCEL':
                os.environ.pop(name)
        os.environ.update(DATABASE_URL='sqlite:///' + str(Path(temporary)/'test.db'),
            WORKFLOW_LOCAL_DATA_DIR=str(Path(temporary)/'workflow'), JOB_EXECUTION='external',
            AUTH_ENABLED='false', MIGRATE_ON_STARTUP='false', SANDBOX_ENABLED='false',
            OPENAI_API_KEY='', GEMINI_API_KEY='', GITHUB_TOKEN='', REPOSITORY_ROOT='',
            AUTORCA_API_TOKEN='', LLM_PROVIDER='openai')
        sys.path.insert(0, str(ROOT/'backend'))
        asyncio.run(exercise())


if __name__ == '__main__':
    main()
