#!/usr/bin/env python3
"""安全层三档整链场景的**几何可行性闸门**（纯静态，秒级，不启仿真）。

## 为什么需要这一层

`tests/check_safety_tiers_escape.py` 只在 `backend:=full` 上**取证**：它读
`/agc/ground/safety_status`，证明安全层真的定过档。但它跑一次要两分钟、且依赖相机把障碍
真的画进 `/agc/map`。**如果场景几何本身不成立**（障碍太小 / 相机太低 / goal 不在障碍另一侧），
那次取证会以"全程 PASS"安静地失败 —— 分不清"安全层不需要介入"与"障碍根本没进地图"。

2026-11-13 的实测教训：`s11` 用 `minimal` 的 `pole_1`（0.3 m 见方、顶面 3.0 m），
低飞时相机只比柱顶高 0.39 m，柱顶在画幅里只有 24 px，而门限是 20 px —— 余量 5 px，
实测拿不到连通域（`障碍像素 0`）。**这是几何不合，不是配置错误**，调参绕不过去。

故本闸门在**开仿真之前**用纯算术回答四个问题（任一不过即 FAIL）：

| # | 判据 | 依据 |
|---|---|---|
| a | 场景已登记且 `world_map` 与其**几何语义**一致（本场景必须 `yard`） | 场景表是唯一登记处 |
| b | **相机高度**：己方机跟踪高度 + 相机安装高 − 障碍顶面 ≥ `cam_clearance_min_m` | 掠射角下拿不到柱顶（s11 实测） |
| c | **像素尺寸**：障碍顶面在画幅中的边长 ≥ `min_obstacle_side_px` × `pixel_margin` | `min_obstacle_side_m` 由 GSD 换算 |
| d | **goal 在障碍另一侧**：`goal` 与 `car` 分居障碍足迹两侧，且直连线段**穿过**障碍足迹 | 否则"逼近"不成立 |
| e | **起终点在自由区**：整条直连线段不与其他障碍相交、不越作业区 | 起点/终点本身不得已冲突 |
| f | **逼近段够长**：`car→障碍近边` ≥ `d_safety + 车体半对角 + 余量` | 否则一出生就在 `SLOW` 带里，测不到 `PASS` 段 |

**口径纪律**：本文件**只读**几何配置文件与已登记的相机内参/高度派生值，不写死任何
"相机会看到什么"的经验数字；`GSD = H/f`、`f = W/(2·tan(HFOV/2))` 都是相机参数的函数。

用法：
  python3 tests/check_safety_scene_geometry.py                # 退出码 0=PASS
  python3 tests/check_safety_scene_geometry.py --json out.json
"""

import argparse
import json
import math
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
TASK_CFG = os.path.join(ROOT, 'src', 'agc_task', 'config')
SIM_CFG = os.path.join(ROOT, 'src', 'agc_sim', 'config')

# 本闸门守护的场景（安全层三档整链取证）。新增同类场景时**在这里加一行**，
# 而不是把判据散到各场景里 —— 判据必须对每个场景逐条跑同一套。
SAFETY_SCENES = {
    's19_static_static_safety_tiers': {
        'map': 'yard',
        # 期望成为"车与 goal 之间那道墙"的实体 id（在几何配置文件里）。
        'barrier': 'container_yard_b',
        # 直连路径上**允许穿过的唯一实体**：就是 barrier 本身。
        'allow_crossing': ('container_yard_b',),
    },
}

# 掠射/像素判据的两个可判定门限（**不是**感知配置的副本：感知用 0.24 m 物理门限，
# 这里额外要求 3 倍像素余量与 2 m 高度余量，因为"刚好过门限"在实测里等于拿不到）。
PIXEL_MARGIN = 3.0          # 顶面边长 ≥ 3 × 门限像素
CAM_CLEARANCE_MIN_M = 2.0   # 相机高于障碍顶面的下限（s11 实测 0.39 m 失败）
PATH_END_CLEAR_M = 0.6      # 起终点与障碍足迹的净空（≈ 车体半对角 0.5789）
# 逼近型构造的余量：出生点距障碍 ≥ d_safety + 车体半对角 + 本值。
# 取 1.0 = **两个 0.5 m 栅格**，小于它时"起点在带宽外"可能只差一格，落地即抖。
APPROACH_MIN_MARGIN_M = 1.0
# 起终点到**任一**障碍的净空余量（在半对角之外）。0.3 m ≈ 半个 0.5 m 栅格 + 离散误差。
SPAWN_CLEARANCE_MARGIN_M = 0.3


