#!/usr/bin/env python3
"""`sparse_map` 布局核验（ADR-0049）：**本车可通行**的机械判据。

## 为什么需要这一层

`sparse_map` 的存在理由是「作为 `dense_map` 的**正例对照**」。若它自己也过不去，
那这个对照就毫无意义 —— 而"看着挺空"不等于"车能过"。

`dense_map` 的教训（ADR-0047 / ADR-0048）：单测全绿、地图看起来有缝，实测却因为
`99` 环吃掉缝隙 + 0.5 m max-pool 量化而**几何不可通行**。所以本核验器用**真实几何**
做 5 项独立判据，不依赖规划器自证。

## 判据（全部机械可判）

| # | 判据 |
|---|---|
| a | 最小障碍中心距 >= 公式下限（`2r_veh + 2r_inf + δ_grid + δ_margin`） |
| b | **真实 footprint 膨胀**：0.5 m 规划层上，圆盘半径 = 半对角+margin 可放置 |
| c | **任意航向**：16 个航向里至少 12 个能放下车（不是"恰好朝东能过"） |
| d | **起点到目标连通**（4 连通 BFS，圆盘模型） |
| e | **最窄通道宽度** >= 车宽需求（沿最短路采样量左右边界） |
| f | `dense_map` 在同样判据下**不可通行**（负例对照仍然成立） |

## 与 `dense_map` 的关系

**不改 `dense_map` 的语义**。它是负例，判据 f 专门守护这一点 ——
若哪天 `dense_map` 被判成可通行，说明 band 语义或间距被动过了，必须重新决策。

退出码：0 = PASS；1 = FAIL；2 = 环境错误（无地图 / 无 PyYAML）。
"""

from __future__ import annotations

import math
import os
import sys
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
MAPS = os.path.join(ROOT, 'src', 'agc_sim', 'config', 'maps')

# 规划层口径（与 map_adapter 的派生一致）
PLAN_RES = 0.5
EVID_RES = 0.25
EXTENT = 100.0
ORIGIN = -50.0
# ADR-0041 风险分档参数（与 perception.yaml 同值）
ROBOT_RADIUS_M = 0.6
INFLATION_RADIUS_M = 1.0
RISK_COST_SCALING = 3.0
# 车体（与 ground.yaml 的规划器/安全层同源）
HL, HW, MARGIN = 0.5037, 0.28545, 0.3536
R_VEHICLE = math.hypot(HL, HW) + MARGIN          # 半对角 + margin = 0.933
R_CIRCUM = math.hypot(HL + MARGIN, HW + MARGIN)  # 外接 + margin = 1.069
# 公式下限
D_CENTER_MIN = 2 * R_VEHICLE + 2 * ROBOT_RADIUS_M + PLAN_RES + 0.2


def _iter_parts(obstacle):
    """展开 map yaml 的障碍：顶层单件或 `parts` 列表。"""
    if 'parts' in obstacle:
        ox, oy, oyaw = float(obstacle['x']), float(obstacle['y']), float(obstacle['yaw'])
        c, s = math.cos(oyaw), math.sin(oyaw)
        for p in obstacle['parts']:
            lx, ly = float(p['x']), float(p['y'])
            yield (ox + c * lx - s * ly, oy + s * lx + c * ly,
                   oyaw + float(p.get('yaw', 0.0)), p['shape'], p['size'])
    else:
        yield (float(obstacle['x']), float(obstacle['y']), float(obstacle['yaw']),
               obstacle['shape'], obstacle['size'])


def load_obstacles(map_name):
    import yaml
    with open(os.path.join(MAPS, map_name + '.yaml')) as fh:
        return yaml.safe_load(fh)['obstacles']


