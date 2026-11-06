#!/usr/bin/env python3
"""round-7 A1/A3 高度体系量化脚本（**只读**，不启动任何仿真）。

用途：给定三张地图的几何真源，算出
  * 全图最高障碍 H_max；
  * 与 C1 真八字足迹（rx=15 → x±15、ry=9 → y±4.5）**相交**的最高障碍；
  * 与目标机待机环带（以目标 spawn (15,−2) 为心、半径 = standoff safe_max 11.2 m）相交的最高障碍；
  * 与空中安全层圆盘相交的最高障碍（margin = 矩形距离 − safety_radius）；
  * 感知几何约束：range_max=12 m / vfov=70° / 停止点 10.2 m 下的 |dz| 上限。

真源一律经 `src/agc_sim/launch/world_map.py` 解析（单一清单，不另写文件名表）；
几何用各 part 的**水平 AABB**（对 yaw 取 |cos|/|sin| 的保守外扩），与 `obstacle_safety_radius`
同源。本脚本**不**改任何配置，只读并打印 JSON。

用法：python3 height_survey.py [--json]
退出码 0 = 正常；非 0 = 真源读取失败。
"""
import json
import math
import os
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'src', 'agc_sim', 'launch'))
import world_map as wm  # noqa: E402

GEOM_DIR = os.path.join(ROOT, 'src', 'agc_sim', 'config')

# ---- 从真源配置读出的常量（不在此重复定义数值真源，仅作推导输入）----
FIG8_RX, FIG8_RY = 15.0, 9.0          # air.yaml traj.rx / traj.ry（= C1）
FIG8_H = 2.5                          # air.yaml traj.height（= C1 几何高度）
OWN_TAKEOFF = 2.5                     # air.yaml takeoff_altitude_m
OWN_TRACK = 2.5                       # air.yaml standoff_follower.height
TARGET_CRUISE = 2.0                   # w6_base.yaml intruder_driver.cruise_alt_m
SAFE_MIN, SAFE_MAX, HYST = 8.0, 11.2, 1.0   # air.yaml standoff_follower
STOP_POINT = SAFE_MAX - HYST          # 10.2 m —— standoff 的「停止趋近点」
RANGE_MAX = 12.0                      # perception_sensors.yaml air_eo_front.range_max_m
VFOV = 70.0                           # perception_sensors.yaml air_eo_front.vfov_deg
HFOV = 100.0
TARGET_SPAWN = (15.0, -2.0)           # spawn_layout.yaml target.x/y
# s02 实测 GT 起止（162101 probe 的 gt_target_samples 首末），用于"目标会平移"形态的包络
TARGET_PATH_S02 = ((15.0, -2.0), (30.10, -2.14))


def envelope_h_max(name, path=None, radius=SAFE_MAX, fig8=False):
    """**作业包络内**的最高障碍顶 —— 定高真正该用的量（不是全图 H_max）。

    包络语义（几何**精确**，不用外扩矩形近似）：

    * `fig8=True`：己方机水平位置 = **八字足迹本身**（流程验证场景），不再外扩；
    * 给了 `path=(A,B)`：目标在 A→B 线段上移动 ⇒ 己方机位置 = 该线段 ⊕ `radius`（胶囊）；
    * 缺省（静止目标）：己方机位置 = 以目标为心、半径 ≤ `radius` 的圆盘。

    （不用"点/线段外扩 radius 的 AABB"——那会把角上 11.2·√2 = 15.8 m 处的障碍也算进来，过度保守。）
    返回 `(ztop, id, 最近水平距离)`。
    """
    doc = yaml.safe_load(open(os.path.join(GEOM_DIR, wm.MAP_GEOMETRY_FILES[name])))
    fig8_box = (-FIG8_RX, FIG8_RX, -FIG8_RY / 2.0, FIG8_RY / 2.0, 0.0)
    if path is None:
        a, b = TARGET_SPAWN, TARGET_SPAWN
    else:
        a, b = tuple(path[0]), tuple(path[1])
    best = (0.0, None, None)
    for ob in doc['obstacles']:
        r = rect_of(ob)
        if fig8:
            d = rect_rect_dist(r, fig8_box)
        else:
            d = rect_segment_dist(r, a, b)
        if d <= radius and r[4] > best[0]:
            best = (round(r[4], 3), ob['id'], round(d, 3))
    return best


