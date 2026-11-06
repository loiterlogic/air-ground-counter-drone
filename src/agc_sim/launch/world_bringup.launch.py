#!/usr/bin/env python3
"""world_bringup —— 世界启动编排（世界 + 桥 + spawn 车/目标）。

单一入口，供 顶层 launch include。参数配置文件：
 * 车 / 目标模型与 spawn 位默认值取自 config/car.yaml、config/target.yaml；
 * 桥配置取自 config/bridge.yaml；
 * 静态障碍几何取自**配置文件** config/world_geometry.yaml（ADR-0007）——
 `agc_world.sdf` 为不含 `pole_*` 的 base world，本 launch 按 `world_obstacles`
 （`static` 注入 / `none` 不注入）由配置文件生成运行期世界；
 * ：配置文件按**地图**分文件——`world_map` ∈ `minimal`（config/world_geometry.yaml）|
 `yard` / `open_field`（config/maps/*.yaml）；`world_obstacles` 的 `static|none`
 语义**不变**（`none` 仍强制无任何障碍，用于轴对照）；
 * 全部经 launch ../../../docs/adr/0020-package-boundaries-and-runtime-topology.md#params），节点不得覆写。
"""

import math
import os
import sys
import tempfile

# 与 launch 同目录安装（CMake 安装整个 launch/），供 world_bringup 与单测复用。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gui_render_backend import describe, select_gui_render_env  # noqa: E402
# 配置文件「按地图分文件」的**单一清单**（路径解析 / 形状规范化）在此，不在本文件重复。
from world_map import (  # noqa: E402
    DEFAULT_WORLD_MAP,
    FINISH_PBR,
    is_composite,
    obstacle_finish,
    obstacle_geometry_sdf,
    obstacle_part_geometry_sdf,
    obstacle_parts,
    obstacle_safety_radius,
    obstacle_shape,
    part_finish,
)
from world_map import geometry_path as geometry_file_for_map  # noqa: E402

import yaml

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, EnvironmentVariable, FindExecutable, LaunchConfiguration
from launch_ros.actions import Node


def _load_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def _load_geometry(path):
    """读**单一几何来源**（ADR-0007）；P1-1 起路径由 `world_map` 决定。"""
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def _material_sdf(color, finish=None):
    """经典材质（ambient/diffuse/specular）+ **可选标量 PBR**（视觉保真，2026-10-29）。

 `finish` 留空 → 输出与旧版**逐字节一致**（无 `<pbr>` 块），保证 minimal / open_field 与
 历史证据不漂移。`finish` 合法值见 `world_map.FINISHES` / `FINISH_PBR`（标量 metalness /
 roughness，依据本机 sdformat 1.11 `material.sdf`，**不需要贴图**）。
    """
    r, g, b = color[0], color[1], color[2]
    if finish is None:
        return ('          <material>\n'
                '            <ambient>%(r)s %(g)s %(b)s 1</ambient>\n'
                '            <diffuse>%(r)s %(g)s %(b)s 1</diffuse>\n'
                '            <specular>%(sr)s %(sg)s %(sb)s 1</specular>\n'
                '          </material>' % {
                    'r': r, 'g': g, 'b': b,
                    # 高光略亮于本体（同一颜色族的 1.15 倍，上限 1.0），给单色图元一点层次
                    'sr': min(1.0, r * 1.15 + 0.08),
                    'sg': min(1.0, g * 1.15 + 0.08),
                    'sb': min(1.0, b * 1.15 + 0.08)})
    metal, rough, spec, dk = FINISH_PBR[finish]
    dr, dg, db = min(1.0, r * dk), min(1.0, g * dk), min(1.0, b * dk)
    return ('          <material>\n'
            '            <ambient>%(dr)s %(dg)s %(db)s 1</ambient>\n'
            '            <diffuse>%(dr)s %(dg)s %(db)s 1</diffuse>\n'
            '            <specular>%(sp)s %(sp)s %(sp)s 1</specular>\n'
            '            <pbr>\n'
            '              <metal>\n'
            '                <metalness>%(m)s</metalness>\n'
            '                <roughness>%(rg)s</roughness>\n'
            '              </metal>\n'
            '            </pbr>\n'
            '          </material>' % {
                'dr': dr, 'dg': dg, 'db': db, 'sp': spec, 'm': metal, 'rg': rough})


