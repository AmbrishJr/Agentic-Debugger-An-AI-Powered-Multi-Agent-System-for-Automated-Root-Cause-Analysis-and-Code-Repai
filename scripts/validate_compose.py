"""Opt-in disposable Compose verification; no real credentials or application data."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--context', default='colima-autorca')
    args = parser.parse_args()
    if not args.execute: parser.error('Pass --execute to start and remove a disposable verification stack.')
    root = Path(__file__).resolve().parents[1]
    project = 'autorca-verify-' + secrets.token_hex(4)
    report = {'status':'started','project':project,'checks':[]}
    output = root/'docs/compose-validation.json'
    def save(): output.write_text(json.dumps(report, indent=2)+'\n')
    save()
    # Do not pass provider, GitHub, or workspace secrets into this fixture.
    env = {k:v for k,v in os.environ.items() if k in ('PATH','HOME','DOCKER_CONFIG')}
    env['DOCKER_CONTEXT'] = args.context
    with tempfile.TemporaryDirectory(prefix='autorca-compose-check-') as tmp:
        config = Path(tmp)/'verify.env'
        config.write_text('BACKEND_PORT=18080\nFRONTEND_PORT=13080\nPUBLIC_ORIGIN=http://127.0.0.1:13080\n')
        binary = [shutil.which('docker-compose')] if shutil.which('docker-compose') else ['docker','compose']
        command = [*binary,'--env-file',str(config),'-p',project,'-f',str(root/'docker-compose.yml')]
        def compose(*args, input=None):
            result = subprocess.run([*command,*args], input=input, capture_output=True, text=True, env=env, timeout=120)
            if result.returncode: raise RuntimeError('Compose operation failed: ' + result.stderr[-2000:])
            return result.stdout
        try:
            compose('up','-d','--no-build','--wait','--wait-timeout','90')
            report['checks'].append('Three-service stack starts with isolated volume and loopback ports');save()
            password = secrets.token_urlsafe(24)
            seed = "import sys; from app.db.session import SessionLocal; from app.models.records import User; from app.services.auth import password_hash; db=SessionLocal(); db.add(User(username='verifier',password_hash=password_hash(sys.stdin.read()),role='admin')); db.commit()"
            compose('exec','-T','backend','python','-c',seed,input=password)
            with httpx.Client(base_url='http://127.0.0.1:13080',timeout=20) as web:
                for _ in range(40):
                    try:
                        if web.get('/api/health').status_code == 200:break
                    except httpx.HTTPError:pass
                    time.sleep(.5)
                assert web.get('/api/incidents').status_code == 401
                login=web.post('/api/auth/login',json={'username':'verifier','password':password})
                assert login.status_code == 200, login.text
                web.headers['x-csrf-token']=login.json()['csrf_token']
                report['checks'].append('Authentication cookie and CSRF token work through Next proxy');save()
                sample=web.get('/api/samples').json()['items'][0]
                incident=web.post('/api/incidents',json={k:sample[k] for k in ('title','error_log','repository','mode')}).json()
                path='/api/incidents/'+incident['id']
                compose('stop','worker')
                assert web.post(path+'/investigate',json={}).status_code == 202
                assert web.get(path).json()['jobs'][0]['status']=='queued'
                compose('start','worker')
                for _ in range(120):
                    detail=web.get(path).json()
                    if detail['status']!='investigating': break
                    time.sleep(.5)
                assert detail['status']=='awaiting_review',detail['status']
                assert len(detail['executions'])==7
                report['checks'].append('Persisted queued investigation completes after worker restart');save()
                assert web.post(path+'/approve',json={}).status_code==200
                assert web.post(path+'/resolve',json={'note':'Synthetic checkout recovery confirmed.','evidence':'Disposable Compose fixture and four regression tests.'}).status_code==200
                compose('restart','backend','worker')
                for _ in range(60):
                    response=web.get(path)
                    if response.status_code==200:break
                    time.sleep(.5)
                assert response.json()['status']=='resolved'
                assert web.get('/api/dashboard/stats').json()['resolved']==1
                report['checks'].append('Session, approval, resolution, audit, and database survive service restart');save()
                viewer_password=secrets.token_urlsafe(24)
                assert web.post('/api/users',json={'username':'viewer','password':viewer_password,'role':'viewer'}).status_code==201
                with httpx.Client(base_url='http://127.0.0.1:13080',timeout=20) as viewer:
                    login=viewer.post('/api/auth/login',json={'username':'viewer','password':viewer_password})
                    viewer.headers['x-csrf-token']=login.json()['csrf_token']
                    assert viewer.get(path).status_code==200
                    assert viewer.post(path+'/reopen',json={'note':'Attempted unauthorized change.'}).status_code==403
                report['checks'].append('Viewer reads incidents and cannot change them');save()
                assert web.post('/api/auth/logout',json={}).status_code==200
                assert web.get(path).status_code==401
                report['checks'].append('Logout revokes the server-side session')
            report['status']='passed'
        except Exception as exc:
            report.update(status='failed',error_type=type(exc).__name__)
            raise
        finally:
            try:
                compose('down','--volumes','--remove-orphans')
                report['cleanup']='Only this disposable project containers, network, and volume removed.'
            finally:save()
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
