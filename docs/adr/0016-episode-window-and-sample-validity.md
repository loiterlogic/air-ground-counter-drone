<a id="top"></a>
# episode 窗口统计与有效样本掩码

## Status

accepted（2026-11-02 由 0036 / 0038 / 0043 / 0078 合并；结论未变，其中样本掩码已两次修订，正文只保留现行 `window_valid_v2` / `scan_frame_fresh_v2` 口径并注明旧口径作废）

## 背景

这些决定处理同一件事的三个断面：**一个 episode 的边界在哪**（窗口从哪开到哪关）、**窗口里的每个样本算不算数**
（陈旧 / 缺数据不能冒充有效）、以及**跨 episode 的污染怎么挡住**（旧回合的命中、旧目标的近距观测、旧车位置不得
拼进本回合）。病根一致：进程全过程被当统计窗口、`terminal_state` 被后到的任意状态覆写、陈旧 `scan` 按新 `odom`
重复计数、**缺数据反而使指标更好**；捕获裁决无任务门、输入无寿命、`fired_` 不复位、消费侧不隔离。任何一条都会
让「SUCCESS」与「0 失败率」失去意义。

## 决策

### (a) episode 事件窗口分段（窗口口径 ≠ 进程口径）

以 task 进入 / 离开 **active**（`AIR_SEARCH` / `TARGET_ACQUIRED` / `GROUND_APPROACH`）为事件边界：

- 进入 active 且无开窗 → **开窗**；
- 有开窗且收到**终态**（`TRACKING_SUCCESS` / `INTERCEPT_CONFIRMED` / `MISSION_FAILED` / `ABORTED` /
  `INFRA_FAILURE`）或 `IDLE` → **关窗**，记 `leave_s` / `closed` / `exit_state` / `exit_reason`；
- 开窗期间**每一拍 `odom`** 计入当前窗口计数（`ticks_total` … `scan_samples`）；
- `finalize()` 时若仍有开窗 → `closed=false`（显式标注未闭合），`leave_s = have_sim_ ? sim_end_s_ : 最后已知时刻`。

窗口分段使**预热 / 关闭时长不改变**窗口统计。

### (b) 有效样本掩码（现行口径：`scan_frame_fresh_v2` + `window_valid_v2`）

每拍（`odom` 回调）以该拍时刻 `t_now = now().seconds()` 计算三个布尔量，计数关系
`ticks_valid + ticks_invalid_scan + ticks_invalid_action == ticks_total` **不变**：

- **`scan_fresh`** = **收到过 scan 帧**（`have_scan_frame_`）且 `t_now − scan_rx_s_ ≤ scan_max_age_s_`。
  **不再**要求前向锥有有限回波 —— 「前向锥无回波」是**有效读数**（范围内无遮挡），不是缺数据。
  旧口径（要求前向锥有有限回波）**已作废**：无障碍场景下它把整窗判为无效（实测 `s01` / `s08` 为
  `ticks_invalid_scan = 396/396`）。
- **`action_fresh`** = 「**状态已知**」（窗口内曾收到过 `collision_monitor_state`，其值即**当前**动作）**且安全层存活**
  （唯一执行口 `/agc/ground/cmd_vel` = `collision_monitor` 的 `cmd_vel_out` 仍在新鲜窗口内）；
  `action_max_age_s_` 的语义因此是**约束安全层存活证据的年龄**，**不再**约束 state 话题逐拍新鲜度。
  旧口径（要求 `collision_monitor_state` 逐拍新鲜）**已作废**：Nav2 的 `state_topic` 是**边沿（动作变化）发布**、
  非心跳，动作长期不变（如整场 `DO_NOTHING`）时一条都不发，逐拍门会把「状态一直是 X」误判为缺数据
  （实测 full 无障碍场景 `ticks_invalid_action = ticks_total`）。
- **`tick_valid = scan_fresh && action_fresh`**；计数规则：`!scan_fresh` → `ticks_invalid_scan`；否则
  `!action_fresh` → `ticks_invalid_action`；否则 `ticks_valid`（其中 `triggered` 计 `triggered_ticks`，
  `contact || ttc < ttc_min_s_` 计 `infeasible_ticks`）。`ticks_invalid_action` **保留**（语义 = 该拍
  「安全层不存活 / 状态未知」）。
