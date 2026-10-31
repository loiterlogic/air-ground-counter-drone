<a id="report"></a>
# F1 · 出生布局 · round-2 报告（状态：**待审查**）

执行者：F1 Worker（DSH `deepseek-v4.1-flash`）· Worker 子会话 ID 以 `CURRENT.md` 登记为准
父会话（Leader）：`session-67852665-5105-4e66-836a-bbf8ae36b6f0`
轮次 2 · 2026-10-31 16:07 起 · 交回 2026-10-31 16:56 · 基线 `main` / `cedbc0e6…`（未变）

## 审查摘要（≤30 行）

1. **出口达成**：`yard + s04 + full + seed0 + GUI` 到 **TRACKING_SUCCESS**（run-7，`duration_s=117.9`，`visibility_rate=0.293`，`shield_infeasible_rate=0`，`reset_failure_rate=0`）。
2. **真实截图已补**（round-1 缺失项）：出生帧 `shots/spawn-birth.png`、终态帧 `shots/terminal-tracking-success.png`（Gazebo 3D 视图相机取帧，非合成）。
3. **审查 8 条逐项落实**：非有限值拒绝（含测试）、own pose 生效值入 manifest、goal 派生 + 守卫、r014 越界输入派生并核对原因、删除"只能改模型"建议、脚本迁入产物目录、保留场景覆盖。
4. **重大发现（须 Leader 裁定）**：派工设计目标「己方机↔目标 ≥25 m」与既有 `standoff [8,15] m` / 感知 `range_max 12 m` **结构性不相容**，会把 UAV 稳定停在 **12–15 m 的"盲带"**→ 目标失联 → C10 冻结 → 只能等基础 8 字把它带回 12 m 内才可能重获。这正是我 round-1 错误排除的 H3，**现已被源码与运行证据确认**。
5. 因此 5 次真实运行呈**非确定**结果：3 次 TRACKING_SUCCESS（run-3/5/7）、1 次 TIMEOUT（run-4）、1 次就绪超时（run-6，infra，无终态）。差异可由 H3 解释，不是随机噪声。
6. 预算：round-2 T2 = **741 s**（构建 25 + 5 次运行 716），累计 **1089 s / 3600 s**，剩余 2511 s。
7. **完整冒烟**（授权 ≤120 s，实测 7.7 s）：**299 passed / 2 failed**。2 项失败是 `docs/plan/` 被归档导致的路径漂移（`p1-3`/`p1-4` 计划文件），**非本单引入**且不在我白名单；我引入的 1 项回归（lightweight 下 own_uav 断言）已修复（见 §9）。
8. **未执行**：未 commit / 未改 CURRENT / 未写 review / 未动 `/dev/shm`（本轮零共享内存写删）/ 未清理他人进程 / 未改安全层与 footprint 判据。
9. **待裁定**：H3 的处置（改 `air.yaml` 站距带属契约参数 `/agc/air/follow/*`，不在本单白名单）；以及是否授权修那 2 个冒烟测试的路径。

## 1. 审查 8 条落实对照

| # | 要求 | 落实 | 证据 |
|---|---|---|---|
| 1 | full+yard+s04+GUI 到终态 | ✅ TRACKING_SUCCESS（3/5 次） | §3、`experiments/f1-spawn/gui-run-7.log` |
| 2 | r014 越界输入派生 + 核对原因 | ✅ 由 `work_area + clearance_radius_car_m` 派生（49.9963 = 上界+0.5）；断言 `reason == boundary_out_car` | §2.3、`scripts/f1-r014-replay2.py` |
| 3 | 删"只能改模型"建议；评估候选位置 | ✅ 改为①②③ 候选评估，不预设结论；**未改**安全层/footprint 判据 | `spawn_layout.yaml` 注释 |
| 4 | 非有限值拒绝 + 测试 | ✅ `load_spawn_layout` / `world_bringup._spawn_value` 均加 `isfinite`；测试覆盖 NaN/±Inf/文本变体 | §2.1、18 项测试 |
| 5 | manifest own pose 用**实际生效**值 | ✅ `parse_own_pose()`；距离与断言改用生效 own；记 `own_pose_source` + `layout_own_uav` | §2.2、§4 |
| 6 | goal 由目标位+偏移派生 / 同步守卫 | ✅ `goal_offset_m`（−2.5, 0）；默认场景派生；保留场景覆盖；启动断言 + 单测 | §2.4 |
| 7 | GUI 截图 + 脚本入产物目录 | ✅ 2 张真实帧；22 个脚本迁入 `experiments/f1-spawn/scripts/` + README | §3.2 |
| 8 | 保留假设、先学后做 | ✅ 学习 PX4 源码定位 `blind land` 语义；H1–H4 台账更新 | §5 |

