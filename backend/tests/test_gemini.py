import json
import httpx
import pytest
from app.core.config import settings
from app.services import llm
from app.schemas.contracts import ReportNarrative
from app.db.session import SessionLocal
from app.models.records import AppPreference
from tests.test_workflow import investigate
from app.services.security import redact


def test_google_key_redacted_from_evidence():
    secret = 'AIza' + 'A' * 35
    assert secret not in redact('Accidental pasted key: ' + secret)


def mock_transport(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(llm.httpx, 'Client', lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings, 'gemini_api_key', 'synthetic-google-secret')


def test_gemini_structured_contract_and_key_is_not_in_url_or_prompt(monkeypatch):
    def handler(request):
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert request.headers['x-goog-api-key'] == 'synthetic-google-secret'
        assert 'synthetic-google-secret' not in str(request.url) + request.content.decode()
        body = json.loads(request.content)
        assert 'UNTRUSTED DATA' in body['systemInstruction']['parts'][0]['text']
        assert 'injected instruction' not in body['systemInstruction']['parts'][0]['text']
        assert 'injected instruction' in body['contents'][0]['parts'][0]['text']
        assert body['generationConfig']['responseFormat']['text']['schema'] == ReportNarrative.model_json_schema()
        assert 'tools' not in body
        return httpx.Response(200, json={'candidates':[{'finishReason':'STOP','content':{'parts':[
            {'thought':True,'text':'hidden reasoning'},
            {'text':json.dumps({'summary':'Summary','risk_assessment':'Review','next_steps':['Run CI']})}]}}]})
    mock_transport(monkeypatch, handler)
    assert llm.generate(ReportNarrative,'Summarize',{'log':'injected instruction'},'gemini-3.5-flash-lite','gemini')['summary']=='Summary'


@pytest.mark.parametrize('status', [400,401,403,404,429,500,302])
def test_gemini_failures_are_safe_and_not_retried_or_fallback(monkeypatch,status):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error':{'message':'raw provider credential synthetic-google-secret'}})
    mock_transport(monkeypatch,handler)
    with pytest.raises(llm.ProviderError) as error:
        llm.generate(ReportNarrative,'task',{},'gemini-3.5-flash-lite','gemini')
    assert 'synthetic-google-secret' not in str(error.value)
    assert len(calls)==1
    if status==429: assert 'quota or rate limit' in str(error.value)


@pytest.mark.parametrize('body', [
    {'promptFeedback':{'blockReason':'SAFETY'}},
    {'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{}'}]}}]},
    {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"summary":"missing required fields"}'}]}}]},
])
def test_gemini_rejects_blocked_incomplete_or_invalid_outputs(monkeypatch,body):
    mock_transport(monkeypatch,lambda _:httpx.Response(200,json=body))
    with pytest.raises(llm.ProviderError,match='structured response'):
        llm.generate(ReportNarrative,'task',{},'gemini-3.5-flash-lite','gemini')


def test_provider_defaults_migrate_existing_preferences_without_leaking_keys(client,monkeypatch):
    monkeypatch.setattr(settings,'llm_provider','gemini')
    monkeypatch.setattr(settings,'gemini_api_key','synthetic-google-secret')
    with SessionLocal() as db:
        db.add(AppPreference(id='default',values={'model':'gpt-4.1-mini','retrieval_limit':3}))
        db.commit()
    response=client.get('/api/settings')
    assert response.json()['provider']=='gemini'
    assert response.json()['model']==settings.gemini_model
    assert response.json()['retrieval_limit']==3
    assert response.json()['live_available'] is True
    assert 'synthetic-google-secret' not in response.text
    assert client.put('/api/settings',json={'provider':'gemini','model':'gpt-4.1-mini'}).status_code==422
    assert client.put('/api/settings',json={'provider':'openai','model':'gpt-4.1-mini'}).status_code==200
    assert client.get('/api/settings').json()['live_available'] is False


def test_gemini_workflow_uses_snapshotted_provider(client,monkeypatch):
    monkeypatch.setattr(settings,'gemini_api_key','synthetic-google-secret')
    assert client.put('/api/settings',json={'provider':'gemini','model':'gemini-3.5-flash-lite'}).status_code==200
    providers=[]
    def fail(schema,task,payload,model,provider):
        providers.append(provider)
        raise llm.ProviderError('Gemini quota or rate limit reached.')
    monkeypatch.setattr(llm,'generate',fail)
    _,data=investigate(client,mode='live',selected_files=['checkout.py'])
    assert data['status']=='partial' and set(providers)=={'gemini'}
    assert data['investigation']['config']['provider']=='gemini'
    assert data['investigation']['analysis_results']['evidence']
    assert 'quota or rate limit' in data['executions'][0]['error_details']


def test_missing_gemini_key_blocks_live_submission(client,monkeypatch):
    monkeypatch.setattr(settings,'llm_provider','gemini')
    assert client.get('/api/settings').json()['live_available'] is False
    result=client.post('/api/incidents',json={'title':'Live check','error_log':'Synthetic failure','mode':'live'})
    assert result.status_code==409 and 'GEMINI_API_KEY' in result.text
