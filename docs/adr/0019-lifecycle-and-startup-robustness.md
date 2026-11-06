<a id="top"></a>
# 生命周期可重建与启动健壮性

## Status

accepted（2026-11-02 由 ADR-0049 / ADR-0072 / ADR-0080 合并；结论未变）

## 背景

本条起于评审风险 **r-034（生命周期恢复）**。空中链路只验证过「首次 autostart」，跨 episode 复用与故障恢复没人管：基类只转发四个生命周期回调、没有 `on_shutdown` / `on_error` 清理路径；`configure` 反复裸声明参数而 `cleanup` 不注销，第二轮可能抛重复参数异常；两个 launch 都把 `bond_timeout` 设成 `0.0`，等于**关掉节点失联检测**。另一侧，整链评价长期恒为 `TIMEOUT`：控制权从未交接（`/agc/air/release_control` 全仓无调用）、姿态四元数字段序解析错约 58°（可见率仅 1.4%）、以及启动期 lifecycle manager 阻塞 + 节点侧 bond 在 configure 就开计时导致 `px4_adapter` 失效停机。三件事都属「系统起不来 / 起不稳」，故合并裁定。

## 决策

### (a) 可重复资源状态机（configure 幂等）

基类提供 `declare_param_idempotent<T>(name, default)`：`has_parameter` 先判，已声明则直接读取。被管空中节点（`px4_adapter / takeoff_controller / trajectory_tracker / standoff_follower`）与 `OffboardInterface` **一律**改用该助手。`cleanup` **释放全部资源**（订阅 / 发布器 / 定时器 / 服务 reset），使 `configure→activate→deactivate→cleanup→configure` 可**重复**，第二轮不抛重复参数异常。

**如实标注**：rclcpp **静态类型参数不可 `undeclare`**（`cannot undeclare a statically typed parameter`），故「注销」只能以**释放资源 + 幂等声明**承载—— 幂等由 `has_parameter` 守卫，不靠注销。

### (b) 转发 `on_shutdown` / `on_error` 做完整清理

基类新增虚函数 `on_shutdown_impl` / `on_error_impl`（**默认复用 cleanup 语义**），并 `final` 转发 `on_shutdown` / `on_error`：停看门狗 → 运行清理 → `destroyBond`。`on_error` 返回 SUCCESS → 状态回 **UNCONFIGURED**（对齐 rcl 默认状态机 errorprocessing→unconfigured，保留可恢复性）。被管节点在 `deactivate / cleanup / shutdown / error` 时**停止产出控制数据**（停定时器、发布器 on_deactivate / reset），**不**残留有效 setpoint。

### (c) bond 失联检测（对齐 Nav2，但有意偏离一处）

基类实现 `createBond` / `destroyBond`，对齐 `nav2_util`：`bond::Bond("bond", get_name, shared_from_this)`、`setHeartbeatPeriod(bond_heartbeat_period)`、`setHeartbeatTimeout(4.0)`、`start`。**与 `nav2_util` 默认不同**：节点侧**不**把 `bond_disable_heartbeat_timeout` 置 true，**保留节点侧心跳超时**—— 使被管节点能检测 **manager 失联**（安全优先）。launch 侧 `bond_timeout` 由 `0.0` 改为 **5.0**（与已选节点兼容的失联检测；manager 检测到被管节点死亡 → 硬复位）。

### (d) 失效停机（节点侧看门狗）

`on_activate` 建 250 ms 看门狗轮询 `bond_->isBroken`；**仅当 bond 曾建立过**（`on_formed` 置位）**后断开**才触发 `on_bond_broken`（默认：真实 `deactivate→cleanup` 转移，状态回 UNCONFIGURED，setpoint 停发）。**未**建立过（无 manager 的独立运行，如既有验收台架）**不**误停。

### (e) 启动期 lifecycle 预热与 bond 时序

