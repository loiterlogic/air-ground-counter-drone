#!/usr/bin/env python3
"""引用纪律闸门 —— 代码中引用设计决策只允许 ADR。

规范见 docs/conventions/引用与注释纪律.md#rule。

三条断言：
  1. **全量不回潮**：代码/配置里**任何**位置（注释、单行字符串、多行 docstring、
     以及配置值）都不得出现非 ADR 的决策引用（评审/批次/契约项编号、章节号、
     真源口语、实验轮次、已退役过程目录路径）。
     2026-11-07 用户裁定「以后在项目中不再看到任何这些情况」，故本闸门**不再只比基线增量**：
     存量必须为零，新增自然也为零。基线 diff 仍保留（`test_guard_bypasses` 用它测"基线不可达必须失败"）。
  2. **ADR 编号可解析**：任何 `ADR-NNNN` 必须在 docs/adr/ 有对应文件。
  3. **文件名不含过程编号**：活跃区文件名不得带 W/R/S/C/F/P/N3/M0 等过程编号。

扫描范围：src/ · scripts/ · tests/ · run_demo.sh · .gitignore · CMakeLists.txt ·
活跃 docs。历史归档 / 研究工具 / 协作台账 / 实验产物 / docs/adr/ 不扫描
（它们按 ADR-0002 / ADR-0025 是历史事实，改写即伪造记录）。

## 为什么把「字符串」也扫进来（2026-11-07 改造）

原实现只扫注释（且只收**多行** STRING）。实测盲区：活跃代码层 127 处命中里，
122 处在**单行字符串**（`description='…W7-c…'`、`help='…'`、`assert` 消息、
`'proposition': '…F-04…'`），闸门一行都拦不住——规则说"只能在代码中引用 ADR"，
机器却只查注释，覆盖面比规则窄得多。现在把字符串纳入：`launch` 参数的
`description` 会显示给用户，`assert` 消息会进报告，都属"代码/配置里的决策引用"。

**仍排除**：`experiments/` 路径串（产物落点，是数据标识不是决策引用，
规范第 37 行明确豁免）。判据用整行是否含 `experiments/` 前缀。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = '860e778'

EXCLUDED_PARTS = {
    '.git', 'build', 'install', 'log', 'toolchain', 'experiments',
    '__pycache__', '.pytest_cache', 'node_modules', 'refs',
}
EXCLUDED_MARKERS = (
    # 冻结历史区（ADR-0002 / ADR-0025：历史事实不重写）
    '/archive/', '/temp/', 'scripts/research/',
    # 反例本体：本文件必须**写出**被禁止的形态（如 R-031）才能测"闸门能否拦住它"。
    # 与 test_reference_discipline.py 同理豁免；新增需同样说明"为什么自指"。
    'scripts/tests/test_reference_discipline.py',
    'scripts/tests/test_guard_bypasses.py',
    'docs/conventions/引用与注释纪律.md',
    'docs/plan/README.md',
    # 路径配置工具：本文件职责就是声明「扫哪些目录」，其中的 `docs/plan/*.md` /
    # `.coordination/*.md` 是扫描范围的事实陈述，不是引用已退役目录陈述当前行为。
    'tests/docs_link_check.py',
    # **2026-11-07 用户裁定：全仓零容忍** —— ADR 目录与协作台账目录不再豁免。
    # ADR 正文里的评审编号已改为可读标题；协作台账的批次/轮次编号已改为自解释说法。
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
    # 2026-11-07 用户续裁：以后不再看到任何这些情况 → 全量清零，不再"存量豁免"。
    (r'\bR-\d{2,3}\b', 'R 编号'),
    (r'\bW\d+(-[a-z])?\b', 'W 编号'),
    (r'\bS-\d+\b', 'S 编号'),
    (r'\bC\d+\b', 'C 编号'),
    (r'\bF-\d+\b', 'F 编号'),
    (r'§\s*\d', '§ 章节号'),
    (r'第\s*\d+(\.\d+)?\s*节', '「第 N 节」'),
    (r'规范\s*\d+\.\d+', '「规范 N.N」'),
    (r'\bround-\d+|\bround\s*\d+', '实验轮次'),
    # 路径类：**只在代码/配置里禁**（文档里是目录结构的事实陈述，如"产物落 scripts/archive/"）
    (r'\.coordination/', '协作台账路径'),
    (r'docs/plan/', '临时计划路径'),
    (r'\bspecs/', '历史规格路径'),
    (r'\bP\d+-\d|\bN3\b|\bM0\b', '过程批次号'),
    # 现行 ADR 编号为 0001–0033；旧体系从 0034 起算。**新增 ADR 时必须同步上调**，
    # 否则新编号会被误判成旧体系（此前上限 0032 就误伤过 0032 本身）。
    # 旧体系 ADR 编号：**在 ADR 索引的合并映射表里有释义**，属可解析的历史沿革，
    # 不是"无指向的裸编号"。故不列入 FORBIDDEN；ADR 索引须持续维护该映射表。
    # 「真源」：**代码/配置里禁**（是口语指代）。文档里的「契约真源」「单一真源」是
    # 项目专有名词（GLOSSARY 定义），不是口语，故不在此列。
    (r'真源', '「真源」'),
)

# 文档里只禁「编号」，不禁路径与术语（它们是文档的正常内容）
DOC_FORBIDDEN = tuple(
    x for x in FORBIDDEN if x[1] not in ('协作台账路径', '临时计划路径', '历史规格路径', '「真源」'))

# 允许的契约条目引用形式：契约没有 ADR 时，用硬约束锚点而非 C1/C10。
CONTRACT_ANCHOR_RE = re.compile(r'docs/adr/0020-[a-z-]+\.md#hc-\d+|#hc-\d+')

# 数据标识豁免：`experiments/` 下的批次目录名是产物落点（ADR-0006），不是决策引用。
DATA_PATH_RE = re.compile(r"experiments/|'experiments'|\"experiments\"")
# 路径形态豁免：`task/<ID>/round-N/` 这类**目录名**是文件系统事实，不是"轮次编号引用"。
# 判据：`round-N` 后紧跟 `/`（目录分隔）或出现在 `(...)` 链接目标里。
DIR_PATH_RE = re.compile(r'round-\d+/')

ADR_REF = re.compile(r'ADR-(\d{4})')
COMMENT_PREFIXES = ('#', '//', '/*', '*', '"""', "'''")

