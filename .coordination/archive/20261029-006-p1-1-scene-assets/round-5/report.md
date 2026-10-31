# P1-1 · round-5 报告（视觉保真：材质 / 配色 / 细部 / 略增小型件）

- 执行者：Worker（DSH 会话）
- **授权来源：用户**（2026-10-29 21:00 直接对话）——本轮回同样**没有** Leader 书面 `request.md`，
  请 Leader 据此补认。
- 状态：**待审查**（自查全绿；含 3 项口径变更需追认，见 §5）
- 上游：[round-4 报告](../round-4/report.md#p1-1-r4-user)（100×100 与场站式重做）

<a id="p1-1-r5-user"></a>
## 1. 用户裁定（原文）

> 「我非常满意，但是现在建筑和地面精细度不高，能不能优化，比如材质改变，颜色分配优化。
> 二是小型物体（路牌这种）现在有点少，略微增加不要过分密集。网页看不了就不看了，
> 学习本地能看的就行，依旧设计好了再动手」

→ 四件事：**① 材质改变；② 颜色分配优化；③ 略增小型件（不过分密集）；④ 只学本地、先设计再动手**。

<a id="p1-1-r5-learn"></a>
## 2. 先学后做（决定性依据全部来自本机）

| 本机来源 | 学到什么 | 用途 |
|---|---|---|
| `/opt/ros/jazzy/opt/sdformat_vendor/share/sdformat14/1.11/material.sdf` | `<pbr><metal>` 的 **`<metalness>` / `<roughness>` 是标量**（默认 0.5），**不需要贴图** | 证明"改材质"与"不引入外部资产"不冲突 → 材质档方案成立 |
| `gz sdf -p agc_world.sdf` | 标量 PBR 被解析、无报错 | 落地前验证 |
| `nav2_minimal_tb4_sim/worlds/warehouse.sdf`（同引擎） | 通道式内部道路 / 成排对齐 / 小件成组 | 地面分层与小型件布置的现实依据 |
| 本机 PX4 官方世界 | `<gui><plugin MinimalScene><camera_pose>` 固定相机写法 | （round-4 已落地，本轮沿用） |

外部网页按用户指示**不再尝试**。

<a id="p1-1-r5-design"></a>
## 3. 先设计、后动手

进度与设计**先在设计核验器**（`/tmp/agc-p1-1-r3/candidate_visual.py` + `layout_harness.py`）里迭代，
全闸门通过后才写真源。迭代：v5 初稿 36 实体 / 186 图元 / 并集 **11.28%**（贴 12% 上限）→
把 4 栋建筑与勒脚外扩各收一档 → **10.85%（本地口径）/ 10.89%（官方口径）**，留出余量。

**全闸门（写盘前后一致）**：8 字净空 **+1.31 m**、待机环带 **81.53% / 293.5°**、
C7 **+8.67 / +6.49 / +9.04 m**、实体重叠 **none**、z=0.48 全部可见、并集覆盖 **10.89%**（5%–12%）。

<a id="p1-1-r5-files"></a>
## 4. 实际落盘

| 文件 | 改动 |
|---|---|
| `src/agc_sim/launch/world_map.py` | 新增 `FINISHES` / `FINISH_PBR` / `part_finish()` / `obstacle_finish()`（唯一 schema 出口；非法值拒绝运行） |
| `src/agc_sim/launch/world_bringup.launch.py` | `_material_sdf(color, finish)` 生成经典材质 + **标量 `<pbr><metal>`**；`_link_sdf` / `_obstacle_model_sdf` 透传 part 级 finish（part 覆盖实体） |
| `src/agc_sim/worlds/agc_world.sdf` | 基层混凝土改冷灰 + PBR；**新增 6 条沥青道路 + 3 处混凝土场坪/作业坪**（含 collision，视觉同源；抬升 2–6 mm） |
| `src/agc_sim/config/maps/yard.yaml` | **配色分族重写 + 逐 part 材质档 + 建筑细部（窗带/勒脚/压顶/屋面/卷帘门/门厅/台阶/雨棚/月台/屋顶设备/基础环/爬梯/法兰）+ 新增 7 个小型件**；29→36 实体、107→186 图元、13→19 小型件；头部新增「材质档 / 配色分族 / 建筑细部 / 地面分层」四节与更新后的实测边界 |
| `tests/w6_geometry_check.py` | (a) 增 `finish` 合法性；(b) 增 **`material_finish_match`** 逐 link 材质核对；(o) 上限 32→**40** + `material_kinds_ge_3`；新增材质解析辅助 |
| `docs/plan/p1-1-地图与场景资产.md` | 实测表更新 + 新增 [视觉保真节](../../../../docs/plan/p1-1-地图与场景资产.md#p1-1-visual) |
| `docs/adr/0106-...md` | 追加 **修订（视觉保真）** 节：finish 标量 PBR 决策 / 配色分族 / 细部 / 地面分层 / 核查扩展 / 未决（无贴图边界） |
| `docs/adr/README.md` | `scripts/adr_index.py` 重新生成，`--check` PASS |

**未动**：分区与中央空场、8 字轨迹（契约 C1）、9 消息 ABI、唯一执行口、状态机、安全阈值、终态判据。
**未 git commit**。

<a id="p1-1-r5-evidence"></a>
## 5. 证据

| 命令 | 结果 |
|---|---|
| `python3 tests/w6_geometry_check.py` | **PASS (maps=minimal,yard,open_field)**；`coverage_union_pct=10.89`、`n_obstacles=36`、`n_parts=186`、`small_parts_count=19`、`material_kinds=['concrete','glass','paint','rubber','steel']` |
| `python3 tests/w6_geometry_check.py --out …json` | 三图 `material_finish_match=True`；yard `material_kinds_used` 5 档；minimal/open_field `kinds=[]`（**旧行为未漂移**） |
| `gz sdf -p src/agc_sim/worlds/agc_world.sdf` | 无 error（标量 PBR 被接受） |
| 渲染取证（`backend=gz-offscreen-camera`） | 俯视图 8 朝向假设 IoU 拟合 → 命中 **北朝上 / 东朝右**；按世界坐标采样：中央场坪 **177** / 基层 **166** / 西环路 **90** / 北环路 **98** —— **逐位置与设计一致**，同时佐证朝向与地面分层 |
| 3/4 视角渲染 | 非背景像素 49.4%、饱和度>0.2 像素 3.43%（材质/配色确实渲出） |
| `python3 scripts/adr_index.py --check` | PASS（106 篇） |

产物：`/tmp/agc-p1-1-r3/` 下 `yard_v5_plan.png`（俯视，带指北/比例尺）、
`gz_render_v5_plan.png` / `gz_render_v5_3q.png`（整帧）、`design_v5.png`（示意图）、
`candidate_visual.py`、`shoot.py`、`snapshot/`（9 个改动文件快照）。
真源哈希：`yard.yaml` `e38917cf…`、`agc_world.sdf` `68c80c04…`。

<a id="p1-1-r5-deviations"></a>
## 6. 偏离与需追认项

1. **口径变更（需追认）**：实体上限 32→**40**；断言 (o) 新增 `material_kinds_ge_3`；
   断言 (a) 收紧了 `finish` 校验；断言 (b) 新增 `material_finish_match`。
2. **改了 `agc_world.sdf` 的地面**（基层颜色 + 9 个地面块）：属**视觉层**，但确实改动了 world 文件；
   断言 (n) 仍 PASS（`ground_plane` 名称与 collision 保留、`physics` 未动、几何真源未受影响）。
   **地面块带 collision**（视觉与碰撞同源），因此让车实际抬高 2–6 mm —— 如实登记，**未**重标定任何阈值。
3. **分层地面不在任何真源里**（就地内联在 base world）：与既有 `ground_plane` 同一处理方式；
   若 Leader 认为应纳入真源派生链，请指示（届时需扩 schema：地面层不是障碍）。
4. **仍未取得 GUI 窗口截图**（本机 Wayland 无 Xvfb / portal / import / xwd / ffmpeg / grim；
   `PIL.ImageGrab` 的 X11 `XGetImage` 报 BadMatch）。GUI **进程**启动已多次验证无 error；
   画面证据用同姿态渲染替代并**明确标注**，不冒充 GUI。
5. **未跑主场景 / 未重建 `agc_task`**（round-4 遗留的 C++ 默认值改动仍未生效）。
6. **`git` 仍未 add**：几何真源目录依旧未跟踪（round-4 已提示，风险未消除）。

<a id="p1-1-r5-next"></a>
## 7. 请求 Leader 的最小下一步

1. **先 `git add`**（`src/agc_sim/config/maps/`、`src/agc_sim/launch/world_map.py` 与本轮改动）。
2. 追认 §6.1 的口径变更；裁定 §6.2/6.3（地面改动与真源归属）。
3. 在有截屏能力的环境补 **GUI 截图**（相机预设已就位），闭环硬约束 C3 的定性证据。
4. 之后才谈 P1-1 原有出口判据（yard 上跑通 `TRACKING_SUCCESS`）——两轮均未推进该项。