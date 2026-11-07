<a id="top"></a>
# 目标无人机运动规则与三主体速度体制

## Status

accepted（2026-11-04）

## 背景

本篇同时结档两条 plan：**目标无人机运动规则** 与 **速度调研与运行节奏优化**
（两者按 [任务计划规则](../plan/README.md#plan-index) 结档即删，结论只存在于本篇）。
它们共用 `intruder_driver` 与 `scenarios.yaml` 的同一批参数（目标机速度本身就是
运动规则的一部分），故合并为一条决策。

两个待解决的问题：

1. **目标机几乎只会悬停**。`scenarios.yaml` 的 18 个场景里 `static` 占 8 个，其余
   `linear`（6）/ `maneuver`（2）都只用 `speed_mps: 0.5`。演示上目标机要么不动、
   要么以 0.5 m/s 缓慢平移—— 不像"入侵者"。
2. **整体观感偏慢**。基线一轮 `duration_s 149.5`（sim 116.4 s，RTF 0.776）才到终态。

本轮**先反解再动手**：把四条下游影响链（感知 [硬约束 hc-10](0020-package-boundaries-and-runtime-topology.md#hc-10) / 跟踪安全带 / 火控提前量 / 网弹道）
逐条量化成不等式，再从约束**反解**速度，而不是先拍数再找理由。

<a id="constraints"></a>
## 决策前的反解（约束 → 数值）

### (a) 三条硬事实（代码/配置可复核）

| 事实 | 来源 |
|---|---|
| `gt_adapter`：`rate_hz 10`、`latency_s 0.2`、`drop_prob 0.1`、`sigma_xy 0.3`、`confidence 1.0`、**无几何门控** | `agc_perception/config/perception.yaml` |
| `standoff_follower`：`safe_min 8.0` / `safe_max 11.2` / `hyst 1.0` ⇒ 停止点 **10.2**；`max_step_m 0.1 @ 20 Hz` ⇒ **2.0 m/s** 水平上限 | `agc_air/config/air.yaml`、`standoff_follower.cpp` |
| yard 网弹道（12 m 派生）：`v0 15.81`、`θ 85°`、`t_land 3.211 s`、`vh = 1.240 m/s` | `composition.net_params_for_altitude` |

### (b) 四条影响链

**感知—— 目标速度不消耗预算**（预算是时间维度的）：

```
latency 0.2 + 采样周期 0.1 = 0.3 s < ref_max_age_s 0.5 s 余量 0.2 s（40%）
fit 窗口 1.5 s @10 Hz = 15 样本，drop 0.1 ⇒ 期望 13.5 ≥ min_samples 8 余量 5.5
样本位移 v·Δt = 1.0×0.1 = 0.1 m ≪ target_gate_m 1.0 m 余量 10×
```

⇒ 速度 0.5 → 1.0 **不改变任何感知门限的通过性**。速度影响感知的上界是
`v < gate_m/Δt = 10 m/s`（每拍位移不得触发新息门重置），与本次取值差一个量级。

**跟踪—— 闭合不等式**。初始站距 26.17 m，需收到 `safe_max 11.2` ⇒ 闭合 14.97 m，
闭合速率 `2.0 − v_t`：

```
t_close = 14.97/(2.0 − v_t) < t_max 120 s ⇒ v_t < 1.875 m/s ← "追得上"的硬上界
```

**火控—— 提前量**。网到达 12 m 的首次穿越 `t_f = 1.243 s`（解 `15.75t − 4.905t² = 12`）：

```
lead = v_t · 1.243 ≤ target_max_lead_m 1.5 ⇒ v_t ≤ 1.206 m/s ← 火控上界
```

超过它 `TargetMotionFilter::predicted` 会**截断**提前量，瞄准点落后目标
`1.243·v_t − 1.5`；`v_t=1.5` 时残差 0.36 m、网半径 0.5 ⇒ 余量只剩 0.14 m；
`v_t=2.0` 时残差 0.99 m ⇒ **必然打空**。下界 `2×static_eps = 0.30`（低于它被判静止）。

**网弹道—— 只由高度派生**，与水平速度无关；速度只经上面的提前量进入。
由此得一条**新约束**：新运动**不得加显著 z 运动**——`gateStatus` 用当前 `h = target.z`
预演，z 振幅 `A_z` 直接变成瞄准残差，要求 `A_z ≤ 0.5 − 0.2 = 0.3 m`。

<a id="speeds"></a>
### (c) 三主体速度（反解结果）

| 主体 | 取值 | 上界来源 | 余量 / 失效边界 |
|---|---|---|---|
| **车** | `reference 1.0` / `fast 1.3` / `max 1.5` —— **不变** | `max_offset 1.0` 在 1.3 m/s 满速下 3 次实测标定（1.017/1.083/1.287，取 min）；`max_linear_velocity 1.5` 是平台顶速 | 提 `fast>1.3` ⇒/「真实逃逸能力」标定失效 |
| **己方机** | `2.0 m/s`（`max_step_m 0.1@20Hz`）—— **不变** | 安全层下界 `8.0+1.5+0.2×2.0+0.3 = 10.2` **恰等于**停止点 `safe_max−hyst = 10.2` | 0（相切）；抬到 3.0 m/s ⇒ 下界 10.4 > 10.2 ⇒ 与 `safe_max` 冲突 |
| **目标机** | **1.0 m/s**（仅新运动场景；既有场景 0.5 不动） | 三条上界取最小：火控 1.206、车名义 1.0、闭合预算 1.011 | 火控 +0.206（17%）；车快速档 +0.3；闭合预算 +0.011（极薄） |

**闭合预算为什么只有 0.011 仍取 1.0**：因为**运动形状**把这条约束解开了。平移目标
（`linear`）要求车以 `1.3 − v_t` 闭合，`v_t=1.0` 时只剩 0.3 m/s、需 90 s，而实测可用
窗口 94 s—— 贴着极限。有界环绕的**质心不动**，车只需闭合到环绕区（`27.15 − r` @1.3
⇒ 16.3 s），余量 5×。**⇒ 选环绕类形状，不是选速度。**

<a id="motion"></a>
### (d) 运动规则：`epicycle`（漂移轨道）

```
c(t) = o + A·(sin(ω_c t), cos(ω_c t))， ω_c = 2π/T_drift
p(t) = c(t) + r·(cos(ω_o t), sin(ω_o t))，ω_o = v / r
```

取 `v=1.0 / r=1.8 / A=0.6 / T=30`。四条性质逐条对应验收：

| 性质 | 不等式 | 实测/余量 |
|---|---|---|
| **起点恒定** | `p(0) = (ox+r, oy+A)`（`sin0=0, cos0=1`） | 与 `_start_pose` 逐位相等 |
| **越界安全** | `max|p−o| ≤ A+r = 2.40` | ≪ `run_region_radius_m 15.0` ⇒ 夹持**永不触发** |
| **峰值速度** | `|dp/dt| ≤ Aω_c + rω_o = 0.126+1.000 = 1.126` | 解析上界 ≤ 1.206 ✓；**机体实测超限，见 (d)** |
| **dwell 可达** | `A+r+goal_tol = 2.40+0.3 = 2.70 < d_track 3.0` | 目标恒在车的 `d_track` 圆内 ⇒ 不触发 `RANGE_EXCEEDED` |

**为什么是它、不是另外四个候选**：

| 候选 | 否决理由 |
|---|---|
| M1 定常圆周（= 现有 `maneuver`） | 已存在，**不产生新轴取值** ⇒ 不满足"当前有消费者" |
| M3 多航点折线 | 顶点处**速度方向跳变** ⇒ 火控回归窗口出现阶跃；车必须停走 ⇒ `t_dwell 3.0` 反复被打断 |
| M4 高度正弦 | 水平静止 ⇒ 位移包络不达标；且 `A_z` 直接吃网半径余量（见 (b) 网弹道） |
| M5 规避式（远离己方机） | 需**新订 `/agc/air/odom`** ⇒ 非确定性 + 新耦合，与/可复现纪律冲突；且按构造最大化闭合时间 ⇒ 必然超 `t_max` |

**参数命名纪律**（写进 `base.yaml` 与代码注释）：`drift_amplitude_m` 是**圆心**的漂移幅度，
**不是**轨道半径；轨道半径仍是 `radius_m`。合成位移上界 = 两者之和。

<a id="start-protocol"></a>
### (e) 起点协议兼容性（关键，曾被误判为阻塞）

**表面矛盾**：`_maybe_start` 要求 `speed ≤ start_vel_eps_mps 0.35` 持续 `start_dwell_s`；
而 `epicycle` 在 `t=0` 的切线速度是 `|dp/dt(0)| = hypot(Aω_c, v) ≈ 1.008 m/s`，**远大于 0.35**。
看起来"永远无法满足 ⇒ `t0_` 恒 None ⇒ 目标机停在起始点不动"。

**实际不成立**，推理链：

1. `_tick` 在 `t0_ is None` 时发的是 `_start_pose`——**常量**，不是 `_target(now)`；
2. 位置 setpoint 恒定 ⇒ 机体收敛到该点 ⇒ `speed_`（来自 odom 实测）**趋于 0**；
3. 故 `_maybe_start` 的 `speed ≤ 0.35` 判据**能满足**，`t0_` 被正常记录；
4. 轨迹的切线速度只在 `t0_` 记录**之后**才被真正执行。

**这不是 `epicycle` 特有的**：`maneuver` 在 `t=0` 同样有切向速度（`v=0.5`），历史上能跑通，
原因完全相同。**本运动只是把该机制写成了显式结论**，并加单测锁死
`_start_pose` 对 t 是常量（四种运动全测）—— 防止将来有人把它改成依赖 t，
那会让 setpoint 在 episode 开始前漂走、机体永远追不上，表现为"目标机不动"且**日志无异常**。

<a id="learning"></a>
## 先学后做：外部实现对照

对照对象是 PX4 官方实现（`toolchain/PX4-Autopilot/`，只读）与 MAVLink 语义。三条结论直接影响
本仓的选择：

### (a) `TrajectorySetpoint` 是**逐字段**语义，不是"模式选择"

`msg/TrajectorySetpoint.msg` 同时含 `position` / `velocity` / `acceleration` / `jerk`，
文件头写明「setting a value to **NaN** means the state should not be controlled」。
`mc_pos_control/PositionControl/PositionControl.cpp` 据此实现：

```cpp
const trajectory_setpoint_s empty_trajectory_setpoint =
    {0, {NAN,NAN,NAN}, {NAN,NAN,NAN}, {NAN,NAN,NAN}, {NAN,NAN,NAN}, NAN, NAN};
// _positionControl:
Vector3f vel_sp_position = (_pos_sp - _pos).emult(_gain_pos_p);
ControlMath::addIfNotNanVector3f(_vel_sp, vel_sp_position); // NaN ⇒ 不施加影响
```

即**位置环把位置误差折成速度前馈，再与外部速度 setpoint 相加**；任一侧 NaN 即不参与。
⇒ 位置与速度**不是互斥模式**，而是同一条链上的两个可独立留空的字段。

### (b) Offboard 的存活判据是"模式位 + 新鲜度"，与 setpoint 内容无关

`commander/HealthAndArmingChecks/checks/offboardCheck.cpp`：

```cpp
bool offboard_available = (ocm.position || ocm.velocity || ocm.acceleration || ...)
                          && data_is_recent; // hrt_absolute_time < ocm.timestamp + COM_OF_LOSS_T
reporter.failsafeFlags.offboard_control_signal_lost = !offboard_available;
```

⇒ **停发 `OffboardControlMode` 就会触发 offboard-loss**，无论最后一帧 setpoint 是什么。
本仓 `intruder_driver` 的干扰路径正是依赖这一点（`jammed_` ⇒ 停发流 ⇒ PX4 offboard-loss，
/ADR-0015），**不是** data-link-loss。

### (c) MAVLink `SET_POSITION_TARGET_LOCAL_NED` 的 `type_mask` = 逐字段 IGNORE

`mavlink_receiver.cpp` 把 `POSITION_TARGET_TYPEMASK_X_IGNORE` 等位**逐字段**翻译成 NaN：

```cpp
setpoint.position[0] = (type_mask & POSITION_TARGET_TYPEMASK_X_IGNORE) ? NAN : x;
setpoint.velocity[0] = (type_mask & POSITION_TARGET_TYPEMASK_VX_IGNORE) ? NAN : vx;
```

⇒ **"位置 vs 速度 setpoint 之争"在实现层是伪命题**：协议本来就允许任意子集，
所谓"争议"来自**上层怎么用**—— 位置 setpoint 会**掩盖速度语义**（机体的实际速度由位置环
隐式决定，不再是你指定的那个），这正是本仓需要警惕的点。

### (d) 对本仓的直接含义

本仓 `intruder_driver` 用**纯位置 setpoint**（`sp.position`，`sp.yaw=0`），速度/加速度字段
留默认 0—— 按上面的语义，这等价于"速度前馈 = 0，只走位置环"。三条后果：

1. **轨迹的解析速度不会被执行器精确复现**，机体速度由位置环增益与 PX4 限幅（`MPC_XY_VEL_MAX`
   默认 12 m/s，远大于本仓 1.0）共同决定。故本 ADR 的"峰值速度上界 1.126"是**参考轨迹**的
   上界，不是机体实测速度的上界—— 后者需 GT 实测（见 Consequences 的未完成项）。
2. **不引入速度前馈是正确的**：`standoff_follower.cpp` 的注释记录了照搬 `move * rate_hz_`
   造成 ±13 m/s 垂直前馈、机体剧烈振荡的实测教训。位置-only 对本任务足够。
3. **`epicycle` 的 C∞ 光滑性是必要的**：位置 setpoint 有跳变时，位置环会把跳变折成
   速度前馈尖峰。折线（M3）被否，除了 dwell 冲突，这也是原因之一。

<a id="not-doing"></a>
## 不做什么

- **不改 `traj.speed`（契约的 2.0 m/s）**。反无人机场景的 `trajectory_plugin` 是
  `agc_control/HoverTrajectory`，其 `initialize` 只读 `use_hold_z` / `hold_z`，
  **`traj.*` 整段不被读取**（`agc_control/src/trajectory_generators.cpp`；
  另有 `test_counter_uav_scenes_declare_non_motion_trajectory` 守护）。改它 = 改契约换零运行时收益。
- **不改任何判据阈值**：`d_track_m 3.0` / `t_dwell_s 3.0` / [硬约束 hc-2](0020-package-boundaries-and-runtime-topology.md#hc-2) `max_offset 1.0` /
  `safe_max 11.2` / 网弹道参数，**逐项不变**（理由见 (c) 的"上界来源"列）。
- **不提车与己方机速度**（理由见 (c)）。
- **不做** RL 训练、不引入新依赖、不改感知链路、不新增 `xxx_mode/xxx_source/xxx_path` 类 launch 参数。
- **不做**"目标快于己方机 2.0 m/s"的场景档：那必然跟丢（`v_t > 1.875` 即超时），
  不是能力展示而是失败演示。

## Consequences

<a id="consequences"></a>
<a id="why-s18-is-stable"></a>
### (a0) `s18` 比 `s04` 快 2.2 倍——**但这不是"机动目标更好跟"**

实测（同 seed 0、同地图 yard、同 `t_max_s 120`）：

| 场景 | 终态 | `duration_s` | sim 窗口 | RTF |
|---|---|---|---|---|
| `s04`（static，基线） | `MISSION_FAILED / TIMEOUT` | 165.7 | 158.7 s | 0.958 |
| `s18`（epicycle） | `TRACKING_SUCCESS` | **72.6 / 74.1 / 75.7**（3 次） | ~70 s | 0.92–0.94 |

**必须按下面这个口径读，否则是自我美化**：`s18` 之所以稳，**不是**因为"运动更真实所以更好跟"，
而是因为它的位移被限制在一个小的有界圆内：

```
A + r + goal_tol = 0.6 + 1.8 + 0.3 = 2.70 m < d_track_m = 3.0 m （余量 0.30 m）
```

⇒ 目标**恒在车的 `d_track` 圆内**，`target_xy_distance` 不会周期性越过 3.0，
`RANGE_EXCEEDED` 清零 dwell 的机制（见 (d) 的实测根因）**根本不会被触发**。

换句话说：`s18` 是**绕开**了一个既有缺陷，而不是证明了新运动在能力上更优。
若将来修好 `d_track` 的边界滞回，`s04` 与 `s18` 的差距应显著缩小——
**那时才能比较运动规则本身的优劣**。当前数据**不支持**任何"epicycle 优于 static"的结论。

### (a) 新增的适用边界

1. `epicycle` 要求 `drift_amplitude_m + radius_m + goal_tol < d_track_m`。
   当前 `0.6+1.8+0.3 = 2.70 < 3.0`，**余量仅 0.30 m**—— 调大任一项都要重验 dwell 可达性。
2. `epicycle` 的峰值速度上界 `A·2π/T + v ≤ 1.206`。调 `drift_amplitude_m` / `drift_period_s`
   时该不等式必须重新成立。
3. 目标机 1.0 m/s 的失效边界：`>1.206` 火控提前量截断；`>1.875` 己方机追不上（冻结）；
   `>2.0` 必然跟丢。**当前不提供**超过 1.206 的场景档。

### (b) 对既有 ADR 的影响

- [ADR-0008](0008-air-trajectory-and-tracking-calibration.md#top)（八字轨迹）：**无影响**。
  该 ADR 的轨迹在反无人机场景本就不被读取；`traj.speed` 保持 2.0 未改。
- [ADR-0010](0010-safety-thresholds-and-failsafe.md#top)（与逃逸标定）：**无影响**。
  车速度未改，`max_offset 1.0` 的标定前提（1.3 m/s 满速）仍成立。
- [ADR-0011](0011-interception-and-fire-control.md#top)（网弹道与火控门）：**无影响**。
  网参数不变；目标速度 1.0 在提前量上界内（1.243 m < 1.5 m）。
- [ADR-0014](0014-task-fsm-and-scenario-transaction.md#top)（FSM 与 `T_max`）：**无影响**。
- [ADR-0018](0018-acceptance-and-coverage-matrix.md#top)（验收矩阵）：新增 `target_motion=epicycle`
  轴取值，**不改**既有格。

### (c) 回滚方式

- 删 `scenarios.yaml` 的 `s18` 块 + `scenario_carriers.yaml` 的 `epicycle` 条目
  ⇒ `carrier_entry` 会对声明该轴值的场景**拒绝运行**（不会静默降级）；
- `intruder_driver._target` 删 `epicycle` 分支 ⇒ 未知 `motion` 回落 `static`（既有兜底行为）；
- `base.yaml` 删 `drift_amplitude_m` / `drift_period_s` 两键。
三者互相独立，任一单独回滚都不会破坏其余两种运动。

### (d) 已知未完成 / 未验证

- **机体实测速度已测，且**超过参考上界**（如实登记，不是"达标"）**。

  **数字的唯一来源 = 可复现脚本**：
  ```
  python3 experiments/target-motion-speed/analyze_traj.py
  ```
  它读 `traj-s18.csv`（`/agc/gt/intruder_uav` @30 Hz，1100 帧）并打印全部口径。
  **本 ADR 的所有速度数字都取自该脚本输出**，不得手抄或另算。

  **数据边界（先讲清，否则会误读）**：该 CSV 的 `t` 是**墙钟 epoch 秒**，
  且只覆盖 **36.65 s**（记录器 `--duration 130` 只截到 run 前段），
  **不含完整 episode**（run 的 sim 窗口约 70 s）。

  **窗口定义（显式，这是可复现的前提）**：
  * `air` = `z > (z_min+z_max)/2 = 6.050 m` 的帧（剔除地面与起飞爬升主体）⇒ 900 帧；
  * `steady` = `air` 中**第一个"连续 10 帧 |Δz| < 0.05 m"** 的位置之后
    （即**高度已稳定**，爬升完成）⇒ 跳过 50 帧，得 **850 帧 / 28.32 s**。
  * 速度 = **中心差分** `|p[i+1]−p[i−1]|/(t[i+1]−t[i−1])`（主口径），另给前向差分与 1 s 平滑作对照。

  | 口径 | median | p95 | max | frac > 1.206 |
  |---|---|---|---|---|
  | **中心差分（主口径）** | **0.931** | **1.285** | **1.459** | **14.0%** |
  | 前向相邻差分 | 1.008 | 1.357 | 1.525 | 22.6% |
  | 1 s 平滑后中心差分 | 0.941 | 1.254 | 1.440 | 7.3% |

  **对照**：参考轨迹均值 1.000 m/s、解析峰值上界 1.126 m/s、火控上界 1.206 m/s。

  **解释**（机理，不是辩解）：位置-only setpoint 下，机体速度由 PX4 位置环响应决定，
  **不等于**参考轨迹的解析速度。转弯处位置环需要额外加速度，机体实际速度会**冲过**
  参考速度再回落—— 这正是"先学后做"(d) 预判的「位置 setpoint 掩盖速度语义」。

  **对本 ADR 结论的影响**：`epicycle` 的**参考轨迹**满足 `≤1.206`，
  但**机体**在三种口径下 max 均超 1.206（1.44–1.53），超限帧占比 7%–23%。
  这**不改变**捕获结论（`s08`/`s13` 仍 `CAPTURE_NET`，且它们用的是 static/linear），
  但意味着 **`epicycle` 场景下火控提前量余量比解析值更薄**。
  若要在 `epicycle` 场景下授权射击，**必须先重标**这一项，不得直接套用 1.206 的推导。
  当前 `s18` 是 tracking 场景（未授权射击），故不构成实际风险。

  > **口径分歧如实保留**：不同平滑窗口会得到不同的 `max`（1.44–1.53）与超限占比（7%–23%）。
  > **三者都超过 1.206**，故"超限"这个定性结论对口径不敏感；但**具体数值必须注明口径**。

- **A3 位移包络实测 2.622 m vs 解析上界 2.40 m**：超出 0.22 m（9.2%），属执行器跟踪误差
  （位置环超调，与上面的速度超限同源）。仍远小于 `run_region_radius_m=15.0`，夹持未触发。
  数字取自同一脚本（`analyze_traj.py` 的 `envelope_m`），窗口同 `steady`。
- **`epicycle` 的 `drift_*` 两键未进 manifest 的 `effective_params`**：`composition.py`
  的 `intruder_driver` 白名单只列 `motion/speed_mps/radius_m`。补进去需改该文件，
  不在本批次白名单内，**留给后续**（当前可由 `params_applied.yaml` 还原）。
- **`s04` 基线的既有不稳定**（与本 ADR 无关，但同批发现并**已取证**）。

  **失败模式必须分开统计**（合并成一个"成功率"会把三种不同病因压成一个数字）：

  | 终态 | 次数 | 含义 |
  |---|---|---|
  | `TRACKING_SUCCESS` | 3 | 正常达成 |
  | `MISSION_FAILED / TIMEOUT` | 2 | 任务时限内未攒满 dwell |
  | `IDLE` | 3 | 未进入任务（启动/门禁问题，**不是** TIMEOUT） |
  | `INFRA_FAILURE` | 1 | 基础设施失败（**不是**能力失败） |
  | 无 summary | 1 | 进程异常退出 |

  **`TIMEOUT` 的根因已由 `dwell_event` 实测证实**（`experiments/target-motion-speed/dwell-s04b.jsonl`）：
  一次成功 run（`r7`，`TRACKING_SUCCESS`）里捕获 **15 次 `DWELL_START` + 14 次 `DWELL_INTERRUPT`，
  全部 `reason=RANGE_EXCEEDED`**；分段有效时长为
  `0.30 / 0.70 / 0.50 / 0.60 / 2.88 / 0.50 / 0.10 / 0.97 / 0.38 / 0.60 / 1.20 / 2.40 / 1.60 / 1.40 s`。
  **最长一段 2.884 s，距 `t_dwell_s=3.0` 只差 0.116 s**—— 第 15 次才终于攒满。
  同配置的另一次 run（`r6`）则以 `MISSION_FAILED/TIMEOUT` 结束。

  ⇒ 机理：车在 `d_track=3.0` 边界附近，`target_xy_distance` 在 2.0–3.2 m 间抖动，
  每越过 3.0 一次就把已累计的 dwell 清零（`task_manager.cpp` 的逐拍 `RANGE_EXCEEDED` 判据），
  **能否成功取决于"哪一次恰好没被清零"**。这是**既有缺陷**（`d_track` 判据对边界抖动无滞回），
  **不在本 ADR 范围内修**—— 修它要动 `d_track`/`t_dwell` 判据，属本单红线。

  > **证据强度说明**：本节最初只有"距离 2.5↔3.3 m 来回振荡"的**推断**（日志距离读数 + 代码符号），
  > 在既有 run 的日志里 grep `RANGE_EXCEEDED` 是 **0 命中**—— 因为该事件只发布到 ROS 话题
  > `/agc/task/dwell_event`，**从不落盘**。后经 `probe_dwell_events.py` 订阅该话题才取得直接证据。
  > **第一版探针因未复用 `dds_transport` 而零送达**，差点被误读成"dwell 从未启动"——
  > 这类"探针自身缺陷伪装成阴性结论"的风险，与本 ADR 无关但值得记下。
