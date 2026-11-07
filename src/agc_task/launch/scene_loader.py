#!/usr/bin/env python3
"""scene_loader —— 场景定义加载：backend 能力表、承载者校验、轴覆盖与参数合并。

三件事，且只有这三件：
 * `BACKENDS` —— **backend 能力表**：每 backend 声明 `air_link` / `px4` / `target_source` /
   `required_nodes`（完整展开节点名）/ `supported_axes`；`coverage_status` 的 `not_carried`
   状态**由能力表派生**（不再逐文件硬编码「轻量栈无空中链路」）。
 * `load_scene` —— 读 `scenarios.yaml` + `scenario_carriers.yaml`，校验声明轴**必有承载者**，
   并按域写出派生文件（感知障碍先验 / 地图几何）。
 * `compose_params` —— base → 场景覆盖的合并，再注入几何派生量。
"""

import os
import tempfile

import yaml

from scene_common import new_run_token
from scene_geometry import (
    DEFAULT_WORLD_MAP,
    geometry_ids,
    geometry_path,
    geometry_sha256,
    geometry_xs,
    geometry_ys,
    load_geometry,
    obstacle_bbox_size,
    obstacle_shape,
    resolve_world_map,
    work_area_bounds,
)



# backend 能力表：每 backend 声明能力事实，驱动覆盖状态派生与 manifest 节点展开。
# * air_link —— 是否含空中链路（PX4 / 空中节点）；False → requires_air_link 承载者 not_carried。
# * px4 —— 是否起 PX4 SITL 实例。
# * target_source —— 感知轴目标源。**2026-11-04 起恒为 `gt_adapter`**（air_fusion 已退役）。
# * required_nodes —— 该 backend 完整展开的节点 / 进程名（manifest `nodes` 字段）。
# * supported_axes —— 该 backend 实际执行的轴（不含即如实标注 not_carried / N/A）。
BACKENDS = {
    'lightweight': {
        'air_link': False,
        'px4': False,
        'target_source': 'gt_adapter',
        'required_nodes': [
            'world_bringup', 'ros_gz_bridge', 'set_pose_bridge',
            'perception_bringup', 'ground_bringup',
            'scenario_reset', 'task_manager', 'run_logger',
            'capture_adjudicator', 'jammer',
        ],
        # 轻量栈无 PX4 / 空中链路：仅承载地面侧轴（obstacle / outcome）。
        'supported_axes': ['obstacle', 'outcome'],
    },
    'full': {
        'air_link': True,
        'px4': True,
        'target_source': 'gt_adapter',   # 2026-11-04：air_fusion 退役，与 lightweight 一致
        'required_nodes': [
            'world_bringup', 'ros_gz_bridge', 'set_pose_bridge',
            'perception_bringup', 'ground_bringup',
            'uxrce_dds_agent0', 'uxrce_dds_agent1', 'px4_own', 'px4_intruder',
            'px4_adapter', 'takeoff_controller', 'trajectory_tracker', 'standoff_follower',
            'lifecycle_manager_air',
            'scenario_reset', 'task_manager', 'run_logger',
            'capture_adjudicator', 'jammer', 'intruder_driver',
        ],
        # 整链承载 3 轴（obstacle / outcome + target_motion 的空中侧）。
        # `perception` 轴已于 2026-11-06 退役（无消费者的 sensors_file 通道变体），不再登记。
        'supported_axes': ['obstacle', 'outcome', 'target_motion'],
    },
}


def derive_px4_sim_seed(master_seed, instance):
    """Derive a stable per-PX4 simulation seed from the experiment seed.

 The PX4 processes are outside Python's RNG graph, so passing the experiment
 seed only to ``scenario_reset`` is insufficient. Keep this small integer
 mixer here as the single launch-side derivation used by both PX4 instances
 and the run manifest.
    """
    z = (int(master_seed) + 0x9E3779B9 + int(instance) * 0x85EBCA6B) & 0xFFFFFFFF
    z = ((z ^ (z >> 16)) * 0x85EBCA6B) & 0xFFFFFFFF
    z = ((z ^ (z >> 13)) * 0xC2B2AE35) & 0xFFFFFFFF
    return (z ^ (z >> 16)) & 0xFFFFFFFF


