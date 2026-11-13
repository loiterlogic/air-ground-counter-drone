#!/usr/bin/env python3
"""scene_spawn —— 出生布局：配置文件读取、校验与四处派生（ADR-0007）。

出生布局坐标的**配置文件**是 `agc_task/config/spawn_layout.yaml`。为什么需要它：
世界 spawn（world_bringup 的 car_x/target_x…）、复位位置（scenario_reset 的同一组参数）、
己方机起飞参考（PX4_GZ_MODEL_POSE 与空中节点 origin_pose）**原本各自写默认值**
（`car.yaml` / `target.yaml` / `base.yaml` / air.yaml / C++ declare_parameter），四份值可漂移。
现统一由本模块读一处、派生四处；未知/缺失键一律**拒绝运行**（不静默回退到某份旧默认值）。
"""

import hashlib
import math
import os

import yaml

SPAWN_LAYOUT_FILE = 'spawn_layout.yaml'


def _validate_per_map(per_map, path):
    """**无条件**校验整张 `per_map` 表的结构（与"本次选了哪张图"无关）。

 为什么无条件：拼错实体段（`cars`）只有在该图**被选中**时才暴露，等于让一个拼写错误
 潜伏到"某天刚好跑那张图"。结构错误是**文件级**错误，应当在任何一次加载时都拒绝。
    """
    if per_map is None:
        return
    if not isinstance(per_map, dict):
        raise RuntimeError(
            '出生布局文件 %s 的 `spawn_layout.per_map` 非映射 → 拒绝运行' % path)
    for name, over in per_map.items():
        if not isinstance(over, dict):
            raise RuntimeError(
                '出生布局文件 %s 的 `spawn_layout.per_map.%s` 非映射 → 拒绝运行'
                % (path, name))
        for entity, sec in over.items():
            if entity not in ('car', 'target', 'own_uav'):
                raise RuntimeError(
                    '出生布局文件 %s 的 `spawn_layout.per_map.%s` 含未知实体段 %r'
                    '（只允许 car / target / own_uav）→ 拒绝运行' % (path, name, entity))
            if not isinstance(sec, dict):
                raise RuntimeError(
                    '出生布局文件 %s 的 `spawn_layout.per_map.%s.%s` 非映射 → 拒绝运行'
                    % (path, name, entity))


def _merge_map_override(layout, world_map, path):
    """把 `spawn_layout.per_map.<world_map>` 的键**深合并一层**到顶层实体段上。

 ADR-0036：出生位是**地图属性**（与 `flight_altitude` 同款论证）。顶层段提供**完整缺省**，
 `per_map.<map>` 只写要覆盖的键 —— 这样 `minimal` / `yard` / `open_field` 三图逐值不变，
 新增地图只需加一段，不必复制整份布局。

 纪律：
 * `world_map` 为 `None` / 空 → 不合并（顶层缺省，即历史行为逐值不变）；
 * `world_map` **未在 `per_map` 登记** → 不合并（回落到顶层缺省）；**这是刻意**：
   登记表只描述"与缺省不同"的图，未登记 = 用缺省，而不是拒绝运行——否则每加一张图
   都要先改本文件才能跑。真正需要拒绝的是"地图名本身非法"，那由 `world_map.resolve` 管。
 * `per_map` 的**结构**由 `_validate_per_map` **无条件**校验（拼错实体名一律拒绝运行）。
    """
    per_map = layout.get('per_map')
    _validate_per_map(per_map, path)
    if per_map is None:
        return layout
    name = (world_map or '').strip()
    if not name:
        return layout
    over = per_map.get(name)
    if over is None:
        return layout
    merged = {k: (dict(v) if isinstance(v, dict) else v) for k, v in layout.items()}
    for entity, sec in over.items():
        merged.setdefault(entity, {}).update(sec)
    return merged