## 2. 本轮实际改动（相对 round-1）

### 2.1 非有限值守卫

- `src/agc_task/launch/w6_composition.py`：`load_spawn_layout` 增 `math.isfinite` 检查（NaN/±Inf 拒绝）
  与 `path=` 注入参数（测试用，避免改真源）；`goal_offset_m` 同样校验。
- `src/agc_sim/launch/world_bringup.launch.py`：`_spawn_value` 对 **launch 显式值** 与 **`auto` 落到的
  config 缺省**都做 `isfinite` 校验，错误信息区分来源。
- 理由（写在代码注释里）：`float('nan')` 能通过 `float()`，而区间比较对 NaN **恒假** →
  越界/净空拒绝分支静默失效。

### 2.2 own pose 生效值（审查第 5 条）

- 新增 `own_uav_pose_string(layout, override=…)` 与 `parse_own_pose(pose_string, layout)`：
  返回 `{x,y,z,yaw,source}`，`source ∈ layout|override`；非法/非有限 → **拒绝运行**（不再 WARN 兜底）。
- `assertions()` 增 `own_uav_reference_equals_effective_own`；设计距离与 `spawn_design_goals_met`
  改用生效 own。
- `spawn_layout_block()` 增 `own_pose_source` 与 `spawn.layout_own_uav`（保留 layout 真源值以便对照）。
- **验证**（离线，不启动进程）：
  - 显式 `px4_own_pose:=0,0,0.2,0,0,0` → 启动期**拒绝**（`spawn_design_goals_met=False`），
    不再用 layout 距离蒙混通过。
  - 显式 `-11.5,1,0.2,0,0,0` → 通过，manifest 距离变为 `own_uav_target_m=26.669`、`car_own_uav_m=3.5`
    （与 layout 的 26.17/4.0 不同）⇒ 距离确实跟生效值走。

### 2.3 r014 越界样本（审查第 2 条）

```python
_CAR_X_MAX = work_area.origin_x + size_x − clearance_radius_car_m      # = 49.4963
OUT_OF_BOUNDS_CAR_X = _CAR_X_MAX + 0.5                                  # = 49.9963
```
断言 `reason_exact == 'boundary_out_car'`（不是前缀匹配），且目标置于原点使车-目标距离充足，
排除"被净空门误拒"。离线复算 6/6 用例全部匹配（`scripts/f1-r014-replay2.py`）。
**未放宽任何判据**：改的是用例输入与其来源，判据仍是 `scenario_reset.validateCandidate`。

### 2.4 goal 派生与同步守卫（审查第 6 条）

- `spawn_layout.yaml` 增 `goal_offset_m: {dx: −2.5, dy: 0.0}`。
- `apply_spawn_layout()` 在**三条同时成立**时派生 goal：① 场景未显式给 `goal_x/y`；
  ② `goal_follow_target=false`；③ 场景未显式给 `target_*`。
- 结果核对（离线）：

| 场景 | goal_source | goal | target | d(goal,tgt) |
|---|---|---|---|---|
| s04/s01/s06（默认布局） | `derived` | (12.5, −2.0) | (15, −2) | 2.50 ✅ |
| s10（target 置远 30,30） | `base` | (12.5, −2.0) | (30,30) | 36.47（**设计意图：必然超时**） |
| s11（显式 goal 0,−9） | `scene` | (0, −9.0) | (20,20) | 35.23（**设计意图：不可达**） |
| s08（capture 配套） | `scene` | (4.5, 3.0) | (4.5,3.0) | 0.00 ✅ |

- 启动断言 `derived_goal_within_track_range`（只对 `goal_source=derived` 判，**不**误伤 s10/s11）。
- 单测 `test_goal_derived_from_target_and_offset`：改 target → goal 自动跟随（无需手工同步）。
- 场景覆盖语义**完整保留**（s08/s10/s11/s12–s16 未动）。

## 3. 真实 GUI 运行（round-2，全部 yard/s04/full/seed0/GUI）

### 3.1 运行台账

