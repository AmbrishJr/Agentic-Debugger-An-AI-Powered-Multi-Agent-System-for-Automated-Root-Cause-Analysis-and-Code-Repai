from app.services.sample import SAMPLE_LOG, BUGGY, FIXED
from app.services.security import read_source
from app.core.config import settings
from app.agents import workflow


def create(client, **overrides):
    response = client.post('/api/incidents', json={'title': 'Checkout fails on zero discount', 'error_log': SAMPLE_LOG, **overrides})
    assert response.status_code == 201, response.text
    return response.json()['id']


def investigate(client, **overrides):
    incident_id = create(client, **overrides)
    assert client.post(f'/api/incidents/{incident_id}/investigate', json={}).status_code == 202
    return incident_id, client.get(f'/api/incidents/{incident_id}').json()


def test_end_to_end_demo_approval_and_report(client):
    incident_id, data = investigate(client)
    assert data['status'] == 'awaiting_review'
    assert [x['agent_name'] for x in data['executions']] == workflow.AGENTS
    assert all(x['execution_status'] == 'completed' for x in data['executions'])
    fix = data['fix']
    assert fix['original_code'] == BUGGY
    assert fix['proposed_code'] == FIXED
    assert fix['validation_result']['status'] == 'passed'
    assert fix['validation_result']['fixture']['before']['exit_code'] != 0
    assert fix['validation_result']['fixture']['after']['exit_code'] == 0
    assert 'Ran 4 tests' in fix['validation_result']['fixture']['after']['output']
    assert '--- a/checkout.py' in fix['proposed_patch']
    report = client.get(f'/api/incidents/{incident_id}/report').json()
    assert report['triage']['exception'] == 'ZeroDivisionError'
    assert report['evidence'][1]['path'] == 'checkout.py'
    assert report['evidence'][1]['line_start'] == 1
    assert client.post(f'/api/incidents/{incident_id}/approve', json={'note': 'Reviewed regression checks'}).status_code == 200
    saved = client.get(f'/api/incidents/{incident_id}').json()
    assert saved['fix']['approval_status'] == 'approved'
    assert saved['fix']['decision_note'] == 'Reviewed regression checks'
    assert saved['fix']['decided_at']
    assert client.get(f'/api/incidents/{incident_id}/report').json()['approval_status'] == 'approved'
    assert read_source('sample', 'checkout.py') == BUGGY
    stats = client.get('/api/dashboard/stats').json()
    assert stats['total'] == stats['approved'] == stats['demo_count'] == 1
    assert stats['resolved'] == stats['pending_approvals'] == 0


def test_rejection_is_persistent_and_decision_is_immutable(client):
    incident_id, _ = investigate(client)
    assert client.post(f'/api/incidents/{incident_id}/reject', json={'note': 'Need more coverage'}).status_code == 200
    assert client.get(f'/api/incidents/{incident_id}').json()['status'] == 'rejected'
    assert client.post(f'/api/incidents/{incident_id}/approve', json={}).status_code == 409
    assert client.post(f'/api/incidents/{incident_id}/investigate', json={}).status_code == 409


def test_history_filters_retrieval_and_no_self_match(client):
    first, _ = investigate(client)
    second, data = investigate(client, title='Second checkout failure')
    matches = data['investigation']['analysis_results']['memory']
    assert [m['incident_id'] for m in matches] == [first]
    assert second not in [m['incident_id'] for m in matches]
    assert 'not deployed' not in matches[0]['resolution_summary'] or 'Proposed' in matches[0]['resolution_summary']
    assert client.get('/api/incidents?q=Second&severity=high&status=awaiting_review').json()['total'] == 1
    assert client.get('/api/incidents?offset=1&limit=1').json()['items'][0]['id'] == first
    assert client.get('/api/incidents?q=%').json()['total'] == 0
    client.post(f'/api/incidents/{first}/reject', json={})
    _, third = investigate(client)
    matched = next(x for x in third['investigation']['analysis_results']['memory'] if x['incident_id'] == first)
    assert 'Human rejected; not deployed.' in matched['resolution_summary']


def test_unknown_demo_is_honest_and_has_no_patch(client):
    incident_id, data = investigate(client, error_log='TypeError: unknown application failure')
    assert data['status'] == 'needs_evidence'
    assert data['fix'] is None
    assert data['investigation']['analysis_results']['validation']['status'] == 'skipped'
    assert client.get(f'/api/incidents/{incident_id}/patch').status_code == 404
    assert client.post(f'/api/incidents/{incident_id}/approve', json={}).status_code == 404


def test_sse_terminal_snapshot_and_agent_outputs(client):
    incident_id, _ = investigate(client)
    response = client.get(f'/api/incidents/{incident_id}/events')
    assert response.headers['content-type'].startswith('text/event-stream')
    assert 'event: progress' in response.text
    assert 'event: complete' in response.text
    assert 'awaiting_review' in response.text


