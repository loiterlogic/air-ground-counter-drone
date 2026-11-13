"""栅格几何度量 —— 边界距离、集合 IoU、实例级抖动（零依赖，纯 Python）。

**为什么单独成一个模块**：`perception_quality.py` 里的指标越来越多，而"几何重建"
与"规划可用性"是两套完全不同的口径（ADR-0040）。把它们混在一个文件里，
下一个人只会继续往里加，最后没人分得清哪个数字在回答哪个问题。

**本文件只放纯计算**，不读地图、不订阅话题、不打印结论 —— 那些归调用方。
这样每条算法都能被 `scripts/tests/` 直接单测（含"能红"的负例）。

**依赖策略（重要）**：本文件**只用标准库**。
理由：`perception_quality.py` 要在**新 clone** 上能跑（见测试分层规范），
而 scipy / numpy 不是本仓的硬依赖；引入它们会让"边界距离"这个指标
在别人机器上静默消失。代价是纯 Python 慢一些 —— 200×200 栅格上
一次 EDT 约几十毫秒，相对仿真耗时可以忽略。

**算法来源**：二维欧氏距离变换用 **Felzenszwalb 一维平方距离变换**沿两轴各一遍
（O(N)）。该算法取自本仓参照实现里的 `fillESDF`（Fast-Planner / RACER 的
`plan_env/src/sdf_map.cpp`），与本仓 C++ 侧 `inflation_field.hpp` 的实现**逐式对应** ——
两边必须给出同一个距离，否则"规划膨胀"与"评价边界距离"会各说各话。
"""

from __future__ import annotations

import math
from collections import deque

# 无种子哨兵。与 C++ 侧 `agc_perception::kSeedInf` 同值同语义：
# 不用 float('inf')，因为 `inf + q²` 参与求交会得到 `inf - inf = NaN`，
# 而 NaN 参与比较恒为 False，包络会静默退化成"照单全收"。
SEED_INF = 1e18
NO_SEED_THRESHOLD = 5e17


def distance_transform_1d(f):
    """Felzenszwalb 一维平方距离变换（原地，返回新列表）。

    输入 `f[q]` 是"这一维上位置 q 的初始代价"，
    输出 `out[q] = min_p ( (q-p)² + f[p] )`。

    与 C++ 侧 `distanceTransform1D` 逐行对应（含 `z[0] = -inf` 与
    `do { k--; ... } while (s <= z[k])` 的循环顺序 —— 顺序反了包络会退化，
    数值上表现为距离整体偏小）。
    """
    n = len(f)
    if n <= 0:
        return list(f)
    v = [0] * n
    z = [0.0] * (n + 1)
    k = 0
    v[0] = 0
    z[0] = -float('inf')
    z[1] = float('inf')
    for q in range(1, n):
        while True:
            vk = v[k]
            denom = 2.0 * q - 2.0 * vk
            s = ((f[q] + q * q) - (f[vk] + vk * vk)) / denom
            if k > 0 and s <= z[k]:
                k -= 1
            else:
                break
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = float('inf')
    out = [0.0] * n
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        dq = q - v[k]
        out[q] = dq * dq + f[v[k]]
    return out


def squared_distance_transform(width, height, seeds):
    """二维平方距离变换。

    `seeds` 是可迭代的 (x, y) 或长度为 width*height 的布尔序列。
    返回长度 width*height 的列表，每格是到最近种子的**平方格距**。
    """
    n = width * height
    grid = [SEED_INF] * n
    if width <= 0 or height <= 0:
        return grid
    if isinstance(seeds, (bytes, bytearray, list, tuple)) and len(seeds) == n:
        for i in range(n):
            if seeds[i]:
                grid[i] = 0.0
    else:
        for (x, y) in seeds:
            if 0 <= x < width and 0 <= y < height:
                grid[y * width + x] = 0.0

    # 逐列（竖直）
    for x in range(width):
        line = [grid[y * width + x] for y in range(height)]
        line = distance_transform_1d(line)
        for y in range(height):
            grid[y * width + x] = line[y]
    # 逐行（水平）
    for y in range(height):
        row = grid[y * width:(y + 1) * width]
        row = distance_transform_1d(row)
        grid[y * width:(y + 1) * width] = row
    return grid


