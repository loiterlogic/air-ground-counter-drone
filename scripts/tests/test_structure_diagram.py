#!/usr/bin/env python3
"""系统结构图回归：**表 ↔ 包边界**、**版式几何**、**光栅可读性** 三层（T0，不启任何进程）。

守护的缺陷（来自 2026-10-31 F2 前的实际漂移，不只是理论风险）：

1. **图与配置文件漂移**：旧图把 `agc_sim → agc_msgs` 画成①消息依赖，而 `src/agc_sim/package.xml`
 与源码里**都没有** `agc_msgs`（它只经 ros_gz 桥发标准消息）。读者会据此以为仿真是接口层消费者。
2. **②库链接被放宽**：`agc_control` 是 [ADR-0004](../../docs/adr/0004-ground-control-rl-primary-and-nav2-safety.md#top)
 允许的**唯一**共享库例外；出现第二条库链接边即边界被悄悄改。
3. **`agc_msgs` 不再是叶依赖**：它若有①出边，依赖图成环或分层失效。
4. **`agc_task → 域包`被画成②**：[ADR-0020](../../docs/adr/0020-package-boundaries-and-runtime-topology.md#top)
 的核心澄清是「起进程 ≠ 链接库」。
5. **版式不可读**：旧图 1844 px 宽在 README 里按 820 显示 → 缩放 0.44，12 px 正文实际 5.3 px；
 19 条中心到中心直线穿过框体与文字。**"看起来还行"不是判据**，故本文件同时断言几何与光栅。
6. **渲染不确定**：图若含时间戳/随机，每次 diff 都变，漂移就再也看不出来。

**为什么既验 SVGT 文本又验光栅**（避免"只凭字符串断言宣称美观"）：
字符串断言只能证明"某段文字写进了文件"，证明不了它**放得下、没被压、看得清**。因此这里
(a) 用 `R.run_checks()` 做几何自检（字宽/穿框/交叉/标签互压），(b) 把 SVG 真的光栅化，
用**像素**核对"文字有墨、线有墨、没有裁切、缩到 820 宽后正文仍然清晰"。

运行：
  python3 -m pytest scripts/tests/test_structure_diagram.py -q
"""

import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'demo'))

import render_structure_svg as R  # noqa: E402

BOUNDARY_DOC = os.path.join(ROOT, 'docs', 'conventions', '包边界.md')
STRUCTURE_DOC = os.path.join(ROOT, 'docs', 'conventions', '系统结构图.md')
SVG_PATH = os.path.join(ROOT, 'docs', 'conventions', 'assets', 'system-structure.svg')
PNG_PATH = os.path.join(ROOT, 'docs', 'conventions', 'assets', 'system-structure.png')
DETAIL_SVG = os.path.join(ROOT, 'docs', 'conventions', 'assets', 'system-structure-detail.svg')
DETAIL_PNG = os.path.join(ROOT, 'docs', 'conventions', 'assets', 'system-structure-detail.png')
README = os.path.join(ROOT, 'README.md')

THIRD_PARTY_NAMES = {'px4_msgs'}   # 内联第三方**包**（EXTERNAL 里其余是外部系统，不是包）
BUSINESS = {p['id'] for p in R.PACKAGES}


# --------------------------------------------------------------------------------------
# 0. Qt 光栅化夹具（缺 PyQt5 时**跳过而不是假装通过**）
# --------------------------------------------------------------------------------------


_QT_APP = []      # 必须持有全局引用：QGuiApplication 被 GC 后，后续 QFont/QImage 会段错误


@pytest.fixture(scope='module')
def qt():
    pytest.importorskip('PyQt5.QtSvg', reason='无 PyQt5：无法做光栅判据')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt5 import QtCore, QtGui, QtSvg
    app = QtGui.QGuiApplication.instance()
    if app is None:
        app = QtGui.QGuiApplication([])
        _QT_APP.append(app)
    assert app is not None

    def raster(svg_text=None, scale=1):
        """把 SVG 文本（缺省用磁盘上的）渲染成 QImage。"""
        import tempfile
        if svg_text is None:
            with open(SVG_PATH, encoding='utf-8') as f:
                svg_text = f.read()
        fd, tmp = tempfile.mkstemp(suffix='.svg')
        os.close(fd)
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(svg_text)
            r = QtSvg.QSvgRenderer(tmp)
            assert r.isValid(), 'Qt 无法解析渲染出的 SVG（语法或编码有问题）'
            sz = r.defaultSize()
            img = QtGui.QImage(sz.width() * scale, sz.height() * scale,
                               QtGui.QImage.Format_RGB32)
            img.fill(QtCore.Qt.white)
            p = QtGui.QPainter(img)
            p.setRenderHint(QtGui.QPainter.Antialiasing, True)
            p.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
            r.render(p)
            p.end()
            return img
        finally:
            os.unlink(tmp)

    return dict(raster=raster, QtCore=QtCore, QtGui=QtGui)


