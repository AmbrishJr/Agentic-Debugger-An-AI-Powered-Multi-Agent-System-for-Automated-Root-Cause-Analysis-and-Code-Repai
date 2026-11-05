from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from app.db.session import get_db, serialize_write
from app.models.records import User, AuthSession, LoginThrottle, now
from app.schemas.contracts import StrictModel
from app.services.auth import COOKIE, password_hash, verify_password, create_session, load_session, public_user
from app.core.config import settings

router=APIRouter(prefix='/api')


class Login(StrictModel):
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,64}$')
    password: str = Field(min_length=1,max_length=256)


class CreateUser(Login):
    password: str = Field(min_length=12,max_length=256)
    role: Literal['admin','editor','viewer'] = 'viewer'


class UpdateUser(StrictModel):
    role: Literal['admin','editor','viewer']
    active: bool


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=1,max_length=256)
    new_password: str = Field(min_length=12,max_length=256)


@router.get('/auth/me')
def me(request:Request,db=Depends(get_db)):
    if not settings.auth_enabled:
        return {'enabled':False,'user':{'id':'local','username':'local developer','role':'admin','active':True},'csrf_token':''}
    user,session=load_session(db,request.cookies.get(COOKIE))
    return {'enabled':True,'user':public_user(user) if user else None,'csrf_token':session.csrf_token if session else '',
            'deployment':'vercel' if settings.job_execution == 'vercel' else 'local',
            'setup_required':db.scalar(select(func.count()).select_from(User))==0}


@router.post('/auth/login')
def login(body:Login,response:Response,db=Depends(get_db)):
    username=body.username.lower()
    # Serialize rate-limit updates. A missing username gets the same password work.
    serialize_write(db, 'login:' + username)
    throttle=db.get(LoginThrottle,username)
    if not throttle or throttle.expires_at <= now():
        if throttle: db.delete(throttle);db.flush()
        throttle=LoginThrottle(key=username,attempts=0,expires_at=(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat())
        db.add(throttle)
    if throttle.attempts>=10:
        db.commit()
        raise HTTPException(429,'Too many failed sign-in attempts. Try again in 15 minutes.')
    user=db.scalar(select(User).where(User.username==username))
    encoded=user.password_hash if user else 'pbkdf2_sha256$600000$'+'00'*16+'$'+'00'*32
    valid=verify_password(body.password,encoded)
    if not valid or not user or not user.active:
        throttle.attempts+=1
        db.commit()
        raise HTTPException(401,'Invalid username or password.')
    db.delete(throttle)
    session=create_session(db,user,response)
    return {'user':public_user(user),'csrf_token':session.csrf_token}


@router.post('/auth/logout')
def logout(request:Request,response:Response,db=Depends(get_db)):
    _,session=load_session(db,request.cookies.get(COOKIE))
    if session: db.delete(session);db.commit()
    response.delete_cookie(COOKIE,path='/',httponly=True,secure=settings.secure_cookies,samesite='strict')
    return {'status':'signed_out'}


@router.post('/auth/password')
def change_password(body:PasswordChange,request:Request,response:Response,db=Depends(get_db)):
    user=db.get(User,request.state.user['id'])
    if not user or not verify_password(body.current_password,user.password_hash):
        raise HTTPException(400,'Current password is incorrect.')
    user.password_hash=password_hash(body.new_password)
    db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
    db.commit()
    response.delete_cookie(COOKIE,path='/')
    return {'status':'password_changed_sign_in_again'}


@router.get('/users')
def list_users(db=Depends(get_db)):
    return {'items':[public_user(u) for u in db.scalars(select(User).order_by(User.created_at))]}


@router.post('/users',status_code=201)
def create_user(body:CreateUser,db=Depends(get_db)):
    username=body.username.lower()
    if db.scalar(select(User).where(User.username==username)):
        raise HTTPException(409,'Username already exists.')
    user=User(username=username,password_hash=password_hash(body.password),role=body.role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Username already exists.') from None
    return public_user(user)


@router.put('/users/{user_id}')
def update_user(user_id:str,body:UpdateUser,db=Depends(get_db)):
    serialize_write(db, 'workspace-admins')
    user=db.get(User,user_id)
    if not user: raise HTTPException(404,'User not found.')
    admins=db.scalar(select(func.count()).select_from(User).where(User.role=='admin',User.active==True))
    if user.role=='admin' and user.active and admins<=1 and (not body.active or body.role!='admin'):
        raise HTTPException(409,'The workspace must retain at least one active administrator.')
    user.role,user.active=body.role,body.active
    db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
    db.commit()
    return public_user(user)
