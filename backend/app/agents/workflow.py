import json
import re
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.records import Incident, Investigation, AgentExecution, ProposedFix, now
from app.schemas.contracts import Triage, Evidence, Analysis, FixSuggestion, ReportNarrative
from app.services import llm
from app.services.memory import FTSRetriever, HybridRetriever, remember
from app.services.security import read_source, list_files, digest, redact
from app.services.sample import BUGGY, FIXED, SAMPLE_LOG
from app.services.validation import validate
from app.services.patches import unified_patch
from app.services.jobs import checkpoint, JobCancelled

AGENTS = ['triage', 'evidence', 'memory', 'analysis', 'fix', 'validation', 'report']


class WorkflowState(TypedDict, total=False):
    incident_id: str
    investigation_id: str
    job_id: str
    mode: str
    repository: str
    error_log: str
    selected_files: list[str]
    config: dict
    triage: dict
    evidence: list[dict]
    memory: list[dict]
    analysis: dict
    fix: dict
    validation: dict
    report: dict
    errors: list[dict]


def triage(state):
    log = state['error_log']
    frames = [{'path': m[0], 'line': int(m[1]), 'function': m[2]} for m in re.findall(r'File "([^"]+)", line (\d+), in ([\w<>]+)', log)]
    exceptions = re.findall(r'([\w.]+(?:Error|Exception)):\s*([^\n]+)', log)
    exception, message = exceptions[-1] if exceptions else ('Unknown', 'No recognizable exception found')
    result = Triage(exception=exception, severity='high' if exception != 'Unknown' else 'medium',
                    service='checkout.payment' if log == SAMPLE_LOG else 'Unconfirmed', message=message,
                    timestamps=re.findall(r'\d{4}-\d{2}-\d{2}T[\d:.]+Z', log), frames=frames).model_dump()
    if state['mode'] == 'live':
        result = llm.generate(Triage, 'Classify the error, severity, and likely service from the log.', {'log': log}, state['config']['model'])
        # Locations are always parsed from the actual log, never invented by the model.
        result['frames'] = frames
    return result


def evidence(state):
    log = state['error_log']
    items = [Evidence(id='E1', kind='log', path='submitted.log', line_start=1,
                      line_end=len(log.splitlines()), content=log, sha256=digest(log)).model_dump()]
    files = list_files(state['repository'])
    candidates = list(state['selected_files'])
    for frame in state.get('triage', {}).get('frames', []):
        matches = [f for f in files if frame['path'] == f or frame['path'].endswith('/' + f)]
        if not matches:
            matches = [f for f in files if f.rsplit('/', 1)[-1] == frame['path'].rsplit('/', 1)[-1]]
        if len(matches) == 1:
            candidates.append(matches[0])
    if state['repository'] == 'sample':
        candidates.append('README.md')
    for path in list(dict.fromkeys(candidates))[:state['config']['max_evidence_files']]:
        raw = read_source(state['repository'], path)
        content = redact(raw)
        items.append(Evidence(id=f'E{len(items)+1}', kind='source', path=path, line_start=1,
                              line_end=len(raw.splitlines()), content=content, sha256=digest(raw)).model_dump())
    return items


def memory(state):
    with SessionLocal() as db:
        return (HybridRetriever(db) if state['config'].get('retrieval_mode') == 'hybrid' else FTSRetriever(db)).search(state.get('triage', {}).get('exception', '') + ' ' + state['error_log'][:1500],
                                       state['incident_id'], state['config']['retrieval_limit'])


def is_sample(state):
    return (state['repository'] == 'sample' and state['error_log'] == SAMPLE_LOG and
            any(e['path'] == 'checkout.py' and e['sha256'] == digest(BUGGY) for e in state.get('evidence', [])))


def analysis(state):
    if state['mode'] == 'live':
        result = llm.generate(Analysis, 'Rank root cause hypotheses; cite provided evidence IDs and state uncertainty.',
                              {k: state.get(k) for k in ('triage', 'evidence', 'memory')}, state['config']['model'])
    elif is_sample(state):
        ids = [e['id'] for e in state['evidence']]
        result = Analysis(observed_facts=['The submitted log reports ZeroDivisionError with discount=0.',
                                          'checkout.py divides price by discount.',
                                          'The bundled contract specifies a percentage discount, including zero.'],
            hypotheses=[{'title': 'Percentage discount is implemented as division',
                'explanation': 'A zero discount becomes a zero divisor at checkout.py:3. The same formula also produces incorrect prices for nonzero percentages. Calculate the retained percentage of the price and reject values outside the documented range.',
                'confidence': 'high', 'evidence_ids': ids,
                'uncertainty': 'Deterministic bundled example. Production behavior and downstream callers have not been assessed.'}],
            summary='The checkout calculation divides by the discount instead of applying a percentage reduction. A zero-percent discount therefore crashes checkout.').model_dump()
    else:
        result = Analysis(observed_facts=['The submitted log and available source were collected.'],
            hypotheses=[{'title': 'More evidence is required', 'explanation': 'Demo mode only diagnoses the exact bundled checkout scenario. Configure Live AI Mode for other incidents.',
                         'confidence': 'low', 'evidence_ids': ['E1'], 'uncertainty': 'No root cause established.'}],
            summary='No supported deterministic diagnosis for this input.').model_dump()
    known = {e['id'] for e in state.get('evidence', [])}
    for hypothesis in result['hypotheses']:
        if not set(hypothesis['evidence_ids']).issubset(known):
            raise ValueError('Model cited evidence IDs that were not collected.')
    return result


