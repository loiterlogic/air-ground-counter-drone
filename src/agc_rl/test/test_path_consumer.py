"""G2 判据：路径消费的五类质量门、限界最近点与前视参考（golden tests）。

判据对应 [ADR-0013 (k)(l)](../../../docs/adr/0013-ground-planning-path-contract.md#top) 与
[ADR-0013](../../../docs/adr/0013-ground-planning-path-contract.md#top) (c)：

* 五类质量门（从未收到 / 空 / 单点 / 帧不一致 / 过期）各自独立拒绝，不得合并成一句"无效"；
* 过期用**源 stamp 与仿真时钟之差**判定，`age < 0`（stamp 在未来，reset 时跳）也拒绝；
* 限界最近点在**折返路径**上不得选到后段；
* 前视参考沿弧长前进，不越过末端；
* 路径末端与 goal 不一致时**不得**判为可跟踪（禁止隐性 goal-only）。
"""

from agc_rl import path_consumer as pc


class _Pose:
    def __init__(self, x, y):
        self.position = type('P', (), {'x': x, 'y': y})()


class _PoseStamped:
    def __init__(self, x, y):
        self.pose = _Pose(x, y)


class _Header:
    def __init__(self, frame_id):
        self.frame_id = frame_id


class _Path:
    def __init__(self, pts, frame_id='world'):
        self.header = _Header(frame_id)
        self.poses = [_PoseStamped(x, y) for x, y in pts]


WORLD = 'world'
PARAMS = {'search_dist_m': 0.0, 'lookahead_m': 1.0, 'goal_tol_m': 0.3}


# ----------------------------------------------------------------------------- 五类质量门
def test_gate_never_received():
    r = pc.check_path_gate(None, WORLD, None, 5.0, ever_received=False)
    assert r == pc.PathGateResult(False, pc.NEVER_RECEIVED)


def test_gate_empty():
    r = pc.check_path_gate(_Path([]), WORLD, 0.0, 5.0, ever_received=True)
    assert r.reason == pc.EMPTY


def test_gate_too_short():
    r = pc.check_path_gate(_Path([(0.0, 0.0)]), WORLD, 0.0, 5.0, True)
    assert r.reason == pc.TOO_SHORT


def test_gate_frame_mismatch():
    r = pc.check_path_gate(_Path([(0, 0), (1, 0)], frame_id='map'), WORLD, 0.0, 5.0, True)
    assert r.reason == pc.FRAME_MISMATCH


def test_gate_stale():
    r = pc.check_path_gate(_Path([(0, 0), (1, 0)]), WORLD, 6.0, 5.0, True)
    assert r.reason == pc.STALE


def test_gate_stale_when_age_uncomputable():
    """无可用 stamp → 无法证明新鲜 → 按过期拒绝（宁停不走）。"""
    r = pc.check_path_gate(_Path([(0, 0), (1, 0)]), WORLD, None, 5.0, True)
    assert r.reason == pc.STALE


def test_gate_stale_on_negative_age_after_reset():
    """仿真 reset 导致 stamp 在"未来"：不可信，必须拒绝而不是当成 0 岁。"""
    r = pc.check_path_gate(_Path([(0, 0), (1, 0)]), WORLD, -3.0, 5.0, True)
    assert r.reason == pc.STALE


def test_gate_accepts_valid_path():
    r = pc.check_path_gate(_Path([(0, 0), (1, 0)]), WORLD, 1.0, 5.0, True)
    assert r.ok and r.reason == ''


def test_gate_age_check_disabled_when_max_age_non_positive():
    r = pc.check_path_gate(_Path([(0, 0), (1, 0)]), WORLD, 999.0, 0.0, True)
    assert r.ok


def test_gate_never_received_takes_precedence_over_stale():
    """从未收到与"曾收到但已无路径"必须可区分（对应 G2 启动证据 ① 与 ②）。"""
    r1 = pc.check_path_gate(None, WORLD, None, 5.0, ever_received=False)
    r2 = pc.check_path_gate(None, WORLD, None, 5.0, ever_received=True)
    assert r1.reason == pc.NEVER_RECEIVED
    assert r2.reason == pc.STALE


# ----------------------------------------------------------------- 限界最近点（折返路径）
def _out_and_back():
    """沿 +x 走 10 m 再原路折返 10 m：几何上前后两段完全重合。"""
    fwd = [(float(i), 0.0) for i in range(11)]
    back = [(float(i), 0.0) for i in range(9, -1, -1)]
    return fwd + back


def test_nearest_bounded_search_stays_in_near_window():
    """限界窗口内的最近点；折返路径上"哪一段"由弧长窗口决定，而非几何重合。"""
    path = _Path(_out_and_back(), frame_id=WORLD)
    ref = pc.tracking_reference(path, (0.5, 0.0), dict(PARAMS, search_dist_m=2.0))
    # 窗口 [0, 2] m 内最近的是起点 (0,0)；序号必落在前 3 个点内
    assert ref['nearest_idx'] <= 3
    assert ref['nearest'] == (0.0, 0.0)