- **净空**：有限回波取最小值；**无回波拍**记入 `clearance_no_return_ticks`（范围内无遮挡）。
  `not_applicable.clearance` 改判「是否有新鲜 scan 帧」——全窗无回波时 `clearance_min_m` 仍为 `null`，
  但 `clearance` **不再**标 not_applicable（已知 = ∞）。
- **可标定参数**：`scan_max_age_s` / `action_max_age_s`（默认 `0.5 s`），由 launch **单一注入**
  （契约 [#params](../ROS2迁移交接文档.md#params)），节点不得覆写。
- **`proxy_v1` 计算逻辑保持不变**（触发判定仍用 `cm_action_ == 1 || == 2`），历史字段在有回波场景**逐值不变**。
- **口径版本**：`definition_version` 记 `scan_valid_mask: "scan_frame_fresh_v2"`、
  `shield_infeasible_rate_window: "window_valid_v2"`、`terminal_state: "first_terminal_latch_v1"`；
  `command_attribution.definition_version = "raw_effective_v2"`（新增 `clearance_ticks` /
  `clearance_no_return_ticks` / `clearance_at_intervention_ticks` / `clearance_at_intervention_no_return_ticks`）；
  `metrics_comparability` 显式标注：无障碍场景的 `ticks_invalid_scan` / 动作长期不变场景的
  `ticks_invalid_action` 由 100% 降为 ~0，**与旧口径不可逐值对照**。

### (c) 终态锁存（首个终态）

新增 `terminal_latched_` 与首个终态 `terminal_state_`：仅当收到**终态**且**尚未锁存**时写入一次，
**之后任何 `state` 消息都不得覆写**。`summary` 的 `"terminal_state"`：有锁存终态则用之，否则回落
`last_state_name_`（再空则 `"IDLE"`）；新增键 `"terminal_state_latched"`
（`"first_terminal_latched" | "last_state_no_terminal" | "none"`）。既有 `"reason_code"`（最后一次 `state` 的）
**保留**，另加 `"terminal_reason_code"` 记锁存终态的 reason。

### (d) 无任务 / 无 scan → 拒绝生成可用评价（不以 0 冒充）

聚合窗口量 `agg_ticks_*` / `agg_scan_samples`；`na_reasons`（有序数组）：无窗口 → `"no_episode_window"`；
否则 `agg_ticks_total == 0` → `"no_odom_ticks_in_window"`、`agg_scan_samples == 0` → `"no_scan_in_window"`。
`evaluation_applicable = (na_reasons 为空)`。新增 `"episode_window_metrics"`（`window_count` / 分子分母 /
`ticks_missing_ratio_scan` / `ticks_missing_ratio_action`（`ticks_total == 0` 时 `null`）/
`shield_infeasible_rate_window`）与 `"episode_windows"`（逐窗口）；窗口 `shield_infeasible_rate` 在
`evaluation_applicable == false` 或 `triggered == 0` 时输出 **`null`**；`"not_applicable"` 扩展
`episode_window` / `window_scan` / `window_action` 三键。

### (e) 进程口径与窗口口径互不冒充

`duration_s` / `odom_valid_ratio` / `cmd_vel_rate_hz` / `ticks_*` / `shield_infeasible_rate`（`proxy_v1`）
**保留**为**进程全时长**口径，以 `"process_metrics_note"` 显式标注，与 `episode_window_metrics`
（`window_valid_v2`）互不冒充。三口径（`proxy_v1` / `window_valid_v2` / `gz_contact_v1`）均**不**与旧 RL 安全集
指标直接对照，写于 `metrics_comparability` 与 `definition_version`。

### (f) 捕获事件的 episode 身份：单一来源 `/agc/task/episode`

- **任务窗口门控**：`capture_adjudicator` 订 `/agc/task/state`，**仅当** `state == GROUND_APPROACH`（有效任务窗口）
  **且**输入新鲜**且**身份匹配时才允许产出捕获命中。
- **输入寿命与身份**：`car_max_age_s`（默认 `0.5`）、`target_max_age_s`（默认 `0.5`）、`confidence_min`（默认 `0.5`）、
  `required_target_id`（默认 `""` = 不校验身份）。源停 / 超龄 / `confidence < confidence_min` → 判失效**不产出**
  （含不发布作用包络）；`required_target_id` 非空时 `target_id` 不匹配 → **不产出**。
- **episode 一次性复位**：`fired_` 与标注消费态（`last_skip_label_`）随 episode 变化复位，使连续回合可**独立命中**。
- **配套事件（不改冻结 9 消息 ABI）**：`/agc/task/capture_event`（`std_msgs/String`，`transient_local`，**非**命令者），
  值 `CAPTURE_NET ep=<epoch> t=<ros_sec> target=<id>`（可解析）；`/agc/task/capture_hit` **仍恰为** `CAPTURE_NET`；
  `capture_evidence` 保留。参数 `capture_event_topic`（默认 `/agc/task/capture_event`）。
- **身份单一来源**：`ep` 取 `task_manager` 发布的 `/agc/task/episode`（`std_msgs/Int32`，`transient_local`），
  同时作为 `shot_id` 的 epoch 前缀与新 episode 的火控复位触发（`onEpisodeId`）；参数 `episode_topic`
  （缺省 `/agc/task/episode`，单一注入）；**`have_episode` 之前不允许开火**（杜绝无身份事件）。
  旧口径（`ep` = 物理 `/agc/scenario/reset_epoch`）**已作废**：启动期「initial gated reset」与 `task_manager`
  自身 reset 双复位竞态会让物理 epoch 再 +1，消费侧按 `ep != episode_epoch_` 静默拒收命中 —— 实测
  `w7-rl-b/20261021-w7-rl-b-104120-1456`（40 episodes）中 4 个回合共 **41 次命中事件被丢弃**，7 个「initial 在最后」
  的回合**全部 TIMEOUT、0 成功**。修复后 `w7-rl-b/20261021-w7-rl-b-132023-5915` 三个原错位序回合全部转
  `INTERCEPT_CONFIRMED`（`shot=1-*`，物理 reset epoch 为 2）。
- **拒收不再静默**：`task_manager` 对 `ep != episode_epoch_` 的配套事件加**限频告警**（2 s）。
- **消费侧隔离**：`task_manager` 订阅 `capture_event`（`transient_local`）结算 capture（**不再消费裸 `capture_hit`**），
  解析 `ep`，**仅当 `ep == episode_epoch_`** 才接受，不匹配 → 拒收。jam 仍订 `/agc/task/jam_confirm`
  （**保持** `JAM_*` 值，**不**追加 factor）；因不含 `ep`，以「已存在本 episode（`start` 后到达）**且**非 start 前」
  为门槛：`episode_epoch_ < 0` 的 jam 一律忽略；`start` 成功**清空** `capture_reason_` / `jam_reason_` 并记录本 episode
  `episode_epoch_`。
- **先命中者胜按事件时刻**：分别记录最近一次**有效** capture / jam 事件的到达时刻（`capture_rx_` / `jam_rx_`），
  两者并存时取**更早**者结算，**不再固定 capture 优先**（`JAM_*` 亦可先胜）。

### (g) 连续跟踪 dwell：逐拍判据、分类中断、分段有效时长

`GROUND_APPROACH` 分支内（capture / jam 结算之后）改为**逐拍显式判据**：

- **本拍合法性**：`car_age`（由 `last_car_odom_rx_` 到达时刻算）→ `car_ok`（`have_car_ && 0 ≤ age ≤
  car_odom_max_age_s_`）；`range_ok = have_target_ && car_ok && 水平距 ≤ d_track_`。
- **已有活跃 dwell 逐拍连续性检查**：任一条不满足即**中断清零** —— `epoch` 变化（`EPOCH_CHANGED`）/
  `have_target_ == false`（**含空数组**，`TARGET_LOST`）/ 目标失效（`TARGET_STALE` / `TARGET_LOW_CONF`）/
  车 odom 失效超龄（`CAR_ODOM_STALE` / `CAR_ODOM_MISSING`）/ 换 `target_id`（`TARGET_ID_CHANGED`）/
  包络外（`RANGE_EXCEEDED`）/ 任务暂停（`TASK_PAUSED`，`onAbort` 内先中断活跃 dwell）。
- **无活跃 dwell 且本拍合法** → 起新 dwell（换 id / epoch 变化后**从 0 重算**，杜绝跨段累计）。
- **分段有效时长记录**：`dwell_segment_start_`（当前有效段起点，与 `dwell_start_` 同步）、
  `last_dwell_segment_s_`（刚被中断那段时长）、`dwell_valid_total_s_`（本 episode 累计有效时长）；
  `interruptDwell(t, reason)` 结算 `seg = (t − dwell_segment_start_).seconds()`，并入累计后发布中断事件再清零。
- **成功语义不降级**：成功仍为「**连续** `t_dwell` 有效」（`dwell_start_` 未被中断即
  `(t − dwell_start_) ≥ t_dwell_s`）→ `tracking_milestone_met_ = true` + `enterTerminal(TRACKING_SUCCESS,
  "tracking_milestone")`。**不**改为累计接近时长，**不**降低阈值。
- **参数与事件**：`car_odom_max_age_s`（默认 `1.0`，车地面 odom 寿命门）、`dwell_event_topic`
  （默认 `/agc/task/dwell_event`），经 `config/w6_base.yaml` 单一注入；话题 `std_msgs/String`、depth 10、**非**命令者，
  事件串：起始 `DWELL_START ep=<int> target=<id>`、中断
  `DWELL_INTERRUPT ep=<int> reason=<REASON> seg=<%.3f> total=<%.3f>`。
- **实测**：空数组跨段 → `TARGET_LOST seg=1.000 total=1.000` 且重获后 1.0 s **仍非** `TRACKING_SUCCESS`
  （`no_early_success`），再续 1.5 s 才成功；换 id → `TARGET_ID_CHANGED seg=1.000`；停发 odom →
  `CAR_ODOM_STALE seg=1.450`；`epoch += 7` → `EPOCH_CHANGED seg=1.000`；有效段 1.2 s 后置空 →
  `DWELL_INTERRUPT seg=1.200 total=1.200`。证据
  `experiments/w6-task-eval/20261016-w6-r023-0/metrics/r023.json`（6/6）与
  `experiments/w6-task-eval/20261016-w6-r021-0/metrics/r021.json`。

### (h) ABI / 命令者边界

新增话题均为 `std_msgs` 状态 / 事件（**非**命令者）；**未改**契约**冻结 9 消息** / 服务字段与顺序；
`/agc/task/capture_hit` 取值仍恰为 `CAPTURE_NET`；**未新增第二 ROS 命令者**，**未改**唯一执行口语义；
**不引入** `bt_navigator`（`task_manager` 仍是自研确定性 C++ 状态机）。物理 reset epoch 仍用于 dwell 连续性
（`current_epoch_`）与感知 / 复位簿记，**不**被 episode 身份改动替代。

## 不做什么（边界）

- **不**用进程全时长当统计窗口，**不**以「最后任意 `state`」当终态。
- **不**让陈旧 `scan` 按新 `odom` 重复计数；**不**要求 `collision_monitor_state` 逐拍新鲜（边沿发布语义下不可得）。
- **不**在无任务 / 无 scan 时输出 0 —— 一律 `null` + `evaluation_applicable=false` + `evaluation_na_reasons`。
- **不**把 dwell 改成「累计接近时长」，**不**降低 `t_dwell_s`；**不**让 dwell 跨段 / 跨目标 / 跨 episode 累计。
- **不**直接扩冻结 9 消息（加 `episode` 字段）；**不**把 `episode` 挤进 `reason` 字符串或给 `capture_hit` 追加标签
  （`capture_hit` 必须**恰为** `CAPTURE_NET`）。
- **不**为 jam 统一新增带 `ep` 的配套事件（会改变 `JAM_*` 口径、破坏已验收的 jam 侧）；jam 侧只能以「start 后到达」
  为门槛（**如实限制**），若后续 jammer 能带 `ep` 可升级为强匹配（另项）。
- **不**取消 `ep` 校验（会破坏 episode 隔离，旧事件可结算新 episode）。

## Considered Options

- **继续用进程全时长口径** —— 被否：预热 / 关闭使统计漂移、缺数据使指标虚高。
- **不设掩码、陈旧 scan 按新 odom 重复计数** —— 被否：重复计数虚增不可行率。
- **无任务 / 无 scan 时输出 0** —— 被否：以 0 冒充有效统计。
- **以「最后任意 state」当终态** —— 被否：会被后续状态覆写（正是病灶）。
- **维持旧式（无任务门 / 无寿命 / 不复位 / 固定 capture 优先）** —— 被否：即跨回合污染缺口。
- **serialize `scenario_reset` 的 initial 与 service reset / 等 epoch 稳定后再锁存 / 解析 reset 应答的 epoch** —— 均被否：依赖时序窗口或非构造性保证，后到的 initial reset 仍会再 +1。
- **只在 `have_target_ && have_car_` 内清零 / 空数组跳过 / 车 odom 无寿命** —— 被否：失联段与不同目标可拼成「持续」。
- **(a)–(h) 组合（窗口分段 + 掩码 + 终态锁存 + 拒绝冒充 + 身份单一来源 + 逐拍 dwell）** —— **采纳**。

## Consequences

- **正面**：`summary` 按 episode 事件窗口分段，预热 / 关闭**不改变**窗口统计；陈旧 `scan` 不再重复计数；
  无障碍 / 动作长期不变场景由「整窗无效」转为**有效**（`shield_infeasible_rate_window` 分母首次可用）；
  终态锁存为**首个**终态；无任务 / 无 scan **拒绝**生成可用评价；捕获事件的产生方与消费方共享同一身份来源，
  启动复位顺序不再影响结算且身份错位有显式告警；dwell **不**跨段 / 跨目标 / 跨 episode 累计。
- **代价 / 限制**：窗口计数依赖 **`odom` 拍驱动**（无 `odom` 则无拍）；合成 harness 的 `/clock` 为 20 ms 拍步进，与墙钟 / GZ 物理步长存在差异；`capture_event` 的 `ep` 语义由「物理 reset epoch」变为「task episode id」，历史 run 的事件 ep 与新语义**不可逐值对照**；jam 侧无 `ep` 只能以「start 后到达」为门槛。
- **未决 / 后续**：剩余超时（观测饥饿 / hold 正反馈、火控解算偏差、包络不满足）另行诊断；
  判据分支的确定性由契约证据保证（风险置信度：高），真实火控 / 弹道整链对拍留待后续。

## 参考

- 评审风险：[10-风险](../reviews/agc-review-2026-10-14/10-风险.md#r-021)、
  [10-风险](../reviews/agc-review-2026-10-14/10-风险.md#r-023)、
  [10-风险](../reviews/agc-review-2026-10-14/10-风险.md#r-028)
- 契约：[#hard-constraints](../ROS2迁移交接文档.md#hard-constraints)、[#terminal-semantics](../ROS2迁移交接文档.md#terminal-semantics)、
  [#params](../ROS2迁移交接文档.md#params)、[#execution-port](../ROS2迁移交接文档.md#execution-port)、
  [#messages](../ROS2迁移交接文档.md#messages)
- 相关决策：[ADR-0014](0014-task-fsm-and-scenario-transaction.md#top)（任务 FSM 与终态锁存）、
  [ADR-0011](0011-interception-and-fire-control.md#top)（拦截与火控窗口）、
  [ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与证据纪律）、
  [ADR-0010](0010-safety-thresholds-and-failsafe.md#top)（`proxy_v1` / `gz_contact_v1` 口径）、
  [ADR-0018](0018-acceptance-and-coverage-matrix.md#top)（验收判定）
- 实现：`run_logger.cpp` / `task_manager.cpp` / `capture_adjudicator.cpp` / `w6_r028_check.py`
