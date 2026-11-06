#!/usr/bin/env python3
"""w6_composition —— W6 场景配置解析的**单一真源**（结构评审 S-05；ADR-0020）。

本模块集中承载 W6 顶层 composition 的**全部**场景配置解析逻辑，供统一入口
`w6.launch.py` 复用（`backend` ∈ `lightweight` | `full`）：base/registry/carriers 加载、
carrier 承载者校验、参数合并、轴断言、manifest 生成、临时文件落盘。**不再**在多入口内联重复。

约束类信息（参数入口 / 唯一执行口 / 命名空间 / 硬约束 C1–C10 / 终态语义）**只引用不复述**，
真源见 `docs/ROS2迁移交接文档.md` 的对应锚点。

设计要点（S-05）：
  * `BACKENDS` 为 **backend 能力表**：每 backend 声明 `air_link` / `px4` / `target_source` /
    `required_nodes`（完整展开节点名）/ `supported_axes`；`coverage_status` 的 `not_carried`
    状态**由能力表派生**（不再逐文件硬编码「轻量栈无空中链路」）。
  * manifest 身份与入口名一致：`launch='w6.launch.py'` + 实际 `backend` + `nodes`（展开节点）
    + 生效参数（`scene` / `seed` / `support_status` / `declared_axes` / `expected_terminal` /
    `expected_reason` / `carriers` / `effective_params` / `assertions`）。

设计要点（S-06）：单一几何真源 `agc_sim/config/world_geometry.yaml` 的读取（`load_geometry`）
与内容哈希（`geometry_sha256`）；按域**派生**——感知障碍先验（`write_derived_obstacles`）、
感知地图几何（`write_derived_map`）、`scenario_reset` 障碍 / 边界与空中安全列表注入
（`compose_params` / `apply_air_geometry`）；manifest 记 `geometry` 块；`assertions` 断言
「派生几何 == 真源」。
"""

import hashlib
import json
import math
import os
import random
import tempfile
import time

import yaml

# 统一入口文件名（manifest `launch` 字段须与入口名一致，S-05）。
LAUNCH = 'w6.launch.py'

# S-06：静态障碍 + 作业区几何的**单一真源**（位于 agc_sim share 的 config/ 下）。
GEOMETRY_FILE = 'world_geometry.yaml'

# P1-1：真源按**地图**分文件。**单一清单**在 `agc_sim/launch/world_map.py`（随包安装到
# `share/agc_sim/launch`，与 `world_bringup.launch.py` 同目录）。本模块经 `sim_share` 解析后
# import 该模块，**不再自持第二份文件名表**——两份表漂移会让不同域读到不同真源，
# 正是 ADR-0007 要消灭的病灶。
DEFAULT_WORLD_MAP = 'minimal'

# 源码树定位（未 source 安装环境时的回退）：本文件位于 `src/agc_task/launch/`，
# 同级 `src/agc_sim/launch/world_map.py` 即源码副本（与安装副本同一符号链接目标）。
_SRC_SIM_LAUNCH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'agc_sim', 'launch')
# ADR-0007：`air.yaml` 源码树回退路径（lightweight 后端不起空中链路，但高度断言仍需
# safe_max / hysteresis 做 K1 判据）。与 `_SRC_SIM_LAUNCH` 同款回退口径。
_SRC_AIR_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'agc_air', 'config')

_WORLD_MAP_CACHE = {}


