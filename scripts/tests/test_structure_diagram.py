#!/usr/bin/env python3
"""系统结构图与**包边界真源**的一致性回归（T0：不启任何进程）。

守护的缺陷（P2-1 round-1 自查发现的三类漂移）：

1. **图与真源漂移**：图里多写/漏写一个包，或依赖方向画错（把③运行组合画成②库链接），
   读者会得到错误结论，而**没有任何检查会拦**。本文件把图里的声明式表与
   `colcon list` / `docs/conventions/包边界.md` 逐项对齐。
2. **②库链接被放宽**：`agc_control` 是[ADR-0018](../../docs/adr/0018-shared-control-layer-and-lqr-plugin.md)
   允许的**唯一**共享库例外；一旦图里出现第二条库链接边，就说明边界被悄悄改了。
3. **`agc_msgs` 不再是叶依赖**：它若有①消息出边，依赖图就成环或分层失效。

另断言**渲染确定性**（同输入 → 同字节），否则图会因时间戳/随机导致每次 diff 都变。

运行：
  python3 -m pytest scripts/tests/test_structure_diagram.py -q
"""

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'demo'))

import render_structure_svg as R  # noqa: E402

BOUNDARY_DOC = os.path.join(ROOT, 'docs', 'conventions', '包边界.md')
STRUCTURE_DOC = os.path.join(ROOT, 'docs', 'conventions', '系统结构图.md')
SVG_PATH = os.path.join(ROOT, 'docs', 'plan', 'assets', 'system-structure.svg')

# 第三方内联包：不算业务包，但必须在表里被承认
THIRD_PARTY_NAMES = {t[0] for t in R.THIRD_PARTY}


def _boundary_packages():
    """从包边界 §1 的表格里解析包名（反引号包裹的表格首列）。"""
    with open(BOUNDARY_DOC, encoding='utf-8') as f:
        text = f.read()
    names = re.findall(r'^\| `([a-z0-9_]+)` \|', text, re.M)
    return names


def test_package_set_matches_boundary_doc():
    """图里的包集合 == 包边界 §1 的包集合（8 业务包 + px4_msgs）。"""
    declared = {p[0] for p in R.PACKAGES}
    boundary = set(_boundary_packages())
    assert boundary, '包边界文档里没解析到任何包名（解析口径失效，不是文档为空）'
    business = boundary - THIRD_PARTY_NAMES
    assert declared == business, (
        '图与包边界的业务包集合不一致：图多 %r，图少 %r'
        % (sorted(declared - business), sorted(business - declared))
    )
    # 第三方内联包在包边界里是**散文说明**（"第三方包 `px4_msgs`…原样置于 src/"），
    # 不是表格行——所以核对的是"文档里提到过"，不是"表里有它"。
    with open(BOUNDARY_DOC, encoding='utf-8') as f:
        doc_text = f.read()
    for name in THIRD_PARTY_NAMES:
        assert ('`%s`' % name) in doc_text, (
            '第三方包 %s 未在包边界文档里声明（内联第三方也必须有出处）' % name
        )
    assert len(declared) == 8, '业务包应为 8 个，实际 %d：%r' % (len(declared), sorted(declared))


def test_package_set_matches_colcon_when_available():
    """有 ROS 环境时，再与 `colcon list` 的实际包集合对齐（文档可能对、代码可能多）。"""
    try:
        proc = subprocess.run(['bash', '-c', 'source /opt/ros/jazzy/setup.bash >/dev/null 2>&1;'
                               ' colcon list --names-only'],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip('无 colcon / 超时：跳过实际包集合核对')
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip('colcon list 不可用：%s' % (proc.stderr or '').strip()[:200])
    actual = {ln.strip() for ln in proc.stdout.splitlines() if ln.strip()}
    declared = {p[0] for p in R.PACKAGES} | THIRD_PARTY_NAMES
    assert declared == actual, (
        '图的包集合与 `colcon list` 不一致：图多 %r，图少 %r'
        % (sorted(declared - actual), sorted(actual - declared))
    )


def test_only_control_library_is_link_edge():
    """②库链接边**只允许**指向 `agc_control`（ADR-0018 的唯一例外）。"""
    link_edges = [(s, d) for s, d, k in R.EDGES if k == 2]
    assert link_edges == [('agc_air', 'agc_control'), ('agc_ground', 'agc_control')], (
        '②库链接边必须恰好是 air→control 与 ground→control，实际 %r' % (link_edges,)
    )


def test_msgs_is_leaf_dependency():
    """`agc_msgs` 是叶依赖：不得有任何①消息出边，也不得出现在②/③边里。"""
    for src, dst, kind in R.EDGES:
        assert not (src == 'agc_msgs' and kind == 1), 'agc_msgs 出现了①消息出边'
        assert not (dst == 'agc_msgs' and kind in (2, 3)), (
            'agc_msgs 被当成库链接/运行组合目标（它只是①消息依赖）'
        )


def test_task_edges_are_run_composition_not_link():
    """`agc_task` 对其它域包只能是③运行组合，**不得**是②库链接（ADR-0059 的核心澄清）。"""
    for src, dst, kind in R.EDGES:
        if src != 'agc_task' or kind == 1:
            # ①消息依赖对**任何**域包都合法（含 agc_task → agc_msgs），不在本条范围内
            continue
        assert kind == 3, (
            'agc_task → %s 被画成类别 %d；它对域包只能是③运行组合（起进程）' % (dst, kind)
        )


def test_validate_passes():
    """表自检与几何自检都必须通过（几何自检保证文字不溢出框）。"""
    assert R.validate() == []
    assert R.validate_layout() == []


def test_render_is_deterministic():
    """同一份表渲染两次必须逐字节一致（否则图每次 diff 都变）。"""
    assert R.render() == R.render()


def test_svg_on_disk_matches_table():
    """仓库里提交的 SVG 必须与当前表渲染结果一致（改了表没重新生成 → 失败）。"""
    if not os.path.isfile(SVG_PATH):
        pytest.fail('缺少 %s（先跑 scripts/demo/render_structure_svg.py --out %s）'
                    % (SVG_PATH, SVG_PATH))
    with open(SVG_PATH, encoding='utf-8') as f:
        on_disk = f.read()
    assert on_disk == R.render(), (
        'SVG 与声明式表不一致：改了 PACKAGES/EDGES 后忘了重新生成 '
        '（python3 scripts/demo/render_structure_svg.py --out %s）' % SVG_PATH
    )


def test_structure_doc_covers_all_packages():
    """Mermaid 版本（系统结构图.md）也必须提到全部 8 包，且声明与包边界一致。"""
    with open(STRUCTURE_DOC, encoding='utf-8') as f:
        text = f.read()
    for name, _domain, _build, _desc, _lane, _col in R.PACKAGES:
        assert name in text, '系统结构图.md 里没有提到包 %s' % name
    # 四类依赖都要在图里被区分（不能退化成一种线）
    for label in ('① 消息', '② 链接', '③ 起进程', '④'):
        assert label in text, '系统结构图.md 缺少依赖类别标注 %r' % label


def test_readme_references_existing_assets():
    """README 里引用的图/截图必须真的存在（防"README 指向不存在的图"）。"""
    readme = os.path.join(ROOT, 'README.md')
    with open(readme, encoding='utf-8') as f:
        text = f.read()
    refs = re.findall(r'src="([^"]+)"', text)
    assert refs, 'README 里没有任何图片引用（P2-1 要求顶部有真实截图）'
    missing = [r for r in refs if not os.path.isfile(os.path.join(ROOT, r))]
    assert not missing, 'README 引用了不存在的图片：%r' % missing
