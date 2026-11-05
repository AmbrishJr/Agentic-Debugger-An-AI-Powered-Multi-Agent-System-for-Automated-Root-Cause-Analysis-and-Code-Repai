#!/usr/bin/env python3
"""Migrate schema and optionally copy an offline SQLite workspace. Never prints secrets."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-env', type=Path, required=True, help='Ignored file containing the target DATABASE_URL')
    parser.add_argument('--source', type=Path, help='Existing offline SQLite file; omit for schema migration only')
    parser.add_argument('--execute', action='store_true', help='Required to change the target database')
    args = parser.parse_args()
    from dotenv import dotenv_values
    url = dotenv_values(args.target_env).get('DATABASE_URL', '')
    if not url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        parser.error('The target file must contain a PostgreSQL DATABASE_URL.')
    if args.source and not args.source.is_file():
        parser.error('Source database does not exist.')
    if not args.execute:
        print('Ready to apply schema migrations' + (' and copy the offline workspace into an empty database.' if args.source else '.') + ' Add --execute to proceed.')
        return
    os.environ['DATABASE_URL'] = url
    os.environ['JOB_EXECUTION'] = 'inline'
    os.environ['MIGRATE_ON_STARTUP'] = 'false'
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.db.migrate import migrate
    from app.db.session import engine
    migrate()
    if args.source:
        from app.db.transfer import transfer
        counts = transfer(args.source, engine)
        print('Workspace copied. Existing account passwords are preserved; sign in again.')
        print('Copied records:', sum(counts.values()))
    else:
        print('Schema migrations completed.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Driver errors may contain connection URLs or source data.
        print('Migration failed. Check connectivity, permissions, target emptiness, and active local jobs. Credentials and source records are not printed.', file=sys.stderr)
        raise SystemExit(1)