def world_map_module(sim_share=None):
    """加载 `agc_sim` 的 `world_map` 清单模块（共享模块边界的**唯一实现**）。

    优先从**安装后的 share**（`<sim_share>/launch/world_map.py`）导入，与 `world_bringup`
    读到同一份清单；未提供 / 不存在时回退到源码树路径。按路径缓存，避免重复 exec。
    """
    import importlib.util
    candidates = []
    if sim_share:
        candidates.append(os.path.join(sim_share, 'launch', 'world_map.py'))
    candidates.append(os.path.join(_SRC_SIM_LAUNCH, 'world_map.py'))
    for path in candidates:
        if not os.path.exists(path):
            continue
        cache_key = os.path.realpath(path)
        if cache_key in _WORLD_MAP_CACHE:
            return _WORLD_MAP_CACHE[cache_key]
        spec = importlib.util.spec_from_file_location('agc_world_map', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _WORLD_MAP_CACHE[cache_key] = mod
        return mod
    raise RuntimeError(
        '找不到几何真源地图清单 world_map.py（尝试：%s）→ 拒绝运行' % ', '.join(candidates))


def new_run_token():
    """S-07（ADR-0006）：每次调用生成唯一 token（时刻 + 进程 + 随机），供临时文件命名避免并发 / 重复覆盖。"""
    return '%s-%s-%d-%04d' % (time.strftime('%Y%m%d'), time.strftime('%H%M%S'),
                              os.getpid(), random.randint(0, 9999))


def resolve_world_map(world_map, sim_share=None):
    """校验并规范化 `world_map`；未知值**拒绝运行**（不静默回退 minimal）。"""
    return world_map_module(sim_share).resolve(world_map)


def geometry_path(sim_share, world_map=DEFAULT_WORLD_MAP):
    """按地图解析真源绝对路径（P1-1）。`minimal` → `config/world_geometry.yaml`。"""
    return world_map_module(sim_share).geometry_path(sim_share, world_map)


def load_geometry(sim_share, world_map=DEFAULT_WORLD_MAP):
    """读**单一几何真源**（S-06；ADR-0007）；P1-1 起按 `world_map` 选文件。"""
    _, path = geometry_path(sim_share, world_map)
    with open(path) as f:
        return yaml.safe_load(f)


def geometry_sha256(sim_share, world_map=DEFAULT_WORLD_MAP):
    """真源文件**字节**的 sha256（几何版本身份；写入 manifest）。P1-1：按地图区分。"""
    _, path = geometry_path(sim_share, world_map)
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------- 出生布局（F1）
# 出生布局坐标的**单一真源**（F1，2026-10-31）：`agc_task/config/spawn_layout.yaml`。
# 为什么需要它：世界 spawn（world_bringup 的 car_x/target_x…）、复位位置（scenario_reset 的
# 同一组参数）、己方机起飞参考（PX4_GZ_MODEL_POSE 与空中节点 origin_pose）**原本各自写默认值**
# （`car.yaml` / `target.yaml` / `base.yaml` / air.yaml / C++ declare_parameter），四份值可漂移。
# 现统一由本模块读一处、派生四处；未知/缺失键一律**拒绝运行**（不静默回退到某份旧默认值）。
SPAWN_LAYOUT_FILE = 'spawn_layout.yaml'


def load_spawn_layout(task_share, path=None):
    """读出生布局真源；缺键 / 非数值 / **非有限值（NaN·±Inf）** → `RuntimeError`（拒绝运行）。

    `path` 仅供测试注入（缺省即真源文件），避免测试为造非法值去改真源。

    为什么必须查 `isfinite`：`float('nan')` / `float('inf')` 都能通过 `float()` 转换，但一旦注入
    世界 `create` 或 `scenario_reset`，位姿校验的比较式（`< min` / `> max`）对 NaN **恒为假**，
    于是"越界 / 净空不足"的拒绝分支**永远不会触发**，实体会被静默放到 NaN 位姿上。
    YAML 里 `.nan` / `.inf` 是合法字面量 ⇒ 这不是假想输入。
    """
    path = path or os.path.join(task_share, 'config', SPAWN_LAYOUT_FILE)
    with open(path) as f:
        doc = yaml.safe_load(f) or {}
    layout = doc.get('spawn_layout')
    if not isinstance(layout, dict):
        raise RuntimeError('出生布局真源 %s 缺少顶层 `spawn_layout` → 拒绝运行' % path)
    out = {}
    for entity, keys in (
            ('car', ('x', 'y', 'yaw', 'world_z', 'reset_z')),
            ('target', ('x', 'y', 'z', 'yaw')),
            ('own_uav', ('x', 'y', 'z', 'yaw'))):
        sec = layout.get(entity)
        if not isinstance(sec, dict):
            raise RuntimeError(
                '出生布局真源 %s 缺少 `spawn_layout.%s` → 拒绝运行' % (path, entity))
        vals = {}
        for k in keys:
            if k not in sec:
                raise RuntimeError(
                    '出生布局真源 %s 缺少 `spawn_layout.%s.%s` → 拒绝运行' % (path, entity, k))
            raw = sec[k]
            try:
                val = float(raw)
            except (TypeError, ValueError):
                raise RuntimeError(
                    '出生布局真源 %s 的 `spawn_layout.%s.%s`=%r 非数值 → 拒绝运行'
                    % (path, entity, k, raw))
            if not math.isfinite(val):
                # NaN / ±Inf：比较式对 NaN 恒假 → 越界与净空拒绝分支失效（静默放行）。
                raise RuntimeError(
                    '出生布局真源 %s 的 `spawn_layout.%s.%s`=%r 非有限值（NaN/±Inf）→ 拒绝运行'
                    % (path, entity, k, raw))
            vals[k] = val
        out[entity] = vals
    # 固定任务目标的派生偏移（F1 round-2）：缺省 (−2.5, 0)。缺键时用缺省而不是拒绝——
    # 它是"派生规则参数"，不是出生位本身；但一旦出现就必须是有限数值。
    off = layout.get('goal_offset_m') or {}
    if not isinstance(off, dict):
        raise RuntimeError(
            '出生布局真源 %s 的 `spawn_layout.goal_offset_m` 非映射 → 拒绝运行' % path)
    goal_off = {}
    for k, default in (('dx', -2.5), ('dy', 0.0)):
        raw = off.get(k, default)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            raise RuntimeError(
                '出生布局真源 %s 的 `goal_offset_m.%s`=%r 非数值 → 拒绝运行' % (path, k, raw))
        if not math.isfinite(val):
            raise RuntimeError(
                '出生布局真源 %s 的 `goal_offset_m.%s`=%r 非有限值 → 拒绝运行' % (path, k, raw))
        goal_off[k] = val
    out['goal_offset_m'] = goal_off
    out['source'] = path
    return out


def spawn_layout_sha256(task_share):
    """出生布局真源文件的 sha256（布局版本身份；写入 manifest，便于审查核对）。"""
    path = os.path.join(task_share, 'config', SPAWN_LAYOUT_FILE)
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def own_uav_pose_string(layout, override=None):
    """己方机 spawn 位姿字符串（`x,y,z,roll,pitch,yaw`）——PX4_GZ_MODEL_POSE 与 origin_pose
    **共用同一字符串**（同一 launch 参数），故"起飞参考"与"净空校验坐标"不可能不一致。

    `override` 非空（launch 显式 `px4_own_pose:=…`）时**原样返回**，不再从 layout 拼——
    证据与距离必须用这个真实生效的字符串，而不是 layout 的缺省值（否则会造出
    "manifest 说 own=(−11,1)、实际飞在别处"的自洽假象）。
    """
    if override:
        return override.strip()
    own = layout['own_uav']
    return '%g,%g,%g,0,0,%g' % (own['x'], own['y'], own['z'], own['yaw'])


def parse_own_pose(pose_string, layout=None):
    """解析己方机位姿字符串 → `{x, y, z, yaw, source}`；非法 / 非有限值 → `RuntimeError`。

    `source` ∈ `'override'`（launch 显式给出）| `'layout'`（取自出生布局真源）。
    非法值**拒绝运行**而不是 WARN 后按布局兜底：兜底会让"声明的位置"与"实际飞的位置"
    悄悄分叉，正是本轮要消灭的那类证据失真。
    """
    parts = [p.strip() for p in str(pose_string).split(',')]
    if len(parts) < 6:
        raise RuntimeError(
            '己方机位姿 %r 需要 6 个分量（x,y,z,roll,pitch,yaw）→ 拒绝运行' % (pose_string,))
    try:
        vals = [float(p) for p in parts[:6]]
    except ValueError:
        raise RuntimeError('己方机位姿 %r 含非数值分量 → 拒绝运行' % (pose_string,))
    if not all(math.isfinite(v) for v in vals):
        raise RuntimeError('己方机位姿 %r 含非有限值（NaN/±Inf）→ 拒绝运行' % (pose_string,))
    is_layout = bool(layout) and pose_string.strip() == own_uav_pose_string(layout)
    return {'x': vals[0], 'y': vals[1], 'z': vals[2], 'yaw': vals[5],
            'source': 'layout' if is_layout else 'override'}


def spawn_layout_distances(layout):
    """三组设计距离（车↔目标 / 己方机↔目标 / 车↔己方机）。

    `layout` 可为**实际生效**的位姿字典（`{'car':…, 'target':…, 'own_uav':…}`）——默认场景下
    即 `{'car': effective.car, 'target': effective.target, 'own_uav': 实际生效 own}`。
    传入 layout 真源与传入生效值得到**不同**结果，这正是"距离必须跟实际生效位一致"的落点。
    """
    car, tgt, own = layout['car'], layout['target'], layout['own_uav']
    return {
        'car_target_m': math.hypot(car['x'] - tgt['x'], car['y'] - tgt['y']),
        'own_uav_target_m': math.hypot(own['x'] - tgt['x'], own['y'] - tgt['y']),
        'car_own_uav_m': math.hypot(car['x'] - own['x'], car['y'] - own['y']),
    }


def apply_spawn_layout(merged, layout, sc=None):
    """把出生布局注入合并参数，返回**实际生效**的出生位（世界 spawn 与复位同值）。

    优先级（三级，从高到低）：**场景层显式覆盖 > 出生布局真源 > base / 节点缺省**。

    * 为什么场景覆盖仍可生效：部分场景的"出生位"本身承载**场景语义**，不是"默认出生点"——
      例如 `s11` 的"车被立柱阻隔"、`s10` 的"目标置远 → 必然超时"。用布局真源盖掉它们等于
      改掉这些场景的验收口径（不在本单范围）。故布局真源只提供**缺省**，场景可覆盖。
    * 为什么这不破坏"三者一致"：世界 spawn 取的是**本函数的返回值**（`w6.launch.py` 用它喂
      `world_bringup` 的 `car_x/target_x…`），而复位参数也是同一份 `merged`。二者同源，
      所以"世界 spawn == 复位位置"对**任何**场景都成立，而不只是默认场景。
    * `z` 分两种口径：世界 spawn 的车 z = **轮触地**（布局 `world_z`，模型几何属性，不随场景变），
      复位车 z = 布局 `reset_z`（`scenario_reset` 既有口径 0.010）。

    返回 `{'car': {x,y,yaw,world_z,reset_z}, 'target': {x,y,z,yaw}, 'source': 'scene'|'layout'}`；
    `source` 记明该 run 的出生位来自布局真源还是场景覆盖，写入 manifest 供审查区分。
    """
    car, tgt = layout['car'], layout['target']
    sr = merged.setdefault('scenario_reset', {})
    scene_sr = ((sc or {}).get('params') or {}).get('scenario_reset') or {}
    use_scene = bool(scene_sr)
    eff_car = {
        'x': float(scene_sr.get('car_x', car['x'])),
        'y': float(scene_sr.get('car_y', car['y'])),
        'yaw': float(scene_sr.get('car_yaw', car['yaw'])),
        # 轮触地高度是模型几何属性，不随出生点变；场景若显式给 car_z，那只是复位口径。
        'world_z': car['world_z'],
        'reset_z': float(scene_sr.get('car_z', car['reset_z'])),
    }
    eff_tgt = {
        'x': float(scene_sr.get('target_x', tgt['x'])),
        'y': float(scene_sr.get('target_y', tgt['y'])),
        'z': float(scene_sr.get('target_z', tgt['z'])),
        'yaw': float(scene_sr.get('target_yaw', tgt['yaw'])),
    }
    sr['car_x'] = eff_car['x']
    sr['car_y'] = eff_car['y']
    sr['car_z'] = eff_car['reset_z']
    sr['car_yaw'] = eff_car['yaw']
    sr['target_x'] = eff_tgt['x']
    sr['target_y'] = eff_tgt['y']
    sr['target_z'] = eff_tgt['z']
    sr['target_yaw'] = eff_tgt['yaw']

    # ---- 固定任务目标：默认场景由「目标出生位 + goal_offset_m」派生（F1 round-2）----
    # 触发条件（三条同时成立才派生）：
    #   ① 场景**未**显式给 `task_manager.goal_x/goal_y`（显式值属场景语义，如 s08/s11 的配套目标）；
    #   ② `goal_follow_target` 为假（为真时任务目标由感知目标实时决定，固定点无意义）；
    #   ③ 场景**未**显式给 `scenario_reset.target_*`——否则该场景的目标位是"置远/被阻隔"等
    #      语义设定，派生一个 2.5 m 邻域目标会把 s10 的"必然超时"改成"可达"（改验收口径）。
    tm = merged.setdefault('task_manager', {})
    scene_tm = ((sc or {}).get('params') or {}).get('task_manager') or {}
    follow = bool(tm.get('goal_follow_target', False))
    explicit_goal = ('goal_x' in scene_tm) or ('goal_y' in scene_tm)
    explicit_target = any(k in scene_sr for k in ('target_x', 'target_y'))
    goal_src = 'scene' if explicit_goal else ('derived' if not follow and not explicit_target
                                             else 'base')
    if not explicit_goal and not follow and not explicit_target:
        off = layout.get('goal_offset_m') or {'dx': -2.5, 'dy': 0.0}
        tm['goal_x'] = eff_tgt['x'] + float(off['dx'])
        tm['goal_y'] = eff_tgt['y'] + float(off['dy'])
    return {'car': eff_car, 'target': eff_tgt, 'source': 'scene' if use_scene else 'layout',
            'goal_source': goal_src,
            # 实际生效的固定任务目标（供 manifest / 断言同源比对）。
            'goal_x': float(tm.get('goal_x', 0.0)), 'goal_y': float(tm.get('goal_y', 0.0))}


def obstacle_shape(ob, sim_share=None):
    """实体形状（schema 缺省 = box；ADR-0007 向后兼容——老配置不写 shape 仍可运行）。"""
    return world_map_module(sim_share).obstacle_shape(ob)


def obstacle_safety_radius(ob, sim_share=None):
    """实体水平面**外接圆半径**（空中安全层为二维圆盘模型，须覆盖实体几何）。

    `safety_radius` 缺省 2.0 = 历史 pole 标定值；P1-1 起由真源**逐障碍**给出，
    消除旧的「与障碍数对齐的定长列表」（ADR-0007 未决项②）。
    """
    return world_map_module(sim_share).obstacle_safety_radius(ob)


def geometry_safety_radii(geometry, sim_share=None):
    """按障碍派生的安全半径列表（与 `geometry_ids` 同序；`apply_air_geometry` 使用）。"""
    return [obstacle_safety_radius(ob, sim_share)
            for ob in (geometry.get('obstacles') or [])]


def obstacle_z_top(ob, sim_share=None):
    """实体**顶面高度**（世界 ENU，m；复合体取全部 part 的最大值）。

    消费者 = 空中安全层**垂直门控**（ADR-0010「垂直门控」）：本机高度高于
    `z_top + c_clear` 时，该障碍的水平圆盘对本机不生效。真源已含 `z` + `size[2]`，
    本函数只做派生，**不**新增 schema 键。
    """
    return world_map_module(sim_share).obstacle_z_top(ob)


def geometry_z_tops(geometry, sim_share=None):
    """按障碍派生的顶高列表（与 `geometry_ids` 同序；`apply_air_geometry` 使用）。"""
    return [obstacle_z_top(ob, sim_share)
            for ob in (geometry.get('obstacles') or [])]


def obstacle_bbox_size(ob, sim_share=None):
    """感知先验 / 地图栅格的障碍尺寸（**降级为水平轴对齐包络**）。

    `map_adapter` / `air_perception` 的障碍模型是 OBB（只有 sx/sy/sz + yaw），无法表达圆柱 /
    球 / 多图元复合体；故一律降级为包络矩形（保守外扩，不缩小实体）。该降级为成文约定，
    见 P1-1 规格「派生点需同步改」）。
    """
    return world_map_module(sim_share).obstacle_bbox_size(ob)


def obstacle_is_composite(ob, sim_share=None):
    """复合模型判定（`parts` 非空）；供 manifest / 核查区分单图元与复合体。"""
    return world_map_module(sim_share).is_composite(ob)


def obstacle_footprint_radius(ob, sim_share=None):
    """实体（含复合）水平外接圆半径（覆盖全部 part）。"""
    return world_map_module(sim_share).obstacle_footprint_radius(ob)


def geometry_ids(geometry):
    return [o['id'] for o in (geometry.get('obstacles') or [])]


def geometry_xs(geometry):
    return [float(o['x']) for o in (geometry.get('obstacles') or [])]


def geometry_ys(geometry):
    return [float(o['y']) for o in (geometry.get('obstacles') or [])]


def work_area_bounds(geometry):
    """由真源 `work_area` 派生作业区边界（`map_*`，map 系）。"""
    wa = geometry['work_area']
    return {
        'map_x_min': float(wa['origin_x']),
        'map_x_max': float(wa['origin_x']) + float(wa['size_x']),
        'map_y_min': float(wa['origin_y']),
        'map_y_max': float(wa['origin_y']) + float(wa['size_y']),
    }


# backend 能力表：每 backend 声明能力事实，驱动覆盖状态派生与 manifest 节点展开。
#   * air_link      —— 是否含空中链路（PX4 / 空中节点）；False → requires_air_link 承载者 not_carried。
#   * px4           —— 是否起 PX4 SITL 实例。
#   * target_source —— 感知轴目标源。**2026-11-04 起恒为 `gt_adapter`**（air_fusion 已退役）。
#   * required_nodes —— 该 backend 完整展开的节点 / 进程名（manifest `nodes` 字段）。
#   * supported_axes —— 该 backend 实际执行的轴（不含即如实标注 not_carried / N/A）。
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
        # 整链含全部 4 轴（obstacle / outcome + target_motion / perception 的空中侧）。
        'supported_axes': ['obstacle', 'outcome', 'target_motion', 'perception'],
    },
}


