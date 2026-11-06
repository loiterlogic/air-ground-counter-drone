#!/usr/bin/env python3
"""world_map —— 几何真源「按地图分文件」的**单一清单**（P1-1）。

`world_geometry.yaml`（minimal）与 `maps/*.yaml`（yard / open_field）都是**静态障碍 +
作业区几何**的配置文件，只是按地图拆成多个文件。**哪张地图对应哪个文件**只在本文登记一次；
消费者（`world_bringup.launch.py`、`agc_task/launch/composition.py`、
`agc_air/launch/air_bringup.launch.py`、`tests/check_scene_geometry.py`）一律经本模块解析。

纪律：
 * 新增地图 = 本表加一行 + 加一个 yaml 文件；**不得**在消费方各写一份文件名表
 （三份表漂移会让不同域读到不同配置文件，正是 ADR-0007 要消灭的病灶）。
 * 未知地图名一律**拒绝运行**（不静默回退 minimal）。
 * 本模块只做**路径与形状规范化**，不做几何计算、不读环境、不写文件。

形状口径（与 `world_geometry.yaml` 头部 schema 一致）：
 * `shape`：`box` | `cylinder` | `sphere`，缺省 `box`（老配置不写仍可运行）；
 * `size`：box `[x, y, z]`；cylinder `[r, r, h]`；sphere `[r, r, r]`；
 * `parts`（可选）：**复合模型**——一个 `id` 由多个图元拼成（塔身 + 平台 + 台阶 + 门廊 …）。
 每 part 形如 `{shape, x, y, z, yaw, size, color?}`，坐标是**相对模型锚点**的局部偏移。
 复合模型在物理世界里是**一个 `<model>` 含多个 `<link>`**（每 part 一 link，静态），
 碰撞与视觉仍**同源**（同一 `<geometry>` 片段注入 collision 与 visual）。
 * `safety_radius`：实体水平面**外接圆半径**，缺省 2.0（历史 pole 标定值）；复合模型须覆盖
 **全部 part** 的水平足迹（可由 `footprint_radius` 推导）。
"""

import math
import os

# 地图名 → 相对 `agc_sim/share/agc_sim/config/` 的配置文件文件。
# `minimal` 沿用历史文件名 `world_geometry.yaml`（路径 / 核查基线不变）。
MAP_GEOMETRY_FILES = {
    'minimal': 'world_geometry.yaml',
    'yard': os.path.join('maps', 'yard.yaml'),
    'open_field': os.path.join('maps', 'open_field.yaml'),
}

DEFAULT_WORLD_MAP = 'minimal'

# 可用地图名（保持文件内声明顺序，供报错信息与核查使用）。
WORLD_MAPS = tuple(MAP_GEOMETRY_FILES)

# 外接圆半径缺省值（历史 pole 标定值；ADR-0007）。
DEFAULT_SAFETY_RADIUS = 2.0

# 支持的单图元形状（ 起含 sphere；ADR-0007 / 本单 schema 扩展）。
SHAPES = ('box', 'cylinder', 'sphere')

# 材质档（ 视觉保真；2026-10-29）：**可选**字段 `finish`，缺省不写 = 旧行为（无 PBR 块）。
# 语义 = 真实材料类别的**标量 PBR 近似**（metalness / roughness）。依据：本机 sdformat 1.11
# `material.sdf` 的 `<pbr><metal><metalness>|<roughness>` 是**标量**字段（无需贴图）
# —— 本项目不引入外部资产（world_geometry.yaml 纪律），故只能走标量 PBR。
# 逐 part 可覆盖实体级 `finish`。
# concrete 混凝土 / steel 结构钢 / paint 涂装金属 / glass 玻璃 / rust 锈蚀 /
# asphalt 沥青 / rubber 橡胶塑料
FINISHES = ('concrete', 'steel', 'paint', 'glass', 'rust', 'asphalt', 'rubber', 'roofpanel')

# finish → (metalness, roughness, specular 强度, diffuse 亮度系数)
# specular 强度喂经典材质 `<specular>`；diffuse 系数用于压暗玻璃等。**纯视觉，不改几何**。
FINISH_PBR = {
    'concrete': (0.00, 0.90, 0.12, 1.00),
    # R6（2026-10-30）：**metalness 才是渲染亮度的杠杆**。本轮实测：无环境贴图时
    # metalness=0.75 的构件几乎没有漫反射分量，`steel` 屋面在 118 m 俯视渲染里只有
    # 83/255，而旁边 metalness=0 的混凝土檐是 161/255 —— 即"提亮 albedo 对金属件无效"。
    # 故把 `steel` 从 0.75 降到 0.35（仍偏金属观感），并新增 `roofpanel`（近漫反射的
    # 金属屋面板）作为屋面专用档。语义不变：仍是"该材料的标量近似"。
    'steel':    (0.35, 0.42, 0.60, 1.02),
    'paint':    (0.15, 0.45, 0.42, 1.00),
    'glass':    (0.05, 0.08, 1.00, 0.72),
    'rust':     (0.10, 0.95, 0.10, 0.98),
    'asphalt':  (0.00, 0.95, 0.04, 1.00),
    'rubber':   (0.00, 0.80, 0.10, 1.00),
    # 屋面专用：低金属度 + 中等粗糙 → 在仅有方向光 + 环境光的场景里仍读作"浅色金属板"
    'roofpanel': (0.06, 0.40, 0.48, 1.00),
}


