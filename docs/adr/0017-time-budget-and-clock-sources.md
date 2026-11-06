<a id="top"></a>
# 时间预算口径与时钟/源时刻

## Status

accepted（2026-11-02 由 ADR-0039 / 0047 / 0054 合并；结论未变）

## 背景

系统里同时存在三种互不对应的计时：FSM 超时用 ROS 仿真时钟、runner 用单调墙钟、进程时长用 `steady_clock`。后果是**不同 RTF 的成功率 / 耗时不可比**：暂停仿真不触发 FSM 超时，慢仿真却可能先耗尽 runner 预算；「任务超时失败」与「基础设施看门狗」混为一谈。

空中与地面各有一次「把接收时刻当测量时刻」的缺陷：参考 / 目标年龄用接收 `now` 重置，旧包重放会被"变新鲜"；地面 odom 用发布时刻当 `header.stamp`、`age` 把负年龄钳为 0、速度历史不与复位关联，teleport 位移被差分成非物理速度尖峰。

契约真源见 [#hard-constraints](../ROS2迁移交接文档.md#hard-constraints)、[#terminal-semantics](../ROS2迁移交接文档.md#terminal-semantics)、[#namespace](../ROS2迁移交接文档.md#namespace)、[#params](../ROS2迁移交接文档.md#params)。

## 决策

### (a) 三类时间预算口径成文并命名（互不冒充）

| 口径 | 时钟 | 归属 | 参数入口 | 语义 |
|---|---|---|---|---|
| `mission_sim_budget` | `ros_sim`（`now − start_time_`） | `task_manager` | `t_max_s`（`config/base.yaml` 单一注入） | **任务预算**：episode 任务超时判据（超时算失败） |
| `episode_wall_watchdog` | `wall_monotonic`（`time.monotonic`） | `episode_runner` | `--wall-watchdog-s`（缺省回落 `--timeout`） | **外部看门狗**：墙钟等待上限；超时判 **infra**、**不算成功** |
| `process_wall_duration` | `wall_steady`（`steady_clock`） | `run_logger` | `duration_s`（run 产物字段） | **进程时长**（含预热 / 关闭）；仅记录，**不**参与 episode 判定 |

三者以 `TIME_BUDGETS` 显式标注 `clock` / `owner` / `param`。

### (b) 任务预算选 `mission_sim_budget`（ROS 仿真时钟）

任务成功 / 失败是**任务语义时间**上的判据，故任务预算**必须**跟随仿真时钟：仿真暂停（`/clock` 停发 / RTF→0）时任务时间**不推进**，**不得**因此误判任务超时。**不**把所有 timer 一律改墙钟；墙钟看门狗仅作**外部兜底**（防 runner 无限等待），进程时长仅作运行观测。

### (c) 墙钟看门狗超时的显式分类（且不算成功）

episode 结束判定**收敛到唯一函数** `classify_episode_outcome(...)`：

- 达终态 `TRACKING_SUCCESS` / `INTERCEPT_CONFIRMED` → `mission_terminal` / `classification=mission` / `budget_kind=mission_sim_budget`；
- 达终态 `MISSION_FAILED` / `ABORTED` → `mission_terminal` / `mission` / `mission_sim_budget`；
- 终态 `INFRA_FAILURE` → `infra_failure` / `infra`；
- **未达终态（被墙钟看门狗停止）** → `wall_watchdog_timeout` / **`infra`** / `budget_kind=episode_wall_watchdog` / **`counted_as_success=False`**。

即外部看门狗超时写**显式 infra 分类**且不计成功，区别于的 `MISSION_FAILED` 任务失败。

### (d) RTF 与起止事件记录（同一 run 可比）

- `episode_runner`：每 episode 记 `wall_start_s` / `wall_end_s` / `wall_elapsed_s`、`sim_start_s` / `sim_end_s` / `sim_elapsed_s` 与 **`rtf`**（= 仿真增量 / 墙钟增量）；`report.json` 汇总 `rtf_mean`。记录自 episode 开始（`Monitor` 于 `Popen` 前建立、订阅 `/clock`），故不同 RTF 的**成功率 / 耗时**可按「仿真时间」与「墙钟时间」分别区分。
- `run_logger`：`summary.json` 新增 `duration_kind="process_wall_incl_warmup_shutdown"`、`wall_start_unix_s` / `wall_end_unix_s`（起止事件）、`sim_start_s` / `sim_end_s` / `rtf`；`duration_s` 语义不变（进程墙钟）。

### (e) train / eval 同一预算语义（不产生第三套口径）

`classify_episode_outcome` 是 **episode 结束判定的唯一来源**：评估 adapter 直接调用；训练 adapter 落地时**必须复用**同一函数，**不得**自造独立 step budget / 结束语义。参数单一注入：mission 预算 `t_max_s` 经 `config/base.yaml`，watchdog 预算经 runner CLI。

### (f) 参考 / 目标年龄以源 `header.stamp` 计（不以接收 `now` 覆盖）

`sourceStamp(header.stamp)`：未设**源时间**（全 0）退回接收 `now`（兼容未置 stamp 的发布者），否则取**消息自身时刻**。旧包重放（`header.stamp` 为过去）→ 按源时间判年龄 → **过期即拒**，**不**因接收而"变新鲜"。

### (g) 目标门 = 源时间窗 且 `confidence ≥ confidence_min`

`targetFresh` = `age ∈ [0, target_max_age_s_)` **且** `target_confidence_ ≥ confidence_min_`，默认 `target_max_age_s_ = 0.5` / `confidence_min_ = 0.5`（对齐契约）。**低 confidence 持续消息** → 目标视为过期 / 冻结（**不**仅凭"消息新鲜"继续跟踪）。目标门由 `1 s` **收紧为 0.5 s**。

### (h) 已获模式 + 显式 hold，不静默回落基础轨迹（r-032）

`trajectory_tracker` 记录**是否已获目标**（首次成功采用参考时置 `acquired_=true`，并记 `last_good_ref_`）。参考来源裁定三分：

- `tracking`：参考与目标**均新鲜** → 采用 `tracking_ref`（覆盖基础轨迹）；
- `hold`：**已获目标后**失参考 / 失目标 → 显式 hold（保持 `last_good_ref_` 位置，**速度 / 加速度前馈清零**），**不**回落基础八字；
- `base`：**从未获目标** → 正常基础八字。

新 episode（activate / 接管 / 相位复位）重置 `acquired_` / `frozen_` / `last_good_ref_`。

### (i) `rl_offset` 寿命 / 生效窗口 + 能力限幅

`rlOffsetFresh` 以**源时间**判寿命（`rl_offset_timeout_s_`，默认 0.5 s，超时归零）；应用时幅值限幅 `rl_offset_max_m_`（默认 2.0 m）；**仅正常跟踪模式（`tracking`）生效**——hold / base 模式**不**叠加 offset，从而区分「安全层必要修正」（`shield_active`）与「追逐旧目标」。

诊断：`/agc/air/tracking_status` 每 tick 发 JSON `{acquired, frozen, source(base|tracking|hold), ref_fresh, target_fresh, offset_applied, offset_clamped, shield_active}`（`std_msgs/String`，非 ABI、非命令者）。

### (j) 地面 odom：源采样时刻 = 发布时刻（仅新样本发布，不静默外推，r-039）

- `onGt` 记录**源样本时刻** `src_stamp_`；`tick` 仅在 `src_stamp_ != last_pub_stamp_`（**有新样本**）时发布 odom / TF，`header.stamp = src_stamp_`。
- **不用 `now` 冒充测量时刻**；**不引入**任何静默外推。TF 连续性由「源率 = odom 率（均 30 Hz）」承载；无新样本时**停发** odom / TF 并以 `valid=false` 显式表达（与 tf2「缺变换即显式错误」惯例一致）。
- **负年龄 / 时钟回拨 → 显式无效**：年龄改为**有符号** `age = now − 源采样时刻`；`age < 0` → `state=clock_anomaly` + `valid=false`；`age > odom_max_age_s_` → `state=stale` + `valid=false`。**删除** `std::max(0.0, ...)` 钳制。
- **复位 epoch 清空速度历史**：订阅 `/agc/scenario/reset_epoch`（`std_msgs/Int32`，`transient_local`）；**epoch 变化即清空 `history_`**，重建 ≥ 2 个新样本前**速度输出 0**（`state=reset_rebuild`）。另有**位置跳变守卫**（`reset_jump_clear_m`，默认 0.5 m）：相邻样本位移超阈值即清历史，与 epoch 订阅**双保险**（覆盖 teleport 样本先于 epoch 消息到达的时序）。
- 诊断话题：latched `std_msgs/String` `/agc/ground/odom_diag`，内容 `state=<ok|stale|clock_anomaly|no_sample|reset_rebuild> age=<秒> epoch=<n>`；参数写入 `config/perception.yaml` 的 `ground_odom_adapter:` 段（launch 单一设置，节点不覆写）。
- 边界不变：`/agc/ground/odom` 的 `frame_id=world` / `child_frame_id=car/base_link` 与 `/agc/ground/odom_valid`（Bool）语义不变；twist 仍按 ROS 约定表达在 child（车体）系。

### (k) 取证与验收

- **本批取证实测**：`experiments/w6-task-eval/<run_id>/r039/bench.json` —— 修复后 odom 的 `Header.stamp` **逐条等于**源样本 stamp（`unmatched_stamps=0`）；`time_jump`（future stamp）→ `state=clock_anomaly` 且 `valid=false`；`teleport`（新 epoch + 跳变）→ 重建前速度 0、**无尖峰**（`max_speed_after_teleport ≤ 2.0 m/s`，旧实现跨 teleport 差分约 ~600 m/s），与同轴真值速度误差 ≤ 0.35 m/s。
- **时间预算验收**：`run_w6_r024.sh` → `experiments/w6-task-eval/20261016-w6-r024-0/metrics/r024.json`（`overall_pass: true`，5/5）—— 暂停仿真时 `mission_budget_not_triggered=true` 而墙钟看门狗判 `wall_watchdog_timeout / infra`；恢复 `/clock` 后按仿真时钟触发 `MISSION_FAILED reason=TIMEOUT`；`rtf` 按两组墙钟 / 仿真组合得 2.0 / 0.5；`def classify_episode_outcome` 全仓**恰 1 处**。
- **空中验收**：`run_w6_r032.sh` + `w6_r032_bench.py` 四场景（已获后失参考 → hold 不回落八字；旧 ref 重放 → 按源时间拒；低 confidence 持续 → 冻结不跟随；offset 超幅 ~17.3 m → 限幅到 2.0 m、源停即归零），产物 `experiments/w6-task-eval/<run_id>/r032/bench.json`；本台架隔离安全层（`safety.enabled=false`），非整链 / 非 GUI。
- **地面验收**：`run_w6_r039.sh` + `w6_r039_bench.py`（真实二进制 + 合成真值 / epoch，四场景：断源 / 旧样本 / teleport / time jump，同一时间轴记录真值 / odom 速度）。

## 不做什么（边界）

- **不**把所有 timer 一律改墙钟（仿真暂停会误判任务超时）。
- **不**以固定 `sleep` 代就绪、**不**以 0 冒充空指标。
- **不**在无新样本时用速度外推模型把缓存位置包装成「当前测量」（会让 `age` 又趋 0，重造口径混淆）；极低源率场景是否需要**显式**外推（须诊断标注 `extrapolated`）本批不做，按需另议。
- **不**保留负年龄钳 0，**不**只加告警而不改发布 `stamp`。
- **不**用 `/agc/scenario/reset` 服务调用当复位时序信号（服务不携带「已完成 teleport」的可靠时序）。
- **不**改冻结 9 消息 / 服务 ABI、**不**变唯一执行口语义、**不**新增第二 ROS 命令者；新增字段仅落 run 产物与诊断话题。
- **不**把「正常 drop-out 的冻结」与「全链故障保证」混为一项验收。

## Considered Options

- **维持三套口径互不对应、runner 超时写 `ACTIVE` 无分类** —— 被否：跨 RTF 不可比，infra 看门狗与失败混淆。
- **训练侧另立 step budget** —— 被否：违反「train / eval 同一预算语义」，会产生第三套结果。
- **新增带时间字段的冻结 9 消息承载 RTF** —— 被否：违 ABI 与唯一执行口语义；RTF / 起止仅落 run 产物即可。
- **继续用接收 `now` 判参考年龄** —— 被否：旧包重放会"变新鲜"，源时间语义丢失。
- **目标门继续 1 s 且不检 confidence** —— 被否：与契约（0.5 s + confidence）不一致。
- **获后失参考仍回落基础八字** —— 被否：正是「获后故障退回八字」的病灶。
- **offset 永久叠加** —— 被否：会掩盖真实安全约束、追逐旧目标。
- **地面 odom 用显式速度外推到当前时刻** —— 被否：把缓存位置重新包装成当前测量，`age` 又趋 0。
- **只订阅 `/agc/scenario/reset` 服务调用清历史** —— 被否：缺可靠时序。

## Consequences

- **正面**：三类时间口径分别标注、互不冒充；外部看门狗超时写显式 infra 分类且不计成功；暂停仿真不触发任务预算、恢复后按仿真时钟触发；run 证据含 RTF 与起止事件；参考 / 目标年龄以**源时间**计，旧包过期即拒；获后失参考进入显式 hold；`rl_offset` 有寿命 + 限幅且仅正常跟踪生效；地面 odom 的 `header.stamp` 如实表达源采样时刻，teleport 不再产生速度尖峰。
- **代价 / 限制**：新增参数 `target_max_age_s` / `confidence_min` / `rl_offset_timeout_s` / `rl_offset_max_m`（承载者登记于 `air.yaml`）；地面 odom 发布率**随源率**（30 Hz），无新样本时**停发** odom / TF—— 下游须改以 `valid=false` / 诊断判失效（`task_manager` 门禁用 `odom_valid`、`ground_baseline` 读最新样本，已适配）；墙钟看门狗与任务预算的边界须靠 `budget_kind` 字段区分。
- **未决 / 后续**：整链（含 PX4 / GUI）的空中冻结行为属后续；冲突恢复后是否需重置参考相位另裁；极低源率的外推模型未引入。

## 参考

- 契约：[#hard-constraints](../ROS2迁移交接文档.md#hard-constraints) / [#terminal-semantics](../ROS2迁移交接文档.md#terminal-semantics) / [#namespace](../ROS2迁移交接文档.md#namespace) / [#params](../ROS2迁移交接文档.md#params) / [#messages](../ROS2迁移交接文档.md#messages)
- 相关决策：[ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与证据纪律）、[ADR-0018](0018-acceptance-and-coverage-matrix.md#top)（验收判定与覆盖矩阵）、[ADR-0014](0014-task-fsm-and-scenario-transaction.md#top)（任务 FSM 与终态锁存）、[ADR-0012](0012-spawn-clearance-and-reset-transaction.md#top)（复位事务）、[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)（真值派生感知）、[ADR-0003](0003-nav2-paradigm-absorption.md#top)（Nav2 吸收）
- 证据：`experiments/w6-task-eval/20261016-w6-r024-0/metrics/r024.json`、`experiments/w6-task-eval/<run_id>/r032/bench.json`、`experiments/w6-task-eval/<run_id>/r039/bench.json`
