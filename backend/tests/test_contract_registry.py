import copy
import json
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.records import User, IncidentEvent, ValidationRun, Investigation
from app.services.auth import password_hash
from app.services.validation_runs import execute_validation
from tests.test_workflow import create
from tests.test_json_contracts import contract, phase
from tests.test_sandbox import ready
from tests.test_repair_outcomes import consistent


def login(client, name):
    response = client.post('/api/auth/login', json={'username':name,'password':'registry-test-password'})
    assert response.status_code == 200, response.text
    client.headers['x-csrf-token'] = response.json()['csrf_token']


@pytest.fixture
def accounts(client, monkeypatch):
    with SessionLocal() as db:
        hashed = password_hash('registry-test-password')
        for name, role in [('author','admin'),('reviewer','editor'),('observer','viewer')]:
            db.add(User(username=name, password_hash=hashed, role=role))
        db.commit()
    monkeypatch.setattr(settings, 'auth_enabled', True)
    login(client, 'author')
    return client


def register(client, identifier, declaration=None):
    return client.post(f'/api/incidents/{identifier}/verification-contract', json={'files':['checkout.py'], 'contract':declaration or contract()})


def review(client, identifier, registration):
    return client.post(f'/api/incidents/{identifier}/verification-contract/review', json={
        'registration_sha256':registration['sha256'],'reviewed':True,'rationale':'Compared the required arithmetic and zero behavior with the incident.'})


def reviewed(client):
    identifier = create(client)
    response = register(client, identifier)
    assert response.status_code == 201, response.text
    registration = response.json()
    login(client, 'reviewer')
    assert review(client, identifier, registration).status_code == 201
    assert client.post(f'/api/incidents/{identifier}/investigate', json={}).status_code == 202
    return identifier, registration


def plan(client, identifier, registration):
    response = client.post(f'/api/incidents/{identifier}/validation-plans',json={'files':['checkout.py'],
        'profile':'python-json-stdio','registered_contract_sha256':registration['sha256']})
    assert response.status_code == 201, response.text
    return response.json()


def authorize(client, identifier, planned):
    return client.post(f'/api/incidents/{identifier}/validation-runs/{planned["id"]}/authorize',
        json={'authorized':True,'plan_hash':planned['plan_hash']})


def test_local_mode_cannot_claim_independent_identity(client):
    identifier = create(client)
    assert register(client, identifier).status_code == 400


def test_registration_requires_two_accounts_and_precedes_investigation(accounts):
    client = accounts
    identifier = create(client)
    registration = register(client, identifier).json()
    assert review(client, identifier, registration).status_code == 400
    assert client.post(f'/api/incidents/{identifier}/investigate',json={}).status_code == 400
    assert client.get(f'/api/incidents/{identifier}').json()['investigation'] is None
    assert register(client, identifier).status_code == 400
    login(client, 'observer')
    assert review(client, identifier, registration).status_code == 403
    login(client, 'reviewer')
    bad = {**registration, 'sha256':'0'*64}
    assert review(client, identifier, bad).status_code == 400
    reviewed_response = review(client, identifier, registration)
    assert reviewed_response.status_code == 201
    assert reviewed_response.json()['actor']['id'] != registration['actor']['id']
    assert review(client, identifier, registration).status_code == 400
    assert client.post(f'/api/incidents/{identifier}/investigate',json={}).status_code == 202
    assert register(client, identifier).status_code == 400
    assert review(client, identifier, registration).status_code == 400


def test_late_registration_and_forged_identity_fields_rejected(accounts):
    identifier = create(accounts)
    body={'files':['checkout.py'],'contract':contract(),'actor':{'id':'someone-else'}}
    assert accounts.post(f'/api/incidents/{identifier}/verification-contract',json=body).status_code == 422
    accounts.post(f'/api/incidents/{identifier}/investigate',json={})
    assert register(accounts, identifier).status_code == 400


def test_answers_never_enter_investigation_inputs(accounts, monkeypatch):
    from app.agents import workflow
    graph = workflow.graph
    class InspectInputs:
        def invoke(self, state):
            assert 'withheld_answer_97413' not in json.dumps(state)
            return graph.invoke(state)
    monkeypatch.setattr(workflow, 'graph', InspectInputs())
    identifier = create(accounts)
    declaration = contract()
    declaration['cases'][0]['expected'] = 'withheld_answer_97413'
    registration = register(accounts, identifier, declaration).json()
    login(accounts, 'reviewer')
    review(accounts, identifier, registration)
    accounts.post(f'/api/incidents/{identifier}/investigate',json={})
    detail = accounts.get(f'/api/incidents/{identifier}').json()
    assert 'withheld_answer_97413' not in json.dumps(detail['investigation'])
    assert 'withheld_answer_97413' not in json.dumps(detail['executions'])
    binding = detail['investigation']['config']['verification_contract']
    assert binding['registration_sha256'] == registration['sha256']


