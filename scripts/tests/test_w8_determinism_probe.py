import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('probe', Path(__file__).parents[1] / 'w8_determinism_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize('values,expected', [
    ([0]*5, 'reproducible_at_probe_resolution'),
    ([0, .009, 0, 0, 0], 'reproducible_at_probe_resolution'),
    ([0, .01, 0, 0, 0], 'execution_level_variability_observed'),
    ([0, .27, 0, 0, 0], 'execution_level_variability_observed'),
    ([0, .271, 0, 0, 0], 'beyond_reference_range'),
    ([0]*4, 'incomplete'),
    ([0, float('nan'), 0, 0, 0], 'incomplete'),
])
def test_decision(values, expected):
    assert probe.decision(values) == expected


def test_raw_counts_and_failed_mission(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    summary = tmp_path / 'summary.json'
    summary.write_text(json.dumps({
        'episode_window_metrics': {'vis_ticks_total': 10, 'ticks_total': 99,
                                   'ticks_fire_control_opportunity': 3},
        'episode_windows': [{'enter_s': 5, 'leave_s': 25}],
        'shield_infeasible_rate': 0, 'reset_failure_rate': 0,
    }))
    run = tmp_path / 'run'
    (run / 'metrics').mkdir(parents=True)
    row = {'scene': probe.SCENE, 'arm': 'p1_coop', 'seed': 5, 'backend': 'full',
           'air_tracking_ref': 'on', 'observe_yaw_mode': 'target', 'shield': 'true',
           'infra_retries_used': 0, 'terminal_state': 'MISSION_FAILED',
           'outcome_class': 'mission_terminal', 'summary_path': str(summary)}
    path = run / 'metrics/arms.json'
    path.write_text(json.dumps({'mode': 'headless', 'arms': [row]}))
    result = probe.read_attempt(run)
    assert result['is_mission']
    assert result['active_fco'] == .3
    assert result['window_s'] == 20
    row['seed'] = 6
    path.write_text(json.dumps({'mode': 'headless', 'arms': [row]}))
    with pytest.raises(AssertionError, match='condition mismatch'):
        probe.read_attempt(run)


def test_infra_never_inserts_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    run = tmp_path / 'run'
    (run / 'metrics').mkdir(parents=True)
    row = {'scene': probe.SCENE, 'arm': 'p1_coop', 'seed': 5, 'backend': 'full',
           'air_tracking_ref': 'on', 'observe_yaw_mode': 'target', 'shield': 'true',
           'infra_retries_used': 0, 'terminal_state': 'INFRA_FAILURE',
           'outcome_class': 'infra'}
    (run / 'metrics/arms.json').write_text(json.dumps({'mode': 'headless', 'arms': [row]}))
    result = probe.read_attempt(run)
    assert not result['is_mission']
    assert 'active_fco' not in result