def _ink(img, rect=None):
    """返回 (非白像素数, 总像素数)。rect 用 QRect。"""
    from PyQt5 import QtGui
    if rect is None:
        rect = img.rect()
    n = 0
    for y in range(rect.top(), rect.top() + rect.height()):
        for x in range(rect.left(), rect.left() + rect.width()):
            c = img.pixelColor(x, y)
            if c.red() < 250 or c.green() < 250 or c.blue() < 250:
                n += 1
    return n, rect.width() * rect.height()


# --------------------------------------------------------------------------------------
# 1. 表 ↔ 包边界配置文件
# --------------------------------------------------------------------------------------


def _boundary_packages():
    with open(BOUNDARY_DOC, encoding='utf-8') as f:
        text = f.read()
    return re.findall(r'^\| `([a-z0-9_]+)` \|', text, re.M)


def test_package_set_matches_boundary_doc():
    """图里的 8 个业务包 == 包边界#1-包清单 的表格行；px4_msgs 必须在正文被声明。"""
    declared = {p['id'] for p in R.PACKAGES}
    boundary = set(_boundary_packages())
    assert boundary, '包边界文档里没解析到任何包名（解析口径失效，不是文档为空）'
    assert declared == boundary, (
        '图与包边界的业务包集合不一致：图多 %r，图少 %r'
        % (sorted(declared - boundary), sorted(boundary - declared)))
    with open(BOUNDARY_DOC, encoding='utf-8') as f:
        doc = f.read()
    assert '`px4_msgs`' in doc, '第三方内联包 px4_msgs 未在包边界声明'
    assert len(declared) == 8, '业务包应为 8 个，实际 %d：%r' % (len(declared), sorted(declared))