def carrier_entry(carriers, axis, value, scene):
    """声明轴值必须有承载者；无承载者 → 显式拒绝运行（不以命名当执行；ADR-0018）。"""
    ent = (carriers.get(axis) or {}).get(value)
    if ent is None:
        raise RuntimeError(
            '场景 %s 声明 %s=%s：scenario_carriers.yaml 无承载者登记 → 拒绝运行' % (
                scene, axis, value))
    if not ent.get('supported', False):
        raise RuntimeError(
            '场景 %s 声明 %s=%s 无承载者（%s）→ 拒绝运行（不支持轴，不以命名推定已覆盖）' % (
                scene, axis, value, ent.get('reason', 'unsupported')))
    return ent


def coverage_status(entry, backend):
    """承载者状态：**由 backend 能力表派生**——需空中链路而该 backend 无 → not_carried。

不再硬编码 `backend == 'lightweight'`，而以 `BACKENDS[backend]['air_link']` 判定。
    """
    if entry.get('requires_air_link') and not BACKENDS[backend]['air_link']:
        return 'not_carried', 'backend=%s 无空中链路 / PX4（能力表 air_link=False），承载者不生效' % (
            backend,)
    return 'covered', ''


# `epicycle` 的标定参数（配置文件 = s18 / ADR-0031 §(a)）。
# CLI 覆盖到 epicycle 时必须一并对齐：base 的 `radius_m=6.0` 会让位移上界
# A+r = 6.6 m ≫ d_track 3.0 → 必然 RANGE_EXCEEDED / TIMEOUT（s04 继承的是 base，
# 不是 s18 的场景覆盖）。此处只收**与 base 不同**的项，避免复制第二份数值配置文件。
EPICYCLE_PARAMS = {'radius_m': 1.8}


def apply_target_motion_override(info, carriers, motion, backend):
    """`target_motion:=` CLI 覆盖：把**本 run 的目标运动轴**整条链一次性对齐。

 `target_motion` 是 `scenario_carriers.yaml` 登记的**场景轴取值**（static/linear/
 maneuver/epicycle），不是路线分支（治理 2.1「场景轴」排除项）。CLI 覆盖的是该轴在
 本 run 的取值，因此必须同步三处，缺一处就会"实际跑 epicycle、声明/manifest 写 static"：

 1. `info['sc'].params.intruder_driver.motion` —— 实际注入节点参数（compose_params 读它）；
 2. `info['axes']['target_motion']` —— 声明轴（assertions / build_manifest 读它）；
 3. `info['entries']['target_motion']` —— 承载者登记（carriers 台账读它）。

 `epicycle` 额外补齐 `EPICYCLE_PARAMS`（radius_m=1.8）：ADR-0031 §(a) 的
 `A+r+goal_tol=2.70 < d_track 3.0` 只在 r=1.8 时成立；s04 继承 base 的 r=6.0，
 不补齐就是必然 TIMEOUT。**不做**静默回落：这些是数值参数，不是路线分支。

    为什么必须重取承载者：`carrier_entry()` 会在 `load_scene` 里按**原**声明轴校验，
 覆盖后轴值变了，须按新值重新校验「有登记 / supported / 该 backend 承载」。

 无覆盖（空串）时**逐值不改**：默认启动、历史研究脚本的既有场景语义完全不变。

 轻量栈无 `intruder_driver`（`supported_axes` 不含 `target_motion`），显式覆盖一律
    **拒绝运行**，而不是悄悄忽略——否则 `--escape` 在 lightweight 下会静默不逃逸。
    """
    if not motion:
        return info
    if 'target_motion' not in BACKENDS[backend]['supported_axes']:
        raise RuntimeError(
            'backend=%s 不承载 target_motion 轴（无 intruder_driver）：'
            'target_motion:=%s 无法生效 → 拒绝运行（不静默忽略）' % (backend, motion))
    if motion not in ('static', 'linear', 'maneuver', 'epicycle'):
        raise RuntimeError('未知 target_motion：%s' % motion)
    scene = info['scene']
    drv = info['sc'].setdefault('params', {}).setdefault('intruder_driver', {})
    drv['motion'] = motion
    if motion == 'epicycle':
        drv.update(EPICYCLE_PARAMS)
    info['axes'] = dict(info['axes'])
    info['axes']['target_motion'] = motion
    info['entries'] = dict(info['entries'])
    info['entries']['target_motion'] = carrier_entry(carriers, 'target_motion', motion, scene)
    return info


