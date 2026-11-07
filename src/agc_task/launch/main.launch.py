#!/usr/bin/env python3
"""main —— 顶层统一入口（ADR-0020；backend 参数化单一入口）。

一条 `ros2 launch` 按 `backend` 组装场景：
 * backend:=lightweight（默认）—— 轻量栈：include `skeleton.launch.py`（世界 + 桥 + 感知 +
 地面链路 + 任务层 scenario_reset/task_manager/run_logger）+ `capture_adjudicator` + `jammer`；
 **无** PX4 / 空中链路。
 * backend:=full —— 双 PX4 整链：`world_bringup` + `perception_bringup` + `ground_bringup`
    (command_source=rl) + 2×uXRCE-DDS Agent（8888/8889）+ 己方 PX4(实例0) + 入侵者 PX4(实例1, attach)
 + 空中链路 4 节点 + `lifecycle_manager_air` + 任务层 5 节点 + `intruder_driver`。

场景配置解析（base/registry/carriers 加载、carrier 校验、参数合并、轴断言、manifest 生成）
**配置文件**在共享模块 `launch/composition.py`；本入口不含重复解析逻辑。约束类信息
（参数入口 / 唯一执行口 / 命名空间 / 硬约束）**只引用不复述**——约束条文见 `docs/adr/0020-package-boundaries-and-runtime-topology.md`。

用法：
  ros2 launch agc_task main.launch.py backend:=lightweight scene:=s01_static_none_nominal_track
  ros2 launch agc_task main.launch.py backend:=full scene:=s02_linear_none_nominal_track \\
 gz_args:="-s -r -v 3 <world>"
"""

import os
import sys
from pathlib import Path

from ament_index_python.packages import get_package_prefix, get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# 共享配置解析模块与本入口同目录（随包安装到 share/agc_task/launch）。
_LAUNCH_DIR = os.path.dirname(os.path.realpath(__file__))
if _LAUNCH_DIR not in sys.path:
    sys.path.insert(0, _LAUNCH_DIR)
from composition import (  # noqa: E402
    BACKENDS,
    apply_flight_altitude_params,
    apply_spawn_layout,
    apply_target_motion_override,
    assertions,
    build_manifest,
    compose_params,
    derive_px4_sim_seed,
    load_scene,
    load_spawn_layout,
    merge_air_params,
    own_uav_pose_string,
    parse_own_pose,
    px4_cmd,
    px4_paths,
    require_toolchain,
    seed_px4_run_root,
    spawn_args,
    spawn_layout_sha256,
    write_air_params,
    write_manifest,
    write_temp_params,
)


def _compose(context, *args, **kwargs):
    """顶层组装：解析输入 → 按 backend 分派（两个 backend 的**参数拼装**都在 `composition`）。"""
    ctx = _resolve(context)
    if ctx['backend'] == 'lightweight':
        return _compose_lightweight(ctx)
    return _compose_full(ctx, Path(LaunchConfiguration('agc_root').perform(context)))


def _resolve(context):
    task_share = get_package_share_directory('agc_task')
    perc_share = get_package_share_directory('agc_perception')
    sim_share = get_package_share_directory('agc_sim')
    # backend:=full 才用，但在这里**统一解析**：两个 backend 的 ctx 形状一致，
    # 避免下游 `ctx['air_share']` 在 lightweight 下 KeyError（shape 不一致是最难查的坑）。
    air_share = get_package_share_directory('agc_air')
    ground_share = get_package_share_directory('agc_ground')
    use_sim_time = LaunchConfiguration('use_sim_time')
    gz_args = LaunchConfiguration('gz_args')
    gui_render_backend = LaunchConfiguration('gui_render_backend')

    backend = LaunchConfiguration('backend').perform(context)
    # （R5/R6）：命令源单一选择由本入口透传至 ground_bringup——
    # rl（RL 主控，默认）| baseline（Navfn + 自研 LQR 离线对照基线）| train（外部训练/评估适配层作命令源）。
    command_source = LaunchConfiguration('command_source').perform(context)
    # （P1，ADR-0022）：`target_source` **覆盖**——P1 的自变量 α（协同程度）：
    # 缺省（空）= 用 backend 能力表值（**2026-11-04 起两 backend 都恒为 gt_adapter**）；
    # 显式 `gt_adapter` = 地面直取真值（空中域不参与观测 → **非协同**臂）。
    # 仅变更观测来源，余同（同场景 / seed / 安全层 / 终态 / 预算）。
    _ts = LaunchConfiguration('target_source').perform(context)
    target_source = _ts if _ts else BACKENDS[backend]['target_source']
    # （R3）：训练视图开关——显式设置时按 seed 随机化出生位（spawn 流）；缺省 None 不改既有行为。
    # 2026-11-04：`spawn_randomize` 已删除（服务已结档的 训练视图，见路线分支治理 5.3）。
    spawn_randomize = None
    # P2 v3（ADR-0023）：`goal_follow_target` 覆盖——true = 任务目标跟随**感知目标**
    # （A 与 B 同源 `/agc/targets`）；空/缺省 = 沿用场景值（不改既有场景语义）。
    _gf = LaunchConfiguration('goal_follow_target').perform(context)
    goal_follow_target = None if _gf in (None, '', 'None') else (str(_gf).lower() in ('1', 'true', 'yes'))
    if backend not in BACKENDS:
        raise RuntimeError(
            '未知 backend: %s（可用：%s）→ 拒绝运行' % (backend, list(BACKENDS)))
    scene = LaunchConfiguration('scene').perform(context)
    seed = int(LaunchConfiguration('seed').perform(context))
    # 地图（配置文件选择）——minimal（核查基线）| yard（演示主地图）| open_field。
    # 解析**两级**且只在 `load_scene` 一处实现（launch 显式非空 > 场景登记 > 缺省 minimal）；
    # 未知值在 `resolve_world_map` 内拒绝运行（不静默回退）。此处**不**先行解析空串。
    world_map = LaunchConfiguration('world_map').perform(context).strip()

    # ---- 视觉定位路径已于 2026-11-04 退役（用户裁定）----
    # 原 `perception_path` ∈ {truth, vision} / `vision_detector` / `detector_backend` 三个
    # launch 参数及其互斥校验已删除：项目不做目标识别，目标位置**始终由真值给出**
    # （ADR-0009 (a2)）。`/agc/targets` 的发布者此后**恒为 `gt_adapter`**（air_fusion 亦已退役）。
    # 己方 PX4 gz 机型：默认 gz_x500 = 既有行为逐字不变；gz_x500_mono_cam = 挂机载相机。
    px4_sim_model = (LaunchConfiguration('px4_sim_model').perform(context) or '').strip()
    if not px4_sim_model:
        raise RuntimeError('px4_sim_model 不得为空（默认 gz_x500）→ 拒绝运行')

    info = load_scene(task_share, sim_share, scene, seed, world_map=world_map)

    # `target_motion:=` CLI 覆盖（`--escape`）：必须在 **load_scene 之后、两个 backend 分支之前**
    # 一次性对齐「生效参数 / 声明轴 / 承载者」三处，否则启动期断言
    # `target_motion_effective_equals_declared` 会拿旧声明轴（s04=static）比新生效值
    # （epicycle）→ 拒绝运行（2026-11-05 实测），且 manifest 的 declared_axes / carriers
    # 会如实写成 static 而实际跑 epicycle，证据链失真。空串 = 不覆盖，既有场景语义逐值不变。
    target_motion = (LaunchConfiguration('target_motion').perform(context) or '').strip()
    apply_target_motion_override(info, info['carriers'], target_motion, backend)

    # ---------------- F1：出生布局**配置文件**（2026-10-31） ----------------
    # 车 / 目标 / 己方机的出生位只从 `config/spawn_layout.yaml` 取一次，再派生四处：
    # ① 世界 spawn（world_bringup 的 car_x/car_y/target_x/target_y —— 覆盖 car.yaml/target.yaml 缺省）；
    # ② 复位位置（scenario_reset 的同一组参数——由下方 apply_spawn_layout 显式覆盖）；
    # ③ 己方机起飞参考（`own_uav_pose_string(layout)`，同一字符串既作 PX4_GZ_MODEL_POSE 又作 origin_pose）；
    # ④ 出生净空校验坐标（scenario_reset.own_uav_x/y 由 ③ 派生，见 compose_params）。
    # 显式 launch 参数（px4_own_pose）仍可覆盖 ③（保留旧的覆盖能力），但**不再默默取默认值 0,0,0.2**。
    layout = load_spawn_layout(task_share)
    layout_sha256 = spawn_layout_sha256(task_share)
    own_pose_override = (LaunchConfiguration('px4_own_pose').perform(context) or '').strip()
    own_pose = own_uav_pose_string(layout, override=own_pose_override)
    # 实际生效的己方机位姿（**解析一次**，供净空校验 / manifest / 断言三处共用）。
    # 非法或非有限值 → 拒绝运行（不再 WARN 后按 layout 兜底：兜底会让"声明"与"实际"悄悄分叉）。
    effective_own = parse_own_pose(own_pose, layout)
    print('[w6] spawn_layout=%s sha256=%s car=(%g,%g) target=(%g,%g) own=(%s) [%s]'
          % (layout['source'], layout_sha256[:16], layout['car']['x'], layout['car']['y'],
             layout['target']['x'], layout['target']['y'], own_pose,
             effective_own['source']))


    return {
        'task_share': task_share, 'sim_share': sim_share, 'perc_share': perc_share,
        'air_share': air_share, 'ground_share': ground_share,
        'use_sim_time': use_sim_time, 'gz_args': gz_args,
        'gui_render_backend': gui_render_backend,
        'backend': backend, 'command_source': command_source,
        'target_source': target_source, 'spawn_randomize': spawn_randomize,
        'goal_follow_target': goal_follow_target, 'scene': scene, 'seed': seed,
        'world_map': world_map, 'px4_sim_model': px4_sim_model,
        'info': info, 'layout': layout, 'layout_sha256': layout_sha256,
        'own_pose': own_pose, 'effective_own': effective_own, 'context': context,
    }


