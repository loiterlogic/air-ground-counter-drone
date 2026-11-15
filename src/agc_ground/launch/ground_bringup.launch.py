#!/usr/bin/env python3
"""ground_bringup —— 地面链路一键启动。

起：静态 TF（`car/base_link → car/lidar_link`）+ **自研安全层** `ground_safety_filter`
+ 地面执行中继（唯一执行口）+ **命令源**（`command_source` 单一选择，二者互斥）。

链路：命令源 → `/agc/ground/cmd_vel_raw` → `ground_safety_filter` → `/agc/ground/cmd_vel`
 → `ground_drive_relay` → GZ（`/model/agc_car/cmd_vel`）。

命令源（`command_source`，互斥；同一时刻仅一路下发）：
 * `rl` —— `agc_rl` 的 RL 推理节点（主控，ADR-0004）。RL **不消费** costmap
 （仅订 odom/scan/goal/state，见 `agc_rl.inference_node` / `agc_rl.interface`），
 故**不**起独立 costmap 进程（按命令源裁剪，[ADR-0003](../../../docs/adr/0003-nav2-paradigm-absorption.md#top)）；
 仅安全层 + 唯一执行口中继。
 * `baseline` —— `agc_ground` 的离线对照基线（Nav2 planner 插件 + `agc_control` LQR 插件）；
 基线自持内建 costmap（同一 `config/costmap.yaml` 参数源），故不再单起 costmap 节点。
 * ~~`train`~~ / ~~`rl_high`~~ —— **2026-11-04 已删除**：两者都服务 / 的研究臂，
 而 已结档（[ADR-0023](../../../docs/adr/0023-adjudication-record-and-exit.md#top)：
 P1 inconclusive / P2 falsified）。研究复跑须用 `scripts/research/` 自带的参数文件，
 **不得**在主链保留"外部进程作命令源"的分支。见
 [路线分支治理](../../../docs/conventions/路线分支治理.md#rule) 5.3。

安全层（`shield`）：**2026-11-04 起恒定启用**，launch 开关已删除。
安全层：**自研 `ground_safety_filter`**（[ADR-0045](../../../docs/adr/0045-ground-safety-layer-self-owned.md#top)），
恒定启用、无 launch 开关，"无 shield 对照臂"属消融研究，演示与验收**永远不该关安全层**；
它**不引入** Nav2 安全层运行时，唯一障碍输入是 `/agc/map`。

参数配置文件：`config/ground.yaml`（安全层 / 中继）、`config/costmap.yaml`（分层 costmap，基线自持）、
`config/baseline.yaml`（基线）、`agc_rl/config/rl.yaml`（RL）（../../../docs/adr/0020-package-boundaries-and-runtime-topology.md#params）。

路径输入与命令源的关系（2026-11-01，ADR-0013）：
 * `/agc/ground/path`（`nav_msgs/Path`，`frame_id=world`）是地面侧规划器发布的**路径数据**，
 不是命令，因此**不进** `command_source` 的互斥域。
 **参数边界**：路径相关参数全部是**节点本地 config**（`agc_rl/config/rl.yaml` 的 `path.*`、
 `agc_ground/config/ground.yaml` 的 `hybrid_astar_se2_planner.*`），由既有 launch 透传；
 **未新增契约全局入口**（`#params` 无新条目），也**未新增 launch 级开关**——
 goal-only 对照只用节点本地 `path.enabled`。
 * 路径的消费侧质量门（从未收到 / 空 / 单点 / 帧不一致 / 过期）与"失效即零速、禁止静默退回
    goal-only"由消费方实现（ADR-0013(e)）；G2 负责接线并给出行为证据。
 * **启动边界**（与改造前**相反**）：自研安全层用定时器**每拍无条件发布**，无任何输入时发零速
 （[ADR-0045](../../../docs/adr/0045-ground-safety-layer-self-owned.md#top)）；旧 Nav2 安全层
 「命令源缺失时一个速度都不发」的缺口已被消除 —— `/agc/ground/cmd_vel` 断流自此即为缺陷。
 * 本注释**不改变任何有效逻辑或参数值**：`command_source` 分支、managed 编排均原样。
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# 传感器几何（与 agc_sim/models/agc_car/agc_car.sdf.xacro 的 car/lidar_link pose 一致）
LIDAR_X, LIDAR_Y, LIDAR_Z = 0.0, 0.0, 0.48
# gz 点云/LaserScan 的 header.frame_id 为 gz 作用域名（`<model>/<link>/<sensor>`），非契约帧名；
# 以单位静态 TF 将其接到契约帧 `car/lidar_link`（见 。
GZ_LIDAR_FRAME = 'agc_car/car/lidar_link/lidar3d'


def _nodes(context, *args, **kwargs):
    command_source = LaunchConfiguration('command_source').perform(context)
    use_sim_time = LaunchConfiguration('use_sim_time')
    ground_share = get_package_share_directory('agc_ground')
    rl_share = get_package_share_directory('agc_rl')
    params_file = os.path.join(ground_share, 'config', 'ground.yaml')
    costmap_file = os.path.join(ground_share, 'config', 'costmap.yaml')
    baseline_file = os.path.join(ground_share, 'config', 'baseline.yaml')

    common = [params_file, {'use_sim_time': use_sim_time}]

    actions = [
        # R2：传感器系静态 TF（costmap / RL 策略需将扫描变换到 base_frame；安全层不用 scan）
        Node(
            package='tf2_ros', executable='static_transform_publisher',
            name='car_lidar_tf',
            arguments=[
                '--x', str(LIDAR_X), '--y', str(LIDAR_Y), '--z', str(LIDAR_Z),
                '--roll', '0', '--pitch', '0', '--yaw', '0',
                '--frame-id', 'car/base_link', '--child-frame-id', 'car/lidar_link',
            ],
            parameters=[{'use_sim_time': use_sim_time}], output='screen',
        ),
        Node(
            package='tf2_ros', executable='static_transform_publisher',
            name='car_lidar_gz_frame_tf',
            arguments=[
                '--x', '0', '--y', '0', '--z', '0',
                '--roll', '0', '--pitch', '0', '--yaw', '0',
                '--frame-id', 'car/lidar_link', '--child-frame-id', GZ_LIDAR_FRAME,
            ],
            parameters=[{'use_sim_time': use_sim_time}], output='screen',
        ),
        # 自体过滤（激光自返回置 inf）——消费者是 costmap 与 RL 策略，**不是**安全层
        # （安全层的唯一障碍输入是 /agc/map，ADR-0045）。
        Node(
            package='agc_ground', executable='scan_self_filter',
            name='scan_self_filter', parameters=common, output='screen',
        ),
    ]

    # 安全层：**自研** `ground_safety_filter`（ADR-0045）。恒定启用、无 launch 开关。
    # 它**不**是 Nav2 组件、**不**链接 nav2_*，唯一障碍输入是 `/agc/map`（与规划同源）。
    # 旧 `nav2_collision_monitor` 已随本改造退役：不保留"两套实现由开关选择"的路线分支
    # （[路线分支治理](../../../docs/conventions/路线分支治理.md#rule)）；
    # 防复活闸门见 scripts/tests/test_retirement_ledger.py。
    managed = []
    actions.append(Node(
        package='agc_ground', executable='ground_safety_filter',
        name='ground_safety_filter', parameters=common, output='screen',
    ))
    # 唯一执行口中继
    actions.append(Node(
        package='agc_ground', executable='ground_drive_relay',
        name='ground_drive_relay', parameters=common, output='screen',
    ))

    if command_source == 'baseline':
        # R8：离线对照基线；自持内建 costmap（参数取 costmap.yaml 的 `costmap:` 段）
        actions.append(Node(
            package='agc_ground', executable='ground_baseline',
            name='ground_baseline',
            parameters=[baseline_file, costmap_file, {'use_sim_time': use_sim_time}],
            output='screen',
        ))
        managed.append('ground_baseline')
    else:
        # 命令源 = agc_rl 推理节点（include agc_rl 的 launch）。
        # （ADR-0003）：RL 主控**不消费** costmap → **不**起闲置的独立 `nav2_costmap_2d` 进程；
        # 分层 costmap 仅由离线基线（`command_source=baseline`）自持（见上分支）。
        #
        # （ADR-0048）：`rl` 拓扑起地面全局路径规划器 Hybrid A* on SE(2)。
        # * 它**只发路径、不发速度** → 不产生第二 `cmd_vel_raw` 生产者；
        # * 不进 `command_source` 互斥域（路径是数据，不是命令）；
        # * 不接 Navfn / planner_server、不起 costmap；唯一障碍输入是 `/agc/map`。
        # * **不提供 launch 级开关**：是否消费路径只由节点本地 `path.enabled` 决定
        # （显式对照模式）；本文件**不为它新增任何 launch 参数**，也不新增契约全局入口。
        # 顺序上先起规划器（发布方），再 include RL（订阅方），避免启动瞬间无发布者。
        actions.append(Node(
            package='agc_ground', executable='hybrid_astar_se2_planner',
            name='hybrid_astar_se2_planner', parameters=common, output='screen',
        ))
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(rl_share, 'launch', 'rl_inference.launch.py')),
            launch_arguments={'use_sim_time': use_sim_time}.items(),
        ))

    # lifecycle 编排：复用 Nav2 lifecycle_manager 统一 configure→activate（ADR-0003 吸收点）
    if managed:
        actions.append(Node(
            package='nav2_lifecycle_manager', executable='lifecycle_manager',
            name='lifecycle_manager_ground',
            parameters=[{'use_sim_time': use_sim_time,
                         'autostart': True,
                         'node_names': managed}],
            output='screen',
        ))
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument(
            'command_source', default_value='rl',
            description='命令源（互斥）：rl（RL 主控，ADR-0004）| baseline（离线对照基线，R8）'
                        '（train / rl_high 已于 2026-11-04 随研究结档清退，'
                        '见 docs/conventions/路线分支治理.md 5.3）'),
        # 2026-11-04 清退：`shield` 开关已删除——安全层恒定启用。
        OpaqueFunction(function=_nodes),
    ])