def derive_px4_sim_seed(master_seed, instance):
    """Derive a stable per-PX4 simulation seed from the experiment seed.

    The PX4 processes are outside Python's RNG graph, so passing the experiment
    seed only to ``scenario_reset`` is insufficient.  Keep this small integer
    mixer here as the single launch-side derivation used by both PX4 instances
    and the run manifest.
    """
    z = (int(master_seed) + 0x9E3779B9 + int(instance) * 0x85EBCA6B) & 0xFFFFFFFF
    z = ((z ^ (z >> 16)) * 0x85EBCA6B) & 0xFFFFFFFF
    z = ((z ^ (z >> 13)) * 0xC2B2AE35) & 0xFFFFFFFF
    return (z ^ (z >> 16)) & 0xFFFFFFFF


def carrier_entry(carriers, axis, value, scene):
    """R-026：声明轴值必须有承载者；无承载者 → 显式拒绝运行（不以命名当执行）。"""
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

    S-05：不再硬编码 `backend == 'lightweight'`，而以 `BACKENDS[backend]['air_link']` 判定。
    """
    if entry.get('requires_air_link') and not BACKENDS[backend]['air_link']:
        return 'not_carried', 'backend=%s 无空中链路 / PX4（能力表 air_link=False），承载者不生效' % (
            backend,)
    return 'covered', ''


# `epicycle` 的标定参数（单一真源 = s18 / ADR-0031 §(a)）。
# CLI 覆盖到 epicycle 时必须一并对齐：base 的 `radius_m=6.0` 会让位移上界
# A+r = 6.6 m ≫ d_track 3.0 → 必然 RANGE_EXCEEDED / TIMEOUT（s04 继承的是 base，
# 不是 s18 的场景覆盖）。此处只收**与 base 不同**的项，避免复制第二份数值真源。
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
    """S-06：由真源派生**感知障碍先验文件**（`obstacles.yaml` 形态），返回 (路径, id 列表)。

    `static` → 真源障碍实体（`id/x/y/z/yaw/size`）；`none` → 空数组（与「无障碍世界」一致）。
    w6 路径**不再**读 agc_perception 包内副本（副本仅作 standalone 回退）。
    P1-1：`size` 取**感知可表达尺寸**——box 原值、cylinder 降级为外接矩形
    （`obstacle_bbox_size`；感知障碍模型是 OBB，无圆柱分支，降级为保守外扩）。
    """
    token = token or new_run_token()
    if mode == 'static':
        obstacles = [{
            'id': ob['id'], 'x': float(ob['x']), 'y': float(ob['y']), 'z': float(ob['z']),
            'yaw': float(ob.get('yaw', 0.0)), 'size': obstacle_bbox_size(ob, sim_share),
            # P1-1：形状透传（消费方当前只吃 box 尺寸，此处如实登记源形状以便审计；
            #   不新增感知语义、不改既有字段顺序）
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
    """S-06：由真源 `work_area` 派生**感知地图几何文件**（`map.yaml` 形态），返回路径。"""
    token = token or new_run_token()
    wa = geometry['work_area']
    doc = {'resolution': float(wa['resolution']), 'size_x': float(wa['size_x']),
           'size_y': float(wa['size_y']), 'origin_x': float(wa['origin_x']),
           'origin_y': float(wa['origin_y'])}
    path = os.path.join(tempfile.gettempdir(), 'w6_derived_map_%s_%d_%s.yaml' % (scene, seed, token))
    with open(path, 'w') as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=True)
    return path


def load_scene(task_share, perc_share, sim_share, scene, seed, token=None,
               world_map=None):
    """加载场景配置：base / registry / carriers，校验 scene 存在与 support_status，逐轴取承载者。

    返回结构化 dict（含 base / sc / axes / support_status / entries 与按轴选择的文件路径）；
    S-06：额外返回几何真源（`geometry` / `geometry_sha256`）与**按域派生文件**
    （`derived_obstacles_file` / `derived_map_file`）。
    P1-1：地图解析**两级**（优先级从高到低）：
      1. `world_map` 参数**显式非空** → 用它（launch `world_map:=` 覆盖；未知值拒绝运行）；
      2. 否则用**场景登记**的 `sc.world_map`（`scenarios.yaml` 的 `world_map:` 键）；
      3. 都没有 → `DEFAULT_WORLD_MAP`（minimal）。
    返回的 `world_map_source` 记明来源（`launch` / `scene` / `default`），供 manifest 审计。
    """
    token = token or new_run_token()
    base = yaml.safe_load(open(os.path.join(task_share, 'config', 'w6_base.yaml')))
    registry = yaml.safe_load(open(os.path.join(task_share, 'config', 'scenarios.yaml')))
    carriers = yaml.safe_load(
        open(os.path.join(task_share, 'config', 'scenario_carriers.yaml')))['axes']
    scenes = registry.get('scenes', {})
    if scene not in scenes:
        raise RuntimeError('unknown scene: %s; available=%s' % (scene, list(scenes)))
    sc = scenes[scene] or {}
    axes = sc.get('axes') or {}
    support_status = sc.get('support_status', 'supported')

    # P1-1：地图选择（launch 覆盖 > 场景登记 > 缺省）；未知值一律拒绝运行。
    requested = (world_map or '').strip()
    if requested:
        map_name, map_source = resolve_world_map(requested, sim_share), 'launch'
    elif (sc.get('world_map') or '').strip():
        map_name, map_source = resolve_world_map(sc['world_map'], sim_share), 'scene'
    else:
        map_name, map_source = DEFAULT_WORLD_MAP, 'default'

    # R-026 启动时校验：每个声明轴值必须有承载者（obstacle=dynamic → 拒绝运行）
    entries = {ax: carrier_entry(carriers, ax, val, scene) for ax, val in axes.items()}
    if str(support_status).startswith('unsupported'):
        raise RuntimeError(
            '场景 %s support_status=%s（声明轴无承载者）→ 拒绝运行' % (scene, support_status))

    # 按轴选择承载者文件
    sensors_file_name = entries['perception']['sensors_file']
    obstacles_file_name = entries['obstacle']['obstacles_file']
    world_obstacles = entries['obstacle']['world_obstacles']
    sensors_file = os.path.join(perc_share, 'config', sensors_file_name)

    # S-06：几何真源 + 按域派生（感知障碍先验 / 感知地图）。障碍文件改由真源派生，
    #   不再读 agc_perception 包内副本。P1-1：真源文件由 `world_map` 决定。
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
        # carriers 随 info 带出：CLI 覆盖场景轴时须按新轴值重取承载者（单一真源，不二次读盘）。
        'carriers': carriers,
        'support_status': support_status, 'entries': entries,
        'sensors_file_name': sensors_file_name, 'obstacles_file_name': obstacles_file_name,
        'world_obstacles': world_obstacles,
        'world_map': map_name,
        'world_map_source': map_source,
        'sensors_file': sensors_file,
        'obstacles_file': derived_obstacles_file,          # S-06：派生路径（非包内副本）
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

    lightweight：`task_manager.air_present=False`（无空中域，相位复位门禁 C5 不适用，R-001）。
    full：`task_manager.air_present=True` + `scenario_reset.own_uav_present/x/y`（己方机在场 + 出生净空校验透传）。
    seed 经 launch 单一覆盖（run_logger 记录 + scenario_reset 生成 spawn，C7 可复现）。
    `spawn_randomize`（W7-a · R3）：`None` = 不改（沿用 base / 场景值）；显式 `True/False` = 覆盖——
    训练视图按 seed 随机化出生位（spawn 流），缺省 `None` → 既有 W6 行为不变。
    S-06：`scenario_reset` 障碍清单 / 作业区边界由**单一几何真源**注入（w6_base 不再硬编码几何）。
    """
    merged = {node: dict(sec.get('ros__parameters', {})) for node, sec in base.items()}
    for node, over in (sc.get('params') or {}).items():
        merged.setdefault(node, {}).update(over)
    if backend == 'lightweight':
        # 轻量栈不起空中链路：task_manager 显式声明无空中域，不得由服务缺席推定（R-001）。
        merged['task_manager']['air_present'] = False
    else:
        # 整链起真实空中链路：相位复位门禁（C5）强制（R-001）。
        merged['task_manager']['air_present'] = True
        # R-014：己方机在出生净空校验中视为在场（显式运行模式），并透传其 spawn 位（world ENU）。
        merged['scenario_reset']['own_uav_present'] = True
        merged['scenario_reset']['own_uav_x'] = own_uav[0]
        merged['scenario_reset']['own_uav_y'] = own_uav[1]
    merged['run_logger']['seed'] = seed
    merged['scenario_reset']['spawn_seed'] = seed
    # W7-a（R3）：训练视图按 seed 随机化出生位（显式覆盖；缺省 None → 沿用 base / 场景值）。
    if spawn_randomize is not None:
        merged['scenario_reset']['spawn_randomize'] = bool(spawn_randomize)
    # W7-b P2 v3（ADR-0023）：任务目标是否跟随感知目标——显式覆盖场景值（None=不改）。
    if goal_follow_target is not None:
        merged.setdefault('task_manager', {})['goal_follow_target'] = bool(goal_follow_target)
    # S-06：静态障碍清单 + 作业区边界由**真源**派生注入（物理世界为 static 时注入 pole_*）。
    if geometry is not None:
        merged['scenario_reset']['obstacle_names'] = geometry_ids(geometry)
        merged['scenario_reset']['obstacle_x'] = geometry_xs(geometry)
        merged['scenario_reset']['obstacle_y'] = geometry_ys(geometry)
        merged['scenario_reset'].update(work_area_bounds(geometry))
    return merged


