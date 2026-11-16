"""Read-only release/schema checks shared by health and deployment preflight."""
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import false, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import records  # Register every application table before probing.
from app.db.session import Base


class DatabaseNotReady(RuntimeError):
    pass


@lru_cache(maxsize=1)
def release_heads():
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'migrations'))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def check_database_schema(db: Session):
    """Require this release's revisions and readable tables/columns, without rows or writes.

    Revision equality alone cannot detect a stamped but incomplete migration.
    The zero-row subqueries resolve every mapped column in one database round trip.
    This does not audit indexes, constraints, column types or application records.
    """
    expected = release_heads()
    try:
        with db.no_autoflush:
            actual = frozenset(db.execute(text('SELECT version_num FROM alembic_version')).scalars())
            if not expected or actual != expected:
                raise DatabaseNotReady('Database migrations do not match this release. Apply the release migrations before serving traffic.')
            probes = [select(*table.c).where(false()).exists().label(table.name)
                      for table in Base.metadata.sorted_tables]
            db.execute(select(*probes)).one()
    except SQLAlchemyError:
        # Driver exceptions may contain credentials, SQL, or private values.
        raise DatabaseNotReady('Database schema readiness could not be confirmed. Check connectivity, permissions and release migrations.') from None
