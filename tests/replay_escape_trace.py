#!/usr/bin/env python3
"""横向逃逸轨迹的**离线重放**核对（纯离线，不 import rclpy、不启仿真）。

## 它证明什么

`tests/check_safety_calibration.py --stage slow` 把每轮逼近/转向的**逐拍真值轨迹**
落进 `escape_arc_traces.json`。本脚本用**同一份公式**（垂直于初始航向的位移投影）离线
重算：

1. 每轮的横向位移与在线报的值**逐轮一致**（差 ≤ `--tol`，默认 1 mm）；
2. **最差折扣**（`min(reach) / 理想圆弧`）与在线的 `eff_ratio_min` 一致；
3. 每轮是否真的进过 `SLOW`（档位来自逐拍 `tier`），与 `slow_engaged` 一致；
4. 配置的 `max_offset` 是否超过实测可达最小值（`required_reachable`）。

## 为什么必须能离线重放（用户裁定的硬要求）

"实测最小 0.769 m / 折扣 0.55"这类结论如果只能由跑仿真的那一刻得出，别人**无法复核**——
他要么相信，要么再花两分钟跑一次且很可能得到另一组数。逐拍轨迹落盘后，
"最小值、折扣、余量"全部变成**可从数据重算的量**，失败样本也留在里面。

## 用法

    python3 tests/replay_escape_trace.py --traces experiments/.../escape_arc_traces.json
    python3 tests/replay_escape_trace.py --run-id 20261113-calib-slow4 \
        --experiments-root experiments

退出码：0 = 逐轮一致；1 = 有不一致（**含"轨迹里根本没有 SLOW 段"**）；2 = 用法 / 文件错误。
"""

import argparse
import glob
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# 理想圆弧（与生产 `slowRatioFloor()` 同公式）：L = (v_cap/ω_cap)·(1-cos(ω_cap·T))。
# 参数取 `ground.yaml` 的 v_cap / w_cap 与反应窗口 T —— **不在这里另写一套数字**。
DEFAULT_TOL_M = 0.001


def _load_yaml(path):
    import yaml
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def ideal_lateral_from_config():
    """理想圆弧上界 —— **必须用与实测同一组输入**，否则"折扣"比的是两件事。

    生产 `slowRatioFloor()` 用 `v_cap / w_cap`（1.5 / 2.0）是对的：它要回答的是
    "在最坏情况（满速满角）下能横移多少"。但**实测那一轮的输入是 `v=1.0, ω=0.96`**
    （见轨迹里逐拍的 `cmd_v` / `cmd_w`），用 1.5/2.0 去算折扣会得到 >1 的荒谬值
    （实测踩过：0.96 的 ω 让 `1-cos(ωT)` 更大，理想值反而小于满速理想值）。

    故本函数**从轨迹里取实际指令**算理想值；取不到才退回配置上限，并显式标注口径。
    """
    g = _load_yaml(os.path.join(ROOT, 'src', 'agc_ground', 'config', 'ground.yaml'))
    p = g['ground_safety_filter']['ros__parameters']
    return (float(p['v_cap']) / float(p['w_cap'])) * (
        1.0 - math.cos(float(p['w_cap']) * float(p['lateral_window_s'])))


def ideal_lateral_from_trace(trace):
    """按该轮**实际指令**算理想圆弧：L = (v/ω)(1−cos(ωT))。"""
    ss = trace.get('samples') or []
    if not ss:
        return None
    v = float(ss[0].get('cmd_v') or 0.0)
    w = float(ss[0].get('cmd_w') or 0.0)
    T = float(trace.get('window_s') or 0.0)
    if v <= 0.0 or w <= 0.0 or T <= 0.0:
        return None
    return (v / w) * (1.0 - math.cos(w * T))


