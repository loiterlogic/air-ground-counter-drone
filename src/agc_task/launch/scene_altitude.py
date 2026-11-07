#!/usr/bin/env python3
"""scene_altitude —— 飞行高度：按地图派生与注入（ADR-0007）。

用户 2026-11-02 裁定：「高度和地图绑定，因为后面会做小障碍高密度和大障碍低密度等图」。
⇒ 每张地图在自己几何文件里声明"该图该飞多高"，运行期派生注入，
`air.yaml` / `base.yaml` **不再是**高度的第二来源。

本模块只处理"高度"这一件事；几何本身在 `scene_geometry`，场景合并在 `scene_loader`。
"""

import math

from scene_geometry import (
    geometry_ids,
    geometry_safety_radii,
    geometry_xs,
    geometry_ys,
    geometry_z_tops,
)


def apply_air_geometry(air_merged, geometry, sim_share=None):
    """把几何源文件的静态障碍几何注入空中安全列表（`trajectory_tracker.safety`）。

 `obstacle_names/x/y` 由配置文件派生；**：`obstacle_safety_radius` 亦按障碍派生**
 （`safety_radius` 逐障碍取值，缺省 2.0），消除旧的「与障碍数对齐的定长列表」——
 该列表加到 N 个障碍却不同步扩展时会导致 `safety_shield` 索引错位或越界
 （ADR-0007 未决项②； 的五数组等长校验仍在启动期拒绝不一致）。原地修改并返回。
 `obstacle_margin` / `target_margin` / 反应时间 / 可达性等**安全余量**仍来自 `air.yaml`
 （安全参数，非几何）。

 ADR-0010「垂直门控」：另注入 `obstacle_z_top`（逐障碍顶面高度）与 `vertical_clearance_m`
 （= 地图 `flight_altitude.own_clearance_min_m`，**不另立参数**——同一张图的高度与净空同源）。
    """
    safety = air_merged.setdefault('trajectory_tracker', {}).setdefault('safety', {})
    safety['obstacle_names'] = geometry_ids(geometry)
    safety['obstacle_x'] = geometry_xs(geometry)
    safety['obstacle_y'] = geometry_ys(geometry)
    safety['obstacle_safety_radius'] = geometry_safety_radii(geometry, sim_share)
    safety['obstacle_z_top'] = geometry_z_tops(geometry, sim_share)
    safety['vertical_clearance_m'] = flight_altitude_block(geometry)['own_clearance_min_m']
    return air_merged


def flight_altitude_block(geometry):
    """ADR-0007：读地图几何里的 `flight_altitude` 块并**规范化 + 校验**。

 用户 2026-11-02 裁定：「高度和地图绑定，因为后面会做小障碍高密度和大障碍低密度等图」。
 ⇒ 每张地图在自己几何文件里声明"该图该飞多高"，运行期派生注入，`air.yaml` / `base.yaml`
 的同名键降级为 standalone / 单测兜底（与 `safety.obstacle_*` 同款处理）。

 缺块 / 缺键 / 非有限值 / 非正 → **拒绝运行**（不静默回退到某份旧默认值——那正是
 ADR-0007 要消灭的第二配置文件）。返回规范化 dict（含 `derived` 子块，供断言比对）。
    """
    fa = (geometry or {}).get('flight_altitude')
    if not isinstance(fa, dict):
        raise RuntimeError(
            '地图几何文件缺少 flight_altitude 块（ADR-0007：高度必须随地图声明）→ 拒绝运行')
    out = {}
    for key in ('own_track_m', 'own_takeoff_m', 'target_cruise_m', 'own_clearance_min_m'):
        if key not in fa:
            raise RuntimeError('flight_altitude 缺少键 %r → 拒绝运行' % (key,))
        try:
            v = float(fa[key])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                'flight_altitude.%s=%r 非数值 → 拒绝运行' % (key, fa[key])) from exc
        if not math.isfinite(v) or v <= 0.0:
            raise RuntimeError(
                'flight_altitude.%s=%r 非有限正数（NaN/±Inf/≤0）→ 拒绝运行' % (key, fa[key]))
        out[key] = v
    derived = fa.get('derived') or {}
    out['derived'] = {
        'h_max_map_m': float(derived.get('h_max_map_m') or 0.0),
        'h_max_env_m': float(derived.get('h_max_env_m') or 0.0),
        'rule_version': int(derived.get('rule_version') or 1),
    }
    return out


