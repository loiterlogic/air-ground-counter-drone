#!/usr/bin/env python3
"""docs_link_check.py — 项目文档本地链接 / 锚点核查（退出码语义）。

用途
----
扫描项目内 markdown 文档的相对链接，确认：
  1. 目标文件存在；
  2. 目标锚点存在（显式 ``<a id="...">`` / ``<a name="...">``，或标题 slug，或 GitHub ``#L<n>`` 行锚点）；
  3. 报告断链清单。

归属见 ``docs/conventions/目录与命名规范.md#10-产物分类与生命周期``：断言行为、退出码语义 → ``tests/``。

退出码
------
  0  PASS：活跃范围内无断链（历史范围按 ``--scope all`` 时只报告、不计入失败）
  1  FAIL：活跃范围内存在断链
  2  用法 / 环境错误

排除边界（刻意的，不是忽略）
----------------------------
  * 围栏代码块（``` / ~~~）与行内代码 `` `...` `` 内的链接不解析——它们是示例或模板，不是导航。
  * 含 ``<占位符>`` / ``{占位符}`` 的链接目标视为模板占位，跳过（模板由
    ``docs/conventions/spec模板.md`` 维护，其正文是代码块，不参与导航校验）。
  * 外部链接（``http(s)://``、``mailto:``）不做网络请求，只计数。
  * 纯锚点链接（``#anchor``）按同文件校验。
  * 非 markdown 目标只校验文件存在性，不校验锚点（无法解析锚点语义）。
  * 本仓 ``docs/reviews/`` 使用 ``<file>.md:<line>`` 的行号引用惯例（编辑器可点击），
    与 ``#L<n>`` 同义处理为行锚点；两者都要求目标文件存在且行号在范围内。
  * **绝对路径证据引用**（``/home/...``、``/opt/ros/...``）是评审快照对
    ``file:line`` 的取证记录，指向本机源码树或发行版安装树，不是文档导航。
    单列为"证据引用"计数，不判为断链（重写即伪造历史证据，见 ADR-0066(d)）。
  * **``experiments/`` 内的指向**同样是证据引用：该目录按 ADR-0081 本地保留、不入库，
    大归档按 ADR-0064 移入 ``experiments/_archive/``。文档只能记录"当时的 run 在哪里"，
    不能因为本机清理过就判文档错误。计入证据引用，不判为断链。

历史缺失清单
------------
归档文档（``docs/archive/``、``.coordination/archive/``）的断链属**历史事实**：
归档文档反映当时路径，重写会伪造记录（见 ADR-0066 与 ADR-0105）。
因此历史范围的断链**逐条列名**输出，不计入退出码；``--strict-history`` 可把它
们也变成失败，用于将来真正清理时的一次性核查。**不提供**"整段忽略"的宽泛开关。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------------------
# 扫描范围
# --------------------------------------------------------------------------------------

# 活跃文档：当前真源 / 入口 / 索引。断链即失败。
ACTIVE_GLOBS = (
    "AGENTS.md",
    "GLOSSARY.md",
    "docs/*.md",
    "docs/adr/*.md",
    "docs/conventions/*.md",
    "docs/plan/*.md",
    "docs/reviews/**/*.md",
    "docs/toolchain/**/*.md",
    "src/**/README.md",
    "scripts/README.md",
    "tests/README.md",
    "toolchain/README.md",
    ".coordination/*.md",
    ".coordination/roles/*.md",
    ".coordination/archive/**/*.md",
    # 迁移后的规格归档：链接必须与迁移前同等有效（见 P0-3 出口判据）
    "docs/archive/**/*.md",
    # 项目级技能：技能资源本身也是文档，其相对链接必须可解析
    # （P0-3 round-2 修正：只检查"别人指向技能"会漏掉技能内部的断链）
    ".agents/**/*.md",
    # 递归索引 README（docs 各子目录 + scripts/archive），
    # 供 P0-4 的 scripts/README 与目录自动核对复用。
    # 注意：toolchain/ 是外部仓库（不入库、内容不受本仓约束），已由 EXCLUDED_PARTS 排除，
    # 不会因这组 glob 被误扫。
    "scripts/archive/**/README.md",
    "docs/**/README.md",
)

# 本机保留、**不纳入 git** 的目标前缀（`.gitignore` 精确忽略）。
# 指向这些路径的链接在**本地完整检出**里有效，但在公开 clone 里必然缺失：
# 单独归类，既不判断链，也不声称公开 clone 可导航。
LOCAL_ONLY_PREFIXES = (
    "docs/archive/specs/",   # 历史规格：保持不发布（ADR-0081 / ADR-0105）
    "experiments/",          # 实验产物与证据（ADR-0081 / ADR-0064）
    "reference/",            # 旧树归档（只读）
    "toolchain/",            # 外部工具链（仅 README 入库）
    ".trae/",                # 已退役；残留即异常，但语义仍是"本机"
    ".coordination/wake/",   # 已退役叫醒产物
)

# 历史范围：断链只列名，不计入失败。
HISTORICAL_PREFIXES = (
    "docs/archive/",
    ".coordination/archive/",
)

# 永不扫描（生成物 / 外部树 / 实验证据）。
EXCLUDED_PARTS = {
    "build",
    "install",
    "log",
    "reference",
    "experiments",
    ".git",
    "__pycache__",
    ".pytest_cache",
}

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
ANCHOR_RE = re.compile(r"""<a\s+(?:id|name)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)*\1")
# [text](target "title") / ![alt](target) ; 目标内允许一层括号
LINK_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+[\"'(][^)]*)?\s*\)")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
LINE_ANCHOR_RE = re.compile(r"^L(\d+)(?:-L?(\d+))?$")
# 仓库内 ``<file>.md:<line>`` / ``<file>.md:<from>-<to>`` 行号引用惯例
PATH_LINE_SUFFIX_RE = re.compile(r"^(?P<path>.*?\.md):(?P<a>\d+)(?:-(?P<b>\d+))?$")