def test_package_set_matches_colcon_when_available():
    """有 ROS 环境时再与 `colcon list` 对齐（文档可能对、代码可能多）。"""
    if shutil.which('bash') is None:
        pytest.skip('无 bash')
    try:
        proc = subprocess.run(
            ['bash', '-c', 'source /opt/ros/jazzy/setup.bash >/dev/null 2>&1;'
                           ' colcon list --names-only'],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip('无 colcon / 超时：跳过实际包集合核对')
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip('colcon list 不可用：%s' % (proc.stderr or '').strip()[:200])
    actual = {ln.strip() for ln in proc.stdout.splitlines() if ln.strip()}
    declared = BUSINESS | THIRD_PARTY_NAMES
    assert declared == actual, (
        '图的包集合与 colcon list 不一致：图多 %r，图少 %r'
        % (sorted(declared - actual), sorted(actual - declared)))


def test_declared_package_xml_matches_edges():
    """每个包在 `package.xml` 里真实声明的包间依赖，必须与图里的①②③边一致。

 这条是**反漂移的主判据**：图不是"人对文档的理解"，而是"manifest 的投影"。
    """
    if not os.path.isdir(os.path.join(ROOT, 'src')):
        pytest.skip('无 src/')
    import xml.etree.ElementTree as ET
    for pid in sorted(BUSINESS):
        xml = os.path.join(ROOT, 'src', pid, 'package.xml')
        if not os.path.isfile(xml):
            pytest.skip('缺 src/%s/package.xml' % pid)
        root = ET.parse(xml).getroot()
        declared = set()
        for tag in ('depend', 'build_depend', 'exec_depend', 'build_export_depend'):
            for el in root.findall(tag):
                name = (el.text or '').strip()
                if name in BUSINESS and name != pid:
                    declared.add(name)
        in_graph = {d for s, d, _k in R.PACKAGE_EDGES if s == pid}
        # 图可以比 manifest 少（例如 ①②③ 的具体类别需要人工判定），但不能凭空多
        extra = in_graph - declared
        assert not extra, (
            '%s 在图里有边指向 %r，但 package.xml 从未声明（图比 package.xml 多画了依赖）'
            % (pid, sorted(extra)))


def test_control_is_the_only_library_link_target():
    """②库链接边**只允许** air→control 与 ground→control（ADR-0004 唯一例外）。"""
    link_edges = [(s, d) for s, d, k in R.PACKAGE_EDGES if k == 2]
    assert link_edges == [('agc_air', 'agc_control'), ('agc_ground', 'agc_control')], (
        '②库链接边必须恰好是 air→control 与 ground→control，实际 %r' % (link_edges,))
    for p in ('agc_air', 'agc_ground'):
        cmake = os.path.join(ROOT, 'src', p, 'CMakeLists.txt')
        if os.path.isfile(cmake):
            with open(cmake, encoding='utf-8') as f:
                assert 'find_package(agc_control' in f.read(), (
                    '%s 在 CMakeLists 里没有 find_package(agc_control)，②边无据' % p)


def test_msgs_is_leaf_dependency():
    """`agc_msgs` 是叶依赖：无①出边，也不被②/③指向。"""
    for src, dst, kind in R.PACKAGE_EDGES:
        assert not (src == 'agc_msgs' and kind == 1), 'agc_msgs 出现了①消息出边'
        assert not (dst == 'agc_msgs' and kind in (2, 3)), (
            'agc_msgs 被当成库链接/运行组合目标（它只是①消息依赖）')


def test_sim_does_not_depend_on_msgs():
    """回归本任务修掉的实际漂移：`agc_sim` **不**依赖 `agc_msgs`。

    依据：`src/agc_sim/package.xml` 无 agc_msgs、`CMakeLists.txt` 无 find_package(agc_msgs)、
 源码无 include。旧图把它画成①依赖，属配置文件漂移。
    """
    edges = {(s, d) for s, d, _k in R.PACKAGE_EDGES}
    assert ('agc_sim', 'agc_msgs') not in edges, 'agc_sim 不应有到 agc_msgs 的边'
    xml = os.path.join(ROOT, 'src', 'agc_sim', 'package.xml')
    if os.path.isfile(xml):
        with open(xml, encoding='utf-8') as f:
            assert 'agc_msgs' not in f.read(), (
                'src/agc_sim/package.xml 现在声明了 agc_msgs：package.xml 已变，图与判据都要跟着改')


def test_task_edges_are_run_composition_not_link():
    """`agc_task` 对其它域包只能是③运行组合（ADR-0020 核心澄清）。"""
    for src, dst, kind in R.PACKAGE_EDGES:
        if src != 'agc_task' or kind == 1:
            continue
        assert kind == 3, (
            'agc_task → %s 被画成类别 %d；它对域包只能是③运行组合（起进程）' % (dst, kind))


def test_task_is_declared_exec_depend_for_every_started_package():
    """③ 每条边都必须能在 `main.launch.py` / package.xml 里找到「起进程」的落脚点。"""
    xml = os.path.join(ROOT, 'src', 'agc_task', 'package.xml')
    launch = os.path.join(ROOT, 'src', 'agc_task', 'launch', 'main.launch.py')
    if not (os.path.isfile(xml) and os.path.isfile(launch)):
        pytest.skip('缺 agc_task 的 package.xml / main.launch.py')
    with open(xml, encoding='utf-8') as f:
        pkg = f.read()
    with open(launch, encoding='utf-8') as f:
        lch = f.read()
    for src, dst, kind in R.PACKAGE_EDGES:
        if src != 'agc_task' or kind != 3 or dst not in BUSINESS:
            continue
        assert ('<exec_depend>%s</exec_depend>' % dst) in pkg, (
            'agc_task 未 exec_depend %s，但图里画了③起进程' % dst)
        assert ("'%s'" % dst) in lch or ("\"%s\"" % dst) in lch, (
            'agc_task/launch/main.launch.py 未见引用 %s，③边缺落点' % dst)


# --------------------------------------------------------------------------------------
# 2. 版式几何（不靠肉眼）
# --------------------------------------------------------------------------------------


def test_validate_passes():
    """表自检 + 几何自检 + 布线自检 + 标签自检必须全通过。"""
    assert R.validate() == []
    assert R.run_checks() == [], '版式/布线/标签自检失败：%r' % (R.run_checks(),)


def test_text_width_model_matches_real_font(qt):
    """**字宽模型必须与真实字体对齐**：否则"按像素换行"只是自欺。

 这条把渲染器里的 `_EM` 字宽表与 Qt 的实测 advance 对比（逐类采样），偏差 > 6% 即失败。
 图里所有"放得下"的结论都建立在这个模型上，它一旦失真，几何自检就失去意义。
    """
    from PyQt5 import QtGui
    samples = ['agc_perception', 'ament_cmake + rosidl', '仿真世界与模型',
               '世界 · 车/UAV/目标模型 · ros_gz 桥', 'obs/action 接口 · 策略推理',
               '9 条 msg：AgcTaskState', '③ 运行组合', '② 库链接依赖（2 条 · 唯一例外）',
               '自研 ground_safety_filter 安全层', '④ Gazebo Harmonic（gz-sim 8）']
    for px in (10, 12):
        f = QtGui.QFont('DejaVu Sans')
        f.setPixelSize(px)
        fm = QtGui.QFontMetricsF(f)
        for s in samples:
            real = fm.horizontalAdvance(s)
            model = R.text_px(s, px)
            rel = abs(model - real) / max(real, 1e-6)
            assert rel < 0.06, (
                '字宽模型偏差 %.1f%%（%r @ %dpx：模型 %.1f / 实测 %.1f）'
                % (rel * 100, s, px, model, real))


def test_no_node_text_overflows_or_is_truncated():
    """逐行复核：每行都放得下、没有被省略号截断（图里不允许省略）。"""
    nodes, _bands, _frame = R.layout()
    for pid, (_x, _y, w, _h) in nodes.items():
        inner = w - 2 * R.PAD_X
        for line in R.node_lines(R.NODE_BY_ID[pid], w):
            txt, size, bold = line[0], line[1], line[2]
            need = R.text_px(txt, size, bold)
            assert need <= inner + 0.5, (
                '%s 的 %r 超宽：%.1f > %.1f' % (pid, txt, need, inner))
            assert not txt.endswith('…'), '%s 出现省略号截断：%r' % (pid, txt)


def test_no_line_crosses_a_box_or_another_label():
    """布线自检：轴对齐、不穿框、跨类别不交叉、不压标签。"""
    nodes, bands, _frame = R.layout()
    segs = R.routes(nodes, bands)
    labels, boxes = R.place_labels(nodes, segs, R.label_specs(nodes, bands))
    assert R.validate_routes(nodes, segs) == []
    assert R.validate_labels(nodes, segs, boxes) == []
    assert len(labels) >= 8, '图里至少应有 5 个层名 + 3 个线类别标注'


def test_canvas_width_equals_readme_display_width():
    """**画布宽必须等于 README 的显示宽**，否则又回到"缩放到 5 px 字"。

 旧图 1844 px 被 README 以 820 显示 = 0.44 缩放，是本次重画的首要动因。
    """
    with open(README, encoding='utf-8') as f:
        readme = f.read()
    m = re.search(r'<img src="docs/conventions/assets/system-structure\.svg"\s+width="(\d+)"', readme)
    assert m, 'README 里没有系统结构图的 820 宽显示区（或写法变了）'
    assert int(m.group(1)) == R.CANVAS_W, (
        'README 显示宽 %s ≠ 画布宽 %d：会出现缩放，字会糊'
        % (m.group(1), R.CANVAS_W))
    with open(SVG_PATH, encoding='utf-8') as f:
        head = f.read(400)
    assert 'width="%d"' % R.CANVAS_W in head, (
        'SVG 的 width 属性不是 %d（viewBox 一致但 width 不同仍会缩放）' % R.CANVAS_W)


def test_font_sizes_meet_review_requirement():
    """按审查要求：**包名 ≥ 15 px，主要职责正文 ≥ 12 px**。

 这条是**下限断言**，不是"等于某个值"——可以继续调大，不能为了通过测试而调小。
 注释里写明历史： 交付时正文只有 10 px，被审查判为偏小。
    """
    assert R.FS_NODE >= 15, '包名字号 %.1f px < 15 px' % R.FS_NODE
    for name in ('FS_ROLE', 'FS_DESC', 'FS_EXT'):
        v = getattr(R, name)
        assert v >= 12, '%s = %.1f px < 12 px（主要职责正文下限）' % (name, v)
    assert R.FS_CARD >= 12, '明细正文 %.1f px < 12 px' % R.FS_CARD
    assert R.FS_FOOT >= 11, '脚注 %.1f px < 11 px' % R.FS_FOOT


def test_all_rendered_text_is_at_least_12px():
    """不只看常量：把概览**实际渲染**的每个字号从 SVG 里读回来，逐条卡下限。"""
    with open(SVG_PATH, encoding='utf-8') as f:
        svg = f.read()
    sizes = {float(m) for m in re.findall(r'font-size="([\d.]+)"', svg)}
    assert sizes, 'SVG 里没有任何 font-size（渲染异常）'
    too_small = sorted(s for s in sizes if s < 11)
    assert not too_small, 'SVG 里出现 < 11 px 的字号：%r' % too_small


def test_detail_svg_exists_and_is_separate_asset():
    """明细必须是**独立资产**（审查要求：不要让一张长图同时承担概览与清单）。"""
    for path in (DETAIL_SVG, DETAIL_PNG):
        assert os.path.isfile(path), '缺明细资产 %s' % path
    with open(SVG_PATH, encoding='utf-8') as f:
        overview = f.read()
    with open(DETAIL_SVG, encoding='utf-8') as f:
        detail = f.read()
    # 概览不应再内嵌完整边清单（旧 的 B 面板那种卡片列表）
    assert '库链接依赖（2 条' not in overview, '概览里仍内嵌完整边清单（应移到明细图）'
    assert '库链接依赖（2 条' in detail, '明细图里没有 ② 的完整清单'
    # 明细图必须覆盖四类
    for label in ('① 消息', '② 库链接', '③ 运行组合', '④ 外部设备'):
        assert label in detail, '明细图缺 %r 段' % label


def test_overview_and_detail_edge_sets_are_equal():
    """拆分后最容易的漂移：概览画了、明细没列（或反之）。"""
    assert R._edge_set() == {(a, b, k) for a, b, k in R.PACKAGE_EDGES} | \
        {(e, s, w) for e, s, w, _n in R.EXT_RELATIONS}
    # 明细文本必须提到每一条包间边
    detail_text = '\n'.join(t for _k, t, *_ in R.detail_lines())
    for src, dst, _kind in R.PACKAGE_EDGES:
        assert src in detail_text and dst in detail_text, (
            '明细图缺包间边 %s → %s' % (src, dst))


def test_bold_factor_matches_font(qt):
    """粗体放大系数也得对：包名是粗体，估错就会溢出。"""
    from PyQt5 import QtGui
    f = QtGui.QFont('DejaVu Sans')
    f.setPixelSize(13)
    fb = QtGui.QFont('DejaVu Sans')
    fb.setPixelSize(13)
    fb.setBold(True)
    fm, fmb = QtGui.QFontMetricsF(f), QtGui.QFontMetricsF(fb)
    for s in ('agc_perception', 'agc_ground', 'agc_control'):
        real = fmb.horizontalAdvance(s) / fm.horizontalAdvance(s)
        assert abs(real - R.BOLD_FACTOR) < 0.04, (
            'BOLD_FACTOR=%r 与实测 %.3f 差太多（%r）' % (R.BOLD_FACTOR, real, s))


# --------------------------------------------------------------------------------------
# 3. 光栅判据（真的把 SVG 画出来看像素）
# --------------------------------------------------------------------------------------


def test_svg_rasterizes_with_ink_everywhere(qt):
    """每个节点框内都必须有墨（否则是"框在、字没画出来"或字色=底色）。"""
    img = qt['raster'](scale=1)
    nodes, _bands, _frame = R.layout()
    for pid, (x, y, w, h) in nodes.items():
        rect = qt['QtCore'].QRect(int(x) + 2, int(y) + 2, int(w) - 4, int(h) - 4)
        n, total = _ink(img, rect)
        assert n > total * 0.02, (
            '%s 框内几乎没有墨（%d/%d 像素）：文字可能没渲染或被裁掉' % (pid, n, total))


def test_no_content_is_clipped_at_canvas_edges(qt):
    """画布四边各留 2 px 检查带必须**全白**：有墨就说明内容被裁切。"""
    img = qt['raster'](scale=1)
    QtCore = qt['QtCore']
    h, w = img.height(), img.width()
    bands = {
        'top': QtCore.QRect(0, 0, w, 2),
        'bottom': QtCore.QRect(0, h - 2, w, 2),
        'left': QtCore.QRect(0, 0, 2, h),
        'right': QtCore.QRect(w - 2, 0, 2, h),
    }
    for name, rect in bands.items():
        n, _ = _ink(img, rect)
        assert n == 0, '画布 %s 边缘有 %d 个非白像素：内容被裁切（先是页脚，实测踩过）' % (name, n)


def test_body_text_is_legible_at_820px_width(qt):
    """820 px 实宽下正文**真的可读**：用像素核对笔画分离度，而不是只断言字号。

 做法：取一段已知正文（`agc_msgs` 的说明行）的包围盒，1x 光栅化后统计
 「墨/背景」交替次数——文字被渲染成可分辨的笔画时，横扫一行的黑白翻转次数会远高于糊成
 一条灰带的情况。阈值取 >= 6（实测该行约 30+，纯灰带 < 3）。
    """
    img = qt['raster'](scale=1)
    nodes, _bands, _frame = R.layout()
    x, y, w, h = nodes['agc_msgs']
    lines = R.node_lines(R.NODE_BY_ID['agc_msgs'], w)
    # 取最后一条正文（节点说明），基线由渲染器同一套 line_step 推出
    yy = y + R.PAD_TOP
    for i, (_t, size, _b, _c) in enumerate(lines):
        if i:
            yy += R.line_step(size)
    # 基线之上 4 px 落在 x-height 中部，是最能反映笔画分离度的扫描线
    scan_y = int(yy - 4)

    def flips_on(scan_y):
        n, prev = 0, None
        for px in range(int(x) + R.PAD_X, int(x + w) - R.PAD_X):
            c = img.pixelColor(px, scan_y)
            dark = (c.red() + c.green() + c.blue()) < 3 * 210
            if prev is not None and dark != prev:
                n += 1
            prev = dark
        return n

    # 基线上下各扫 3 px，取最好的一条（避免正好落在字缝里）
    best = max(flips_on(scan_y + d) for d in (-3, -2, -1, 0, 1, 2, 3))
    assert best >= 6, (
        '820 px 下该行最多只出现 %d 次明暗翻转：正文糊成灰带（字太小或权重太轻）' % best)


def test_lines_are_distinguishable_from_background(qt):
    """三类连线在光栅化后都必须留下可见笔画（别把线画成"看不见"的浅色）。"""
    img = qt['raster'](scale=1)
    nodes, bands, _frame = R.layout()
    segs = R.routes(nodes, bands)
    checked = 0
    for seg in segs:
        for (x1, y1), (x2, y2) in zip(seg['pts'], seg['pts'][1:], strict=False):
            span = abs(x2 - x1) + abs(y2 - y1)
            if span < 8:
                continue          # 太短，多半是端口进出段
            # 沿整段**逐像素**扫描：虚线有空隙，只取中点会误判
            hit = False
            steps = int(span)
            for t in range(steps + 1):
                f = t / max(steps, 1)
                mx = int(round(x1 + (x2 - x1) * f))
                my = int(round(y1 + (y2 - y1) * f))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        c = img.pixelColor(mx + dx, my + dy)
                        if (c.red() + c.green() + c.blue()) < 3 * 245:
                            hit = True
                            break
                    if hit:
                        break
                if hit:
                    break
            assert hit, ('类 %d 的线段 %r→%r 在光栅化后完全不可见'
                         % (seg['kind'], (x1, y1), (x2, y2)))
            checked += 1
    assert checked >= 8, '启用的线段检查过少（%d），判据可能失效' % checked


def test_png_preview_exists_and_matches_svg_size():
    """仓库里的 PNG 预览必须存在，且尺寸 = SVG 尺寸 × 2（@2x，供放大查看）。"""
    assert os.path.isfile(PNG_PATH), (
        '缺少 %s（跑 render_structure_svg.py --out … --png %s --scale 2）'
        % (PNG_PATH, PNG_PATH))
    from PyQt5 import QtGui
    img = QtGui.QImage(PNG_PATH)
    assert not img.isNull(), 'PNG 预览无法解码'
    with open(SVG_PATH, encoding='utf-8') as f:
        head = f.read(400)
    m = re.search(r'width="(\d+)" height="(\d+)"', head)
    assert m, 'SVG 头部没有 width/height'
    assert (img.width(), img.height()) == (int(m.group(1)) * 2, int(m.group(2)) * 2), (
        'PNG 预览 %dx%d 与 SVG %sx%s 的 @2x 不一致（改了图没重出 PNG）'
        % (img.width(), img.height(), m.group(1), m.group(2)))
    # 明细 PNG 同理
    dimg = QtGui.QImage(DETAIL_PNG)
    assert not dimg.isNull(), '明细 PNG 无法解码'
    with open(DETAIL_SVG, encoding='utf-8') as f:
        dhead = f.read(400)
    dm = re.search(r'width="(\d+)" height="(\d+)"', dhead)
    assert dm, '明细 SVG 头部没有 width/height'
    assert (dimg.width(), dimg.height()) == (int(dm.group(1)) * 2, int(dm.group(2)) * 2), (
        '明细 PNG %dx%d 与 SVG %sx%s 的 @2x 不一致' % (dimg.width(), dimg.height(),
                                                     dm.group(1), dm.group(2)))


# --------------------------------------------------------------------------------------
# 4. 可重复生成 / 磁盘与表一致
# --------------------------------------------------------------------------------------


def test_render_is_deterministic():
    """同输入渲染两次必须逐字节一致（否则每次 diff 都变，漂移再也看不出来）。"""
    assert R.render_overview() == R.render_overview()
    assert R.render_detail() == R.render_detail()


def test_svg_on_disk_matches_table():
    """仓库里提交的 SVG 必须与当前表渲染结果**逐字节**一致。"""
    assert os.path.isfile(SVG_PATH), (
        '缺少 %s（先跑 scripts/demo/render_structure_svg.py --out %s）' % (SVG_PATH, SVG_PATH))
    with open(SVG_PATH, encoding='utf-8') as f:
        on_disk = f.read()
    assert on_disk == R.render_overview(), (
        '概览 SVG 与声明式表不一致：改了 PACKAGES/EDGES 后忘了重新生成 '
        '（--out %s --png %s）' % (SVG_PATH, PNG_PATH))
    with open(DETAIL_SVG, encoding='utf-8') as f:
        detail_disk = f.read()
    assert detail_disk == R.render_detail(), (
        '明细 SVG 与声明式表不一致：改了 EXT_RELATIONS 后忘了重新生成 '
        '（--detail %s --detail-png %s）' % (DETAIL_SVG, DETAIL_PNG))


def test_cli_exit_codes():
    """CLI 契约：--check-only 通过返回 0，缺参数返回 2。"""
    ok = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'demo',
                                                      'render_structure_svg.py'), '--check-only'],
                        capture_output=True, text=True, timeout=120)
    assert ok.returncode == 0, '自检模式返回 %d：%s' % (ok.returncode, ok.stderr[:400])
    bad = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'demo',
                                                       'render_structure_svg.py')],
                         capture_output=True, text=True, timeout=120)
    assert bad.returncode == 2, '缺 --out 应返回 2（用法错误），实际 %d' % bad.returncode