def _compose_lightweight(ctx):
    """backend:=lightweight 的 actions —— 参数拼装全部经 `composition`，本函数只组装 actions。"""
    info, backend = ctx['info'], ctx['backend']
    task_share, sim_share = ctx['task_share'], ctx['sim_share']
    scene, seed = ctx['scene'], ctx['seed']
    merged = compose_params(info['base'], info['sc'], backend, seed,
                            geometry=info['geometry'],
                            spawn_randomize=ctx['spawn_randomize'],
                            goal_follow_target=ctx['goal_follow_target'])
    # ADR-0007：高度随地图派生注入（任务侧）。必须在 compose_params 之后、
    # assertions 之前——与 apply_air_geometry 的时序纪律同款。
    apply_flight_altitude_params(merged, info)
    # F1：出生位注入（场景覆盖优先；否则用布局配置文件），返回值即世界 spawn 的唯一来源。
    effective_spawn = apply_spawn_layout(merged, ctx['layout'], info['sc'])
    world_spawn_args = spawn_args(effective_spawn)
    tmp = write_temp_params(merged, backend, scene, seed)
    asserts = assertions(scene, merged, info, sim_share=sim_share, layout=ctx['layout'],
                         effective_spawn=effective_spawn, effective_own=ctx['effective_own'])
    manifest_path = write_manifest(
        build_manifest(backend, info, merged, asserts, sim_share=sim_share,
                       layout=ctx['layout'], layout_sha256=ctx['layout_sha256'],
                       own_pose=ctx['own_pose'], effective_spawn=effective_spawn,
                       effective_own=ctx['effective_own']),
        backend, scene, seed)
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(task_share, 'launch', 'skeleton.launch.py')),
            launch_arguments=dict({
                'params_file': tmp,
                'gz_args': ctx['gz_args'],
                'use_sim_time': ctx['use_sim_time'],
                'world_obstacles': info['world_obstacles'],
                'world_map': info['world_map'],
                # `sensors_file` 已于 2026-11-06 随 `perception` 轴退役，不再透传。
                # 障碍先验 / 地图几何由**配置文件派生**（不再读 agc_perception 包内副本）
                'obstacles_file': info['obstacles_file'],
                'map_file': info['derived_map_file'],
                # （ADR-0006）：世界模型文件（run_logger 记 sha256）单一注入
                'world_file': info['world_file'],
                'scene_manifest_file': manifest_path,
                # ：安全层开关透传（缺省 true；false = 无 shield 对照臂，纯仿真）
                # （P1）：观测来源——**用已解析的 `target_source`**（含 backend 能力表回退），
                # **不**直接透传 `LaunchConfiguration('target_source')`：后者在未显式给出时为
                # **空串**，会**覆盖** perception_bringup 的默认值 → gt_adapter 不发布
                # 「不发布 /agc/targets」→ 任务无目标 → TIMEOUT（实测轻量栈回归）。
                'target_source': ctx['target_source'],
            }, **world_spawn_args).items(),
        ),
        # 拦截裁决（地面侧，无需 PX4）：发射式网捕获裁决器 + 行为级干扰注入
        Node(package='agc_task', executable='capture_adjudicator',
             name='capture_adjudicator',
             parameters=[tmp, {'use_sim_time': ctx['use_sim_time']}], output='screen'),
        Node(package='agc_task', executable='jammer', name='jammer',
             parameters=[tmp, {'use_sim_time': ctx['use_sim_time']}], output='screen'),
    ]