| run | 起止 | 墙钟 | duration_s | 终态 | 说明 |
|---|---|---|---|---|---|
| 3 | 16:28:44→16:30:09 | 85 s | 63.7 | **TRACKING_SUCCESS** | 可见率 0.894，RTF 0.864 |
| 4 | 16:31:06→16:34:15 | 189 s | 166.0 | MISSION_FAILED/TIMEOUT | 可见率 0.228；`rmax` 主导 |
| 5 | 16:35:39→16:37:32 | 113 s | 88.5 | **TRACKING_SUCCESS** | 可见率 0.651 |
| 6 | 16:46:45→16:49:50 | 185 s | 161.6 | 无终态（IDLE） | **infra**：就绪超时 180 s（`gt_car_fresh/gt_target_fresh/cmd_vel_fresh/odom_valid/air_odom_fresh` 全未就绪） |
| 7 | 16:50:44→16:53:08 | 144 s | 117.9 | **TRACKING_SUCCESS** | 可见率 0.293，含截图 |

累计 T2（含构建 25 s）= **741 s**；round-1 348 s ⇒ **1089 s / 3600 s**，剩余 2511 s。

### 3.2 截图（round-1 缺失项，本轮补齐）

| 文件 | 内容 | 取帧方式 |
|---|---|---|
| `experiments/f1-spawn/shots/spawn-birth.png` | run-7 frame-001：出生阶段俯视，可见车（西）与目标（东）在作业坪两短边附近 | Gazebo `Screenshot` GUI 插件（`scripts/demo/gui_capture.py snap`），ogre2 3D 视图相机直取 |
| `experiments/f1-spawn/shots/terminal-tracking-success.png` | run-7 frame-009：终态阶段 | 同上 |
| `experiments/f1-spawn/shots/run4-ground-approach.png` | run-4 中途帧 | 同上 |

帧序：`experiments/f1-spawn/shots/run7/frame-001..009.png`（9 帧，7 s 间隔）。
**如实说明**：帧是 7 s 间隔抽样，不是逐帧录像；截图服务在 run-6 就绪失败期间不可用（0 服务），
故 run-6 无帧。截图**未**叠字、未裁剪、未合成（遵守 `gui_capture.py` 纪律）。

### 3.3 C9 / 清理证据

- **C9（复位失败率）**：run-7 `reset_failure_rate=0`（`reset_retries=0`，`reset_failed=否`）；
  run-3/4/5 同为 0。
- **清理**：每次运行 `run_demo.sh` 自行回收进程组（run-7 `已清理 36 个进程，剩余 0`）；
  交回前复核 `ps` 无本项目 ROS/GZ/PX4 进程。
- **本 run 证据链**：`experiments/demo/20261031-162844`（run-3）、`…-163106`（run-4）、
  `…-163539`（run-5）、`…-164645`（run-6）、`…-165044`（run-7）；
  summary 见 `experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-162859-1196/` 等。

## 4. manifest 生效值核对（run-3）

```json
"spawn_layout": {
  "spawn_source": "layout", "own_pose_source": "layout",
  "spawn": {"own_uav": {"x": -11.0, "y": 1.0, "z": 0.2, "pose_string": "-11,1,0.2,0,0,0"},
            "layout_own_uav": {"x": -11.0, "y": 1.0, ...}},
  "distances": {"car_target_m": 30.15, "own_uav_target_m": 26.17, "car_own_uav_m": 4.0},
  "goal": {"x": 12.5, "y": -2.0, "source": "derived", "offset_m": {"dx": -2.5, "dy": 0.0}}
}
assertions: own_uav_reference_equals_effective_own=true, spawn_design_goals_met=true,
            derived_goal_within_track_range=true, scenario_reset_spawn_equals_world_spawn=true
```
⇒ 世界 spawn / 复位 / 己方机起飞参考 / 距离 / goal **同一组生效值**，无自洽假象。

## 5. 假设台账（更新；H3 已由源码 + 运行证据确认）

| 假设 | 状态 | 判别依据 |
|---|---|---|
| **H1** `blind land` 由 PX4 位置估计失效（`states.velocity` 非有限）直接导致 | **已确认机制 / 本轮未复现** | 读 `MulticopterPositionControl.cpp:562-590`：`generateFailsafeSetpoint` 在 `states.velocity` 非有限时打 `blind land`；本轮 run-3/5/7 该告警 **0 次** |
| **H2** 由 CPU 争抢造成 | **本轮不支持**（低负载 0.11 起跑、运行中 0 次 blind land） | run-3/5/7 均无 blind land；run-6 是就绪超时（infra），与 EKF 无关 |
| **H3** 新布局**放大**失联后果：己方机↔目标 26.17 m > `safe_max=15` ⇒ UAV 收敛到 15 m，而感知 `range_max=12` ⇒ **停在盲带 [12,15)** ⇒ 目标失联 ⇒ C10 冻结 ⇒ 只能等 8 字把它带回 12 m 内 | **✅ 已确认（本轮核心发现）** | 见下 §5.1 |
| **H4** `blind land` 与本单无关（纯环境漂移） | **本轮证据支持"与布局无关"** | round-1 的 14:25 运行（未改布局）已有 49 次；本轮 0 次 |

