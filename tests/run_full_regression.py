#!/usr/bin/env python3
"""N3 · `full` 整链定时回归（**拉起完整仿真**，与离线冒烟分开）。

## 定位

[`run_smoke.py`](./run_smoke.py) 是"每次提交跑"的**离线**门槛（秒级、不启仿真）；
本文件是 N3 要求的**另一条**：定时跑一条 `full` 整链，**失败可定位**。
两者职责不重叠，不要互相替代（headless CI 不替代 GUI 验收，见
[N3 实施边界](../docs/plan/N3-持续验证.md#scope)）。

## 为什么是这几个场景

从 `scripts/episode_runner.py` 的登记表里挑**终态各不相同**的最小集，
让一次回归同时覆盖"成功"与"应当失败"两条路径：

| 场景 | 期望终态 | 覆盖什么 |
|---|---|---|
| `s01_static_none_nominal_track` | `TRACKING_SUCCESS` | 静态目标 + 跟踪里程碑（整链最快路径） |
| `s08_static_none_nominal_capture` | `INTERCEPT_CONFIRMED` | 拦截捕获终态 + 火控链 |
| `s10_maneuver_none_fov_timeout` | `MISSION_FAILED` | **负例**：机动目标出视场后应判失败（防"假成功"） |

## 判据（退出码与 tests/ 约定一致）

`0` = 全部场景达到**期望终态**且 `pass=True`；`1` = 任一不达；`2` = 用法 / 环境错误。
`infra` 类失败（`ready=false`、`wall_watchdog_timeout`、`start_message=service unavailable`）
单独标出——它**不是**能力回归，不要与"任务没完成"混为一谈（见
[排障速查](../docs/conventions/整链排障速查.md#dds-transport)）。

## 用法

```bash
python3 tests/run_full_regression.py                 # 默认 3 场景 × seed 0
python3 tests/run_full_regression.py --list          # 只列场景与命令
python3 tests/run_full_regression.py --scenes s01_static_none_nominal_track
python3 tests/run_full_regression.py --timeout 180 --keep-going
```

**前置**：已 `source /opt/ros/jazzy/setup.bash` 与 `source install/setup.bash`；
`toolchain/bin/MicroXRCEAgent` 与 PX4 SITL 二进制在位（`./run_demo.sh doctor` 可查）。
**独占**：整链占用 GZ / PX4 / DDS，**不得**与其它仿真任务并行。
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

# (scene, expected_terminal, 覆盖说明)
SCENES = [
    ('s01_static_none_nominal_track', 'TRACKING_SUCCESS', '静态目标 + 跟踪里程碑'),
    ('s08_static_none_nominal_capture', 'INTERCEPT_CONFIRMED', '拦截捕获终态 + 火控链'),
    ('s10_maneuver_none_fov_timeout', 'MISSION_FAILED', '负例：出视场应判失败'),
]

# 单场景墙钟预算：实测 s01 约 71 s（RTF≈0.90）；留足余量给 PX4 错峰与就绪门。
SCENE_TIMEOUT_S = 300
READY_TIMEOUT_S = 120

GREEN, RED, YELLOW, RESET = '\033[32m', '\033[31m', '\033[33m', '\033[0m'

# infra 类（环境/启动问题），与"任务没打成"区分开
INFRA_OUTCOMES = {'wall_watchdog_timeout', 'infra'}


def _shell(argv):
    """把命令包在 source 之后的 bash 里（ROS 环境只能靠 shell 设置）。"""
    pre = []
    for f in (ROS_SETUP, WS_SETUP):
        if os.path.isfile(f):
            pre.append('. %s >/dev/null 2>&1' % f)
    pre.append('cd %s' % ROOT)
    return ' && '.join(pre + [' '.join(argv)])


def _env():
    """DDS 策略走单一真源，与 run_demo.sh / 测试完全一致（见 ADR-0028）。"""
    env = dict(os.environ)
    env.setdefault('ROS_DOMAIN_ID', '0')
    sys.path.insert(0, os.path.join(ROOT, 'scripts', 'demo'))
    try:
        import dds_transport
        dds_transport.apply(env)
    except Exception:  # noqa: BLE001  选择器不可用时如实降级，不静默改判
        pass
    return env


def run_scene(scene, expected, timeout_s, campaign, seed, verbose):
    run_id = 'n3-%s-%d' % (scene.split('_')[0], seed)
    argv = [sys.executable, os.path.join(ROOT, 'scripts', 'episode_runner.py'),
            '--scenes', scene, '--seeds', str(seed), '--backend', 'full',
            '--mode', 'headless', '--campaign', campaign, '--run-id',
            '%s-%d' % (run_id, int(time.time())),
            '--timeout', str(timeout_s), '--ready-timeout-s', str(READY_TIMEOUT_S)]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(['bash', '-c', _shell(argv)], cwd=ROOT, env=_env(),
                              capture_output=True, text=True, timeout=timeout_s + 120)
        rc, out = proc.returncode, (proc.stdout or '') + (proc.stderr or '')
    except subprocess.TimeoutExpired:
        rc, out = 124, 'TIMEOUT：>%d s\n' % (timeout_s + 120)
    elapsed = time.monotonic() - t0

    # episode_runner 的 report 是唯一判据（不解析日志文本，避免"看起来像成功"）
    rec = None
    try:
        camp_dir = os.path.join(ROOT, 'experiments', campaign)
        cands = sorted((os.path.join(camp_dir, d) for d in os.listdir(camp_dir)),
                       key=os.path.getmtime)
        for d in reversed(cands):
            p = os.path.join(d, 'metrics', 'report.json')
            if os.path.isfile(p):
                with open(p, encoding='utf-8') as f:
                    rep = json.load(f)
                eps = rep.get('episodes') or []
                if eps:
                    rec = eps[0]
                    break
    except (OSError, ValueError):
        rec = None

    if rec is None:
        return {'ok': False, 'infra': True, 'elapsed': elapsed, 'rc': rc,
                'detail': '未找到 report.json（启动阶段失败）', 'log': out[-2000:]}

    got = rec.get('terminal_state')
    outcome = rec.get('outcome_class') or ''
    infra = (not rec.get('ready', False)) or outcome in INFRA_OUTCOMES
    ok = (got == expected) and bool(rec.get('pass'))
    return {'ok': ok, 'infra': infra, 'elapsed': elapsed, 'rc': rc,
            'terminal': got, 'expected': expected, 'outcome': outcome,
            'ready': rec.get('ready'), 'started': rec.get('started'),
            'start_message': rec.get('start_message'),
            'log': (out[-3000:] if verbose else '')}


def main(argv=None):
    ap = argparse.ArgumentParser(description='N3 · full 整链定时回归')
    ap.add_argument('--scenes', nargs='+', default=None,
                    help='只跑指定场景（默认：%s）' % ' '.join(s for s, _t, _d in SCENES))
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--campaign', default='n3-regression')
    ap.add_argument('--timeout', type=float, default=float(SCENE_TIMEOUT_S),
                    help='单场景墙钟上限（秒，默认 %d）' % SCENE_TIMEOUT_S)
    ap.add_argument('--keep-going', action='store_true', help='失败后继续跑剩余场景')
    ap.add_argument('--list', action='store_true', help='只列出场景与命令')
    ap.add_argument('--verbose', action='store_true', help='失败时打印完整输出')
    args = ap.parse_args(argv)

    known = {s: (t, d) for s, t, d in SCENES}
    if args.scenes:
        unknown = [s for s in args.scenes if s not in known]
        if unknown:
            print('未登记的场景：%s\n已登记：%s'
                  % (', '.join(unknown), ', '.join(known)), file=sys.stderr)
            return 2
        todo = [(s, known[s][0], known[s][1]) for s in args.scenes]
    else:
        todo = list(SCENES)

    if args.list:
        print('N3 整链回归（backend=full, headless, seed=%d）' % args.seed)
        for s, t, d in todo:
            print('\n[%s] 期望 %s — %s' % (s, t, d))
            print('  python3 scripts/episode_runner.py --scenes %s --seeds %d '
                  '--backend full --mode headless' % (s, args.seed))
        return 0

    color = sys.stdout.isatty() and os.environ.get('NO_COLOR') is None

    def c(text, code):
        return '%s%s%s' % (code, text, RESET) if color else text

    print('=' * 78)
    print('N3 整链回归 · %d 场景 · backend=full · headless · 单场景上限 %d s'
          % (len(todo), args.timeout))
    print('独占仿真；判据取 episode_runner 的 report.json（不解析日志）')
    print('=' * 78, flush=True)

    results = []
    t_all = time.monotonic()
    for scene, expected, desc in todo:
        sys.stdout.write('%-38s ' % scene)
        sys.stdout.flush()
        r = run_scene(scene, expected, args.timeout, args.campaign, args.seed,
                      args.verbose)
        results.append((scene, expected, r))
        if r['ok']:
            mark = c('OK', GREEN)
        elif r['infra']:
            mark = c('INFRA', YELLOW)
        else:
            mark = c('FAIL', RED)
        print('%-5s %6.1f s  got=%s' % (mark, r['elapsed'], r.get('terminal', 'n/a')))
        if not r['ok'] and not args.keep_going:
            break

    total = time.monotonic() - t_all
    print('-' * 78)
    bad = [(s, r) for s, _e, r in results if not r['ok']]
    infra = [(s, r) for s, r in bad if r['infra']]

    for scene, expected, r in results:
        if r['ok']:
            continue
        print('\n%s %s（期望 %s，实际 %s，outcome=%s）'
              % (c('失败：', RED), scene, expected, r.get('terminal'),
                 r.get('outcome')))
        if r['infra']:
            print('  分类：**infra**（环境/启动问题，不是能力回归）')
            print('  ready=%s started=%s start_message=%r'
                  % (r.get('ready'), r.get('started'), r.get('start_message')))
            print('  先查 docs/conventions/整链排障速查.md#dds-transport 与 #preflight')
        if r.get('log'):
            print(r['log'])

    print('\n合计 %d/%d 场景达标，墙钟 %.1f s'
          % (len(results) - len(bad), len(results), total))
    if not bad:
        print(c('PASS 整链回归通过', GREEN))
        return 0
    if infra:
        print(c('FAIL 整链回归未通过（其中 %d 个是 infra，先修环境再谈能力）'
                % len(infra), YELLOW))
    else:
        print(c('FAIL 整链回归未通过', RED))
    return 1


if __name__ == '__main__':
    sys.exit(main())
