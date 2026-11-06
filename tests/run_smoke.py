#!/usr/bin/env python3
"""`./run_demo.sh test` —— 项目**冒烟门槛**（单一入口，5 分钟内全绿）。

## 为什么有这个文件

`tests/` 有 59 个 `*_check.py` 验收核查，但**原本没有"一次跑完并全绿"的入口**。
这些核查里很多要拉起完整 SITL / 整链仿真，跑一遍几十分钟，**不适合**作为"新人改完一行代码
先跑这个"的门槛。本文件只挑**秒级、只读、无副作用**的那几项，构成可信的冒烟集：

| 组 | 断言什么 | 为什么进冒烟集 |
|---|---|---|
| `geometry` | 几何派生链：地图配置文件 → 世界 SDF 展开一致（`tests/check_scene_geometry.py`） | 改地图/材质最常踩的坑，纯静态 |
| `messages` | 9 消息 ABI 字段与顺序不变 + `AgcTaskState` 9 个状态常量 | 契约红线，离线可判 |
| `docs` | 活跃文档本地链接与锚点可解析（`tests/docs_link_check.py`） | 改 README / 计划文档后必跑 |
| `index` | 脚本索引与实际文件集合一致（`scripts/adr_index.py --check` + `scripts/tests/test_scripts_index.py`） | 索引漂移靠测试拦，不靠纪律 |
| `offline` | `scripts/tests/` 全部离线单测（不启 ROS 节点 / 不启仿真） | 演示入口、视觉接线、视觉高亮等回归 |

**不是**要求全部核查全绿——那需要整链环境，语义是"验收"而非"冒烟"
（见 [tests/README](README.md#top)）。

## 用法

```bash
./run_demo.sh test # 全部 5 组
./run_demo.sh test --list       # 只列出组与命令，不执行
./run_demo.sh test --only docs  # 只跑某组（可多次）
./run_demo.sh test --verbose    # 失败时打印完整输出（默认只打最后 20 行）
```

退出码：`0` = 全绿；`1` = 有组失败；`2` = 用法/环境错误。

## 纪律

* **只读**：本文件不写任何项目内文件（pytest 的 `__pycache__` 由 `.gitignore` 排除）；
* **不启仿真**：不 `ros2 launch`、不起 GZ / PX4 / GUI；只调离线脚本与 pytest；
* **预算**：单组超时 300 s（`--timeout` 可调），整轮超预算即判失败并报出耗时；
* 需要 ROS 环境（`xacro` / `agc_msgs`）时先 `source /opt/ros/jazzy/setup.bash` 与
 `source install/setup.bash`；缺环境时**如实报错**，不静默跳过。
"""

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ROS_SETUP = '/opt/ros/jazzy/setup.bash'
WS_SETUP = os.path.join(ROOT, 'install', 'setup.bash')

# 整轮预算：设计目标"5 分钟内全绿"（超预算即返回非 0，见 main()）
TOTAL_BUDGET_S = 300
GROUP_TIMEOUT_S = 300

# 每组：(名称, 说明, 命令前缀列表)
GROUPS = [
    ('geometry', '几何派生链：地图配置 → 世界 SDF',
     [[sys.executable, os.path.join(ROOT, 'tests', 'check_scene_geometry.py')]]),
    ('messages', '9 消息 ABI 字段序 + AgcTaskState 状态常量',
     [[sys.executable, '-m', 'pytest', '-q',
       os.path.join(ROOT, 'scripts', 'tests', 'test_demo_observability.py'),
       '-k', 'message or state']]),
    ('docs', '活跃文档本地链接与锚点',
     [[sys.executable, os.path.join(ROOT, 'tests', 'docs_link_check.py')]]),
    ('index', 'ADR 索引 + 脚本索引一致性',
     [[sys.executable, os.path.join(ROOT, 'scripts', 'adr_index.py'), '--check'],
      [sys.executable, '-m', 'pytest', '-q',
       os.path.join(ROOT, 'scripts', 'tests', 'test_scripts_index.py')]]),
    ('offline', 'scripts/tests 全部离线单测',
     [[sys.executable, '-m', 'pytest', '-q', os.path.join(ROOT, 'scripts', 'tests')]]),
    # 2026-11-04：DDS 契约闸门。**必须留在默认冒烟里**——写死 LOCALHOST 曾两次让整条
    # 收发链静默零送达（本机 `lo` 无 IFF_MULTICAST），每次都花掉一整轮定位。
    # 纯静态、秒级；判据见 tests/check_dds_contract.py 的 case e。
    ('dds', 'DDS 契约：不得写死 LOCALHOST / launch 不覆盖发现范围',
     [[sys.executable, os.path.join(ROOT, 'tests', 'check_dds_contract.py')]]),
    # 「PX4/toolchain 可复现构建逐步固化」（2026-11-04）：pin 清单与实机一致性。
    # 纯只读、秒级；此前有单测但**没接任何门槛**，等于不跑。判据见 ADR-0005(d)。
    # 前提是 `toolchain/` 在本机存在（外部依赖、不入 git）；缺失时如实 FAIL 而不是静默跳过。
    ('toolchain', '工具链 pin 清单与实机一致（ADR-0005）',
     [[sys.executable, os.path.join(ROOT, 'scripts', 'toolchain_pin_check.py')]]),
]

GREEN, RED, YELLOW, DIM, RESET = '\033[32m', '\033[31m', '\033[33m', '\033[2m', '\033[0m'


def _color(text, code, enabled):
    return '%s%s%s' % (code, text, RESET) if enabled else text