@dataclass
class Broken:
    source: str
    line: int
    target: str
    reason: str
    historical: bool


@dataclass
class Stats:
    files: int = 0
    links: int = 0
    external: int = 0
    evidence: int = 0
    checked_anchors: int = 0
    skipped_templates: int = 0
    broken_active: list[Broken] = field(default_factory=list)
    broken_historical: list[Broken] = field(default_factory=list)
    local_only_present: list[Broken] = field(default_factory=list)  # 指向本机保留路径，本地可解析
    local_only_missing: list[Broken] = field(default_factory=list)  # 指向本机保留路径，但本地也缺


def _is_excluded(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in EXCLUDED_PARTS for part in rel.parts)


def _is_historical(rel: str) -> bool:
    return any(rel.startswith(prefix) for prefix in HISTORICAL_PREFIXES)


def slugify(text: str) -> str:
    """GitHub 风格标题 slug；保留 CJK（``str.isalnum()`` 对中文为真）。"""
    text = INLINE_CODE_RE.sub(lambda m: m.group(0).strip("`"), text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.lower()
    kept = []
    for ch in text:
        if ch.isalnum() or ch in {" ", "-", "_"}:
            kept.append(ch)
        elif ch == "\u3000":  # 全角空格
            kept.append(" ")
    slug = re.sub(r"-{2,}", "-", "".join(kept).replace(" ", "-"))
    return slug.strip("-")


class Doc:
    """单个 markdown 的锚点集合。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.anchors: set[str] = set()
        self.line_count = 0
        self._parse()

    def _parse(self) -> None:
        try:
            # utf-8-sig 容错 BOM；errors=replace 保证不会因为个别字节失败而静默跳过整个文件
            text = self.path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return
        lines = text.splitlines()
        self.line_count = len(lines)
        in_fence = False
        fence = ""
        seen: dict[str, int] = {}
        for raw in lines:
            fence_match = FENCE_RE.match(raw)
            if fence_match:
                marker = fence_match.group(1)[0] * 3
                if not in_fence:
                    in_fence, fence = True, marker
                elif marker == fence:
                    in_fence, fence = False, ""
                continue
            if in_fence:
                continue
            for anchor in ANCHOR_RE.findall(raw):
                self.anchors.add(anchor)
            heading = HEADING_RE.match(raw)
            if heading:
                base = slugify(heading.group(2))
                if not base:
                    continue
                # GitHub 对重复标题追加 -1 / -2 …
                count = seen.get(base, 0)
                seen[base] = count + 1
                self.anchors.add(base if count == 0 else f"{base}-{count}")


def iter_markdown(root: Path, extra_globs: list[str] | None = None) -> list[Path]:
    """按 ACTIVE_GLOBS（+ 调用方追加）取项目内文档，去重排序。"""
    found: dict[str, Path] = {}
    for pattern in tuple(ACTIVE_GLOBS) + tuple(extra_globs or ()):
        for path in root.glob(pattern):
            if not path.is_file() or path.suffix.lower() != ".md":
                continue
            if _is_excluded(path, root):
                continue
            found[str(path.relative_to(root))] = path
    return [found[key] for key in sorted(found)]


def clean_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return target


def is_template_placeholder(target: str) -> bool:
    return bool(re.search(r"[<>{}]", target))


def resolve_link(source: Path, target: str, root: Path) -> tuple[Path | None, str]:
    """把链接目标解析成文件路径 + 锚点。返回 (文件或 None, 锚点)。"""
    path_part, _, anchor = target.partition("#")
    path_part = path_part.strip()
    if not path_part:
        return source, anchor
    # 仓库惯例：``<file>.md:<line>`` 视作行锚点
    suffix = PATH_LINE_SUFFIX_RE.match(path_part)
    if suffix:
        path_part = suffix.group("path")
        if not anchor:
            anchor = f"L{suffix.group('a')}" + (
                f"-L{suffix.group('b')}" if suffix.group("b") else ""
            )
    # URL 解码常用转义，避免 %20 一类被误判为文件名
    path_part = path_part.replace("%20", " ")
    resolved = (source.parent / path_part).resolve()
    return resolved, anchor


def check_anchor(doc: Doc, anchor: str, source_rel: str, line: int, target: str) -> str | None:
    if not anchor:
        return None
    line_match = LINE_ANCHOR_RE.match(anchor)
    if line_match:
        first = int(line_match.group(1))
        last = int(line_match.group(2) or first)
        if first < 1 or last > doc.line_count:
            return f"行锚点越界（文件 {doc.line_count} 行）"
        return None
    if anchor in doc.anchors:
        return None
    return f"锚点不存在：#{anchor}"


def run(root: Path, strict_history: bool, extra_globs: list[str] | None = None) -> Stats:
    stats = Stats()
    docs: dict[Path, Doc] = {}
    files = iter_markdown(root, extra_globs)

    def doc_for(path: Path) -> Doc:
        if path not in docs:
            docs[path] = Doc(path)
        return docs[path]

    for path in files:
        stats.files += 1
        rel = str(path.relative_to(root))
        historical = _is_historical(rel)
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            stats.broken_historical.append(
                Broken(rel, 0, "", f"读取失败：{exc}", True)
            )
            continue

        in_fence = False
        fence = ""
        for lineno, raw in enumerate(text.splitlines(), start=1):
            fence_match = FENCE_RE.match(raw)
            if fence_match:
                marker = fence_match.group(1)[0] * 3
                if not in_fence:
                    in_fence, fence = True, marker
                elif marker == fence:
                    in_fence, fence = False, ""
                continue
            if in_fence:
                continue
            # 行内代码里的链接是示例，剥掉再匹配
            scanned = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), raw)
            for match in LINK_RE.finditer(scanned):
                raw_target = clean_target(match.group(1))
                if not raw_target:
                    continue
                if SCHEME_RE.match(raw_target) or raw_target.startswith("//"):
                    stats.external += 1
                    continue
                if raw_target.startswith("/"):
                    # 绝对路径 = 评审取证的 file:line 引用，不是文档导航
                    stats.evidence += 1
                    continue
                if "experiments/" in raw_target:
                    # 实验产物本地保留（ADR-0081）/ 大归档（ADR-0064），是证据不是导航
                    stats.evidence += 1
                    continue
                if is_template_placeholder(raw_target):
                    stats.skipped_templates += 1
                    continue
                stats.links += 1
                resolved, anchor = resolve_link(path, raw_target, root)
                broken = Broken(rel, lineno, raw_target, "", historical)
                if resolved is None:
                    continue
                # 目录链接：允许指向目录（README 惯例）
                if resolved.is_dir():
                    continue
                if resolved.exists():
                    # 目标存在：若属"本机保留、不入库"，单独计数——本地可解析，
                    # 但公开 clone 会缺，不能笼统计入"已通过"。
                    try:
                        rel_ok = resolved.relative_to(root).as_posix()
                    except ValueError:
                        rel_ok = ""
                    if rel_ok and any(
                        rel_ok == p or rel_ok.startswith(p) for p in LOCAL_ONLY_PREFIXES
                    ):
                        stats.local_only_present.append(
                            Broken(rel, lineno, raw_target,
                                   "仅本地保留（不被 git 跟踪），公开 clone 中缺失", historical)
                        )
                if not resolved.exists():
                    # 本机保留、不入库的目标（如 docs/archive/specs/）：在**本地完整检出**里
                    # 可解析，但在公开 clone 里必然缺失。单独计数，判为"仅本地存在"，
                    # 既不算断链（本地是对的），也不谎称公开 clone 可导航。
                    try:
                        rel_resolved = resolved.relative_to(root).as_posix()
                    except ValueError:
                        rel_resolved = ""
                    if rel_resolved and any(
                        rel_resolved == p or rel_resolved.startswith(p)
                        for p in LOCAL_ONLY_PREFIXES
                    ):
                        broken.reason = "仅本地保留（不被 git 跟踪），公开 clone 中缺失"
                        stats.local_only_missing.append(broken)
                        continue
                    broken.reason = "目标文件不存在"
                    (stats.broken_historical if historical else stats.broken_active).append(broken)
                    continue
                if resolved.suffix.lower() != ".md" or not anchor:
                    continue
                try:
                    resolved.relative_to(root)
                except ValueError:
                    # 指向项目外的 markdown：无锚点解析义务
                    continue
                stats.checked_anchors += 1
                problem = check_anchor(doc_for(resolved), anchor, rel, lineno, raw_target)
                if problem:
                    broken.reason = problem
                    (stats.broken_historical if historical else stats.broken_active).append(broken)

    if strict_history:
        stats.broken_active.extend(stats.broken_historical)
        stats.broken_historical = []
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="核查项目 markdown 本地链接与锚点（退出码 0=PASS）"
    )
    parser.add_argument("--root", default=None, help="项目根（默认为本脚本../）")
    parser.add_argument(
        "--strict-history",
        action="store_true",
        help="把归档文档的历史断链也计为失败（默认只列名）",
    )
    parser.add_argument("--quiet", action="store_true", help="只打印汇总")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        help="额外扫描的 glob（相对项目根，可重复）。用于迁移前后对同一批文档做对比核查。",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    if not (root / "AGENTS.md").is_file():
        print(f"[ERROR] 未找到项目根：{root}（缺少 AGENTS.md）", file=sys.stderr)
        return 2

    stats = run(root, args.strict_history, args.include)

    if not args.quiet:
        print(f"扫描文件：{stats.files}")
        print(f"本地链接：{stats.links}（锚点校验 {stats.checked_anchors}；外部 {stats.external}；证据绝对路径 {stats.evidence}；模板占位跳过 {stats.skipped_templates}）")

    if stats.broken_active:
        print(f"\n活跃范围断链：{len(stats.broken_active)}")
        for item in sorted(stats.broken_active, key=lambda b: (b.source, b.line, b.target)):
            print(f"  {item.source}:{item.line}  ->  {item.target}  [{item.reason}]")
    else:
        print("\n活跃范围断链：0")

    if stats.broken_historical:
        print(f"\n历史归档断链（不计入失败，逐条列名）：{len(stats.broken_historical)}")
        for item in sorted(stats.broken_historical, key=lambda b: (b.source, b.line, b.target)):
            print(f"  [history] {item.source}:{item.line}  ->  {item.target}  [{item.reason}]")

    total_local = len(stats.local_only_present) + len(stats.local_only_missing)
    if total_local:
        print(
            f"\n指向本机保留路径的链接（不计入断链，也**不**代表公开 clone 可导航）：{total_local}"
        )
        print("  口径：这些目标被 `.gitignore` 精确排除（规格/实验/旧树/工具链），")
        print("        本地完整检出里存在，公开 clone 中必然缺失——属既有发布边界（ADR-0081/0105）。")
        print(f"  本地可解析 {len(stats.local_only_present)} 条；本地也缺失 {len(stats.local_only_missing)} 条")
        if stats.local_only_missing:
            print("  ⚠ 本地也缺失（本机路径不存在，需复核，属真断链）：")
            for item in sorted(stats.local_only_missing, key=lambda b: (b.source, b.line)):
                print(f"    {item.source}:{item.line}  ->  {item.target}")

    if stats.broken_active:
        print("\nFAIL：活跃范围存在断链")
        return 1
    print("\nPASS：活跃文档范围内无断链（本地完整检出口径；本机保留路径单列）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
