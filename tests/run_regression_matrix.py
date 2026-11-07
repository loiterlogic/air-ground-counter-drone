#!/usr/bin/env python3
"""回归矩阵（自结档研究迁入的四类要求，2026-11-04 落地；现为 4 格）。

## 与另外两个入口的关系

| 入口 | 跑什么 | 何时 | 启仿真 |
|---|---|---|---|
| `run_smoke.py` | 离线冒烟（含 DDS 契约闸门） | 每次提交 | 否 |
| `run_full_regression.py` | `full` 整链 3 场景 | 定时 | 是 |
| **本文件** | **回归矩阵**（4 格，全为正向） | 定时 / 里程碑 | 是 |

## 四类要求（ADR-0029 持续验证）

> **现行 4 格**：原五类中的「无目标负例」已因无承载者移除（见下节），故 `MATRIX` 只有 4 条，
> 且**全为正向**。`_assert_negative` 保留但其判据当前无场景命中。

| 类别 | 场景 | 断言 |
|---|---|---|
| 静态正常 | `s01` | 达 `TRACKING_SUCCESS`；`visibility_rate` 显著 > 0 |
| 动态正常 | `s02` / `s03` | 达 `TRACKING_SUCCESS` |
| 丢失重捕获 | `s06`（`drop_prob=0.1`） | 达 `TRACKING_SUCCESS`（丢包下不 hold 死） |
| ~~无目标负例~~ | ~~`s17`（视场收窄到近零）~~ | **已随 `perception` 轴退役，场景号删除**（见下方"负例为什么不可用"） |

## 负例为什么不可用（2026-11-06 起）

`s17` 原靠 `air_perception` 的 FOV 收窄制造"看不见"。`air_fusion` 退役后
`/agc/air/obs` 无人订阅，该门控不再影响 `/agc/targets`；而唯一的发布者 `gt_adapter`
**无几何门控、不分远近**。「看不见」这一前置条件**无法构造**。
2026-11-06（用户裁定「彻底删」）：`perception` 场景轴、`air_perception` 节点、
`perception_sensors*.yaml` 与 `s17` 场景号一并删除。恢复需给 `gt_adapter` 加可致盲
开关，属**新决策、未立项**，须按 [路线分支治理](../docs/conventions/路线分支治理.md#rule) 重新立项。

下面的加严断言逻辑**保留**，它是恢复该负例后的判据（也是任何"某臂不要求成功"的判据模板）。

## 负例为什么需要"加严断言"

单看"终态是 MISSION_FAILED"**不足以**证明负例成立——链路没起来也会失败。所以额外要求
运行时证据同时满足（取自 `run_logger` 的 summary，而非推断）：

* `visibility_rate == 0.0`：整个 episode **从未**认可见目标；
* `terminal_state == MISSION_FAILED` 且 `reason_code == TIMEOUT`；
* 存在 `mission_fco` 记录时，其 `fco_exposure_s == 0`（没有任何火控机会被"看见"）。

只有这些同时成立，"看不见 → 不成功"才算被证明；否则报 `WEAK`（证据不足），
**不**算通过。宁可报弱证据，也不把环境失败当成负例通过。

## 用法

```bash
python3 tests/run_regression_matrix.py --list
python3 tests/run_regression_matrix.py                 # 全部（默认 truth 路径）
python3 tests/run_regression_matrix.py --only static-normal   # 类别名见 MATRIX
```

退出码：`0` 全类通过；`1` 有失败或证据不足；`2` 用法/环境错误。
"""

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ROS_SETUP = '/opt/ros/jazzy/setup.bash'
WS_SETUP = os.path.join(ROOT, 'install', 'setup.bash')

SCENE_TIMEOUT_S = 300
READY_TIMEOUT_S = 120

GREEN, RED, YELLOW, RESET = '\033[32m', '\033[31m', '\033[33m', '\033[0m'

# (类别, 场景, 期望终态, 说明, 额外断言种类)
MATRIX = [
    ('static-normal', 's01_static_none_nominal_track', 'TRACKING_SUCCESS',
     '静态正常：能看到 → 能成功', 'positive'),
    ('dynamic-normal-linear', 's02_linear_none_nominal_track', 'TRACKING_SUCCESS',
     '动态正常（直线）', 'positive'),
    ('dynamic-normal-maneuver', 's03_maneuver_none_nominal_track', 'TRACKING_SUCCESS',
     '动态正常（机动）', 'positive'),
    # 场景 ID 名中的 `dropout` 为历史遗留标签（`perception` 轴已退役）；该场景当前
    # 的丢包来自 `gt_adapter` 的 `drop_prob=0.1`（config/perception.yaml），与轴无关。
    ('loss-reacquire', 's06_static_none_dropout_track', 'TRACKING_SUCCESS',
     '丢失重捕获（gt_adapter drop_prob=0.1）', 'positive'),
    # 视觉定位路径已于 2026-11-04 退役（用户裁定）：原 `('vision-cost', ..., 'vision')`
    # 一格随之删除。矩阵不再有"感知代价臂"——目标位置始终由真值给出（ADR-0009 (a2)）。
    # 无目标负例（`s17`）亦已随 `perception` 轴于 2026-11-06 删除：`air_fusion` 退役后
    # 没有消费者读取 `air_perception` 的 FOV 门控，而 `gt_adapter` 无几何门控
    # ⇒「看不见」无法构造。见文件头「负例为什么不可用」。
]

