"""Explicit denominators; human RCA adjudication is bound to exact predictions."""
import math
from statistics import median
from app.services.security import digest
import json


def prediction_digest(prediction):
    return digest(json.dumps(prediction, sort_keys=True, separators=(',', ':')))


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def percentile95(values):
    return sorted(values)[max(0, math.ceil(len(values) * .95) - 1)] if values else None


def aggregate(rows):
    if len({r['mode'] for r in rows}) > 1 or any(r['mode'] not in ('demo', 'live') for r in rows):
        raise ValueError('Demo, live and mocked results must never be pooled.')
    judgeable = [r for r in rows if r['judgeable']]
    scored = [r for r in judgeable if r['rca_correct'] is not None]
    localizable = [r for r in rows if r['localizable']]
    abstained = [r for r in rows if r['abstained']]
    uncertain = [r for r in rows if r['uncertain']]
    correct_abstentions = sum(r['uncertain'] for r in abstained)
    times = [r['latency_seconds'] for r in rows]
    return {
        'total_cases': len(rows), 'failed_cases': sum(bool(r['errors']) for r in rows),
        'rca_accuracy_scored': ratio(sum(r['rca_correct'] is True for r in scored), len(scored)),
        'rca_scoring_coverage': ratio(len(scored), len(judgeable)),
        'unscored_judgeable_cases': len(judgeable) - len(scored),
        'top1_retrieved_file': ratio(sum(r['top1'] for r in localizable), len(localizable)),
        'top3_retrieved_file': ratio(sum(r['top3'] for r in localizable), len(localizable)),
        'citation_reference_validity': ratio(sum(r['valid_citations'] for r in rows), sum(r['citation_count'] for r in rows)),
        'exact_citation_validity': ratio(sum(r.get('exact_citations', 0) for r in rows), sum(r.get('structured_citation_count', 0) for r in rows)),
        'patch_apply_rate': ratio(sum(r['patch_applied'] is True for r in rows), sum(r['patch_applied'] is not None for r in rows)),
        'verified_repair_rate': ratio(sum(r['repair_eligible'] and r['outcome'] == 'VERIFIED' for r in rows), sum(r['repair_eligible'] for r in rows)),
        'abstention_precision': ratio(correct_abstentions, len(abstained)),
        'abstention_recall': ratio(correct_abstentions, len(uncertain)),
        'validation_phase_coverage': ratio(sum(r['tests_executed'] for r in rows), sum(r['tests_required'] for r in rows)),
        'latency_seconds': {'median': median(times) if times else None, 'p95': percentile95(times)},
        'api_cost': {'mean': 0 if rows and all(r['mode'] == 'demo' for r in rows) else None,
                     'p95': 0 if rows and all(r['mode'] == 'demo' for r in rows) else None,
                     'currency': 'USD', 'usage': 'no provider calls' if rows and rows[0]['mode'] == 'demo' else 'not instrumented'},
        'limits': ['Reference validity checks IDs, paths and ranges, not semantic claim support.',
                   'Free-text RCA requires reviewed adjudication; failures and abstentions on judgeable cases count as incorrect.',
                   'Localization ranks collected source evidence; it is not a ranked model diagnosis.',
                   'Reference fixture checks are excluded from predicted repair metrics.'],
    }
