from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.pool import NullPool
from hashlib import sha256
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings


class Base(DeclarativeBase):
    pass


def database_url(value):
    if value.startswith(('postgres://', 'postgresql://')):
        return 'postgresql+psycopg://' + value.split('://', 1)[1]
    return value


def make_engine(url):
    url = database_url(url)
    if url.startswith('sqlite:///'):
        Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
        result = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30})
        event.listen(result, 'connect', sqlite_setup)
        return result
    if not url.startswith('postgresql+psycopg://'):
        raise ValueError('Use SQLite locally or PostgreSQL for cloud deployments.')
    # A hosted pooler owns the pool; each function releases its connections.
    return create_engine(url, poolclass=NullPool, connect_args={'connect_timeout': 10, 'prepare_threshold': None})


def sqlite_setup(connection, _):
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA journal_mode=WAL')


def serialize_write(db, key):
    """Protect read/modify/write operations, including rows that don't exist yet."""
    if db.get_bind().dialect.name == 'sqlite':
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    else:
        from sqlalchemy import text
        lock_id = int.from_bytes(sha256(key.encode()).digest()[:8], 'big', signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_id})


engine = make_engine(settings.database_url)


SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