def distance_field_meters(width, height, resolution, occupied):
    """每格到最近占据格的**米制**距离；没有占据格时为 `float('inf')`。"""
    sq = squared_distance_transform(width, height, occupied)
    out = []
    for v in sq:
        if v >= NO_SEED_THRESHOLD:
            out.append(float('inf'))
        else:
            out.append(resolution * math.sqrt(v))
    return out


def boundary_distance(src_mask, dst_mask, width, height, resolution=1.0):
    """`src` 的**占据格**到 `dst` 最近占据格的距离分布（米）。

    **命名说明（避免误读）**：本函数统计的是 `src` 的**全部占据格**，不是只取
    "边界格"。对几何重建评价这正是想要的量 —— 它同时抓住"整体偏移"（所有格同向偏）
    与"局部外扩"（边缘格离得远），而不像单向 Hausdorff 只看最远的那一个点。

    **为什么要双向调用**：单向只回答"我画的东西离真值多远"，不回答"真值有没有被我漏掉"。
    调用方对两个方向各调一次：`src=地图` 得到"画出去的离真值多远"，
    `src=真值` 得到"真值离最近地图格多远"（后者大 ⇒ 漏检多）。

    **为什么不用 scipy 的 directed_hausdorff**：那是**点集**之间的最大最小距离，
    对栅格要先把每格展成点，代价 O(N²)；这里用距离变换 + 按掩码取值就够，O(N)。

    返回 dict：`p50` / `p90` / `max`（米），以及参与统计的格数 `n`。
    任一侧为空时返回 None（**不返回 0** —— 0 会被误读成"完全重合"）。
    """
    if not src_mask or not dst_mask:
        return None
    dist = distance_field_meters(width, height, resolution, dst_mask)
    vals = []
    for i, v in enumerate(src_mask):
        if v and math.isfinite(dist[i]):
            vals.append(dist[i])
    if not vals:
        return None
    vals.sort()
    return {
        'p50': _pct(vals, 0.50),
        'p90': _pct(vals, 0.90),
        'max': vals[-1],
        'n': len(vals),
    }


def _pct(sorted_vals, q):
    if not sorted_vals:
        return None
    k = min(int(q * (len(sorted_vals) - 1)), len(sorted_vals) - 1)
    return sorted_vals[k]


def set_iou(a, b):
    """两个索引集合的 IoU。两者都空时返回 None（不是 1.0 —— 空集没有"重合"可言）。"""
    if not a and not b:
        return None
    union = len(a | b)
    return (len(a & b) / union) if union else None


def connected_components_8(mask, width, height, min_cells=1):
    """8 邻域连通域（返回每域格索引集合的列表）。

    **为什么 8 邻域**：闭运算后的碎片常只剩对角相接，4 邻域会把同一个障碍
    拆成多个实例，实例级指标因此虚高（"实例数"翻倍）。与 C++ 侧
    `labelBlobs8` 同一连通性口径。
    """
    seen = [False] * (width * height)
    out = []
    for start in range(width * height):
        if not mask[start] or seen[start]:
            continue
        comp = set()
        dq = deque([start])
        seen[start] = True
        while dq:
            cur = dq.popleft()
            comp.add(cur)
            cx, cy = cur % width, cur // width
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        ni = ny * width + nx
                        if mask[ni] and not seen[ni]:
                            seen[ni] = True
                            dq.append(ni)
        if len(comp) >= min_cells:
            out.append(comp)
    return out


def instance_centroid(comp, width):
    """连通域质心（格坐标浮点）。"""
    if not comp:
        return None
    sx = sy = 0.0
    for idx in comp:
        sx += idx % width
        sy += idx // width
    n = len(comp)
    return (sx / n, sy / n)


