#!/usr/bin/env python3
"""地图 `dense_map`（小障碍高密度）的**只读核验器** —— 设计期迭代用，不写任何来源文件。

为什么单独一份（而不是直接跑 `check_scene_geometry.py`）：
 * 正式核查要跑三张地图 + 世界生成子进程，约 15 s；设计期要反复迭代候选布局；
 * 正式核查**没有**"8 字净空"与"实体互不重叠"两条断言（见技能 GATES.md），
   而这两条恰是高密度图最容易踩的；
 * 正式核查的 (i) 是**纯二维圆盘**口径，不含垂直门控 —— 本图全部构件 ≤3 m 而飞行 14 m，
   两者结论相差极大，必须在设计期同时看到两个数。

口径**逐项复刻** `tests/check_scene_geometry.py`（同一组 `world_map` / `checklib` 函数），
不一致就是"假绿"。用法：

    python3 tests/check_dense_map_layout.py [--map dense_map] [--json /tmp/dense.json]

退出码 0 = 全部设计闸门通过。
"""

import argparse
import importlib.util
import json
import math
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

# 复刻：直接 import 正式核查的实现，**不复制公式**（复制就会漂移）。
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import check_scene_geometry as C  # noqa: E402

# 地面 `collision_monitor` 三档（`agc_ground/config/ground.yaml`，ADR-0010 标定值）。
# 这里**只读**用于"车能否到达"的设计判断，不是第二来源：权威值在 ground.yaml。
CM_SAFETY_M = 4.0
CM_COLLISION_M = 2.0
CM_EMERGENCY_M = 1.0

# 最小间距下限（m）：ADR-0044 第二轮「再 +15%」= ADR-0037 的 2.3 × 1.15 = 2.645。
# 这是**验收口径**（用户裁定），改它须回 Leader 裁定并留痕，不得为了让某次布局变绿而放宽。
MIN_GAP_M = 2.645

# 8 字轨迹参数：权威值在 `agc_air/config/air.yaml` 的 `trajectory_tracker.traj`
# （本图不跑预设轨迹，但净空仍要算出来如实登记）。
FIG8_KEYS = ('rx', 'ry', 'center_x', 'center_y')


def _load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def _share(pkg):
    return C._share(pkg)


def _map_path(sim_share, world_map_mod, name):
    return world_map_mod.geometry_path(sim_share, name)[1]


def _part_poly_world(part, ob, wm):
    """复刻 `C._part_h_poly`（同一实现，不重写）。"""
    return C._part_h_poly(part, ob, wm)


def _poly_overlap(poly_a, poly_b):
    """逐图元 **SAT**（分离轴）—— 与技能 GATES.md (4) 同口径，不是包围盒相交。

 box/cylinder 近似多边形都是凸的，凸多边形的 SAT 只需检查两边法线。
    """
    for poly in (poly_a, poly_b):
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            axis = (-(y2 - y1), x2 - x1)
            norm = math.hypot(axis[0], axis[1])
            if norm < 1e-12:
                continue
            ax, ay = axis[0] / norm, axis[1] / norm
            pa = [ax * px + ay * py for px, py in poly_a]
            pb = [ax * px + ay * py for px, py in poly_b]
            if max(pa) < min(pb) - 1e-9 or max(pb) < min(pa) - 1e-9:
                return False
    return True


def _disk_r(ob, wm, ring):
    return C._disk_radius(ob, wm, ring)


