#!/usr/bin/env python3
"""历史 L4 脚本的**归档登记闸门** + 新口径替代判据的存在性核查（纯静态，秒级）。

## 它守的是什么

2026-11-13 Nav2 地面安全层退役（[ADR-0045](../docs/adr/0045-ground-safety-layer-self-owned.md#top)）后，
`tests/` 下 5 个脚本仍在查 `/collision_monitor/get_state` —— 该服务已不存在，它们会**如实 FAIL**。

按 [ADR-0046](../docs/adr/0046-lateral-escape-capability-narrowing.md#top) (f) 与产物分类，
这 5 个脚本属"历史证据档案"：**原样保留、不改写**（改写即伪造历史记录，ADR-0002）。
但"保留"必须**可判定**，否则会出现两种漂移：

* 有人"顺手"把它们改回能跑（= 伪造历史）；
* 有人把它们删掉/移走，却没人知道新口径判据在哪（= 失去可追溯性）。

本闸门因此断言四件事：

| # | 断言 | 为什么 |
|---|---|---|
| a | 5 个脚本**仍在** `tests/` 下 | 移走/删除即失去历史证据 |
| b | 它们仍引用 `/collision_monitor/get_state` | 证明"它断言的是旧链路"这一登记属实；改成新服务就不再是历史档案 |
| c | 它们**没有**被写进任何**活跃门槛**（`run_smoke.py` 的 `GROUPS`） | 活跃门槛天天红会被忽略，比没有门槛更糟 |
| d | **新口径替代判据**存在且各自可判定 | "归档"必须有去处，不能只说"不再用" |

## 为什么不在这些脚本里加 `pytest.skip`

它们的退出码语义是"断言失败"，改成 skip 等于让"历史断言不成立"这件事**不可见**。
正确做法是：**保留失败**，用本闸门说明"这个失败是预期的、有登记的"，并在活跃门槛里用新判据。

用法：
  python3 tests/check_safety_legacy_scripts.py      # 退出码 0=PASS
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
TESTS = os.path.join(ROOT, 'tests')

# 归档登记的历史脚本 → 它引用的**已退役**对象。
# 新增条目必须同时在 `docs/conventions/路线分支治理.md` 的 5.3 台账登记。
LEGACY_SCRIPTS = {
    'check_scan_self_filter.py': '/collision_monitor/get_state',
    'check_scan_source_loss_stop.py': '/collision_monitor/get_state',
    'check_action_direction_escape.py': '/collision_monitor/get_state',
    'check_actuation_relay_hardening.py': '/collision_monitor/get_state',
    'check_baseline_path_replan.py': '/collision_monitor/get_state',
}

# 新口径替代判据：文件 → 它必须回答的问题（用于人读，不参与断言逻辑）。
REPLACEMENTS = {
    'check_safety_tiers_escape.py': '整链三档 PASS→SLOW→STOP_COLLISION（读安全层自己的 state）',
    'check_safety_layer_live.py': '节点级三档 + 失效语义 + STOP_EMERGENCY（故障注入）',
    'check_safety_scene_geometry.py': '取证场景的几何可行性前置闸门',
    'replay_escape_trace.py': '横向逃逸能力的离线可重放核对',
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    checks = {}

    # a + b：脚本仍在，且仍引用旧服务
    missing, not_referencing = [], []
    for name, token in LEGACY_SCRIPTS.items():
        path = os.path.join(TESTS, name)
        if not os.path.isfile(path):
            missing.append(name)
            continue
        src = checklib.read_text(path) or ''
        if token not in src:
            not_referencing.append(name)
    checks['a_legacy_scripts_still_present'] = {
        'pass': not missing, 'missing': missing}
    checks['b_legacy_scripts_still_reference_retired_service'] = {
        'pass': not not_referencing,
        'detail': '这 5 个脚本必须仍引用 %s（证明它们断言的是旧链路）'
                  % sorted(set(LEGACY_SCRIPTS.values())),
        'not_referencing': not_referencing}

    # c：不得进活跃门槛
    smoke = checklib.read_text(os.path.join(TESTS, 'run_smoke.py')) or ''
    m = re.search(r'^GROUPS\s*=\s*\[', smoke, re.M)
    block = ''
    if m:
        depth = 0
        for i in range(m.end() - 1, len(smoke)):
            if smoke[i] == '[':
                depth += 1
            elif smoke[i] == ']':
                depth -= 1
                if depth == 0:
                    block = smoke[m.end() - 1:i + 1]
                    break
    leaked = [n for n in LEGACY_SCRIPTS if n in block]
    checks['c_legacy_scripts_not_in_active_gate'] = {
        'pass': not leaked,
        'detail': '归档脚本不得进 run_smoke.py 的 GROUPS（活跃门槛必须只跑新口径判据）',
        'leaked': leaked}

    # d：替代判据存在
    missing_rep = [n for n in REPLACEMENTS if not os.path.isfile(os.path.join(TESTS, n))]
    checks['d_replacement_checks_exist'] = {
        'pass': not missing_rep, 'missing': missing_rep,
        'detail': REPLACEMENTS}

    # e：台账登记（治理规范的 5.3 必须提到这 5 个脚本）
    ledger = checklib.read_text(
        os.path.join(ROOT, 'docs', 'conventions', '路线分支治理.md')) or ''
    unregistered = [n for n in LEGACY_SCRIPTS if n not in ledger]
    checks['e_ledger_lists_every_legacy_script'] = {
        'pass': not unregistered,
        'detail': '5.3 保留项台账必须逐个登记（"保留"要可判定，不能只说"不再用"）',
        'unregistered': unregistered}

    failures = [k for k, v in checks.items() if not v['pass']]
    for k, v in checks.items():
        print('  %s  %-46s %s' % ('PASS' if v['pass'] else 'FAIL', k,
                                  v.get('detail', '') if v['pass'] else v))
    payload = {'pass': not failures, 'checks': {k: v['pass'] for k, v in checks.items()},
               'detail': checks}
    if args.json:
        import json
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    if failures:
        print('\nFAIL：%d 项不通过：%s' % (len(failures), ', '.join(failures)))
        return 1
    print('\nPASS：5 个历史脚本已归档登记，且新口径替代判据齐备')
    return 0


if __name__ == '__main__':
    sys.exit(main())