def apply_air_geometry(air_merged, geometry, sim_share=None):
    """S-06：把真源静态障碍几何注入空中安全列表（`trajectory_tracker.safety`）。

    `obstacle_names/x/y` 由真源派生；**P1-1：`obstacle_safety_radius` 亦按障碍派生**
    （`safety_radius` 逐障碍取值，缺省 2.0），消除旧的「与障碍数对齐的定长列表」——
    该列表加到 N 个障碍却不同步扩展时会导致 `safety_shield` 索引错位或越界
    （ADR-0007 未决项②；R-038 的五数组等长校验仍在启动期拒绝不一致）。原地修改并返回。
    `obstacle_margin` / `target_margin` / 反应时间 / 可达性等**安全余量**仍来自 `air.yaml`
    （安全参数，非几何）。

    ADR-0010「垂直门控」：另注入 `obstacle_z_top`（逐障碍顶面高度）与 `vertical_clearance_m`
    （= 地图 `flight_altitude.own_clearance_min_m`，**不另立参数**——同一张图的高度与净空同源）。
    """
    safety = air_merged.setdefault('trajectory_tracker', {}).setdefault('safety', {})
    safety['obstacle_names'] = geometry_ids(geometry)
    safety['obstacle_x'] = geometry_xs(geometry)
    safety['obstacle_y'] = geometry_ys(geometry)
    safety['obstacle_safety_radius'] = geometry_safety_radii(geometry, sim_share)
    safety['obstacle_z_top'] = geometry_z_tops(geometry, sim_share)
    safety['vertical_clearance_m'] = flight_altitude_block(geometry)['own_clearance_min_m']
    return air_merged


