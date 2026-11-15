#!/usr/bin/env python3
"""一次性作者工具：生成 `src/agc_sim/config/maps/sparse_map.yaml`。

**产物 yaml 才是唯一来源**（ADR-0007 单一来源纪律）。本脚本只回答"这份 yaml 当初
怎么排出来的"，**不是**第二来源：核验器（`tests/check_sparse_map_layout.py`）读 yaml，
不读本脚本。默认**拒绝覆盖**已存在的 yaml（`--force` 才写）。

## 这张图为什么存在（ADR-0049）

`dense_map`（间距 2.645 m）在 [ADR-0041](../../docs/adr/0041-geometry-metadata-instances-and-risk-map.md#top)
的风险分档下对本车**几何上不可通行**：实测圆盘连通阈值 R ≤ 0.70 m，而本车
footprint 外接半径（含 margin）是 1.069 m、半对角 0.933 m。它的正确定位是
**高密度感知压力图 + 几何不可行负例** —— 用来证明规划器能**正确拒绝**无解地图。

本图是它的**正例对照**：障碍足够稀疏，保证本车在 0.5 m 规划层上**任意航向**都能
找到连通通道。

## 最小中心距的推导（不是拍的）

```text
D_center >= 2·r_vehicle + 2·r_inflation + δ_grid + δ_margin
```

| 项 | 值 | 依据 |
|---|---|---|
| `r_vehicle` | 0.933 m | `hypot(0.5037, 0.28545) + 0.3536`（半对角 + 半格量化） |
| `r_inflation` | 0.6 m | ADR-0041 的 `99` 环半径（`robot_radius`） |
| `δ_grid` | 0.5 m | 规划层格宽（max-pool 量化） |
| `δ_margin` | 0.2 m | 额外安全裕量 |

⇒ `D_center >= 2×0.933 + 2×0.6 + 0.5 + 0.2 = 3.765 m`。

取 **4.0 m** 而不是 3.765：留 0.235 m 余量吸收「任意航向」的离散误差
（外接圆 1.069 m 与半对角 0.933 m 之间还有 0.136 m 的航向依赖）。

**实际值不能只按公式拍定** —— `tests/check_sparse_map_layout.py` 会用真实几何核验：
真实 footprint 膨胀、0.5 m max-pool、任意航向、起点到目标连通性、最窄通道宽度。

## 与 dense_map 的对照

| 图 | 最小中心距 | 每道缝（扣 99 环 + 格宽） | 本车需 | 结论 |
|---|---|---|---|---|
| `dense_map` | 2.645 m | 0.85 m | 2.14 m | **不可通行**（负例） |
| `sparse_map` | 4.0 m | 2.30 m | 2.14 m | 可通行（正例） |

## 边界

* **不改 `dense_map` 的语义**：它是负例，不是"待修的图"。
* **不新增任何模式开关**：`sparse_map` 是一个**地图资产选择**（`world_map`），
  不是 `planner_mode` / `dense_map_mode` 之类的运行时路线分支
  （[路线分支治理](../docs/conventions/路线分支治理.md#rule) 明确「地图 / 模型文件选择」不算分支）。
"""

import argparse
import math
import os
import random

# 本文件位于 `scripts/maps/`，项目根在其上两层。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
OUT = os.path.join(ROOT, 'src', 'agc_sim', 'config', 'maps', 'sparse_map.yaml')

MAP_NAME = 'sparse_map'
CORE_HALF = 35.0          # 撒点区域半边长（70×70），与 dense_map 同区域便于对照
# 最小中心距（m）：见文件头的推导，公式给 3.765，取 4.0 留航向余量。
MIN_GAP = 4.0
SEED = 20261114           # 固定种子：随机 ≠ 不可复现
TARGET_OBSTACLES = 150    # 4.0 m 间距下 70×70 的可复现落点（实测上限约 153；150 仅需 6.8 万次尝试，留 83% 余量）
MAX_TRIES = 400000        # 拒绝采样上限（防死循环；取不到目标数就如实报错）
POCKET_R = 6.0            # 目标口袋半径（与 dense_map 同：d_track=3.0 的几何下界）
CAR_PAD = 2.0             # 车出生 pad
OWN_PAD = 1.5             # 己方机出生 pad

TARGET = (0.0, 0.0)
CAR = (-34.0, -6.0)
OWN = (-34.0, -2.0)

