"""Runs only through the production pipeline; reference answers never enter it."""
import json
import os
import platform
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid
from app.evaluation.contracts import EvaluationDataset, OracleDataset, Adjudication
from app.evaluation.metrics import aggregate, prediction_digest
from app.services.security import allowed_path, digest


def load_dataset(directory):
    inputs = EvaluationDataset.model_validate_json((directory / 'inputs.json').read_text())
    oracles = OracleDataset.model_validate_json((directory / 'oracles.json').read_text())
    ids = [c.id for c in inputs.cases]
    if len(set(ids)) != len(ids) or len({c.id for c in oracles.cases}) != len(oracles.cases) or set(ids) != {c.id for c in oracles.cases}:
        raise ValueError('Dataset IDs must be unique and match oracle IDs.')
    by_id = {o.id: o for o in oracles.cases}
    for case in inputs.cases:
        oracle = by_id[case.id]
        if set(case.sources) & set(oracle.tests):
            raise ValueError('Independent tests must be separate from investigation sources.')
        frames = re.findall(r'File "([^"]+)"', case.error_log)
        hidden_names = {Path(p).name for p in oracle.tests}
        if any(Path(frame).name in hidden_names for frame in frames):
            raise ValueError('Incident stack frames must not expose independent test files.')
        for path in [*case.sources, *oracle.tests, *oracle.reference_patch]:
            allowed_path(path)
        if not set(case.selected_files).issubset(case.sources) or not set(oracle.reference_patch).issubset(case.sources):
            raise ValueError('Selected and patched paths must exist in case sources.')
    return inputs, by_id


def apply_patch(fix):
    if not fix:
        return None
    from app.services.patches import unified_patch
    changes = fix.get('files') or [fix]
    with tempfile.TemporaryDirectory(prefix='autorca-patch-check-') as temp:
        for f in changes:
            allowed_path(f['path'])
            path = Path(temp, f['path'])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f['original_code'])
        patch = fix['proposed_patch']
        # Also verify the proposed diff describes precisely the saved proposal.
        if patch != ''.join(unified_patch(f['path'], f['original_code'], f['proposed_code']) for f in changes):
            return False
        git = shutil.which('git')
        if not git:
            return None
        result = subprocess.run([git, 'apply', '--whitespace=nowarn', '-'], input=patch, text=True,
                                capture_output=True, cwd=temp, timeout=10, env={'PATH': os.defpath})
        return result.returncode == 0 and all(Path(temp, f['path']).read_text() == f['proposed_code'] for f in changes)


def citations(prediction, source, log):
    evidence = {e['id']: e for e in prediction.get('evidence', [])}
    cited = [key for h in prediction.get('analysis', {}).get('hypotheses', []) for key in h['evidence_ids']]
    valid = 0
    for key in cited:
        e = evidence.get(key)
        if not e:
            continue
        raw = log if e['kind'] == 'log' and e['path'] == 'submitted.log' else source.get(e['path'])
        if raw is not None and e['sha256'] == digest(raw) and 1 <= e['line_start'] <= e['line_end'] <= len(raw.splitlines()):
            valid += 1
    return valid, len(cited)


def reference_check(case, oracle, authorized):
    if not oracle.tests:
        return {'status': 'not_applicable'}
    if not authorized:
        return {'status': 'skipped', 'reason': 'Independent fixture execution requires --authorize-isolated.'}
    from app.services import sandbox
    ready = sandbox.availability()
    if not ready['available']:
        return {'status': 'skipped', 'reason': ready['reason']}
    policy = sandbox.policy('python-unittest')
    original = {**case.sources, **oracle.tests}
    identifier = str(uuid.uuid4())
    before = sandbox.run_snapshot(identifier, 'before', original, policy)
    after = sandbox.run_snapshot(identifier, 'after', {**original, **oracle.reference_patch}, policy) if before['status'] == 'failed' else {'status': 'skipped'}
    return {'status': 'passed' if before['status'] == 'failed' and after['status'] == 'passed' else 'failed',
            'before': before, 'after': after, 'policy': policy,
            'note': 'Reference-patch fixture check; not an agent repair result.'}