def _load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def _obstacles(geom):
    """把几何配置展开成 `[{id, x0,x1,y0,y1, top}]`（复合模型按 parts 取包络）。"""
    out = []
    for ob in geom.get('obstacles') or []:
        parts = ob.get('parts') or []
        if parts:
            base = (float(ob.get('x', 0.0)), float(ob.get('y', 0.0)))
            items = [(base[0] + float(p.get('x', 0.0)), base[1] + float(p.get('y', 0.0)),
                      float(p.get('yaw', 0.0) or 0.0), p.get('shape', 'box'), p.get('size'),
                      float(p.get('z', 0.0))) for p in parts]
        else:
            items = [(float(ob.get('x', 0.0)), float(ob.get('y', 0.0)),
                      float(ob.get('yaw', 0.0) or 0.0), ob.get('shape', 'box'),
                      ob.get('size'), float(ob.get('z', 0.0)))]
        xs, ys, top = [], [], 0.0
        for px, py, yaw, shape, size, z in items:
            if shape == 'cylinder':
                sx, sy, h = 2.0 * size[0], 2.0 * size[0], size[2]
            elif shape == 'sphere':
                sx, sy, h = 2.0 * size[0], 2.0 * size[0], 2.0 * size[0]
            else:
                sx, sy, h = size[0], size[1], size[2]
            c, s = math.cos(yaw), math.sin(yaw)
            for dx in (-sx / 2.0, sx / 2.0):
                for dy in (-sy / 2.0, sy / 2.0):
                    xs.append(px + dx * c - dy * s)
                    ys.append(py + dx * s + dy * c)
            top = max(top, z + h / 2.0)
        out.append({'id': ob['id'], 'x0': min(xs), 'x1': max(xs),
                    'y0': min(ys), 'y1': max(ys), 'top': top})
    return out


def _camera_intrinsics(model_sdf):
    """从机型 SDF 读相机参数 → `{width, hfov_rad, focal_px, mount_z}`。

    单目正下视只认 `sensor type` 含 `camera` 的**第一个**传感器（本仓 nadir 机的 rgbd 与 seg
    共内参，取哪个都一样；这里取第一个并显式声明这一假设）。
    """
    import re
    text = checklib.read_text(model_sdf) or ''
    m = re.search(r'<horizontal_fov>\s*([0-9.]+)\s*</horizontal_fov>', text)
    w = re.search(r'<width>\s*(\d+)\s*</width>', text)
    if not (m and w):
        raise RuntimeError('机型 %s 里找不到相机内参（horizontal_fov / width）' % model_sdf)
    hfov = float(m.group(1))
    width = int(w.group(1))
    focal = width / (2.0 * math.tan(hfov / 2.0))
    # 相机相对机体的安装高：`<joint>` 的 z 偏移（本仓 nadir 机是 0.242）。
    jz = re.search(r'<pose relative_to="base_link">\s*0\s+0\s+([0-9.]+)', text)
    mount_z = float(jz.group(1)) if jz else 0.0
    return {'width': width, 'height': width, 'hfov_rad': hfov,
            'focal_px': focal, 'mount_z': mount_z}


def _seg_rect_interval(x0, y0, x1, y1, r):
    """线段参数化 `t∈[0,1]` 上落在矩形**内部**的区间（Liang–Barsky）。

    返回 `(t_enter, t_exit)`；完全不相交返回 `None`。

    **为什么不用"是否相交"布尔量**：判"goal 在障碍另一侧"需要知道**障碍是否严格夹在
    两个端点之间**（`0 < t_enter` 且 `t_exit < 1`）。只判"相交"会把"车已经贴着障碍、
    障碍在车身后方"也算成"越过了它"—— s19 的板是 6.5 m 长的窄条，车会**平行**着它开，
    这种情况下"相交"与"被它隔开"是两件事。
    """
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - r['x0']), (dx, r['x1'] - x0),
                 (-dy, y0 - r['y0']), (dy, r['y1'] - y0)):
        if abs(p) < 1e-12:
            if q < 0.0:
                return None
            continue
        t = q / p
        if p < 0.0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 >= t1:
            return None
    return (t0, t1)


def _seg_crosses_rect(x0, y0, x1, y1, r):
    """线段是否与矩形内部相交（上面的区间判定的布尔化）。"""
    return _seg_rect_interval(x0, y0, x1, y1, r) is not None


