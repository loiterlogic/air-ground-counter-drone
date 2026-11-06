#!/usr/bin/env python3
"""`tests/` 共用小工具（**只放被多个核查复用、且语义单一**的东西）。

## 为什么有这个文件

`tests/` 下 57 个 `check_*.py` 是从不同时期的一次性核查累积起来的，各自带了一份脚手架：
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


def print_case_table(results):
    """统一的 `name PASS/FAIL` 行输出（多数核查逐字相同）。"""
    for name, value in results.items():
        print('%-30s %s' % (name, 'PASS' if value.get('pass') else 'FAIL'))