def run(args, scratch):
    # Imports happen only after the CLI has installed disposable environment settings.
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.config import settings
    from app.services import sandbox
    from app.services.security import read_source
    dataset, oracles = load_dataset(args.dataset)
    decisions = {}
    if args.adjudications:
        for entry in json.loads(args.adjudications.read_text()):
            d = Adjudication.model_validate(entry)
            if d.case_id in decisions:
                raise ValueError('Duplicate adjudication.')
            decisions[d.case_id] = d
    if set(decisions) - set(oracles):
        raise ValueError('Adjudication names an unknown case.')
    cases = [c for c in dataset.cases if args.split == 'all' or c.split == args.split][:args.max_cases]
    if not cases:
        raise ValueError('No matching evaluation cases.')
    rows = []
    with TestClient(app) as client:
        for case in cases:
            oracle = oracles[case.id]
            source_root = scratch / case.id
            source_root.mkdir()
            for name, content in {**case.sources, **oracle.tests}.items():
                target = source_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            settings.repository_root = str(source_root)
            log = case.error_log or '[No diagnostic logs supplied.]'
            started = time.monotonic()
            response = client.post('/api/incidents', json={'title': case.title, 'error_log': log,
                'repository': case.repository, 'selected_files': case.selected_files, 'mode': args.mode})
            response.raise_for_status()
            identifier = response.json()['id']
            client.post(f'/api/incidents/{identifier}/investigate', json={}).raise_for_status()
            detail = client.get(f'/api/incidents/{identifier}').json()
            validation_execution = {'status': 'skipped', 'reason': 'No isolated execution authorized or no patch available.'}
            if args.authorize_isolated and detail.get('fix'):
                # Tests are content-pinned at intake, but never selected as model evidence.
                paths = list(case.sources)
                if case.repository == 'sample':
                    paths = ['checkout.py', 'test_checkout.py']
                else:
                    paths += list(oracle.tests)
                ready = sandbox.availability()
                if ready['available'] and oracle.tests:
                    planned = client.post(f'/api/incidents/{identifier}/validation-plans', json={'files': paths})
                    if planned.status_code == 201:
                        plan = planned.json()
                        executed = client.post(f'/api/incidents/{identifier}/validation-runs/{plan["id"]}/authorize',
                            json={'authorized': True, 'plan_hash': plan['plan_hash']})
                        executed.raise_for_status()
                        validation_execution = {'status': 'executed', 'run_id': plan['id']}
                    else:
                        validation_execution = {'status': 'rejected', 'reason': planned.json().get('error', {}).get('message', 'Plan rejected')}
                else:
                    validation_execution = {'status': 'skipped', 'reason': ready['reason']}
                detail = client.get(f'/api/incidents/{identifier}').json()
            results = detail['investigation']['analysis_results']
            prediction = {'analysis': results.get('analysis', {}), 'evidence': results.get('evidence', []),
                          'fix': {k: detail['fix'][k] for k in ('files', 'proposed_patch')} if detail.get('fix') else None}
            hashed = prediction_digest(prediction)
            outcome = (detail.get('repair_outcome') or {}).get('status')
            errors = results.get('errors', [])
            abstained = outcome == 'INSUFFICIENT_EVIDENCE' and not errors
            decision = decisions.get(case.id)
            if decision and decision.prediction_sha256 != hashed:
                raise ValueError('Adjudication does not match prediction for ' + case.id)
            correctness = (False if errors or abstained else decision.correct if decision else None) if oracle.cause else None
            sources = dict(case.sources)
            if case.repository == 'sample':
                sources.update({e['path']: read_source('sample', e['path']) for e in prediction['evidence'] if e['kind'] == 'source'})
            valid, count = citations(prediction, sources, log)
            from app.services.grounding import validate_citation
            refs = [c for o in prediction['analysis'].get('observations', []) for c in o['citations']]
            refs += [c for h in prediction['analysis'].get('hypotheses', []) for key in ('supporting_evidence', 'contradicting_evidence') for c in h.get(key, [])]
            exact = 0
            for citation in refs:
                try:
                    validate_citation(citation, {e['id']: e for e in prediction['evidence']})
                    exact += 1
                except ValueError:
                    pass
            ranked = [e['path'] for e in prediction['evidence'] if e['kind'] == 'source']
            fix = detail.get('fix')
            isolated = (fix or {}).get('validation_result', {}).get('isolated', {})
            rows.append({'case_id': case.id, 'split': case.split, 'mode': args.mode,
                'configuration': detail['investigation']['config'], 'environment': case.environment,
                'repository_snapshot': detail.get('repository_snapshot', {}),
                'source_manifest': {path: digest(content) for path, content in sorted(sources.items())},
                'prediction': prediction, 'prediction_sha256': hashed, 'adjudication': decision.model_dump() if decision else None,
                'outcome': outcome, 'repair_outcome': detail.get('repair_outcome'),
                'validation': fix['validation_result'] if fix else results.get('validation', {}),
                'validation_runs': client.get(f'/api/incidents/{identifier}/validation-runs').json()['items'] if fix else [],
                'errors': errors, 'judgeable': oracle.cause is not None,
                'rca_correct': correctness, 'localizable': bool(oracle.files),
                'top1': bool(set(ranked[:1]) & set(oracle.files)), 'top3': bool(set(ranked[:3]) & set(oracle.files)),
                'valid_citations': valid, 'citation_count': count,
                'exact_citations': exact, 'structured_citation_count': len(refs), 'abstained': abstained, 'uncertain': oracle.uncertain,
                'patch_applied': apply_patch(fix),
                'patch_application_exclusion': 'Git executable unavailable' if fix and not shutil.which('git') else None, 'repair_eligible': oracle.repair_eligible,
                'tests_required': 2 if oracle.repair_eligible else 0,
                'tests_executed': sum(isolated.get(p, {}).get('status') in ('passed', 'failed') for p in ('before', 'after')),
                'latency_seconds': round(time.monotonic() - started, 4), 'validation_execution': validation_execution,
                'reference_fixture': reference_check(case, oracle, args.check_fixtures and args.authorize_isolated)})
            print(case.id + ': ' + str(outcome), flush=True)
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True).stdout.strip() or None
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True).stdout
    return {'schema_version': 1, 'runtime': {'python': platform.python_version(), 'system': platform.system()}, 'dataset_sha256': digest((args.dataset / 'inputs.json').read_text() + (args.dataset / 'oracles.json').read_text()),
            'application_revision': revision, 'application_dirty': bool(dirty),
            'application_source_sha256': digest(''.join(str(p.relative_to(Path(__file__).resolve().parents[3])) + p.read_text() for folder in ('backend/app', 'frontend/src') for p in sorted((Path(__file__).resolve().parents[3] / folder).rglob('*')) if p.is_file() and p.suffix in ('.py', '.tsx', '.ts'))),
            'configuration': {'mode': args.mode, 'provider': args.provider if args.mode == 'live' else None,
                              'model': args.model if args.mode == 'live' else None, 'split': args.split,
                              'max_cases': args.max_cases, 'isolated_authorized': args.authorize_isolated},
            'metrics': aggregate(rows), 'cases': rows}


def markdown(result):
    lines = ['# Evaluation results', '', 'Mode: ' + result['configuration']['mode'], '',
             'These results do not measure live-model accuracy unless mode is explicitly live.', '', '| Metric | Result |', '| --- | --- |']
    for name, value in result['metrics'].items():
        if isinstance(value, dict) and 'denominator' in value:
            text = f"{value['numerator']}/{value['denominator']}" if value['denominator'] else 'not available (0 denominator)'
            lines.append(f'| {name} | {text} |')
    lines += ['', '```json', json.dumps({k: v for k, v in result['metrics'].items() if not isinstance(v, dict) or 'denominator' not in v}, indent=2), '```', '',
              '| Case | Outcome | RCA scored |', '| --- | --- | --- |']
    lines += [f"| {r['case_id']} | {r['outcome']} | {r['rca_correct'] if r['rca_correct'] is not None else 'unscored / not applicable'} |" for r in result['cases']]
    return '\n'.join(lines) + '\n'
