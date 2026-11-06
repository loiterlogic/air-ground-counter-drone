#!/usr/bin/env python3
"""round-7 B 项：安全回归定性（**纯离线**，不起仿真、不读真值以外的在线数据）。

只读三处原始产物：
  * `experiments/w6-task-eval/<run>/metrics/summary.json`
  * `experiments/w6-task-eval/<run>/config/scene_manifest.json`
  * `experiments/w6-task-eval/<run>/config/params_applied.yaml`
  * round-6/evidence/probe-r6.json（**归属 162101**：started_at 16:20:46 / launch_pid 19363）
  * round-6/evidence/launch-r6.log（**归属 162046-19363**：参数文件名内嵌）

输出：
  * `run-config-compare.json` —— 三次 run 的逐项配置/终态/指标比对
  * `b-causal-chain.json`    —— 视觉航迹误差、goal 跳变、安全层触发时间线

纪律：**一 run 一目录**。本脚本**不**把不同 run 的 summary / manifest / 探针混装；
所有跨 run 的比对都显式带 run_id 列，且标注每份产物的归属依据。

用法：python3 b_regression_analysis.py ；退出码 0 = 全部读取成功。
"""
import bisect
import json
import math
import os
import re
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))
EXP = os.path.join(ROOT, 'experiments', 'w6-task-eval')
R6 = os.path.join(ROOT, '.coordination', 'task', '20261102-002-n1-vision-minimal-loop',
                  'round-6', 'evidence')

RUNS = {
    'run-155603-2790': '20261102-s02_linear_none_nominal_track-0-155603-2790',
    'run-161832-2961': '20261102-s02_linear_none_nominal_track-0-161832-2961',
    'run-162101-7315': '20261102-s02_linear_none_nominal_track-0-162101-7315',
}

# 安全层常量（真源：agc_task/src/run_logger.cpp 的 declare_parameter 缺省 + 地图/场景配置）
CONTACT_DIST_M = 2.0      # run_logger.cpp:155  contact_dist_m 缺省
TTC_MIN_S = 1.0           # run_logger.cpp:156  ttc_min_s 缺省
FORWARD_CONE_RAD = 0.9    # run_logger.cpp:157  forward_cone_rad 缺省


def load_run(run_dir):
    s = json.load(open(os.path.join(EXP, run_dir, 'metrics', 'summary.json')))
    m = json.load(open(os.path.join(EXP, run_dir, 'config', 'scene_manifest.json')))
    return s, m


def config_block(s, m):
    ep = m.get('effective_params', {})
    return {
        'perception_path': s.get('perception_path'),
        'detector_backend': s.get('detector_backend'),
        'target_source': ep.get('target_source'),
        'sensors_file': (ep.get('sensors_file') or '').split('/')[-1],
        'world_map': ep.get('world_map'),
        'world_obstacles': ep.get('world_obstacles'),
        'observe_yaw_mode': ep.get('observe_yaw_mode'),
        'cruise_alt_m': (ep.get('cruise_altitude') or {}).get('effective_m'),
        'cruise_alt_source': (ep.get('cruise_altitude') or {}).get('source'),
        'vision_plane_z': (ep.get('vision_plane') or {}).get('world_enu_plane_z'),
        'vision_plane_source': (ep.get('vision_plane') or {}).get('source'),
        'scene': m.get('scene'), 'seed': m.get('seed'), 'backend': m.get('backend'),
        'seed_protocol': ep.get('seed_protocol'),
        'spawn_distances': (m.get('spawn_layout') or {}).get('distances'),
        'goal': (m.get('spawn_layout') or {}).get('goal'),
        'geometry_sha256': (m.get('geometry') or {}).get('sha256'),
        'spawn_layout_sha256': (m.get('spawn_layout') or {}).get('sha256'),
    }


