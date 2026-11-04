"""Explicit live Gemini check: only bundled synthetic evidence, isolated database."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--model',default=None)
    parser.add_argument('--output',default='docs/gemini-validation.json')
    args=parser.parse_args()
    if not args.execute:parser.error('Pass --execute to authorize Gemini requests containing bundled synthetic evidence only.')
    with tempfile.TemporaryDirectory(prefix='autorca-gemini-check-') as tmp:
        os.environ.update(DATABASE_URL='sqlite:///'+str(Path(tmp)/'validation.db'),LLM_PROVIDER='gemini',
            AUTH_ENABLED='false',JOB_EXECUTION='inline',AUTORCA_API_TOKEN='',REPOSITORY_ROOT='',
            GITHUB_TOKEN='',OPENAI_API_KEY='',SANDBOX_ENABLED='false')
        from app.core.config import settings
        from app.main import app
        from app.services.sample import SAMPLE_LOG
        from fastapi.testclient import TestClient
        model=args.model or settings.gemini_model
        report={'status':'started','provider':'gemini','model':model,'checked_at':datetime.now(timezone.utc).isoformat(),
                'scope':'Live structured generation on bundled synthetic evidence. No production logs/source, approval, publication, or generated-code execution.'}
        output=Path(args.output)
        def save():output.write_text(json.dumps(report,indent=2)+'\n')
        save()
        if not settings.gemini_api_key:
            report.update(status='blocked',reason='GEMINI_API_KEY is not configured.');save()
            print(json.dumps(report,indent=2));return
        with TestClient(app) as client:
            response=client.put('/api/settings',json={'provider':'gemini','model':model})
            assert response.status_code==200
            response=client.post('/api/incidents',json={'title':'Synthetic Gemini checkout check','error_log':SAMPLE_LOG,
                'repository':'sample','selected_files':['checkout.py'],'mode':'live'})
            assert response.status_code==201
            identifier=response.json()['id']
            assert client.post(f'/api/incidents/{identifier}/investigate',json={}).status_code==202
            result=client.get(f'/api/incidents/{identifier}').json()
            report.update(incident_status=result['status'],agents=[{'name':e['agent_name'],'status':e['execution_status'],
                'error':e['error_details']} for e in result['executions']],
                changed_files=[f['path'] for f in (result['fix'] or {}).get('files',[])],
                validation=(result['fix'] or {}).get('validation_result',{}).get('status'))
            report['status']='passed' if result['status']=='awaiting_review' and len(result['executions'])==7 and all(e['execution_status']=='completed' for e in result['executions']) and report['validation'] in ('passed','partial') else 'failed'
            if report['status']=='passed':
                report['checks']=['Real Gemini authentication','Provider selection','Structured triage, analysis, patch, and report',
                    'Evidence citations validated','Collected patch paths and source hashes verified','Proposed Python syntax parsed without execution',
                    'Repository tests honestly skipped pending isolated authorization','Report available before human review']
            save()
        print(json.dumps(report,indent=2))
        if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