def fix(state):
    with SessionLocal() as db:
        saved = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == state['incident_id']))
        if saved and saved.validation_result.get('status') != 'regenerate':
            return {'available': True, 'id': saved.id, 'path': saved.path, 'proposed_code': saved.proposed_code,
                    'explanation': saved.explanation, 'risks': saved.risks, 'diff': saved.proposed_patch,
                    'original_code': saved.original_code, 'original_sha256': saved.original_sha256, 'files': saved.files}
    if not state.get('analysis') or any(e['agent'] in ('triage', 'evidence', 'analysis') for e in state.get('errors', [])):
        return {'available': False, 'reason': 'Required evidence or analysis is incomplete.'}
    if state['mode'] == 'demo':
        if not is_sample(state):
            return {'available': False, 'reason': 'Demo fixes are limited to the exact bundled sample.'}
        suggestion = FixSuggestion(path='checkout.py', proposed_code=FIXED,
            explanation='Apply the documented percentage contract and guard invalid price and discount ranges.',
            risks=['Changes the incorrect output for all nonzero discounts.', 'Floating-point currency arithmetic is still used; consider Decimal in a separate change.']).model_dump()
    else:
        suggestion = llm.generate(FixSuggestion, 'Propose a minimal fix to at most five collected source files. Return complete updated contents in files. Also set path and proposed_code to the first file for compatibility. Use empty files and an empty path if no safe fix is supported.',
                                  {'analysis': state['analysis'], 'evidence': state.get('evidence', [])}, state['config']['model'])
        if not suggestion['path']:
            return {'available': False, 'reason': suggestion['explanation']}
    files = []
    changes = suggestion.get('files') or [{'path': suggestion['path'], 'proposed_code': suggestion['proposed_code']}]
    if len({c['path'] for c in changes}) != len(changes):
        raise ValueError('Duplicate patch targets are not allowed.')
    for change in changes:
        matching = next((e for e in state.get('evidence', []) if e['kind'] == 'source' and e['path'] == change['path']), None)
        if not matching:
            raise ValueError('Proposed path is not a collected source file.')
        original = read_source(state['repository'], change['path'])
        proposed = change['proposed_code']
        if digest(original) != matching['sha256']:
            raise ValueError('Source changed after evidence collection. Start a new investigation.')
        if redact(original) != original or redact(proposed) != proposed:
            raise ValueError('Secret-like content prevents safe patch generation for this file.')
        if original != proposed:
            files.append({**change, 'original_code': original, 'original_sha256': digest(original),
                          'diff': unified_patch(change['path'], original, proposed)})
    if not files:
        return {'available': False, 'reason': 'No code change proposed.'}
    first = files[0]
    patch = ''.join(f['diff'] for f in files)
    suggestion.update(path=first['path'], proposed_code=first['proposed_code'], files=files)
    with SessionLocal() as db:
        record = db.scalar(select(ProposedFix).where(ProposedFix.incident_id == state['incident_id']))
        if not record:
            record = ProposedFix(incident_id=state['incident_id'])
        for key, value in dict(path=first['path'], original_code=first['original_code'], proposed_code=first['proposed_code'],
            original_sha256=first['original_sha256'], proposed_patch=patch, explanation=suggestion['explanation'],
            risks=suggestion['risks'], files=files, validation_result={}).items():
            setattr(record, key, value)
        db.add(record)
        db.commit()
        return {'available': True, 'id': record.id, **suggestion, 'diff': patch, 'original_code': first['original_code'], 'original_sha256': record.original_sha256}


def validation(state):
    proposed = state.get('fix', {})
    if not proposed.get('available'):
        return {'status': 'skipped', 'checks': [], 'limitations': 'No proposed fix is available.'}
    files = proposed.get('files') or [proposed]
    results = [validate(state['repository'], f['path'], f['original_sha256'], f['proposed_code'], state['mode']) for f in files]
    result = results[0]
    if len(results) > 1:
        result = {**result, 'checks': [{**c, 'detail': f['path'] + ': ' + c['detail']} for f, r in zip(files, results) for c in r['checks']],
                  'status': 'failed' if any(r['status'] == 'failed' for r in results) else ('partial' if any(r['status'] == 'partial' for r in results) else 'passed')}

    with SessionLocal() as db:
        record = db.get(ProposedFix, proposed['id'])
        record.validation_result = result
        db.commit()
    return result


