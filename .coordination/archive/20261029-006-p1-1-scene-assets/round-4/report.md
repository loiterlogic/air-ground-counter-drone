# P1-1 · round-4 报告（作业区 100×100 与 yard 场站式重做）

- 执行者：Worker（DSH 会话，接手 round-3 崩溃后的工作区）
- **授权来源：用户**（2026-10-29 18:44 直接对话）。本轮回**没有** Leader 书面 `request.md`
  —— 该轮由用户当场裁定并直接指派 Worker，故只有本报告，无对应派工单。请 Leader 据此补认。
- 状态：**待审查**（自查全绿，但含 3 项需 Leader 裁定/补认的偏离）
- 上游：round-2 [report](../round-2/report.md#p1-1-r2-summary)（已崩溃的 round-3 无有效报告）

<a id="p1-1-r4-user"></a>
## 1. 用户裁定（原文，本轮的**唯一**范围来源）

> 「现在的障碍物已经挺不错了，但是我考虑到在空地协同反无人机中 80\*80 可能不太够，改成 100\*100，
> 然后重新布局障碍物分布和数量以及样式，样式要考虑现实世界中正常情况下是怎么分布的，
> 你可以先学习一下别人是怎么做的，然后在设计，**一定是设计好大致分布再动手**」

→ 拆成三件：**① 作业区 80×80 → 100×100；② yard 障碍重新布局（分布/数量/样式）；
③ 先学 → 先设计 → 再动手**。③ 是流程约束，本轮按它执行（先离线设计+核验，再改真源）。

<a id="p1-1-r4-learn"></a>
## 2. 先学后做（未凭假设试错）

按项目铁律的优先顺序，**先查本机同版本可运行实现**，再查官方：

| 来源 | 学到什么 |
|---|---|
| `nav2_minimal_tb4_sim/worlds/warehouse.sdf`（GZ Sim 8，20 行 include，**同引擎可运行**） | 26 个 include：货架**成排对齐**（yaw 只有 0 / 1.57）、Jersey 隔离墩**成列同 x**、椅/桌**成组贴近**功能区 → 现实布局 = "网格对齐 + 功能聚集"，**不是均匀撒点** |
| `PX4-Autopilot/Tools/simulation/gz/worlds/baylands.sdf` 等 4 个官方世界 | `<gui><plugin MinimalScene><camera_pose>` **固定相机预设**写法（可复现截图）；`ros_gz_sim_demos/worlds/*.sdf` 同款 |
| gz-sim 8 自带 worlds（`/opt/ros/jazzy/opt/gz_sim_vendor/.../worlds/`） | 世界/传感器条目组织方式；相机传感器姿态口径（下文实测校正） |
| 现实工业场站布局通则 | 功能分区 + 内部道路网格（8–15 m）+ 尺寸层次长尾 + 中央作业坪留空 |

**外部网络**：`web_search` 无 API key（不可用）；`curl` 可达 px4/nav2/gazebo 文档站但内容抓取不稳，
故**主要依据本机同版本资产**（正是铁律的首选来源）。

<a id="p1-1-r4-design"></a>
## 3. 先设计、后动手（本轮的关键过程）

**没有直接改真源**。先写了一个**只读设计核验器** `/tmp/agc-p1-1-r3/layout_harness.py`，
复刻 `tests/w6_geometry_check.py` 的口径（安全盘半径 = `safety_radius+2.5+0.7`；待机环带
r=10.2 m；8 字 rx15/ry9；C7 逐图元足迹；SAT 重叠；z=0.48 可见性；并集覆盖率），
用它把候选布局迭代到**全部闸门通过**，最后才落到真源。

**迭代轨迹（每版都全量核验）**：

| 版本 | 关键动作 | 8 字净空 | 待机弧 | 并集覆盖 | 结论 |
|---|---|---|---|---|---|
| v1 | 按 7 分区铺开 | **−2.04** FAIL | 131.7° | 11.16% | 中央南带压到 8 字下瓣 → 修 |
| v2 | 南带内容整体南移 | +2.55 | 293.5° | 10.44% | 全绿 |
| v3 | 北仓/堆场向中带收拢、中央内容补到 4 个 | +1.31 | 293.5° | 10.44% | 全绿 |
| v4 | 围墙改 **30–34 m 分段长墙**（短墙段不像围墙） | +1.31 | 293.5° | 10.78% | 全绿（修掉 2 处墙-房重叠） |
| **final** | 建筑缩尺给覆盖率留余量 | +1.31 | 293.5° | **10.32%** | **全绿** |

**过程中修掉自己的两处口径 bug（如实登记，避免污染结论）**：
① 单图元实体的 `yaw` 被重复叠加一次；② `cylinder`/`sphere` 的 `size[0]` 是**半径**，
我误当直径除以 2 —— 后者会让**重叠判定与 C7 偏松**，属于会掩盖问题的错。修完与官方检查器
的并集覆盖对齐（10.32% vs 官方 10.33%）。

<a id="p1-1-r4-files"></a>
## 4. 实际落盘的文件

| 文件 | 改动 | 性质 |
|---|---|---|
| `src/agc_sim/config/maps/yard.yaml` | **整体重写**：29 实体 / 107 图元 / 27 复合体 / 13 小型件；7 分区；头部写布局范式、分区图、实测边界、覆盖口径、已知限制 | 几何真源 |
| `src/agc_sim/config/maps/open_field.yaml` | `work_area` → 100×100/−50；加"作业区随裁定统一"注释（**障碍未动**，对照图故意稀疏） | 几何真源 |
| `src/agc_sim/config/world_geometry.yaml` | `work_area` → 100×100/−50；schema 头补 `sphere`/`parts` 与"外接圆 ≈ 半长"限制；补作业区裁定注 | 几何真源 |
| `src/agc_perception/config/map.yaml` | 回退副本同步 100×100（断言 (c) 要求与 minimal 一致） | 回退副本 |
| `src/agc_task/src/scenario_reset.cpp` | **standalone 默认边界** ±40 → ±50（非真源，仅回退默认） | C++ |
| `src/agc_sim/worlds/agc_world.sdf` | 新增 `<gui>` 相机预设（正俯视平面图，北朝上）；注释说明 | 视觉层 |
| `src/agc_sim/config/car.yaml`、`target.yaml` | 注释里的 80×80 → 100×100（**值未动**） | 注释 |
| `tests/w6_geometry_check.py` | 断言 (o)：实体上限 20→**32**、新增**并集覆盖 5%–12%**；**新增断言 (p)** 三图作业区一致；新增 3 个只读 helper | 核查 |
| `docs/plan/p1-1-地图与场景资产.md` | 旧表标为历史；新增 [100×100 重做节](../../../../docs/plan/p1-1-地图与场景资产.md#p1-1-100x100)；非目标里改"不改 80×80" | 文档 |
| `docs/adr/0106-work-area-100x100-and-yard-layout-paradigm.md` | **新增 ADR**（含 Considered Options 与否掉通长围墙的技术理由） | 文档 |
| `docs/adr/README.md` | 由 `scripts/adr_index.py` 重新生成（106 篇，`--check` PASS） | 生成物 |

**未动**：9 消息 ABI、唯一执行口、状态机、安全阈值、终态判据、`air.yaml` 的 8 字轨迹（契约 C1）。
**未 git commit**（按 P1-1 约束）。

<a id="p1-1-r4-evidence"></a>
## 5. 证据

| 命令 | 结果 |
|---|---|
| `python3 tests/w6_geometry_check.py` | **PASS (maps=minimal,yard,open_field)**；(o) `coverage_union_pct=10.33` / `n_obstacles=29` / `n_parts=107` / `central_count=4`；(p) `is_100x100_origin_-50=True` |
| `python3 /tmp/agc-p1-1-r3/layout_harness.py src/agc_sim/config/maps/yard.yaml` | 8 字净空 **+1.31 m**；待机环带可行 **81.53%**、最长可行弧 **293.5°**；C7 车 **+8.67** / 目标 **+6.49** / 己方机 **+9.04** m；重叠 **无**；z=0.48 不可见 **无** |
| `python3 scripts/adr_index.py --check` | PASS（106 篇） |
| `gz sim -r -v 2 <生成的 yard 世界>`（GUI） | 进程起、世界加载、**无致命错误**（仅 QML binding loop / FSAA 警告）→ `<gui>` 预设不破坏 GUI |
| `gz sim -s -r <yard + 俯视相机传感器>` + gz-transport 订阅取帧 | 取到 1400×1400 真实渲染帧；**对渲染掩膜与几何投影做 IoU 拟合**判定朝向：`yaw=0` → 东朝上；`yaw=+π/2` → **北朝上**（IoU 0.501，优于其余 7 个假设） |

产物位置（`/tmp/agc-p1-1-r3/`）：
`yard_100x100_plan.png`（真实渲染裁到作业区、带指北/比例尺）、`gz_render_northup.png`（整帧）、
`design_final.png`（带 8 字与环带的示意图）、`layout_harness.py`、`candidate_final.py`、
`snapshot/`（本轮改动文件的快照）。

<a id="p1-1-r4-deviations"></a>
## 6. 偏离、阻塞与必须上报项

1. **旧 `yard.yaml` 已被覆盖且无备份** ⚠：该文件（连同整个 `src/agc_sim/config/maps/`、
   `src/agc_sim/launch/world_map.py`）**从未 `git add`**（`git ls-files` 为空），本轮重写
   **就地覆盖**。→ 旧图（80×80）任何指标**已无法逐值复算**；旧文档的 `覆盖 7.36%` 与
   `C7 12.2/8.2/10.6` **既不能确认也不能否证**；我中途对旧图的复算还带着上文⑦的半径 bug，
   故**连我的复算值也不可引用**。已在新真源头部与 plan 文档用"旧账"块如实登记。
   **请 Leader 裁定如何处理**（我未从记忆重建旧文件——重建件不可信，反而会制造假证据）。
2. **未取得 GUI 窗口截图** ⚠：本机为 Wayland 会话；`PIL.ImageGrab` 的 X11 `XGetImage` 报
   `error 8 (BadMatch)`；无 Xvfb / `xdg-desktop-portal` / `import` / `xwd` / `ffmpeg` / `grim`。
   → 改用**同姿态相机传感器真实渲染**取证，并**明确标注** `backend=gz-offscreen-camera`，
   **不冒充 GUI 证据**（硬约束 C3 的定性验收仍需 Leader 在有截图能力的环境补）。
   GUI 预设本身的**可用性**已由 GUI 进程正常启动佐证，**朝向**已由同姿态渲染实测佐证。
3. **未跑世界冒烟 / full attempt**：round-3 派工的预算（2 次 GUI full、1 次局部构建）与
   本轮的"重做布局"是两件事；本轮**没有**叠加实例、没有重跑 PX4 链路。当前**无遗留 GZ/桥/PX4
   进程**（已核 `ps`）。
4. **测试断言放宽**：`n_obstacles_le_20` → `_le_32`。这是**验收口径变更**，需 Leader 追认；
   理由：面积 ×1.56 且用户显式要求"重新布局数量"。同时**新增**并集覆盖断言（收紧了另一头）。
5. **`open_field` 作业区也改了**（用户只提 yard）：理由是三图 `work_area` 应一致，
   否则同一世界两套边界；已加断言 (p) 固化。**若 Leader 认为不该动，请指示回退**。
6. **C++ 改了 2 行默认值**（`scenario_reset.cpp`）。属回退默认、非真源，但**需重建 `agc_task`**
   才生效（本轮未构建）。

<a id="p1-1-r4-assumptions"></a>
## 7. 假设台账（可证伪）

| # | 假设 | 支撑 | 若错则… |
|---|---|---|---|
| A1 | `MinimalScene` 的 `camera_pose` 与相机传感器同姿态口径（前向 +x、画面上 = 局部 +z） | 官方 4 个世界同款默认值语义一致 + 同姿态渲染实测 | GUI 里朝向不是"北朝上"（需按实测 yaw 再修） |
| A2 | 并集覆盖率是 P1-1 "5%–12%" 的应有口径 | plan 文档写的是"障碍占作业区"，并集才是真实占地 | 覆盖断言口径需改（但断言本身已可自动判定） |
| A3 | 实体数上限 32 用户可接受 | 用户要求"重新布局数量"，且面积 ×1.56 | 需回调布局规模 |

<a id="p1-1-r4-next"></a>
## 8. 请求 Leader 的最小下一步

1. **立即 `git add` 几何真源**（`src/agc_sim/config/maps/`、`src/agc_sim/launch/world_map.py`
   以及本轮改动）——当前它们是未跟踪文件，随时可能被清理。
2. 裁定 §6 的 5 项偏离（尤其 1、4、5）。
3. 在有截图能力的环境补一次 **GUI 平面图截图**（预设已就位），闭环硬约束 C3 的定性证据。
4. 之后才谈 P1-1 的原有出口判据（yard 上主场景跑通 `TRACKING_SUCCESS`）——**本轮未推进该项**。