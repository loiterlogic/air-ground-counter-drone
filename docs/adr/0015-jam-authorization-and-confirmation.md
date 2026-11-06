<a id="top"></a>
# 干扰：单一授权、真实确认与因子分离

## Status

accepted（2026-11-02 由 ADR-0032 / ADR-0033 / ADR-0034 合并；结论未变。其中「发送即确认」与「停流 ≡ `NAV_DLL_ACT`」两处旧口径作废）

## 背景

干扰是拦截的两种手段之一，但它最容易造假：只要「发了命令」就算成功，干扰成功率与核心论文结论立刻失真。历史实现同时踩了三个坑：**双授权路径**（注入执行者 `intruder_driver` 直订原始命令话题，绕过 `jammer` 的包络裁决）、**发送即确认**（`jammer` 发完 `VehicleCommand` 立即发 `JAM_*`，`task_manager` 见非 `JAM_NONE` 即置 `INTERCEPT_CONFIRMED`）、**因果混淆**（把「停发 Offboard」写成 `NAV_DLL_ACT` 等价，且 `LOST` 同时镜像强制 `RTL`，使三种机制无法区分）。本组决策把干扰拆成「意图 → 授权 → 发送 → ACK → 真实 nav_state → 持续行为」的证据链，并锁定运行时参数使因果可复核。

## 决策

### (a) `jammer` 是唯一授权 / 确认裁决者

- **授权**：仅当「命令合法」（`key in JAM_MAP`）**且**「作用包络**新鲜**」才产出**已校验授权事件** `JAM_*`（发布到 `/agc/task/jam_state`）并 `_send_nav_state`；未知命令 / 包络外 / 包络过期（未就绪）一律**不产出事件**。
- **包络新鲜度**：参数 `envelope_max_age_s`（默认 **0.5**）。判据 `envelope_in_ and last_env_rx_ is not None and (now − last_env_rx_) <= envelope_max_age_s`——**包络过期视同包络外**（与「包络以 20 Hz 发布、停发即失效」的语义一致）；日志区分「包络外」与「包络过期 / 未就绪」两种措辞。
- **单一消费**：`intruder_driver` **删除**参数 `jam_cmd_topic` 与其原始命令订阅，改订 `jam_state_topic`（默认 `/agc/task/jam_state`，`std_msgs/String` depth 10），`key = m.data.strip().upper()`，`jammed = key not in ('', 'JAM_NONE')`；`jammed_` → 停发 Offboard 流（模拟链路被切断）语义不变。
- **不新增命令者 / 命令话题**：复用既有 `/agc/task/jam_state` 作已校验事件（`task_manager` 已在消费）。`JAM_NONE` = **释放**（非注入）：`''` / `NONE` / `CLEAR` 输入 → **始终**发出 `JAM_NONE`，从不受包络 / 新鲜度门控。

### (b) 真实行为确认：授权 / 发送 / ACK 单独都不算成功

- `jammer` 订阅入侵者 PX4 `VehicleStatus`（`vehicle_status_topic`，默认 `/px4_1/fmu/out/vehicle_status`，BEST_EFFORT depth 5）。发送后开**确认窗口** `jam_confirm_window_s`（默认 **3.0 s**）；**仅当**实际 `nav_state`（在新鲜度阈值内）**等于所命令模式**且**持续 ≥ `jam_sustain_s`**（默认 **1.0 s**）才发布确认。
- `ACK` = 窗口内首次收到状态流，**仅作证据、不作确认**（对齐「goal accepted ≠ result succeeded」）。模式中途退出会**重置**持续计时起点。
- **两条新增 `std_msgs/String` 通道**（非冻结 9 消息、非命令话题）：`/agc/task/jam_confirm`（`confirm_topic`，仅在满足真实条件时发布一次 `JAM_RTL|JAM_LAND|JAM_HOLD|JAM_LOST`）与 `/agc/task/jam_evidence`（`evidence_topic`，全量证据 / 负例，可审计）。
- **`task_manager` 只认已确认事件**：参数 `jam_confirm_topic`（默认 `/agc/task/jam_confirm`），回调**仅**对正向集合 `{JAM_RTL, JAM_LAND, JAM_HOLD, JAM_LOST}` 置 `jam_reason_`；`reason_code = JAM_*`，FSM 分支不变。**授权事件 `/agc/task/jam_state` 不再被订阅**，故单独不足以确认。

