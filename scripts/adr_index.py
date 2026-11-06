#!/usr/bin/env python3
"""adr_index.py — 从 docs/adr/*.md 生成 ADR 索引（`docs/adr/README.md`）。

为什么自动生成
--------------
ADR 是"只追加、不重写"的决策记录，手写索引必然漂移。索引只从**文件本身**读：

 * 编号：文件名前缀 `NNNN-`
 * 标题：文件内第一个 `# ` 一级标题
 * Status：`## Status` 节的第一段非空正文（保留完整原文，含括号里的日期/来源/限定）
 * 结论：`## 决策` / `## 背景与决策` / `## Decision` 节的首段（截断到一行），缺失则留空

**不猜状态**：状态就是 `## Status` 里写的原文；脚本不从标题或正文推断
`accepted`，也不把"暂停"当成"废止"（暂停记在 plan 的方向索引里，不是 ADR 状态）。

用法
----
    python3 scripts/adr_index.py            # 生成/覆盖 docs/adr/README.md
    python3 scripts/adr_index.py --check    # 只校验，索引与 ADR 不一致 -> 退出码 1
    python3 scripts/adr_index.py --stdout   # 打印到标准输出，不写文件

退出码
------
 0 成功 / 校验通过
  1  校验不一致（`--check`）
 2 用法或环境错误

归属：`scripts/`（长期工具，可重跑、结果确定），见 `docs/conventions/目录与命名规范.md#10-产物分类与生命周期`。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

INDEX_NAME = "README.md"
NAME_RE = re.compile(r"^(\d{4})-(.+)\.md$")
H1_RE = re.compile(r"^# +(.+?)\s*$")
H2_RE = re.compile(r"^## +(.+?)\s*$")

STATUS_HEADINGS = ("status",)
DECISION_HEADINGS = ("决策", "背景与决策", "decision", "决策（已采纳 (b)）")

MAX_CONCLUSION = 150


def read_sections(text: str) -> tuple[str, dict[str, str], list[str]]:
    """返回 (一级标题, {二级标题: 该节正文}, 按出现顺序的二级标题列表)。"""
    lines = text.splitlines()
    title = ""
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    current: str | None = None
    in_fence = False
    for raw in lines:
        if raw.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            if current is not None:
                sections[current].append(raw)
            continue
        if not in_fence:
            h1 = H1_RE.match(raw)
            if h1 and not title:
                title = h1.group(1).strip()
                continue
            h2 = H2_RE.match(raw)
            if h2:
                current = h2.group(1).strip()
                if current not in sections:
                    sections[current] = []
                    order.append(current)
                continue
        if current is not None:
            sections[current].append(raw)
    return title, {k: "\n".join(v) for k, v in sections.items()}, order


def first_paragraph(body: str) -> str:
    """取节内第一段非空正文（跳过标题行、水平线、显式锚点、列表与表头噪声）。

 * 以 `###` 子标题开头的节（合并篇常见：`## 决策` 后直接是 `### (a) …`）跳过子标题行本身，
 继续取子标题下的正文——否则索引「结论」列只会是子标题文字，读不出决定内容；
 * `<a id="…"></a>` 显式锚点行同理跳过（它是导航设施，不是结论）；
 * **表格**压成一句话；表头行（紧跟 `|---|` 分隔行的那行）跳过，否则结论列是列名碎片；
 * 列表项去掉行首 `- ` / `1. ` 标记，避免结论列出现悬空破折号。
    """
    lines = [raw.strip() for raw in body.splitlines()]
    chunks: list[str] = []
    for idx, line in enumerate(lines):
        if not line:
            if chunks:
                break
            continue
        if line.startswith(("---", "***", "___")) and len(line) <= 4:
            if chunks:
                break
            continue
        if not chunks and (line.startswith("#") or line.startswith("<a ")):
            continue  # 子标题 / 显式锚点：跳过，继续找正文
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            cells = [c for c in cells if c and not set(c) <= {"-", ":"}]
            if not cells:
                continue  # 表格分隔行
            nxt = next((x for x in lines[idx + 1:] if x), "")
            if nxt.startswith("|") and set(nxt) <= set("|-: "):
                continue  # 表头行：下一行是分隔行
            line = " · ".join(cells)
        else:
            line = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", line)
        if line:
            chunks.append(line)
    return " ".join(chunks)


def clean_status(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^[-*]\s*", "", text)
    return text


def clean_conclusion(text: str) -> str:
    text = text.strip()
    # 只剥「列表标记 + 空白」；不能剥掉**加粗**开头的 `*`（旧写法会把 `**X**` 削成 `*X**`）
    text = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", text)
    text = re.sub(r"^\([a-z]\)\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    # 表格行压成一句话
    if text.startswith("|"):
        cells = [c.strip() for c in text.strip("|").split("|")]
        text = " · ".join(c for c in cells if c and not set(c) <= {"-", ":"})
    text = text.replace("|", "\\|")
    if len(text) > MAX_CONCLUSION:
        text = text[: MAX_CONCLUSION - 1].rstrip() + "…"
    return text


MERGED_RE = re.compile(r"由\s*(?:ADR-)?(\d{4})((?:\s*[/、,]\s*(?:ADR-)?\d{4})*)\s*合并")


def parse_merged_from(status: str) -> list[str]:
    """从 `Status` 的「由 ADR-00NN / 00MM 合并」一句里取出被合并的旧编号（按出现顺序去重）。

 只为在索引里留一份**合并映射**：读旧编号的人能查到它现在归哪篇。取不到就返回空列表，
 不猜。
    """
    found: list[str] = []
    for m in MERGED_RE.finditer(status):
        for num in re.findall(r"\d{4}", m.group(0)):
            if num not in found:
                found.append(num)
    return found


def collect(adr_dir: Path) -> list[dict[str, str]]:
    entries = []
    for path in sorted(adr_dir.glob("*.md")):
        if path.name == INDEX_NAME:
            continue
        match = NAME_RE.match(path.name)
        if not match:
            continue
        number, slug = match.group(1), match.group(2)
        title, sections, order = read_sections(path.read_text(encoding="utf-8", errors="replace"))

        status = ""
        for heading in order:
            if heading.lower() in STATUS_HEADINGS:
                status = clean_status(first_paragraph(sections[heading]))
                break

        conclusion = ""
        for heading in order:
            if heading.lower() in DECISION_HEADINGS:
                conclusion = clean_conclusion(first_paragraph(sections[heading]))
                if conclusion:
                    break
        if not conclusion:
            # 没有决策节：取第一段（单段式 ADR 的正文）
            for heading in order:
                if heading.lower() in STATUS_HEADINGS or heading.lower() == "date":
                    continue
                candidate = clean_conclusion(first_paragraph(sections[heading]))
                if candidate:
                    conclusion = candidate
                    break

        entries.append(
            {
                "number": number,
                "slug": slug,
                "file": path.name,
                "title": (title or slug).replace("|", "\\|"),
                "status": (status or "（未标注）").replace("|", "\\|"),
                "conclusion": conclusion or "—",
                "merged_from": parse_merged_from(status),
            }
        )
    return entries


def render(entries: list[dict[str, str]]) -> str:
    accepted = sum(1 for e in entries if e["status"].lower().startswith("accepted"))
    deferred = sum(1 for e in entries if e["status"].lower().startswith("deferred"))
    other = len(entries) - accepted - deferred
    lines = [
        '<a id="adr-index"></a>',
        "# ADR 索引（自动生成）",
        "",
        "> **本文件由 `scripts/adr_index.py` 生成，请勿手改**；改了会被 `--check` 抓到。",
        "> 规则：编号与标题取自文件名与一级标题，`Status` 与「结论」取自各篇正文，**不推断、不改写**。",
        "> 用法：查历史决策先扫本表 → 只打开命中的 1–2 篇；**不要**靠 `grep` 全目录。",
        "> 全量决策仍以各 ADR 正文为准；本表只是索引。状态说明见 [目录与命名规范](../conventions/目录与命名规范.md#10-产物分类与生命周期)。",
        "> **旧编号体系已退役**：各篇正文里「由 ADR-00xx 合并」的编号属 2026-11-02 重写前的旧体系，",
        "> 对应文件已删除；现行有效编号只有本表 0001–0032（见 [引用与注释纪律](../conventions/引用与注释纪律.md#rule)）。",
        "",
        "## 怎么用",
        "",
        "- **想知道某件事当初怎么定的**：按标题/结论里的关键词在表里找，再点进去看正文。",
        "- **`Status` 是原文摘录**（可能带日期与限定语）；`accepted` 表示决策有效，不代表实施完成。",
        "- **`deferred` 不等于废止**：表示已裁定暂缓，括号里通常写了阻塞原因。",
        "- **合并篇的 `deferred` 写在正文里**（2026-11-02 起）：合并后每篇只保留一个 `Status`，",
        "  其下若有某项仍暂缓，正文对应小节会以 `**deferred**` 显式标注；查暂缓项请搜正文，不要只看本表。",
        "- **暂停的路线其 ADR 仍是 `accepted`**：暂停事实记在 plan 的开关文件，不写进 ADR 状态。",
        "",
        "## 统计",
        "",
        f"- 合计 **{len(entries)}** 篇：`accepted` {accepted} 篇、`deferred` {deferred} 篇"
        + (f"、其它 {other} 篇" if other else ""),
        "",
        "## 索引表",
        "",
        "| 编号 | 标题 | Status | 结论 |",
        "|---|---|---|---|",
    ]
    for e in entries:
        link = f"[{e['number']}](./{e['file']})"
        lines.append(f"| {link} | {e['title']} | {e['status']} | {e['conclusion']} |")

    merged = [e for e in entries if e["merged_from"]]
    if merged:
        lines.append("")
        lines.append("## 合并映射（2026-11-02，112 → 27）")
        lines.append("")
        lines.append("> 2026-11-02 做过一次**显式例外**的合并：同域旧 ADR 归并、去重过程叙事，结论逐条保留。")
        lines.append("> 下表用于回答「我以前记得的 `ADR-00NN` 现在归哪篇」。映射取自各篇 `Status` 的合并说明，**不另行维护**。")
        lines.append("")
        lines.append("| 旧编号 | 现编号 |")
        lines.append("|---|---|")
        for e in merged:
            for old in e["merged_from"]:
                lines.append(f"| {old} | [{e['number']}](./{e['file']}) |")
    lines.append("")
    lines.append("## 相关")
    lines.append("")
    lines.append("- 文档真源分层与稳定锚点 / 决策适用关系与引用纪律："
                 "[ADR-0002](./0002-docs-source-of-truth-and-reference-discipline.md#top)")
    lines.append("- 新增 ADR 的写法：[`.agents/skills/domain-modeling/ADR-FORMAT.md`](../../.agents/skills/domain-modeling/ADR-FORMAT.md)")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成/校验 docs/adr/README.md 索引")
    parser.add_argument("--check", action="store_true", help="只校验，不一致则退出码 1")
    parser.add_argument("--stdout", action="store_true", help="打印到标准输出，不写文件")
    parser.add_argument("--root", default=None, help="项目根（默认为本脚本上一级）")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    adr_dir = root / "docs" / "adr"
    if not adr_dir.is_dir():
        print(f"[ERROR] 未找到 ADR 目录：{adr_dir}", file=sys.stderr)
        return 2

    entries = collect(adr_dir)
    if not entries:
        print(f"[ERROR] {adr_dir} 下没有匹配 NNNN-slug.md 的 ADR", file=sys.stderr)
        return 2

    rendered = render(entries)
    index = adr_dir / INDEX_NAME

    if args.stdout:
        print(rendered)
        return 0

    if args.check:
        if not index.is_file():
            print(f"FAIL：索引不存在：{index}", file=sys.stderr)
            return 1
        current = index.read_text(encoding="utf-8", errors="replace")
        if current.rstrip("\n") != rendered.rstrip("\n"):
            print("FAIL：docs/adr/README.md 与 ADR 不一致，请运行 `python3 scripts/adr_index.py` 重新生成", file=sys.stderr)
            cur_lines = current.splitlines()
            new_lines = rendered.splitlines()
            for i in range(max(len(cur_lines), len(new_lines))):
                a = cur_lines[i] if i < len(cur_lines) else "<缺行>"
                b = new_lines[i] if i < len(new_lines) else "<缺行>"
                if a != b:
                    print(f"  首个差异在第 {i + 1} 行：", file=sys.stderr)
                    print(f"    索引：{a[:160]}", file=sys.stderr)
                    print(f"    期望：{b[:160]}", file=sys.stderr)
                    break
            return 1
        print(f"PASS：ADR 索引与 {len(entries)} 篇 ADR 一致")
        return 0

    index.write_text(rendered, encoding="utf-8")
    print(f"已生成 {index}（{len(entries)} 篇 ADR）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
