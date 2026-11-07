<a id="top"></a>
# 任务 FSM、起始事务与终态锁存

## Status

accepted（2026-11-02 由 ADR-0028 / 0030 / 0031 / 0037 / 0076 合并；结论未变）

## 背景

三个相互咬合的缺口把「一回合」变成不可判定的东西：

- **起始门禁竞态**：`/agc/task/start` 在主单线程回调内阻塞等待 `scenario/reset`，等待期间自身的
  `odom_valid` / 地面 odom / `cmd_vel` 订阅**停止更新**，于是「reset 后再校验」实际读的是阻塞前缓存；
  且 `odom_valid` 无年龄、时钟仅判 `now>0`、世界名仅比较参数字符串。
- **复位非事务**：`scenario_reset` 只有两次非原子 `set_pose`（车、目标依次写），目标写失败会留下
  「车已移动、目标未复位」的中间态；可复位态集合漏掉成功拦截终态；启动定时器 bypass 门控。
- **命令非幂等**：start 无允许态检查（active 期间重入会先 reset、再无条件置 `INFRA_FAILURE`）、
  abort 无条件覆写终态、终态不记归属 episode、调用结果把「超时」与「失败」混为一谈。

此外入侵者按**首帧 odom** 起算运动（起点依赖启动快慢、多回合累积偏差），capture 场景里
「跟踪里程碑先锁存终态、交火窗口被提前关闭」。本篇一并收敛。

## 决策

### (a) 起始事务不阻塞节点
`main` 由 `rclcpp::spin` 改 `MultiThreadedExecutor`；`/agc/task/start` 与 `/agc/task/abort` 放专用
互斥回调组（`srv_cb_group_`），服务回调可在本线程阻塞等 `reset` / `reset_phase`，订阅留在默认组、
由执行器其它线程持续刷新。start 与 abort 同组互斥，避免并发重入；复位服务与启动定时器另置
**独立互斥回调组**，使事务回调内的有界阻塞（静止观察 / 读回等待）期间 gt / odom 缓存仍由其它线程刷新。

### (b) 门禁绑定「复位后新鲜数据」
`scenario/reset` 成功后记 `reset_done_time_`（复位完成 epoch）。门禁数据须**到达时刻 ≥
`reset_done_time_` 且年龄 ≤ 上限**：`odom_valid` / 地面 odom ≤ `odom_valid_max_age_s`（config，默认
1.0 s），`cmd_vel` 回环 ≤ 0.5 s。复位完成瞬间 adapter 尚未发下一帧，故先做**有界等待**（上限 =
`odom_valid_max_age_s`）；超时仍无新样本 → `odom_valid_stale` / `ground_odom_stale`。

### (c) 时钟门 = 进展校验，世界名 = 配置校验
1 Hz 状态计时器（默认组，服务阻塞期间持续采样）维护 `prev_clock_`；通过条件为
`now.seconds > 0` **且** `now > prev_clock_`（严格推进），否则 `clock_not_progressing`。
世界名比较保留为配置校验（`single_world_mismatch`）。各门输出 `evidenceSummary`（epoch / 各门到达
时刻 / 时钟采样 / 世界名）随 Trigger 应答回传并记日志，供 run 记录关联。

### (d) 复位 = 受控事务：门控窗口
可复位态 = 全部**非 active** 态：`IDLE` + `TRACKING_SUCCESS` + `INTERCEPT_CONFIRMED(7)` +
`MISSION_FAILED` + `ABORTED` + `INFRA_FAILURE`；active（`AIR_SEARCH` / `TARGET_ACQUIRED` /
`GROUND_APPROACH`）一律拒（`not_resettable`）。门控通过即撤销运动许可—— 非 active 期间无授权命令者
（RL 仅在 `GROUND_APPROACH` 驱动），「停止执行」在策略层面已成立。

