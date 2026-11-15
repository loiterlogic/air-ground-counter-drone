#!/usr/bin/env python3
"""`tests/` 共用小工具（**只放被多个核查复用、且语义单一**的东西）。

## 为什么有这个文件

`tests/` 下 70 个 `check_*.py` 是从不同时期的一次性核查累积起来的，各自带了一份脚手架：
`dump()` 最多有 33 份副本、`_read()` 18 份、`_load()` 16 份，且**已经漂移**（同名的
`dump()` 有 4 种签名、写不同的目录）。任何"改一处目录结构"的改动都要动几十个文件，
漏一个就静默分叉。

本文件只收**实现逐字相同**、且**不依赖 ROS / 不启仿真**的纯函数。带状态的 harness
（起节点、抓话题、写证据目录）暂不收，避免把差异伪装成统一。

## 口径

* 纯静态：不 import rclpy，不起进程（`git ls-files` 除外，它是只读查询）。
* 不改调用方的退出码语义：这里的函数只返回数据，判定与 `dump()` 仍归各核查自己。
"""

from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


# --------------------------------------------------------------------------------------
# 读文件（原来在 30+ 个核查里各写一遍）
# --------------------------------------------------------------------------------------

def read_text(path):
    """读文本；路径为空 / 不存在返回 None（调用方据此判定"缺证据"）。"""
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def read_text_strict(path):
    """读文本；文件不存在则**抛出**（用于"该文件必须在"的静态核查）。

 与 `read_text` 的分工是**语义**差别而不是风格差别：产物 / 证据类路径允许缺失
 （缺失本身就是判定依据），而源码 / 配置类路径缺失说明核查本身已失效，应当炸掉。
    """
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def load_json(path):
    """读 JSON；路径为空 / 不存在返回 None，**不**吞解析错误（坏证据应报错）。"""
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def code_only(text):
    """剥离整行注释，仅保留可执行行（避免注释里提到 `rm -rf` 之类被误判）。"""
    if not text:
        return ''
    return '\n'.join(
        s for s in (ln.strip() for ln in text.splitlines()) if not s.startswith('#'))


# --------------------------------------------------------------------------------------
# markdown 的"代码 vs 正文"切分
# --------------------------------------------------------------------------------------

_FENCE = re.compile(r'^[ \t]*(```|~~~).*?^[ \t]*\1', re.S | re.M)


def strip_code(text):
    """去掉 markdown 的**围栏代码块**与**行内代码**，只留正文。

 用途：判"文档正文有没有用章节号引用"时，写在反引号里的示例是**说明规则的例子**，
 不是引用；把示例当违规会让规则文本和它自己的门禁互相打架（本仓真实发生过：
 `引用与注释纪律.md` 里的示例让两个核查长期恒 FAIL，真回归被淹没成噪声）。
    """
    if not text:
        return ''
    body = _FENCE.sub('', text)
    body = re.sub(r'`[^`\n]*`', '', body)
    return body


def section_number_hits(root=None, subdir='docs'):
    """返回 `[(相对路径, 行号, 行文本)]`：正文里用章节号（形如 S 符号加数字）引用的位置。

 只扫 `.md`，只扫给定子目录（默认 `docs/`）。代码块与行内代码已剔除，见 `strip_code`。
    """
    base = os.path.join(root or ROOT, subdir)
    hits = []
    for dirpath, _dirnames, filenames in os.walk(base):
        for fn in sorted(filenames):
            if not fn.endswith('.md'):
                continue
            path = os.path.join(dirpath, fn)
            text = read_text(path) or ''
            body = strip_code(text)
            for i, line in enumerate(body.splitlines(), 1):
                if re.search(r'§\s*[0-9]', line):
                    hits.append((os.path.relpath(path, root or ROOT), i, line.strip()))
    return hits


# --------------------------------------------------------------------------------------
# 核查分类（"哪些能进默认冒烟"的**机械口径**，见 tests/README.md#categories）
# --------------------------------------------------------------------------------------

CATEGORIES = ('static', 'evidence', 'needs_sim')

_IMPORTS_RCLPY = re.compile(r'^\s*(?:import\s+rclpy|from\s+rclpy\b)', re.M)


def check_categories(tests_dir=None):
    """把 `check_*.py` 按**运行前提**分三类（只读源码字面，不 import 任何东西）。

    * `needs_sim` —— `import rclpy`：判定要活着的 ROS 图 / 仿真；
    * `evidence`  —— 不 import rclpy，但接受 `--experiments-root`：判定涉及 `experiments/`
      （读历史 run 的证据，或把本次结果写成证据）；
    * `static`    —— 两者皆无：纯静态，只读源码 / 配置，**可以**进默认冒烟。

    返回 `{类别: [文件名...]}`（按文件名排序）。`tests/check_doc_counts.py` 的计数闸门与
    `tests/run_smoke.py --with-evidence` 的可选组**共用这一份口径**：分类只写在文档里、
    实际靠人记，就是本仓反复出现的漂移形态。
    """
    base = tests_dir or os.path.join(ROOT, 'tests')
    groups = {name: [] for name in CATEGORIES}
    for fn in sorted(os.listdir(base)):
        if not (fn.startswith('check_') and fn.endswith('.py')):
            continue
        src = read_text(os.path.join(base, fn)) or ''
        if _IMPORTS_RCLPY.search(src):
            groups['needs_sim'].append(fn)
        elif '--experiments-root' in src:
            groups['evidence'].append(fn)
        else:
            groups['static'].append(fn)
    return groups