**根因两层**：① Nav2 lifecycle manager 的 `change_state` 走 `nav2_util::ServiceClient`，默认**无限超时**，本机 DDS 发现存在「首个服务调用超时」特性 → manager 在节点服务尚未完成发现时发起 configure 会**永久阻塞**，后续 activate 永不发生；② 节点侧在 **configure** 就建 bond 并开始 4 s 心跳超时，而 manager 只在 **activate** 才建其侧 bond，configure→activate 间隔 > 4 s（manager 卡住时必然如此）即触发 broken → `on_bond_broken` 失效停机。

现口径：

- **预热**：`air_lifecycle_prewarm.py` 对四个被管节点各调用一次 `/<node>/get_state`（3 次重试，容忍首次发现超时）；**只预热、不改任何节点状态**；完成后 launch 的 `OnProcessExit` 才启动 Nav2 `lifecycle_manager`；失败打印 `[prewarm] ... unavailable/timed out` 便于定位。
- **bond 改在 activate 建立**：`on_configure` **不再** `createBond`；`on_activate` 成功后才 `createBond` + `startBondWatchdog`，与 manager 的 activate 侧 bond **同拍**；bond 失效安全语义**不变**（已建立的 bond 断开仍触发失效停机）。
- **不动**：不改 Nav2 `lifecycle_manager` 本体、不引入自定义 manager、不改 `bond_timeout`（manager 5 s）/ `bond_heartbeat_period`（节点 0.1 s）、不改空中节点控制逻辑与感知门限。

### (f) 控制权交接时序：等「起飞完成（悬停）」再 release

`trajectory_tracker` 只在被**显式授权**（`active_controller==trajectory_tracker`）时接管；授权由 `takeoff_controller` 的 `/agc/air/release_control` 移交。**必须等悬停**：`takeoff_controller` 是**唯一**发 ARM / Offboard-mode 的节点，提前 release 会停其 tick → 飞机**永不 arm**（实测 start 时尚未 arm、悬停发生在 start 后约 10–14 s）；且过早接管会让 tracker 以当前近地高度为基准而**不**继续爬升。

- 由 `task_manager`（唯一任务协调者）在 `reset_phase` 后、等待「起飞完成（悬停）」再调 `release_control`；控制权交接属**任务决策**，不耦合进 `takeoff_controller` 的飞行时序。
- 悬停判据 = `/agc/air/odom` 世界 ENU z 相对**起飞前基准**（本 run 最小 z，即地面高度）的爬升量 ≥ `air_hover_climb_m`（默认 **2.3**，对齐 `air.yaml` 的 `takeoff_altitude_m=2.5` / `hover_tolerance_m=0.25`）；`air_hover_timeout_s`（默认 **18.0**，后放宽到 **45.0**）为有界等待上限，超时如实拒绝 start（`INFRA_FAILURE`）。轻量栈整段跳过。
- 参数 `release_service` / `air_odom_topic` / `air_hover_climb_m` / `air_hover_timeout_s` 单一来源 `base.yaml`，节点不得覆写。
- **限制**：`release_control` 为**每进程一次**（`takeoff_controller.released_` 锁存）→ 单 run 单 episode，多 episode 需重启 launch（与 runner 现况一致）。

### (g) PX4 姿态四元数字段序 = Hamilton `[w,x,y,z]`

px4_msgs / uORB `VehicleOdometry.q` 为 `float32[4]`，`q[0]` 即实部 `w`（注释「First value NaN if invalid/unknown」；ekf2 工具链的 ULog 转换脚本亦按 `q[0]→qw` 解析）。实测 raw `q=[0.877,0.004,0.002,0.480]`：按 `[w,x,y,z]` 解析得 ENU 偏航 **32.7°**（与 PX4 `vehicle_attitude` 31.9°、被令偏航 32.7°、目标方位约 33° 一致）；按 `[x,y,z,w]` 解析得 **89.5°**（即修复前的错误上报值）。

