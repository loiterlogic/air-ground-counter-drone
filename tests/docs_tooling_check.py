#!/usr/bin/env python3
"""docs_link_check / adr_index 的离线自检（退出码语义，0 = PASS）。

不依赖本仓真实内容：每个用例在临时目录里造最小项目，断言脚本的判定口径，
因此以后调整文档时若把护栏改坏，这里会先失败。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK_CHECK = ROOT / "tests" / "docs_link_check.py"
ADR_INDEX = ROOT / "scripts" / "adr_index.py"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        failures.append(name)
        print(f"  FAIL  {name}  {detail}")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
    )


def make_project(tmp: Path) -> Path:
    """造一个最小项目：AGENTS.md 是根标志。"""
    write(tmp / "AGENTS.md", "# A\n\n见 [契约](docs/contract.md#hard-constraints)。\n")
    write(
        tmp / "docs" / "contract.md",
        """
        # 契约

        <a id="hard-constraints"></a>
        ## 6. 硬约束

        正文。

        ## 命名空间

        正文。
        """,
    )
    return tmp


def case_clean(tmp: Path) -> None:
    print("\n[1] 干净项目")
    root = make_project(tmp / "clean")
    result = run(LINK_CHECK, "--root", str(root))
    check("退出码 0", result.returncode == 0, result.stdout + result.stderr)
    check("报告 0 断链", "活跃范围断链：0" in result.stdout, result.stdout)


def case_missing_file(tmp: Path) -> None:
    print("\n[2] 目标文件不存在")
    root = make_project(tmp / "missing")
    write(root / "docs" / "bad.md", "# B\n\n[缺](nope.md)\n")
    result = run(LINK_CHECK, "--root", str(root))
    check("退出码 1", result.returncode == 1, result.stdout)
    check("指出目标文件不存在", "目标文件不存在" in result.stdout, result.stdout)


def case_missing_anchor(tmp: Path) -> None:
    print("\n[3] 锚点不存在")
    root = make_project(tmp / "anchor")
    write(root / "docs" / "bad.md", "# B\n\n[错锚点](contract.md#nope)\n")
    result = run(LINK_CHECK, "--root", str(root))
    check("退出码 1", result.returncode == 1, result.stdout)
    check("指出锚点不存在", "锚点不存在" in result.stdout, result.stdout)


def case_heading_slug(tmp: Path) -> None:
    print("\n[4] 标题 slug 与显式锚点都能解析")
    root = make_project(tmp / "slug")
    write(
        root / "docs" / "ok.md",
        "# O\n\n[标题](contract.md#命名空间) [显式](contract.md#hard-constraints)\n"
        "[行锚](contract.md#L3) [行号写法](contract.md:3)\n",
    )
    result = run(LINK_CHECK, "--root", str(root))
    check("退出码 0", result.returncode == 0, result.stdout)


def case_code_fence(tmp: Path) -> None:
    print("\n[5] 代码块与行内代码里的链接不算导航")
    root = make_project(tmp / "fence")
    write(
        root / "docs" / "code.md",
        """
        # C

        ```markdown
        [示例](不存在.md)
        ```

        行内 `[示例](也不存在.md)` 也不算。
        """,
    )
    result = run(LINK_CHECK, "--root", str(root))
    check("退出码 0", result.returncode == 0, result.stdout)


def case_evidence_paths(tmp: Path) -> None:
    print("\n[6] 绝对路径与 experiments/ 计为证据引用")
    root = make_project(tmp / "evidence")
    write(
        root / "docs" / "review.md",
        "# R\n\n[源码](/home/x/src/a.cpp:12) [证据](../../experiments/x/y.json)\n",
    )
    result = run(LINK_CHECK, "--root", str(root))
    check("退出码 0", result.returncode == 0, result.stdout)
    check("计入证据引用", "证据绝对路径" in result.stdout, result.stdout)


def case_template_placeholder(tmp: Path) -> None:
    print("\n[7] 模板占位不判断链")
    root = make_project(tmp / "template")
    write(root / "docs" / "tpl.md", "# T\n\n[依据](<锚点>.md#<anchor>)\n")
    result = run(LINK_CHECK, "--root", str(root))
    check("退出码 0", result.returncode == 0, result.stdout)


def case_history(tmp: Path) -> None:
    print("\n[8] 历史范围只列名、不计失败；--strict-history 才失败")
    root = make_project(tmp / "history")
    write(root / "docs" / "archive" / "old.md", "# O\n\n[旧路径](../gone.md)\n")
    result = run(LINK_CHECK, "--root", str(root))
    check("默认退出码 0", result.returncode == 0, result.stdout)
    check("标为 history", "[history]" in result.stdout, result.stdout)
    strict = run(LINK_CHECK, "--root", str(root), "--strict-history")
    check("--strict-history 退出码 1", strict.returncode == 1, strict.stdout)


def case_local_only(tmp: Path) -> None:
    print("\n[12] 本机保留路径：本地存在则单列，不计断链也不算通过")
    root = make_project(tmp / "localonly")
    # 造一个"本机保留"目录并在里面放文件。用 `toolchain/`：它在 LOCAL_ONLY_PREFIXES 里，
    # 且不像 `experiments/` 那样被"证据引用"规则提前跳过。
    # （原示例 `docs/archive/specs/` 已于 2026-11-03 删除。）
    write(root / "toolchain" / "PX4-Autopilot" / "README.md", "# T\n")
    write(root / "docs" / "page.md", "# P\n\n[工具链](../toolchain/PX4-Autopilot/README.md)\n")
    result = run(LINK_CHECK, "--root", str(root))
    check("退出码 0（本地可解析）", result.returncode == 0, result.stdout)
    check("单列为本机保留", "指向本机保留路径" in result.stdout, result.stdout)
    check("未谎称公开可导航", "公开 clone" in result.stdout, result.stdout)
    check("标为本地可解析 1 条", "本地可解析 1 条" in result.stdout, result.stdout)

    # 同类路径但本地也缺 -> 报为需复核，而不是静默通过
    write(root / "docs" / "page2.md", "# P2\n\n[缺](../toolchain/missing/README.md)\n")
    missing = run(LINK_CHECK, "--root", str(root))
    check("本地也缺失时退出码 0 但单列", missing.returncode == 0, missing.stdout)
    check("提示本地也缺失", "本地也缺失 1 条" in missing.stdout, missing.stdout)


def case_missing_root(tmp: Path) -> None:
    print("\n[9] 根目录不对 -> 用法错误退出码 2")
    empty = tmp / "empty"
    empty.mkdir(parents=True, exist_ok=True)
    result = run(LINK_CHECK, "--root", str(empty))
    check("退出码 2", result.returncode == 2, result.stdout + result.stderr)


def make_adr(dirpath: Path, name: str, title: str, status: str, decision: str) -> None:
    write(
        dirpath / name,
        f"""
        # {title}

        ## Status

        {status}

        ## 决策

        {decision}
        """,
    )


def case_adr_index(tmp: Path) -> None:
    print("\n[10] adr_index 生成 / 幂等 / --check / 漂移检测")
    root = tmp / "adr"
    adr = root / "docs" / "adr"
    make_adr(adr, "0001-first.md", "甲决定", "accepted", "选 甲，因为 1。")
    make_adr(adr, "0002-second.md", "乙决定", "deferred（等 X）", "暂缓 乙。")
    write(root / "docs" / "conventions" / "目录与命名规范.md", "# 规范\n\n## 10. 产物\n")

    gen = run(ADR_INDEX, "--root", str(root))
    check("生成退出码 0", gen.returncode == 0, gen.stdout)
    index = adr / "README.md"
    check("索引已生成", index.is_file())
    text = index.read_text(encoding="utf-8")
    check("含编号", "0001" in text and "0002" in text)
    check("含标题", "甲决定" in text and "乙决定" in text)
    check("含 Status 原文", "deferred（等 X）" in text, text[:400])
    check("含结论", "选 甲" in text)
    check("不猜状态", "accepted" in text and text.count("accepted") >= 2)

    first = text
    run(ADR_INDEX, "--root", str(root))
    check("重跑幂等", first == index.read_text(encoding="utf-8"))

    ok = run(ADR_INDEX, "--root", str(root), "--check")
    check("--check 通过", ok.returncode == 0, ok.stdout + ok.stderr)

    make_adr(adr, "0003-third.md", "丙决定", "accepted", "新增。")
    drift = run(ADR_INDEX, "--root", str(root), "--check")
    check("新增 ADR 后 --check 失败", drift.returncode == 1, drift.stdout + drift.stderr)

    # 手改索引也要被抓到
    run(ADR_INDEX, "--root", str(root))
    index.write_text(index.read_text(encoding="utf-8") + "\n手写追加\n", encoding="utf-8")
    tampered = run(ADR_INDEX, "--root", str(root), "--check")
    check("手改索引后 --check 失败", tampered.returncode == 1, tampered.stdout)


def case_adr_ignores_readme(tmp: Path) -> None:
    print("\n[11] ADR 索引不把自己算进 ADR")
    root = tmp / "adr2"
    adr = root / "docs" / "adr"
    make_adr(adr, "0001-only.md", "唯一", "accepted", "只有一篇。")
    write(root / "docs" / "conventions" / "目录与命名规范.md", "# 规范\n")
    run(ADR_INDEX, "--root", str(root))
    run(ADR_INDEX, "--root", str(root))
    check_module = run(ADR_INDEX, "--root", str(root), "--check")
    text = (adr / "README.md").read_text(encoding="utf-8")
    check("统计只算 1 篇", "合计 **1** 篇" in text, text[:600])
    check("--check 通过", check_module.returncode == 0, check_module.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agc-docscheck-") as raw:
        tmp = Path(raw)
        case_clean(tmp)
        case_missing_file(tmp)
        case_missing_anchor(tmp)
        case_heading_slug(tmp)
        case_code_fence(tmp)
        case_evidence_paths(tmp)
        case_template_placeholder(tmp)
        case_history(tmp)
        case_local_only(tmp)
        case_missing_root(tmp)
        case_adr_index(tmp)
        case_adr_ignores_readme(tmp)

    print()
    if failures:
        print(f"FAIL：{len(failures)} 项未通过 -> {failures}")
        return 1
    print("PASS：全部用例通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
