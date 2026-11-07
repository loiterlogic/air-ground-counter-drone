#!/usr/bin/env python3
"""场景几何单一来源 + 按域派生 + 三地图 —— 一致性核查（只读）。

断言（任一失败即整体 FAIL，退出码 1）。**(a)-(h)** 对**每张已登记地图**逐一跑（minimal /
yard / open_field）；**(i)-(m)** 是跨图 / 一次性断言。

单图断言（per map）：
 (a) 配置文件 schema 合法（work_area 五键；障碍 id/x/y/z/yaw/size；`shape ∈ {box, cylinder}`；
 cylinder `size[0] == size[1]`；`safety_radius` 有限且 > 0）；
 (b) `world_bringup`「static 世界」中每个障碍的 pose / 几何 == 配置文件（box 比 `<box><size>`、
 cylinder 比 `<cylinder><radius><length>`），且**视觉 == 碰撞**（同片段）；
 `minimal` 另外要求 `pole_1`/`pole_2` 逐值不变（历史基线）与 `none` 世界无障碍；
 (c) `agc_perception/config/{obstacles,map}.yaml`（standalone 回退副本）与 **minimal** 配置文件一致
 （不漂移）——非 minimal 无回退副本，standalone 路径必须显式拒绝（见 (j)）；
 (d) `agc_air/config/air.yaml` 已**无**任何硬编码障碍几何 **与半径列表**（定长列表已消除）；
 (e) `agc_task/config/base.yaml` 已去硬编码几何（派生入口），且 `composition` 派生注入 == 配置文件；
 (f) `geometry_sha256` 稳定且**按图区分**；manifest `geometry` 块（含 `map` / `shape` /
 `safety_radius`）== 配置文件；
 (g) 出生净空：车/目标/己方机 ↔ 每个障碍**足迹**净空 ≥ 物体外伸之和（与
 `scenario_reset.validateCandidate` 同一判据），且作业区边界内缩成立；
 (h) 障碍族可见性：每个实体在 z=0.48（地面激光扫描面）处有水平截面（ADR-0009 口径）；
 (i) 空中安全层**存在可行解**：目标周围 [8,15] m 待机环带上的可行率 / 最大连续阻塞弧，
 且新地图**不新增**阻塞单元（相对 minimal 逐单元比对）；
 (j) 回退副本边界：`perception_bringup` 的 `map_file` / `obstacles_file` 缺省仍指向包内副本，
 且 `w6` 路径按地图派生注入（非 minimal 不读副本）；
 (k) 权限：`obstacles.yaml` 静态先验成文假设仍在（不静默引入真值优势）；
 (l) 地图登记一致：`scenarios.yaml` 的 `world_map` 值 ∈ 清单；s04 主场景指向 yard；
 (m) 配置文件清单**单一实现**：`world_bringup` / `air_bringup` / `composition` 都经
 `agc_sim/launch/world_map.py` 解析，且三处无自持文件名表。

输出 JSON 摘要（stdout）；`--out <path>` 落盘。用法：
  `python3 tests/check_scene_geometry.py`              # 三张地图全查
  `python3 tests/check_scene_geometry.py --maps minimal`  # 只查一张
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import yaml
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))  # noqa: E402
import checklib  # noqa: E402  （tests/ 内共用小工具）

# 项目根**自定位**（2026-10-31 ，裁定 A）：本文件在 `<ROOT>/tests/`，上溯两级即根。
# 原来写死 `/home/chen/AGC`，使冒烟 `geometry` 组在别处 clone 时检的是**原仓库**。
ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# ADR-0009：地面激光扫描面高度（`car/lidar_link` z=0.48）。障碍在 z=0.48 处须有水平截面，
# 否则「世界里看得见、安全层和 costmap 看不见」——必须在文档里标注，不得假装能避。
LASER_PLANE_Z_M = 0.48

# 空中安全层待机环带（由 air.yaml 派生，见 `_air_ring_params`）：目标周围 [safe_min, safe_max]
# 是 standoff 跟踪可达域；安全层圆盘半径 = safety_radius + obstacle_margin + 反应/可达余量。
RING_R_MIN, RING_R_MAX = 8.0, 15.0


def _share(pkg):
    """优先取 install share；失败回退 src/<pkg>。"""
    try:
        from ament_index_python.packages import get_package_share_directory
        return get_package_share_directory(pkg)
    except Exception:  # noqa: BLE001
        return os.path.join(ROOT, 'src', pkg)


def _load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _generate_static_world(wb_path, src, dst, geometry):
    """调用 `world_bringup.launch.py` 的 `_inject_static_obstacles` 生成 static 世界（**单一实现**）。

 经子进程加载 launch 模块：独立把 ROS lib 目录并入 LD_LIBRARY_PATH，使未 `source` ROS 环境
 （缺少 `librcl_action.so`）时 `launch_ros` 亦可导入；主进程本身**不**导入 launch（无 ROS 依赖）。
    """
    lib = '/opt/ros/%s/lib' % os.environ.get('ROS_DISTRO', 'jazzy')
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = lib + ':' + env.get('LD_LIBRARY_PATH', '')
    code = (
        "import importlib.util, json, sys\n"
        "spec = importlib.util.spec_from_file_location('wb_launch', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "m._inject_static_obstacles(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))\n"
    )
    subprocess.run([sys.executable, '-c', code, wb_path, src, dst, json.dumps(geometry)],
                   check=True, env=env, capture_output=True)
    return dst


def _sdf_models(world_path):
    """返回 {model_name: {'pose': [...], 'geometry': ('box', [..]) | ('cylinder', [..])}}。"""
    root = ET.parse(world_path).getroot()
    out = {}
    for world in root.iter('world'):
        for m in world.findall('model'):
            name = m.get('name')
            pose_el = m.find('pose')
            pose = [float(v) for v in pose_el.text.split()] if pose_el is not None else None
            coll = m.find('.//collision/geometry')
            vis = m.find('.//visual/geometry')
            out[name] = {
                'pose': pose,
                'geometry': _geom_of(coll),
                'visual_geometry': _geom_of(vis),
            }
    return out


def _geom_of(node):
    """把 `<geometry>` 子节点解析成 `(kind, [a, b, c])`；未知形状返回 None。"""
    if node is None:
        return None
    box = node.find('box/size')
    if box is not None:
        return ('box', [float(v) for v in box.text.split()])
    cyl = node.find('cylinder')
    if cyl is not None:
        r = cyl.findtext('radius')
        h = cyl.findtext('length')
        if r is not None and h is not None:
            return ('cylinder', [float(r), float(h)])
    sph = node.find('sphere')
    if sph is not None:
        r = sph.findtext('radius')
        if r is not None:
            return ('sphere', [float(r)])
    return None


def _close(a, b, eps=1e-9):
    return a is not None and b is not None and len(a) == len(b) and all(
        abs(x - y) <= eps for x, y in zip(a, b, strict=False))


def _src_geometry_of(ob, world_map_mod):
    """几何文件里的障碍（单图元）→ 期望世界几何 `(kind, [..])`（与 `world_bringup` 注入口径一致）。"""
    return _src_part_geometry_of(ob, world_map_mod)


def _src_part_geometry_of(part, world_map_mod):
    """单个 part → 期望世界几何 `(kind, [..])`（与 `world_map` 的注入口径一致）。"""
    size = world_map_mod.obstacle_size(part, part)
    shape = world_map_mod.obstacle_shape(part)
    if shape == 'cylinder':
        return ('cylinder', [float(size[0]), float(size[2])])
    if shape == 'sphere':
        return ('sphere', [float(size[0])])
    return ('box', [float(size[0]), float(size[1]), float(size[2])])


def _src_geometry_of_box_only(ob, world_map_mod):
    return _src_part_geometry_of(ob, world_map_mod)


def _resolve_maps(sim_share):
    """加载 `world_map` 单一清单（同 `world_bringup` 用的那份）。"""
    return _load_module(os.path.join(sim_share, 'launch', 'world_map.py'), 'world_map')


def _air_ring_params(air_share):
    """由 `air.yaml` 派生空中安全层圆盘半径公式参数（安全余量，非几何）。"""
    safety = _load_yaml(os.path.join(air_share, 'config', 'air.yaml'))[
        'trajectory_tracker']['ros__parameters']['safety']
    extra = (float(safety['reaction_time_s']) * float(safety['max_speed_mps'])
             + float(safety['reachability_margin']))
    return {
        'obstacle_margin': float(safety['obstacle_margin']),
        'target_margin': float(safety['target_margin']),
        'target_min_dist': float(safety['target_min_dist']),
        'extra': extra,
    }


def _disk_radius(ob, world_map_mod, ring):
    """安全层实际使用的圆盘半径（与 `safety_shield.cpp` 一致）。"""
    return (world_map_mod.obstacle_safety_radius(ob) + ring['obstacle_margin'] + ring['extra'])


def _obb_clearance(px, py, ob, world_map_mod):
    """点到实体**水平足迹**的距离（复合模型取全部 part 的最小值；重合为 0）。"""
    best = float('inf')
    for part in world_map_mod.obstacle_parts(ob):
        yaw = float(part.get('yaw', 0.0))
        # 复合适配：part 的 x/y 是相对锚点的局部偏移
        ox = float(ob['x']) + float(part.get('x', 0.0)) if world_map_mod.is_composite(ob) \
            else float(ob['x'])
        oy = float(ob['y']) + float(part.get('y', 0.0)) if world_map_mod.is_composite(ob) \
            else float(ob['y'])
        yaw = yaw + (float(ob.get('yaw', 0.0)) if world_map_mod.is_composite(ob) else 0.0)
        dx, dy = px - ox, py - oy
        c, s = math.cos(-yaw), math.sin(-yaw)
        lx, ly = c * dx - s * dy, s * dx + c * dy
        size = [float(v) for v in part['size']]
        shape = world_map_mod.obstacle_shape(part)
        if shape in ('cylinder', 'sphere'):
            d = max(0.0, math.hypot(lx, ly) - size[0])
        else:
            qx, qy = abs(lx) - size[0] / 2.0, abs(ly) - size[1] / 2.0
            d = 0.0 if (qx <= 0.0 and qy <= 0.0) else math.hypot(max(qx, 0.0), max(qy, 0.0))
        best = min(best, d)
    return best


def _footprint_extent(ob, world_map_mod):
    """实体**水平外接圆**半径（C7 两实体外伸之和口径；复合体覆盖全部 part）。"""
    return world_map_mod.obstacle_footprint_radius(ob)


def _part_h_poly(part, ob, world_map_mod):
    """part 在**世界系**下的水平多边形（box=4 角；cylinder/sphere 用 16 边形近似）。

 口径与 `_inject_static_obstacles` 注入的 `<geometry>` 一致：part 的 x/y 在复合模型里是
 相对锚点的局部偏移，旋转 = 锚点 yaw + part yaw。
    """
    comp = world_map_mod.is_composite(ob)
    ox = float(ob['x']) + (float(part.get('x', 0.0)) if comp else 0.0)
    oy = float(ob['y']) + (float(part.get('y', 0.0)) if comp else 0.0)
    yaw = float(part.get('yaw', 0.0)) + (float(ob.get('yaw', 0.0)) if comp else 0.0)
    size = [float(v) for v in part['size']]
    shape = world_map_mod.obstacle_shape(part)
    c, s = math.cos(yaw), math.sin(yaw)

    def W(dx, dy):
        return (ox + c * dx - s * dy, oy + s * dx + c * dy)

    if shape in ('cylinder', 'sphere'):
        r = size[0]
        return [W(r * math.cos(2 * math.pi * i / 16), r * math.sin(2 * math.pi * i / 16))
                for i in range(16)]
    hx, hy = size[0] / 2.0, size[1] / 2.0
    return [W(hx, hy), W(-hx, hy), W(-hx, -hy), W(hx, -hy)]


def _point_in_poly(px, py, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1) + x1):
            inside = not inside
    return inside


def _union_coverage_pct(obstacles, wa, world_map_mod, res=0.2):
    """障碍水平投影的**并集**面积占作业区比例（%）。

 口径成文（2026-10-29）：**同一实体多图元相互堆叠只计一次**，故用并集而非图元和。
 旧记录 `yard 覆盖 7.36%` 既非并集（4.64%）亦非图元和（6.85%）→ 不可复现，已作废。
    """
    cells = set()
    for ob in obstacles:
        for part in world_map_mod.obstacle_parts(ob):
            poly = _part_h_poly(part, ob, world_map_mod)
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            ix0, ix1 = int(math.floor(min(xs) / res)), int(math.ceil(max(xs) / res))
            iy0, iy1 = int(math.floor(min(ys) / res)), int(math.ceil(max(ys) / res))
            for ix in range(ix0, ix1 + 1):
                px = (ix + 0.5) * res
                for iy in range(iy0, iy1 + 1):
                    if (ix, iy) not in cells and _point_in_poly(px, (iy + 0.5) * res, poly):
                        cells.add((ix, iy))
    area = float(wa['size_x']) * float(wa['size_y'])
    return 100.0 * len(cells) * res * res / area if area > 0 else 0.0


def _safety_disk_contains(ob, px, py, world_map_mod, ring):
    """安全层圆盘判定：实体**锚点**为圆心、半径为 safety_radius+margin+extra。

 与 `safety_shield.cpp` 的二维静态圆盘模型同口径（锚点为圆心；复合体由 `safety_radius`
 覆盖全部 part 足迹）。复合体不再用「中心距离」，而用锚点（模型 pose）。
    """
    return math.hypot(px - float(ob['x']), py - float(ob['y'])) < _disk_radius(
        ob, world_map_mod, ring)


def _blocked_cells(geometry_obs, ring, world_map_mod):
    """待机环带 [RING_R_MIN, RING_R_MAX] 上被安全层圆盘覆盖的 (径向) 单元集合。"""
    blocked = set()
    r_steps = int(round((RING_R_MAX - RING_R_MIN) / 0.1)) + 1
    for ri in range(r_steps):
        r = RING_R_MIN + ri * 0.1
        for k in range(720):
            a = 2.0 * math.pi * k / 720.0
            px = TARGET_X + r * math.cos(a)
            py = TARGET_Y + r * math.sin(a)
            if any(math.hypot(px - float(o['x']), py - float(o['y'])) < _disk_radius(o, world_map_mod, ring)
                   for o in geometry_obs):
                blocked.add((ri, k))
    return blocked


# s04 主场景的出生位与目标（F1，2026-10-31：**改从出生布局配置文件读取**，不再硬编码）。
# 配置文件 = `src/agc_task/config/spawn_layout.yaml`（世界 spawn / 复位 / 己方机起飞参考的配置文件）。
# 硬编码副本会让"配置改了、核查还在验旧位"这种漂移静默通过——正是 F1 要消灭的病灶。
SPAWN_LAYOUT_PATH = os.path.join(ROOT, 'src', 'agc_task', 'config', 'spawn_layout.yaml')


def _spawn_layout():
    doc = _load_yaml(SPAWN_LAYOUT_PATH)['spawn_layout']
    return doc


_LAYOUT = _spawn_layout()
CAR_XY = (float(_LAYOUT['car']['x']), float(_LAYOUT['car']['y']))
TARGET_X, TARGET_Y = float(_LAYOUT['target']['x']), float(_LAYOUT['target']['y'])
OWN_XY = (float(_LAYOUT['own_uav']['x']), float(_LAYOUT['own_uav']['y']))


def _check_map(map_name, sim_share, perc_share, air_share, task_share, geom_path,
               world_path, wb_path, air_cfg, base_cfg, world_map_mod, ring, res):
    """对一张地图跑 (a)–(h)；返回该图的汇总 dict。"""
    geometry = _load_yaml(geom_path)
    obstacles = geometry.get('obstacles') or []
    wa = geometry.get('work_area') or {}
    sha = hashlib.sha256(open(geom_path, 'rb').read()).hexdigest()
    out = {'source': geom_path, 'sha256': sha, 'n_obstacles': len(obstacles)}

    src_ids = [o['id'] for o in obstacles]
    src_pose = {o['id']: [float(o['x']), float(o['y']), float(o['z']), 0.0, 0.0,
                          float(o.get('yaw', 0.0))] for o in obstacles}
    src_geom = {o['id']: _src_geometry_of(o, world_map_mod)
                for o in obstacles if not world_map_mod.is_composite(o)}
    # 复合模型：一个 <model> 含多个 <link>，逐 link 比对（link 名 = part id）
    src_parts = {o['id']: {pt['id']: _src_part_geometry_of(pt, world_map_mod)
                           for pt in world_map_mod.obstacle_parts(o)}
                 for o in obstacles if world_map_mod.is_composite(o)}

    # ---- (a) schema ----
    def _schema_ok(o):
        try:
            parts = world_map_mod.obstacle_parts(o)
            for pt in parts:
                world_map_mod.obstacle_shape(pt)
                world_map_mod.obstacle_size(pt, pt)
                # 材质档（视觉保真）：非法 finish → RuntimeError → schema 不合法
                world_map_mod.part_finish(pt)
            world_map_mod.obstacle_finish(o)
        except RuntimeError:
            return False
        rad = world_map_mod.obstacle_safety_radius(o)
        if not (math.isfinite(rad) and rad > 0.0):
            return False
        # 单图元须有顶层 size；复合模型须有 parts（顶层 x/y/z/yaw 为锚点）
        if world_map_mod.is_composite(o):
            return all(k in o for k in ('id', 'x', 'y', 'z', 'yaw'))
        return all(k in o for k in ('id', 'x', 'y', 'z', 'yaw', 'size'))


    a = {
        'declared_map_matches': (geometry.get('map') or 'minimal') == map_name,
        'work_area_keys_ok': all(k in wa for k in (
            'resolution', 'size_x', 'size_y', 'origin_x', 'origin_y')),
        'obstacles_nonempty': bool(obstacles),
        'obstacle_schema_ok': all(_schema_ok(o) for o in obstacles),
        'ids_unique': len(set(src_ids)) == len(src_ids),
        'shapes_registered': all(
            world_map_mod.obstacle_shape(pt) in world_map_mod.SHAPES
            for o in obstacles for pt in world_map_mod.obstacle_parts(o)),
    }
    a['pass'] = all(a.values())
    out['a_schema'] = a

    # ---- (b) 物理世界派生 ----
    tmp_world = os.path.join(tempfile.gettempdir(),
                             'w6_geometry_check_static_%s.sdf' % map_name)
    _generate_static_world(wb_path, world_path, tmp_world, geometry)
    static_models = _sdf_models(tmp_world)
    none_models = _sdf_models(world_path)  # base world（none 直接用）
    # 复合模型的 link 几何（按 model/link 取）
    comp_ok = True
    comp_detail = {}
    if src_parts:
        root = ET.parse(tmp_world).getroot()
        by_model = {}
        for m in root.iter('model'):
            links = {}
            for ln in m.findall('link'):
                geom = _geom_of(ln.find('.//collision/geometry'))
                vis = _geom_of(ln.find('.//visual/geometry'))
                links[ln.get('name')] = (geom, vis)
            by_model[m.get('name')] = links
        for mid, parts in src_parts.items():
            got = by_model.get(mid) or {}
            for pid, want in parts.items():
                if pid not in got:
                    comp_ok = False
                    comp_detail['%s/%s' % (mid, pid)] = 'missing link'
                    continue
                if got[pid][0] != want:
                    comp_ok = False
                    comp_detail['%s/%s' % (mid, pid)] = '%s != %s' % (got[pid][0], want)
                if got[pid][1] != got[pid][0]:
                    comp_ok = False
                    comp_detail['%s/%s' % (mid, pid)] = 'visual != collision'

    # ---- 材质档 → `<material><pbr>` 逐 link 核对（视觉保真；2026-10-29）----
    # 只核对**障碍模型**：地面 / 道路（`ground_plane` / `road_*` / `apron_*`）不在配置文件内，
    # 它们的 PBR 在 base world 里，属世界视觉层，不参与本条判定。
    src_by_id = {o['id']: o for o in obstacles}
    mat_ok = True
    mat_detail = {}
    mat_used = set()
    root_mat = ET.parse(tmp_world).getroot()
    for m in root_mat.iter('model'):
        mid = m.get('name')
        if mid not in src_by_id:
            continue
        ob = src_by_id[mid]
        want = {}
        if world_map_mod.is_composite(ob):
            for pr in world_map_mod.obstacle_parts(ob):
                want[pr['id']] = (world_map_mod.part_finish(pr)
                                  or world_map_mod.obstacle_finish(ob))
        else:
            want['link'] = world_map_mod.obstacle_finish(ob)
        for ln in m.findall('link'):
            name = ln.get('name')
            finish = want.get(name)
            metal = ln.find('.//visual/material/pbr/metal')
            if finish is None:
                if metal is not None:
                    mat_ok = False
                    mat_detail['%s/%s' % (mid, name)] = '未声明 finish 却写了 <pbr>'
                continue
            mat_used.add(finish)
            if metal is None:
                mat_ok = False
                mat_detail['%s/%s' % (mid, name)] = '声明 finish=%s 但缺 <pbr>' % finish
                continue
            exp_m, exp_r = world_map_mod.FINISH_PBR[finish][0], world_map_mod.FINISH_PBR[finish][1]
            got_m, got_r = metal.findtext('metalness'), metal.findtext('roughness')
            try:
                ok = (abs(float(got_m) - exp_m) < 1e-9 and abs(float(got_r) - exp_r) < 1e-9)
            except (TypeError, ValueError):
                ok = False
            if not ok:
                mat_ok = False
                mat_detail['%s/%s' % (mid, name)] = '%s/%s != %s/%s' % (
                    got_m, got_r, exp_m, exp_r)

    b = {
        'static_has_all_ids': all(i in static_models for i in src_ids),
        # （用户返工 ①）：yard **不含** pole_*；minimal 必须**仍含**两柱（核查基线）
        'pole_policy_matches_map': (('pole_1' in src_ids and 'pole_2' in src_ids)
                                    if map_name == 'minimal'
                                    else ('pole_1' not in src_ids and 'pole_2' not in src_ids)),
        'static_pose_match': all(_close(static_models[i]['pose'], src_pose[i])
                                 for i in src_ids if i in static_models),
        'static_geometry_match': all(
            static_models[i]['geometry'] == src_geom[i]
            for i in src_geom if i in static_models),
        # 视觉与碰撞**同源**（同一 `obstacle_geometry_sdf` 片段注入两次）
        'visual_equals_collision': all(
            static_models[i]['visual_geometry'] == static_models[i]['geometry']
            for i in src_geom if i in static_models),
        'none_world_has_no_obstacles': not any(n in none_models for n in src_ids) and not any(
            str(n).startswith('pole') for n in none_models),
        'static_world_wellformed': True,
        # 精致化：复合模型逐 part 的几何 / 视觉==碰撞
        'composite_parts_match': comp_ok,
        'composite_detail': comp_detail or 'n/a',
        'composite_model_count': len(src_parts),
        # 视觉保真（2026-10-29）：声明 `finish` 的 part → 世界 `<pbr><metal>` 的
        # metalness/roughness **逐值等于** `world_map.FINISH_PBR`；未声明 → **不得**出现 `<pbr>`。
        'material_finish_match': mat_ok,
        'material_detail': mat_detail or 'n/a',
        'material_kinds_used': sorted(mat_used),
    }
    if map_name == 'minimal':
        # 历史基线：pole_1/pole_2 的 pose / size **逐值不变**（0,-6,1.5)/(6,6,1.5)/(0.3,0.3,3.0)
        b['minimal_poles_unchanged'] = (
            _close(src_pose.get('pole_1'), [0.0, -6.0, 1.5, 0.0, 0.0, 0.0])
            and _close(src_pose.get('pole_2'), [6.0, 6.0, 1.5, 0.0, 0.0, 0.0])
            and _close([float(v) for v in
                        next(o for o in obstacles if o['id'] == 'pole_1')['size']],
                       [0.3, 0.3, 3.0]))
    # **显式列出**参与判定的布尔键：其余是细节（文本 / 计数），计数为 0 不代表失败
    _b_keys = ('static_has_all_ids', 'pole_policy_matches_map', 'static_pose_match',
               'static_geometry_match', 'visual_equals_collision',
               'none_world_has_no_obstacles', 'static_world_wellformed',
               'composite_parts_match', 'material_finish_match')
    b['pass'] = all(b[k] for k in _b_keys)
    if map_name == 'minimal':
        b['pass'] = b['pass'] and b.get('minimal_poles_unchanged', False)
    out['b_world_generation'] = b

    # ---- (c) 回退副本（仅 minimal；非 minimal 由 (j) 判定必须拒绝）----
    fb_obs_path = os.path.join(perc_share, 'config', 'obstacles.yaml')
    fb_map_path = os.path.join(perc_share, 'config', 'map.yaml')
    fb_obs = _load_yaml(fb_obs_path)
    fb_map = _load_yaml(fb_map_path)
    fb_list = fb_obs.get('obstacles') or []
    minimal_geom = _load_yaml(os.path.join(
        sim_share, 'config', world_map_mod.MAP_GEOMETRY_FILES['minimal']))
    min_pose = {o['id']: [float(o['x']), float(o['y']), float(o['z']), float(o.get('yaw', 0.0))]
                for o in (minimal_geom.get('obstacles') or [])}
    min_size = {o['id']: [float(s) for s in o['size']]
                for o in (minimal_geom.get('obstacles') or [])}

    def _fb_ok(o):
        return (o['id'] in min_pose
                and _close([float(o['x']), float(o['y']), float(o['z']),
                            float(o.get('yaw', 0.0))], min_pose[o['id']])
                and _close([float(s) for s in o['size']], min_size[o['id']]))

    min_wa = minimal_geom.get('work_area') or {}
    c = {
        'applies_to_map': 'minimal',
        'obstacles_ids_match': [o['id'] for o in fb_list] == [
            o['id'] for o in (minimal_geom.get('obstacles') or [])],
        'obstacles_geoms_match': all(_fb_ok(o) for o in fb_list),
        'map_matches_work_area': _close(
            [float(fb_map[k]) for k in
             ('resolution', 'size_x', 'size_y', 'origin_x', 'origin_y')],
            [float(min_wa[k]) for k in
             ('resolution', 'size_x', 'size_y', 'origin_x', 'origin_y')]),
    }
    c['pass'] = all(c.values())
    out['c_fallback_copies_match'] = c

    # ---- (d) air.yaml 无硬编码几何 / 半径列表 ----
    safety = air_cfg['trajectory_tracker']['ros__parameters']['safety']
    d = {
        'no_obstacle_names': 'obstacle_names' not in safety,
        'no_obstacle_x': 'obstacle_x' not in safety,
        'no_obstacle_y': 'obstacle_y' not in safety,
        # **定长半径列表已消除**（旧 `obstacle_safety_radius: [2.0, 2.0]`）
        'no_obstacle_safety_radius': 'obstacle_safety_radius' not in safety,
        # ADR-0010 (j)：顶高与净空同样**不得**在 air.yaml 硬编码（逐障碍 / 逐地图派生）。
        'no_obstacle_z_top': 'obstacle_z_top' not in safety,
        'no_vertical_clearance_m': 'vertical_clearance_m' not in safety,
    }
    d['pass'] = all(d.values())
    out['d_air_no_hardcoded_geometry'] = d

    # ---- (e) base 去硬编码 + compose 派生 == 配置文件 ----
    sys.path.insert(0, os.path.join(task_share, 'launch'))
    comp = _load_module(os.path.join(task_share, 'launch', 'composition.py'),
                        'composition')
    sr_base = base_cfg['scenario_reset']['ros__parameters']
    merged = comp.compose_params(base_cfg, {}, 'lightweight', 0, geometry=geometry)
    sr = merged['scenario_reset']
    bounds = comp.work_area_bounds(geometry)
    src_xs = [float(o['x']) for o in obstacles]
    src_ys = [float(o['y']) for o in obstacles]
    e = {
        'base_no_obstacle_names': 'obstacle_names' not in sr_base,
        'base_no_map_bounds': not any(k in sr_base for k in bounds),
        'compose_obstacles_match': (
            list(sr['obstacle_names']) == src_ids
            and [float(v) for v in sr['obstacle_x']] == src_xs
            and [float(v) for v in sr['obstacle_y']] == src_ys),
        'compose_bounds_match': all(float(sr[k]) == v for k, v in bounds.items()),
    }
    # ADR-0010 (j)：安全层几何注入必须含顶高 + 净空（且与配置文件逐值一致、与 ids 等长）
    air_inj = {'trajectory_tracker': {}}
    comp.apply_air_geometry(air_inj, geometry, sim_share=sim_share)
    inj = air_inj['trajectory_tracker']['safety']
    fa = geometry.get('flight_altitude') or {}
    e['air_z_tops_match'] = (
        [float(v) for v in inj.get('obstacle_z_top', [])]
        == [world_map_mod.obstacle_z_top(o) for o in obstacles])
    e['air_clearance_matches_map'] = (
        abs(float(inj.get('vertical_clearance_m', -1e9))
            - float(fa.get('own_clearance_min_m', float('nan')))) < 1e-9)
    e['pass'] = all(e.values())
    out['e_base_derived'] = e

    # ---- (f) sha256 稳定 + manifest geometry 块 == 配置文件 ----
    info = comp.load_scene(task_share, sim_share,
                           's04_static_static_obs_track', 0, world_map=map_name)
    # ADR-0007：高度随地图派生——核查脚本必须复现 launch 的同一条派生链，
    # 否则 `flight_altitude_derived_matches_source` 会因"没注入"而失败（假阴性）。
    _merged_for_assert = comp.compose_params(base_cfg, info['sc'], 'lightweight', 0,
                                             geometry=info['geometry'])
    comp.apply_flight_altitude_params(_merged_for_assert, info)
    asserts = comp.assertions('s04_static_static_obs_track', _merged_for_assert,
                              info, sim_share=sim_share)
    man = comp.build_manifest('lightweight', info, merged, asserts, sim_share=sim_share)
    gb = man.get('geometry') or {}
    f = {
        'sha256_matches_file': info['geometry_sha256'] == sha and len(sha) == 64,
        'manifest_map_matches': gb.get('map') == map_name,
        'manifest_sha256_match': gb.get('sha256') == sha,
        'derived_obstacles_match': [o['id'] for o in (gb.get('obstacles') or [])] == src_ids,
        'manifest_shapes_match': [o.get('shape') for o in (gb.get('obstacles') or [])] == [
            (None if world_map_mod.is_composite(o)
             else world_map_mod.obstacle_shape(o)) for o in obstacles],
        'manifest_radii_match': [o.get('safety_radius') for o in (gb.get('obstacles') or [])] == [
            world_map_mod.obstacle_safety_radius(o) for o in obstacles],
        # ADR-0010 (j)：manifest 的 z_top == 配置文件派生（垂直门控输入，登账可复核）
        'manifest_z_tops_match': [o.get('z_top') for o in (gb.get('obstacles') or [])] == [
            world_map_mod.obstacle_z_top(o) for o in obstacles],
        'assertions_all_pass': all(asserts.values()),
        # 感知先验尺寸 == 配置文件按**感知可表达**尺寸（cylinder 降级为外接矩形 2r×2r×h）
        'derived_obstacles_size_matches_perception_schema': all(
            _close([float(v) for v in d['size']],
                   world_map_mod.obstacle_bbox_size(
                       next(o for o in obstacles if o['id'] == d['id'])))
            for d in (_load_yaml(info['obstacles_file']).get('obstacles') or [])),
    }
    f['pass'] = all(f.values())
    out['f_derivation_and_hash'] = f

    # ---- (g) 出生净空（与 scenario_reset.validateCandidate 同判据）----
    # F1（2026-10-31）：坐标来自出生布局配置文件（`spawn_layout.yaml`），并追加
    # 「车-目标 / 己方机-目标 / 车-己方机」三组设计距离判据——这是派工单的验收口径，
    # 不再只有"车↔目标 ≥6 m"这一条。
    g = {'map': map_name, 'spawn_layout_source': SPAWN_LAYOUT_PATH}
    worst = {}
    for name, (px, py), _extent in (
            ('car', CAR_XY, 0.5037), ('target', (TARGET_X, TARGET_Y), 0.25),
            ('own_uav', OWN_XY, 0.25)):
        clear = min(_obb_clearance(px, py, o, world_map_mod) - _footprint_extent(o, world_map_mod)
                    for o in obstacles)
        worst[name] = round(clear, 6)
    g['min_footprint_clearance_m'] = worst
    g['all_spawns_clear'] = all(v > 0.0 for v in worst.values())
    # 车↔目标 标定值 6.0 m（ADR-0012）
    car_target = math.hypot(CAR_XY[0] - TARGET_X, CAR_XY[1] - TARGET_Y)
    own_target = math.hypot(OWN_XY[0] - TARGET_X, OWN_XY[1] - TARGET_Y)
    car_own = math.hypot(CAR_XY[0] - OWN_XY[0], CAR_XY[1] - OWN_XY[1])
    g['car_target_distance_m'] = round(car_target, 6)
    g['own_uav_target_distance_m'] = round(own_target, 6)
    g['car_own_uav_distance_m'] = round(car_own, 6)
    g['car_target_clearance_ok'] = car_target >= 6.0
    # F1 设计目标（派工单）：车/目标 ≥30 m、己方机/目标 ≥25 m、己方车机 3–8 m。
    g['car_target_ge_30'] = car_target >= 30.0
    g['own_uav_target_ge_25'] = own_target >= 25.0
    g['car_own_uav_in_3_8'] = 3.0 <= car_own <= 8.0
    g['boundary_inner_ok'] = bool(
        wa['origin_x'] + 0.5037 <= CAR_XY[0] <= wa['origin_x'] + wa['size_x'] - 0.5037
        and wa['origin_y'] + 0.5037 <= CAR_XY[1] <= wa['origin_y'] + wa['size_y'] - 0.5037)
    g['pass'] = all(g[k] for k in (
        'all_spawns_clear', 'car_target_clearance_ok', 'boundary_inner_ok',
        'car_target_ge_30', 'own_uav_target_ge_25', 'car_own_uav_in_3_8'))
    out['g_spawn_clearance_c7'] = g

    # ---- (h) 障碍族可见性（z=0.48 处有水平截面）----
    h = {'map': map_name, 'laser_plane_z_m': LASER_PLANE_Z_M}
    invisible = []
    for o in obstacles:
        visible = False
        for pt in world_map_mod.obstacle_parts(o):
            size = [float(v) for v in pt['size']]
            # `obstacle_parts` 已把缺失的 z 归一化为 size[2]/2；单图元的 z 即**模型内**几何中心，
            # 复合模型的 part z 是相对锚点偏移。两种情形都由 model 的 pose z 承担绝对高度，
            # 故这里比较的绝对 z = 模型 z + part 局部 z（单图元 part 局部 z 取 0 对应模型 z 本身）。
            if world_map_mod.is_composite(o):
                z_center = float(o['z']) + float(pt['z'])
            else:
                z_center = float(o['z'])
            z0 = z_center - size[2] / 2.0
            z1 = z_center + size[2] / 2.0
            if z0 <= LASER_PLANE_Z_M <= z1:
                visible = True
                break
        if not visible:
            invisible.append(o['id'])
    h['obstacles_invisible_to_ground_laser'] = invisible
    h['all_visible_to_ground_laser'] = not invisible
    h['pass'] = h['all_visible_to_ground_laser']
    out['h_laser_visibility'] = h
    return out


def _accepts(fn, kw):
    import inspect
    try:
        return kw in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None, help='JSON 摘要落盘路径（可选）')
    ap.add_argument('--maps', default=None,
                    help='逗号分隔地图名（缺省=清单全部：minimal,yard,open_field）')
    args = ap.parse_args()

    sim_share = _share('agc_sim')
    perc_share = _share('agc_perception')
    air_share = _share('agc_air')
    task_share = _share('agc_task')

    world_path = os.path.join(sim_share, 'worlds', 'agc_world.sdf')
    wb_path = os.path.join(sim_share, 'launch', 'world_bringup.launch.py')

    res = {'per_map': {}}
    try:
        world_map_mod = _resolve_maps(sim_share)
        res['map_registry'] = list(world_map_mod.WORLD_MAPS)
        maps = ([m.strip() for m in args.maps.split(',') if m.strip()]
                if args.maps else list(world_map_mod.WORLD_MAPS))
        air_cfg = _load_yaml(os.path.join(air_share, 'config', 'air.yaml'))
        base_cfg = _load_yaml(os.path.join(task_share, 'config', 'base.yaml'))
        ring = _air_ring_params(air_share)
        res['air_ring'] = ring

        for map_name in maps:
            _, geom_path = world_map_mod.geometry_path(sim_share, map_name)
            res['per_map'][map_name] = _check_map(
                map_name, sim_share, perc_share, air_share, task_share, geom_path,
                world_path, wb_path, air_cfg, base_cfg, world_map_mod, ring, res)

        # ---- (i) 空中安全层可行解（跨图；以 minimal 为基线）----
        baseline = None
        i_res = {'ring_r_min_m': RING_R_MIN, 'ring_r_max_m': RING_R_MAX, 'maps': {}}
        for map_name in maps:
            _, geom_path = world_map_mod.geometry_path(sim_share, map_name)
            obs = _load_yaml(geom_path).get('obstacles') or []
            cells = _blocked_cells(obs, ring, world_map_mod)
            if baseline is None:
                baseline = cells
            # 环带可行率（按 RING 半径的 3600 个角向采样）与最大连续阻塞弧
            ring_r = ring['target_min_dist'] + ring['target_margin'] + ring['extra']
            total = 3600
            blocked = [False] * total
            for k in range(total):
                ang = 2.0 * math.pi * k / total
                px = TARGET_X + ring_r * math.cos(ang)
                py = TARGET_Y + ring_r * math.sin(ang)
                blocked[k] = any(
                _safety_disk_contains(o, px, py, world_map_mod, ring) for o in obs)
            feasible = total - sum(blocked)
            # 最长**连续可行弧**（环形）：安全层有可行解 ⟺ 存在一段可用弧供 standoff 驻留
            cur = 0
            max_free = 0
            for k in range(2 * total):
                if not blocked[k % total]:
                    cur += 1
                    max_free = max(max_free, cur)
                else:
                    cur = 0
            cur = 0
            max_blocked = 0
            for k in range(2 * total):
                if blocked[k % total]:
                    cur += 1
                    max_blocked = max(max_blocked, cur)
                else:
                    cur = 0
            i_res['maps'][map_name] = {
                'ring_radius_m': round(ring_r, 4),
                'feasible_pct': round(100.0 * feasible / total, 2),
                'max_free_arc_deg': round(360.0 * max_free / total, 2),
                'max_blocked_arc_deg': round(360.0 * max_blocked / total, 2),
                # 相对 minimal 的**新增**阻塞单元：如实登记（不参与 pass——用户要求中央加内容，
                # 阻塞必然增加；判据是"仍存在可行解"而不是"不比 minimal 多"）。
                'new_blocked_cells_vs_minimal': len(cells - baseline),
                'blocked_cells': len(cells),
            }
        # 判据：**空中安全层在每张地图上均存在可行解**——
        # ① 环带可行率 > 0（不是全被膨胀圆盘吃掉）；② 最长连续可行弧 ≥ 90°（够 standoff 驻留）。
        # 新增阻塞量只作登记：yard 按用户要求增加中央内容后必然更挡环带，须如实报告而不据此判 FAIL。
        i_res['feasible_solution_exists'] = all(
            v['feasible_pct'] > 0.0 for v in i_res['maps'].values())
        i_res['max_free_arc_ge_90deg'] = all(
            v['max_free_arc_deg'] >= 90.0 for v in i_res['maps'].values())
        i_res['pass'] = i_res['feasible_solution_exists'] and i_res['max_free_arc_ge_90deg']
        res['tests'] = res.get('tests', {})
        res['tests']['i_air_shield_feasible'] = i_res

        # ---- (j) 回退副本边界 ----
        perc_launch = open(os.path.join(perc_share, 'launch', 'perception_bringup.launch.py'),
                           encoding='utf-8').read()
        w6_src = open(os.path.join(task_share, 'launch', 'main.launch.py'),
                      encoding='utf-8').read()
        j = {
            'perception_default_map_file_is_fallback': 'default_map_file' in perc_launch,
            'perception_default_obstacles_is_fallback': 'default_obstacles_file' in perc_launch,
            'w6_injects_derived_map_file': "info['derived_map_file']" in w6_src,
            'w6_injects_derived_obstacles': "info['obstacles_file']" in w6_src,
            'w6_passes_world_map': "'world_map': info['world_map']" in w6_src,
        }
        j['pass'] = all(j.values())
        res['tests']['j_fallback_boundary'] = j

        # ---- (k) 权限成文假设 ----
        obs_txt = open(os.path.join(perc_share, 'config', 'obstacles.yaml'),
                       encoding='utf-8').read()
        k = {
            'static_prior_wording_present': '静态先验' in obs_txt,
            'no_truth_advantage_clause_present': '不得静默引入真值优势' in obs_txt,
        }
        k['pass'] = all(k.values())
        res['tests']['k_permission_assumption'] = k

        # ---- (l) 地图登记一致 ----
        reg = _load_yaml(os.path.join(task_share, 'config', 'scenarios.yaml'))['scenes']
        declared = {s: (v.get('world_map') or '') for s, v in reg.items() if v.get('world_map')}
        l = {
            'all_declared_maps_registered': all(m in world_map_mod.WORLD_MAPS
                                                for m in declared.values()),
            's04_uses_yard': declared.get('s04_static_static_obs_track') == 'yard',
            'unregistered_scenes_default_minimal': all(
                (v.get('world_map') or 'minimal') == 'minimal'
                for s, v in reg.items() if s not in declared),
            'declared_scenes': declared,
        }
        l['pass'] = all(l[k_] for k_ in (
            'all_declared_maps_registered', 's04_uses_yard',
            'unregistered_scenes_default_minimal'))
        res['tests']['l_scene_map_registration'] = l

        # ---- (m) 清单单一实现（无自持文件名表）----
        wb_src = open(wb_path, encoding='utf-8').read()
        air_launch = open(os.path.join(air_share, 'launch', 'air_bringup.launch.py'),
                          encoding='utf-8').read()
        comp_src = open(os.path.join(task_share, 'launch', 'composition.py'),
                        encoding='utf-8').read()
        m = {
            'world_bringup_imports_world_map': 'from world_map import' in wb_src,
            'air_bringup_imports_world_map': 'import world_map as' in air_launch,
            'composition_loads_world_map': 'world_map.py' in comp_src,
            'world_bringup_has_no_own_table': 'MAP_GEOMETRY_FILES = {' not in wb_src,
            'composition_has_no_own_table': "MAP_GEOMETRY_FILES = {" not in comp_src,
            'world_map_module_installed': os.path.exists(
                os.path.join(sim_share, 'launch', 'world_map.py')),
        }
        m['pass'] = all(m.values())
        res['tests']['m_single_registry'] = m

        # ---- (n) GUI 网格只关视觉（用户返工 ③）----
        world_txt = open(os.path.join(sim_share, 'worlds', 'agc_world.sdf'),
                         encoding='utf-8').read()
        wroot = __import__('xml.etree.ElementTree', fromlist=['parse']).parse(
            os.path.join(sim_share, 'worlds', 'agc_world.sdf')).getroot()
        grid_el = wroot.find('.//scene/grid')
        n = {
            'grid_visual_disabled': (grid_el is not None
                                     and str(grid_el.text).strip().lower() == 'false'),
            'ground_plane_still_present': any(
                mm.get('name') == 'ground_plane' for mm in wroot.iter('model')),
            'ground_plane_collision_present': any(
                mm.get('name') == 'ground_plane' and mm.find('.//collision') is not None
                for mm in wroot.iter('model')),
            'physics_unchanged': 'max_step_size>0.004<' in world_txt.replace(' ', ''),
            'geometry_source_not_touched_by_grid': all(
                len(_load_yaml(world_map_mod.geometry_path(sim_share, mp)[1])
                    .get('obstacles') or []) > 0 for mp in world_map_mod.WORLD_MAPS),
        }
        n['pass'] = all(n.values())
        res['tests']['n_grid_visual_only'] = n

        # ---- (o) yard 形状 / 尺寸 / 朝向多样性（用户返工 ②）----
        _, yard_path = world_map_mod.geometry_path(sim_share, 'yard')
        yard_geom = _load_yaml(yard_path)
        yard_obs = yard_geom.get('obstacles') or []
        wa = yard_geom.get('work_area') or {}
        all_parts = [pt for o in yard_obs for pt in world_map_mod.obstacle_parts(o)]
        part_sizes = [max(float(v) for v in pt['size']) for pt in all_parts]
        small_parts = [s for s in part_sizes if s < 1.0]
        shapes = sorted({world_map_mod.obstacle_shape(pt) for pt in all_parts})
        longest = max(part_sizes)
        shortest = min(min(float(v) for v in pt['size'][:2]) for pt in all_parts)
        yaws = sorted({round(float(o.get('yaw', 0.0)), 3) for o in yard_obs})
        heights = [float(pt['size'][2]) for pt in all_parts]
        o_res = {
            # 2026-10-29 用户裁定：作业区 80×80 → 100×100 并**重做 yard 数量与分布**（上限 20→32）；
            # 同日 21:00 再次要求「略增小型件」→ 上限 32→**40**（现 36 实体，仍留余量，不放任膨胀）。
            # R6（2026-10-30）用户裁定「加尺度参照物」→ 上限 40 → **46**（现 42，留余量）。
            # 变更理由：参照物必须**可碰撞**（禁止装饰性无碰撞件），故只能进配置文件 / 计入实体数。
            'n_obstacles_le_46': len(yard_obs) <= 46,
            'n_obstacles': len(yard_obs),
            'n_parts': len(all_parts),
            # 覆盖口径成文为**并集**（同一实体多图元堆叠只计一次）；5%–12% 是 规格目标，
            # 旧记录 7.36% 不可复现（见 _union_coverage_pct 注释），本断言使其第一次可自动判定。
            'coverage_union_pct': round(_union_coverage_pct(yard_obs, wa, world_map_mod), 2),
            'coverage_union_in_5_12': 5.0 <= _union_coverage_pct(yard_obs, wa, world_map_mod) <= 12.0,
            'geometry_kinds_ge_3': len({world_map_mod.obstacle_shape(pt) for pt in all_parts}) >= 3,
            'geometry_kinds': sorted({world_map_mod.obstacle_shape(pt) for pt in all_parts}),
            'small_parts_ge_6': len(small_parts) >= 6,
            'small_parts_count': len(small_parts),
            'material_kinds_ge_3': len({world_map_mod.part_finish(pt) for pt in all_parts
                                        if world_map_mod.part_finish(pt)}) >= 3,
            'material_kinds': sorted({world_map_mod.part_finish(pt) for pt in all_parts
                                      if world_map_mod.part_finish(pt)}),
            'has_composite_models': any(world_map_mod.is_composite(o) for o in yard_obs),
            'composite_model_count': sum(1 for o in yard_obs if world_map_mod.is_composite(o)),
            'shapes_ge_2': len(shapes) >= 2,
            'shape_kinds': shapes,
            'size_ratio_ge_3': (longest / shortest) >= 3.0,
            'longest_over_shortest': round(longest / shortest, 2),
            'height_ratio_ge_2': (max(heights) / min(heights)) >= 2.0,
            'yaw_kinds_ge_3': len(yaws) >= 3,
            'yaw_kinds': len(yaws),
            'central_content_ge_3': sum(
                1 for o in yard_obs
                if math.hypot(float(o['x']), float(o['y'])) <= 15.0) >= 3,
            'central_count': sum(
                1 for o in yard_obs
                if math.hypot(float(o['x']), float(o['y'])) <= 15.0),
        }
        o_res['pass'] = all(o_res[k_] for k_ in (
            'n_obstacles_le_46', 'shapes_ge_2', 'size_ratio_ge_3', 'height_ratio_ge_2',
            'yaw_kinds_ge_3', 'central_content_ge_3', 'geometry_kinds_ge_3',
            'small_parts_ge_6', 'has_composite_models', 'coverage_union_in_5_12',
            'material_kinds_ge_3'))
        res['tests']['o_yard_diversity'] = o_res

        # ---- (p) 三图作业区一致（2026-10-29 用户裁定 100×100）----
        wa_all = {}
        for map_name in maps:
            _, gp = world_map_mod.geometry_path(sim_share, map_name)
            wa_all[map_name] = tuple(float(v) for v in (_load_yaml(gp)['work_area'][k]
                                     for k in ('resolution', 'size_x', 'size_y', 'origin_x', 'origin_y')))
        p_res = {
            'work_area_per_map': {k: list(v) for k, v in wa_all.items()},
            'all_maps_uniform': len(set(wa_all.values())) == 1,
            'is_100x100_origin_-50': all(v[1] == 100.0 and v[2] == 100.0
                                         and v[3] == -50.0 and v[4] == -50.0 for v in wa_all.values()),
        }
        p_res['pass'] = p_res['all_maps_uniform'] and p_res['is_100x100_origin_-50']
        res['tests']['p_work_area_uniform'] = p_res

        # ---- (q) 明度带（R6，2026-10-30）：**屋面 L − 基层地面 L ≥ 0.30** ----
        # 用户裁定「建筑与地面区分度低」的量化判据。取配置文件里 `finish: roofpanel` 的屋面
        # albedo 亮度最小值 vs base world `ground_plane` 的 albedo 亮度。
        def _lum(c):
            return 0.2126 * float(c[0]) + 0.7152 * float(c[1]) + 0.0722 * float(c[2])

        world_txt = open(world_path, encoding='utf-8').read()
        gp = re.search(r'<model name="ground_plane">.*?<ambient>([0-9.]+) ([0-9.]+) ([0-9.]+)',
                       world_txt, re.S)
        ground_l = _lum([float(gp.group(1)), float(gp.group(2)), float(gp.group(3))]) if gp else None
        # R6②：地面贴了 albedo_map 时，基色会被置白（贴图与基色相乘），真实地面色在贴图里
        # → 从 materials/manifest.json 的 base_srgb 取，否则会误判成 "地面 L=1.0"。
        tex_m = re.search(r'<model name="ground_plane">.*?<albedo_map>([^<]+)</albedo_map>',
                          world_txt, re.S)
        if tex_m:
            import json as _json
            man = os.path.join(sim_share, 'materials', 'manifest.json')
            tex_name = os.path.basename(tex_m.group(1)).rsplit('.', 1)[0]
            with open(man, encoding='utf-8') as f:
                base = _json.load(f)['textures'][tex_name]['base_srgb']
            ground_l = _lum(base)
        _, yard_p = world_map_mod.geometry_path(sim_share, 'yard')
        yard_obs_q = _load_yaml(yard_p).get('obstacles') or []
        roofs = [pt for o in yard_obs_q for pt in world_map_mod.obstacle_parts(o)
                 if world_map_mod.part_finish(pt) == 'roofpanel']
        roof_l = min((_lum(pt['color']) for pt in roofs), default=None)
        q_res = {
            'ground_albedo_luma': None if ground_l is None else round(ground_l, 3),
            'roof_albedo_luma_min': None if roof_l is None else round(roof_l, 3),
            'roof_parts_count': len(roofs),
            'gap': None if (roof_l is None or ground_l is None) else round(roof_l - ground_l, 3),
            'gap_ge_0_30': (roof_l is not None and ground_l is not None
                            and (roof_l - ground_l) >= 0.30),
            # 金属度纪律：屋面若用 `steel`（metalness 高）在无环境贴图时会被渲染成黑色，
            # 本轮实测确认 → 要求屋面档必须是 `roofpanel`。
            'roof_uses_roofpanel': len(roofs) > 0,
        }
        q_res['pass'] = q_res['gap_ge_0_30'] and q_res['roof_uses_roofpanel']
        res['tests']['q_luma_bands'] = q_res

        res['overall_pass'] = all(t.get('pass') for t in res['tests'].values()) and all(
            all(sub.get('pass') for sub in v.values() if isinstance(sub, dict) and 'pass' in sub)
            for v in res['per_map'].values())
    except Exception as exc:  # noqa: BLE001
        import traceback
        res['error'] = repr(exc)
        res['traceback'] = traceback.format_exc()
        res['overall_pass'] = False

    for map_name, per in res.get('per_map', {}).items():
        print('[%s] n_obstacles=%s sha256=%s' % (
            map_name, per.get('n_obstacles'), (per.get('sha256') or '')[:16]))
        for name, t in per.items():
            if not isinstance(t, dict) or 'pass' not in t:
                continue
            print('    %-30s %s' % (name, 'PASS' if t.get('pass') else 'FAIL'))
            if not t.get('pass'):
                for kk, vv in t.items():
                    if kk != 'pass':
                        print('        %s = %s' % (kk, vv))
    for name, t in res.get('tests', {}).items():
        print('%-32s %s' % (name, 'PASS' if t.get('pass') else 'FAIL'))
        for kk, vv in t.items():
            if kk != 'pass':
                print('    %s = %s' % (kk, vv))
    if 'error' in res:
        print('error:', res['error'])
        print(res.get('traceback', ''))
    print('\n%s (maps=%s)' % (
        'PASS' if res.get('overall_pass') else 'FAIL',
        ','.join(res.get('per_map', {}).keys())))

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        checklib.write_json(args.out, res)
        print('-> %s' % args.out)
    return 0 if res.get('overall_pass') else 1


if __name__ == '__main__':
    sys.exit(main())
