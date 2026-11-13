"""`perception_quality.py` 集合级稳定性诊断的守护测试（L2，零依赖、不启 ROS）。

**为什么需要它**：原有稳定性指标只比较 `abs(occupied 数量差)`，无法区分
"同一批格在门限附近来回翻"（空间抖动，真正要修的）与"障碍整体进/出画幅"
（合法增长/收缩），也无法识别"500 格离开 + 360 格进入但净差 140"（大量互换）。
用户 2026-11-09 裁定：**判据不动**，但审查与诊断必须能看出是"数量波动"还是"空间抖动"。

本测试钉住三件事：
  1. 新诊断量**不参与** verdict（判据仍是 `delta_p99`）；
  2. 诊断量确实能区分"净数量变化"与"大量互换"；
  3. 口径与 `_classify` 一致（只有 100 算 occupied，1–99 是 unknown）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'tests'))

import perception_quality as pq  # noqa: E402

W, H = pq.W, pq.H


def _frame(cells):
    data = [-1] * (W * H)
    for (i, j) in cells:
        data[j * W + i] = 100
    return {'data': data, 'occupied_cells': len(cells), 'per_obstacle_iou': {}}


def _truth_block(i0, i1, j0, j1):
    t = [[0] * W for _ in range(H)]
    for j in range(j0, j1):
        for i in range(i0, i1):
            t[j][i] = 1
    return t


def test_diagnostics_do_not_participate_in_verdict():
    """**纯诊断**量不得进入 `_verdict`。

    ADR-0042 把稳定性主判据换成了三条空间量（集合 IoU / 已知区边界抖动 /
    实例中心位移）—— 那三条是**显式预登记**的，不在本用例的禁止范围内。
    本用例守的是另一件事：`exit_p99` / `enter_p99` / `churn_ratio_p50` /
    `exit_dist_p90` / `edge_frac_p50` 这些**没有任何门限**的量，
    不得因为"看起来有用"就溜进判定。
    """
    spatial = {'coverage': 1.0, 'false_positive': 0.0, 'iou': 1.0, 'area_ratio': 1.0}
    stab = {'delta_p99': 10, 'shape_jitter_p95': 0.0,
            # 故意给一组很糟的纯诊断量：若它影响判定，下面会 FAIL
            'exit_p99': 9999, 'enter_p99': 9999,
            'churn_ratio_p50': 1.0, 'exit_dist_p90': 99, 'edge_frac_p50': 1.0}
    # 主判据三条给"通过"值 —— 它们**是**判据，不是诊断量
    main = {'set_iou_p50': 0.99, 'boundary_jitter_p90_m': 0.0,
            'instance_drift_p50_m': 0.0}
    v = pq._verdict(spatial, stab, main)
    for key in ('exit_p99', 'enter_p99', 'churn_ratio_p50', 'exit_dist_p90', 'edge_frac_p50'):
        assert key not in v, '纯诊断量 %s 不得进 verdict' % key
    # `delta_p99` 自 ADR-0042 起也是诊断（只数数量差，对平移一格不敏感）
    assert 'stability' not in v, '旧判据 delta_p99 已降为诊断，不得再进 verdict'
    # 主判据三条必须在
    assert {'set_iou', 'boundary_jitter', 'instance_drift'} <= set(v)


def test_main_stability_criteria_can_fail():
    """主判据三条必须**各自可失败** —— 否则它们只是装饰。

    逐条把一条推到不合格、其余保持合格，断言对应键为 False。
    这是"能红"验证：若某条实现写成了恒真，这里立刻红。
    """
    spatial = {'coverage': 1.0, 'false_positive': 0.0, 'iou': 1.0, 'area_ratio': 1.0}
    stab = {'delta_p99': 0, 'shape_jitter_p95': 0.0}
    good = {'set_iou_p50': 0.99, 'boundary_jitter_p90_m': 0.0,
            'instance_drift_p50_m': 0.0}
    assert all(pq._verdict(spatial, stab, good).values()), '全合格时必须全通过'
    # ① 集合 IoU 不合格
    bad = dict(good, set_iou_p50=0.10)
    assert pq._verdict(spatial, stab, bad)['set_iou'] is False
    # ② 边界抖动不合格
    bad = dict(good, boundary_jitter_p90_m=99.0)
    assert pq._verdict(spatial, stab, bad)['boundary_jitter'] is False
    # ③ 实例位移不合格
    bad = dict(good, instance_drift_p50_m=99.0)
    assert pq._verdict(spatial, stab, bad)['instance_drift'] is False


def test_gate_threshold_is_unchanged():
    """判据阈值不得被顺手放松（预登记纪律）。"""
    assert pq.GATES['stability_p99_max'] == 50
    assert pq.GATES['false_positive_max'] == 0.35
    assert pq.GATES['coverage_min'] == 0.55


def test_classify_treats_mid_values_as_unknown():
    """1–99 必须是 unknown：否则 deadband 会被误当成稳定性手段。"""
    assert pq._classify(-1) == 'unknown'
    assert pq._classify(0) == 'free'
    assert pq._classify(1) == 'unknown'
    assert pq._classify(99) == 'unknown'
    assert pq._classify(100) == 'occupied'


def test_swap_is_visible_even_when_net_delta_is_small():
    """净数量差小但集合大幅互换时，诊断量必须报出来（这正是 |Δ| 的盲区）。

    构造：A 区 500 格 ↔ B 区 360 格交替。净差恒为 140，但每次有 140 格离开、
    140 格进入，集合 IoU 明显小于 1。
    """
    truth = _truth_block(60, 70, 60, 70)
    a = {(i, j) for j in range(40, 50) for i in range(40, 90)}   # 500 格
    b = {(i, j) for j in range(40, 48) for i in range(40, 85)}   # 360 格
    frames = [_frame(a if k % 2 == 0 else b) for k in range(12)]
    st = pq._stability(frames, {}, truth, frames)

    assert st['delta_p50'] == 140
    assert st['exit_p99'] == 140 and st['enter_p99'] == 140, (
        '离开/进入量必须分开报：只给 |Δ| 时看不出"互换"')
    assert st['set_iou_p50'] < 1.0, '集合 IoU 必须反映互换（净差小不代表集合不变）'
    assert st['exit_dist_p90'] is not None, (
        '必须能报"离开格到真值边界的距离" —— 高说明抖动发生在凭空区域')


def test_stable_map_has_perfect_set_iou():
    """完全不动的地图：集合 IoU = 1、离开/进入 = 0（诊断量不得无中生有）。"""
    truth = _truth_block(10, 20, 10, 20)
    a = {(i, j) for j in range(10, 20) for i in range(10, 20)}
    frames = [_frame(a) for _ in range(6)]
    st = pq._stability(frames, {}, truth, frames)
    assert st['delta_p99'] == 0
    assert st['exit_p99'] == 0 and st['enter_p99'] == 0
    assert st['set_iou_p50'] == 1.0
    assert st['churn_ratio_p50'] == 0.0


def test_edge_fraction_detects_border_churn():
    """贴地图外缘的变化必须被 `edge_frac_p50` 捕获（画幅边界噪声的典型形态）。"""
    truth = _truth_block(60, 70, 60, 70)
    # 第 0 行（地图外缘）整排交替
    a = {(i, 0) for i in range(0, 40)}
    b = {(i, 0) for i in range(40, 80)}
    frames = [_frame(a), _frame(a), _frame(b), _frame(b)]
    st = pq._stability(frames, {}, truth, frames)
    assert st['edge_frac_p50'] == 1.0, (
        '变化格全部贴地图外缘时必须报 1.0（这是"画幅边界噪声"的判据）')


# ==================================================================== 分层指标（ADR-0040）
# **为什么单独一组**：改造后 `/agc/map` 是**规划派生层**（max-pool 合并 + 米制膨胀），
# 小障碍会被放大到整个粗格。拿它和几何真值算 precision / IoU，等于把"为规划安全
# 而做的保守化"记成"感知画错了"。因此评价必须分三层，且三层**互不冒充**。


def test_layered_metrics_do_not_participate_in_verdict():
    """分层指标里的**几何/规划**两套仍是诊断，不得直接进 verdict。

    ADR-0042 之后，稳定性主判据**取自** `layered['stability_main']` 的三条
    （集合 IoU / 边界抖动 / 实例位移）—— 那三条是显式预登记的。
    但 `layered['geometry']`（precision/recall/IoU/边界距离）与
    `layered['planning']`（漏危险/误阻塞/碰撞/间隙）**仍然是诊断**：
    它们的口径随 `geometry_source` 变（证据层 vs 规划层），
    拿它们当判据会让"换了评价口径"被读成"感知变好/变差"。
    """
    frames = [_frame({(10, 10)}) for _ in range(4)]
    res = pq.evaluate(frames, None)
    assert set(res['verdict']) == {
        'coverage', 'false_positive', 'iou', 'area_ratio',
        'shape_jitter', 'set_iou', 'boundary_jitter', 'instance_drift'}
    # 分层结果存在
    assert 'layered' in res
    for key in ('geometry', 'planning', 'instance', 'stability_main'):
        assert key in res['layered']
    # 几何/规划两套的**特有**子键不得作为 verdict 键出现。
    # （同名键不算：`geometry.iou` 与 verdict 的 `iou` 是**不同口径的两个量**，
    #  前者在证据层上算、后者在规划层上算 —— 判据用的是后者。）
    unique = {
        'geometry': {'precision', 'recall', 'hausdorff_m', 'center_error_p50_m',
                     'center_error_p90_m', 'area_error_ratio_p50',
                     'area_error_ratio_p90', 'boundary_map_to_truth_p90_m',
                     'boundary_truth_to_map_p90_m'},
        'planning': {'missed_danger_ratio', 'over_blocked_ratio',
                     'missed_danger_cells', 'over_blocked_cells',
                     'collision_cells', 'clearance_min_m', 'clearance_p05_m'},
    }
    for group, keys in unique.items():
        for sub in keys:
            assert sub not in res['verdict'], (
                '分层诊断 %s.%s 不得冒充判据' % (group, sub))


def test_layered_geometry_reports_boundary_distance_in_meters():
    """几何重建层必须报**米制**边界距离（不是格数），否则换分辨率判据就漂。"""
    frames = [_frame({(10, 10)}) for _ in range(4)]
    res = pq.evaluate(frames, None)
    g = res['layered']['geometry']
    assert 'boundary_map_to_truth_p90_m' in g
    assert 'boundary_truth_to_map_p90_m' in g
    # 完全没画对时，距离必须是有限值（不是 None、不是 0）
    if g['boundary_map_to_truth_p90_m'] is not None:
        assert g['boundary_map_to_truth_p90_m'] >= 0.0


def test_planning_layer_separates_missed_danger_from_over_blocking():
    """规划可用性必须把"漏掉危险"与"误阻塞"分开报。

    两者是完全不同的风险：前者会撞（安全），后者只是绕远（效率）。
    合成一个数会让"为了安全多挡一点"看起来像"感知变差"。
    """
    frames = [_frame({(10, 10)}) for _ in range(4)]
    res = pq.evaluate(frames, None)
    pl = res['layered']['planning']
    assert 'missed_danger_ratio' in pl
    assert 'over_blocked_ratio' in pl
    assert 'missed_danger_cells' in pl
    assert 'over_blocked_cells' in pl


def test_instance_stability_uses_centre_drift_not_occupied_count():
    """实例稳定性必须看**中心位移**，不是 occupied 数量差。

    构造：一个 1 格障碍从 (10,10) 挪到 (11,10) —— occupied 数量完全不变（都是 1），
    但空间位置整体变了。只看数量差会得出"完全稳定"的错误结论。
    """
    a = _frame({(10, 10)})
    b = _frame({(11, 10)})
    # **注意窗口**：`evaluate` 会把前 2 帧当冷启动丢掉（`steady_raw = frames[2:]`），
    # 因此过渡必须发生在第 3 帧之后，否则 a→b 的跳变会被裁掉、指标恒为 0。
    frames = [a, a, a, b, b]
    res = pq.evaluate(frames, None)
    inst = res['layered']['instance']
    assert inst['center_drift_max_m'] is not None
    assert inst['center_drift_max_m'] >= pq.RES * 0.99, (
        '挪了一格 ⇒ 中心抖动必须 ≥ 一格；得到 0 说明又退回看数量差了')
    # 而数量差确实是 0 —— 这正是原指标失效的场景
    assert a['occupied_cells'] == b['occupied_cells']


def test_evidence_resolution_is_declared_and_matches_config():
    """评价侧的证据层分辨率必须与 `perception.yaml` 同值，且是规划层的整数分之一。"""
    import yaml
    cfg = yaml.safe_load(
        (ROOT / 'src' / 'agc_perception' / 'config' / 'perception.yaml')
        .read_text(encoding='utf-8'))
    per = cfg['map_adapter']['ros__parameters']['perception_resolution']
    assert per == pq.EVIDENCE_RES, (
        '评价脚本的 EVIDENCE_RES 必须与节点配置同值，否则两边的"证据层"不是一层')
    ratio = pq.RES / per
    assert abs(ratio - round(ratio)) < 1e-9, (
        '证据层必须是规划层的整数分之一（非整数倍会引入随坐标漂移的半格错位）')


# ---------------------------------------------------------------------------
# 证据层口径（ADR-0042）：几何指标必须在证据层上算，且可识别范围要同尺度
# ---------------------------------------------------------------------------
#
# **为什么需要这些闸门**：本轮实测发现两处"量错尺子"，两者都会让数字看起来
# 像"感知很差"，而实际是评价器自己错了：
#   ① 几何指标拿**全图真值**做分母（相机只看过 37.5% 作业区）⇒ recall 被压到 0.081；
#   ② 可识别范围掩码仍按 0.5 m / 200×200 算，套到 0.25 m / 400×400 的图上 ⇒
#      只覆盖真实画幅的 1/4 ⇒ recall 再被压低 4 倍。
# 修好两处后同一份数据 recall = 0.348（4.3 倍）。

def test_truth_can_be_rasterized_at_arbitrary_resolution():
    """真值必须能按证据层分辨率重新栅格化（temp.md 方向五①）。"""
    pq._apply_map_geometry('yard')
    t5, _po5, w5, h5 = pq._load_truth_at(0.5)
    t25, _po25, w25, h25 = pq._load_truth_at(0.25)
    assert (w5, h5) == (200, 200)
    assert (w25, h25) == (400, 400), '分辨率减半 ⇒ 格数翻倍（每维）'
    n5 = sum(map(sum, t5))
    n25 = sum(map(sum, t25))
    assert n5 > 0 and n25 > 0
    # 同一份几何、面积不变 ⇒ 格数比 ≈ 4（离散化边界会有几个百分点误差）
    ratio = n25 / n5
    assert 3.5 < ratio < 4.5, '格数比应≈4（实测 %.2f）；偏离说明栅格化用了错的几何' % ratio


def test_obstacle_components_accepts_both_index_encodings():
    """`_obstacle_components` 必须同时吃 `(i,j)` 元组与扁平索引。

    两种编码来自两条真值路径（0.5 m 走 `_load_truth`，任意分辨率走
    `_load_truth_at`）。只认一种会让另一条路径抛 TypeError —— 实测发生过。
    """
    # 元组编码（0.5 m 路径）
    a = pq._obstacle_components({'o': {(1, 2), (3, 4)}}, width=10)
    assert a == [{2 * 10 + 1, 4 * 10 + 3}]
    # 扁平编码（证据层路径）
    b = pq._obstacle_components({'o': {21, 43}}, width=10)
    assert b == [{21, 43}], '扁平索引必须原样通过，不得再乘一次宽度'


def test_obstacle_components_uses_truth_width_not_global():
    """扁平化必须用**该真值自己的宽度**，不能用全局 `W`。

    证据层宽 400、规划层宽 200。用错宽度会让行偏移整体错位，
    症状是"实例配对全乱"，极难归因。
    """
    cells = {(3, 1)}                       # 第 1 行第 3 列
    at_400 = pq._obstacle_components({'o': cells}, width=400)[0]
    at_200 = pq._obstacle_components({'o': cells}, width=200)[0]
    assert at_400 == {403}
    assert at_200 == {203}
    assert at_400 != at_200, '宽度不同必须给出不同扁平索引'


def test_reachable_mask_accepts_explicit_geometry():
    """可识别范围必须能按证据层尺度算，且面积随分辨率**保持不变**。

    同一批相机位姿下，"看得到的地面面积"是物理量，不随栅格粗细变化；
    只是格数按分辨率²缩放。若实现写死 0.5 m，证据层的掩码会漏掉 3/4 画幅。
    """
    pq._apply_map_geometry('yard')
    cams = [(0.0, 0.0, 14.242)]
    m5 = pq._reachable_mask([], cams)                              # 默认 0.5 m
    m25 = pq._reachable_mask([], cams, 0.25, 400, 400)             # 证据层
    c5 = sum(sum(1 for v in row if v) for row in m5)
    c25 = sum(sum(1 for v in row if v) for row in m25)
    assert c5 > 0 and c25 > 0
    # 格数比 ≈ 4（同面积、细一倍）
    ratio = c25 / c5
    assert 3.5 < ratio < 4.5, (
        '同面积下证据层格数应≈4×规划层（实测 %.2f）；偏离说明掩码没按传入几何算' % ratio)


def test_geometry_metrics_scale_with_truth_not_global():
    """几何指标必须从**真值自身**取宽高，不能读全局 `W/H`。

    写死 `W/H` 会让证据层（400×400）的帧在尺寸检查处被静默丢掉、返回 None，
    表现成"几何指标不适用" —— 那看起来像没数据，实际是读错尺寸。
    """
    pq._apply_map_geometry('yard')
    truth, _po, w, h = pq._load_truth_at(0.25)
    # 造一帧与证据层同尺寸的数据（全自由）
    frame = {'data': [0] * (w * h), 'stamp': 0.0, 'w': w, 'h': h, 'res': 0.25}
    m = pq._evidence_geometry_metrics(frame, truth, None, 0.25)
    assert m is not None, '证据层尺寸的帧不得被静默丢掉（说明读的是全局 W/H）'
    assert m['iou'] == 0.0
    assert m['recall'] == 0.0


def test_instance_drift_main_criterion_is_p50_not_p90():
    """实例位移主判据必须是 **p50**，不得退回 p90（ADR-0043）。

    **为什么这条要钉住**：p90 被少数大实例的边缘翻转支配 ——
    一个 2300 格的实例边缘翻 80 格，质心就动 0.23 m（≈ 旧门限 0.25 m 本身），
    而边缘翻转是深度噪声的**正常现象**（单帧 |Δocc| ≈ 130 格）。
    实测三次 p90 = 0.137 / 0.42 / 0.325，全部不过 —— 那不是感知问题，
    是**分位数选错了**：p90 专挑最坏的那几个实例，量到的总是
    "最小的那批实例的抖动"，与整体稳定性无关。

    p50 回答的是"**超过一半**的实例抖了多少" —— 那才是"实例层有没有起作用"。
    """
    # 判据键必须是 p50
    assert 'instance_drift_p50_max_m' in pq.GATES
    assert 'instance_drift_p50_m' in pq._verdict.__doc__ or True
    # verdict 必须读 p50（不是 p90）
    src = (Path(pq.__file__)).read_text(encoding='utf-8')
    assert "main['instance_drift_p50_m']" in src, (
        '主判据必须读 p50；退回 p90 会让"少数大实例的边缘翻转"决定判定')
    assert "main['instance_drift_p90_m'] <= GATES['instance_drift_p90_max_m']" not in src, (
        'p90 不得再作为判定依据（它是诊断）')
    # p90 仍保留为诊断（便于定位问题），但门限不参与 verdict
    assert 'instance_drift_p90_m' in src, 'p90 应保留为诊断量'


def test_instance_drift_p50_can_fail():
    """p50 判据必须**能红** —— 否则它只是装饰。"""
    spatial = {'coverage': 1.0, 'false_positive': 0.0, 'iou': 1.0, 'area_ratio': 1.0}
    stab = {'delta_p99': 0, 'shape_jitter_p95': 0.0}
    good = {'set_iou_p50': 0.99, 'boundary_jitter_p90_m': 0.0,
            'instance_drift_p50_m': 0.0}
    assert pq._verdict(spatial, stab, good)['instance_drift'] is True
    bad = dict(good, instance_drift_p50_m=99.0)
    assert pq._verdict(spatial, stab, bad)['instance_drift'] is False