### (c) 负例分类（不确认，逐条落证据）

窗口到期未确认时按**实际观测**分类：`JAM_FAIL_TARGET_ABSENT`（从未见过目标 `VehicleStatus`：飞控缺席 / sysid 不符）、`JAM_FAIL_NO_FEEDBACK`（曾见状态但窗口内无状态：数据链断续）、`JAM_FAIL_MODE_UNREACHED`（窗口内有状态但未达目标模式：命令被拒 / `target_system` 不匹配）、`JAM_FAIL_NOT_SUSTAINED`（曾达目标模式但未持续 `jam_sustain_s`：短暂进入后退出）。

释放路径：`''` / `NONE` / `CLEAR` → 取消待确认、`state_topic` 照旧发 `JAM_NONE`、`evidence_topic` 发 `JAM_RELEASE`。

### (d) 三类独立实验因子（`factor` 标签）

1. **强制模式**（`forced_mode`）：`RTL` / `LAND` / `HOLD` 经 uXRCE 发 `px4_msgs/VehicleCommand`（`VEHICLE_CMD_SET_NAV_STATE`）强制 nav_state **5 / 18 / 4**。
2. **仅断 Offboard**（`offboard_only`）：`LOST` **只**停发 Offboard 流，**不发** `SET_NAV_STATE`（`JAM_MAP` 的 `nav_state` 为 `None`）；随后行为由运行时锁定的 `COM_OF_LOSS_T` / `COM_OBL_RC_ACT` 解释。其确认期望 nav_state = 参数 `lost_expected_nav_state`（默认 **2** = POSCTL）= 运行时锁定 `COM_OBL_RC_ACT` 的映射值。
3. **数据链失联**（`NAV_DLL_ACT`）：**本轮未实现**（见下条限制）。

因子标签随证据串落 `/agc/task/jam_evidence`：`JAM_SENT/JAM_ACK/JAM_CONFIRMED/JAM_FAIL_* <reason> factor=<factor>`；`/agc/task/jam_confirm` 取值仍**恰为** `JAM_*`（**不**追加 factor，保 `task_manager` 精确匹配）。

### (e) 「停流 ≠ `NAV_DLL_ACT`」事实更正

本条回应评审风险 r-019（failsafe 因果混淆）。停发 Offboard 流触发的是 **offboard-loss**（`COM_OF_LOSS_T` 默认 **1.0 s** + `COM_OBL_RC_ACT` 默认 **0** = Position，enum `0 Position / 1 Altitude / 2 Manual / 3 Return / 4 Land / 5 Hold / 6 Terminate / 7 Disarm`），**不是** data-link-loss（`NAV_DLL_ACT` 默认 0 = Disabled）。`COM_OBL_RC_ACT = 0` 映射到 nav_state `POSCTL = 2`（`MANUAL=0, ALTCTL=1, POSCTL=2, AUTO_LOITER=4, AUTO_RTL=5, OFFBOARD=14, AUTO_LAND=18`）。原「停流触发起自身 failsafe 等价」「模拟链路被切断」「LOST 以 RTL 近似」等叙述**作废**；不改契约真源文字，更正记录在本条。

### (f) 运行时参数锁定与记录

- **单一真源** `src/agc_task/config/px4_failsafe_lock.yaml`（非 ROS 节点参数，顶层平铺）：`com_of_loss_t` / `com_obl_rc_act` / `nav_dll_act`（以及仿真时间源开关 `UXRCE_DDS_SYNCT: 0`，见 [ADR-0027](0027-uxrce-startup-reproducibility.md)）。
- **注入**：`scripts/lock_px4_failsafe_params.sh` 读该真源，生成 SITL 启动参数文件 `build/px4_sitl_default/etc/init.d-posix/px4-rc.params`（`param set ...`）；写前若 `.agc-orig` 不存在则备份一次；SITL 目录不存在则告警并 `exit 0`（不阻断 launch）；末尾把 `NAME=VALUE` 三行打印到 stdout。**只写 build 产物，不改 PX4 源码**。
- **接线**：launch 的 `actions` **开头**插入该脚本，确保在 PX4 定时器之前执行。
- **记录**：run 证据写 `runtime_px4_params` + `runtime_px4_params_source`，值取自**实际注入**的 `px4-rc.params`，**不以源码默认代填**。

## 不做什么（边界）