def load_spawn_layout(task_share, path=None, world_map=None):
    """读出生布局文件；缺键 / 非数值 / **非有限值（NaN·±Inf）** → `RuntimeError`（拒绝运行）。

 `path` 仅供测试注入（缺省即配置文件文件），避免测试为造非法值去改配置文件。
 `world_map` 非空时先按 `spawn_layout.per_map.<world_map>` 覆盖（ADR-0036，见
 `_merge_map_override`）；缺省 `None` = 只用顶层布局（历史行为逐值不变）。

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
        raise RuntimeError('出生布局文件 %s 缺少顶层 `spawn_layout` → 拒绝运行' % path)
    layout = _merge_map_override(layout, world_map, path)
    out = {}
    for entity, keys in (
            ('car', ('x', 'y', 'yaw', 'world_z', 'reset_z')),
            ('target', ('x', 'y', 'z', 'yaw')),
            ('own_uav', ('x', 'y', 'z', 'yaw'))):
        sec = layout.get(entity)
        if not isinstance(sec, dict):
            raise RuntimeError(
                '出生布局文件 %s 缺少 `spawn_layout.%s` → 拒绝运行' % (path, entity))
        vals = {}
        for k in keys:
            if k not in sec:
                raise RuntimeError(
                    '出生布局文件 %s 缺少 `spawn_layout.%s.%s` → 拒绝运行' % (path, entity, k))
            raw = sec[k]
            try:
                val = float(raw)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    '出生布局文件 %s 的 `spawn_layout.%s.%s`=%r 非数值 → 拒绝运行'
                    % (path, entity, k, raw)) from exc
            if not math.isfinite(val):
                # NaN / ±Inf：比较式对 NaN 恒假 → 越界与净空拒绝分支失效（静默放行）。
                raise RuntimeError(
                    '出生布局文件 %s 的 `spawn_layout.%s.%s`=%r 非有限值（NaN/±Inf）→ 拒绝运行'
                    % (path, entity, k, raw))
            vals[k] = val
        out[entity] = vals
    # 固定任务目标的派生偏移（F1 ）：缺省 (−2.5, 0)。缺键时用缺省而不是拒绝——
    # 它是"派生规则参数"，不是出生位本身；但一旦出现就必须是有限数值。
    off = layout.get('goal_offset_m') or {}
    if not isinstance(off, dict):
        raise RuntimeError(
            '出生布局文件 %s 的 `spawn_layout.goal_offset_m` 非映射 → 拒绝运行' % path)
    goal_off = {}
    for k, default in (('dx', -2.5), ('dy', 0.0)):
        raw = off.get(k, default)
        try:
            val = float(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                '出生布局文件 %s 的 `goal_offset_m.%s`=%r 非数值 → 拒绝运行' % (path, k, raw)) from exc
        if not math.isfinite(val):
            raise RuntimeError(
                '出生布局文件 %s 的 `goal_offset_m.%s`=%r 非有限值 → 拒绝运行' % (path, k, raw))
        goal_off[k] = val
    out['goal_offset_m'] = goal_off
    out['source'] = path
    return out


def spawn_layout_sha256(task_share):
    """出生布局文件的 sha256（布局版本身份；写入 manifest，便于审查核对）。"""
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

 `source` ∈ `'override'`（launch 显式给出）| `'layout'`（取自出生布局配置文件）。
 非法值**拒绝运行**而不是 WARN 后按布局兜底：兜底会让"声明的位置"与"实际飞的位置"
 悄悄分叉，正是本轮要消灭的那类证据失真。
    """
    parts = [p.strip() for p in str(pose_string).split(',')]
    if len(parts) < 6:
        raise RuntimeError(
            '己方机位姿 %r 需要 6 个分量（x,y,z,roll,pitch,yaw）→ 拒绝运行' % (pose_string,))
    try:
        vals = [float(p) for p in parts[:6]]
    except ValueError as exc:
        raise RuntimeError('己方机位姿 %r 含非数值分量 → 拒绝运行' % (pose_string,)) from exc
    if not all(math.isfinite(v) for v in vals):
        raise RuntimeError('己方机位姿 %r 含非有限值（NaN/±Inf）→ 拒绝运行' % (pose_string,))
    is_layout = bool(layout) and pose_string.strip() == own_uav_pose_string(layout)
    return {'x': vals[0], 'y': vals[1], 'z': vals[2], 'yaw': vals[5],
            'source': 'layout' if is_layout else 'override'}


def spawn_layout_distances(layout):
    """三组设计距离（车↔目标 / 己方机↔目标 / 车↔己方机）。

 `layout` 可为**实际生效**的位姿字典（`{'car':…, 'target':…, 'own_uav':…}`）——默认场景下
 即 `{'car': effective.car, 'target': effective.target, 'own_uav': 实际生效 own}`。
 传入 layout 配置文件与传入生效值得到**不同**结果，这正是"距离必须跟实际生效位一致"的落点。
    """
    car, tgt, own = layout['car'], layout['target'], layout['own_uav']
    return {
        'car_target_m': math.hypot(car['x'] - tgt['x'], car['y'] - tgt['y']),
        'own_uav_target_m': math.hypot(own['x'] - tgt['x'], own['y'] - tgt['y']),
        'car_own_uav_m': math.hypot(car['x'] - own['x'], car['y'] - own['y']),
    }


def apply_spawn_layout(merged, layout, sc=None):
    """把出生布局注入合并参数，返回**实际生效**的出生位（世界 spawn 与复位同值）。

 优先级（三级，从高到低）：**场景层显式覆盖 > 出生布局配置文件 > base / 节点缺省**。

 * 为什么场景覆盖仍可生效：部分场景的"出生位"本身承载**场景语义**，不是"默认出生点"——
 例如 `s11` 的"车被立柱阻隔"、`s10` 的"目标置远 → 必然超时"。用布局配置文件盖掉它们等于
 改掉这些场景的验收口径（不在本单范围）。故布局配置文件只提供**缺省**，场景可覆盖。
 * 为什么这不破坏"三者一致"：世界 spawn 取的是**本函数的返回值**（`main.launch.py` 用它喂
 `world_bringup` 的 `car_x/target_x…`），而复位参数也是同一份 `merged`。二者同源，
 所以"世界 spawn == 复位位置"对**任何**场景都成立，而不只是默认场景。
 * `z` 分两种口径：世界 spawn 的车 z = **轮触地**（布局 `world_z`，模型几何属性，不随场景变），
 复位车 z = 布局 `reset_z`（`scenario_reset` 既有口径 0.010）。

 返回 `{'car': {x,y,yaw,world_z,reset_z}, 'target': {x,y,z,yaw}, 'source': 'scene'|'layout'}`；
 `source` 记明该 run 的出生位来自布局配置文件还是场景覆盖，写入 manifest 供审查区分。
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

    # ---- 固定任务目标：默认场景由「目标出生位 + goal_offset_m」派生（F1 ）----
    # 触发条件（三条同时成立才派生）：
    # ① 场景**未**显式给 `task_manager.goal_x/goal_y`（显式值属场景语义，如 s08/s11 的配套目标）；
    # ② `goal_follow_target` 为假（为真时任务目标由感知目标实时决定，固定点无意义）；
    # ③ 场景**未**显式给 `scenario_reset.target_*`——否则该场景的目标位是"置远/被阻隔"等
    # 语义设定，派生一个 2.5 m 邻域目标会把 s10 的"必然超时"改成"可达"（改验收口径）。
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