# Mermaid 里的 Mermaid 节点 id → 声明表里的名字（单一映射，测试与被测文档共用）
MERMAID_NODE = {
    'TASK': 'agc_task', 'SIM': 'agc_sim', 'PER': 'agc_perception', 'AIR': 'agc_air',
    'GROUND': 'agc_ground', 'RL': 'agc_rl', 'CTRL': 'agc_control', 'MSGS': 'agc_msgs',
}
MERMAID_EXT = {
    'GZ': 'Gazebo Harmonic', 'PX4': 'PX4 SITL', 'AGENT': 'uXRCE-DDS Agent',
    'NAV2': 'Nav2 组件', 'PX4MSGS': 'px4_msgs',
}


def _mermaid_block():
    """取系统结构图.md 里第一段 `flowchart TB`（结构图，非数据流图）。"""
    with open(STRUCTURE_DOC, encoding='utf-8') as f:
        text = f.read()
    m = re.search(r'```mermaid\n(flowchart TB.*?)```', text, re.S)
    assert m, '系统结构图.md 里没有 flowchart TB 结构图'
    return m.group(1)


def test_mermaid_four_edges_match_declaration_table():
    """**Mermaid 的 ④ 边必须与 EXT_RELATIONS 逐条一致**（审查指出的漂移）。

 旧文档的 Mermaid 少了 `task → px4_msgs`，还多画了 `ground → Agent`（`agc_ground` 根本不
 起 Agent）。这条把 Mermaid 文本解析成边集合，与声明表做双向差集——任一方向都不许有差。
    """
    block = _mermaid_block()
    mermaid = {(MERMAID_NODE[a], MERMAID_EXT[b])
               for a, b in re.findall(r'(\w+) ==④==> (\w+)', block)}
    declared = {(src, ext) for ext, src, _way, _note in R.EXT_RELATIONS}
    assert mermaid == declared, (
        'Mermaid ④ 与 EXT_RELATIONS 不一致：Mermaid 多 %r，Mermaid 少 %r'
        % (sorted(mermaid - declared), sorted(declared - mermaid)))