- 修复：`px4AttitudeToEnu` 按 `Quaternion q_px4(w=q[0], x=q[1], y=q[2], z=q[3])`；单测 identity 字面由 `{0,0,0,1}` 改 `{1,0,0,0}`，并新增回归用例 `AttitudeFieldOrderIsPx4HamiltonWxyz`（58.1° NED → 31.9° ENU，容差 1e-3°）拦字段序回退。
- **影响面**：`px4AttitudeToEnu` 是 `px4_adapter` 唯一姿态归一化入口，决定 `/agc/air/odom` 的 `pose.orientation` 及由此推导的机体速度。解析错约 58° 会让感知的 FOV 门把目标判在视场外（`visibility_rate≈1.4%` → 无持续获取 → `TIMEOUT`），也让 tracker 的机体速度反馈与接管初始 yaw 被旋转错。任何**依赖 `/agc/air/odom` 姿态 / 机体速度**的旧空中结论（航向 / 机体速度 / 速度 P95 等）建立在错误口径上，须按新解析**重验**；本条只登记影响，**未**在旧 run 上重跑。
- 修后同 run 因果链：相位复位 → 起飞完成 / 悬停 → `release_control` 移交 → tracker 接管（唯一授权）→ `start OK`；终态 **`TRACKING_SUCCESS`**、`visibility_rate=0.982`（335/341）。证据 `experiments/w6-task-eval/20261019-s08_static_none_nominal_capture-0-225005-4480/`。

## 不做什么（边界）

- **不**用 `undeclare_parameter` 做 cleanup（静态类型参数不可注销）。
- **不**把节点侧 `bond_disable_heartbeat_timeout` 置 true（manager 死亡时节点会静默继续，与「失效停机」冲突）。
- **不**用固定延时启动 manager（延时无法覆盖发现慢的偶发情况）。
- **不**自写 lifecycle manager（偏离 Nav2 复用，且需自行实现 bond 监控）。
- **不**关 bond、**不**靠延长超时掩盖 manager 卡死。
- **不**让 `takeoff_controller` 自动释放控制权。
- **不**按「差角补偿」修姿态（错的是字段序而非恒定偏置），也**不**只在 `air_perception` 内修（须在唯一归一化点 `px4_adapter` 修正）。
- **不**改冻结 9 消息 / 服务 ABI、**不**变唯一执行口语义、**不**新增第二 ROS 命令者（bond 为 lifecycle 配套，非 ABI、非命令者）。
- ~~**不**改感知量程 / 站距参数：`range_max_m=12.0` 与空中站距带 `[8, 15] m` 的几何盲区**已裁定保留**~~
  **（本条已于 2026-11-03 作废，见下）**

  > **作废理由**：该条把 12.0 当成"环境边界"，但 12.0 **不是物理极限**，而是提交 `40f4b91`
  > **手填、无推导记录**的魔数。按相机实际能力反算，12 m 对应机体 9.8 px，恰是 Johnson 判据的
  > 「**辨认**」距离—— 即"把辨认距离当成检测距离用"，属**量纲错位**，不是保守取值。
  > 物理上限实为 **112.9 m**（相机 640×480 / hfov 1.74 rad → 367.8 px/rad；高亮球 1.2 m；
  > 检测器 `min_area_px=12`）。
  >
  > **现行值**：`range_max_m = 30.0` = 任务下限 26.25 m（`spawn_layout` 开局几何）+ 3.75 m 余量，
  > **远低于** 112.9 m。推导见 `agc_perception/config/perception_sensors.yaml` 文件头。
  > 站距带上沿 `safe_max=11.2` **不变**—— 它由安全层几何定（`10.2 + hysteresis 1.0`），与量程无关。
  >
  > **因此 `rmax` 不再可当"已知环境边界"忽略**：若 `metrics/perception_health.json` 仍报
  > `rmax` 占比偏高，说明是**真问题**（目标被推到 30 m 外，例如布局变更未同步、或
  > `spawn_layout` 与场景覆盖冲突），须排查。
- **未实现 / 后续**：`bond_respawn` 重连策略未启用（只验证失联可判，未验证 respawn 恢复）；实机独立急停不在本条范围；感知 v2（站距上限约 11.5 m 或量程 16 m，二选一）须另立决策。

## Considered Options

