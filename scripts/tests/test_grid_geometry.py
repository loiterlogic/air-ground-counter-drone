"""栅格几何度量（`grid_geometry.py`）的守护测试（L2，零依赖、不启 ROS）。

**为什么需要它**：ADR-0040 把评价口径拆成三层（几何重建 / 规划可用性 / 实例稳定性），
而这三层的每一个数字都建立在"距离算得对"之上。距离算错时指标不会崩，
它只会**安静地给出一个看似合理的数** —— 那比崩溃危险得多。

因此本测试用**暴力 O(N³) 逐格对拍**钉住 EDT，而不是抽查几个点：
  1. 一维/二维距离变换与暴力结果在 1×1–9×9 全部尺寸、全部种子位置上一致；
  2. 无种子时是 +inf 而不是 0（0 会被读成"障碍就在脚下"）；
  3. 边界距离、集合 IoU、连通域、占据率的分母口径各自可判定；
  4. 与 C++ 侧 `inflation_field.hpp` 的哨兵常量同值（两边不得各说各话）。
"""

from __future__ import annotations

import math
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'tests'))

import grid_geometry as G  # noqa: E402

INFLATION_HPP = (ROOT / 'src' / 'agc_perception' / 'include' / 'agc_perception'
                 / 'inflation_field.hpp')


# ---------------------------------------------------------------- ① 距离变换精确性
def test_squared_distance_transform_matches_brute_force_single_seed():
    """单种子：1×1–9×9 全部尺寸 × 全部种子位置，逐格与暴力对拍。"""
    for w in range(1, 10):
        for h in range(1, 10):
            for sy in range(h):
                for sx in range(w):
                    sq = G.squared_distance_transform(w, h, [(sx, sy)])
                    for y in range(h):
                        for x in range(w):
                            expect = (x - sx) ** 2 + (y - sy) ** 2
                            assert abs(sq[y * w + x] - expect) < 1e-9, (
                                'w=%d h=%d seed=(%d,%d) at (%d,%d): 期望 %d 实得 %r'
                                % (w, h, sx, sy, x, y, expect, sq[y * w + x]))


