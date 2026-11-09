"""Conservative repair conclusions, independent of workflow and human approval."""
from app.services.validation_runs import patch_digest
from app.schemas.contracts import RepairOutcome


def resolve_outcome(incident, investigation, fix, run=None):
    results = investigation.analysis_results if investigation else {}
    validation = fix.validation_result if fix else results.get('validation', {})
    state = validation.get('status')
    run_id = validation.get('isolated_run_id')

    def outcome(status, reason):
        return RepairOutcome(status=status, reasons=[reason], validation_run_id=run_id).model_dump()

    # An earlier successful run must not survive regeneration or an active run.
    if state in ('running', 'regenerate'):
        return outcome('PATCH_UNVERIFIED', 'Validation is running or the proposal is being regenerated.') if fix else None
    isolated = validation.get('isolated', {})
    before, after = isolated.get('before', {}), isolated.get('after', {})
    if (state in ('failed', 'error') or any(c.get('status') in ('failed', 'error') for c in validation.get('checks', []))
            or after.get('status') in ('failed', 'error') or before.get('status') == 'error'
            or any(p.get('timed_out') or p.get('output_limited') or p.get('cleanup_succeeded') is False for p in (before, after))):
        return outcome('VALIDATION_FAILED', 'A required check or execution integrity check failed; inspect the validation evidence.')
    if before.get('status') == 'passed' and before.get('exit_code') == 0:
        return outcome('NOT_REPRODUCED', 'The permitted baseline tests passed before the patch.')
    proof = isolated.get('proof', {})
    if (fix and run and run.id == run_id and run.fix_id == fix.id and run.incident_id == incident.id
            and run.status == 'completed' and run.authorized_at and run.result == isolated
            and run.proposed_sha256 == patch_digest(fix) and state == 'passed'
            and proof.get('version') == 1 and proof.get('scope') == 'bundled-checkout-v1'
            and all(proof.get(k) is True for k in ('integrity', 'independent_tests', 'expected_failure', 'regressions_passed', 'isolated'))):
        return outcome('VERIFIED', 'The pinned bundled fixture reproduced its expected failure and passed immutable independent regressions in isolation. Scope: bundled checkout only.')
    if fix:
        return outcome('PATCH_UNVERIFIED', 'A patch is available, but independent isolated proof of repair is incomplete. Demo results and process exit codes alone do not verify a repair.')
    if (investigation and investigation.agent_status == 'completed' and results.get('analysis')
            and not results.get('errors') and incident.status not in ('failed', 'cancelled', 'investigating', 'submitted')):
        return outcome('INSUFFICIENT_EVIDENCE', 'The completed investigation did not establish a supported code repair; inspect the diagnosis and missing evidence.')
    return None