def rect_of(ob):
    """实体（含复合）的水平 AABB + 顶高（世界 ENU z，m）。复合模型叠加锚点 x/y。"""
    ax = float(ob.get('x') or 0.0)
    ay = float(ob.get('y') or 0.0)
    parts = wm.obstacle_parts(ob) if wm.is_composite(ob) else [ob]
    xs, ys, ztop = [], [], 0.0
    for p in parts:
        size = wm.obstacle_size(p, p)
        cx = float(p.get('x') or 0.0) + ax
        cy = float(p.get('y') or 0.0) + ay
        cz = float(p.get('z') or 0.0)
        yaw = float(p.get('yaw') or 0.0)
        if wm.obstacle_shape(p) in ('cylinder', 'sphere'):
            hx = hy = size[0]
        else:
            hx, hy = size[0] / 2.0, size[1] / 2.0
        c, s = abs(math.cos(yaw)), abs(math.sin(yaw))
        ex, ey = hx * c + hy * s, hx * s + hy * c
        xs += [cx - ex, cx + ex]
        ys += [cy - ey, cy + ey]
        ztop = max(ztop, cz + size[2] / 2.0)
    return (min(xs), max(xs), min(ys), max(ys), ztop)


def rect_rect_dist(a, b):
    dx = max(a[0] - b[1], b[0] - a[1], 0.0)
    dy = max(a[2] - b[3], b[2] - a[3], 0.0)
    return math.hypot(dx, dy)


def point_rect_dist(px, py, r):
    dx = max(r[0] - px, 0.0, px - r[1])
    dy = max(r[2] - py, 0.0, py - r[3])
    return math.hypot(dx, dy)


