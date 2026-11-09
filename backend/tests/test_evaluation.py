import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
from app.evaluation.metrics import aggregate, prediction_digest, ratio
from app.evaluation.runner import load_dataset, citations, reference_check

ROOT = Path(__file__).resolve().parents[2]


def row(**overrides):
    return dict({'mode':'demo', 'judgeable':True, 'rca_correct':None, 'localizable':True, 'abstained':False,
        'uncertain':False, 'latency_seconds':1, 'errors':[], 'top1':True, 'top3':True, 'valid_citations':1,
        'citation_count':1, 'patch_applied':None, 'repair_eligible':True, 'outcome':'PATCH_UNVERIFIED',
        'tests_executed':0, 'tests_required':2}, **overrides)


def test_denominators_unscored_and_abstention():
    result = aggregate([row(), row(rca_correct=False, abstained=True),
                        row(judgeable=False, localizable=False, uncertain=True, abstained=True, repair_eligible=False, tests_required=0)])
    assert result['rca_accuracy_scored'] == ratio(0,1)
    assert result['rca_scoring_coverage'] == ratio(1,2)
    assert result['top1_retrieved_file'] == ratio(2,2)
    assert result['verified_repair_rate'] == ratio(0,2)
    assert result['abstention_precision'] == ratio(1,2)
    assert result['abstention_recall'] == ratio(1,1)
    assert result['validation_phase_coverage'] == ratio(0,4)
    assert result['patch_apply_rate']['value'] is None
    assert aggregate([])['latency_seconds']['median'] is None


def test_modes_costs_and_hash_binding():
    assert aggregate([row(mode='live')])['api_cost']['mean'] is None
    assert aggregate([row()])['api_cost']['mean'] == 0
    with pytest.raises(ValueError): aggregate([row(), row(mode='live')])
    with pytest.raises(ValueError): aggregate([row(mode='mock')])
    assert prediction_digest({'a':1,'b':2}) == prediction_digest({'b':2,'a':1})
    assert prediction_digest({'a':1}) != prediction_digest({'a':2})


def test_eight_cases_hidden_inputs_and_executable_tests():
    dataset, oracles = load_dataset(ROOT / 'benchmarks/v1')
    assert len(dataset.cases) == 8
    assert sum(c.split == 'held-out' for c in dataset.cases) == 2
    for case in dataset.cases:
        oracle = oracles[case.id]
        assert not set(case.sources) & set(oracle.tests)
        assert 'cause' not in case.model_dump() and 'reference_patch' not in case.model_dump()
        for source in [*case.sources.values(), *oracle.tests.values(), *oracle.reference_patch.values()]:
            compile(source, '<fixture>', 'exec')  # Parse only; never execute repository code on host.
        assert reference_check(case, oracle, False)['status'] in ('skipped','not_applicable')


def test_invalid_citation_path_range_and_digest():
    from app.services.security import digest
    e = {'id':'E1','kind':'source','path':'a.py','sha256':digest('pass\n'),'line_start':1,'line_end':1}
    p = {'analysis':{'hypotheses':[{'evidence_ids':['E1','fake']}]},'evidence':[e]}
    assert citations(p, {'a.py':'pass\n'}, '') == (1,2)
    e['line_end'] = 2
    assert citations(p, {'a.py':'pass\n'}, '') == (0,2)
    e['line_end'], e['path'] = 1, 'invented.py'
    assert citations(p, {'a.py':'pass\n'}, '') == (0,2)


def test_cli_refuses_live_without_explicit_parameters(tmp_path):
    process = subprocess.run([sys.executable, str(ROOT / 'scripts/evaluate.py'), '--mode','live','--output',str(tmp_path/'result')], capture_output=True, text=True)
    assert process.returncode != 0
    assert 'Live evaluation requires' in process.stderr
    assert not list(tmp_path.iterdir())


def test_offline_cli_real_pipeline_and_no_oracle_leakage(tmp_path):
    target = tmp_path / 'result'
    process = subprocess.run([sys.executable, str(ROOT / 'scripts/evaluate.py'), '--output',str(target)], capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stderr
    result = json.loads(target.with_suffix('.json').read_text())
    assert result['metrics']['total_cases'] == 8
    assert result['metrics']['api_cost']['mean'] == 0
    assert result['application_revision'] and result['application_source_sha256']
    for case in result['cases']:
        assert case['outcome'] != 'VERIFIED'
        assert case['reference_fixture']['status'] in ('skipped', 'not_applicable')
        assert not any(e['path'].startswith('test_') for e in case['prediction']['evidence'])
    assert result['cases'][0]['validation']['fixture']['before']['exit_code'] != 0
    assert result['cases'][0]['validation']['fixture']['after']['exit_code'] == 0
    assert result['cases'][0]['validation_runs'] == []
    assert result['cases'][0]['patch_applied'] is True
    assert result['cases'][0]['rca_correct'] is None
    # Adjudications are rejected if stale, not silently applied to a new prediction.
    decisions = tmp_path/'adjudications.json'
    decisions.write_text(json.dumps([{'case_id':'percentage','prediction_sha256':'0'*64,'correct':True,'reviewer':'reviewer','rationale':'Reviewed independently.'}]))
    process = subprocess.run([sys.executable, str(ROOT/'scripts/evaluate.py'), '--output',str(tmp_path/'stale'), '--adjudications',str(decisions)], capture_output=True, text=True, timeout=60)
    assert process.returncode != 0 and 'does not match prediction' in process.stderr
