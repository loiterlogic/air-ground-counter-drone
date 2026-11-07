#!/usr/bin/env python3
"""scene_assertions —— 启动期轴断言：派生链任何一环漂移都在这里被抓住。

核心判据是「**派生几何 == 配置文件**」：几何配置文件是唯一来源（ADR-0007），
派生出的感知障碍先验 / 地图几何 / 空中安全列表 / 复位参数都必须与它一致。
断言结果随 manifest 落盘，审查可复核"本 run 的派生链是否自洽"。

与 `scene_manifest` 的分工：本模块只**判定**（返回 `{name: bool}`），不拼 manifest。
"""

import math

from scene_altitude import cruise_altitude_block, flight_altitude_block
from scene_geometry import (
    geometry_ids,
    geometry_safety_radii,
    geometry_xs,
    geometry_ys,
    geometry_z_tops,
    work_area_bounds,
)
from scene_spawn import spawn_layout_distances


def assertions(scene, merged, info, air_merged=None, sim_share=None, layout=None,
               effective_spawn=None, effective_own=None):
    """断言：实际生效参数 == 声明轴、**派生几何 == 几何源文件**、
 **生效出生位 == 喂给世界的那一组**；任一失败 → 拒绝运行。

    F1（2026-10-31）：`effective_spawn` 为 `apply_spawn_layout()` 的返回值（该 run 实际生效的
 车 / 目标位，也是 `main.launch.py` 喂给 `world_bringup` 的值）。断言
 「`scenario_reset` 参数 == `effective_spawn`」= 「复位位置 == 世界 spawn」在**启动前**可判定。

    `effective_own`（`parse_own_pose()` 结果）：己方机位姿可被 launch 显式覆盖，故
 ① `scenario_reset.own_uav_x/y` 必须等于**实际生效** own（而非 layout 缺省）；
 ② 设计距离必须按实际生效 own 算——否则"覆盖过的 run"会被 layout 的距离误判为通过
 （审查第 5 条）。
    """
    axes = info['axes']
    entries = info['entries']
    geometry = info['geometry']
    gids = geometry_ids(geometry)
    gxs = geometry_xs(geometry)
    gys = geometry_ys(geometry)
    bounds = work_area_bounds(geometry)
    sr = merged.get('scenario_reset', {})
    obs_ids = info['derived_obstacles_ids']
    res = {
        'target_motion_effective_equals_declared':
            merged.get('intruder_driver', {}).get('motion') == axes.get('target_motion'),
        'obstacle_world_effective_matches':
            info['world_obstacles'] == entries['obstacle']['world_obstacles'],
        'obstacles_file_effective_matches':
            info['obstacles_file_name'] == entries['obstacle']['obstacles_file'],
        # 派生几何 == 配置文件（scenario_reset 障碍清单 / 作业区边界）。
        'scenario_reset_obstacles_match_geometry':
            list(sr.get('obstacle_names', [])) == gids
            and [float(v) for v in sr.get('obstacle_x', [])] == gxs
            and [float(v) for v in sr.get('obstacle_y', [])] == gys,
        'scenario_reset_bounds_match_work_area':
            all(k in sr for k in bounds)
            and all(float(sr[k]) == v for k, v in bounds.items()),
        # 感知障碍先验按轴派生（static=配置文件；none=空），无第二份几何。
        'derived_obstacles_match_axis':
            (obs_ids == gids) if info['world_obstacles'] == 'static' else (obs_ids == []),
    }
    if effective_spawn is not None:
        car, tgt = effective_spawn['car'], effective_spawn['target']
        # 「复位位置 == 世界 spawn」：世界 spawn 用的就是这组 eff_*，故这里是同一判据的两侧。
        res['scenario_reset_spawn_equals_world_spawn'] = (
            abs(float(sr.get('car_x', 1e9)) - car['x']) < 1e-9
            and abs(float(sr.get('car_y', 1e9)) - car['y']) < 1e-9
            and abs(float(sr.get('car_z', 1e9)) - car['reset_z']) < 1e-9
            and abs(float(sr.get('target_x', 1e9)) - tgt['x']) < 1e-9
            and abs(float(sr.get('target_y', 1e9)) - tgt['y']) < 1e-9
            and abs(float(sr.get('target_z', 1e9)) - tgt['z']) < 1e-9)
    if layout is not None:
        # （ADR-0012）不变量：车↔目标出生距离不得低于标定下限（本任务只许拉大，不许削弱）。
        car = effective_spawn['car'] if effective_spawn is not None else layout['car']
        tgt = effective_spawn['target'] if effective_spawn is not None else layout['target']
        # own 用**实际生效**值：显式覆盖时不得拿 layout 的 own 算距离（那会造出自洽假象）。
        own = effective_own if effective_own is not None else layout['own_uav']
        dists = spawn_layout_distances({'car': car, 'target': tgt, 'own_uav': own})
        clearance_min = float(sr.get('spawn_clearance_min_m', 6.0))
        res['spawn_car_target_meets_c7'] = dists['car_target_m'] >= clearance_min
        if effective_own is not None:
            # 己方机出生净空校验坐标 == 实际生效 own（覆盖后仍须一致）。
            # 仅当**本 run 声明己方机在场**时判：`backend:=lightweight` 不起空中链路，
            # `own_uav_present=False`、`own_uav_x/y` 保持 base 的 0.0 占位（不是"出生位"），
            # 拿它去比布局配置文件会误判——那是"该字段不适用"，不是"配置不一致"。
            if bool(sr.get('own_uav_present', False)):
                res['own_uav_reference_equals_effective_own'] = (
                    abs(float(sr.get('own_uav_x', 1e9)) - own['x']) < 1e-9
                    and abs(float(sr.get('own_uav_y', 1e9)) - own['y']) < 1e-9)
        # F1 设计目标（派工单）：车/目标 ≥30 m、己方机/目标 ≥25 m、己方车机 3–8 m。
        # 仅对**默认出生布局**（source=layout）判；场景自定义出生位（s10/s11…）属场景语义，
        # 不按本任务设计目标约束（否则等于改那些场景的验收口径）。
        # 己方机被显式覆盖时**同样判**——设计目标是对"本 run 实际几何"的约束，不因覆盖而豁免。
        if effective_spawn is None or effective_spawn.get('source') == 'layout':
            res['spawn_design_goals_met'] = (
                dists['car_target_m'] >= 30.0
                and dists['own_uav_target_m'] >= 25.0
                and 3.0 <= dists['car_own_uav_m'] <= 8.0)
        # F1 （审查第 6 条）：**派生**的目标位必须落在 `d_track` 可达范围内。
        # 只判 `goal_source == 'derived'`——场景显式给目标位的（s10/s11）其"不可达"是设计意图，
        # 不能拿本规则误判它们为配置错误。这一条把"改了 target、忘了 goal"挡在启动前。
        if (effective_spawn or {}).get('goal_source') == 'derived':
            gx = float((effective_spawn or {}).get('goal_x', 1e9))
            gy = float((effective_spawn or {}).get('goal_y', 1e9))
            d_track = float((merged.get('task_manager') or {}).get('d_track_m', 3.0))
            res['derived_goal_within_track_range'] = (
                math.hypot(gx - tgt['x'], gy - tgt['y']) <= d_track)
    # ADR-0014 不变量：**已授权射击**的场景必须关闭「跟踪里程碑即终态」——
    # 否则 `capture_adjudicator` 的交火窗口（`task_state == GROUND_APPROACH`）会在
    # `TRACKING_SUCCESS` 锁存时被提前关闭，捕获（`INTERCEPT_CONFIRMED/CAPTURE_NET`）**永不发生**
    # （实测 s08 协同臂 20/20 落 TRACKING_SUCCESS）。此断言把该配置矛盾挡在启动前。
    authorized = bool((merged.get('capture_adjudicator') or {}).get('interception_authorized', False))
    milestone_terminal = bool(
        (merged.get('task_manager') or {}).get('tracking_milestone_is_terminal', True))
    res['capture_authorized_requires_nonterminal_milestone'] = (not authorized) or (not milestone_terminal)
    # H0（2026-11-02）：巡航高度必须**配置文件且合法**——两个同值参数各自承担语义正是 H0 要消除的歧义。
    # 与 `intruder_driver._resolve_cruise_alt` 同判据，此处**启动前**就挡住，避免跑到半程才崩。
    _ca = cruise_altitude_block(merged, info, effective_spawn)
    res['cruise_altitude_single_valid_source'] = bool(
        _ca['valid'] and not _ca['alias_conflicts'] and _ca['source'] != 'missing')
    if air_merged is not None:
        safety = air_merged.get('trajectory_tracker', {}).get('safety', {})
        res['air_obstacles_match_geometry'] = (
            list(safety.get('obstacle_names', [])) == gids
            and [float(v) for v in safety.get('obstacle_x', [])] == gxs
            and [float(v) for v in safety.get('obstacle_y', [])] == gys)
        # 安全半径**按障碍派生**（不再来自 air.yaml 的定长列表）。
        res['air_safety_radii_match_geometry'] = (
            [float(v) for v in safety.get('obstacle_safety_radius', [])]
            == geometry_safety_radii(geometry, sim_share))
        # ADR-0010「垂直门控」：顶高与净空也必须**逐障碍 / 逐地图**派生，长度与 ids 等长。
        # 漏注入时安全层的缺省是「无顶高 → 门控不生效」（保守但仍正确）；本断言把
        # 「明明有配置文件却没接上」挡在启动前，而不是让它静默退化成全高圆柱。
        z_tops = geometry_z_tops(geometry, sim_share)
        res['air_z_tops_match_geometry'] = (
            len(safety.get('obstacle_z_top', [])) == len(gids)
            and all(abs(float(v) - z) < 1e-9
                    for v, z in zip(safety.get('obstacle_z_top', []), z_tops, strict=False)))
        res['air_vertical_clearance_matches_source'] = (
            abs(float(safety.get('vertical_clearance_m', -1e9))
                - flight_altitude_block(geometry)['own_clearance_min_m']) < 1e-9)
    # ADR-0007：高度派生四条断言——**无论 backend** 都要跑（lightweight 不起空中链路时，
    # 空中侧两键改用地图声明值 + air.yaml 基线做判据，见 `_flight_altitude_assertions`）。
    # 放在 `if air_merged is not None` **之外**是刻意的：地图高度配置是否自洽与后端无关。
    res.update(_flight_altitude_assertions(merged, info, air_merged, geometry))
    bad = [k for k, v in res.items() if not v]
    if bad:
        raise RuntimeError(
            '场景 %s 实际生效参数 != 声明轴 或 派生几何 != 几何源文件（断言失败：%s）→ 拒绝运行' % (
                scene, bad))
    return res