def point_seg_dist(px, py, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def rect_segment_dist(r, a, b):
    """矩形到**线段**的水平最短距离（矩形外→线段，或线段穿入矩形时为 0）。

    精确性做法：把矩形按到线段的"切比雪夫"判据分解——先判线段是否与矩形相交
    （Liang–Barsky 裁剪），相交即 0；否则取「线段两端点到矩形」与「矩形四角到线段」
    两类候选的最小值。这覆盖了二者不相交时的全部最短距离情形。
    """
    # 1) 线段是否与矩形相交（Liang–Barsky）
    x0, y0 = a
    dx, dy = b[0] - x0, b[1] - y0
    t_enter, t_exit = 0.0, 1.0
    inside = True
    for p, q in ((-dx, x0 - r[0]), (dx, r[1] - x0), (-dy, y0 - r[2]), (dy, r[3] - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                inside = False
                break
        else:
            t = q / p
            if p < 0:
                t_enter = max(t_enter, t)
            else:
                t_exit = min(t_exit, t)
            if t_enter > t_exit:
                inside = False
                break
    if inside:
        return 0.0
    # 2) 不相交：候选 = 端点到矩形、四角到线段
    cands = [point_rect_dist(a[0], a[1], r), point_rect_dist(b[0], b[1], r)]
    for cx, cy in ((r[0], r[2]), (r[0], r[3]), (r[1], r[2]), (r[1], r[3])):
        cands.append(point_seg_dist(cx, cy, a, b))
    return min(cands)


def survey_map(name):
    path = os.path.join(GEOM_DIR, wm.MAP_GEOMETRY_FILES[name])
    doc = yaml.safe_load(open(path))
    fig8_box = (-FIG8_RX, FIG8_RX, -FIG8_RY / 2.0, FIG8_RY / 2.0)
    rows = []
    for ob in doc['obstacles']:
        r = rect_of(ob)
        sr = float(wm.obstacle_safety_radius(ob))
        rows.append({
            'id': ob['id'],
            'ztop_m': round(r[4], 3),
            'dist_to_fig8_m': round(rect_rect_dist(r, fig8_box), 3),
            'dist_to_target_m': round(point_rect_dist(TARGET_SPAWN[0], TARGET_SPAWN[1], r),
                                      3),
            'safety_radius_m': round(sr, 3),
            'shield_margin_m': round(rect_rect_dist(r, fig8_box) - sr, 3),
        })
    by_top = sorted(rows, key=lambda x: -x['ztop_m'])
    in_fig8 = [x for x in rows if x['dist_to_fig8_m'] <= 0.0]
    in_ring = [x for x in rows if x['dist_to_target_m'] <= SAFE_MAX]
    shield_hit = [x for x in rows if x['shield_margin_m'] < 0.0]
    env_static = envelope_h_max(name)
    env_moving = envelope_h_max(name, path=TARGET_PATH_S02)
    # 八字足迹：己方机**就在**这条曲线上，不再外扩 radius（故 radius=0，判相交即命中）
    env_fig8 = envelope_h_max(name, radius=0.0, fig8=True)
    return {
        'map': name,
        'geometry_file': wm.MAP_GEOMETRY_FILES[name],
        'n_entities': len(rows),
        'h_max_full_map_m': by_top[0]['ztop_m'],
        'h_max_full_map_id': by_top[0]['id'],
        # ↓ 定高真正该用的量：**作业包络内**最高障碍
        'h_max_env_static_m': env_static[0],
        'h_max_env_static_id': env_static[1],
        'h_max_env_static_dist_m': env_static[2],
        'h_max_env_moving_m': env_moving[0],
        'h_max_env_moving_id': env_moving[1],
        'h_max_env_moving_dist_m': env_moving[2],
        'h_max_env_active_m': max(env_static[0], env_moving[0]),
        'h_max_env_with_fig8_m': env_fig8[0],
        'h_max_env_with_fig8_id': env_fig8[1],
        'h_max_in_fig8_footprint_m': (max(x['ztop_m'] for x in in_fig8) if in_fig8 else 0.0),
        'n_in_fig8_footprint': len(in_fig8),
        'h_max_in_target_ring_m': (max(x['ztop_m'] for x in in_ring) if in_ring else 0.0),
        'n_in_target_ring': len(in_ring),
        'target_ring_radius_m': SAFE_MAX,
        'n_shield_disk_overlaps_fig8': len(shield_hit),
        'top10_tallest': by_top[:10],
        'nearest_to_target': sorted(rows, key=lambda x: x['dist_to_target_m'])[:5],
    }


def perception_table():
    """高度差 dz 与感知几何的关系（range 球 + vfov）。"""
    def budget(dz):
        return math.sqrt(max(0.0, RANGE_MAX ** 2 - dz ** 2))

    half_v = VFOV / 2.0
    out = {
        'inputs': {'range_max_m': RANGE_MAX, 'vfov_deg': VFOV, 'hfov_deg': HFOV,
                   'stop_point_m': STOP_POINT},
        # 目标保持 cruise=2.0 m，问己方机可以多高仍能让停止点落在量程球内/视场内
        'dz_limit_range_sphere_m': round(math.sqrt(RANGE_MAX ** 2 - STOP_POINT ** 2), 3),
        'dz_limit_vfov_m': round(STOP_POINT * math.tan(math.radians(half_v)), 3),
        'own_height_upper_from_range_m': round(
            TARGET_CRUISE + math.sqrt(RANGE_MAX ** 2 - STOP_POINT ** 2), 3),
        'own_height_upper_from_vfov_m': round(
            TARGET_CRUISE + STOP_POINT * math.tan(math.radians(half_v)), 3),
        # 水平预算 √(R²−dz²) 作为 dz 的函数（dz = 己方跟踪高度 − 目标高度）
        'horizontal_budget_by_dz': [
            {'dz_m': dz, 'horizontal_budget_m': round(budget(dz), 3),
             'stop_point_fits': budget(dz) >= STOP_POINT,
             'elevation_deg_at_stop_point': round(math.degrees(math.atan2(dz, STOP_POINT)), 2),
             'vfov_ok': abs(math.degrees(math.atan2(dz, STOP_POINT))) <= half_v}
            for dz in (-10.0, -6.0, -3.5, -2.0, -1.5, -0.5, 0.0, 0.5, 1.5, 2.5, 4.0, 6.0, 10.0)
        ],
        # 两机同步抬升、dz 不变时，感知几何**不变**（这是本文件的关键结论）
        'co_raise_invariant': {
            'note': '己方与目标同步等量抬升 ⇒ dz 不变 ⇒ range 球水平预算与视线俯仰角不变；'
                    '变化的只有**绝对高度**（越障净空）与**目标机的可捕获高度包络**。',
            'examples': [
                {'h_target': ht, 'h_own': ht + (OWN_TRACK - TARGET_CRUISE),
                 'dz': round(OWN_TRACK - TARGET_CRUISE, 3),
                 'horizontal_budget_m': round(budget(OWN_TRACK - TARGET_CRUISE), 3)}
                for ht in (2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
            ],
        },
    }
    return out


def main():
    res = {
        'note': '只读量化；数值均由真源 + 上式推导，不含任何实测（本轮 T1=0、默认不跑仿真）',
        'constants_from_source': {
            'fig8': {'rx': FIG8_RX, 'ry': FIG8_RY, 'h': FIG8_H, 'source': 'air.yaml traj (C1)'},
            'own_takeoff_altitude_m': OWN_TAKEOFF,
            'own_track_height_m': OWN_TRACK,
            'target_cruise_alt_m': TARGET_CRUISE,
            'standoff': {'safe_min': SAFE_MIN, 'safe_max': SAFE_MAX, 'hysteresis': HYST,
                         'stop_point_m': STOP_POINT},
        },
        'maps': [survey_map(n) for n in wm.WORLD_MAPS],
        'perception_geometry': perception_table(),
    }
    text = json.dumps(res, ensure_ascii=False, indent=1)
    if '--json' in sys.argv:
        print(text)
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
