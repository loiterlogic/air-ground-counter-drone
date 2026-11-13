#!/usr/bin/env python3
"""一次性作者工具：生成 `src/agc_sim/config/maps/dense_map.yaml`。

**产物 yaml 才是唯一来源**（ADR-0007 单一来源纪律）。本脚本只回答"这份 yaml 当初怎么排出来的"，
**不是**第二来源：核验器（`tests/check_dense_map_layout.py`）读 yaml，不读本脚本。
默认**拒绝覆盖**已存在的 yaml（`--force` 才写）—— 生成后人工改过的内容不得被误跑覆盖。

布局范式（用户 2026-11-10 裁定，见 ADR-0037）：
 * 目标在作业区正中 (0,0)；车与己方机在西边缘；
 * **随机撒点**（用户原话「布局怎么这么规整，还是用 Fast-Planner 它这种随机生成吧」）——
   范式取自 `refs/Fast-Planner/uav_simulator/map_generator/src/random_forest_sensing.cpp`：
   `uniform_real_distribution` 撒点 + 最小间距拒绝采样。**只迁移范式，不抄资产/尺度**。
 * **固定种子**（`SEED`）：随机 ≠ 不可复现。同种子同输出，证据可复核。
 * 间距**两轮加宽**（都按"最近邻中位数再 +15%"落点，即下限 = 上一轮下限 × 1.15）：
   六角错排 2.0 m → ADR-0037 的 2.3 m → ADR-0044 的 **2.645 m**（现行，拒绝采样判据）。
 * 单件水平尺寸 0.6–1.2 m（box）/ r 0.25–0.40 m（cylinder），高度 0.6–3.0 m（**上限 3 m**）；
 * 目标口袋 r=6 m（`d_track=3.0` 的几何下界：车中心需能贴到距目标 3 m 且不撞）；
 * **不留走廊**：车沿直连 goal 会进入 `collision_monitor` 碰撞档，本图跟踪终态不可达（设计意图；
   用户 2026-11-12 再次裁定「不要走廊，后面会做路径规划」—— 通行靠规划，不靠地图开洞）。

> 历史：ADR-0007 曾否决"随机撒点做多样性"（判为伪多样性）。用户 2026-11-10 明确要求随机，
> 该否决在本图上被用户裁定推翻（ADR-0037）；**ADR-0007 的否决对其余地图仍然有效**。
"""

import argparse
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
OUT = os.path.join(ROOT, 'src', 'agc_sim', 'config', 'maps', 'dense_map.yaml')

MAP_NAME = 'dense_map'
CORE_HALF = 35.0          # 撒点区域半边长（70×70）—— 间距加宽后区域**不变**（用户 2026-11-12 裁定），
                          # 代价是实体数下降（gap=2.645 下 70×70 实测上限 490；见 ADR-0044）
# 最小间距（m）：上一轮下限 2.3 × 1.15（用户 2026-11-12「障碍物的间隔再增加 15%」）= 2.645
# （首轮 2.3 的来历见 ADR-0037：六角错排最近邻中位数 2.0 × 1.15）
MIN_GAP = 2.645
SEED = 20261110           # 固定种子：随机 ≠ 不可复现
TARGET_OBSTACLES = 486    # 目标实体数：间距加宽后 70×70 的可复现落点（490 需 36.8 万次尝试，
                          # 逼近 MAX_TRIES 且不可复现；486 仅需 22.4 万次，留 44% 余量）
MAX_TRIES = 400000        # 拒绝采样上限（防死循环；取不到目标数就如实报错）
POCKET_R = 6.0            # 目标口袋半径
CAR_PAD = 2.0             # 车出生小 pad（车在核心区外，实际不起作用，保留以防移动）
OWN_PAD = 1.5             # 己方机出生小 pad

TARGET = (0.0, 0.0)
CAR = (-34.0, -6.0)
OWN = (-34.0, -2.0)

# 高度档（m）：全部 ≤ 3.0（用户 2026-11-10 裁定「不要超过 3 m」）
HEIGHTS = (0.6, 0.9, 1.2, 1.5, 1.8, 2.2, 2.6, 3.0)
# box 水平尺寸档（m）
BOX_W = (0.6, 0.8, 1.0, 1.2)
BOX_D = (0.6, 0.9, 1.2)
# cylinder 半径档（m）
CYL_R = (0.25, 0.325, 0.40)
# 配色（同族一致、族间可辨；只影响视觉，不是几何）
PALETTE = (
    (0.62, 0.60, 0.56),   # 混凝土灰（料箱 / 料堆）
    (0.45, 0.52, 0.58),   # 冷灰蓝（料架）
    (0.58, 0.44, 0.30),   # 锈棕（旧箱）
    (0.52, 0.56, 0.44),   # 军绿（覆盖布）
    (0.66, 0.58, 0.34),   # 土黄（木托盘）
    (0.40, 0.42, 0.45),   # 深钢灰（金属件）
)