def _ring_metrics(obs, wm, ring, target_xy):
    """环带可行率 + 最长连续可行弧（复刻正式核查 (i) 的采样口径：3600 角向）。"""
    ring_r = ring['target_min_dist'] + ring['target_margin'] + ring['extra']
    total = 3600
    blocked = [False] * total
    for k in range(total):
        ang = 2.0 * math.pi * k / total
        px = target_xy[0] + ring_r * math.cos(ang)
        py = target_xy[1] + ring_r * math.sin(ang)
        blocked[k] = any(_disk_r(o, wm, ring) > math.hypot(px - float(o['x']), py - float(o['y']))
                         for o in obs)
    cur = max_free = 0
    for k in range(2 * total):
        if not blocked[k % total]:
            cur += 1
            max_free = max(max_free, cur)
        else:
            cur = 0
    cur = max_blocked = 0
    for k in range(2 * total):
        if blocked[k % total]:
            cur += 1
            max_blocked = max(max_blocked, cur)
        else:
            cur = 0
    return {
        'ring_radius_m': round(ring_r, 4),
        'feasible_pct': round(100.0 * (total - sum(blocked)) / total, 2),
        'max_free_arc_deg': round(360.0 * max_free / total, 2),
        'max_blocked_arc_deg': round(360.0 * max_blocked / total, 2),
    }


def _ring_metrics_gated(obs, wm, ring, target_xy, gate_z, c_clear):
    """**门控口径**的环带指标：先按 `z_gate ≥ z_top + c_clear` 移除障碍，再算环带。

 与 `safety_shield.cpp` 的 `deriveRings` 同判据（平飞 ⇒ z_gate = 当前高度）。
 这条口径是**运行期真实生效**的那条；二维口径保留作登记（ADR-0036 (c)）。
    """
    alive = []
    gated = 0
    for o in obs:
        if gate_z >= wm.obstacle_z_top(o) + c_clear:
            gated += 1
            continue
        alive.append(o)
    m = _ring_metrics(alive, wm, ring, target_xy)
    m['gated_off'] = gated
    m['alive'] = len(alive)
    return m


def _coverage_pct(obs, wa, wm, res=0.2):
    return C._union_coverage_pct(obs, wa, wm, res=res)


def _spawn_clearance(obs, wm, points):
    """逐出生点到**实体足迹**的净空（与核查 (g) 同口径）。"""
    out = {}
    for name, (px, py) in points.items():
        best = min(C._obb_clearance(px, py, o, wm) - C._footprint_extent(o, wm)
                   for o in obs)
        worst = min(obs, key=lambda o: C._obb_clearance(px, py, o, wm)
                    - C._footprint_extent(o, wm))
        out[name] = {'clearance_m': round(best, 3), 'nearest': worst['id']}
    return out


def _fig8_clearance(obs, wm, ring, traj):
    """8 字轨迹对**安全层膨胀圆盘**的最小净空（技能 GATES.md (1)，正式核查**没有**此断言）。

 x(θ) = cx + rx·sinθ；y(θ) = cy + ry·sinθ·cosθ
 判据：min_θ [‖p(θ) − anchor‖ − disk_r] ≥ 0
    """
    rx, ry = float(traj['rx']), float(traj['ry'])
    cx, cy = float(traj['center_x']), float(traj['center_y'])
    worst = (float('inf'), None)
    steps = 7200
    for k in range(steps):
        th = 2.0 * math.pi * k / steps
        px = cx + rx * math.sin(th)
        py = cy + ry * math.sin(th) * math.cos(th)
        for o in obs:
            d = math.hypot(px - float(o['x']), py - float(o['y'])) - _disk_r(o, wm, ring)
            if d < worst[0]:
                worst = (d, o['id'])
    return {'min_clearance_m': round(worst[0], 3), 'tightest': worst[1]}


def _car_reaches_goal(obs, wm, car, goal, stop_m=CM_COLLISION_M):
    """车沿**直连**路径（占位规划器的真实行为）行进，第一次进入 `stop_m` 档的位置。

 返回 None 表示全程未进入该档（车能开到 goal）；否则返回 (s, x, y, 最近实体, 净空)。
 口径：车中心到**实体足迹**的距离（与 `collision_monitor` 的 scan 判据同量级近似）。
    """
    best = None
    for t in range(0, 1001):
        s = t / 1000.0
        px = car[0] + (goal[0] - car[0]) * s
        py = car[1] + (goal[1] - car[1]) * s
        for o in obs:
            d = C._obb_clearance(px, py, o, wm)
            if d < stop_m:
                return {'s': round(s, 3), 'x': round(px, 2), 'y': round(py, 2),
                        'nearest': o['id'], 'clearance_m': round(d, 3)}
        if best is None:
            best = s
    return None


