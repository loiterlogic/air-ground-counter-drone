#!/usr/bin/env python3
"""w7b_worker_repeatability —— **只读**的单 worker 重复性 / 时间线诊断（ADR-0024）。

**定位**：本脚本**不**启动新 episode、**不**参与 P1 / P2 判定、**不**改写任何 verdict；
只用既有 run 产物（`metrics/arms.json` + `summary.json` + 逐 episode 日志）回答：

  1. 同 seed 的 active 指标（`active_fco = active_visibility × env_occ|visible`）散布有多大；
  2. 差异落在哪条时间线上：启动状态（PX4 ready / release_control / start OK / active 窗口起点）、
     目标估计（首射 age、intruder `[tw=` 相位、目标拒绝比例）、还是交战几何（首次包络 / 捕获 / 窗口时长）；
  3. A/B/P 预声明门（`src/agc_rl/config/multi_worker_admission.yaml`）在**已有产物**下能评估到哪一步。

**口径**：primary DV 用 active 窗口指标；`arms.json` 的 legacy 固定窗口指标只作描述并标注。
缺失字段 / 缺失 summary / 缺失日志一律记为 `null` 并写进 `missing_fields`，不崩溃。
A/B 或 P 尚未运行时，对应门结果写 `not_evaluated`。

用法：
  python3 scripts/research/w7b_worker_repeatability.py \
    --campaign w7-rl-b \
    --out-run-id 20261025-w7-rl-b-repeat-diagnosis \
    --case c1-01=20261024-w7-rl-b-c1-serial-01 \
    --case c4-w0=20261025-w7-rl-b-c4-trial3:0

`--case` 语法：`LABEL=RUN_ID[:WORKER][#SEED]`；`WORKER` 为 0/1 时读 `worker_<id>/`。
未给 `#SEED` 且该 run 有多个 arm（逐 seed）时，自动展开为 `LABEL-s<seed>`。
产物：`experiments/<campaign>/<out_run_id>/metrics/worker_repeatability.{json,md}`。
"""

import argparse
import glob
import hashlib
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone

ROOT = '/home/chen/AGC'
DEFAULT_PLAN = 'src/agc_rl/config/multi_worker_admission.yaml'
OK_TERMINALS = ('INTERCEPT_CONFIRMED', 'TRACKING_SUCCESS')

# 需要出现在报告 / JSON 的 case 字段（缺失 -> null 并列入 missing_fields）
CASE_FIELDS = [
    'active_fco', 'active_visibility', 'env_occ_given_visible',
    'legacy_fixed_fco', 'legacy_fixed_visibility',
    'window_enter_s', 'window_leave_s', 'window_duration_s',
    'first_fco_rel_s', 'first_envelope_rel_s',
    'n_shots', 'first_shot_t_s', 'capture_t_s', 'flight_s', 'shot_age_s', 'target_age_max_s',
    'px4_ready_wall', 'release_control_wall', 'start_ok_wall', 'release_to_start_wall_s',
    'intruder_offboard_tw_s',
    'rtf', 'sim_start_s', 'sim_end_s', 'duration_s', 'terminal_state', 'infra_retries_used',
]
EVIDENCE_FIELDS = [
    'outcome_class', 'event_identity_rejects', 'shared_writes_detected', 'lifecycle',
]
LIFECYCLE_FIELDS = (
    'n_fired', 'n_unresolved', 'n_duplicated', 'n_negative_flight',
    'n_over_bound', 'n_absurd_miss_dist',
)
EVENT_IDENTITY_MARKER = 'ep != episode_epoch_'
LOG_FIELDS = [
    'px4_ready_wall', 'release_control_wall', 'start_ok_wall', 'release_to_start_wall_s',
    'intruder_offboard_tw_s', 'n_shots', 'first_shot_t_s', 'capture_t_s', 'flight_s',
    'shot_age_s', 'target_age_max_s',
]
STAT_FIELDS = [
    'active_fco', 'active_visibility', 'env_occ_given_visible',
    'legacy_fixed_fco', 'legacy_fixed_visibility',
    'window_enter_s', 'window_leave_s', 'window_duration_s',
    'first_fco_rel_s', 'first_envelope_rel_s', 'fco_span_s',
    'n_shots', 'first_shot_t_s', 'capture_t_s', 'flight_s', 'shot_age_s',
    'target_age_max_s', 'rtf', 'release_to_start_wall_s', 'start_ok_rel_log_s',
    'target_reject_ratio', 'window_enter_rel_start_s',
]

DEFAULT_GATES = {
    'window_pad_s': 5.0,
    'active_visibility_floor': 0.90,
    'active_fco_band': 0.01,
    'infra': 'B 总 infra ≤ A 总 infra（A 基线默认 0）',
    'hard_invariants': 'B 全部通过（终态类别 / 每发唯一终局 / 事件身份 / 无残留）',
    'shared_px4_writable': 'B run 期间共享 build 可写文件 sha256 / 文件数 / mtime 不变',
}
DEFAULT_ATTRIBUTION = {
    'startup_state': 'active 窗口 enter_s 差异 > 5 s，或 release_control / start OK 墙钟差 > 5 s',
    'target_estimation': 'shot age > 0.30 s，或目标拒绝比例差 > 10 pp，或 intruder [tw=] 相位差 > 5 s',
    'physical_scatter': 'active 可见率 ≥ 0.95，且 env_occ 差异可由 first FCO / 捕获时刻 / 窗口时长解释',
    'unexplained': '不符合以上任一类',
}

TS_RE = re.compile(r'\[(\d{10}\.\d+)\]')
SHOT_RE = re.compile(r'SHOT_FIRED shot=(\S+) t=([\d.]+).*?age=([\d.]+)')
CAPTURE_RE = re.compile(r'CAPTURE（发射式网动态命中）.*?shot=(\S+).*?flight=([\d.]+) s')
R041_RE = re.compile(r'R-041：目标有效性 goal_valid=(true|false).*?age=(-?[\d.]+)')
TW_RE = re.compile(r'\[tw=([\d.]+)s\] requesting OFFBOARD')
R013_RE = re.compile(r'R-013 门禁证据.*?now=([\d.]+)')
B1_RE = re.compile(r'B1 诊断')
B1_KEYS = ('gate_ok', 'no_pose', 'behind', 'rmin', 'rmax', 'fov_az', 'fov_el', 'blocked', 'dropped')


# --------------------------------------------------------------------------- 通用

def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def safe_div(a, b):
    if a is None or b in (None, 0):
        return None
    return float(a) / float(b)