def _full_params(ctx, agc_root):
    """backend:=full 的参数与证据准备（**不组装 actions**）；返回 dict 供 action 组装使用。"""
    info, backend = ctx['info'], ctx['backend']
    sim_share, scene, seed = ctx['sim_share'], ctx['scene'], ctx['seed']
    own_uav_x, own_uav_y = ctx['effective_own']['x'], ctx['effective_own']['y']
    merged = compose_params(info['base'], info['sc'], backend, seed, (own_uav_x, own_uav_y),
                            geometry=info['geometry'],
                            spawn_randomize=ctx['spawn_randomize'],
                            goal_follow_target=ctx['goal_follow_target'])
    # ADR-0007：高度随地图派生注入（任务侧：巡航高度 / 网弹道 / 起飞完成判据）。
    # 时序纪律：compose_params 之后、apply_spawn_layout / assertions 之前。
    apply_flight_altitude_params(merged, info)
    # F1：出生位注入（场景覆盖优先；否则用布局配置文件），返回值即世界 spawn 的唯一来源。
    effective_spawn = apply_spawn_layout(merged, ctx['layout'], info['sc'])
    world_spawn_args = spawn_args(effective_spawn)
    tmp = write_temp_params(merged, backend, scene, seed)

    # 空中链路节点参数 = air.yaml 基参 + 场景覆盖 + 几何/高度派生（**唯一**合并入口在 composition）。
    air_merged = merge_air_params(ctx['air_share'], info['sc'].get('params'),
                                  info['geometry'], sim_share=sim_share)
    air_tmp = write_air_params(air_merged, backend, scene, seed)

    # + 断言（含空中安全列表 == 配置文件）在 air 合并后做；不符即拒绝运行。
    # F1：同时断言「复位位置 == 世界 spawn」（两侧同源于 effective_spawn）。
    asserts = assertions(scene, merged, info, air_merged, sim_share=sim_share,
                         layout=ctx['layout'], effective_spawn=effective_spawn,
                         effective_own=ctx['effective_own'])
    manifest_path = write_manifest(
        build_manifest(backend, info, merged, asserts, sim_share=sim_share,
                       layout=ctx['layout'], layout_sha256=ctx['layout_sha256'],
                       own_pose=ctx['own_pose'], effective_spawn=effective_spawn,
                       effective_own=ctx['effective_own'], air_merged=air_merged,
                       cli_observe_yaw_mode='',
                       # 视觉定位路径已于 2026-11-04 退役：manifest 不再带路径/平面/后端字段
                       perception_path='truth',
                       vision_plane=None,
                       detector_backend=None),
        backend, scene, seed)
    return {'merged': merged, 'tmp': tmp, 'air_merged': air_merged,
            'air_tmp': air_tmp, 'manifest_path': manifest_path,
            'world_spawn_args': world_spawn_args, 'effective_spawn': effective_spawn}


def _px4_env(ctx, agc_root):
    """PX4 工具链路径 / 可写运行根 / 机型 env / warmup 开关（**不组装 actions**）。"""
    px4_dir, px4_build, px4_bin = px4_paths(agc_root)
    # 启动前校验工具链二进制存在（缺失即拒启动，清晰报错）。
    _missing = require_toolchain(agc_root, px4_bin)
    if _missing:
        raise RuntimeError(
            '工具链缺失，拒绝启动：%s\n请确认 agc_root 指向固定项目根（默认 /home/chen/AGC）；'
            '亦可用 agc_root:=<path> 覆盖' % ', '.join(_missing))
    # （ADR-0024）：opt-in 每实例 PX4 可写运行根。空 = 既有共享 build（默认行为逐字不变）。
    # 非空时每实例独立 `-w` 目录 + worker 私有 `etc`（rcS 末段 source 本实例的 px4-rc.params）。
    px4_run_root = LaunchConfiguration('px4_run_root').perform(ctx['context']).strip()
    px4_root = Path(px4_run_root).resolve() if px4_run_root else None
    # 播种参数初态（ADR-0024：共享 build 只读，绝不回写）。
    seed_px4_run_root(px4_root, px4_build)
    gz_models = os.path.join(px4_dir, 'Tools', 'simulation', 'gz', 'models')
    gz_worlds = os.path.join(px4_dir, 'Tools', 'simulation', 'gz', 'worlds')

    # ---- ADR-0030：机载正下视相机机型（opt-in）----
    # `gz_agc_x500_nadir` 的模型资产在**本仓** `install/agc_sim/share/agc_sim/models/agc_x500_nadir/`，
    # 不在 PX4 工具链里（工具链只读，**禁止**加 airframe）。机型解析不改工具链，走两条既有机制：
    # ① `PX4_SYS_AUTOSTART=4001` —— rcS:41-44 的该分支**优先于**按 `PX4_SIM_MODEL` 文件名反查
    # （rcS:52-63），故 rcS 仍 source 官方 `4001_gz_x500`（旋翼/参数集与默认臂完全相同），
    # 而 `PX4_SIM_MODEL` 只用于 spawn 时给 gz 的模型名；
    # ② gz 侧按 `GZBridge.cpp:73-77` 的相对路径 `agc_x500_nadir/model.sdf` 解析，靠 gz 服务器
    # 的 `GZ_SIM_RESOURCE_PATH`（world_bringup 已把 `install/agc_sim/share/agc_sim/models`
    # 追加进去）。此处再把同一目录并入**己方 PX4 进程**的 env：standalone 下虽由 gz 服务器
    # 解析，但显式给出可避免将来改成自起 gz 时静默失效。
    # **默认臂已改为 `gz_agc_x500`（2026-11-05，用户裁定）**：与 nadir 走**同一套**机制
    # （本仓 models 资源路径 + `PX4_SYS_AUTOSTART=4001`），差别只在模型名 → 本仓 `agc_x500`
    # = x500 + 纯视觉青色高亮球。`gz_x500` 仍可显式选用（此时不加路径、不注入 AUTOSTART，
    # rcS 走原「按名反查 4001_gz_x500」路径，行为与改动前逐字一致）。
    nadir_sim_model = 'gz_agc_x500_nadir'
    nadir_enabled = (ctx['px4_sim_model'] == nadir_sim_model)
    # 2026-11-05（用户裁定）：己方机 **GUI 辨识高亮**机型 `gz_agc_x500`。
    # 与 nadir 同一解析机制（本仓 models 资源路径 + PX4_SYS_AUTOSTART=4001 让 rcS 仍 source
    # 官方 `4001_gz_x500`，旋翼/参数集逐字不变），差别只在模型名指向本仓
    # `agc_x500/model.sdf` = x500 + 一个**纯视觉**青色高亮球（无 collision → 不影响物理 /
    # 接触 / 安全层）。实体名随之变为 `agc_x500_0`（GZBridge.cpp 的 `<model_sim>_<instance>`）。
    # 实测依据：默认 `gz_x500` 在 50 m 正俯视下仅约 5 px（85 m 时 3 px），用户"看不见我方机"。
    highlight_sim_model = 'gz_agc_x500'
    own_repo_model = nadir_enabled or (ctx['px4_sim_model'] == highlight_sim_model)
    own_px4_env_extra = {}
    if own_repo_model:
        own_px4_env_extra['GZ_SIM_RESOURCE_PATH'] = (
            gz_models + ':' + gz_worlds + ':' + os.path.join(ctx['sim_share'], 'models'))
        own_px4_env_extra['PX4_SYS_AUTOSTART'] = '4001'

    # ADR-0027（uXRCE 预热，可选）：own agent 的**首个** DDS participant 在发现图繁忙时可达
    # 1.5–4.9 s（> PX4 1 s 预算）。sacrificial SIH warmup 可让 agent 先付掉首次创建成本；
    # 但 A/B（A4 no-warmup 5/5 vs warmup 5/5）显示：**own 25 s 错峰后 warmup 不再必要**，
    # 故默认关闭；保留开关供极端负载 / 回退使用。warmup 自身允许 create entities failed。
    c = ctx['context']
    warmup_enable = LaunchConfiguration('px4_warmup').perform(c) == 'true'
    warmup_delay_s = float(LaunchConfiguration('px4_warmup_delay_s').perform(c))
    warmup_timeout_s = float(LaunchConfiguration('px4_warmup_timeout_s').perform(c))
    own_px4_delay_s = float(LaunchConfiguration('own_px4_delay_s').perform(c))
    intruder_px4_delay_s = float(LaunchConfiguration('intruder_px4_delay_s').perform(c))
    return {
        'px4_dir': px4_dir, 'px4_build': px4_build, 'px4_bin': px4_bin, 'px4_root': px4_root,
        'gz_models': gz_models, 'gz_worlds': gz_worlds,
        'own_px4_env_extra': own_px4_env_extra,
        'warmup_enable': warmup_enable, 'warmup_delay_s': warmup_delay_s,
        'warmup_timeout_s': warmup_timeout_s, 'own_px4_delay_s': own_px4_delay_s,
        'intruder_px4_delay_s': intruder_px4_delay_s,
        'agent0_port': LaunchConfiguration('agent0_port').perform(c),
        'agent1_port': LaunchConfiguration('agent1_port').perform(c),
        'agent_bin': str(Path(agc_root) / 'toolchain' / 'bin' / 'MicroXRCEAgent'),
    }