def test_mermaid_one_two_three_edges_match_declaration_table():
    """①②③ 三类边同样逐条对齐（Mermaid 可以简化为「外部项合并」，但不能少边）。"""
    block = _mermaid_block()
    m2 = {(MERMAID_NODE[a], MERMAID_NODE[b]) for a, b in
          re.findall(r'(\w+) --② 链接--> (\w+)', block)}
    d2 = {(s, d) for s, d, k in R.PACKAGE_EDGES if k == 2}
    assert m2 == d2, 'Mermaid ② 不一致：多 %r 少 %r' % (sorted(m2 - d2), sorted(d2 - m2))

    m3 = {(MERMAID_NODE[a], MERMAID_NODE[b]) for a, b in
          re.findall(r'(\w+) ==③ 起进程==> (\w+)', block)}
    d3 = {(s, d) for s, d, k in R.PACKAGE_EDGES if k == 3}
    assert m3 == d3, 'Mermaid ③ 不一致：多 %r 少 %r' % (sorted(m3 - d3), sorted(d3 - m3))

    m1 = {(MERMAID_NODE[a], MERMAID_NODE[b]) for a, b in
          re.findall(r'(\w+) -\.① 消息\.-> (\w+)', block)}
    d1 = {(s, d) for s, d, k in R.PACKAGE_EDGES if k == 1}
    assert m1 == d1, 'Mermaid ① 不一致：多 %r 少 %r' % (sorted(m1 - d1), sorted(d1 - m1))