def instance_drift(prev_mask, cur_mask, width, height, min_cells=1):
    """实例级抖动：最近实例的中心位移（米 = 格数 × resolution 由调用方乘）。

    **为什么需要它**（`shape_jitter=0` 已失去区分能力的教训）：
    原指标统计的是 OBB 形状，而地图早已主要由 footprint 逐点累积产生 ——
    形状稳定不等于**足迹**稳定。而稳定性 p99 只看 occupied 数量差，
    对小目标极不公平：一个障碍从一个格跳到相邻格，数量差可能是 0，
    但空间位置已完整变化；多个小障碍的进入/离开还会互相抵消数量差。

    因此实例级指标必须直接看**位置**：把前后两帧的占据格各自聚成实例，
    对每个当前实例找最近的上一帧实例，取中心距离。

    返回 dict：`p50` / `p90` / `max`（**格**），`n`（配上的实例数）。
    上一帧无实例时返回 None。
    """
    prev = connected_components_8(prev_mask, width, height, min_cells)
    cur = connected_components_8(cur_mask, width, height, min_cells)
    if not prev or not cur:
        return None
    prev_c = [instance_centroid(c, width) for c in prev]
    cur_c = [instance_centroid(c, width) for c in cur]
    drifts = []
    for (cx, cy) in cur_c:
        best = min(
            (math.hypot(cx - px, cy - py) for (px, py) in prev_c),
            default=None)
        if best is not None:
            drifts.append(best)
    if not drifts:
        return None
    drifts.sort()
    return {
        'p50': _pct(drifts, 0.50),
        'p90': _pct(drifts, 0.90),
        'max': drifts[-1],
        'n': len(drifts),
    }


def occupancy_ratio_coarse(fine_mask, width, height, factor):
    """细层布尔掩码 → 粗层**连续占据率**（0..1，行主序）。

    与 C++ 侧 `agc_perception::occupancyRatio` **同一口径**：
    分母固定为 `factor²`，**不是**"已观测细格数"。
    若分母只数已观测格，一个只看到 1 格、而那格被占的粗格会得到 1.0 ——
    与"整格都被占"无法区分，评价会系统性高估。

    粗层尺寸向下取整（多出的细格不足以构成一个粗格时丢弃）。
    """
    cw = width // factor
    ch = height // factor
    out = [0.0] * (cw * ch)
    total = factor * factor
    for cy in range(ch):
        for cx in range(cw):
            hits = 0
            for dy in range(factor):
                base = (cy * factor + dy) * width + cx * factor
                for dx in range(factor):
                    if fine_mask[base + dx]:
                        hits += 1
            out[cy * cw + cx] = hits / total
    return out, cw, ch


def hausdorff(a_mask, b_mask, width, height, resolution=1.0):
    """双向 Hausdorff 距离（米）：`max(max_a min_b, max_b min_a)`。

    与 `boundary_distance` 的区别：那个返回**分布**（p50/p90/max），这个只返回
    **最坏点**。两者都要报 —— 分布告诉你"整体偏移多少"，Hausdorff 告诉你
    "最坏的那个点偏了多少"（对小障碍，后者往往由单个错位点决定）。

    任一侧为空时返回 None（不返回 0 —— 0 会被读成"完全重合"）。
    """
    if not any(a_mask) or not any(b_mask):
        return None
    d_to_b = distance_field_meters(width, height, resolution, b_mask)
    d_to_a = distance_field_meters(width, height, resolution, a_mask)
    worst_a = max((d_to_b[i] for i in range(width * height)
                   if a_mask[i] and math.isfinite(d_to_b[i])), default=None)
    worst_b = max((d_to_a[i] for i in range(width * height)
                   if b_mask[i] and math.isfinite(d_to_a[i])), default=None)
    if worst_a is None or worst_b is None:
        return None
    return max(worst_a, worst_b)


def obstacle_errors(map_mask, truth_components, width, height, resolution=1.0):
    """逐障碍的**中心误差**与**面积误差**（temp.md 方向五：几何重建指标）。

    `truth_components`：真值侧每个障碍的格索引集合列表。
    对每个真值障碍，找地图侧**质心最近**的连通域作为它的匹配：
      * center_error_m：两者质心距离；
      * area_error_ratio：`(map_area - truth_area) / truth_area`（正=画大了）。

    **为什么按"最近质心"配对而不是按 IoU 配对**：小障碍在 0.5 m 栅格上只有 1–3 格，
    边界一偏 IoU 就掉到 0，按 IoU 配会大量配对失败（表现为"全部漏检"）。
    质心配对对小目标稳健，且它衡量的正是"我把这个障碍放对位置了吗"。

    返回 dict：`center_p50` / `center_p90` / `center_max`（米）、
    `area_ratio_p50` / `area_ratio_p90`（无量纲）、`matched` / `truth_n`。
    """
    map_comps = connected_components_8(map_mask, width, height, min_cells=1)
    if not map_comps or not truth_components:
        return None
    map_cent = [instance_centroid(c, width) for c in map_comps]
    centers = []
    area_ratios = []
    for cells in truth_components:
        tcent = instance_centroid(cells, width)
        if tcent is None:
            continue
        best_i, best_d = -1, float('inf')
        for i, mc in enumerate(map_cent):
            if mc is None:
                continue
            d = math.hypot(tcent[0] - mc[0], tcent[1] - mc[1])
            if d < best_d:
                best_d, best_i = d, i
        if best_i < 0:
            continue
        centers.append(best_d * resolution)
        truth_n = max(1, len(cells))
        area_ratios.append((len(map_comps[best_i]) - truth_n) / truth_n)
    if not centers:
        return None
    centers.sort()
    area_ratios.sort()
    return {
        'center_p50': _pct(centers, 0.50),
        'center_p90': _pct(centers, 0.90),
        'center_max': centers[-1],
        'area_ratio_p50': _pct(area_ratios, 0.50),
        'area_ratio_p90': _pct(area_ratios, 0.90),
        'matched': len(centers),
        'truth_n': len(truth_components),
    }