def build_config_compare():
    out = {}
    for k, d in RUNS.items():
        s, m = load_run(d)
        out[k] = {
            'run_id': s['run_id'],
            'artifacts': {
                'summary': os.path.join(EXP, d, 'metrics', 'summary.json'),
                'manifest': os.path.join(EXP, d, 'config', 'scene_manifest.json'),
            },
            'identity': {x: s.get(x) for x in
                         ('git_commit', 'episode_id', 'wall_start_unix_s', 'wall_end_unix_s',
                          'duration_s', 'sim_start_s', 'sim_end_s')},
            'config': config_block(s, m),
            'terminal': {x: s.get(x) for x in
                         ('terminal_state', 'reason_code', 'shield_infeasible_rate',
                          'ticks_infeasible', 'ticks_total', 'ticks_triggered',
                          'true_shield_infeasible_rate', 'collision_count',
                          'stopping_margin_min_m', 'stopping_margin_negative_ticks')},
            'episode_window_metrics': s.get('episode_window_metrics'),
            'command_attribution': s.get('command_attribution'),
            'visibility_metrics': s.get('visibility_metrics'),
        }
    # 结论性判据（可被 report 直接引用）
    cfgs = [out[k]['config'] for k in RUNS]
    def _same(field):
        vals = {json.dumps(c.get(field), sort_keys=True) for c in cfgs}
        return len(vals) == 1, [c.get(field) for c in cfgs]
    out['_comparability'] = {
        'note': '三次 run 的 params_applied.yaml 逐键比对亦为 0 差异（154 键），见 report §B1',
        'identical_fields': {f: _same(f)[0] for f in
                             ('perception_path', 'target_source', 'sensors_file', 'world_map',
                              'world_obstacles', 'observe_yaw_mode', 'cruise_alt_m',
                              'cruise_alt_source', 'vision_plane_z', 'vision_plane_source',
                              'scene', 'seed', 'backend', 'seed_protocol', 'geometry_sha256',
                              'spawn_layout_sha256')},
        'differing_fields': {
            'detector_backend': {
                'values': [c['detector_backend'] for c in cfgs],
                'reason': '155603 是 W7-b 的 C 项（detector_backend 入 summary）落地**之前**的 run，'
                          'summary 无该键；161832 与 162101 均为 synthetic_color，二者相同',
            },
        },
    }
    return out


def build_clock_map(probe):
    """墙钟 → 仿真时刻的映射，**必须**由探针自带的同时刻对 `(rx_epoch, track_stamp)` 建立。

    为什么不能用 `summary.wall_start_unix_s − summary.sim_start_s` 当常数偏移：本 run 实测
    该偏移在 173 s 墙钟内**漂移 15.37 s**（RTF≈0.91），说明仿真不是实时比 1:1；用常数偏移
    会把 30 s 量级的时间线错位到另一处（实测错位 ~19 s，足以把 stop 段归到错误的时刻）。
    正确做法：用探针里成对的 `(rx_epoch 墙钟, track_stamp 仿真)` 做**分段线性内插**，
    范围外按最近端点偏移**常数外推**（不外推斜率，避免噪声放大）。
    """
    tr = probe['pairing_chain']['track_records']
    wall = [r['rx_epoch'] for r in tr]
    sim = [r['track_stamp'] for r in tr]
    offs = [w - s for w, s in zip(wall, sim)]

    def w2s(w):
        if w <= wall[0]:
            return w - offs[0]
        if w >= wall[-1]:
            return w - offs[-1]
        i = bisect.bisect_left(wall, w)
        a = (w - wall[i - 1]) / (wall[i] - wall[i - 1]) if wall[i] > wall[i - 1] else 0.0
        return w - (offs[i - 1] + a * (offs[i] - offs[i - 1]))

    return w2s, {
        'method': 'probe (rx_epoch, track_stamp) 分段线性内插；范围外常数外推',
        'n_anchors': len(wall),
        'offset_first_s': round(offs[0], 3),
        'offset_last_s': round(offs[-1], 3),
        'offset_drift_s': round(offs[-1] - offs[0], 3),
        'wall_span_s': round(wall[-1] - wall[0], 2),
        'sim_span_s': round(sim[-1] - sim[0], 2),
        'implied_rtf': round((sim[-1] - sim[0]) / (wall[-1] - wall[0]), 4),
        'rejected_alternative': (
            'summary.wall_start_unix_s − summary.sim_start_s 作常数偏移 —— 实测会错位约 19 s，'
            '故**不采用**；该差异本身是本 run 的 RTF≠1 证据'),
    }