**门控窗口裁定**：契约 [#task-gating](0014-task-fsm-and-scenario-transaction.md#task-gating) 的「运行期」明确为
**任务已获运动许可（active）期间**，即「复位允许窗口 = 非 active + 受控事务；禁止窗口 = active」。
这是**措辞澄清**、非语义变更：门控意图是防「active 期间被复位覆盖 `car_start`」，而又要求 start
前复位（此刻尚未 active）—— 只有把「运行期」锚定 active 才不自相矛盾。契约文字未改，裁定以本篇为准。

### (e) 停止执行 = 门控 + 静止证据（不新增命令者）
`scenario_reset` **SHALL NOT** 发布任何 `cmd_vel`（`/agc/ground/cmd_vel` 是唯一命令车体运动的通道，
落地者 `ground_drive_relay`；唯一例外是场景复位的位姿写入）。复位前订阅 `/agc/ground/odom`
（`nav_msgs/Odometry`）取 twist 线速度模长，做有界等待（上限 `stop_exec_max_s`，默认 0.5 s），
速度 < `quiescence_eps`（0.05 m/s）视为静止并记录证据。该等待**非致命**：残余为滑行且随后 teleport
中和；非静止只记 `car_not_quiescent` 证据（速度 / 等待时长），不阻断复位。

### (f) 读回前置 + 原子事务 + 回滚
订阅真值旁路 gt（`car_gt_topic` / `target_gt_topic`，world 系 `PoseStamped`）缓存最新位姿，作为
「写入前状态」与回滚目标；写入前该缓存须新鲜（年龄 ≤ `readback_max_age_s`，默认 0.5 s），否则
`gt_stale`。事务顺序：写车 → 读回（对 gt 最新位姿，XY 欧氏距 ≤ `readback_tolerance_m` 0.25，有界等待
`readback_timeout_s` 1.0）→ 写目标 → 读回校验。任一步失败 → **回滚**已写入实体到写入前位姿；回滚再
失败 → 置**持久**标记 `env_needs_rebuild_` 且 reason 后缀 `env_rebuild_needed`。**绝不留中间态**。
理由码：`not_resettable` / `no_candidate` / `gt_stale` / `car_set_pose_failed` /
`target_set_pose_failed` / `readback_mismatch_car` / `readback_mismatch_target` / `rollback_failed`。
实测（起 gz 世界 + set_pose 桥，`ros2 service call`）：对**不存在**的实体名 `set_pose` 仍返回
`success=True` ⇒ **任何「写入成功」判据都不得只看 `set_pose.success`**，必须以真值读回为准。

### (g) epoch 与 car_start 仅成功发布
`car_start`（`/agc/scenario/car_start`）仅在完整成功后发布；每次成功复位 `reset_epoch_++` 并发布
`/agc/scenario/reset_epoch`（`std_msgs/Int32`，transient_local depth 1），`car_start.header.stamp =
now`，应答含 `epoch=N`（失败保持 `reset rejected: <reason>`）。启动 4 s 初始复位走**同一门控**
（`doReset`，SHALL NOT bypass），保留延迟等 gz / 桥就绪；早启动时若任务 active 则被拒、不再覆盖。

### (h) FSM 允许态矩阵
| 命令 | 接受态 | 拒绝态（回显当前态；不 reset / 不 fail / 不覆写） |
|---|---|---|
| `/agc/task/start` | `IDLE` + 任一终态 | active（`AIR_SEARCH` / `TARGET_ACQUIRED` / `GROUND_APPROACH`） |
| `/agc/task/abort` | active | `IDLE` + 任一终态 |

`onStart` 在**任何** reset 之前判 `isActive`；`onAbort` 判 `!isActive`。两者均不再触发侧效应。

### (i) 调用结果三分
`callTrigger` 由 `bool` 改 `enum class CallOutcome { Ok, Failed, Indeterminate }`：`Ok` = 收到应答且
`success=true`；`Failed` = 收到应答但 `success=false`（**确定性**门禁失败，允许置 `INFRA_FAILURE`）；
`Indeterminate` = 服务未就绪或 `spin_until_future_complete` 超时 / 取消（**非确定性**，**仅**回
`success=false`，**不改** `state_`）。超时须对 Client 调 `remove_pending_request` 清理待决请求。
超时用 `reset_call_timeout_s`（默认 8.0，reset 与 reset_phase 共用）替换硬编码；best-effort 语义不变。

### (j) 终态锁存 + episode 关联
`latched_state_{0xFF}` / `latched_epoch_{-1}` 与唯一入口 `enterTerminal(s, reason)`：先记「锁存终态 +
所属 `episode_epoch_`」再 `setState`。所有进终态路径统一走它（`MISSION_FAILED` / `TRACKING_SUCCESS` /
`INTERCEPT_CONFIRMED` / `ABORTED` / `INFRA_FAILURE`）；非终态转换仍走 `setState`。迟到命令据此拒绝并
回显，不覆写锁存结果。

### (k) 新 episode 由显式 start 创建
start 成功路径清锁存（`latched_state_ = 0xFF` / `latched_epoch_ = -1`）；reset 前记 `ep_before`，
reset `Ok` 后**有界等待**（≤0.5 s）`current_epoch_ != ep_before`（规避 epoch 投递竞态，超时以
`current_epoch_` 兜底），再置 `episode_epoch_` 并发布 `/agc/task/episode`（`std_msgs/Int32`，
transient_local，**非命令者**）。

### (l) 入侵者 episode 起点协议
- **预热独立于 episode 计时**：启动即记 `warmup_t0_`，`tw > 1.0 s` 才请求 ARM，`armed_` 且
  `nav_state_ != OFFBOARD(14)` 时请求 `VEHICLE_CMD_SET_NAV_STATE = OFFBOARD`（保留 `arm_retry_s`
  重试）。预热时间**不进入**轨迹参数 `t`—— 它属链路就绪，不是任务推进。
- **epoch 订阅**：`epoch_topic`（默认 `/agc/scenario/reset_epoch`，depth 1 + RELIABLE +
  `DurabilityPolicy.TRANSIENT_LOCAL`）。值变化即新 episode：重锚 `origins_`（下一条 odom 起算）、
  `t0_ = None`、`episode_armed_ = True`、`jammed_ = False`、`terminated_ = False`。
- **起点协议**：`_start_pose = _target(0)`；未进入 episode 时 setpoint **恒定**悬停、**不推进**；
  `dist ≤ start_tol_m`（0.4）且 `speed ≤ start_vel_eps_mps`（0.35）连续 `start_dwell_s`（0.5）→
  `t0_ = ts`。切换瞬间 `t ≈ 0`，与起始位姿连续、无跳跃。
- **轨迹**：`static` → `(ox, oy, z)`；`linear` → `(ox, oy + v·t, z)`；`maneuver` →
  `(ox + r·cos θ, oy + r·sin θ, z)`，`θ = (v/r)·t`，即切入 = t=0 落在圆周定义点 `(ox+r, oy)`；
  `z = oz − alt_m`。
- **运行区边界**：`run_region_radius_m`（默认 15.0，`<= 0` 关闭）。setpoint 水平距 `origins_` 超过 R
  时夹持到边界点、置 `terminated_ = True`，此后 `t` 继续但 setpoint 停在边界（**不外推**）。
  `_start_pose` 亦经受同一夹持。
- **CLEAR 重基准**：`jammed_` True→False 且 `t0_` 已定 → `t0_ += (now - jam_on_us_)`，把暂停时长
  加回，参考从**干扰发生时刻**连续续上（不跳变）。`jammed_` 守卫提前 `return`（停发 Offboard 流 →
  PX4 failsafe）的语义不变。`jam_cmd` 的**来源**不在本篇（见 [ADR-0015](0015-jam-authorization-and-confirmation.md#top)）。
- **参数**（`base.yaml` 单一注入，节点不得覆写）：`px4_ns: "px4_1"` / `target_system: 2` /
  `motion: "static"` / `alt_m: 2.0` / `speed_mps: 1.0` / `radius_m: 6.0` / `rate_hz: 20.0` /
  `arm_retry_s: 2.0` / `start_tol_m: 0.4` / `start_vel_eps_mps: 0.35` / `start_dwell_s: 0.5` /
  `run_region_radius_m: 15.0`；场景层只覆盖 `motion` / `speed_mps` / `radius_m`。

### (m) capture 场景：跟踪里程碑不再等价终态
capture 场景里里程碑先 `enterTerminal(TRACKING_SUCCESS)` → 状态离开 `GROUND_APPROACH` →
`capture_adjudicator` 的交火窗口关闭 → `CAPTURE_NET` 永不发生（里程碑总是赢）。新增**单一注入**参数
`task_manager.tracking_milestone_is_terminal`：基参 `base.yaml` 缺省 `true`（既有行为完全不变）；
置 `false` 时里程碑仍置 `tracking_milestone_met_ = true`（随 `/agc/task/state` 正常发布，**指标口径
不变**）但**不**进终态，FSM 留在 `GROUND_APPROACH`，结局交由 `capture_adjudicator`
（`INTERCEPT_CONFIRMED(CAPTURE_NET)`）或 `t_max_s` 超时（`MISSION_FAILED(TIMEOUT)`，超时一律失败）。
仅 capture 场景在场景层覆盖：`s08_static_none_nominal_capture` 为 `false`；
`s12_linear_dynamic_nominal_capture` **不**覆盖（其 `interception_authorized` 缺省 false，同时关掉
里程碑终态会注定超时，显式登记为待办）。不改 `t_dwell_s` / `d_track_m` / `t_max_s` / 网弹道 / 火控
门限，不改场景 `expected_terminal`（**不**用「改期望」迁就实现）。

### (n) 任务门控与场景复位

<a id="task-gating"></a>

- 任务门控 `/agc/task/start`；状态 `/agc/task/state`（`AgcTaskState`）。
- 场景复位 `/agc/scenario/reset`；`scenario_reset` 受**运行期门控**（非运行期不得写位姿）。

### (o) 终态语义

<a id="terminal-semantics"></a>

- 阶段划分：**阶段 A = 跟踪**；**阶段 B = 拦截**（本轮启用阶段 B）。
- 地面任务**跟踪**终态统一为 `TRACKING_SUCCESS`（"抵近并持续跟踪"）；**不得**表述为"拦截完成"。
- **拦截达成**终态为 **`INTERCEPT_CONFIRMED`**（阶段 B 启用，见
  [ADR-0011](0011-interception-and-fire-control.md#top)），由 `reason_code` 区分方式：
  物理捕获 `CAPTURE_NET`（[ADR-0011](0011-interception-and-fire-control.md#top)）/
  行为级干扰 `JAM_RTL|JAM_LAND|JAM_HOLD|JAM_LOST`；**不新增消息枚举**
  （消息字段 / 顺序不得变更，见 [ADR-0020](0020-package-boundaries-and-runtime-topology.md#messages)）。
- 失败 / 中止终态：`MISSION_FAILED`（超时 / 未达成）、`ABORTED`（外部中止）、
  `INFRA_FAILURE`（门禁失败）。

## 不做什么（边界）
- **不**引入 `bt_navigator` / 行为树；`task_manager` 仍是自研确定性 C++ 状态机。
- **不**新增第二 ROS 命令者；`scenario_reset` 不发布 `cmd_vel`；`/agc/task/episode` 与
  `/agc/scenario/reset_epoch` 都是状态话题，不是命令口。
- **不**改冻结 9 消息 / 服务 ABI（沿用 `std_srvs/Trigger`）；`/agc/task/capture_hit` 取值仍恰为
  `CAPTURE_NET`。
- **不**让复位 bypass 门控；**不**在 `Indeterminate` 时改状态；**不**在 active 期间接受 start。

## Considered Options
- **保持两次非原子 `set_pose`** —— 被否：目标写失败即留中间态。
- **复位前由 `scenario_reset` 发零速 `cmd_vel`** —— 被否：新增第二命令者，违反唯一执行口。
- **只用 `set_pose.success` 判写入成功** —— 被否：实测对不存在实体仍为 true。
- **超时 / 取消也一律置 `INFRA_FAILURE`** —— 被否：把非确定性当确定性失败，慢应答会污染状态。
- **用 `/agc/task/state` 相位变化当 episode 信号** —— 被否：相位不是「复位完成」的权威时刻。
- **`maneuver` 从原点起跳渐进到圆周 / 越界后继续外推** —— 被否：前者使 t=0 与场景登记不符，
  后者越出实验口径边界。
- **把 s08 的 `expected_terminal` 改成 `TRACKING_SUCCESS` / 放宽交战包络** —— 被否：前者把捕获场景
  降级成跟踪场景，后者改变任务难度。
- **无条件取消里程碑终态（不加参数）** —— 被否：会改变所有跟踪类场景的既有行为，破坏历史证据可比性。

## Consequences
- **正面**：事务期间订阅不再冻结；门禁判定可复现（epoch + 年龄 + 时钟进展）；复位不留中间态；
  start / abort 幂等、终态可归属 episode；入侵者起点不依赖启动快慢（同进程多回合 `|S1-S2| < 0.05 m`，
  CLEAR 后 `|x_after - x_before| < 0.3 m`）；capture 场景恢复登记语义。
- **代价 / 限制**：capture 场景 episode 时长从 ~16 s 变为 ~28 s 或至 `t_max` ⇒ 固定观测窗口内的行为
  随之改变，**本改动前后的 P1 数值不可混用**；语义改变前产生的旧判定保留原样，只标注其口径已被取代。
- **证据**：`experiments/w6-task-eval/20261016-w6-r013-0/metrics/r013.json`（起始门禁 a–d 全 PASS）、
  `experiments/w6-task-eval/20261016-w6-r022-0/metrics/r022.json`（幂等 / 锁存 / 慢应答 6 用例 PASS）、
  `experiments/w7-rl-b/20261020-w7-rl-b-220524-1123`（s08 恢复 `INTERCEPT_CONFIRMED`，
  `expected_match=true`，`vis_rate=0.991`、`fco_rate=0.301`）。
- **回归防线**：`composition.assertions` 的 `capture_authorized_requires_nonterminal_milestone`
  （授权射击 ⇒ 必须关闭里程碑终态，配置自相矛盾即**拒绝运行**）+ `test_scene_config_invariants.py`
  全场景静态扫描（已接入 `colcon test`，红-绿验证）。
- **风险标注**：入侵者闭环跃迁以**已观测 setpoint 流**验证（假 PX4 无真实机体动力学）；真实 PX4
  Offboard 下从起点稳定到接管的行为需整链对拍。

## 参考
- [ADR-0012](0012-spawn-clearance-and-reset-transaction.md#top)（出生净空与场景复位事务）
- [ADR-0011](0011-interception-and-fire-control.md#top)（拦截口径与火控：交火窗口）
- [ADR-0015](0015-jam-authorization-and-confirmation.md#top)（干扰授权与真实确认）
- [ADR-0016](0016-episode-window-and-sample-validity.md#top)（episode 窗口与有效样本掩码）
- [ADR-0017](0017-time-budget-and-clock-sources.md#top)（时间预算口径与时钟源）
- [ADR-0019](0019-lifecycle-and-startup-robustness.md#top)（生命周期可重建与启动健壮性）
- [ADR-0023](0023-adjudication-record-and-exit.md#top)（裁定记录与出口闭合）