def numeric_stats(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {'n': 0, 'min': None, 'max': None, 'median': None}
    return {'n': len(vals), 'min': min(vals), 'max': max(vals),
            'median': statistics.median(vals)}


def resolve_repo_path(path, repo_root):
    """历史产物里 summary_path 是绝对路径；repo-root 不同时按 experiments/ 重锚。"""
    if not path:
        return None
    path = str(path)
    idx = path.find('experiments/')
    if idx >= 0:
        return os.path.join(repo_root, path[idx:])
    return path


def condition_group(label):
    """分组：A/B/P 条件；否则取 label 的第一个 '-' 前 token（C1/C4/P1/P2）。"""
    for cond in ('A', 'B', 'P'):
        if re.fullmatch(cond + r'\d*', label or '', flags=re.IGNORECASE):
            return cond
    return (label or 'UNKNOWN').split('-')[0].upper()


def parse_case_arg(arg):
    """LABEL=RUN_ID[:WORKER][#SEED]"""
    if '=' not in arg:
        raise ValueError('--case 需要 LABEL=RUN_ID[:WORKER][#SEED]：%r' % arg)
    label, right = arg.split('=', 1)
    seed = None
    if '#' in right:
        right, seed_s = right.rsplit('#', 1)
        seed = int(seed_s)
    worker = None
    if ':' in right:
        run_id, maybe_worker = right.rsplit(':', 1)
        if maybe_worker.isdigit():
            run_id, worker = run_id, int(maybe_worker)
        else:
            run_id = right
    else:
        run_id = right
    return label, run_id, worker, seed


# --------------------------------------------------------------------------- 计划

def load_plan(path, repo_root):
    path = path if os.path.isabs(path) else os.path.join(repo_root, path)
    out = {
        'path': path, 'sha256': None, 'loaded': False, 'missing': not os.path.exists(path),
        'gate_defaults': dict(DEFAULT_GATES),
        'attribution_rules': dict(DEFAULT_ATTRIBUTION),
        'raw': {},
        'note': '',
    }
    if not os.path.exists(path):
        out['note'] = '计划文件缺失，使用 spec 默认门值'
        return out
    with open(path, 'rb') as f:
        raw = f.read()
    out['sha256'] = hashlib.sha256(raw).hexdigest()
    try:
        import yaml
        doc = yaml.safe_load(raw.decode('utf-8')) or {}
    except Exception as exc:  # noqa: BLE001 - 只读诊断，计划解析失败不阻塞
        out['note'] = '计划 YAML 解析失败：%r；使用默认门值' % (exc,)
        return out
    plan = doc.get('w7c_admission_plan') or {}
    gates = plan.get('gates') or {}
    a_vs_b = gates.get('a_vs_b') or {}
    p_vs_b = gates.get('p_vs_b') or {}
    attrs = plan.get('attribution_rules') or {}
    gd = out['gate_defaults']

    def first_float(text, default):
        m = re.search(r'(\d+(?:\.\d+)?)', str(text or ''))
        return float(m.group(1)) if m else default

    if a_vs_b.get('active_window_enter'):
        gd['window_pad_s'] = first_float(a_vs_b['active_window_enter'], gd['window_pad_s'])
    if a_vs_b.get('active_visibility_floor') is not None:
        gd['active_visibility_floor'] = _to_float(a_vs_b['active_visibility_floor'])
    if a_vs_b.get('active_fco_band'):
        gd['active_fco_band'] = first_float(a_vs_b['active_fco_band'], gd['active_fco_band'])
    for key in ('infra', 'hard_invariants', 'shared_px4_writable'):
        if a_vs_b.get(key):
            gd[key] = a_vs_b[key]
    for key, default in DEFAULT_ATTRIBUTION.items():
        out['attribution_rules'][key] = attrs.get(key) or default
    out['loaded'] = True
    out['raw'] = {'a_vs_b': a_vs_b, 'p_vs_b': p_vs_b}
    return out


# --------------------------------------------------------------------------- 日志

def find_log(ev_dir, arm, scene, seed):
    log_dir = os.path.join(ev_dir, 'log')
    if not os.path.isdir(log_dir):
        return None
    patterns = []
    if arm and scene and seed is not None:
        patterns.append('ep_%s_%s_%s.log' % (arm, scene, seed))
    if arm and seed is not None:
        patterns.append('ep_%s_*_%s.log' % (arm, seed))
    patterns.append('ep_*.log')
    for pat in patterns:
        hits = sorted(glob.glob(os.path.join(log_dir, pat)))
        if hits:
            return hits[0]
    return None


def parse_log(path):
    """解析既有 episode 日志。PX4 行没有 ROS 时间戳 -> 用最近的时间戳行近似并标 estimated。"""
    out = {
        'log_file': path, 'log_missing': not bool(path),
        'px4_ready_wall': [], 'px4_ready_estimated': [], 'px4_ready_tag': [],
        'release_control_wall': None, 'start_ok_wall': None, 'start_ok_sim_s': None,
        'release_to_start_wall_s': None, 'start_ok_rel_log_s': None,
        'release_control_rel_log_s': None,
        'intruder_offboard_tw_s': [], 'n_shots': 0, 'shot_times_s': [], 'shot_ids': [],
        'first_shot_t_s': None, 'shot_age_s': None, 'capture_t_s': None,
        'capture_shot_id': None, 'flight_s': None, 'capture_wall': None,
        'target_age_max_s': None, 'r041_valid_n': 0, 'r041_invalid_n': 0,
        'target_reject_ratio': None, 'target_reject_ratio_all': None,
        'target_reject_counts': {}, 'target_reject_scope': None,
        'event_identity_rejects': None,
        'px4_blind_land_n': 0, 'px4_invalid_setpoint_n': 0, 'px4_arming_denied_n': 0,
        'px4_blind_land_wall': [], 'first_log_wall': None, 'last_log_wall': None,
    }
    if not path or not os.path.exists(path):
        out['log_missing'] = True
        return out

    out['event_identity_rejects'] = 0
    cur_wall = None
    shots = []
    capture_shot = None
    capture_flight = None
    target_ages_valid = []
    all_ages = []
    reject_after_release = {k: 0 for k in B1_KEYS}
    reject_all = {k: 0 for k in B1_KEYS}
    saw_after_release = False

    with open(path, errors='replace') as fh:
        for line in fh:
            m = TS_RE.search(line)
            has_ts = bool(m)
            if has_ts:
                cur_wall = float(m.group(1))
                if out['first_log_wall'] is None:
                    out['first_log_wall'] = cur_wall
                out['last_log_wall'] = cur_wall

            if 'Ready for takeoff!' in line:
                out['px4_ready_wall'].append(cur_wall)
                out['px4_ready_estimated'].append(not has_ts)
                tag = re.search(r'\[(px4-\d+|[A-Za-z0-9_]+-\d+)\]', line)
                out['px4_ready_tag'].append(tag.group(1) if tag else None)

            if 'release_control：控制权移交' in line and out['release_control_wall'] is None:
                out['release_control_wall'] = cur_wall
            if 'start OK -> AIR_SEARCH' in line and out['start_ok_wall'] is None:
                out['start_ok_wall'] = cur_wall
            if 'R-013 门禁证据' in line and out['start_ok_sim_s'] is None:
                mm = R013_RE.search(line)
                if mm:
                    out['start_ok_sim_s'] = float(mm.group(1))

            mm = TW_RE.search(line)
            if mm:
                out['intruder_offboard_tw_s'].append(float(mm.group(1)))

            mm = SHOT_RE.search(line)
            if mm:
                shots.append({'shot_id': mm.group(1), 't': float(mm.group(2)),
                              'age': float(mm.group(3)), 'wall': cur_wall})
                if out['shot_age_s'] is None:
                    out['shot_age_s'] = float(mm.group(3))
            mm = CAPTURE_RE.search(line)
            if mm:
                capture_shot = mm.group(1)
                capture_flight = float(mm.group(2))
                out['capture_wall'] = cur_wall

            mm = R041_RE.search(line)
            if mm:
                age = float(mm.group(2))
                if mm.group(1) == 'true':
                    out['r041_valid_n'] += 1
                    if age >= 0:
                        target_ages_valid.append(age)
                else:
                    out['r041_invalid_n'] += 1
                if age >= 0:
                    all_ages.append(age)

            if B1_RE.search(line):
                counts = {}
                for key in B1_KEYS:
                    km = re.search(key + r'=(\d+)', line)
                    counts[key] = int(km.group(1)) if km else 0
                for key, val in counts.items():
                    reject_all[key] += val
                    if (out['release_control_wall'] is not None and cur_wall is not None
                            and cur_wall >= out['release_control_wall']
                            and (out['capture_wall'] is None
                                 or cur_wall <= out['capture_wall'])):
                        reject_after_release[key] += val
                        saw_after_release = True

            if 'Failsafe: blind land' in line:
                out['px4_blind_land_n'] += 1
                if cur_wall is not None:
                    out['px4_blind_land_wall'].append(cur_wall)
            if 'invalid setpoints' in line:
                out['px4_invalid_setpoint_n'] += 1
            if 'Arming denied' in line:
                out['px4_arming_denied_n'] += 1
            if EVENT_IDENTITY_MARKER in line:
                out['event_identity_rejects'] += 1

    out['n_shots'] = len(shots)
    out['shot_times_s'] = [s['t'] for s in shots]
    out['shot_ids'] = [s['shot_id'] for s in shots]
    if shots:
        out['first_shot_t_s'] = shots[0]['t']
    if capture_flight is not None:
        out['flight_s'] = capture_flight
        out['capture_shot_id'] = capture_shot
        base_t = None
        for s in shots:
            if s['shot_id'] == capture_shot:
                base_t = s['t']
        if base_t is None and shots:
            base_t = shots[-1]['t']
        if base_t is not None:
            out['capture_t_s'] = round(base_t + capture_flight, 3)

    if target_ages_valid:
        out['target_age_max_s'] = max(target_ages_valid)
    elif all_ages:
        out['target_age_max_s'] = max(all_ages)

    out['target_reject_counts'] = reject_after_release if saw_after_release else reject_all
    out['target_reject_scope'] = ('release_control→capture 墙钟段' if saw_after_release
                                  else '全日志（无 release_control 锚点）')

    def ratio(counts):
        total = sum(counts.values())
        return safe_div(total - counts.get('gate_ok', 0), total)

    out['target_reject_ratio'] = ratio(out['target_reject_counts'])
    out['target_reject_ratio_all'] = ratio(reject_all)

    if out['release_control_wall'] is not None:
        out['release_control_rel_log_s'] = (
            out['release_control_wall'] - out['first_log_wall']
            if out['first_log_wall'] is not None else None)
    if out['start_ok_wall'] is not None:
        out['start_ok_rel_log_s'] = (
            out['start_ok_wall'] - out['first_log_wall']
            if out['first_log_wall'] is not None else None)
    if out['release_control_wall'] is not None and out['start_ok_wall'] is not None:
        out['release_to_start_wall_s'] = out['start_ok_wall'] - out['release_control_wall']
    out['px4_blind_land_wall'] = sorted(out['px4_blind_land_wall'])
    return out


# --------------------------------------------------------------------------- case

def select_arm_row(arms, seed):
    if seed is not None:
        for row in arms:
            if row.get('seed') == seed:
                return row
        return None
    return arms[0] if arms else None


def read_lifecycle(ev_dir):
    """只读该 case 自己的 fire_control_lifecycle.json（worker 不回落 run 根，避免跨 worker 混用）。"""
    path = os.path.join(ev_dir, 'metrics', 'fire_control_lifecycle.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            doc = json.load(f)
    except Exception:  # noqa: BLE001 - 缺失 / 损坏一律按证据不足处理
        return None
    out = {'source_path': path}
    for key in LIFECYCLE_FIELDS + ('n_hit', 'n_miss', 'n_aborted', 'n_logs'):
        out[key] = doc.get(key)
    return out


def read_shared_writes(ev_dir, worker):
    """只对 worker case 读取隔离证据；普通 run 没有该 JSON，返回 null。"""
    if worker is None:
        return None
    path = os.path.join(ev_dir, 'metrics', 'px4_writable_isolation.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            doc = json.load(f)
    except Exception:  # noqa: BLE001
        return None
    writes = doc.get('writes_detected') or {}
    return {
        'source_path': path,
        'any': writes.get('any'),
        'changes': writes.get('changes') or [],
    }


def load_case(repo_root, campaign, label, run_id, worker=None, seed=None):
    run_dir = os.path.join(repo_root, 'experiments', campaign, run_id)
    ev_dir = os.path.join(run_dir, 'worker_%d' % worker) if worker is not None else run_dir
    rec = {
        'label': label, 'run_id': run_id, 'worker': worker, 'campaign': campaign,
        'evidence_dir': ev_dir, 'arm': None, 'seed': seed, 'scene': None,
        'terminal_state': None, 'reason_code': None, 'outcome_class': None,
        'infra_retries_used': None, 'active_window_ticks': None,
        'vis_ticks_total': None, 'vis_ticks_visible': None, 'fco_ticks': None,
        'fco_span_s': None, 'fco_tick_density_hz': None,
        'window_enter_rel_start_s': None,
        'start_ok_sim_s': None, 'px4_blind_land_n': None, 'px4_arming_denied_n': None,
        'target_reject_ratio': None, 'target_reject_ratio_all': None,
        'target_reject_scope': None, 'r041_valid_n': None, 'r041_invalid_n': None,
        'summary_path': None, 'log_file': None, 'episode_id': None,
        'event_identity_rejects': None, 'shared_writes_detected': None,
        'lifecycle': None, 'is_infra': False,
        'missing_fields': [], 'missing_evidence': [], 'notes': [],
    }
    for field in CASE_FIELDS + ['px4_ready_estimated', 'px4_ready_tag', 'shot_times_s',
                                'start_ok_rel_log_s', 'release_control_rel_log_s',
                                'target_reject_counts', 'px4_blind_land_wall']:
        rec.setdefault(field, None)

    arms_path = os.path.join(ev_dir, 'metrics', 'arms.json')
    if not os.path.exists(arms_path):
        rec['notes'].append('arms.json 缺失')
        rec['missing_fields'] = list(CASE_FIELDS)
        rec['missing_evidence'] = list(EVIDENCE_FIELDS)
        return rec
    try:
        with open(arms_path) as f:
            arms_doc = json.load(f)
    except Exception as exc:  # noqa: BLE001
        rec['notes'].append('arms.json 解析失败：%r' % (exc,))
        rec['missing_fields'] = list(CASE_FIELDS)
        rec['missing_evidence'] = list(EVIDENCE_FIELDS)
        return rec
    arms = arms_doc.get('arms') or []
    row = select_arm_row(arms, seed)
    if row is None:
        rec['notes'].append('未找到 seed=%r 的 arm 行' % (seed,))
        rec['missing_fields'] = list(CASE_FIELDS)
        rec['missing_evidence'] = list(EVIDENCE_FIELDS)
        return rec

    rec['arm'] = row.get('arm')
    rec['seed'] = row.get('seed')
    rec['scene'] = row.get('scene')
    rec['terminal_state'] = row.get('terminal_state')
    rec['reason_code'] = row.get('reason_code')
    rec['outcome_class'] = row.get('outcome_class')
    rec['infra_retries_used'] = row.get('infra_retries_used')
    rec['active_window_ticks'] = row.get('active_window_ticks')
    rec['legacy_fixed_fco'] = row.get('fire_control_opportunity_rate')
    rec['legacy_fixed_visibility'] = row.get('visibility_rate')
    rec['rtf'] = row.get('rtf')

    summary_path = resolve_repo_path(row.get('summary_path'), repo_root)
    rec['summary_path'] = summary_path
    if summary_path and not os.path.exists(summary_path):
        local = os.path.join(ev_dir, 'metrics', 'summary.json')
        summary_path = local if os.path.exists(local) else None
        rec['summary_path'] = summary_path
    summary = {}
    if summary_path and os.path.exists(summary_path):
        try:
            with open(summary_path) as f:
                summary = json.load(f)
        except Exception as exc:  # noqa: BLE001
            rec['notes'].append('summary.json 解析失败：%r' % (exc,))
    else:
        rec['notes'].append('summary.json 缺失')

    ew = summary.get('episode_window_metrics') or {}
    windows = summary.get('episode_windows') or []
    win = windows[0] if windows else {}
    rec['episode_id'] = summary.get('episode_id')
    rec['vis_ticks_total'] = ew.get('vis_ticks_total')
    rec['vis_ticks_visible'] = ew.get('vis_ticks_visible')
    rec['fco_ticks'] = ew.get('ticks_fire_control_opportunity')
    rec['active_fco'] = row.get('fire_control_opportunity_rate_active')
    if rec['active_fco'] is None:
        rec['active_fco'] = safe_div(rec['fco_ticks'], rec['vis_ticks_total'])
    rec['active_visibility'] = ew.get('visibility_rate')
    if rec['active_visibility'] is None:
        rec['active_visibility'] = safe_div(rec['vis_ticks_visible'], rec['vis_ticks_total'])
    rec['env_occ_given_visible'] = safe_div(rec['fco_ticks'], rec['vis_ticks_visible'])
    rec['window_enter_s'] = win.get('enter_s')
    rec['window_leave_s'] = win.get('leave_s')
    if rec['window_enter_s'] is not None and rec['window_leave_s'] is not None:
        rec['window_duration_s'] = rec['window_leave_s'] - rec['window_enter_s']
    rec['first_fco_rel_s'] = ew.get('first_fire_control_opportunity_s')
    rec['first_envelope_rel_s'] = ew.get('first_envelope_in_s')
    rec['sim_start_s'] = summary.get('sim_start_s')
    rec['sim_end_s'] = summary.get('sim_end_s')
    rec['duration_s'] = summary.get('duration_s')
    rec['rtf'] = summary.get('rtf') if summary.get('rtf') is not None else rec['rtf']
    if rec['window_enter_s'] is not None and rec['first_fco_rel_s'] is not None \
            and rec['window_leave_s'] is not None:
        rec['fco_span_s'] = max(0.0, rec['window_leave_s']
                                - (rec['window_enter_s'] + rec['first_fco_rel_s']))
    if rec['fco_span_s'] and rec['fco_ticks'] is not None:
        rec['fco_tick_density_hz'] = safe_div(rec['fco_ticks'], rec['fco_span_s'])

    log_path = find_log(ev_dir, rec['arm'], rec['scene'], rec['seed'])
    rec['log_file'] = log_path
    log = parse_log(log_path)
    for key, val in log.items():
        if key not in ('log_file', 'log_missing'):
            rec[key] = val

    if rec.get('window_enter_s') is not None and rec.get('start_ok_sim_s') is not None:
        rec['window_enter_rel_start_s'] = rec['window_enter_s'] - rec['start_ok_sim_s']

    rec['lifecycle'] = read_lifecycle(ev_dir)
    rec['shared_writes_detected'] = read_shared_writes(ev_dir, worker)
    rec['is_infra'] = bool(rec.get('outcome_class') == 'infra'
                           or rec.get('terminal_state') == 'INFRA_FAILURE')

    rec['missing_fields'] = [f for f in CASE_FIELDS if rec.get(f) is None]
    rec['missing_evidence'] = []
    for field in EVIDENCE_FIELDS:
        if field == 'shared_writes_detected':
            # 普通 A case 本就没有隔离 JSON；只有 worker case 才把缺失记为证据不足
            if worker is not None and (rec['shared_writes_detected'] is None
                                       or rec['shared_writes_detected'].get('any') is None):
                rec['missing_evidence'].append(field)
        elif rec.get(field) is None:
            rec['missing_evidence'].append(field)
    if log['log_missing']:
        rec['notes'].append('日志缺失')
    return rec


def expand_case(repo_root, campaign, label, run_id, worker, seed):
    """未显式给 seed 且 arms.json 有多行（逐 seed）时，展开为 LABEL-s<seed>。"""
    if seed is not None:
        return [(label, seed)]
    run_dir = os.path.join(repo_root, 'experiments', campaign, run_id)
    ev_dir = os.path.join(run_dir, 'worker_%d' % worker) if worker is not None else run_dir
    arms_path = os.path.join(ev_dir, 'metrics', 'arms.json')
    if not os.path.exists(arms_path):
        return [(label, None)]
    try:
        with open(arms_path) as f:
            arms = (json.load(f).get('arms') or [])
    except Exception:  # noqa: BLE001
        return [(label, None)]
    if len(arms) <= 1:
        return [(label, arms[0].get('seed') if arms else None)]
    return [('%s-s%s' % (label, row.get('seed')), row.get('seed')) for row in arms]


# --------------------------------------------------------------------------- 分组 / 门 / 归因

def build_groups(cases):
    groups = {}
    for case in cases:
        groups.setdefault(condition_group(case['label']), []).append(case)
    return groups


def group_stats(cases):
    stats = {}
    for field in STAT_FIELDS:
        stats[field] = numeric_stats([c.get(field) for c in cases])
    stats['n'] = len(cases)
    stats['labels'] = [c['label'] for c in cases]
    return stats


def choose_baseline_group(label, groups):
    group = condition_group(label)
    if group == 'B' and groups.get('A'):
        return 'A'
    if group == 'P' and groups.get('B'):
        return 'B'
    if len(groups.get(group) or []) >= 3:
        return group
    if group != 'C1' and len(groups.get('C1') or []) >= 3:
        return 'C1'
    return group


def _delta(value, base):
    if value is None or base is None:
        return None
    return value - base


def _nearest_tw(tw_list, base):
    if not tw_list or base is None:
        return None
    return min(tw_list, key=lambda x: abs(x - base))


def attribute_case(case, base_group, base_stats):
    res = {'baseline_group': base_group, 'category': None, 'comparable': True,
           'deltas': {}, 'flags': [], 'evidence': []}
    deltas = res['deltas']
    deltas['window_enter_s'] = _delta(case.get('window_enter_s'),
                                      base_stats['window_enter_s']['median'])
    deltas['release_to_start_wall_s'] = _delta(
        case.get('release_to_start_wall_s'),
        base_stats['release_to_start_wall_s']['median'])
    deltas['shot_age_s'] = _delta(case.get('shot_age_s'), base_stats['shot_age_s']['median'])
    d_tw = _delta(_nearest_tw(case.get('intruder_offboard_tw_s') or [],
                              base_stats.get('_tw_median')),
                  base_stats.get('_tw_median'))
    deltas['intruder_tw_s'] = d_tw
    d_reject_pp = None
    if case.get('target_reject_ratio') is not None \
            and base_stats['target_reject_ratio']['median'] is not None:
        d_reject_pp = (case['target_reject_ratio']
                       - base_stats['target_reject_ratio']['median']) * 100.0
    deltas['target_reject_pp'] = d_reject_pp
    deltas['active_fco'] = _delta(case.get('active_fco'), base_stats['active_fco']['median'])
    deltas['env_occ_given_visible'] = _delta(
        case.get('env_occ_given_visible'), base_stats['env_occ_given_visible']['median'])
    deltas['first_fco_rel_s'] = _delta(case.get('first_fco_rel_s'),
                                       base_stats['first_fco_rel_s']['median'])
    deltas['capture_t_s'] = _delta(case.get('capture_t_s'),
                                   base_stats['capture_t_s']['median'])
    deltas['window_duration_s'] = _delta(case.get('window_duration_s'),
                                         base_stats['window_duration_s']['median'])

    terminal = case.get('terminal_state')
    if terminal and terminal not in OK_TERMINALS:
        res['comparable'] = False
        res['category'] = 'not_comparable'
        res['evidence'].append('终态 %s 属 mission/infra 结果，不参与数值归因' % terminal)
        return res
    if terminal is None:
        res['comparable'] = False
        res['category'] = 'unknown'
        res['evidence'].append('终态缺失，无法判定是否可比')
        return res

    startup = ((deltas['window_enter_s'] is not None
                and abs(deltas['window_enter_s']) > 5.0)
               or (deltas['release_to_start_wall_s'] is not None
                   and abs(deltas['release_to_start_wall_s']) > 5.0))
    target = ((case.get('shot_age_s') is not None and case['shot_age_s'] > 0.30)
              or (d_tw is not None and abs(d_tw) > 5.0)
              or (d_reject_pp is not None and abs(d_reject_pp) > 10.0))
    if startup:
        res['flags'].append('startup_state')
    if target:
        res['flags'].append('target_estimation')

    vis = case.get('active_visibility')
    material = (abs(deltas['env_occ_given_visible'] or 0) > 0.01
                or abs(deltas['active_fco'] or 0) > 0.01)
    deltas['fco_span_s'] = _delta(case.get('fco_span_s'),
                                  base_stats['fco_span_s']['median'])
    deltas['window_enter_rel_start_s'] = _delta(
        case.get('window_enter_rel_start_s'),
        base_stats['window_enter_rel_start_s']['median'])
    timing_explained = any(
        abs(deltas[k] or 0) > 0.5
        for k in ('first_fco_rel_s', 'capture_t_s', 'window_duration_s', 'fco_span_s'))

    if startup:
        res['category'] = 'startup_state'
        res['evidence'].append(
            'window enter 差 %s s（基线 %s）；release→start 墙钟差 %s s；'
            '窗口相对 start OK 的差 %s s' % (
                fmt(deltas['window_enter_s'], '%.2f'),
                fmt(base_stats['window_enter_s']['median'], '%.2f'),
                fmt(deltas['release_to_start_wall_s'], '%.3f'),
                fmt(deltas['window_enter_rel_start_s'], '%.2f')))
        if case.get('px4_blind_land_n'):
            walls = case.get('px4_blind_land_wall') or []
            rel = case.get('release_control_wall')
            before = [w for w in walls if rel is None or w <= rel]
            after = [w for w in walls if rel is not None and w > rel]
            res['evidence'].append(
                'PX4 own blind-land failsafe 共 %d 次（release 前 %d 次，最后约 %s；'
                'release 后 %d 次；最早约 %s）' % (
                    case['px4_blind_land_n'], len(before),
                    fmt(before[-1] if before else None, '%.2f'), len(after),
                    fmt(walls[0] if walls else None, '%.2f')))
    elif target:
        res['category'] = 'target_estimation'
        res['evidence'].append(
            'shot_age=%s s；Δintruder_tw=%s s；Δ目标拒绝比例=%s pp' % (
                fmt(case.get('shot_age_s'), '%.3f'), fmt(d_tw, '%.2f'),
                fmt(d_reject_pp, '%.1f')))
    elif vis is not None and vis >= 0.95 and (timing_explained or not material):
        res['category'] = 'physical_scatter'
        if timing_explained:
            res['evidence'].append(
                'active_visibility=%s；env_occ=%s（基线 %s）；Δfirst_fco=%s s，'
                'Δcapture=%s s，Δwindow=%s s；fco_span=%s s' % (
                    fmt(vis), fmt(case.get('env_occ_given_visible')),
                    fmt(base_stats['env_occ_given_visible']['median']),
                    fmt(deltas['first_fco_rel_s'], '%.2f'),
                    fmt(deltas['capture_t_s'], '%.2f'),
                    fmt(deltas['window_duration_s'], '%.2f'),
                    fmt(case.get('fco_span_s'), '%.2f')))
        else:
            res['evidence'].append(
                'active_visibility=%s；env_occ 与基线无实质偏离（Δ=%s），属组内散布' % (
                    fmt(vis), fmt(deltas['env_occ_given_visible'], '%.4f')))
    else:
        res['category'] = 'unexplained'
        if vis is None:
            res['evidence'].append('active_visibility 缺失，无法归因')
        elif vis < 0.95:
            res['evidence'].append(
                'active_visibility=%s < 0.95，且无 startup/target 标记' % fmt(vis))
        else:
            res['evidence'].append('env_occ 差异无法由 first FCO / 捕获 / 窗口时长解释')
    return res


def attach_attribution(cases, groups):
    tw_median = {}
    for name, cs in groups.items():
        tws = [tw for c in cs for tw in (c.get('intruder_offboard_tw_s') or [])]
        tw_median[name] = statistics.median(tws) if tws else None
    for case in cases:
        base_group = choose_baseline_group(case['label'], groups)
        base_stats = group_stats(groups[base_group])
        base_stats['_tw_median'] = tw_median.get(base_group)
        case['attribution'] = attribute_case(case, base_group, base_stats)


# --------------------------------------------------------------------------- 门

def _gate_not_evaluated(reason):
    return {
        'status': 'not_evaluated', 'reason': reason, 'complete': False,
        'pass': None, 'evaluable_pass': None,
        'hard_invariants': {'pass': None, 'reason': 'not_evaluated'},
        'shared_px4_writable': {'pass': None, 'reason': 'not_evaluated'},
        'infra': {'pass': None, 'reason': 'not_evaluated'},
        'active_window_enter': {'pass': None},
        'active_visibility_floor': {'pass': None},
        'active_fco_band': {'coarse_shift': None},
    }


def _aggregate(values):
    """True / False / None 三值聚合：显式 fail 优先，其次缺证据，最后 pass。"""
    if any(v is False for v in values):
        return False
    if any(v is None for v in values):
        return None
    return True


def _check_hard_invariants(target_cases, ref_cases):
    """terminal 类别一致 + lifecycle unresolved/duplicated == 0 + 事件身份拒收 == 0。"""
    ref_terms = sorted({c.get('terminal_state') for c in ref_cases
                        if c.get('terminal_state') is not None})
    term_per = {}
    for c in target_cases:
        terminal = c.get('terminal_state')
        term_per[c['label']] = {
            'terminal_state': terminal,
            'outcome_class': c.get('outcome_class'),
            'pass': (None if (terminal is None or not ref_terms)
                     else bool(terminal in ref_terms)),
        }
    term_pass = _aggregate([v['pass'] for v in term_per.values()])

    life_per = {}
    life_missing = []
    for c in target_cases:
        lc = c.get('lifecycle')
        if not lc or lc.get('n_unresolved') is None or lc.get('n_duplicated') is None:
            life_per[c['label']] = {'n_unresolved': (lc or {}).get('n_unresolved'),
                                    'n_duplicated': (lc or {}).get('n_duplicated'),
                                    'pass': None}
            life_missing.append(c['label'])
        else:
            life_per[c['label']] = {
                'n_unresolved': lc.get('n_unresolved'),
                'n_duplicated': lc.get('n_duplicated'),
                'pass': bool(lc['n_unresolved'] == 0 and lc['n_duplicated'] == 0),
            }
    life_pass = _aggregate([v['pass'] for v in life_per.values()])

    event_per = {}
    event_missing = []
    for c in target_cases:
        val = c.get('event_identity_rejects')
        event_per[c['label']] = {'event_identity_rejects': val,
                                 'pass': (None if val is None else bool(val == 0))}
        if val is None:
            event_missing.append(c['label'])
    event_pass = _aggregate([v['pass'] for v in event_per.values()])

    overall = _aggregate([term_pass, life_pass, event_pass])
    return {
        'pass': overall,
        'reference_terminal_states': ref_terms,
        'terminal_state': {'pass': term_pass, 'per_case': term_per},
        'lifecycle': {'pass': life_pass, 'per_case': life_per, 'missing': life_missing},
        'event_identity': {'pass': event_pass, 'per_case': event_per,
                           'missing': event_missing},
        'note': ('lifecycle / event identity 缺失时整体 not_evaluated；'
                 '任一显式 fail 则整体 fail'),
    }


def _check_shared(target_cases):
    """workers 的 shared_writes_detected.any 必须全部为 false。"""
    workers = [c for c in target_cases if c.get('worker') is not None]
    per = {}
    for c in workers:
        sw = c.get('shared_writes_detected')
        if not sw or sw.get('any') is None:
            per[c['label']] = {'any': (sw or {}).get('any'),
                               'changes': (sw or {}).get('changes') or [],
                               'pass': None}
        else:
            per[c['label']] = {'any': bool(sw.get('any')),
                               'changes': sw.get('changes') or [],
                               'pass': not bool(sw.get('any'))}
    if not workers:
        return {'pass': None, 'reason': '没有 worker case（普通 run 无隔离证据）',
                'per_case': {}, 'evaluable': False}
    return {
        'pass': _aggregate([v['pass'] for v in per.values()]),
        'per_case': per,
        'n_workers': len(workers),
        'evaluable': any(v['pass'] is not None for v in per.values()),
    }


def _count_infra(cases):
    """infra 计数只看 outcome_class / INFRA_FAILURE，不用 infra_retries_used。"""
    infra_cases = [c['label'] for c in cases if c.get('is_infra')]
    unclassified = [c['label'] for c in cases
                    if c.get('terminal_state') is None
                    or (c.get('outcome_class') is None
                        and c.get('terminal_state') != 'INFRA_FAILURE')]
    return {'count': len(infra_cases), 'cases': infra_cases,
            'unclassified': unclassified}


def _eval_status(complete, items):
    missing = [name for name, val in items.items() if val is None]
    failed = [name for name, val in items.items() if val is False]
    if complete:
        reason = '全部可评估项均为 pass'
    elif failed:
        reason = '存在 fail：%s；缺证据：%s' % (', '.join(failed),
                                               ', '.join(missing) or '无')
    else:
        reason = '缺证据：%s' % ', '.join(missing)
    evaluable_pass = _aggregate(list(items.values()))
    return {'status': ('evaluated' if complete else 'evaluated_subset'),
            'reason': reason, 'complete': complete,
            'evaluable_pass': evaluable_pass}


def gate_ab(groups, gate_defaults):
    A, B = groups.get('A'), groups.get('B')
    if not A or not B:
        return _gate_not_evaluated('缺少 A 或 B run（本轮只做历史产物诊断）')
    floor = gate_defaults['active_visibility_floor']
    band = gate_defaults['active_fco_band']
    pad = gate_defaults['window_pad_s']
    a_enters = [c['window_enter_s'] for c in A if c.get('window_enter_s') is not None]
    lo, hi = (min(a_enters) - pad, max(a_enters) + pad) if a_enters else (None, None)
    enter_per = {c['label']: {'enter_s': c.get('window_enter_s'),
                              'pass': (None if (c.get('window_enter_s') is None or lo is None)
                                       else bool(lo <= c['window_enter_s'] <= hi))}
                 for c in B}
    vis_per = {c['label']: {'active_visibility': c.get('active_visibility'),
                            'pass': (None if c.get('active_visibility') is None
                                     else bool(c['active_visibility'] >= floor))}
               for c in B}
    enter_pass = (_aggregate([v['pass'] for v in enter_per.values()])
                  if enter_per else None)
    vis_pass = _aggregate([v['pass'] for v in vis_per.values()]) if vis_per else None

    a_fcos = [c['active_fco'] for c in A if c.get('active_fco') is not None]
    b_fcos = [c['active_fco'] for c in B if c.get('active_fco') is not None]
    coarse = None
    if a_fcos and b_fcos:
        coarse = all(v < min(a_fcos) - band for v in b_fcos) or \
                 all(v > max(a_fcos) + band for v in b_fcos)

    hard = _check_hard_invariants(B, A)
    shared = _check_shared(B)
    infra_a = _count_infra(A)
    infra_b = _count_infra(B)
    if infra_a['unclassified'] or infra_b['unclassified']:
        infra_pass = None
        infra_reason = 'outcome_class / terminal 缺失，无法可靠分类 infra：%s' % (
            ', '.join(infra_a['unclassified'] + infra_b['unclassified']))
    else:
        infra_pass = bool(infra_b['count'] <= infra_a['count'])
        infra_reason = 'B_infra ≤ A_infra'

    items = {
        'hard_invariants': hard['pass'],
        'shared_px4_writable': shared['pass'],
        'infra': infra_pass,
        'active_window_enter': enter_pass,
        'active_visibility_floor': vis_pass,
    }
    complete = all(v is not None for v in items.values())
    status = _eval_status(complete, items)
    return {
        'status': status['status'], 'reason': status['reason'],
        'complete': complete, 'pass': status['evaluable_pass'],
        'evaluable_pass': status['evaluable_pass'],
        'evaluable_items': items,
        'hard_invariants': hard,
        'shared_px4_writable': shared,
        'infra': {'A_total': infra_a['count'], 'B_total': infra_b['count'],
                  'A_cases': infra_a['cases'], 'B_cases': infra_b['cases'],
                  'A_unclassified': infra_a['unclassified'],
                  'B_unclassified': infra_b['unclassified'],
                  'pass': infra_pass, 'reason': infra_reason},
        'active_window_enter': {'A_range': [lo, hi], 'pad_s': pad,
                                'per_case': enter_per, 'pass': enter_pass},
        'active_visibility_floor': {'floor': floor, 'per_case': vis_per, 'pass': vis_pass},
        'active_fco_band': {'A_min': (min(a_fcos) if a_fcos else None),
                            'A_max': (max(a_fcos) if a_fcos else None),
                            'band': band,
                            'B_values': {c['label']: c.get('active_fco') for c in B},
                            'coarse_shift': coarse,
                            'note': '只作粗移提示，不作等价门'},
    }


def gate_pb(groups, gate_defaults):
    P, B = groups.get('P'), groups.get('B')
    if not P or not B:
        return _gate_not_evaluated('缺少 P 或 B run（P 为条件性重试，未启动时写 not_evaluated）')
    floor = gate_defaults['active_visibility_floor']
    band = gate_defaults['active_fco_band']
    pad = gate_defaults['window_pad_s']
    b_enters = [c['window_enter_s'] for c in B if c.get('window_enter_s') is not None]
    lo, hi = (min(b_enters) - pad, max(b_enters) + pad) if b_enters else (None, None)
    enter_per = {c['label']: {'enter_s': c.get('window_enter_s'),
                              'pass': (None if (c.get('window_enter_s') is None or lo is None)
                                       else bool(lo <= c['window_enter_s'] <= hi))}
                 for c in P}
    vis_per = {c['label']: {'active_visibility': c.get('active_visibility'),
                            'pass': (None if c.get('active_visibility') is None
                                     else bool(c['active_visibility'] >= floor))}
               for c in P}
    enter_pass = (_aggregate([v['pass'] for v in enter_per.values()])
                  if enter_per else None)
    vis_pass = _aggregate([v['pass'] for v in vis_per.values()]) if vis_per else None

    b_fcos = [c['active_fco'] for c in B if c.get('active_fco') is not None]
    p_fcos = [c['active_fco'] for c in P if c.get('active_fco') is not None]
    coarse = None
    if b_fcos and p_fcos:
        coarse = all(v < min(b_fcos) - band for v in p_fcos) or \
                 all(v > max(b_fcos) + band for v in p_fcos)

    b_ticks = [c['vis_ticks_total'] for c in B if c.get('vis_ticks_total') is not None]
    b_ticks_med = statistics.median(b_ticks) if b_ticks else None
    tick_per = {c['label']: {'vis_ticks_total': c.get('vis_ticks_total'),
                             'pass': (None if (c.get('vis_ticks_total') is None
                                               or b_ticks_med is None)
                                      else bool(c['vis_ticks_total'] >= 0.9 * b_ticks_med))}
                for c in P}
    tick_pass = (_aggregate([v['pass'] for v in tick_per.values()])
                 if tick_per else None)

    hard = _check_hard_invariants(P, B)
    shared = _check_shared(P)
    infra_b = _count_infra(B)
    infra_p = _count_infra(P)
    if infra_b['unclassified'] or infra_p['unclassified']:
        infra_pass = None
        infra_reason = 'outcome_class / terminal 缺失，无法可靠分类 infra：%s' % (
            ', '.join(infra_b['unclassified'] + infra_p['unclassified']))
    else:
        infra_pass = bool(infra_p['count'] <= infra_b['count'])
        infra_reason = 'P_infra ≤ B_infra'

    items = {
        'hard_invariants': hard['pass'],
        'shared_px4_writable': shared['pass'],
        'infra': infra_pass,
        'active_window_enter': enter_pass,
        'active_visibility_floor': vis_pass,
    }
    complete = all(v is not None for v in items.values())
    all_items = dict(items)
    all_items['rtf_and_ticks'] = tick_pass
    status = _eval_status(complete, all_items)
    return {
        'status': status['status'], 'reason': status['reason'],
        'complete': complete, 'pass': status['evaluable_pass'],
        'evaluable_pass': status['evaluable_pass'],
        'evaluable_items': all_items,
        'hard_invariants': hard,
        'shared_px4_writable': shared,
        'cross_worker': {'pass': None, 'reason': 'not_evaluated（需 ROS 图 / gz 话题证据）'},
        'infra': {'B_total': infra_b['count'], 'P_total': infra_p['count'],
                  'B_cases': infra_b['cases'], 'P_cases': infra_p['cases'],
                  'B_unclassified': infra_b['unclassified'],
                  'P_unclassified': infra_p['unclassified'],
                  'pass': infra_pass, 'reason': infra_reason},
        'active_window_enter': {'B_range': [lo, hi], 'pad_s': pad,
                                'per_case': enter_per, 'pass': enter_pass},
        'active_visibility_floor': {'floor': floor, 'per_case': vis_per, 'pass': vis_pass},
        'active_fco_band': {'B_min': (min(b_fcos) if b_fcos else None),
                            'B_max': (max(b_fcos) if b_fcos else None),
                            'band': band,
                            'P_values': {c['label']: c.get('active_fco') for c in P},
                            'coarse_shift': coarse,
                            'note': '只作粗移提示，不作等价门'},
        'rtf_and_ticks': {'B_vis_ticks_median': b_ticks_med, 'per_case': tick_per,
                          'pass': tick_pass},
    }


# --------------------------------------------------------------------------- 问答块

def same_seed_question(cases):
    pool = [c for c in cases
            if condition_group(c.get('label')) == 'C1'
            and c.get('seed') == 0
            and c.get('scene') == 's08_static_none_nominal_capture'
            and c.get('arm') == 'p2_rl_high'
            and c.get('active_fco') is not None]
    if len(pool) < 2:
        return {'status': 'insufficient_evidence',
                'reason': '同 scene/seed/arm 且带 active FCO 的 case 少于 2 个',
                'note': '未解释（证据不足）'}
    lo = min(pool, key=lambda c: c['active_fco'])
    hi = max(pool, key=lambda c: c['active_fco'])
    ratio = safe_div(hi['active_fco'], lo['active_fco'])
    categories = {(c.get('attribution') or {}).get('category') for c in (lo, hi)}
    if categories == {'physical_scatter'}:
        classification = 'physical_scatter'
    elif 'unexplained' in categories:
        classification = 'unexplained'
    else:
        classification = 'mixed'
    explanation = (
        '%s active FCO=%s 与 %s active FCO=%s 相差 %s 倍；active 可见率 %s vs %s 几乎相同，'
        '差异几乎全部来自 env_occ|visible（%s vs %s）。时间线：窗口 enter %s vs %s s、'
        '窗口时长 %s vs %s s、首次 FCO 相对窗口起点 %s vs %s s、捕获时刻约 %s vs %s s、'
        'FCO 持续段 %s vs %s s、FCO 拍 %s vs %s（首射 age %s vs %s s，intruder tw %s vs %s s）。'
        '⇒ 归因 %s：同 seed 下拦截几何 / 进入 1 m 火控包络的相对时机不同，导致包络内停留拍数差异；'
        '不是 active 可见率、启动窗口或目标年龄的粗移。' % (
            hi['label'], fmt(hi['active_fco']), lo['label'], fmt(lo['active_fco']),
            fmt(ratio, '%.1f'), fmt(hi.get('active_visibility')),
            fmt(lo.get('active_visibility')),
            fmt(hi.get('env_occ_given_visible')), fmt(lo.get('env_occ_given_visible')),
            fmt(hi.get('window_enter_s'), '%.2f'), fmt(lo.get('window_enter_s'), '%.2f'),
            fmt(hi.get('window_duration_s'), '%.2f'), fmt(lo.get('window_duration_s'), '%.2f'),
            fmt(hi.get('first_fco_rel_s'), '%.2f'), fmt(lo.get('first_fco_rel_s'), '%.2f'),
            fmt(hi.get('capture_t_s'), '%.2f'), fmt(lo.get('capture_t_s'), '%.2f'),
            fmt(hi.get('fco_span_s'), '%.2f'), fmt(lo.get('fco_span_s'), '%.2f'),
            fmt(hi.get('fco_ticks'), '%d'), fmt(lo.get('fco_ticks'), '%d'),
            fmt(hi.get('shot_age_s'), '%.3f'), fmt(lo.get('shot_age_s'), '%.3f'),
            fmt((hi.get('intruder_offboard_tw_s') or [None])[0], '%.1f'),
            fmt((lo.get('intruder_offboard_tw_s') or [None])[0], '%.1f'),
            classification))
    keys = ('label', 'active_fco', 'active_visibility', 'env_occ_given_visible',
            'window_enter_s', 'window_leave_s', 'window_duration_s', 'first_fco_rel_s',
            'capture_t_s', 'fco_span_s', 'fco_ticks', 'n_shots', 'shot_age_s',
            'intruder_offboard_tw_s')
    return {
        'status': 'answered',
        'scope': 'scene=s08_static_none_nominal_capture, seed=0, arm=p2_rl_high（C1/C4 历史）',
        'min': {'label': lo['label'], 'active_fco': lo['active_fco']},
        'max': {'label': hi['label'], 'active_fco': hi['active_fco']},
        'ratio_max_over_min': ratio,
        'classification': classification,
        'explanation': explanation,
        'evidence': {
            'min_case': {k: lo.get(k) for k in keys},
            'max_case': {k: hi.get(k) for k in keys},
        },
        'note': '描述性；n 小，不据此宣称分布或并行负载因果',
    }


def c4_worker0_question(cases):
    w0 = next((c for c in cases if c.get('worker') == 0), None)
    if w0 is None or w0.get('window_enter_s') is None:
        return {'status': 'insufficient_evidence',
                'reason': '缺少 worker_0 或 window enter',
                'note': '未解释（证据不足）'}
    w1 = next((c for c in cases if c.get('worker') == 1
               and c.get('run_id') == w0.get('run_id')), None)
    ref_enter = w1.get('window_enter_s') if w1 else None
    d_enter = (w0['window_enter_s'] - ref_enter) if ref_enter is not None else None
    release_off = None
    if w1 and w0.get('release_control_wall') is not None \
            and w1.get('release_control_wall') is not None:
        release_off = w0['release_control_wall'] - w1['release_control_wall']
    start_off = None
    if w1 and w0.get('start_ok_wall') is not None \
            and w1.get('start_ok_wall') is not None:
        start_off = w0['start_ok_wall'] - w1['start_ok_wall']
    classification = (w0.get('attribution') or {}).get('category')
    if classification != 'startup_state':
        return {
            'status': 'answered_descriptively',
            'label': w0['label'], 'window_enter_s': w0['window_enter_s'],
            'reference_label': (w1 or {}).get('label'),
            'reference_window_enter_s': ref_enter,
            'delta_window_enter_s': d_enter,
            'release_control_offset_vs_worker1_s': release_off,
            'start_ok_offset_vs_worker1_s': start_off,
            'classification': classification,
            'explanation': '窗口偏晚，但当前归因规则未将其判为 startup_state；见归因表。',
            'note': '描述性；未解释（证据不足）时不得用于并行扩容判断',
        }
    start_sim0 = w0.get('start_ok_sim_s')
    start_sim1 = (w1 or {}).get('start_ok_sim_s')
    d_start_sim = (start_sim0 - start_sim1) if (start_sim0 is not None
                                                and start_sim1 is not None) else None
    rel_start0 = w0.get('window_enter_rel_start_s')
    rel_start1 = (w1 or {}).get('window_enter_rel_start_s')
    d_rel_start = (rel_start0 - rel_start1) if (rel_start0 is not None
                                               and rel_start1 is not None) else None
    parts = [
        'worker_0 active 窗口 enter=%s s，worker_1=%s s（Δ=%s s）。' % (
            fmt(w0['window_enter_s'], '%.2f'), fmt(ref_enter, '%.2f'), fmt(d_enter, '%.2f')),
        'release_control 墙钟晚 %s s，start OK 墙钟晚 %s s，但 start OK 的仿真时刻仅差 %s s'
        '（%s vs %s s）。' % (
            fmt(release_off, '%.2f'), fmt(start_off, '%.2f'), fmt(d_start_sim, '%.2f'),
            fmt(start_sim0, '%.2f'), fmt(start_sim1, '%.2f')),
        '窗口相对 start OK：%s vs %s s（Δ=%s s）——窗口后移主要发生在 start OK 之后，'
        '不能只用 release 墙钟延迟解释。' % (
            fmt(rel_start0, '%.2f'), fmt(rel_start1, '%.2f'), fmt(d_rel_start, '%.2f')),
    ]
    if w0.get('px4_blind_land_n'):
        walls = w0.get('px4_blind_land_wall') or []
        rel = w0.get('release_control_wall')
        before = [w for w in walls if rel is None or w <= rel]
        after = [w for w in walls if rel is not None and w > rel]
        gap = (rel - before[-1]) if (rel is not None and before) else None
        parts.append(
            'worker_0 own PX4 在起飞后进入 `mc_pos_control invalid setpoints / '
            'Failsafe: blind land`（共 %d 次；release 前 %d 次，最后一次距 release %s s；'
            'release 后仍有 %d 次），与窗口后移同期。' % (
                w0['px4_blind_land_n'], len(before), fmt(gap, '%.2f'), len(after)))
    parts.append(
        '⇒ 归因 startup_state：own PX4 的 blind-land failsafe 与控制权交接 / 地面接近门晚开'
        '同期，窗口起点随之后移；但“failsafe → 接近门”的中间链路在日志中未显式记录，'
        '属时间线推断。')
    parts.append(
        '该证据只说明时间线因果链，不能据此证明并行负载本身导致（同条件仅 1 个 worker_0 样本）；'
        'C4 的历史“不准入”记录保持原样。')
    return {
        'status': 'answered',
        'label': w0['label'],
        'window_enter_s': w0['window_enter_s'],
        'reference_label': (w1 or {}).get('label'),
        'reference_window_enter_s': ref_enter,
        'delta_window_enter_s': d_enter,
        'release_control_wall': w0.get('release_control_wall'),
        'reference_release_control_wall': (w1 or {}).get('release_control_wall'),
        'release_control_offset_vs_worker1_s': release_off,
        'start_ok_wall': w0.get('start_ok_wall'),
        'reference_start_ok_wall': (w1 or {}).get('start_ok_wall'),
        'start_ok_offset_vs_worker1_s': start_off,
        'start_ok_sim_s': start_sim0,
        'reference_start_ok_sim_s': start_sim1,
        'delta_start_ok_sim_s': d_start_sim,
        'window_enter_rel_start_s': rel_start0,
        'reference_window_enter_rel_start_s': rel_start1,
        'delta_window_enter_rel_start_s': d_rel_start,
        'px4_ready_wall': w0.get('px4_ready_wall'),
        'reference_px4_ready_wall': (w1 or {}).get('px4_ready_wall'),
        'px4_blind_land_n': w0.get('px4_blind_land_n'),
        'px4_invalid_setpoint_n': w0.get('px4_invalid_setpoint_n'),
        'classification': 'startup_state',
        'explanation': ''.join(parts),
        'caveat': '描述性时间线证据；不证明并行负载因果，不改变 C4 历史结论',
    }


# --------------------------------------------------------------------------- 输出

def fmt(v, pattern='%.4f'):
    if v is None:
        return '-'
    try:
        return pattern % v
    except (TypeError, ValueError):
        return str(v)


def pass_str(value):
    return 'not_evaluated' if value is None else ('pass' if value else 'fail')


def md_table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |',
           '|' + '|'.join(['---'] * len(headers)) + '|']
    for row in rows:
        out.append('| ' + ' | '.join(str(x) for x in row) + ' |')
    return out


def render_gate_md(g, target='B', reference='A'):
    lines = ['- status: **%s**；pass: **%s**；complete: **%s**；evaluable_pass: **%s**' % (
        g.get('status'), pass_str(g.get('pass')), str(g.get('complete')),
        pass_str(g.get('evaluable_pass'))),
        '- reason: %s' % (g.get('reason') or '-')]
    if g.get('status') == 'not_evaluated':
        return lines
    hard = g.get('hard_invariants') or {}
    lines.append('- hard_invariants: **%s**（terminal=%s；lifecycle=%s；event identity=%s）' % (
        pass_str(hard.get('pass')), pass_str((hard.get('terminal_state') or {}).get('pass')),
        pass_str((hard.get('lifecycle') or {}).get('pass')),
        pass_str((hard.get('event_identity') or {}).get('pass'))))
    ref_terms = hard.get('reference_terminal_states') or []
    if ref_terms:
        lines.append('  - 参考 terminal 类别：%s' % ', '.join(ref_terms))
    lines.append('  - 判定：terminal ∈ 参考集合；lifecycle unresolved/duplicated=0；'
                 'event identity rejects=0；缺失任一项即 not_evaluated。')
    for key, label in (('lifecycle', 'lifecycle'), ('event_identity', 'event identity')):
        missing = (hard.get(key) or {}).get('missing') or []
        if missing:
            lines.append('  - %s 证据缺失：%s' % (label, ', '.join(missing)))
    shared = g.get('shared_px4_writable') or {}
    shared_per = shared.get('per_case') or {}
    if shared_per:
        detail = '；'.join('%s: any=%s changes=%s' % (
            label, sw.get('any'), len(sw.get('changes') or []))
            for label, sw in shared_per.items())
    else:
        detail = shared.get('reason') or '无 worker case'
    lines.append('- shared_px4_writable: **%s**（%s）' % (
        pass_str(shared.get('pass')), detail))
    lines.append('  - 判定：worker case 的 writes_detected.any 必须全部为 false；'
                 '任一 true → fail；无 worker case → not_evaluated。')
    infra = g.get('infra') or {}
    lines.append('- infra: **%s**（%s_total=%s，%s_total=%s；cases %s=%s，%s=%s）' % (
        pass_str(infra.get('pass')), reference, infra.get('%s_total' % reference),
        target, infra.get('%s_total' % target),
        reference, infra.get('%s_cases' % reference),
        target, infra.get('%s_cases' % target)))
    lines.append('  - 计数口径：outcome_class==infra 或 terminal_state==INFRA_FAILURE；'
                 '不再使用 infra_retries_used。')
    unclassified = (list(infra.get('%s_unclassified' % reference) or [])
                    + list(infra.get('%s_unclassified' % target) or []))
    if unclassified:
        lines.append('  - infra 分类缺失：%s' % ', '.join(unclassified))
    enter = g.get('active_window_enter') or {}
    lines.append('- active_window_enter: **%s**（%s 允许区间 %s，pad=%s s）' % (
        pass_str(enter.get('pass')), reference, enter.get('%s_range' % reference),
        enter.get('pad_s')))
    vis = g.get('active_visibility_floor') or {}
    lines.append('- active_visibility_floor: **%s**（下限 %s）' % (
        pass_str(vis.get('pass')), vis.get('floor')))
    band = g.get('active_fco_band') or {}
    lines.append('- active_fco_band: coarse_shift=%s（%s min/max=%s/%s，band=%s；只作粗移提示）' % (
        band.get('coarse_shift'), reference, band.get('%s_min' % reference),
        band.get('%s_max' % reference), band.get('band')))
    rt = g.get('rtf_and_ticks')
    if rt:
        lines.append('- rtf_and_ticks: **%s**（B vis_ticks 中位数=%s）' % (
            pass_str(rt.get('pass')), rt.get('B_vis_ticks_median')))
    items = g.get('evaluable_items') or {}
    if items:
        lines.append('- 可评估项：%s' % '；'.join(
            '%s=%s' % (k, pass_str(v)) for k, v in items.items()))
    return lines


def render_md(data):
    plan = data['plan']
    gd = plan['gate_defaults']
    md = ['# 单 worker 重复性 / 时间线诊断 · %s' % data['out_run_id'], '',
          '> **描述性诊断，不参与 P1 / P2 判定。** 只读既有产物（`metrics/arms.json` + '
          '`summary.json` + 逐 episode 日志）；不启动新 run，不改写任何 report / ADR / verdict。', '',
          '- campaign: `%s`' % data['campaign'],
          '- generated_by: `scripts/research/w7b_worker_repeatability.py`',
          '- generated_at: `%s`' % data['generated_at'],
          '- plan: `%s`' % plan['path'],
          '- plan sha256: `%s`' % (plan['sha256'] or '-'),
          '- 说明：%s' % (plan['note'] or '计划读取成功'),
          '- 口径：primary = active 窗口 FCO；legacy `window_fixed_v1` 仅作描述（含终态后停泊）。',
          '']

    md += ['## 门默认值（来自预声明计划）', '']
    md += md_table(['项', '值'], [
        ['active 窗口 enter pad', '%s s' % gd['window_pad_s']],
        ['active 可见率下限', gd['active_visibility_floor']],
        ['active FCO 粗移带', '±%s' % gd['active_fco_band']],
        ['infra', gd['infra']],
        ['hard invariants', gd['hard_invariants']],
        ['shared PX4 writable', gd['shared_px4_writable']],
    ])
    md += ['', '归因规则：', '']
    for key in ('startup_state', 'target_estimation', 'physical_scatter', 'unexplained'):
        md.append('- **%s**：%s' % (key, data['attribution_rules'][key]))
    md += ['']

    md += ['## 逐 case 指标', '',
           '| case | terminal | infra | active FCO | active vis | env_occ\\|vis | legacy FCO | legacy vis |',
           '|---|---|---|---|---|---|---|---|']
    for c in data['cases']:
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
            c['label'], c.get('terminal_state') or '-',
            fmt(c.get('infra_retries_used'), '%d'),
            fmt(c.get('active_fco')), fmt(c.get('active_visibility')),
            fmt(c.get('env_occ_given_visible')),
            fmt(c.get('legacy_fixed_fco')), fmt(c.get('legacy_fixed_visibility'))))
    md += ['', '| case | window enter | leave | 时长 | 首次 FCO(rel) | 首次包络(rel) | FCO span | FCO ticks |',
           '|---|---|---|---|---|---|---|---|']
    for c in data['cases']:
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
            c['label'], fmt(c.get('window_enter_s'), '%.2f'),
            fmt(c.get('window_leave_s'), '%.2f'), fmt(c.get('window_duration_s'), '%.2f'),
            fmt(c.get('first_fco_rel_s'), '%.2f'), fmt(c.get('first_envelope_rel_s'), '%.2f'),
            fmt(c.get('fco_span_s'), '%.2f'), fmt(c.get('fco_ticks'), '%d')))
    md += ['', '| case | n shots | first shot t | capture t | flight | shot age | target age max | RTF | sim start→end |',
           '|---|---|---|---|---|---|---|---|---|']
    for c in data['cases']:
        sim = '%s→%s' % (fmt(c.get('sim_start_s'), '%.2f'), fmt(c.get('sim_end_s'), '%.2f'))
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            c['label'], fmt(c.get('n_shots'), '%d'), fmt(c.get('first_shot_t_s'), '%.2f'),
            fmt(c.get('capture_t_s'), '%.2f'), fmt(c.get('flight_s'), '%.3f'),
            fmt(c.get('shot_age_s'), '%.3f'), fmt(c.get('target_age_max_s'), '%.3f'),
            fmt(c.get('rtf')), sim))

    md += ['', '## active FCO 分解（`active_fco = active_visibility × env_occ|visible`）', '',
           '| case | active FCO | active vis | env_occ\\|vis | 乘积校验 |',
           '|---|---|---|---|---|']
    for c in data['decomposition']:
        md.append('| %s | %s | %s | %s | %s |' % (
            c['label'], fmt(c['active_fco']), fmt(c['active_visibility']),
            fmt(c['env_occ_given_visible']), fmt(c['identity_check'])))

    md += ['', '## 时间线（启动 / 目标 / 交战）', '',
           '> PX4 的 `Ready for takeoff!` 行自身没有 ROS 时间戳；表中该列取最近一条有戳日志行近似'
           '（JSON 的 `px4_ready_estimated` 标出哪些是近似值）。'
           'target reject = `release_control→capture` 墙钟段 B1 拒绝计数比例；'
           'target age max = R-041 `goal_valid=true` 的最大 age（不是全日志最大值）。', '',
           '| case | PX4 ready wall | release_control wall | start OK wall | release→start | start OK sim | intruder tw | blind land | target reject | reject scope |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for c in data['cases']:
        ready = c.get('px4_ready_wall') or []
        ready_s = ', '.join(fmt(x, '%.2f') for x in ready) if ready else '-'
        tw = c.get('intruder_offboard_tw_s') or []
        tw_s = ', '.join(fmt(x, '%.1f') for x in tw) if tw else '-'
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            c['label'], ready_s, fmt(c.get('release_control_wall'), '%.2f'),
            fmt(c.get('start_ok_wall'), '%.2f'),
            fmt(c.get('release_to_start_wall_s'), '%.3f'),
            fmt(c.get('start_ok_sim_s'), '%.2f'), tw_s,
            fmt(c.get('px4_blind_land_n'), '%d'),
            fmt(c.get('target_reject_ratio'), '%.3f'),
            c.get('target_reject_scope') or '-'))

    md += ['', '## 硬不变量与隔离（按 case）', '',
           '> lifecycle / 事件身份 / 共享 build 写入均来自既有产物；普通 run 或未产出隔离证据的 '
           'worker case 没有 `px4_writable_isolation.json`，该项记 `-`（null），不视为失败。', '',
           '| case | worker | terminal | outcome_class | lifecycle unresolved | lifecycle duplicated | event identity rejects | shared writes any | changes | infra |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for c in data['cases']:
        lc = c.get('lifecycle') or {}
        sw = c.get('shared_writes_detected') or {}
        md.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            c['label'], ('-' if c.get('worker') is None else c.get('worker')),
            c.get('terminal_state') or '-', c.get('outcome_class') or '-',
            fmt(lc.get('n_unresolved'), '%d'), fmt(lc.get('n_duplicated'), '%d'),
            fmt(c.get('event_identity_rejects'), '%d'),
            ('-' if not sw else str(sw.get('any'))),
            fmt(len(sw.get('changes') or []), '%d') if sw else '-',
            'yes' if c.get('is_infra') else 'no'))
    md += ['']

    md += ['## 条件基线（min / median / max）', '']
    for name, stats in data['groups'].items():
        md += ['### %s（n=%d；labels：%s）' % (name, stats['n'], ', '.join(stats['labels'])), '']
        md += md_table(['字段', 'min', 'median', 'max'],
                       [[f, fmt(stats[f]['min']), fmt(stats[f]['median']),
                         fmt(stats[f]['max'])]
                        for f in ('active_fco', 'active_visibility', 'env_occ_given_visible',
                                  'window_enter_s', 'window_duration_s', 'first_fco_rel_s',
                                  'capture_t_s', 'shot_age_s', 'target_reject_ratio')])
        md += ['']

    md += ['## A/B 门（预声明）', '']
    md += render_gate_md(data['gates']['a_vs_b'], target='B', reference='A')
    md += ['', '## P/B 门（预声明，条件性）', '']
    md += render_gate_md(data['gates']['p_vs_b'], target='P', reference='B')
    md += ['']

    md += ['## 归因', '',
           '> 基线选择：C1 用自身 3 样本中位数；C4 仅 2 样本，改用同 scene/seed/arm 的 C1 串行参考'
           '（n=3），否则 2 样本中位数会让两个 worker 都成为“离群”；A/B/P 条件按预声明门互比。', '',
           '| case | baseline group | category | Δwindow enter | Δshot age | Δtw | Δreject(pp) | Δenv_occ | 证据 |',
           '|---|---|---|---|---|---|---|---|---|']
    for c in data['cases']:
        a = c.get('attribution') or {}
        d = a.get('deltas') or {}
        md.append('| %s | %s | **%s** | %s | %s | %s | %s | %s | %s |' % (
            c['label'], a.get('baseline_group'),
            a.get('category'), fmt(d.get('window_enter_s'), '%.2f'),
            fmt(d.get('shot_age_s'), '%.3f'), fmt(d.get('intruder_tw_s'), '%.2f'),
            fmt(d.get('target_reject_pp'), '%.1f'),
            fmt(d.get('env_occ_given_visible'), '%.4f'),
            '；'.join(a.get('evidence') or []) or '-'))
    md += ['', '### unexplained 列表', '']
    if data['unexplained']:
        md += ['- %s' % x for x in data['unexplained']]
    else:
        md += ['- 无（在可比 case 中）']
    md += ['']

    md += ['## 必答问题 1：同 seed active FCO 为何从 0.005 级到 0.216 级', '',
           '- status: **%s**' % data['questions']['same_seed_fco_range']['status']]
    if data['questions']['same_seed_fco_range']['status'] == 'answered':
        md += ['- %s' % data['questions']['same_seed_fco_range']['explanation']]
    else:
        md += ['- %s；%s' % (data['questions']['same_seed_fco_range']['reason'],
                             data['questions']['same_seed_fco_range']['note'])]
    md += ['', '## 必答问题 2：C4 worker_0 的 active 窗口为何晚至 56.2 s', '',
           '- status: **%s**' % data['questions']['c4_worker0_late_window']['status']]
    q2 = data['questions']['c4_worker0_late_window']
    if q2.get('status') in ('answered', 'answered_descriptively'):
        md += ['- %s' % q2.get('explanation')]
        for key in ('window_enter_s', 'reference_window_enter_s', 'delta_window_enter_s',
                    'release_control_offset_vs_worker1_s', 'start_ok_offset_vs_worker1_s',
                    'px4_blind_land_n'):
            md.append('- %s: %s' % (key, q2.get(key)))
    else:
        md += ['- %s；%s' % (q2.get('reason'), q2.get('note'))]
    md += ['']

    md += ['## 缺失 / 备注', '']
    missing_any = False
    for c in data['cases']:
        if c.get('missing_fields') or c.get('missing_evidence') or c.get('notes'):
            missing_any = True
            md.append('- **%s**：缺失字段 %s；缺失证据 %s；备注：%s' % (
                c['label'], ', '.join(c.get('missing_fields') or []) or '无',
                ', '.join(c.get('missing_evidence') or []) or '无',
                '；'.join(c.get('notes') or []) or '无'))
    if not missing_any:
        md.append('- 无缺失字段 / 日志。')
    md += ['', '> 证据边界：本报告是**描述性诊断**；n 小，不能用 1–3 次 run 宣称分布、等价或并行负载因果。']
    return '\n'.join(md) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--campaign', default='w7-rl-b')
    ap.add_argument('--out-run-id', default='20261025-w7-rl-b-repeat-diagnosis')
    ap.add_argument('--case', action='append', default=[],
                    help='LABEL=RUN_ID[:WORKER][#SEED]，可重复')
    ap.add_argument('--plan', default=DEFAULT_PLAN)
    ap.add_argument('--repo-root', default=ROOT)
    args = ap.parse_args()

    repo_root = os.path.abspath(args.repo_root)
    plan = load_plan(args.plan, repo_root)
    specs = []
    for arg in args.case:
        label, run_id, worker, seed = parse_case_arg(arg)
        for expanded_label, expanded_seed in expand_case(repo_root, args.campaign, label,
                                                          run_id, worker, seed):
            specs.append((expanded_label, run_id, worker, expanded_seed))
    if not specs:
        print('至少需要一个 --case', file=sys.stderr)
        return 2

    cases = [load_case(repo_root, args.campaign, label, run_id, worker, seed)
             for label, run_id, worker, seed in specs]
    groups = build_groups(cases)
    attach_attribution(cases, groups)

    decomposition = [{
        'label': c['label'],
        'active_fco': c.get('active_fco'),
        'active_visibility': c.get('active_visibility'),
        'env_occ_given_visible': c.get('env_occ_given_visible'),
        'identity_check': (c['active_visibility'] * c['env_occ_given_visible']
                          if (c.get('active_visibility') is not None
                              and c.get('env_occ_given_visible') is not None) else None),
    } for c in cases]

    group_view = {name: group_stats(cs) for name, cs in groups.items()}
    unexplained = ['%s：%s' % (c['label'], '；'.join((c.get('attribution') or {})
                                                    .get('evidence') or []))
                   for c in cases
                   if (c.get('attribution') or {}).get('category') == 'unexplained']

    data = {
        'kind': 'descriptive_diagnosis（描述性诊断，不参与 P1 / P2 判定）',
        'generated_by': 'scripts/research/w7b_worker_repeatability.py',
        'generated_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
        'campaign': args.campaign,
        'out_run_id': args.out_run_id,
        'repo_root': repo_root,
        'plan': plan,
        'attribution_rules': plan['attribution_rules'],
        'baseline_policy': ('C1 用自身 3 样本中位数；C4 仅 2 样本，改用同 scene/seed/arm 的 '
                            'C1 串行参考（n=3）；A/B/P 条件按预声明门互比（B vs A，P vs B）。'),
        'cases': cases,
        'decomposition': decomposition,
        'groups': group_view,
        'gates': {
            'a_vs_b': gate_ab(groups, plan['gate_defaults']),
            'p_vs_b': gate_pb(groups, plan['gate_defaults']),
        },
        'unexplained': unexplained,
        'questions': {
            'same_seed_fco_range': same_seed_question(cases),
            'c4_worker0_late_window': c4_worker0_question(cases),
        },
    }

    out_dir = os.path.join(repo_root, 'experiments', args.campaign, args.out_run_id,
                           'metrics')
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, 'worker_repeatability.json')
    md_path = os.path.join(out_dir, 'worker_repeatability.md')
    with open(json_path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(md_path, 'w') as f:
        f.write(render_md(data))
    print('-> %s\n-> %s' % (json_path, md_path))
    print('cases=%d groups=%s unexplained=%d' % (
        len(cases), list(group_view.keys()), len(unexplained)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
