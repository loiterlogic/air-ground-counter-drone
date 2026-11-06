#!/usr/bin/env python3
"""入口文件**语法可解析**核查（纯静态，秒级，不启任何仿真）。

## 为什么有这条

2026-11-06 批量改名时，一次正则替换把 `run_demo.sh` 里 6 处空括号删掉
（`fail()` → `fail {`、`d.resolve()` → `d.resolve`），**一键演示入口整条不可用**。
当时 `./run_demo.sh test` 七组全绿、375 个单测全过——因为**没有任何门槛读这个 shell 文件**。
同类误伤（`.strip()` → `.strip`）在 Python 侧被 pytest 抓到过，说明"能跑"比"有人看"可靠。

故本核查把"入口文件至少还能被解析器读懂"变成一条会失败的测试。它不判断行为，只判断
**语法**：一个连 `bash -n` 都过不去的脚本，任何行为断言都没有意义。

## 判据

 a) 所有 **git 跟踪** 的 `*.sh` 通过 `bash -n`（不执行、不 source、不需要 ROS）；
 b) 所有 git 跟踪的 `*.py` 通过 `compile()`（**不**写 `__pycache__`，不 import，无副作用）。

只看跟踪文件：`build/`、`install/`、`experiments/` 里的副本与产物不入判据。

用法：
  python3 tests/check_entry_syntax.py          # 退出码 0=PASS
  python3 tests/check_entry_syntax.py --json
"""

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _tracked(suffix):
    """git 跟踪的指定后缀文件（相对路径）。git 不可用时如实失败，不静默跳过。"""
    proc = subprocess.run(['git', 'ls-files', '*%s' % suffix], cwd=ROOT,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError('git ls-files 失败：%s' % (proc.stderr or '').strip())
    return [p for p in proc.stdout.splitlines() if p.strip()]


def case_a_shell_parses(res):
    """所有跟踪的 shell 脚本必须能被 `bash -n` 解析。"""
    files = _tracked('.sh')
    bad = []
    for rel in files:
        proc = subprocess.run(['bash', '-n', os.path.join(ROOT, rel)],
                              cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            msg = (proc.stderr or '').strip().splitlines()
            bad.append('%s: %s' % (rel, msg[0] if msg else 'exit %d' % proc.returncode))
    res['shell_files'] = len(files)
    res['shell_syntax_errors'] = bad
    res['pass'] = not bad
    return res


def case_b_python_compiles(res):
    """所有跟踪的 Python 文件必须能被 `compile()` 读懂（不 import、不写缓存）。"""
    files = _tracked('.py')
    bad = []
    for rel in files:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding='utf-8') as f:
                src = f.read()
            compile(src, rel, 'exec')
        except (SyntaxError, UnicodeDecodeError) as exc:
            bad.append('%s: %s' % (rel, exc))
    res['python_files'] = len(files)
    res['python_syntax_errors'] = bad
    res['pass'] = not bad
    return res


def case_c_entry_demo_exportable(res):
    """`run_demo.sh` 的入口存在且**没有**残留的"函数定义缺括号"迹象。

  比 `bash -n` 更窄，但给出**可读的失败原因**：一旦有人再误删括号，报错指向具体文件名
  而不是一个 `syntax error near unexpected token`。
    """
    rel = 'run_demo.sh'
    path = os.path.join(ROOT, rel)
    res['entry_exists'] = os.path.isfile(path)
    hits = []
    if res['entry_exists']:
        # bash 的函数定义是 `name() {`。`name {` 不是——误删括号时症状正是后者，
        # 故按**行首标识符 + 花括号**判，不看行尾（行尾注释会把 `{` 带走）。
        bad_def = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*\s*\{')
        with open(path, encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if bad_def.match(line.strip()):
                    hits.append('%s:%d %s' % (rel, i, line.strip()))
    res['function_defs_without_parens'] = hits
    res['pass'] = bool(res['entry_exists'] and not hits)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true', help='只输出 JSON')
    args = ap.parse_args()

    out = {}
    for name, fn in (('a_shell_parses', case_a_shell_parses),
                     ('b_python_compiles', case_b_python_compiles),
                     ('c_entry_defs', case_c_entry_demo_exportable)):
        try:
            out[name] = fn({})
        except Exception as exc:                     # noqa: BLE001
            out[name] = {'pass': False, 'error': '%s: %s' % (type(exc).__name__, exc)}

    ok = all(v.get('pass') for v in out.values())
    if args.json:
        print(json.dumps({'pass': ok, 'cases': out}, indent=2, ensure_ascii=False))
    else:
        for name, v in out.items():
            print('%-26s %s' % (name, 'PASS' if v.get('pass') else 'FAIL'))
            for key, val in v.items():
                if key != 'pass':
                    print('    %s = %r' % (key, val))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
