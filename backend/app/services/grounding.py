"""Validate quotations/provenance, not the semantic truth of model reasoning."""
from app.schemas.contracts import Analysis, Citation
from app.services.security import digest


class CitationError(ValueError):
    pass


def reference(evidence, first, last):
    lines = evidence['content'].splitlines()
    offset = evidence['line_start']
    return {k: evidence[k] for k in ('kind', 'path', 'sha256', 'snapshot_id', 'commit_sha')} | {
        'evidence_id': evidence['id'], 'line_start': first, 'line_end': last,
        'quote': '\n'.join(lines[first-offset:last-offset+1])}


def validate_citation(citation, evidence):
    c = Citation.model_validate(citation).model_dump()
    e = evidence.get(c['evidence_id'])
    if not e or any(c[k] != e.get(k) for k in ('kind', 'path', 'sha256', 'snapshot_id', 'commit_sha')):
        raise CitationError('Citation identity, file hash or revision does not match collected evidence.')
    if digest(e['content']) != e.get('content_sha256'):
        raise CitationError('Stored evidence content failed its integrity check.')
    if not (e['line_start'] <= c['line_start'] <= c['line_end'] <= e['line_end']) or c['line_end'] - c['line_start'] >= 50:
        raise CitationError('Citation line range is outside the collected evidence or exceeds 50 lines.')
    expected = reference(e, c['line_start'], c['line_end'])['quote']
    if c['quote'] != expected:
        raise CitationError('Citation quotation does not match the exact collected lines.')
    return c


def ground_analysis(result, items):
    result = Analysis.model_validate(result).model_dump()
    evidence = {e['id']: e for e in items}
    if len(evidence) != len(items):
        raise CitationError('Evidence identifiers are not unique.')
    for observation in result['observations']:
        observation['citations'] = [validate_citation(c, evidence) for c in observation['citations']]
    # Never present uncited legacy/model free-text facts as validated observations.
    result['observed_facts'] = [o['statement'] for o in result['observations']]
    for hypothesis in result['hypotheses']:
        if not set(hypothesis['evidence_ids']).issubset(evidence):
            raise CitationError('Model cited evidence IDs that were not collected.')
        for key in ('supporting_evidence', 'contradicting_evidence'):
            hypothesis[key] = [validate_citation(c, evidence) for c in hypothesis[key]]
        hypothesis['evidence_ids'] = list(dict.fromkeys(c['evidence_id'] for key in ('supporting_evidence', 'contradicting_evidence') for c in hypothesis[key]))
        if not hypothesis['supporting_evidence']:
            hypothesis['missing_checks'] = list(dict.fromkeys([*hypothesis['missing_checks'], 'Collect precise supporting evidence.']))
    first = result['hypotheses'][0] if result['hypotheses'] else {}
    supported = (first.get('supporting_evidence') and not first.get('contradicting_evidence')
                 and not first.get('missing_checks') and result['observations'])
    if not supported:
        result['disposition'] = 'insufficient_evidence'
    count = sum(len(o['citations']) for o in result['observations']) + sum(len(h[k]) for h in result['hypotheses'] for k in ('supporting_evidence', 'contradicting_evidence'))
    result['citation_validation'] = {'version': 1, 'status': 'validated' if count else 'no_citations', 'count': count,
        'limitation': ('Exact quotations and provenance are validated; causal interpretations remain hypotheses.' if count
                      else 'No precise citations were supplied; the diagnosis is not supported.')}
    return result


def permits_patch(analysis):
    if analysis.get('disposition') != 'supported' or analysis.get('citation_validation', {}).get('version') != 1:
        return False
    first = (analysis.get('hypotheses') or [{}])[0]
    return (not first.get('contradicting_evidence') and not first.get('missing_checks')
            and {c['kind'] for c in first.get('supporting_evidence', [])} >= {'log', 'source'})
