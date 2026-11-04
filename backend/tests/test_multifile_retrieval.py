import base64
import json
from types import SimpleNamespace
import httpx
from app.agents import workflow
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.records import Incident, ProposedFix, IncidentMemory
from app.services import github, sandbox
from app.services.memory import HybridRetriever, FTSRetriever
from app.services.security import digest


def test_multifile_generation_plan_and_stale_second_file(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'repository_root', str(tmp_path))
    originals = {'one.py':'x = 1\n', 'two.py':'y = 1\n', 'test_pair.py':'def test_pair(): assert True\n'}
    for path, content in originals.items(): (tmp_path / path).write_text(content)
    with SessionLocal() as db:
        incident = Incident(title='Two-file repair', error_log='Synthetic test', repository='local', status='awaiting_review')
        db.add(incident); db.commit(); identifier = incident.id
    changes = [{'path':p,'proposed_code':originals[p].replace('1','2')} for p in ('one.py','two.py')]
    monkeypatch.setattr(workflow.llm,'generate',lambda *args: {'path':'one.py','proposed_code':'x = 2\n','files':changes,'explanation':'Update pair','risks':[]})
    state = {'incident_id':identifier,'mode':'live','config':{'model':'test'},'repository':'local','analysis':{'summary':'test'},
             'evidence':[{'kind':'source','path':p,'sha256':digest(content)} for p,content in originals.items()]}
    fix = workflow.fix(state)
    assert len(fix['files']) == 2 and 'b/two.py' in fix['diff']
    state['fix'] = fix
    assert workflow.validation(state)['status'] == 'partial'
    monkeypatch.setattr(sandbox,'availability',lambda:{'available':True})
    path=f'/api/incidents/{identifier}'
    assert client.post(path+'/validation-plans',json={'files':['one.py','test_pair.py']}).status_code == 400
    plan=client.post(path+'/validation-plans',json={'files':list(originals),'profile':'python-pytest'}).json()
    assert plan['policy']['profile'] == 'python-pytest'
    (tmp_path/'two.py').write_text('y = 3\n')
    assert client.post(path+'/approve',json={}).status_code == 409
    assert client.post(path+f'/validation-runs/{plan["id"]}/authorize',json={'authorized':True,'plan_hash':plan['plan_hash']}).status_code == 400


def test_multifile_github_commit_is_atomic_and_retry_safe(monkeypatch):
    monkeypatch.setattr(settings,'github_token','synthetic-token')
    monkeypatch.setattr(settings,'github_repository','example/temporary')
    files=[{'path':p,'original_code':'old','proposed_code':'new'} for p in ('one.py','two.py')]
    incident=SimpleNamespace(id='pair',repository='local',title='Repair pair')
    fix=SimpleNamespace(files=files,explanation='Repair both files.',validation_result={'status':'partial'})
    calls=[]
    branch=False
    published=False
    def handle(r):
        nonlocal branch,published
        p=r.url.path.split('/temporary/')[1]
        calls.append((r.method,p,json.loads(r.content) if r.content else {}))
        if p=='pulls' and r.method=='GET': data=[]
        elif p=='git/ref/heads/main': data={'object':{'sha':'base'}}
        elif p=='git/commits/base': data={'tree':{'sha':'base-tree'}}
        elif p.startswith('contents/'): data={'encoding':'base64','content':base64.b64encode(b'old').decode()}
        elif p=='git/trees/base-tree': data={'tree':[{'path':p,'sha':'blob','mode':'100644'} for p in ('one.py','two.py')]}
        elif p=='git/blobs': data={'sha':'new-blob'}
        elif p=='git/trees':
            assert len(json.loads(r.content)['tree'])==2
            data={'sha':'new-tree'}
        elif p.startswith('git/ref/heads/autorca'):
            if not branch:return httpx.Response(404,json={})
            data={'object':{'sha':'commit' if published else 'base'}}
        elif p=='git/refs': branch=True;data={}
        elif p=='git/commits':
            assert json.loads(r.content)['tree']=='new-tree'
            data={'sha':'commit'}
        elif p.startswith('git/refs/heads/autorca'):
            assert json.loads(r.content)['force'] is False
            published=True;data={}
        elif p=='git/commits/commit':data={'tree':{'sha':'new-tree'}}
        elif p=='pulls':data={'html_url':'https://github.com/example/temporary/pull/1'}
        else:raise AssertionError(p)
        return httpx.Response(200,json=data)
    real=httpx.Client
    monkeypatch.setattr(github.httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(handle),**kw))
    github.create_pull_request(incident,fix)
    github.create_pull_request(incident,fix)
    assert sum(m=='PATCH' for m,_,_ in calls)==1
    assert sum(m=='POST' and p=='git/commits' for m,p,_ in calls)==1


def test_concept_vectors_find_related_terms_without_literal_overlap(client):
    with SessionLocal() as db:
        incident=Incident(title='Timeout',error_log='Synthetic')
        db.add(incident);db.flush()
        db.add(IncidentMemory(incident_id=incident.id,error_signature='deadline',root_cause='Database timeout',resolution_summary='Reduce query work.'))
        db.commit()
        assert FTSRetriever(db).search('slow sql','other') == []
        found=HybridRetriever(db).search('slow sql','other')
        assert found[0]['incident_id']==incident.id and found[0]['vector_similarity']>0
        assert 'no neural embeddings' in found[0]['retrieval']
        assert HybridRetriever(db).search('slow sql',incident.id)==[]
