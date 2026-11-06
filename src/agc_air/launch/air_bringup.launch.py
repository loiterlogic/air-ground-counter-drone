#!/usr/bin/env python3
"""air_bringup —— 空中链路一键启动。

一条 `ros2 launch` 起：agc_world（唯一 gz server，经 agc_sim/world_bringup）+ uXRCE-DDS Agent
+ PX4 SITL（`PX4_GZ_STANDALONE=1`、`PX4_GZ_WORLD=agc_world`、`PX4_SIM_MODEL=gz_x500`（launch 参数
`px4_sim_model` 可换 `gz_x500_mono_cam` 挂机载相机，），
由 PX4 自身 gz_bridge 向 `/world/agc_world/create` spawn 机型）+ 空中链路节点。

参数配置文件：`config/air.yaml`（契约 [参数入口]）。链路连接层（agent 地址 / 端口 / PX4 目录）
集中在此文件与 launch 参数 —— 实机替换只动这一处（spec R11，薄抽象）。
"""

import os
import sys
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
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _generate(context, *args, **kwargs):
    share = get_package_share_directory('agc_air')
    sim_share = get_package_share_directory('agc_sim')
    perception_share = get_package_share_directory('agc_perception')
    seed = LaunchConfiguration('seed')
    # 项目根**显式注入**（launch 参数 agc_root，默认固定根 /home/chen/AGC），
    # 不再由包 share 目录深度上溯推断；ROS 资产仍经 ament index。
    agc_root = Path(LaunchConfiguration('agc_root').perform(context))

    params_file = os.path.join(share, 'config', 'air.yaml')
    # （ADR-0007）：静态障碍几何来自**配置文件**，注入空中安全列表
    # （`trajectory_tracker.safety.obstacle_*`）；air.yaml 不再硬编码几何。
    # 配置文件按**地图**分文件——`world_map`（minimal | yard | open_field）选文件；
    # 清单与形状规范化在 `agc_sim/launch/world_map.py`（**单一实现**，本文件不复制表）。
    sys.path.insert(0, os.path.join(sim_share, 'launch'))
    import world_map as agc_world_map  # noqa: E402  （与 world_bringup 同目录安装）
    map_name, geom_path = agc_world_map.geometry_path(
        sim_share, LaunchConfiguration('world_map').perform(context))
    geometry = yaml.safe_load(open(geom_path))
    # 安全半径亦按障碍派生（消除旧的定长列表）；五数组等长由 SafetyShield 启动期校验。
    # ADR-0010「垂直门控」：`obstacle_z_top` = 各实体顶面高度（复合体取 part 最大值），
    # 供安全层在"本机已高于该障碍顶面 + c_clear"时**不施加**其水平圆盘。
    fa = geometry.get('flight_altitude') or {}
    safety_geometry = {
        'safety.obstacle_names': [o['id'] for o in geometry['obstacles']],
        'safety.obstacle_x': [float(o['x']) for o in geometry['obstacles']],
        'safety.obstacle_y': [float(o['y']) for o in geometry['obstacles']],
        'safety.obstacle_safety_radius': [
            agc_world_map.obstacle_safety_radius(o) for o in geometry['obstacles']],
        'safety.obstacle_z_top': [
            agc_world_map.obstacle_z_top(o) for o in geometry['obstacles']],
    }
    if fa.get('own_clearance_min_m') is not None:
        safety_geometry['safety.vertical_clearance_m'] = float(fa['own_clearance_min_m'])
    print('[air_bringup] world_map=%s geometry=%s obstacles=%d'
          % (map_name, geom_path, len(geometry['obstacles'])))

    # ---- 链路连接层（唯一可替换处，spec R11）----
    px4_dir = str(agc_root / 'toolchain' / 'PX4-Autopilot')
    px4_build = os.path.join(px4_dir, 'build', 'px4_sitl_default')
    px4_bin = os.path.join(px4_build, 'bin', 'px4')
    agent_bin = str(agc_root / 'toolchain' / 'bin' / 'MicroXRCEAgent')
    # 启动前校验工具链二进制存在（缺失即拒启动，清晰报错）。
    _required = [agc_root / 'toolchain' / 'bin' / 'MicroXRCEAgent', Path(px4_bin)]
    _missing = [str(p) for p in _required if not p.exists()]
    if _missing:
        raise RuntimeError(
            '工具链缺失，拒绝启动：%s\n请确认 agc_root 指向固定项目根（默认 /home/chen/AGC）；'
            '亦可用 agc_root:=<path> 覆盖' % ', '.join(_missing))
    gz_models = os.path.join(px4_dir, 'Tools', 'simulation', 'gz', 'models')
    gz_worlds = os.path.join(px4_dir, 'Tools', 'simulation', 'gz', 'worlds')

    # ---- 本仓己方机型：ADR-0030 正下视相机 + 2026-11-05 GUI 高亮，与 main.launch.py 同一口径 ----
    # 模型资产在**本仓**（install/agc_sim/share/agc_sim/models/{agc_x500_nadir,agc_x500}），
    # 不在 PX4 工具链里；机型解析走 `PX4_SYS_AUTOSTART=4001`（rcS:41-44 优先于按名反查
    # rcS:52-63）→ rcS 仍 source 官方 `4001_gz_x500`，`PX4_SIM_MODEL` 只决定 spawn 给 gz 的
    # 模型名（GZBridge.cpp:73-77 相对路径）。
    # 两个本仓机型共用同一注入（本仓 models 路径 + AUTOSTART），差别只在模型名：
    # `gz_agc_x500_nadir` → agc_x500_nadir（正下视相机）；`gz_agc_x500` → agc_x500（纯视觉高亮球）。
    # **其它机型**（含 PX4 官方 `gz_x500`）dict 为空，env 与改动前完全相同。
    nadir_sim_model = 'gz_agc_x500_nadir'
    highlight_sim_model = 'gz_agc_x500'
    sim_model_now = LaunchConfiguration('px4_sim_model').perform(context)
    own_repo_model = sim_model_now in (nadir_sim_model, highlight_sim_model)
    px4_env_extra = {}
    if own_repo_model:
        px4_env_extra['GZ_SIM_RESOURCE_PATH'] = (
            gz_models + ':' + gz_worlds + ':' + os.path.join(sim_share, 'models'))
        px4_env_extra['PX4_SYS_AUTOSTART'] = '4001'

    # ---- 世界 + 桥 + 车/目标 spawn（复用 agc_sim，唯一世界 / 唯一时钟）----
    world = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(sim_share, 'launch', 'world_bringup.launch.py')),
        launch_arguments={
            'gz_args': LaunchConfiguration('gz_args'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            # 按地图选择配置文件（世界生成与安全列表同源）
            'world_map': LaunchConfiguration('world_map'),
        }.items(),
    )

    # ---- 感知适配层（真值旁路 + 目标源）；目标源由本 launch 单一设置 ----
    perception = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(perception_share, 'launch', 'perception_bringup.launch.py')),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'target_source': LaunchConfiguration('target_source'),
            'seed': seed,
        }.items(),
    )

    # ---- uXRCE-DDS Agent（PX4 与 ROS2 之间的桥）----
    agent = ExecuteProcess(
        cmd=[agent_bin, 'udp4', '-p', LaunchConfiguration('agent_port')],
        output='screen',
    )

    # ---- PX4 SITL（standalone：不自起 gz，挂入 agc_world）----
    px4_env = {
        'GZ_SIM_RESOURCE_PATH': gz_models + ':' + gz_worlds,
        'PX4_GZ_STANDALONE': '1',
        'PX4_GZ_WORLD': 'agc_world',
        # 机型改由 launch 参数**单一设置**；默认 `gz_x500` = 既有行为**逐字不变**。
        # 可选 `gz_x500_mono_cam`（airframe 4010：只把 PX4_SIM_MODEL 指向 merge 了
        # `mono_cam` 的机型，旋翼/参数集与 4001 完全相同）——相机口径与验收见
        # experiments/p1-4//preregistration/。
        # 实体名规则（GZBridge.cpp：无 -n 且给 -i → `<model_sim>_<instance>`）：
        # gz_x500 → x500_0；gz_x500_mono_cam → x500_mono_cam_0。
        # ADR-0030：gz_agc_x500_nadir → agc_x500_nadir_0，另注入 PX4_SYS_AUTOSTART=4001 +
        # 本仓 models 资源路径（见上方 px4_env_extra；默认臂该 dict 为空）。
        'PX4_SIM_MODEL': LaunchConfiguration('px4_sim_model'),
        'PX4_GZ_MODEL_POSE': LaunchConfiguration('px4_gz_model_pose'),
        'AGC_PX4_SIM_SEED': seed,
    }
    px4_env.update(px4_env_extra)
    # 用 PX4 官方启动脚本（与官方 gz_x500 流程一致；不注入任何自定义参数）
    px4 = ExecuteProcess(
        cmd=[px4_bin, '-d', '-s', 'etc/init.d-posix/rcS'],
        cwd=px4_build,
        additional_env=px4_env,
        output='screen',
    )

    # ---- 空中链路节点（长跑控制节点为 lifecycle managed node）----
    # `origin_pose`：PX4 局部系原点（世界 ENU）= 己方机 spawn 位姿，经 launch 单一注入；
    # px4_adapter（局部→世界）与 OffboardInterface（世界→局部 setpoint）共用该值。
    common = [params_file, {'use_sim_time': LaunchConfiguration('use_sim_time'),
                            'origin_pose': LaunchConfiguration('px4_gz_model_pose')}]
    nodes = [
        Node(package='agc_air', executable='px4_adapter',
             name='px4_adapter', parameters=common, output='screen'),
        Node(package='agc_air', executable='takeoff_controller',
             name='takeoff_controller', parameters=common, output='screen'),
        Node(package='agc_air', executable='trajectory_tracker',
             name='trajectory_tracker', parameters=common + [safety_geometry], output='screen'),
        Node(package='agc_air', executable='standoff_follower',
             name='standoff_follower', parameters=common, output='screen'),
    ]

    # ADR-0019：manager 启动**前**预热被管节点的 lifecycle 服务连接，避免其阻塞式
    # `change_state` 在 DDS 发现预热期永久挂起（实测停在 `Configuring takeoff_controller`）。
    prewarm_bin = os.path.join(
        get_package_prefix('agc_air'), 'lib', 'agc_air', 'air_lifecycle_prewarm')
    prewarm = ExecuteProcess(
        cmd=[prewarm_bin, 'px4_adapter', 'takeoff_controller', 'trajectory_tracker',
             'standoff_follower'],
        output='screen')

    # lifecycle 编排：**复用 Nav2 `lifecycle_manager`**（ADR-0003 吸收点）。
    # 它先 wait_for_service 等节点就绪，再统一 configure → activate，天然避免"节点未就绪就下发"
    # 与固定延时竞态（原先手写 TimerAction + `ros2 lifecycle set` 重试的做法已废弃）。
    # 被管空中节点已实现 Nav2 bond（topic=`bond`、id=节点名、`bond_heartbeat_period`）→
    # `bond_timeout` **不**再置 0，启用 bond 失联检测（被管节点死亡 → manager 硬复位，见 ADR-0019）。
    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_air',
        parameters=[{
            'autostart': LaunchConfiguration('autostart'),
            'node_names': ['px4_adapter', 'takeoff_controller', 'trajectory_tracker',
                           'standoff_follower'],
            'bond_timeout': 5.0,
        }],
        output='screen',
    )

    # gz 服务器在**运行期**经 `/world/agc_world/create` 解析 PX4 机型 `model://x500`
    # （PX4 自身 gz_bridge 只给文件名，资源解析靠 gz 侧），故本变量必须对整个 launch 生效。
    # OpaqueFunction 要求函数返回实体**列表**（LaunchDescription 本身不可迭代），
    # 故直接返回按原顺序组装的实体清单。
    return [
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH', gz_models + ':' + gz_worlds),
        world,
        perception,
        agent,
        TimerAction(period=12.0, actions=[px4]),
        *nodes,
        prewarm,
        RegisterEventHandler(OnProcessExit(target_action=prewarm, on_exit=[lifecycle_manager])),
    ]