def _density_metrics(obs, wm, wa):
    """高密度量化（"高密度"此前**没有**任何可判定口径，ADR-0036 (e) 定口径）。"""
    parts = [(pt, o) for o in obs for pt in wm.obstacle_parts(o)]
    n = len(obs)
    area = float(wa['size_x']) * float(wa['size_y'])
    xs = [float(o['x']) for o in obs]
    ys = [float(o['y']) for o in obs]
    # 最近邻（锚点间距；n 大时用网格加速，避免 O(n²) 拖慢设计迭代）
    cell = 4.0
    grid = {}
    for o in obs:
        grid.setdefault((int(math.floor(float(o['x']) / cell)),
                         int(math.floor(float(o['y']) / cell))), []).append(o)
    nn = []
    for o in obs:
        ox, oy = float(o['x']), float(o['y'])
        best = float('inf')
        cx, cy = int(math.floor(ox / cell)), int(math.floor(oy / cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for p in grid.get((cx + dx, cy + dy), ()):
                    if p is o:
                        continue
                    d = math.hypot(ox - float(p['x']), oy - float(p['y']))
                    if d < best:
                        best = d
        nn.append(best)
    tops = [wm.obstacle_z_top(o) for o in obs]
    # 密集区：包含 ≥90% 实体的最小轴对齐方形（以实体质心为中心）
    mcx = sum(xs) / n
    mcy = sum(ys) / n
    half = 0.0
    for o in obs:
        half = max(half, abs(float(o['x']) - mcx), abs(float(o['y']) - mcy))
    return {
        'n_obstacles': n,
        'n_parts': len(parts),
        'obstacles_per_1000m2': round(1000.0 * n / area, 2),
        'nn_min_m': round(min(nn), 3),
        'nn_median_m': round(sorted(nn)[len(nn) // 2], 3),
        'nn_max_m': round(max(nn), 3),
        'core_half_extent_m': round(half, 2),
        'core_density_per_1000m2': round(1000.0 * n / ((2 * half) ** 2), 2),
        'z_top_max_m': round(max(tops), 3),
        'z_top_min_m': round(min(tops), 3),
        'footprint_side_min_m': round(min(
            min(float(v) for v in pt['size'][:2]) for pt, _ in parts), 3),
        'footprint_side_max_m': round(max(
            max(float(v) for v in pt['size'][:2]) for pt, _ in parts), 3),
        'composite_count': sum(1 for o in obs if wm.is_composite(o)),
        'shapes': sorted({wm.obstacle_shape(pt) for pt, _ in parts}),
        'finishes': sorted({f for f in (wm.part_finish(pt) for pt, _ in parts) if f}),
    }


def check_map(map_name, sim_share=None, json_out=None):
    sim_share = sim_share or _share('agc_sim')
    air_share = _share('agc_air')
    task_share = _share('agc_task')
    wm = C._resolve_maps(sim_share)
    geom_path = _map_path(sim_share, wm, map_name)
    geometry = _load_yaml(geom_path)
    obstacles = geometry.get('obstacles') or []
    wa = geometry.get('work_area') or {}
    ring = C._air_ring_params(air_share)
    air_cfg = _load_yaml(os.path.join(air_share, 'config', 'air.yaml'))
    traj = air_cfg['trajectory_tracker']['ros__parameters']['traj']
    fa = geometry.get('flight_altitude') or {}
    c_clear = float(fa['own_clearance_min_m'])
    gate_z = float(fa['own_track_m'])

    # 出生位：按地图派生（ADR-0036），与 main.launch.py 同一条解析路径。
    sys.path.insert(0, os.path.join(task_share, 'launch'))
    import scene_spawn  # noqa: E402
    layout = scene_spawn.load_spawn_layout(task_share, world_map=map_name)
    car = (layout['car']['x'], layout['car']['y'])
    target = (layout['target']['x'], layout['target']['y'])
    own = (layout['own_uav']['x'], layout['own_uav']['y'])
    off = layout['goal_offset_m']
    goal = (target[0] + off['dx'], target[1] + off['dy'])

    res = {'map': map_name, 'source': geom_path, 'spawn': {
        'car': list(car), 'target': list(target), 'own_uav': list(own), 'goal': list(goal)}}

    # ---- (A) schema（与正式核查 (a) 同口径）----
    ids = [o['id'] for o in obstacles]
    schema_ok = True
    schema_err = []
    for o in obstacles:
        try:
            for pt in wm.obstacle_parts(o):
                wm.obstacle_shape(pt)
                wm.obstacle_size(pt, pt)
                wm.part_finish(pt)
            wm.obstacle_finish(o)
            rad = wm.obstacle_safety_radius(o)
            if not (math.isfinite(rad) and rad > 0.0):
                raise RuntimeError('safety_radius 非法')
        except RuntimeError as exc:
            schema_ok = False
            schema_err.append('%s: %s' % (o.get('id'), exc))
    res['A_schema'] = {
        'declared_map_matches': (geometry.get('map') or '') == map_name,
        'work_area_keys_ok': all(k in wa for k in (
            'resolution', 'size_x', 'size_y', 'origin_x', 'origin_y')),
        'ids_unique': len(set(ids)) == len(ids),
        'all_schema_ok': schema_ok,
        'errors': schema_err[:5],
    }
    res['A_schema']['pass'] = all(v for k, v in res['A_schema'].items()
                                  if isinstance(v, bool))

    # ---- (B) 实体互不重叠（逐图元 SAT；正式核查**没有**这条）----
    parts_all = [(pt, o) for o in obstacles for pt in wm.obstacle_parts(o)]
    polys = [(_part_poly_world(pt, o, wm), o['id']) for pt, o in parts_all]
    # 网格加速：同一 4 m 格及邻格才可能重叠
    cell = 4.0
    grid = {}
    for idx, (poly, _oid) in enumerate(polys):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        cx, cy = int(math.floor(sum(xs) / len(xs) / cell)), int(
            math.floor(sum(ys) / len(ys) / cell))
        grid.setdefault((cx, cy), []).append(idx)
    overlaps = []
    seen = set()
    for (cx, cy), idxs in grid.items():
        cand = list(idxs)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    cand.extend(grid.get((cx + dx, cy + dy), ()))
        for i in idxs:
            for j in cand:
                if j <= i:
                    continue
                key = (i, j)
                if key in seen:
                    continue
                seen.add(key)
                # 同一实体的多个 part 之间不算重叠（复合体内部堆叠是合法的）
                if polys[i][1] == polys[j][1]:
                    continue
                if _poly_overlap(polys[i][0], polys[j][0]):
                    overlaps.append([polys[i][1], polys[j][1]])
    res['B_no_overlap_sat'] = {'overlap_pairs': len(overlaps),
                              'examples': overlaps[:5],
                              'pass': not overlaps}

    # ---- (C) 出生净空（复刻正式核查 (g)）----
    spawn = _spawn_clearance(obstacles, wm, {'car': car, 'target': target, 'own_uav': own})
    d_car_target = math.hypot(car[0] - target[0], car[1] - target[1])
    d_own_target = math.hypot(own[0] - target[0], own[1] - target[1])
    d_car_own = math.hypot(car[0] - own[0], car[1] - own[1])
    res['C_spawn_clearance'] = {
        'per_entity': spawn,
        'all_positive': all(v['clearance_m'] > 0.0 for v in spawn.values()),
        'car_target_m': round(d_car_target, 3),
        'own_target_m': round(d_own_target, 3),
        'car_own_m': round(d_car_own, 3),
        'design_goals_met': (d_car_target >= 30.0 and d_own_target >= 25.0
                             and 3.0 <= d_car_own <= 8.0),
    }
    res['C_spawn_clearance']['pass'] = (res['C_spawn_clearance']['all_positive']
                                        and res['C_spawn_clearance']['design_goals_met'])

    # ---- (D) 地面激光可见性（复刻正式核查 (h)）----
    invisible = []
    for o in obstacles:
        vis = False
        for pt in wm.obstacle_parts(o):
            size = [float(v) for v in pt['size']]
            z_center = (float(o['z']) + float(pt['z'])) if wm.is_composite(o) else float(o['z'])
            if z_center - size[2] / 2.0 <= C.LASER_PLANE_Z_M <= z_center + size[2] / 2.0:
                vis = True
                break
        if not vis:
            invisible.append(o['id'])
    res['D_laser_visibility'] = {'invisible': invisible[:5], 'n_invisible': len(invisible),
                                'pass': not invisible}

    # ---- (E) 环带：二维口径 vs **门控口径**（ADR-0036 (c)）----
    ring_2d = _ring_metrics(obstacles, wm, ring, target)
    ring_gated = _ring_metrics_gated(obstacles, wm, ring, target, gate_z, c_clear)
    res['E_ring'] = {
        'two_d': ring_2d,
        'gated': ring_gated,
        'gate_z_m': gate_z,
        'c_clear_m': c_clear,
        # pass 判据 = **门控口径**（运行期真实生效的那条）；二维口径只登记。
        'pass': ring_gated['feasible_pct'] > 0.0 and ring_gated['max_free_arc_deg'] >= 90.0,
    }

    # ---- (F) 8 字净空（技能 GATES.md (1)；正式核查**没有**此断言）----
    fig8 = _fig8_clearance(obstacles, wm, ring, traj)
    res['F_fig8_clearance'] = {
        **fig8, 'traj': {k: traj[k] for k in FIG8_KEYS},
        # 负值只登记、不判 FAIL（技能明确：负值是设计信号，不是失败判决）。
        'note': '负值 = 名义参考轨迹压到静态膨胀圆盘；本图不跑预设轨迹，只登记',
    }

    # ---- (G) 覆盖率（并集口径，复刻正式核查 (o) 的算法）----
    cov = _coverage_pct(obstacles, wa, wm)
    res['G_coverage_union'] = {'pct': round(cov, 2), 'res_m': 0.2}

    # ---- (H) 车能否到达任务目标（地面 `collision_monitor` 口径）----
    blocked_at = _car_reaches_goal(obstacles, wm, car, goal)
    res['H_car_reaches_goal'] = {
        'goal': [round(goal[0], 3), round(goal[1], 3)],
        'goal_to_target_m': round(math.hypot(goal[0] - target[0], goal[1] - target[1]), 3),
        'collision_stop_m': CM_COLLISION_M,
        'first_blocked': blocked_at,
        'reaches_goal': blocked_at is None,
        # 这是**设计意图**而非缺陷：本图不留走廊（用户 2026-11-10 裁定）。
        'intended_unreachable': True,
    }

    # ---- (I) 高密度量化（ADR-0036 (e) 定的新口径）----
    res['I_density'] = _density_metrics(obstacles, wm, wa)

    # ---- (J) 高度上限（用户 2026-11-10 裁定「不要超过 3 m」）----
    tops = [wm.obstacle_z_top(o) for o in obstacles]
    res['J_height_cap'] = {
        'cap_m': 3.0,
        'z_top_max_m': round(max(tops), 3),
        'pass': max(tops) <= 3.0 + 1e-9,
    }

    # ---- (K) 门控口径的覆盖说明（能力收窄，如实登记）----
    res['K_gate_coverage'] = {
        'gate_z_m': gate_z,
        'c_clear_m': c_clear,
        'n_gated_off': ring_gated['gated_off'],
        'n_total': len(obstacles),
        'all_gated': ring_gated['gated_off'] == len(obstacles),
        'implication': ('全部障碍被垂直门控移除 ⇒ 本图不提供空中避障证据；'
                        '环带 (i) 在门控口径下必然 100%'),
    }

    # ---- (L) 地面样式（ADR-0037：用户「地板换成纯色就行」）----
    # 判据 = 声明了 `plain`，且**实际剥离生效**（走 world_bringup 的真实注入路径，
    # 不是只读 yaml 字段就宣称生效）。
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        '_wb_for_ground', os.path.join(ROOT, 'src', 'agc_sim', 'launch',
                                       'world_bringup.launch.py'))
    _wb = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_wb)
    style = _wb._ground_style(geometry)
    _tmp = os.path.join('/tmp', 'dense_ground_probe.sdf')
    _wb._inject_static_obstacles(
        os.path.join(sim_share, 'worlds', 'agc_world.sdf'), _tmp, geometry)
    _txt = open(_tmp, encoding='utf-8').read()
    import re as _re
    _names = _re.findall(r'<model name="([^"]+)"', _txt)
    _decor = [n for n in _names if any(n.startswith(p) for p in _wb.GROUND_DECOR_PREFIXES)]
    res['L_ground_style'] = {
        'declared': style,
        'decor_models_after_inject': len(_decor),
        'ground_plane_present': 'ground_plane' in _names,
        'obstacles_injected': sum(1 for o in obstacles if o['id'] in _names),
        # plain ⇒ 装饰族必须全部消失，但基层地面必须还在（否则没有可跑的地面碰撞）。
        'pass': style == 'plain' and not _decor and 'ground_plane' in _names,
    }
    os.remove(_tmp)

    # ---- (M) 随机性 + 间距下限（ADR-0037 / ADR-0044）----
    # 用户要求「随机生成」+「间距加宽约 15%」（2026-11-10，首轮；2026-11-12 再 +15%）。
    # 随机本身不可断言，可断言的是：
    # ① 最小间距 ≥ 2.645 m（第二轮的落点 = 首轮 2.3 × 1.15）；② 位置不是规则栅格。
    dens = res['I_density']
    xs = sorted({round(float(o['x']), 3) for o in obstacles})
    ys = sorted({round(float(o['y']), 3) for o in obstacles})
    # 规则栅格会有大量重复的 x / y 值；随机撒点几乎每行都不同。
    # 判据：唯一 x 值占比 ≥ 80%（若只有几十条竖线就是栅格）。
    ux = len(xs) / float(len(obstacles))
    uy = len(ys) / float(len(obstacles))
    res['M_random_and_gap'] = {
        'min_gap_m': dens['nn_min_m'],
        'min_gap_ge_2_645m': dens['nn_min_m'] >= MIN_GAP_M - 1e-3,  # 1 mm 容差：3 位小数表示精度
        'nn_median_m': dens['nn_median_m'],
        'unique_x_ratio': round(ux, 3),
        'unique_y_ratio': round(uy, 3),
        'not_a_grid': ux >= 0.8 and uy >= 0.8,
        'pass': dens['nn_min_m'] >= MIN_GAP_M - 1e-3 and ux >= 0.8 and uy >= 0.8,
    }

    gates = ('A_schema', 'B_no_overlap_sat', 'C_spawn_clearance', 'D_laser_visibility',
             'E_ring', 'J_height_cap', 'L_ground_style', 'M_random_and_gap')
    res['overall_pass'] = all(res[g].get('pass') for g in gates)
    res['gates_judged'] = list(gates)

    if json_out:
        os.makedirs(os.path.dirname(json_out) or '.', exist_ok=True)
        with open(json_out, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--map', default='dense_map')
    ap.add_argument('--json', default=None)
    args = ap.parse_args()
    res = check_map(args.map, json_out=args.json)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print('\n%s (map=%s)' % ('PASS' if res['overall_pass'] else 'FAIL', args.map))
    return 0 if res['overall_pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
