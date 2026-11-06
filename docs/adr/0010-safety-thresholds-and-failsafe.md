<a id="top"></a>
# 安全阈值、末端失效停车与安全屏障

## Status

accepted（2026-11-02 由 ADR-0021 / 0025 / 0042 / 0048 / 0050 合并；结论未变）

## 背景

地面与空中各有一次「安全层看起来存在、实际不成立」的事故级发现：地面三档距离阈值继承自 40×40 m 小场地旧配置，作业区放大到 80×80 m、车速提到 1.5 m/s 后没有推导依据；末端（GZ `DiffDrive`）对命令中继死亡**没有任何超时保证**；安全层把「触发拍 + 前向扫描 ≤ contact」当成碰撞，正常提前停车被统计成高不可行率；空中安全参考只是**端点**安全而非**轨迹**安全；空中控制权用「发布者计数 > 1」判定，既漏报真实争夺也误报合法静默发布者。这五项都必须给出**可复核口径**，而不是补一句注释。

约束真源见 [#hard-constraints](../ROS2迁移交接文档.md#hard-constraints)与 [#execution-port](../ROS2迁移交接文档.md#execution-port)（**唯一执行口语义**）。

## 决策

### (a)：顺序是不变量，绝对值是可标定量

硬约束 **** 保留的是**顺序不变量** `紧急 < 碰撞 < 安全`；三档**绝对值**由地面安全层按实测动力学标定，属契约真源的可标定量。旧值 `0.7 / 0.9 / 2.4 m`（源自旧树无人机避障配置、为小场地慢速设定）**作废**，文档 / 报告不得再引用。

现行三档：**`紧急 1.0 m < 碰撞 2.0 m < 安全 4.0 m`**，由 `collision_monitor` 的 zone 承载（`StopEmergency@1` / `StopCollision@2` / `SlowSafety@4`），参数单一注入 `src/agc_ground/config/ground.yaml`。

### (b) 标定口径：Nav2 时间窗 × 速度 + 制动距离

绝对值**不得**由旧值等比放大，按 Nav2 / 工业安全惯例推导（`collision_monitor` 默认 `time_before_collision: 2.0 s`，本项目取 `t_before ∈ [1.2, 2.0] s`）：安全档 = `v_car_max · t_before + 裕度`；碰撞档 = `v_car_max² / (2a) + 车体半长 + 裕度`（`a` = 锁轮制动加速度）；紧急档 = 车体半长 + 固定小裕度；再计**相对接近速度**（闭合上限 ≈ `v_car + v_target`）取包络。

实测标定输入：`v_car_max = 1.5 m/s`、`a ≈ 0.9 m/s²`、`t_before ∈ [1.5, 2.0] s`、车体半长 ≈ `0.5 m`、裕度 `0.3–0.5 m` → 碰撞 ≈ 2.0 m、安全 ≈ 4.0 m、紧急 ≈ 1.0 m。实跑佐证：车自立柱前直行逼近，`cmd_vel 0.80 → 0.24`（`SlowSafety@4 m`）`→ 0.00`（`StopCollision@2 m`），停在柱前未接触。

### (c) 地面平台保形换装（不改驱动内核）

地面平台改为**差速轮式 UGV（Husky 级尺度）**，模型取自 Gazebo Fuel 官方模型，**保形换装**：只替换**视觉 mesh + 碰撞体**，并按新尺度回填质量 / 惯量 / 几何；**保留** `DiffDrive` 真实物理内核（不改阿克曼、不动执行口语义）。保留的不变量：`car/base_link`、`car/lidar_link` 及话题 `/agc/car_lidar`、`car/capture_net`（2 m 网面）+ `car/jammer`、GZ `DiffDrive`、桥入 `/model/agc_car/cmd_vel`、桥出 `/agc/sim/ground_odom_raw`、`src/agc_sim/config/car.yaml` 为**唯一**参数源。

配套模型修正：2 m 捕获网面原竖在车头正前方、遮挡 `gpu_lidar`（正前方恒返回 0.50 m，安全层"看不见"障碍）→ 网面抬至 `x 0.55 / z 1.60`（网面下沿 base z 0.60 > 雷达 z 0.48），既解开遮挡又贴合目标机 ~2 m 高度。

### (d) 安全层感知源：`scan` + 标定过的 `source_timeout`

<a id="source"></a>
<a id="source_timeout-calibration"></a>

- **感知源用 `scan`（2D `LaserScan`）而非点云**：水平扫描天然不返回地面，避免点云高度带 / 地面滤除的调参脆弱性。
- **`source_timeout` 由 `5.0 s` 改为 `0.3 s`**（`src/agc_ground/config/ground.yaml` 单一注入）。原值照抄 Nav2 官方示例、未经本车标定：失源盲行尺度可达 `1.5 × 5.0 = 7.5 m`，远超 4 m 安全档。
- **判据**：总停距 = 盲行 `d_blind = v_max · T` + 制动 `s_brake = v_max²/(2a)` 必须 ≤ 碰撞档 2.0 m，且 `T ≥ 3 ×` 扫描周期（10 Hz → 0.1 s）。取 `T = 0.3 s`：`0.45 + 1.25 = 1.70 m < 2.0 m`（余量 0.30 m），并与 `src/agc_perception/config/perception.yaml` 的 `source_timeout_s: 0.3` 同口径。
- **语义取证**：本机 Jazzy `nav2_collision_monitor` 的 `Source::getData` 对失效源返回 false 并**封锁机器人**（`source.hpp`：`@return false if an invalid source should block the robot`）—— 源超龄即**停车**，非静默透传；由故障注入实测确认（`experiments/w5-ground-nav-safety/<run_id>/metrics/r008.json`）。
- **`stop_pub_timeout` 置极大**：使安全层持续发布（含零速），否则 idle 时停发零速会让任务门控的 `cmd_vel` 回环确认**死锁**。

### (e) 末端失效停车：意图 / 执行分离 + 死区看门狗

执行中继失效已从"中置信度风险"转为**已取证事实**：静态取证（`libgz-sim8-diff-drive-system.so` 无 `timeout` / `deadman` token）与动态取证（`SIGKILL` 中继后 5 s 采样窗内持续运动，位移 7.45 m、末端仍 1.458 m/s）共同确证。做法：在**唯一执行通道内部**（GZ 服务器进程内）建末端失效停车，**双话题 + 死区看门狗**—— 守门人插件 `agc_cmd_deadman`（`gz::sim::System` + `ISystemConfigure` + `ISystemPreUpdate`）成为 `DiffDrive` 命令口的**唯一写入者**：

- ROS 侧话题名**不变**（`/model/agc_car/cmd_vel`），桥把其 gz 侧改桥到**意图话题** `/agc/sim/cmd_intent`；
- 插件订阅意图；`PreUpdate` 中 **fresh → 转发缓存值，stale → 发零速** 到 `DiffDrive` 默认订阅的 gz `/model/agc_car/cmd_vel`（**不改 SDF 的 `DiffDrive` 主题**）；
- 超时由 SDF `<timeout>` 注入，值源自 `src/agc_sim/config/car.yaml` 的 `model.cmd_deadman_timeout_s = 0.3` → launch xacro arg（参数单一来源），与中继 `watchdog_s = 0.3` 同量级；
- 时钟用 `std::chrono::steady_clock`，与仿真暂停 / ROS 时钟**冻结**解耦。

**边界**：插件 SHALL NOT 构成**第二 ROS 命令者**—— 只转发 ROS 已下达的值或归零，**永不自创运动**（无独立目标 / 轨迹 / 控制律），不产生任何 ROS 话题 / 节点；它能作为"保证"的**唯一**原因是位于 GZ 服务器进程内、与物理引擎同生命周期，ROS 侧全部死亡时仍生效。

验收：`SIGKILL` 中继 → 真值停稳 **0.849 s**（上界 2.5 s）、残余位移 **0.729 m**（上界 2.0 m）；正常命令不误触发；重启中继即恢复（`experiments/w5-ground-nav-safety/20261015-w5-r009-0/metrics/r009.json`）。

### (f) 真实碰撞与不可行率的诚实口径（r-027）

历史字段 `shield_infeasible_rate` / `ticks_total` / `ticks_triggered` / `ticks_infeasible` **保留不动**（不静默重算旧历史），新增 `definition_version`（`{"shield_infeasible_rate": "proxy_v1", "collision_truth": "gz_contact_v1", "true_shield_infeasible": "gz_contact_v1"}`）与 `metrics_comparability` 文字，使「同名字段在不同版本下含义不同」**可判定**。

- **真实碰撞 = GZ 接触真值**：`car/base_link` 加 contact sensor（监测同 link 的 `base_collision`），经世界已加载的 `gz-sim-contact-system` 发布 `gz.msgs.Contacts`，由 `bridge.yaml` 桥为 ROS `/agc/ground/contact`。`run_logger` 逐帧判**车↔非车**接触对（一侧 name 含 `agc_car`、另一侧非空且不含 `agc_car`），**排除世界地面**（`ground_plane`，车体复位瞬间轻微没入地面属建模产物），按**上升沿**去重，记 `collision_count` / `collision_events`（`{t_sim, other, depth, position}`）。
- **触发事件与干预时长**：`trigger_events` 取 `triggered && !prev_triggered_` 上升沿；`intervention_duration_s` 用**仿真时钟**增量累计（`dt > 0` 才累加）。
- **剩余停车裕度**：`margin = scan_min_forward − brake_d`（`brake_d = v²/(2·a_brake)`，`a_brake` 取 (b) 实测），维护 `stopping_margin_min_m` / `stopping_margin_negative_ticks`；无 `scan` 的触发拍记 `ticks_triggered_no_scan` 且不计入裕度。
- **真实安全不可行**：触发期结束（下降沿）时若该期内发生过真实接触 → 计一次；episode 在触发期内结束（无下降沿）且已接触 → `finalize` 补记一次（honest 优先，避免漏报）。`true_shield_infeasible_rate = infeasible_events_total / trigger_events_`；`trigger_events_ == 0` 时输出 **`null`**，**不以 0 冒充**。
- **零速停于阈值外不计碰撞**：阈值外缓停（`v≈0`、无接触）→ 无 GZ 接触 → `collision_count == 0`。`ticks_infeasible`（触发拍代理）与真实碰撞**分离**，互不冒充。
- **缺数据 → `not_applicable` 掩码**：`{"scan_derived": total_ticks_ == 0 || scan_samples_ == 0, "trigger_derived": trigger_events_ == 0, "collision_truth": contact_topic 参数为空}`。
- `proxy_v1` 与 `gz_contact_v1` **均不与旧 RL 安全集指标直接对照**（口径 / 分母不同），写入 `metrics_comparability`。

验收 `run_w6_r027.sh` + `check_safety_infeasible_rate.py`：Phase A 负对照（阈值外提前停车 → `collision_count == 0`）、Phase B 正例（spawn 几何重叠 → GZ 真实接触 → `collision_count >= 1` 且 `other` 含 `pole`）、Phase C 核查 (a)…(f)；产物落 `experiments/w6-task-eval/<run_id>/metrics/r027.json`。

### (g) 空中安全屏障：联合复检 + 扫掠复检 + 显式不可行（r-033）

此前参考**不等于**安全轨迹：逐个障碍推参考点再按目标间距后投影（投影不可交换，后投影可重新落入前约束）、只检**端点**无**扫掠**检验、静态表不含车 / 动态障碍、无「不可行」显式输出。现行口径：

- **联合约束集**：静态障碍约束与目标间距约束建为**同一条**约束集（XY 圆盘，修正后半径 = 硬半径 + 余量）。`apply` 三步：候选端点不可行时做**联合投影**（对所有违约盘反复径向推出，直至**同时**满足或耗尽迭代预算）→ **终检**（端点满足全部约束 **且** 当前位置→候选的直线段不穿约束，`feasibleXY` ∧ `sweptClear`）→ 通过则采用（`reason="adjusted_obstacle"` / `"adjusted_target"`，(j) 起按**触发圆盘**归因），否则显式不可行。
- **扫掠复检**：对每个**起点在外**的约束盘，检验当前位置→参考端点的**线段最短距离** ≥ 修正后半径；起点已在盘内的约束跳过（属「自当前位置逃出」，由不可行路径处理）。端点安全但连线穿障 → `reason="infeasible_swept"`。
- **显式不可行路径**：`infeasible=true` + `reason ∈ {infeasible_joint, infeasible_swept}` + `action ∈ {hold, escape}`。当前位置本身安全 → **hold**（参考 = 当前位置，速度 / 加速度前馈清零）；否则 → **escape**（联合投影逃到最近可行点）；连联合投影亦不收敛 → 对最严重违约约束做单约束径向推出。**不**向 LQR 给可能不可达 / 会侵入约束的参考。
- **余量分层**（`air.yaml` 的 `trajectory_tracker.safety` 段）：修正后半径 = 硬半径 **+** `obstacle_margin`（跟踪误差 / LQR 滞后）**+** `reaction_time_s × max_speed_mps`（反应时间）**+** `reachability_margin`（可达性 / 制动）。绝对值是可标定量（对齐精神）。
- **二维静态限定模型**：只处理 XY 静态障碍圆盘 + 目标间距圆盘，**不**含车 / 动态障碍状态（记账 `unsupported`），**不**建模三维机体外形 / 载荷外伸 / 网几何。**不得**把二维立柱世界结论外推为三维通用安全。
- 诊断：`/agc/air/tracking_status` 每 tick 追加 `shield_infeasible` / `shield_reason` / `shield_action`（非 ABI、非命令者）。
- 验收：四场景台架（两障碍交叠 → `infeasible_joint`；端点安全但连线穿障 → `infeasible_swept`；目标快速闭合致盘冲突 → hold；真值最小净空按**硬半径**计 ≥ 0 且不可行事件计数 ≥ 3），产物落 `experiments/w6-task-eval/<run_id>/r033/bench.json`。本台架为**逻辑台架**，非整链 / 非 GUI。

### (h) 空中控制唯一权威：显式许可 + claim/ack 顺序（r-035）

以「拓扑数量」当「实际控制权」不能证明唯一命令者（本拍仍发 setpoint、计数含静默 publisher、task_manager 不订阅冲突标志）。现行口径：

- **权威 = 显式控制许可（lease）**：授权由交权路线中的**显式指定**承载（`/agc/air/active_controller`，`std_msgs/String`，transient_local）。交权顺序：先销毁 setpoint / OCM 发布器（真正让出唯一发布者），**再**指定 `trajectory_tracker`。**禁用**「仅凭发布者计数」决定权威。
- **ack = 新话题 `/agc/air/control_permit`**（`std_msgs/String`，transient_local + reliable；参数 `control_permit_topic`），每条 claim 为 JSON：`{"ev":"claim","by":…,"uid":…,"epoch":…,"permit":…,"conflict":…,"writers":…,"sp_hz":…,"competitor_uid":…}`。`self_uid` 在构造期生成（`getpid` + 随机数）→ 可区分**同名重复节点**。
- **不误报合法静默 publisher**：只有**显式 claim**（不同 `uid` 且 `by == own_name`）才算竞争者；`writers` 仅作告警，**永不**单独吊销权威。
- **冲突 → 已定义安全状态**：`tick` 先由 `active_controller` 推 `is_authorized_` → `updateConflict` → `permit = is_authorized_ && !conflict_` → 发布 `control_conflict`（**先于**任何 setpoint）→ 无许可则发布 claim 后 `return`（本拍不发 OCM / setpoint）。冲突期停发 control mode 与 setpoint（= relinquish，让 PX4 自身 failsafe 保持 / 降落）。竞争者持续 > `conflict_persist_s_` 置冲突，消失 ≥ `conflict_clear_s_`（默认 2.0 s）后清冲突并恢复（若仍被授权）。
- **重启不残留旧权威**：`on_activate` / `on_deactivate` / `on_cleanup`（含转发的 shutdown / error）重置授权 / 冲突 / 竞争者状态；`on_activate` 后从当前 `active_controller` 重新推导。
- **写者记账**（诊断，非 ABI）：`OffboardInterface` 记 `setpoint_write_count_` 与首末写入时刻，暴露 `setpointWriteCount` / `setpointRateHz` / `hasSetpointPublisher`，供回答「谁在写、频率、持续多久」。
- `control_conflict` 对 `task_manager` **只读**可观测（transient_local，变化时 WARN），**严禁**改其状态机 / 终态语义。`/fmu/in/trajectory_setpoint` 的唯一 ROS 发布器仍只在 `OffboardInterface`。

### (i) 第三方资产许可适用关系

<a id="third-party-license-note"></a>

(c) 中「Gazebo Fuel 官方 **CC0** 模型」的许可表述系当时**未核实**的断言（来源材料未随资产保留）。上游 Clearpath Husky ROS 资产族（`husky_description` / `husky_gazebo` / `clearpath_gz`）在 ROS Wiki / ROS Index 标 **`BSD`**（要求保留版权 / 许可署名），故第三方 mesh 的**许可**表述不再由本 ADR 断言：来源 / 许可 / 署名 / `sha256` 一律引用[第三方资产与许可](../conventions/第三方资产与许可.md)（许可**分列**，自有包 `Proprietary` **不外推**；未核实前登记为**未决**）。本注不影响保形换装口径、标定、`DiffDrive` 内核等其余决策。

### (j) 空中安全层的**垂直门控**（2026-11-04，用户裁定）

<a id="vertical-gate"></a>

(g) 的圆盘与飞行高度**无关**：每个静态障碍都被当成无限高圆柱。`yard` 实测（真源逐实体）：
42/42 个障碍**全部低于**地图派生飞行高度 14 m，安全圆盘面积合计 **6398 m²**（作业区 10000 m²，
占 **64%**）—— 最刺眼的单例是 `wall_n`（顶高 2.56 m）挡出 **17.0 m** 半径的禁飞圆盘。
⇒ 抬高在控制层**零收益**；本节是其落地项，也是 (g) 尾部「二维屏障的三维保真需另立项」的闭合
（**只做垂直门控**，不承诺通用三维）。

- **判据（含下降前视）**：障碍 `o` 的圆盘对本机生效 **除非**
  `z_ref − max(−v_z, 0)·reaction_time_s ≥ z_top(o) + c_clear`，
  其中 `z_ref = current_pos.z`（**实测**高度，**不是**参考高度—— 本层是参考滤波器、参考超前于
  实际，用参考会让圆盘在不该失效时失效；LQR 滞后余量已在 `dynamicMargin` 中）。
  下降速度前视使"下落穿越顶面"的圆盘**在到达之前即复活**，因此**不需要**状态机或滞回。
- **净空来源**：`c_clear = vertical_clearance_m`，运行期由地图 `flight_altitude.own_clearance_min_m`
  **同源注入**（不另立参数、不做第二真源）；`air.yaml` 的 0.5 仅脱机兜底。
- **顶高来源**：`world_map.obstacle_z_top(ob)` = 单图元 `z + size[2]/2`、复合体取**全部 part 的最大值**
  （与 `height_survey` 同口径）。真源本就含 `z` / `size`，本项是**派生链补一列**，
  **不新增 schema 键、不新增视觉能力**。
- **平行数组变五个**：`obstacle_{names,x,y,safety_radius,z_top}` 五者等长，在启动期**拒绝**
  不一致。`obstacle_z_top` **整体缺省 = 顶高未知 ⇒ 门控不生效**（保守退化为无限高圆柱，旧行为逐值
  不变）；**逐项**坏值（0 / 负 / NaN / ±Inf）一律拒绝—— 缺省**不取 0**，否则所有障碍会在正常巡航
  高度下静默失效。
- **门控只作用于静态障碍盘**：目标间距盘（`target_min_dist + target_margin`）**始终生效**，
  否则抬高即可无限接近目标，K1 视场与捕获几何随之失效。
- **归因可观测**：`shield_reason` 的 `adjusted` 拆为 `adjusted_obstacle` / `adjusted_target`
  （语义不变，只消除"目标盘导致"与"避障导致"的歧义—— 两者调参方向相反）；
  `/agc/air/tracking_status` 追加 `shield_rings_obstacles` / `shield_rings_gated_off` /
  `shield_rings_target` / `shield_gate_height_m`（非 ABI）。
- **K3 断言降级**：`own_height_covers_h_max_env` 由"硬前提"降为**推荐高度**—— 门控使"飞得比楼低"
  不再等于违约，但低于顶面时圆盘仍生效；断言本身保留（它守护"按地图定高自洽"）。
- **验收**：`src/agc_air/test/test_safety_shield_vertical_gate.cpp`（10 例：高于顶面 → 移除 /
  低于 → 生效 / 恰好等于 → 移除 / **下降穿越 → 到达前复活** / 上升不改变判定 / 五数组不等长拒绝 /
  逐项坏值拒绝 / 整体缺省 = 不门控 / 目标盘永不门控 / 归因）—— 圆盘集经**生产函数**
  `deriveRings` 取得，测试不复制投影逻辑。

## 不做什么（边界）

- **不做**三维通用安全承诺：(g) 是二维静态限定模型，动态障碍 / 车状态 / 三维外形 / 载荷外伸 / 网几何一律 `unsupported`。
- **不做**三维通用途中的其它事：(j) 只做**静态障碍的垂直门控**—— 不做三维栅格 / 三维规划 / 越障爬升路径生成（属任务层或后续立项），**不**建模机体外形，**不**把 `/agc/map` 改成三维（地面侧无消费者）。
- **不引入** QP / CBF 联合安全滤波（列为后续更优路线）；**不**为 `obstacle=dynamic` 新建执行节点、**不**改世界物理。
- **不**把 GZ 守门人插件做成第二命令者（无自创运动、无 ROS 接口）。
- **不**用「发布者计数」判定空中权威；**不**在冲突期仍发 setpoint。
- **不**以 0 冒充空集合统计（`trigger_events_ == 0` → `null`；缺数据 → `not_applicable`）。
- **不改**冻结 9 消息 / 服务 ABI、**不改**唯一执行口语义、**不新增**第二 ROS 命令者。
- **不**再引用旧阈值 `0.7 / 0.9 / 2.4 m` 或「对齐 Nav2 示例 `5.0`」作为现行取值依据。

## Considered Options

- **保留旧阈值 `0.7/0.9/2.4`（或等比放大）** —— 被否：新标度下无推导依据，且数值过小。
- **保持字面绝对值、新值只落 config** —— 被否：契约真源与实现长期不一致（真源说谎）。
- **换成阿克曼整车 / 整包引入 ROS2 仿真包 / 自建 mesh** —— 均被否：形态不符、违包边界、收益低。
- **在 `/model/agc_car/cmd_vel` 上自回环守门** —— 被否：插件会把自己的零 / 上次值当心跳，掩盖真实失源。
- **ROS 侧守门 / 信号处理** —— 不足：验收用 `SIGKILL` 不可捕获，节点自身也可能是故障源。
- **直接改 `shield_infeasible_rate` 为真实接触口径** —— 被否：破坏历史可比，旧 run 无法解释。
- **仅用几何（`scan ≤ contact`）当接触真值** —— 被否：几何不产生物理接触，提前停车也会命中（正是 r-027 病灶）。
- **顺序单遍投影 / 仅检端点 / 无解仍返回投影结果** —— 三条全被否：分别是 r-033 的三个病灶。
- **冲突时只置标志、仍本拍发 setpoint** —— 被否：即争夺未停的病灶本身。
- **新增独立「许可仲裁节点」** —— 被否：会引入第二权威源，与唯一执行口语义冲突。
- **(j) 让障碍"消失"或缩半径来体现高度** —— 被否：那是改几何真源，会让物理世界与安全层不一致。
- **(j) 用状态机 / 滞回处理"下降到顶面以下圆盘复发"** —— 被否：多一份状态就多一个与 odom 失步的分支；下降速度前视是闭式判据，可在单测里逐条断言。
- **(j) `obstacle_z_top` 缺省取 0** —— 被否：所有障碍会在正常巡航高度静默失效（与同类的"静默漏障碍"），故缺省取 `+inf`（门控不生效）。

## Consequences

- **正面**：三档阈值有可复核推导与实跑佐证；末端失效停车在 ROS 全死时仍生效；不可行率区分「触发代理」与「真实接触」并可判版本；空中参考从端点安全升级为联合 + 扫掠安全，无解时进入显式 hold / escape；空中权威由显式许可判定、冲突先置位后停发。
- **代价 / 限制**：`source_timeout` 收紧到 0.3 s 使安全层对源抖动更敏感（需 10 Hz 稳定扫描）；GZ contact sensor 的 gz 话题名由**作用域名**决定（换世界 / 换模型须同步核对），接触证据仅覆盖 `base_collision`，未覆盖轮 / 载荷几何；空中修正半径因叠加反应 + 可达性余量而更保守；claim/ack 依赖 DDS 发现（本地测试网内成立）。
- **未决 / 后续**：真实安全不可行的判定阈值（裕度门限）、多接触体聚合；空中冲突恢复后是否需重置参考相位。二维屏障的三维保真已由 (j) **只做垂直门控**的方式部分闭合；**仍不做**通用三维安全。
- **(j) 的代价 / 限制**：垂直门控消除了"顶面在脚下"的虚假圆盘，但**不消除"圆形"带来的浪费**——`wall_n` 的 17.0 m 半径主要来自外接圆包住长薄墙，门控只让它在该高度失效，不解决形状拟合差；改用逐障碍 OBB 属另立项（ADR-0010 边界外）。门控**不**降低安全层介入次数：实测 `s01`（无障碍场景）仍有 `trigger_events=2`，触发源是**目标间距盘**。

## 实施回填

以下结论曾写在 `src/agc_task/config/px4_failsafe_lock.yaml` 的注释里，现收敛到此：

- **桥时间同步必须关闭**（`UXRCE_DDS_SYNCT=0`）：开启时 uXRCE-DDS 桥把 PX4 时间戳推到
  墙上时钟尺度，与 gz `/clock` 的仿真时钟映射产生负 / 离奇时间戳（`sec≈−1.7e9`），
  使下游年龄门失效、`rclcpp::Time` 负值崩溃。仿真以 gz `/clock` 为唯一时间基准。
- **仿真磁力计必须显式启用**（`SENS_EN_MAGSIM=1`）：PX4 官方 gz `x500` 机型无磁力计传感器，
  `sensor_mag_sim` 用 GPS 位置 + 世界磁场模型合成，但参数默认 0。关闭时链路无磁力计 →
  `Compass Sensor 0 missing` / yaw 估计误差 → EKF 不发 `vehicle_odometry` → 目标机永不 ARM。
  `SYS_HAS_MAG=0` / `EKF2_MAG_TYPE=5` 不是解法（实测 `Ready for takeoff` 降为 0 次）。
- **"目标没起飞"不得靠感知致盲间接暴露**：量程改为 30.0 m 后，己方机与目标地面高度差
  14 m 时斜距仍小于量程，地面目标照样产生航迹。只能由 `target_takeoff_guard` 按真值 z 判定。
- **`px4-rc.params` 由 `scripts/lock_px4_failsafe_params.sh` 生成**，使每次 SITL 启动确定化；
  取值清单见 `src/agc_task/config/px4_failsafe_lock.yaml`。


## 参考

- 契约：[#hard-constraints](../ROS2迁移交接文档.md#hard-constraints) / [#execution-port](../ROS2迁移交接文档.md#execution-port) / [#messages](../ROS2迁移交接文档.md#messages) / [#params](../ROS2迁移交接文档.md#params)
- 相关决策：[ADR-0002](0002-docs-source-of-truth-and-reference-discipline.md#top)（引用纪律）、[ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与证据）、[ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)（地面主控与安全层）、[ADR-0003](0003-nav2-paradigm-absorption.md#top)（Nav2 吸收）、[ADR-0017](0017-time-budget-and-clock-sources.md#top)（时间预算与源时刻）、[ADR-0019](0019-lifecycle-and-startup-robustness.md#top)（生命周期）
- 第三方资产与许可：[`docs/conventions/第三方资产与许可.md`](../conventions/第三方资产与许可.md)
- 证据：`experiments/w5-ground-nav-safety/`（r008 / r009）、`experiments/w6-task-eval/<run_id>/metrics/r027.json`
