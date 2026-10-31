# P1-1 地图与场景资产 · 批次第 2 轮回报

- 任务 ID：`20261029-006-p1-1-scene-assets`　轮次：`2`
- 执行者：Worker（DSH 子会话，workbuddy / `deepseek-v4.1-flash` / `max`）
- Worker 子会话 ID：`c6c6de0c-5ba8-4ef2-9cef-7122dca7123b`（沿用 Leader 首轮登记值）
- 起始：2026-10-29T15:39（用户反馈时刻）　**结束：GUI 复验仍在进行，见"未完成 / 进行中"**
- 状态：`执行中`（批次内不逐轮置 `待审查`）

<a id="p1-1-r2-summary"></a>
## 审查摘要（≤30 行）

**结论**：用户 15:39 的三点返工要求**已全部实现并通过静态派生核查**；用户 17:00 追加的「更精致 + 小型障碍」
要求**也已实现**（新增 `sphere` 图元与 `parts` 复合模型能力）。**但 GUI 全链 s04 仍未跑通**
（attempt-1 因 `air_hover_timeout` 失败，属 PX4 EKF 侧，非几何；未重跑，见"未完成"）。

**差异清单**：

1. `src/agc_sim/config/maps/yard.yaml` —— **重写**：删 pole；13→**19 实体 / 44 图元 / 11 复合体**；
   新增 sphere；小型件 9 个；覆盖 **7.36%**（首轮 5.20%）。
2. `src/agc_sim/launch/world_map.py` —— 新增 `sphere` 图元、`parts` 复合模型、足迹推导安全半径、
   复合锚点 z 必须为 0 的守卫。
3. `src/agc_sim/launch/world_bringup.launch.py` —— 注入器支持多 link 复合 `<model>` + sphere + 材质高光。
4. `src/agc_sim/worlds/agc_world.sdf` —— 新增 `<scene><grid>false</grid></scene>`（**只关视觉网格**）。
5. `src/agc_task/launch/w6_composition.py` —— manifest 支持复合体（`composite` / `parts` / `footprint_radius`）。
6. `tests/w6_geometry_check.py` —— 断言扩展到复合 / sphere / 小型件；修正 4 处自测 bug。
7. `src/agc_task/src/scenario_reset.cpp` —— **首轮误改已回退**（不在白名单，见 §偏离）。

**未执行**：GUI 全链 s04 的主场景终态（`TRACKING_SUCCESS`）**未取得**；RL 基线（首轮）也未取得。

**证据**：截图 `experiments/demo/20261029-p1-1-yard-rework/round2-shots/`；
静态核查 `/tmp/agc-p1-1-artifacts/geometry_check_round2.json`（三图 PASS）。

<a id="p1-1-r2-gui"></a>
## 一、用户两点反馈的落地

### 1.1 15:39 三点（删 pole / 中央重做 / 关网格）

| 要求 | 落地 | 证据 |
|---|---|---|
| ① yard 删 `pole_1`/`pole_2`，minimal 保留 | yard.yaml 无 pole（`b.pole_policy_matches_map` 断言）；minimal 两柱逐值不变（`b.minimal_poles_unchanged`） | 核查断言 (b) |
| ② 中央重做 + 尺寸/形状/方向多样 + 保留通道/净空 | 中央 5 实体（tower / tank_farm / slab_c / silo_a / hut_c）；见 §1.2 | 断言 (o)；离线几何表 |
| ③ GUI 网格关闭 | `agc_world.sdf` 的 `<scene><grid>false</grid>` | 断言 (n)；GUI 截图**无网格** |

**网格来源查证（回答用户"是否 ground_plane"）**：**不是** `ground_plane`，也**不是**地面贴图。
Gazebo 的地面网格由 world 的 `<scene><grid>` 字段控制（SDF 缺省 `true`），GUI 按 cell 尺寸绘制，
**不参与碰撞 / 物理 / 任何真源几何**。因此只写 `<scene><grid>false</grid>`：
`physics`（`max_step_size=0.004`）、`ground_plane` 的 `<collision>`、全部几何真源**均未改动**
（断言 (n) 逐项核对 `ground_plane_still_present` / `ground_plane_collision_present` /
`physics_unchanged` / `geometry_source_not_touched_by_grid`）。

### 1.2 17:00「不够精致 / 缺小型障碍 / 只能做简单形状吗」