def flight_altitude_block(geometry):
    """ADR-0007：读地图真源里的 `flight_altitude` 块并**规范化 + 校验**。

    用户 2026-11-02 裁定：「高度和地图绑定，因为后面会做小障碍高密度和大障碍低密度等图」。
    ⇒ 每张地图在自己几何文件里声明"该图该飞多高"，运行期派生注入，`air.yaml` / `w6_base.yaml`
    的同名键降级为 standalone / 单测兜底（与 `safety.obstacle_*` 同款处理）。

    缺块 / 缺键 / 非有限值 / 非正 → **拒绝运行**（不静默回退到某份旧默认值——那正是
    ADR-0007 要消灭的第二真源）。返回规范化 dict（含 `derived` 子块，供断言比对）。
    """
    fa = (geometry or {}).get('flight_altitude')
    if not isinstance(fa, dict):
        raise RuntimeError(
            '地图几何真源缺少 flight_altitude 块（ADR-0007：高度必须随地图声明）→ 拒绝运行')
    out = {}
    for key in ('own_track_m', 'own_takeoff_m', 'target_cruise_m', 'own_clearance_min_m'):
        if key not in fa:
            raise RuntimeError('flight_altitude 缺少键 %r → 拒绝运行' % (key,))
        try:
            v = float(fa[key])
        except (TypeError, ValueError):
            raise RuntimeError('flight_altitude.%s=%r 非数值 → 拒绝运行' % (key, fa[key]))
        if not math.isfinite(v) or v <= 0.0:
            raise RuntimeError(
                'flight_altitude.%s=%r 非有限正数（NaN/±Inf/≤0）→ 拒绝运行' % (key, fa[key]))
        out[key] = v
    derived = fa.get('derived') or {}
    out['derived'] = {
        'h_max_map_m': float(derived.get('h_max_map_m') or 0.0),
        'h_max_env_m': float(derived.get('h_max_env_m') or 0.0),
        'rule_version': int(derived.get('rule_version') or 1),
    }
    return out


def net_params_for_altitude(target_cruise_m, base_cap):
    """ADR-0007：按**目标巡航高度**反推网弹道参数（仅当基线弹道打不到时使用）。

    设计口径（与 `dynamic_fire_control.hpp` 的 `netPos` / `radius` 同一套物理）：
      * 抛射角固定 **85°**（近垂直 → 水平射程小，车可停在目标近旁开火）；
      * 初速取「解析顶点 = 目标高度 + 0.65 m」反解：`v0 = √(2g(h+0.65)) / sinθ`；
      * 飞行超时 = 落地时刻 `2·v0·sinθ/g` + 0.3 s（留一个结算周期余量）。

    **只在基线弹道打不到该高度时才派生**（`apex_base < target_cruise_m`）——
    这样 `minimal` / `open_field`（目标 2.0 m，基线 apex 2.009 m）**逐值不变**，
    历史证据基线不被改写。返回 `None` 表示沿用基线参数。
    """
    apex_base = (base_cap['v0'] * math.sin(math.radians(base_cap['angle_deg']))) ** 2 / (
        2.0 * base_cap['g'])
    if target_cruise_m <= apex_base:
        return None
    angle_deg = 85.0
    margin_m = 0.65
    v0 = math.sqrt(2.0 * base_cap['g'] * (target_cruise_m + margin_m)) / math.sin(
        math.radians(angle_deg))
    vy = v0 * math.sin(math.radians(angle_deg))
    return {
        'net_v0_mps': round(v0, 2),
        'net_angle_deg': angle_deg,
        'net_flight_timeout_s': round(2.0 * vy / base_cap['g'] + 0.3, 2),
        # 派生值只作证据：解析顶点与落地时刻，供断言/审查复算。
        '_apex_m': round(vy * vy / (2.0 * base_cap['g']), 4),
        '_t_land_s': round(2.0 * vy / base_cap['g'], 4),
        '_rule': 'apex = target_cruise + 0.65 m; θ=85°; timeout = t_land + 0.3 s',
    }


def apply_flight_altitude_params(merged, info):
    """ADR-0007：把地图高度注入**任务侧**参数。原地修改并返回规范化块。

    注入三处（其余高度键在 `apply_flight_altitude_air`）：
      1. `intruder_driver.cruise_alt_m`（+ 同值弃用别名 `alt_m`，否则别名冲突会让节点拒绝启动）；
      2. `capture_adjudicator` 的网弹道参数 —— **仅当基线弹道打不到该高度**时派生
         （`net_params_for_altitude`），否则逐值不变；
      3. `task_manager.air_hover_climb_m` —— 起飞完成判据必须跟着抬，否则「爬升量 ≥ 阈值」
         永远不成立，整链卡在 `air_hover_timeout`。
    """
    geometry = (info or {}).get('geometry')
    fa = flight_altitude_block(geometry)
    idr = merged.setdefault('intruder_driver', {})
    idr['cruise_alt_m'] = fa['target_cruise_m']
    if 'alt_m' in idr:
        idr['alt_m'] = fa['target_cruise_m']
    # 起飞完成判据：与 `takeoff_altitude_m` 同步（基线 2.5 → 2.3，差 0.2 = hover_tolerance）。
    merged.setdefault('task_manager', {})['air_hover_climb_m'] = round(fa['own_takeoff_m'] - 0.2, 3)
    cap = merged.setdefault('capture_adjudicator', {})
    base_cap = {
        'v0': float(cap.get('net_v0_mps', 6.5)),
        'angle_deg': float(cap.get('net_angle_deg', 75.0)),
        'g': float(cap.get('net_g', 9.81)),
    }
    derived_net = net_params_for_altitude(fa['target_cruise_m'], base_cap)
    if derived_net is not None:
        cap['net_v0_mps'] = derived_net['net_v0_mps']
        cap['net_angle_deg'] = derived_net['net_angle_deg']
        cap['net_flight_timeout_s'] = derived_net['net_flight_timeout_s']
    # 干扰包络上限**只升不降**：抬目标后 2.0 m 的旧上限会让 jam 场景恒判包络外。
    jam_max = float(cap.get('jam_envelope_max_alt_m', 2.0))
    if fa['target_cruise_m'] > jam_max:
        cap['jam_envelope_max_alt_m'] = round(fa['target_cruise_m'] + 0.5, 3)
    fa['_net_derived'] = derived_net
    # 来源登记走 `info`（launch 自有 dict），**不**注入节点参数——否则多一个未声明参数会拒绝启动。
    # `cruise_altitude_block` 据此把 source 报成 `map`（ADR-0007 改变了 H0 的"必须来自场景"口径）。
    if isinstance(info, dict):
        info['flight_altitude'] = fa
    return fa


def apply_flight_altitude_air(air_merged, geometry):
    """ADR-0007：把地图高度注入**空中侧**参数（与 `apply_air_geometry` 同款同位置）。"""
    fa = flight_altitude_block(geometry)
    air_merged.setdefault('standoff_follower', {})['height'] = fa['own_track_m']
    air_merged.setdefault('takeoff_controller', {})['takeoff_altitude_m'] = fa['own_takeoff_m']
    return air_merged