def report(state):
    narrative = {'summary': state.get('analysis', {}).get('summary', 'Investigation incomplete.'),
                 'risk_assessment': 'Review the evidence and behavioral changes. Approval records a decision only; no deployment occurs.',
                 'next_steps': ['Review the proposed change and validation limitations.', 'Approve or reject the fix.', 'Run integration tests in your own isolated CI before merging.']}
    if state['mode'] == 'live' and state.get('analysis'):
        narrative = llm.generate(ReportNarrative, 'Summarize the investigation. Do not claim deployment or tests beyond the supplied validation results.',
                                 {k: state.get(k) for k in ('analysis', 'validation', 'errors')}, state['config']['model'])
    return {**narrative, 'incident_id': state['incident_id'], 'mode': state['mode'],
            'triage': state.get('triage', {}), 'analysis': state.get('analysis', {}),
            'evidence': state.get('evidence', []), 'history': state.get('memory', []),
            'affected_files': [e['path'] for e in state.get('evidence', []) if e['kind'] == 'source'],
            'fix': state.get('fix', {}), 'validation': state.get('validation', {}),
            'errors': state.get('errors', []), 'approval_status': 'pending'}


def tracked(name, function):
    def node(state):
        checkpoint(state.get('job_id'))
        if name in state:
            return {}  # Reuse durable completed steps after restart/retry.
        started = time.monotonic()
        with SessionLocal() as db:
            execution = AgentExecution(investigation_id=state['investigation_id'], agent_name=name)
            db.add(execution)
            db.get(Investigation, state['investigation_id']).agent_status = name
            db.commit()
            execution_id = execution.id
        error = None
        try:
            output = function(state)
            # Also scrub any model-generated explanations before persistence.
            output = json.loads(redact(json.dumps(output)))
            updates = {name: output}
        except Exception as exc:
            # Never store provider errors, prompts, credentials, or raw exception messages.
            error = f'{name.title()} could not complete ({type(exc).__name__}). Check configuration and source availability; partial results are preserved.'
            output = {'error': error}
            updates = {'errors': state.get('errors', []) + [{'agent': name, 'message': error}]}
        with SessionLocal() as db:
            execution = db.get(AgentExecution, execution_id)
            execution.execution_status = 'failed' if error else 'completed'
            execution.error_details = error
            execution.duration = round(time.monotonic() - started, 3)
            execution.output_summary = output if isinstance(output, dict) else {'items': output}
            inv = db.get(Investigation, state['investigation_id'])
            inv.analysis_results = {**inv.analysis_results, **updates}
            if name == 'triage' and not error:
                db.get(Incident, state['incident_id']).severity = output['severity']
            if name == 'evidence' and not error:
                inv.evidence_references = output
            if name == 'analysis' and not error:
                inv.root_cause_summary = output['summary']
            db.commit()
        checkpoint(state.get('job_id'))
        return updates
    return node


builder = StateGraph(WorkflowState)
for name in AGENTS:
    builder.add_node(name + '_agent', tracked(name, globals()[name]))
builder.add_edge(START, AGENTS[0] + '_agent')
for first, second in zip(AGENTS, AGENTS[1:]):
    builder.add_edge(first + '_agent', second + '_agent')
builder.add_edge(AGENTS[-1] + '_agent', END)
graph = builder.compile()


def run_investigation(incident_id: str, job_id: str = ''):
    with SessionLocal() as db:
        incident = db.get(Incident, incident_id)
        inv = db.scalar(select(Investigation).where(Investigation.incident_id == incident_id))
        state = WorkflowState(incident_id=incident_id, investigation_id=inv.id, job_id=job_id, mode=incident.mode,
            repository=incident.repository, error_log=incident.error_log, selected_files=incident.selected_files,
            config=inv.config, errors=[])
        state.update({k: v for k, v in inv.analysis_results.items() if k in AGENTS or k == 'errors'})
    try:
        result = graph.invoke(state)
        with SessionLocal() as db:
            incident, inv = db.get(Incident, incident_id), db.get(Investigation, state['investigation_id'])
            has_fix = result.get('fix', {}).get('available', False)
            incident.status = 'partial' if result.get('errors') else ('awaiting_review' if has_fix else 'needs_evidence')
            incident.updated_at = now()
            inv.agent_status = 'completed'
            inv.analysis_results = {k: v for k, v in result.items() if k in AGENTS or k == 'errors'}
            if result.get('analysis') and not result.get('errors') and has_fix:
                remember(db, incident, result['analysis'], result.get('triage', {}))
            db.commit()
    except JobCancelled:
        raise
    except Exception:
        with SessionLocal() as db:
            incident = db.get(Incident, incident_id)
            incident.status, incident.updated_at = 'failed', now()
            inv = db.get(Investigation, state['investigation_id'])
            inv.agent_status = 'failed'
            inv.analysis_results = {**inv.analysis_results, 'workflow_error': 'Workflow interrupted; persisted agent results remain available.'}
            db.commit()
