"""Copy an offline local workspace into an empty cloud database, atomically."""
from sqlalchemy import MetaData, create_engine, select, func
from app.db.session import Base
from app.models import records

OMIT = {'auth_sessions', 'login_throttles', 'worker_state'}


def transfer(source_path, target):
    # mode=ro prevents modifying or creating the source database.
    from urllib.parse import quote
    source = create_engine('sqlite:///file:' + quote(str(source_path.resolve()), safe='/') + '?mode=ro&uri=true')
    old = MetaData()
    old.reflect(source)
    if 'users' not in old.tables or 'incidents' not in old.tables:
        raise ValueError('Source is not an initialized AutoRCA workspace.')
    try:
        with source.connect() as src, target.begin() as dst:
            if dst.dialect.name != 'postgresql':
                raise ValueError('The migration target must be PostgreSQL.')
            dst.exec_driver_sql("SELECT pg_advisory_xact_lock(731947220)")
            for table in Base.metadata.sorted_tables:
                if dst.scalar(select(func.count()).select_from(table)):
                    raise ValueError('Target must be empty. Existing cloud data will never be overwritten.')
            for name, states in (('jobs', ('running', 'queued')), ('validation_runs', ('running', 'cleanup_failed'))):
                if name in old.tables:
                    table = old.tables[name]
                    if src.scalar(select(func.count()).select_from(table).where(table.c.status.in_(states))):
                        raise ValueError('Stop local workers and finish or cancel active jobs before copying the workspace.')
            counts = {}
            for table in Base.metadata.sorted_tables:
                if table.name in OMIT or table.name not in old.tables:
                    continue
                rows = []
                for row in src.execute(select(old.tables[table.name])).mappings():
                    values = {key: value for key, value in row.items() if key in table.c}
                    if table.name == 'validation_runs':
                        values['snapshot'] = {}
                        if values['status'] == 'planned':
                            values['status'] = 'expired'
                    if table.name == 'jobs':
                        values['workflow_run_id'] = None
                        values['dispatch_token'] = records.uid()
                    if table.name == 'proposed_fixes' and values['pr_status'] == 'creating':
                        values['pr_status'] = 'failed'
                    rows.append(values)
                if rows:
                    dst.execute(table.insert(), rows)
                counts[table.name] = len(rows)
            return counts
    finally:
        source.dispose()
