"""Opt-in real Docker/Colima validation. All source is synthetic; no API credentials are needed."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

ISOLATION_TESTS = '''import os
from pathlib import Path
import socket
import unittest

class IsolationTests(unittest.TestCase):
    def test_non_root(self):
        self.assertEqual(os.getuid(), 65534)
    def test_no_network(self):
        with socket.socket() as client:
            client.settimeout(1)
            with self.assertRaises(OSError):
                client.connect(("1.1.1.1", 80))
    def test_root_is_read_only(self):
        with self.assertRaises(OSError):
            Path("/outside-workspace").write_text("not allowed")
    def test_no_application_credentials(self):
        for key in ("OPENAI_API_KEY", "GITHUB_TOKEN", "AUTORCA_API_TOKEN"):
            self.assertNotIn(key, os.environ)
    def test_no_docker_socket(self):
        self.assertFalse(Path("/var/run/docker.sock").exists())
    def test_no_capabilities(self):
        status = Path("/proc/self/status").read_text()
        cap = next(line.split()[1] for line in status.splitlines() if line.startswith("CapEff:"))
        self.assertEqual(int(cap, 16), 0)
    def test_memory_and_process_limits(self):
        self.assertEqual(Path("/sys/fs/cgroup/pids.max").read_text().strip(), "32")
        self.assertEqual(Path("/sys/fs/cgroup/memory.max").read_text().strip(), str(256*1024*1024))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--context',default='colima-autorca')
    parser.add_argument('--output',default='docs/sandbox-validation.json')
    args=parser.parse_args()
    if not args.execute:
        parser.error('Pass --execute to authorize resource-limited synthetic test containers.')
    image = subprocess.run(['docker','--context',args.context,'image','inspect','autorca-runner:local','--format','{{.Id}}'],capture_output=True,text=True,check=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix='autorca-runner-check-') as tmp:
        os.environ.update(DATABASE_URL='sqlite:///' + str(Path(tmp)/'tests.db'),SANDBOX_ENABLED='true',
            SANDBOX_IMAGE=image,SANDBOX_DOCKER_CONTEXT=args.context,SANDBOX_TIMEOUT_SECONDS='10',AUTORCA_API_TOKEN='')
        from app.services import sandbox
        from app.services.sample import BUGGY, FIXED, REGRESSION_TEST
        from app.services.patches import unified_patch
        from app.services.security import digest
        from app.services.validation import validate
        from app.core.config import settings
        from app.db.session import SessionLocal
        from app.models.records import Incident, ProposedFix
        from app.main import app
        from fastapi.testclient import TestClient
        ready=sandbox.availability()
        if not ready['available']:
            raise RuntimeError(ready['reason'])
        settings.repository_root=tmp
        fixture={'checkout.py':BUGGY,'test_checkout.py':REGRESSION_TEST,'test_isolation.py':ISOLATION_TESTS}
        for name,content in fixture.items():
            Path(tmp,name).write_text(content)
        report={'status':'started','image':image,'docker_context':args.context}
        output=Path(args.output)
        def save():
            output.write_text(json.dumps(report,indent=2)+'\n')
        save()
        try:
            with TestClient(app) as client:
                with SessionLocal() as db:
                    incident=Incident(title='Synthetic Docker isolation check',error_log='Synthetic fixture only.',repository='local',status='awaiting_review')
                    db.add(incident);db.flush()
                    fix=ProposedFix(incident_id=incident.id,path='checkout.py',original_code=BUGGY,proposed_code=FIXED,
                        original_sha256=digest(BUGGY),proposed_patch=unified_patch('checkout.py',BUGGY,FIXED),
                        explanation='Synthetic runner validation.',risks=[],validation_result=validate('local','checkout.py',digest(BUGGY),FIXED,'demo'))
                    db.add(fix);db.commit();identifier=incident.id
                response=client.post(f'/api/incidents/{identifier}/validation-plans',json={'files':list(fixture)})
                assert response.status_code==201,response.text
                plan=response.json()
                report['plan_hash']=plan['plan_hash'];save()
                response=client.post(f'/api/incidents/{identifier}/validation-runs/{plan["id"]}/authorize',json={'authorized':True,'plan_hash':plan['plan_hash']})
                assert response.status_code==202,response.text
                run=client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'][0]
                report['before_after']=run['result'];save()
                assert run['status']=='completed',run['result']
                assert run['result']['before']['status']=='failed'
                assert run['result']['after']['status']=='passed'
                assert 'Ran 11 tests' in run['result']['after']['output']
                assert client.post(f'/api/incidents/{identifier}/approve',json={}).status_code==200
            settings.sandbox_timeout_seconds=5
            timeout=sandbox.run_snapshot(str(uuid.uuid4()),'before',{'test_timeout.py':'while True: pass\n'},sandbox.policy())
            report['timeout']={k:v for k,v in timeout.items() if k!='output'};save()
            assert timeout['timed_out'] and timeout['status']=='error' and timeout['cleanup_succeeded']
            noise=sandbox.run_snapshot(str(uuid.uuid4()),'before',{'test_output.py':'while True: print("x" * 8192, flush=True)\n'},sandbox.policy())
            report['output_limit']={k:v for k,v in noise.items() if k!='output'};save()
            assert noise['output_limited'] and noise['status']=='error' and noise['cleanup_succeeded']
            assert len(noise['output'].encode())<=sandbox.OUTPUT_LIMIT
            report.update(status='passed',checks=['API plan and one-use authorization','Original regression fails','Patched suite passes',
                'Non-root UID','No external network','Read-only root','No application credentials','No Docker socket','No Linux capabilities',
                'Enforced memory and PID limits','Timeout enforced','Output bounded','Containers removed','Approval after validation'])
            save()
        except Exception as exc:
            report.update(status='failed',error_type=type(exc).__name__);save()
            raise
        print(json.dumps({'status':report['status'],'checks':report['checks'],'report':str(output),'image':image},indent=2))


if __name__=='__main__':
    main()
