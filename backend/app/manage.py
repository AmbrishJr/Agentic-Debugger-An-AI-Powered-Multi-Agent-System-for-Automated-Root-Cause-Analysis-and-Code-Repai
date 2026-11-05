"""Local operator commands. Passwords never appear in arguments, output, or logs."""
import argparse
import getpass
import re
from sqlalchemy import select, func
from app.db.migrate import migrate
from app.db.session import SessionLocal, serialize_write
from app.models.records import User, AuthSession
from app.services.auth import password_hash


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['create-admin','reset-password'])
    parser.add_argument('--username',required=True)
    args=parser.parse_args()
    username=args.username.lower()
    if not re.fullmatch(r'[a-z0-9_.-]{3,64}',username):parser.error('Username must be 3–64 letters, digits, dots, underscores, or hyphens.')
    password=getpass.getpass('Password (12+ characters): ')
    if password!=getpass.getpass('Confirm password: '):parser.error('Passwords do not match.')
    hashed=password_hash(password)
    migrate()
    with SessionLocal() as db:
        serialize_write(db, 'workspace-admins')
        user=db.scalar(select(User).where(User.username==username))
        if args.command=='create-admin':
            if db.scalar(select(func.count()).select_from(User)):
                parser.error('Workspace is already initialized. Use its administrator account to add users.')
            db.add(User(username=username,password_hash=hashed,role='admin'))
        else:
            if not user:parser.error('User not found.')
            user.password_hash=hashed
            for session in db.scalars(select(AuthSession).where(AuthSession.user_id==user.id)):db.delete(session)
        db.commit()
    print('Account updated. Sign in through the application.')


if __name__=='__main__':main()