def _inside_pad(x, y, px, py, r):
    return math.hypot(x - px, y - py) <= r


def _footprint_r(shape, size):
    if shape == 'cylinder':
        return float(size[0])
    return math.hypot(float(size[0]), float(size[1])) / 2.0


def generate():
    """随机撒点 + 最小间距拒绝采样（Fast-Planner 范式；固定种子 ⇒ 可复现）。

 与 `random_forest_sensing.cpp` 的对应关系（只迁移范式）：
 * 它是 `uniform_real_distribution` 撒点 + 与已放置点/出生位做距离拒绝 —— 此处同构；
 * 它的最小间距由栅格分辨率隐式给出，此处显式取 `MIN_GAP`（用户「加宽 15%」的落点）；
 * 它按 `_obs_num` 定数量，此处按 `TARGET_OBSTACLES`（取不到即报错，不静默少放）。
    """
    rng = random.Random(SEED)
    placed = []          # [(x, y, radius)]，用于间距拒绝
    obstacles = []
    tries = 0
    while len(obstacles) < TARGET_OBSTACLES and tries < MAX_TRIES:
        tries += 1
        x = rng.uniform(-CORE_HALF, CORE_HALF)
        y = rng.uniform(-CORE_HALF, CORE_HALF)
        # 目标口袋 / 出生小 pad 一律留空（与上一版同口径）
        if _inside_pad(x, y, TARGET[0], TARGET[1], POCKET_R):
            continue
        if _inside_pad(x, y, CAR[0], CAR[1], CAR_PAD):
            continue
        if _inside_pad(x, y, OWN[0], OWN[1], OWN_PAD):
            continue
        # 先抽属性（间距判据要含半径：两个大件不能只按中心距判）
        h = rng.choice(HEIGHTS)
        yaw = rng.uniform(-math.pi, math.pi)
        color = rng.choice(PALETTE)
        if rng.random() < 0.15:
            shape = 'cylinder'
            r = rng.choice(CYL_R)
            size = [r, r, h]
        else:
            shape = 'box'
            size = [rng.choice(BOX_W), rng.choice(BOX_D), h]
        fr = _footprint_r(shape, size)
        # 最小间距：中心距 ≥ MIN_GAP（这是用户「加宽 15%」的判据，不含半径）
        if any(math.hypot(x - px, y - py) < MIN_GAP for px, py, _ in placed):
            continue
        # 额外：足迹不得相互穿插（保守外扩 —— 随机撒点比规则栅格更容易出现贴边）
        if any(math.hypot(x - px, y - py) < fr + pr + 0.05 for px, py, pr in placed):
            continue
        placed.append((x, y, fr))
        obstacles.append({
            'id': ('drum_%03d' % len(obstacles)) if shape == 'cylinder'
                  else ('crate_%03d' % len(obstacles)),
            'shape': shape,
            'x': round(x, 3), 'y': round(y, 3),
            'z': round(h / 2.0, 3), 'yaw': round(yaw, 4),
            'size': [round(v, 3) for v in size],
            'color': list(color),
            'finish': 'paint' if shape == 'cylinder' else 'concrete',
        })
    if len(obstacles) < TARGET_OBSTACLES:
        raise SystemExit(
            '只放下 %d/%d 个实体（%d 次尝试）—— 请调小 MIN_GAP 或目标数，'
            '不得静默少放（那会让"高密度"名不副实）'
            % (len(obstacles), TARGET_OBSTACLES, tries))
    return obstacles


def z_top(ob):
    return float(ob['z']) + float(ob['size'][2]) / 2.0


def footprint_r(ob):
    if ob['shape'] in ('cylinder', 'sphere'):
        return float(ob['size'][0])
    return math.hypot(float(ob['size'][0]), float(ob['size'][1])) / 2.0


def derived_altitude(obstacles, safe_max):
    """按 `height_survey` 同口径算 h_max_map / h_max_env（包络 = 目标 ⊕ safe_max）。"""
    top = max(obstacles, key=z_top)
    env = [o for o in obstacles
           if math.hypot(float(o['x']) - TARGET[0], float(o['y']) - TARGET[1])
           - footprint_r(o) <= safe_max]
    env_top = max(env, key=z_top) if env else top
    return top, env_top