def _compose_full(ctx, agc_root):
    """backend:=full 的 actions —— 参数拼装经 composition，PX4 env 经 `_px4_env`，本函数只组装。"""
    info = ctx['info']
    sim_share, perc_share, ground_share = ctx['sim_share'], ctx['perc_share'], ctx['ground_share']
    seed = ctx['seed']
    use_sim_time = ctx['use_sim_time']

    p = _full_params(ctx, agc_root)
    tmp, air_tmp = p['tmp'], p['air_tmp']
    manifest_path = p['manifest_path']
    world_spawn_args = p['world_spawn_args']

    e = _px4_env(ctx, agc_root)
    px4_build, px4_root = e['px4_build'], e['px4_root']
    gz_models, gz_worlds = e['gz_models'], e['gz_worlds']
    own_px4_env_extra = e['own_px4_env_extra']
    agent_bin, agent0_port, agent1_port = e['agent_bin'], e['agent0_port'], e['agent1_port']
    own_px4_delay_s, intruder_px4_delay_s = e['own_px4_delay_s'], e['intruder_px4_delay_s']

    def _px4_cmd(instance=None):
        return px4_cmd(e['px4_bin'], px4_build, px4_root, instance)

    common = [tmp, {'use_sim_time': use_sim_time,
                    'scene_manifest_file': manifest_path, 'params_file': tmp}]
    # `origin_pose`：己方 PX4 局部系原点（世界 ENU）= 己方机 spawn 位姿（同一 launch 参数）；
    # px4_adapter（局部→世界）与 OffboardInterface（世界→局部 setpoint）共用该值。
    air_common = [air_tmp, {'use_sim_time': use_sim_time, 'origin_pose': ctx['own_pose']}]

    # 入侵者 PX4（实例 1）：attach 已生 `intruder_uav`。其进程 start 事件驱动 `intruder_driver`
    # （见下方 RegisterEventHandler）——不再用绝对时间盲计时。
    intruder_px4 = ExecuteProcess(
        cmd=_px4_cmd(1), cwd=px4_build,
        additional_env={
            'GZ_SIM_RESOURCE_PATH': gz_models + ':' + gz_worlds,
            'PX4_GZ_STANDALONE': '1', 'PX4_GZ_WORLD': 'agc_world',
            'PX4_SIM_MODEL': 'gz_x500', 'PX4_GZ_MODEL_NAME': 'intruder_uav',
            # 2026-10-20（uXRCE 实体创建失败排障）：按实例注入 **独立 agent 端口**——rcS 支持
            # `PX4_UXRCE_DDS_PORT` 覆盖（`uxrce_dds_client start -p $uxrce_dds_port`）。此前两实例
            # 都用默认 8888（8889 空置）→ 单 agent 承双客户端，约 1 s 的客户端实体创建超时更易触发
            # `create entities failed: participant: 255`（own 实例无 odom / 不收 arm）。
            'PX4_UXRCE_DDS_PORT': agent1_port,
            'AGC_PX4_SIM_SEED': str(derive_px4_sim_seed(seed, 1)),
        }, output='screen')

    # ADR-0027：sacrificial SIH warmup——只创建 participant，不参与任务。
    # `timeout` 保证它在 own PX4 启动前后被收回；warmup 自身失败不影响 own PX4。
    warmup_action = None
    if e['warmup_enable']:
        warmup_action = TimerAction(period=e['warmup_delay_s'], actions=[ExecuteProcess(
            cmd=['timeout', ('%.1f' % e['warmup_timeout_s'])] + _px4_cmd(3),
            cwd=px4_build,
            additional_env={
                'GZ_SIM_RESOURCE_PATH': gz_models + ':' + gz_worlds,
                'PX4_SIMULATOR': 'sihsim', 'PX4_SIM_MODEL': 'none',
                'PX4_UXRCE_DDS_PORT': agent0_port,
                'AGC_PX4_SIM_SEED': str(derive_px4_sim_seed(seed, 3)),
            }, output='screen')])

    actions = [
        # （ADR-0015）：运行时 PX4 failsafe 参数锁定——须在 PX4（12 s / 25 s 定时器）**之前**执行，
        # 写入 SITL 启动参数文件 `px4-rc.params`（由 rcS source），使每次 SITL 启动确定化。
        ExecuteProcess(
            cmd=['bash', str(agc_root / 'scripts' / 'lock_px4_failsafe_params.sh')],
            # 隔离模式下把锁定写入 worker 私有 etc（空 root 时保持既有共享 build 行为）。
            additional_env=({'AGC_PX4_ETC_DIR': str(px4_root / 'etc')}
                            if px4_root is not None else None),
            output='screen'),
        # PX4 模型库须先入资源路径：world_bringup 生成 `intruder_uav` 时 merge `model://x500`
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH', gz_models + ':' + gz_worlds),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(sim_share, 'launch', 'world_bringup.launch.py')),
            launch_arguments=dict({
                'gz_args': ctx['gz_args'], 'use_sim_time': use_sim_time,
                'target_controlled': 'true',
                # / ADR-0021：GUI 渲染后端由单一 launch 参数下发（auto | d3d12 | software）。
                'gui_render_backend': ctx['gui_render_backend'],
                # 按障碍轴选择世界（none 生成不含任何障碍的世界）
                'world_obstacles': info['world_obstacles'],
                # 按地图选择配置文件（minimal | yard | open_field）
                'world_map': info['world_map'],
            }, **world_spawn_args).items()),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(perc_share, 'launch', 'perception_bringup.launch.py')),
            launch_arguments={
                'use_sim_time': use_sim_time,
                # 2026-11-04：`target_source` 恒为 gt_adapter（air_fusion 退役）；仍保留透传口，
                # 因为 gt_adapter 用该参数决定自己是否发布 `/agc/targets`。
                # 2026-11-06：`sensors_file` / `perception` 轴已退役，不再透传。
                'target_source': ctx['target_source'],
                # 障碍先验 / 地图几何由**配置文件派生**（不再读 agc_perception 包内副本）
                'obstacles_file': info['obstacles_file'],
                'map_file': info['derived_map_file'],
                # 视觉定位路径已于 2026-11-04 退役（`perception_path` / `target_plane_z_m` /
                # `obstacles_source` 的 vision 特判一并删除）。`/agc/targets` 的发布者恒为 gt_adapter。
            }.items()),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(ground_share, 'launch', 'ground_bringup.launch.py')),
            launch_arguments={'use_sim_time': use_sim_time,
                              'command_source': ctx['command_source'],
                              # ：安全层开关透传（缺省 true；false = 无 shield 对照臂）
                              }.items()),
        # 两个 uXRCE-DDS Agent（实例各一，端口独立）
        ExecuteProcess(cmd=[agent_bin, 'udp4', '-p', agent0_port], output='screen'),
        ExecuteProcess(cmd=[agent_bin, 'udp4', '-p', agent1_port], output='screen'),
        *([warmup_action] if warmup_action is not None else []),
        # 己方 PX4（实例 0）：standalone，自 spawn gz_x500 自机。
        # 计时**保留**理由：属 gz 引擎 spawn 时序（世界/桥先起，PX4 才具 gz 资源与时钟）；
        # ADR-0027：默认 25 s——等 5 s warmup 完成首次 participant 创建，且让 DDS 发现图
        # 从启动风暴中稳定；12 s 实测会让 own participant 创建落入 1.5–13 s 长尾。
        # 本层仍无可达就绪信号（该 PX4 进程本身即被 spawn），故用计时 + 后续 air odom 门。
        TimerAction(period=own_px4_delay_s, actions=[ExecuteProcess(
            cmd=_px4_cmd(), cwd=px4_build,
            additional_env=dict({
                'GZ_SIM_RESOURCE_PATH': gz_models + ':' + gz_worlds,
                'PX4_GZ_STANDALONE': '1', 'PX4_GZ_WORLD': 'agc_world',
                # 己方机型由 launch 参数单一设置（默认 gz_x500 = 既有行为逐字不变）。
                # 入侵者（实例 1，attach）仍固定 gz_x500——它不参与视觉链路。
                # ADR-0030：gz_agc_x500_nadir 时另注入 PX4_SYS_AUTOSTART=4001 + 本仓 models 资源路径
                # （见上方 own_px4_env_extra；默认臂该 dict 为空 → env 与改动前逐字相同）。
                'PX4_SIM_MODEL': ctx['px4_sim_model'], 'PX4_GZ_MODEL_POSE': ctx['own_pose'],
                # 己方实例绑 agent0 端口（显式，与入侵者的 agent1 端口对称，配置文件）
                'PX4_UXRCE_DDS_PORT': agent0_port,
                'AGC_PX4_SIM_SEED': str(derive_px4_sim_seed(seed, 0)),
            }, **own_px4_env_extra), output='screen')]),
        # 入侵者 PX4（实例 1）：attach 已生 `intruder_uav`（world_bringup 于 gz+3 s spawn）。
        # ADR-0027：默认 35 s——与 own（25 s）错峰 10 s，避免两个 agent 同时创建 participant
        # 造成 1.5–3 s 级并发热点（25/25 实测 own+intruder 双双 `create entities failed`）。
        TimerAction(period=intruder_px4_delay_s, actions=[intruder_px4]),
    ]

    actions.extend(_air_and_task_actions(ctx, common, air_common, intruder_px4))
    return actions