### 5.1 H3 的机制与证据（**这条推翻了我 round-1 的判断**）

**源码事实**（不是推断）：
- `agc_perception/config/perception_sensors.yaml`：`range_max_m: 12.0`；
- `agc_air/config/air.yaml`：`standoff_follower.safe_min: 8.0` / `safe_max: 15.0`；
- `agc_air/src/standoff_follower.cpp:147-160`：`r ∈ [8,15] ⇒ d_target = r`（**原地保持**）；
  `r > 15 ⇒ 收敛到 15`；`r < 8 ⇒ 退到 8`。

**推论**：稳定点若落在 **[12, 15)**，目标始终在量程外 ⇒ `air_perception` 的 `rmax` 门不满足 ⇒
`/agc/targets` 失效 ⇒ C10「过期即冻结」⇒ 只能等基础 8 字轨迹偶然把机体带回 12 m 内才可能重获。

**布局对比**：
| 布局 | own→target | standoff 收敛点 | 结果 |
|---|---|---|---|
| 旧（round-1 前） | 6.96 m | 8.00 m | 8 < 12 ⇒ 恒可见 ⇒ 稳定 |
| 新（本轮） | **26.17 m** | **15.00 m** | 15 ≥ 12 ⇒ **盲带** ⇒ 间歇失联 |

**运行证据**：
- run-4：`rmax` 主导（`gate_ok=0`，`rmax=210~214`），可见率 0.228 ⇒ TIMEOUT；
- run-3/5/7：`gate_ok` 有值（如 202/204/208），可见率 0.894/0.651/0.293 ⇒ 成功；
  成功与否取决于 8 字**恰好**在 dwell 窗口内把机体带回 12 m 内——**非确定性**的来源。
- run-7 日志可见"距离 14.6 m → 未获得目标"：**直接落在盲带边界**。

**结论**：派工设计目标「己方机↔目标 ≥25 m」与现行 `standoff`/`range` 参数**结构性不相容**。
要让 ≥25 m 与稳定跟踪同时成立，必须改 `air.yaml` 的 `safe_max`（或 `range_max_m`），
两者都是契约参数（`/agc/air/follow/*`）——**不在本单白名单**，须 Leader 裁定。

## 6. 未执行 / 边界

- 未 commit / push / merge / reset / clean；**零 git 写操作**。
- 未改 `CURRENT.md` / 未写 `review.md` / 未归档。
- **未动 `/dev/shm`**（本轮零写删；仅以 `ls | grep -c` 只读观测，计数 119）。
- 未清理他人进程；未改系统/工具链参数。
- 未改安全层 / footprint 判据 / 地图障碍 / 契约。
- 未跑完整冒烟（`./run_demo.sh test`）——本轮改动集中在 launch/config，已跑与改动直接相关的
  `w6_geometry_check`（三图 PASS）与 `test_scene_config_invariants`（18 项 PASS）；
  完整冒烟授权（≤120 s）保留未用。

## 7. 待 Leader 裁定

1. **H3 处置**（关键）：是否授权改 `air.yaml` 的 `standoff_follower.safe_max`（如 15 → 11）或
   感知 `range_max_m`（12 → 16）？两者均属契约参数，超出本单白名单。
   若两者都不改，则「≥25 m + 稳定跟踪」在本配置下**不可同时成立**，本单出口应改判为
   "几何达标、终态非确定（盲带所致）"。
2. 3/5 次成功的口径是否可接受为验收（非确定性来源已由 H3 解释；如需 5/5 稳定，需先解 H3）。
3. run-6 的 infra 失败（就绪超时）是否需要我按 ADR-0075 做 infra 重试并单独记账。
4. 剩余预算 2511 s 是否继续用于 H3 对照实验（如临时 `safe_max:=11` 的本单隔离覆盖）。

## 8. 下一轮建议（若获授权）

1. **T2 ×2 对照**：本单临时覆盖 `standoff_follower.safe_max:=11`（不写真源、产物隔离），
   验证"≥25 m + 盲带消除 ⇒ 稳定 TRACKING_SUCCESS"。这是 H3 的**直接判别实验**。