def net_params_for_altitude(target_cruise_m, base_cap):
    """ADR-0007：按**目标巡航高度**反推网弹道参数（仅当基线弹道打不到时使用）。

 设计口径（与 `dynamic_fire_control.hpp` 的 `netPos` / `radius` 同一套物理）：
 * 抛射角固定 **85°**（近垂直 → 水平射程小，车可停在目标近旁开火）；
      * 初速取「解析顶点 = 目标高度 + 0.65 m」反解：`v0 = √(2g(h+0.65)) / sinθ`；
 * 飞行超时 = 落地时刻 `2·v0·sinθ/g` + 0.3 s（留一个结算周期余量）。

 **只在基线弹道打不到该高度时才派生**（`apex_base < target_cruise_m`）——
 这样 `minimal` / `open_field`（目标 2.0 m，基线 apex 2.009 m）**逐值不变**，
 历史证据基线不被改写。返回 `None` 表示沿用基线参数。
    """
    apex_base = (base_cap['v0'] * math.sin(math.radians(base_cap['angle_deg']))) ** 2 / (
        2.0 * base_cap['g'])
    if target_cruise_m <= apex_base:
        return None
    angle_deg = 85.0
    margin_m = 0.65
    v0 = math.sqrt(2.0 * base_cap['g'] * (target_cruise_m + margin_m)) / math.sin(
        math.radians(angle_deg))
    vy = v0 * math.sin(math.radians(angle_deg))
    return {
        'net_v0_mps': round(v0, 2),
        'net_angle_deg': angle_deg,
        'net_flight_timeout_s': round(2.0 * vy / base_cap['g'] + 0.3, 2),
        # 派生值只作证据：解析顶点与落地时刻，供断言/审查复算。
        '_apex_m': round(vy * vy / (2.0 * base_cap['g']), 4),
        '_t_land_s': round(2.0 * vy / base_cap['g'], 4),
        '_rule': 'apex = target_cruise + 0.65 m; θ=85°; timeout = t_land + 0.3 s',
    }


def apply_flight_altitude_params(merged, info):
    """ADR-0007：把地图高度注入**任务侧**参数。原地修改并返回规范化块。

 注入三处（其余高度键在 `apply_flight_altitude_air`）：
 1. `intruder_driver.cruise_alt_m`（+ 同值弃用别名 `alt_m`，否则别名冲突会让节点拒绝启动）；
 2. `capture_adjudicator` 的网弹道参数 —— **仅当基线弹道打不到该高度**时派生
 （`net_params_for_altitude`），否则逐值不变；
 3. `task_manager.air_hover_climb_m` —— 起飞完成判据必须跟着抬，否则「爬升量 ≥ 阈值」
 永远不成立，整链卡在 `air_hover_timeout`。
    """
    geometry = (info or {}).get('geometry')
    fa = flight_altitude_block(geometry)
    idr = merged.setdefault('intruder_driver', {})
    idr['cruise_alt_m'] = fa['target_cruise_m']
    if 'alt_m' in idr:
        idr['alt_m'] = fa['target_cruise_m']
    # 起飞完成判据：与 `takeoff_altitude_m` 同步（基线 2.5 → 2.3，差 0.2 = hover_tolerance）。
    merged.setdefault('task_manager', {})['air_hover_climb_m'] = round(fa['own_takeoff_m'] - 0.2, 3)
    cap = merged.setdefault('capture_adjudicator', {})
    base_cap = {
        'v0': float(cap.get('net_v0_mps', 6.5)),
        'angle_deg': float(cap.get('net_angle_deg', 75.0)),
        'g': float(cap.get('net_g', 9.81)),
    }
    derived_net = net_params_for_altitude(fa['target_cruise_m'], base_cap)
    if derived_net is not None:
        cap['net_v0_mps'] = derived_net['net_v0_mps']
        cap['net_angle_deg'] = derived_net['net_angle_deg']
        cap['net_flight_timeout_s'] = derived_net['net_flight_timeout_s']
    # 干扰包络上限**只升不降**：抬目标后 2.0 m 的旧上限会让 jam 场景恒判包络外。
    jam_max = float(cap.get('jam_envelope_max_alt_m', 2.0))
    if fa['target_cruise_m'] > jam_max:
        cap['jam_envelope_max_alt_m'] = round(fa['target_cruise_m'] + 0.5, 3)
    fa['_net_derived'] = derived_net
    # 来源登记走 `info`（launch 自有 dict），**不**注入节点参数——否则多一个未声明参数会拒绝启动。
    # `cruise_altitude_block` 据此把 source 报成 `map`（ADR-0007 改变了 H0 的"必须来自场景"口径）。
    if isinstance(info, dict):
        info['flight_altitude'] = fa
    return fa