def part_finish(src):
    """图元 / 实体的材质档（缺省 `None` = 不写 PBR 块，保持旧渲染行为）；非法值拒绝运行。"""
    raw = src.get('finish')
    if raw is None:
        return None
    val = str(raw).strip().lower()
    if val not in FINISHES:
        raise RuntimeError(
            '障碍 %s 的 finish=%r 不受支持（可用：%s；留空则用旧材质）→ 拒绝运行'
            % (src.get('id'), src.get('finish'), ' | '.join(FINISHES)))
    return val


def obstacle_finish(ob):
    """实体级材质档（复合模型的 part 可在注入处逐 part 覆盖）。"""
    return part_finish(ob)


def resolve(world_map):
    """规范化并校验地图名；未知值抛 `RuntimeError`（调用方据此拒绝运行）。"""
    name = (world_map or DEFAULT_WORLD_MAP).strip()
    if name not in MAP_GEOMETRY_FILES:
        raise RuntimeError(
            '未知 world_map=%s（可用：%s）→ 拒绝运行' % (name, ' | '.join(WORLD_MAPS)))
    return name


def geometry_path(sim_share, world_map=DEFAULT_WORLD_MAP):
    """返回 `(地图名, 真源绝对路径)`。"""
    name = resolve(world_map)
    return name, os.path.join(sim_share, 'config', MAP_GEOMETRY_FILES[name])


def obstacle_shape(ob):
    """单图元形状（缺省 box）；非法值抛 `RuntimeError`。"""
    shape = str(ob.get('shape') or 'box').strip().lower()
    if shape not in SHAPES:
        raise RuntimeError(
            '障碍 %s 的 shape=%r 不受支持（可用：%s）→ 拒绝运行'
            % (ob.get('id'), ob.get('shape'), ' | '.join(SHAPES)))
    return shape


def is_composite(ob):
    """复合模型判定：`parts` 非空即为复合（此时顶层 `shape`/`size` 可省略）。"""
    return bool(ob.get('parts') or [])


def obstacle_parts(ob):
    """把实体规范化为 **parts 列表**（单图元 → 单 part；复合 → 原样 parts）。

 单图元的 `x/y/z/yaw/size/color` 即 part 自身；复合模型的顶层 `x/y/z/yaw` 是**锚点**，
 每 part 的 `x/y/z` 是相对锚点的局部偏移（`yaw` 为 part 自身的局部朝向）。
    """
    if is_composite(ob):
        parts = []
        for i, pt in enumerate(ob['parts']):
            part = dict(pt)
            part.setdefault('id', '%s_part%d' % (ob.get('id'), i))
            part.setdefault('yaw', 0.0)
            part.setdefault('z', float(part['size'][2]) / 2.0)
            part.setdefault('x', 0.0)
            part.setdefault('y', 0.0)
            parts.append(part)
        if not parts:
            raise RuntimeError('复合障碍 %s 的 parts 为空 → 拒绝运行' % ob.get('id'))
        # 锚点 z 必须为 0：part 的 z 是相对锚点的**绝对高度偏移**（注入器不再叠加锚点 z）。
        # 非零锚点会让整段模型悬浮/埋地（实测 wall_w 曾被写成 z=1.1 → 整墙悬空 1.1 m）。
        if abs(float(ob.get('z', 0.0))) > 1e-9:
            raise RuntimeError(
                '复合障碍 %s 的锚点 z=%s 必须为 0（part 的 z 已是绝对高度偏移）→ 拒绝运行'
                % (ob.get('id'), ob.get('z')))
        return parts
    return [ob]


def obstacle_size(ob, part=None):
    """单图元 `size` 三元组（float）；分量不足 / cylinder 半径不一致即拒绝运行。"""
    src = part if part is not None else ob
    shape = obstacle_shape(src)
    size = [float(v) for v in (src.get('size') or [])]
    if len(size) < 3:
        raise RuntimeError('障碍 %s 的 size 需 3 个分量，实际 %r → 拒绝运行'
                           % (src.get('id'), src.get('size')))
    if shape == 'cylinder' and abs(size[0] - size[1]) > 1e-9:
        raise RuntimeError(
            'cylinder 障碍 %s 的 size[0]=%s 与 size[1]=%s 不相等（口径为 [r, r, h]）→ 拒绝运行'
            % (src.get('id'), size[0], size[1]))
    if shape == 'sphere' and (abs(size[0] - size[1]) > 1e-9 or abs(size[0] - size[2]) > 1e-9):
        raise RuntimeError(
            'sphere 障碍 %s 的 size 须为 [r, r, r]，实际 %r → 拒绝运行'
            % (src.get('id'), size))
    return size