def collision_and_clearance(risk_values, truth_mask, width, height, resolution=1.0,
                            robot_radius_m=0.6):
    """规划可用性：**是否碰撞** 与 **安全间隙**（temp.md 方向五）。

    * `collision_cells`：风险图判为可通行（0）但**真值上是障碍**的格 —— 车开过去会撞。
      这是最危险的一类错误，必须单独报，不能混进"误覆盖率"。
    * `clearance_min_m`：风险图判为**可通行**的区域，到最近真值障碍的最小距离。
      它回答"我留了多少余量"；负值不可能（距离非负），所以它只会 >= 0。

    **口径**：`risk_values` 是 `/agc/map` 的 `data`（-1/0/1–99/100）。
    `1–99` 是"有代价"，规划器会尽量避开但**允许**通过 —— 因此它们**不计入**
    collision（那是设计上的取舍，不是感知错），只计入 clearance。
    """
    free = [1 if (v == 0) else 0 for v in risk_values]
    collision = sum(1 for i in range(width * height) if free[i] and truth_mask[i])
    dist = distance_field_meters(width, height, resolution, truth_mask)
    # **间隙只在"非碰撞"的自由格上统计**：碰撞格的间隙必然是 0（它自己就是障碍），
    # 把它算进去会让 `clearance_min_m` 恒为 0 —— 那个数字就失去区分力了。
    # 两个量回答两个不同问题："我有没有撞上去"（collision）与
    # "我没撞的地方还留了多少余量"（clearance）。
    finite = [dist[i] for i in range(width * height)
              if free[i] and not truth_mask[i] and math.isfinite(dist[i])]
    return {
        'collision_cells': collision,
        'clearance_min_m': (min(finite) if finite else None),
        'clearance_p05_m': _pct(sorted(finite), 0.05) if finite else None,
        'free_cells': sum(free),
    }