- **保持薄基类 + `bond_timeout=0`** —— 被否：失联不可判、退出清理不明。
- **完全照抄 `nav2_util`（节点侧关闭心跳超时）** —— 被否：manager 死亡时节点静默继续，与「失效停机 / 不静默继续上游命令」冲突。
- **cleanup 用 `undeclare_parameter`** —— 被否：实测对静态类型参数抛异常。
- **只做「替代看门狗」不实现 bond** —— 被否：`bond_timeout` 仍须为 0，且无法复用 Nav2 manager 语义。
- **`on_error` 返回 FAILURE** —— 被否：状态趋 FINALIZED 不可再配置，丢失可恢复性。
- **固定延时启动 manager / 自写管理器 / 提高 bond 超时** —— 均被否（见边界）。
- **保留 `[x,y,z,w]` 解析并按差角补偿** —— 被否：字段序错误不是恒定偏置，补偿无法在所有姿态成立且污染速度换基。
- **由 `takeoff_controller` 自动释放控制权** —— 被否：控制权交接属任务决策，不应耦合入飞行时序。

## Consequences

- **正面**：`cleanup→configure` 可重复（无重复参数异常）；`shutdown / error` 走完整清理（资源全释放、setpoint 停发）；被管节点死亡 manager 可判（"IS DOWN" 硬复位）、manager 死亡节点失效停机回 UNCONFIGURED；启动期 lifecycle 卡死不再导致 `px4_adapter` 失效，零可见的链路主因被消除；整链**评价可用**（真实终态，非 `TIMEOUT`），`visibility_rate` 0.014 → 0.982。
- **代价 / 限制**：新增依赖 `bond` / `bondcpp`（`agc_air`）；节点侧保留心跳超时（偏离 `nav2_util` 默认）→ manager 重启若超过心跳超时会使节点先失效停机（**安全保守**，manager 复位后可重新 configure）；启动多 4 次只读 `get_state`（毫秒级）；manager 若在**已发现**服务上仍丢失应答，理论上仍可能阻塞（Nav2 无限超时固有限制，本条不解决）；旧姿态 / 机体速度证据须重验。
- **取证方式**：`run_w6_r034.sh` + `w6_r034_bench.py`（Phase A 实跑真实节点 + 真实 `lifecycle_manager`）+ `check_lifecycle_resource_state.py`（Phase B 自包含核查），覆盖 configure / activate / deactivate / cleanup 循环 ≥2 轮、direct shutdown、error 注入、manager / 被管节点死亡四类；实测杀被管节点约 6 s 后 manager 打印 `SERVER ... IS DOWN`、杀 manager 约 4 s 后节点打印 `bond 断开 → 失效停机` 且 `ros2 lifecycle get` 回 `unconfigured`。启动健壮的**取证**另见 run `w7-rl-b/20261021-w7-rl-b-204755-7986`：`[prewarm] <node>: ok`、四节点均 `bond formed`、**0 条 `bond 断开`**、三个种子均 `INTERCEPT_CONFIRMED`（`vis=0.992/0.992/0.996`）。
- **回归防线**：prewarm 日志 + `no_pose` 计数 + 启动期 manager 是否到 Activating 可在批次日志直接检查；姿态字段序有单测锁定。

## 参考

- 任务 FSM 与终态锁存（`release_control` 由任务协调者触发）：[ADR-0014](0014-task-fsm-and-scenario-transaction.md)
- 空中控制权与 permit：[ADR-0010](0010-safety-thresholds-and-failsafe.md)
- PX4 工具链与链路：[ADR-0005](0005-px4-toolchain-and-link.md)
- 整链覆盖与同 run 因果记录：[ADR-0018](0018-acceptance-and-coverage-matrix.md)
- 感知口径与能力边界（`rmax` 几何盲区）：[ADR-0009](0009-perception-truth-derived-and-vision-path.md)
- 契约：[硬约束](../ROS2迁移交接文档.md#hard-constraints)、[执行口](../ROS2迁移交接文档.md#execution-port)、[参数入口](../ROS2迁移交接文档.md#params)、[消息](../ROS2迁移交接文档.md#messages)、[命名空间](../ROS2迁移交接文档.md#namespace)
