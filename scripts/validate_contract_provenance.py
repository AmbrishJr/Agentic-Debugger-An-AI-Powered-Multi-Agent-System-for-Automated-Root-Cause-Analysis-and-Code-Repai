"""Opt-in synthetic API/provenance/isolated-run check; seeded proposal, never an accuracy benchmark."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/evaluations/registered-contract-isolated.json')
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute is required to authorize isolated synthetic execution.')
    with tempfile.TemporaryDirectory(prefix='autorca-provenance-') as temp:
        source = Path(temp, 'source'); source.mkdir()
        original = 'def calculate(x):\n    return 0 if x == 0 else x - 1\n'
        proposed = 'def calculate(x):\n    return 0 if x == 0 else x + 1\n'
        (source / 'logic.py').write_text(original)
        (source / 'main.py').write_text('import json,sys\nfrom logic import calculate\nprint(json.dumps(calculate(json.load(sys.stdin))))\n')
        os.environ.update(DATABASE_URL='sqlite:///' + str(Path(temp,'checks.db')), REPOSITORY_ROOT=str(source),
            AUTH_ENABLED='true', JOB_EXECUTION='inline', MIGRATE_ON_STARTUP='true', AUTORCA_API_TOKEN='',
            SANDBOX_ENABLED='true', SANDBOX_PROVIDER='docker', OPENAI_API_KEY='', GEMINI_API_KEY='', GITHUB_TOKEN='')
        os.environ.pop('VERCEL', None)
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import SessionLocal
        from app.models.records import User, ProposedFix, Incident
        from app.services.auth import password_hash
        from app.services.security import digest
        from app.services.patches import unified_patch
        from app.services import sandbox
        ready = sandbox.availability()
        result = {'kind':'registered_contract_integration', 'accuracy_benchmark':False, 'proposal_origin':'seeded_synthetic_reference',
                  'availability':ready, 'status':'skipped'}
        if ready['available']:
            with TestClient(app) as client:
                with SessionLocal() as db:
                    hashed = password_hash('synthetic-contract-password')
                    for name in ('synthetic-author','synthetic-reviewer'):
                        db.add(User(username=name,password_hash=hashed,role='editor'))
                    db.commit()
                def login(name):
                    response = client.post('/api/auth/login',json={'username':name,'password':'synthetic-contract-password'})
                    response.raise_for_status()
                    client.headers['x-csrf-token'] = response.json()['csrf_token']
                login('synthetic-author')
                response = client.post('/api/incidents',json={'title':'Synthetic increment behavior', 'repository':'local', 'mode':'demo',
                    'selected_files':['logic.py'], 'error_log':'File "logic.py", line 2, in calculate\nValueError: increment result was 1 for input 2'})
                response.raise_for_status(); identifier = response.json()['id']
                declaration = {'version':1, 'reviewed':True, 'entrypoint':'main.py', 'rationale':'Independently specified increment and unchanged-zero behavior for a synthetic fixture.',
                    'cases':[{'id':'increment','role':'reproduction','input':2,'baseline':1,'expected':3},
                             {'id':'zero','role':'regression','input':0,'baseline':0,'expected':0}]}
                base = f'/api/incidents/{identifier}'
                response = client.post(base+'/verification-contract',json={'files':['main.py','logic.py'],'contract':declaration})
                response.raise_for_status(); registration = response.json()
                body = {'registration_sha256':registration['sha256'],'reviewed':True,'rationale':'Reviewed the synthetic incident mapping and required zero-input regression independently of a proposed patch.'}
                assert client.post(base+'/verification-contract/review',json=body).status_code == 400
                assert client.post(base+'/investigate',json={}).status_code == 400
                login('synthetic-reviewer')
                response = client.post(base+'/verification-contract/review',json=body)
                response.raise_for_status(); review = response.json()
                client.post(base+'/investigate',json={}).raise_for_status()
                # Demo intentionally abstains outside its bundled fixture. Seed a reference proposal
                # only AFTER the real contract registration, review and investigation lifecycle.
                with SessionLocal() as db:
                    incident = db.get(Incident, identifier)
                    incident.status = 'awaiting_review'
                    db.add(ProposedFix(incident_id=identifier,path='logic.py',original_code=original,proposed_code=proposed,
                        original_sha256=digest(original),proposed_patch=unified_patch('logic.py',original,proposed),
                        explanation='Seeded synthetic reference proposal, not model output.',risks=[],
                        validation_result={'status':'partial','checks':[{'name':'Repository tests','status':'skipped','detail':'Pending authorized isolation.'}]}))
                    db.commit()
                response = client.post(base+'/validation-plans',json={'files':['main.py','logic.py'],'profile':'python-json-stdio',
                    'registered_contract_sha256':registration['sha256']})
                response.raise_for_status(); planned = response.json()
                client.post(base+f'/validation-runs/{planned["id"]}/authorize',json={'authorized':True,'plan_hash':planned['plan_hash']}).raise_for_status()
                detail = client.get(base).json()
                patch = client.get(base+'/patch').json()
                report = client.get(base+'/report').json()
                assert detail['repair_outcome'] == patch['repair_outcome'] == report['repair_outcome']
                assert detail['repair_outcome']['status'] == 'VERIFIED', report['validation']
                client.post(base+'/approve',json={'note':'Synthetic integration check only.'}).raise_for_status()
                assert client.get(base).json()['repair_outcome'] == detail['repair_outcome']
                run = client.get(base+'/validation-runs').json()['items'][0]
                result.update(status='passed', registration=registration, review=review, validation_run=run,
                    repair_outcome=detail['repair_outcome'], checks=['self-review rejected','investigation waits for review',
                    'different authenticated account reviewed','answers frozen before investigation','registered sources pinned',
                    'real expected failure and regressions matched','outcomes identical across API/report','approval preserves scoped outcome'])
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'status':result['status'],'kind':result['kind'],'accuracy_benchmark':False,'artifact':str(args.output)}))


if __name__ == '__main__':
    main()