# --------------------------------------------------------------------------- 规划成功率
def astar_grid(risk_values, width, height, start, goal, resolution=1.0,
               allow_unknown=False, max_expansions=200000):
    """在**风险图**上做 8 邻域 A*，返回 (found, path_len_m, expansions)。

    **口径（与 `agc_ground/planning_policy.hpp` 的 `classifyCell` 一致）**：
      * `0`          = 已知自由，可通行；
      * `1..99`      = 有代价，**可通行但代价高**（风险带，规划器会绕）；
      * `>=100`      = 占据，不可通行；
      * `-1`（及其他负值）= 未知。`allow_unknown=False` 时**不可通行**。

    **为什么未知默认不可通行**：这是本仓的既有口径（`planning_policy.hpp` 明写
    "未知不可走"，并解释过 Navfn 的 `allow_unknown` 默认 true 会与之互相抵消）。
    若这里默认放行未知，量出来的成功率会系统性虚高，而且与真实规划器不一致。

    **参照结论**：ego-planner 的 `dyn_a_star.cpp` 里 `search()` 的邻居循环 ——
    `getInflateOccupancy == 1` 即跳过，`!optimistic && getOccupancy == UNKNOWN` 也跳过。
    本实现按同一口径（含"起点/终点先就近脱困"不做，那属于规划器策略，不是评价口径）。

    **它回答什么、不回答什么（必须如实标注）**：
      * 回答：**在这个栅格上，从起点到终点存不存在一条可通行路径**。
      * 不回答：车的动力学能不能跟上、路径平不平滑、要不要倒车。
        所以结果只能叫「栅格可达率」，**不得**表述为"规划成功率"而不加限定。

    代价取 `1 + risk/10`：占据代价越高的格越倾向被绕开，但仍可通行
    （与 Nav2 `computeCost` 的"代价不是禁止"同一语义）。
    """
    import heapq

    if width <= 0 or height <= 0 or len(risk_values) != width * height:
        return False, None, 0
    sx, sy = int(start[0]), int(start[1])
    gx, gy = int(goal[0]), int(goal[1])

    def inside(x, y):
        return 0 <= x < width and 0 <= y < height

    def passable(x, y):
        v = risk_values[y * width + x]
        if v >= 100:
            return False
        if v < 0 and not allow_unknown:
            return False
        return True

    if not inside(sx, sy) or not inside(gx, gy):
        return False, None, 0
    if not passable(sx, sy) or not passable(gx, gy):
        # 端点本身不可通行 ⇒ 直接判失败。**不要**做"就近脱困"：
        # 那是规划器的策略，评价器替它脱困等于替它作弊。
        return False, None, 0

    def step_cost(x, y, nx, ny):
        base = math.hypot(nx - x, ny - y) * resolution
        v = risk_values[ny * width + nx]
        risk = 0.0 if v <= 0 else min(99.0, float(v))
        return base * (1.0 + risk / 10.0)

    def heuristic(x, y):
        # 对角距离（与 ego-planner `getDiagHeu` 的二维情形同式）
        dx = abs(x - gx)
        dy = abs(y - gy)
        diag = min(dx, dy)
        return (diag * math.sqrt(2.0) + (max(dx, dy) - diag)) * resolution

    open_heap = [(heuristic(sx, sy), 0.0, sx, sy)]
    best = {(sx, sy): 0.0}
    parent = {}
    expansions = 0
    while open_heap:
        _, g, x, y = heapq.heappop(open_heap)
        if (x, y) == (gx, gy):
            # 回溯路径长度
            length = 0.0
            cur = (x, y)
            while cur in parent:
                prev = parent[cur]
                length += math.hypot(cur[0] - prev[0], cur[1] - prev[1]) * resolution
                cur = prev
            return True, length, expansions
        if g > best.get((x, y), float('inf')):
            continue
        expansions += 1
        if expansions > max_expansions:
            # 超预算 = **失败**（超时一律算失败，与硬约束"训练与评估成功定义统一"同口径）。
            # 静默返回"成功"会让大图上的搜索成本被隐藏。
            return False, None, expansions
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not inside(nx, ny) or not passable(nx, ny):
                    continue
                ng = g + step_cost(x, y, nx, ny)
                if ng < best.get((nx, ny), float('inf')):
                    best[(nx, ny)] = ng
                    parent[(nx, ny)] = (x, y)
                    heapq.heappush(open_heap, (ng + heuristic(nx, ny), ng, nx, ny))
    return False, None, expansions


def planning_success_rate(frames, width, height, start, goal, resolution=1.0,
                          allow_unknown=False):
    """逐帧跑 `astar_grid`，统计**栅格可达率**。

    **为什么逐帧而不是只跑末帧**：地图在收敛过程中会变（新障碍进入、旧障碍擦除），
    "末帧能走通"不代表"整个过程中都能走通"。逐帧给出的是
    "有多少比例的时刻，这张地图上是通的"。

    返回 dict：
      * `success_rate`：成功帧 / 有效帧；
      * `n_frames` / `n_success`；
      * `path_len_p50_m`：成功帧的路径长度中位数（失败帧不计入）；
      * `expansions_p50`：搜索展开节点数中位数（成本指标）。
    """
    ok = 0
    total = 0
    lengths = []
    expansions = []
    for f in frames:
        data = f.get('data')
        if data is None or len(data) != width * height:
            continue
        total += 1
        found, plen, exp = astar_grid(
            data, width, height, start, goal, resolution, allow_unknown)
        expansions.append(exp)
        if found:
            ok += 1
            if plen is not None:
                lengths.append(plen)
    if total == 0:
        return {'success_rate': None, 'n_frames': 0, 'n_success': 0,
                'path_len_p50_m': None, 'expansions_p50': None}
    lengths.sort()
    expansions.sort()
    return {
        'success_rate': ok / total,
        'n_frames': total,
        'n_success': ok,
        'path_len_p50_m': _pct(lengths, 0.5) if lengths else None,
        'expansions_p50': _pct(expansions, 0.5) if expansions else None,
    }
