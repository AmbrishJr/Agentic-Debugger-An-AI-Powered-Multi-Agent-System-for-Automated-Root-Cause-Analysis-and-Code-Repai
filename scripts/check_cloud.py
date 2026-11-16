#!/usr/bin/env python3
"""Read-only database readiness check before deploying this release. No provider calls."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-env', type=Path, required=True,
                        help='Ignored file containing the target PostgreSQL DATABASE_URL')
    args = parser.parse_args()
    from dotenv import dotenv_values
    if not args.target_env.is_file():
        parser.error('Target environment file does not exist.')
    url = dotenv_values(args.target_env).get('DATABASE_URL') or ''
    if not url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        parser.error('The target file must contain a PostgreSQL DATABASE_URL.')
    os.environ['DATABASE_URL'] = url
    os.environ['MIGRATE_ON_STARTUP'] = 'false'
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.db.readiness import check_database_schema
    from app.db.session import engine, SessionLocal
    try:
        with SessionLocal() as db:
            check_database_schema(db)
        print('Database schema is ready for this release. No records were changed.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Do not expose connection strings or driver errors in deployment logs.
        print('Database readiness failed. Check connectivity, permissions and release migrations. No migration was attempted.', file=sys.stderr)
        raise SystemExit(1)
