<a id="top"></a>
# 地图几何的两极：`sparse_map` 作可通行正例，`dense_map` 作几何不可行负例

## Status

accepted（2026-11-14，用户裁定）

> **不改 `dense_map` 的语义**：[ADR-0037](0037-dense-map-random-layout-and-plain-ground.md#top) 的随机撒点范式、
> [ADR-0044](0044-dense-map-second-gap-widening.md#top) 的 2.645 m 间距、[ADR-0041](0041-geometry-metadata-instances-and-risk-map.md#top)
> 的风险分档**全部不变**。本篇只回答"`dense_map` 到底能证明什么"以及"缺的那一半由谁补"。
>
> **不新增任何模式开关**：`sparse_map` 是**地图资产选择**（`world_map` 参数），
> 不是 `planner_mode` / `dense_map_mode` 之类的运行时路线分支
> （[路线分支治理](../conventions/路线分支治理.md#rule) 明确「地图 / 模型文件选择」不算分支）。

## 背景

[ADR-0048](0048-ground-hybrid-astar-se2-planner.md#top) 落地地面全局规划器后，`dense_map` 上的实测
暴露了一个**地图与车体几何的矛盾**，且它无法通过调规划器解决：

```text
dense_map 最小障碍中心距 = 2.646 m（ADR-0044）
ADR-0041 的 99 环每侧 0.6 m ⇒ 每道缝被吃掉 1.2 m
剩余自由带 0.25–0.85 m，而本车需要 0.93 m（半对角 + margin）
0.5 m max-pool 再量化掉剩余部分
```

圆盘连通性扫描（0.5 m 规划层，4 连通）：

| 圆盘半径 | 能否从车位到目标 |
|---|---|
| ≤ 0.70 m | 能 |
| ≥ 0.80 m | **不能** |

本车需要 0.93 m ⇒ **`dense_map` 在当前 band 语义下对本车不可通行**。

这与 [ADR-0047](0047-directional-safety-tier-semantics.md#top) 已登记的事实一致：
「0.5 m 规划层分辨不了 < 1.5 m 的缝」，用户裁定的验收下限是「≥ 1.5 m 间隙」，
而 `dense_map` 的最小缝在扣掉 99 环后是 0.246 m。

**问题**：规划器的出口判据要求「`dense_map` 多障碍绕行」的整链证据 ——
在该图当前语义下**不可能**。而且如果只有 `dense_map` 一张能力图，
规划器"失败"与"规划器坏了"无法区分。

## 决策

### (a) `dense_map` 的定位收窄为**高密度感知压力图 + 几何不可行负例**

它的价值不是"证明车能过"，而是：

1. **感知压力**：486 个小障碍、面积覆盖 7.2%，压测感知的漏检/误覆盖/稳定性（ADR-0040–0044 的全部指标在这张图上量）；
2. **负例**：证明规划器在**几何不可行**的地图上**正确拒绝**而不是硬凑一条穿障路径。

规划器在 `dense_map` 上失败是**正确行为**，不得记为缺陷。

### (b) 新增 `sparse_map` 作**可通行正例**

`src/agc_sim/config/maps/sparse_map.yaml`，由 `scripts/maps/gen_sparse_map.py` 一次性生成
（固定种子 `20261114`，产物 yaml 是唯一来源）。

与 `dense_map` 的**唯一变量是障碍密度**：同 100×100 m 作业区、同目标 `(0,0)`、
同出生位 `车 (-34,-6) / 己方机 (-34,-2)`、同构件尺寸与高度档。

### (c) 最小中心距**按公式推导**，不靠"看着挺空"

```text
D_center >= 2·r_vehicle + 2·r_inflation + δ_grid + δ_margin
```

| 项 | 值 | 依据 |
|---|---|---|
| `r_vehicle` | 0.933 m | `hypot(0.5037, 0.28545) + 0.3536`（半对角 + 半格量化） |
| `r_inflation` | 0.6 m | ADR-0041 的 `99` 环半径 |
| `δ_grid` | 0.5 m | 规划层格宽（max-pool 量化） |
| `δ_margin` | 0.2 m | 额外安全裕量 |

⇒ `D_center >= 3.765 m`。**取 4.0 m**，留 0.235 m 吸收「任意航向」的离散误差
（外接圆 1.069 m 与半对角 0.933 m 之间还有 0.136 m 的航向依赖）。

实际落点：150 个实体，实测最小中心距 **4.516 m**（> 3.765 m）。

### (d) 用**核验器**而非公式拍定实际值

`tests/check_sparse_map_layout.py`，7 项机械判据：

| # | 判据 | 实测 |
|---|---|---|
| a | 最小中心距 ≥ 公式下限 | 4.516 m ≥ 3.765 m ✓ |
| a2 | `dense_map` 更紧（负例对照仍成立） | 2.646 m < 3.765 m ✓ |
| b | 真实 footprint 膨胀后可放置 | 8420 个格点（半径 0.933 m）✓ |
| c | **任意航向**：≥12/16 航向可放 | 7974/8420 ✓ |
| d | 起点→目标连通（4 连通圆盘 BFS） | 可达，访问 7625 格 ✓ |
| d2 | `dense_map` 同判据**不可达** | 不可达 ✓ |
| e | 最窄通道宽度 ≥ 车需 | 2.50 m ≥ 1.87 m ✓ |

判据 d2 是关键：**同一套判据**下 `sparse_map` 通、`dense_map` 不通 ——
这证明两者确实构成正/负对照，而不是"一个松一个紧"。

### (e) 场景：`sparse_scene` 与 `dense_scene` 成对

`sparse_scene`（`world_map: sparse_map`）与 `dense_scene`（`world_map: dense_map`）
**逐值相同**的出生位与任务参数，唯一变量是障碍密度。

两者的 `expected_terminal` 当前都是 `MISSION_FAILED / TIMEOUT`。

### (f) 整链实测结果（2026-11-14，`sparse_scene`，`backend:=full`，GUI）

**结论：`TRACKING_SUCCESS`**（车从 34.2 m 推进到 **2.9 m**，`collision_count = 0`）。

| 项 | 实测 |
|---|---|
| 终态 | **`TRACKING_SUCCESS`**（`terminal_reason_code = tracking_milestone`，已锁存） |
| 车距目标 | 34.2 m → **2.9 m** |
| 规划成功 | **53 次**（31.6–33.9 m 路径，曲率 0.184–0.389，离障 0.25 m，搜索 1.2–1.5 万节点） |
| 规划失败 | 9 次：`start_not_free`×4 / `goal_collision`×2 / `goal_not_free`×2 / `dynamics_infeasible`×1（全在启动期与瞬时状态） |
| 碰撞 | `collision_count = 0` |
| 安全层 | 有 `SLOW` / `STOP_COLLISION` 转换，**未绕过** |
| 地图 | 健康（263/268 帧有障碍，峰值 749 格） |

**必须同时登记的一次失败（同一场景，更早的一轮）**：在 `t_max_s = 120` 下实测为
`MISSION_FAILED / TIMEOUT`，车只推进 3.4 m。原因是**任务时限不足**，不是规划器或地图问题：
车在等目标进入感知覆盖（目标是 `(0,0)`，己方机出生距它 34.1 m，可信半径 29.4 m），
期间目标格 unknown ⇒ 规划器按「未知禁入」正确失败并停车。放宽时限后即到达。

**如实解读（不得夸大）**：

- 这一轮证明了「规划器 → `/agc/ground/path` → 既有消费者 → 车」整链**真的跑通了**，
  且车**实际绕过 `sparse_map` 的障碍**到达跟踪圈；
- **不得**据此宣称「`dense_map` 也能过」（两者几何不同，`dense_map` 仍是负例）；
- **不得**据此宣称感知能力提升：`sparse_map` 只有 150 个障碍，感知压力远低于 `dense_map`；
- `sparse_scene` 的 `expected_terminal` 仍是 `MISSION_FAILED`（未改），
  但**实测终态是 `TRACKING_SUCCESS`** ⇒ 与期望**不一致**。这是一个**待裁定项**（未决 #1）：
  改期望值还是保留，属独立决策，不在本篇自行改。

## 不做什么

- **不改 `dense_map` 的间距 / band 语义**让它"变得可通行"。它是负例，不是待修的图。
- **不新增 `dense_map_mode` / `planner_mode` 等运行时开关**。
- **不为了 `sparse_map` 通过而放宽核验器判据**（如把「任意航向」从 12/16 降到 6/16）。
- **不把 `sparse_map` 的通过读成"`dense_map` 也能过"**：两者是不同几何。
- **不在 `sparse_map` 上宣称感知能力**：它只有 150 个障碍，感知压力远低于 `dense_map`。

## Considered Options

- **调 `dense_map` 的间距到 4.0 m** —— 被否：会推翻 ADR-0044（用户 2026-11-12 裁定的 2.645 m），
  且失去高密度感知压力图的用途。一张图不能同时承担"高密度感知"与"可通行规划"。
- **调 `dense_map` 的 band 语义（`99` 环缩到 0.3 m）** —— 被否：`99` 是 ADR-0041 的安全膨胀，
  缩它会改变安全语义；且会推翻 ADR-0047 的方向化定档结论。
- **接受"规划器只在 `yard` 上取证"** —— 被否：`yard` 主场景车位到目标 12.5 m 直线上
  **没有任何障碍**，测不到绕障；`s19` 的 goal 在感知覆盖外（39.8 m > 28.28 m）。
- **放宽「顶层脚本 ≤ 12」的上限来放 `gen_sparse_map.py`** —— 被否：该上限是防平铺护栏，
  每加一个就提一次等于取消护栏。改为归入 `scripts/maps/`。
- **把生成器放 `scripts/archive/`** —— 被否：它仍是长期作者工具（与 `gen_dense_map.py` 同级），
  放 archive 等于宣称退役。

## Consequences

### 正面

- 规划器有了**正/负双向证据**：`sparse_map` 必须成功（34.20 m 绕障路径，曲率 0.45），
  `dense_map` 必须显式失败。两者一起排除了"一律失败"与"一律成功"两种退化。
- 最小中心距第一次是**推导出来的**（3.765 m）而不是试出来的，且有核验器守它。
- `dense_map` 的定位被收窄到它真正能证明的东西，不再被误读成"通行能力图"。

### 代价 / 限制（如实登记，不得据此宣称能力）

- **`sparse_map` 不是 `dense_map` 的替代**：它的感知压力只有 150 个障碍，
  不能用于 ADR-0040–0044 的任何感知指标。
- **两张图的整链终态都还是 `MISSION_FAILED`**：`sparse_map` 的规划器离线可达，
  但整链到达受感知覆盖限制（目标距己方机 34.06 m > 可信半径 28.28 m）。
- **`sparse_map` 的"任意航向"判据是 12/16 而非 16/16**：留了 4 个航向的余量，
  因为外接圆口径（1.069 m）比半对角（0.933 m）保守 —— 真实车体不是圆盘。
- **`gen_dense_map.py` 仍在 `scripts/` 顶层**（历史遗留），未随本次迁移；
  将来若再加地图工具应一并迁入 `scripts/maps/`。

### 未决（不得靠默认值掩盖）

| # | 未决项 | 归宿 |
|---|---|---|
| 1 | `sparse_scene` 的 `expected_terminal` 何时改为 `TRACKING_SUCCESS` | **已实测到达**（见 (f)），但改期望值是独立裁定，本篇不改；现状是「实测 `TRACKING_SUCCESS` / 期望 `MISSION_FAILED`」不一致 |
| 2 | 是否把 `gen_dense_map.py` 迁入 `scripts/maps/` | 下次动脚本目录时一并处理 |
| 3 | 是否需要一张"目标在感知覆盖内 + 路径有障碍"的专用整链场景 | 若 `sparse_scene` 整链仍不可达，需新决策 |

## 参考

- 地图几何：[ADR-0007](0007-scene-geometry-single-source-and-layout.md#top)（单一真源）、
  [ADR-0036](0036-dense-obstacle-map-and-per-map-spawn.md#top)（按地图派生出生位）、
  [ADR-0037](0037-dense-map-random-layout-and-plain-ground.md#top)（随机撒点范式）、
  [ADR-0044](0044-dense-map-second-gap-widening.md#top)（`dense_map` 间距）
- 规划与安全：[ADR-0041](0041-geometry-metadata-instances-and-risk-map.md#top)（风险分档与 `99` 环）、
  [ADR-0047](0047-directional-safety-tier-semantics.md#top)（0.5 m 层分辨不了 < 1.5 m 的缝）、
  [ADR-0048](0048-ground-hybrid-astar-se2-planner.md#top)（规划器与它的走廊判据）
- 规范：[路线分支治理](../conventions/路线分支治理.md#rule)、
  [测试分层与可测性](../conventions/测试分层与可测性.md#layers)
- 生成器：`scripts/maps/gen_sparse_map.py`（本图的作者工具）
- 核验器：`tests/check_sparse_map_layout.py`（7 项机械判据）