def test_nearest_unbounded_would_pick_later_segment():
    """反证：不限界时，几何上更近的后段会被选中——说明限界不是装饰。

    折返路径（同一条直线往返）两段**几何完全重合**，最近点序号取决于扫描顺序，
    不能作为判据；这里用"绕远后回到起点附近"的路径做反证，后段确实几何更近。
    """
    path = _Path([(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.3, 0.05)], frame_id=WORLD)
    bounded = pc.tracking_reference(path, (0.3, 0.0), dict(PARAMS, search_dist_m=2.0))
    unbounded = pc.tracking_reference(path, (0.3, 0.0), dict(PARAMS, search_dist_m=0.0))
    assert bounded['nearest_idx'] == 0
    assert unbounded['nearest_idx'] == 3


def test_lookahead_advances_by_arclength():
    path = _Path([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)], frame_id=WORLD)
    ref = pc.tracking_reference(path, (0.0, 0.0), dict(PARAMS, lookahead_m=3.0))
    assert ref['point'] == (3.0, 0.0)


def test_lookahead_does_not_pass_end():
    """前视点夹在末端，但**车还没到**时不得判 finished（否则会提前停车）。"""
    path = _Path([(0.0, 0.0), (1.0, 0.0)], frame_id=WORLD)
    ref = pc.tracking_reference(path, (0.0, 0.0), dict(PARAMS, lookahead_m=99.0))
    assert ref['point'] == (1.0, 0.0)
    assert ref['finished'] is False, '车距末端 1.0 m > goal_tol 0.3 m，不得判已到位'


def test_finished_requires_car_within_tolerance():
    """finished 的判据是**车**到末端在容差内，而不是前视点到达末端。"""
    path = _Path([(0.0, 0.0), (1.0, 0.0)], frame_id=WORLD)
    far = pc.tracking_reference(path, (0.0, 0.0), dict(PARAMS, lookahead_m=99.0))
    near = pc.tracking_reference(path, (0.85, 0.0), dict(PARAMS, lookahead_m=99.0))
    assert far['finished'] is False
    assert near['finished'] is True


def test_degenerate_two_identical_points_finished_when_at_goal():
    """退化到位路径（两点重合）：车在末端容差内 → finished=True（本轮返工 B2）。

    修复前：累计弧长全 0 → `_advance_index` 只能停在 index 0 → finished 永假 → 到点后不零速。
    """
    path = _Path([(5.0, 3.0), (5.0, 3.0)], frame_id=WORLD)
    ref = pc.tracking_reference(path, (5.0, 3.0), dict(PARAMS, lookahead_m=1.0))
    assert ref['finished'] is True
    assert ref['point'] == (5.0, 3.0)


def test_degenerate_two_identical_points_not_finished_when_far():
    """退化路径但车距离末端很远 → 不得判 finished（防止"任意退化路径都算到位"）。"""
    path = _Path([(5.0, 3.0), (5.0, 3.0)], frame_id=WORLD)
    ref = pc.tracking_reference(path, (0.0, 0.0), dict(PARAMS, lookahead_m=1.0))
    assert ref['finished'] is False


def test_reference_is_interpolated_not_quantized_to_vertices():
    """前视落在两点之间时必须插值，否则参考会跳变。"""
    path = _Path([(0.0, 0.0), (10.0, 0.0)], frame_id=WORLD)
    ref = pc.tracking_reference(path, (0.0, 0.0), dict(PARAMS, lookahead_m=2.5))
    assert abs(ref['point'][0] - 2.5) < 1e-9


def test_diagonal_arclength_uses_euclidean():
    path = _Path([(0.0, 0.0), (3.0, 4.0)], frame_id=WORLD)
    ref = pc.tracking_reference(path, (0.0, 0.0), dict(PARAMS, lookahead_m=2.5))
    # 3-4-5 三角形：前视 2.5 → (1.5, 2.0)
    assert abs(ref['point'][0] - 1.5) < 1e-9
    assert abs(ref['point'][1] - 2.0) < 1e-9


# -------------------------------------------------------------- goal 一致性与直连点生成
def test_goal_consistency_rejects_mismatched_end():
    path = _Path([(0.0, 0.0), (5.0, 0.0)], frame_id=WORLD)
    assert pc.goal_consistent_with_path(path, (5.0, 0.0), 0.3) is True
    assert pc.goal_consistent_with_path(path, (9.0, 0.0), 0.3) is False


def test_goal_consistency_false_without_path():
    assert pc.goal_consistent_with_path(None, (0.0, 0.0), 0.3) is False


def test_straight_path_points_endpoints_and_spacing():
    pts = pc.straight_path_points((0.0, 0.0), (10.0, 0.0), 1.0)
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (10.0, 0.0)
    assert len(pts) == 11
    for (x0, _), (x1, _) in zip(pts, pts[1:]):
        assert abs((x1 - x0) - 1.0) < 1e-9


def test_straight_path_points_degenerate_zero_length():
    """起点==目标时也必须给至少 2 个点，否则会被 TOO_SHORT 拒掉。"""
    pts = pc.straight_path_points((1.0, 2.0), (1.0, 2.0), 1.0)
    assert len(pts) >= 2


def test_reason_text_covers_all_gate_reasons():
    for reason in (pc.NEVER_RECEIVED, pc.EMPTY, pc.TOO_SHORT, pc.FRAME_MISMATCH, pc.STALE):
        assert reason in pc.REASON_TEXT