**答案：能做得更精致。原实现确实只支持 `box`；本轮把能力扩展到 3 类图元 + 复合模型。**

| 维度 | 首轮 | 本轮 |
|---|---|---|
| 图元种类 | box、cylinder（2） | box、cylinder、**sphere**（3） |
| 单实体可含图元数 | 1 | **多（`parts`）**，一个 `<model>` 含多 static `<link>` |
| 复合实体数 | 0 | **11**（塔/厂房/罐场/围墙/仓库/附楼/配电房/花坛/标牌/管线/罐） |
| 图元总数 | 13 | **44** |
| 小型件（单件最大边 <1 m） | 0 | **9**（锥桶×2、石墩、标牌、花坛、管线段等） |
| 尺寸跨度（水平边） | 37.5× | **243×**（14 m 厂房主体 ↔ 0.0575 m 立柱） |
| 高度跨度 | 5.3× | **60×**（0.12 m 塔顶平台 ↔ 7.2 m 塔身） |

**精致化的具体形态**（都是"一个实体 = 多个图元"，不是把大方块换成小方块）：

- `tower`：塔身 cylinder(r=1.1, h=7.2) + 顶部平台 cylinder + 检修爬梯 box + 航障灯 **sphere**；
- `hall_west`：主体 box(14×9×5.2) + 屋顶檐口 box(14.6×9.6×0.45) + 侧附体 box；
- `tank_farm`：两个不同径高罐 + 两个顶盖 + 连接管；
- `wall_w`：墙身 + **3 个墙垛**；
- `depot_e`：主体 + 2 根门廊柱 + 雨棚；
- `annex_sw`：主体 + 雨棚 + **两级台阶**；
- `planter_a`：池体 + 灌木（sphere）；`pipe_a`：主管 + 2 个法兰。

**视觉层次**：每个实体可有 `color`，part 可覆盖（同实体不同图元不同色）；
`_material_sdf` 按本体色派生略亮的 specular，单色图元也有明暗。

<a id="p1-1-r2-geom"></a>
## 二、几何可行性（离线核验，与 `air.yaml` 安全层同口径）

| 指标 | 值 | 判据 | 结论 |
|---|---|---|---|
| 实体数 | **19** | 用户放宽至 ≤20（原规格 15） | PASS |
| 图元数 | 44 | — | — |
| 覆盖面积 | **7.36%** | 规格 5%–12% | PASS |
| 地面走廊足迹净空（车→任务目标 (4,3)） | **7.52 m** | ≥2 m | PASS |
| 8 字轨迹安全盘净空最小值 | **+0.48 m** | ≥0 | PASS |
| 待机环带可行率 / 最长连续可行弧 | 48.8% / **106.4°** | 存在解且弧 ≥90° | PASS |
| C7 出生净空（车 / 目标 / 己方机） | 12.2 / 8.2 / 10.6 m | >0 且车↔目标 ≥6.0 m | PASS |
| 实体足迹两两重叠 | **0 对** | 无重叠 | PASS |
| z=0.48 激光面可见性 | 19/19 有 part 覆盖扫描面 | 全部可见 | PASS |

> **布局约束的物理含义**：8 字轨迹占 x∈[-15,15]、y∈[-4.5,4.5]；其**膨胀盘**（安全半径 +
> 障碍余量 2.5 + 反应/可达余量 0.7）把可放置区压成"轨迹外围"。故中央内容安排在
> **两条内容带**（北带 y≈8..14、南带 y≈-7..-12），既在中央可视范围内，又不切断轨迹。

<a id="p1-1-r2-t2"></a>
## 三、T2 真实运行（如实记账，**未成功**）

| # | 内容 | 结果 | 证据 |
|---|---|---|---|
| T2-1 | colcon 全量构建（首轮） | **EXIT 0**，39.7 s | `/tmp/agc-p1-1-artifacts/logs/colcon_build.log` |
| T2-2 | 局部重构建（agc_sim/agc_task/agc_air/agc_perception） | **EXIT 0**，25.1 s | 会话输出 |
| T2-3 | 局部重构建（agc_sim/agc_task，精致化后） | **EXIT 0**，3.4 s | 会话输出 |
| T2-4 | GUI 世界冒烟 yard（首轮布局） | 启动成功、GUI 可见、**截图有网格** | `world_smoke_yard.log` |
| T2-5 | GUI 世界冒烟 yard（返工后） | 启动成功、**截图无网格**、中央有内容 | `round2-shots/yard_fine_*.png` |
| T2-6 | GUI 世界冒烟 2 | 启动成功 | `world_smoke_yard_r2.log` |
| T2-7 | **GUI 全链 s04 × yard × seed0** | **FAIL：`start rejected: air_hover_timeout`** | `full-attempt1/launch.log` |
| T2-8 | GUI 世界（精致化后，供用户观看） | **运行中**，PID 31849 | `logs/gui_fine.log` |