def test_squared_distance_transform_matches_brute_force_multi_seed():
    """多种子（最近者胜）：验证两遍可分离变换确实给出**欧氏**最近距离，
    而不是"先竖直后水平各自取最近"这种错误组合。"""
    for w in range(1, 9):
        for h in range(1, 9):
            seeds = [(i % w, i // w) for i in range(0, w * h, 3)]
            sq = G.squared_distance_transform(w, h, seeds)
            for y in range(h):
                for x in range(w):
                    best = min((x - i) ** 2 + (y - j) ** 2 for (i, j) in seeds)
                    assert abs(sq[y * w + x] - best) < 1e-9, (
                        'w=%d h=%d at (%d,%d): 期望 %d 实得 %r'
                        % (w, h, x, y, best, sq[y * w + x]))


def test_distance_is_euclidean_not_manhattan():
    """(3,4) 的格距平方必须是 25（欧氏），不是 49（曼哈顿）。"""
    sq = G.squared_distance_transform(5, 5, [(0, 0)])
    assert sq[4 * 5 + 3] == 25
    assert sq[4 * 5 + 3] != 49, '曼哈顿距离会让斜向边界距离系统性偏大'


# ---------------------------------------------------------------- ② 无种子语义
def test_no_seed_yields_infinite_meters_not_zero():
    """没有占据格时距离必须是 +inf。

    若把"无种子"当成距离 0，整张没有障碍的图会被判成"处处障碍" ——
    规划器原地不动，而原因在日志里看不出来。
    """
    meters = G.distance_field_meters(4, 4, 0.5, [0] * 16)
    assert all(not math.isfinite(d) for d in meters)
    assert all(d > 0 for d in meters), '绝不能是 0（0 会被读成"障碍就在脚下"）'


def test_sentinel_constants_match_cpp_side():
    """哨兵常量必须与 C++ 侧同值 —— 两边算距离的口径不得各说各话。"""
    src = INFLATION_HPP.read_text(encoding='utf-8')
    assert 'constexpr double kSeedInf = 1e18;' in src, (
        'C++ 侧哨兵必须是有界值；Python 侧 SEED_INF 必须与它同值')
    assert 'constexpr double kNoSeedThreshold = 5e17;' in src
    assert G.SEED_INF == 1e18
    assert G.NO_SEED_THRESHOLD == 5e17


# ---------------------------------------------------------------- ③ 边界距离
def test_boundary_distance_zero_for_identical_masks():
    m = [0, 1, 1, 0]
    d = G.boundary_distance(m, m, 2, 2, 0.5)
    assert d is not None
    assert d['max'] == 0.0


def test_boundary_distance_detects_uniform_shift():
    """整体偏移一格 ⇒ 边界距离必须是**一格**（这正是"整体偏移"要抓的）。"""
    a = [1, 0, 0, 0]
    b = [0, 1, 0, 0]
    d = G.boundary_distance(a, b, 4, 1, 0.5)
    assert d is not None
    assert abs(d['max'] - 0.5) < 1e-9, '一格 = 0.5 m'


def test_boundary_distance_none_when_one_side_empty():
    """任一侧为空时返回 None，**不返回 0** —— 0 会被误读成"完全重合"。"""
    assert G.boundary_distance([0, 0, 0, 0], [1, 0, 0, 0], 4, 1, 0.5) is None
    assert G.boundary_distance([1, 0, 0, 0], [0, 0, 0, 0], 4, 1, 0.5) is None


# ---------------------------------------------------------------- ④ 集合与实例
def test_set_iou_empty_sets_are_none_not_one():
    """两个空集的 IoU 是 None（不是 1.0）：空集没有"重合"可言。"""
    assert G.set_iou(set(), set()) is None
    assert G.set_iou({1, 2}, {1, 2}) == 1.0
    assert G.set_iou({1}, {2}) == 0.0


def test_connected_components_uses_8_neighbourhood():
    """对角相接必须连成一个域 —— 4 邻域会把同一障碍拆成多个实例。"""
    # 2×2：对角两个格
    mask = [1, 0, 0, 1]
    comps = G.connected_components_8(mask, 2, 2, min_cells=1)
    assert len(comps) == 1, '对角相接在 8 邻域下是同一个域（4 邻域会得到 2 个）'


def test_instance_drift_zero_for_identical_frames():
    mask = [0, 1, 1, 0, 0, 0, 0, 0, 0]
    d = G.instance_drift(mask, mask, 3, 3, min_cells=1)
    assert d is not None
    assert d['max'] == 0.0


def test_instance_drift_detects_position_jump():
    """一个障碍整体挪一格 ⇒ 实例抖动必须是 1 格（数量差可能是 0）。"""
    a = [0] * 16
    b = [0] * 16
    a[0] = 1
    b[1] = 1
    d = G.instance_drift(a, b, 4, 4, min_cells=1)
    assert d is not None
    assert abs(d['max'] - 1.0) < 1e-9


# ---------------------------------------------------------------- ⑤ 占据率口径
def test_occupancy_ratio_denominator_is_fixed():
    """分母固定为 factor²，不是"已观测细格数"。

    若分母按已观测数归一，一个只看到 1 格、而那格被占的粗格会得到 1.0 ——
    与"整格全占"无法区分，评价会系统性高估。
    """
    fine = [1, 0, 0, 0]     # 2×2 细格，只占 1 个
    out, cw, ch = G.occupancy_ratio_coarse(fine, 2, 2, 2)
    assert (cw, ch) == (1, 1)
    assert out[0] == 0.25, '固定分母下是 0.25，而不是 1.0'


def test_occupancy_ratio_matches_cpp_formula():
    """与 C++ 侧 `occupancyRatio` 同口径：分子数占据细格，分母 factor²。"""
    hpp = (ROOT / 'src' / 'agc_perception' / 'include' / 'agc_perception'
           / 'multi_res_grid.hpp').read_text(encoding='utf-8')
    assert 'const int total = geo.factor * geo.factor;' in hpp, (
        'C++ 侧分母必须是固定 factor²；改了要让本测试同步')
    fine = [1, 1, 0, 0]
    out, _, _ = G.occupancy_ratio_coarse(fine, 2, 2, 2)
    assert out[0] == 0.5


# ---------------------------------------------------------------- ⑥ 方向五补齐的指标
def test_hausdorff_is_worst_point_not_mean():
    """Hausdorff 必须报**最坏点**，不是平均偏移。

    与 `boundary_distance` 的分工：那个给分布（p50/p90），这个给最坏值。
    对小障碍，最坏值往往由单个错位点决定 —— 那是平均值看不见的。
    """
    # 两个**多点**集合：绝大多数格重合，只有一个孤立的点偏出去很远。
    # 单点集不合适（p50 与 max 相等，区分不出两个指标）；
    # 相邻偏移也不合适（偏出去 1 格时 p50 可能是 0，但那只是"贴着"）。
    a = [1, 1, 1, 1, 0, 0, 0, 1]     # 第 0-3 格 + 第 7 格（孤立远点）
    b = [1, 1, 1, 1, 0, 0, 0, 0]     # 第 0-3 格
    hd = G.hausdorff(a, b, 8, 1, 1.0)
    bd = G.boundary_distance(a, b, 8, 1, 1.0)
    assert hd == 4.0, (
        '最坏点：a 的第 7 格到 b 最近的第 3 格 = 4 格，实得 %r' % hd)
    assert bd['p50'] < hd, (
        '边界距离的 p50 只看多数点（4 个里有 3 个重合 ⇒ p50=0），'
        '而 Hausdorff 抓那个孤立远点；实得 p50=%r hd=%r' % (bd['p50'], hd))


def test_hausdorff_is_bidirectional():
    """Hausdorff 必须**双向**取最大。

    单向会漏掉"我漏检了一大片"这类错误：只算 `a→b` 时，如果 a 只有 1 个点
    而 b 有 20 个点，单向距离很小（那 1 个点离 b 很近），完全看不出"b 的大部分
    没被 a 覆盖"。本用例构造**两个方向距离不同**的输入，单向实现必然失败。
    """
    # a 在左端密集，b 在右端密集 ⇒ a→b 与 b→a 都大；
    # 但 a 只有 1 点、b 有 5 点 ⇒ 单向 a→b 小、单向 b→a 大
    a = [1, 0, 0, 0, 0, 0, 0, 0]          # 只有最左 1 格
    b = [0, 0, 0, 0, 1, 1, 1, 1]          # 右边 4 格
    hd = G.hausdorff(a, b, 8, 1, 1.0)
    assert hd == 7.0, (
        '双向取最大：a 的格到 b 最近是 4 格、b 的最左格到 a 是 4 格、'
        'b 的最右格到 a 是 7 格 ⇒ 应为 7，实得 %r' % hd)
    # 单向 a→b 会得到 4（漏掉 b 右端那一大片）
    assert hd > 4.0, '单向实现会得到 4（漏掉"b 的大部分没被覆盖"）'


def test_hausdorff_none_when_one_side_empty():
    assert G.hausdorff([0, 0, 0, 0], [1, 0, 0, 0], 4, 1) is None
    assert G.hausdorff([1, 0, 0, 0], [0, 0, 0, 0], 4, 1) is None


def test_obstacle_errors_pair_by_centroid_not_iou():
    """逐障碍中心/面积误差必须按**质心最近**配对。

    为什么不用 IoU 配对：小障碍在 0.5 m 栅格上只有 1–3 格，边界一偏 IoU 就掉到 0，
    按 IoU 会大量配对失败（表现为"全部漏检"）。质心配对对小目标稳健。
    """
    W = H = 10
    # 真值：一个 2x2 障碍在 (1,1)
    truth_cells = [1 * W + 1, 1 * W + 2, 2 * W + 1, 2 * W + 2]
    # 地图：同一个障碍被画大成 3x3
    mask = [0] * (W * H)
    for j in range(1, 4):
        for i in range(1, 4):
            mask[j * W + i] = 1
    r = G.obstacle_errors(mask, [set(truth_cells)], W, H, 0.5)
    assert r is not None
    assert r['matched'] == 1
    # 面积从 4 变 9 ⇒ 相对误差 +1.25
    assert abs(r['area_ratio_p50'] - 1.25) < 1e-9, r


def test_collision_counts_free_but_truth_occupied():
    """碰撞格 = 判为可通行（0）但真值是障碍。这是最危险的一类错误。"""
    W, H = 5, 1
    risk = [0, 0, 0, 0, 0]
    truth = [0, 1, 0, 0, 0]
    r = G.collision_and_clearance(risk, truth, W, H, 0.5)
    assert r['collision_cells'] == 1


def test_clearance_excludes_collision_cells():
    """间隙统计必须**排除碰撞格**。

    碰撞格到真值障碍的距离必然是 0（它自己就是障碍），把它算进去会让
    `clearance_min_m` 恒为 0 —— 那个数字就失去区分力了。
    """
    W, H = 6, 1
    risk = [0, 0, 0, 0, 0, 0]
    truth = [0, 1, 0, 0, 0, 0]     # 第 1 格是障碍，但地图判它 free
    r = G.collision_and_clearance(risk, truth, W, H, 1.0)
    assert r['collision_cells'] == 1
    assert r['clearance_min_m'] == 1.0, (
        '排除碰撞格后，最近的自由格距障碍 1 格；若把碰撞格算进去会得到 0')


# --------------------------------------------------------------------------- 规划成功率
# **口径**：`astar_grid` 量的是"这张栅格图上从起点到终点存不存在可通行路径"。
# 它**不**含动力学、不含车体积（膨胀由风险图承担）、不含倒车。
# 下面的用例全部是"已知答案"的构造图，因此能证明实现是对的，
# 而不是"在真实数据上看起来合理"。


def test_astar_all_free_is_reachable():
    w = h = 20
    found, plen, _ = G.astar_grid([0] * (w * h), w, h, (0, 0), (19, 19))
    assert found
    # 对角距离 = 19·√2（8 邻域可以走纯对角）
    assert plen == pytest.approx(19 * math.sqrt(2), rel=1e-9)


def test_astar_all_blocked_is_unreachable():
    w = h = 20
    found, plen, _ = G.astar_grid([100] * (w * h), w, h, (0, 0), (19, 19))
    assert not found
    assert plen is None


def test_astar_wall_with_gap_is_reachable():
    # 一堵竖墙、只留一个缺口：必须能找到，且路径长于直连（绕路）。
    w = h = 21
    cells = [0] * (w * h)
    for y in range(h):
        # 缺口开在 y=0，**不在直连线 y=10 上** —— 否则直连就穿过缺口，
        # "必须绕行"的断言恒假（那是用例写错，不是实现错）。
        if y != 0:
            cells[y * w + 10] = 100
    found, plen, _ = G.astar_grid(cells, w, h, (0, 10), (20, 10))
    assert found
    direct = 20.0
    assert plen > direct, '必须绕行，不能穿墙'


def test_astar_wall_without_gap_is_unreachable():
    # **能红的关键用例**：把缺口堵上，同一张图必须变成不可达。
    # 若实现把 100 当成"可通行但代价高"，这里会红。
    w = h = 21
    cells = [0] * (w * h)
    for y in range(h):
        cells[y * w + 10] = 100
    found, _, _ = G.astar_grid(cells, w, h, (0, 10), (20, 10))
    assert not found


def test_astar_unknown_is_impassable_by_default():
    # 未知（-1）默认不可通行 —— 与 planning_policy.hpp 的 classifyCell 同口径。
    w = h = 10
    cells = [0] * (w * h)
    for y in range(h):
        cells[y * w + 5] = -1
    found, _, _ = G.astar_grid(cells, w, h, (0, 5), (9, 5))
    assert not found, '未知默认不可通行'
    # 显式放行后才通（对照：证明上面那个 False 来自未知判据，不是别的原因）
    found2, _, _ = G.astar_grid(
        cells, w, h, (0, 5), (9, 5), allow_unknown=True)
    assert found2


def test_astar_risk_band_is_passable_but_costly():
    # 1..99 是"有代价"，**可通行**。若实现把它当占据，这里会红。
    w = h = 10
    cells = [0] * (w * h)
    for y in range(h):
        cells[y * w + 5] = 50
    found, plen, _ = G.astar_grid(cells, w, h, (0, 5), (9, 5))
    assert found, '风险带必须可通行（它是代价，不是禁止）'
    # **注意口径**：`plen` 是**几何路径长度**（米），风险代价只影响搜索的
    # `g` 值、不改变几何长度。因此这里不能拿 `plen` 比大小 ——
    # 那会得到"相等"，然后被误读成"风险带没生效"。
    # 正确的判据是：风险带**可通行**（上面那句），且**绕开时几何路径会变长**。
    # 下面构造"中间一列风险带、但旁边完全可绕"的图：A* 应当选择**绕行**
    # （几何更长但代价更低）—— 这才是代价真正起作用的证据。
    w2 = h2 = 11
    cells2 = [0] * (w2 * h2)
    for y in range(1, h2):               # **留出第 0 行可绕**：整列铺满就没有"绕行"可言
        cells2[y * w2 + 5] = 99          # 高代价竖带（但可通行）
    found2, plen2, _ = G.astar_grid(cells2, w2, h2, (0, 5), (10, 5))
    assert found2
    # 绕行必然长于直连 10 m（除非它选择穿过高代价带 —— 那说明代价没进 step_cost）
    assert plen2 > 10.0, 'A* 应当绕开高代价带，而不是直线穿过'


def test_astar_endpoint_in_obstacle_fails_without_escape():
    # 端点不可通行 ⇒ 直接失败。**不做"就近脱困"**：
    # 那是规划器的策略，评价器替它脱困等于替它作弊。
    w = h = 10
    cells = [0] * (w * h)
    cells[0] = 100            # 起点就在障碍里
    found, _, _ = G.astar_grid(cells, w, h, (0, 0), (9, 9))
    assert not found


def test_astar_budget_exhaustion_counts_as_failure():
    # 展开预算用尽 = 失败（"超时一律算失败"）。
    # 静默返回成功会把大图的搜索成本隐藏起来。
    w = h = 60
    cells = [0] * (w * h)
    found, _, exp = G.astar_grid(
        cells, w, h, (0, 0), (59, 59), max_expansions=5)
    assert not found
    assert exp > 5


def test_planning_success_rate_counts_frames():
    # 三帧里两帧通、一帧堵 ⇒ 2/3。
    w = h = 10
    open_cells = [0] * (w * h)
    blocked = [100] * (w * h)
    frames = [{'data': open_cells}, {'data': open_cells}, {'data': blocked}]
    r = G.planning_success_rate(frames, w, h, (0, 0), (9, 9))
    assert r['n_frames'] == 3
    assert r['n_success'] == 2
    assert r['success_rate'] == pytest.approx(2 / 3)


def test_planning_success_rate_skips_wrong_size_frames():
    # 尺寸不符的帧必须**跳过**（不计入分母），不能算作失败 ——
    # 否则"几何换档"会被误读成"规划失败率上升"。
    w = h = 10
    frames = [{'data': [0] * (w * h)}, {'data': [0] * 3}]
    r = G.planning_success_rate(frames, w, h, (0, 0), (9, 9))
    assert r['n_frames'] == 1
    assert r['n_success'] == 1


def test_planning_success_rate_empty_input():
    r = G.planning_success_rate([], 10, 10, (0, 0), (9, 9))
    assert r['success_rate'] is None
    assert r['n_frames'] == 0