def _link_sdf(link_name, pose, geom_sdf, color, finish=None):
    return (
        '      <link name="%(ln)s">\n'
        '        <pose>%(px)s %(py)s %(pz)s %(pr)s %(pp)s %(pyaw)s</pose>\n'
        '        <collision name="%(ln)s_collision">\n'
        '          <geometry>%(geom)s</geometry>\n'
        '        </collision>\n'
        '        <visual name="%(ln)s_visual">\n'
        '          <geometry>%(geom)s</geometry>\n'
        '%(mat)s\n'
        '        </visual>\n'
        '      </link>' % {
            'ln': link_name, 'geom': geom_sdf, 'mat': _material_sdf(color, finish),
            'px': pose[0], 'py': pose[1], 'pz': pose[2],
            'pr': pose[3], 'pp': pose[4], 'pyaw': pose[5]})


def _obstacle_model_sdf(ob):
    """单个实体 → 一个 `<model>`（复合实体 = 一个 model 含多个 static link）。

 **视觉与碰撞同源**：同一 `<geometry>` 片段同时注入 collision 与 visual（禁止装饰性实体）。
 复合模型（`parts`）的 part pose 是**相对锚点**的局部偏移 + 局部 yaw。
    """
    color = ob.get('color') or [0.7, 0.7, 0.7]
    if not is_composite(ob):
        return ('\n    <model name="%(id)s">\n'
                '      <static>true</static>\n'
                '      <pose>%(x)s %(y)s %(z)s 0 0 %(yaw)s</pose>\n'
                '%(link)s\n'
                '    </model>' % {
                    'id': ob['id'], 'x': ob['x'], 'y': ob['y'], 'z': ob['z'],
                    'yaw': ob.get('yaw', 0.0),
                    'link': _link_sdf('link', (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                                      obstacle_geometry_sdf(ob), color,
                                      obstacle_finish(ob))})
    links = []
    for part in obstacle_parts(ob):
        part_color = part.get('color') or color
        # 材质档：part 级优先，缺省继承实体级；两者都无 → 不写 PBR（旧行为）
        links.append(_link_sdf(
            part['id'], (part['x'], part['y'], part['z'], 0.0, 0.0, part['yaw']),
            obstacle_part_geometry_sdf(part), part_color,
            part_finish(part) or obstacle_finish(ob)))
    return ('\n    <model name="%(id)s">\n'
            '      <static>true</static>\n'
            '      <pose>%(x)s %(y)s %(z)s 0 0 %(yaw)s</pose>\n'
            '%(links)s\n'
            '    </model>' % {
                'id': ob['id'], 'x': ob['x'], 'y': ob['y'], 'z': ob['z'],
                'yaw': ob.get('yaw', 0.0), 'links': '\n'.join(links)})


def _inject_static_obstacles(src_path, dst_path, geometry):
    """由**地图 yaml 的 obstacles**向 base world 注入静态障碍 `<model>` 块，
 生成运行期世界写入临时文件。

 **不**手写第二份完整 world：base world（光源/地面/物理/插件/`spherical_coordinates`）
 原样保留，仅把配置文件障碍**逐值**注入到 `</world>` 之前——保证几何**只**来自配置文件、
 「无障碍」只改障碍因子（`none` 直接用 base，不注入）、**不改世界其它物理**。
按 `shape` 生成 `<box>` / `<cylinder>` / `<sphere>`，支持**复合模型**（`parts` →
 多 static link）；**视觉与碰撞同源**。
    """
    with open(src_path, 'r') as f:
        text = f.read()
    if '</world>' not in text:
        raise RuntimeError('world 生成失败：base world %s 无 </world> 锚点' % src_path)
    injected = ''.join(_obstacle_model_sdf(ob) for ob in (geometry.get('obstacles') or []))
    idx = text.rfind('</world>')
    out = text[:idx] + injected + '\n\n  ' + text[idx:]
    with open(dst_path, 'w') as f:
        f.write(out)
    return dst_path


def _make_gz_sim(world_file, ros_gz_sim_launch, sim_share):
    """按 `world_map` × `world_obstacles` 选择世界：
 * `static` —— base world + 由**所选地图配置文件**注入障碍的生成世界（临时文件，按地图命名）；
 * `none` —— base world 本身（**已无**障碍，不注入）。
 世界路径经 gz_args token（按 basename 匹配替换，兼容相对/绝对）单一指定，不由上层手写。
运行期世界文件名带地图名（`agc_world_static_obstacles_<map>.sdf`），使并行/
 连续 run 的不同地图不会互相覆盖；`minimal` 保留历史文件名 `agc_world_static_obstacles.sdf`
 （既有脚本 `scripts/archive/run_w6_r026.sh` 与 `tests/check_scene_axis_carriers.py` 按该名取证）。
 几何在 `_opaque` 内**按实际 `world_map`** 读取（不在 generate 阶段预读，避免读到默认图）。
    """
    def _opaque(context, *args, **kwargs):
        gz_args = LaunchConfiguration('gz_args').perform(context)
        world_obstacles = LaunchConfiguration('world_obstacles').perform(context)
        world_map = LaunchConfiguration('world_map').perform(context)
        map_name, geom_path = geometry_file_for_map(sim_share, world_map)
        geometry = _load_geometry(geom_path)
        if world_obstacles == 'static':
            suffix = '' if map_name == DEFAULT_WORLD_MAP else '_' + map_name
            world = os.path.join(
                tempfile.gettempdir(), 'agc_world_static_obstacles%s.sdf' % suffix)
            _inject_static_obstacles(world_file, world, geometry)
        elif world_obstacles == 'none':
            world = world_file
        else:
            raise RuntimeError(
                '未知 world_obstacles=%s（可用：static | none）→ 拒绝运行' % world_obstacles)
        base = os.path.basename(world_file)
        tokens = gz_args.split()
        replaced = [world if os.path.basename(t) == base else t for t in tokens]
        if not any(os.path.basename(t) == base for t in tokens):
            replaced.append(world)
        gz_args = ' '.join(replaced)
        backend = LaunchConfiguration('gui_render_backend').perform(context)
        render_env = select_gui_render_env(backend)
        print('[world_bringup] world_map=%s world_obstacles=%s geometry=%s'
              % (map_name, world_obstacles, geom_path))
        print('[world_bringup] %s' % describe(backend, render_env))
        actions = [SetEnvironmentVariable(k, v) for k, v in sorted(render_env.items())]
        actions.append(IncludeLaunchDescription(
            PythonLaunchDescriptionSource(ros_gz_sim_launch),
            launch_arguments={'gz_args': gz_args}.items()))
        return actions
    return OpaqueFunction(function=_opaque)


def generate_launch_description():
    share = get_package_share_directory('agc_sim')
    car = _load_yaml(os.path.join(share, 'config', 'car.yaml'))['agc_sim']['car']
    target = _load_yaml(os.path.join(share, 'config', 'target.yaml'))['agc_sim']['target']

    world_file = os.path.join(share, 'worlds', 'agc_world.sdf')
    car_xacro = os.path.join(share, 'models', 'agc_car', 'agc_car.sdf.xacro')
    target_xacro = os.path.join(share, 'models', 'intruder_uav', 'intruder_uav.sdf.xacro')
    bridge_cfg = os.path.join(share, 'config', 'bridge.yaml')
    ros_gz_sim_launch = os.path.join(
        get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')

    car_m = car['model']
    car_s = car['spawn']
    tgt_m = target['model']
    tgt_s = target['spawn']

    # F1（2026-10-31）：spawn 位可被上层（`main.launch.py` 由出生布局配置文件派生）显式覆盖；
    # 缺省 **'auto'** = 用本文件读到的 car.yaml / target.yaml 值 → standalone 行为逐字不变。
    # 为什么需要这个口：世界 spawn 与 `/agc/scenario/reset` 的复位位置必须**同一组坐标**，
    # 否则复位会把实体从出生点"挪走"（实测口径见 composition.apply_spawn_layout）。
    def _spawn_arg(name, default):
        return DeclareLaunchArgument(
            name, default_value=str(default),
            description='spawn %s（world ENU；auto=用 config 里的缺省值）' % name)

    spawn_args = [
        _spawn_arg('car_x', car_s['x']), _spawn_arg('car_y', car_s['y']),
        _spawn_arg('car_z', car_s['z']), _spawn_arg('car_yaw', car_s['yaw']),
        _spawn_arg('target_x', tgt_s['x']), _spawn_arg('target_y', tgt_s['y']),
        _spawn_arg('target_z', tgt_s['z']), _spawn_arg('target_yaw', tgt_s['yaw']),
    ]

    def _spawn_value(context, name, default):
        """`auto`/空 → 用 config 缺省；否则解析为**有限**数值（非法 / NaN / ±Inf → 拒绝运行）。

 `auto` 分支同样校验：config 缺省值来自 `car.yaml` / `target.yaml`，若被改成 `.nan`
 也必须在启动前挡住——否则实体被静默放到 NaN 位姿上（`gz create` 不报错）。
        """
        raw = (LaunchConfiguration(name).perform(context) or '').strip()
        src = 'config 缺省'
        if raw not in ('', 'auto'):
            src = 'launch 参数'
        else:
            raw = str(default)
        try:
            val = float(raw)
        except ValueError:
            raise RuntimeError(
                'spawn 参数 %s=%r（来源：%s）非数值（可用：有限数值 | auto）→ 拒绝运行'
                % (name, raw, src))
        if not math.isfinite(val):
            # NaN 会让一切区间比较恒假；±Inf 会让 create/物理出现非有限位姿。
            raise RuntimeError(
                'spawn 参数 %s=%r（来源：%s）非有限值（NaN/±Inf）→ 拒绝运行' % (name, raw, src))
        return raw

    def _spawn_kwargs(context):
        return {
            'car_x': _spawn_value(context, 'car_x', car_s['x']),
            'car_y': _spawn_value(context, 'car_y', car_s['y']),
            'car_z': _spawn_value(context, 'car_z', car_s['z']),
            'car_yaw': _spawn_value(context, 'car_yaw', car_s['yaw']),
            'target_x': _spawn_value(context, 'target_x', tgt_s['x']),
            'target_y': _spawn_value(context, 'target_y', tgt_s['y']),
            'target_z': _spawn_value(context, 'target_z', tgt_s['z']),
            'target_yaw': _spawn_value(context, 'target_yaw', tgt_s['yaw']),
        }

    def _spawn_kwargs(context):
        return {
            'car_x': _spawn_value(context, 'car_x', car_s['x']),
            'car_y': _spawn_value(context, 'car_y', car_s['y']),
            'car_z': _spawn_value(context, 'car_z', car_s['z']),
            'car_yaw': _spawn_value(context, 'car_yaw', car_s['yaw']),
            'target_x': _spawn_value(context, 'target_x', tgt_s['x']),
            'target_y': _spawn_value(context, 'target_y', tgt_s['y']),
            'target_z': _spawn_value(context, 'target_z', tgt_s['z']),
            'target_yaw': _spawn_value(context, 'target_yaw', tgt_s['yaw']),
        }

    declared = [
        DeclareLaunchArgument(
            'gz_args', default_value=['-r -v 3 ', world_file],
            description='Arguments passed to gz sim（更 -s 可无头）'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        # 车（F1：spawn 位可被上层显式覆盖；`auto` = 用 config 缺省）
        *spawn_args[:4],
        DeclareLaunchArgument('car_wheel_separation', default_value=str(car_m['wheel_separation'])),
        DeclareLaunchArgument('car_wheel_radius', default_value=str(car_m['wheel_radius'])),
        DeclareLaunchArgument('car_wheel_width', default_value=str(car_m['wheel_width'])),
        DeclareLaunchArgument('car_max_wheel_torque', default_value=str(car_m['max_wheel_torque'])),
        DeclareLaunchArgument('car_max_wheel_acceleration', default_value=str(car_m['max_wheel_acceleration'])),
        DeclareLaunchArgument('car_max_linear_velocity', default_value=str(car_m['max_linear_velocity'])),
        DeclareLaunchArgument('car_max_angular_velocity', default_value=str(car_m['max_angular_velocity'])),
        DeclareLaunchArgument('car_body_length', default_value=str(car_m['body_length'])),
        DeclareLaunchArgument('car_body_width', default_value=str(car_m['body_width'])),
        DeclareLaunchArgument('car_body_height', default_value=str(car_m['body_height'])),
        DeclareLaunchArgument('car_body_mass', default_value=str(car_m['body_mass'])),
        DeclareLaunchArgument('car_capture_net_radius', default_value=str(car_m['capture_net_radius'])),
        DeclareLaunchArgument('car_payload_mass', default_value=str(car_m['payload_mass'])),
        DeclareLaunchArgument('car_cmd_deadman_timeout_s', default_value=str(car_m['cmd_deadman_timeout_s'])),
        # 目标（F1：spawn 位同样可覆盖；`auto` = 用 config 缺省）
        *spawn_args[4:],
        DeclareLaunchArgument('target_body_length', default_value=str(tgt_m['body_length'])),
        DeclareLaunchArgument('target_body_width', default_value=str(tgt_m['body_width'])),
        DeclareLaunchArgument('target_body_height', default_value=str(tgt_m['body_height'])),
        DeclareLaunchArgument('target_body_mass', default_value=str(tgt_m['body_mass'])),
        DeclareLaunchArgument(
            'target_controlled', default_value='false',
            description='目标模型模式：false=被动失重；'
                        'true=PX4 可控机型（merge x500，由第二 PX4 实例控制）'),
        # / ：按场景障碍轴选择世界。
        # static —— base world 由配置文件注入障碍（含 pole_*）；
        # none —— base world 本身（不含任何障碍）。
        DeclareLaunchArgument(
            'world_obstacles', default_value='static',
            description='障碍轴世界生成：static（由所选地图几何注入障碍）| none（base world，无任何障碍）'),
        # 配置文件按地图分文件——minimal（config/world_geometry.yaml，默认）|
        # yard / open_field（config/maps/*.yaml）。未知值拒绝运行。
        DeclareLaunchArgument(
            'world_map', default_value=DEFAULT_WORLD_MAP,
            description='地图（几何来源选择）：minimal（默认，核查基线）| yard（演示主地图）| '
                        'open_field（能力对照）'),
        DeclareLaunchArgument(
            'gui_render_backend', default_value='auto',
            description='GUI 渲染后端：auto（WSL2 + /dev/dxg + X11 自动 D3D12）| d3d12 | software；'
                        'headless（gz -s）忽略'),
    ]

    # gz sim（世界）：按 `world_map` × `world_obstacles` 由**单一配置文件**注入 / 不注入生成
    gz_sim = _make_gz_sim(world_file, ros_gz_sim_launch, share)

    # ros_gz 桥（话题，声明式 YAML）
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        parameters=[{
            'config_file': bridge_cfg,
            'expand_gz_topic_names': True,
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
        output='screen',
    )

    # ros_gz 桥（set_pose 服务，CLI 形式）
    # 本机 ros_gz_bridge(1.0.24) 的 YAML 服务条目在 factory 侧会因空 topic 名崩溃，
    # 故该服务以 CLI 形式桥接（等价），见 config/bridge.yaml 注释。
    set_pose_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='set_pose_bridge',
        arguments=['/world/agc_world/set_pose@ros_gz_interfaces/srv/SetEntityPose'],
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        output='screen',
    )

    # spawn 车（xacro → SDF 字符串）
    car_desc = Command([
        FindExecutable(name='xacro'), ' ', car_xacro,
        ' wheel_separation:=', LaunchConfiguration('car_wheel_separation'),
        ' wheel_radius:=', LaunchConfiguration('car_wheel_radius'),
        ' wheel_width:=', LaunchConfiguration('car_wheel_width'),
        ' max_wheel_torque:=', LaunchConfiguration('car_max_wheel_torque'),
        ' max_wheel_acceleration:=', LaunchConfiguration('car_max_wheel_acceleration'),
        ' max_linear_velocity:=', LaunchConfiguration('car_max_linear_velocity'),
        ' max_angular_velocity:=', LaunchConfiguration('car_max_angular_velocity'),
        ' body_length:=', LaunchConfiguration('car_body_length'),
        ' body_width:=', LaunchConfiguration('car_body_width'),
        ' body_height:=', LaunchConfiguration('car_body_height'),
        ' body_mass:=', LaunchConfiguration('car_body_mass'),
        ' capture_net_radius:=', LaunchConfiguration('car_capture_net_radius'),
        ' payload_mass:=', LaunchConfiguration('car_payload_mass'),
        ' cmd_deadman_timeout_s:=', LaunchConfiguration('car_cmd_deadman_timeout_s'),
    ])
    # spawn 车 / 目标（F1：坐标在 OpaqueFunction 内**解析后**注入——`auto` 落到 config 缺省，
    # 显式值时逐值使用；同时把生效值打印出来，便于与复位日志逐项比对）。
    def _spawn_actions(context, *args, **kwargs):
        kw = _spawn_kwargs(context)
        print('[world_bringup] spawn car=(%s,%s,%s,%s) target=(%s,%s,%s,%s)'
              % (kw['car_x'], kw['car_y'], kw['car_z'], kw['car_yaw'],
                 kw['target_x'], kw['target_y'], kw['target_z'], kw['target_yaw']))
        car_node = Node(
            package='ros_gz_sim', executable='create', output='screen',
            arguments=[
                '-world', 'agc_world', '-name', 'agc_car', '-string', car_desc,
                '-x', kw['car_x'], '-y', kw['car_y'], '-z', kw['car_z'], '-Y', kw['car_yaw'],
            ],
        )
        target_node = Node(
            package='ros_gz_sim', executable='create', output='screen',
            arguments=[
                '-world', 'agc_world', '-name', 'intruder_uav', '-string', target_desc,
                '-x', kw['target_x'], '-y', kw['target_y'], '-z', kw['target_z'],
                '-Y', kw['target_yaw'],
            ],
        )
        return [TimerAction(period=15.0, actions=[car_node, target_node])]

    # spawn 目标（与车同一条 OpaqueFunction，见上；此处只构造模型描述串）
    target_desc = Command([
        FindExecutable(name='xacro'), ' ', target_xacro,
        ' controlled:=', LaunchConfiguration('target_controlled'),
        ' body_length:=', LaunchConfiguration('target_body_length'),
        ' body_width:=', LaunchConfiguration('target_body_width'),
        ' body_height:=', LaunchConfiguration('target_body_height'),
        ' body_mass:=', LaunchConfiguration('target_body_mass'),
    ])

    ld = LaunchDescription()
    for a in declared:
        ld.add_action(a)
    # 模型资源路径：agc_car 的 mesh 用 `model://agc_car/...`，需将此 models 目录加入 gz 资源搜索路径
    # （**追加**而非覆盖：air_bringup 会另行追加 PX4 模型库，二者需共存）。
    sim_models = os.path.join(share, 'models')
    ld.add_action(SetEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH',
        [sim_models, ':', EnvironmentVariable('GZ_SIM_RESOURCE_PATH')]))
    # （ADR-0010）：gz 进程加载 GZ 侧末端失效停车插件 agc_cmd_deadman。
    # 插件库装于 <pkg prefix>/lib（install/agc_sim/lib），追加到 GZ_SIM_SYSTEM_PLUGIN_PATH
    # （gz_sim.launch.py 会再并入 LD_LIBRARY_PATH，故内置系统插件仍可加载）。**追加**而非覆盖。
    plugin_dir = os.path.join(os.path.dirname(share), 'lib')
    ld.add_action(SetEnvironmentVariable(
        'GZ_SIM_SYSTEM_PLUGIN_PATH',
        [plugin_dir, ':', EnvironmentVariable('GZ_SIM_SYSTEM_PLUGIN_PATH')]))
    ld.add_action(gz_sim)
    ld.add_action(bridge)
    ld.add_action(set_pose_bridge)
    # F1：spawn 动作在 OpaqueFunction 内按**解析后**坐标生成（`auto` → config 缺省）。
    ld.add_action(OpaqueFunction(function=_spawn_actions))
    return ld