HEADER = """\
# AGC 场景配置文件 · 地图 `dense_map`（小障碍高密度能力图）
#
# 本文件受 `world_geometry.yaml` 头部 schema 与纪律约束；此处只记**本图专属**意图与边界。
# **本文件由 `scripts/gen_dense_map.py` 一次性生成**；生成后**本文件即唯一来源**，
# 核验器 `tests/check_dense_map_layout.py` 只读本文件。人工改过之后不要再跑生成器（会覆盖）。
#
# ---- 用途（用户 2026-11-10 裁定）----
# **感知与地面规划**的能力/实验图，**不是**演示主地图（演示主地图仍是 `yard`）。
# 定位：ADR-0035「实验 D（不同地图验证感知指标）」的承载图；同时压测地面 `collision_monitor`
# 在密排小件下的行为。
#
# ---- 与无人机无关（用户原话「跟无人机没关系，无人机还是飞14m」）----
# 己方机仍飞 14 m、目标 12 m（与 `yard` 同档，使两图感知指标可直接对照）。
# **几何后果（必须如实登记）**：本图全部构件顶面 ≤ 3.0 m，而空中安全层的**垂直门控**
# （ADR-0010(j)）在 `z_gate ≥ z_top + c_clear` 时移除该障碍的二维圆盘；
# 14 m ≥ 3.0 + 0.5 ⇒ **本图全部障碍对空中安全层透明**。故本图**不提供**空中避障证据，
# 也不用于证伪"环带不可行"（判据见核查 (i) 的双口径登记）。
#
# ---- 布局（世界 ENU，m；ADR-0037 范式 / ADR-0044 现行间距）----
# 目标 (0,0) 在作业区正中；车 (-34,-6)、己方机 (-34,-2) 在西边缘（车↔机 4.0 m）。
# **随机撒点**（用户 2026-11-10：「布局怎么这么规整，还是用 Fast-Planner 它这种随机生成吧」）：
# 范式取自 `refs/Fast-Planner/.../random_forest_sensing.cpp`（均匀撒点 + 距离拒绝），
# **只迁移范式不抄资产**；固定种子 `SEED` ⇒ 同种子同输出，证据可复核。
# 撒点区 **70×70 m**（x,y ∈ [-35,35]）：**区域不变**（用户 2026-11-12 裁定），间距再 +15%
# （2.3 → **2.645 m** 最小间距）后，70×70 实测只能复现 **486** 个（间距与数量不能同时保住，
# 这是面积约束，不是取舍偏好 —— 见 ADR-0044 的容量表）。
# 目标口袋 **r=6 m** 留空（`d_track=3.0` 的几何下界：车中心须能贴到距目标 3 m 且不撞）。
# **不留走廊**：车沿直连 goal 行进会进入 `collision_monitor` 碰撞档（2.0 m）
# ⇒ 本图跟踪终态**不可达**（`expected_terminal: MISSION_FAILED`），这是**设计意图**
# （用户 2026-11-12 复述裁定：「不要走廊，后面会做路径规划」—— 通行由规划器解决，地图不开洞）。
#
# ---- 尺度与密度（用户 2026-11-10 裁定「不要超过 3 m」= 高度上限）----
# box 水平尺寸 0.6–1.2 m；cylinder r 0.25–0.40 m；高度 0.6–3.0 m（8 档，**上限 3.0 m**）。
# 属性（尺寸 / 高度 / 朝向 / 配色 / 形状）全部**随机抽取**，与位置同源。
# ⚠ ADR-0007 曾否决"随机撒点做多样性"；用户 2026-11-10 明确要求随机，
# 该否决**在本图上**被用户裁定推翻（ADR-0037），对其余地图仍然有效。
# 实测值一律跑核验器读 JSON，本文**不写**实体数 / 覆盖率（那是随时漂移的实测值）。
#
# ---- 为什么不做精致（用户原话「不需要做的太精致」）----
# 单图元、**无 `parts`**、材质只 2 档（concrete / paint）、无窗带 / 勒脚 / 屋面细部、
# 不改地面分层。代价：本图**不能**当视觉保真证据（那是 `yard` 的职责）。
#
# ---- 已知限制（如实登记，不假装能力）----
# * 全部构件 ≤ 3.0 m ⇒ 对空中安全层透明（见上）；本图**不**测空中避障。
# * 密集区覆盖 8 字轨迹足迹（`traj.rx=15 / ry=9 / center=(0,0)`）⇒ **8 字净空为负**。
#   本图**不**用于流程验证的预设轨迹场景（反无人机场景本就禁用预设轨迹，ADR-0008）。
#   负值只表示名义参考轨迹压到静态圆盘，**不**证明运行期必然失败。
# * 无贴图 / 无 mesh（不引入外部资产）⇒ 材质只有标量 PBR + 纯色。
"""


