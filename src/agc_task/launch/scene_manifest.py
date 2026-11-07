#!/usr/bin/env python3
"""scene_manifest —— manifest 构建与产物落盘。

manifest 身份与入口名一致：`launch='main.launch.py'` + 实际 `backend` + `nodes`（展开节点）
+ 生效参数（`scene` / `seed` / `support_status` / `declared_axes` / `expected_terminal` /
`expected_reason` / `carriers` / `effective_params` / `assertions`）。

`assertions` 的结果（来自 `scene_assertions`）原样嵌入，本模块**不重新判定**。
"""

import json
import os
import tempfile

import yaml

from scene_common import new_run_token
from scene_geometry import (
    DEFAULT_WORLD_MAP,
    obstacle_bbox_size,
    obstacle_footprint_radius,
    obstacle_is_composite,
    obstacle_safety_radius,
    obstacle_shape,
    obstacle_z_top,
    world_map_module,
)
from scene_loader import BACKENDS, coverage_status, derive_px4_sim_seed
from scene_spawn import own_uav_pose_string, spawn_layout_distances
from scene_altitude import cruise_altitude_block

# 统一入口文件名（manifest `launch` 字段须与入口名一致）。
LAUNCH = 'main.launch.py'


def vision_plane_block(plane=None, perception_path='truth', detector_backend=None):
    """视觉目标高度平面登记块（**2026-11-04 起恒为"未启用"**）。

 历史：`perception_path=vision` 时本块记录 `datum` / `world_enu_plane_z` / `source`，
 供审查复核视觉投影用的世界 ENU 平面。视觉路径已整体退役，因此本函数**保留字段形状、
 值恒为 `applied=false`：

 * 为什么保留而不删：`manifest` 是对外产物 schema，历史 run 都带 `perception_path` /
 `vision_plane` 两个键；删键会让新旧 run 不可直接对比。保留后审查看到的仍是
 "本 run 不使用高度平面"，而不是"忘了记"。
 * `perception_path` 也恒为 `truth`（不再由 launch 参数驱动）。
    """
    _ = (plane, detector_backend)   # 仅为签名兼容保留；不再有视觉路径消费它们
    return {
        'applied': False,
        'perception_path': 'truth',
        'datum': 'episode_origin_ned',
        'world_enu_plane_z': None,
        'source': None,
        'stacks_on_spawn_z': False,
        'note': ('视觉定位路径已于 2026-11-04 退役（ADR-0009 (a2)）：本 run 不使用目标高度平面。'
                 '目标位置由真值给出（gt_adapter；air_fusion 已退役），不经像素反推。'),
    }


