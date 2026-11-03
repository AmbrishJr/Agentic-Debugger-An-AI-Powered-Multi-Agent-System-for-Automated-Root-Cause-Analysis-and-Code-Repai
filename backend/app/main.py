import hmac
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from sqlalchemy import select
from app.api.routes import router
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.migrate import migrate
from app.models.records import Incident, Investigation, AgentExecution, ProposedFix, ValidationRun, now
from app.services import sandbox


@asynccontextmanager
async def lifespan(app):
    migrate()
    # Single worker local service: make interrupted jobs explicit on restart.
    with SessionLocal() as db:
        for run in db.scalars(select(ValidationRun).where(ValidationRun.status == 'running')):
            cleaned = all([sandbox.cleanup(sandbox.container_name(run.id, phase)) for phase in ('before', 'after')])
            run.status, run.finished_at, run.snapshot = 'error', now(), {}
            run.result = {'error': 'Service restarted during isolated validation.', 'cleanup_succeeded': cleaned}
            fix = db.get(ProposedFix, run.fix_id)
            fix.validation_result = {**fix.validation_result, 'status': 'error', 'isolated': run.result}
        for row in db.scalars(select(Incident).where(Incident.status == 'investigating')):
            row.status = 'failed'
        for row in db.scalars(select(AgentExecution).where(AgentExecution.execution_status == 'running')):
            row.execution_status, row.error_details = 'failed', 'Service restarted during execution.'
        for row in db.scalars(select(Investigation).where(Investigation.agent_status != 'completed')):
            row.agent_status = 'failed'
        for row in db.scalars(select(ProposedFix).where(ProposedFix.pr_status == 'creating')):
            row.pr_status = 'failed'
        db.commit()
    yield


app = FastAPI(title='AutoRCA-X', version='0.1.0', lifespan=lifespan)


@app.middleware('http')
async def request_guard(request: Request, call_next):
    if settings.autorca_api_token and not hmac.compare_digest(request.headers.get('x-autorca-token', ''), settings.autorca_api_token):
        return JSONResponse({'error': {'code': 'unauthorized', 'message': 'API authentication required.'}}, 401)
    if request.method in ('POST', 'PUT', 'PATCH'):
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'error': {'code': 'content_type', 'message': 'Use application/json.'}}, 415)
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > 100000:
                return JSONResponse({'error': {'code': 'too_large', 'message': 'Request exceeds 100 KB.'}}, 413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({'error': {'code': str(exc.status_code), 'message': str(exc.detail)}}, exc.status_code)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    errors = [{'field': '.'.join(map(str, e['loc'])), 'message': e['msg']} for e in exc.errors()]
    return JSONResponse({'error': {'code': 'validation', 'message': 'Check the submitted fields.', 'fields': errors}}, 422)


@app.exception_handler(ValueError)
async def invalid_value(request, exc):
    return JSONResponse({'error': {'code': 'invalid_input', 'message': str(exc)}}, 400)


@app.exception_handler(Exception)
async def internal_error(request, exc):
    return JSONResponse({'error': {'code': 'internal', 'message': 'The operation failed. No sensitive error details are returned.'}}, 500)


app.include_router(router)
