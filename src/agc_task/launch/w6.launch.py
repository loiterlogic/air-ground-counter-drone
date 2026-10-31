#!/usr/bin/env python3
"""w6 —— W6 顶层统一入口（结构评审 S-05；ADR-0061；backend 参数化单一入口）。

一条 `ros2 launch` 按 `backend` 组装 W6 场景：
  * backend:=lightweight（默认）—— 轻量栈：include `m0_skeleton.launch.py`（世界 + 桥 + 感知 +
    地面链路 + 任务层 scenario_reset/task_manager/run_logger）+ `capture_adjudicator` + `jammer`；
    **无** PX4 / 空中链路。
  * backend:=full —— 双 PX4 整链：`world_bringup` + `perception_bringup` + `ground_bringup`
    (command_source=rl) + 2×uXRCE-DDS Agent（8888/8889）+ 己方 PX4(实例0) + 入侵者 PX4(实例1, attach)
    + 空中链路 4 节点 + `lifecycle_manager_air` + 任务层 5 节点 + `intruder_driver`。

场景配置解析（base/registry/carriers 加载、carrier 校验、参数合并、轴断言、manifest 生成）
**单一真源**在共享模块 `launch/w6_composition.py`；本入口不含重复解析逻辑。约束类信息
（参数入口 / 唯一执行口 / 命名空间 / 硬约束）**只引用不复述**——真源 `docs/ROS2迁移交接文档.md`。

用法：
  ros2 launch agc_task w6.launch.py backend:=lightweight scene:=s01_static_none_nominal_track
  ros2 launch agc_task w6.launch.py backend:=full scene:=s02_linear_none_nominal_track \\
    gz_args:="-s -r -v 3 <world>"
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

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
from w6_composition import (  # noqa: E402
    BACKENDS,
    apply_air_geometry,
    assertions,
    build_manifest,
    compose_params,
    derive_px4_sim_seed,
    load_scene,
    new_run_token,
    write_manifest,
    write_temp_params,
)


def _compose(context, *args, **kwargs):
    task_share = get_package_share_directory('agc_task')
    perc_share = get_package_share_directory('agc_perception')
    sim_share = get_package_share_directory('agc_sim')
    use_sim_time = LaunchConfiguration('use_sim_time')
    gz_args = LaunchConfiguration('gz_args')
    gui_render_backend = LaunchConfiguration('gui_render_backend')

    backend = LaunchConfiguration('backend').perform(context)
    # W7-a（R5/R6）：命令源单一选择由本入口透传至 ground_bringup——
    #   rl（RL 主控，默认）| baseline（Navfn + 自研 LQR 离线对照基线）| train（W7 外部训练/评估适配层作命令源）。
    command_source = LaunchConfiguration('command_source').perform(context)
    # W7-b（P1，ADR-0070(a)）：`target_source` **覆盖**——P1 的自变量 α（协同程度）：
    #   缺省（空）= 用 backend 能力表值（full → air_fusion = 空地**协同观测**）；
    #   显式 `gt_adapter` = 地面直取真值（空中域不参与观测 → **非协同**臂）。
    #   仅变更观测来源，余同（同场景 / seed / 安全层 / 终态 / 预算）。
    _ts = LaunchConfiguration('target_source').perform(context)
    target_source = _ts if _ts else BACKENDS[backend]['target_source']
    # W7-a（R3）：训练视图开关——显式设置时按 seed 随机化出生位（spawn 流）；缺省 None 不改既有行为。
    _sr = LaunchConfiguration('spawn_randomize').perform(context)
    spawn_randomize = None if _sr in (None, '', 'None') else (str(_sr).lower() in ('1', 'true', 'yes'))
    # W7-b P2 v3（ADR-0083）：`goal_follow_target` 覆盖——true = 任务目标跟随**感知目标**
    #   （A 与 B 同源 `/agc/targets`）；空/缺省 = 沿用场景值（不改既有场景语义）。
    _gf = LaunchConfiguration('goal_follow_target').perform(context)
    goal_follow_target = None if _gf in (None, '', 'None') else (str(_gf).lower() in ('1', 'true', 'yes'))
    if backend not in BACKENDS:
        raise RuntimeError(
            '未知 backend: %s（可用：%s）→ 拒绝运行' % (backend, list(BACKENDS)))
    scene = LaunchConfiguration('scene').perform(context)
    seed = int(LaunchConfiguration('seed').perform(context))
    # P1-1：地图（几何真源选择）——minimal（核查基线）| yard（演示主地图）| open_field。
    # 解析**两级**且只在 `load_scene` 一处实现（launch 显式非空 > 场景登记 > 缺省 minimal）；
    # 未知值在 `resolve_world_map` 内拒绝运行（不静默回退）。此处**不**先行解析空串。
    world_map = LaunchConfiguration('world_map').perform(context).strip()

    # ---- P1-4（ADR-0103）：感知路径 + 己方机型——**单一设置**，默认行为逐字不变 ----
    # `perception_path` ∈ {truth, vision}：truth = 既有真值派生链（ADR-0020，默认）；
    #   vision = 新增视觉路径（相机 → 识别 → 检测）。两条路径**互斥**，不得同一 run 内混跑。
    #   本入口只做**透传与合法性校验**：不改任务编排、终态、安全参数；不改 9 消息 ABI。
    perception_path = (LaunchConfiguration('perception_path').perform(context) or '').strip()
    if perception_path not in ('truth', 'vision'):
        raise RuntimeError(
            '未知 perception_path=%r（可用：truth | vision）→ 拒绝运行'
            '（空串不作默认猜测，见 ADR-0103）' % (perception_path,))
    # truth 路径**不得**接视觉识别节点：显式拒绝，避免"以为互斥、其实两路都在跑"。
    # vision 路径下真值派生链（gt_bypass/air_perception/air_fusion）保持不变（目标源仍按场景/backend 决定），
    # 区别只在于**决策输入**由识别结果承担——本轮 vision 不接管决策（见 round-2 报告口径）。
    _vd = LaunchConfiguration('vision_detector').perform(context)
    vision_detector_on = (str(_vd).strip().lower() in ('1', 'true', 'yes'))
    if perception_path == 'truth' and vision_detector_on:
        raise RuntimeError(
            'perception_path=truth 时不得启用 vision_detector:=true → 拒绝运行'
            '（truth / vision 互斥，ADR-0103）')
    if perception_path == 'vision' and not vision_detector_on:
        raise RuntimeError(
            'perception_path=vision 时必须显式 vision_detector:=true → 拒绝运行'
            '（不静默降级为 truth）')
    # 己方 PX4 gz 机型（P1-4）：默认 gz_x500 = 既有行为逐字不变；gz_x500_mono_cam = 挂机载相机。
    px4_sim_model = (LaunchConfiguration('px4_sim_model').perform(context) or '').strip()
    if not px4_sim_model:
        raise RuntimeError('px4_sim_model 不得为空（默认 gz_x500）→ 拒绝运行')

    info = load_scene(task_share, perc_share, sim_share, scene, seed, world_map=world_map)

    # ---------------- backend:=lightweight ----------------
    if backend == 'lightweight':
        merged = compose_params(info['base'], info['sc'], backend, seed,
                                geometry=info['geometry'], spawn_randomize=spawn_randomize, goal_follow_target=goal_follow_target)
        tmp = write_temp_params(merged, backend, scene, seed)
        asserts = assertions(scene, merged, info, sim_share=sim_share)
        manifest_path = write_manifest(
            build_manifest(backend, info, merged, asserts, sim_share=sim_share),
            backend, scene, seed)
        return [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(task_share, 'launch', 'm0_skeleton.launch.py')),
                launch_arguments={
                    'params_file': tmp,
                    'gz_args': gz_args,
                    'use_sim_time': use_sim_time,
                    'world_obstacles': info['world_obstacles'],
                    'world_map': info['world_map'],
                    'sensors_file': info['sensors_file'],
                    # S-06：障碍先验 / 地图几何由**真源派生**（不再读 agc_perception 包内副本）
                    'obstacles_file': info['obstacles_file'],
                    'map_file': info['derived_map_file'],
                    # R-029（ADR-0044）：世界模型文件（run_logger 记 sha256）单一注入
                    'world_file': info['world_file'],
                    'scene_manifest_file': manifest_path,
                    # W7-b（T1/E1）：安全层开关透传（缺省 true；false = 无 shield 对照臂，纯仿真）
                    'shield': LaunchConfiguration('shield'),
                    # W7-b（P1）：观测来源——**用已解析的 `target_source`**（含 backend 能力表回退），
                    # **不**直接透传 `LaunchConfiguration('target_source')`：后者在未显式给出时为
                    # **空串**，会**覆盖** perception_bringup 的默认值 → gt_adapter/air_fusion 均
                    # 「不发布 /agc/targets」→ 任务无目标 → TIMEOUT（实测轻量栈回归）。
                    'target_source': target_source,
                    'seed': LaunchConfiguration('seed'),
                }.items(),
            ),
            # W6 拦截裁决（地面侧，无需 PX4）：发射式网捕获裁决器 + 行为级干扰注入
            Node(package='agc_task', executable='capture_adjudicator',
                 name='capture_adjudicator',
                 parameters=[tmp, {'use_sim_time': use_sim_time}], output='screen'),
            Node(package='agc_task', executable='jammer', name='jammer',
                 parameters=[tmp, {'use_sim_time': use_sim_time}], output='screen'),
        ]

    # ---------------- backend:=full ----------------
    air_share = get_package_share_directory('agc_air')
    ground_share = get_package_share_directory('agc_ground')
    # S-11：项目根**显式注入**（launch 参数 agc_root，默认固定根 /home/chen/AGC），
    # 不再由包 share 目录深度上溯推断；ROS 资产仍经 ament index（get_package_share_directory）。
    agc_root = Path(LaunchConfiguration('agc_root').perform(context))

    own_pose = LaunchConfiguration('px4_own_pose').perform(context)
    # R-014：己方机 spawn 位（world ENU）透传给 scenario_reset 做出生净空校验
    try:
        own_parts = [float(v) for v in own_pose.split(',')]
        own_uav_x, own_uav_y = own_parts[0], own_parts[1]
    except (ValueError, IndexError):
        print('WARN: w6 px4_own_pose 解析失败 %r → 按 (0,0) 处理' % (own_pose,))
        own_uav_x, own_uav_y = 0.0, 0.0
    agent0_port = LaunchConfiguration('agent0_port').perform(context)
    agent1_port = LaunchConfiguration('agent1_port').perform(context)
    # ADR-0094（uXRCE 预热，可选）：own agent 的**首个** DDS participant 在发现图繁忙时可达
    #   1.5–4.9 s（> PX4 1 s 预算）。sacrificial SIH warmup 可让 agent 先付掉首次创建成本；
    #   但 A/B（A4 no-warmup 5/5 vs warmup 5/5）显示：**own 25 s 错峰后 warmup 不再必要**，
    #   故默认关闭；保留开关供极端负载 / 回退使用。warmup 自身允许 create entities failed。
    warmup_enable = LaunchConfiguration('px4_warmup').perform(context) == 'true'
    warmup_delay_s = float(LaunchConfiguration('px4_warmup_delay_s').perform(context))
    warmup_timeout_s = float(LaunchConfiguration('px4_warmup_timeout_s').perform(context))
    own_px4_delay_s = float(LaunchConfiguration('own_px4_delay_s').perform(context))
    intruder_px4_delay_s = float(LaunchConfiguration('intruder_px4_delay_s').perform(context))

    merged = compose_params(info['base'], info['sc'], backend, seed, (own_uav_x, own_uav_y),
                            geometry=info['geometry'], spawn_randomize=spawn_randomize, goal_follow_target=goal_follow_target)
    tmp = write_temp_params(merged, backend, scene, seed)

    # R-026：空中链路节点参数 = air.yaml 基参 + scenarios.yaml 场景覆盖**合并后注入**
    air_base = yaml.safe_load(open(os.path.join(air_share, 'config', 'air.yaml')))
    air_merged = {n: dict(sec.get('ros__parameters', {})) for n, sec in air_base.items()}
    for n, over in (info['sc'].get('params') or {}).items():
        if n in air_merged:
            air_merged[n].update(over)
    # W7-b（P1，甲方案）：空中机**观测偏航**覆盖——P1 自变量 α 的另一半落地（与 `target_source` 并列）：
    #   缺省（空）= 用 air.yaml 默认 `velocity`（机头随速度 = 非协同观测）；
    #   显式 `target` = 机头/相机**对准目标**（= 空地协同观测）。仅此一处自变量不同，余全同。
    _oy = LaunchConfiguration('observe_yaw_mode').perform(context)
    if _oy:
        air_merged.setdefault('trajectory_tracker', {})['observe_yaw_mode'] = _oy
    # W7-b（P1 公平性修正）：`air_tracking_ref:=off` → 空中机**固定航迹**（不订阅目标跟踪参考）——
    #   tracker 永不 `acquired_`，故**不**会触发「已获目标后永久 hold 停机」（契约 C10 的自保语义
    #   保持不变，只改变**本臂是否喂入跟踪参考**）。用于 P1 非协同臂（对应 ADR-0070「空中固定航迹」），
    #   避免该臂因观测丢失而停机自锁 → 使「观测指向」成为真正被隔离的自变量。
    if LaunchConfiguration('air_tracking_ref').perform(context) == 'off':
        air_merged.setdefault('trajectory_tracker', {})['tracking_ref_topic'] = \
            '/agc/air/tracking_ref__inactive_p1_fixed_traj'
    # S-06：静态障碍几何由**真源**注入空中安全列表（obstacle_names/x/y；半径 / margin 仍来自 air.yaml）。
    apply_air_geometry(air_merged, info['geometry'], sim_share=sim_share)
    air_doc = {n: {'ros__parameters': p} for n, p in air_merged.items()}
    air_tmp = os.path.join(tempfile.gettempdir(),
                           'w6_%s_air_%s_%d_%s.yaml' % (backend, scene, seed, new_run_token()))
    with open(air_tmp, 'w') as f:
        yaml.safe_dump(air_doc, f, allow_unicode=True, sort_keys=True)

    # R-026 + S-06 断言（含空中安全列表 == 真源）在 air 合并后做；不符即拒绝运行。
    asserts = assertions(scene, merged, info, air_merged, sim_share=sim_share)
    manifest_path = write_manifest(
        build_manifest(backend, info, merged, asserts, sim_share=sim_share),
        backend, scene, seed)

    px4_dir = str(agc_root / 'toolchain' / 'PX4-Autopilot')
    px4_build = os.path.join(px4_dir, 'build', 'px4_sitl_default')
    px4_bin = os.path.join(px4_build, 'bin', 'px4')
    # W7-c（ADR-0095）：opt-in 每实例 PX4 可写运行根。空 = 既有共享 build（默认行为逐字不变）。
    #   非空时每实例独立 `-w` 目录 + worker 私有 `etc`（rcS 末段 source 本实例的 px4-rc.params）。
    px4_run_root = LaunchConfiguration('px4_run_root').perform(context).strip()
    px4_root = Path(px4_run_root).resolve() if px4_run_root else None
    if px4_root is not None:
        # PX4 v1.15.4 显式 `-w` 时不自动追加实例号 → 每个实例目录显式给出。
        if not (px4_root / 'etc').exists():
            shutil.copytree(Path(px4_build) / 'etc', px4_root / 'etc')
        for _inst in (0, 1, 3):
            (px4_root / ('instance_%d' % _inst)).mkdir(parents=True, exist_ok=True)

    def _px4_cmd(instance=None):
        """PX4 启动命令；空 root 时与原命令逐字一致（默认路径不变）。"""
        if px4_root is None:
            if instance is None:
                return [px4_bin, '-d', '-s', 'etc/init.d-posix/rcS']
            return [px4_bin, '-i', str(instance), '-d', '-s', 'etc/init.d-posix/rcS']
        cmd = [px4_bin]
        if instance is not None:
            cmd += ['-i', str(instance)]
        # `-w` = 可写运行目录（dataman / parameters*.bson / log / eeprom 均落此）；
        # 末尾 positional data_path = 私有 etc 绝对路径（PX4 在 cwd 建 `etc -> data_path` 符号链接，
        # 使相对的 `-s etc/init.d-posix/rcS` 解析到本实例私有 etc）。
        cmd += ['-w', str(px4_root / ('instance_%d' % (instance or 0)))]
        cmd += ['-d', '-s', 'etc/init.d-posix/rcS', str(px4_root / 'etc')]
        return cmd

    agent_bin = str(agc_root / 'toolchain' / 'bin' / 'MicroXRCEAgent')
    # S-11：启动前校验工具链二进制存在（缺失即拒启动，清晰报错）。
    _required = [agc_root / 'toolchain' / 'bin' / 'MicroXRCEAgent', Path(px4_bin)]
    _missing = [str(p) for p in _required if not p.exists()]
    if _missing:
        raise RuntimeError(
            '工具链缺失，拒绝启动：%s\n请确认 agc_root 指向固定项目根（默认 /home/chen/AGC）；'
            '亦可用 agc_root:=<path> 覆盖' % ', '.join(_missing))
    gz_models = os.path.join(px4_dir, 'Tools', 'simulation', 'gz', 'models')
    gz_worlds = os.path.join(px4_dir, 'Tools', 'simulation', 'gz', 'worlds')

    common = [tmp, {'use_sim_time': use_sim_time,
                    'scene_manifest_file': manifest_path, 'params_file': tmp}]
    # `origin_pose`（R-003）：己方 PX4 局部系原点（世界 ENU）= 己方机 spawn 位姿（同一 launch 参数）；
    # px4_adapter（局部→世界）与 OffboardInterface（世界→局部 setpoint）共用该值。
    air_common = [air_tmp, {'use_sim_time': use_sim_time, 'origin_pose': own_pose}]

    # 入侵者 PX4（实例 1）：attach 已生 `intruder_uav`。其进程 start 事件驱动 `intruder_driver`
    # （见下方 RegisterEventHandler）——不再用绝对时间盲计时。
    intruder_px4 = ExecuteProcess(
        cmd=_px4_cmd(1), cwd=px4_build,
        additional_env={
            'GZ_SIM_RESOURCE_PATH': gz_models + ':' + gz_worlds,
            'PX4_GZ_STANDALONE': '1', 'PX4_GZ_WORLD': 'agc_world',
            'PX4_SIM_MODEL': 'gz_x500', 'PX4_GZ_MODEL_NAME': 'intruder_uav',
            # 2026-10-20（uXRCE 实体创建失败排障）：按实例注入 **独立 agent 端口**——rcS 支持
            #   `PX4_UXRCE_DDS_PORT` 覆盖（`uxrce_dds_client start -p $uxrce_dds_port`）。此前两实例
            #   都用默认 8888（8889 空置）→ 单 agent 承双客户端，约 1 s 的客户端实体创建超时更易触发
            #   `create entities failed: participant: 255`（own 实例无 odom / 不收 arm）。
            'PX4_UXRCE_DDS_PORT': agent1_port,
            'AGC_PX4_SIM_SEED': str(derive_px4_sim_seed(seed, 1)),
        }, output='screen')

    # ADR-0094：sacrificial SIH warmup——只创建 participant，不参与任务。
    #   `timeout` 保证它在 own PX4 启动前后被收回；warmup 自身失败不影响 own PX4。
    warmup_action = None
    if warmup_enable:
        warmup_action = TimerAction(period=warmup_delay_s, actions=[ExecuteProcess(
            cmd=['timeout', ('%.1f' % warmup_timeout_s)] + _px4_cmd(3),
            cwd=px4_build,
            additional_env={
                'GZ_SIM_RESOURCE_PATH': gz_models + ':' + gz_worlds,
                'PX4_SIMULATOR': 'sihsim', 'PX4_SIM_MODEL': 'none',
                'PX4_UXRCE_DDS_PORT': agent0_port,
                'AGC_PX4_SIM_SEED': str(derive_px4_sim_seed(seed, 3)),
            }, output='screen')])

    actions = [
        # R-019（ADR-0034）：运行时 PX4 failsafe 参数锁定——须在 PX4（12 s / 25 s 定时器）**之前**执行，
        # 写入 SITL 启动参数文件 `px4-rc.params`（由 rcS source），使每次 SITL 启动确定化。
        ExecuteProcess(
            cmd=['bash', str(agc_root / 'scripts' / 'lock_px4_failsafe_params.sh')],
            # W7-c：隔离模式下把锁定写入 worker 私有 etc（空 root 时保持既有共享 build 行为）。
            additional_env=({'AGC_PX4_ETC_DIR': str(px4_root / 'etc')}
                            if px4_root is not None else None),
            output='screen'),
        # PX4 模型库须先入资源路径：world_bringup 生成 `intruder_uav` 时 merge `model://x500`
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH', gz_models + ':' + gz_worlds),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(sim_share, 'launch', 'world_bringup.launch.py')),
            launch_arguments={
                'gz_args': gz_args, 'use_sim_time': use_sim_time,
                'target_controlled': 'true',
                # W8 / ADR-0096：GUI 渲染后端由单一 launch 参数下发（auto | d3d12 | software）。
                'gui_render_backend': gui_render_backend,
                # R-026：按障碍轴选择世界（none 生成不含任何障碍的世界）
                'world_obstacles': info['world_obstacles'],
                # P1-1：按地图选择几何真源（minimal | yard | open_field）
                'world_map': info['world_map'],
            }.items()),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(perc_share, 'launch', 'perception_bringup.launch.py')),
            launch_arguments={
                'use_sim_time': use_sim_time,
                # R-026：整链以 air_fusion 承载感知轴 + 按轴选择通道 / 障碍文件
                # W7-b（P1）：`target_source` 可被 launch 覆盖（协同=air_fusion / 非协同=gt_adapter）
                'target_source': target_source,
                'seed': LaunchConfiguration('seed'),
                'sensors_file': info['sensors_file'],
                # S-06：障碍先验 / 地图几何由**真源派生**（不再读 agc_perception 包内副本）
                'obstacles_file': info['obstacles_file'],
                'map_file': info['derived_map_file'],
            }.items()),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(ground_share, 'launch', 'ground_bringup.launch.py')),
            launch_arguments={'use_sim_time': use_sim_time,
                              'command_source': command_source,
                              # W7-b（T1/E1）：安全层开关透传（缺省 true；false = 无 shield 对照臂）
                              'shield': LaunchConfiguration('shield')}.items()),
        # 两个 uXRCE-DDS Agent（实例各一，端口独立）
        ExecuteProcess(cmd=[agent_bin, 'udp4', '-p', agent0_port], output='screen'),
        ExecuteProcess(cmd=[agent_bin, 'udp4', '-p', agent1_port], output='screen'),
        *([warmup_action] if warmup_action is not None else []),
        # 己方 PX4（实例 0）：standalone，自 spawn gz_x500 自机。
        # 计时**保留**理由：属 gz 引擎 spawn 时序（世界/桥先起，PX4 才具 gz 资源与时钟）；
        # ADR-0094：默认 25 s——等 5 s warmup 完成首次 participant 创建，且让 DDS 发现图
        #   从启动风暴中稳定；12 s 实测会让 own participant 创建落入 1.5–13 s 长尾。
        #   本层仍无可达就绪信号（该 PX4 进程本身即被 spawn），故用计时 + 后续 air odom 门。
        TimerAction(period=own_px4_delay_s, actions=[ExecuteProcess(
            cmd=_px4_cmd(), cwd=px4_build,
            additional_env={
                'GZ_SIM_RESOURCE_PATH': gz_models + ':' + gz_worlds,
                'PX4_GZ_STANDALONE': '1', 'PX4_GZ_WORLD': 'agc_world',
                # P1-4：己方机型由 launch 参数单一设置（默认 gz_x500 = 既有行为逐字不变）。
                #   入侵者（实例 1，attach）仍固定 gz_x500——它不参与视觉链路。
                'PX4_SIM_MODEL': px4_sim_model, 'PX4_GZ_MODEL_POSE': own_pose,
                # 己方实例绑 agent0 端口（显式，与入侵者的 agent1 端口对称，单一来源）
                'PX4_UXRCE_DDS_PORT': agent0_port,
                'AGC_PX4_SIM_SEED': str(derive_px4_sim_seed(seed, 0)),
            }, output='screen')]),
        # 入侵者 PX4（实例 1）：attach 已生 `intruder_uav`（world_bringup 于 gz+3 s spawn）。
        # ADR-0094：默认 35 s——与 own（25 s）错峰 10 s，避免两个 agent 同时创建 participant
        #   造成 1.5–3 s 级并发热点（25/25 实测 own+intruder 双双 `create entities failed`）。
        TimerAction(period=intruder_px4_delay_s, actions=[intruder_px4]),
    ]

    # 空中链路节点 + lifecycle（复用 Nav2 lifecycle_manager）
    for exe in ('px4_adapter', 'takeoff_controller', 'trajectory_tracker', 'standoff_follower'):
        actions.append(Node(package='agc_air', executable=exe, name=exe,
                            parameters=air_common, output='screen'))
    lifecycle_manager = Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
        name='lifecycle_manager_air',
        # R-034（ADR-0049）：bond_timeout **不**无条件置 0——被管空中节点已实现 Nav2 bond
        #   （topic=bond、id=节点名），故启用 bond 失联检测（被管节点死亡 → manager "IS DOWN" 硬复位）。
        parameters=[{'autostart': True, 'bond_timeout': 5.0, 'use_sim_time': use_sim_time,
                     'node_names': ['px4_adapter', 'takeoff_controller',
                                    'trajectory_tracker', 'standoff_follower']}],
        output='screen')
    # ADR-0080：manager 启动前预热 lifecycle 服务连接（只读 get_state），避免其阻塞式
    # `change_state` 在 DDS 发现预热期永久挂起（实测停在 `Configuring takeoff_controller`）。
    #
    # P1-4 baseline closure（2026-10-30）：**加硬超时**。原实现只有
    # `RegisterEventHandler(OnProcessExit(target_action=prewarm, on_exit=[lifecycle_manager]))`
    # 这一条**单事件依赖**——若预热进程因 rclpy 收尾竞态挂住不退出（实测：四个节点都打印
    # `ok (attempt 1)` 之后**没有**打印 `done ok=`，进程一直活着直到 SIGINT 才被强杀），
    # `OnProcessExit` 永不触发 → `lifecycle_manager_air` **从不启动** → 空中节点停在 inactive
    # → `/agc/air/odom` 无发布者 → 整链就绪超时（run_demo 报 `air_odom_fresh` 未就绪）。
    #
    # 修复只做**一件事**：用 `timeout` 给预热进程一个确定的上界，使 `OnProcessExit` 必定触发。
    # 预热本身仍是 best-effort（ADR-0080 的语义不变：它只是让 manager 的首次服务调用落在
    # 已建立的连接上；预热没跑满也不改变任何节点状态）。超时值 45 s < run_demo 的 180 s 就绪门，
    # 且远大于正常预热耗时（实测 T-A 全程数秒）。
    #
    # **必须带 `-k`**：GNU `timeout` 在只给一个时长时，到点只发 SIGTERM 然后**无限期等待**子进程；
    # 若子进程忽略 / 卡住不响应 SIGTERM，`timeout` 自己**永不返回** → `OnProcessExit` 依旧不触发
    # （修复等于没做）。round-5 T-B 的失败形态正是"SIGINT 5 s 不退、SIGTERM 10 s 不退、只能 SIGKILL"，
    # 故单靠 `timeout N` 不成立。`-k KILL_AFTER` 使到点后 `KILL_AFTER` 秒强杀，保证进程一定退出。
    # T1 实测（本任务 round-2）：`timeout 3` 对忽略 TERM 的子进程**永不返回**；`timeout -k 2 3` 在 4.3 s
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

    # W6 任务层（地面侧）
    for exe in ('scenario_reset', 'task_manager', 'run_logger', 'capture_adjudicator', 'jammer'):
        # R-029：run_logger 另注入世界模型文件路径（记 sha256 作工具链 / 世界身份）
        extra = ([{'world_file': info['world_file']}] if exe == 'run_logger' else [])
        # W7-b（T1/E1）：安全层开关（字符串承载→节点内解析）
        if exe == 'run_logger':
            extra = extra + [{'shield_layer_enabled': LaunchConfiguration('shield')}]
            # P2-1 round-9（裁定 α+，2026-10-31）：**写盘根显式派生自 agc_root**。
            # 原来这两个键在 `w6_base.yaml` 里写死 `/home/chen/AGC/...`，而 `run_logger.cpp` 的
            # C++ 节点默认声明也是同一字面量 → 克隆到别处跑时评测产物**写回原仓库**
            # （round-8 实测：summary 落 /home/chen/AGC/experiments/w6-task-eval/，克隆侧
            #  terminal_explanation 报"未取得本轮 summary"）。
            # launch 参数在 yaml 之后生效 → 这里的值**覆盖** yaml 与 C++ 默认值。
            # `git_root` 也必须传：漏了它，summary 里的 git 身份仍读主仓。
            _agc_root = LaunchConfiguration('agc_root').perform(context)
            extra = extra + [{
                'experiments_root': os.path.join(_agc_root, 'experiments'),
                'git_root': _agc_root,
            }]
            # P1-4（ADR-0103）：感知路径 + 视觉模型标识——**新增键**，既有字段语义不变。
            #   summary.json 据此可区分 truth / vision 产物（ADR-0103「证据必须可区分」）。
            _vm = LaunchConfiguration('vision_model_id').perform(context)
            extra = extra + [{
                'perception_path': perception_path,
                'vision_model_id': str(_vm or 'none'),
                'vision_model_name': str(
                    LaunchConfiguration('vision_model_name').perform(context) or ''),
                'vision_model_version': str(
                    LaunchConfiguration('vision_model_version').perform(context) or ''),
                'vision_model_sha256': str(
                    LaunchConfiguration('vision_model_sha256').perform(context) or ''),
            }]
            # ADR-0077：W7-c 并行时 run_logger 的默认 run_id 只到秒 + 随机后缀，
            #   同秒启动的两个 worker 会撞同一 run 目录（实测 20261025...-091552-6372）。
            #   episode_runner 在 worker 模式下注入含 worker id 的唯一 override。
            _rid = LaunchConfiguration('run_id_override').perform(context)
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

    # P1-4（ADR-0103）：视觉识别节点**不在本入口编排内**（见 round-2 派工单的白名单口径——
    #   本入口只做 `px4_sim_model` / `perception_path` 的**透传与互斥校验**，不改任务编排）。
    #   识别进程按工具域独立起（`scripts/vision/vision_detector.py`），经话题交互；
    #   `vision_detector:=true` 只是**声明**"本次 run 的 vision 路径由外部识别进程承担"，
    #   其与 `perception_path` 的一致性由上面的互斥校验保证（truth + true → 拒绝运行）。

    # R6 演示叠加层（viz:=true）**不在此处注册** —— 唯一注册点在
    # `generate_launch_description` 末尾的顶层 `OpaqueFunction(lambda c: _viz_actions(c, sim_share))`。
    # 两处同时注册会使 `backend:=full` 把 static_tf / viz_markers / rviz2 **各起两份**
    # （lightweight 因提前 return 只命中顶层一处，故该缺陷只在 full 链显形；P1-2 round-1 实测
    # full+viz 三节点各 2 份、lightweight+viz 各 1 份）。回归见
    # `scripts/tests/test_w6_viz_registration.py`。
    return actions


def _viz_actions(context, sim_share):
    """R6（2026-10-30）演示叠加层：**GUI 纯场景 + RViz 语义层**（用户裁定）。

    `viz:=true` 时起 `viz_markers`（把 targets/obstacles/安全圆盘/8 字参考转成
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
        description='W6 后端：lightweight（轻量栈，无 PX4）| full（双 PX4 整链）'))
    ld.add_action(DeclareLaunchArgument(
        'scene', default_value='s01_static_none_nominal_track',
        description='场景 id（见 config/scenarios.yaml）'))
    ld.add_action(DeclareLaunchArgument('seed', default_value='0',
                                        description='episode 种子（run_logger 记录 + spawn 生成）'))
    # P1-1：地图覆盖（几何真源选择）。**缺省空** = 按场景登记解析：
    #   `scenarios.yaml` 的 `world_map:` 键（s04 = yard，其余 = minimal）；显式给出
    #   （minimal | yard | open_field）则强制该地图。未知值在 _compose 内拒绝运行。
    ld.add_action(DeclareLaunchArgument(
        'world_map', default_value='',
        description='地图覆盖（几何真源选择）：空=按场景登记（s04→yard，其余→minimal）；'
                    '显式 minimal | yard | open_field 则强制该地图'))
    ld.add_action(DeclareLaunchArgument(
        'run_id_override', default_value='',
        description='ADR-0077：run_logger run_id 覆盖（W7-c worker 唯一性；空=默认生成）'))
    # W7-a（R5/R6）：命令源单一选择（透传 ground_bringup）——
    #   rl | baseline（Navfn + 自研 LQR 离线对照基线）| train（W7 外部适配层作命令源，仅 lightweight）。
    ld.add_action(DeclareLaunchArgument(
        'command_source', default_value='rl',
        description='命令源（互斥）：rl（RL 主控）| baseline（离线对照基线）| train（W7 外部适配层）'))
    # W7-a（R3）：训练视图——按 seed 随机化出生位；缺省空（不改既有 W6 行为）。
    ld.add_action(DeclareLaunchArgument(
        'spawn_randomize', default_value='',
        description='W7 训练视图：spawn 随机化开关（空=不改既有行为；true/false=显式覆盖）'))
    # W7-b（T1/E1，ADR-0070(d)）：安全层开关——缺省 true（既有行为不变）；false = 无 shield 对照臂（纯仿真）。
    ld.add_action(DeclareLaunchArgument(
        'shield', default_value='true',
        description='安全层开关：true=起 collision_monitor（默认）；'
                    'false=无 shield 对照臂（恒等透传，纯仿真，不用于部署）'))
    ld.add_action(DeclareLaunchArgument(
        'target_source', default_value='',
        description='W7-b P1：观测来源覆盖（空=用 backend 能力表值；air_fusion=协同；gt_adapter=非协同）'))
    ld.add_action(DeclareLaunchArgument(
        'observe_yaw_mode', default_value='',
        description='W7-b P1（甲）：空中机观测偏航模式（空=air.yaml 默认 velocity；target=机头对准目标）'))
    ld.add_action(DeclareLaunchArgument(
        'air_tracking_ref', default_value='on',
        description='W7-b P1：空中机**是否使用目标跟踪参考**（on=协同臂：空中机跟随目标；'
                    'off=固定航迹臂：仅飞基础图-8，不订阅 /agc/air/tracking_ref）'))
    # W7-b P2 v3（ADR-0083）：任务目标是否跟随感知目标；空=沿用场景值（不改既有场景语义）。
    ld.add_action(DeclareLaunchArgument(
        'goal_follow_target', default_value='',
        description='W7-b P2 v3：true=task_manager 目标跟随 /agc/targets（A/B 同源感知目标）；'
                    '空=沿用场景值（s08 缺省 false=固定任务目标）'))
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
        'px4_own_pose', default_value='0,0,0.2,0,0,0',
        description='己方机 spawn 位（world ENU；仅 backend:=full 生效）'))
    ld.add_action(DeclareLaunchArgument(
        'agent0_port', default_value='8888', description='uXRCE-DDS Agent 端口（仅 backend:=full）'))
    ld.add_action(DeclareLaunchArgument(
        'agent1_port', default_value='8889', description='uXRCE-DDS Agent 端口（仅 backend:=full）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_warmup', default_value='false',
        description='ADR-0094：可选 sacrificial SIH warmup（true/false；默认 false——25/35 错峰已足够）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_warmup_delay_s', default_value='5.0',
        description='ADR-0094：warmup PX4 启动延时（s；默认在 own PX4 之前完成首次 participant 创建）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_warmup_timeout_s', default_value='6.5',
        description='ADR-0094：warmup PX4 运行上限（s；timeout 收回，不参与任务）'))
    ld.add_action(DeclareLaunchArgument(
        'own_px4_delay_s', default_value='25.0',
        description='ADR-0094：own PX4 启动延时（s；默认 25 s，等 warmup 完成 + 发现图稳定）'))
    ld.add_action(DeclareLaunchArgument(
        'intruder_px4_delay_s', default_value='35.0',
        description='ADR-0094：intruder PX4 启动延时（s；默认 35 s，与 own 错峰 10 s）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_run_root', default_value='',
        description='W7-c：PX4 每实例可写运行根（空=既有共享 build 行为）'))
    ld.add_action(DeclareLaunchArgument(
        'agc_root', default_value='/home/chen/AGC',
        description='固定项目根（AGENTS.md；colcon 根即项目根）；工具链在其下 toolchain/'))
    # ---- P1-4（ADR-0103）：感知路径与己方机型——默认 = 既有行为，逐字不变 ----
    ld.add_action(DeclareLaunchArgument(
        'perception_path', default_value='truth',
        description='感知路径（互斥，ADR-0103）：truth（默认，真值派生链）| vision（相机→识别→检测）'))
    ld.add_action(DeclareLaunchArgument(
        'vision_detector', default_value='false',
        description='P1-4：本次 run 的 vision 路径是否由外部识别进程承担；'
                    'true 时要求 perception_path=vision（truth+true → 拒绝运行，防静默混用）'))
    ld.add_action(DeclareLaunchArgument(
        'vision_model_id', default_value='none',
        description='P1-4：识别模型标识（none = 无模型 → 显式降级空检测）；写入 summary.json'))
    ld.add_action(DeclareLaunchArgument(
        'vision_model_name', default_value='', description='P1-4：识别模型名称（写入 summary）'))
    ld.add_action(DeclareLaunchArgument(
        'vision_model_version', default_value='', description='P1-4：识别模型版本（写入 summary）'))
    ld.add_action(DeclareLaunchArgument(
        'vision_model_sha256', default_value='', description='P1-4：识别模型权重哈希（写入 summary）'))
    ld.add_action(DeclareLaunchArgument(
        'px4_sim_model', default_value='gz_x500',
        description='P1-4：己方 PX4 机型（默认 gz_x500 无相机；gz_x500_mono_cam 挂机载前视相机）'))
    ld.add_action(OpaqueFunction(function=_compose))
    ld.add_action(OpaqueFunction(function=lambda c: _viz_actions(c, sim_share)))
    return ld