def _flight_altitude_assertions(merged, info, air_merged, geometry):
    """ADR-0007：高度派生三条断言（误配即拒绝运行）。

 三条对应规范 [规范](../../docs/conventions/飞行高度分层与按地图定高.md#where) 第 4 点：
 1. `flight_altitude_derived_matches_source` —— 注入值 == 地图文件值（防"有人又改了 air.yaml"）
 2. `own_height_covers_h_max_env` —— `h_o ≥ H_max_env + c_clear`（防"飞得比楼低"）
 3. `target_within_capture_envelope` —— capture/jam 场景 `h_t ≤ 包络上限`（防"抬完打不着"）

 原第 3 条 `dz_within_perception_range`（K1 感知量程自洽性验算）已于 2026-11-06 删除：
 它读的 `sensors_file` / `air_perception` 随 `perception` 场景轴一并退役，且规范本身
 标注"当前不生效、`gt_adapter` 不做几何门控"，删它不改变任何运行期判定。
    """
    fa = flight_altitude_block(geometry)
    res = {}
    # `air_merged is None`（lightweight 后端：不起空中链路）时，空中侧两键**不注入**。
    # 此时 ①②③ 改用**地图声明值**做判据——这正是"这张图的高度配置本身是否自洽"，
    # 仍然能在启动前挡住"地图写了个比楼低的高度"；断言 ① 则如实降级为"只校验任务侧"。
    has_air = air_merged is not None
    sf = (air_merged or {}).get('standoff_follower') or {}
    tk = (air_merged or {}).get('takeoff_controller') or {}
    # ① 注入值 == 地图文件值（两侧同源于 `geometry`，此处判"是否真的注入了"）。
    task_side_ok = abs(float((merged.get('intruder_driver') or {}).get('cruise_alt_m', -1e9))
                       - fa['target_cruise_m']) < 1e-9
    if has_air:
        res['flight_altitude_derived_matches_source'] = (
            task_side_ok
            and abs(float(sf.get('height', -1e9)) - fa['own_track_m']) < 1e-9
            and abs(float(tk.get('takeoff_altitude_m', -1e9)) - fa['own_takeoff_m']) < 1e-9)
    else:
        # 如实登记"空中侧不适用"，而不是省略字段（省略会让审查分不清"没用"与"忘了记"）。
        res['flight_altitude_derived_matches_source'] = task_side_ok
    # ② 垂直净空：己方机跟踪高度必须高于**作业包络内**最高障碍 + c_clear。
    h_max_env = float(fa['derived']['h_max_env_m'])
    res['own_height_covers_h_max_env'] = (
        fa['own_track_m'] >= h_max_env + fa['own_clearance_min_m'] - 1e-9)
    # ③ 捕获/干扰包络（K4）：**只对已授权射击的场景**判（tracking 类不判，避免误伤）。
    cap = merged.get('capture_adjudicator') or {}
    authorized = bool(cap.get('interception_authorized', False))
    if authorized:
        v0 = float(cap.get('net_v0_mps', 6.5))
        ang = float(cap.get('net_angle_deg', 75.0))
        g = float(cap.get('net_g', 9.81))
        launcher = float(cap.get('launcher_height_m', 0.0))
        apex = (v0 * math.sin(math.radians(ang))) ** 2 / (2.0 * g)
        # h = 目标高度 − 车体 z − 发射器高度；车 z 取复位口径（地面）。
        car_z = float((merged.get('scenario_reset') or {}).get('car_z', 0.0))
        h_target = fa['target_cruise_m'] - car_z - launcher
        res['target_within_capture_envelope'] = (h_target <= apex + 1e-9)
    return res