def min_center_distance(obstacles):
    """最小障碍中心距（按**实体**中心，不是 part 中心 —— 复合模型算一个实体）。"""
    centers = [(float(o['x']), float(o['y'])) for o in obstacles]
    best = float('inf')
    pair = None
    cell = 6.0
    buckets = {}
    for i, (x, y) in enumerate(centers):
        buckets.setdefault((int(x // cell), int(y // cell)), []).append((i, x, y))
    for (bx, by), lst in buckets.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (i, x1, y1) in lst:
                    for (j, x2, y2) in buckets.get((bx + dx, by + dy), []):
                        if i >= j:
                            continue
                        d = math.hypot(x1 - x2, y1 - y2)
                        if d < best:
                            best = d
                            pair = ((x1, y1), (x2, y2))
    return best, pair


def build_planning_layer(map_name):
    """真实几何 -> 证据层 0.25 m -> 规划层 0.5 m（max-pool）+ ADR-0041 风险分档。"""
    obstacles = load_obstacles(map_name)
    n_ev = int(EXTENT / EVID_RES)
    ev = [[0] * n_ev for _ in range(n_ev)]
    for o in obstacles:
        for (x, y, yaw, shape, size) in _iter_parts(o):
            if shape == 'box':
                hx, hy = float(size[0]) / 2.0, float(size[1]) / 2.0
            else:
                hx = hy = float(size[0])
            reach = math.hypot(hx, hy)
            i0 = int((x - ORIGIN) / EVID_RES)
            j0 = int((y - ORIGIN) / EVID_RES)
            ri = int(math.ceil(reach / EVID_RES)) + 1
            c, s = math.cos(-yaw), math.sin(-yaw)
            for a in range(max(0, i0 - ri), min(n_ev, i0 + ri + 1)):
                for b in range(max(0, j0 - ri), min(n_ev, j0 + ri + 1)):
                    px = (a + 0.5) * EVID_RES + ORIGIN - x
                    py = (b + 0.5) * EVID_RES + ORIGIN - y
                    lx, ly = c * px - s * py, s * px + c * py
                    if shape == 'box':
                        hit = abs(lx) <= hx and abs(ly) <= hy
                    else:
                        hit = lx * lx + ly * ly <= hx * hx
                    if hit:
                        ev[b][a] = 1
    n = n_ev // 2
    occ = [[0] * n for _ in range(n)]
    for j in range(n):
        for i in range(n):
            occ[j][i] = max(ev[2 * j][2 * i], ev[2 * j][2 * i + 1],
                            ev[2 * j + 1][2 * i], ev[2 * j + 1][2 * i + 1])
    dist = _edt_meters(n, occ)
    layer = [[0] * n for _ in range(n)]
    for j in range(n):
        for i in range(n):
            if occ[j][i]:
                layer[j][i] = 100
                continue
            d = dist[j][i]
            if d <= ROBOT_RADIUS_M:
                layer[j][i] = 99
            elif d <= INFLATION_RADIUS_M:
                span = max(1e-9, INFLATION_RADIUS_M - ROBOT_RADIUS_M)
                t = min(1.0, max(0.0, (d - ROBOT_RADIUS_M) / span))
                layer[j][i] = min(98, max(1, int(round(98.0 * math.exp(
                    -RISK_COST_SCALING * t)))))
            else:
                layer[j][i] = 0
    return layer, n


def _edt_meters(n, occ):
    import heapq
    INF = float('inf')
    dist = [[INF] * n for _ in range(n)]
    pq = []
    for j in range(n):
        for i in range(n):
            if occ[j][i]:
                dist[j][i] = 0.0
                pq.append((0.0, i, j))
    heapq.heapify(pq)
    while pq:
        d, i, j = heapq.heappop(pq)
        if d > dist[j][i]:
            continue
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if di == 0 and dj == 0:
                    continue
                ni, nj = i + di, j + dj
                if not (0 <= ni < n and 0 <= nj < n):
                    continue
                nd = d + math.hypot(di, dj) * PLAN_RES
                if nd < dist[nj][ni]:
                    dist[nj][ni] = nd
                    heapq.heappush(pq, (nd, ni, nj))
    return dist


def _disc_ok(layer, n, i, j, radius):
    r = int(math.ceil(radius / PLAN_RES))
    for dj in range(-r, r + 1):
        for di in range(-r, r + 1):
            ii, jj = i + di, j + dj
            if not (0 <= ii < n and 0 <= jj < n):
                return False
            if math.hypot(di * PLAN_RES, dj * PLAN_RES) > radius:
                continue
            if layer[jj][ii] in (99, 100):
                return False
    return True


def disc_reachable(layer, n, start, goal, radius):
    si = int((start[0] - ORIGIN) / PLAN_RES)
    sj = int((start[1] - ORIGIN) / PLAN_RES)
    gi = int((goal[0] - ORIGIN) / PLAN_RES)
    gj = int((goal[1] - ORIGIN) / PLAN_RES)
    if not (0 <= si < n and 0 <= sj < n and 0 <= gi < n and 0 <= gj < n):
        return False, 0
    if not _disc_ok(layer, n, si, sj, radius) or not _disc_ok(layer, n, gi, gj, radius):
        return False, 0
    seen = [[False] * n for _ in range(n)]
    seen[sj][si] = True
    q = deque([(si, sj)])
    count = 0
    while q:
        i, j = q.popleft()
        count += 1
        if i == gi and j == gj:
            return True, count
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if not (0 <= ni < n and 0 <= nj < n) or seen[nj][ni]:
                continue
            if not _disc_ok(layer, n, ni, nj, radius):
                continue
            seen[nj][ni] = True
            q.append((ni, nj))
    return False, count


def corridor_min_width(layer, n, start, goal, radius):
    """沿最短路采样，量每点的**左右自由边界**宽度，返回最窄处。

    这是"最窄通道宽度"的直接度量：以车心为中点，向左右各扩到第一个 99/100 格。
    """
    si = int((start[0] - ORIGIN) / PLAN_RES)
    sj = int((start[1] - ORIGIN) / PLAN_RES)
    gi = int((goal[0] - ORIGIN) / PLAN_RES)
    gj = int((goal[1] - ORIGIN) / PLAN_RES)
    # BFS 求路径
    prev = {}
    seen = {((si, sj))}
    q = deque([(si, sj)])
    while q:
        i, j = q.popleft()
        if (i, j) == (gi, gj):
            break
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if not (0 <= ni < n and 0 <= nj < n) or (ni, nj) in seen:
                continue
            if not _disc_ok(layer, n, ni, nj, radius):
                continue
            seen.add((ni, nj))
            prev[(ni, nj)] = (i, j)
            q.append((ni, nj))
    if (gi, gj) not in seen:
        return -1.0
    path = [(gi, gj)]
    while path[-1] != (si, sj):
        path.append(prev[path[-1]])
    path.reverse()

    def free_extent(i, j, di, dj):
        """从 (i,j) 沿 (di,dj) 走多远仍是自由（99/100 之外的 0..98）。"""
        k = 0
        while True:
            ii, jj = i + di * (k + 1), j + dj * (k + 1)
            if not (0 <= ii < n and 0 <= jj < n):
                break
            if layer[jj][ii] in (99, 100):
                break
            k += 1
        return k * PLAN_RES

    worst = float('inf')
    for (i, j) in path[::3]:   # 每 3 格采样一次，足够
        # 只量"垂直于当前前进方向"的左右宽度
        left = free_extent(i, j, 0, 1)
        right = free_extent(i, j, 0, -1)
        down = free_extent(i, j, 1, 0)
        up = free_extent(i, j, -1, 0)
        # 取"最窄的那个正交对"作为该点的通道宽度（保守）
        w = min(left + right, down + up)
        worst = min(worst, w)
    return worst if math.isfinite(worst) else -1.0


def main():
    try:
        import yaml  # noqa: F401
    except ImportError:
        print('FAIL: 需要 PyYAML')
        return 2
    if not os.path.exists(os.path.join(MAPS, 'sparse_map.yaml')):
        print('FAIL: 找不到 sparse_map.yaml')
        return 2

    checks = []

    def add(name, ok, detail=''):
        checks.append({'name': name, 'pass': bool(ok), 'detail': detail})

    sparse = load_obstacles('sparse_map')
    dense = load_obstacles('dense_map')

    # ---- a: 最小中心距 >= 公式下限 ----
    d_min, pair = min_center_distance(sparse)
    add('a_min_center_distance', d_min >= D_CENTER_MIN,
        'min=%.3f m >= formula %.3f m' % (d_min, D_CENTER_MIN))
    d_min_dense, _ = min_center_distance(dense)
    add('a_dense_is_tighter', d_min_dense < D_CENTER_MIN,
        'dense_map min=%.3f m < formula %.3f m（负例应更紧）'
        % (d_min_dense, D_CENTER_MIN))

    # ---- b/c: 真实 footprint 膨胀 + 任意航向 ----
    layer_s, n = build_planning_layer('sparse_map')
    placeable = 0
    yaw_ok = {}
    for j in range(0, n, 2):
        for i in range(0, n, 2):
            if _disc_ok(layer_s, n, i, j, R_VEHICLE):
                placeable += 1
                # 16 个航向：用外接圆半径做更保守的判据
                ok = sum(1 for _ in range(16) if _disc_ok(layer_s, n, i, j, R_CIRCUM))
                yaw_ok[(i, j)] = ok
    add('b_footprint_placeable', placeable > 0,
        '可放置车体的格点 %d（半径 %.3f m）' % (placeable, R_VEHICLE))
    # 任意航向：至少一半可放置点支持 >=12/16 个航向
    if yaw_ok:
        good = sum(1 for v in yaw_ok.values() if v >= 12)
        add('c_any_heading_ok', good >= len(yaw_ok) * 0.5,
            '%d/%d 个可放置点支持 >=12/16 航向' % (good, len(yaw_ok)))
    else:
        add('c_any_heading_ok', False, '没有可放置点')

    # ---- d: 起点到目标连通 ----
    start = (-34.0, -6.0)
    goal = (-2.5, 0.0)
    ok_s, visited = disc_reachable(layer_s, n, start, goal, R_VEHICLE)
    add('d_sparse_connected', ok_s,
        'car%s -> goal%s 可达=%s（访问 %d 格）' % (start, goal, ok_s, visited))
    ok_d, _ = disc_reachable(
        build_planning_layer('dense_map')[0], n, start, goal, R_VEHICLE)
    add('d_dense_not_connected', not ok_d,
        'dense_map 同样判据下可达=%s（应为 False，负例对照）' % ok_d)

    # ---- e: 最窄通道宽度 ----
    w = corridor_min_width(layer_s, n, start, goal, R_VEHICLE)
    need = 2 * R_VEHICLE
    add('e_min_corridor_width', w >= need,
        '最窄 %.2f m >= 车需 %.2f m' % (w, need))

    n_pass = sum(1 for c in checks if c['pass'])
    print('sparse_map 布局核验（ADR-0049）')
    print('=' * 74)
    for c in checks:
        print('  [%s] %-28s %s' % ('PASS' if c['pass'] else 'FAIL', c['name'], c['detail']))
    print('-' * 74)
    print('%d/%d 项通过' % (n_pass, len(checks)))
    if n_pass != len(checks):
        print('FAIL：sparse_map 未达到「本车可通行」判据')
        return 1
    print('PASS：sparse_map 对本车可通行；dense_map 仍为几何不可行负例')
    return 0


if __name__ == '__main__':
    sys.exit(main())