def assertions(scene, merged, info, air_merged=None, sim_share=None, layout=None,
               effective_spawn=None, effective_own=None):
    """R-026 + S-06 + F1 断言：实际生效参数 == 声明轴、**派生几何 == 真源**、
    **生效出生位 == 喂给世界的那一组**；任一失败 → 拒绝运行。

    F1（2026-10-31）：`effective_spawn` 为 `apply_spawn_layout()` 的返回值（该 run 实际生效的
    车 / 目标位，也是 `w6.launch.py` 喂给 `world_bringup` 的值）。断言
    「`scenario_reset` 参数 == `effective_spawn`」= 「复位位置 == 世界 spawn」在**启动前**可判定。

    `effective_own`（`parse_own_pose()` 结果）：己方机位姿可被 launch 显式覆盖，故
    ① `scenario_reset.own_uav_x/y` 必须等于**实际生效** own（而非 layout 缺省）；
    ② 设计距离必须按实际生效 own 算——否则"覆盖过的 run"会被 layout 的距离误判为通过
       （round-1 审查第 5 条）。
    """
    axes = info['axes']
    entries = info['entries']
    geometry = info['geometry']
    gids = geometry_ids(geometry)
    gxs = geometry_xs(geometry)
    gys = geometry_ys(geometry)
    bounds = work_area_bounds(geometry)
    sr = merged.get('scenario_reset', {})
    obs_ids = info['derived_obstacles_ids']
    res = {
        'target_motion_effective_equals_declared':
            merged.get('intruder_driver', {}).get('motion') == axes.get('target_motion'),
        'obstacle_world_effective_matches':
            info['world_obstacles'] == entries['obstacle']['world_obstacles'],
        'obstacles_file_effective_matches':
            info['obstacles_file_name'] == entries['obstacle']['obstacles_file'],
        'perception_sensors_file_effective_matches':
            info['sensors_file_name'] == entries['perception']['sensors_file'],
        # S-06：派生几何 == 真源（scenario_reset 障碍清单 / 作业区边界）。
        'scenario_reset_obstacles_match_geometry':
            list(sr.get('obstacle_names', [])) == gids
            and [float(v) for v in sr.get('obstacle_x', [])] == gxs
            and [float(v) for v in sr.get('obstacle_y', [])] == gys,
        'scenario_reset_bounds_match_work_area':
            all(k in sr for k in bounds)
            and all(float(sr[k]) == v for k, v in bounds.items()),
        # S-06：感知障碍先验按轴派生（static=真源；none=空），无第二份几何。
        'derived_obstacles_match_axis':
            (obs_ids == gids) if info['world_obstacles'] == 'static' else (obs_ids == []),
    }
    if effective_spawn is not None:
        car, tgt = effective_spawn['car'], effective_spawn['target']
        # 「复位位置 == 世界 spawn」：世界 spawn 用的就是这组 eff_*，故这里是同一判据的两侧。
        res['scenario_reset_spawn_equals_world_spawn'] = (
            abs(float(sr.get('car_x', 1e9)) - car['x']) < 1e-9
            and abs(float(sr.get('car_y', 1e9)) - car['y']) < 1e-9
            and abs(float(sr.get('car_z', 1e9)) - car['reset_z']) < 1e-9
            and abs(float(sr.get('target_x', 1e9)) - tgt['x']) < 1e-9
            and abs(float(sr.get('target_y', 1e9)) - tgt['y']) < 1e-9
            and abs(float(sr.get('target_z', 1e9)) - tgt['z']) < 1e-9)
    if layout is not None:
        # C7（ADR-0012）不变量：车↔目标出生距离不得低于标定下限（本任务只许拉大，不许削弱）。
        car = effective_spawn['car'] if effective_spawn is not None else layout['car']
        tgt = effective_spawn['target'] if effective_spawn is not None else layout['target']
        # own 用**实际生效**值：显式覆盖时不得拿 layout 的 own 算距离（那会造出自洽假象）。
        own = effective_own if effective_own is not None else layout['own_uav']
        dists = spawn_layout_distances({'car': car, 'target': tgt, 'own_uav': own})
        clearance_min = float(sr.get('spawn_clearance_min_m', 6.0))
        res['spawn_car_target_meets_c7'] = dists['car_target_m'] >= clearance_min
        if effective_own is not None:
            # 己方机出生净空校验坐标 == 实际生效 own（覆盖后仍须一致）。
            # 仅当**本 run 声明己方机在场**时判：`backend:=lightweight` 不起空中链路，
            # `own_uav_present=False`、`own_uav_x/y` 保持 base 的 0.0 占位（不是"出生位"），
            # 拿它去比布局真源会误判——那是"该字段不适用"，不是"配置不一致"。
            if bool(sr.get('own_uav_present', False)):
                res['own_uav_reference_equals_effective_own'] = (
                    abs(float(sr.get('own_uav_x', 1e9)) - own['x']) < 1e-9
                    and abs(float(sr.get('own_uav_y', 1e9)) - own['y']) < 1e-9)
        # F1 设计目标（派工单）：车/目标 ≥30 m、己方机/目标 ≥25 m、己方车机 3–8 m。
        # 仅对**默认出生布局**（source=layout）判；场景自定义出生位（s10/s11…）属场景语义，
        # 不按本任务设计目标约束（否则等于改那些场景的验收口径）。
        # 己方机被显式覆盖时**同样判**——设计目标是对"本 run 实际几何"的约束，不因覆盖而豁免。
        if effective_spawn is None or effective_spawn.get('source') == 'layout':
            res['spawn_design_goals_met'] = (
                dists['car_target_m'] >= 30.0
                and dists['own_uav_target_m'] >= 25.0
                and 3.0 <= dists['car_own_uav_m'] <= 8.0)
        # F1 round-2（审查第 6 条）：**派生**的目标位必须落在 `d_track` 可达范围内。
        # 只判 `goal_source == 'derived'`——场景显式给目标位的（s10/s11）其"不可达"是设计意图，
        # 不能拿本规则误判它们为配置错误。这一条把"改了 target、忘了 goal"挡在启动前。
        if (effective_spawn or {}).get('goal_source') == 'derived':
            gx = float((effective_spawn or {}).get('goal_x', 1e9))
            gy = float((effective_spawn or {}).get('goal_y', 1e9))
            d_track = float((merged.get('task_manager') or {}).get('d_track_m', 3.0))
            res['derived_goal_within_track_range'] = (
                math.hypot(gx - tgt['x'], gy - tgt['y']) <= d_track)
    # ADR-0014 不变量：**已授权射击**的场景必须关闭「跟踪里程碑即终态」——
    #   否则 `capture_adjudicator` 的交火窗口（`task_state == GROUND_APPROACH`）会在
    #   `TRACKING_SUCCESS` 锁存时被提前关闭，捕获（`INTERCEPT_CONFIRMED/CAPTURE_NET`）**永不发生**
    #   （实测 s08 协同臂 20/20 落 TRACKING_SUCCESS）。此断言把该配置矛盾挡在启动前。
    authorized = bool((merged.get('capture_adjudicator') or {}).get('interception_authorized', False))
    milestone_terminal = bool(
        (merged.get('task_manager') or {}).get('tracking_milestone_is_terminal', True))
    res['capture_authorized_requires_nonterminal_milestone'] = (not authorized) or (not milestone_terminal)
    # H0（2026-11-02）：巡航高度必须**单一来源且合法**——两个同值参数各自承担语义正是 H0 要消除的歧义。
    # 与 `intruder_driver._resolve_cruise_alt()` 同判据，此处**启动前**就挡住，避免跑到半程才崩。
    _ca = cruise_altitude_block(merged, info, effective_spawn)
    res['cruise_altitude_single_valid_source'] = bool(
        _ca['valid'] and not _ca['alias_conflicts'] and _ca['source'] != 'missing')
    if air_merged is not None:
        safety = air_merged.get('trajectory_tracker', {}).get('safety', {})
        res['air_obstacles_match_geometry'] = (
            list(safety.get('obstacle_names', [])) == gids
            and [float(v) for v in safety.get('obstacle_x', [])] == gxs
            and [float(v) for v in safety.get('obstacle_y', [])] == gys)
        # P1-1：安全半径**按障碍派生**（不再来自 air.yaml 的定长列表）。
        res['air_safety_radii_match_geometry'] = (
            [float(v) for v in safety.get('obstacle_safety_radius', [])]
            == geometry_safety_radii(geometry, sim_share))
        # ADR-0010「垂直门控」：顶高与净空也必须**逐障碍 / 逐地图**派生，长度与 ids 等长。
        #   漏注入时安全层的缺省是「无顶高 → 门控不生效」（保守但仍正确）；本断言把
        #   「明明有真源却没接上」挡在启动前，而不是让它静默退化成全高圆柱。
        z_tops = geometry_z_tops(geometry, sim_share)
        res['air_z_tops_match_geometry'] = (
            len(safety.get('obstacle_z_top', [])) == len(gids)
            and all(abs(float(v) - z) < 1e-9
                    for v, z in zip(safety.get('obstacle_z_top', []), z_tops)))
        res['air_vertical_clearance_matches_source'] = (
            abs(float(safety.get('vertical_clearance_m', -1e9))
                - flight_altitude_block(geometry)['own_clearance_min_m']) < 1e-9)
    # ADR-0007：高度派生四条断言——**无论 backend** 都要跑（lightweight 不起空中链路时，
    # 空中侧两键改用地图声明值 + air.yaml 基线做判据，见 `_flight_altitude_assertions`）。
    # 放在 `if air_merged is not None` **之外**是刻意的：地图高度配置是否自洽与后端无关。
    res.update(_flight_altitude_assertions(merged, info, air_merged, geometry))
    bad = [k for k, v in res.items() if not v]
    if bad:
        raise RuntimeError(
            '场景 %s 实际生效参数 != 声明轴 或 派生几何 != 真源（断言失败：%s）→ 拒绝运行' % (
                scene, bad))
    return res