def build_manifest(backend, info, merged, assertions_result, sim_share=None,
                   layout=None, layout_sha256=None, own_pose=None, effective_spawn=None,
                   effective_own=None, air_merged=None, cli_observe_yaw_mode='',
                   perception_path='truth', vision_plane=None, detector_backend=None):
    # `perception_path` / `vision_plane` / `detector_backend` 三个形参**保留但不再使用**：
    # 视觉定位路径已于 2026-11-04 退役，manifest 对应字段恒写固定值（见 vision_plane_block）。
    # 保留形参是为了不改既有调用点的签名（w6.launch / w6_geometry_check 等）。
    _ = (perception_path, vision_plane, detector_backend)
    """产出 manifest dict（身份与入口名一致 + 完整展开节点 + 生效参数）。

 `launch` == `LAUNCH`（入口名）；`backend` = 实际 backend；`nodes` 由 backend 能力表派生。
 F1（2026-10-31）：传 `layout` 时追加 `spawn_layout` 块——出生布局配置文件路径 / sha256 /
 **实际生效**的车 / 目标位 / 己方机起飞参考字符串 / 三组距离，使"世界 spawn、复位位置、
 己方机起飞参考"三者在**同一份 run 证据**里可逐项比对（不靠配置自述）。
    `effective_own`（`parse_own_pose()` 结果）用于让距离与生效 own pose 同源，见
 `spawn_layout_block`。
    """
    scene = info['scene']
    seed = info['seed']
    axes = info['axes']
    entries = info['entries']
    sc = info['sc']
    support_status = info['support_status']
    world_obstacles = info['world_obstacles']
    obstacles_file_name = info['obstacles_file_name']
    obstacles_file = info['obstacles_file']
    world_file = info['world_file']
    target_source = BACKENDS[backend]['target_source']
    px4_seed_protocol = 'agc-px4-sim-seed-v1'
    px4_seeds = {
        'own': derive_px4_sim_seed(seed, 0),
        'intruder': derive_px4_sim_seed(seed, 1),
        'warmup': derive_px4_sim_seed(seed, 3),
    }

    # 实际障碍集：从**配置文件派生** obstacles_file 读取 id（none → []；static → 配置文件全量）
    _obs_doc = yaml.safe_load(open(obstacles_file)) or {}
    obstacle_ids = [o.get('id') for o in (_obs_doc.get('obstacles') or [])]

    # 几何版本身份——配置文件路径 + 内容 sha256 + work_area + 障碍（id/pose/size）。
    # 新增 `map` / `shape` / `safety_radius`——三张地图的几何身份可在 manifest 直接区分
    # （D6 判据：「两次 run 的 geometry.sha256 不同」）；`shape` 为源形状，`size` 为**源尺寸**
    # （cylinder 为 [r, r, h]），感知侧的外接矩形降级只在派生 obstacles 文件里出现。
    geometry = info['geometry']
    geometry_block = {
        'source': info['geometry_source'],
        'map': info.get('world_map', DEFAULT_WORLD_MAP),
        'sha256': info['geometry_sha256'],
        'work_area': geometry.get('work_area'),
        'obstacles': [
            {
                'id': ob['id'],
                # 复合模型：顶层无 shape/size（由 parts 描述）；单图元照旧
                'composite': obstacle_is_composite(ob, sim_share),
                'shape': (None if obstacle_is_composite(ob, sim_share)
                          else obstacle_shape(ob, sim_share)),
                'pose': [float(ob['x']), float(ob['y']), float(ob['z']), 0.0, 0.0,
                         float(ob.get('yaw', 0.0))],
                # 单图元 = 源尺寸；复合 = 水平包络盒（与感知降级口径一致）
                'size': ([float(s) for s in ob['size']] if not obstacle_is_composite(ob, sim_share)
                         else obstacle_bbox_size(ob, sim_share)),
                'safety_radius': obstacle_safety_radius(ob, sim_share),
                'footprint_radius': obstacle_footprint_radius(ob, sim_share),
                # ADR-0010 (j)：顶面高度（垂直门控的输入），与注入安全层的值同源同值。
                'z_top': obstacle_z_top(ob, sim_share),
                'parts': ([{'id': pt['id'], 'shape': obstacle_shape(pt, sim_share),
                            'pose': [float(pt['x']), float(pt['y']), float(pt['z']), 0.0, 0.0,
                                     float(pt.get('yaw', 0.0))],
                            'size': [float(v) for v in pt['size']]}
                           for pt in world_map_module(sim_share).obstacle_parts(ob)]
                          if obstacle_is_composite(ob, sim_share) else []),
            }
            for ob in (geometry.get('obstacles') or [])
        ],
    }

    # 运行时证据：声明轴 + 承载者（状态由能力表派生）+ 实际生效参数/文件
    carriers_ledger = {}
    for ax, val in axes.items():
        st, why = coverage_status(entries[ax], backend)
        eff = {}
        if ax == 'obstacle':
            eff = {'world_obstacles': world_obstacles, 'obstacles_file': obstacles_file_name,
                   'obstacle_ids': obstacle_ids, 'world_map': info.get('world_map', DEFAULT_WORLD_MAP)}
        elif ax == 'target_motion':
            eff = {'intruder_driver.motion': merged.get('intruder_driver', {}).get('motion')}
        carriers_ledger[ax] = {'value': val, 'carrier': entries[ax].get('carrier'),
                               'status': st, 'reason': why, 'effective': eff}

    return {
        'scene': scene, 'seed': seed, 'backend': backend, 'launch': LAUNCH,
        'support_status': support_status,
        'declared_axes': axes,
        'expected_terminal': sc.get('expected_terminal'),
        'expected_reason': sc.get('expected_reason'),
        'nodes': list(BACKENDS[backend]['required_nodes']),
        'carriers': carriers_ledger,
        'effective_params': {
            'task_manager': {k: merged.get('task_manager', {}).get(k) for k in (
                'air_present', 'goal_follow_target', 'goal_x', 'goal_y', 't_max_s')},
            'intruder_driver': {k: merged.get('intruder_driver', {}).get(k) for k in (
                'motion', 'speed_mps', 'radius_m')},
            # H0（2026-11-02）：巡航高度**实际生效值 + 来源**。`cruise_alt_m` 是唯一权威输入；
            # 场景/基参未给时回落弃用别名 `alt_m`（与 intruder_driver 的解析规则同口径）。
            # 同时显式登记**该值的参考基准**，避免下游把"相对 episode 原点的增量"误当世界 ENU 高度。
            'cruise_altitude': cruise_altitude_block(merged, info, effective_spawn),
            # H0 ：空中机**观测偏航实际生效值 + 来源**（场景默认 / CLI 覆盖 / air.yaml 缺省）。
            'observe_yaw_mode': observe_yaw_block(info, air_merged, cli_observe_yaw_mode),
            # 视觉定位路径已于 2026-11-04 退役：两键**保留、值固定**（schema 不漂移；
            # 见 vision_plane_block 文件头）。
            'perception_path': 'truth',
            'vision_plane': vision_plane_block(),
            'run_logger': {'scenario': merged.get('run_logger', {}).get('scenario'), 'seed': seed},
            'target_source': target_source,
            'seed_protocol': {
                'name': px4_seed_protocol,
                'master_seed': seed,
                'px4_sim_seeds': px4_seeds,
            },
            # `sensors_file` 随 `perception` 轴退役（2026-11-06）：保留键、值固定为
            # 退役标记（规范 schema 不漂移），使新旧 run 仍可直接对比，且审查
            # 一眼能看出本 run 不使用任何传感器通道变体（而非"忘了记"）。
            'sensors_file': 'retired:perception-axis',
            'obstacles_file': obstacles_file,
            'world_obstacles': world_obstacles, 'world_file': world_file,
            # 地图（配置文件选择）与实际世界生成路径——`static` 时世界是
            # `/tmp/agc_world_static_obstacles[_<map>].sdf`，与配置文件一一对应。
            'world_map': info.get('world_map', DEFAULT_WORLD_MAP),
            'world_geometry_file': info['geometry_source'],
        },
        'geometry': geometry_block,
        'spawn_layout': spawn_layout_block(layout, layout_sha256, own_pose, effective_spawn,
                                           effective_own),
        'assertions': assertions_result,
    }