def _point_in_rect(x, y, r, pad=0.0):
    return (r['x0'] - pad) <= x <= (r['x1'] + pad) and (r['y0'] - pad) <= y <= (r['y1'] + pad)


def _dist_to_rect(x, y, r):
    dx = max(r['x0'] - x, 0.0, x - r['x1'])
    dy = max(r['y0'] - y, 0.0, y - r['y1'])
    return math.hypot(dx, dy)


def check_scene(scene, want, scenes, base, ground_cfg, air_cfg, sim_cfg):
    """对单个场景跑 (a)–(f)。返回 `{check: {pass, detail, ...}}`。"""
    res = {}
    sc = (scenes or {}).get(scene)
    res['a_scene_registered'] = {
        'pass': bool(sc),
        'detail': 'scenario 已登记' if sc else 'scenarios.yaml 里没有 %s' % scene,
    }
    if not sc:
        return res

    world_map = (sc.get('world_map') or 'minimal').strip()
    res['a_map_matches_semantics'] = {
        'pass': world_map == want['map'],
        'detail': 'world_map=%s（期望 %s）' % (world_map, want['map']),
    }

    geom_path = {'yard': os.path.join(SIM_CFG, 'maps', 'yard.yaml'),
                 'minimal': os.path.join(SIM_CFG, 'world_geometry.yaml')}.get(world_map, '')
    if not geom_path or not os.path.isfile(geom_path):
        res['a_map_matches_semantics']['pass'] = False
        res['a_map_matches_semantics']['detail'] += '（几何配置文件不存在）'
        return res
    geom = _load_yaml(geom_path)
    obs = {o['id']: o for o in _obstacles(geom)}

    # ---- 出生位 / goal（场景层优先，其次 base；与 launch 的合并口径一致） ----
    sr = ((sc.get('params') or {}).get('scenario_reset') or {})
    base_sr = ((base.get('scenario_reset') or {}).get('ros__parameters') or {})
    car = (float(sr.get('car_x', base_sr.get('car_x', -15.0))),
           float(sr.get('car_y', base_sr.get('car_y', 1.0))))
    tm = ((sc.get('params') or {}).get('task_manager') or {})
    base_tm = ((base.get('task_manager') or {}).get('ros__parameters') or {})
    goal = (float(tm.get('goal_x', base_tm.get('goal_x', 0.0))),
            float(tm.get('goal_y', base_tm.get('goal_y', 0.0))))

    # 车体半对角（与安全层同一份 footprint 参数）：起终点净空判据要用它，
    # 故在 e/f 之前先算一次，**不在两处各写一遍数字**。
    gsp = ((ground_cfg.get('ground_safety_filter') or {}).get('ros__parameters') or {})
    half_diag_geom = math.hypot(float(gsp.get('footprint_half_length', 0.5037)),
                                float(gsp.get('footprint_half_width', 0.28545)))

    barrier = obs.get(want['barrier'])
    res['a_barrier_present'] = {
        'pass': barrier is not None,
        'detail': 'barrier=%s' % want['barrier'] if barrier else
                  '几何里没有 %s' % want['barrier'],
    }
    if barrier is None:
        return res

    # ---- b. 相机高度 ----
    fa = ((geom.get('flight_altitude') or {}))
    own_track = float(fa.get('own_track_m', 0.0))
    intrinsics = _camera_intrinsics(
        os.path.join(ROOT, 'src', 'agc_sim', 'models', 'agc_x500_nadir', 'model.sdf'))
    cam_h = own_track + intrinsics['mount_z']
    clearance = cam_h - barrier['top']
    res['b_camera_clearance'] = {
        'pass': clearance >= CAM_CLEARANCE_MIN_M,
        'detail': '相机高 %.2f m − 障碍顶 %.2f m = %.2f m（下界 %.2f m）'
                  % (cam_h, barrier['top'], clearance, CAM_CLEARANCE_MIN_M),
        'camera_height_m': round(cam_h, 3),
        'obstacle_top_m': round(barrier['top'], 3),
    }

    # ---- c. 像素尺寸 ----
    gsd = cam_h / intrinsics['focal_px']            # m/px（正下视）
    perc = _load_yaml(os.path.join(ROOT, 'src', 'agc_perception', 'config',
                                   'perception.yaml'))
    nadir_params = ((perc.get('nadir_projection') or {}).get('ros__parameters') or {})
    min_side_m = float(nadir_params.get('min_obstacle_side_m', 0.24))
    min_px = min_side_m / gsd
    # 用"顶面最小边"与"整体足迹最小边"里**更保守**的那个：掠射角下真正决定能否成连通域的
    # 是可见投影，这里以顶面（物理上一定可见的那一面）为下界。
    top_short = min(barrier['x1'] - barrier['x0'], barrier['y1'] - barrier['y0'])
    top_px = top_short / gsd
    res['c_pixel_size'] = {
        'pass': top_px >= PIXEL_MARGIN * min_px,
        'detail': '顶面短边 %.2f m = %.1f px；门限 %.1f px（%.2f m 由 GSD 换算），'
                  '要求 ≥ %.1f px（%.1f 倍余量）'
                  % (top_short, top_px, min_px, min_side_m,
                     PIXEL_MARGIN * min_px, PIXEL_MARGIN),
        'gsd_m_per_px': round(gsd, 5),
        'top_short_side_m': round(top_short, 3),
        'top_short_side_px': round(top_px, 1),
        'threshold_px': round(min_px, 1),
    }

    # ---- d. goal 在障碍另一侧：障碍**严格夹在**起点与终点之间 ----
    #
    # 判据 = 两端都在障碍足迹**外**，且直连线段穿过其内部并满足 `0 < t_enter`、`t_exit < 1`。
    # 这样"被它隔开"与"贴着它开过去"才分得开（见 `_seg_rect_interval` 的说明）。
    interval = _seg_rect_interval(car[0], car[1], goal[0], goal[1], barrier)
    start_out = not _point_in_rect(car[0], car[1], barrier)
    goal_out = not _point_in_rect(goal[0], goal[1], barrier)
    between = bool(interval and interval[0] > 1e-6 and interval[1] < 1.0 - 1e-6)
    behind = bool(start_out and goal_out and between)
    res['d_goal_behind_barrier'] = {
        'pass': behind,
        'detail': 'car=%s goal=%s；两端在足迹外=%s/%s；线段内部区间 t∈%s（须严格在 (0,1) 内）'
                  % (car, goal, start_out, goal_out,
                     ('(%.3f, %.3f)' % interval) if interval else '不相交'),
        'interval': interval,
        'path_length_m': round(math.hypot(goal[0] - car[0], goal[1] - car[1]), 3),
    }

    # ---- e. 起终点在自由区：整条线段不与其他障碍相交、端点不在任何障碍内 ----
    allow = set(want.get('allow_crossing') or ())
    hits = []
    for oid, o in obs.items():
        if oid in allow:
            continue
        if _seg_crosses_rect(car[0], car[1], goal[0], goal[1], o):
            hits.append(oid)
        if _point_in_rect(car[0], car[1], o) or _point_in_rect(goal[0], goal[1], o):
            hits.append('%s(端点在内)' % oid)
    # 出生点 / 终点到**每一个**障碍的净空（不只路径相交）。
    #
    # 为什么必须有这一条：2026-11-13 实测踩过 —— 车生成在 `silo_s`（半径 1.05 m）的
    # 足迹内（车右缘 0.50 m vs 柱缘 0.45 m），整链一开跑就 `STOP_COLLISION` 且
    # `collision_count=1; silo_s::link::link_collision@t=0.15s`。
    # 只查"路径是否相交"抓不到这种情况：路径本身确实只穿过 barrier，
    # 但**起点就在另一个障碍里**。这类错误的症状是"安全层一直停着"，
    # 极易被误读成"安全层判错"。
    clearance_need = half_diag_geom + SPAWN_CLEARANCE_MARGIN_M
    tight = []
    for oid, o in obs.items():
        dc = _dist_to_rect(car[0], car[1], o)
        dg = _dist_to_rect(goal[0], goal[1], o)
        if dc < clearance_need:
            tight.append('%s(出生点净空 %.2f m < %.2f)' % (oid, dc, clearance_need))
        if dg < clearance_need:
            tight.append('%s(终点净空 %.2f m < %.2f)' % (oid, dg, clearance_need))
    res['e_path_free_of_other_obstacles'] = {
        'pass': not hits and not tight,
        'detail': '直连路径只穿过 %s；路径命中：%s；起终点净空不足：%s'
                  % (want['barrier'], hits or '无', tight or '无'),
        'hits': hits + tight,
        'clearance_required_m': round(clearance_need, 3),
    }

    # ---- f. 逼近/定档段：整条直连路径都要有"离障碍足够远 → 足够近"的跨度 ----
    #
    # 判据（**两种满足方式，任一即可**，因为它们对应两种合法的取证构造）：
    #   ① **逼近型**：出生点离障碍近边 ≥ d_safety + 车体半对角 + 余量
    #      ⇒ 车**开近**障碍，净空从 >d_safety 连续降到 <d_collision（PASS→SLOW→STOP_COLLISION）；
    #   ② **贴靠型**：出生点已在 `(d_emergency, d_safety)` 带内（`SLOW` 档），
    #      且直连路径**穿过**障碍 ⇒ 车一动就在安全带内，必然定档（哪怕只有 SLOW/STOP）。
    #
    # 不管哪种，都必须同时满足：**路径上离障碍最近的点 < d_collision**（否则整条路径都在
    # 安全带宽之外，安全层**正确地**不介入，那次取证会以"全程 PASS"安静地失败）。
    d_safety = float(gsp.get('d_safety', 4.0))
    d_collision = float(gsp.get('d_collision', 2.0))
    d_emergency = float(gsp.get('d_emergency', 1.0))
    half_diag = math.hypot(float(gsp.get('footprint_half_length', 0.5037)),
                           float(gsp.get('footprint_half_width', 0.28545)))
    # 逼近型的下界 = d_safety + 车体半对角（出生点至少不能在 `SLOW` 带里）+
    # APPROACH_MIN_MARGIN_M（真正的余量，见常量注释）。
    half_diag = half_diag_geom
    need_far = d_safety + half_diag + APPROACH_MIN_MARGIN_M
    gap_start = _dist_to_rect(car[0], car[1], barrier)
    approach_mode = gap_start >= need_far
    near_mode = d_emergency < gap_start < d_safety
    # 路径上离障碍最近的距离：端点 + 线段对矩形的最近点（穿矩形时为 0）。
    interval = _seg_rect_interval(car[0], car[1], goal[0], goal[1], barrier)
    if interval is not None:
        gap_min = 0.0
    else:
        gap_min = min(_dist_to_rect(car[0], car[1], barrier),
                      _dist_to_rect(goal[0], goal[1], barrier))
    res['f_approach_span'] = {
        'pass': bool((approach_mode or near_mode) and gap_min < d_collision),
        'detail': '出生点距障碍近边 %.2f m（逼近型需 ≥ %.2f；贴靠型需 ∈ (%.2f, %.2f)）；'
                  '路径最近距离 %.2f m（须 < d_collision %.2f）；档=%s'
                  % (gap_start, need_far, d_emergency, d_safety, gap_min, d_collision,
                     'approach' if approach_mode else ('near' if near_mode else 'none')),
        'gap_start_m': round(gap_start, 3),
        'gap_min_m': round(gap_min, 3),
        'required_far_m': round(need_far, 3),
        'd_emergency_m': d_emergency, 'd_collision_m': d_collision, 'd_safety_m': d_safety,
    }
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--json', default=None)
    args = ap.parse_args()

    scenes = (_load_yaml(os.path.join(TASK_CFG, 'scenarios.yaml')) or {}).get('scenes') or {}
    base = _load_yaml(os.path.join(TASK_CFG, 'base.yaml')) or {}
    ground = _load_yaml(os.path.join(ROOT, 'src', 'agc_ground', 'config', 'ground.yaml'))
    air = _load_yaml(os.path.join(ROOT, 'src', 'agc_air', 'config', 'air.yaml'))

    payload = {'checks': {}, 'scenes': list(SAFETY_SCENES)}
    failures = []
    for scene, want in SAFETY_SCENES.items():
        r = check_scene(scene, want, scenes, base, ground, air, SIM_CFG)
        payload['checks'][scene] = r
        for key, val in r.items():
            if not val.get('pass'):
                failures.append('%s/%s: %s' % (scene, key, val.get('detail')))

    for scene, checks in payload['checks'].items():
        print('[%s]' % scene)
        for key in sorted(checks):
            v = checks[key]
            print('  %s  %-38s %s' % ('PASS' if v.get('pass') else 'FAIL', key,
                                      v.get('detail')))
    payload['pass'] = not failures

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    if failures:
        print('\nFAIL：%d 项几何不成立 —— 场景**不得**用于三档取证（先改几何，别去调参）'
              % len(failures))
        return 1
    print('\nPASS：安全层取证场景几何成立（%d 个场景）' % len(SAFETY_SCENES))
    return 0


if __name__ == '__main__':
    sys.exit(main())