def _flight_altitude_assertions(merged, info, air_merged, geometry):
    """ADR-0007：高度派生四条断言（误配即拒绝运行）。

    四条对应规范 [§4.2](../../docs/conventions/飞行高度分层与按地图定高.md#where) 第 4 点：
      1. `flight_altitude_derived_matches_source` —— 注入值 == 地图文件值（防"有人又改了 air.yaml"）
      2. `own_height_covers_h_max_env`            —— `h_o ≥ H_max_env + c_clear`（防"飞得比楼低"）
      3. `dz_within_perception_range`             —— `|h_o − h_t| ≤ √(R²−S²)`（防"抬完看不见目标"）
      4. `target_within_capture_envelope`         —— capture/jam 场景 `h_t ≤ 包络上限`（防"抬完打不着"）
    """
    fa = flight_altitude_block(geometry)
    res = {}
    # `air_merged is None`（lightweight 后端：不起空中链路）时，空中侧两键**不注入**。
    # 此时 ①②③ 改用**地图声明值**做判据——这正是"这张图的高度配置本身是否自洽"，
    # 仍然能在启动前挡住"地图写了个比楼低的高度"；断言 ① 则如实降级为"只校验任务侧"。
    has_air = air_merged is not None
    sf = (air_merged or {}).get('standoff_follower') or {}
    tk = (air_merged or {}).get('takeoff_controller') or {}
    # ① 注入值 == 地图文件值（两侧同源于 `geometry`，此处判"是否真的注入了"）。
    task_side_ok = abs(float((merged.get('intruder_driver') or {}).get('cruise_alt_m', -1e9))
                       - fa['target_cruise_m']) < 1e-9
    if has_air:
        res['flight_altitude_derived_matches_source'] = (
            task_side_ok
            and abs(float(sf.get('height', -1e9)) - fa['own_track_m']) < 1e-9
            and abs(float(tk.get('takeoff_altitude_m', -1e9)) - fa['own_takeoff_m']) < 1e-9)
    else:
        # 如实登记"空中侧不适用"，而不是省略字段（省略会让审查分不清"没用"与"忘了记"）。
        res['flight_altitude_derived_matches_source'] = task_side_ok
    # ② 垂直净空：己方机跟踪高度必须高于**作业包络内**最高障碍 + c_clear。
    h_max_env = float(fa['derived']['h_max_env_m'])
    res['own_height_covers_h_max_env'] = (
        fa['own_track_m'] >= h_max_env + fa['own_clearance_min_m'] - 1e-9)
    # ③ 感知量程（K1，三维球）：`|dz| ≤ √(R² − S²)`，R = 感知量程，S = 停止趋近点。
    #    停止点 = safe_max − hysteresis；lightweight 下从 air.yaml 基线取（节点不启动，但仍需自洽）。
    sensors = _load_sensors_range(info)
    safe_max = float(sf.get('safe_max', 11.2))
    hyst = float(sf.get('hysteresis', 1.0))
    if not has_air:
        base_air = _load_air_baseline(info)
        sf_base = (base_air or {}).get('standoff_follower') or {}
        safe_max = float(sf_base.get('safe_max', safe_max))
        hyst = float(sf_base.get('hysteresis', hyst))
    stop_point = safe_max - hyst
    dz = abs(fa['own_track_m'] - fa['target_cruise_m'])
    if sensors is not None and sensors > stop_point:
        res['dz_within_perception_range'] = (
            dz <= math.sqrt(sensors * sensors - stop_point * stop_point) + 1e-9)
    # ④ 捕获/干扰包络（K4）：**只对已授权射击的场景**判（tracking 类不判，避免误伤）。
    cap = merged.get('capture_adjudicator') or {}
    authorized = bool(cap.get('interception_authorized', False))
    if authorized:
        v0 = float(cap.get('net_v0_mps', 6.5))
        ang = float(cap.get('net_angle_deg', 75.0))
        g = float(cap.get('net_g', 9.81))
        launcher = float(cap.get('launcher_height_m', 0.0))
        apex = (v0 * math.sin(math.radians(ang))) ** 2 / (2.0 * g)
        # h = 目标高度 − 车体 z − 发射器高度；车 z 取复位口径（地面）。
        car_z = float((merged.get('scenario_reset') or {}).get('car_z', 0.0))
        h_target = fa['target_cruise_m'] - car_z - launcher
        res['target_within_capture_envelope'] = (h_target <= apex + 1e-9)
    return res


def _load_air_baseline(info):
    """读 `air.yaml` 基线（lightweight 后端不起空中链路时，断言仍需要 safe_max / hysteresis）。

    从 `info` 的 `air_file`（若 launch 提供）或源码树相对路径读；读不到返回 `None`
    → 对应判据退化为 `air.yaml` 的内置缺省，不伪造通过。
    """
    path = (info or {}).get('air_file') or os.path.join(_SRC_AIR_CONFIG, 'air.yaml')
    if not os.path.exists(str(path)):
        return None
    try:
        return yaml.safe_load(open(str(path)))
    except Exception:   # noqa: BLE001
        return None


def _load_sensors_range(info):
    """感知量程 `range_max_m`（三维球半径）——从传感器配置读，**不复制参数**。

    读不到（文件缺失 / 无通道）时返回 `None`，对应断言**不参与判定**
    （如实标注"该 run 无法核验"，而不是伪造一个通过）。
    """
    path = (info or {}).get('sensors_file_path') or (info or {}).get('sensors_file')
    if not path or not os.path.exists(str(path)):
        return None
    try:
        doc = yaml.safe_load(open(str(path)))
        chans = (doc or {}).get('sensors') or []
        return min(float(c['range_max_m']) for c in chans if 'range_max_m' in c)
    except Exception:   # noqa: BLE001 —— 解析失败不阻断启动，断言自动跳过（如实降级）
        return None


