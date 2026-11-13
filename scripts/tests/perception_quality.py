"""感知栅格质量指标 —— 把「地图好不好」从主观观感变成可复跑的数字。

**为什么需要它**：2026-11-08 用户反馈"红色方框太大、障碍形状面积一直在变"，
此前的证据是**目视 + 一次实跑日志**。改造（框层退役、足迹点 + log-odds、
free-space carving、屋顶带过滤、相机 1152²）之后，必须能回答"现在到底有多好"，
而且换参数后能立刻复验。

**六项指标**（全部对 `yard.yaml` 的**几何真值**，不是对上一次的地图）：

| 指标 | 定义 | 期望方向 |
|---|---|---|
| `coverage` | 真值占据格中被地图判为占据的比例 | 越高越好 |
| `false_positive` | 地图判为占据但真值是空的格 / 地图占据格 | 越低越好 |
| `iou` | 真值占据 ∩ 地图占据 / 并集 | 越高越好 |
| `area_ratio` | 地图占据格数 / 真值占据格数（面积膨胀比） | → 1.0 |
| `stability` | 稳态相邻两帧的 ``abs(Δoccupied)`` p99 | 越低越好 |
| `shape_jitter` | 每个障碍的 IoU 在相邻两帧间的变化量 p95 | 越低越好 |

**口径（必须与实现一致，否则数字无意义）**：
  * 真值：`yard.yaml` 的 42 个障碍按 `parts` 逐 box 栅格化到 0.5 m 格（与 `map_adapter` 同几何）。
  * 地图：`/agc/map` 的 `data`，`100 = occupied`、`0 = free`、`-1 = unknown`、`1–99 = 量化概率`。
    **`≥100` 才算占据**（与 `planning_policy.hpp` 的 `classifyCell` 同口径）。
  * 只统计**已观测区**（地图非 unknown）内的指标 —— 未观测区的"漏检"不是算法问题，
    是**覆盖问题**，单列 `unobserved_truth`。

**边界（不得外推）**：
  * 真值是**静态几何**，不含动态障碍；地图含感知噪声与遮挡，两者本就不该完全相等。
  * 屋顶带过滤会**有意**剔除侧墙点，所以 `area_ratio < 1` 不必然是缺陷（可能是正确的足迹）。
  * `coverage` 受**遮挡**限制（K5 判据）：UAV 高度不足时楼后地面本就看不清。

用法：
    python3 scripts/tests/perception_quality.py --bag <run_dir>     # 离线读采样
    python3 scripts/tests/perception_quality.py --live --duration 60 # 实时订阅
退出码：0 = 全部判据通过；1 = 有判据未通过。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAPS_DIR = ROOT / 'src' / 'agc_sim' / 'config' / 'maps'

# 纯几何度量（EDT / 集合 IoU / 实例抖动）在**同目录**的 grid_geometry 里，
# 与 C++ 侧 `inflation_field.hpp` 逐式对应。这里显式加入搜索路径，
# 让脚本无论从哪个工作目录调用都能导入（不依赖 PYTHONPATH）。
import sys as _sys
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)
YARD = MAPS_DIR / 'yard.yaml'

# 与 map_adapter / costmap 同一几何口径（只是复算参数，不另立几何来源）。
# **几何与真值必须来自同一张地图**：此前这里写死 yard，拿它量 dense_map 会得到
# 全错的数字（覆盖率 0.221 / 误覆盖 0.935）—— 那不是算法问题，是量错了尺子。
# 现在由 `--map <name>` 切换，默认仍是 yard（既有判据与历史数字口径不变）。
RES = 0.5
OX, OY = -50.0, -50.0
W, H = 200, 200

# 当前使用的地图名（`main()` 里按 `--map` 改写；`_load_truth` 读它）
_ACTIVE_MAP = 'yard'


def _map_path(name: str) -> Path:
    return MAPS_DIR / ('%s.yaml' % name)


def _apply_map_geometry(name: str) -> None:
    """按地图文件切换栅格几何（resolution / size / origin），**不另立来源**。

    与 `agc_perception/config/map.yaml` 及 costmap 同一口径；若地图文件的 work_area
    与这里读出的不一致，宁可**报错**也不静默用错几何（那正是"量错尺子"的来源）。
    """
    global RES, OX, OY, W, H, _ACTIVE_MAP
    import yaml
    p = _map_path(name)
    if not p.exists():
        raise SystemExit('地图不存在：%s（可选：%s）' % (
            p, ', '.join(sorted(x.stem for x in MAPS_DIR.glob('*.yaml')))))
    wa = (yaml.safe_load(p.read_text(encoding='utf-8')) or {}).get('work_area') or {}
    RES = float(wa.get('resolution', RES))
    OX = float(wa.get('origin_x', OX))
    OY = float(wa.get('origin_y', OY))
    W = int(round(float(wa.get('size_x', W * RES)) / RES))
    H = int(round(float(wa.get('size_y', H * RES)) / RES))
    _ACTIVE_MAP = name
    # 距离图缓存按真值算，换地图必须失效（否则沿用上一张图的距离场）
    global _TRUTH_DT_CACHE
    _TRUTH_DT_CACHE = None

def _spawn_layout(name: str):
    """读该图的出生布局（车 / 目标），供**栅格可达率**当起终点。

    **为什么必须读配置而不是写死坐标**：写死会让"换图后还在用旧图的起终点"，
    量出来的可达率与真实任务无关。`spawn_layout.yaml` 是唯一来源（ADR-0007/0012），
    这里只读 `per_map.<map>` 的覆盖值，缺省回落到顶层。
    """
    import yaml
    p = ROOT / 'src' / 'agc_task' / 'config' / 'spawn_layout.yaml'
    if not p.exists():
        return None
    d = (yaml.safe_load(p.read_text(encoding='utf-8')) or {}).get('spawn_layout') or {}
    per = (d.get('per_map') or {}).get(name) or {}

    def pick(key, field, default):
        return float(((per.get(key) or {}).get(field,
                       (d.get(key) or {}).get(field, default))))

    car_x = pick('car', 'x', 0.0)
    car_y = pick('car', 'y', 0.0)
    tgt_x = pick('target', 'x', 0.0)
    tgt_y = pick('target', 'y', 0.0)
    # 任务目标 = 目标位置 + goal_offset_m（与 scene_spawn 的派生口径一致）
    off = d.get('goal_offset_m') or {}
    goal_x = tgt_x + float(off.get('dx', 0.0))
    goal_y = tgt_y + float(off.get('dy', 0.0))
    return {
        'start_world': (car_x, car_y),
        'goal_world': (goal_x, goal_y),
    }


def _world_to_cell(x, y):
    return (int(math.floor((x - OX) / RES)), int(math.floor((y - OY) / RES)))


# 判据（预登记，不得事后调整；改判据须新任务 + 新预登记）
GATES = {
    'coverage_min': 0.55,        # 已观测区内至少覆盖一半真值
    'false_positive_max': 0.35,  # 误覆盖不超过 35%
    'iou_min': 0.45,
    'area_ratio_max': 1.60,      # 面积膨胀不超过 1.6×（改造前框层实测 1.65×）
    'shape_jitter_p95_max': 0.25,
    # ---- 稳定性主判据（ADR-0042，**先预登记后测量**）----
    #
    # temp.md：只统计 occupied 数量差对小目标不公平 ——
    # "1 个障碍从一个格跳到相邻格，数量差可能为 0，但空间位置已经发生了完整变化"。
    # 故主判据换成三条空间量，**全部满足**才算通过。
    #
    # 门限是**物理推导**，不是看结果凑的（推导见 ADR-0042 的预登记节）：
    'set_iou_p50_min': 0.85,            # 约 8% 的格在换 = 边界量化抖动的量级上限
    'boundary_jitter_p90_max_m': 0.50,  # 一个证据层格宽；超过 = 障碍被画到别的格上
    # **主判据用 p50**（ADR-0043）：p90 被少数大实例的边缘翻转支配 ——
    # 一个 2300 格的实例边缘翻 80 格，质心就动 0.23 m（≈ 旧门限本身），
    # 而边缘翻转是深度噪声的**正常现象**（单帧 |Δocc| ≈ 130 格）。
    # p50 = 0.15 m = 0.6 个证据层格宽：超过它说明**超过一半**的实例在帧间
    # 跳了多半格，那才是"实例层没起作用"。
    'instance_drift_p50_max_m': 0.15,
    # **诊断**（不进 verdict）：最坏那批实例抖了多少，用于定位问题。
    'instance_drift_p90_max_m': 0.25,
    # **旧判据保留为诊断**（不进 verdict）：它与历史结论可比，删掉就无法回答
    # "换尺子之后差多少"。门限不变。
    'stability_p99_max': 50,
}


# ----------------------------------------------------------------------------- 真值
def _load_truth():
    """按**当前地图**的 parts 逐 box 栅格化出真值占据格（与 map_adapter 同几何）。

    `_ACTIVE_MAP` 由 `--map` 决定（默认 yard）。dense_map 无 `parts`（单图元），
    同一套代码按 `is_self` 分支处理，不需要第二条栅格化路径。
    """
    import yaml
    d = yaml.safe_load(_map_path(_ACTIVE_MAP).read_text(encoding='utf-8'))
    truth = [[0] * W for _ in range(H)]
    per_obstacle = {}   # id → set((i,j))

    def rot(px, py, ang):
        c, s = math.cos(ang), math.sin(ang)
        return px * c - py * s, px * s + py * c

    for o in d['obstacles']:
        oid = o['id']
        base_ang = float(o.get('yaw', 0.0))
        cells = set()
        parts = o.get('parts') or [o]
        for p in parts:
            # **2026-11-09 修复（实测 bug）**：没有 `parts` 的障碍，`o` 本身就是那个
            # part，此时 `o['x']/o['y']` 是**世界坐标**，不能再当作局部偏移叠加一次。
            # 改造前对 `slab_s`（world -10.5,-14.5）算出 bbox x[-0.8,4.8] —— 整体
            # 平移了约 10 m，真值因此缺失两块真实障碍，覆盖率/误覆盖全被污染。
            is_self = p is o
            lx, ly = (0.0, 0.0) if is_self else (float(p.get('x', 0.0)), float(p.get('y', 0.0)))
            wx0, wy0 = rot(lx, ly, base_ang)
            cx, cy = o['x'] + wx0, o['y'] + wy0
            # 自身即 part 时，朝向就是 `yaw`（不能把 base_ang 再加一次）
            pang = base_ang if is_self else base_ang + float(p.get('yaw', 0.0))
            sz = p.get('size') or [0, 0, 0]
            shape = (p.get('shape') or 'box').lower()
            if shape in ('cylinder', 'sphere'):
                rx = ry = sz[0]
            else:
                rx, ry = sz[0] / 2.0, sz[1] / 2.0
            # 外接半径决定扫描范围（旋转后仍包围）
            rad = math.hypot(rx, ry)
            i0 = max(0, int((cx - rad - OX) // RES))
            i1 = min(W - 1, int((cx + rad - OX) // RES) + 1)
            j0 = max(0, int((cy - rad - OY) // RES))
            j1 = min(H - 1, int((cy + rad - OY) // RES) + 1)
            ca, sa = math.cos(-pang), math.sin(-pang)
            for j in range(j0, j1 + 1):
                py = OY + (j + 0.5) * RES
                for i in range(i0, i1 + 1):
                    px = OX + (i + 0.5) * RES
                    dx, dy = px - cx, py - cy
                    u, v = dx * ca - dy * sa, dx * sa + dy * ca
                    if shape in ('cylinder', 'sphere'):
                        hit = u * u + v * v <= rx * rx
                    else:
                        hit = abs(u) <= rx and abs(v) <= ry
                    if hit:
                        cells.add((i, j))
                        truth[j][i] = 1
        if cells:
            per_obstacle[oid] = cells
    return truth, per_obstacle


def _load_truth_at(resolution):
    """按**任意分辨率**把同一份地图几何栅格化成真值（temp.md 方向五①）。

    **为什么必须能换分辨率**：temp.md 要求"在高分辨率层与高分辨率真值比较"。
    改造前真值固定 0.5 m，于是评价只能落在规划层上 —— 那正是"拿膨胀图评价感知"
    的口径错误。这里把**同一份几何真值**按证据层分辨率重新栅格化，
    两边分辨率一致，几何指标才有意义。

    返回 `(truth, per_obstacle, w, h)`；几何口径与 `map_adapter` 同源
    （同一 `work_area` 的 origin / size，只换 resolution）。
    """
    import yaml
    d = yaml.safe_load(_map_path(_ACTIVE_MAP).read_text(encoding='utf-8'))
    wa = d.get('work_area') or {}
    size_x = float(wa.get('size_x', W * RES))
    size_y = float(wa.get('size_y', H * RES))
    ox = float(wa.get('origin_x', OX))
    oy = float(wa.get('origin_y', OY))
    w = int(round(size_x / resolution))
    h = int(round(size_y / resolution))
    truth = [[0] * w for _ in range(h)]
    per_obstacle = {}

    def rot(px, py, ang):
        c, s = math.cos(ang), math.sin(ang)
        return px * c - py * s, px * s + py * c

    for o in d['obstacles']:
        oid = o['id']
        base_ang = float(o.get('yaw', 0.0))
        cells = set()
        parts = o.get('parts') or [o]
        for p in parts:
            is_self = p is o
            lx, ly = (0.0, 0.0) if is_self else (float(p.get('x', 0.0)), float(p.get('y', 0.0)))
            wx0, wy0 = rot(lx, ly, base_ang)
            cx, cy = o['x'] + wx0, o['y'] + wy0
            pang = base_ang if is_self else base_ang + float(p.get('yaw', 0.0))
            sz = p.get('size') or [0, 0, 0]
            shape = (p.get('shape') or 'box').lower()
            if shape in ('cylinder', 'sphere'):
                rx = ry = sz[0]
            else:
                rx, ry = sz[0] / 2.0, sz[1] / 2.0
            rad = math.hypot(rx, ry)
            i0 = max(0, int((cx - rad - ox) // resolution))
            i1 = min(w - 1, int((cx + rad - ox) // resolution) + 1)
            j0 = max(0, int((cy - rad - oy) // resolution))
            j1 = min(h - 1, int((cy + rad - oy) // resolution) + 1)
            ca, sa = math.cos(-pang), math.sin(-pang)
            for j in range(j0, j1 + 1):
                py = oy + (j + 0.5) * resolution
                for i in range(i0, i1 + 1):
                    px = ox + (i + 0.5) * resolution
                    dx, dy = px - cx, py - cy
                    u, v = dx * ca - dy * sa, dx * sa + dy * ca
                    if shape in ('cylinder', 'sphere'):
                        hit = u * u + v * v <= rx * rx
                    else:
                        hit = abs(u) <= rx and abs(v) <= ry
                    if hit:
                        cells.add(j * w + i)
                        truth[j][i] = 1
        if cells:
            per_obstacle[oid] = cells
    return truth, per_obstacle, w, h


# ----------------------------------------------------------------------------- 地图
def _classify(v: int) -> str:
    """与 `agc_ground/planning_policy.hpp` 的 `classifyCell` 同口径。"""
    if v == 0:
        return 'free'
    if v < 0:
        return 'unknown'
    if v >= 100:
        return 'occupied'
    return 'unknown'    # 1–99 = 有证据但未跨门限 → 未知


_TRUTH_DT_CACHE = None

def _truth_distance(truth):
    """每个格到最近真值障碍的格距（欧氏近似，BFS 曼哈顿）。零依赖实现。"""
    global _TRUTH_DT_CACHE
    if _TRUTH_DT_CACHE is not None:
        return _TRUTH_DT_CACHE
    from collections import deque
    dist = [[-1] * W for _ in range(H)]
    q = deque()
    for j in range(H):
        for i in range(W):
            if truth[j][i]:
                dist[j][i] = 0
                q.append((i, j))
    while q:
        i, j = q.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if 0 <= ni < W and 0 <= nj < H and dist[nj][ni] < 0:
                dist[nj][ni] = dist[j][i] + 1
                q.append((ni, nj))
    _TRUTH_DT_CACHE = dist
    return dist


def _frame_metrics(grid: dict, truth, per_obstacle, reachable=None):
    """对一帧算 5 项空间指标（stability/shape_jitter 需要两帧，另算）。

    **`reachable` 是"相机可识别范围"掩码**（用户 2026-11-09 裁定）：
    "覆盖率注意是相机可识别范围内的，照不到肯定不能要求"。
    不在该范围内的真值格**不计入分母**（既不算覆盖失败，也不算误覆盖）。
    """
    data = grid['data']
    if len(data) != W * H:
        # **报清楚是哪条口径错了**：规划层判据只能在 0.5 m 帧上算。
        # 传错（例如把 0.25 m 的证据层帧塞进来）时报"尺寸不符"看不出原因，
        # 而真正的修法可能是"该用 evidence_frames 参数"。
        raise ValueError(
            '规划层判据只接受 %dx%d 的帧（%.2f m），收到 %d 格（%.2f m）。'
            '证据层帧请传给 evidence_frames，不要传给 frames。'
            % (W, H, RES, len(data), grid.get('res') or -1))

    occ_map = 0
    tp = fp = fn = 0
    fp_beyond_q = 0
    unobserved_truth = 0
    out_of_range_truth = 0
    per_obs_iou = {}
    # **FP 分档诊断（ADR-0039，不参与判定）**：把误覆盖按"距最近真值障碍的格距"分档。
    # 三档对应三种**不同**的根因，混在一起看只会得出"误覆盖高"这一个无用结论：
    #   0–1 格：栅格量化 / 边界误差（改判据或加膨胀就能消，不是地图画错）；
    #   1–3 格：投影误差 / 时间错位 / 形态外扩（真问题，靠补偿与空间支持修）；
    #   >3 格：明显错误投影 / 残影 / 错误 carving（真问题，靠生命周期与遮挡置信度修）。
    fp_bins = {'0-1': 0, '1-3': 0, '>3': 0}
    # 另外记录"到真值距离"的分位数原料（格），供中位数/p90 统计
    fp_dist_cells = []
    # **覆盖率分母（2026-11-09 用户观察修正）**：只统计"该障碍落在画幅并集内"的格。
    # 用户实测发现：`hall_north` 距相机 43 m，而画幅半径仅 30.6 m —— **整个障碍都不在
    # 视野内**，标注率必然 0.00。把它的全部格计入分母等于要求"看到看不见的东西"。
    # 同理 `hall_northeast` / `warehouse_south` / `workshop_w` / `admin_block` /
    # `depot_east` / `office_w` 末帧标注率全为 0.00 —— 它们从未进入画幅。
    in_range_truth = 0
    for oid, cells in per_obstacle.items():
        inter = union = 0
        for (i, j) in cells:
            if reachable is not None and not reachable[j][i]:
                out_of_range_truth += 1
                continue
            in_range_truth += 1
            v = data[j * W + i]
            m = _classify(v)
            if m == 'unknown':
                unobserved_truth += 1
                continue
            if m == 'occupied':
                inter += 1
                union += 1
            else:
                union += 1
        per_obs_iou[oid] = (inter / union) if union else None

    # 预计算真值距离图（量化效应判定用）：每个格到最近真值障碍的**格距**
    # 需要 scipy；为保持零依赖，这里用缓存 + 可选导入。
    truth_dt = _truth_distance(truth)

    for j in range(H):
        for i in range(W):
            if reachable is not None and not reachable[j][i]:
                continue
            v = data[j * W + i]
            t = truth[j][i]
            m = _classify(v)
            if m == 'occupied':
                occ_map += 1
                if t:
                    tp += 1
                else:
                    fp += 1
                    # 量化下界：离真值 >1 格才是算法该负责的误覆盖
                    if truth_dt is not None:
                        d = truth_dt[j][i]
                        if d > 1.0:
                            fp_beyond_q += 1
                        fp_dist_cells.append(d)
                        if d <= 1.0:
                            fp_bins['0-1'] += 1
                        elif d <= 3.0:
                            fp_bins['1-3'] += 1
                        else:
                            fp_bins['>3'] += 1
            elif m == 'free' and t:
                fn += 1

    observed_truth = tp + fn
    coverage = (tp / observed_truth) if observed_truth else None
    fp_rate = (fp / occ_map) if occ_map else None
    union = tp + fp + fn
    iou = (tp / union) if union else None
    truth_n = sum(sum(r) for r in truth)
    area_ratio = (occ_map / truth_n) if truth_n else None
    return {
        'occupied_cells': occ_map,
        'tp': tp, 'fp': fp, 'fn': fn, 'fp_beyond_q': fp_beyond_q,
        # ---- FP 分档诊断（不参与判定，ADR-0039）----
        'fp_bins': fp_bins,
        'fp_dist_p50': _pct(fp_dist_cells, 0.50),
        'fp_dist_p90': _pct(fp_dist_cells, 0.90),
        'truth_cells': truth_n,
        'unobserved_truth': unobserved_truth,
        'out_of_range_truth': out_of_range_truth,
        'in_range_truth': in_range_truth,
        'coverage': coverage,
        'false_positive': fp_rate,
        'iou': iou,
        'area_ratio': area_ratio,
        'per_obstacle_iou': per_obs_iou,
    }


def _pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    k = min(int(q * (len(s) - 1)), len(s) - 1)
    return s[k]


def _occupied_set(frame):
    """一帧的 occupied 格索引集合（**只认 100**，与 `_classify` 同口径）。"""
    return {i for i, v in enumerate(frame['data']) if v >= 100}


def _stability(frames, per_obstacle, truth=None, raw_frames=None):
    """稳态稳定性 + 形状抖动 + **集合级诊断**。跳过冷启动（前 2 帧：空→首次建图不是抖动）。

    **2026-11-09 用户裁定的口径修正（诊断，不改判据）**：
    原有指标只比较 `abs(occupied 数量差)`。它无法区分
      * "同一批格在门限附近来回翻"（空间抖动，真正要修的），
      * "障碍整体进/出画幅"（合法增长/收缩），
      * "500 格离开 + 360 格进入但数量只差 140"（大量互换）。
    因此额外统计集合级量，**只做诊断、不参与判定**（判据仍是 `delta_p99`）：
      * `exit_p99` / `enter_p99`：离开 / 进入 occupied 的格数，
      * `set_iou_p50`：两帧 occupied 集合的 IoU，
      * `churn_ratio_p50`：`(exit+enter)/(2·|并集|)` —— 高而 `|Δ|` 低 ⇒ 大量互换，
      * `exit_dist_p90`：离开格到真值边界的距离（格）—— 高 ⇒ 抖动在"凭空"区域，
      * `edge_frac_p50`：变化格落在**地图/画幅外缘**的比例。
    """
    occ = [f['occupied_cells'] for f in frames]
    d = [abs(b - a) for a, b in zip(occ, occ[1:])]
    d_steady = d[2:] if len(d) > 2 else d
    jitter = []
    ious = [f['per_obstacle_iou'] for f in frames]
    for a, b in zip(ious, ious[1:]):
        for oid in per_obstacle:
            x, y = a.get(oid), b.get(oid)
            if x is None or y is None:
                continue
            jitter.append(abs(x - y))

    # ---- 集合级诊断（不改判据）----
    # 注意：`frames` 是**每帧指标**（没有原始 `data`），集合级统计必须用原始栅格帧。
    # 两者按同一稳态窗口对齐（`raw_frames` 传进来时已由 evaluate() 切好）。
    sets = [_occupied_set(f) for f in (raw_frames if raw_frames is not None else [])]
    exit_n, enter_n, set_iou, churn = [], [], [], []
    exit_dists, edge_fracs = [], []
    truth_dt = _truth_distance(truth) if truth is not None else None
    W_edges, H_edges = W, H
    for prev, cur in zip(sets, sets[1:]):
        gone = prev - cur
        came = cur - prev
        exit_n.append(len(gone))
        enter_n.append(len(came))
        union = prev | cur
        set_iou.append((len(prev & cur) / len(union)) if union else None)
        churn.append(((len(gone) + len(came)) / (2.0 * len(union))) if union else None)
        # 变化格到真值边界的距离：区分"贴着真实障碍边缘翻"与"凭空翻"
        if truth_dt is not None and gone:
            dists = []
            for idx in gone:
                j, i = divmod(idx, W_edges)
                dists.append(truth_dt[j][i])
            exit_dists.append(_pct(dists, 0.90))
        # 变化格落在地图外缘 3 格以内的比例（那里是画幅边界/量化噪声的聚集地）
        changed = gone | came
        if changed:
            near = 0
            for idx in changed:
                j, i = divmod(idx, W_edges)
                if i < 3 or j < 3 or i >= W_edges - 3 or j >= H_edges - 3:
                    near += 1
            edge_fracs.append(near / len(changed))

    def _tail(vals, q):
        v = [x for x in vals if x is not None]
        return _pct(v, q) if v else None

    return {
        'delta_p50': _pct(d_steady, 0.50),
        'delta_p90': _pct(d_steady, 0.90),
        'delta_p99': _pct(d_steady, 0.99),
        'delta_max': max(d_steady) if d_steady else None,
        'shape_jitter_p95': _pct(jitter, 0.95),
        'n_pairs': len(d_steady),
        # ---- 以下为诊断量（不参与 verdict）----
        'exit_p99': _tail(exit_n, 0.99),
        'enter_p99': _tail(enter_n, 0.99),
        'set_iou_p50': _tail(set_iou, 0.50),
        'churn_ratio_p50': _tail(churn, 0.50),
        'exit_dist_p90': _tail(exit_dists, 0.50),
        'edge_frac_p50': _tail(edge_fracs, 0.50),
    }


# ----------------------------------------------------------------------------- 分层指标
# **为什么必须分层**（ADR-0040）：`/agc/map` 现在是**规划派生层** —— 它由证据层经
# max-pool 合并而来，小障碍会被放大到整个 0.5 m 格。拿它去和几何真值算 precision /
# IoU，等于把"为规划安全而做的保守化"记成"感知画错了"。那正是改造前误覆盖率
# 0.668 里相当大的一部分。
#
# 因此本模块把三套口径**分开报**，谁也不冒充谁：
#   ① 几何重建（证据层）：precision / recall / IoU / 边界距离 / 实例中心误差；
#   ② 规划可用性（规划层）：是否漏掉危险障碍、误阻塞率、安全间隙；
#   ③ 稳定性：集合 IoU + 实例中心抖动（不再只看 occupied 数量差）。

# 证据层分辨率（与 `perception.yaml` 的 `perception_resolution` 同值）。
# 离线复算时地图只有规划层（0.5 m），所以"几何重建"这一套在**规划层栅格**上
# 以"格"为单位计算，但**判据与阈值按证据层尺度给出**（见 EVIDENCE_RES 的用法）：
# 边界距离用米表达，实例中心误差也用米 —— 这样换分辨率时判据不变。
EVIDENCE_RES = 0.25


def _obstacle_components(per_obstacle, width=None):
    """真值侧逐障碍的格索引集合（供中心/面积误差配对用）。

    **必须转成扁平索引**：`_load_truth` 的 `per_obstacle` 存的是 `(i, j)` 元组，
    而地图侧 `connected_components_8` 产出的是扁平索引 `j*W+i`。
    两套编码混用会让 `instance_centroid` 对着元组做取模（实测 TypeError）。
    这里统一成**扁平索引**，与地图侧同一编码。
    """
    # **两种编码都要能吃**：`_load_truth`（0.5 m）存 `(i,j)` 元组，
    # `_load_truth_at`（任意分辨率）直接存扁平索引 `j*w+i`。
    # 统一成扁平索引时**必须用该真值自己的宽度**，不能用全局 `W` ——
    # 证据层是 400 宽、规划层是 200 宽，用错宽度会让行偏移整体错位，
    # 而且症状是"实例配对全乱"，极难归因。
    w = width or W
    out = []
    for cells in per_obstacle.values():
        if not cells:
            continue
        first = next(iter(cells))
        if isinstance(first, tuple):
            out.append(set(j * w + i for (i, j) in cells))
        else:
            out.append(set(cells))
    return out


def _evidence_geometry_metrics(frame, truth, reachable=None, resolution=RES,
                               truth_components=None):
    """几何重建指标：precision / recall / IoU + 边界距离（米）。

    与 `_frame_metrics` 的差别：这里**不把 FP 归因于"感知错"**，只报几何量。
    边界距离用双向距离变换，抓"整体偏移"而不只是"多画了几格"。
    """
    from grid_geometry import boundary_distance

    # **几何从真值自身取，不从全局常量取**（temp.md 方向五①）：
    # 证据层是 0.25 m / 400×400，规划层是 0.5 m / 200×200。写死 `W/H` 会让
    # 证据层的帧在尺寸检查处被静默丢掉（返回 None），几何指标变成"不适用"——
    # 那看起来像"没有数据"，实际是"读错了尺寸"。
    h = len(truth)
    w = len(truth[0]) if h else 0
    data = frame['data']
    if w <= 0 or h <= 0 or len(data) != w * h:
        return None
    occ = [1 if v >= 100 else 0 for v in data]
    tru = [1 if truth[j][i] else 0 for j in range(h) for i in range(w)]
    if reachable is not None:
        for j in range(h):
            for i in range(w):
                if not reachable[j][i]:
                    occ[j * w + i] = 0
                    tru[j * w + i] = 0
    tp = fp = fn = 0
    for k in range(w * h):
        if occ[k] and tru[k]:
            tp += 1
        elif occ[k]:
            fp += 1
        elif tru[k]:
            fn += 1
    precision = (tp / (tp + fp)) if (tp + fp) else None
    recall = (tp / (tp + fn)) if (tp + fn) else None
    union = tp + fp + fn
    iou = (tp / union) if union else None
    # 边界距离：地图边界 → 真值边界，与 真值边界 → 地图边界
    m2t = boundary_distance(occ, tru, w, h, resolution)
    t2m = boundary_distance(tru, occ, w, h, resolution)
    from grid_geometry import hausdorff, obstacle_errors
    hd = hausdorff(occ, tru, w, h, resolution)
    oe = (obstacle_errors(occ, truth_components, w, h, resolution)
          if truth_components else None)
    return {
        'precision': precision,
        'recall': recall,
        'iou': iou,
        'boundary_map_to_truth_p90': (m2t or {}).get('p90'),
        'boundary_truth_to_map_p90': (t2m or {}).get('p90'),
        'boundary_map_to_truth_max': (m2t or {}).get('max'),
        # ---- temp.md 方向五：几何重建的另外三项 ----
        'hausdorff_m': hd,
        'center_error_p50_m': (oe or {}).get('center_p50'),
        'center_error_p90_m': (oe or {}).get('center_p90'),
        'area_error_ratio_p50': (oe or {}).get('area_ratio_p50'),
        'area_error_ratio_p90': (oe or {}).get('area_ratio_p90'),
        'obstacles_matched': (oe or {}).get('matched'),
        'obstacles_truth': (oe or {}).get('truth_n'),
    }


def _planning_usability_metrics(frame, truth, reachable=None, robot_radius_m=0.6):
    """规划可用性指标：**漏掉危险障碍** 与 **误阻塞**。

    两个量回答的是完全不同的风险，不能合成一个数：
      * `missed_danger`：真值障碍格，在规划层被标成**可通行**（0）—— 会撞。
        这是安全风险，优先级最高。
      * `over_blocked`：规划层占据，但**离真值障碍超过车半径** —— 明明能过却被挡。
        这是效率损失，不是安全风险。
    """
    from grid_geometry import distance_field_meters

    data = frame['data']
    if len(data) != W * H:
        return None
    tru = [1 if truth[j][i] else 0 for j in range(H) for i in range(W)]
    if reachable is not None:
        for j in range(H):
            for i in range(W):
                if not reachable[j][i]:
                    tru[j * W + i] = 0
    dist_to_truth = distance_field_meters(W, H, RES, tru)
    missed = 0
    truth_n = 0
    over = 0
    occ_n = 0
    for k in range(W * H):
        v = data[k]
        known_free = (v == 0)
        occupied = (v >= 100)
        if tru[k]:
            truth_n += 1
            if known_free:
                missed += 1
        if occupied:
            occ_n += 1
            d = dist_to_truth[k]
            if d > robot_radius_m:
                over += 1
    from grid_geometry import collision_and_clearance
    cc = collision_and_clearance(data, tru, W, H, RES, robot_radius_m)
    return {
        'missed_danger_cells': missed,
        'missed_danger_ratio': (missed / truth_n) if truth_n else None,
        'over_blocked_cells': over,
        'over_blocked_ratio': (over / occ_n) if occ_n else None,
        # ---- temp.md 方向五：规划可用性的另外三项 ----
        'collision_cells': cc['collision_cells'],
        'clearance_min_m': cc['clearance_min_m'],
        'clearance_p05_m': cc['clearance_p05_m'],
    }


def _instance_drift_by_id(meta_frames, width=None, height=None, resolution=None):
    """实例中心位移，按**实例 id** 跨帧配对（ADR-0042 主判据的口径）。

    **与聚类配对的区别**：id 由实例层维护、跨帧不变；聚类是每帧重算，
    大障碍被切碎时会产生"新块配到别的障碍上"的伪影（实测 1–5 m）。

    **只在两帧都出现的 id 上统计**（新出现 / 消失的实例不算漂移 ——
    那是生命周期事件，不是位置抖动）。

    返回逐 (id, 相邻两帧) 的位移（米）。
    """
    res = resolution or RES
    w = width or W
    h = height or H
    cents = [_instance_centers_by_id(f, w, h) for f in meta_frames]
    out = []
    for prev, cur in zip(cents, cents[1:]):
        for sid, (cx, cy, _n) in cur.items():
            p = prev.get(sid)
            if p is None:
                continue      # 新出现的实例：生命周期事件，不算漂移
            out.append(math.hypot(cx - p[0], cy - p[1]) * res)
    return out


def _instance_centers_by_id(frame, width=None, height=None):
    """按**实例 id** 分组求质心（格坐标）—— 实例身份来自实例层，不是重新聚类。

    **为什么不能用"每帧重新聚类 + 最近配对"**（本轮实测踩过）：
    连通域数量在帧间会变（实测 24 → 28）——一个大障碍的边缘被深度噪声切掉一块，
    就成了两个连通域。此时"最近的上一帧连通域"会把新出现的小块配到**别的**障碍上，
    得出的位移是 1–5 m 的**配对伪影**，而真实障碍根本没动。

    实例层给的是**跨帧稳定的 id**（`instance_cell_owner_` 写入 `source_instance_id`），
    同一个 id 在相邻帧就是同一个障碍 —— 那才是 temp.md 说的"实例中心位移"。

    返回 `{id: (cx, cy, n_cells)}`；无 `source_instance_id` 时返回空 dict。
    """
    ids = frame.get('source_instance_id')
    if not ids:
        return {}
    w = width or W
    h = height or H
    acc = {}
    for idx, sid in enumerate(ids):
        if sid is None or sid < 0:
            continue
        j, i = divmod(idx, w)
        s = acc.get(sid)
        if s is None:
            acc[sid] = [float(i), float(j), 1]
        else:
            s[0] += i
            s[1] += j
            s[2] += 1
    return {sid: (v[0] / v[2], v[1] / v[2], v[2]) for sid, v in acc.items()}


def _boundary_jitter_by_id(meta_frames, width=None, height=None, resolution=None):
    """边界抖动，按**实例 id** 配对后算 —— temp.md 要的"几何 footprint 的边界位移"。

    **为什么不能用连通域配对**（本轮实测两次踩过）：
      1. 全局 Hausdorff（第一版）→ 两个不同障碍相距 80 m 时报 80 m；
      2. 连通域最近配对 + 质心门限（第二版）→ 大障碍被切掉一侧时，
         质心仍很近（<2 m）但 Hausdorff 抓到"被切掉那角"的距离 → 22 格 = 5.5 m。
         实测分布：p50 = 0.25 m（1 格，正常量化）、p90 = 1.12 m、max = 5.5 m。

    两者都不是"边界在抖"，而是**配对方式与切碎**造成的伪影。
    实例 id 跨帧稳定，同一个 id 的足迹在相邻帧就是同一个障碍的边界 —— 那才是位移。

    实现：对每个相邻帧对上**两帧都出现**的实例 id，取该 id 足迹格的
    **中位边界位移**（`boundary_distance` 的 p50，双向取大者）。

    **为什么是 p50 而不是 Hausdorff**（本轮实测第三次修正）：
    Hausdorff 取**最远的一个点**，于是"大障碍被切掉一侧"会让它报 5.96 m，
    而同一障碍其余 99% 的边界只动了 0.25 m（一格）。temp.md 要的是
    "几何 footprint 的**边界位移**"，那是一个**典型量**，不是最坏点。
    最坏点会永远被少量切碎支配，指标失去区分力 —— 与 `shape_jitter` 失效同一教训。
    最坏值仍保留为诊断（`boundary_jitter_max_m`）。
    """
    from grid_geometry import boundary_distance
    res = resolution or RES
    w = width or W
    h = height or H
    out = []
    for prev, cur in zip(meta_frames, meta_frames[1:]):
        pa = _cells_by_instance(prev, w, h)
        ca = _cells_by_instance(cur, w, h)
        for sid, cells_b in ca.items():
            cells_a = pa.get(sid)
            if not cells_a:
                continue      # 新出现 / 上一帧没有：生命周期事件，不算抖动
            ma = [False] * (w * h)
            for idx in cells_a:
                ma[idx] = True
            mb = [False] * (w * h)
            for idx in cells_b:
                mb[idx] = True
            # 双向各算一次，取较大的 p50（与 `boundary_distance` 的双向纪律一致）
            ab = boundary_distance(ma, mb, w, h, res)
            ba = boundary_distance(mb, ma, w, h, res)
            cand = [x for x in ((ab or {}).get('p50'), (ba or {}).get('p50'))
                    if x is not None]
            if cand:
                out.append(max(cand))
    return out


def _cells_by_instance(frame, width, height):
    """`{id: [格索引...]}` —— 逐格 `source_instance_id` 反查。"""
    ids = frame.get('source_instance_id')
    if not ids:
        return {}
    out = {}
    for idx, sid in enumerate(ids):
        if sid is None or sid < 0:
            continue
        out.setdefault(sid, []).append(idx)
    return out


def _boundary_jitter_known_region(frames, width=None, height=None, resolution=None,
                                   match_gate_m=2.0):
    """边界抖动，**逐障碍配对**后取位移（ADR-0042 主判据）。

    **为什么不能用全局 Hausdorff**（本轮实测踩过）：
    第一版用"两帧 occupied 集合的双向 Hausdorff"，构造用例显示 ——
    障碍从 A 移到 B（相距 160 格）时它报 **80 m**。但那不是抖动，
    是"两个障碍都在，它们之间很远"。Hausdorff 量的是**集合**的最远点距，
    而 temp.md 要的是"**同一个**障碍的几何 footprint 边界位移"。

    第二版（修正）：
      1. 把两帧 occupied 各自聚成连通域（每个域 ≈ 一个障碍）；
      2. 按质心最近配对（与 `instance_drift` 同一配对纪律）；
      3. 对**配对上的那一对**算双向 Hausdorff —— 此时两个集合是同一个障碍，
         最远点距才有"边界位移"的含义；
      4. 只在**两帧都已知**的区域内算（unknown 是"没看过"，不是"边界移动"）。

    **配对必须设距离门限**：只按"最近"配对会把"A 处障碍消失、B 处出现"这对
    **不同**障碍配成一对，Hausdorff 于是报出它们之间的距离（实测 80 m）。
    那不是抖动。门限取 `match_gate_m`（米，默认 2.0 = 4 个证据层格）：
    超过它的两个连通域不认为是同一个障碍，**不参与统计**。

    返回逐对抖动（米）列表。
    """
    from grid_geometry import connected_components_8, hausdorff, instance_centroid
    w = width or W
    h = height or H
    res = resolution or RES
    out = []
    for a, b in zip(frames, frames[1:]):
        da, db = a['data'], b['data']
        if len(da) != w * h or len(db) != w * h:
            continue
        # 只在两帧都已知的格上比较（unknown 并集剔掉）
        ma = [(da[k] >= 100) and (da[k] >= 0 and db[k] >= 0) for k in range(w * h)]
        mb = [(db[k] >= 100) and (da[k] >= 0 and db[k] >= 0) for k in range(w * h)]
        ca = connected_components_8(ma, w, h, min_cells=1)
        cb = connected_components_8(mb, w, h, min_cells=1)
        if not ca or not cb:
            continue
        cen_a = [instance_centroid(c, w) for c in ca]
        cen_b = [instance_centroid(c, w) for c in cb]
        # 逐障碍配对：每个当前连通域找质心最近的上一帧连通域
        for comp_b, (bx, by) in zip(cb, cen_b):
            if bx is None:
                continue
            best, best_d = None, float('inf')
            for idx, (ax, ay) in enumerate(cen_a):
                if ax is None:
                    continue
                d = math.hypot(ax - bx, ay - by) * res
                if d < best_d:
                    best_d, best = d, idx
            if best is None:
                continue
            if best_d > match_gate_m:
                # 质心相距超过门限 ⇒ **不是同一个障碍**（一个消失、一个出现）。
                # 把它算成"边界位移"会把"合法的新观测"记成抖动。
                continue
            # 配上的这一对是**同一个障碍**，此时 Hausdorff 才是边界位移
            m_a = [False] * (w * h)
            for idx in ca[best]:
                m_a[idx] = True
            m_b = [False] * (w * h)
            for idx in comp_b:
                m_b[idx] = True
            hd = hausdorff(m_a, m_b, w, h, res)
            if hd is not None:
                out.append(hd)
    return out


def _boundary_and_area_stability(frames):
    """temp.md 方向五要求的另外两项稳定性：
      * **边界 Hausdorff 抖动**：相邻两帧 occupied 集合的双向 Hausdorff 距离（米）；
      * **实例面积抖动**：相邻两帧里同一实例（按质心最近配对）的面积相对变化。

    为什么这两项与 `delta_p99` 不同：`delta_p99` 只看**数量差**，
    一个障碍整体平移一格时数量差可能是 0（该项为 0 却空间已变），
    而 Hausdorff 会立刻看到"最远偏了一格"；实例面积抖动则抓"同一个障碍
    画大画小"（数量差会被"一个变大一个变小"互相抵消）。
    """
    from grid_geometry import hausdorff, connected_components_8
    hds = []
    area_jit = []
    for a, b in zip(frames, frames[1:]):
        ma = [v >= 100 for v in a['data']]
        mb = [v >= 100 for v in b['data']]
        hd = hausdorff(ma, mb, W, H, RES)
        if hd is not None:
            hds.append(hd)
        ca = connected_components_8(ma, W, H, min_cells=1)
        cb = connected_components_8(mb, W, H, min_cells=1)
        if not ca or not cb:
            continue
        # 按质心最近配对，取面积相对变化
        from grid_geometry import instance_centroid
        cent_b = [instance_centroid(c, W) for c in cb]
        for comp_a in ca:
            tcent = instance_centroid(comp_a, W)
            best, best_d = None, float('inf')
            for i, mc in enumerate(cent_b):
                if mc is None:
                    continue
                d = abs(tcent[0] - mc[0]) + abs(tcent[1] - mc[1])
                if d < best_d:
                    best_d, best = d, i
            if best is None:
                continue
            na, nb = len(comp_a), len(cb[best])
            if na > 0:
                area_jit.append(abs(nb - na) / na)
    hds.sort()
    area_jit.sort()
    return {
        'boundary_hausdorff_jitter_p90_m': _pct(hds, 0.90) if hds else None,
        'boundary_hausdorff_jitter_max_m': hds[-1] if hds else None,
        'instance_area_jitter_p50': _pct(area_jit, 0.50) if area_jit else None,
        'instance_area_jitter_p90': _pct(area_jit, 0.90) if area_jit else None,
    }


def _instance_stability(frames, truth=None):
    """实例级稳定性：**中心抖动**（米），不再只看 occupied 数量差。

    改造前的 `delta_p99` 只看 `abs(Δoccupied)`，对小目标极不公平：
    一个障碍从一个格跳到相邻格时数量差可能是 0，但空间位置已完整变化；
    多个小障碍的进入/离开还会互相抵消数量差。
    """
    from grid_geometry import instance_drift

    drifts = []
    for a, b in zip(frames, frames[1:]):
        ma = [v >= 100 for v in a['data']]
        mb = [v >= 100 for v in b['data']]
        d = instance_drift(ma, mb, W, H, min_cells=1)
        if d is not None:
            drifts.append(d)
    if not drifts:
        return {'center_drift_p90_m': None, 'center_drift_max_m': None, 'n_pairs': 0}
    p90 = [d['p90'] * RES for d in drifts if d['p90'] is not None]
    mx = [d['max'] * RES for d in drifts if d['max'] is not None]
    return {
        'center_drift_p90_m': _pct(sorted(p90), 0.50) if p90 else None,
        'center_drift_max_m': max(mx) if mx else None,
        'n_pairs': len(drifts),
    }


def _verdict(spatial, stab, main=None):
    """逐条判据。None 表示该指标不适用（如全图无占据格），不算失败。

    **稳定性主判据自 ADR-0042 起换成三条空间量**（`main`）：
    集合 IoU / 已知区边界抖动 / 实例中心位移。
    理由：`delta_p99` 只数 occupied 数量差 —— 一个障碍整体平移一格时它可能是 0，
    而空间位置已经完整变化（temp.md 的原始观察）。
    旧的 `delta_p99` 保留为**诊断**，不再进 verdict。
    """
    v = {}
    v['coverage'] = (spatial['coverage'] is None or
                     spatial['coverage'] >= GATES['coverage_min'])
    v['false_positive'] = (spatial['false_positive'] is None or
                           spatial['false_positive'] <= GATES['false_positive_max'])
    v['iou'] = (spatial['iou'] is None or spatial['iou'] >= GATES['iou_min'])
    v['area_ratio'] = (spatial['area_ratio'] is None or
                       spatial['area_ratio'] <= GATES['area_ratio_max'])
    # ---- 稳定性主判据（三条全满足）----
    main = main or {}
    v['set_iou'] = (main.get('set_iou_p50') is None or
                    main['set_iou_p50'] >= GATES['set_iou_p50_min'])
    v['boundary_jitter'] = (main.get('boundary_jitter_p90_m') is None or
                            main['boundary_jitter_p90_m'] <= GATES['boundary_jitter_p90_max_m'])
    v['instance_drift'] = (main.get('instance_drift_p50_m') is None or
                           main['instance_drift_p50_m'] <= GATES['instance_drift_p50_max_m'])
    v['shape_jitter'] = (stab['shape_jitter_p95'] is None or
                         stab['shape_jitter_p95'] <= GATES['shape_jitter_p95_max'])
    return v


def _reachable_mask(frames, cam_positions=None, resolution=None, width=None,
                    height=None):
    """相机**可识别范围**的并集（用户 2026-11-09 裁定）。

    "覆盖率注意是相机可识别范围内的，照不到肯定不能要求"。

    口径（与 `footprint_geometry.hpp` 的 `footprintFromCamera` 同源）：
      * 画幅 = 以相机地面投影为中心的**轴对齐正方形**，半宽 = `H·(width/2)/fx`；
      * 对所有帧求**并集** —— 只要某一帧看得到，那一格就"可要求"；
      * 高度/内参未知时返回 None（退化为全图统计，并明确告警）。

    **为什么用并集而不是逐帧交集**：地图是**累积**的（log-odds），
    任何一帧看到过的证据都会留在图上。所以"可识别范围"也是累积口径。

    `resolution` / `width` / `height` 缺省取规划层（0.5 m / 200×200）。
    **证据层必须显式传自己的几何**（0.25 m / 400×400）—— 用错尺度会让
    "可识别范围"只覆盖真实画幅的 1/4，几何 recall 被人为压低 4 倍，
    而症状是"看起来感知很差"，极难归因。
    """
    import math
    if cam_positions is None:
        print('  ⚠ 无相机轨迹 → 覆盖率按**全图**统计（含照不到的区域），会偏低')
        return None
    # 相机参数：1152²、fx=268.6（与 SDF / camera_info 一致）
    # 注意：这里写死是为了离线复算（没有 camera_info 可订阅）；实跑时的真值
    # 由 map_adapter 从 camera_info 推导，两者用同一恒等式 GSD = H/f。
    fx = 268.6
    half_frac = 1152 / 2.0 / fx        # 半宽 / 高度
    res = resolution or RES
    w = width or W
    hh = height or H
    mask = [[False] * w for _ in range(hh)]
    n = 0
    for (cx, cy, h) in cam_positions:
        if not (h > 0.0):
            continue
        half = h * half_frac
        i0 = max(0, int((cx - half - OX) // res))
        i1 = min(w - 1, int((cx + half - OX) // res))
        j0 = max(0, int((cy - half - OY) // res))
        j1 = min(hh - 1, int((cy + half - OY) // res))
        for j in range(j0, j1 + 1):
            wy = OY + (j + 0.5) * res
            if abs(wy - cy) > half:
                continue
            row = mask[j]
            for i in range(i0, i1 + 1):
                wx = OX + (i + 0.5) * res
                if abs(wx - cx) <= half:
                    row[i] = True
        n += 1
    covered = sum(sum(1 for v in row if v) for row in mask)
    print('  可识别范围（%d 个相机位姿的并集，%.2f m）：%d 格 = %.1f%% 作业区' % (
        n, res, covered, 100.0 * covered / (w * hh)))
    return mask


def evaluate(frames, cam_positions=None, evidence_frames=None, meta_frames=None):
    """frames: [{'data': [...], 'stamp': float}, ...] 按时间顺序。

    `cam_positions`：与 frames 对齐的 (x, y, height) 列表；给了就只统计
    **相机可识别范围内**的指标（用户 2026-11-09 裁定）。

    `evidence_frames`：`/agc/map/evidence` 的帧（证据层，分辨率 = `perception_resolution`）。
    **给了就在它上面算几何重建指标**（temp.md 方向五①「在高分辨率层与高分辨率真值比较」）；
    不给则退回在规划层上算，并在输出里明确标注口径 —— 两者**不得混读**。
    """
    truth, per_obstacle = _load_truth()
    reachable = _reachable_mask(frames, cam_positions)
    per_frame = [_frame_metrics(f, truth, per_obstacle, reachable) for f in frames]
    # 空间指标用**稳态帧**（跳过前 2 帧冷启动），否则首帧 unknown 会把 coverage 拉低
    steady = per_frame[2:] if len(per_frame) > 2 else per_frame
    # 集合级诊断需要**原始栅格**（含 data），与指标帧按同一窗口对齐
    steady_raw = frames[2:] if len(frames) > 2 else frames
    if not steady:
        raise ValueError('帧数不足（至少 3 帧）')

    def agg(key):
        vals = [f[key] for f in steady if f[key] is not None]
        return (sum(vals) / len(vals)) if vals else None

    def agg_fp(bin_key):
        vals = [f['fp_bins'][bin_key] for f in steady
                if f.get('fp_bins') is not None]
        return (sum(vals) / len(vals)) if vals else None

    spatial = {
        'coverage': agg('coverage'),
        'false_positive': agg('false_positive'),
        'fp_beyond_q': agg('fp_beyond_q'),
        'iou': agg('iou'),
        'area_ratio': agg('area_ratio'),
        'occupied_cells': agg('occupied_cells'),
        'truth_cells': steady[0]['truth_cells'],
        'unobserved_truth': agg('unobserved_truth'),
        'out_of_range_truth': agg('out_of_range_truth'),
        'in_range_truth': agg('in_range_truth'),
        'n_frames': len(steady),
        # ---- FP 分档诊断（不参与判定，ADR-0039）----
        'fp_bins': {k: agg_fp(k) for k in ('0-1', '1-3', '>3')},
        'fp_dist_p50': agg('fp_dist_p50'),
        'fp_dist_p90': agg('fp_dist_p90'),
    }
    stab = _stability(steady, per_obstacle, truth, steady_raw)
    # ---- 分层指标（ADR-0040）：几何重建 / 规划可用性 / 实例稳定性 ----
    #
    # **这三套都只是诊断，不参与既有判据**：`GATES` 是预登记的，事后调整等于
    # 伪造结论。它们的用途是把"剩余误差属于哪一类"变成可读的数字，
    # 而不是让指标"看起来通过"。
    truth_components = _obstacle_components(per_obstacle)
    # ---- 几何重建：**优先在证据层上算**（temp.md 方向五①）----
    #
    # 口径分三种，输出里必须标注是哪一种（否则数字会被跨口径比较）：
    #   * `evidence`：证据层帧 + 同分辨率真值 —— **唯一正确的几何评价口径**；
    #   * `planning`：规划层帧 + 0.5 m 真值 —— 含安全膨胀，几何指标会偏低；
    #   * `unavailable`：没有证据层帧，退回规划层（显式标注，不静默混读）。
    geo_source = 'planning'
    geo_reachable = reachable
    geo_frames = steady_raw
    geo_truth = truth
    geo_components = truth_components
    geo_res = RES
    geo_w, geo_h = W, H
    # 元数据的几何（与证据层同尺寸，但独立取 —— 万一两者不同步，用它自己的）
    meta_w, meta_h, meta_res = W, H, RES
    if meta_frames:
        meta_w = int(meta_frames[0].get('w') or W)
        meta_h = int(meta_frames[0].get('h') or H)
        meta_res = float(meta_frames[0].get('res') or RES)
        meta_frames = meta_frames[2:] if len(meta_frames) > 2 else meta_frames
    if evidence_frames:
        ev_res = float(evidence_frames[0].get('res') or EVIDENCE_RES)
        ev_truth, ev_per_obstacle, ev_w, ev_h = _load_truth_at(ev_res)
        ev_steady = evidence_frames[2:] if len(evidence_frames) > 2 else evidence_frames
        # 证据层帧的尺寸必须与同分辨率真值一致；不一致说明几何参数没对齐，
        # **不猜**——直接标 `unavailable` 而不是拿两张不同尺寸的图硬算。
        if ev_steady and ev_w == ev_steady[0].get('w') and ev_h == ev_steady[0].get('h'):
            geo_source = 'evidence'
            geo_frames = ev_steady
            geo_truth = ev_truth
            geo_components = _obstacle_components(ev_per_obstacle, ev_w)
            geo_res = ev_res
            geo_w, geo_h = ev_w, ev_h
            # **可识别范围必须按证据层尺度重算**（同一画幅、更细的格）。
            # 用规划层的 200×200 掩码去套 400×400 的图，会让"可要求"的
            # 真值范围只有真实的 1/4，recall 被人为压低 —— 那是量错尺子，
            # 不是感知变差（本轮实测踩过：recall 0.081 全来自这里）。
            geo_reachable = _reachable_mask(
                geo_frames, cam_positions, ev_res, ev_w, ev_h)
        else:
            geo_source = 'unavailable'
            geo_frames = []
    # 非证据层口径下 `geo_reachable` 沿用规划层掩码（同尺度，可直接用）
    if geo_source != 'evidence':
        geo_reachable = reachable
    geo = [m for m in (_evidence_geometry_metrics(
                           f, geo_truth, geo_reachable, geo_res,
                           truth_components=geo_components)
                       for f in geo_frames) if m is not None]
    plan = [m for m in (_planning_usability_metrics(f, truth, reachable)
                        for f in steady_raw) if m is not None]
    inst = _instance_stability(steady_raw, truth)
    # ---- 栅格可达率（temp.md 方向五"规划成功率"）----
    #
    # **口径声明（不得省略）**：这是"在这个栅格上从起点到终点存不存在一条
    # 可通行路径"，**不含**动力学可行性、不含路径质量、不含倒车。
    # 因此字段名是 `reachability` 而不是 `success_rate` —— 后者会让人
    # 以为量的是"车能不能真的开过去"，那是另一件事。
    #
    # **为什么不能用"碰撞格=0"冒充**：碰撞格为 0 只说明"我没把障碍画成可通行"，
    # 完全不代表"存在一条通路"（可能整片区域被误阻塞，车根本出不去）。
    # 这两件事必须分开量。
    from grid_geometry import planning_success_rate
    layout = _spawn_layout(_ACTIVE_MAP)
    reach = {'success_rate': None, 'n_frames': 0, 'n_success': 0,
             'path_len_p50_m': None, 'expansions_p50': None}
    if layout is not None:
        sc = _world_to_cell(*layout['start_world'])
        gc = _world_to_cell(*layout['goal_world'])
        reach = planning_success_rate(steady_raw, W, H, sc, gc, RES)
        reach['start_cell'] = sc
        reach['goal_cell'] = gc

    def _mean(rows, key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return (sum(vals) / len(vals)) if vals else None

    layered = {
        'evidence_resolution_m': EVIDENCE_RES,
        # 几何指标实际用的口径与分辨率 —— **必须与数字一起读**：
        # `evidence` 才是正确口径，`planning` 含安全膨胀，`unavailable` 是没数据。
        'geometry_source': geo_source,
        'geometry_resolution_m': geo_res,
        'geometry': {
            'precision': _mean(geo, 'precision'),
            'recall': _mean(geo, 'recall'),
            'iou': _mean(geo, 'iou'),
            'boundary_map_to_truth_p90_m': _mean(geo, 'boundary_map_to_truth_p90'),
            'boundary_truth_to_map_p90_m': _mean(geo, 'boundary_truth_to_map_p90'),
            # 逐帧 max 的平均。**它只属于"地图→真值"这个方向** —— 打印时必须与
            # 另一个方向的数值分开，否则读者会拿它和"真值→地图 p90"比较，
            # 得出"max 小于 p90"的错误结论（实测发生过）。
            'boundary_map_to_truth_max_m': _mean(geo, 'boundary_map_to_truth_max'),
            'hausdorff_m': _mean(geo, 'hausdorff_m'),
            'center_error_p50_m': _mean(geo, 'center_error_p50_m'),
            'center_error_p90_m': _mean(geo, 'center_error_p90_m'),
            'area_error_ratio_p50': _mean(geo, 'area_error_ratio_p50'),
            'area_error_ratio_p90': _mean(geo, 'area_error_ratio_p90'),
        },
        'planning': {
            'missed_danger_ratio': _mean(plan, 'missed_danger_ratio'),
            'over_blocked_ratio': _mean(plan, 'over_blocked_ratio'),
            'missed_danger_cells': _mean(plan, 'missed_danger_cells'),
            'over_blocked_cells': _mean(plan, 'over_blocked_cells'),
            'collision_cells': _mean(plan, 'collision_cells'),
            'clearance_min_m': (min((r['clearance_min_m'] for r in plan
                                     if r.get('clearance_min_m') is not None),
                                    default=None)),
            'clearance_p05_m': _mean(plan, 'clearance_p05_m'),
        },
        'instance': inst,
        # ---- 稳定性主判据三条（ADR-0042）：**都在几何口径上算** ----
        'stability_main': {
            'set_iou_p50': stab.get('set_iou_p50'),
            # 边界抖动**优先用实例 id 口径**（跨帧身份稳定）。
            # 连通域配对口径已知会把"大障碍被切掉一侧"记成 5.5 m 抖动（本轮实测），
            # 降级为诊断。
            'boundary_jitter_p90_m': (
                _pct(sorted(_boundary_jitter_by_id(meta_frames, meta_w, meta_h, meta_res)), 0.90)
                if meta_frames else _pct(
                    sorted(_boundary_jitter_known_region(geo_frames, geo_w, geo_h, geo_res)),
                    0.90) if geo_frames else None),
            'boundary_jitter_source': 'instance_id' if meta_frames else 'cluster',
            'boundary_jitter_cluster_p90_m': (
                _pct(sorted(_boundary_jitter_known_region(geo_frames, geo_w, geo_h, geo_res)),
                     0.90) if geo_frames else None),
            # 实例位移**优先用实例 id 口径**（跨帧身份稳定）。
            # 退回聚类配对（`inst.center_drift_p90_m`）只在没有元数据帧时发生，
            # 而那个口径已知会报出 1–5 m 的**配对伪影**（本轮实测），
            # 所以它降级为诊断、不参与判定。
            # **主判据：p50**（ADR-0043）—— 不被少数大实例的边缘翻转支配
            'instance_drift_p50_m': (
                _pct(sorted(_instance_drift_by_id(meta_frames, meta_w, meta_h, meta_res)), 0.50)
                if meta_frames else None),
            # **诊断**：p90 是"最坏那批实例抖了多少"，对定位有用但不进判定
            'instance_drift_p90_m': (
                _pct(sorted(_instance_drift_by_id(meta_frames, meta_w, meta_h, meta_res)), 0.90)
                if meta_frames else None),
            'instance_drift_source': 'instance_id' if meta_frames else 'unavailable',
            # 聚类配对口径（**诊断**，不进判定）：已知含配对伪影
            'instance_drift_cluster_p90_m': inst.get('center_drift_p90_m'),
            'geometry_source': geo_source,
            'geometry_resolution_m': geo_res,
        },
        'reachability': reach,
        'stability_extra': _boundary_and_area_stability(steady_raw),
    }
    return {
        'spatial': spatial,
        'stability': stab,
        'layered': layered,
        'verdict': _verdict(spatial, stab, layered['stability_main']),
        'gates': GATES,
        'per_frame': per_frame,
    }


# ----------------------------------------------------------------------------- 采集
def _dds_env():
    """套用 demo 的 DDS 传输配置 —— **不套就一帧都收不到**（实测）。

    **为什么必须**：本机 WSL2 的 `lo` 无 `IFF_MULTICAST`（flags=0x9），默认 FastDDS
    发现绑到 `lo` 且往 224.0.0.1 发包 ⇒ 零送达。`scripts/demo/dds_transport.py` 因此
    在 `lo` 无组播时强制 `SUBNET + SHM`。测量脚本若用默认 env，会**静默收到 0 帧**
    （我第一次就是这么失败的，还以为地图没在更新）。
    """
    import os
    import sys
    demo_dir = str(ROOT / 'scripts' / 'demo')
    if demo_dir not in sys.path:
        sys.path.insert(0, demo_dir)
    import dds_transport
    env = dds_transport.env_for(flags=0)   # 强制 subnet-shm（本机唯一可用组合）
    os.environ.update(env)
    return dds_transport.select()


def _collect_live(duration_s: float, min_frames: int):
    """实时订阅 /agc/map（transient_local 会立刻给最后一帧，然后按更新收）。"""
    import time
    policy = _dds_env()
    print('DDS 策略 = %s（已套用 demo 的传输配置）' % policy)
    import rclpy
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from nav_msgs.msg import OccupancyGrid

    rclpy.init()
    node = rclpy.create_node('perception_quality')
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE,
                     history=HistoryPolicy.KEEP_LAST)
    frames = []

    def cb(msg):
        frames.append({'data': list(msg.data),
                       'stamp': msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                       'w': msg.info.width, 'h': msg.info.height,
                       'res': msg.info.resolution})

    node.create_subscription(OccupancyGrid, '/agc/map', cb, qos)

    # ---- 证据层（ADR-0042）：几何重建的权威表达 ----
    #
    # **为什么必须收它**：temp.md 方向五要求"在高分辨率层与高分辨率真值比较"。
    # 改造前这里只收 `/agc/map`（0.5 m 规划层 + 风险分档 + max-pool），
    # 于是量到的几何精度里混着"安全膨胀有多保守"—— 那正是要修的口径错误。
    # 现在两层分开收，几何指标只在证据层上算。
    ev_frames = []

    def ev_cb(msg):
        ev_frames.append({'data': list(msg.data),
                          'stamp': msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                          'w': msg.info.width, 'h': msg.info.height,
                          'res': msg.info.resolution})

    node.create_subscription(OccupancyGrid, '/agc/map/evidence', ev_cb, qos)

    # ---- 逐格元数据（ADR-0042）：实例身份与可见性的来源 ----
    #
    # **为什么实例位移必须用它**：实例身份必须**跨帧稳定**。每帧重新聚类再按
    # 最近配对，会在大障碍被切成两块时把新块配到别的障碍上，得到 1–5 m 的
    # 配对伪影（实测 24→28 个连通域），而真实障碍没动。
    meta_frames = []

    def meta_cb(msg):
        meta_frames.append({
            'stamp': msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            'w': msg.width, 'h': msg.height, 'res': msg.resolution,
            'source_instance_id': list(msg.source_instance_id),
            'fully_visible': list(msg.fully_visible),
            'confidence': list(msg.confidence),
            'occupancy_ratio': list(msg.occupancy_ratio),
            'last_seen_s': list(msg.last_seen_s),
        })

    try:
        from agc_msgs.msg import PerceptionCellMeta
        node.create_subscription(PerceptionCellMeta, '/agc/map/cell_meta', meta_cb, qos)
    except Exception:      # noqa: BLE001
        # 消息不可用（旧构建）时**不阻塞评价**：实例位移会退回"不可用"，
        # 而不是拿聚类伪影冒充（那会给出一个看起来合理的错数字）。
        pass

    # **相机轨迹**（2026-11-09 用户裁定）：覆盖率只对"相机可识别范围"算，
    # 所以必须同时记录相机位姿。高度用机体 z + 安装高（与 map_adapter 同口径）。
    from nav_msgs.msg import Odometry
    poses = []   # (stamp, x, y, h)

    def on_odom(m):
        poses.append((m.header.stamp.sec + m.header.stamp.nanosec * 1e-9,
                      m.pose.pose.position.x, m.pose.pose.position.y,
                      m.pose.pose.position.z + 0.242))

    node.create_subscription(Odometry, '/agc/air/odom', on_odom, 20)

    t0 = time.time()
    while time.time() - t0 < duration_s:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_node()
    rclpy.shutdown()
    if len(frames) < min_frames:
        raise SystemExit('只收到 %d 帧（需要 ≥%d）；地图未在更新？' % (len(frames), min_frames))
    # 把每个地图帧对齐到**最近的**相机位姿
    for f in frames + ev_frames:
        if not poses:
            f['cam'] = None
            continue
        best = min(poses, key=lambda p: abs(p[0] - f['stamp']))
        f['cam'] = (best[1], best[2], best[3])
    # 证据层 / 元数据帧挂在主帧列表的旁路上（调用方按需使用）。
    return frames, ev_frames, meta_frames


def _save_frames(frames, path: Path):
    """存成 .npz：`data` 是 (n_frames, W*H) int8，`stamp` 是 (n_frames,) float64。

    **为什么要存**：仿真一次约 2.5 分钟，而分析误覆盖/跳变要反复试不同切片方式。
    存下来就能离线跑任意分析，不必每次重跑 —— 这是"先取证再下结论"的前提。
    """
    import numpy as np
    arr = np.array([f['data'] for f in frames], dtype=np.int8)
    stamps = np.array([f['stamp'] for f in frames], dtype=np.float64)
    # 相机位姿（缺失填 NaN）—— 离线算"可识别范围"必需
    cams = np.array([f.get('cam') or (np.nan, np.nan, np.nan) for f in frames],
                    dtype=np.float64)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, data=arr, stamp=stamps, cam=cams,
                        w=W, h=H, res=RES, ox=OX, oy=OY)
    print('已存 %d 帧 → %s' % (len(frames), path))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--map', default='yard',
                    help='真值/几何来源地图名（默认 yard；dense_map 等）')
    ap.add_argument('--live', action='store_true', help='实时订阅 /agc/map')
    ap.add_argument('--duration', type=float, default=60.0, help='实时采样时长（s）')
    ap.add_argument('--min-frames', type=int, default=5)
    ap.add_argument('--json', type=Path, help='把完整结果写到该文件')
    ap.add_argument('--save-frames', type=Path,
                    help='把原始栅格帧存成 .npz（供离线反复分析，不必重跑仿真）')
    args = ap.parse_args(argv)
    _apply_map_geometry(args.map)

    if not args.live:
        raise SystemExit('本脚本目前只支持 --live（离线 bag 读取待实现）')
    frames, ev_frames, meta_frames = _collect_live(args.duration, args.min_frames)
    if args.save_frames:
        _save_frames(frames, args.save_frames)
    cams = [f.get('cam') for f in frames]
    res = evaluate(frames, cams if all(c is not None for c in cams) else None,
                   evidence_frames=ev_frames or None,
                   meta_frames=meta_frames or None)

    sp, st, vd = res['spatial'], res['stability'], res['verdict']
    sm = (res.get('layered') or {}).get('stability_main') or {}
    print('感知栅格质量（%d 帧稳态，对 %s.yaml 几何真值）' % (sp['n_frames'], _ACTIVE_MAP))
    print('-' * 62)
    print('  真值占据格          %d' % sp['truth_cells'])
    print('  地图占据格（均值）  %.0f' % (sp['occupied_cells'] or 0))
    print('  画幅内真值格        %.0f（覆盖率分母；范围外的不做要求）'
          % (sp['in_range_truth'] or 0))
    print('  未观测的真值格      %.0f（在画幅内但没被标出来）' % (sp['unobserved_truth'] or 0))
    print('-' * 62)
    # (显示名, 判据键, 值, 格式, 门限, 比较符)
    rows = [
        ('面积覆盖率', 'coverage', sp['coverage'], '%.3f', GATES['coverage_min'], '>='),
        ('误覆盖率', 'false_positive', sp['false_positive'], '%.3f',
         GATES['false_positive_max'], '<='),
        ('  其中超量化下界', None, sp['fp_beyond_q'], '%.0f', None, ''),        ('IoU', 'iou', sp['iou'], '%.3f', GATES['iou_min'], '>='),
        ('面积比', 'area_ratio', sp['area_ratio'], '%.3f', GATES['area_ratio_max'], '<='),
        ('形状抖动 p95', 'shape_jitter', st['shape_jitter_p95'], '%.3f',
         GATES['shape_jitter_p95_max'], '<='),
        # ---- 稳定性主判据（ADR-0042）----
        ('集合 IoU p50', 'set_iou', sm.get('set_iou_p50'), '%.3f',
         GATES['set_iou_p50_min'], '>='),
        ('边界抖动 p90 m', 'boundary_jitter', sm.get('boundary_jitter_p90_m'), '%.2f',
         GATES['boundary_jitter_p90_max_m'], '<='),
        ('实例位移 p50 m', 'instance_drift', sm.get('instance_drift_p50_m'), '%.2f',
         GATES['instance_drift_p50_max_m'], '<='),
    ]
    for name, key, val, fmt, gate, op in rows:
        if val is None:
            print('  %-14s   不适用' % name)
            continue
        if key is None:
            # 参考行（不参与判定）：离真值 >1 格的误覆盖格数 —— 量化效应不该算算法错
            print('  %-14s %8s   格（参考，不判定）' % (name, fmt % val))
            continue
        mark = 'OK' if vd[key] else 'FAIL'
        print('  %-14s %8s   (判据 %s %s)  %s' % (name, fmt % val, op, gate, mark))
    print('-' * 62)
    # ---- FP 分档诊断（**不参与判定**，ADR-0039）----
    # 三档对应三种不同根因，混在一起只会得出"误覆盖高"这一个无用结论：
    #   0–1 格 = 栅格量化/边界误差；1–3 格 = 投影误差/时间错位/形态外扩；
    #   >3 格 = 明显错误投影/残影/错误 carving。
    fb = sp.get('fp_bins') or {}
    if any(v is not None for v in fb.values()):
        total = sum(v for v in fb.values() if v is not None)
        def _pct_of(v):
            return ('%.1f%%' % (100.0 * v / total)) if (total and v is not None) else '-'
        print('  [诊断] FP 分档（距真值格距）：0–1 格 %s（%s） 1–3 格 %s（%s） >3 格 %s（%s）' % (
            '%.0f' % (fb.get('0-1') or 0), _pct_of(fb.get('0-1')),
            '%.0f' % (fb.get('1-3') or 0), _pct_of(fb.get('1-3')),
            '%.0f' % (fb.get('>3') or 0), _pct_of(fb.get('>3'))))
        print('  [诊断] FP 到真值距离 p50=%s p90=%s 格' % (
            sp.get('fp_dist_p50'), sp.get('fp_dist_p90')))
    print('-' * 62)
    print('  |Δocc| p50=%s p90=%s max=%s（%d 对）' % (
        st['delta_p50'], st['delta_p90'], st['delta_max'], st['n_pairs']))
    # ---- 集合级诊断（**不参与判定**，用于区分"空间抖动"与"数量波动"）----
    # 只有 |Δ| 时无法判断：140 是"140 格离开"还是"500 格离开 + 360 格进入"。
    print('  [诊断] 离开 p99=%s 进入 p99=%s 集合 IoU p50=%s 互换率 p50=%s' % (
        st['exit_p99'], st['enter_p99'],
        '%.3f' % st['set_iou_p50'] if st['set_iou_p50'] is not None else None,
        '%.3f' % st['churn_ratio_p50'] if st['churn_ratio_p50'] is not None else None))
    print('  [诊断] 离开格到真值边界 p90=%s 格  变化格贴地图外缘占比 p50=%s' % (
        st['exit_dist_p90'],
        '%.3f' % st['edge_frac_p50'] if st['edge_frac_p50'] is not None else None))
    # 旧判据自 ADR-0042 起降为**诊断**：它只数 occupied 数量差，对"整体平移一格"
    # 这类真实抖动不敏感（temp.md 的原始观察）。保留它是因为与历史结论可比。
    print('  （|Δocc| p99 自 ADR-0042 起为**诊断**：只数数量差，对平移一格不敏感；'
          '主判据见上表三条空间量）')
    # ---- 分层指标（ADR-0040，**不参与判定**）----
    #
    # 三层回答三个不同问题，不得互相冒充：
    #   几何重建 —— 感知把障碍画得准不准（对真值几何）；
    #   规划可用性 —— 规划图会不会漏掉危险 / 会不会误挡；
    #   实例稳定性 —— 同一个障碍的中心会不会来回跳。
    ly = res.get('layered') or {}
    g = ly.get('geometry') or {}
    pl = ly.get('planning') or {}
    ins = ly.get('instance') or {}

    def _fmt(v, fmt='%.3f'):
        return '—' if v is None else (fmt % v)

    print('-' * 62)
    # **口径必须与数字一起读**：`evidence` 才是正确的几何评价口径；
    # `planning` 含安全膨胀（几何指标会偏低）；`unavailable` 是没收到证据层帧。
    src = ly.get('geometry_source') or 'planning'
    src_label = {'evidence': '证据层', 'planning': '规划层（含膨胀，口径偏低）',
                 'unavailable': '无数据'}.get(src, src)
    print('  [分层] 几何重建（感知准不准，对真值几何）· 口径=%s @ %.2f m'
          % (src_label, ly.get('geometry_resolution_m') or RES))
    print('         precision=%s recall=%s IoU=%s' % (
        _fmt(g.get('precision')), _fmt(g.get('recall')), _fmt(g.get('iou'))))
    # **每方向一行**：两个方向的距离不可混读（一个是"我画出去的多远"，
    # 另一个是"真值离我多远"）。把 max 跟在另一个方向的 p90 后面会误导读者。
    print('         边界距离 地图→真值：p90 %s m / 最大 %s m（画出去的东西偏多远）' % (
        _fmt(g.get('boundary_map_to_truth_p90_m'), '%.2f'),
        _fmt(g.get('boundary_map_to_truth_max_m'), '%.2f')))
    print('         边界距离 真值→地图：p90 %s m（真值有没有被我漏掉）' % (
        _fmt(g.get('boundary_truth_to_map_p90_m'), '%.2f'),))
    print('  [分层] 规划可用性（会不会漏危险 / 会不会误挡）')
    print('         漏掉危险障碍 %s（%s 格）  误阻塞 %s（%s 格）' % (
        _fmt(pl.get('missed_danger_ratio')),
        _fmt(pl.get('missed_danger_cells'), '%.0f'),
        _fmt(pl.get('over_blocked_ratio')),
        _fmt(pl.get('over_blocked_cells'), '%.0f')))
    print('         碰撞格 %s（判为可通行但真值是障碍）；'
          '最小安全间隙 %s m（p05 %s m）' % (
              _fmt(pl.get('collision_cells'), '%.0f'),
              _fmt(pl.get('clearance_min_m'), '%.2f'),
              _fmt(pl.get('clearance_p05_m'), '%.2f')))
    print('         最坏点 Hausdorff %s m；中心误差 p50 %s / p90 %s m；'
          '面积误差 p50 %s / p90 %s' % (
              _fmt(g.get('hausdorff_m'), '%.2f'),
              _fmt(g.get('center_error_p50_m'), '%.2f'),
              _fmt(g.get('center_error_p90_m'), '%.2f'),
              _fmt(g.get('area_error_ratio_p50'), '%+.2f'),
              _fmt(g.get('area_error_ratio_p90'), '%+.2f')))
    # ---- 栅格可达率（temp.md 方向五）----
    #
    # **必须带限定语**：这是"栅格上通不通"，不是"车能不能开过去"。
    # 省略限定语会让这个数字被当成端到端规划成功率引用 —— 那是另一件事，
    # 本脚本**没有**跑规划器、也没有动力学模型。
    rc = ly.get('reachability') or {}
    if rc.get('n_frames'):
        print('  [分层] 栅格可达率（**不含动力学**：只答"图上通不通"）')
        print('         成功 %s / %s 帧 = %s  路径长 p50=%s m  展开 p50=%s' % (
            rc.get('n_success'), rc.get('n_frames'),
            _fmt(rc.get('success_rate')),
            _fmt(rc.get('path_len_p50_m'), '%.1f'),
            _fmt(rc.get('expansions_p50'), '%.0f')))
        sc, gc = rc.get('start_cell'), rc.get('goal_cell')
        if sc and gc:
            print('         起终点格 %s → %s（来自 spawn_layout，非写死）' % (sc, gc))
    else:
        print('  [分层] 栅格可达率  不适用（无出生布局或无有效帧）')
    print('  [分层] 实例稳定性（同一障碍中心会不会跳）')
    print('         中心抖动 p90=%s m，最大 %s m' % (
        _fmt(ins.get('center_drift_p90_m'), '%.2f'),
        _fmt(ins.get('center_drift_max_m'), '%.2f')))
    se = ly.get('stability_extra') or {}
    print('         边界 Hausdorff 抖动 p90=%s m（最大 %s m）；'
          '实例面积抖动 p50=%s p90=%s' % (
              _fmt(se.get('boundary_hausdorff_jitter_p90_m'), '%.2f'),
              _fmt(se.get('boundary_hausdorff_jitter_max_m'), '%.2f'),
              _fmt(se.get('instance_area_jitter_p50'), '%.3f'),
              _fmt(se.get('instance_area_jitter_p90'), '%.3f')))
    print('  （以上三套均为诊断量，**不参与判定**；既有判据见上表）')
    all_ok = all(vd.values())
    print('  总判定：%s' % ('✅ 全部通过' if all_ok else '❌ 有判据未通过：' +
                           ', '.join(k for k, ok in vd.items() if not ok)))
    if args.json:
        args.json.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                             encoding='utf-8')
        print('  完整结果 → %s' % args.json)
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
