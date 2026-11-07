#!/usr/bin/env python3
"""scene_geometry —— 几何源文件的加载与**派生量**（ADR-0007）。

本模块只做一件事：把"按地图分文件的几何配置"变成各域可直接用的派生量。
**几何算法本身不在本模块**——它唯一存在于 `agc_sim/launch/world_map.py`，
本模块只按 `sim_share` 解析并**委托**。两份实现漂移会让不同域读到不同几何，
正是 ADR-0007 要消灭的病灶。

为什么单独成模块：`composition.py` 原先 1445 行，把"读配置 / 派生几何 / 合参数 /
写 manifest / 拼 PX4 命令"混在一处，改任一处都要先读懂另外四件事。
"""

import hashlib
import importlib.util
import os

import yaml

# 静态障碍 + 作业区几何的**配置文件**（位于 agc_sim share 的 config/ 下）。
GEOMETRY_FILE = 'world_geometry.yaml'

# 配置文件按**地图**分文件。**单一清单**在 `agc_sim/launch/world_map.py`（随包安装到
# `share/agc_sim/launch`，与 `world_bringup.launch.py` 同目录）。本模块经 `sim_share` 解析后
# import 该模块，**不再自持第二份文件名表**。
DEFAULT_WORLD_MAP = 'minimal'

# 源码树定位（未 source 安装环境时的回退）：本文件位于 `src/agc_task/launch/`，
# 同级 `src/agc_sim/launch/world_map.py` 即源码副本（与安装副本同一符号链接目标）。
_SRC_SIM_LAUNCH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'agc_sim', 'launch')

_WORLD_MAP_CACHE = {}


def world_map_module(sim_share=None):
    """加载 `agc_sim` 的 `world_map` 清单模块（共享模块边界的**唯一实现**）。

 优先从**安装后的 share**（`<sim_share>/launch/world_map.py`）导入，与 `world_bringup`
 读到同一份清单；未提供 / 不存在时回退到源码树路径。按路径缓存，避免重复 exec。
    """
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
        '找不到地图清单 world_map.py（尝试：%s）→ 拒绝运行' % ', '.join(candidates))


def resolve_world_map(world_map, sim_share=None):
    """校验并规范化 `world_map`；未知值**拒绝运行**（不静默回退 minimal）。"""
    return world_map_module(sim_share).resolve(world_map)


def geometry_path(sim_share, world_map=DEFAULT_WORLD_MAP):
    """按地图解析几何源文件的绝对路径。`minimal` → `config/world_geometry.yaml`。"""
    return world_map_module(sim_share).geometry_path(sim_share, world_map)


def load_geometry(sim_share, world_map=DEFAULT_WORLD_MAP):
    """读**单一几何来源**（ADR-0007）；按 `world_map` 选文件。"""
    _, path = geometry_path(sim_share, world_map)
    with open(path) as f:
        return yaml.safe_load(f)


def geometry_sha256(sim_share, world_map=DEFAULT_WORLD_MAP):
    """几何源文件**字节**的 sha256（版本身份；写入 manifest；按地图区分）。"""
    _, path = geometry_path(sim_share, world_map)
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------- 派生量
# 下面这些函数**只委托**给 world_map 的单一实现（ADR-0007）；
# 它们存在是为了让调用方拿到 `sim_share` 已解析好的模块，而不是各自去猜路径。

def obstacle_shape(ob, sim_share=None):
    """实体形状（schema 缺省 = box；ADR-0007 向后兼容——老配置不写 shape 仍可运行）。"""
    return world_map_module(sim_share).obstacle_shape(ob)


def obstacle_safety_radius(ob, sim_share=None):
    """实体水平面**外接圆半径**（空中安全层为二维圆盘模型，须覆盖实体几何）。

 `safety_radius` 缺省 2.0 = 历史 pole 标定值；起由配置文件**逐障碍**给出，
 消除旧的「与障碍数对齐的定长列表」。
    """
    return world_map_module(sim_share).obstacle_safety_radius(ob)


def geometry_safety_radii(geometry, sim_share=None):
    """按障碍派生的安全半径列表（与 `geometry_ids` 同序；`apply_air_geometry` 使用）。"""
    return [obstacle_safety_radius(ob, sim_share)
            for ob in (geometry.get('obstacles') or [])]


def obstacle_z_top(ob, sim_share=None):
    """实体**顶面高度**（世界 ENU，m；复合体取全部 part 的最大值）。

    消费者 = 空中安全层**垂直门控**（ADR-0010 的 #vertical-gate）：本机高度高于
 `z_top + c_clear` 时，该障碍的水平圆盘对本机不生效。配置文件已含 `z` + `size[2]`，
 本函数只做派生，**不**新增 schema 键。
    """
    return world_map_module(sim_share).obstacle_z_top(ob)


def geometry_z_tops(geometry, sim_share=None):
    """按障碍派生的顶高列表（与 `geometry_ids` 同序；`apply_air_geometry` 使用）。"""
    return [obstacle_z_top(ob, sim_share)
            for ob in (geometry.get('obstacles') or [])]


def obstacle_bbox_size(ob, sim_share=None):
    """感知先验 / 地图栅格的障碍尺寸（**降级为水平轴对齐包络**）。

 `map_adapter` 的障碍模型是 OBB（只有 sx/sy/sz + yaw），无法表达圆柱 /
 球 / 多图元复合体；故一律降级为包络矩形（保守外扩，不缩小实体）。该降级为成文约定。
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
    """由几何源文件的 `work_area` 派生作业区边界（`map_*`，map 系）。"""
    wa = geometry['work_area']
    return {
        'map_x_min': float(wa['origin_x']),
        'map_x_max': float(wa['origin_x']) + float(wa['size_x']),
        'map_y_min': float(wa['origin_y']),
        'map_y_max': float(wa['origin_y']) + float(wa['size_y']),
    }