- **不**保留双授权路径（注入执行者不得自行解析原始命令 / 自行做包络裁决）。
- **不**新增专用命令话题、**不**新增第二 ROS 命令者、**不**改冻结 9 消息 / 服务 ABI（新通道均为 `std_msgs/String`）。
- **不**用「收到任一 `VehicleStatus`」当确认（ACK ≠ 效果）；**不**以「达到模式」为唯一判据而不要求持续。
- **不**让 `task_manager` 自行订 `VehicleStatus` 判定（重开双裁决）。
- **不**运行期读 PX4 参数代替启动锁定；**不**以源码默认值代填运行值。
- **未实现**：因子③ data-link-loss **未**隔离——本项目未切断真正的数据链（uXRCE / MAVLink），`NAV_DLL_ACT` 保持默认 `0`（Disabled），仅如实标注、不声称已隔离；报告与 `r019.json` 以 `factor_3_data_link_loss = {implemented: false, note: ...}` 记录。
- **不**在本条范围内实现真实 PX4 Offboard 动力学与真实电磁场（确认闭环以假 PX4 回读状态流验证，真实 SITL 整链对拍留待后续）。

## Considered Options

- **保持双路径（driver 直订原始命令）** —— 被否：授权语义不单一、无新鲜度。
- **新增专用「已校验事件」话题** —— 被否：违反「不新增命令话题」；复用既有话题更简且消费方已在用。
- **包络无新鲜度（仅布尔）** —— 被否：包络过期仍授权注入（目标已飞离仍被干扰）。
- **让注入执行者自行做包络 / 新鲜度裁决** —— 被否：重开双裁决，违背单一授权。
- **保持「发送即 `JAM_*` 即确认」** —— 被否：无 status / ack 回读即成功，是能直接产生与实际飞控效果无关的拦截成功的缺陷。
- **仅凭 ACK 确认** —— 被否：ACK ≠ 效果，PX4 可能拒命令或模式瞬进瞬出。
- **改冻结 9 消息或新增命令话题来承载确认** —— 被否：改用 `std_msgs/String` 状态 / 事件即可。
- **`LOST` 强制 `LAND` / `HOLD` 近似 offboard-loss** —— 被否：仍是强制模式，掩盖 offboard-loss 与 data-link-loss 的机制差异。

## Consequences

- **正面**：干扰授权单一化——原始意图（未知 / 包络外 / 过期）不再能切断链路；`INTERCEPT_CONFIRMED` 只由真实 `nav_state` 持续达标驱动，PX4 缺席 / 无反馈 / `target_system` 不匹配 / 命令被拒 / 模式瞬进瞬出均产出负例事件而不确认；`RTL/LAND/HOLD`（发命令）与 `LOST`（不发命令）在时序日志上可区分；offboard-loss 的因果归因 = 运行时锁定参数。
- **代价 / 限制**：`JAM_NONE` 无条件释放，`CLEAR` 后参考从干扰发生时刻连续续上（`|Δ| < 0.3 m`，重基准语义不变）；因子③未实现，需后续 workstream 单列；确认闭环的置信度受限于假 PX4 harness。
- **证据**：`experiments/w6-task-eval/20261016-w6-r018-0/metrics/r018.json`（无状态 / `target_system` 不匹配 / 未达模式 / 短暂进入 / 持续达标 / 仅授权事件六类用例）与 `experiments/w6-task-eval/20261016-w6-r019-0/metrics/r019.json`（`LOST` 无 `SET_NAV_STATE`、`RTL` 有命令、运行时参数三源一致、因子③限制）均 `overall_pass: true`。

## 参考

- 拦截口径与火控（含干扰作用包络与 `JAM_*` 终态语义）：[ADR-0011](0011-interception-and-fire-control.md)
- 任务 FSM 与终态锁存：[ADR-0014](0014-task-fsm-and-scenario-transaction.md)
- 时间源与 `UXRCE_DDS_SYNCT`：[ADR-0027](0027-uxrce-startup-reproducibility.md)
- 安全阈值与失效停车：[ADR-0010](0010-safety-thresholds-and-failsafe.md)
- 契约：[硬约束](../ROS2迁移交接文档.md#hard-constraints)、[执行口](../ROS2迁移交接文档.md#execution-port)、[参数入口](../ROS2迁移交接文档.md#params)、[消息](../ROS2迁移交接文档.md#messages)、[终态语义](../ROS2迁移交接文档.md#terminal-semantics)