def _env():
    """source ROS + 工作区后执行（与 `run_demo.sh` 同口径，避免"少 source"误报失败）。

 DDS 发现范围 / 传输走**配置文件**（`scripts/demo/dds_transport.py`），与
 `run_demo.sh` / `episode_runner` / 测试完全一致。原先此处写死 `LOCALHOST`，
 在 `lo` 无 `IFF_MULTICAST` 的机器上会让任何**跨进程收发**的组静默全 0 失败——
 本组目前恰好不需要收发，才侥幸没暴露（见 docs/conventions/整链排障速查.md#dds-transport）。
    """
    env = dict(os.environ)
    env.setdefault('ROS_DOMAIN_ID', '0')
    sys.path.insert(0, os.path.join(ROOT, 'scripts', 'demo'))
    import dds_transport
    dds_transport.apply(env)
    return env


def _shell(cmd):
    """把命令包在 source 之后的 bash 里（ROS 环境只能靠 shell 设置）。"""
    quoted = ' '.join(_quote(a) for a in cmd)
    pre = []
    if os.path.isfile(ROS_SETUP):
        pre.append('. %s >/dev/null 2>&1' % _quote(ROS_SETUP))
    if os.path.isfile(WS_SETUP):
        pre.append('. %s >/dev/null 2>&1' % _quote(WS_SETUP))
    pre.append('cd %s' % _quote(ROOT))
    pre.append(quoted)
    return ' && '.join(pre)


def _quote(value):
    if not value or any(c in value for c in ' \t"\'$`\\*?[](){}<>|&;#~'):
        return "'" + value.replace("'", "'\\''") + "'"
    return value


def _tail(text, lines=20):
    rows = (text or '').splitlines()
    return '\n'.join(rows[-lines:]) if len(rows) > lines else '\n'.join(rows)


def run_group(name, commands, verbose, timeout_s):
    """跑一组的全部命令；返回 (ok, elapsed, log)。任一条非 0 即该组失败。"""
    t0 = time.monotonic()
    logs = []
    ok = True
    for cmd in commands:
        try:
            proc = subprocess.run(['bash', '-c', _shell(cmd)], cwd=ROOT, env=_env(),
                                  capture_output=True, text=True, timeout=timeout_s)
            rc, out = proc.returncode, (proc.stdout or '') + (proc.stderr or '')
        except subprocess.TimeoutExpired:
            rc, out = 124, 'TIMEOUT：>%d s\n' % timeout_s
        logs.append('$ %s\n[exit %d]\n%s' % (' '.join(cmd), rc, _tail(out)))
        if rc != 0:
            ok = False
            break
    return ok, time.monotonic() - t0, '\n'.join(logs)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True,
                                 description='AGC 冒烟门槛（5 分钟内全绿）')
    ap.add_argument('--only', action='append', default=[], metavar='GROUP',
                    help='只跑指定组（可多次）：%s' % ', '.join(g[0] for g in GROUPS))
    ap.add_argument('--list', action='store_true', help='只列出组与命令，不执行')
    ap.add_argument('--verbose', action='store_true', help='失败时打印完整输出')
    ap.add_argument('--timeout', type=int, default=GROUP_TIMEOUT_S,
                    help='单组超时秒数（默认 %d）' % GROUP_TIMEOUT_S)
    args = ap.parse_args(argv)

    if args.list:
        print('AGC 冒烟门槛（整轮预算 %d s）' % TOTAL_BUDGET_S)
        for name, desc, cmds in GROUPS:
            print('\n[%s] %s' % (name, desc))
            for cmd in cmds:
                print('  %s' % ' '.join(cmd))
        return 0

    known = [g[0] for g in GROUPS]
    unknown = [n for n in args.only if n not in known]
    if unknown:
        print('未知组：%s（可用：%s）' % (', '.join(unknown), ', '.join(known)),
              file=sys.stderr)
        return 2
    selected = [g for g in GROUPS if not args.only or g[0] in args.only]

    color = sys.stdout.isatty() and os.environ.get('NO_COLOR') is None
    print('=' * 74)
    print('AGC 冒烟门槛 · %d 组 · 整轮预算 %d s' % (len(selected), TOTAL_BUDGET_S))
    print('提示：只读、不启仿真；要跑完整验收见 tests/README.md')
    print('=' * 74, flush=True)

    t_all = time.monotonic()
    failures = []
    results = []
    for name, desc, cmds in selected:
        sys.stdout.write('%-10s %-46s ' % (name, desc))
        sys.stdout.flush()
        ok, elapsed, log = run_group(name, cmds, args.verbose, args.timeout)
        results.append((name, ok, elapsed, log))
        print('%s %6.2f s' % (_color('OK' if ok else 'FAIL', GREEN if ok else RED, color),
                              elapsed))
        if not ok:
            failures.append(name)

    total = time.monotonic() - t_all
    print('-' * 74)
    print('合计 %d/%d 组通过，墙钟 %.2f s（预算 %d s）'
          % (len(selected) - len(failures), len(selected), total, TOTAL_BUDGET_S))

    if failures:
        for name, ok, elapsed, log in results:
            if ok:
                continue
            print('\n' + '=' * 74)
            print(_color('失败组：%s（%.2f s）' % (name, elapsed), RED, color))
            print('=' * 74)
            print(log if args.verbose else _tail(log, 30))
        print('\n%s 冒烟未全绿：%s' % (_color('FAIL', RED, color), ', '.join(failures)))
        return 1

    if total > TOTAL_BUDGET_S:
        print('%s 全绿但超预算：%.2f s > %d s'
              % (_color('WARN', YELLOW, color), total, TOTAL_BUDGET_S))
        return 1

    print('%s 冒烟全绿（%.2f s / %d s 预算）'
          % (_color('PASS', GREEN, color), total, TOTAL_BUDGET_S))
    return 0


if __name__ == '__main__':
    sys.exit(main())