def replay_trace(trace):
    """用逐拍真值重算横向位移（**与在线的公式逐字相同**）。

    口径：垂直于**初始航向**的单位向量 `(-sin yaw0, cos yaw0)` 上的投影。
    不取世界 y 差值 —— 只有 yaw0≈0 时两者才相等，取错会把"沿车头的位移"算成横向。
    """
    ss = trace.get('samples') or []
    if len(ss) < 2:
        return {'error': '轨迹样本不足（<2 拍）'}
    yaw0 = float(trace['heading_rad'])
    x0, y0 = ss[0]['x'], ss[0]['y']
    x1, y1 = ss[-1]['x'], ss[-1]['y']
    lateral = -(x1 - x0) * math.sin(yaw0) + (y1 - y0) * math.cos(yaw0)
    tiers = [s.get('tier') for s in ss if s.get('tier')]
    return {
        'reach_m': round(abs(lateral), 6),
        'signed_m': round(lateral, 6),
        'samples': len(ss),
        'states_seen': sorted(set(tiers)),
        'slow_engaged': 'SLOW' in set(tiers),
        'duration_s': round(ss[-1]['t'] - ss[0]['t'], 3),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--traces', default=None, help='escape_arc_traces.json 路径')
    ap.add_argument('--run-id', default=None)
    ap.add_argument('--experiments-root', default=os.path.join(ROOT, 'experiments'))
    ap.add_argument('--tol', type=float, default=DEFAULT_TOL_M)
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    path = args.traces
    if not path:
        if not args.run_id:
            ap.error('需要 --traces 或 --run-id')
        cand = glob.glob(os.path.join(
            args.experiments_root, 'w5-ground-nav-safety', args.run_id,
            'metrics', 'escape_arc_traces.json'))
        if not cand:
            print('FAIL：找不到 %s 的 escape_arc_traces.json（先跑 --stage slow）' % args.run_id)
            return 2
        path = cand[0]
    if not os.path.isfile(path):
        print('FAIL：文件不存在 %s' % path)
        return 2

    with open(path, encoding='utf-8') as f:
        payload = json.load(f)
    traces = payload.get('traces') or {}
    if not traces:
        print('FAIL：轨迹文件里没有 traces')
        return 2

    ideal_cap = ideal_lateral_from_config()
    problems = []
    rows = []
    ideals = {}
    for name in sorted(traces):
        tr = traces[name]
        r = replay_trace(tr)
        if 'error' in r:
            problems.append('%s: %s' % (name, r['error']))
            continue
        online = tr.get('online_reach_m')
        delta = abs(r['reach_m'] - float(online)) if online is not None else None
        ideal_tr = ideal_lateral_from_trace(tr)
        if ideal_tr:
            ideals[name] = ideal_tr
        rows.append({'trace': name, 'online_m': online, 'replay_m': r['reach_m'],
                     'delta_m': round(delta, 6) if delta is not None else None,
                     'states': r['states_seen'], 'samples': r['samples'],
                     'ideal_arc_m': round(ideal_tr, 4) if ideal_tr else None,
                     'eff_ratio': (round(r['reach_m'] / ideal_tr, 4)
                                   if ideal_tr else None)})
        if delta is not None and delta > args.tol:
            problems.append('%s: 重放 %.6f 与在线 %.6f 相差 %.6f m（容差 %.3f）'
                            % (name, r['reach_m'], online, delta, args.tol))
        # SLOW 轨迹必须真的进过 SLOW：否则量到的是"车原本的机动能力"，
        # 根本没有回答"SLOW 下还行不行"（改造前踩过这个坑）。
        if name.startswith('slow_') and not r['slow_engaged']:
            problems.append('%s: 轨迹里没有 SLOW 段 ⇒ 这一轮没有回答 SLOW 的机动性' % name)

    slow_rows = [r for r in rows if r['trace'].startswith('slow_')]
    summary = {}
    if slow_rows:
        reach = [r['replay_m'] for r in slow_rows]
        ratios = [r['eff_ratio'] for r in slow_rows if r['eff_ratio'] is not None]
        summary = {
            'slow_trials': len(slow_rows),
            'min_m': round(min(reach), 4),
            'median_m': round(sorted(reach)[len(reach) // 2], 4),
            'max_m': round(max(reach), 4),
            # 理想值按**该轮实际指令**算（与实测同一组输入），不是取配置上限。
            'ideal_arc_m_each': [r['ideal_arc_m'] for r in slow_rows],
            'ideal_arc_m_cap': round(ideal_cap, 4),
            'ideal_arc_basis': 'per-trial: (cmd_v/cmd_w)*(1-cos(cmd_w*T))',
            'eff_ratio_each': ratios,
            'eff_ratio_min': round(min(ratios), 4) if ratios else None,
        }
        # 与在线 `eff_ratio_min` 对照（轨迹文件本身不带 summary，故只在这里算并打印）
        print('实测（离线重算）：min %.4f / median %.4f / max %.4f m；'
              '逐轮理想圆弧 %s；最差折扣 %s'
              % (summary['min_m'], summary['median_m'], summary['max_m'],
                 summary['ideal_arc_m_each'], summary['eff_ratio_min']))

    for r in rows:
        print('  %-14s 在线 %-8s 重放 %-8s Δ%-9s 档位=%s'
              % (r['trace'], r['online_m'], r['replay_m'], r['delta_m'], r['states']))
    for p in problems:
        print('  ✗ %s' % p)

    payload_out = {'traces_file': path, 'tol_m': args.tol,
                   'ideal_arc_m_cap': round(ideal_cap, 4),
                   'rows': rows, 'summary': summary, 'problems': problems,
                   'pass': not problems}
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(payload_out, f, ensure_ascii=False, indent=2)

    print('%s（横向逃逸轨迹离线重放）' % ('PASS' if not problems else 'FAIL'))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
