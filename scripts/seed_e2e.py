"""Initialize only the dedicated browser-test database with a non-production account."""
import os
from pathlib import Path
if os.environ.get('AUTORCA_E2E') != '1' or Path(os.environ.get('DATABASE_URL', '')).name != 'e2e.db':
    raise SystemExit('This initializer is restricted to the explicitly selected e2e database.')
from app.db.migrate import migrate
from app.db.session import SessionLocal
from app.models.records import User
from app.services.auth import password_hash
from sqlalchemy import select
migrate()
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username == 'browser-admin'))
    if not user:
        db.add(User(username='browser-admin', password_hash=password_hash('browser-test-password-only'), role='admin'))
        db.commit()