def apply_flight_altitude_air(air_merged, geometry):
    """ADR-0007：把地图高度注入**空中侧**参数（与 `apply_air_geometry` 同款同位置）。"""
    fa = flight_altitude_block(geometry)
    air_merged.setdefault('standoff_follower', {})['height'] = fa['own_track_m']
    air_merged.setdefault('takeoff_controller', {})['takeoff_altitude_m'] = fa['own_takeoff_m']
    return air_merged

def cruise_altitude_block(merged, info=None, effective_spawn=None):
    """H0（2026-11-02）：巡航高度**实际生效值 + 来源 + 参考基准**（manifest 可还原）。

 为什么单独成块：H0 的核心歧义是"同一个数字既是出生高度、又是爬升量、又是巡航高度"。
 把"生效值 / 来源 / 基准 / 是否叠加"四件事写进 manifest，使每个 run 的高度语义**可逐项复核**，
 而不是靠读两份 yaml 自己推。

    解析规则与 `intruder_driver._resolve_cruise_alt()` **同口径**（此处只做记录，不重复实现校验；
 真正的拒绝启动由节点在运行期执行，故本函数对非法值如实标注 `invalid` 而不抛异常）。
    """
    idr = merged.get('intruder_driver') or {}
    cruise = idr.get('cruise_alt_m')
    alias = idr.get('alt_m')
    scene_over = (((info or {}).get('sc') or {}).get('params') or {}).get('intruder_driver') or {}
    # ADR-0007（2026-11-02）：高度归**地图**。`apply_flight_altitude_params` 已在 `info` 里
    # 登记本图派生块，故来源优先级变为：**map > scene > base**。
    # 这是对 H0「vision 平面必须 source=scene」口径的**显式修订**（见 ADR-0007）：
    # 地图是几何事实、场景是任务意图；高度属前者。场景仍可覆盖（向后兼容），但默认走地图。
    map_fa = (info or {}).get('flight_altitude')
    if map_fa is not None and cruise is not None \
            and abs(float(cruise) - float(map_fa['target_cruise_m'])) < 1e-9:
        source = 'map'
    elif 'cruise_alt_m' in scene_over:
        source = 'scene'
    elif cruise is not None:
        source = 'base'
    elif alias is not None:
        source = 'base(alt_m 弃用别名)'
    else:
        source = 'missing'
    effective = cruise if cruise is not None else alias
    valid = isinstance(effective, (int, float)) and effective > 0
    return {
        'effective_m': effective,
        'source': source,
        # 弃用别名同时记录：两者不相等时节点会拒绝启动，manifest 让"为什么会拒"可见。
        'deprecated_alias_alt_m': alias,
        'alias_conflicts': (cruise is not None and alias is not None
                            and abs(float(cruise) - float(alias)) > 1e-9),
        'valid': bool(valid),
        # 参考基准：本值相对 **episode 原点**（epoch 后首帧 odom），**不是**世界 ENU 高度。
        'datum': 'episode_origin_ned',
        'world_enu_absolute': False,
        # 明确登记"不与世界 spawn 值叠加"——这是 H0 判定过的结论，不是默认假设。
        'stacks_on_spawn_z': False,
        'spawn_place_z': (((effective_spawn or {}).get('target')) or {}).get('z'),
        # ADR-0007：本 run 的地图高度派生块（None = 未经地图派生，如历史单测）。
        'map_flight_altitude': ({k: v for k, v in map_fa.items() if not k.startswith('_')}
                                if map_fa is not None else None),
        'note': ('巡航高度 = episode 原点世界高度 + effective_m；原点世界高度由 EKF 初始化决定、'
                 '跨 run 不可复现，故本值不是绝对世界高度。世界放置值另见 spawn_layout.target.z'
                 '（PX4 attach 前瞬态，不与本值叠加）。'),
    }
