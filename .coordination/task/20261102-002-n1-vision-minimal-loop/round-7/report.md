<a id="report"></a>
# N1 · round-7 高度体系调研与安全回归定性（报告）

| 字段 | 值 |
|---|---|
| 领取时间 | `2026-11-02T17:03:40+08:00`（Asia/Shanghai） |
| 执行者 | `worker`（新建会话，接手 round-7；不继承 `18d8e00b` 的任何待办） |
| 子会话 ID | `7d4f6dcb-4653-4eb8-8db1-73732f9eb2ee` |
| 预算起点 | `2026-11-02T17:03:40+08:00`；总墙钟 7,200 s → 截止 `19:03:40` |
| 本轮性质 | **调研 + 回归定性**；非实施轮、非验收轮 |
| 状态 | **待审查** |

<a id="summary"></a>
## 一、审查摘要（≤30 行）

1. **A 项主交付**：[`docs/conventions/飞行高度分层与按地图定高.md`](../../../../docs/conventions/飞行高度分层与按地图定高.md#flight-altitude)（新增，唯一新增文档）。含高度五层语义分层、反无人机场景禁用固定轨迹的硬规则、按地图定高的推导公式、落地位置与复用清单、三图建议值、5 条待用户确认项。
2. **已复核 Leader 的 4 个高度参数**，且**实际是 5 个语义层**：`traj.height`（C1 八字几何）/ `takeoff_altitude_m` / `standoff_follower.height` / `cruise_alt_m`（目标机，相对 episode-origin NED），外加 **L3 = AGL 在本项目根本不存在**（无下视测距、无地形库）。四者当前都恰为 `2.5`/`2.0`，语义互不冒充。
3. **契约三分结论（已核实）**：改 `cruise_alt_m` **不动** C1；改 `takeoff_altitude_m` / `standoff_follower.height` **不动** C1；**只有**改 `traj.height` 才需要改 C1 + ADR-0008。三者是**独立参数**，`air.yaml` 里没有共用变量。
4. **`motion` 区分已核实**：`intruder_driver.py` 的 `motion` 只有 `static`/`linear`/`maneuver`，**不含真八字**；八字是**己方机**轨迹（`agc_control/plugins.xml` 的 `Figure8Trajectory`）。目标机从来没有八字。
5. **反无人机场景禁用固定轨迹 —— 技术上可行，已有通路**（独立复核）：`/agc/targets → standoff_follower → /agc/air/tracking_ref → trajectory_tracker → LQR → PX4`。禁用 Figure8 后**己方机高度由 `standoff_follower.height` 决定**，`traj.height` **不再影响该场景**（插件换成 `HoverTrajectory` 后 `traj.*` 整段不被读取）。⇒ "提高己方机高度"**只需改 `standoff_follower.height`**（+ 起飞高度配套），**不必动 C1**。
6. **发现一个未预料的结构性约束（本轮最重要的技术结论）**：抬高**不是免费的**，但**只有"两机同步抬升"才是免费的**——
   `dz = h_own − h_target` 不变 ⇒ 感知几何（量程球水平预算、视线俯仰角）**逐值不变**；
   只抬己方机则 `dz` 变大 ⇒ **K1 硬上界 `|dz| ≤ √(12² − 10.2²) = 6.32 m`**。抬到 12 m（若能越 `admin_block`）时水平预算只剩 6.63 m < 停止点 10.2 m，**感知直接失效**。
7. **`yard` 的"太低"必须按**作业包络**算，不是全图**：全图 `H_max = 10.55 m`（`admin_block`），但它距目标 32.29 m、**在包络外**。`s04`（静止）包络内最高只 **2.10 m**（`pipe_rack_e`，距目标 10.34 m）；**若目标平移到 x≈30（s02 形态），包络内最高升到 7.97 m（`tank_farm_e`）**。
8. **由此出一个必须用户裁定的冲突**：要越 7.97 m 需 `h_o ≥ 7.97 + c_clear`，而 K1 限 `h_o ≤ 2.009 + 6.321 = 8.330 m` ⇒ **垂直净空余量一旦 > 0.35 m，`yard` + 目标平移形态即不可行**。
9. **抬目标机撞捕获包络（K4）**：`applicable_max_alt_m = 2.009`、`jam_envelope_max_alt_m = 2.0`，均由网弹道 `(v0·sinθ)²/(2g)` 解出。目标机抬到 ~2 m 以上，`CAPTURE_NET`/`JAM_*` 立即 `kOutOfApplicableRange` ⇒ capture/jam 场景全变 `TIMEOUT`。要抬必须重标定网弹道（ADR-0011 口径）。
10. **安全层是二维的，抬高不替代避障**（已核代码）：`SafetyShield::apply` 只按 XY 圆盘约束，**不含 z**。⇒ 本规范明确分工：避障靠二维安全层，"飞得比楼高"是真实感/几何问题，二者不得互相冒充。
11. **B 项：`shield_infeasible_rate = 0.639` 不是空中安全层的不可行，是地面 `collision_monitor` 的代理口径**（`run_logger.cpp` 的 `proxy_v1`：STOP/SLOWDOWN 拍中前向扫描 ≤ 2.0 m 或 TTC < 1.0 s 的占比）。round-6 把它表述为"安全层不可行"是**口径误指**，本轮已核清。
12. **两次 run 可比性：配置完全相同**。`params_applied.yaml` 三个 run 的 sha256 **逐字节相同**（`ddc7d883…`），155 键零差异；manifest 的 16 个可比字段全同（含 `perception_path=vision`、`target_source=air_fusion`、`sensors_file=perception_sensors.yaml`、`world_map=minimal`、`seed=0`、`seed_protocol` 逐键相同）。**唯一差异**：155603 的 summary 无 `detector_backend` 键（该字段是它之后才落地的）。
13. **`collision_monitor` 侧在成功 run 几乎不触发**：155603（成功，headless）全程只有 **2 条**边沿（1 次 invalid-source stop + continue）；162101（失败）有 **29 条**、构成 8 个触发段，**最长一段 24.93 s**。
14. **关键纠错（影响时序结论）**：不能用 `summary.wall_start − summary.sim_start` 当墙钟↔仿真常数偏移——本 run 该偏移在 173 s 内**漂移 15.37 s**（隐含 RTF 0.911），常数偏移会把时间线**错位约 19 s**。本轮改用探针自带成对 `(rx_epoch, track_stamp)` 做分段内插，`b-causal-chain.json` 已按此重算并记录**为何拒绝另一口径**。
15. **因果链主因（有证据）**：视觉 goal 的 **x 轴误差随时间单调恶化**，末段 `dx mean +11.63 m`；1 Hz 采样的 goal 跳变 **53.7% 超过 planner 的 1.0 m 重规划阈值**（p95 = 22.32 m，max = 59.9 m，真值目标 2 s 位移 p50 仅 0.08 m）⇒ `placeholder_path_planner` 持续重规划、`ground_policy_rl` 的 `goal_mismatch` 门持续拒绝（162101 的 launch 日志里 **50 次拒绝**；155603 只有 19 次，且不在停止段）。
16. **C8 不可达的量化证据**：episode 窗口内视觉 goal 与**真值目标**的距离 p50 = **2.99 m**、p95 = 10.76 m；120/240（**50%**）的采样 **> `d_track=3.0 m`**。⇒ 即使车精确到达视觉 goal，`range_ok` 也有一半时间不成立，dwell 无法连续 3 s ⇒ `t_max=120 s` 到点 `TIMEOUT`。
17. **末段几何解释误差放大**：末段真值视线俯仰角 **−34.5°…−43.7°（40/40 全部低于 vfov 下沿 −35°）**、水平距离塌到 **2.8–3.8 m**（远低于 `safe_min=8.0`）。即己方机已贴到真目标约 4 m，处于"低头看不到、且已侵入安全间距带"的位形。
18. **不是"随机性"，是"同配置下的吸引子"**：155603/161832 两次成功、162101 一次失败，配置全同、seed 全同、git 全同；差异来自**视觉误差随时间的随机漂移是否恰好越过 `d_track`**。162101 的 `hold` 段更长（`HOLD_LAST_VALID` + `EXPIRED` 共 20/171 条 vs 成功 run 更少），放大了误差累积窗口。
19. **未执行项（如实标记）**：① 未跑任何仿真（T1=0，T2 未动用）；② 未改任何配置/代码/契约/地图；③ 未做 GUI 取证（环境无 X display，round-5/6 已裁定阻塞，本轮不重复）；④ 未验证"禁用 Figure8 后整链跑通"（需实施授权 + T2）。
20. **待用户确认 5 项**：`c_clear` 取值；是否接受"抬目标机 ⇒ 重标定网弹道"；`yard` 演示是否要"明显高于最高建筑"；是否把"禁用固定轨迹"做成启动断言；是否采纳 `flight_altitude` 派生注入方案。

<a id="deliverables"></a>
## 二、交付物清单

| 类型 | 路径 | 说明 |
|---|---|---|
| **新增文档（A3 主交付）** | [`docs/conventions/飞行高度分层与按地图定高.md`](../../../../docs/conventions/飞行高度分层与按地图定高.md#flight-altitude) | 唯一新增文档；五层语义、禁用固定轨迹硬规则、推导公式、落地位置、复用清单、三图建议值、5 条待确认 |
| 外部依据 | [`evidence/external-references.md`](evidence/external-references.md#external-references) | 14 条来源 + 检索无果项 + 外部→本项目映射的适用性边界 |
| 几何量化脚本 | [`evidence/height_survey.py`](evidence/height_survey.py) | 只读；经 `world_map.py` 单一清单解析三图 |
| 几何量化结果 | [`evidence/height-survey.json`](evidence/height-survey.json) | 三图 `H_max_map` / `H_max_env` / 安全圆盘重叠 / 感知几何表 |
| B 项分析脚本 | [`evidence/b_regression_analysis.py`](evidence/b_regression_analysis.py) | 只读；含时钟映射的正确做法与拒绝的另一口径 |
| 配置逐项比对 | [`evidence/run-config-compare.json`](evidence/run-config-compare.json) | 三 run × 16 字段，含 `_comparability` 判据 |
| 因果链 | [`evidence/b-causal-chain.json`](evidence/b-causal-chain.json) | 触发段、视觉 vs 真值（1 Hz）、goal 跳变 |
| 方位残差 | [`evidence/b-bearing-residual.json`](evidence/b-bearing-residual.json) | 同一平面下的方位一致性（排除"纯平面假设"解释） |
| 一 run 一证据包 | `evidence/run-{155603-2790,161832-2961,162101-7315}/` | 各含 `OWNERSHIP.md` + `summary-excerpt.json` + `manifest-excerpt.json` + `params_applied.sha256.txt` |
| 证据总校验 | [`evidence/SHA256SUMS.txt`](evidence/SHA256SUMS.txt) | 19 项，`sha256sum -c` **全 OK**（exit 0） |

> **证据包纪律**：三个 run **一 run 一目录**，各自 `OWNERSHIP.md` 写明 `run_id` / `launch_pid` / 归属依据 / 源文件绝对路径 + sha256。
> 跨 run 的比对只出现在 `run-config-compare.json` 与 `b-causal-chain.json`，**逐项带 run_id**，不混装。

<a id="task-a"></a>
## 三、任务 A：高度体系调研

### A0. 先纠正一处口径（影响所有后续结论）

Leader 提示"高度是四个变量"——**复核成立，但严格说是 5 个语义层，其中一层在本项目不存在**：

| 层 | 参数 | 位置 | 语义（**已核实**） |
|---|---|---|---|
| L0 | — | Gazebo `agc_world` | 世界 ENU z，+z 向上（唯一基准） |
| L1 | — | PX4 EKF2 local origin | 局部 NED，z **向下**；原点 = **EKF2 启动瞬间机位** |
| L2a | `cruise_alt_m` | `w6_base.yaml:135` + `scenarios.yaml:35,58` | **目标机**巡航高度，相对 **episode 原点**（epoch 后首帧 odom）的**上升量** |
| L2b | `standoff_follower.height` | `air.yaml:187` | 己方机**跟踪高度**，世界 ENU z（绝对） |
| L2c | `takeoff_controller.takeoff_altitude_m` | `air.yaml:35` | 己方机起飞高度，**相对起飞时刻机体高度**（`launch_point_.z + 本值`） |
| L2d | `trajectory_tracker.traj.height` | `air.yaml:113` | **C1 真八字几何高度**；因 `z_offset_` 是**层高基准**，它只决定"相对形状"，绝对高度由接管时机体高度决定 |
| **L3** | **不存在** | — | **AGL / 真高**。本项目无下视测距（`dist_bottom` 不可得）、无 SRTM 地形库 ⇒ **不可得** |

**关键点**：`air.yaml` 里 L2b/L2c/L2d **是三个独立键，没有共用变量**（已逐行核对 `air.yaml` 全文 + `trajectory_tracker.cpp` 的 `declare_param_idempotent`）。

### A1. "太低"到底是问题——量化

#### A1.1 当前值

| 量 | 值 | 真源 |
|---|---|---|
| 己方机起飞高度 | **2.5 m** | `air.yaml:35` |
| 己方机跟踪高度 | **2.5 m** | `air.yaml:187` |
| 目标机巡航高度 | **2.0 m**（相对 episode 原点） | `w6_base.yaml:135` |
| C1 八字几何高度 `h` | **2.5 m** | `air.yaml:113`（契约 C1） |
| `dz`（己方 − 目标） | 名义 **+0.5 m** | `air.yaml:159` 注释 |
| `dz`（**实测**，用 TF 反解） | **+2.487 m** | 见下 |

> **实测 vs 名义的重要差异**：`air.yaml:159` 的注释假设 `dz = 2.5 − 2.0 = 0.5 m`。
> 但 162101 末段 TF 显示相机世界 z ≈ **3.651 m**（− mount 0.242 ⇒ base_link ≈ **3.409 m**），
> 而同刻目标真值 z ≈ **0.923 m** ⇒ **实际 `dz ≈ +2.49 m`**，是名义值的 5 倍。
> 原因：己方机高度取**世界 ENU 绝对**，目标机取"相对 episode 原点"——**两个基准不同**，
> 名义 2.5/2.0 的差在本 run 并不等于真实的 0.5 m。**这正是"高度语义不分层"的活证据。**

#### A1.2 各地图最高障碍（**已独立复核**）

| 地图 | 全图 `H_max` | 最高实体 | 与八字足迹相交 | 目标 11.2 m 环带内 |
|---|---|---|---|---|
| `minimal` | **3.000 m** | `pole_1` / `pole_2`（0.3×0.3×3.0） | 无 | **无**（最近 `pole_2` 14.14 m） |
| `open_field` | **3.000 m** | `shed`（8×6×3.0） | 无 | **无**（最近 `cyl_2` 31.73 m） |
| `yard` | **10.550 m** | **`admin_block`**（复合体，`_ac` 檐口件最高） | 无 | **2.10 m**（`pipe_rack_e`，距目标 10.34 m）/ **7.97 m**（目标移到 x≈30 时 `tank_farm_e`） |

- Leader 初算的三个数（3.0 / 3.0 / 10.55）**全部复核正确**。
- **但"yard 上己方机 2.5 m 飞得比楼低"这条证据需要收窄**：`admin_block` 距目标 (15,−2) **32.29 m**、
  距八字足迹 **26.06 m**，**都在作业包络之外**。己方机根本不飞到它旁边。
  真正压在包络上的是 `pipe_rack_e`(2.10 m, s04，距目标 10.34 m) 与 `tank_farm_e`(7.97 m, 目标平移后，距 4.11 m)；
  且 `hut_s`(2.56 m) 只在环带外 0.11 m 处，**边界余量不足**，故建议值按它定（详见方法文档 [§6.1](../../../../docs/conventions/飞行高度分层与按地图定高.md#current-values)）。
  ⇒ 结论修正为：**"2.5 m 低于 10.55 m 的楼"是真实感/演示层面的硬证据，但不是当前的碰撞或感知瓶颈**。

#### A1.3 感知几何：高度怎么影响可见性

`perception_sensors.yaml`：`range_max_m = 12.0`、`hfov 100°`（±50°）、`vfov 70°`（±35°）、`boresight_body [1,0,0]`（前视）。
注意 `air_perception.cpp` 的距离门是**三维** `r = ‖target − uav‖`，而 `standoff_follower` 的收敛点是**水平**距离。

设 `S = safe_max − hysteresis = 11.2 − 1.0 = 10.2 m`（停止趋近点），`dz = h_own − h_target`：

- **K1（量程球）**：`√(R² − dz²) ≥ S` ⇔ `|dz| ≤ √(144 − 104.04) = 6.321 m`
- **K2（垂直视场）**：`|dz| ≤ S·tan35° = 7.142 m`（比 K1 松，K1 先绑定）

| `dz` | 水平预算 | 停止点在内？ | 俯仰角 @10.2 m | 视场 |
|---|---|---|---|---|
| +0.5 m（名义） | 11.99 | ✓ | +2.8° | ✓ |
| +2.49 m（**本 run 实测**） | 11.74 | ✓ | +13.8° | ✓ |
| +6.32 m | 10.20 | 临界 | +31.7° | ✓ |
| **+10.0 m**（只抬己方到 12 m） | **6.63** | **✗** | **+44.4°** | **✗** |

> **结论（反直觉但必须写明）**：**抬高己方机不提高可见性，反而降低**。
> 目标通常**低于**己方机，`dz` 越大视线越低头。**只有两机同步等量抬升**（`dz` 不变）时感知几何才逐值不变。

#### A1.4 安全层：二维，且抬高不替代避障

- `safe_min 8.0` / `safe_max 11.2` 是**水平**距离（`standoff_follower.cpp` 用 `std::hypot(delta.x(), delta.y())`）。
- 停止点 `11.2 − 1.0 = 10.2 m` 与安全层目标圆盘下界
  `target_min_dist 8.0 + target_margin 1.5 + (0.2×2.0 + 0.3)` = **10.20 m** **精确相切**（H0 结论复核成立，差 0.000 m）。
- **`SafetyShield::apply` 只构造 XY `Disk`，不含 z**（`safety_shield.cpp:162-190` 逐行核对）。
  ⇒ **抬高不会让飞机"越过"障碍**；圆盘约束照样把它推回。
- `air.yaml:159` 的 `dz = 2.5 − 2.0 = 0.5 m` 注释**需更新**：① 名义值不等于实测值（实测 +2.49 m）；
  ② 两个数的**基准不同**（绝对 vs 相对 episode 原点），写成一个减法会误导。

### A2. 换什么高度来源

#### A2.1 契约红线：三分结论（**已核实**）

| # | 对象 | 改它要不要动 C1？ | 依据 |
|---|---|---|---|
| 1 | **目标机** `cruise_alt_m` | **不要** | C1 只规定**真八字**（己方机）的 `rx/ry/h`；`cruise_alt_m` 是 `intruder_driver` 的参数，八字与目标机无关 |
| 2 | **己方机** `takeoff_altitude_m` / `standoff_follower.height` | **不要** | 两者是 L2c/L2b，与 `traj.height` 是**独立键**；C1 只约束 `traj.height` |
| 3 | **C1 的 `h = 2.5 m`**（`traj.height`） | **必须** 改契约 + ADR-0008 | C1 明文 `h=2.5 m`；ADR-0008 Consequences 首条"此为契约真源变更" |

**是否共用同一个变量？** **否。** `air.yaml` 中 `traj.height: 2.5`（:113）、`takeoff_altitude_m: 2.5`（:35）、
`standoff_follower.height: 2.5`（:187）是三个独立键，分属三个不同节点段；节点侧分别由
`ParametricTrajectory::configure`（读 `traj` ns）、`takeoff_controller`、`standoff_follower` **各自**声明，
**没有共享变量、没有从一处派生另一处**。

> **⇒ 在新裁定下（反无人机场景禁用固定轨迹），契约冲突降级**：改己方机高度只需动 L2b（+L2c 配套），
> **不需要动 C1**。本轮**未修改** C1 / ADR-0008 / 任何契约文本。

#### A2.2 「禁用固定轨迹后己方机参考由谁生成」——独立复核结论

**已存在的通路（逐条代码证据）**：

| 环节 | 代码锚点 | 事实 |
|---|---|---|
| 目标输入 | `standoff_follower.cpp:60-70` | 订阅 `target_topic="/agc/targets"` |
| 跟踪参考输出 | `standoff_follower.cpp:71-73` | 发布 `out_topic="/agc/air/tracking_ref"` |
| **高度来源** | `standoff_follower.cpp:169,175` | `standoff.z() = height_m_` / `ref.pos.z() = height_m_` —— **己方机跟踪高度只来自这里** |
| 高度前馈为零 | `standoff_follower.cpp:176-181` | 注释写明"高度参考速度必须为 0，否则双环振荡" |
| 参考消费 | `trajectory_tracker.cpp:184-188` | 订阅 `/agc/air/tracking_ref`，`tracking_ref_timeout_s_=0.5` |
| **参考来源裁定** | `trajectory_tracker.cpp:429-458` | `tracking`（参考+目标均新鲜）> `hold`（已获目标后失效）> `base`（插件兜底） |
| 兜底插件 | `trajectory_tracker.cpp:70-71` + `air.yaml:51` | `trajectory_plugin` 默认 `agc_control/Figure8Trajectory` |
| 兜底采样 | `trajectory_tracker.cpp:400` | `trajectory_->sample(t)` 仅在 `source=="base"` 时成为 `effective` |

**⇒ 三个明确回答**：

1. **禁用 Figure8 技术上可行，不需要新造接口**——感知驱动通路已存在且是**优先路径**。
2. **该场景己方机高度由 `standoff_follower.height`（L2b）决定**，不是 `traj.height`。
3. **`traj.height` 只在 `source=="base"` 时影响参考**（从未获目标，或 takeover 前）。禁用 Figure8 后
   兜底插件**必须换成 `HoverTrajectory`**（`HoverTrajectory::reset` 把 `hold_` 设为接管位置，
   `sample()` 恒返回该点 ⇒ 无运动），且换掉后 **`traj.*` 段（`height`/`rx`/`ry`/`speed`/`center_*`）全部失效**
   （`HoverTrajectory::configure` 只读 `use_hold_z` / `hold_z`）。

**是否仍需 `traj.height` 与 `standoff_follower.height` 一致？** ——**不建议一致，且建议刻意不一致**：
两者语义不同（一个是 C1 契约几何，一个是实际飞行高度）。若强令相等，一旦有人误把 Figure8 选回来，
"八字高度 = 跟踪高度"会让误用**不可辨认**（飞机平滑地飞走而不是明显跳变）。
**建议**：① 反无人机场景 `trajectory_plugin = HoverTrajectory`；② `traj.*` 保持 C1 原值 **2.5**（契约不动）；
③ `standoff_follower.height` 按地图给（与 2.5 不同）；④ 两者不等本身作为"没有走兜底"的可观测信号。
方法文档已按此写入（[§2](../../../../docs/conventions/飞行高度分层与按地图定高.md#no-fixed-trajectory)）。

#### A2.3 目标机高度来源的候选比较

| 候选 | 依据 | 代价 | 评价 |
|---|---|---|---|
| ① 用**真实状态估计**的 z（`/agc/targets` 的 z 分量 / `sigma_z`）替代固定平面 | `vision_target.cpp` 已输出 `z`（当前恒 = `plane_z_`）与协方差；`sigma_z_m=0.12` | 需**第二个观测源**提供 z（单目 + 固定平面**无法**测 z，这是几何事实）；若用真值 z 则违反 ADR-0009 的"感知不得读真值" | **当前不可行**：单目 + 单平面本质欠定。`/agc/targets` 的 `z` 现在是"输入"不是"观测" |
| ② 双目 / 多视角三角化 | 两台相机或运动视差 | 需新增传感器与标定；属**新能力**，不在 N1 范围 | **超出本轮范围**，且是"换感知体制"不是"换高度来源" |
| ③ 仅对**恒定高度**目标保留平面先验，**显式限定 N1 适用域** | round-6 已实测：`|z − 2.0| ≤ 0.10 m` 仅 1.67%、放宽到 0.50 m 才 26.7%；本 run 目标 z 在 0.90–2.00 间漂移 | **缩小 N1 声称范围**（代价诚实但真实） | **最可行**：不改体制、不改契约，只把"固定高度平面仅对固定高度目标有效"写进 N1 适用域 |

**推荐组合**：**③ 为基线 + ① 作为后续能力项**。理由：③ 立刻可做且诚实；① 需要第二观测源，须另立任务。
② 明确判为"不在本轮/本 N1 范围"。

**己方机**：`takeoff_altitude_m` 与 `standoff_follower.height` **应当随地图变化**——理由见任务 A3。

#### A2.4 一个必须记录的实现坑（浅合并）

`w6.launch.py:287-289` 的合并是 `air_merged[n].update(over)`，**浅合并**。实测：
场景写 `trajectory_tracker: {traj: {height: 10}}` 会把整个 `traj` 段**替换**成 `{height: 10}`，
`rx`/`ry`/`speed`/`center_*` **全部丢失**（已用静态模拟验证）。
⇒ 场景层改 `trajectory_plugin`（一级键）**安全**；改 `traj.*`（二级键）**危险**，必须写全段或走派生注入。

### A3. 不同地图固定不同高度——方法文档

已写 [`docs/conventions/飞行高度分层与按地图定高.md`](../../../../docs/conventions/飞行高度分层与按地图定高.md#flight-altitude)，
覆盖派工单要求的 5 点：

| 派工单要求 | 文档章节 | 核心内容 |
|---|---|---|
| ① 高度语义分层 | [§1](../../../../docs/conventions/飞行高度分层与按地图定高.md#layers) | L0/L1/L2a-d/L3 五层，逐层给唯一真源 + 消费者；**明确 L3(AGL) 不存在**（沿用 H0，不推翻） |
| ② 按地图定高的推导规则 | [§3](../../../../docs/conventions/飞行高度分层与按地图定高.md#rule) | 先算 **`H_max_env`**（作业包络内）而非 `H_max_map`；K1/K2/K3/K4 四条约束与不等式；**两机同步抬升是免费变换** |
| ③ 落到配置哪一层 | [§4](../../../../docs/conventions/飞行高度分层与按地图定高.md#where) | 建议写进**各地图几何文件**的 `flight_altitude` 五键；由 `w6_composition.apply_flight_altitude`（与既有 `apply_air_geometry` 同款同位置）派生注入；`air.yaml` 只留 standalone 兜底；四条启动断言 |
| ④ 新地图复用步骤 | [§5](../../../../docs/conventions/飞行高度分层与按地图定高.md#reuse) | 7 步清单：画图 → 算三数 → 定 `h_t`（先验 K4）→ 定 `h_o`（验 K1/K2）→ 填五键 → 跑 `w6_geometry_check` → 场景侧设 Hover + `cruise_alt_m` |
| ⑤ 三图建议值 | [§6](../../../../docs/conventions/飞行高度分层与按地图定高.md#current-values) | 见下表 |

#### A3.1 三张地图的建议值

| 地图 | `H_max_map` | `H_max_env`（s04 静止 / s02 目标平移） | 现 `h_o`/`h_t` | **建议** `h_o`/`h_t` | 需用户确认 |
|---|---|---|---|---|---|
| `minimal` | 3.00 m | **0 / 0** | 2.5 / 2.0 | **维持 2.5 / 2.0** | 否 |
| `open_field` | 3.00 m | **0 / 0** | 2.5 / 2.0 | **维持 2.5 / 2.0** | 否 |
| `yard` | 10.55 m | **2.10 / 7.97** | 2.5 / 2.0 | 静止：**3.5 / 2.0**（按边界外 0.11 m 的 `hut_s` 2.56 + `c_clear` 0.5）<br>平移：**见下冲突** | **是** |

**`yard` + 目标平移形态的不可行冲突（必须用户裁定）**：

```
K3:  h_o ≥ 7.97 + c_clear          （越过 tank_farm_e）
K1:  h_o ≤ h_t + 6.321 ≤ 2.009 + 6.321 = 8.330 m   （感知量程，h_t 受 K4 限制）
⇒ 可行当且仅当  c_clear ≤ 8.330 − 7.97 = 0.350 m
```

三条出路（**均需用户裁定，本轮不动**）：
① `c_clear ≤ 0.35 m`（极薄净空）；
② 约束目标路径不进入 `tank_farm_e` 包络（改场景/地图，属目标级变更）；
③ 抬目标机 —— **被 K4 2.009 m 挡住**，除非先按 ADR-0011 重标定网弹道。

<a id="task-b"></a>
## 四、任务 B：安全回归定性

### B1. 两次运行的可比性——**配置完全相同**

**最硬的证据**：三个 run 的 `params_applied.yaml` **sha256 逐字节相同** = `ddc7d883aac5610489e196e4ad32f11b87f05a30120d4992f3fb9c1f9c78d7a7`；
`diff` 两两为空；154 个参数键零差异。见各 run 目录的 `params_applied.sha256.txt`。

**逐项比对**（`run-config-compare.json` 的 `_comparability`）：

| 字段 | 155603（成功） | 161832（成功） | 162101（失败） | 相同？ |
|---|---|---|---|---|
| `perception_path` | vision | vision | vision | ✓ |
| `detector_backend` | **（无此键）** | synthetic_color | synthetic_color | 键存在性差异¹ |
| `target_source` | air_fusion | air_fusion | air_fusion | ✓ |
| `sensors_file` | perception_sensors.yaml | 同 | 同 | ✓ |
| `world_map` / `world_obstacles` | minimal / none | 同 | 同 | ✓ |
| `observe_yaw_mode` | velocity（air_yaml） | 同 | 同 | ✓ |
| `cruise_alt_m` / source | 2.0 / scene | 2.0 / scene | 2.0 / scene | ✓ |
| `vision_plane_z` / source | 2.0 / scene | 2.0 / scene | 2.0 / scene | ✓ |
| `scene` / `seed` / `backend` | s02_linear… / 0 / full | 同 | 同 | ✓ |
| `seed_protocol` | `{own:2462723854, intruder:38592188, warmup:1700723251}` | 同 | 同 | ✓ |
| `geometry_sha256` / `spawn_layout_sha256` | 同 | 同 | 同 | ✓ |
| `git_commit` | 49e099cc | 49e099cc | 49e099cc | ✓ |
| `episode_id` | 2 | 2 | 2 | ✓ |

¹ 155603 跑在 `detector_backend` 入 summary（round-6 的 C 项）**之前**，仅**元数据缺失**，不是配置差异。

**⇒ 结论：配置完全相同。差异只能来自运行时（视觉误差随时间的随机漂移）。**

> 补充：155603 与 162101 的 `duration_s` 差异极大（394.9 s vs 173.4 s）——155603 是 headless 且包含更长的预热/收尾，**不是**任务时长差异；任务时长由 `sim_end_s`（397.1 vs 179.0）与 episode 窗口（49.65 s vs 120.06 s）体现。

### B2. 不可行的直接成因

#### B2.1 先纠正口径（**这是本轮最关键的一处澄清**）

`shield_infeasible_rate = 0.639` **不是**空中 `safety_shield`（`trajectory_tracker` 的 `shield_infeasible`）的不可行率。
它来自 `run_logger.cpp` 的 **proxy_v1** 定义：

```
proxy_v1: triggered_ticks = 地面 collision_monitor 处于 STOP(1)/SLOWDOWN(2) 的拍
          infeasible_ticks = 上述拍中「前向扫描最小距离 ≤ contact_dist_m(2.0)
                                或 TTC = scan_min/v < ttc_min_s(1.0)」的拍
          shield_infeasible_rate = infeasible_ticks / triggered_ticks      (进程全时长)
          episode 窗口口径 = 同上，但只在 episode 窗口内、且只算 valid 拍
```

（源码：`run_logger.cpp:155-157`、`:973-1006`；前向锥 `forward_cone_rad = 0.9 rad ≈ ±51.6°`）

**⇒ 它的语义是"地面车被安全层拦下时，前向净空或 TTC 已不足的占比"，不是"空中安全层求不出可行解"。**
round-6 报告把它与空中安全层混述是**口径误指**，本轮已核清并写进 `b-causal-chain.json` 的 `infeasible_metric_semantics`。

#### B2.2 时间线（**已修正时钟映射**）

**纠错**：不能用 `summary.wall_start_unix_s − summary.sim_start_s` 当常数偏移。实测本 run 该偏移在
173.47 s 墙钟内**漂移 15.365 s**（隐含 RTF **0.9114**）；用它换算会把时间线**错位约 19 s**。
本轮改用探针自带的成对 `(rx_epoch 墙钟, track_stamp 仿真)`（1078 个锚点）做**分段线性内插**、
范围外按最近端点偏移**常数外推**。`b-causal-chain.json` 的 `evidence_ownership.clock_map` 记录了
方法与**拒绝另一口径的理由**。

`collision_monitor` 动作边沿（29 条）折成 8 个触发段：

| 起 | 止 | 时长 | 原因 |
|---|---|---|---|
| 9.02 | 10.92 | 1.90 s | invalid source（启动未就绪） |
| 76.90 | 77.70 | 0.80 s | SlowSafety 多边形（降速 30%） |
| 77.90 | 80.73 | 2.83 s | SlowSafety |
| 80.93 | 82.73 | 1.80 s | SlowSafety |
| **82.93** | **107.86** | **24.93 s** | **StopCollision 多边形（停车）** |
| 108.07 | 108.16 | 0.09 s | StopCollision |
| 162.59 | 162.62 | 0.03 s | invalid source |
| 174.47 | 174.51 | 0.04 s | invalid source |

**累计触发 ~32.4 s**（含启动段 1.9 s；纯任务段 ~30.5 s）。episode 窗口（31.11–151.18 s，120.06 s）内
`triggered_ticks = 914 / 3601 拍 ≈ 30.5 s`（30 Hz）——**与日志边沿完全对得上**（独立交叉验证）。

**对照成功 run（155603）**：全程只有 **2 条**边沿（1 次 invalid-source stop + continue），
**零 SlowSafety、零 StopCollision**。

#### B2.3 因果链：视觉航迹异常 → ground goal 偏移 → 车进入停止位形

**(a) 视觉航迹异常是否成立？** 成立，且**集中在 x 轴、随时间单调恶化**：

| 时段 | `dx` 均值 | `dy` 均值 | 误差 p50 | 误差 p95 | goal 跳变 > 1.0 m 占比 |
|---|---|---|---|---|---|
| 30–60 s | **+1.85 m** | +0.25 m | 3.72 m | 8.99 m | 48.3% |
| 60–100 s | +0.90 m | +0.26 m | 1.72 m | 6.31 m | 32.5% |
| 100–140 s | +3.62 m | −0.12 m | 4.17 m | 6.61 m | 55.0% |
| **140–178 s** | **+11.63 m** | −1.32 m | **7.07 m** | **33.57 m** | **78.9%** |

（1 Hz 对齐视觉 goal 与真值目标；数据出自 `probe-r6.json` 的 `pairing_chain.track_records` 与 `gt_target_samples`）

**(b) 异常是否传导到 ground goal？** 传导，且**逐拍**：

- `task_manager.publishGoal()`（`task_manager.cpp:786-812`）在 `goal_follow_target: true` 时
  **直接把目标位置当作车辆 goal**，`gx = target_x_; gy = target_y_`（**无任何合理性钳位**、不检工作区边界）。
- `placeholder_path_planner` 的重规划触发条件：`goal_moved > replan_displacement_m(1.0 m)`
  （`placeholder_path_planner.cpp:137-146`）。
- 实测 **53.7%** 的 1 Hz goal 采样跳变 > 1.0 m（p95 = 22.32 m，max = 59.9 m）；
  而**真值目标** 2 s 位移 p50 仅 **0.08 m**（受控 0.5 m/s，且大量时间静止）。
- `ground_policy_rl` 的质量门 `goal_consistent_with_path`（容差 `goal_consistency_m = 1.0`）
  因此持续拒绝：162101 的日志里 **50 次 `goal_mismatch` → 持续零速**；155603 只有 19 次且不在停止段。

**(c) 车是否真进入停止位形？** 是。24.93 s 的 StopCollision 段对应车被安全层停车；
该段内**视觉 track 与真值目标的误差中位数仅 1.13 m、p95 2.86 m**——即**视觉本身在这一段是好的**。
⇒ 停车的原因是**车的位置/朝向 + 周围障碍**，而不是此刻的视觉噪声。

**(d) 误差为何在末段放大？** 末段几何解释（40 个 TF 查询，t = 177.3–178.7 s）：

| 量 | 值 |
|---|---|
| 真值视线俯仰角 | **−34.5° … −43.7°**（**40/40 全部低于 vfov 下沿 −35°**） |
| 己方机↔真值目标 水平距离 | **2.8 – 3.8 m**（`safe_min = 8.0` ⇒ **已侵入安全间距带**） |
| 三维斜距 | 3.9 – 4.6 m |
| 同一平面 z=2.0 下"报告点 vs 真值射线交点"的残余 | p50 **10.14 m**、p95 54.98 m、max 65.43 m |

> 最后一行是**排除性证据**：平面假设的误差只能把点**沿射线移动**，**不能改变射线方向**。
> 因此在**同一平面**下比较仍差 10 m 量级 ⇒ 这**不是**（或不只是）"固定高度平面"造成的，
> 还有**方位（像素侧）**的不一致。round-6 的"平面假设主因"结论**不能单独成立**。
> 至于"方位侧"的具体机制（检测框中心偏移 / 相机内外参 / 目标成像尺寸小），**本轮未定位**，
> 需要能拿到原始检测框与图像的证据——本轮 T1=0、不跑仿真，**无法判定**（见 §六 未决项 V2）。

**(e) 因果链总结**：

```
视觉观测（单目 + 固定平面 2.0 m）
   │  目标实际 z 在 0.90–2.00 m 漂移（≠ 平面）
   ├─→ depth（沿射线）系统性放大  ──→ x 误差随时间恶化（末段 +11.6 m）
   │                                    │
   │                                    ├─→ goal 1 Hz 跳变 > 1.0 m（53.7%）
   │                                    │      └─→ planner 持续重规划
   │                                    │             └─→ ground_policy_rl goal_mismatch → 零速
   │                                    │
   │                                    └─→ goal 与真值目标距离 p50 2.99 m（> d_track 3.0 的占 50%）
   │                                           └─→ C8 range_ok 不成立 → dwell 无法连续 3 s
   │                                                  └─→ t_max = 120 s 到点 → TIMEOUT
   │
   └─→（另一条独立链）己方机也被同一错误目标牵着飞，末段贴到真值目标 ~4 m、
        视线俯仰 −35°…−44°（视场外），落入 StopCollision 位形（24.93 s）
```

**反证检查**：若"视觉是主因"，则成功 run 应无 `goal_mismatch` 高峰 —— 155603 只有 19 次（且不在停止段），
162101 有 50 次。方向一致。**但**：24.93 s 停车段内视觉误差中位仅 1.13 m，
说明**停车段的直接触发不是当刻视觉噪声**，而是"此前误差累积已把车带进停止位形"。
两条链**先分叉再合流**，报告不把二者说成同一件事。

### B3. 是否可复现

**离线结论**：`shield_infeasible_rate = 0.639` 在**同配置、同 seed、同 git** 下**不是确定性的**——
三次运行结果 2 成功 / 1 失败，且失败 run 与成功 run 的 `params_applied` **逐字节相同**。
⇒ 这是**"同配置下的吸引子"**：视觉误差的随机漂移是否越过 `d_track=3.0 m` 与 `goal_consistency_m=1.0` 决定结局。

**要确认可复现性，最小实验设计**（**本轮未执行，须申请**）：
- **必要性**：现有三次运行不足以给出失败率（n=3，2/1）。要给"失败率"需要 ≥10 次同类运行。
- 设计：`s02 + seed 0..9`（10 次），每次 `backend=full`、`perception_path=vision`、
  `detector_backend=synthetic_color`、`gz_args=-s`（headless，与 155603 同口径），
  单次 ≤ 900 s、一 run 一目录、每次记 `run_id`/`launch_pid`。
- 预算：10 × ~180 s 仿真 ≈ 1,800 s T2（**正好用满本轮剩余 T2 额度**，且无余量做二次验证）。
- 判据：失败率与 `shield_infeasible_rate` 的分布；若 ≥3/10 失败则"不稳定"成立。

> 本轮**不申请执行**：T2 只有 1,800 s、单次上限 900 s，且 B 项要求"先做离线分析"。离线已给出
> 定性的、有证据的因果链；"失败率"是**统计量**，需要用户裁定是否值得花掉全部 T2 余量。

**⚠ 一个限制（如实记录，影响 V1 的可比性设计）**：155603 的探针**没有 `pairing_chain` / `track_records`
/ `gt_target_samples`**（`probe-headless.json` 的 `pairing_chain` 为空字典），只有 `counts` 与
`status_last`。⇒ **成功 run 无法做本轮同款"视觉 vs 真值"1 Hz 对齐**，"失败 run 误差更大"这一条
只能靠 **"goal_mismatch 次数 19 vs 50"** 与 **"collision_monitor 边沿 2 vs 29"** 间接支持。
V1 的实验设计必须**统一探针**（都采 `pairing_chain` + `gt_target_samples`），否则 10 次运行仍不可比。
这是 round-6 教训（证据包不可比）在本轮的延伸，已写进方法文档的复用清单。

### B4. 与 round-5 成功运行的关系

| 维度 | 155603（成功） | 161832（成功） | 162101（失败） |
|---|---|---|---|
| 配置 | 相同（sha256 相同） | 同 | 同 |
| `seed` / `seed_protocol` | 0 / 同 | 同 | 同 |
| git commit | 49e099cc | 同 | 同 |
| `collision_monitor` 触发段 | **0**（仅 1 次启动 invalid-source） | 无日志可查 | **8 段**，最长 24.93 s |
| `goal_mismatch` 次数 | **19** | 无日志可查 | **50** |
| `visibility_rate`（窗口） | 0.8874 | 0.9269 | 0.9075 |
| `ticks_intervened / ticks_total` | 1122 / 1741 = 0.644 | 777 / 1492 = 0.521 | 2028 / 3601 = 0.563 |
| episode 窗口时长 | 49.65 s | 49.65 s | **120.06 s**（跑满 `t_max`） |
| 结局 | TRACKING_SUCCESS | TRACKING_SUCCESS | **MISSION_FAILED / TIMEOUT** |

**⇒ 答案是"随机性导致的时序差异"，不是"配置差异"，也不是"round-5 的质量更好"**：

1. **155603 之所以成功，一部分是"结束得早"**：它在 49.65 s 就达里程碑（`t_dwell=3.0 s` 连续满足），
   **没有进入误差恶化的后段**（误差在 t>120 s 才显著放大：`dx` 从 +3.62 跳到 +11.63）。
2. **162101 失败了 120 s（跑满 `t_max`）**，因而**暴露**了随时间的误差累积。
3. `visibility_rate` 三者接近（0.887/0.927/0.908）——**可见率不能区分成功与失败**；
   区分它们的是"**可见时的深度精度**"与"**持续时间**"。
4. ⚠ **可比性附带限制**：155603 是 **headless**（`gz_args=-s`），161832/162101 是 GUI 尝试失败后
   转 headless（`gui_render_backend:=auto`）。round-5 已记录"本会话无 X display"，三者
   **实际都是 headless**，但 155603 的 `gz_args` 显式带 `-s`、另两者不带——**渲染后端可能不同**。
   按契约 C3，GUI↔headless 等价核验**未做**；本条**不影响**配置比对（`params_applied` 相同），
   但**限制**"渲染差异是否影响检测"的推断（本轮不主张其影响，也未排除）。

<a id="resources"></a>
## 五、命令、退出码与资源账目

### 5.1 命令与退出码（全部只读 / 静态）

| # | 命令 | 退出码 | 产物 |
|---|---|---|---|
| 1 | `python3 evidence/height_survey.py > height-survey.json` | **0** | `height-survey.json` |
| 2 | `python3 evidence/b_regression_analysis.py` | **0** | `run-config-compare.json` + `b-causal-chain.json` |
| 3 | `python3 tests/docs_link_check.py` | **1**（既有断链 2 条，**非本轮引入**） | 见下 |
| 4 | `python3 tests/docs_tooling_check.py` | **0**（全部用例 PASS） | — |
| 5 | `sha256sum` / `diff` 三 run 的 `params_applied.yaml` | **0** | 逐字节相同 |

**#3 的说明（重要，避免误读为回归）**：`docs_link_check.py` 报"活跃范围断链 2 条"：
- `.coordination/CURRENT.md:33 → ../docs/adr/0019-….md#top` —— **既有**（ADR-0008 无 `#top` 锚点）；
- `docs/plan/无人机俯视相机.md:13 → 能力闭环裁定.md#r7` —— **既有**（该文件是 `??` 未跟踪的新文件，非本单产物）。
本轮新增的 `docs/conventions/飞行高度分层与按地图定高.md` **零断链**（首轮自查发现 25 条，已全部修正：
去掉不存在的 `#top` 锚点——本仓仅 13/111 个 ADR 有该锚点，非通用约定；修正两处 ADR 文件名；
`.coordination` 相对路径上两级；补 `#perception` / `#capture` 锚点）。
**本单不修**上面两条既有断链（不在白名单，且 `CURRENT.md` 禁区）。

### 5.2 资源账目

| 项 | 额度 | 实际使用 | 说明 |
|---|---|---|---|
| **墙钟** | 7,200 s | 见 §五.3 结算 | 自 `17:03:40` 起算 |
| **T2** | 1,800 s（单次 ≤900 s） | **0 s** | **未跑任何仿真**；理由：B 项离线已给出有证据的因果链，统计复现需 ≥10 次运行（≈1,800 s 全部余量），须用户裁定 |
| **T1** | **0** | **0** | 未启动任何 T1 |
| **静态/离线** | 900 s（单次 ≤30 s） | 全部命令单次 < 30 s，合计远低于 900 s | 纯 Python 只读脚本 + 文档检索 |
| **外部检索** | 无额度限制 | 14 条来源（含 3 条无果，已留痕） | 见 `external-references.md` |
| **仿真进程** | — | **0 个** | 未启动 gz / PX4 / launch / 任何 ROS 节点 |

### 5.3 墙钟结算

| 项 | 值 |
|---|---|
| 领取 | `2026-11-02T17:03:40+08:00` |
| 结束（本报告定稿） | `2026-11-02T17:49:09+08:00` |
| **已用墙钟** | **2,729 s / 7,200 s（37.9%）** |
| 剩余 | 4,471 s（**未使用**；本轮工作已完成，不空转） |

> **不空转的理由**：A 项已产出可复用的方法文档与三图建议值（含唯一需裁定的 `yard` 冲突）；
> B 项已给出有证据的因果链与"是否可复现"的最小实验设计。剩余时间能做的只有
> **V1（失败率统计）**——它需要 ≥10 次运行、要吃掉全部 T2 余量，且是**统计量**而非新机理，
> 按"判断再做也不会有新证据时就停"的纪律，本轮停在这里并把判决交给用户。

<a id="changes"></a>
## 六、实际改动（全部写操作）

### 6.1 新增文件

| 文件 | 类型 | 内容 |
|---|---|---|
| `docs/conventions/飞行高度分层与按地图定高.md` | **文档（A3 主交付）** | ~320 行；5 层语义 + 禁用固定轨迹硬规则 + K1-K4 + 落地位置 + 复用清单 + 三图建议 + 5 条待确认 |
| `round-7/report.md` | 报告 | 本文件 |
| `round-7/evidence/external-references.md` | 证据 | 14 条外部来源 + 检索无果项 + 映射边界 |
| `round-7/evidence/height_survey.py` | 脚本 | 只读几何量化 |
| `round-7/evidence/height-survey.json` | 证据 | 三图量化结果 |
| `round-7/evidence/b_regression_analysis.py` | 脚本 | 只读 B 项分析（含时钟映射纠错） |
| `round-7/evidence/run-config-compare.json` | 证据 | 三 run × 16 字段比对 |
| `round-7/evidence/b-causal-chain.json` | 证据 | 触发段 / 视觉 vs 真值 / goal 跳变 |
| `round-7/evidence/b-bearing-residual.json` | 证据 | 方位残差（排除纯平面解释） |
| `round-7/evidence/run-{155603-2790,161832-2961,162101-7315}/OWNERSHIP.md` | 证据 | 每 run 的归属声明 |
| `round-7/evidence/run-*/summary-excerpt.json` | 证据 | 该 run 的 summary 摘录 |
| `round-7/evidence/run-*/manifest-excerpt.json` | 证据 | 该 run 的 manifest 摘录 |
| `round-7/evidence/run-*/params_applied.sha256.txt` | 证据 | 该 run 的 `params_applied.yaml` 哈希 |

### 6.2 中间产物与返工（如实计入）

| 操作 | 说明 |
|---|---|
| 写了 3 个临时 Python 片段后又修正 | 首版几何脚本因复合模型锚点/类型错误崩了 3 次（`TypeError`），修正后成功；未留下垃圾文件 |
| `height-survey.err` | 脚本 stderr 空文件（首次运行时用 `2>` 创建）；保留以证明无告警 |
| **B 项时钟映射返工** | 初版用 `summary` 常数偏移得到"最长 27.888 s 停止段"，**错**；发现偏移漂移 15.37 s 后改用探针成对锚点内插，**修正为 24.93 s**，并把错误口径与拒绝理由写进 `b-causal-chain.json` |
| **conventions 文档断链返工** | 首版 25 条断链（12 条 `#top` 不存在 + 2 条 ADR 文件名错 + 5 条 `.coordination` 路径层级错 + 4 条锚点缺失 + 2 处任务 ID 笔误），全部修正后 0 条 |

### 6.3 **未**改动的（逐项确认）

- ❌ `src/agc_air/config/air.yaml`（**未动**：`traj.height` / `takeoff_altitude_m` / `standoff_follower.height` 全部原值）
- ❌ `src/agc_task/config/{scenarios,w6_base,spawn_layout}.yaml`
- ❌ `src/agc_sim/config/world_geometry.yaml` 与 `config/maps/*.yaml`
- ❌ `docs/ROS2迁移交接文档.md`（契约真源）、任何 `docs/adr/*.md`
- ❌ `src/agc_msgs/`、`task_manager.cpp`、`scenario_reset.cpp`、任何 `src/` 代码
- ❌ `.coordination/CURRENT.md`、`round-1..6` 记录
- ❌ 未归档、未派 N2/N3、未 `git stash`/`reset`/`clean`/`checkout`/`commit`/切分支

<a id="open"></a>
## 七、未决项与待用户确认

### 7.1 待用户裁定（影响后续实施）

| # | 事项 | 为什么必须用户定 | 建议 |
|---|---|---|---|
| **U1** | 垂直净空下限 `c_clear` 取多少 | 决定 `yard` + 目标平移形态是否可行（阈值 **0.35 m**）；本仓当前**无任何一层**守护垂直净空，属**新标定量** | 若不做目标平移，`c_clear = 0.5 m` 即可（`s04` 全绿） |
| **U2** | 是否接受"抬目标机 ⇒ 必须重标定网弹道" | 触及 ADR-0011 的包络口径（`applicable_max_alt_m` 由物理参数解出），非配置微调 | 建议**不抬目标机**，保持 2.0 m |
| **U3** | `yard` 演示要不要"明显高于最高建筑" | 会撞 K1（`dz≈9 m > 6.32 m` ⇒ 感知失效），必须同时抬目标机 + 重标定 | 若只是演示观感，建议改**相机视角/构图**而非改飞行高度 |
| **U4** | 是否把"反无人机场景禁用预设轨迹"做成启动断言 | 会**拒绝运行**，影响既有流程验证场景写法 | 建议做，但先确认哪些场景属"流程验证"白名单 |
| **U5** | 是否采纳 `flight_altitude` 派生注入方案（含 4 条断言） | 改 `w6_composition.py` + 3 个地图文件，属**实施授权** | 建议采纳；与既有 `apply_air_geometry` 同款，风险低 |

### 7.2 本轮未能判定（需更多授权）

| # | 事项 | 为什么判不了 | 最小追加授权 |
|---|---|---|---|
| **V1** | `shield_infeasible_rate` 的**失败率**（n=3 → 2 成功/1 失败，不足以给率） | 需要 ≥10 次同配置运行 | **T2 ≈1,800 s**（10 × ~180 s） |
| **V2** | 视觉误差的病根是"平面假设"还是"方位（像素/内外参）" | 同一平面下残余仍 p50 = 10.14 m，说明方位侧也有问题；但定位它需要**原始检测框 + 图像**，本轮 T1=0 取不到 | 需保留检测框的探针（可离线，T1 级）；或一次带 `--ros-args` 记录的 T2 |
| **V3** | "禁用 Figure8 + `HoverTrajectory`"整链是否跑通 | 需改配置 + 跑仿真，本轮禁止 | 实施授权 + T2 |
| **V4** | GUI↔headless 等价性（C3） | 环境无 X display（round-5/6 已裁定阻塞，无 root 无法解包 Xvfb） | **环境限制，非授权问题**；本轮未重复尝试 |

<a id="refs"></a>
## 八、引用与证据索引

- **本轮新增方法文档**：[飞行高度分层与按地图定高](../../../../docs/conventions/飞行高度分层与按地图定高.md#flight-altitude)
- 外部依据：[external-references.md](evidence/external-references.md#external-references)
- 几何量化：[height-survey.json](evidence/height-survey.json)（由 [height_survey.py](evidence/height_survey.py) 生成，exit 0）
- 配置比对：[run-config-compare.json](evidence/run-config-compare.json)
- 因果链：[b-causal-chain.json](evidence/b-causal-chain.json)（由 [b_regression_analysis.py](evidence/b_regression_analysis.py) 生成，exit 0）
- 方位残差：[b-bearing-residual.json](evidence/b-bearing-residual.json)
- **一 run 一证据包**：[run-155603-2790/](evidence/run-155603-2790/OWNERSHIP.md#ownership)、
  [run-161832-2961/](evidence/run-161832-2961/OWNERSHIP.md#ownership)、
  [run-162101-7315/](evidence/run-162101-7315/OWNERSHIP.md#ownership)
- 上游：[round-6 审查](../round-6/review.md#review)、[round-5 报告](../round-5/report.md#report)、
  [round-3 审查](../round-3/review.md#review)
- 契约与决策：[硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)、
  [ADR-0008](../../../../docs/adr/0008-air-trajectory-and-tracking-calibration.md#top)、
  [ADR-0011](../../../../docs/adr/0011-interception-and-fire-control.md#top)、
  [ADR-0010](../../../../docs/adr/0010-safety-thresholds-and-failsafe.md#top)、
  [ADR-0008](../../../../docs/adr/0008-air-trajectory-and-tracking-calibration.md#top)、
  [ADR-0009](../../../../docs/adr/0009-perception-truth-derived-and-vision-path.md#top)、
  [ADR-0007](../../../../docs/adr/0007-scene-geometry-single-source-and-layout.md#top)
