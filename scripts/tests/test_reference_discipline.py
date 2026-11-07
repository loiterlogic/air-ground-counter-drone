#!/usr/bin/env python3
"""引用纪律闸门 —— 代码中引用设计决策只允许 ADR。

规范见 docs/conventions/引用与注释纪律.md#rule。

两条断言：
  1. **不回潮**：相对基线（`860e778` 之后的改动）里，代码/配置注释不得新增内部黑话引用
     （评审/批次/契约项编号、章节号、真源口语、实验轮次、已退役过程目录路径）。
     存量历史注释由报告列出，逐块清理，不因历史包袱阻塞提交。
  2. **ADR 编号可解析**：任何 `ADR-NNNN` 必须在 docs/adr/ 有对应文件。

扫描范围：src/ · scripts/ · tests/ · run_demo.sh · .gitignore · CMakeLists.txt ·
活跃 docs 规范。历史归档 / 评审快照 / 协作台账 / 实验产物 / docs/adr/ 不扫描。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '860e778'

EXCLUDED_PARTS = {
    '.git', 'build', 'install', 'log', 'toolchain', 'experiments',
    '__pycache__', '.pytest_cache', 'node_modules',
}
EXCLUDED_MARKERS = (
    '/archive/', '/temp/', '.coordination', 'scripts/research/',
    'docs/adr/', 'tests/w6_r0', 'tests/w5_r0', 'tests/w7', 'tests/w8',
    'scripts/tests/test_reference_discipline.py',
    # 反例本体：本文件必须**写出**被禁止的形态（如 R-031）才能测"闸门能否拦住它"。
    # 与 test_reference_discipline.py 同理豁免；新增需同样说明"为什么自指"。
    'scripts/tests/test_guard_bypasses.py',
    'docs/conventions/引用与注释纪律.md',
    'docs/plan/README.md',
)

# 目录名**事实陈述**白名单：规范文档必须能描述目录结构（如「产物落 scripts/archive/」），
# 这不是"引用已退役的过程目录陈述当前行为"，而是目录分类表本身的内容。
# 判定：整行不含 `](`（不是链接）且只出现目录名作为**名词**。
DIRNAME_FACT_FILES = frozenset({
    'docs/conventions/目录与命名规范.md',
    'docs/conventions/路线分支治理.md',
})

FORBIDDEN = (
    # 2026-11-06 用户裁定：**整个项目以后只能在代码中引用 ADR**。
    # 下列形态一律不许出现在代码/配置里（不是"软建议"，是硬规则）。
    (r'\bR-\d{2,3}\b', 'R 编号'),
    (r'\bW\d+(-[a-z])?\b', 'W 编号'),
    (r'\bS-\d+\b', 'S 编号'),
    (r'\bC\d+\b', 'C 编号'),
    (r'§\s*\d', '§ 章节号'),
    (r'第\s*\d+(\.\d+)?\s*节', '「第 N 节」'),
    (r'规范\s*\d+\.\d+', '「规范 N.N」'),
    (r'\bround-\d+|\bround\s*\d+', '实验轮次'),
    (r'\.coordination/', '协作台账路径'),
    (r'docs/plan/', '临时计划路径'),
    (r'\bspecs/', '历史规格路径'),
    (r'\bP\d+-\d|\bF\d+-\d|\bN3\b|\bM0\b', '过程批次号'),
    # 现行 ADR 编号为 0001–0033；旧体系从 0034 起算。**新增 ADR 时必须同步上调**，
    # 否则新编号会被误判成旧体系（此前上限 0032 就误伤过 0032 本身）。
    (r'ADR-0(?:0(?:3[4-9]|[4-9]\d)|[1-9]\d\d)', '旧体系 ADR 编号'),
    (r'真源', '「真源」'),
)

# 允许的契约条目引用形式：契约没有 ADR 时，用硬约束锚点而非 C1/C10。
CONTRACT_ANCHOR_RE = re.compile(r'docs/adr/0020-[a-z-]+\.md#hc-\d+|#hc-\d+')

ADR_REF = re.compile(r'ADR-(\d{4})')
COMMENT_PREFIXES = ('#', '//', '/*', '*', '"""', "'''")


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return True
    return any(m in '/' + rel for m in EXCLUDED_MARKERS)


