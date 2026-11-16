from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.readiness import check_database_schema
from app.db.session import get_db, SessionLocal
from app.main import app


@pytest.fixture
def database(tmp_path):
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'migrations'))
    config.set_main_option('sqlalchemy.url', 'sqlite:///' + str(tmp_path / 'readiness.db'))
    engine = create_engine(config.get_main_option('sqlalchemy.url'))
    try:
        yield config, engine
    finally:
        engine.dispose()


def override_database(engine):
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = session


def test_health_rejects_old_schema_and_recovers_after_migration(client, database):
    config, engine = database
    command.upgrade(config, '004')
    override_database(engine)
    try:
        response = client.get('/api/health')
        assert response.status_code == 503
        assert response.json()['error']['code'] == 'database_not_ready'
        assert response.headers['cache-control'] == 'no-store'
        with engine.connect() as connection:
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar() == '004'
        command.upgrade(config, 'head')
        response = client.get('/api/health')
        assert response.status_code == 200
        assert response.json()['schema_ready'] is True
        assert response.json()['live_available'] is False
        assert response.headers['cache-control'] == 'no-store'
        with engine.connect() as connection:
            assert connection.execute(text('SELECT count(*) FROM app_preferences')).scalar() == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize('damage', ['uninitialized', 'missing_version', 'future_revision', 'missing_column', 'missing_table'])
def test_health_rejects_incomplete_schema(client, database, damage):
    config, engine = database
    if damage != 'uninitialized':
        command.upgrade(config, 'head')
        statement = {
            'missing_version': 'DELETE FROM alembic_version',
            'future_revision': "UPDATE alembic_version SET version_num='future-release'",
            'missing_column': 'ALTER TABLE incidents DROP COLUMN repository_snapshot',
            'missing_table': 'DROP TABLE login_throttles',
        }[damage]
        with engine.begin() as connection:
            connection.execute(text(statement))
    override_database(engine)
    try:
        response = client.get('/api/health')
        assert response.status_code == 503
        assert response.json()['status'] == 'unavailable'
        assert 'SELECT' not in response.text
        assert str(engine.url) not in response.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_sanitizes_database_failure(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OperationalError('private SQL', {}, Exception('postgresql://secret:password@private-host/db'))
    monkeypatch.setattr(Session, 'execute', unavailable)
    response = client.get('/api/health')
    assert response.status_code == 503
    assert 'secret' not in response.text and 'private' not in response.text


def test_readiness_works_on_active_test_dialect_without_writes(client):
    from app.models.records import User
    with SessionLocal() as db:
        db.add(User(username='must-not-flush', password_hash='not-a-credential', role='viewer'))
        check_database_schema(db)
        assert db.execute(text('SELECT count(*) FROM users')).scalar() == 0
        db.rollback()
