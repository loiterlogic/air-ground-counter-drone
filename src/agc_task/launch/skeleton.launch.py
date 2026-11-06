#!/usr/bin/env python3
"""skeleton —— 最小端到端闭环顶层 launch。

一条命令起全链：include agc_sim 的世界+桥，再起 odom 适配、地面执行链、
门控/复位与 run logger。参数配置文件 src/agc_task/config/skeleton.yaml。
验收跑有头（GUI）；无头可传 gz_args:='-s -r -v 3 <world>'。

`command_source` 透传至 agc_ground 的 ground_bringup（ 命令源互斥选择）：
 * rl（默认）—— `agc_rl` 推理节点为主控（ADR-0004）；
 * baseline —— `agc_ground` 的离线对照基线（R8）。

 顶层入口已统一为 `main.launch.py`（`backend` 参数；见 ADR-0020），
本文件保留为**骨架基座**供其 include（轻量栈）。
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    sim_share = get_package_share_directory('agc_sim')
    task_share = get_package_share_directory('agc_task')
    perception_share = get_package_share_directory('agc_perception')
    params_file = LaunchConfiguration('params_file')
    world_file = os.path.join(sim_share, 'worlds', 'agc_world.sdf')
    default_params = os.path.join(task_share, 'config', 'skeleton.yaml')

    world_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(sim_share, 'launch', 'world_bringup.launch.py')),
        launch_arguments={
            'gz_args': LaunchConfiguration('gz_args'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            # 按障碍轴选择世界（none 生成不含任何障碍的世界）
            'world_obstacles': LaunchConfiguration('world_obstacles'),
            # 按地图选择配置文件（minimal | yard | open_field）
            'world_map': LaunchConfiguration('world_map'),
            # F1（2026-10-31）：世界 spawn 由**出生布局配置文件**派生后经 w6 透传。
            # 缺省 'auto' = 不覆盖 world_bringup 自己的 car.yaml / target.yaml 缺省
            # （即 standalone 行为不变）；w6 会显式传入**与复位同值**的坐标。
            'car_x': LaunchConfiguration('car_x'),
            'car_y': LaunchConfiguration('car_y'),
            'car_z': LaunchConfiguration('car_z'),
            'car_yaw': LaunchConfiguration('car_yaw'),
            'target_x': LaunchConfiguration('target_x'),
            'target_y': LaunchConfiguration('target_y'),
            'target_z': LaunchConfiguration('target_z'),
            'target_yaw': LaunchConfiguration('target_yaw'),
        }.items(),
    )

    # 感知适配层（真值旁路 + 地面 odom 归一 + 目标源）；ground_odom_adapter 自 起
    # 由 agc_perception 提供（位姿来源改为真值旁路）， 不再直接起该节点。
    perception = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(perception_share, 'launch', 'perception_bringup.launch.py')),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            # （P1）：观测来源（lightweight 缺省 gt_adapter；可被上层覆盖）
            'target_source': LaunchConfiguration('target_source'),
            # 障碍真值文件按场景轴由上层选择并单一注入
            # 2026-11-06：`sensors_file` / `seed` 随 `perception` 轴退役，不再透传。
            'obstacles_file': LaunchConfiguration('obstacles_file'),
            # （ADR-0007）：地图几何文件由上层经配置文件派生注入
            'map_file': LaunchConfiguration('map_file'),
        }.items(),
    )

    # 地面链路（安全层 collision_monitor + 中继 + 命令源）；替代 的 safety stub
    ground_share = get_package_share_directory('agc_ground')
    ground_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ground_share, 'launch', 'ground_bringup.launch.py')),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'command_source': LaunchConfiguration('command_source'),
            # （T1/E1）：安全层开关透传（缺省 true；false = 无 shield 对照臂，纯仿真）
        }.items(),
    )

    common = [params_file, {'use_sim_time': LaunchConfiguration('use_sim_time')}]
    # ground_controller 字段随 command_source 切换（rl → agc_rl；baseline → agc_ground）
    controller_name = PythonExpression([
        "'agc_rl' if '", LaunchConfiguration('command_source'), "' == 'rl' else 'agc_ground'"])

    nodes = [
        Node(package='agc_task', executable='scenario_reset',
             name='scenario_reset', parameters=common, output='screen'),
        Node(package='agc_task', executable='task_manager',
             name='task_manager',
             parameters=common + [{'ground_controller_name': controller_name}],
             output='screen'),
        Node(package='agc_task', executable='run_logger',
             name='run_logger',
             parameters=common + [
                 # scene_manifest（声明轴 + 承载者 + 实际生效参数）与合并后参数文件
                 # 经 run_logger 拷入 run 的 config/（缺省空 = 不拷贝，不影响既有调用方）
                 {'scene_manifest_file': LaunchConfiguration('scene_manifest_file'),
                  # （ADR-0006）：世界模型文件 → run_logger 记 sha256（工具链身份）
                  'world_file': LaunchConfiguration('world_file'),
                  'params_file': LaunchConfiguration('params_file'),
                  # （T1/E1）：安全层开关（字符串承载→节点内解析）——false 时 action 新鲜度门不适用
                  'shield_layer_enabled': True}],
             output='screen'),
    ]

    ld = LaunchDescription()
    ld.add_action(DeclareLaunchArgument('use_sim_time', default_value='true'))
    ld.add_action(DeclareLaunchArgument(
        'params_file', default_value=default_params,
        description='任务层参数文件（默认 config/skeleton.yaml；W5 场景用 config/safety_scenario.yaml）'))
    ld.add_action(DeclareLaunchArgument(
        'gz_args', default_value=['-r -v 3 ', world_file],
        description='gz sim 参数（加 -s 可无头）'))
    ld.add_action(DeclareLaunchArgument(
        'command_source', default_value='rl',
        description='W5 地面命令源（互斥）：rl | baseline'))
    ld.add_action(DeclareLaunchArgument(
        'target_source', default_value='gt_adapter',
        description='观测来源（gt_adapter；air_fusion 已退役）'))
    # 2026-11-06 清退：`seed` 与 `sensors_file` 随 `perception` 场景轴退役，
    # 本入口不再声明、也不再向 perception_bringup 透传（见 docs/conventions/路线分支治理.md）。
    # 2026-11-04 清退：`shield` 开关已删除——安全层恒定启用
    # （见 docs/conventions/路线分支治理.md 5.3）。
    # 场景轴承载者接线（缺省 = 既有行为：static 世界 + 默认障碍 + 无 manifest）
    ld.add_action(DeclareLaunchArgument(
        'world_obstacles', default_value='static',
        description='障碍轴世界生成：static | none（由上层按场景轴传入）'))
    # 地图（配置文件选择）；缺省 minimal = 既有行为。
    ld.add_action(DeclareLaunchArgument(
        'world_map', default_value='minimal',
        description='地图（几何来源选择）：minimal（默认）| yard | open_field（由上层传入）'))
    # F1（2026-10-31）：出生布局透传口。缺省 **'auto'** = 不改 world_bringup 的缺省
    # （car.yaml / target.yaml 的值）→ standalone 行为逐字不变；main.launch.py 显式传入
    # 布局配置文件派生值（或场景覆盖值），两侧（世界 spawn / 复位）同源。
    for _arg, _desc in (
            ('car_x', '车 spawn x（world ENU，m；auto=用 agc_sim car.yaml 缺省）'),
            ('car_y', '车 spawn y（world ENU，m；auto=用 agc_sim car.yaml 缺省）'),
            ('car_z', '车 spawn z（轮触地，m；auto=用 agc_sim car.yaml 缺省）'),
            ('car_yaw', '车 spawn yaw（rad；auto=用 agc_sim car.yaml 缺省）'),
            ('target_x', '目标 spawn x（world ENU，m；auto=用 agc_sim target.yaml 缺省）'),
            ('target_y', '目标 spawn y（world ENU，m；auto=用 agc_sim target.yaml 缺省）'),
            ('target_z', '目标 spawn z（m；auto=用 agc_sim target.yaml 缺省）'),
            ('target_yaw', '目标 spawn yaw（rad；auto=用 agc_sim target.yaml 缺省）')):
        ld.add_action(DeclareLaunchArgument(_arg, default_value='auto', description=_desc))
    # `sensors_file` 已于 2026-11-06 随 `perception` 轴退役（无消费者），不再声明。
    ld.add_action(DeclareLaunchArgument(
        'obstacles_file',
        default_value=os.path.join(perception_share, 'config', 'obstacles.yaml'),
        description='障碍真值文件（由上层按障碍轴传入）'))
    ld.add_action(DeclareLaunchArgument(
        'map_file',
        default_value=os.path.join(perception_share, 'config', 'map.yaml'),
        description='S-06 地图几何文件（缺省 = 包内回退副本；由上层按几何来源派生传入）'))
    ld.add_action(DeclareLaunchArgument(
        'scene_manifest_file', default_value='',
        description='R-026 scene_manifest.json 路径（由上层生成；空 = 不落）'))
    ld.add_action(DeclareLaunchArgument(
        'world_file', default_value=world_file,
        description='R-029 世界模型文件路径（run_logger 记 sha256；缺省 = agc_world.sdf）'))
    ld.add_action(world_bringup)
    ld.add_action(perception)
    ld.add_action(ground_bringup)
    for n in nodes:
        ld.add_action(n)
    return ld