def parse_collision_events(log_path, w2s):
    """从 launch 日志抽 collision_monitor 的动作边沿，并用 `w2s` 把墙钟换算成 sim 时间。"""
    pat = re.compile(r'\[collision_monitor-\d+\] \[(\w+)\] \[(\d+\.\d+)\].*Robot to (\w+)(.*)')
    ev = []
    for ln in open(log_path, errors='ignore'):
        m = pat.search(ln)
        if m:
            ev.append({
                't_sim': round(w2s(float(m.group(2))), 3),
                'level': m.group(1),
                'action': m.group(3),
                'why': m.group(4).strip()[:80],
            })
    return ev


def triggered_spans(events):
    """把边沿折成 [start, end] 触发区间（stop/slowdown → continue）。"""
    spans, start = [], None
    for e in events:
        if e['action'] in ('stop', 'slowdown'):
            if start is None:
                start = e
        elif e['action'] == 'continue' and start is not None:
            spans.append({'start_s': start['t_sim'], 'end_s': e['t_sim'],
                          'dur_s': round(e['t_sim'] - start['t_sim'], 3),
                          'kind': start['why'][:60]})
            start = None
    if start is not None:
        spans.append({'start_s': start['t_sim'], 'end_s': None, 'dur_s': None,
                      'kind': start['why'][:60] + ' (未闭合)'})
    return spans