def _air_and_task_actions(ctx, common, air_common, intruder_px4):
    """空中链路节点 + lifecycle manager + 任务层 + 入侵者驱动 + 起飞守卫（**顺序即语义**）。

    顺序敏感：lifecycle prewarm 必须在 manager 之前、intruder_driver 由 intruder_px4 的
    start 事件驱动、target_takeoff_guard 必须在最后。改动顺序会改变启动时序语义。
    """
    info = ctx['info']
    actions = []

    # 空中链路节点 + lifecycle（复用 Nav2 lifecycle_manager）
    for exe in ('px4_adapter', 'takeoff_controller', 'trajectory_tracker', 'standoff_follower'):
        actions.append(Node(package='agc_air', executable=exe, name=exe,
                            parameters=air_common, output='screen'))
    lifecycle_manager = Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
        name='lifecycle_manager_air',
        # （ADR-0019）：bond_timeout **不**无条件置 0——被管空中节点已实现 Nav2 bond
        # （topic=bond、id=节点名），故启用 bond 失联检测（被管节点死亡 → manager "IS DOWN" 硬复位）。
        parameters=[{'autostart': True, 'bond_timeout': 5.0,
                     'use_sim_time': ctx['use_sim_time'],
                     'node_names': ['px4_adapter', 'takeoff_controller',
                                    'trajectory_tracker', 'standoff_follower']}],
        output='screen')
    # ADR-0019：manager 启动前预热 lifecycle 服务连接（只读 get_state），避免其阻塞式
    # `change_state` 在 DDS 发现预热期永久挂起（实测停在 `Configuring takeoff_controller`）。
    #
    # baseline closure（2026-10-30）：**加硬超时**。原实现只有
    # `RegisterEventHandler(OnProcessExit(target_action=prewarm, on_exit=[lifecycle_manager]))`
    # 这一条**单事件依赖**——若预热进程因 rclpy 收尾竞态挂住不退出（实测：四个节点都打印
    # `ok (attempt 1)` 之后**没有**打印 `done ok=`，进程一直活着直到 SIGINT 才被强杀），
    # `OnProcessExit` 永不触发 → `lifecycle_manager_air` **从不启动** → 空中节点停在 inactive
    # → `/agc/air/odom` 无发布者 → 整链就绪超时（run_demo 报 `air_odom_fresh` 未就绪）。
    #
    # 修复只做**一件事**：用 `timeout` 给预热进程一个确定的上界，使 `OnProcessExit` 必定触发。
    # 预热本身仍是 best-effort（ADR-0019 的语义不变：它只是让 manager 的首次服务调用落在
    # 已建立的连接上；预热没跑满也不改变任何节点状态）。超时值 45 s < run_demo 的 180 s 就绪门，
    # 且远大于正常预热耗时（实测 T-A 全程数秒）。
    #
    # **必须带 `-k`**：GNU `timeout` 在只给一个时长时，到点只发 SIGTERM 然后**无限期等待**子进程；
    # 若子进程忽略 / 卡住不响应 SIGTERM，`timeout` 自己**永不返回** → `OnProcessExit` 依旧不触发
    # （修复等于没做）。 T-B 的失败形态正是"SIGINT 5 s 不退、SIGTERM 10 s 不退、只能 SIGKILL"，
    # 故单靠 `timeout N` 不成立。`-k KILL_AFTER` 使到点后 `KILL_AFTER` 秒强杀，保证进程一定退出。
    # T1 实测（本任务 ）：`timeout 3` 对忽略 TERM 的子进程**永不返回**；`timeout -k 2 3` 在 4.3 s
    # 以 rc=137 退出。故 `prewarm_timeout_s + prewarm_kill_after_s` 才是真正的上界（45 + 5 = 50 s
    # < 180 s 就绪门）。
    prewarm_timeout_s = 45
    prewarm_kill_after_s = 5
    prewarm_bin = os.path.join(
        get_package_prefix('agc_air'), 'lib', 'agc_air', 'air_lifecycle_prewarm')
    prewarm = ExecuteProcess(
        cmd=['timeout', '-k', str(prewarm_kill_after_s), str(prewarm_timeout_s), prewarm_bin,
             'px4_adapter', 'takeoff_controller', 'trajectory_tracker',
             'standoff_follower'],
        output='screen')
    actions.append(prewarm)
    actions.append(RegisterEventHandler(OnProcessExit(
        target_action=prewarm, on_exit=[lifecycle_manager])))

    # 任务层（地面侧）
    for exe in ('scenario_reset', 'task_manager', 'run_logger', 'capture_adjudicator', 'jammer'):
        # run_logger 另注入世界模型文件路径（记 sha256 作工具链 / 世界身份）
        extra = ([{'world_file': info['world_file']}] if exe == 'run_logger' else [])
        # ：安全层开关（字符串承载→节点内解析）
        if exe == 'run_logger':
            extra = extra + [{'shield_layer_enabled': True}]
            # （裁定 α+，2026-10-31）：**写盘根显式派生自 agc_root**。
            # 原来这两个键在 `base.yaml` 里写死 `/home/chen/AGC/...`，而 `run_logger.cpp` 的
            # C++ 节点默认声明也是同一字面量 → 克隆到别处跑时评测产物**写回原仓库**
            # （实测：summary 落 /home/chen/AGC/experiments/w6-task-eval/，克隆侧
            # terminal_explanation 报"未取得本轮 summary"）。
            # launch 参数在 yaml 之后生效 → 这里的值**覆盖** yaml 与 C++ 默认值。
            # `git_root` 也必须传：漏了它，summary 里的 git 身份仍读主仓。
            _agc_root = LaunchConfiguration('agc_root').perform(ctx['context'])
            extra = extra + [{
                'experiments_root': os.path.join(_agc_root, 'experiments'),
                'git_root': _agc_root,
            }]
            # 视觉定位路径已于 2026-11-04 退役：以下四个键**保留并恒写固定值**。
            # 为什么保留而不删：`summary.json` 是对外产物 schema，历史 run 都带这些键；
            # 删键会让新旧 run 不可直接对比（ADR-0009「证据必须可区分」的反面要求——
            # **schema 不得漂移**）。值恒为 `truth` / `none` / 空串，不再由 launch 参数驱动。
            extra = extra + [{
                'perception_path': 'truth',
                'detector_backend': 'none',
                'vision_model_id': 'none',
                'vision_model_name': '',
                'vision_model_version': '',
                'vision_model_sha256': '',
            }]
            # ADR-0024： 并行时 run_logger 的默认 run_id 只到秒 + 随机后缀，
            # 同秒启动的两个 worker 会撞同一 run 目录（实测 20261025...-091552-6372）。
            # episode_runner 在 worker 模式下注入含 worker id 的唯一 override。
            _rid = LaunchConfiguration('run_id_override').perform(ctx['context'])
            if _rid:
                extra = extra + [{'run_id_override': _rid}]
        params = common + extra
        actions.append(Node(package='agc_task', executable=exe, name=exe,
                            parameters=params, output='screen'))

    # 入侵者驱动：**就绪依赖**（事件驱动）替代绝对时间盲计时——入侵者 PX4 进程 start 即起
    # intruder_driver；其自身已就绪门控（无 odom 先 no-op），故无需再叠加延时。
    actions.append(RegisterEventHandler(
        OnProcessStart(target_action=intruder_px4, on_start=[
            Node(package='agc_task', executable='intruder_driver', name='intruder_driver',
                 parameters=common, output='screen')])))

    # ---- 2026-11-03：目标机"是否真的起飞"的启动期守卫 ----
    # 病灶（s04 抬高度 run `20261103-093912` 实测）：`intruder_driver` 的 odom 订阅 QoS 漏
    # `TRANSIENT_LOCAL` → 与 PX4 writer 不兼容 → 静默收不到 odom → 永不 ARM → 目标停地面
    # → 卡 AIR_SEARCH 三分钟，**全程无任何错误日志**。
    # （2026-11-03 更正：当时把它归因为"垂直差 14 m > 量程 12 m ⇒ 感知恒盲"，该**诊断特征
    # 已失效**——量程改为 30.0 后 √(26.17²+14²)=29.68 m 仍在量程内（余量 0.32 m），
    # 目标停地面时感知照样有航迹，只是钉在地面不动。**因此本守卫不能省**：它是唯一
    # 能在启动期把"目标没起飞"大声报出来的机制。）
    # 故用真值 gt_z 做**独立**守卫：未起飞就大声报 + 非零退出。
    # 阈值为**地图派生巡航高度的一半**（不在此写死第二份高度配置文件）；仅 full 后端有意义
    # （lightweight 不起空中链路，`own_uav_present=false`，目标也不由 PX4 驱动）。
    _fa_guard = (info.get('flight_altitude') or {})
    _tgt_cruise = float(_fa_guard.get('target_cruise_m') or 2.0)
    actions.append(Node(
        package='agc_task', executable='target_takeoff_guard', name='target_takeoff_guard',
        parameters=[{
            'target_gt_topic': '/agc/gt/intruder_uav',
            'result_topic': '/agc/task/target_takeoff',
            'min_takeoff_alt_m': round(_tgt_cruise * 0.5, 3),
            # 2026-11-03 实测标定：目标机从 launch 到"真正 Armed 并开始爬升"落在 **110 s 量级**
            # ——PX4 实例 1 排在 own（+25 s）之后（+35 s），EKF 收敛 + uXRCE 会话 + driver 首帧
            # odom + 反复 ARM 重试，实测 `Armed by external command` 在 tw≈110 s。
            # 原 60 s 会在这个正常时序**之前**判死（实测超时点比 ARM 成功早约 6 s），把"还没到"
            # 误报成"不会起飞"。放宽到 150 s：仍拦得住真正卡死（odom 永不到），又不与正常启动竞争。
            # 将来若再调 PX4 错峰（own_px4_delay_s / intruder_px4_delay_s），本值须同步复核。
            'startup_timeout_s': 150.0,
            'rate_hz': 10.0,
            'use_sim_time': ctx['use_sim_time'],
        }],
        output='screen'))

    # R6 演示叠加层（viz:=true）**不在此处注册** —— 唯一注册点在
    # `generate_launch_description` 末尾的顶层 `OpaqueFunction(lambda c: _viz_actions(c, sim_share))`。
    # 两处同时注册会使 `backend:=full` 把 static_tf / viz_markers / rviz2 **各起两份**
    # （lightweight 因提前 return 只命中顶层一处，故该缺陷只在 full 链显形；实测
    # full+viz 三节点各 2 份、lightweight+viz 各 1 份）。回归见
    # `scripts/tests/test_viz_registration.py`。

    return actions