def write_derived_obstacles(geometry, mode, scene, seed, token=None, sim_share=None):
    """由几何源文件派生**感知障碍先验文件**（`obstacles.yaml` 形态），返回 (路径, id 列表)。

 `static` → 配置文件障碍实体（`id/x/y/z/yaw/size`）；`none` → 空数组（与「无障碍世界」一致）。
 w6 路径**不再**读 agc_perception 包内副本（副本仅作 standalone 回退）。
`size` 取**感知可表达尺寸**——box 原值、cylinder 降级为外接矩形
 （`obstacle_bbox_size`；感知障碍模型是 OBB，无圆柱分支，降级为保守外扩）。
    """
    token = token or new_run_token()
    if mode == 'static':
        obstacles = [{
            'id': ob['id'], 'x': float(ob['x']), 'y': float(ob['y']), 'z': float(ob['z']),
            'yaw': float(ob.get('yaw', 0.0)), 'size': obstacle_bbox_size(ob, sim_share),
            # 形状透传（消费方当前只吃 box 尺寸，此处如实登记源形状以便审计；
            # 不新增感知语义、不改既有字段顺序）
            'shape': obstacle_shape(ob, sim_share),
        } for ob in (geometry.get('obstacles') or [])]
    elif mode == 'none':
        obstacles = []
    else:
        raise RuntimeError('未知障碍模式 %s（可用：static | none）→ 拒绝运行' % mode)
    path = os.path.join(tempfile.gettempdir(), 'w6_derived_obstacles_%s_%d_%s.yaml' % (scene, seed, token))
    with open(path, 'w') as f:
        yaml.safe_dump({'obstacles': obstacles}, f, allow_unicode=True, sort_keys=True)
    return path, [o['id'] for o in obstacles]


def write_derived_map(geometry, scene, seed, token=None):
    """由几何源文件 `work_area` 派生**感知地图几何文件**（`map.yaml` 形态），返回路径。"""
    token = token or new_run_token()
    wa = geometry['work_area']
    doc = {'resolution': float(wa['resolution']), 'size_x': float(wa['size_x']),
           'size_y': float(wa['size_y']), 'origin_x': float(wa['origin_x']),
           'origin_y': float(wa['origin_y'])}
    path = os.path.join(tempfile.gettempdir(), 'w6_derived_map_%s_%d_%s.yaml' % (scene, seed, token))
    with open(path, 'w') as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=True)
    return path


def load_scene(task_share, sim_share, scene, seed, token=None,
               world_map=None):
    """加载场景配置：base / registry / carriers，校验 scene 存在与 support_status，逐轴取承载者。

 返回结构化 dict（含 base / sc / axes / support_status / entries 与按轴选择的文件路径）；
额外返回配置文件（`geometry` / `geometry_sha256`）与**按域派生文件**
 （`derived_obstacles_file` / `derived_map_file`）。
地图解析**两级**（优先级从高到低）：
 1. `world_map` 参数**显式非空** → 用它（launch `world_map:=` 覆盖；未知值拒绝运行）；
 2. 否则用**场景登记**的 `sc.world_map`（`scenarios.yaml` 的 `world_map:` 键）；
 3. 都没有 → `DEFAULT_WORLD_MAP`（minimal）。
 返回的 `world_map_source` 记明来源（`launch` / `scene` / `default`），供 manifest 审计。
    """
    token = token or new_run_token()
    base = yaml.safe_load(open(os.path.join(task_share, 'config', 'base.yaml')))
    registry = yaml.safe_load(open(os.path.join(task_share, 'config', 'scenarios.yaml')))
    carriers = yaml.safe_load(
        open(os.path.join(task_share, 'config', 'scenario_carriers.yaml')))['axes']
    scenes = registry.get('scenes', {})
    if scene not in scenes:
        raise RuntimeError('unknown scene: %s; available=%s' % (scene, list(scenes)))
    sc = scenes[scene] or {}
    axes = sc.get('axes') or {}
    support_status = sc.get('support_status', 'supported')

    # 地图选择（launch 覆盖 > 场景登记 > 缺省）；未知值一律拒绝运行。
    requested = (world_map or '').strip()
    if requested:
        map_name, map_source = resolve_world_map(requested, sim_share), 'launch'
    elif (sc.get('world_map') or '').strip():
        map_name, map_source = resolve_world_map(sc['world_map'], sim_share), 'scene'
    else:
        map_name, map_source = DEFAULT_WORLD_MAP, 'default'

    # 启动时校验：每个声明轴值必须有承载者（obstacle=dynamic → 拒绝运行）
    entries = {ax: carrier_entry(carriers, ax, val, scene) for ax, val in axes.items()}
    if str(support_status).startswith('unsupported'):
        raise RuntimeError(
            '场景 %s support_status=%s（声明轴无承载者）→ 拒绝运行' % (scene, support_status))

    # 按轴选择承载者文件（`perception` 轴已于 2026-11-06 退役，不再有 sensors_file）
    obstacles_file_name = entries['obstacle']['obstacles_file']
    world_obstacles = entries['obstacle']['world_obstacles']

    # 配置文件 + 按域派生（感知障碍先验 / 感知地图）。障碍文件改由配置文件派生，
    # 不再读 agc_perception 包内副本。：配置文件文件由 `world_map` 决定。
    _, geom_source = geometry_path(sim_share, map_name)
    geometry = load_geometry(sim_share, map_name)
    geometry_hash = geometry_sha256(sim_share, map_name)
    derived_obstacles_file, derived_obstacles_ids = write_derived_obstacles(
        geometry, world_obstacles, scene, seed, token, sim_share=sim_share)
    derived_map_file = write_derived_map(geometry, scene, seed, token)
    world_file = os.path.join(sim_share, 'worlds', 'agc_world.sdf')

    return {
        'scene': scene, 'seed': seed,
        'base': base, 'sc': sc, 'axes': axes,
        # carriers 随 info 带出：CLI 覆盖场景轴时须按新轴值重取承载者（配置文件，不二次读盘）。
        'carriers': carriers,
        'support_status': support_status, 'entries': entries,
        'obstacles_file_name': obstacles_file_name,
        'world_obstacles': world_obstacles,
        'world_map': map_name,
        'world_map_source': map_source,
        'obstacles_file': derived_obstacles_file,          # 派生路径（非包内副本）
        'derived_obstacles_file': derived_obstacles_file,
        'derived_obstacles_ids': derived_obstacles_ids,
        'derived_map_file': derived_map_file,
        'geometry': geometry,
        'geometry_source': geom_source,
        'geometry_sha256': geometry_hash,
        'world_file': world_file,
    }