def observe_yaw_block(info=None, air_merged=None, cli_value=''):
    """`trajectory_tracker.observe_yaw_mode` 的**实际生效值 + 来源**（manifest 可追溯）。

 三级优先级（与 `main.launch.py` 的合并顺序一致，此处只做记录、不改合并）：
 CLI `observe_yaw_mode:=<mode>`（非空） > 场景 `trajectory_tracker.observe_yaw_mode`
 > `air.yaml` 缺省。

 为什么记录来源： 的证据表明 s04 的成败取决于这一项（`behind` 门）。
 只有把"本 run 到底用了哪个模式、是场景给的还是 CLI 覆盖的"写进 manifest，
 才能事后区分"场景默认生效"与"某次实验用 CLI 强制了别的臂"——否则无法复核。
    """
    scene_val = ((((info or {}).get('sc') or {}).get('params') or {})
                 .get('trajectory_tracker') or {}).get('observe_yaw_mode')
    if air_merged is None:
        # lightweight：不起空中链路，本项不适用（不冒充 air.yaml 缺省）。
        return {'effective': None, 'source': 'not_applicable(lightweight)',
                'scene_default': scene_val, 'cli_override': cli_value or None}
    base_val = (air_merged.get('trajectory_tracker') or {}).get('observe_yaw_mode')
    if cli_value:
        source = 'cli'
    elif scene_val is not None:
        source = 'scene'
    else:
        source = 'air_yaml'
    return {'effective': base_val, 'source': source,
            'scene_default': scene_val, 'cli_override': cli_value or None}



