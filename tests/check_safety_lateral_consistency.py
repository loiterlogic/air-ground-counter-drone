#!/usr/bin/env python3
"""横向能力主张的**单一数值**闸门（纯静态，秒级，不启仿真）。

## 它守的是什么

`max_offset` 这一个数字同时出现在**三处**，任一处不同就是两套能力口径：

| # | 位置 | 语义 |
|---|---|---|
| 1 | `src/agc_rl/config/rl.yaml` 的 `control.max_offset` | 动作映射的满偏横向幅值（策略以为能做多少）|
| 2 | `src/agc_ground/config/ground.yaml` 的 `lateral_reach_required_m` | 安全层反解 `SLOW` 下限的输入（安全层按多少校验）|
| 3 | `src/agc_ground/include/agc_ground/safety_policy.hpp` 的默认值 | 离线重放 / 单测用的缺省（**必须**与 2 同值）|

2026-11-13 实测踩过：ADR-0045 的实测证据 E 里 `max_offset` 写 1.0、`ground.yaml` 也写 1.0，
但实测可达只有 0.769 m —— **配置在说一件车做不到的事**，而没有任何门槛能发现。
[ADR-0046](../docs/adr/0046-lateral-escape-capability-narrowing.md#top) 裁定收窄到 0.75 m 后，
本闸门把"三处必须同值"变成可判定的。

## 判据

| # | 断言 |
|---|---|
| a | 三处数值**完全相等**（浮点按 1e-9 容差）|
| b | `lateral_window_s`（反应窗口 T）= 2.0（ADR-0046 (b) 裁定**不放宽**）|
| c | `slow_min_ratio` ∈ (0, 1]（`1.0` 是合法值：实测能力贴着要求 ⇒ 不降速）|
| d | 若 `slow_min_ratio` < 1.0，则必须能通过 `slowRatioFloor()` 反解下限（用同一公式复算）|
| e | ADR-0046 存在且其 Status 含 `accepted`（裁定有出处，不是"某人改了个数"）|

用法：
  python3 tests/check_safety_lateral_consistency.py     # 退出码 0=PASS
"""

import argparse
import json
import math
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
RL_YAML = os.path.join(ROOT, 'src', 'agc_rl', 'config', 'rl.yaml')
GROUND_YAML = os.path.join(ROOT, 'src', 'agc_ground', 'config', 'ground.yaml')
POLICY_HPP = os.path.join(ROOT, 'src', 'agc_ground', 'include', 'agc_ground',
                          'safety_policy.hpp')
ADR = os.path.join(ROOT, 'docs', 'adr', '0046-lateral-escape-capability-narrowing.md')

TOL = 1e-9


def _yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def _policy_default(name):
    """从纯头文件里取某个字段的默认值（`double name{value};`）。"""
    src = checklib.read_text(POLICY_HPP) or ''
    m = re.search(r'double\s+%s\s*\{\s*([-0-9.eE+]+)\s*\}' % re.escape(name), src)
    return float(m.group(1)) if m else None


def slow_ratio_floor(v_cap, w_cap, T, eff, required):
    """复算 `slowRatioFloor()`（与生产同一公式；**不**引用 C++ 实现，独立复算）。"""
    v = max(1e-6, v_cap)
    w = max(1e-6, w_cap)
    T = max(1e-6, T)
    eff = min(1.0, max(1e-6, eff))
    need = required / eff
    lateral = lambda r: (v / w) * (1.0 - math.cos(r * w * T))  # noqa: E731
    if lateral(1.0) < need:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if lateral(mid) >= need:
            hi = mid
        else:
            lo = mid
    return hi


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    rl = _yaml(RL_YAML)['ground_policy_rl']['ros__parameters']['control']
    g = _yaml(GROUND_YAML)['ground_safety_filter']['ros__parameters']
    checks = {}

    rl_val = float(rl['max_offset'])
    gy_val = float(g['lateral_reach_required_m'])
    hpp_val = _policy_default('lateral_reach_required_m')
    same = (hpp_val is not None
            and abs(rl_val - gy_val) <= TOL
            and abs(gy_val - hpp_val) <= TOL)
    checks['a_single_value_everywhere'] = {
        'pass': bool(same),
        'detail': 'rl.yaml=%s ground.yaml=%s safety_policy.hpp=%s（三处必须同值）'
                  % (rl_val, gy_val, hpp_val),
        'values': {'rl_yaml': rl_val, 'ground_yaml': gy_val, 'policy_hpp': hpp_val}}

    window = float(g['lateral_window_s'])
    checks['b_window_frozen'] = {
        'pass': abs(window - 2.0) <= TOL,
        'detail': 'lateral_window_s=%s（ADR-0046 (b)：T=2.0 s 不为迁就能力主张而放宽）' % window}

    ratio = float(g['slow_min_ratio'])
    checks['c_ratio_in_range'] = {
        'pass': 0.0 < ratio <= 1.0,
        'detail': 'slow_min_ratio=%s（(0,1]；1.0 表示"能力贴着要求 ⇒ SLOW 不降速"）' % ratio}

    floor = slow_ratio_floor(float(g['v_cap']), float(g['w_cap']), window,
                             float(g['lateral_eff_ratio']), gy_val)
    checks['d_ratio_meets_escape_floor'] = {
        'pass': ratio + 1e-9 >= floor,
        'detail': 'slow_min_ratio=%s ≥ 反解下限 %.6f（required=%s m / eff=%s）'
                  % (ratio, floor, gy_val, g['lateral_eff_ratio']),
        'floor': round(floor, 6)}

    adr = checklib.read_text(ADR) or ''
    status_ok = bool(re.search(r'## Status\s*\n\s*\n?\s*accepted', adr))
    checks['e_adr_records_the_verdict'] = {
        'pass': status_ok,
        'detail': 'ADR-0046 存在且 Status=accepted（数值变更须有裁定出处）' if status_ok
                  else 'ADR-0046 缺失或其 Status 不是 accepted'}

    failures = [k for k, v in checks.items() if not v['pass']]
    for k, v in checks.items():
        print('  %s  %-34s %s' % ('PASS' if v['pass'] else 'FAIL', k, v['detail']))
    payload = {'pass': not failures,
               'checks': {k: v['pass'] for k, v in checks.items()},
               'detail': checks, 'escape_floor': round(floor, 6)}
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    if failures:
        print('\nFAIL：%d 项不通过：%s' % (len(failures), ', '.join(failures)))
        return 1
    print('\nPASS：横向能力主张三处同值 %s m；T=%.1f s；slow_min_ratio=%.2f（下限 %.4f）'
          % (rl_val, window, ratio, floor))
    return 0


if __name__ == '__main__':
    sys.exit(main())