# 高度档（m）：全部 ≤ 3.0（与 dense_map 同，便于感知指标对照）
HEIGHTS = (0.6, 0.9, 1.2, 1.5, 1.8, 2.2, 2.6, 3.0)
BOX_W = (0.6, 0.8, 1.0, 1.2)
BOX_D = (0.6, 0.9, 1.2)
CYL_R = (0.25, 0.325, 0.40)
# 配色（同族一致、族间可辨；只影响视觉，不是几何）
PALETTE = (
    (0.62, 0.60, 0.56),   # 混凝土灰
    (0.72, 0.47, 0.22),   # 锈橙
    (0.24, 0.38, 0.55),   # 涂装蓝
    (0.55, 0.58, 0.62),   # 结构钢
    (0.76, 0.77, 0.75),   # 浅灰
)


def generate():
    rng = random.Random(SEED)
    placed = []          # (x, y, footprint_radius)

    def far_enough(x, y, r):
        for (px, py, pr) in placed:
            if math.hypot(x - px, y - py) < MIN_GAP + r + pr:
                return False
        # 目标口袋与两个出生位留空
        if math.hypot(x - TARGET[0], y - TARGET[1]) < POCKET_R + r:
            return False
        if math.hypot(x - CAR[0], y - CAR[1]) < CAR_PAD + r:
            return False
        if math.hypot(x - OWN[0], y - OWN[1]) < OWN_PAD + r:
            return False
        return True

    obstacles = []
    tries = 0
    while len(obstacles) < TARGET_OBSTACLES and tries < MAX_TRIES:
        tries += 1
        x = rng.uniform(-CORE_HALF, CORE_HALF)
        y = rng.uniform(-CORE_HALF, CORE_HALF)
        shape = rng.choice(('box', 'cylinder'))
        if shape == 'box':
            w = rng.choice(BOX_W)
            d = rng.choice(BOX_D)
            size = [w, d]
            radius = math.hypot(w, d) / 2.0
        else:
            r = rng.choice(CYL_R)
            size = [r, r]
            radius = r
        if not far_enough(x, y, radius):
            continue
        h = rng.choice(HEIGHTS)
        yaw = rng.uniform(-math.pi, math.pi)
        color = rng.choice(PALETTE)
        finish = rng.choice(('concrete', 'steel', 'paint'))
        obstacles.append({
            'id': '%s_%03d' % ('crate' if shape == 'box' else 'drum', len(obstacles)),
            'shape': shape,
            'x': round(x, 3),
            'y': round(y, 3),
            'z': round(h / 2.0, 3),
            'yaw': round(yaw, 4),
            'size': [round(size[0], 3), round(size[1], 3), round(h, 3)],
            'color': list(color),
            'finish': finish,
        })
        placed.append((x, y, radius))

    if len(obstacles) < TARGET_OBSTACLES:
        raise SystemExit(
            '只放到 %d / %d 个实体（尝试 %d 次）。间距 %.2f 下区域容量不足，'
            '应下调 TARGET_OBSTACLES 或扩大 CORE_HALF。'
            % (len(obstacles), TARGET_OBSTACLES, tries, MIN_GAP))

    h_max = max(o['size'][2] for o in obstacles)
    h_max_id = max(obstacles, key=lambda o: o['size'][2])['id']
    return obstacles, h_max, h_max_id, tries


