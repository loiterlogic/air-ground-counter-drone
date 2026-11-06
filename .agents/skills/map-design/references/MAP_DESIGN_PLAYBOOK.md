# 地图设计与实现 · 技术流程参考（Playbook）

<a id="migrated"></a>
> **迁移说明（2026-10-31，任务 `20261031-015-map-design-skill`）**：本文件是仓库根目录
> `MAP_DESIGN_PLAYBOOK.md` 的**内容快照**，已迁入 map-design 技能的按需资源，根目录不再保留副本。
> 迁移时**只做两处改动**：① 相对链接前缀改为本文件所在深度（`../../../../`），目标文件不变；
> ② 增加本段说明。**正文一字未改**，包括文中"本文暂放根目录…应迁走"的位置说明——
> 那是迁移**之前**的状态，保留它是为了不伪造历史（[ADR-0002](../../../../docs/adr/0002-docs-source-of-truth-and-reference-discipline.md#top)）。
>
> **它是历史快照，不是现行约束**：文中所有数字（实体数 / 覆盖率 / 净空 / 内存占用）都是
> **当时**的实测值，会漂移；现行值一律跑 `python3 tests/check_scene_geometry.py` 读 JSON。
> 现行流程见 [SKILL.md](../SKILL.md)，闸门口径见 [GATES.md](../GATES.md)，
> schema 与派生链见 [SCHEMA-AND-DERIVATION.md](../SCHEMA-AND-DERIVATION.md)，
> 取证纪律见 [EVIDENCE.md](../EVIDENCE.md)。
> 约束仍只引用[契约真源](../../../../docs/adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints)。

> **这是什么**：AGC 项目「场景地图」从零到当前形态的**完整技术流程**，含三轮演化的决策史、
> 可复用的操作步骤、实测闸门数值、以及踩过的坑。**目的是被改写成技能**（`.agents/skills/<name>/SKILL.md`），
> 不是约束、不是真源。
>
> **不是真源**：几何 schema 的唯一出口是 [`world_map.py`](../../../../src/agc_sim/launch/world_map.py)，
> 派生链纪律见 [ADR-0007](../../../../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)，
> 布局范式见 [ADR-0007](../../../../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)，
> 进度口径见 [当前方向](../../../../docs/plan/README.md#plan-index)。本文**只引用不复述**约束。
>
> **位置说明**：按 [目录与命名规范](../../../../docs/conventions/目录与命名规范.md#10-产物分类与生命周期)，
> 项目级可复用 Agent 资产的家是 `.agents/skills/<name>/SKILL.md`；本文暂放根目录是为了先成型，
> **改写成技能后应迁走**，避免根目录出现第二个入口。

---

<a id="toc"></a>
## 目录

1. [一张图看懂架构](#arch)
2. [三轮演化时间线](#timeline)
3. [流程：八个步骤](#pipeline)
4. [第 1 步 · 先学后做](#learn)
5. [第 2 步 · 先设计后动手](#design)
6. [第 3 步 · 布局范式](#paradigm)
7. [第 4 步 · 几何可行性闸门](#gates)
8. [第 5 步 · 表达同一份几何（schema）](#schema)
9. [第 6 步 · 视觉保真](#visual)
10. [第 7 步 · 派生链落地](#derive)
11. [第 8 步 · 核查](#verify)
12. [已知限制与坑](#traps)
13. [本次发现的文档漂移（待修）](#drift)
14. [起跑命令与运行陷阱](#run)
15. [下一轮方向（已定方案）](#next)

---

<a id="arch"></a>
## 1. 一张图看懂架构

几何**只有一个家**，其余全部派生（[ADR-0007](../../../../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)）：

```text
world_geometry.yaml ← minimal（核查基线，pole 双柱，几何逐值不变）
maps/yard.yaml ← 演示主地图（36 实体 / 100×100 工业场站）
maps/open_field.yaml ← 能力对照 / 快跑（5 实体，故意稀疏）
        │
        │ ← 三者的路径表**只在** world_map.py 写一次（MAP_GEOMETRY_FILES）
        │ 未知地图名一律拒绝运行，不静默回退
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │ world_map.py（只做路径与形状规范化，253 行，可单测） │
  └─────────────────────────────────────────────────────────┘
        │
        ├─→ world_bringup._inject_static_obstacles
        │ → 运行期 SDF（把 obstacle 块注入 base world 的 </world> 前）
        │ → GZ 物理世界（collision 与 visual **同一 geometry 片段**）
        │
        ├─→ composition.write_derived_obstacles → 感知障碍先验
        ├─→ composition.write_derived_map → 感知 OccupancyGrid 几何
        ├─→ composition.apply_air_geometry → 空中安全圆盘列表
        └─→ composition.compose_params → scenario_reset 校验用几何
```

**三条铁律**：

1. **改地图 = 改一份 yaml**；碰 SDF 就是错的（唯一例外：地面分层这类**非障碍**的纯视觉层）。
2. **视觉与碰撞同源** —— 同一个 `<geometry>` 注入 collision 与 visual，禁止装饰性无碰撞块
   （否则出现"看着撞了却穿过去"的演示事故）。
3. **每改一次真源，立刻跑核查**（[`tests/check_scene_geometry.py`](../../../../tests/check_scene_geometry.py)）。

---

<a id="timeline"></a>
## 2. 三轮演化时间线

理解"为什么现在是这样"，比读最终文件更重要。

| 轮 | 触发（用户原话） | 实质变化 | 规模 |
|---|---|---|---|
| **R1–R2**<br>80×80 定形 | 「当前地图太过空旷简单，只有两个生成的障碍物」<br>→「不够精致…只能做简单形状吗」 | 从 2 根柱子 → 多实体；**能力扩展**：`sphere` 图元 + `parts` 复合模型；关 GUI 网格 | 19 实体 / 44 图元 / 11 复合体 / 9 小型件 |
| **R4**<br>100×100 重做 | 「80\*80 可能不太够，改成 100\*100，重新布局…样式要考虑现实世界中正常情况下是怎么分布的，先学习别人怎么做，**一定先设计好大致分布再动手**」 | 作业区 ×1.56；按**现实场站范式**整体重做（分区 + 对齐 + 留白 + 长尾）；**覆盖口径成文为并集**；新增断言 (p) 三图一致 | 29 实体 / 107 图元 / 27 复合 / 13 小型件 |
| **R5**<br>视觉保真 | 「建筑和地面精细度不高…材质改变，颜色分配优化。二是小型物体现在有点少，略微增加不要过分密集。学习本地能看的就行，**依旧设计好了再动手**」 | 材质档 `finish`（标量 PBR）+ 配色分族 + 建筑细部 + **地面三层**（基层/沥青/场坪）+ 小型件 +7 | **36 实体 / 186 图元 / 34 复合 / 19 小型件** |
| **R6**<br>区分度与呈现<br>（2026-10-30，**已实施**） | 「还有什么可优化的方向…建筑物和地面的区分度还是有点低」→ 依次裁定：明度分层 / 屋顶优化 / 地面语义层 / 尺度参照物 / **只做贴图** / **GUI 纯场景 + RViz 叠加**；**不采纳**阴影强化 | 屋面重做（檐+下沉金属屋面+屋脊/天窗/设备）、地面压暗 + 语义层、+6 个可碰撞参照物、程序化地面贴图、RViz 语义层 | **42 实体 / 234 图元 / 覆盖 11.48%** |

**演化里的三个方法论转折**（这才是可复用的部分）：

1. **R4 起，"先设计后动手"从不自觉变成硬流程**：先写**只读设计核验器**迭代候选布局，
   全闸门通过后才写真源。R4 迭代 5 版（v1 的 8 字净空是 **−2.04 m**，FAIL）。
2. **R4 起，覆盖口径从"图元和"改成"并集"**：同一实体多图元堆叠在"图元和"里被重复计数，
   不是真实占地。旧文档的 `7.36%` 因此作废（既非并集也非图元和）。
3. **R5 起，"取证只用本机"**：用户明确「网页看不了就不看了，学习本地能看的就行」。
   决定性依据来自本机 sdformat 的 `material.sdf`，而非网上教程。

---

<a id="pipeline"></a>
## 3. 流程：八个步骤

```text
① 先学后做 → 查本机同版本可运行实现，得出可迁移的范式
② 先设计后动手 → 写只读设计核验器，迭代到全闸门通过（不要先改 yaml）
③ 布局范式 → 功能分区 + 网格对齐 + 道路留白 + 尺寸长尾 + 中央留空
④ 几何闸门 → 7 项判据逐项核过（8 字净空 / 环带 // 重叠 / 可见性 / 覆盖 / 实体内涵）
⑤ schema 表达 → 用统一 schema 写出同一份几何（box/cylinder/sphere + parts + finish）
⑥ 视觉保真 → 材质档 / 配色分族 / 建筑细部 / 地面分层（只改视觉，不改判据）
⑦ 派生链落地 → 改 yaml 后确认 5 条派生路径全部跟上
⑧ 核查 → w6_geometry_check 三图 PASS，否则不提交
```

**顺序不可交换**：③ 会改变 ④ 的结果，⑤ 只是把 ③ 写下来。跳过 ② 直接写 yaml 是本项目历史上
返工最贵的一步（R4 的 v1 就 FAIL 了 8 字净空）。

---

<a id="learn"></a>
## 4. 第 1 步 · 先学后做

项目铁律规定的取证优先顺序，**从本机开始**：

| 优先级 | 来源 | 本项目实际用到的 |
|---|---|---|
| ① 本机同版本可运行实现 | `nav2_minimal_tb4_sim/worlds/warehouse.sdf`（GZ Sim 8，同引擎） | **分布范式**：26 个 include，货架成排对齐（yaw 只有 0 / 1.57）、隔离墩成列同 x、小件成组贴功能区 → "网格对齐 + 功能聚集"，**不是均匀撒点** |
| ② ROS2 社区 / 官方文档 | PX4 官方世界 `baylands.sdf` | **`<gui><plugin MinimalScene><camera_pose>` 固定相机写法**（可复现截图） |
| ③ 外部搜索 | — | 用户裁定不用（"网页看不了就不看了"） |

**另外两个关键取证（都在本机）**：

- **sdformat 1.11 `material.sdf`**：`<pbr><metal>` 的 `<metalness>` / `<roughness>` 是**标量**字段
  （默认 0.5），**不需要贴图** → 证明"改材质"与"不引入外部资产"不冲突。这是 R5 能做的根本原因。
- **`gz sdf -p <world>`**：落地前先让解析器验一遍，比在 GUI 里看报错快得多。

**结论的迁移方式**：学**范式**，不抄**资产**。Nav2 warehouse 是室内 28×45 m 仓库，
与本项目室外 100×100 场站不同；能迁移的是"分区 + 对齐 + 留白 + 长尾"。

---

<a id="design"></a>
## 5. 第 2 步 · 先设计后动手

### 5.1 设计核验器（harness）

**做法**：写一个只读脚本，**复刻正式核查的口径**，对候选布局算全部闸门，迭代到全绿再写真源。

复刻的口径清单（必须与 [`check_scene_geometry.py`](../../../../tests/check_scene_geometry.py) **逐项一致**，
否则你在假绿上做设计）：

```text
安全盘半径 = safety_radius + obstacle_margin(2.5) + extra(0.7)
  extra = reaction_time_s(0.2) × max_speed_mps(2.0) + reachability_margin(0.3) = 0.7
待机环带半径 = target_min_dist(8.0) + target_margin(1.5) + extra(0.7) = 10.2
8 字轨迹 = rx 15.0 / ry 9.0 / h 2.5（契约，**不改**）
出生净空 = 逐图元足迹距离（**不是**实体中心距离）
实体重叠 = 逐图元 SAT（**不是**包围盒相交）
可见性 = 每个实体在 z = 0.48 处有水平截面
覆盖率 = 并集投影面积 / 作业区面积，栅格 res = 0.2 m
```

### 5.2 迭代轨迹（R4 实证：5 版才全绿）

| 版本 | 关键动作 | 8 字净空 | 待机弧 | 并集覆盖 | 结论 |
|---|---|---|---|---|---|
| v1 | 按 7 分区铺开 | **−2.04** FAIL | 131.7° | 11.16% | 中央南带压到 8 字下瓣 → 修 |
| v2 | 南带内容整体南移 | +2.55 | 293.5° | 10.44% | 全绿 |
| v3 | 北仓/堆场向中带收拢、中央补到 4 个 | +1.31 | 293.5° | 10.44% | 全绿 |
| v4 | 围墙改 **30–34 m 分段**（短墙段不像围墙） | +1.31 | 293.5° | 10.78% | 全绿（修掉 2 处墙-房重叠） |
| **final** | 建筑缩尺给覆盖留余量 | +1.31 | 293.5° | **10.89%** | **全绿** |

### 5.3 这一步最容易犯的两个错（本项目都犯过）

1. **`cylinder` / `sphere` 的 `size[0]` 是半径，不是直径。** 当成直径除以 2 会让
   **重叠判定与全部偏松**—— 是"会掩盖问题"的错，比偏严更危险。
2. **单图元实体的 `yaw` 被重复叠加一次**（复合体的 part yaw 已是相对量）。
   修完后本地口径 10.32% 才与官方 10.33% 对齐。

> **惨痛教训**：R4/R5 的设计核验器写在 `/tmp/agc-p1-1-r3/`，**已被清理，无法复现**。
> 下一轮必须把它放到 `tests/` 或 `scripts/` 入库——**"先设计后动手"的产物本身就是资产**。

---

<a id="paradigm"></a>
## 6. 第 3 步 · 布局范式

现实工业场站的分布 = **功能分区 + 网格对齐 + 道路留白 + 尺寸长尾 + 中央留空**，
不是均匀随机撒点（[ADR-0007](../../../../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)）。

### 6.1 七个分区（yard，世界 ENU，作业区 [−50,50]²）

| 分区 | 范围 | 内容 |
|---|---|---|
| 北外环生产仓储带 | y 26..40 | 主厂房、仓库、办公楼、配电房 |
| 东区罐区/管廊/变电站 | x 26..46 | 罐区（防火堤+基础环）、管廊、变电站 |
| 南外环堆场与库房 | y −44..−26 | 集装箱堆场、库房、配送库 |
| 西区维修与办公 | x −46..−26 | 维修车间、办公楼 |
| 中央南带 | y −13..−22 | 堆场、薄板堆、筒仓、工具房、隔离墩/锥桶/石墩/花坛列 |
| 中央北带 | y 9..13 | 监控塔、双罐、指路牌 |
| 周界 | 四边 | **30–34 m 分段长墙 + 段间门洞** |

### 6.2 三条布局约束（都有物理原因）

1. **中央不是自由矩形，而是"轨迹外围的两条带"。**
   8 字占 x∈[−15,15]、y∈[−4.5,4.5]，膨胀盘还要 +3.2 m（2.5 余量 + 0.7 反应/可达）。
   所以内容只能放在北带 / 南带，中央 15 m 内只保留 4 个实体。
2. **不能用一根 100 m 通长围墙闭合场站。**
   安全层是二维静态圆盘，半径 ≈ 半长；100 m 墙的圆盘会吃掉整个空域，把 8 字判为不可行。
   → 分段长墙既贴现实（围墙本就按柱距分段），又让每段圆盘远离 8 字空域。
3. **尺寸长尾是"真实感"的来源。**
   yard 的最长/最短边比 **566.67×**（`wall_n` 的 34 m 长边 ↔ `sign_a` 的 0.06 m 立柱），
   图元高度比也 ≥ 2×。全部等大 = 玩具感。

### 6.3 配色分族（同族一致，族间可辨）

生产仓储 = 混凝土冷灰 + 银灰蓝屋面；办公 = 暖灰 + 深蓝绿玻璃；
罐区 = 银白钢（**仅一台**标识罐暖橙）；集装箱 = **同一排同色**（现实按批号成排堆放），
第五个箱位**留空**（真实堆场不是满格）；路缘家具各就各位。

---

<a id="gates"></a>
## 7. 第 4 步 · 几何可行性闸门

七项判据，**缺一项都不能写真源**。下表是 yard 当前实测值（2026-10-29）：

| # | 判据 | 阈值 | yard 实测 | 对应断言 |
|---|---|---|---|---|
| 1 | **8 字轨迹净空**（安全盘不切轨迹） | ≥ 0 m | **+1.31 m**（最紧 `sign_a`） | ⚠ 仅在离线核验器里，**不在正式断言** |
| 2 | **待机环带可行解** | 最长连续可行弧 ≥ 90° | **81.53% / 293.5°**（r = 10.2 m） | (i) |
| 3 | **出生净空** | 逐足迹净空 > 0，车↔目标 ≥ 6.0 m | 车 **8.67** / 目标 **6.48** / 己方机 **9.07** m；车↔目标 **11.85 m** | (g) |
| 4 | **实体互不重叠** | SAT 无交 | 无 | 离线核验器 |
| 5 | **地面激光可见性**（z=0.48） | 每个实体在该面有水平截面 | 全部可见 | (h) |
| 6 | **并集覆盖率** | 5%–12%（yard） | **11.48%**（R6 加参照物后） | (o) |
| 7 | **尺寸/形状/朝向长尾** | 尺寸比 ≥3×、高度比 ≥2×、yaw ≥3 种、形状 ≥2 类 | 566.67× / 12 种 yaw / 3 类形状 | (o) |
| 8 | **明度带**（R6 新增） | 屋面 − 基层地面 ≥ 0.30 | **0.877 − 0.396 = 0.481** | (q) |

### 7.1 第 1 项是唯一的"单点故障"，却没有正式断言

8 字净空最危险：**它一变成负数，空中安全层直接判不可行，整个演示跑不起来**，
但正式核查只查"环带可行弧"，不查"轨迹是否被切断"。设计时必须自己算。

### 7.2 覆盖率的余量极薄（这是当前最大约束）

yard 现在 **10.89%**，上限 12% → 100×100 作业区里只剩 **111 m²** 的投影余量。
任何加物件/加建筑的动作都要先算面积，别等核查 FAIL 才发现。

### 7.3 闸门之间会互相踩

- 环带（8–15 m）被挤 → 加中央内容就掉；
- 覆盖率被顶 → 加建筑就爆；
- 分段墙的逻辑反过来救了环带（见 6.2 第 2 条）。

**所以布局是联合求解，不是逐项满足。**

---

<a id="schema"></a>
## 8. 第 5 步 · 表达同一份几何（schema）

schema 的**唯一出口**是 [`world_map.py`](../../../../src/agc_sim/launch/world_map.py)。核心字段：

```yaml
map: yard
work_area: {resolution: 0.5, size_x: 100.0, size_y: 100.0, origin_x: -50.0, origin_y: -50.0}

obstacles:
  # 单图元实体
  - id: silo_s
    shape: cylinder # box(缺省) | cylinder | sphere
    x: 0.0
    y: -18.0
    z: 1.6 # 几何**中心**高度（box 与 cylinder 同口径）
    yaw: 0.0
    size: [1.8, 1.8, 3.2] # box:[x,y,z] / cylinder:[r,r,h] / sphere:[r,r,r]
    color: [0.72, 0.74, 0.76]
    finish: steel # 材质档（可选）
    safety_radius: 1.8 # 可选，缺省由足迹推导

  # 复合实体（一个 <model> 含多个 static <link>）
  - id: hall_north
    x: -26
    y: 30
    z: 0.0 # ⚠ 复合体锚点 z **必须为 0**（part 的 z 是绝对高度偏移）
    yaw: 0.0
    parts:
      - {shape: box, size: [14.5, 9.5, 7.5], x: 0, y: 0, z: 3.75, finish: concrete, color: [...]}
      - {shape: box, size: [14.8, 9.8, 0.3], x: 0, y: 0, z: 7.62, finish: steel}
```

### 8.1 三条必须知道的规范

1. **cylinder / sphere 的口径是半径**，`size[0] == size[1]`（cylinder）或三值相等（sphere），
   不相等**拒绝运行**。
2. **复合体锚点 `z` 必须为 0**。曾经把 `wall_w` 写成 `z: 1.1`，注入器又叠加 part z →
   **整段围墙悬空 1.1 m**，靠断言 (h) 才抓到。现在 `obstacle_parts` 里有启动期守卫。
3. **缺省不写 `finish` = 旧行为**（无 `<pbr>` 块），保证 minimal / open_field 与历史证据
   **逐字节不漂移**。这条兼容纪律必须保持。

### 8.2 派生时的降级（成文约定）

感知只有 OBB（`sx/sy/sz` + yaw），表达不了圆柱/球/多图元 →
**一律降级为水平轴对齐包络矩形**（保守外扩，不缩小实体）。
`finish` 只进物理世界 `<material>`，**不进**感知先验 / 占位栅格（材质不是几何）。

### 8.3 `safety_radius` 的推导规则

```text
显式给出 → 用它
否则 box → 半对角 = hypot(sx, sy) / 2
否则 cylinder/sphere → r
否则复合体 → max over parts(hypot(part.x, part.y) + part 足迹半径)
全部为 0 → 兜底 2.0（历史 pole 标定值）
```

**后果**：细长实体的外接圆半径 ≈ **半长**。这是 6.2 第 2 条（不能用通长围墙）的根因。

---

<a id="visual"></a>
## 9. 第 6 步 · 视觉保真

**只改视觉，不动任何判据**。这是 R5 的全部工作，也是最容易越界的一步。

### 9.1 材质档 `finish`（标量 PBR）

七个档，逐 part 可覆盖实体级，非法值**拒绝运行**：

| finish | metalness | roughness | 语义 |
|---|---|---|---|
| `concrete` | 0.00 | 0.90 | 混凝土（墙 / 勒脚 / 压顶 / 基础 / 围墙） |
| `steel` | **0.35** | **0.42** | 结构钢 / 罐体 / 管廊 / 灯杆（R6 由 0.75/0.35 下调，见 15.2②） |
| `paint` | 0.15 | 0.45 | 涂装金属（集装箱 / 卷帘门 / 标牌 / 岗亭） |
| `glass` | 0.05 | 0.08 | 玻璃（窗带 / 门厅），diffuse 压暗到 0.72 出深色玻璃感 |
| `rust` | 0.10 | 0.95 | 锈蚀件（预留） |
| `asphalt` | 0.00 | 0.95 | 沥青（场地道路） |
| `rubber` | 0.00 | 0.80 | 橡胶 / 塑料（锥桶、灌木球） |
| `roofpanel` | 0.06 | 0.40 | **金属屋面板**（R6 新增；低金属度才有亮度，见 15.2②） |

依据：本机 sdformat 1.11 `material.sdf` 里 `<metalness>` / `<roughness>` 是**标量**，
不需要贴图 → 与"不引入外部资产"纪律不冲突。

### 9.2 建筑细部（让"建筑"像建筑）

每栋大体量建筑按需组合：**勒脚** + **女儿墙压顶** + **金属屋面板** + 逐层**窗带**
（微凸出墙面的**真几何**，不是贴图）+ **卷帘门/玻璃门厅** + **台阶** + **屋顶设备** +
**雨棚/月台/门廊柱**。塔罐加基础环与爬梯，管廊加法兰。

### 9.3 地面分层（在 `agc_world.sdf`，**不是障碍**）

四层：基层混凝土 `ground_plane`(200×200) + 沥青环形主路 + 中央混凝土作业坪 + 两处场坪。

**必须遵守**：

- 三者都是**地面**：不进几何真源 `obstacles`、不进空中安全层、不进感知占位栅格；
- **视觉与碰撞同源**（每块都带 collision），抬升 2–6 mm 避免与基层共面 z-fighting；
- 断言 (n) 会核验 `ground_plane` 碰撞与 `physics` **未被改动**。

> 副作用需如实登记：地面块带 collision → 车实际抬高 2–6 mm。**不重标定任何阈值**。

### 9.4 GUI 相机预设（修"地图是斜的"）

写进 `agc_world.sdf` 的 `<gui><plugin MinimalScene>`：

```xml
<camera_pose>0 0 118 0 1.5708 1.5708</camera_pose>
<ambient_light>0.45 0.45 0.45</ambient_light>
<background_color>0.78 0.82 0.86</background_color>
```

`yaw=+π/2` 使画面 **北朝上、东朝右**（纯俯视平面图）。朝向不是猜的，是用
**同姿态相机传感器**渲染后对几何投影做 IoU 拟合校正的（`yaw=0` → 东朝上，`yaw=+π/2` → 北朝上）。

### 9.5 视觉层归属的分界线

| 元素 | 归属 | 判据 |
|---|---|---|
| 路缘石 / 停车线 / 排水沟 / 碎石带 / 绿化带 | **world 视觉层**（同 `ground_plane`） | 高度 < 0.48 m，进真源会直接 FAIL 断言 (h) |
| 叉车 / 货车 / 托盘堆垛 / 集装箱拖车 | **几何真源 `obstacles`** | 高度 > 0.48 m，可作障碍 |

---

<a id="derive"></a>
## 10. 第 7 步 · 派生链落地

改完 yaml，**五条派生路径必须全部跟上**，否则出现"世界里有墙但地图上没有"的诡异行为：

| # | 派生点 | 函数 | 常见漏点 |
|---|---|---|---|
| 1 | GZ 物理世界 | `world_bringup._inject_static_obstacles` | 以为改 SDF 就行 |
| 2 | 感知障碍先验 | `composition.write_derived_obstacles` | 复合体降级为包络矩形 |
| 3 | 感知 Map 几何 | `composition.write_derived_map` | `work_area` 变了没同步 |
| 4 | 空中安全圆盘列表 | `composition.apply_air_geometry` | **定长列表**是历史坑（已消除） |
| 5 | `scenario_reset` 校验几何 | `compose_params` | 边界写死 |

**回退副本纪律**：`agc_perception/config/{obstacles,map}.yaml` 是 standalone 回退副本，
**必须与 minimal 真源一致**（断言 (c)）。改 minimal 忘同步 → (c) 直接 FAIL。
非 minimal 地图在 standalone 路径上会**显式拒绝**（比静默用错几何好）。

**地图选择优先级**（`load_scene`）：

```text
launch world_map:=<name> （显式覆盖，未知值拒绝运行）
  ↓ 空
scenarios.yaml 的 world_map 键 （场景登记：s04 → yard，其余 → minimal）
  ↓ 空
缺省 minimal
```

---

<a id="verify"></a>
## 11. 第 8 步 · 核查

### 11.1 一条命令

```bash
python3 tests/check_scene_geometry.py # 三图全查
python3 tests/check_scene_geometry.py --maps yard # 只查一张
python3 tests/check_scene_geometry.py --out /tmp/g.json # 落盘 JSON 摘要
```

**退出码语义：0 = PASS**。当前状态：`PASS (maps=minimal,yard,open_field)`。

### 11.2 断言清单（16 组，任一项 FAIL 即整体 FAIL）

| 断言 | 内容 |
|---|---|
| (a) | schema 合法（work_area 五键 / shape 合法 / cylinder 半径一致 / safety_radius > 0）|
| (b) | 世界生成 == 真源，且**视觉 == 碰撞**；minimal 的 `pole_*` 逐值不变；`none` 世界无障碍 |
| (c) | standalone 回退副本与 minimal 一致 |
| (d) | `air.yaml` 已无硬编码几何**与半径列表** |
| (e) | `base.yaml` 已去硬编码；composition 派生 == 真源 |
| (f) | `geometry_sha256` 稳定且**按图区分**；manifest 几何块 == 真源 |
| (g) | **出生净空**（与 `scenario_reset.validateCandidate` 同判据）|
| (h) | **z=0.48 障碍族可见性** |
| (i) | **空中安全层存在可行解**（环带可行率 > 0 且最长连续可行弧 ≥ 90°）|
| (j) | 回退副本边界（非 minimal 不读副本）|
| (k) | 权限：`obstacles.yaml` 静态先验成文假设仍在 |
| (l) | 地图登记一致（`scenarios.yaml` 的 `world_map` ∈ 清单；s04 → yard）|
| (m) | 几何真源清单**单一实现**（三处都经 `world_map.py`）|
| (n) | GUI 网格是纯视觉（`ground_plane` 碰撞与 `physics` 未变）|
| (o) | yard 形状/尺寸/朝向多样性 + **并集覆盖 5%–12%** + 实体上限 |
| (p) | 三图作业区一致（100×100 / origin −50）|

### 11.3 当前实测（yard）

```text
n_obstacles = 36 n_parts = 186 composite = 34 small_parts = 19
coverage_union_pct = 10.89 material_kinds = 5 shape_kinds = 3
size_ratio = 566.67 yaw_kinds = 12 central_count = 4
ring: feasible 81.53% / max_free_arc 293.5° (r = 10.2 m)
car 8.67 / target 6.48 / own_uav 9.07 m car↔target 11.85 m
```

---

<a id="traps"></a>
## 12. 已知限制与坑

### 12.1 能力边界（如实登记，不假装）

1. **空中安全层是二维静态圆盘**，半径 = 实体水平外接圆半径。
   细长实体的圆盘 ≈ 半长 → **不能用通长围墙**，必须分段（见 6.2）。
2. **无贴图 / 无 mesh** → 材质只有标量 PBR + 纯色，出不了纹理细节。
   再往上要贴图必须走 [ADR-0005](../../../../docs/adr/0005-px4-toolchain-and-link.md#top)
   的 provenance / 许可 / 哈希登记。
3. **地面激光是 z≈0.48 m 的单一水平面**。矮墙、悬空结构、薄片对它**不可见**，
   若加入必须在文档中如实标注"该障碍对地面激光不可见"，**不得假装能避**。
4. **感知只有 OBB** → 圆柱/球/复合体一律降级为包络矩形。
5. **实体间距要留余量**：中央内容受 8 字膨胀盘挤压，这是硬约束不是审美问题。

### 12.2 工程陷阱

| # | 陷阱 | 后果 | 防法 |
|---|---|---|---|
| 1 | 复合体锚点 `z ≠ 0` | 整段模型悬空/埋地 | 启动期守卫（已加） |
| 2 | cylinder 半径当直径 | **重叠与偏松**，掩盖问题 | 核验器写完先自测 |
| 3 | part 的 yaw 与实体 yaw 重复叠加 | 布局错位 | 复合体 part yaw 是相对量 |
| 4 | 改 minimal 忘同步回退副本 | 断言 (c) FAIL | 改完立刻跑核查 |
| 5 | 以为 GUI 网格来自 `ground_plane` | 找不到"网格从哪来" | 它在 `<scene><grid>`，非 `ground_plane` |
| 6 | 靠 GUI 里累积 `/gui/move_to/pose` 调视角 | 截图朝向不可复现 | 用 `<gui>` 相机预设 |
| 7 | 设计与核验器写在 `/tmp` | 产物丢失、无法复现 | 入库到 `tests/` 或 `scripts/` |

### 12.3 取证能力限制（本机）

本机是 **Wayland** 会话：`PIL.ImageGrab` 的 X11 `XGetImage` 报 `BadMatch`；
无 Xvfb / `xdg-desktop-portal` / `import` / `xwd` / `ffmpeg` / `grim` / `scrot`（已核实）。
→ 只能改用**同姿态相机传感器渲染**取证，并**明确标注** `backend=gz-offscreen-camera`，
**不冒充 GUI 截图**。

---

<a id="drift"></a>
## 13. 本次发现的文档漂移（待修）

核查三图全绿，但**文档与代码/数据有 4 处不一致 + 1 处代码缺陷**，建议下一轮顺手修掉：

| # | 位置 | 漂移内容 | 实际 |
|---|---|---|---|
| 1 | [`world_geometry.yaml:11`](../../../../src/agc_sim/config/world_geometry.yaml) | 写 yard 是"29 实体 / 107 图元" | **36 / 186**（R5 已改，注释未跟上） |
| 2 | [`world_geometry.yaml:13`](../../../../src/agc_sim/config/world_geometry.yaml) | 引用 `composition.resolve_geometry_file` | 该函数**不存在**，实际是 `world_map.geometry_path` |
| 3 | [`check_scene_geometry.py:8`](../../../../tests/check_scene_geometry.py) | docstring 写 `shape ∈ {box, cylinder}` | 代码用 `SHAPES`（**3 类**，含 sphere） |
| 4 |规格（已删除，见 [ADR-0025](../../../../docs/adr/0025-publishing-boundary-and-retirement.md#top)）值 6.49 / 9.04 | 与实测 6.48 / 9.07 有 0.01–0.03 偏差 | 实测优先 |
| 5 | [`world_bringup.launch.py:380`](../../../../src/agc_sim/launch/world_bringup.launch.py) | `plugin_dir` 算成 `install/agc_sim/share/lib`（**不存在**） | 真实插件在 `install/agc_sim/lib`；详见 [14.2](#run) |

**另有一处结构性风险（比上面 5 条严重）**：

> `src/agc_sim/config/maps/` 与 `src/agc_sim/launch/world_map.py` **仍未纳入 Git**
> （`git status` 显示 `??`）。任何 `git clean` / 回滚都会**删掉几何真源**。
> 这是 R4 起就反复提示、至今未解决的事项。**先把它们 `git add` 再谈别的。**

---

<a id="run"></a>
## 14. 起跑命令与运行陷阱

### 14.1 启动演示主场景（yard）

```bash
cd /home/chen/AGC
source /opt/ros/jazzy/setup.bash
source install/setup.bash
# ⚠ 必须先设这个，否则 launch 立刻失败（见 14.2）
export GZ_SIM_SYSTEM_PLUGIN_PATH="/home/chen/AGC/install/agc_sim/lib"
ros2 launch agc_task main.launch.py backend:=lightweight scene:=s04_static_static_obs_track
# 想同时看 RViz 语义层（GUI 保持纯场景）：
ros2 launch agc_task main.launch.py backend:=lightweight \
  scene:=s04_static_static_obs_track viz:=true
```

> `viz:=true` 会额外起 `viz_markers`（把真源几何 / 安全圆盘 / 8 字参考转成 MarkerArray）
> 和 `rviz2`（固定布局 `config/agc_demo.rviz`），并**发一条 `map→world` 恒等静态 TF**
> —— 少了这条 TF，RViz 的 Fixed Frame `map` 无效，**窗口会完全空白且不报错**（15.3 坑 1）。

`s04` 在 `scenarios.yaml` 里登记了 `world_map: yard`，无需显式传；
要换图用 `world_map:=minimal` / `world_map:=open_field` 强制覆盖。

### 14.2 运行陷阱一：`GZ_SIM_SYSTEM_PLUGIN_PATH` 未定义（本次实测遇到）

```text
[ERROR] [launch]: Caught exception in launch: environment variable
        'GZ_SIM_SYSTEM_PLUGIN_PATH' does not exist
```

**根因有两个，同时存在**：

1. **`world_bringup.launch.py:383` 用 `EnvironmentVariable('GZ_SIM_SYSTEM_PLUGIN_PATH')`
   做"追加"**（`[plugin_dir, ':', EnvironmentVariable(...)]`，见 380–383 行）。该变量在
   `install/setup.bash` 里**不存在**，而 launch 的 `EnvironmentVariable` 对未定义变量**抛错**
   （不像 `environ.get(..., default="")` 那样容忍）。历史脚本
   [`run_w7_baseline.sh`](../../../../scripts/archive/run_w7_baseline.sh) 靠外部 `export` 绕过。
2. **`plugin_dir` 本身算错了**（实测确认）。`world_bringup.launch.py:380` 写的是
   `os.path.join(os.path.dirname(share), 'lib')`，而 `share` = `install/agc_sim/share/agc_sim`
   → 得到 `install/agc_sim/share/lib`，**该目录不存在**。真实插件在 `install/agc_sim/lib`。
   即：即使变量存在，追加进去的也是**无效路径**（`os.path.exists` 实测 `False`）。

**修法（短期）**—— 直接导出**正确**路径，不要照抄 14.1 之外的猜测：

```bash
export GZ_SIM_SYSTEM_PLUGIN_PATH="/home/chen/AGC/install/agc_sim/lib"
```

**为什么短期能救**：`ros_gz_sim` 的 `gz_sim.launch.py:91` 会把
`GZ_SIM_SYSTEM_PLUGIN_PATH` 与 `LD_LIBRARY_PATH` **合并**后再传给 gz 进程，
而 `install/setup.bash` 已经把 `install/agc_sim/lib` 放进 `LD_LIBRARY_PATH`（实测确认）
→ 插件**仍能被加载**，只是不靠 world_bringup 那条追加。

**修法（长期，建议下一轮一起改）**：

- 把 `plugin_dir` 改对：`os.path.join(os.path.dirname(os.path.dirname(share)), 'lib')`；
- 让追加对未定义变量容错（用 `EnvironmentVariable(..., default="")` 或先判断），
  避免"必须记得 export"的隐性前置条件—— 这属于入口健壮性问题，与地图无关。

### 14.3 运行陷阱二：PX4 / EKF

`backend:=full` 的 GUI 全链曾因 `start rejected: air_hover_timeout` 失败，
根因是 **PX4 EKF 定位发散**（`/agc/air/odom` x≈1032 m、`Preflight Fail: ekf2 missing data`），
**与地图几何无关**（世界生成 / 桥 / 复位均正常）。排查地图问题时先确认这一项。
隔离 PX4 状态用独立的 `px4_run_root:=/tmp/agc-<tag>-<unique>`。

### 14.4 只验证地图渲染（不起全链）

```bash
gz sim -r -v 3 <生成的运行期 world> # GUI，看画面
gz sdf -p src/agc_sim/worlds/agc_world.sdf # 只验解析，秒级
```

---

<a id="next"></a>
## 15. R6 实做记录（2026-10-30，**已实施**）

这一章是**执行后的复盘**：哪些按设计成了、哪些设计判断被实测推翻、踩了什么坑。
比设计稿更有价值的是**被推翻的那几条**。

### 15.1 实际落地的东西

| # | 项 | 做法 | 结果 |
|---|---|---|---|
| ① | 明度分层 + 屋顶 | 檐（`concrete` 0.553）压在体顶，**金属屋面再压在檐之上、内缩 0.6 m**；新增 `finish: roofpanel` | 屋面 albedo L **0.877**，地面 **0.396**，gap **0.481**（判据 0.30） |
| — | 屋顶细部 | 每栋 +屋脊 / 2 天窗 / 1 空调机组（全在足迹内） | 图元 186 → **234** |
| ② | 地面语义层 | 路缘石 8 条 / 停车位线 11 条 / 排水沟 4 条 / 碎石带 4 块 / 绿化带 2 条，**全在 `agc_world.sdf` 视觉层**（带 collision，抬升 4–6 mm） | 29 个地面块；断言 (n) 仍 PASS |
| ③ | 尺度参照物 | 货车 / 叉车×2 / 托盘×2 / 集装箱拖车 = **6 个可碰撞实体** | 实体 36 → **42**；覆盖 10.89% → **11.48%** |
| ④ | 地面贴图 | `materials/gen_textures.py` 产 4 张 512² albedo（concrete/asphalt/apron/gravel）+ `manifest.json` | 贴到 10 个地面模型；渲染 σ 从 **0.00 → 4.20** |
| ⑤ | RViz 语义层 | `agc_task/scripts/viz_markers.py` + `config/agc_demo.rviz` + `viz:=true` | 静态 278 个 marker：障碍几何 234 + 安全圆盘 42 + 作业区 + 8 字参考 |

**渲染实测（118 m 俯视，sRGB）**—— 这是"看得见"的口径，比 albedo 更硬：

| 层 | 亮度 | 占比 |
|---|---|---|
| 沥青道路 | ~93 | 18.6% |
| 基层地面 | **135** | 47.9% |
| 混凝土场坪 | **150** | 12.6% |
| **金属屋面** | **202** | 5.3% |

屋面 / 地面 = **202 / 135**，差 67 级 —— R5 时期差只有 6 级。

### 15.2 四条被实测推翻的设计判断（**最重要的部分**）

**（1）"区分度低是配色问题"—— 错，是几何缺陷。**
实测发现 5 栋建筑的「女儿墙压顶」被做成了**整块盖板**（`size` ≥ 本体足迹、`z` 在最上层），
把金属屋面**完全盖住**。俯视看到的其实是压顶（L≈0.49），比地面（0.67）还暗。
→ 光调 albedo 没有用，必须**改几何**（把压顶变成"檐 + 下沉屋面"的台阶关系）。

**（2）"提高 albedo 就能提亮屋面"—— 对金属件无效。**
金属度 0.75 的 `steel` 在"只有方向光 + 环境光、无环境贴图"的场景里几乎没有漫反射分量：
渲染只有 **83/255**，而旁边 metalness=0 的混凝土檐是 **161/255**。
**`metalness` 才是亮度杠杆。** → 新增 `roofpanel`(0.06/0.40)，并把 `steel` 从 0.75 下调到 0.35。

**（3）"加贴图就会有材质感"—— 先要过两道编码关。**
- `<albedo_map>` 与 `<diffuse>`/`<ambient>` 是**相乘**的：基色仍 0.52 时渲染从 150 掉到 **76**。
  → 带贴图的材质必须把基色置**白**，颜色交给贴图。
- PNG 被当 **sRGB**、SDF `<diffuse>` 是**线性**：直接把线性值写进 PNG 会整体压暗一档（150 → **106**）。
  → 落盘前做线性 → sRGB 编码。
- 且 `box`/`plane` **没有 UV 缩放**：一张图会被拉到整个面，200 m 地面与 12×9 场坪密度差 20 倍。
  → 只做**低频斑驳 + 细颗粒**，分格/拉线继续用真几何。

**（4）"GUI 里叠一层"—— 技术上走不通。**
本机 `libros_gz_bridge.so` **不映射 `visualization_msgs`**（实测只有 sensor_msgs / nav_msgs /
geometry_msgs / tf2 / ros_gz_interfaces）。→ 语义层只能用 RViz（原生支持 OccupancyGrid /
Path / LaserScan / MarkerArray），GUI 保持纯场景。

### 15.3 本次踩过的工程坑（按代价排序）

| # | 坑 | 症状 | 正确做法 |
|---|---|---|---|
| 1 | **RViz 全空** | 窗口打开但什么都不画，且不报错 | 项目话题都在 `world` 系，但 **TF 里没有 `world` 帧** → RViz 的 Fixed Frame 无效。→ 发 `map→world` 恒等静态 TF，Fixed Frame 用 `map` |
| 2 | **part id 撞号** | 断言 (b) `material_finish_match` FAIL，报 `part9: 0.15/0.45 != 0.75/0.35` | 重排 `parts` 后自动编号变位 → 保留段必须**固化原始 id**，新增件用语义 id（`*_rim` / `*_roof` / `*_sky0`） |
| 3 | **文本替换静默失败** | 脚本报"已改 10 处"，文件里一处没变 | 先改了 `block` 变量再用 `txt.replace(block,…)` —— 改过的字符串已不在原文里。→ **保留 `orig`，replace 用 `orig`** |
| 4 | **贴图不可复现** | 同脚本两次运行产出的 PNG 不同 | `abs(hash(name))` 受 `PYTHONHASHSEED` 随机化 → 改用 `zlib.crc32` |
| 5 | **`pkill -f "rviz2 -d"` 杀掉自己** | 整条 launch + Gazebo 一起没了 | `-f` 会匹配到自己的 `bash -c` 命令行 → **按 PID 杀**，或用不包含自身命令行的模式 |
| 6 | **改了脚本没生效** | `install(PROGRAMS)` 是**拷贝**不是符号链接 | 改完 `scripts/*.py` 必须 `colcon build` 该包 |
| 7 | **`OpaqueFunction` 签名** | `TypeError: takes 1 positional argument but 2 were given` | 必须写 `OpaqueFunction(function=...)`，不能只传 lambda |
| 8 | **RViz 视图类名** | `plugin for class 'rviz_default_plugins/Ortho' failed to load` | 正俯视是 **`rviz_default_plugins/TopDownOrtho`**（属性是 `Scale`/`Angle`，不是 `Distance`/`Pitch`/`Yaw`） |
| 9 | **断言 (q) 误判** | 加贴图后地面 L 被读成 **1.0**（基色置白所致）（原来的 0.396） | 有 `albedo_map` 时，地面色去 `materials/manifest.json` 的 `base_srgb` 取 |
| 10 | **改名空间断言** | 实体 36→42 撞上 `n_obstacles_le_40` | 上限 **40 → 46**（口径变更，需追认；理由：参照物必须可碰撞，只能进真源） |
| 11 | **覆盖余量** | 加完参照物 11.48%，离 12% 只剩 **52 m²** | 任何再加物件前先算面积 |
| 12 | **参照物压到既有足迹** | 首版 `trailer_a` 与 `container_yard_a` 重叠 | 落位前逐图元做重叠检测（官方核查**不查**这一项） |
| 13 | **RViz 里长围墙方向错** | 围墙画成轴对齐，实际绕 Z 转了 π/2 | marker 必须写 `pose.orientation`（`z=sin(yaw/2), w=cos(yaw/2)`）；复合体总朝向 = **实体 yaw + part yaw** |
| 14 | **正俯视视图 `Scale` 语义** | `TopDownOrtho` 的 `Scale` 是"米/像素"，写 95 等于整图缩成 1 像素 → 看着像全空 | 用 **`Orbit`**（`Distance`=150、`Pitch`=1.5707、`Yaw`=0）最不容易误设 |
| 15 | **同一时刻开两个 RViz** | 关掉一个后"看起来没变化"（其实看的是另一个旧窗口） | 重启前先确认 `pgrep -af "rviz2 -d"` 只剩 0 个 |

### 15.4 一个仍然存在的验证缺口

**8 字轨迹净空没有正式断言。** 官方 `check_scene_geometry.py` 只查"待机环带可行弧 ≥ 90°"，
不查"安全盘是否切断 8 字轨迹"。R4/R5 靠临时核验器算过（+1.31 m），但那个核验器在 `/tmp`
已丢失。**下一轮优先把它做成 `tests/` 里的正式断言**，否则这条最危险的判据永远靠人肉。

另注：本轮参照物全部落在 y≈−30..−40 的外环，远离 8 字带（|y|≤7.7）与待机环带，故
净空不可能被改变—— 但这是**推理**，不是**验证**。

---

## 16. 内存与并发（2026-10-30 实测，WSL 卡死后复盘）

**背景**：演示时 WSL 卡死，主机侧 Vmmem 从 ~2 GB 涨到 ~10 GB。先问"是不是障碍物太多"——
**不是**。

### 16.1 客观规模（先排除"地图太重"）

| 项 | 实测 |
|---|---|
| 实体 / SDF 静态 link | **42 / 234**（box 201、cylinder 29、sphere 4） |
| 贴图 | 4 张 512²，共 **756 KB** |
| 世界 SDF | 33 KB |

对 Gazebo 来说这是**很轻**的规模（上千个 link 才是常态）。所以内存问题与地图规模无关。

### 16.2 实测占用（同一台机，`memory=8GB` 的 WSL2）

| 场景 | 客机 used | 主要进程 |
|---|---|---|
| 空载 | ~950 MB | — |
| **仅 GUI 演示**（lightweight + Gazebo GUI + 全任务栈） | **~2.0 GB** | `ruby`(gz) ×2 ≈ 2.0 GB |
| **GUI + RViz 全开**（`viz:=true`） | **~2.3 GB** | 上面 + `rviz2` 257 MB + `viz_markers` ~90 MB |

结论：**一整套演示 ≈ 2.3 GB（起步）**。10 GB 是"起步 + 持续增长 + 多实例叠加"的结果。

### 16.2b 增长是 Gazebo GUI 自身的行为，**与地图规模无关**（对照实验）

同一台机、同一套 lightweight 栈，只换地图，连续采样：

| 地图 | 时间线（客机 used） | gz 两个进程 RSS |
|---|---|---|
| **minimal**（只有 2 根柱子） | 2465 → 2585 → 2707 → **2827** MB（↑362 MB / 135 s） | 608 → 689 → 772 → **853** MB（↑245 MB / 135 s） |
| **yard**（42 实体 / 234 link） | 3842 → **4033** MB（↑191 MB / 60 s） | 1543 → **1671** MB（↑128 MB / 60 s） |

→ **两种地图都在线性增长，速率都约 1.8–2.1 MB/s**。yard 比 minimal 只是多了约 **2 GB 的常驻**，
**增长斜率几乎一样**。所以：

- **不是障碍物太多**（2 根柱子也涨）；
- 增长来自 **Gazebo GUI（OGRE2 渲染）进程本身**，属环境/引擎侧，与本项目的地图内容无关；
- 按 ~2 MB/s 推算：从 2.3 GB 起步，**连续跑 45–50 分钟就会顶到 8 GB 上限**并开始换页/卡死。
  这正是"从 2000 涨到 10000"的时间尺度。

**另外**：本轮为取证又起了无头 `gz sim --headless-rendering`（每次 +1–1.5 GB），
与 GUI 同时存在 → 直接把峰值推到 10 GB。**这是我造成的放大，不是地图造成的。**

### 16.3 真正的三个放大因素

1. **同时跑多个 Gazebo 实例**：为了做渲染取证，我在 GUI 演示**还开着**的时候又起了
   无头 `gz sim -s --headless-rendering`（每次 +1–1.5 GB）。这是本次最主要的放大源。
   → **取证渲染必须与 GUI 演示互斥**（先关演示，再渲染）。
2. **WSL2 不主动归还内存**：`.wslconfig` 里只有 `memory=8GB`，**没有 `autoMemoryReclaim`**。
   page cache（构建产物、`~/.ros/log` 152 MB、渲染 PNG）算进 Vmmem，且默认不回收
   → 峰值一旦上去就停在 10 GB，最终触发换页/卡死。
3. **高频话题 + 高频重发**：`/agc/map` **2 Hz**、`/agc/obstacles` **10 Hz**；我最初让
   `viz_markers` 把 **278 个 marker 每秒重发**一次（纯浪费），已改为**静态层只发一次**
   （TRANSIENT_LOCAL 保留给后订阅者）、之后只发动态层。

### 16.4 已做的降载改动

- `viz_markers`：静态层（障碍几何 234 + 安全圆盘 42 + 作业区 + 8 字）**只发一次**；
  动态层 2 Hz。
- `agc_demo.rviz`：**占位栅格缺省关闭** —— 本机 RViz 的 OccupancyGrid 着色器链接失败
  （GLSL：`active samplers with a different type refer to the same texture image unit`），
  显示不出来还跟着 2 Hz 重传；能正常渲染的机器把 `Enabled` 改 `true` 即可。

### 16.5 建议（需要你在 Windows 侧改 `.wslconfig`）

```ini
[wsl2]
networkingMode=mirrored
autoProxy=true
memory=8GB
processors=4
# 让 WSL 主动回收 page cache（这是 10 GB 不回落的关键）
autoMemoryReclaim=gradual
# 交换区保留小一点，避免卡死时疯狂换页（可选）
swap=2GB
```

改完执行 `wsl --shutdown`（会关掉所有窗口）再进。若仍紧张，把 `memory` 提到 10–12 GB。

**演示时的纪律**（成本最低也最有效）：

1. 演示只用 `backend:=lightweight`；`backend:=full`（双 PX4）另加 2–3 GB。
2. **不要**在演示期间跑 `scripts/` 的批量实验或渲染取证。
3. 同一时刻只开**一个** Gazebo 实例、**一个** RViz。
4. **单次演示别超过 30–40 分钟**（GUI 以 ~2 MB/s 增长，8 GB 上限约 45–50 分钟到顶）；
   连着讲多场就每场之间重开一次，跑完 `wsl --shutdown` 让 Vmmem 归零。
5. 出现卡顿/换页就先看 `free -m`：`available` 掉到 1 GB 以下就该重启演示了。

## 16. 下一步（未做，按优先级）

1. **把 8 字净空做成正式断言**（见 15.4）—— 最高优先，补上唯一没有自动化的致命判据。
2. **贴图往建筑外墙扩展**：需要解决 UV 拉伸（本机 SDF 无 UV 缩放）→ 要么接受 mesh，要么放弃。
3. **RViz 的 `Map` 显示在本机有 GLSL 报错**（`indexed_8bit_image` 着色器链接失败：
   "active samplers with a different type refer to the same texture image unit"）——
   属驱动/OGRE 层问题，占位栅格可能因此不显示；marker 层不受影响。
4. ~~几何真源未纳入 Git~~ —— **2026-10-30 已解决**：`src/agc_sim/config/maps/`、
   `src/agc_sim/launch/world_map.py`、`src/agc_sim/materials/` 等 21 个文件已 `git add`
   （`git ls-files` 可验证）。**尚未 commit**，需按流程决定提交粒度。