def _viz_actions(context, sim_share):
    """R6（2026-10-30）演示叠加层：**GUI 纯场景 + RViz 语义层**（用户裁定）。

 `viz:=true` 时起 `viz_markers`（把 targets/obstacles转成
 `visualization_msgs/MarkerArray`）+ `rviz2`（用 `config/agc_demo.rviz` 固定布局）。
 缺省 false → 既有时序与行为**完全不变**。

 为什么不在 Gazebo GUI 里叠加：本机 `ros_gz_bridge` 不映射 `visualization_msgs`，
 叠加只能静态内联或自写桥（不可复现），而 RViz 原生支持 OccupancyGrid / Path /
 LaserScan / MarkerArray。
    """
    if (LaunchConfiguration('viz').perform(context) or '').strip().lower() not in ('true', '1'):
        return []
    from ament_index_python.packages import get_package_share_directory
    rviz_cfg = os.path.join(get_package_share_directory('agc_task'), 'config', 'agc_demo.rviz')
    # RViz 的 Fixed Frame 必须是 TF 里**存在**的帧。本项目所有话题都在 `world` 系，但
    # TF 里没有 `world` 这个帧（实测 `tf2_echo world map` 报 frame does not exist），
    # 于是 RViz 什么都不画。→ 发一条 map→world 的恒等静态变换，Fixed Frame 用 `map`。
    tf = Node(package='tf2_ros', executable='static_transform_publisher', name='world_frame_tf',
              arguments=['0', '0', '0', '0', '0', '0', 'map', 'world'], output='log')
    return [
        tf,
        Node(package='agc_task', executable='viz_markers', name='viz_markers',
             parameters=[{'use_sim_time': True,
                          'world_map': LaunchConfiguration('world_map')}], output='screen'),
        Node(package='rviz2', executable='rviz2', name='rviz2', arguments=['-d', rviz_cfg],
             parameters=[{'use_sim_time': True}], output='screen'),
    ]


