#!/usr/bin/env python3
"""`refs/` 隔离核查 —— 外部参照区不得被本仓任何东西引用。

## 为什么存在

`refs/`（用户 2026-11-07 裁定）是**外部参照项目只读区**：源码浅克隆 + 论文原文 + 解读笔记，
整目录不入库（`.gitignore` 的 `/refs/`），`COLCON_IGNORE` 阻断 colcon。

它有一条**铁律**：**与本仓其余部分绝对无关，不可被任何东西引用。**
判据是「删掉整个 `refs/`，本仓构建 / 测试 / 演示 / 文档链接核查必须全部照常通过」。

这条规则靠人记不住：一次顺手写下的 `参见 refs/RACER/`、一段 `sys.path.append('../refs')`、
一个指向 `refs/` 的 YAML 路径，都会把"只进不出的输入区"变成隐式依赖，
换机器（`refs/` 不存在）立刻崩，而且公开 clone 里根本没有这个目录。

**结论去向**：从 `refs/` 学到的东西不得以路径形式回流本仓 —— 决策进 `docs/adr/`、
规范进 `docs/conventions/`、可执行判据进 `tests/`。本核查守的就是这条回流通道。

## 判据（纯静态、秒级、不启进程）

| # | 断言 |
|---|---|
| a | 本仓活文件（`src/` `scripts/` `tests/` `docs/` `toolchain/README.md` 及根级文档）中**不存在**指向 `refs/` 的路径字面量 |
| b | `refs/` 目录若存在，必须带 `COLCON_IGNORE`（阻断 colcon 递归扫描） |
| c | 根 `.gitignore` 必须存在精确规则 `/refs/`（防误提交） |
| d | `docs_link_check.py` 的 `EXCLUDED_PARTS` 必须含 `refs`（防扫描器把本目录当文档源） |

**允许出现 `refs` 字样的位置**（不判失败）：本核查自身、`refs/` 内部文件、
`tests/docs_link_check.py` 的排除声明、根 `.gitignore`、`AGENTS.md` 若登记了隔离事实。
判据 a 扫描时按 `ALLOWED_FILES` 白名单跳过这些。

退出码：0 = PASS；1 = FAIL；2 = 用法/环境错误。

用法：
  python3 tests/check_refs_isolation.py
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# 扫描范围：本仓**活文件**。build/install/log/experiments/refs 与工具链外部树不在此列。
SCAN_DIRS = ('src', 'scripts', 'tests', 'docs', '.coordination', '.agents')
SCAN_ROOT_FILES = ('AGENTS.md', 'README.md', 'GLOSSARY.md', 'pyproject.toml', 'run_demo.sh')
SCAN_EXTS = ('.py', '.md', '.yaml', '.yml', '.xml', '.cpp', '.hpp', '.h', '.c', '.sh',
             '.toml', '.cfg', '.txt', '.json', '.rst', '.launch')

# 允许出现 refs 路径字样的文件（隔离机制自身的登记点）。
ALLOWED_FILES = {
    'tests/check_refs_isolation.py',
    'tests/docs_link_check.py',
    '.gitignore',
    'AGENTS.md',
}

# 不扫描的目录名（生成物 / 外部树 / 证据 / 本区自身）。
SKIP_PARTS = {'build', 'install', 'log', 'refs', 'reference', 'experiments',
              '__pycache__', '.git', '.pytest_cache', 'node_modules'}

# 匹配 `refs/` 路径字面量（前面不能紧跟字母数字或下划线，避免误伤 refs/heads）。
REFS_PATH_RE = re.compile(r'(?<![A-Za-z0-9_./-])refs/')
# 明显属于外部 URL 的片段：github 的 /refs/heads、/refs/tags 等，不算本仓路径。
URL_REFS_RE = re.compile(r'(?:github\.com/[^/\s]+/[^/\s]+/|/archive/)refs/')
# git **内部引用命名空间**：`refs/original` / `refs/heads` / `refs/tags` / `refs/remotes` /
# `refs/notes` / `refs/stash` 是 git 自己的目录结构，与本仓的 refs/ 参照区同名但无关。
# 判据 a 只针对**参照区路径**，不能把 git 术语当违规（ADR-0025 记载清理 `refs/original`）。
GIT_INTERNAL_REFS_RE = re.compile(r'^refs/(?:original|heads|tags|remotes|notes|stash|replace|bisect|worktree)(?:/|\s|$|[`\'"，。、)])')


def _iter_files():
    for d in SCAN_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [n for n in dirnames if n not in SKIP_PARTS]
            for name in filenames:
                if name.endswith(SCAN_EXTS):
                    yield os.path.join(dirpath, name)
    for name in SCAN_ROOT_FILES:
        path = os.path.join(ROOT, name)
        if os.path.isfile(path):
            yield path


def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def scan_refs_paths():
    """判据 a：活文件里不得出现指向 `refs/` 的路径字面量。"""
    violations = []
    for path in _iter_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        if rel in ALLOWED_FILES:
            continue
        text = _read(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in REFS_PATH_RE.finditer(line):
                # 排除 github /archive/refs/ 这类外部 URL
                window = line[max(0, m.start() - 80):m.end() + 40]
                if URL_REFS_RE.search(window):
                    continue
                # 排除 git 内部命名空间（refs/original、refs/heads ...）
                tail = line[m.start():m.start() + 40]
                if GIT_INTERNAL_REFS_RE.match(tail):
                    continue
                violations.append((rel, lineno, line.strip()[:120]))
                break  # 一行只报一次
    return violations


def check_colcon_ignore():
    """判据 b：`refs/` 存在时必须带 COLCON_IGNORE。"""
    refs = os.path.join(ROOT, 'refs')
    if not os.path.isdir(refs):
        return True, 'refs/ 不存在（跳过）'
    marker = os.path.join(refs, 'COLCON_IGNORE')
    if os.path.isfile(marker):
        return True, 'COLCON_IGNORE 存在'
    return False, 'refs/ 存在但缺 COLCON_IGNORE（colcon 会递归扫描）'


def check_gitignore():
    """判据 c：根 .gitignore 必须有精确规则 /refs/。"""
    text = _read(os.path.join(ROOT, '.gitignore'))
    if text is None:
        return False, '.gitignore 不可读'
    for line in text.splitlines():
        if line.strip() == '/refs/':
            return True, '存在精确规则 /refs/'
    return False, '.gitignore 缺 /refs/ 规则（refs/ 会被误提交）'


def check_link_check_exclusion():
    """判据 d：docs_link_check.py 的 EXCLUDED_PARTS 必须含 refs。"""
    text = _read(os.path.join(ROOT, 'tests', 'docs_link_check.py'))
    if text is None:
        return False, 'docs_link_check.py 不可读'
    m = re.search(r'EXCLUDED_PARTS\s*=\s*\{([^}]*)\}', text, re.S)
    if not m:
        return False, 'docs_link_check.py 里找不到 EXCLUDED_PARTS'
    names = set(re.findall(r'"([^"]+)"', m.group(1)))
    if 'refs' in names:
        return True, 'EXCLUDED_PARTS 含 refs'
    return False, 'EXCLUDED_PARTS 缺 refs（扫描器会误入本目录）'


def main():
    ok = True
    print('refs/ 隔离核查')
    print('=' * 60)

    violations = scan_refs_paths()
    if violations:
        ok = False
        print(f'[FAIL] a. 活文件引用了 refs/：{len(violations)} 处')
        for rel, lineno, snippet in violations[:20]:
            print(f'       {rel}:{lineno}  {snippet}')
        if len(violations) > 20:
            print(f'       ... 另有 {len(violations) - 20} 处')
    else:
        print('[PASS] a. 活文件未引用 refs/')

    for label, (passed, msg) in (
        ('b', check_colcon_ignore()),
        ('c', check_gitignore()),
        ('d', check_link_check_exclusion()),
    ):
        print(f'[{"PASS" if passed else "FAIL"}] {label}. {msg}')
        ok = ok and passed

    print('=' * 60)
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