def render(obstacles, h_max, h_max_id, tries):
    lines = []
    lines.append('# AGC 场景配置文件 · 地图 `%s`（**可通行**正例图）' % MAP_NAME)
    lines.append('#')
    lines.append('# 本文件由 `scripts/gen_sparse_map.py` 一次性生成；生成后**本文件即唯一来源**，')
    lines.append('# 核验器 `tests/check_sparse_map_layout.py` 只读本文件。')
    lines.append('# 人工改过之后不要再跑生成器（会覆盖）。')
    lines.append('#')
    lines.append('# ---- 用途（ADR-0049）----')
    lines.append('# `dense_map` 在 ADR-0041 风险分档下对本车**几何不可通行**（圆盘连通阈值')
    lines.append('# R ≤ 0.70 m，本车需 0.933 m）。它的正确定位是**高密度感知压力图 +')
    lines.append('# 几何不可行负例**。本图是它的正例对照：障碍足够稀疏，保证本车在 0.5 m')
    lines.append('# 规划层上**任意航向**都能找到连通通道。')
    lines.append('#')
    lines.append('# ---- 最小中心距的推导（不是拍的）----')
    lines.append('#   D_center >= 2*r_vehicle + 2*r_inflation + delta_grid + delta_margin')
    lines.append('#     r_vehicle   = hypot(0.5037, 0.28545) + 0.3536 = 0.933 m（半对角 + 半格量化）')
    lines.append('#     r_inflation = 0.6 m（ADR-0041 的 99 环半径）')
    lines.append('#     delta_grid  = 0.5 m（规划层格宽）')
    lines.append('#     delta_margin= 0.2 m（额外裕量）')
    lines.append('#   => D_center >= 3.765 m。取 **%.1f m** 留 0.235 m 吸收「任意航向」的离散误差。' % MIN_GAP)
    lines.append('#')
    lines.append('# ---- 与 dense_map 的对照 ----')
    lines.append('#   dense_map : 间距 2.645 m，每道缝（扣 99 环 + 格宽）0.85 m < 车需 2.14 m => 不可通行')
    lines.append('#   sparse_map: 间距 %.1f m，每道缝 %.2f m >= 车需 2.14 m => 可通行' % (
        MIN_GAP, MIN_GAP - 2 * 0.6 - 0.5))
    lines.append('#')
    lines.append('# ---- 生成参数（可复现）----')
    lines.append('#   种子 %d，目标实体数 %d，实际落点 %d，尝试 %d 次' % (
        SEED, TARGET_OBSTACLES, len(obstacles), tries))
    lines.append('#   撒点区 70×70 m（x,y ∈ [-35,35]），目标口袋 r=6 m，出生位 pad 车 2.0 / 机 1.5 m')
    lines.append('#   尺寸：box 0.6–1.2 m / cylinder r 0.25–0.40 m；高度 0.6–3.0 m（8 档）')
    lines.append('#')
    lines.append('# ---- 边界（不得误读）----')
    lines.append('# * **不改 dense_map 的语义**：它是负例，不是"待修的图"。')
    lines.append('# * **不新增任何模式开关**：`sparse_map` 是**地图资产选择**（`world_map`），')
    lines.append('#   不是 `planner_mode` / `dense_map_mode` 之类的运行时路线分支')
    lines.append('#   （路线分支治理：地图 / 模型文件选择不算分支）。')
    lines.append('')
    lines.append('map: %s' % MAP_NAME)
    lines.append('ground_style: plain')
    lines.append('work_area:')
    lines.append('  resolution: 0.5')
    lines.append('  size_x: 100.0')
    lines.append('  size_y: 100.0')
    lines.append('  origin_x: -50.0')
    lines.append('  origin_y: -50.0')
    lines.append('flight_altitude:')
    lines.append('  own_track_m: 14.0')
    lines.append('  own_takeoff_m: 14.0')
    lines.append('  target_cruise_m: 12.0')
    lines.append('  own_clearance_min_m: 0.5')
    lines.append('  derived:')
    lines.append('    h_max_map_m: %.2f' % h_max)
    lines.append('    h_max_map_id: %s' % h_max_id)
    lines.append('    h_max_env_m: %.2f' % h_max)
    lines.append('    h_max_env_id: %s' % h_max_id)
    lines.append('    rule_version: 1')
    lines.append('obstacles:')
    for o in obstacles:
        lines.append('  - id: %s' % o['id'])
        lines.append('    shape: %s' % o['shape'])
        lines.append('    x: %s' % o['x'])
        lines.append('    y: %s' % o['y'])
        lines.append('    z: %s' % o['z'])
        lines.append('    yaw: %s' % o['yaw'])
        lines.append('    size: [%s, %s, %s]' % tuple(o['size']))
        lines.append('    color: [%s, %s, %s]' % tuple(o['color']))
        lines.append('    finish: %s' % o['finish'])
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--force', action='store_true', help='覆盖已存在的 yaml')
    args = ap.parse_args()
    if os.path.exists(OUT) and not args.force:
        raise SystemExit(
            '%s 已存在。产物 yaml 是唯一来源，生成后人工改动不得被误跑覆盖；'
            '确需重生成请加 --force。' % OUT)
    obstacles, h_max, h_max_id, tries = generate()
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write(render(obstacles, h_max, h_max_id, tries))
    print('已生成 %s（%d 个实体，尝试 %d 次）' % (OUT, len(obstacles), tries))


if __name__ == '__main__':
    main()
