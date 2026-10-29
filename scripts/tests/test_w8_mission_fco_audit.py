"""w8_mission_fco_audit 的关键错误案例（只读审核器）。"""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'mfc_audit', Path(__file__).parents[1] / 'w8_mission_fco_audit.py')
audit_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_mod)


def _mission():
    return {
        'episode_id': 7,
        'episode_available': True,
        't0_seen': True,
        't0_verified': True,
        't0_s': 0.0,
        'terminal_seen': True,
        'terminal_within_budget': True,
        'terminal_s': 10.0,
        'known_preterminal_s': 10.0,
        'missing_preterminal_s': 0.0,
        'post_terminal_budget_s': 50.0,
        'fco_exposure_s': 10.0,
        'mission_fco_fraction': 10.0 / 60.0,
        'identification_lower': 10.0 / 60.0,
        'identification_upper': 10.0 / 60.0,
        'point_valid': True,
        'bounds_valid': True,
    }


def _ledger_mission():
    rec = _mission()
    rec['intervals'] = [
        {'start_s': 0.0, 'end_s': 10.0, 'fco': True, 'kind': 'known', 'reason': 'fco'},
        {'start_s': 10.0, 'end_s': 60.0, 'fco': False, 'kind': 'post_terminal',
         'reason': 'mission_terminal'},
    ]
    return rec


def _summary(mission=None):
    return {
        'visibility_metrics': {'definition_version': 'window_fixed_v1'},
        'episode_window_metrics': {'window_count': 1},
        'mission_fco_fixed_budget_v1': {
            'definition_version': 'mission_fco_fixed_budget_v1',
            'budget_s': 60.0,
            'mission_count': 1,
            'missions': [mission or _mission()],
        },
    }


def _ledger(mission=None):
    return {
        'definition_version': 'mission_fco_fixed_budget_v1',
        'budget_s': 60.0,
        'missions': [mission or _ledger_mission()],
    }


def _fail_names(summary, ledger):
    result = audit_mod.audit(summary, ledger)
    return {c['check'] for c in result.failures()}


def test_valid_ledger_passes():
    assert _fail_names(_summary(), _ledger()) == set()


def test_coverage_mismatch_fails():
    m = _mission()
    m['known_preterminal_s'] = 9.0
    m['post_terminal_budget_s'] = 50.0
    m['fco_exposure_s'] = 9.0
    m['mission_fco_fraction'] = 9.0 / 60.0
    m['identification_lower'] = 9.0 / 60.0
    m['identification_upper'] = 9.0 / 60.0
    rec = _ledger_mission()
    rec.update({k: m[k] for k in (
        'known_preterminal_s', 'post_terminal_budget_s', 'fco_exposure_s',
        'mission_fco_fraction', 'identification_lower', 'identification_upper')})
    rec['intervals'][0]['end_s'] = 9.0
    rec['intervals'][1]['start_s'] = 9.0
    failures = _fail_names(_summary(m), _ledger(rec))
    assert 'mission[0].coverage' in failures


def test_point_valid_with_missing_fails():
    m = _mission()
    m['missing_preterminal_s'] = 1.0
    m['known_preterminal_s'] = 9.0
    m['fco_exposure_s'] = 9.0
    m['identification_upper'] = 10.0 / 60.0
    rec = _ledger_mission()
    rec.update({k: m[k] for k in (
        'known_preterminal_s', 'missing_preterminal_s', 'fco_exposure_s',
        'identification_upper')})
    rec['intervals'] = [
        {'start_s': 0.0, 'end_s': 9.0, 'fco': True, 'kind': 'known', 'reason': 'fco'},
        {'start_s': 9.0, 'end_s': 10.0, 'fco': False, 'kind': 'missing', 'reason': 'gap'},
        {'start_s': 10.0, 'end_s': 60.0, 'fco': False, 'kind': 'post_terminal',
         'reason': 'mission_terminal'},
    ]
    failures = _fail_names(_summary(m), _ledger(rec))
    assert 'mission[0].point_has_no_missing' in failures


def test_non_contiguous_intervals_fail():
    rec = _ledger_mission()
    rec['intervals'][1]['start_s'] = 10.5
    failures = _fail_names(_summary(), _ledger(rec))
    assert 'mission[0].intervals_contiguous' in failures


def test_missing_ledger_fails():
    failures = _fail_names(_summary(), None)
    assert 'ledger_version' in failures
    assert 'ledger_missions_match' in failures


def test_cli_writes_report(tmp_path):
    run = tmp_path / 'run' / 'metrics'
    run.mkdir(parents=True)
    (run / 'summary.json').write_text(json.dumps(_summary()))
    (run / 'mission_fco_intervals.json').write_text(json.dumps(_ledger()))
    import subprocess, sys
    out = tmp_path / 'audit.json'
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / 'w8_mission_fco_audit.py'),
         '--run-dir', str(run.parent), '--out', str(out)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(out.read_text())
    assert result['ok'] is True