@pytest.mark.parametrize('behavior,expected', [('matched','VERIFIED'),('wrong','VALIDATION_FAILED'),('already_correct','NOT_REPRODUCED'),('malformed','VALIDATION_FAILED')])
def test_registered_contract_outcomes(accounts, ready, monkeypatch, behavior, expected):
    identifier, registration = reviewed(accounts)
    def run(rid, stage, files, policy, invocation=None):
        x = invocation['input']
        value = 0 if x == 0 else 1 if stage == 'before' else 3
        if behavior == 'wrong' and stage == 'after': value = 99
        if behavior == 'already_correct' and x: value = 3
        if behavior == 'malformed': return {**phase(0),'output':'pretend success'}
        return phase(value)
    monkeypatch.setattr('app.services.sandbox.run_snapshot',run)
    planned = plan(accounts, identifier, registration)
    assert authorize(accounts, identifier, planned).status_code == 202
    result = consistent(accounts, identifier, expected)
    if expected == 'VERIFIED':
        assert 'registered contract cases only' in result['reasons'][0]
        assert accounts.post(f'/api/incidents/{identifier}/approve',json={}).status_code == 200
        assert consistent(accounts, identifier, 'VERIFIED') == result


@pytest.mark.parametrize('target,when', [('registration','before'),('review','queued'),('binding','queued'),('registration','during'),('review','after'),('observations','after')])
def test_tampered_provenance_or_observations_never_verify(accounts, ready, monkeypatch, target, when):
    identifier, registration = reviewed(accounts)
    planned = plan(accounts, identifier, registration)
    def tamper():
        with SessionLocal() as db:
            if target in ('registration','review'):
                action = 'verification_contract_registered' if target == 'registration' else 'verification_contract_reviewed'
                event = db.scalar(select(IncidentEvent).where(IncidentEvent.incident_id==identifier, IncidentEvent.action==action))
                value = json.loads(event.evidence)
                value['actor']['id'] = 'forged-account'
                event.evidence = json.dumps(value)
            elif target == 'binding':
                inv = db.scalar(select(Investigation).where(Investigation.incident_id==identifier))
                inv.config = {k:v for k,v in inv.config.items() if k != 'verification_contract'}
            else:
                from app.models.records import ProposedFix
                run = db.get(ValidationRun, planned['id'])
                changed = copy.deepcopy(run.result)
                changed['specification_assessment']['cases'][0]['after']['output'] = '999'
                run.result = changed
                fix = db.get(ProposedFix, run.fix_id)
                fix.validation_result = {**fix.validation_result, 'isolated':changed}
            db.commit()
    def execute(rid, stage, files, policy, invocation=None):
        if when == 'during' and stage == 'after': tamper()
        return phase(0 if invocation['input']==0 else 1 if stage=='before' else 3)
    monkeypatch.setattr('app.services.sandbox.run_snapshot',execute)
    if when == 'before':
        tamper()
        assert authorize(accounts, identifier, planned).status_code == 400
    elif when == 'queued':
        monkeypatch.setattr(settings,'job_execution','external')
        authorize(accounts, identifier, planned)
        tamper()
        monkeypatch.setattr('app.services.sandbox.run_snapshot',lambda *a,**kw: pytest.fail('Tampered provenance must not run'))
        execute_validation(planned['id'])
        consistent(accounts, identifier, 'VALIDATION_FAILED')
    else:
        authorize(accounts, identifier, planned)
        if when == 'after': tamper()
        outcome = accounts.get(f'/api/incidents/{identifier}').json()['repair_outcome']
        assert outcome['status'] != 'VERIFIED'


def test_registered_sources_cannot_be_substituted(accounts,ready):
    identifier, registration = reviewed(accounts)
    response = accounts.post(f'/api/incidents/{identifier}/validation-plans',json={'files':['checkout.py','test_checkout.py'],
        'profile':'python-json-stdio','registered_contract_sha256':registration['sha256']})
    assert response.status_code == 400


def test_registration_and_investigation_start_serialize(accounts):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    identifier = create(accounts)
    barrier = Barrier(2)
    def create_registration():
        barrier.wait()
        return register(accounts, identifier).status_code
    def start():
        barrier.wait()
        return accounts.post(f'/api/incidents/{identifier}/investigate',json={}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(create_registration), pool.submit(start)
        assert (a.result(), b.result()) in ((201,400), (400,202))
