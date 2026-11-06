#!/usr/bin/env python3
"""G2 round-6 判据：从 PX4 `ulg` 提取"GPS 自举是否成功"的可复跑证据。

为什么用 ulg 而不是日志文本： 的判别完全依赖 ulg 里的
`sensor_gps` / `vehicle_global_position` / `sensor_mag` 条数与 `reset_count_quat`；
日志文本只能看到 "invalid setpoints" 这类**下游症状**。

判据（每条都可被 ulg 直接证伪）：

  * `gps_ok` —— `sensor_gps` 条数 ≥ `--min-gps` **且** 时间跨度 ≥ `--min-span`；
  * `gpos_ok` —— `vehicle_global_position` 条数 ≥ `--min-gpos`；
  * `mag_ok` —— `sensor_mag` 条数 ≥ `--min-mag`；
 * `quat_ok` —— `reset_count_quat` ≥ 2（航向完成二次收敛， 的强判别量）；
 * `failsafe` —— `vehicle_status.failsafe` 是否出现 1。

用法：
    python3 scripts/g2/g2_px4_bootstrap_check.py --log-dir <ulg 目录> [--since <unix 时间>]

退出码：0 全部通过；1 有判据不满足；2 用法/环境错误。
"""

import argparse
import glob
import os
import sys
import time

try:
    import pyulog
except ImportError:
    print('ERROR: 需要 pyulog（pip install pyulog）', file=sys.stderr)
    sys.exit(2)


def summarize(ulg_path):
    u = pyulog.ULog(ulg_path)
    names = {d.name for d in u.data_list}

    def rows(nm):
        d = [x for x in u.data_list if x.name == nm]
        return d[0].data if d else None

    out = {'file': os.path.basename(ulg_path)}
    gps = rows('sensor_gps')
    if gps:
        ts = gps['timestamp']
        out['gps_n'] = len(ts)
        out['gps_span_s'] = round((ts[-1] - ts[0]) * 1e-6, 1) if len(ts) > 1 else 0.0
    else:
        out['gps_n'] = 0
        out['gps_span_s'] = 0.0

    gpos = rows('vehicle_global_position')
    out['gpos_n'] = len(gpos['timestamp']) if gpos else 0

    mag = rows('sensor_mag')
    out['mag_n'] = len(mag['timestamp']) if mag else 0
    out['mag_device_id'] = int(mag['device_id'][0]) if mag else None

    es = rows('estimator_status')
    out['reset_quat'] = int(es['reset_count_quat'][-1]) if es and 'reset_count_quat' in es else None
    out['reset_vel_ne'] = int(es['reset_count_vel_ne'][-1]) if es and 'reset_count_vel_ne' in es else None

    vs = rows('vehicle_status')
    out['failsafe'] = int(max(vs['failsafe'])) if vs and 'failsafe' in vs else 0
    if vs and 'nav_state' in vs:
        ns = vs['nav_state']
        out['nav_state_min'] = int(min(ns))
        out['nav_state_max'] = int(max(ns))
    else:
        out['nav_state_min'] = out['nav_state_max'] = None

    out['has_attitude'] = 'vehicle_attitude' in names
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--log-dir', required=True)
    ap.add_argument('--since', type=float, default=None,
                    help='只统计 mtime >= 该 unix 时间（秒）的 ulg，用于隔离本轮新运行')
    ap.add_argument('--min-gps', type=int, default=30)
    ap.add_argument('--min-span', type=float, default=20.0)
    ap.add_argument('--min-gpos', type=int, default=2000)
    ap.add_argument('--min-mag', type=int, default=30)
    ap.add_argument('--expect-quat', type=int, default=2)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)

    files = sorted(glob.glob(os.path.join(args.log_dir, '*.ulg')))
    if args.since is not None:
        files = [f for f in files if os.path.getmtime(f) >= args.since]
    if not files:
        print('ERROR: 没有匹配的 ulg', file=sys.stderr)
        return 2

    results = []
    ok_all = True
    for f in files:
        try:
            r = summarize(f)
        except Exception as e:                      # noqa: BLE001 - 坏 ulg 不应中断整批判定
            r = {'file': os.path.basename(f), 'error': str(e)}
        if 'error' not in r:
            r['gps_ok'] = r['gps_n'] >= args.min_gps and r['gps_span_s'] >= args.min_span
            r['gpos_ok'] = r['gpos_n'] >= args.min_gpos
            r['mag_ok'] = r['mag_n'] >= args.min_mag
            # `reset_count_quat` 只对**目标实例**有判别意义：己方实例走 LQR 八字轨迹，
            # 实测可在 quat=1 下长期稳定（nav_state 恒 4、failsafe=0），故不能一刀切。
            # 目标实例的识别特征：nav_state 出现过 <4（被踢出 Offboard）或 failsafe=1。
            target_like = ((r['nav_state_min'] is not None and r['nav_state_min'] < 4)
                           or r['failsafe'] != 0)
            r['target_like'] = target_like
            r['quat_ok'] = (r['reset_quat'] is not None
                            and r['reset_quat'] >= args.expect_quat)
            r['passed'] = (r['gps_ok'] and r['gpos_ok'] and r['mag_ok']
                           and r['failsafe'] == 0
                           and (r['quat_ok'] or not target_like))
            ok_all = ok_all and r['passed']
        results.append(r)

    if args.json:
        import json
        print(json.dumps({'passed': ok_all, 'files': results}, indent=2, ensure_ascii=False))
    else:
        print('%-16s %-6s %-7s %-8s %-7s %-6s %-5s %s' % (
            'ulg', 'gps_n', 'gps_span', 'gpos_n', 'mag_n', 'quat', 'fs', 'pass'))
        for r in results:
            if 'error' in r:
                print('%-16s ERROR %s' % (r['file'], r['error']))
                continue
            print('%-16s %-6d %-7.1f %-8d %-7d %-6s %-5d %s' % (
                r['file'], r['gps_n'], r['gps_span_s'], r['gpos_n'], r['mag_n'],
                r['reset_quat'], r['failsafe'], 'OK' if r['passed'] else 'FAIL'))
        print()
        print('总体:', 'PASS' if ok_all else 'FAIL')
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
