#!/usr/bin/env python3
"""证据核查可选组 —— 冒烟 `--with-evidence` 的执行体。

## 为什么有这个文件

`tests/` 的 59 个 `check_*.py` 按**运行前提**分三类（口径见 [tests/README](README.md#categories)，
实现见 `checklib.check_categories`）：

| 类 | 数量 | 能否进**默认**冒烟 | 原因 |
|---|---|---|---|
| `static` | 4 | **能**（已在） | 只读源码 / 配置，无产物也全绿 |
| `evidence` | 22 | **不能** | 判据是"历史 run 的证据仍在且自洽"，需要 `experiments/` |
| `needs_sim` | 33 | 不能 | 要活着的 ROS 图 / 仿真 |

`evidence` 这一类**不能**并进默认冒烟，不是因为慢，而是因为它**违反冒烟的两条前提**：
空证据根下它们**如实 FAIL**（实测：22 个在 `/tmp/emptyexp` 下全部非 0），
而默认冒烟承诺"只读 + 无产物也全绿"。硬塞进去只会让门槛天天红、然后被人忽略。

因此做成**可选组**：默认 8 组不变，`--with-evidence` 才追加这一组。
本文件就是这一组的执行体，也可单独跑：

```bash
python3 tests/run_evidence_checks.py --experiments-root /path/to/evidence
```

## 口径

* 逐个跑，**任一非 0 即整组失败**（不做"跳过失败项"的粉饰）；
* 失败时**逐条列出**该核查的退出码与其输出末几行——"缺哪个文件"由核查自己打印，
  本文件只负责不吞掉它；
* 不改变任何核查的判定逻辑：只决定**跑不跑**、传什么证据根。

退出码：`0` = 全部证据核查 PASS；`1` = 有 FAIL；`2` = 用法 / 环境错误（如证据根不存在）。
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402  （tests/ 内共用小工具）

TESTS = os.path.dirname(os.path.realpath(__file__))
DEFAULT_ROOT = os.path.join(os.path.dirname(TESTS), 'experiments')


def evidence_checks():
    """`evidence` 类的核查文件名列表（口径唯一出处：`checklib.check_categories`）。"""
    return checklib.check_categories(TESTS)['evidence']


def run_one(name, experiments_root, timeout_s, verbose):
    path = os.path.join(TESTS, name)
    cmd = [sys.executable, path, '--experiments-root', experiments_root]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        rc, out = proc.returncode, (proc.stdout or '') + (proc.stderr or '')
    except subprocess.TimeoutExpired:
        rc, out = 124, 'TIMEOUT：>%d s\n' % timeout_s
    tail = out.splitlines()
    shown = tail if verbose else tail[-8:]
    print('%-42s %s (exit %d)' % (name, 'PASS' if rc == 0 else 'FAIL', rc))
    if rc != 0:
        for line in shown:
            print('    %s' % line)
    return rc == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='证据核查可选组（冒烟 --with-evidence 的执行体）')
    ap.add_argument('--experiments-root', default=DEFAULT_ROOT,
                    help='证据根（默认 %s）' % DEFAULT_ROOT)
    ap.add_argument('--only', action='append', default=[], metavar='NAME',
                    help='只跑指定核查（可多次），名字可省略 .py')
    ap.add_argument('--timeout', type=int, default=600, help='单个核查超时秒数（默认 600）')
    ap.add_argument('--verbose', action='store_true', help='失败时打印完整输出（默认只打末 8 行）')
    ap.add_argument('--list', action='store_true', help='只列出本组包含哪些核查，不执行')
    args = ap.parse_args(argv)

    names = evidence_checks()
    if not names:
        print('ERROR：分类结果为空，checklib.check_categories 可能已失效', file=sys.stderr)
        return 2

    if args.list:
        print('证据核查可选组 · %d 项（证据根 %s）' % (len(names), args.experiments_root))
        for n in names:
            print('  %s' % n)
        return 0

    if args.only:
        wanted = {n if n.endswith('.py') else n + '.py' for n in args.only}
        unknown = sorted(wanted - set(names))
        if unknown:
            print('未知证据核查：%s' % ', '.join(unknown), file=sys.stderr)
            return 2
        names = [n for n in names if n in wanted]

    if not os.path.isdir(args.experiments_root):
        print('ERROR：证据根不存在：%s' % args.experiments_root, file=sys.stderr)
        return 2

    print('=' * 74)
    print('证据核查可选组 · %d 项 · 证据根 %s' % (len(names), args.experiments_root))
    print('提示：这些核查判"历史证据仍在且自洽"，空证据根下会如实 FAIL')
    print('=' * 74, flush=True)

    failures = []
    for name in names:
        if not run_one(name, args.experiments_root, args.timeout, args.verbose):
            failures.append(name)

    print('-' * 74)
    print('合计 %d/%d 通过' % (len(names) - len(failures), len(names)))
    if failures:
        print('FAIL 证据核查未全绿：%s' % ', '.join(failures))
        return 1
    print('PASS 证据核查全绿')
    return 0


if __name__ == '__main__':
    sys.exit(main())