def spawn_layout_block(layout, layout_sha256=None, own_pose=None, effective_spawn=None,
                       effective_own=None):
    """出生布局证据块：文件身份 + **实际生效**位姿 + 三组距离 + 己方机起飞参考。

 `layout=None`（未注入出生布局的调用方，如历史单测）→ 返回 `None`，不改既有行为。
 `spawn` 是**消费者实际拿到的值**：车给出 `world_z`（世界 spawn，轮触地）与 `reset_z`
 （复位口径）；`spawn_source` 记该 run 的出生位来自布局配置文件（`layout`）还是场景覆盖（`scene`）。

    `effective_own`（`parse_own_pose()` 的结果）**优先**于 layout 的 own_uav：
 己方机位姿可被 launch 显式覆盖，若距离仍按 layout 算，manifest 就会自洽地"证明"一个
 并没有发生过的布局（审查第 5 条）。此处把关：`distances` 与 `own_uav` 用同一个值，
 并额外记录 `layout_own_uav` + `own_pose_source`，让"覆盖过"这件事本身可见。
    """
    if layout is None:
        return None
    own = layout['own_uav']
    if effective_spawn is not None:
        car, tgt = effective_spawn['car'], effective_spawn['target']
        src = effective_spawn.get('source')
    else:
        car, tgt, src = layout['car'], layout['target'], 'layout'
    own_eff = own
    own_src = 'layout'
    if effective_own is not None:
        own_eff = effective_own
        own_src = effective_own.get('source', 'override')
    pose_string = own_pose or own_uav_pose_string(layout, override=None if own_src == 'layout' else
                                                  '%g,%g,%g,0,0,%g' % (own_eff['x'], own_eff['y'],
                                                                        own_eff['z'], own_eff['yaw']))
    return {
        'source': layout.get('source'),
        'sha256': layout_sha256,
        'spawn_source': src,
        'own_pose_source': own_src,
        'spawn': {
            'car': {'x': car['x'], 'y': car['y'], 'yaw': car['yaw'],
                    'world_z': car['world_z'], 'reset_z': car['reset_z']},
            'target': {'x': tgt['x'], 'y': tgt['y'], 'z': tgt['z'], 'yaw': tgt['yaw']},
            'own_uav': {'x': own_eff['x'], 'y': own_eff['y'], 'z': own_eff['z'],
                        'yaw': own_eff['yaw'], 'pose_string': pose_string},
            # layout 配置文件里的 own 位（便于审查一眼看出"被覆盖了"）——不参与距离。
            'layout_own_uav': {'x': own['x'], 'y': own['y'], 'z': own['z'], 'yaw': own['yaw']},
        },
        # 距离一律按**实际生效**位算（own 用 own_eff）。
        'distances': spawn_layout_distances(
            {'car': car, 'target': tgt, 'own_uav': own_eff}),
        # F1 ：固定任务目标与其来源（`derived`=由目标出生位+偏移派生）。
        # 审查可据此核对"改了出生布局，goal 是否跟着走"，不必再去翻合并后的临时参数。
        'goal': {'x': (effective_spawn or {}).get('goal_x'),
                 'y': (effective_spawn or {}).get('goal_y'),
                 'source': (effective_spawn or {}).get('goal_source'),
                 'offset_m': layout.get('goal_offset_m')},
        'design_goals': {'car_target_min_m': 30.0, 'own_uav_target_min_m': 25.0,
                         'car_own_uav_range_m': [3.0, 8.0]},
    }


def write_temp_params(merged, backend, scene, seed, token=None):
    """把合并后参数写入临时 yaml（`w6_<backend>_<scene>_<seed>_<token>.yaml`），返回路径。"""
    token = token or new_run_token()
    doc = {node: {'ros__parameters': p} for node, p in merged.items()}
    tmp = os.path.join(tempfile.gettempdir(), 'w6_%s_%s_%d_%s.yaml' % (backend, scene, seed, token))
    with open(tmp, 'w') as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=True)
    return tmp


def write_manifest(manifest, backend, scene, seed, token=None):
    """把 manifest 写入临时 json（`w6_<backend>_manifest_<scene>_<seed>_<token>.json`），返回路径。"""
    token = token or new_run_token()
    path = os.path.join(
        tempfile.gettempdir(), 'w6_%s_manifest_%s_%d_%s.json' % (backend, scene, seed, token))
    with open(path, 'w') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    return path