def render(obstacles, h_max_map, h_max_env):
    lines = [HEADER]
    lines.append('map: %s\n' % MAP_NAME)
    lines.append(
        '# ---- 地面样式（ADR-0037）----\n'
        '# `plain` = 剥离 base world 的地表分层（沥青环路 / 场坪 / 路缘石 / 车位线 / 排水沟 /\n'
        '# 碎石带 / 绿化带），只留基层 `ground_plane` 纯色。用户 2026-11-10：\n'
        '# 「地板怎么是s18的，不需要，换成纯色就行」。\n'
        '# **纯视觉**：地表装饰本就不进障碍几何 / 空中安全层 / 占位栅格。\n'
        '# 缺省（不写）= `layered`，即 `yard` / `minimal` / `open_field` 的现有外观逐字不变。\n'
        'ground_style: plain\n')
    lines.append(
        'work_area:\n'
        '  resolution: 0.5\n'
        '  size_x: 100.0\n'
        '  size_y: 100.0\n'
        '  origin_x: -50.0\n'
        '  origin_y: -50.0\n')
    lines.append(
        '# ---- 飞行高度（ADR-0007；高度随地图声明）----\n'
        '# 与 `yard` **同档**（己方 14 / 目标 12 / c_clear 0.5），使两图的感知指标可直接对照；\n'
        '# 用户 2026-11-10：「跟无人机没关系，无人机还是飞14m」。\n'
        '# 注意：14 m 远高于本图最高构件 3.0 m ⇒ 全部障碍被垂直门控移除（见文件头）。\n'
        'flight_altitude:\n'
        '  own_track_m: 14.0\n'
        '  own_takeoff_m: 14.0\n'
        '  target_cruise_m: 12.0\n'
        '  own_clearance_min_m: 0.5\n'
        '  derived:\n'
        '    h_max_map_m: %.2f\n'
        '    h_max_map_id: %s\n'
        '    h_max_env_m: %.2f\n'
        '    h_max_env_id: %s\n'
        '    rule_version: 1\n' % (
            z_top(h_max_map), h_max_map['id'],
            z_top(h_max_env), h_max_env['id']))
    lines.append('\nobstacles:')
    for ob in obstacles:
        lines.append(
            '  - id: %s\n'
            '    shape: %s\n'
            '    x: %s\n'
            '    y: %s\n'
            '    z: %s\n'
            '    yaw: %s\n'
            '    size: [%s, %s, %s]\n'
            '    color: [%s, %s, %s]\n'
            '    finish: %s' % (
                ob['id'], ob['shape'], ob['x'], ob['y'], ob['z'], ob['yaw'],
                ob['size'][0], ob['size'][1], ob['size'][2],
                ob['color'][0], ob['color'][1], ob['color'][2], ob['finish']))
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--force', action='store_true',
                    help='允许覆盖已存在的 yaml（默认拒绝：生成后 yaml 即唯一来源，'
                         '人工改过的内容不得被误跑覆盖）')
    args = ap.parse_args()
    if os.path.exists(args.out) and not args.force:
        raise SystemExit(
            '拒绝覆盖已存在的 %s —— 生成后 yaml 即唯一来源（ADR-0036）；\n'
            '确要按本脚本重新生成，请显式加 --force（会丢弃对该 yaml 的人工修改）。'
            % args.out)
    obstacles = generate()
    # `safe_max` 从 air.yaml 读（安全参数，不写死在生成器里）
    import yaml
    air = yaml.safe_load(open(os.path.join(
        ROOT, 'src', 'agc_air', 'config', 'air.yaml'), encoding='utf-8'))
    safe_max = float(air['standoff_follower']['ros__parameters']['safe_max'])
    h_max_map, h_max_env = derived_altitude(obstacles, safe_max)
    text = render(obstacles, h_max_map, h_max_env)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text)
    print('wrote %s (%d obstacles, %d lines)' % (args.out, len(obstacles),
                                                 text.count('\n')))


if __name__ == '__main__':
    main()