def test_no_key_live_fails_without_demo_fallback(client):
    response = client.post('/api/incidents', json={'title': 'Live incident', 'error_log': SAMPLE_LOG, 'mode': 'live'})
    assert response.status_code == 409


def test_live_provider_failure_preserves_partial_evidence(client, monkeypatch):
    monkeypatch.setattr(settings, 'openai_api_key', 'test-only-not-a-real-key')
    def failure(*args, **kwargs):
        raise RuntimeError('Sensitive provider error sk-do-not-log-this-secret')
    monkeypatch.setattr(workflow.llm, 'generate', failure)
    incident_id, data = investigate(client, mode='live', selected_files=['checkout.py'])
    assert data['status'] == 'partial'
    assert any(e['execution_status'] == 'failed' for e in data['executions'])
    assert data['investigation']['analysis_results']['evidence']
    assert data['fix'] is None
    assert 'do-not-log' not in str(data)


def test_live_workflow_uses_structured_provider_and_skips_host_execution(client, monkeypatch):
    monkeypatch.setattr(settings, 'openai_api_key', 'test-only-not-a-real-key')
    calls = []
    def structured(schema, task, payload, model, provider='openai'):
        calls.append(schema.__name__)
        outputs = {
            'Triage': {'exception': 'ZeroDivisionError', 'severity': 'high', 'service': 'checkout', 'message': 'division by zero', 'timestamps': [], 'frames': []},
            'Analysis': {'observed_facts': ['E1 reports division by zero.'], 'hypotheses': [{'title': 'Zero divisor', 'explanation': 'E2 divides by discount.', 'confidence': 'high', 'evidence_ids': ['E1','E2'], 'uncertainty': 'No production replay.'}], 'summary': 'Division by zero at checkout.'},
            'FixSuggestion': {'path': 'checkout.py', 'proposed_code': FIXED, 'explanation': 'Apply percentage discount.', 'risks': ['Behavior changes.']},
            'ReportNarrative': {'summary': 'Review the checkout fix.', 'risk_assessment': 'Behavior not tested in live mode.', 'next_steps': ['Run CI.']},
        }
        if schema.__name__ == 'Analysis':
            from app.services.grounding import reference
            log, source = payload['evidence'][:2]
            refs = [reference(log, 5, 5), reference(source, 3, 3)]
            outputs['Analysis'].update(disposition='supported', observations=[{'statement': 'Division by zero is logged.', 'citations': [refs[0]]}])
            outputs['Analysis']['hypotheses'][0]['supporting_evidence'] = refs
        return schema.model_validate(outputs[schema.__name__]).model_dump()
    monkeypatch.setattr(workflow.llm, 'generate', structured)
    _, data = investigate(client, mode='live')
    assert calls == ['Triage', 'Analysis', 'FixSuggestion', 'ReportNarrative']
    assert data['status'] == 'awaiting_review'
    assert data['fix']['validation_result']['status'] == 'partial'
    assert data['fix']['validation_result']['fixture'] == {}
    assert any(c['status'] == 'skipped' for c in data['fix']['validation_result']['checks'])


def test_fabricated_evidence_ids_are_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, 'openai_api_key', 'test-only-not-a-real-key')
    def fabricate(schema, *args):
        if schema.__name__ == 'Triage':
            return {'exception':'ZeroDivisionError','severity':'high','service':'checkout','message':'zero','timestamps':[],'frames':[]}
        return {'summary':'Invented root cause','observed_facts':[], 'hypotheses':[{'title':'Invented','explanation':'No evidence','confidence':'high','evidence_ids':['FAKE'],'uncertainty':''}]}
    monkeypatch.setattr(workflow.llm, 'generate', fabricate)
    _, data = investigate(client, mode='live')
    assert data['status'] == 'partial'
    assert data['fix'] is None
    assert next(e for e in data['executions'] if e['agent_name'] == 'analysis')['execution_status'] == 'failed'


def test_settings_persist_and_do_not_expose_credentials(client, monkeypatch):
    monkeypatch.setattr(settings, 'openai_api_key', 'test-only-sensitive')
    response = client.put('/api/settings', json={'model':'gpt-4.1-mini','retrieval_limit':3,'max_evidence_files':4,'default_mode':'live'})
    assert response.status_code == 200
    assert client.get('/api/settings').json()['retrieval_limit'] == 3
    assert 'test-only-sensitive' not in response.text
    assert 'openai_api_key' not in response.json()


def test_pr_requires_review_and_separate_explicit_authorization(client):
    incident_id, _ = investigate(client)
    assert client.post(f'/api/incidents/{incident_id}/pull-request', json={}).status_code == 422
    assert client.post(f'/api/incidents/{incident_id}/pull-request', json={'authorized':True}).status_code == 409
    client.post(f'/api/incidents/{incident_id}/approve', json={})
    assert client.post(f'/api/incidents/{incident_id}/pull-request', json={'authorized':True}).status_code == 409