def _part_footprint_radius(part):
    """单 part 在**局部**坐标下的水平外接圆半径。"""
    shape = obstacle_shape(part)
    size = obstacle_size(part, part)
    if shape in ('cylinder', 'sphere'):
        return size[0]
    return math.hypot(size[0], size[1]) / 2.0


def obstacle_footprint_radius(ob):
    """实体（含复合）在**锚点局部系**下的水平外接圆半径——覆盖全部 part。"""
    if not is_composite(ob):
        return _part_footprint_radius(ob)
    best = 0.0
    for part in obstacle_parts(ob):
        d = math.hypot(float(part['x']), float(part['y'])) + _part_footprint_radius(part)
        best = max(best, d)
    return best


def obstacle_safety_radius(ob):
    """实体水平面外接圆半径（显式 `safety_radius` 优先；否则由**足迹**推导，缺省 2.0）。

复合 / 自定义形体不再依赖手写常量——未显式给出时按 part 足迹推导，
 保证安全层圆盘**必然覆盖**实体几何（保守外扩）。
    """
    if ob.get('safety_radius') is not None:
        return float(ob['safety_radius'])
    if is_composite(ob) or ob.get('shape') in ('box', 'cylinder', 'sphere'):
        radius = obstacle_footprint_radius(ob)
        if radius > 0.0:
            return radius
    return DEFAULT_SAFETY_RADIUS


def _part_bbox_size(part):
    """单 part 在感知 / 栅格可表达的尺寸（box 原值；cylinder → 2r×2r×h；sphere → 2r 立方）。"""
    size = obstacle_size(part, part)
    shape = obstacle_shape(part)
    if shape == 'cylinder':
        return [2.0 * size[0], 2.0 * size[1], size[2]]
    if shape == 'sphere':
        return [2.0 * size[0], 2.0 * size[0], 2.0 * size[0]]
    return size


def obstacle_z_top(ob):
    """实体**顶面高度**（世界 ENU，m）：单图元 `z + size[2]/2`；复合体取**全部 part 的最大值**。

    消费者 = 空中安全层的**垂直门控**（`safety.obstacle_z_top`，见 ADR-0010「垂直门控」）。
    口径与 `height_survey` 的 `rect_of()[4]` 一致：复合体 part 的 `z` 已是**绝对高度偏移**
 （锚点 z 恒为 0，见 `obstacle_parts`），故直接 `part.z + size[2]/2` 取 max，**不**叠加锚点 z。

 这是**派生**量（配置文件仍是各 part 的 `z` / `size`），不新增 schema 键，故无需改动任何地图文件。
    """
    top = 0.0
    for part in obstacle_parts(ob):
        size = obstacle_size(part, part)
        top = max(top, float(part.get('z') or 0.0) + float(size[2]) / 2.0)
    return top


def obstacle_bbox_size(ob):
    """感知先验 / 地图栅格可表达的尺寸：单图元按 `_part_bbox_size`；复合模型取**包络盒**。

 `map_adapter` 的障碍模型是 OBB（只有 sx/sy/sz + yaw），无法表达圆柱 /
 球 / 多图元；故一律**降级为水平轴对齐包络矩形**（保守外扩，不缩小实体）。成文约定。
 （原 `air_perception` 同用此降级，已于 2026-11-06 随 `perception` 轴退役删除。）
    """
    if not is_composite(ob):
        return _part_bbox_size(ob)
    xs_min = ys_min = float('inf')
    xs_max = ys_max = float('-inf')
    z_max = 0.0
    for part in obstacle_parts(ob):
        hx, hy = _part_bbox_size(part)[0] / 2.0, _part_bbox_size(part)[1] / 2.0
        cx, cy = float(part['x']), float(part['y'])
        xs_min, xs_max = min(xs_min, cx - hx), max(xs_max, cx + hx)
        ys_min, ys_max = min(ys_min, cy - hy), max(ys_max, cy + hy)
        z_max = max(z_max, float(part['z']) + float(part['size'][2]) / 2.0)
    return [xs_max - xs_min, ys_max - ys_min, z_max]


def _part_geometry_sdf(part):
    """单图元 `<geometry>` 片段（视觉与碰撞同源）。"""
    size = obstacle_size(part, part)
    shape = obstacle_shape(part)
    if shape == 'cylinder':
        return '<cylinder><radius>%s</radius><length>%s</length></cylinder>' % (size[0], size[2])
    if shape == 'sphere':
        return '<sphere><radius>%s</radius></sphere>' % (size[0],)
    return '<box><size>%s %s %s</size></box>' % (size[0], size[1], size[2])


def obstacle_geometry_sdf(ob):
    """单图元实体 → `<geometry>` 片段（复合模型请用 `obstacle_part_geometry_sdf`）。"""
    if is_composite(ob):
        raise RuntimeError(
            '复合模型 %s 须逐 part 取几何（用 obstacle_part_geometry_sdf）→ 拒绝运行'
            % ob.get('id'))
    return _part_geometry_sdf(ob)


def obstacle_part_geometry_sdf(part):
    """复合模型中单个 part 的 `<geometry>` 片段（视觉与碰撞同源）。"""
    return _part_geometry_sdf(part)