# 文件名层：活跃区文件名不得带过程编号（历史区 archive/research 豁免）。
FILENAME_FORBIDDEN = re.compile(
    r'(?<![a-z0-9])(r\d{2,3}|w\d+[a-z]?|s\d{2}|c\d+|f\d{2}|p\d+-\d|n3|m0)(?![a-z0-9])',
    re.I)


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return True
    return any(m in '/' + rel for m in EXCLUDED_MARKERS)


def _scanned_line_numbers(path: Path) -> set[int]:
    """用 tokenize 精确取出"注释行 + **所有**字符串行"的行号集合。

    为什么不用行首前缀判断：2026-11-06 反例实测，docstring **正文行**不以 `#` 或
    三引号开头，原 `_is_comment_line` 全部漏扫——这正是 ~300 处历史编号既清不掉
    也挡不住新增的原因。tokenize 按词法切分，能准确给出 COMMENT 与 STRING 的区间。

    **2026-11-07 改造：单行字符串也收**。原实现只收多行（`tok.end[0] > tok.start[0]`），
    理由是"单行字符串常量是数据标识"——但实测活跃代码层 127 处命中里 122 处正是
    单行字符串（`description='…W7-c…'`、`assert` 消息、`'proposition': '…'`），
    闸门一行都拦不住。现在字符串一律算"代码/配置里可被人读到的决策引用"。
    数据标识豁免走 `DATA_PATH_RE`（`experiments/` 路径行整行跳过）。

    文件不是合法 Python（语法错误 / 非 .py）时，退回保守判定：整行都扫。
    """
    import tokenize

    lines: set[int] = set()
    try:
        with open(path, 'rb') as fh:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type == tokenize.COMMENT:
                    lines.add(tok.start[0])
                elif tok.type == tokenize.STRING:
                    # 字符串（单行或多行）= 会被人读到的文案，其所有行都属"文本语义"
                    lines.update(range(tok.start[0], tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError, OSError, UnicodeDecodeError):
        return None  # 交给调用方按"整文件可疑"处理
    return lines


def _is_comment_line(line: str) -> bool:
    """行首前缀的快速判定（保留作兜底 / 供非 Python 文件使用）。"""
    s = line.strip()
    if s.startswith(COMMENT_PREFIXES):
        return True
    # 行尾内联注释：行内有 `#` 且不是以引号开头（避免把字符串里的 `#` 当注释）
    return '#' in line and not s.startswith(('"', "'"))


def _hits(line: str, rules=None):
    out = []
    for pat, label in (rules if rules is not None else FORBIDDEN):
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

    2026-11-07 起本函数**不再**是主判据（主判据是全量扫描）；保留它是为了让
    `test_guard_bypasses` 仍能测"基线不可达必须失败"这一失效模式。
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
    return (rel.startswith(('src/', 'scripts/', 'tests/', '.coordination/')) or
            rel in ('run_demo.sh', '.gitignore') or
            p.name in ('CMakeLists.txt', 'package.xml') or
            (rel.startswith('docs/') and p.suffix == '.md'))


def _git_tracked() -> list[str]:
    """入库文件清单（相对仓库根）。用于区分「入库文档」与「本地逐轮过程物」。

    为什么需要：`.coordination/task/` `drafts/` `locks/*.lock` `STOP-*.md` 被 `.gitignore`
    排除，是本地过程物（`.coordination/README.md` 明写"不入库"），属冻结历史；
    把它们纳入扫描会把"当时的逐轮记录"当"当前行为陈述"来改写，即伪造记录（ADR-0002）。
    """
    proc = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise BaselineUnavailable('无法执行 git ls-files；本闸门依赖 git 追踪状态')
    return [f for f in proc.stdout.split('\n') if f]


def _iter_scannable_files():
    """全量枚举活跃区可扫描文件（不依赖 git diff）。"""
    files = []
    for base in ('src', 'scripts', 'tests', 'docs'):
        for p in (ROOT / base).rglob('*'):
            if p.is_file():
                rel = p.relative_to(ROOT).as_posix()
                if _scannable(rel):
                    files.append(rel)
    for rel in ('run_demo.sh', '.gitignore', 'AGENTS.md', 'GLOSSARY.md', 'README.md'):
        if (ROOT / rel).is_file() and _scannable(rel):
            files.append(rel)
    # 协作台账：2026-11-07 起纳入零容忍（原为豁免区）。
    # **只扫入库文件**：`task/` `drafts/` `locks/*.lock` `STOP-*.md` 被 `.gitignore` 排除，
    # 是本地逐轮过程物（`.coordination/README.md` 明写"不入库"）——它们属冻结历史，
    # 改写即伪造记录（ADR-0002）。判据用 git 追踪状态，不用目录名。
    tracked = set(_git_tracked())
    for p in (ROOT / '.coordination').rglob('*.md'):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel in tracked and _scannable(rel):
            files.append(rel)
    return sorted(set(files))


def _scan_hits(rel: str, cache: dict):
    """产出一个文件里所有命中行：(lineno, labels, text)。"""
    p = ROOT / rel
    if rel not in cache:
        cache[rel] = _scanned_line_numbers(p) if p.suffix == '.py' else None
    scanned = cache[rel]
    out = []
    try:
        lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return out
    for i, line in enumerate(lines, 1):
        if scanned is None:
            hit = _is_comment_line(line)
        else:
            hit = i in scanned
        if not hit:
            continue
        # 数据标识豁免：`experiments/` 路径是产物落点，不是决策引用（规范第 37 行）
        if DATA_PATH_RE.search(line):
            continue
        # 目录名豁免：`round-N/` 是文件系统目录名（如 `task/<ID>/round-2/review.md`）
        if DIR_PATH_RE.search(line):
            continue
        rules = DOC_FORBIDDEN if rel.endswith('.md') else FORBIDDEN
        labels = _hits(line, rules)
        # 目录分类表里的目录名属事实陈述，不是引用（见 DIRNAME_FACT_FILES 注释）
        if rel in DIRNAME_FACT_FILES and '](' not in line:
            labels = [x for x in labels if x not in ('协作台账路径', '评审快照路径', '临时计划路径')]
        if labels:
            out.append((i, labels, line.strip()[:110]))
    return out


def test_no_forbidden_references_anywhere():
    """全量：活跃区**任何**注释/字符串都不得出现非 ADR 决策引用（存量为零）。"""
    problems = []
    cache: dict = {}
    for rel in _iter_scannable_files():
        for lineno, labels, text in _scan_hits(rel, cache):
            for label in labels:
                problems.append('%s:%d [%s] %s' % (rel, lineno, label, text))
    assert not problems, (
        '代码/配置里出现禁止的决策引用（docs/conventions/引用与注释纪律.md#rule）：\n  %s\n'
        '改法：换成对应 ADR（`ADR-NNNN`）或契约硬约束锚点 `#hc-N`；过程编号直接删。'
        % '\n  '.join(problems[:80]))


def test_no_new_forbidden_references_since_baseline():
    """增量：基线之后新增的行同样不得出现（保留该断言以覆盖"改动行"路径）。"""
    problems = []
    cache: dict = {}
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
        if DATA_PATH_RE.search(text):
            continue
        if DIR_PATH_RE.search(text):
            continue
        rules = DOC_FORBIDDEN if rel.endswith('.md') else FORBIDDEN
        labels = _hits(text, rules)
        if rel in DIRNAME_FACT_FILES and '](' not in text:
            labels = [x for x in labels if x not in ('协作台账路径', '评审快照路径', '临时计划路径')]
        for label in labels:
            problems.append('%s:%d [%s] %s' % (rel, lineno, label, text.strip()[:100]))
    assert not problems, (
        '新增/改动行出现禁止的决策引用（docs/conventions/引用与注释纪律.md#rule）：\n  %s'
        % '\n  '.join(problems[:60]))


def test_active_filenames_have_no_process_numbers():
    """文件名层：活跃区（src/scripts/tests/docs，历史区除外）不得带过程编号。"""
    problems = []
    for rel in _iter_scannable_files():
        if rel.startswith(('docs/adr/',)):
            continue  # ADR 文件名由 `NNNN-slug.md` 规则约束，slug 见下方专门断言
        name = Path(rel).name
        if FILENAME_FORBIDDEN.search(name):
            problems.append(rel)
    assert not problems, (
        '活跃区文件名带过程编号（应改为按能力命名）：\n  %s' % '\n  '.join(problems))


def test_adr_filenames_have_no_process_numbers():
    """ADR 文件名：`NNNN-slug.md`，slug 里不得带 W/R/S/C/F 等过程编号。"""
    problems = []
    for p in sorted((ROOT / 'docs' / 'adr').glob('*.md')):
        if p.name == 'README.md':
            continue
        if FILENAME_FORBIDDEN.search(p.stem):
            problems.append(p.name)
    assert not problems, (
        'ADR 文件名带过程编号（应按能力命名，编号只保留 NNNN）：\n  %s' % '\n  '.join(problems))


def test_adr_references_resolve():
    missing = []
    files = []
    idx_path = ROOT / 'docs' / 'adr' / 'README.md'
    idx_text = idx_path.read_text(encoding='utf-8', errors='replace') if idx_path.is_file() else ''"'"''"'"
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
            if list((ROOT / 'docs' / 'adr').glob(num + '-*.md')):
                continue
            # 旧体系编号在「合并映射」表里有释义即算可解析——那是"旧号 → 新篇"
            # 查询表，不是指向已删文件。判据：`| 0070 | [0022](...)` 这种首列为编号的行。
            if re.search(r'^\|\s*' + num + r'\s*\|\s*\[', idx_text, re.M):
                continue
            missing.append('%s: ADR-%s' % (p.relative_to(ROOT), num))
    assert not missing, '引用了不存在的 ADR：\n  %s' % '\n  '.join(sorted(set(missing)))