**T2-7 失败现场**（如实记录，未掩盖）：

- `/clock` 推进正常（**246 Hz**）；`/agc/task/state` = `IDLE`；
- 显式 `ros2 service call /agc/task/start` → `success=False, message='start rejected: air_hover_timeout'`（49 s 后返回）；
- `/agc/air/odom` 的 **x=1032.79 / y=932.70**（应为 ~0）→ **PX4 EKF 定位发散**；
  `z=1.51` 且在 2 s 后变为 2.86 → 3.30（漂移中）；
- PX4 日志：`Preflight Fail: ekf2 missing data`；`px4_adapter` 记
  `EKF 复位计数 0 → 9：局部原点可能跳变`；
- 结论：**失败在 PX4/EKF 侧，与 map 几何无关**（yd 世界生成、桥、scenario_reset 均正常：
  `reset ok epoch=1 car=(-4.000,-3.000) target=(6.500,2.500)`）。

**按预算停手**：本轮 `T2` 的 GUI full attempt 预算为 1（首轮 0 次），已用尽；且预登记停止条件为
"2 次 GUI full attempt 后仍未得 yard 主场景终态即判定不可测"。故**未重跑**，也未擅自扩预算。

<a id="p1-1-r2-bugs"></a>
## 四、本轮修正的自身缺陷（如实记录）

| # | 缺陷 | 如何发现 | 修正 |
|---|---|---|---|
| 1 | `wall_w` 复合模型锚点 z=1.1，注入器又叠加 part z → **整段围墙悬空 1.1 m** | 断言 (h) 报 `wall_w` 在 z=0.48 无截面 | 锚点 z 改 0 + `world_map` 加守卫（复合锚点 z 必须为 0，否则拒绝运行） |
| 2 | 断言 (b) 把 `composite_model_count = 0` 当布尔 → minimal 误判 FAIL | 断言自测 | 改为**显式列出**参与判定的布尔键 |
| 3 | `_footprint_extent` / `_obb_clearance` 假设实体有顶层 `size` → 复合体 KeyError | 断言自测 | 改为逐 part 的足迹距离 |
| 4 | 断言 (i) 用「实体中心距离」判环带 → 复合体口径错 | 断言自测 | 统一为 `safety_radius` 圆盘口径（与 `safety_shield.cpp` 一致） |
| 5 | 首轮在 `src/agc_task/src/scenario_reset.cpp` 改了注释（**越白名单**） | 自查 | **已回退**（`git diff` 为空） |

> 说明：第 2–4 项是**核查脚本自身的 bug**，不是产品缺陷；已全部修复并复跑通过。
> 第 1 项是**真实产品缺陷**（视觉/碰撞同源但位置错），已修复并加了启动期守卫。

<a id="p1-1-r2-notdone"></a>
## 五、未完成 / 进行中（**不谎报**）

| 项 | 状态 |
|---|---|
| GUI 全链 s04 × yard 达 `TRACKING_SUCCESS` | **未达成**（T2-7 失败；PX4 EKF 发散） |
| 空中安全层在 yard 上"实跑"存在可行解 | **静态已证**（106.4° 可行弧）；**实跑未证**（全链未起来） |
| 视觉识别 / 遮挡开启 | 未做（属 P1-4；`occlusion.enabled` 仍 false） |
| 用户"更精致"的进一步打磨（贴图 / mesh 材质） | 未做（**不能做**：禁止外部资产；ADR-0068 provenance） |

<a id="p1-1-r2-assumption"></a>
## 六、假设台账（K=4 熔断用）