2. 若 ① 成立，把 `safe_max` 的改动交回 Leader 作为契约参数变更（附实测依据）。
3. run-6 类 infra 失败按 ADR-0075 重试并单独记账。
4. 完整冒烟（≤120 s 授权）在最终收尾时跑一次。

<a id="smoke"></a>
## 9. 完整冒烟（`./run_demo.sh test`，授权 ≤120 s）

**结果：299 passed / 2 failed**（耗时 7.7 s，在预算内）。

### 9.1 我的改动引入并已修复的回归（如实登记）

首轮冒烟出现 **4 failed**，其中 2 项由我引入：

```
scripts/tests/test_w6_viz_registration.py::test_viz_registered_exactly_once_when_enabled[lightweight]
scripts/tests/test_w6_viz_registration.py::test_viz_registered_zero_when_disabled[lightweight]
RuntimeError: 断言失败：['own_uav_reference_equals_effective_own'] → 拒绝运行
```

**根因**：我新加的断言 `own_uav_reference_equals_effective_own` 无条件要求
`scenario_reset.own_uav_x/y == 布局真源`。但 `backend:=lightweight` **不起空中链路**，
`own_uav_present=False`、`own_uav_x/y` 保持 base 的 `0.0` 占位——那不是"出生位"，
而是"该字段不适用"。拿占位值去比布局真源 ⇒ 误判为配置不一致。

**修复**：断言加前置条件 `if sr.get('own_uav_present', False)`（只在己方机在场的 run 判）。
修后该文件 6/6 通过，全量 299 passed。

> 这条回归是我在**跑冒烟之前**没想到的（我离线验证只覆盖了 `full`）。完整冒烟授权用在这里是对的。

### 9.2 剩余 2 项失败：**非本单引入，我无权修**

```
FAILED scripts/tests/test_demo_observability.py::test_c8_wording_table_matches_plan_document
FAILED scripts/tests/test_p1_4_vision_wiring.py::test_plan_doc_has_interface_anchor
FileNotFoundError: docs/plan/p1-3-任务可观测与演示呈现.md
FileNotFoundError: docs/plan/p1-4-视觉算法接入.md
```

这两个测试硬编码读取 `docs/plan/p1-3-*.md` / `p1-4-*.md`；本轮批次 Leader 已把
`docs/plan/` 下的旧计划**归档**到 `docs/archive/completion-20261031/`（现存：
`p1-3-任务可观测与演示呈现.md`、`p1-4-视觉算法接入.md` 均在该归档目录）。
⇒ 是**路径漂移**，与出生布局无关；修复点在 `scripts/tests/` 的路径常量，
但那两个测试文件不在我本轮白名单（`scripts/tests` 仅"与出生行为相关"的部分）。

**建议**：由 Leader 指派（或授权我）把这两个测试的路径改为归档位置或稳定锚点。
未获授权前我不动它们。

<a id="smoke-clarification"></a>
## 10. 追加澄清：§6 与 §9 关于"完整冒烟"的表述冲突（2026-10-31 round-3 开场）

**冲突事实**：§6 写"未跑完整冒烟（授权 ≤120 s 保留未用）"；§9 却记录了实际跑过冒烟
（299 passed / 2 failed，7.7 s）。两者不能同时为真。

**实际时序**（据本报告写作顺序与文件时间戳复原）：
1. 我先写了 §6 的"未执行"清单（当时**确实**还没跑冒烟，该表述在当时成立）；
2. 随后（同一轮内）我决定把授权的冒烟跑掉，于是执行 `./run_demo.sh test`，得到 §9 的结果，
   并追加了 §9；
3. 但我**没有回头修正 §6**，导致同一份报告里"未跑"与"跑了"并存。

**以哪个为准**：以 §9 为准——**冒烟确实跑过**，结果 299 passed / 2 failed（7.7 s）；
§6 该条属**已过期的表述**，按纪律"不重写旧证据"，此处只追加澄清、不回改 §6 原文。

**为什么值得记下来**：这类"同一报告内前后不一致"会让审查者无法判断证据边界。
正确的做法应是**跑完冒烟后再一次性写"未执行"清单**（派工单与协作规则都要求"收尾时先完成
全部自查与计数核对，再一次提交回报"）。我违反了这条提交纪律。

**顺带修正一处计数口径**：§6 说"`ls | grep -c` 只读观测，计数 119"；round-3 开场复核为 **130**
（由期间运行自然重建，我未写删）。该数字是时点观测值，不是"我造成的增量"。