def vision_plane_block(plane=None, perception_path='truth', detector_backend=None):
    """视觉目标高度平面登记块（**2026-11-04 起恒为"未启用"**）。

    历史：`perception_path=vision` 时本块记录 `datum` / `world_enu_plane_z` / `source`，
    供审查复核视觉投影用的世界 ENU 平面。视觉路径已整体退役，因此本函数**保留字段形状、
    值恒为 applied=false**：

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
    #   视觉定位路径已于 2026-11-04 退役，manifest 对应字段恒写固定值（见 vision_plane_block）。
    #   保留形参是为了不改既有调用点的签名（w6.launch / w6_geometry_check 等）。
    _ = (perception_path, vision_plane, detector_backend)
    """产出 manifest dict（身份与入口名一致 + 完整展开节点 + 生效参数）。

    `launch` == `LAUNCH`（入口名）；`backend` = 实际 backend；`nodes` 由 backend 能力表派生。
    F1（2026-10-31）：传 `layout` 时追加 `spawn_layout` 块——出生布局真源路径 / sha256 /
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
    sensors_file_name = info['sensors_file_name']
    obstacles_file_name = info['obstacles_file_name']
    sensors_file = info['sensors_file']
    obstacles_file = info['obstacles_file']
    world_file = info['world_file']
    target_source = BACKENDS[backend]['target_source']
    px4_seed_protocol = 'agc-px4-sim-seed-v1'
    px4_seeds = {
        'own': derive_px4_sim_seed(seed, 0),
        'intruder': derive_px4_sim_seed(seed, 1),
        'warmup': derive_px4_sim_seed(seed, 3),
    }

    # 实际障碍集：从**真源派生** obstacles_file 读取 id（none → []；static → 真源全量）
    _obs_doc = yaml.safe_load(open(obstacles_file)) or {}
    obstacle_ids = [o.get('id') for o in (_obs_doc.get('obstacles') or [])]

    # S-06：几何版本身份——真源路径 + 内容 sha256 + work_area + 障碍（id/pose/size）。
    # P1-1：新增 `map` / `shape` / `safety_radius`——三张地图的几何身份可在 manifest 直接区分
    #   （D6 判据：「两次 run 的 geometry.sha256 不同」）；`shape` 为源形状，`size` 为**源尺寸**
    #   （cylinder 为 [r, r, h]），感知侧的外接矩形降级只在派生 obstacles 文件里出现。
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

    # R-026 运行时证据：声明轴 + 承载者（状态由能力表派生）+ 实际生效参数/文件
    carriers_ledger = {}
    for ax, val in axes.items():
        st, why = coverage_status(entries[ax], backend)
        eff = {}
        if ax == 'obstacle':
            eff = {'world_obstacles': world_obstacles, 'obstacles_file': obstacles_file_name,
                   'obstacle_ids': obstacle_ids, 'world_map': info.get('world_map', DEFAULT_WORLD_MAP)}
        elif ax == 'perception':
            eff = {'sensors_file': sensors_file_name, 'target_source': target_source}
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
            # H0 round-5：空中机**观测偏航实际生效值 + 来源**（场景默认 / CLI 覆盖 / air.yaml 缺省）。
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
            'sensors_file': sensors_file, 'obstacles_file': obstacles_file,
            'world_obstacles': world_obstacles, 'world_file': world_file,
            # P1-1：地图（几何真源选择）与实际世界生成路径——`static` 时世界是
            #   `/tmp/agc_world_static_obstacles[_<map>].sdf`，与真源一一对应。
            'world_map': info.get('world_map', DEFAULT_WORLD_MAP),
            'world_geometry_file': info['geometry_source'],
        },
        'geometry': geometry_block,
        'spawn_layout': spawn_layout_block(layout, layout_sha256, own_pose, effective_spawn,
                                           effective_own),
        'assertions': assertions_result,
    }


def observe_yaw_block(info=None, air_merged=None, cli_value=''):
    """H0 round-5：`trajectory_tracker.observe_yaw_mode` 的**实际生效值 + 来源**（manifest 可追溯）。

    三级优先级（与 `w6.launch.py` 的合并顺序一致，此处只做记录、不改合并）：
      CLI `observe_yaw_mode:=<mode>`（非空） > 场景 `trajectory_tracker.observe_yaw_mode`
      > `air.yaml` 缺省。

    为什么记录来源：round-4 的证据表明 s04 的成败取决于这一项（`behind` 门）。
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


def cruise_altitude_block(merged, info=None, effective_spawn=None):
    """H0（2026-11-02）：巡航高度**实际生效值 + 来源 + 参考基准**（manifest 可还原）。

    为什么单独成块：H0 的核心歧义是"同一个数字既是出生高度、又是爬升量、又是巡航高度"。
    把"生效值 / 来源 / 基准 / 是否叠加"四件事写进 manifest，使每个 run 的高度语义**可逐项复核**，
    而不是靠读两份 yaml 自己推。

    解析规则与 `intruder_driver._resolve_cruise_alt()` **同口径**（此处只做记录，不重复实现校验；
    真正的拒绝启动由节点在运行期执行，故本函数对非法值如实标注 `invalid` 而不抛异常）。
    """
    idr = merged.get('intruder_driver') or {}
    cruise = idr.get('cruise_alt_m')
    alias = idr.get('alt_m')
    scene_over = (((info or {}).get('sc') or {}).get('params') or {}).get('intruder_driver') or {}
    # ADR-0007（2026-11-02）：高度归**地图**。`apply_flight_altitude_params` 已在 `info` 里
    # 登记本图派生块，故来源优先级变为：**map > scene > base**。
    # 这是对 H0「vision 平面必须 source=scene」口径的**显式修订**（见 ADR-0007）：
    # 地图是几何事实、场景是任务意图；高度属前者。场景仍可覆盖（向后兼容），但默认走地图。
    map_fa = (info or {}).get('flight_altitude')
    if map_fa is not None and cruise is not None \
            and abs(float(cruise) - float(map_fa['target_cruise_m'])) < 1e-9:
        source = 'map'
    elif 'cruise_alt_m' in scene_over:
        source = 'scene'
    elif cruise is not None:
        source = 'base'
    elif alias is not None:
        source = 'base(alt_m 弃用别名)'
    else:
        source = 'missing'
    effective = cruise if cruise is not None else alias
    valid = isinstance(effective, (int, float)) and effective > 0
    return {
        'effective_m': effective,
        'source': source,
        # 弃用别名同时记录：两者不相等时节点会拒绝启动，manifest 让"为什么会拒"可见。
        'deprecated_alias_alt_m': alias,
        'alias_conflicts': (cruise is not None and alias is not None
                            and abs(float(cruise) - float(alias)) > 1e-9),
        'valid': bool(valid),
        # 参考基准：本值相对 **episode 原点**（epoch 后首帧 odom），**不是**世界 ENU 高度。
        'datum': 'episode_origin_ned',
        'world_enu_absolute': False,
        # 明确登记"不与世界 spawn 值叠加"——这是 H0 判定过的结论，不是默认假设。
        'stacks_on_spawn_z': False,
        'spawn_place_z': (((effective_spawn or {}).get('target')) or {}).get('z'),
        # ADR-0007：本 run 的地图高度派生块（None = 未经地图派生，如历史单测）。
        'map_flight_altitude': ({k: v for k, v in map_fa.items() if not k.startswith('_')}
                                if map_fa is not None else None),
        'note': ('巡航高度 = episode 原点世界高度 + effective_m；原点世界高度由 EKF 初始化决定、'
                 '跨 run 不可复现，故本值不是绝对世界高度。世界放置值另见 spawn_layout.target.z'
                 '（PX4 attach 前瞬态，不与本值叠加）。'),
    }


def spawn_layout_block(layout, layout_sha256=None, own_pose=None, effective_spawn=None,
                       effective_own=None):
    """出生布局证据块（F1）：真源身份 + **实际生效**位姿 + 三组距离 + 己方机起飞参考。

    `layout=None`（未注入出生布局的调用方，如历史单测）→ 返回 `None`，不改既有行为。
    `spawn` 是**消费者实际拿到的值**：车给出 `world_z`（世界 spawn，轮触地）与 `reset_z`
    （复位口径）；`spawn_source` 记该 run 的出生位来自布局真源（`layout`）还是场景覆盖（`scene`）。

    `effective_own`（`parse_own_pose()` 的结果）**优先**于 layout 的 own_uav：
    己方机位姿可被 launch 显式覆盖，若距离仍按 layout 算，manifest 就会自洽地"证明"一个
    并没有发生过的布局（round-1 审查第 5 条）。此处把关：`distances` 与 `own_uav` 用同一个值，
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
            # layout 真源里的 own 位（便于审查一眼看出"被覆盖了"）——不参与距离。
            'layout_own_uav': {'x': own['x'], 'y': own['y'], 'z': own['z'], 'yaw': own['yaw']},
        },
        # 距离一律按**实际生效**位算（own 用 own_eff）。
        'distances': spawn_layout_distances(
            {'car': car, 'target': tgt, 'own_uav': own_eff}),
        # F1 round-2：固定任务目标与其来源（`derived`=由目标出生位+偏移派生）。
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