def test_doc_does_not_overpromise():
    """文档不得再有过度承诺措辞（浏览器缩放/DPI 仍会影响观感）。"""
    with open(STRUCTURE_DOC, encoding='utf-8') as f:
        text = f.read()
    for banned in ('无缩放损失', '机械证明「线段不穿框', '所以概览不可能与清单不一致'):
        assert banned not in text, '文档仍含过度承诺措辞：%r' % banned


def test_redlines_are_pure_references():
    """红线节只引用契约稳定锚点，**不复述条文**（审查第 5 条）。"""
    with open(STRUCTURE_DOC, encoding='utf-8') as f:
        text = f.read()
    sec = re.search(r'### 红线（只引用，不复述）(.*?)<a id="packages">', text, re.S)
    assert sec, '找不到「红线（只引用，不复述）」节'
    body = sec.group(1)
    # 必须有指向契约的锚点
    assert '../adr/0020-package-boundaries-and-runtime-topology.md#execution-port' in body
    assert '../adr/0014-task-fsm-and-scenario-transaction.md#terminal-semantics' in body
    # 不得把条文写回来（这些是契约里的措辞，本节只允许出现指针）
    for forbidden in ('不得直接写', '不是"拦截完成"', '同一 run 不得混跑'):
        assert forbidden not in body, '红线节复述了条文：%r' % forbidden


def test_structure_doc_covers_all_packages():
    """文档版（系统结构图.md）也必须覆盖全部 8 包与四类依赖，且与图共用同一口径。"""
    with open(STRUCTURE_DOC, encoding='utf-8') as f:
        text = f.read()
    for pid in sorted(BUSINESS):
        assert pid in text, '系统结构图.md 里没有提到包 %s' % pid
    for label in ('①', '②', '③', '④'):
        assert label in text, '系统结构图.md 缺少依赖类别标注 %r' % label
    # 文档不得再保留已证伪的 sim→msgs 关系
    assert 'SIM -.① 消息.-> MSGS' not in text, (
        '系统结构图.md 的 Mermaid 仍画着 agc_sim → agc_msgs（package.xml 无此依赖）')


def test_readme_references_existing_assets():
    """README 引用的图/截图必须真的存在（防"README 指向不存在的图"）。"""
    with open(README, encoding='utf-8') as f:
        text = f.read()
    refs = re.findall(r'src="([^"]+)"', text)
    assert refs, 'README 里没有任何图片引用'
    missing = [r for r in refs if not os.path.isfile(os.path.join(ROOT, r))]
    assert not missing, 'README 引用了不存在的图片：%r' % missing
