"""w8_gui_headless_pilot 的口径回归测试（不启仿真、不读 ROS 产物）。

守护：
1. pilot 预声明顺序：P1 从 headless 开始、P2 从 GUI 开始，各 5 次严格交替；
2. attempt 分类与分母：success / MISSION_FAILED(TIMEOUT) / infra 的 mission 分母；
3. 未发生事件：first FCO / capture 记 null + occurrence rate + ITT 敏感性；
4. 汇总：active FCO 的 mean / SD 与各项率；
5. 正式等价：CI 落入 ±δ → equivalent；CI 越界 → not_equivalent；|Δ|>=δ → infeasible；
6. `--dry-run` 只构造命令、不启动子进程、不落盘。

运行：
  python3 -m pytest scripts/tests/test_gui_headless_pilot.py -q
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'research'))

import w8_gui_headless_pilot as w8  # noqa: E402

PLAN = os.path.join(ROOT, w8.DEFAULT_PLAN)


def _record(**kw):
    """合成一条逐 attempt 记录；缺省为 mission 成功。"""
    base = {
        'run_id': 'r', 'scene': 'p1', 'mode': 'gui', 'order': 1,
        'terminal_state': 'INTERCEPT_CONFIRMED', 'reason_code': 'CAPTURE_NET',
        'outcome_class': 'mission',
        'active_fco': None, 'active_visibility': None, 'env_occ_given_visible': None,
        'window_enter_s': None, 'window_leave_s': None, 'window_duration_s': 100.0,
        'first_fco_rel_s': None, 'first_envelope_rel_s': None, 'capture_t_s': None,
        'n_shots': 1, 'first_shot_t_s': None, 'flight_s': None,
        'min_clearance_m': None, 'intervention_segments': None,
        'intervention_duration_s': None, 'intervention_ticks_ratio': None,
        'clearance_min_at_intervention_m': None, 'rtf': None, 'wall_elapsed_s': None,
        'event_identity_rejects': 0, 'lifecycle': None,
        'missing_fields': [], 'notes': [], 'capture_success': 0,
    }
    base.update(kw)
    base['first_fco_occurred'] = base.get('first_fco_rel_s') is not None
    base['first_fco_occurrence'] = int(base['first_fco_occurred'])
    base['capture_occurred'] = base.get('capture_t_s') is not None
    base['capture_success'] = int(base.get('terminal_state') == 'INTERCEPT_CONFIRMED')
    return w8.classify_attempt(base)


# ---------------- 1. pilot 序列 ----------------

def test_pilot_sequence_p1_starts_headless_and_alternates():
    plan, _ = w8.load_plan_doc(ROOT, w8.DEFAULT_PLAN)
    seq = w8.build_mode_sequence(plan, 'p1', 'pilot')
    assert seq == ['headless', 'gui'] * 5
    assert seq.count('headless') == 5 and seq.count('gui') == 5


def test_pilot_sequence_p2_starts_gui_and_alternates():
    plan, _ = w8.load_plan_doc(ROOT, w8.DEFAULT_PLAN)
    seq = w8.build_mode_sequence(plan, 'p2', 'pilot')
    assert seq == ['gui', 'headless'] * 5
    assert seq.count('headless') == 5 and seq.count('gui') == 5


def test_attempt_plan_run_ids_and_commands():
    plan, _ = w8.load_plan_doc(ROOT, w8.DEFAULT_PLAN)
    campaign, items = w8.make_attempt_plan(plan, 'dryrun-check', 'pilot', ['p1', 'p2'])
    assert campaign == 'w8-parity'
    assert len(items) == 20
    p1 = [i for i in items if i['scene'] == 'p1']
    assert [i['mode'] for i in p1] == ['headless', 'gui'] * 5
    assert [i['order'] for i in p1] == list(range(1, 11))
    assert p1[0]['run_id'] == 'dryrun-check-p1-h-01'
    assert p1[1]['run_id'] == 'dryrun-check-p1-g-01'
    assert p1[-1]['run_id'] == 'dryrun-check-p1-g-05'
    cmd = p1[0]['command']
    assert cmd[:3] == ['python3', 'scripts/research/w7b_arms_runner.py', '--campaign']
    for flag, value in (('--mode', 'headless'), ('--arms', 'p1_coop'), ('--seeds', '5'),
                        ('--scene', 's15_static_none_fov_capture'),
                        ('--infra-retries', '0'), ('--obs-horizon-s', '60.0'),
                        ('--timeout', '240.0'), ('--ready-timeout-s', '180.0'),
                        ('--start-timeout-s', '60.0')):
        idx = cmd.index(flag)
        assert cmd[idx + 1] == value
    # 明确不传 worker / PX4 启动参数，让 launch 默认生效
    for flag in ('--worker-id', '--px4-run-root', '--px4-warmup',
                 '--own-px4-delay-s', '--intruder-px4-delay-s'):
        assert flag not in cmd


# ---------------- 2. 分类与分母 ----------------

def test_attempt_classification_and_denominators():
    success = _record(terminal_state='INTERCEPT_CONFIRMED', reason_code='CAPTURE_NET',
                      active_fco=0.10, active_visibility=0.95, first_fco_rel_s=10.0,
                      capture_t_s=20.0)
    timeout = _record(run_id='t', terminal_state='MISSION_FAILED', reason_code='TIMEOUT')
    infra = _record(run_id='i', terminal_state='INFRA_FAILURE',
                    reason_code='cmd_vel_loopback_missing', outcome_class='infra')

    assert success['mission_attempt'] and not success['is_infra']
    assert timeout['is_timeout'] and timeout['mission_attempt']
    assert infra['is_infra'] and not infra['mission_attempt']

    s = w8.summarize_records([success, timeout, infra])
    assert s['n_attempts'] == 3
    assert s['n_mission'] == 2          # infra 不进分母
    assert s['n_infra'] == 1
    assert s['n_timeout'] == 1
    assert s['mission_success_rate'] == pytest.approx(0.5)
    assert s['timeout_rate'] == pytest.approx(0.5)
    assert s['capture_success_rate'] == pytest.approx(0.5)
    assert s['first_fco_occurrence_rate'] == pytest.approx(0.5)


def test_non_occurrence_null_and_itt_sentinel():
    r1 = _record(run_id='a', first_fco_rel_s=None, capture_t_s=None,
                 window_duration_s=100.0)
    r2 = _record(run_id='b', terminal_state='MISSION_FAILED', reason_code='TIMEOUT',
                 first_fco_rel_s=None, capture_t_s=None, window_duration_s=80.0)
    no = w8.build_non_occurrence([r1, r2], obs_horizon_s=60.0)
    assert no['counts']['n_mission'] == 2
    assert no['counts']['first_fco_missing'] == 2
    assert no['counts']['capture_missing'] == 2
    # 主判定字段保持 null，不做插补
    assert r1['first_fco_rel_s'] is None and r1['capture_t_s'] is None
    assert r1['first_fco_occurred'] is False and r1['capture_occurred'] is False
    # ITT 敏感性：first FCO -> 窗口时长；capture -> obs horizon
    assert no['itt_sensitivity']['first_fco_sentinel']['mean'] == pytest.approx(90.0)
    assert no['itt_sensitivity']['capture_t_sentinel']['mean'] == pytest.approx(60.0)
    assert no['itt_sensitivity']['capture_t_sentinel']['n'] == 2


# ---------------- 3. 汇总（mean / SD / 率） ----------------

def test_summary_active_fco_mean_and_stdev():
    gui = [_record(run_id='g1', mode='gui', active_fco=0.10),
           _record(run_id='g2', mode='gui', active_fco=0.30)]
    head = [_record(run_id='h1', mode='headless', active_fco=0.00),
            _record(run_id='h2', mode='headless', active_fco=0.00)]
    s = w8.summarize_records(gui + head)
    st = s['metrics']['active_fco']
    assert st['n'] == 4
    assert st['mean'] == pytest.approx(0.10)
    assert st['min'] == pytest.approx(0.0) and st['max'] == pytest.approx(0.30)
    assert st['stdev'] == pytest.approx(0.141421356, rel=1e-6)
    assert st['iqr'] == pytest.approx(0.15)

    summaries = w8.build_summaries(gui + head)
    assert set(summaries['p1']) == {'gui', 'headless'}
    assert summaries['p1']['gui']['metrics']['active_fco']['mean'] == pytest.approx(0.20)
    assert summaries['p1']['headless']['metrics']['active_fco']['mean'] == pytest.approx(0.0)


def test_mode_differences_is_descriptive_only():
    gui = [_record(run_id='g1', mode='gui', active_fco=0.10),
           _record(run_id='g2', mode='gui', active_fco=0.20)]
    head = [_record(run_id='h1', mode='headless', active_fco=0.05),
            _record(run_id='h2', mode='headless', active_fco=0.15)]
    diff = w8.build_mode_differences(gui + head)['p1']['active_fco']
    assert diff['delta'] == pytest.approx(0.05)
    assert diff['median_difference'] == pytest.approx(0.05)
    assert diff['ci_low'] is not None and diff['ci_high'] is not None


# ---------------- 4. 正式等价判定 ----------------

def test_formal_equivalent_when_ci_inside_delta():
    gui = [0.100, 0.101, 0.099, 0.100]
    head = [0.100, 0.100, 0.099, 0.101]
    d = w8.formal_equivalence_decision(gui, head, 0.05)
    assert d['status'] == 'equivalent'
    assert d['ci_low'] > -0.05 and d['ci_high'] < 0.05
    assert d['p_lower'] < 0.05 and d['p_upper'] < 0.05


def test_formal_not_equivalent_when_ci_outside_delta():
    # Δ=0.04 < δ，但散布大 -> CI 越界
    d = w8.formal_equivalence_decision([0.0, 0.08], [0.0, 0.0], 0.05)
    assert d['status'] == 'not_equivalent'
    assert d['ci_low'] is not None


def test_formal_infeasible_when_delta_exceeds_bound():
    d = w8.formal_equivalence_decision([0.09, 0.11], [0.0, 0.0], 0.05)
    assert d['status'] == 'infeasible'


def test_required_n_formula_and_infeasible():
    n, reason = w8.required_n(0.10, 0.10, 0.05, 0.0)
    expected = __import__('math').ceil(
        (1.959964 + 0.841621) ** 2 * (0.10 ** 2 + 0.10 ** 2) / 0.05 ** 2)
    assert reason is None and n == expected
    assert w8.required_n(0.10, 0.10, 0.05, 0.05)[0] is None
    assert 'infeasible' in w8.required_n(0.10, 0.10, 0.05, 0.06)[1]


def test_formal_gate_fails_on_infra_even_if_co_primary_equivalent():
    co = {'active_fco': {'status': 'equivalent', 'note': ''}}
    status, reasons = w8.decide_formal_gate(
        co, {}, infra_ok=False, hard_ok=True, n_ok=True,
        n_by_mode={'gui': 5, 'headless': 5}, n_per_mode=5)
    assert status == 'failed'
    assert reasons


# ---------------- 5. dry-run 不启动子进程 / 不落盘 ----------------

def test_dry_run_prints_20_attempts_without_subprocess(tmp_path, monkeypatch, capsys):
    def _boom(*_args, **_kwargs):
        raise AssertionError('dry-run 不得启动子进程')

    monkeypatch.setattr(w8.subprocess, 'run', _boom)
    rc = w8.main(['run', '--plan', PLAN, '--pilot-id', 'dryrun-check',
                  '--scene', 'all', '--dry-run', '--repo-root', str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.count('scripts/research/w7b_arms_runner.py') == 20
    assert 'dryrun-check-p1-h-01' in out
    assert 'dryrun-check-p2-g-01' in out
    assert 'dryrun-check-p2-h-05' in out
    assert '合计 20 attempts' in out
    assert not (tmp_path / 'experiments').exists()