def compose_params(base, sc, backend, seed, own_uav=(0.0, 0.0), geometry=None,
                   spawn_randomize=None, goal_follow_target=None):
    """合并参数（base + 场景覆盖）并按 backend 注入运行模式。

 lightweight：`task_manager.air_present=False`（无空中域，相位复位门禁不适用）。
 full：`task_manager.air_present=True` + `scenario_reset.own_uav_present/x/y`（己方机在场 + 出生净空校验透传）。
 seed 经 launch 单一覆盖（run_logger 记录 + scenario_reset 生成 spawn， 可复现）。
 `spawn_randomize`：`None` = 不改（沿用 base / 场景值）；显式 `True/False` = 覆盖——
 训练视图按 seed 随机化出生位（spawn 流），缺省 `None` → 既有 行为不变。
`scenario_reset` 障碍清单 / 作业区边界由**单一配置文件**注入（base 不再硬编码几何）。
    """
    merged = {node: dict(sec.get('ros__parameters', {})) for node, sec in base.items()}
    for node, over in (sc.get('params') or {}).items():
        merged.setdefault(node, {}).update(over)
    if backend == 'lightweight':
        # 轻量栈不起空中链路：task_manager 显式声明无空中域，不得由服务缺席推定。
        merged['task_manager']['air_present'] = False
    else:
        # 整链起真实空中链路：相位复位门禁强制。
        merged['task_manager']['air_present'] = True
        # 己方机在出生净空校验中视为在场（显式运行模式），并透传其 spawn 位（world ENU）。
        merged['scenario_reset']['own_uav_present'] = True
        merged['scenario_reset']['own_uav_x'] = own_uav[0]
        merged['scenario_reset']['own_uav_y'] = own_uav[1]
    merged['run_logger']['seed'] = seed
    merged['scenario_reset']['spawn_seed'] = seed
    # （R3）：训练视图按 seed 随机化出生位（显式覆盖；缺省 None → 沿用 base / 场景值）。
    if spawn_randomize is not None:
        merged['scenario_reset']['spawn_randomize'] = bool(spawn_randomize)
    # P2 v3（ADR-0023）：任务目标是否跟随感知目标——显式覆盖场景值（None=不改）。
    if goal_follow_target is not None:
        merged.setdefault('task_manager', {})['goal_follow_target'] = bool(goal_follow_target)
    # 静态障碍清单 + 作业区边界由**配置文件**派生注入（物理世界为 static 时注入 pole_*）。
    if geometry is not None:
        merged['scenario_reset']['obstacle_names'] = geometry_ids(geometry)
        merged['scenario_reset']['obstacle_x'] = geometry_xs(geometry)
        merged['scenario_reset']['obstacle_y'] = geometry_ys(geometry)
        merged['scenario_reset'].update(work_area_bounds(geometry))
    return merged
