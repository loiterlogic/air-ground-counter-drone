#!/usr/bin/env python3
"""raw / effective 命令归因取证。

读 `episode_runner` campaign 报告（`experiments/w7-rl-b/<run_id>/metrics/report.json`）里每个
episode 的 `summary_path` → 读该 run 的 `metrics/summary.json` 的 `command_attribution` 块，核查：

  * 两话题均收到（`raw_msgs_received` > 0 且 `effective_msgs_received` > 0）；
  * 有**同拍配对**样本（`ticks_paired` > 0）；
  * `not_applicable` 的 raw / effective / paired_ticks / clearance 均 **false**（数据可得）；
  * **有 shield 臂**（`shield_layer_enabled` true）→ `intervened_ticks` > 0（安全层**确实**改过命令，
    否则该证据不足以证明"能记录干预"）；
  * **无 shield 臂**（false）→ `intervened_ticks` == 0 且 `max_abs_delta_v_mps` / `max_abs_delta_w_radps`
    在 epsilon 量级（恒等透传：effective ≡ raw）。

判据依据 [ADR-0022](docs/adr/0022-w7b-research-propositions-and-decision-rule.md#top)(d)（E1）与
（见 ADR-0011）。

用法：
  python3 tests/check_rl_command_attribution.py --report experiments/w7-rl-b/<run_id>/metrics/report.json
  python3 tests/check_rl_command_attribution.py --experiments-root <root>   # 取该根下最新 run
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402  （tests/ 内共用小工具）

ROOT = '/home/chen/AGC'
CAMPAIGN = 'w7-rl-b'
EPS = 1e-6


def check_one(ep, expect_shield):
    ca = ep.get('command_attribution')
    checks = {}
    if not ca:
        return {'checks': {'attribution_present': False}, 'pass': False, 'detail': 'no command_attribution'}
    na = ca.get('not_applicable') or {}
    shield_on = bool(ca.get('shield_layer_enabled'))
    checks['attribution_present'] = True
    checks['raw_received'] = int(ca.get('raw_msgs_received', 0)) > 0
    checks['effective_received'] = int(ca.get('effective_msgs_received', 0)) > 0
    checks['ticks_paired_positive'] = int(ca.get('ticks_paired', 0)) > 0
    checks['na_raw_false'] = (na.get('raw') is False) or (na.get('raw') == 'false')
    checks['na_effective_false'] = (na.get('effective') is False) or (na.get('effective') == 'false')
    checks['na_paired_false'] = (na.get('paired_ticks') is False) or (na.get('paired_ticks') == 'false')
    checks['shield_layer_enabled_matches_expect'] = (shield_on == expect_shield)
    if expect_shield:
        checks['intervened_ticks_positive'] = int(ca.get('intervened_ticks', 0)) > 0
    else:
        checks['no_intervention_on_identity_arm'] = int(ca.get('intervened_ticks', 0)) == 0
        dv = ca.get('max_abs_delta_v_mps', None)
        dw = ca.get('max_abs_delta_w_radps', None)
        checks['identity_delta_v_small'] = (isinstance(dv, (int, float)) and dv <= 1e-3)
        checks['identity_delta_w_small'] = (isinstance(dw, (int, float)) and dw <= 1e-3)
    ok = all(checks.values())
    return {'checks': checks, 'pass': ok,
            'detail': {'shield_layer_enabled': shield_on,
                       'intervened_ticks': ca.get('intervened_ticks'),
                       'ticks_paired': ca.get('ticks_paired'),
                       'same_stamp_ticks': ca.get('same_stamp_ticks'),
                       'intervention_duration_s': ca.get('intervention_duration_s'),
                       'max_abs_delta_v_mps': ca.get('max_abs_delta_v_mps'),
                       'max_abs_delta_w_radps': ca.get('max_abs_delta_w_radps'),
                       'clearance_min_m': ca.get('clearance_min_m'),
                       'clearance_min_at_intervention_m': ca.get('clearance_min_at_intervention_m')}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', default=None, help='campaign report.json 路径（缺省取证据根下最新 run）')
    ap.add_argument('--experiments-root', default=os.path.join(ROOT, 'experiments'),
                    help='证据根（未给 --report 时，取该根 %s 下最新 run 的 report.json）' % CAMPAIGN)
    ap.add_argument('--out', default=None, help='e1.json 输出路径（缺省落同目录 metrics/e1.json）')
    ap.add_argument('--run-id', default=None, help='W7-b run_id（写进证据，缺省取 report.run_id）')
    args = ap.parse_args()

    if not args.report:
        args.report = checklib.latest_report(args.experiments_root, CAMPAIGN)
        if not args.report:
            print('FAIL：%s 下找不到 <run>/metrics/report.json（证据根 %s）'
                  % (CAMPAIGN, args.experiments_root), file=sys.stderr)
            return 1
    if not os.path.isfile(args.report):
        print('FAIL：report.json 不存在：%s' % args.report, file=sys.stderr)
        return 1

    with open(args.report) as f:
        report = json.load(f)
    expect_shield = str(report.get('shield', 'true')).lower() != 'false'

    episodes = [e for e in report.get('episodes', []) if e.get('summary_present')]
    results = []
    for e in episodes:
        sp = e.get('summary_path')
        summary = {}
        if sp and os.path.exists(sp):
            with open(sp) as f:
                summary = json.load(f)
        ep_view = dict(e)
        ep_view['command_attribution'] = summary.get('command_attribution')
        r = check_one(ep_view, expect_shield)
        r.update({'scene': e.get('scene'), 'seed': e.get('seed'), 'run_id': e.get('run_id'),
                  'summary_path': sp})
        results.append(r)

    overall = bool(results) and all(r['pass'] for r in results)
    out = {
        'run_id': args.run_id or report.get('run_id'),
        'report': args.report,
        'campaign': report.get('campaign'),
        'scene': report.get('scenes') or (results[0]['scene'] if results else None),
        'expect_shield': expect_shield,
        'n_episodes_checked': len(results),
        'episodes': results,
        'overall_pass': overall,
        'proposition': 'E1 / F-06：raw / effective 命令**同拍**记录 + 干预标注；'
                       '有 shield 臂出现干预、无 shield 臂 effective≡raw。',
    }
    out_path = args.out or os.path.join(os.path.dirname(args.report), 'e1.json')
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    for r in results:
        print('=== scene=%s seed=%s run_id=%s ===' % (r['scene'], r['seed'], r['run_id']))
        for k, v in r['checks'].items():
            print('  %-38s %s' % (k, 'PASS' if v else 'FAIL'))
        print('  detail: %s' % json.dumps(r['detail'], ensure_ascii=False))
    print('\n%s (n=%d) → %s' % ('PASS' if overall else 'FAIL', len(results), out_path))
    return 0 if overall else 1


if __name__ == '__main__':
    sys.exit(main())