def generate_launch_description():
    sim_share = get_package_share_directory('agc_sim')
    world_file = os.path.join(sim_share, 'worlds', 'agc_world.sdf')

    # 所有 launch 参数在**顶层**声明，保证 `ros2 launch ... --show-args` 可内省；
    # `_generate`（OpaqueFunction）只负责按参数组装 actions。
    declared = [
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('gz_args', default_value=['-r -v 3 ', world_file],
                              description='gz sim 参数（加 -s 可无头）'),
        DeclareLaunchArgument('px4_gz_model_pose', default_value='0,0,0.2,0,0,0',
                              description='己方无人机 spawn 位姿（world 系 ENU，逗号分隔）'),
        # 己方机型。**默认 gz_agc_x500**（2026-11-05，用户裁定）= 本仓 `agc_x500`
        # （PX4 官方 x500 + 纯视觉青色高亮球，无 collision；因默认 gz_x500 在 GUI 俯视下仅约 5 px
        # 看不见我方机）。其余可选：gz_x500（PX4 官方原厂）；gz_x500_mono_cam（机载前视单目相机）；
        # gz_agc_x500_nadir（机载正下视相机，ADR-0030）。未知值由 PX4 rcS 报
        # `Unknown model` 并拒启（airframes 目录按名匹配），不在本文件另立白名单。
        DeclareLaunchArgument('px4_sim_model', default_value='gz_agc_x500',
                              description='己方 PX4 gz 机型：gz_agc_x500（**默认**，x500 + 纯视觉高亮球）| '
                                          'gz_x500（PX4 官方原厂，无高亮）| '
                                          'gz_x500_mono_cam（机载前视单目相机，P1-4）| '
                                          'gz_agc_x500_nadir（机载正下视相机，ADR-0030，仅取证/测绘、无消费者）'),
        DeclareLaunchArgument('agent_port', default_value='8888'),
        DeclareLaunchArgument('autostart', default_value='true',
                              description='是否自动 configure/activate 空中节点'),
        DeclareLaunchArgument('target_source', default_value='gt_adapter',
                              description='契约 /agc/target/source（W4 目标源）：'
                                          'gt_adapter | none（air_fusion 已退役；none 用于单独录制 C1 八字轨迹）'),
        DeclareLaunchArgument('seed', default_value='0',
                              description='实验随机种子（注入 PX4 GPS 仿真；原 air_perception 已于 2026-11-06 退役）'),
        # 地图（配置文件选择）；缺省 minimal = 既有行为（几何逐值不变）。
        DeclareLaunchArgument('world_map', default_value='minimal',
                              description='地图（几何真源选择）：minimal（默认）| yard | open_field'),
    ]

    ld = LaunchDescription()
    ld.add_action(DeclareLaunchArgument(
        'agc_root', default_value='/home/chen/AGC',
        description='固定项目根（AGENTS.md）；工具链在其下 toolchain/'))
    for a in declared:
        ld.add_action(a)
    ld.add_action(OpaqueFunction(function=_generate))
    return ld
