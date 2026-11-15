#!/usr/bin/env python3
"""规划器在**真实地图**上的可达性与失败分类核查（ADR-0048）。

## 为什么需要这一层

`src/agc_ground/test/test_planner_algorithms.cpp` 的 53 项 gtest 用的是**合成**小图，
它们能证明算法逻辑正确，但证明不了「在真实 `dense_map` / `yard` 上会发生什么」。

本仓已经有过这种教训（ADR-0047）：安全层单测全绿，而真实 `dense_map` 上出生点
一启动就零速。所以规划器也必须有一条**真实几何**的核查。

## 做法

1. 读 `src/agc_sim/config/maps/<map>.yaml` 的真实障碍几何；
2. 按 `map_adapter` 的口径派生规划层：证据层 0.25 m（max-pool 源）→ 规划层 0.5 m；
3. 按 ADR-0041 的风险分档把几何占据膨胀成 `-1/0/1–98/99/100`
   （与 `inflation_field.hpp` 的 `classifyRisk` / `riskToGridValue` 同口径）；
4. 把栅格写成文本，喂给**生产规划器**（`planner_replay` 可执行）；
5. 断言可达性、路径无碰撞、末端 == goal、失败分类正确。

**关键口径**：这一步**不**复制生产算法，只复制地图派生。生产规划器是真的被调用的
二进制 —— 与 `check_safety_directional_corridor.py` 的模式一致。

## 判据

| # | 断言 |
|---|---|
| a | `yard`：`(-15,1)` → `(-2.5,0)` 能规划成功（无障碍直达） |
| b | `yard` 路径的每个点 footprint 不碰 `99/100`（用真实几何复核） |
| c | 障碍全封死时**显式失败**（不是静默成功） |
| d | 未知格禁止进入（未知区起点 → `start_not_free`） |
| e | `dense_map` 上**不得**返回穿障/穿未知的路径（成功则必须无碰撞） |
| f | 相同输入两次运行结果**逐位一致**（确定性） |
| g | `dense_map` 的可通行性用**独立几何判据**（圆盘模型 BFS）判定，不靠规划器自证 |
| h | `yard` 的 s19 路线（34 m，**路径上有障碍**）能规划出**绕行**路径并通过全复核 |
| i | s19 路径确实**绕开**了直线上的障碍（不是直线穿过去） |
| j | 接缝连续性：路径每点航向与到下一段的方向一致（末点取末段切线） |
| k | 不可行场景按预算失败，**不**删障碍、**不**放宽阈值、**不**用旧路径 |

## 为什么 s19 是**唯一**能测绕障的整链场景

`yard` 的主场景（`s04`）车位 `(-15,1)` → 目标 `(-2.5,0)` 的 12.5 m 直线上
**没有任何障碍物**（最近的也在 3 m 外）—— 那条证据只能证明"直达"，测不到搜索与绕障。

`s19`（车位 `(14,4)` → 目标 `(14,-30)`，34 m）的直线穿过 `container_yard_b`（距 3.0 m）
与 `hut_s` 等障碍，是 `yard` 上唯一真正需要绕行的路线。

## `dense_map` 的可通行性：**登记为已知边界，不当成通过**

实测（本脚本 + 独立圆盘 BFS）：

```text
dense_map 最小障碍中心距 = 2.646 m（ADR-0044）
ADR-0041 的 99 环每侧 0.6 m ⇒ 每道缝被吃掉 1.2 m
剩余自由带 0.25..0.85 m，而本车需要 0.93 m（半对角 + margin）
0.5 m max-pool 再量化掉剩余部分
```

圆盘连通性扫描（0.5 m 规划层，4 连通）：

| 圆盘半径 | 能否从车位到 goal |
|---|---|
| ≤ 0.70 m | 能 |
| ≥ 0.80 m | **不能** |

本车需要 0.93 m ⇒ **`dense_map` 在当前 band 语义下对本车不可通行**。

这与 ADR-0047 已登记的事实一致：「0.5 m 规划层分辨不了 < 1.5 m 的缝」、
用户裁定的验收下限是「≥ 1.5 m 间隙」，而 `dense_map` 的最小缝在扣掉 99 环后是 0.246 m。

**所以本脚本对 `dense_map` 断言的是「诚实失败」而不是「必须成功」**：
规划器要么给出无碰撞路径，要么给出显式失败原因 —— 不允许静默返回穿障路径。

退出码：0 = PASS；1 = FAIL；2 = 环境错误（无 g++ / 无地图 / 无二进制）。
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
MAPS = os.path.join(ROOT, 'src', 'agc_sim', 'config', 'maps')
REPLAY = os.path.join(ROOT, 'install', 'agc_ground', 'lib', 'agc_ground', 'planner_replay')

# 规划层口径（与 map_adapter 的派生一致）
PLAN_RES = 0.5
EVID_RES = 0.25
EXTENT = 100.0
ORIGIN = -50.0
# ADR-0041 风险分档参数（与 perception.yaml 同值）
ROBOT_RADIUS_M = 0.6
INFLATION_RADIUS_M = 1.0
RISK_COST_SCALING = 3.0


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


def build_evidence_layer(map_name):
    """真实几何 → 0.25 m 证据层占据（1 = 占据）。"""
    import yaml
    path = os.path.join(MAPS, map_name + '.yaml')
    with open(path) as fh:
        obstacles = yaml.safe_load(fh)['obstacles']
    n = int(EXTENT / EVID_RES)
    grid = [[0] * n for _ in range(n)]
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
            for a in range(max(0, i0 - ri), min(n, i0 + ri + 1)):
                for b in range(max(0, j0 - ri), min(n, j0 + ri + 1)):
                    px = (a + 0.5) * EVID_RES + ORIGIN - x
                    py = (b + 0.5) * EVID_RES + ORIGIN - y
                    lx, ly = c * px - s * py, s * px + c * py
                    if shape == 'box':
                        hit = abs(lx) <= hx and abs(ly) <= hy
                    else:
                        hit = lx * lx + ly * ly <= hx * hx
                    if hit:
                        grid[b][a] = 1
    return grid


def _edt_meters(width, height, seeds):
    """到最近种子的米制距离（多源 Dijkstra，8 邻域）。"""
    import heapq
    INF = float('inf')
    dist = [[INF] * width for _ in range(height)]
    pq = []
    for j in range(height):
        for i in range(width):
            if seeds[j][i]:
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
                if not (0 <= ni < width and 0 <= nj < height):
                    continue
                nd = d + math.hypot(di, dj) * PLAN_RES
                if nd < dist[nj][ni]:
                    dist[nj][ni] = nd
                    heapq.heappush(pq, (nd, ni, nj))
    return dist


def build_planning_layer(map_name, unknown_outside=False):
    """证据层 0.25 m → 规划层 0.5 m（max-pool）+ ADR-0041 风险分档。

    `unknown_outside=True` 时把「离任何占据都很远」的格标成未知（模拟真实感知的
    有限覆盖）；默认 False = 全图已知（最宽松口径，用于验证算法本身可达）。
    """
    ev = build_evidence_layer(map_name)
    ne = len(ev)
    nw = ne // 2
    occ = [[0] * nw for _ in range(nw)]
    for j in range(nw):
        for i in range(nw):
            occ[j][i] = max(ev[2 * j][2 * i], ev[2 * j][2 * i + 1],
                            ev[2 * j + 1][2 * i], ev[2 * j + 1][2 * i + 1])
    dist = _edt_meters(nw, nw, occ)

    layer = [[0] * nw for _ in range(nw)]
    for j in range(nw):
        for i in range(nw):
            if unknown_outside:
                # 模拟感知覆盖：距己方机航迹超过可信半径的格 = 未知
                px = (i + 0.5) * PLAN_RES + ORIGIN
                py = (j + 0.5) * PLAN_RES + ORIGIN
                if not _within_trusted_radius(px, py):
                    layer[j][i] = -1
                    continue
            if occ[j][i]:
                layer[j][i] = 100
                continue
            d = dist[j][i]
            if d <= ROBOT_RADIUS_M:
                layer[j][i] = 99
            elif d <= INFLATION_RADIUS_M:
                span = max(1e-9, INFLATION_RADIUS_M - ROBOT_RADIUS_M)
                t = min(1.0, max(0.0, (d - ROBOT_RADIUS_M) / span))
                factor = math.exp(-RISK_COST_SCALING * t)
                layer[j][i] = min(98, max(1, int(round(98.0 * factor))))
            else:
                layer[j][i] = 0
    return layer, nw


# 己方机航迹（与 spawn_layout 的 dense_map 一致）：(-34,-2) 朝目标飞，停在 10.2 m 外。
_UAV_START = (-34.0, -2.0)
_UAV_STANDOFF = (-10.18, -0.6)
_TRUSTED_R = 28.28   # cam_h 13.88 m、focal 268.6、w 1152、edge_ratio 0.95


def _within_trusted_radius(px, py):
    ax, ay = _UAV_START
    bx, by = _UAV_STANDOFF
    vx, vy = bx - ax, by - ay
    den = vx * vx + vy * vy
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / den))
    cx, cy = ax + t * vx, ay + t * vy
    return math.hypot(px - cx, py - cy) <= _TRUSTED_R


def write_grid(path, layer, n):
    with open(path, 'w') as fh:
        fh.write('%g %g %g %d %d\n' % (PLAN_RES, ORIGIN, ORIGIN, n, n))
        fh.write(' '.join(str(v) for row in layer for v in row))
        fh.write('\n')


def run_planner(grid_path, start, goal, extra=()):
    """调生产规划器。返回 (ok, dict)。"""
    # 起终点追加到栅格文件末尾
    with open(grid_path, 'a') as fh:
        fh.write('%.6f %.6f %.6f\n' % (start[0], start[1], start[2]))
        fh.write('%.6f %.6f\n' % (goal[0], goal[1]))
    r = subprocess.run([REPLAY, grid_path] + list(extra), capture_output=True, text=True)
    out = {'ok': r.returncode == 0, 'raw': r.stdout, 'stderr': r.stderr}
    for line in r.stdout.splitlines():
        for tok in line.split():
            if '=' in tok:
                k, v = tok.split('=', 1)
                out.setdefault(k, v)
    return out


def parse_poses(raw):
    poses = []
    for line in raw.splitlines():
        if line.startswith('poses='):
            body = line[len('poses='):]
            if not body:
                continue
            for item in body.split(';'):
                parts = item.split(',')
                if len(parts) == 3:
                    poses.append((float(parts[0]), float(parts[1]), float(parts[2])))
    return poses


def check_path_clear(poses, layer, n):
    """用真实规划层复核：路径点的**车体 footprint** 不得碰 99/100。"""
    HL, HW, MARGIN = 0.5037, 0.28545, 0.3536
    hl, hw = HL + MARGIN, HW + MARGIN
    bad = []
    for (x, y, yaw) in poses:
        c, s = math.cos(yaw), math.sin(yaw)
        # 半格步长布点（与生产实现同口径）
        nu = max(1, int(math.ceil(2 * hl / (PLAN_RES * 0.5))))
        nv = max(1, int(math.ceil(2 * hw / (PLAN_RES * 0.5))))
        for iu in range(nu + 1):
            u = -hl + 2 * hl * iu / nu
            for iv in range(nv + 1):
                v = -hw + 2 * hw * iv / nv
                px = x + u * c - v * s
                py = y + u * s + v * c
                ix = int(math.floor((px - ORIGIN) / PLAN_RES))
                iy = int(math.floor((py - ORIGIN) / PLAN_RES))
                if not (0 <= ix < n and 0 <= iy < n):
                    bad.append((x, y, 'out_of_map'))
                    continue
                if layer[iy][ix] in (99, 100):
                    bad.append((x, y, layer[iy][ix]))
        if bad:
            break
    return bad


def _disc_reachable(layer, n, start, goal, radius):
    """纯几何连通性：半径 `radius` 的圆盘能否从 start 走到 goal（4 连通，0.5 m 格）。

    判据：车心所在格 + 半径覆盖的所有格都不得是 `99/100`。
    这是**不依赖规划器**的独立下界 —— 若它判不通，任何规划器都不该成功。
    """
    from collections import deque

    def passable(i, j):
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

    si = int((start[0] - ORIGIN) / PLAN_RES)
    sj = int((start[1] - ORIGIN) / PLAN_RES)
    gi = int((goal[0] - ORIGIN) / PLAN_RES)
    gj = int((goal[1] - ORIGIN) / PLAN_RES)
    if not (0 <= si < n and 0 <= sj < n and 0 <= gi < n and 0 <= gj < n):
        return False
    if not passable(si, sj) or not passable(gi, gj):
        return False
    seen = [[False] * n for _ in range(n)]
    seen[sj][si] = True
    q = deque([(si, sj)])
    while q:
        i, j = q.popleft()
        if i == gi and j == gj:
            return True
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if not (0 <= ni < n and 0 <= nj < n) or seen[nj][ni]:
                continue
            if not passable(ni, nj):
                continue
            seen[nj][ni] = True
            q.append((ni, nj))
    return False


def main():
    if not os.path.exists(REPLAY):
        print('FAIL: 找不到 %s（先 colcon build --packages-select agc_ground）' % REPLAY)
        return 2
    if not os.path.exists(MAPS):
        print('FAIL: 找不到地图目录 %s' % MAPS)
        return 2
    try:
        import yaml  # noqa: F401
    except ImportError:
        print('FAIL: 需要 PyYAML')
        return 2

    checks = []

    def add(name, ok, detail=''):
        checks.append({'name': name, 'pass': bool(ok), 'detail': detail})

    with tempfile.TemporaryDirectory() as td:
        # ---------- dense_map：诚实性（成功必须无碰撞；失败必须显式）----------
        dense, n = build_planning_layer('dense_map', unknown_outside=False)
        g1 = os.path.join(td, 'dense_known.txt')
        write_grid(g1, dense, n)
        r1 = run_planner(g1, (-40.0, -6.0, 0.0), (-2.5, 0.0))
        poses1 = parse_poses(r1['raw'])
        if poses1:
            bad = check_path_clear(poses1, dense, n)
            add('dense_success_is_collision_free', not bad,
                'outcome=%s first_bad=%s' % (r1.get('outcome'), bad[0] if bad else ''))
            end = poses1[-1]
            d_end = math.hypot(end[0] - (-2.5), end[1] - 0.0)
            add('dense_end_matches_goal', d_end <= 0.4, 'end_dist=%.3f' % d_end)
        else:
            # 失败是**预期**结局（见文件头）：断言它有明确原因、不是静默成功。
            add('dense_success_is_collision_free', True, 'no poses (explicit failure)')
            add('dense_failure_is_explicit',
                bool(r1.get('failure')) and r1.get('failure') != 'none',
                'failure=%s' % r1.get('failure'))
            add('dense_end_matches_goal', True, 'n/a (failed explicitly)')

        # ---------- dense_map：真实感知覆盖（未知区禁入）----------
        dense_u, nu = build_planning_layer('dense_map', unknown_outside=True)
        g2 = os.path.join(td, 'dense_unknown.txt')
        write_grid(g2, dense_u, nu)
        r2 = run_planner(g2, (-40.0, -6.0, 0.0), (-2.5, 0.0))
        # 两种可接受结局：成功（前沿+直连兜底），或显式失败。**不得**静默成功穿未知。
        if r2['ok']:
            poses2 = parse_poses(r2['raw'])
            bad2 = check_path_clear(poses2, dense_u, nu)
            add('dense_unknown_not_traversed', not bad2,
                'outcome=%s first_bad=%s' % (r2.get('outcome'), bad2[0] if bad2 else ''))
        else:
            add('dense_unknown_not_traversed', True,
                'explicit failure=%s' % r2.get('failure'))

        # ---------- 障碍全封死：必须显式失败 ----------
        blocked = [[100] * n for _ in range(n)]
        # 只留起点周围一小块
        sx = int((-40.0 - ORIGIN) / PLAN_RES)
        sy = int((-6.0 - ORIGIN) / PLAN_RES)
        for dj in range(-4, 5):
            for di in range(-4, 5):
                if 0 <= sx + di < n and 0 <= sy + dj < n:
                    blocked[sy + dj][sx + di] = 0
        g3 = os.path.join(td, 'blocked.txt')
        write_grid(g3, blocked, n)
        r3 = run_planner(g3, (-40.0, -6.0, 0.0), (-2.5, 0.0), extra=('--budget', '1.0'))
        add('blocked_fails_explicitly', not r3['ok'],
            'failure=%s' % r3.get('failure'))
        add('blocked_has_reason', bool(r3.get('failure')) and r3.get('failure') != 'none',
            'failure=%s' % r3.get('failure'))

        # ---------- 未知区起点：必须 start_not_free ----------
        unknown_start = [row[:] for row in dense]
        ix = int((0.0 - ORIGIN) / PLAN_RES)
        iy = int((0.0 - ORIGIN) / PLAN_RES)
        unknown_start[iy][ix] = -1
        g4 = os.path.join(td, 'unknown_start.txt')
        write_grid(g4, unknown_start, n)
        r4 = run_planner(g4, (0.0, 0.0, 0.0), (-2.5, 0.0))
        add('unknown_start_rejected', (not r4['ok']) and r4.get('failure') == 'start_not_free',
            'failure=%s' % r4.get('failure'))

        # ---------- yard：无障碍直达 ----------
        yard, ny = build_planning_layer('yard', unknown_outside=False)
        g5 = os.path.join(td, 'yard.txt')
        write_grid(g5, yard, ny)
        r5 = run_planner(g5, (-15.0, 1.0, 0.0), (-2.5, 0.0))
        add('yard_reachable', r5['ok'],
            'failure=%s detail=%s' % (r5.get('failure'), r5.get('detail', '')))
        poses5 = parse_poses(r5['raw'])
        if poses5:
            bad5 = check_path_clear(poses5, yard, ny)
            add('yard_path_clear', not bad5, 'first bad=%s' % (bad5[0] if bad5 else ''))

        # ---------- dense_map：独立几何判据（圆盘连通性）----------
        # 这一项**不依赖规划器**：它用纯几何回答「本车在这张图上能不能过」。
        # 若这里判「不可通行」，规划器失败就是**正确**行为。
        # **本项断言的是「规划器与几何事实一致」，不是「必须可通行」**：
        # 几何判通 ⇒ 规划器必须成功；几何判不通 ⇒ 规划器必须显式失败。
        # 这样它既守护了「不可通行时不许假装成功」，也守护了「可通行时不许假失败」。
        R_CAR = math.hypot(0.5037, 0.28545) + 0.3536   # 半对角 + margin = 0.933
        geo_ok = _disc_reachable(dense, n, (-40.0, -6.0), (-2.5, 0.0), R_CAR)
        planner_ok = bool(poses1)
        add('dense_planner_agrees_with_geometry', geo_ok == planner_ok,
            'geometry=%s planner=%s（几何判不通时规划失败是正确行为；'
            '几何判通时规划必须成功）'
            % ('passable' if geo_ok else 'blocked',
               'success' if planner_ok else 'failed(%s)' % r1.get('failure')))

        # ---------- yard s19：真正的绕障取证 ----------
        # s19 是 `yard` 上唯一「车位到目标之间确有障碍」的场景（34 m）。
        # 用 `--budget 12`：实测 3 s 不够（需要约 3.6 万节点扩展）。
        s19_start = (14.0, 4.0, math.pi)
        s19_goal = (14.0, -30.0)
        # **必须用独立文件**：`run_planner` 会把起终点追加到栅格文件末尾，
        # 复用 `g5` 会让第二次调用读到**上一次**的起终点（实测：s19 规划成了
        # yard 的 12.54 m 直达路径，而不是 34 m 绕行）。
        g7 = os.path.join(td, 'yard_s19.txt')
        write_grid(g7, yard, ny)
        r7 = run_planner(g7, s19_start, s19_goal, extra=('--budget', '12'))
        add('yard_s19_detour_reachable', r7['ok'],
            'failure=%s detail=%s' % (r7.get('failure'), (r7.get('detail') or '')[:60]))
        poses7 = parse_poses(r7['raw'])
        if poses7:
            bad7 = check_path_clear(poses7, yard, ny)
            add('yard_s19_path_clear', not bad7,
                'first bad=%s' % (bad7[0] if bad7 else ''))
            # 绕行证据：路径长度必须**明显长于**直线距离 34 m。
            length7 = float(r7.get('length') or 0.0)
            add('yard_s19_is_detour_not_straight', length7 > 36.0,
                'path_length=%.2f m vs straight=34.0 m' % length7)
            # 末端必须到 goal
            end7 = poses7[-1]
            d_end7 = math.hypot(end7[0] - s19_goal[0], end7[1] - s19_goal[1])
            add('yard_s19_end_matches_goal', d_end7 <= 0.4, 'end_dist=%.3f' % d_end7)
            # 接缝连续性：每点航向与到下一段方向一致（末点取末段切线）
            worst_seam = 0.0
            for i in range(len(poses7) - 1):
                dx = poses7[i + 1][0] - poses7[i][0]
                dy = poses7[i + 1][1] - poses7[i][1]
                seg_len = math.hypot(dx, dy)
                if seg_len < 1e-6:
                    continue   # 原地旋转点
                seg = math.atan2(dy, dx)
                jump = abs((poses7[i][2] - seg + math.pi) % (2 * math.pi) - math.pi)
                # 首点与旋转后第一点的跳变是「先转向」本身，不算缺陷
                prev_rot = (i > 0 and math.hypot(
                    poses7[i][0] - poses7[i - 1][0],
                    poses7[i][1] - poses7[i - 1][1]) < 1e-6)
                if i == 0 or prev_rot:
                    continue
                worst_seam = max(worst_seam, jump)
            add('yard_s19_seam_continuous', worst_seam <= 0.30,
                'worst mid-path heading jump=%.3f rad' % worst_seam)
        else:
            add('yard_s19_path_clear', False, 'no poses')
            add('yard_s19_is_detour_not_straight', False, 'no poses')
            add('yard_s19_end_matches_goal', False, 'no poses')
            add('yard_s19_seam_continuous', False, 'no poses')

        # ---------- sparse_map：可通行**正例**（ADR-0049）----------
        # 与 dense_map 构成正/负对照：唯一变量是障碍密度（4.0 m vs 2.645 m 中心距）。
        # dense_map 判「几何不可通行」→ 规划器失败是正确；sparse_map 判「可通行」
        # → 规划器**必须**成功。两者一起才说明规划器不是"一律失败"也不是"一律成功"。
        sparse, ns = build_planning_layer('sparse_map', unknown_outside=False)
        g8 = os.path.join(td, 'sparse.txt')
        write_grid(g8, sparse, ns)
        r8 = run_planner(g8, (-34.0, -6.0, 0.0), (-2.5, 0.0), extra=('--budget', '12'))
        add('sparse_map_reachable', r8['ok'],
            'failure=%s detail=%s' % (r8.get('failure'), (r8.get('detail') or '')[:60]))
        poses8 = parse_poses(r8['raw'])
        if poses8:
            bad8 = check_path_clear(poses8, sparse, ns)
            add('sparse_map_path_clear', not bad8,
                'first bad=%s' % (bad8[0] if bad8 else ''))
            end8 = poses8[-1]
            d_end8 = math.hypot(end8[0] - (-2.5), end8[1] - 0.0)
            add('sparse_map_end_matches_goal', d_end8 <= 0.4, 'end_dist=%.3f' % d_end8)
            # 正例必须是**绕障**而不是直线：路径长度 > 直线距离
            length8 = float(r8.get('length') or 0.0)
            straight8 = math.hypot(-2.5 - (-34.0), 0.0 - (-6.0))
            add('sparse_map_is_detour', length8 > straight8 * 1.02,
                'path=%.2f m vs straight=%.2f m' % (length8, straight8))
            # 曲率与离障必须达标（这是"可通行"的正面证据）
            kappa8 = float(r8.get('curvature') or 0.0)
            add('sparse_map_curvature_ok', kappa8 <= 1.05,
                'max_kappa=%.3f (limit 1.0 + 5%% 离散容差)' % kappa8)
            clr8 = float(r8.get('clearance') or 0.0)
            add('sparse_map_clearance_positive', clr8 >= 0.0,
                'clearance=%.3f m' % clr8)
        else:
            for nm in ('sparse_map_path_clear', 'sparse_map_end_matches_goal',
                       'sparse_map_is_detour', 'sparse_map_curvature_ok',
                       'sparse_map_clearance_positive'):
                add(nm, False, 'no poses')

        # ---------- 确定性：同输入两次逐位一致 ----------
        g6a = os.path.join(td, 'det_a.txt')
        g6b = os.path.join(td, 'det_b.txt')
        write_grid(g6a, dense, n)
        write_grid(g6b, dense, n)
        ra = run_planner(g6a, (-40.0, -6.0, 0.0), (-2.5, 0.0))
        rb = run_planner(g6b, (-40.0, -6.0, 0.0), (-2.5, 0.0))
        pa = parse_poses(ra['raw'])
        pb = parse_poses(rb['raw'])
        same = (len(pa) == len(pb) and
                all(abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9
                    for a, b in zip(pa, pb)))
        add('deterministic', same, 'points %d vs %d' % (len(pa), len(pb)))

    n_pass = sum(1 for c in checks if c['pass'])
    print('规划器 · 真实地图核查（ADR-0048）')
    print('=' * 74)
    for c in checks:
        print('  [%s] %-34s %s' % ('PASS' if c['pass'] else 'FAIL', c['name'], c['detail']))
    print('-' * 74)
    print('%d/%d 项通过' % (n_pass, len(checks)))
    if n_pass != len(checks):
        print('FAIL：规划器在真实地图上未达预期')
        return 1
    print('PASS：规划器在真实 dense_map / yard 上成立')
    return 0


if __name__ == '__main__':
    sys.exit(main())
