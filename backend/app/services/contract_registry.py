"""Append-only, two-account contract provenance before any investigation begins."""
import json
from datetime import datetime
from sqlalchemy import select
from app.core.config import settings
from app.models.records import IncidentEvent, Investigation, ProposedFix, User, uid, now
from app.services.security import digest, incident_source, read_source, redact
from app.services.json_contracts import bind_contract, canonical

POLICY = 'two-account-preregistration-v1'
REGISTER = 'verification_contract_registered'
REVIEW = 'verification_contract_reviewed'


def identity(db, actor):
    user = db.get(User, actor['id']) if settings.auth_enabled else None
    if not user or not user.active or user.role not in ('admin', 'editor'):
        raise ValueError('Contract provenance requires an authenticated editor or administrator account.')
    return {'id': user.id, 'username': user.username, 'role': user.role}


def before_investigation(db, incident):
    if (incident.status != 'submitted' or db.scalar(select(Investigation.id).where(Investigation.incident_id == incident.id))
            or db.scalar(select(ProposedFix.id).where(ProposedFix.incident_id == incident.id))):
        raise ValueError('Register and review the contract before investigation starts. Submit a new incident for changes.')


def seal(document):
    return {**document, 'sha256': digest(canonical(document))}


def event_document(row, incident):
    value = json.loads(row.evidence)
    if (value.get('version') != 1 or value.get('id') != row.id or value.get('incident_id') != incident.id
            or value.get('created_at') != row.created_at or value.get('actor', {}).get('username') != row.actor
            or value.get('sha256') != digest(canonical({k:v for k,v in value.items() if k != 'sha256'}))):
        raise ValueError('Contract provenance record failed integrity checks.')
    return value


def records(db, incident):
    result = {}
    for action in (REGISTER, REVIEW):
        rows = db.scalars(select(IncidentEvent).where(IncidentEvent.incident_id == incident.id, IncidentEvent.action == action)).all()
        if len(rows) > 1:
            raise ValueError('Contract provenance has duplicate records.')
        result[action] = event_document(rows[0], incident) if rows else None
    registration, review = result[REGISTER], result[REVIEW]
    if review and (not registration or review['registration_sha256'] != registration['sha256']
                   or review['actor']['id'] == registration['actor']['id']
                   or datetime.fromisoformat(review['created_at']) < datetime.fromisoformat(registration['created_at'])):
        raise ValueError('Contract review does not establish separate-account provenance.')
    if registration and (registration['policy'] != POLICY or registration['snapshot_id'] != incident.repository_snapshot.get('snapshot_id')
                         or registration['log_sha256'] != digest(incident.error_log)):
        raise ValueError('Registered contract does not match the incident provenance.')
    return registration, review


def append(db, incident, action, document, note):
    document = seal(document)
    db.add(IncidentEvent(id=document['id'], incident_id=incident.id, action=action, actor=document['actor']['username'],
        note=note, evidence=canonical(document), created_at=document['created_at']))
    db.flush()
    return document


def register(db, incident, actor, declaration, files):
    author = identity(db, actor)
    before_investigation(db, incident)
    if records(db, incident)[0]:
        raise ValueError('This incident already has an immutable contract. Submit a new incident to change it.')
    if len(set(files)) != len(files):
        raise ValueError('Source paths must be unique.')
    snapshot = {path: read_source(incident_source(incident), path) for path in files}
    if any(not path.endswith('.py') or redact(content) != content for path, content in snapshot.items()) or sum(len(c.encode()) for c in snapshot.values()) > 1024*1024:
        raise ValueError('Select bounded Python sources without secret-like content.')
    bound = bind_contract(declaration, snapshot, incident.repository_snapshot, author['username'], now())
    return append(db, incident, REGISTER, {'version': 1, 'id': uid(), 'incident_id': incident.id,
        'created_at': now(), 'actor': author, 'policy': POLICY, 'snapshot_id': bound['snapshot_id'],
        'log_sha256': digest(incident.error_log), 'source_hashes': bound['source_hashes'], 'declaration': bound['declaration']},
        'JSON contract registered before investigation; answers are excluded from model evidence.')


def review(db, incident, actor, expected_hash, rationale):
    reviewer = identity(db, actor)
    before_investigation(db, incident)
    registration, previous = records(db, incident)
    if not registration or previous or registration['sha256'] != expected_hash:
        raise ValueError('Review requires the exact unreviewed registered contract hash.')
    if reviewer['id'] == registration['actor']['id']:
        raise ValueError('A different authenticated account must review the registered contract.')
    if redact(rationale) != rationale:
        raise ValueError('Remove secret-like content from the review rationale.')
    for path, sha in registration['source_hashes'].items():
        if digest(read_source(incident_source(incident), path)) != sha:
            raise ValueError('Registered source changed; submit a new incident.')
    return append(db, incident, REVIEW, {'version': 1, 'id': uid(), 'incident_id': incident.id, 'created_at': now(),
        'actor': reviewer, 'registration_sha256': registration['sha256'], 'rationale': rationale},
        'Separate account reviewed expected behavior and incident relevance before investigation.')


def lock_for_investigation(db, incident):
    registration, review = records(db, incident)
    if not registration:
        return None
    if not review:
        raise ValueError('A separate account must review the registered contract before investigation starts.')
    for path, sha in registration['source_hashes'].items():
        if digest(read_source(incident_source(incident), path)) != sha:
            raise ValueError('Registered source changed; submit a new incident.')
    return {'policy': POLICY, 'registration_id': registration['id'], 'registration_sha256': registration['sha256'],
            'review_id': review['id'], 'review_sha256': review['sha256'], 'locked_at': now()}


def validate_binding(db, incident, investigation, spec):
    registration, review = records(db, incident)
    binding = investigation.config.get('verification_contract') if investigation else None
    if not registration or not review or not binding or spec.get('provenance') != binding:
        raise ValueError('Registered contract was not frozen before this investigation.')
    expected = {'policy': POLICY, 'registration_id': registration['id'], 'registration_sha256': registration['sha256'],
                'review_id': review['id'], 'review_sha256': review['sha256'], 'locked_at': binding['locked_at']}
    if (binding != expected or datetime.fromisoformat(review['created_at']) > datetime.fromisoformat(binding['locked_at'])
            or spec.get('kind') != 'json-stdio' or spec.get('declaration') != registration['declaration']
            or spec.get('source_hashes') != registration['source_hashes'] or spec.get('snapshot_id') != registration['snapshot_id']):
        raise ValueError('Registered contract binding does not match the immutable declaration and review.')
    return registration


def provenance_valid(db, incident, investigation, run):
    if not run:
        return False
    spec = run.result.get('verification_spec', {})
    if not spec.get('provenance'):
        return False
    try:
        registration = validate_binding(db, incident, investigation, spec)
        return (datetime.fromisoformat(spec['provenance']['locked_at']) <= datetime.fromisoformat(run.created_at)
                and {m['path']: m['sha256'] for m in run.manifest} == registration['source_hashes']
                and len(run.manifest) == len(registration['source_hashes'])
                and all(m.get('role') == 'source' for m in run.manifest))
    except (ValueError, KeyError, TypeError):
        return False