def latest_run_id(experiments_root, campaign):
    """`<root>/<campaign>/` 下最新的 run 目录名；不存在返回 None。

    run 目录名以时间戳开头（`YYYYMMDD-...`），字典序即时间序。
    """
    base = os.path.join(experiments_root, campaign)
    if not os.path.isdir(base):
        return None
    names = sorted(n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n)))
    return names[-1] if names else None


def latest_report(experiments_root, campaign):
    """最新一份 `<root>/<campaign>/<run>/metrics/report.json`；没有返回 None。

    用于"只给证据根、不指定 run"的调用口径：**取最新**是显式规则，不是"随便挑一个"。
    """
    base = os.path.join(experiments_root, campaign)
    if not os.path.isdir(base):
        return None
    for name in reversed(sorted(n for n in os.listdir(base)
                                if os.path.isdir(os.path.join(base, n)))):
        path = os.path.join(base, name, 'metrics', 'report.json')
        if os.path.isfile(path):
            return path
    return None


# --------------------------------------------------------------------------------------
# 证据落盘（**只提供路径与写 JSON**，目录布局由调用方决定）
# --------------------------------------------------------------------------------------

def write_json(path, payload):
    """写 JSON（UTF-8 不转义、缩进 2）；父目录不存在则创建。返回路径。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def dump(res, out_dir, filename='check.json', infra=False, notes=None,
         width=30, detail=False, mirror=None, omit=(), detail_keys=None,
         quiet_on_error=False):
    """**唯一的证据落盘 + 报告 + 退出码**实现（原来 33 份 `dump()` 副本，4 种签名）。

    | 参数 | 含义 |
    |---|---|
    | `res` | 结果字典；`res['tests']` 是 `{name: {'pass': bool, ...}}`，`res['overall_pass']` 决定成败 |
    | `out_dir` | 证据目录（run 目录）；`filename` 相对它，可含子目录（如 `'metrics/r025.json'`） |
    | `filename` | 落盘文件名，默认 `check.json` |
    | `infra` | 基础设施失败（不是能力失败）→ 退出码 **2**，与 `1`（判定失败）区分开 |
    | `notes` | 可选 `[(label, value)]`，在测试表之后逐条打印（各核查自己的附加诊断）；
      也接受 `callable(res) -> [(label, value)]`（需要按 `res` 现算的诊断） |
    | `detail` | `False` 只打名字；`'inline'` 同行附其余键（dict 形式）；`'lines'` 每个键一行；
      `'raw'` 同行直接 `%s` 整个测试字典（少数核查的既有口径） |
    | `detail_keys` | `detail='inline'` 时**只**打这些键，且以 `k=v` 形式（`None` = 全打，以 dict 形式） |
    | `mirror` | 可选 `[相对路径...]`，把**同一份** payload 再写一份（历史上 `rXXX/check.json`
      + `metrics/rXXX.json` 双写）——双写是**同一个实现**，不是第二份逻辑 |
    | `omit` | `detail='inline'` 时**不**打印的键（如 `pids` 这类噪声） |
    | `quiet_on_error` | `res` 带 `error` 时**只**打 `error` 与落盘路径，不打测试表（少数核查的既有口径） |

    **退出码语义**（所有副本归一到这里，`infra` 优先）：
    `infra=True` → 2；否则 `overall_pass` → 0，不通过 → 1。

    为什么不各自保留：同名的 `dump()` 曾有 4 种签名（`out_dir` / `run_dir` / `args` /
    `filename`），"改一处目录结构"要动几十个文件，漏一个就静默分叉——这正是本仓
    [ADR-0006](../docs/adr/0006-experiment-artifacts-and-evidence-discipline.md#top)
    要求"证据落盘只有一个实现"的原因。
    """
    path = write_json(os.path.join(out_dir, filename), res)
    for extra in (mirror or ()):
        write_json(os.path.join(out_dir, extra), res)
    if quiet_on_error and 'error' in res:
        print('error:', res['error'])
        print('-> %s' % path)
        if infra:
            return 2
        return 0 if res.get('overall_pass') else 1
    for name, t in (res.get('tests') or {}).items():
        line = '%-*s %s' % (width, name, 'PASS' if t.get('pass') else 'FAIL')
        if detail == 'inline':
            if detail_keys is None:
                line += '  %s' % {k: v for k, v in t.items()
                                  if k != 'pass' and k not in omit}
            else:
                line += '  ' + ' '.join('%s=%s' % (k, t.get(k)) for k in detail_keys)
        elif detail == 'raw':
            line += '  %s' % t
        print(line)
        if detail == 'lines':
            for k, v in t.items():
                if k != 'pass':
                    print('      %s = %s' % (k, v))
    for label, value in ((notes(res) if callable(notes) else notes) or ()):
        print('%s %s' % (label, value))
    if 'error' in res:
        print('error:', res['error'])
    ok = bool(res.get('overall_pass'))
    print('\n%s -> %s' % ('PASS' if ok else 'FAIL', path))
    if infra:
        return 2
    return 0 if ok else 1


def print_case_table(results):
    """统一的 `name PASS/FAIL` 行输出（多数核查逐字相同）。"""
    for name, value in results.items():
        print('%-30s %s' % (name, 'PASS' if value.get('pass') else 'FAIL'))


if __name__ == "__main__":
    # 本文件是**库，不是核查**：没有任何 `main()`。若被当脚本执行（例如
    # `tests/run_all.py --all` 的旧版发现逻辑），静默退 0 会被记成 PASS——
    # 这正是"看着有保护、实际零覆盖"。故显式以退出码 2 拒绝。
    import sys
    print('checklib.py 是共用库，不是可执行的验收核查（见 tests/README.md#top）', file=sys.stderr)
    raise SystemExit(2)
