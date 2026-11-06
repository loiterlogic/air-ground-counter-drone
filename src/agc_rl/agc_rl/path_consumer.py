"""路径消费：五类质量门 + 路径裁剪 + 前视参考点（G2 确定性占位消费者）。

本模块是 `agc_rl` 侧"路径 → 参考"的**纯逻辑**部分（无 ROS 依赖），因此可被 golden test
直接覆盖；ROS 接线在 `agc_rl.inference_node`。

## 身份（必须如实，见 ADR-0013）

这是**确定性占位消费者**，不是学习策略、不是局部避障：

* 它把路径变成一个**参考点/航向**，交给同一套既有 `action_to_twist` 映射；
* 它**不改变** `agc_rl.interface` 的 obs / action 空间，也**不**让路径进入训练观测
 （传输缝 ≠ 模型观测缝，ADR-0013）；
* 因此"能沿路径走"**不是**"训练 RL 已具备路径跟踪能力"。

## 五类质量门（ADR-0013）

按顺序判，任一不过即**拒绝整条路径**（消费侧缓存清空、输出零速）：

1. `NEVER_RECEIVED` —— 启动后从未收到过路径；
2. `EMPTY` —— `poses` 为空；
3. `TOO_SHORT` —— 少于 2 个位姿（无法确定行进方向，对应 RPP 的 `length of one`）；
4. `FRAME_MISMATCH` —— 顶层 `frame_id` 不是期望帧（默认 `world`）；
5. `STALE` —— 路径年龄超过有效期。

**过期判据用"源 stamp 与仿真时钟之差"**，不是"距现在多久"：源 stamp 由发布方按 `/clock`
打，节点用同一 `/clock` 的当前值相减，于是"重新打 `now()`"无法掩盖过期；仿真 reset 导致
时跳时，`age < 0`（stamp 在未来）按**不可信**处理，同样拒绝。

## 限界最近点与前视（提炼自 MPPI / RPP，非照搬实现）

* 先在**路径积分弧长窗口**内找最近点（避免折返路径选到后段）；
* 再按**前视弧长**取参考点（"局部策略看多远"的唯一参数）；
* 路径点自己的 `header.stamp` **不被信任**（Nav2 MPPI 同样以车体时刻覆盖路径点 stamp）。
"""

import math

# 质量门拒绝原因（字符串常量，直接进日志/证据，勿随意改名）
NEVER_RECEIVED = 'never_received'
EMPTY = 'empty'
TOO_SHORT = 'too_short'
FRAME_MISMATCH = 'frame_mismatch'
STALE = 'stale'

REASON_TEXT = {
    NEVER_RECEIVED: '从未收到路径',
    EMPTY: '路径为空',
    TOO_SHORT: '路径位姿少于 2 个',
    FRAME_MISMATCH: '路径 frame_id 与期望帧不一致',
    STALE: '路径过期',
}

MIN_POSES = 2


class PathGateResult:
    """质量门判定结果（不可变，便于断言与日志）。"""

    __slots__ = ('ok', 'reason')

    def __init__(self, ok, reason=''):
        self.ok = bool(ok)
        self.reason = reason if not ok else ''

    def __eq__(self, other):
        if not isinstance(other, PathGateResult):
            return NotImplemented
        return self.ok == other.ok and self.reason == other.reason

    def __repr__(self):
        return 'PathGateResult(ok=%r, reason=%r)' % (self.ok, self.reason)


def _xy(pose_stamped):
    p = pose_stamped.pose.position
    return float(p.x), float(p.y)


def check_path_gate(path, expected_frame, age_s, max_age_s, ever_received):
    """五类质量门。返回 `PathGateResult`；`path` 为 `None` 表示当前无路径。

 参数
 ----
 path : nav_msgs/Path 或 None
 expected_frame : str，期望的顶层坐标系（本仓为 `world`）
 age_s : float 或 None，源 stamp 与**仿真时钟当前值**之差（秒）；`None` = 无法计算
 max_age_s : float，有效期（秒）；`<= 0` 表示不做过期检查（显式关闭）
 ever_received : bool，启动后是否曾收到过路径
    """
    if path is None:
        return PathGateResult(False, NEVER_RECEIVED if not ever_received else STALE)

    poses = getattr(path, 'poses', None) or []
    if len(poses) == 0:
        return PathGateResult(False, EMPTY)
    if len(poses) < MIN_POSES:
        return PathGateResult(False, TOO_SHORT)

    frame = (getattr(path.header, 'frame_id', '') or '').strip()
    if frame != expected_frame:
        return PathGateResult(False, FRAME_MISMATCH)

    if max_age_s is not None and max_age_s > 0.0:
        # age_s 为 None（无法算）按过期处理：宁停不走。
        if age_s is None or age_s < 0.0 or age_s > max_age_s:
            return PathGateResult(False, STALE)

    return PathGateResult(True)


def _segment_lengths(points):
    out = []
    for i in range(1, len(points)):
        (x0, y0), (x1, y1) = points[i - 1], points[i]
        out.append(math.hypot(x1 - x0, y1 - y0))
    return out


