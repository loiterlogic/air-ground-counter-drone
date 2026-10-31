#!/usr/bin/env python3
"""perception_bringup —— W4 感知与融合一键启动（spec R3/R8）。

由上层 launch（air_bringup / m0_skeleton）**include**；参数单一来源 `config/perception.yaml`。
目标源节点（gt_adapter / air_fusion）由本 launch 提供，`/agc/target/source` 由此单一设置。

分段：
  * W4-a：gt_bypass（真值旁路）+ ground_odom_adapter + gt_adapter
  * W4-b：air_perception + air_fusion
  * W4-c：map_adapter
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _reject_non_minimal_fallback(context, *args, **kwargs):
    """P1-1：**回退副本只支持 minimal**（规格「同步回退副本与核查」）。

    standalone 直接起 `perception_bringup`（不经过 `w6_composition` 派生）时，`map_file` /
    `obstacles_file` 用包内回退副本，它们只与 **minimal** 真源一致。若此时声明
    `world_map != minimal`，用回退几何跑「yard 场景」会得到「世界有墙、地图没有」——
    显式拒绝（比静默用错几何好）。w6 路径按真源派生注入，不经本检查。
    """
    name = (LaunchConfiguration('world_map').perform(context) or 'minimal').strip()
    map_file_ = LaunchConfiguration('map_file').perform(context)
    obstacles_file_ = LaunchConfiguration('obstacles_file').perform(context)
    share = get_package_share_directory('agc_perception')
    fallback = (os.path.realpath(os.path.join(share, 'config', 'map.yaml')),
                os.path.realpath(os.path.join(share, 'config', 'obstacles.yaml')))
    using_fallback = (os.path.realpath(map_file_) == fallback[0]
                      or os.path.realpath(obstacles_file_) == fallback[1])
    if name != 'minimal' and using_fallback:
        raise RuntimeError(
            'perception_bringup: world_map=%s 但 map_file/obstacles_file 指向包内回退副本'
            '（仅与 minimal 真源一致）→ 拒绝运行。非 minimal 地图须由上层按几何真源派生注入'
            '（见 w6_composition.write_derived_*）。' % name)
    return []


def generate_launch_description():
    share = get_package_share_directory('agc_perception')
    params_file = os.path.join(share, 'config', 'perception.yaml')
    default_sensors_file = os.path.join(share, 'config', 'perception_sensors.yaml')
    default_obstacles_file = os.path.join(share, 'config', 'obstacles.yaml')
    default_map_file = os.path.join(share, 'config', 'map.yaml')

    use_sim_time = LaunchConfiguration('use_sim_time')
    target_source = LaunchConfiguration('target_source')
    obstacles_source = LaunchConfiguration('obstacles_source')
    # R-026：传感器通道 / 障碍真值文件由上层按场景轴选择并单一注入（契约 #params）。
    sensors_file = LaunchConfiguration('sensors_file')
    obstacles_file = LaunchConfiguration('obstacles_file')
    # S-06（ADR-0062）：地图几何文件由上层经**单一真源**派生注入（缺省 = 包内回退副本）。
    map_file = LaunchConfiguration('map_file')
    # P1-1：地图名（仅用于**显式拒绝**不受支持的回退路径，见 `_reject_non_minimal_fallback`）。
    world_map = LaunchConfiguration('world_map')
    # R-040（ADR-0055）：场景 / 源版本 → 折入地图内容身份 hash（诊断，非 ABI）
    scenario_version = LaunchConfiguration('scenario_version')
    seed = LaunchConfiguration('seed')

    declared = [
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('target_source', default_value='gt_adapter',
                              description='契约 /agc/target/source：gt_adapter | air_fusion'),
        DeclareLaunchArgument('obstacles_source', default_value='air_fusion',
                              description='契约 /agc/obstacles/source：air_fusion | config'),
        DeclareLaunchArgument('sensors_file', default_value=default_sensors_file,
                              description='R-026 传感器通道文件（缺省 = 包内默认；由上层按场景轴选择）'),
        DeclareLaunchArgument('obstacles_file', default_value=default_obstacles_file,
                              description='R-026 障碍真值文件（缺省 = 包内默认；none 场景传空障碍文件）'),
        DeclareLaunchArgument('map_file', default_value=default_map_file,
                              description='S-06 地图几何文件（缺省 = 包内回退副本；由上层按真源派生注入）'),
        # P1-1：地图名。**回退副本只支持 minimal**——standalone 启动若声明非 minimal 地图
        #   （且未显式给派生文件），必须显式报错（比静默用错几何好）。
        DeclareLaunchArgument('world_map', default_value='minimal',
                              description='P1-1 地图名（minimal | yard | open_field）；'
                                          '回退副本仅支持 minimal，其余须由上层派生注入'),
        DeclareLaunchArgument('scenario_version', default_value='',
                              description='R-040 场景 / 源版本（由上层按场景轴选择；折入地图内容身份 hash）'),
        DeclareLaunchArgument('seed', default_value='unseeded',
                              description='感知随机种子（仅注入 air_perception；unseeded=兼容默认）'),
    ]

    common = [params_file, {'use_sim_time': use_sim_time}]

    nodes = [
        # ---- W4-a · 适配层 ----
        Node(package='agc_perception', executable='gt_bypass',
             name='gt_bypass', parameters=common, output='screen'),
        Node(package='agc_perception', executable='ground_odom_adapter',
             name='ground_odom_adapter', parameters=common, output='screen'),
        Node(package='agc_perception', executable='gt_adapter',
             name='gt_adapter',
             parameters=common + [{'target_source': target_source}],
             output='screen'),
        # ---- W4-b · 感知与融合 ----
        # R-038 / P1-1 round-7：`seed` 在 air_perception 是 **string** 参数（`declare_parameter<
        #   std::string>("seed", "unseeded")`；perception.yaml 亦写 `seed: "0"`），但 launch 的
        #   裸 substitution 会先经 **yaml.safe_load** 求值 → `"0"` 变 **int 0** → 节点启动即抛
        #   `InvalidParameterTypeException`（Wrong parameter type ... string → integer 不允许）
        #   并 **exit -6**。实测后果：air_perception 死亡 → `/agc/air/obs` 无发布者 → air_fusion
        #   无观测 → 目标永不可见。故此处用 `ParameterValue(..., value_type=str)` 固定为字符串，
        #   保留 `unseeded` 语义（不把它强转成整数）。
        Node(package='agc_perception', executable='air_perception',
             name='air_perception',
             parameters=common + [{'sensors_file': sensors_file,
                                   'obstacles_file': obstacles_file,
                                   'seed': ParameterValue(seed, value_type=str)}],
             output='screen'),
        Node(package='agc_perception', executable='air_fusion',
             name='air_fusion',
             parameters=common + [{'target_source': target_source,
                                   'obstacles_source': obstacles_source}],
             output='screen'),
        # ---- W4-c · 地图 ----
        Node(package='agc_perception', executable='map_adapter',
             name='map_adapter',
             parameters=common + [{'map_file': map_file,
                                   'obstacles_file': obstacles_file,
                                   'obstacles_source': obstacles_source,
                                   'scenario_version': scenario_version}],
             output='screen'),
    ]

    ld = LaunchDescription()
    for a in declared:
        ld.add_action(a)
    ld.add_action(OpaqueFunction(function=_reject_non_minimal_fallback))
    for n in nodes:
        ld.add_action(n)
    return ld
