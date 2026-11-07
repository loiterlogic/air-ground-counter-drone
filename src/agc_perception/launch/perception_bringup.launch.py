#!/usr/bin/env python3
"""perception_bringup —— 感知一键启动。

由上层 launch（air_bringup / m0_skeleton）**include**；参数配置文件 `config/perception.yaml`。

分段：
 * ：gt_bypass（真值旁路）+ ground_odom_adapter + gt_adapter
 * ：map_adapter

## 已退役的路线（用户裁定）

**① 视觉定位路径**（`perception_path=vision`，含 `camera_tf` + `vision_target`：像素检测 →
射线 × 高度平面求交 → `/agc/targets`）已**整体删除**（2026-11-04）。项目不做目标识别，
目标位置始终由真值给出。

**② `air_fusion`**（两路空中通道观测融合 → `/agc/targets` + `/agc/obstacles`）已**删除**
（2026-11-04）：目标位置既然只由真值给出，融合就没有独立价值。

**③ `air_perception` 与 `perception` 场景轴**（2026-11-06，用户裁定「彻底删」）：
`air_fusion` 退役后 `/agc/air/obs` 恒无订阅者，`sensors_file` 通道变体
（nominal / dropout / fov / no_target）在运行期**行为完全相同**，属"退役了功能但没退役
承载物"。本次一并删除：节点、4 个 `perception_sensors*.yaml`、场景 `perception` 轴、
`sensors_file` 解析/注入链、专项验收脚本。防复活闸门见
`scripts/tests/test_retirement_ledger.py`；处置依据见
[路线分支治理](../conventions/路线分支治理.md#retire) 5.2 台账。

**结果（当前唯一行为）**：`/agc/targets` 的唯一发布者是 `gt_adapter`（**无几何门控，
不分远近**）；`/agc/obstacles` 无发布者，`obstacles_source` 恒为 `config`（静态先验）。
下游不得据任何"传感器量程 / FOV / 丢包"配置宣称本仓当前存在感知质量差异。

`/agc/map` 链（map_adapter → /agc/map → costmap）**不在本次清退范围**：它是 `baseline`
命令源（规范 已批准分支）的组成部分，状态为「待建」，见治理规范 台账。
"""


import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _reject_non_minimal_fallback(context, *args, **kwargs):
    """**回退副本只支持 minimal**（规格「同步回退副本与核查」）。

 standalone 直接起 `perception_bringup`（不经过 `composition` 派生）时，`map_file` /
 `obstacles_file` 用包内回退副本，它们只与 **minimal** 配置文件一致。若此时声明
 `world_map != minimal`，用回退几何跑「yard 场景」会得到「世界有墙、地图没有」——
 显式拒绝（比静默用错几何好）。w6 路径按配置文件派生注入，不经本检查。
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
            '（仅与 minimal 的几何文件一致）→ 拒绝运行。非 minimal 地图须由上层按单一几何来源派生注入'
            '（见 composition.write_derived_*）。' % name)
    return []


def generate_launch_description():
    share = get_package_share_directory('agc_perception')
    params_file = os.path.join(share, 'config', 'perception.yaml')
    default_obstacles_file = os.path.join(share, 'config', 'obstacles.yaml')
    default_map_file = os.path.join(share, 'config', 'map.yaml')

    use_sim_time = LaunchConfiguration('use_sim_time')
    target_source = LaunchConfiguration('target_source')
    # （ADR-0007）：地图几何文件由上层经**配置文件**派生注入（缺省 = 包内回退副本）。
    obstacles_file = LaunchConfiguration('obstacles_file')
    map_file = LaunchConfiguration('map_file')
    # （ADR-0007）：场景 / 源版本 → 折入地图内容身份 hash（诊断，非 ABI）
    scenario_version = LaunchConfiguration('scenario_version')

    declared = [
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        # `target_source` 保留：gt_adapter 用它决定自己是否发布 `/agc/targets`。
        # air_fusion 已退役，故**唯一有效值**是 `gt_adapter`（其它值 = gt_adapter 不发布 → 无目标源）。
        DeclareLaunchArgument('target_source', default_value='gt_adapter',
                              description='契约 /agc/target/source：gt_adapter（air_fusion 已退役）'),
        DeclareLaunchArgument('obstacles_file', default_value=default_obstacles_file,
                              description='障碍真值文件（缺省 = 包内默认；none 场景传空障碍文件）'),
        DeclareLaunchArgument('map_file', default_value=default_map_file,
                              description='地图几何文件（缺省 = 包内回退副本；由上层按单一几何来源派生注入）'),
        # 地图名。**回退副本只支持 minimal**——standalone 启动若声明非 minimal 地图
        # （且未显式给派生文件），必须显式报错（比静默用错几何好）。
        DeclareLaunchArgument('world_map', default_value='minimal',
                              description='地图名（minimal | yard | open_field）；'
                                          '回退副本仅支持 minimal，其余须由上层派生注入'),
        DeclareLaunchArgument('scenario_version', default_value='',
                              description='场景 / 源版本（由上层按场景轴选择；折入地图内容身份 hash）'),
    ]

    common = [params_file, {'use_sim_time': use_sim_time}]

    # ---- · 适配层（gt_bypass / ground_odom_adapter）----
    shared_a = [
        Node(package='agc_perception', executable='gt_bypass',
             name='gt_bypass', parameters=common, output='screen'),
        Node(package='agc_perception', executable='ground_odom_adapter',
             name='ground_odom_adapter', parameters=common, output='screen'),
    ]

    # ---- · 地图 ----
    map_node = Node(package='agc_perception', executable='map_adapter',
                    name='map_adapter',
                    parameters=common + [{'map_file': map_file,
                                          'obstacles_file': obstacles_file,
                                          # 2026-11-04：恒 config（air_fusion 已退役，参数已删）
                                          'obstacles_source': 'config',
                                          'scenario_version': scenario_version}],
                    output='screen')

    # ---- 真值链：唯一发布者 gt_adapter ----
    # `air_fusion` 已于 2026-11-04 退役；`air_perception`（agc/air/obs）及其无消费者的
    # 通道配置已于 2026-11-06 一并删除。本链现在只剩 gt_adapter 一个节点。
    gt_node = Node(package='agc_perception', executable='gt_adapter',
                   name='gt_adapter',
                   parameters=common + [{'target_source': target_source}],
                   output='screen')

    ld = LaunchDescription()
    for a in declared:
        ld.add_action(a)
    ld.add_action(OpaqueFunction(function=_reject_non_minimal_fallback))
    for n in shared_a:
        ld.add_action(n)
    ld.add_action(gt_node)
    ld.add_action(map_node)
    return ld