def _cumulative(points):
    """各点到路径起点的累计弧长（长度与 points 一致，首项 0）。"""
    cum = [0.0]
    for seg in _segment_lengths(points):
        cum.append(cum[-1] + seg)
    return cum


def _interpolate(points, cum, s):
    """按弧长 `s` 在折线上线性插值出一个点；超出端点则夹到端点。"""
    if s <= 0.0:
        return points[0]
    if s >= cum[-1]:
        return points[-1]
    lo, hi = 0, len(cum) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if cum[mid] <= s:
            lo = mid
        else:
            hi = mid
    span = cum[hi] - cum[lo]
    if span <= 1e-12:
        return points[lo]
    t = (s - cum[lo]) / span
    (x0, y0), (x1, y1) = points[lo], points[hi]
    return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))


def nearest_index(points, cum, robot_xy, search_dist):
    """在**起点起 search_dist 弧长窗口**内找离车最近的路径点索引。

 限界的意义：路径折返时，全路径线性扫会把"返程段"误判为更近，从而选到后段。
 返回 `(index, dist)`；`search_dist <= 0` 表示不限界。
    """
    limit = cum[-1] if search_dist is None or search_dist <= 0.0 else min(search_dist, cum[-1])
    rx, ry = robot_xy
    best_i, best_d = 0, float('inf')
    for i, (x, y) in enumerate(points):
        if cum[i] > limit:
            break
        d = math.hypot(x - rx, y - ry)
        if d < best_d:
            best_i, best_d = i, d
    return best_i, best_d


def _advance_index(points, cum, start_i, advance_m):
    """从 start_i 沿路径前进 advance_m 后落到的点索引（不越界）。"""
    target = cum[start_i] + max(0.0, advance_m)
    i = start_i
    while i + 1 < len(points) and cum[i] < target:
        i += 1
    return i


def tracking_reference(path, robot_xy, params):
    """由合格路径算出跟踪参考。

 返回 dict：
 * `point` —— 参考点 (x, y)（world 系）
 * `nearest` —— 限界最近的路径点 (x, y)
 * `nearest_idx`/`target_idx` —— 索引（便于日志）
 * `remaining_m`—— 参考点到路径末端的剩余弧长
 * `finished` —— 参考点是否已到路径末端且距末端小于 `goal_tol_m`

 `params` 键：
 * `search_dist_m` —— 最近点搜索窗口（弧长，`<=0` 不限界）
 * `lookahead_m` —— 前视弧长（"局部策略看多远"的唯一参数）
 * `goal_tol_m` —— 末端到位容差
    """
    points = [_xy(p) for p in path.poses]
    cum = _cumulative(points)
    search = float(params.get('search_dist_m', 0.0))
    lookahead = max(0.0, float(params.get('lookahead_m', 1.0)))
    goal_tol = max(0.0, float(params.get('goal_tol_m', 0.3)))

    near_i, near_d = nearest_index(points, cum, robot_xy, search)
    tgt_i = _advance_index(points, cum, near_i, lookahead)
    s = min(cum[near_i] + lookahead, cum[-1])
    point = _interpolate(points, cum, s)

    end = points[-1]
    remain = math.hypot(point[0] - end[0], point[1] - end[1])
    # 退化路径（所有点重合，total_arclength == 0）下 `_advance_index` 只能停在 index 0，
    # 但"参考点已在末端且车在容差内"仍成立 → 必须判 finished，否则到点后永不零速。
    # 判据用**参考点到末端 + 车到末端**双条件，与路径是否退化无关。
    car_to_end = math.hypot(robot_xy[0] - end[0], robot_xy[1] - end[1])
    finished = (remain <= goal_tol) and (car_to_end <= goal_tol)
    return {
        'point': point,
        'nearest': points[near_i],
        'nearest_idx': near_i,
        'nearest_dist_m': near_d,
        'target_idx': tgt_i,
        'remaining_m': remain,
        'finished': finished,
    }


def goal_consistent_with_path(path, goal_xy, tol_m):
    """路径末端与 goal 是否一致（防止"路径指向旧目标、goal 已换"）。

 不一致时**不得**继续跟踪该路径，也**不得**静默退回 goal-only——由调用方按零速处理。
    """
    if path is None or not getattr(path, 'poses', None):
        return False
    end = _xy(path.poses[-1])
    return math.hypot(end[0] - goal_xy[0], end[1] - goal_xy[1]) <= max(0.0, float(tol_m))


def straight_path_points(start_xy, goal_xy, spacing_m):
    """几何/直连占位的路径点生成（**仅用于台架/单测**；在线节点由发布方给路径）。

    直连 = 起点到目标的一条直线按 `spacing_m` 采样（含首尾）。不是 Navfn、不看 costmap。
    """
    sx, sy = start_xy
    gx, gy = goal_xy
    dist = math.hypot(gx - sx, gy - sy)
    step = max(1e-3, float(spacing_m))
    n = max(1, int(math.ceil(dist / step)))
    pts = []
    for i in range(n + 1):
        t = i / float(n)
        pts.append((sx + t * (gx - sx), sy + t * (gy - sy)))
    return pts