| 假设 | 状态 | 判别实验 | 判别所需授权 |
|---|---|---|---|
| H1：T2-7 的 `air_hover_timeout` 由 PX4 EKF 发散（`ekf2 missing data` + odom x≈1032）导致，与 yard 几何无关 | **未排除**（强证据：odom 1000 m 级偏移、EKF 复位计数 0→9；但未做 minimal 对照） | 同 seed 跑 `world_map:=minimal` 的 full attempt，比对是否同样 hover 超时 | 1 次 GUI full attempt（当前预算已用尽，**需 Leader 追加**） |
| H2：EKF 发散是 PX4 共享 `build/` 状态污染（多次未清理的重启累积） | **未排除** | 用 `px4_run_root:=/tmp/agc-p1-1-px4-<ts>` 隔离每实例运行根后重跑 | 同上（1 次 GUI full attempt） |
| H3：GPU/D3D12 渲染后端在高负载下拖慢 EKF 初始化 | **已排除** | GUI 世界冒烟（同样 d3d12）稳定运行 >5 min，`/clock` 246 Hz | — |
| H4：yard 几何（19 实体膨胀盘）导致空中无解 | **已排除**（静态） | 环带可行弧 106.4° ≥90°，8 字净空 +0.48 m | — |

> **按当前授权，H1/H2 不可判别**：需至少 1 次 GUI full attempt（现预算 2 次中已用 1 次）。

<a id="p1-1-r2-next"></a>
## 七、下一轮建议

1. **追加 1–2 次 GUI full attempt**（最小追加授权），先做 H1 对照（minimal 同 seed），再做 H2 隔离跑。
2. 若 H1 成立（minimal 也 hover 超时）→ 结论是**既有 PX4 链路问题**，应在 P1-2 或专门排障轮处理，
   **不阻塞 P1-1 的几何验收**（P1-1 出口判据的"yard 上主场景跑通"仍需另轮补证）。
3. 若 H1 不成立（minimal 通、yard 不通）→ 才回看 yard 几何与安全层交互。

<a id="p1-1-r2-budget"></a>
## 八、累计预算消耗

| 项 | 首轮 | 本轮 | 合计 |
|---|---|---|---|
| `T1` 微观测 | 0 | 0 | **0 / 8** |
| `T2` colcon 全量 | 1（39.7 s） | 0 | 1 |
| `T2` 局部重构建 | 0 | 2（25.1 + 3.4 s） | 2 |
| `T2` GUI 世界冒烟 | 2（40 + 55 s） | 3（22 + 22 + 运行中） | 5 |
| `T2` GUI full attempt | **0** | **1（失败）** | **1 / 2** |
| 工程轮次 | 1 | 2 | 2 / 3（预登记） |
| 离线静态检查 | 若干（见首轮） | 30+ 次几何核验脚本（单次均 <10 s，总 <120 s） | 未超 1200 s 批次总量 |

<a id="p1-1-r2-addendum"></a>
## 九、追加：GUI 复开与截图（用户要求"重开 GUI 直接观看"）

- **GUI 当前运行中**：`gz sim -r .../tmp/agc_world_static_obstacles_yard.sdf`（渲染后端 `auto`→d3d12），
  无 PX4 / Agent 进程（未起全链，避免再次触发 EKF 问题影响观看）。
- 用户可在本机屏幕上直接看到：**无地面网格**、中央有塔（圆柱+顶平台+爬梯+航障灯球）、
  罐场（双罐+顶盖+连接管）、斜置薄板、集装箱、围墙（带墙垛）。
- 截图（真实运行画面，非示意图）：`experiments/demo/20261029-p1-1-yard-rework/round2-shots/`，
  其中 `yard_live_now.png` 为复开后的即时画面。
- 相机取景说明：`/gui/move_to/pose` 在多次调用后存在累积漂移（实测无法稳定对准中央），
  故截图里实体偏画面一侧；**这是取证视角问题，不是几何缺失**——19 个实体 / 44 个 link
  已在 `/tmp/agc_world_static_obstacles_yard.sdf` 中逐项核对（见 §四）。

## 十、离线护栏（本轮全部通过）

| 检查 | 结果 |
|---|---|
| `python3 tests/w6_geometry_check.py`（三图） | **PASS**（(a)–(o) 全过） |
| `python3 -m pytest src/agc_task/test/test_scene_config_invariants.py scripts/tests -q` | **88 passed**（1.40 s） |
| `python3 tests/docs_link_check.py` | **PASS**（活跃范围无断链） |
| `python3 scripts/adr_index.py --check` | **PASS**（与 105 篇一致） |
| `python3 tests/docs_tooling_check.py` | **PASS** |
