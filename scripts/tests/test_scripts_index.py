"""scripts/ 索引自动核对 —— 索引漂移即测试失败（P0-4）。

**为什么存在**：P0-4 的根因不是"脚本太多"，而是**索引与实际不一致**——
`scripts/` 顶层曾有 32 个脚本，而 `scripts/README.md` 只登记 8 个，多出的 24 个
既无索引也无归属。靠纪律不可持续，故用测试拦（见
`docs/archive/completion-20261031/p0-4-脚本系统瘦身.md#p0-4-goal`）。

**核对的是三方，不是镜像**：

  1. **文件系统** —— `scripts/*.py|sh`、`scripts/research/*.py|sh`、`scripts/archive/*.py|sh`；
  2. **README 索引** —— 从 markdown 的表格里解析出被登记的脚本名（不是硬编码清单）；
  3. **白名单** —— 顶层脚本的**精确集合**（`TOP_LEVEL`），新增必须显式登记。

第 3 点是"防漏记"的关键：只比对"README 表 == 目录内容"会漏掉一种漂移——
**新脚本被加进目录、同时也加了 README 行，但没人问过它该不该在顶层**。
`TOP_LEVEL` 是人工判定过的第二真源，顶层多一个即失败，逼迫新增者先分类。

**失败时的输出**：打印缺失 / 多余 / 未登记的完整差异清单，说明该改哪里，
而不是只报一句 assert 失败。

不启动外部进程、不读 ROS、不联网，纯静态（T0）。

运行：
  python3 -m pytest scripts/tests/test_scripts_index.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
README = SCRIPTS / 'README.md'
RESEARCH = SCRIPTS / 'research'
RESEARCH_README = RESEARCH / 'README.md'
ARCHIVE = SCRIPTS / 'archive'
ARCHIVE_README = ARCHIVE / 'README.md'

# --------------------------------------------------------------------------------------
# 第二真源：顶层允许的长期工具（P0-4 出口判据：≤ 12）
# --------------------------------------------------------------------------------------
# 判定依据：当前阶段（项目收尾 / P1 一键演示入口）会用到的**常驻**工程工具。
# 研究期 / 一次性脚本一律进 research/ 或 archive/，不进此表。
TOP_LEVEL = frozenset({
    'adr_index.py',             # ADR 索引生成 / --check（纯静态）
    'dep_audit.py',             # 包依赖审计
    'episode_runner.py',        # 批量 episode + 三层验收（唯一执行口）
    'evidence_archive.py',      # 证据不可变归档
    'gui_renderer_evidence.py',  # GUI 渲染后端证据（库，无 __main__；episode_runner 导入）
    'lock_px4_failsafe_params.sh',  # PX4 失效安全参数锁定
    'third_party_asset_check.py',   # 第三方资产 provenance
    'toolchain_pin_check.py',       # 工具链 pin 核对
    'toolchain_root_check.py',      # 工具链根注入校验
    'w3_target_driver.py',          # 目标驱动（运行时）
})

TOP_LEVEL_LIMIT = 12

# 由 P0-4 判定迁入 archive/ 的一次性脚本（迁移表须逐条登记）。
ARCHIVE_MIGRATED = frozenset({
    'w7b_full_perception_probe.py',
    'w7c_ab_series.py',
    'w8_measurement_p2_audit.py',
})

EXEC_SUFFIXES = ('.py', '.sh')
# markdown 表格单元格里的脚本引用：`name.py` / [`name.py`](name.py) / `scripts/x/name.sh`
CELL_SCRIPT_RE = re.compile(r'`([A-Za-z0-9_][A-Za-z0-9_.-]*\.(?:py|sh))`')
LINK_SCRIPT_RE = re.compile(r'\]\(([A-Za-z0-9_./-]+\.(?:py|sh))\)')


# --------------------------------------------------------------------------------------
# 解析助手
# --------------------------------------------------------------------------------------

def _scripts_in(directory: Path) -> set[str]:
    """目录**顶层**的执行脚本文件名集合（不递归、跳过 __pycache__）。"""
    if not directory.is_dir():
        return set()
    return {
        p.name for p in directory.iterdir()
        if p.is_file() and p.suffix in EXEC_SUFFIXES
    }


def _top_level_scripts() -> set[str]:
    return _scripts_in(SCRIPTS)


def _table_rows(text: str) -> list[list[str]]:
    """解析 markdown 表格行，返回按 `|` 切分的单元格列表（去掉分隔行与表头分隔）。"""
    rows: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith('|') or not line.endswith('|'):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if not cells:
            continue
        # 跳过 |---|---| 分隔行
        if all(re.fullmatch(r':?-{3,}:?', c) for c in cells if c):
            continue
        rows.append(cells)
    return rows


def _documented_names(readme: Path) -> set[str]:
    """README 表格里登记为**执行脚本**的名字（`*.py` / `*.sh`）。

    只取表格里的代码样式单元格与链接目标，避免把正文叙述里的文件名当登记。
    """
    if not readme.is_file():
        return set()
    text = readme.read_text(encoding='utf-8')
    names: set[str] = set()
    for cells in _table_rows(text):
        for cell in cells:
            for m in CELL_SCRIPT_RE.finditer(cell):
                names.add(Path(m.group(1)).name)
            for m in LINK_SCRIPT_RE.finditer(cell):
                target = Path(m.group(1)).name
                if target.endswith(EXEC_SUFFIXES):
                    names.add(target)
    return names


def _fmt(names: set[str]) -> str:
    return '（空）' if not names else '\n'.join('  - %s' % n for n in sorted(names))


# --------------------------------------------------------------------------------------
# 1. 顶层：精确集合 + 数量上限
# --------------------------------------------------------------------------------------

def test_top_level_matches_curated_set():
    """`scripts/` 顶层必须**恰好**等于人工判定过的长期工具集合。

    多一个 = 有人往顶层平铺了脚本（要么分类，要么显式改 TOP_LEVEL）；
    少一个 = 有人删/移了长期工具却没更新本索引。
    """
    actual = _top_level_scripts()
    missing = TOP_LEVEL - actual
    extra = actual - TOP_LEVEL
    assert not missing, (
        'scripts/ 顶层缺少已登记的长期工具（被删或移动了？若是有意迁移，'
        '请同时更新 scripts/README.md 与 scripts/tests/test_scripts_index.py 的 TOP_LEVEL）：\n%s'
        % _fmt(missing))
    assert not extra, (
        'scripts/ 顶层出现未分类的脚本（新增的？请先判定归属：长期工具 → TOP_LEVEL + '
        'scripts/README.md；研究期 → scripts/research/；一次性 → scripts/archive/）：\n%s'
        % _fmt(extra))


def test_top_level_under_limit():
    """P0-4 出口判据：顶层执行脚本 ≤ 12 个。"""
    actual = _top_level_scripts()
    assert len(actual) <= TOP_LEVEL_LIMIT, (
        'scripts/ 顶层 %d 个执行脚本，超过 P0-4 出口判据上限 %d：\n%s'
        % (len(actual), TOP_LEVEL_LIMIT, _fmt(actual)))


def test_top_level_readme_table_exactly_matches():
    """`scripts/README.md` 顶层表 == 顶层实际文件（双向，漏记与多记都失败）。"""
    actual = _top_level_scripts()
    documented = _documented_names(README)
    undocumented = actual - documented
    phantom = documented - actual
    assert not undocumented, (
        'scripts/README.md 漏记了顶层脚本（索引漂移）：\n%s' % _fmt(undocumented))
    assert not phantom, (
        'scripts/README.md 登记了不存在的顶层脚本：\n%s' % _fmt(phantom))


# --------------------------------------------------------------------------------------
# 2. research/：README 全量准确
# --------------------------------------------------------------------------------------

def test_research_dir_exists_with_readme():
    assert RESEARCH.is_dir(), 'scripts/research/ 不存在（P0-4 要建这个目录）'
    assert RESEARCH_README.is_file(), 'scripts/research/README.md 不存在'


def test_research_readme_exactly_matches():
    """`scripts/research/README.md` 表 == research/ 实际文件（双向）。"""
    actual = _scripts_in(RESEARCH)
    documented = _documented_names(RESEARCH_README)
    undocumented = actual - documented
    phantom = documented - actual
    assert not undocumented, (
        'scripts/research/README.md 漏记了脚本：\n%s' % _fmt(undocumented))
    assert not phantom, (
        'scripts/research/README.md 登记了不存在的脚本：\n%s' % _fmt(phantom))


def test_research_readme_lists_every_script_with_purpose():
    """research 表每行须有用途列 —— 防止"只登记文件名、没有一句话用途"。"""
    text = RESEARCH_README.read_text(encoding='utf-8')
    rows = [c for c in _table_rows(text) if any(
        CELL_SCRIPT_RE.search(cell) or LINK_SCRIPT_RE.search(cell) for cell in c)]
    assert rows, 'scripts/research/README.md 没有登记任何脚本的表格行'
    empty_purpose = []
    for cells in rows:
        # 表头是「文件 | 用途 | 产物 / 依赖」；用途列至少有实质文字
        purpose = cells[1].strip() if len(cells) > 1 else ''
        if len(purpose) < 2:
            name = ''
            for cell in cells:
                m = CELL_SCRIPT_RE.search(cell) or LINK_SCRIPT_RE.search(cell)
                if m:
                    name = Path(m.group(1)).name
                    break
            empty_purpose.append(name)
    assert not empty_purpose, (
        'scripts/research/README.md 这些行缺用途说明：\n%s' % _fmt(set(empty_purpose)))


# --------------------------------------------------------------------------------------
# 3. archive/：P0-4 迁入项登记 + 既有内容未被改名
# --------------------------------------------------------------------------------------

def test_archive_dir_has_readme():
    assert ARCHIVE.is_dir(), 'scripts/archive/ 不存在'
    assert ARCHIVE_README.is_file(), 'scripts/archive/README.md 不存在（P0-4 要建导航）'


def test_archive_readme_documents_every_script():
    """archive 每个脚本都要在 README 中可查（防止 archive 变成新的无索引黑箱）。"""
    actual = _scripts_in(ARCHIVE)
    documented = _documented_names(ARCHIVE_README)
    undocumented = actual - documented
    assert not undocumented, (
        'scripts/archive/README.md 未登记这些脚本（新增一次性脚本后请补表）：\n%s'
        % _fmt(undocumented))


def test_archive_migrated_entries_are_documented_and_present():
    """P0-4 迁入 archive 的 3 个脚本：既在目录里，也在迁移表里，且没被改名。"""
    actual = _scripts_in(ARCHIVE)
    documented = _documented_names(ARCHIVE_README)
    missing_from_disk = ARCHIVE_MIGRATED - actual
    missing_from_index = ARCHIVE_MIGRATED - documented
    assert not missing_from_disk, 'P0-4 迁入 archive 的脚本不见了：\n%s' % _fmt(missing_from_disk)
    assert not missing_from_index, (
        'archive/README.md 缺 P0-4 迁移登记：\n%s' % _fmt(missing_from_index))


def test_no_script_was_deleted_by_curation():
    """P0-4 铁律：**一个脚本都不删**。顶层 + research + archive 的总数不得低于迁移前的 32。

    迁移前顶层 = 32 `.py` + 1 `.sh` = 33 个执行脚本（P0-4 基线实测）。
    archive 既有 65 个历史脚本另计，故下界取 33。
    """
    baseline = 33
    total = (len(_top_level_scripts()) + len(_scripts_in(RESEARCH))
             + len([p for p in ARCHIVE.iterdir()
                    if p.is_file() and p.suffix in EXEC_SUFFIXES]))
    assert total >= baseline, (
        '执行脚本总数 %d < 迁移前基线 %d —— 脚本被删了？P0-4 禁止删除任何脚本'
        % (total, baseline))


# --------------------------------------------------------------------------------------
# 4. 顶层脚本的归属自洽：不许两处同时登记同一个脚本
# --------------------------------------------------------------------------------------

def test_no_script_registered_in_two_layers():
    """同一个脚本名不得同时出现在顶层表、research 表、archive 表 —— 归属唯一。"""
    top = _documented_names(README)
    research = _documented_names(RESEARCH_README)
    archive = _documented_names(ARCHIVE_README)
    dup = (top & research) | (top & archive) | (research & archive)
    assert not dup, '同一脚本被登记在多个归属层（归属必须唯一）：\n%s' % _fmt(dup)


# --------------------------------------------------------------------------------------
# 5. 索引测试自身的有效性（防止"空断言永远通过"）
# --------------------------------------------------------------------------------------

def test_index_checker_detects_injected_drift(tmp_path):
    """反向验证：核对逻辑对"多一个文件 / 少一个登记"确实会失败。

    这条测试守护的是**检测能力**，不是索引内容 —— 若解析器退化成空集合，
    上面所有 `assert not undocumented` 都会静默通过，本条会先失败。
    """
    fake = tmp_path / 'scripts'
    (fake / 'research').mkdir(parents=True)
    (fake / 'archive').mkdir()
    readme = fake / 'README.md'
    readme.write_text(
        '| 文件 | 用途 |\n|---|---|\n| `a.py` | 甲 |\n', encoding='utf-8')
    (fake / 'a.py').write_text('', encoding='utf-8')
    (fake / 'b.py').write_text('', encoding='utf-8')

    # 解析器确实能从表格里取到登记项
    assert _documented_names(readme) == {'a.py'}

    # 注入漂移：目录多一个 b.py，未登记 → 差分必须非空
    actual = _scripts_in(fake)
    documented = _documented_names(readme)
    assert actual - documented == {'b.py'}

    # 反向：登记了不存在的 c.py → 差分必须非空
    readme.write_text(
        '| 文件 | 用途 |\n|---|---|\n| `a.py` | 甲 |\n| `c.py` | 丙 |\n', encoding='utf-8')
    assert _documented_names(readme) - _scripts_in(fake) == {'c.py'}