def _scanned_line_numbers(path: Path) -> set[int]:
    """用 tokenize 精确取出"注释行 + 文档字符串行"的行号集合。

    为什么不用行首前缀判断：2026-11-06 反例实测，docstring **正文行**不以 `#` 或
    三引号开头，原 `_is_comment_line` 全部漏扫——这正是 ~300 处历史编号既清不掉
    也挡不住新增的原因。tokenize 按词法切分，能准确给出 COMMENT 与多行 STRING 的区间。

    **只收多行字符串（docstring）**：单行字符串常量（如 `PATTERN = "R-031"`）不是注释，
    算进来会把代码里的数据标识误报成"历史编号引用"（本函数首版就踩了这个坑，
    由 test_guard_bypasses 的反例抓到）。判据用 token 跨行，即真实 docstring 形态。

    文件不是合法 Python（语法错误 / 非 .py）时，退回保守判定：整行都扫。
    """
    import tokenize

    lines: set[int] = set()
    try:
        with open(path, 'rb') as fh:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type == tokenize.COMMENT:
                    lines.add(tok.start[0])
                elif tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                    # 多行字符串 = docstring / 多行块注释，其正文行都属"注释语义"
                    lines.update(range(tok.start[0], tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError, OSError, UnicodeDecodeError):
        return None  # 交给调用方按"整文件可疑"处理
    return lines


def _is_comment_line(line: str) -> bool:
    """行首前缀的快速判定（保留作兜底 / 供非 Python 文件使用）。"""
    s = line.strip()
    return s.startswith(COMMENT_PREFIXES) or ('#' in line and not s.startswith(('#', '"', "'")))


def _hits(line: str):
    out = []
    for pat, label in FORBIDDEN:
        if re.search(pat, line):
            out.append(label)
    return out


class BaselineUnavailable(RuntimeError):
    """无法取到基线 diff —— 门禁**不得**静默放行。"""


def _changed_lines():
    """产出 (path, lineno, text)：相对 BASELINE 的新增行（只看代码/配置/活跃文档）。

    基线不可达（浅克隆 / squash / rebase / 未装 git）时**必须显式失败**：
    2026-11-06 反例实测，原实现把非 0 退出码吞成 `return`，导致闸门在那种仓库里
    永远绿——"看着有保护、实际零覆盖"比没有闸门更危险。
    """
    try:
        proc = subprocess.run(
            ['git', 'diff', '--unified=0', BASELINE, '--', '.'],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaselineUnavailable(
            '无法执行 git diff（%s）；本闸门依赖 git 历史，请勿在无 git 环境运行' % exc) from exc
    if proc.returncode != 0:
        raise BaselineUnavailable(
            'git diff 基线 %s 不可达（exit %d）：%s\n'
            '本闸门比较"相对基线的改动"，基线缺失时会**零覆盖**。'
            '请在完整克隆里运行，或显式更新 BASELINE 常量。'
            % (BASELINE, proc.returncode, (proc.stderr or '').strip()[:300]))
    diff = proc.stdout
    cur = None
    lineno = 0
    for raw in diff.splitlines():
        if raw.startswith('+++ b/'):
            cur = raw[6:]
        elif raw.startswith('@@'):
            m = re.search(r'\+(\d+)', raw)
            lineno = int(m.group(1)) if m else 0
        elif raw.startswith('+') and not raw.startswith('+++'):
            if cur:
                yield cur, lineno, raw[1:]
            lineno += 1
        elif raw.startswith(' '):
            lineno += 1


# 可扫描的文本扩展名。二进制资产（.stl / .png / .db3 等）**必须排除**：
# 2026-11-06 盘点发现 `.stl` / `.png` 被当文本读，正则匹配到二进制字节里的随机序列，
# 制造了 542 处假命中（占当时统计的 52%）——存量统计因此长期不可信。
TEXT_SUFFIXES = frozenset({
    '.py', '.md', '.sh', '.yaml', '.yml', '.cpp', '.hpp', '.h', '.txt',
    '.xml', '.xacro', '.sdf', '.json', '.cfg', '.cmake', '.urdf', '.world',
})


def _scannable(rel: str) -> bool:
    p = ROOT / rel
    if not p.is_file() or _is_excluded(p):
        return False
    if p.suffix.lower() not in TEXT_SUFFIXES:
        return False
    return (rel.startswith(('src/', 'scripts/', 'tests/')) or
            rel in ('run_demo.sh', '.gitignore') or
            p.name in ('CMakeLists.txt', 'package.xml') or
            (rel.startswith('docs/') and p.suffix == '.md'))


def test_no_new_forbidden_references():
    problems = []
    cache: dict[str, set[int] | None] = {}
    for rel, lineno, text in _changed_lines():
        if not _scannable(rel):
            continue
        if rel not in cache:
            cache[rel] = _scanned_line_numbers(ROOT / rel) if rel.endswith('.py') else None
        scanned = cache[rel]
        if scanned is None:
            hit = _is_comment_line(text)
        else:
            hit = lineno in scanned
        if not hit:
            continue
        labels = _hits(text)
        # 目录分类表里的目录名属事实陈述，不是引用（见 DIRNAME_FACT_FILES 注释）
        if rel in DIRNAME_FACT_FILES and '](' not in text:
            labels = [x for x in labels if x not in ('协作台账路径', '评审快照路径', '临时计划路径')]
        for label in labels:
            problems.append('%s:%d [%s] %s' % (rel, lineno, label, text.strip()[:100]))
    assert not problems, (
        '新增/改动行出现禁止的决策引用（docs/conventions/引用与注释纪律.md#rule）：\n  %s'
        % '\n  '.join(problems[:60]))


def test_adr_references_resolve():
    missing = []
    files = []
    for base in ('src', 'scripts', 'tests', 'docs'):
        files += [p for p in (ROOT / base).rglob('*') if p.is_file() and not _is_excluded(p)]
    files += [ROOT / 'AGENTS.md', ROOT / 'GLOSSARY.md', ROOT / 'README.md', ROOT / 'run_demo.sh',
              ROOT / '.gitignore']
    for p in files:
        try:
            text = p.read_text(encoding='utf-8', errors='replace')
        except (OSError, UnicodeDecodeError):
            continue
        for m in ADR_REF.finditer(text):
            num = m.group(1)
            if not list((ROOT / 'docs' / 'adr').glob(num + '-*.md')):
                missing.append('%s: ADR-%s' % (p.relative_to(ROOT), num))
    assert not missing, '引用了不存在的 ADR：\n  %s' % '\n  '.join(sorted(set(missing)))
