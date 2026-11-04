import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, delete
from app.core.config import settings
from app.models.records import User, AuthSession, now

COOKIE = 'autorca_session'


def password_hash(password):
    if len(password) < 12 or len(password) > 256:
        raise ValueError('Passwords must contain 12–256 characters.')
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    return f'pbkdf2_sha256$600000${salt}${derived}'


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(rounds)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError):
        return False


def public_user(user):
    return {'id':user.id,'username':user.username,'role':user.role,'active':user.active}


def load_session(db, token):
    if not token:
        return None, None
    session = db.get(AuthSession,hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires_at <= now():
        return None, None
    user = db.get(User,session.user_id)
    return (user,session) if user and user.active else (None,None)


def create_session(db,user,response):
    token = secrets.token_urlsafe(32)
    ttl = min(24,max(1,settings.session_hours))*3600
    session = AuthSession(id=hashlib.sha256(token.encode()).hexdigest(),user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),expires_at=(datetime.now(timezone.utc)+timedelta(seconds=ttl)).isoformat())
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now()))
    db.add(session)
    db.commit()
    response.set_cookie(COOKIE,token,max_age=ttl,httponly=True,secure=settings.secure_cookies,samesite='strict',path='/')
    return session


def authorize(request,db):
    if not settings.auth_enabled:
        request.state.user = {'id':'local','username':'local developer','role':'admin','active':True}
        return
    user,session = load_session(db,request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401,'Sign in to access this workspace.')
    request.state.user = public_user(user)
    if request.method not in ('GET','HEAD','OPTIONS'):
        if not hmac.compare_digest(request.headers.get('x-csrf-token',''),session.csrf_token):
            raise HTTPException(403,'The session verification token is missing or expired. Reload and try again.')
        if user.role == 'viewer' and request.url.path not in ('/api/auth/logout','/api/auth/password'):
            raise HTTPException(403,'Viewer accounts cannot modify this workspace.')
        if (request.url.path == '/api/settings' or request.url.path.startswith('/api/users')) and user.role != 'admin':
            raise HTTPException(403,'Administrator access is required.')
    if request.url.path.startswith('/api/users') and user.role != 'admin':
        raise HTTPException(403,'Administrator access is required.')