INFRA_OUTCOMES = {'wall_watchdog_timeout', 'infra', 'infra_failure'}


def _env():
    env = dict(os.environ)
    env.setdefault('ROS_DOMAIN_ID', '0')
    sys.path.insert(0, os.path.join(ROOT, 'scripts', 'demo'))
    try:
        import dds_transport
        dds_transport.apply(env)
    except Exception:  # noqa: BLE001
        pass
    return env


def _shell(argv):
    pre = []
    for f in (ROS_SETUP, WS_SETUP):
        if os.path.isfile(f):
            pre.append('. %s >/dev/null 2>&1' % f)
    pre.append('cd %s' % ROOT)
    return ' && '.join(pre + [' '.join(argv)])


def _latest_summary(campaign, scene, seed):
    """取本场景的 run_logger summary（run_logger 写到 campaign=w6-task-eval）。"""
    camp = os.path.join(ROOT, 'experiments', 'w6-task-eval')
    if not os.path.isdir(camp):
        return None
    cands = []
    for d in os.listdir(camp):
        p = os.path.join(camp, d, 'metrics', 'summary.json')
        if os.path.isfile(p) and scene.split('_')[0] in d:
            cands.append((os.path.getmtime(p), p))
    if not cands:
        return None
    cands.sort()
    # 只取最近一个（本次运行写入的）
    try:
        with open(cands[-1][1], encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _assert_negative(rec, summary):
    """负例加严断言：必须是"看不见"导致失败，而不是"链路没起来"。"""
    problems = []
    if not summary:
        return ['拿不到 summary.json，无法证明"看不见"（不按通过处理）']
    term = summary.get('terminal_state')
    reason = summary.get('reason_code')
    if term != 'MISSION_FAILED':
        problems.append('终端=%r，期望 MISSION_FAILED' % term)
    if reason != 'TIMEOUT':
        problems.append('reason=%r，期望 TIMEOUT（超时算失败）' % reason)
    vm = summary.get('visibility_metrics') or {}
    rate = vm.get('visibility_rate')
    if rate is None:
        problems.append('visibility_rate 缺失（视场证据不可得）')
    elif abs(float(rate)) > 1e-9:
        problems.append('visibility_rate=%r ≠ 0 → 看见了目标却仍失败，负例不成立' % rate)
    block = summary.get('mission_fco_fixed_budget_v1') or {}
    for m in (block.get('missions') or []):
        fco = m.get('fco_exposure_s')
        if fco is not None and float(fco) > 1e-6:
            problems.append('mission fco_exposure_s=%r > 0 → 存在"看见"的证据' % fco)
    return problems


def _assert_positive(rec, summary):
    problems = []
    if summary:
        vm = summary.get('visibility_metrics') or {}
        rate = vm.get('visibility_rate')
        # 正向场景应能看到目标；太低的 rate 说明链路或视场有问题（不能只看终态）
        if rate is not None and float(rate) <= 0.0:
            problems.append('visibility_rate=%r ≤ 0 → 目标从未被看到，成功不可信' % rate)
    return problems


def run_case(category, scene, expected, desc, kind, seed,
             campaign, timeout_s, verbose):
    run_id = 'n3m-%s-%d' % (scene.split('_')[0], int(time.time()))
    argv = [sys.executable, os.path.join(ROOT, 'scripts', 'episode_runner.py'),
            '--scenes', scene, '--seeds', str(seed), '--backend', 'full',
            '--mode', 'headless', '--campaign', campaign, '--run-id', run_id,
            '--timeout', str(timeout_s), '--ready-timeout-s', str(READY_TIMEOUT_S)]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(['bash', '-c', _shell(argv)], cwd=ROOT, env=_env(),
                              capture_output=True, text=True, timeout=timeout_s + 180)
        out = (proc.stdout or '') + (proc.stderr or '')
    except subprocess.TimeoutExpired:
        out = 'TIMEOUT\n'
    elapsed = time.monotonic() - t0

    rep = os.path.join(ROOT, 'experiments', campaign, run_id, 'metrics', 'report.json')
    rec = None
    if os.path.isfile(rep):
        try:
            with open(rep, encoding='utf-8') as f:
                eps = json.load(f).get('episodes') or []
            rec = eps[0] if eps else None
        except (OSError, ValueError):
            rec = None

    if rec is None:
        return {'ok': False, 'weak': False, 'infra': True, 'elapsed': elapsed,
                'detail': '无 report.json（启动失败）', 'log': out[-2500:]}

    got = rec.get('terminal_state')
    outcome = rec.get('outcome_class') or ''
    infra = (not rec.get('ready', False)) or outcome in INFRA_OUTCOMES
    if infra:
        return {'ok': False, 'weak': False, 'infra': True, 'elapsed': elapsed,
                'terminal': got, 'detail': 'infra（未就绪/看门狗）',
                'ready': rec.get('ready'), 'start_message': rec.get('start_message'),
                'log': out[-2500:]}

    summary = _latest_summary(campaign, scene, seed)
    problems = (_assert_negative if kind == 'negative' else _assert_positive)(rec, summary)

    term_ok = (got == expected) and bool(rec.get('pass'))
    if not term_ok:
        problems.insert(0, '终端=%r，期望 %r' % (got, expected))

    return {'ok': not problems, 'weak': False, 'infra': False, 'elapsed': elapsed,
            'terminal': got, 'expected': expected, 'problems': problems,
            'summary': summary, 'log': (out[-3000:] if verbose else '')}


def main(argv=None):
    ap = argparse.ArgumentParser(description='回归矩阵')
    ap.add_argument('--only', nargs='+', default=None,
                    help='只跑指定类别：%s' % ' '.join(c for c, *_ in MATRIX))
    ap.add_argument('--scene', nargs='+', default=None, help='只跑指定场景')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--campaign', default='n3-matrix')
    ap.add_argument('--timeout', type=float, default=float(SCENE_TIMEOUT_S))
    ap.add_argument('--keep-going', action='store_true')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args(argv)

    known_cats = [c for c, *_ in MATRIX]
    todo = MATRIX
    if args.only:
        bad = [c for c in args.only if c not in known_cats]
        if bad:
            print('未知类别：%s\n可用：%s' % (', '.join(bad), ', '.join(known_cats)),
                  file=sys.stderr)
            return 2
        todo = [m for m in MATRIX if m[0] in args.only]
    if args.scene:
        todo = [m for m in todo if m[1] in args.scene]

    if args.list:
        print('回归矩阵（backend=full, headless, seed=%d, perception=truth 默认）'
              % args.seed)
        for cat, scene, term, desc, kind in todo:
            expect = term if term else '（不要求特定终态：判"感知代价可测 + 证据可区分"）'
            print('\n[%s] %s\n  场景 %s\n  期望 %s\n  断言 %s'
                  % (cat, desc, scene, expect, kind))
        return 0

    color = sys.stdout.isatty() and os.environ.get('NO_COLOR') is None

    def c(text, code):
        return '%s%s%s' % (code, text, RESET) if color else text

    print('=' * 78)
    print('回归矩阵 · %d 格 · backend=full · headless · 单格上限 %d s'
          % (len(todo), args.timeout))
    print('负例按**加严断言**判定（必须证明"看不见"，不是"链路不通"）')
    print('=' * 78, flush=True)

    results = []
    t_all = time.monotonic()
    for cat, scene, expected, desc, kind in todo:
        sys.stdout.write('%-22s %-36s ' % (cat, scene))
        sys.stdout.flush()
        r = run_case(cat, scene, expected, desc, kind,
                     args.seed, args.campaign, args.timeout, args.verbose)
        results.append((cat, scene, expected, desc, kind, r))
        if r['ok']:
            mark = c('OK', GREEN)
        elif r['infra']:
            mark = c('INFRA', YELLOW)
        else:
            mark = c('FAIL', RED)
        print('%-5s %6.1f s' % (mark, r['elapsed']))
        if not r['ok'] and not args.keep_going:
            break

    total = time.monotonic() - t_all
    print('-' * 78)
    bad = [x for x in results if not x[5]['ok']]
    infra = [x for x in bad if x[5]['infra']]

    for cat, _scene, _expected, desc, _kind, r in bad:
        print('\n%s %s（%s）' % (c('未通过：', RED), cat, desc))
        if r['infra']:
            print('  分类：**infra** — 不是能力回归；先查环境')
            print('  ready=%s start_message=%r'
                  % (r.get('ready'), r.get('start_message')))
        for p in (r.get('problems') or [r.get('detail', '')]):
            print('  - %s' % p)
        if r.get('log'):
            print(r['log'])

    print('\n合计 %d/%d 格通过，墙钟 %.1f s'
          % (len(results) - len(bad), len(results), total))
    if not bad:
        print(c('PASS 回归矩阵通过', GREEN))
        return 0
    print(c('FAIL 回归矩阵未通过（%d 个 infra，%d 个能力/证据问题）'
            % (len(infra), len(bad) - len(infra)), RED))
    return 1


if __name__ == '__main__':
    sys.exit(main())