def build_causal_chain():
    s = json.load(open(os.path.join(EXP, RUNS['run-162101-7315'], 'metrics', 'summary.json')))
    probe = json.load(open(os.path.join(R6, 'probe-r6.json')))
    if abs(probe['launch_pid'] - 19363) != 0 or not probe['started_at'].startswith('2026-11-02T16:20:46'):
        raise SystemExit('probe-r6.json 归属不是 162101（started_at/launch_pid 不符）→ 拒绝混装')
    w2s, clock = build_clock_map(probe)
    tr = probe['pairing_chain']['track_records']
    gt = probe['gt_target_samples']
    ts = [r['track_stamp'] for r in tr]
    gts = [g[0] for g in gt]

    def trat(t):
        i = bisect.bisect_left(ts, t)
        i = max(1, min(i, len(tr) - 1))
        a = (t - ts[i - 1]) / (ts[i] - ts[i - 1]) if ts[i] > ts[i - 1] else 0.0
        return (tr[i - 1]['x'] + a * (tr[i]['x'] - tr[i - 1]['x']),
                tr[i - 1]['y'] + a * (tr[i]['y'] - tr[i - 1]['y']))

    def gtat(t):
        i = bisect.bisect_left(gts, t)
        i = max(1, min(i, len(gt) - 1))
        a = (t - gt[i - 1][0]) / (gt[i][0] - gt[i - 1][0]) if gt[i][0] > gt[i - 1][0] else 0.0
        return (gt[i - 1][1] + a * (gt[i][1] - gt[i - 1][1]),
                gt[i - 1][2] + a * (gt[i][2] - gt[i - 1][2]))

    # 1 Hz 对齐（goal 发布节奏 1 Hz；planner 重规划位移阈值 replan_displacement_m=1.0）
    grid = [30.0 + i for i in range(148)]
    pair = []
    for t in grid:
        vx, vy = trat(t)
        gx, gy = gtat(t)
        pair.append({'t': t, 'track_x': round(vx, 3), 'track_y': round(vy, 3),
                     'gt_x': round(gx, 3), 'gt_y': round(gy, 3),
                     'dx': round(vx - gx, 3), 'dy': round(vy - gy, 3),
                     'err_xy': round(math.hypot(vx - gx, vy - gy), 3)})
    errs = [p['err_xy'] for p in pair]
    dxs = [p['dx'] for p in pair]
    dys = [p['dy'] for p in pair]
    jumps = [{'t': b['t'], 'delta_m': round(math.hypot(b['track_x'] - a['track_x'],
                                                       b['track_y'] - a['track_y']), 3)}
             for a, b in zip(pair, pair[1:])]
    jv = [j['delta_m'] for j in jumps]

    def band(lo, hi):
        sub = [p for p in pair if lo <= p['t'] < hi]
        if not sub:
            return None
        e = [p['err_xy'] for p in sub]
        return {'t_range': [lo, hi], 'n': len(sub),
                'dx_mean': round(sum(p['dx'] for p in sub) / len(sub), 3),
                'dy_mean': round(sum(p['dy'] for p in sub) / len(sub), 3),
                'err_p50': round(st.median(e), 3),
                'err_p95': round(sorted(e)[int(0.95 * len(e))], 3),
                'err_max': round(max(e), 3),
                'frac_goal_jump_gt_1m': round(
                    sum(1 for j in jumps if lo <= j['t'] < hi and j['delta_m'] > 1.0) /
                    max(1, sum(1 for j in jumps if lo <= j['t'] < hi)), 3)}

    events = parse_collision_events(os.path.join(R6, 'launch-r6.log'), w2s)
    spans = triggered_spans(events)
    win = s['episode_window_metrics']
    return {
        'run_id': s['run_id'],
        'evidence_ownership': {
            'summary/manifest': s['run_id'],
            'probe': 'probe-r6.json → started_at=%s launch_pid=%s' % (
                probe['started_at'], probe['launch_pid']),
            'launch_log': 'launch-r6.log → 参数文件 …_20261102-162046-19363-2408.yaml',
            'clock_map': clock,
        },
        'infeasible_metric_semantics': {
            'definition': 'proxy_v1：**地面** collision_monitor 处于 STOP(1)/SLOWDOWN(2) 的拍中，'
                          '前向扫描最小距离 ≤ contact_dist_m 或 TTC < ttc_min_s 的占比',
            'contact_dist_m': CONTACT_DIST_M, 'ttc_min_s': TTC_MIN_S,
            'forward_cone_rad': FORWARD_CONE_RAD,
            'source': 'src/agc_task/src/run_logger.cpp:155-157,987-989',
            'note': '**不是**空中 safety_shield 的不可行（那是 trajectory_tracker 的 shield_*，'
                    '经 command_attribution 另行统计）',
        },
        'triggered_time_budget': {
            'episode_window_ticks': win['ticks_total'],
            'triggered_ticks': win['triggered_ticks'],
            'infeasible_ticks': win['infeasible_ticks'],
            'infeasible_rate_window': win['shield_infeasible_rate'],
            'ticks_intervened': win['ticks_intervened'],
            'intervention_ticks_ratio': win['intervention_ticks_ratio'],
            'triggered_seconds_at_30hz': round(win['triggered_ticks'] / 30.0, 2),
            'window_seconds': round(win['ticks_total'] / 30.0, 2),
        },
        'collision_monitor_edges': events,
        'triggered_spans': spans,
        'longest_span_s': max((x['dur_s'] or 0.0) for x in spans) if spans else 0.0,
        'vision_vs_truth_1hz': {
            'n': len(pair),
            'dx_mean': round(sum(dxs) / len(dxs), 3),
            'dy_mean': round(sum(dys) / len(dys), 3),
            'err_p50': round(st.median(errs), 3),
            'err_p95': round(sorted(errs)[int(0.95 * len(errs))], 3),
            'err_max': round(max(errs), 3),
            'bands': [b for b in (band(30, 60), band(60, 100), band(100, 140),
                                  band(140, 178)) if b],
        },
        'goal_jump_1hz': {
            'n': len(jumps),
            'frac_gt_replan_threshold_1m': round(sum(1 for v in jv if v > 1.0) / len(jv), 3),
            'p50': round(st.median(jv), 3),
            'p95': round(sorted(jv)[int(0.95 * len(jv))], 3),
            'max': round(max(jv), 3),
            'planner_replan_displacement_m': 1.0,
            'goal_mismatch_rejections_in_log': None,  # 由 report 引用 log grep 计数
        },
        'samples': pair[::10],
    }


def main():
    cfg = build_config_compare()
    json.dump(cfg, open(os.path.join(HERE, 'run-config-compare.json'), 'w'),
              ensure_ascii=False, indent=1)
    chain = build_causal_chain()
    json.dump(chain, open(os.path.join(HERE, 'b-causal-chain.json'), 'w'),
              ensure_ascii=False, indent=1)
    print('run-config-compare.json written; identical fields:',
          sum(1 for v in cfg['_comparability']['identical_fields'].values() if v), '/',
          len(cfg['_comparability']['identical_fields']))
    print('b-causal-chain.json written; infeasible_rate_window=%s longest_span=%ss' % (
        chain['triggered_time_budget']['infeasible_rate_window'], chain['longest_span_s']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