def generate_launch_description():
    sim_share = get_package_share_directory('agc_sim')
    world_file = os.path.join(sim_share, 'worlds', 'agc_world.sdf')

    ld = LaunchDescription()
    ld.add_action(DeclareLaunchArgument(
        'backend', default_value='lightweight',
        description='后端：lightweight（轻量栈，无 PX4）| full（双 PX4 整链）'))
    ld.add_action(DeclareLaunchArgument(
        'scene', default_value='s01_static_none_nominal_track',
        description='场景 id（见 config/scenarios.yaml）'))
    ld.add_action(DeclareLaunchArgument('seed', default_value='0',
                                        description='episode 种子（run_logger 记录 + spawn 生成）'))
    # 地图覆盖（配置文件选择）。**缺省空** = 按场景登记解析：
    # `scenarios.yaml` 的 `world_map:` 键（s04 = yard，其余 = minimal）；显式给出
    # （minimal | yard | open_field）则强制该地图。未知值在 _compose 内拒绝运行。
    ld.add_action(DeclareLaunchArgument(
        'world_map', default_value='',
        description='地图覆盖（几何来源选择）：空=按场景登记（s04→yard，其余→minimal）；'
                    '显式 minimal | yard | open_field 则强制该地图'))
    ld.add_action(DeclareLaunchArgument(
        'run_id_override', default_value='',
        description='ADR-0024：run_logger run_id 覆盖（多 worker 唯一性；空=默认生成）'))
    # （R5/R6）：命令源单一选择（透传 ground_bringup）——
    # rl | baseline（Navfn + 自研 LQR 离线对照基线）| train（外部适配层作命令源，仅 lightweight）。
    ld.add_action(DeclareLaunchArgument(
        'command_source', default_value='rl',
        description='命令源（互斥）：rl（RL 主控）| baseline（离线对照基线）| train（外部适配层）'))
    # （R3）：训练视图——按 seed 随机化出生位；缺省空（不改既有 行为）。
    # 2026-11-04 清退：`spawn_randomize`（训练视图）已删除。
    # 2026-11-04 清退：`shield` 主链开关已删除——**安全层恒定启用**。
    # 无 shield 消融臂属 研究（ADR-0023 已结档），须在 `scripts/research/` 里自带参数，
    # 不得在主链开"关安全层"的口子（演示/验收永远不该关）。
    ld.add_action(DeclareLaunchArgument(
        'target_source', default_value='',
        description='观测来源覆盖（空=用 backend 能力表值，恒为 gt_adapter；air_fusion 已退役）'))
    # ---- 2026-11-04 用户裁定清退的路线分支（见 docs/conventions/路线分支治理.md 5.3）----
    # `observe_yaw_mode` / `air_tracking_ref` / `standoff_safe_max` 三个 launch 参数已删除：
    # * 前两者服务已结档的 对照实验（ADR-0023: P1 inconclusive / P2 falsified）；
    # * `standoff_safe_max` 是零调用方的死参数。
    # 偏航模式与站距带此后**只由 `air.yaml` 配置文件**决定（不再有 run 级覆盖口）。
    # 研究复跑若需要旧行为，改 `air.yaml` 或研究脚本自带的参数文件，**不得**在主链开回覆盖口。
    # `goal_follow_target` **不属于**上述清退集合：它是任务语义参数（目标移动时任务目标是否
    # 跟随，ADR-0001 / ADR-0013），见路线分支治理 5.1 台账「不删」。s02/s03 等活跃场景依赖
    # 场景值；本覆盖口空 = 沿用场景值（不改既有场景语义）。2026-11-05 修复：此前清退时
    # 误删本声明而 `_compose` 仍引用，导致 ros2 launch 解析期抛
    # `launch configuration 'goal_follow_target' does not exist`，整链无法启动。
    ld.add_action(DeclareLaunchArgument(
        'goal_follow_target', default_value='',
        description='任务目标是否跟随感知目标（任务语义参数，非路线分支）：'
                    '空=沿用场景值；true=跟随 /agc/targets；false=固定任务目标'))
    ld.add_action(DeclareLaunchArgument(
        'target_motion', default_value='',
        description='目标运动覆盖：空=场景默认；static|linear|maneuver|epicycle'))
    ld.add_action(DeclareLaunchArgument('use_sim_time', default_value='true'))
    ld.add_action(DeclareLaunchArgument(
        'gz_args', default_value=['-r -v 3 ', world_file],
        description='gz sim 参数（加 -s 可无头）'))
    ld.add_action(DeclareLaunchArgument(
        'viz', default_value='false',
        description='R6 演示叠加层：true = 起 viz_markers + rviz2（GUI 保持纯场景；'
                    '缺省 false，既有时序不变）'))
    ld.add_action(DeclareLaunchArgument(
        'gui_render_backend', default_value='auto',
        description='GUI 渲染后端：auto（WSL2 + /dev/dxg + X11 自动 D3D12）| d3d12 | software；'
                    'headless（gz -s）忽略'))
    ld.add_action(DeclareLaunchArgument(
        'px4_own_pose', default_value='',
        description='己方机 spawn 位（world ENU，逗号分隔；**空 = 取自出生布局文件** '
                    'config/spawn_layout.yaml 的 own_uav 段）。该字符串同时用作 '
                    'PX4_GZ_MODEL_POSE 与空中节点 origin_pose（局部系原点），故"起飞参考"与'
                    '"净空校验坐标"不可能不一致。仅 backend:=full 生效。'))
    ld.add_action(DeclareLaunchArgument(
        'agent0_port', default_value='8888', description='uXRCE-DDS Agent 端口（仅 backend:=full）'))
    ld.add_action(DeclareLaunchArgument(
        'agent1_port', default_value='8889', description='uXRCE-DDS Agent 端口（仅 backend:=full）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_warmup', default_value='false',
        description='ADR-0027：可选 sacrificial SIH warmup（true/false；默认 false——25/35 错峰已足够）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_warmup_delay_s', default_value='5.0',
        description='ADR-0027：warmup PX4 启动延时（s；默认在 own PX4 之前完成首次 participant 创建）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_warmup_timeout_s', default_value='6.5',
        description='ADR-0027：warmup PX4 运行上限（s；timeout 收回，不参与任务）'))
    ld.add_action(DeclareLaunchArgument(
        'own_px4_delay_s', default_value='25.0',
        description='ADR-0027：own PX4 启动延时（s；默认 25 s，等 warmup 完成 + 发现图稳定）'))
    ld.add_action(DeclareLaunchArgument(
        'intruder_px4_delay_s', default_value='35.0',
        description='ADR-0027：intruder PX4 启动延时（s；默认 35 s，与 own 错峰 10 s）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_run_root', default_value='',
        description='ADR-0024：PX4 每实例可写运行根（空=既有共享 build 行为）'))
    ld.add_action(DeclareLaunchArgument(
        'agc_root', default_value='/home/chen/AGC',
        description='固定项目根（AGENTS.md；colcon 根即项目根）；工具链在其下 toolchain/'))
    # 视觉定位路径已于 2026-11-04 退役：`perception_path` / `vision_detector` /
    # `vision_model_*` / `detector_backend` 六个 launch 参数一并删除（项目不做目标识别，
    # 目标位置始终由真值给出，ADR-0009 (a2)）。summary.json 的对应键保留恒写固定值。
    ld.add_action(DeclareLaunchArgument(
        'px4_sim_model', default_value='gz_agc_x500',
        description='2026-11-05：己方 PX4 机型。**默认 gz_agc_x500** = 本仓 `agc_x500`'
                    '（PX4 官方 x500 + 纯视觉青色高亮球；无 collision，物理/接触/安全层不受影响）'
                    '——因默认 gz_x500 在 50 m 正俯视下仅约 5 px，GUI 里看不见我方机。'
                    '其余可选：gz_x500（PX4 官方原厂，无高亮）；gz_x500_mono_cam（机载前视相机）；'
                    'gz_agc_x500_nadir（机载**正下视**相机，ADR-0030，仅取证/测绘、无消费者）'))
    ld.add_action(OpaqueFunction(function=_compose))
    ld.add_action(OpaqueFunction(function=lambda c: _viz_actions(c, sim_share)))
    return ld
