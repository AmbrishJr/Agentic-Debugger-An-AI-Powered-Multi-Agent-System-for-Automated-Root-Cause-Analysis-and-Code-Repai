import os
import tempfile
from pathlib import Path
import pytest

# Isolate tests from the user's database and any real credentials.
_temporary = tempfile.TemporaryDirectory(prefix='autorca-tests-')
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_temporary.name) / 'tests.db')
os.environ['OPENAI_API_KEY'] = ''
os.environ['GEMINI_API_KEY'] = ''
os.environ['LLM_PROVIDER'] = 'openai'
os.environ['GITHUB_TOKEN'] = ''
os.environ['AUTORCA_API_TOKEN'] = ''
os.environ['REPOSITORY_ROOT'] = ''
os.environ['SANDBOX_ENABLED'] = 'false'
os.environ['AUTH_ENABLED'] = 'false'
os.environ['JOB_EXECUTION'] = 'inline'

from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db.session import engine


@pytest.fixture
def client():
    with TestClient(app) as client:
        with engine.begin() as connection:
            for table in ('auth_sessions', 'users', 'login_throttles', 'jobs', 'worker_state', 'incident_events', 'memory_fts', 'incident_memory', 'agent_executions', 'validation_runs', 'proposed_fixes', 'investigations', 'incidents', 'app_preferences'):
                connection.execute(text(f'DELETE FROM {table}'))
        yield client
