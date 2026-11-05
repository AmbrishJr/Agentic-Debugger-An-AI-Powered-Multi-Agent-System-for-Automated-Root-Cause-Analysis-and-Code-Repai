import os
import tempfile
from pathlib import Path
import pytest

# Isolate tests from the user's database and any real credentials.
_temporary = tempfile.TemporaryDirectory(prefix='autorca-tests-')
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_temporary.name) / 'tests.db')
if os.environ.get('AUTORCA_TEST_POSTGRES_URL'):
    from sqlalchemy.engine import make_url
    url = make_url(os.environ['AUTORCA_TEST_POSTGRES_URL'])
    if url.host not in ('localhost', '127.0.0.1') or url.database != 'autorca_test':
        raise RuntimeError('PostgreSQL tests require a local disposable autorca_test database.')
    os.environ['DATABASE_URL'] = os.environ['AUTORCA_TEST_POSTGRES_URL']
os.environ['OPENAI_API_KEY'] = ''
os.environ['GEMINI_API_KEY'] = ''
os.environ['LLM_PROVIDER'] = 'openai'
os.environ['GITHUB_TOKEN'] = ''
os.environ['AUTORCA_API_TOKEN'] = ''
os.environ['REPOSITORY_ROOT'] = ''
os.environ['SANDBOX_ENABLED'] = 'false'
os.environ['AUTH_ENABLED'] = 'false'
os.environ['JOB_EXECUTION'] = 'inline'
os.environ['MIGRATE_ON_STARTUP'] = 'true'
os.environ['SANDBOX_PROVIDER'] = 'docker'

from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db.session import engine


@pytest.fixture
def client():
    with TestClient(app) as client:
        with engine.begin() as connection:
            for table in ('auth_sessions', 'users', 'login_throttles', 'jobs', 'worker_state', 'incident_events', 'memory_fts', 'incident_memory', 'agent_executions', 'validation_runs', 'proposed_fixes', 'investigations', 'incidents', 'app_preferences'):
                if table == 'memory_fts' and engine.dialect.name != 'sqlite':
                    continue
                connection.execute(text(f'DELETE FROM {table}'))
        yield client
