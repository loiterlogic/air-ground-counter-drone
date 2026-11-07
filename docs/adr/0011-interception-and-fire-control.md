<a id="top"></a>
# 拦截口径与火控：发射式网、交战门与在飞生命周期

## Status

accepted（2026-11-02 由 ADR-0015 / ADR-0022 / ADR-0024 / ADR-0035 / ADR-0058 / ADR-0079 / ADR-0091 / ADR-0111 合并；结论未变。其中「入包络即命中」的占位裁决口径已被后续「预演弹道能命中才开火」替换，旧口径作废）

## 背景

拦截是「移动式主动拦截」研究主线的一半，必须由地面移动平台承载，而纯仿真里既没有真实电磁场模型，也不允许把「接近到 R 米」当作拦截完成。三条约束叠在一起逼出了本组决策：捕获必须是**可物理复核**的机制（网、弹道、可达集），干扰只能是**行为级等价**（强制飞控模式 / 断链路触发 failsafe），而火控必须在**不破坏冻结 ABI**的前提下逐步从闭式占位演进到真实弹道。落地过程中又暴露两类实现缺陷：把测量噪声当目标速度（假速度放大成 1–2 m 的打空）、以及在飞网因发射资格门提前返回而永久无结局。

## 决策

### (a) 拦截形态 = 物理捕获 + 行为级电子干扰

- **物理捕获**：以发射式网的物理模型判定，终态 `INTERCEPT_CONFIRMED` + `reason_code = CAPTURE_NET`。
- **电子干扰**：**行为级等价**—— 对入侵者强制 `RTL` / `LAND` / `HOLD`，或用「停发 Offboard 指令」触发 PX4 自身的 offboard-loss failsafe 等价「失联」；`reason_code` 区分 `JAM_RTL|JAM_LAND|JAM_HOLD|JAM_LOST`。**真实电磁场不建模**（仿真器无 EMI 传播模型，仅有路径损耗）；「停流 ≠ 数据链失联」的机制区分见 [ADR-0015](0015-jam-authorization-and-confirmation.md)。
- **执行者**：捕获 / 干扰由**地面移动平台**承载；无人机只做观测、standoff 跟踪与自保。
- **终态分期**：**阶段 A = 跟踪、阶段 B = 拦截**；`INTERCEPT_CONFIRMED` 只在阶段 B 启用，不新增消息枚举（冻结 9 消息字段 / 顺序不得变更）。
- **入侵者必须是自主飞控对象**：`intruder_uav` 为第二个 PX4 SITL 实例（独立 uXRCE-DDS agent + 独立命名空间 `px4_1`，`target_system=2`），不再是脚本刚体—— 因为「被干扰后能自主 RTL / LAND / HOLD / 失联」只有真飞控能承载。注入路径为经 uXRCE 发 `px4_msgs/VehicleCommand`（`VEHICLE_CMD_SET_NAV_STATE`）；`SIM_GZ_EN_*` / `SYS_FAILURE_EN` 在本项目 vendored 的 v1.15.4 里零命中，故**不**用 gz 故障注入。
- **可行性闸门（已通过）**：双 PX4 实例共存、命名不变量（预 spawn 机型 rename 为 `intruder_uav` 后 attach，不 spawn）、mode 注入均经最小实验验证。关键坑：入侵者**必须**设 `PX4_SIM_MODEL=gz_x500`（决定 airframe 含 `SENS_EN_MAGSIM` / `SENS_EN_GPSSIM`），漏设则无磁罗盘 → 无法 arm。

### (b) 捕获机制 = 发射式网，交战包络由物理模型推导

- 车载件 `car/capture_net` 的语义是**网发射器 / 发射出去的网**，不是「车顶固定圆框」；网由车射出并在空中展开，可作用于**非固定高度**的目标。
- **网发射物理模型**：发射初速 `v0`、抛射角 `θ`、重力 `g`、空气阻力、展开时长 `t_exp`、展开后有效直径 `d`；其**可及集（reachable set）**即交战包络。包络是**可标定量**，由模型算得，**不**拍一个半径常数。
- 基线参数（`base.yaml` 单一注入，节点不得覆写）：`net_v0_mps=6.5`、`net_angle_deg=75`、`net_g=9.81`、`net_diameter_m=1.0`、`net_drag=0.9`、`net_t_exp_s=0.2`、`fire_cooldown_s=2.0`、`net_flight_timeout_s=3.0`、`launcher_height_m=0.0`。目标高度超出基线包络时，`v0` / `θ` / `timeout` 由地图几何派生（apex = 目标高度 + 0.65 m，`θ=85°`，timeout = 落地 + 0.3 s）。
- **表述纪律**：不得把捕获表述为「目标穿越固定 2 m 圆网面」（旧判据作废），不得把 `TRACKING_SUCCESS` 表述为「拦截完成」。

### (c) 裁决器可插拔；「调用方不改」= 对外可观测契约不变

- `capture adjudicator` **SHALL** 为可替换接口：现阶段闭式几何判定，后续换逐帧弹道判定器时**调用方（`task_manager`）不改**。
- 「不改」**限定为对外可观测契约**：最终终态与 `reason_code`、冻结 9 消息 ABI、唯一执行口语义均不变，且**不新增第二 ROS 命令者**。
- **内部允许演进**：裁决器内部可有 **shot 生命周期**（射击请求 / 发射 / 到达 / 命中 / 失手 / 取消 / 冷却）与异步事件；消费侧可在既有 ABI 内做必要的状态清理与关联。字面「零改动」的读法作废—— 它会把真实弹道挡死。
- 替换**不是**「零改动」，而是「**对外零破坏**」；执行顺序：**先**完成 episode 隔离与事件身份（见 [ADR-0016](0016-episode-window-and-sample-validity.md)），**再**替换弹道判定器。

### (d) 占位期口径（已作废）与替换内容

阶段的 `capture_adjudicator` 实为「目标一进入包络即置 `INTERCEPT_CONFIRMED`」，这是**闭式占位**，只用于产出终态 / 指标与联调；它把「发射时刻判定」偷换成了「入包络即命中」，且捕获与干扰共用同一包络导致 `先命中者胜` 退化。该口径**不得**作为最终口径，**不得**据此声称实现了移动式主动拦截。

替换后的口径（现已落地，见 (g)(h)）：以网到达时刻的目标预测位置判定可达（**瞄准提前量**）、引入**火控窗口**、发射后含失手 / 冷却、干扰作用包络与捕获包络**分离**。凡引用历史 `CAPTURE_NET` 数据的场合，须标注其为「闭式占位裁决（非弹道 / 火控）」。

### (e) 适用高度：上限派生、高度含车体

- 相对高度 `h = target.z − car.z − launcher_height_m`（`car.z` 取地面 odom）；**高度必须含车体**，否则地形 / 车高变化即造成错误裁决。
- 可达判据 `disc = vy² − 2gh ≥ 0`；适用区间 `[applicable_min_alt_m, applicable_max]`。
- `applicable_min_alt_m` 保留为参数（默认 `0.0`，独立下界语义，不能由弹道推导）。`applicable_max_alt_m` **从参数表删除**，由节点按 `(v0·sinθ)²/(2g)` **派生**（默认参数下 `2.0092`，与旧硬编码一致、无行为漂移）。手写第二真源已作废：改 `net_v0_mps` / `net_angle_deg` 忘改上限会「打得到却判越界」，是抬高度时 capture / jam 场景全部退化为 TIMEOUT 的直接原因。
- **命中 / 越界标注**：`/agc/task/capture_hit` 取值仍**恰为** `CAPTURE_NET`（`task_manager` 精确匹配，不得追加标签）；同时在新证据话题 `/agc/task/capture_evidence`（`std_msgs/String`）发 `CAPTURE_HIT CAPTURE_NET model_id=.. applicable_min_alt_m=.. applicable_max_alt_m=.. h=.. dist=..`。越界 / 不可达 → 不判命中，证据发 `CAPTURE_SKIP <label> h=.. dist=.. model_id=..`（`out_of_applicable_range` / `unreachable`），`envelope_in=false`，同一状态跳变只发一次。
- **不倒调参数**：真实目标高度超出可达高度时**如实报告**（`reachability_check` 块写 `real_target_alt_m` / `reachable_max_alt_m` / `reachable` / `note`），不以结果期望反推参数制造命中。

### (f) 独立干扰作用包络（捕获 ≠ 干扰）

- 干扰包络与网弹道模型**不同源**，话题 `/agc/task/envelope_jam`（`std_msgs/Bool`），参数组 `jam_envelope_*`：`jam_model_id="behavioral_range_gate"`、`jam_envelope_min_alt_m=0.0`、`jam_envelope_max_alt_m=2.0`、`jam_envelope_max_range_m=1.0`。
- 判据：`hj = target.z − car.z`，`jam_envelope_min_alt_m ≤ hj ≤ jam_envelope_max_alt_m` **且**水平距离 ≤ `jam_envelope_max_range_m`。
- `jammer` 门控话题 `envelope_topic` 指 `/agc/task/envelope_jam`，`envelope_max_age_s=0.5` 新鲜度门控沿用（授权与确认口径见 [ADR-0015](0015-jam-authorization-and-confirmation.md)）。目标抬高后 `jam_envelope_max_alt_m` 由派生**只升不降**（= 目标巡航高度 + 0.5 m）。
- 捕获作用包络仍在 `/agc/task/envelope_in`，用网弹道模型。两模型分离后，目标在捕获包络内但不在干扰包络内时干扰**不**生效。

### (g) 火控解算：目标运动估计 + 发射解算门

**缺陷**：20 Hz 融合位置的测量噪声被逐帧差分（`dt≈0.05 s`）放大成 1–2 m/s 假速度，乘以约 1.3 s 网飞行时间 → 瞄准点偏 1–2.5 m，而网有效半径仅 0.5 m（`net_diameter_m=1.0`）→ 连续 28 发 0 中。**不是弹道错、不是包络错，是把测量噪声当成了目标速度。**

`TargetMotionFilter`（纯标准库、可单测，`target_motion_filter.hpp`）：

- **位置**：一阶低通 `target_pos_alpha=0.5`；
- **速度**：对最近 `target_fit_window_s=1.5` 内样本做**最小二乘直线拟合**；低于 `target_static_speed_eps_mps=0.15`（对齐 PX4 `MINIMUM_SPEED_FOR_TARGET_MOVING=0.1` 先例）→ 速度置零；硬上限 10 m/s；
- **新息门**：位置跳变 > `target_gate_m=1.0` → 视为复位 / 鬼影 / 换目标，**重置滤波**，不把跳变融进速度；
- **预测**：`p + clamp(v·t_lead, target_max_lead_m=1.5)`，速度短时异常也不会把瞄准点甩出网半径。

**发射解算门**：滤波器**已就绪**（窗口 ≥ `target_fit_min_s=0.75` 且样本 ≥ `target_fit_min_samples=8`）才允许开火，未就绪按冷却处理、不发弹；交会时间改**两轮迭代**（`t = 距离 / 网水平速度` ↔ 预测点），不再单次近似；`SHOT_FIRED` 日志追加 `vel=(...)` 使「速度估计 → 瞄准点」可追溯。已废弃的 `target_vel_max_age_s` 删除。

**实测结论**：静止目标假速度消除，瞄准点偏差从 1–2.5 m 收敛到 < 0.35 m（`p1_coop/seed2` 2 发 1 中，`pred=(4.32,3.02,1.88)` vs 真值 4.5/3.0/2.0）；全量 N=20 协同臂 20/20 `INTERCEPT_CONFIRMED`，非协同臂 18/20（余 2 例 `fco≈0.001/0.002` 属固定航迹行为，非实现缺陷）。证据 `experiments/w7-rl-b/20261021-w7-rl-b-175313-3256/metrics/`。

**限制**：1.5 s 回归窗口对高机动目标的提前量有滞后（当前静态 / 线性场景可接受，机动场景需另评估）；火控行为已变（发射时机 / 弹数 / 命中率），**本改动前后的 P1 数值不可混用**，须重跑。

### (h) 交战门 = 预演弹道最近距离

旧 `gateStatus` 用 `d.dist > reach + 0.5·diameter` 判可交战，`reach` 只是「网落到该高度时的水平距离」，不是「该距离上一定能命中」：一是余量极薄（默认参数 0.18 m，抬到 12 m 剩 0.08 m，20 m 剩 0.008 m），抬得越高越差；二是网两次经过目标高度的两个交点之间有空隙，目标落在空隙里时「门真但必空」。

现口径：以当前瞄准方向（目标滤波位置）**预演弹道**—— 复用 `netPos` / `radius` 同一套物理、512 步—— 求网心与目标的**最近距离** `d_min`，仅当

```
d_min ≤ 0.5 · diameter − aim_margin
```

才判定可交战（`engaged=true`，发 `/agc/task/envelope_in=true`）。新增参数 `net_aim_margin_m`（默认 `0.0` = 预演能擦到就开火；调大 = 更靠近才开火）。

**语义变化（必须记住）**：门为真 ⇔ 此刻开火**必然命中**；`envelope_in`（可交战）与 `capture_hit`（命中）从此同源，不再存在「门真但必空」。代价：`envelope_in` 触发时刻后移（从「刚进射程」变成「瞄准解算成立」），故 `envelope_in_rate` / `first_envelope_in_s` 的历史值**不可直接跨版本比较**，跨版本对照须标注本口径的生效边界。本门只改**判据**，不改物理参数、不改命中判定（`d3 ≤ radius(t)` 逐帧推进）、不改 ABI / 话题 / 终态语义，`model_id` 保持 `net_ballistic_frame_v2`。

### (i) 在飞生命周期与发射资格解耦

**缺陷**：原 `step` 把「位姿缺失」与「交战门」的提前返回放在 `if (in_flight_)` 之前，节点 `tick` 也在新鲜度失败时直接 `return`。后果：网在飞期间目标短时越出高度 / 射程或输入失效时，**弹道时钟不推进、落地与超时都不结算**，一条 `SHOT_FIRED` 永久无结局（实测一条 shot 悬空约 114 s，另有 `flight=32.592 s`、`miss_dist` 达 5007.883 m 的畸形值）。

现口径：

- `step` **先**处理 `in_flight_`，再处理发射资格。只要在飞，**每一控制拍**用调用方传入的仿真时刻推进弹道时钟；落地判据 `net.z < net_z0_ − 0.01`、超时判据 `t_s − t_fire_ > net_flight_timeout_s` 每拍检查。
- 发射资格（适用高度 / 可达 / 水平射程、冷却、授权、身份、任务窗口、`TargetMotionFilter::settled`）**只约束新发射**。`tick` 不再早退，把 `car_fresh` / `target_fresh`（含 `confidence_min=0.5`）编码为 `Pose2.valid` 后**始终**调用 `step`；`envelope_in` / `envelope_jam` 只在两路输入均有效时发布。
- **目标缺失不判命中但照常结算**：只有 `target.valid` 才更新滤波器并做球比对，无效拍跳过命中判定（不用缓存位姿）；从未获得有效观测时 `miss_dist_m` 如实为 `inf` 并标 `miss_dist_valid=false`。
- **唯一结局与显式中止**：每次 `SHOT_FIRED` 恰有一个终局——`SHOT_HIT`、`SHOT_MISS`，或 `SHOT_ABORTED shot=<id> reason=<episode_reset|clock_regression> t=<sim>`（追加 token，既有 `SHOT_FIRED|SHOT_HIT|SHOT_MISS` 解析不受影响；`capture_evidence` 同步标注）。`SHOT_ABORTED` **不**发 `/agc/task/capture_hit`、**不**写 `CAPTURE_NET`、**不**冒充命中 / 失手。episode 身份变化时在 `adjudicator_->reset(e)` 之前若在飞则发 `reason=episode_reset`；仿真时钟回退（`t_s < t_fire_ − 1e-6`）以 `reason=clock_regression` 结算、`flight_s` 夹到 `≥0`。结算后 `cooldown_until = t_settle + fire_cooldown_s`，同一 shot 不再产生第二个终局。
- **时间基**：在飞推进、落地与超时结算以 ROS 仿真时钟（`use_sim_time=true`）为唯一时间基；正常 20 Hz 下 `0 ≤ flight_s ≤ net_flight_timeout_s + 1/rate_hz + 数值容差`。
- **模型身份升版**：`model_id` 由 `net_ballistic_frame_v1` 升为 `net_ballistic_frame_v2`，仅用于区分「修复前 / 修复后」时序证据；物理参数、`t_est` 定义、弹道模型逐字不变。
- **接口**：`DynamicFireControlAdjudicator` 抽到可单测头文件 `dynamic_fire_control.hpp`（纯标准库，无 ROS / GZ / PX4）；内部 `CaptureAdjudicator` 接口新增 `abortInFlight` / `inFlight`（非纯虚，缺省无在飞状态），不改变节点对可插拔实现的依赖方式。

**回归**：确定性单测 `test_dynamic_fire_control.cpp` 以显式 `t_s` 覆盖目标过期 / 低置信度 / 越出上下限高度 / 越出水平射程 / 车辆位姿缺失 / 落地（`flight≈1.30 s`）/ 超时（`timeout=0.5 → 0.55 s`）/ 冷却 / 复位中止 / 时钟回退 / 唯一终局 / 正常命中，修复前首条用例为红（`scan.count=0`、`status=kInvalid`），修复后全绿；含门回归锚点后单测合计 16 条。

## 不做什么（边界）

- **不**建模真实电磁场 / EMI 传播；干扰只到行为级等价。
- **不**用 gz 故障注入（本版本无后端）。
- **不**引入固定圆网面 + 「目标穿越」判据（已作废）。
- **不**新增消息枚举、**不**改冻结 9 消息 ABI、**不**新增第二 ROS 命令者、**不**改唯一执行口语义。
- **不**以结果期望倒调 `applicable_*` / `net_*` 参数制造命中。
- **不**用墙钟（`steady_clock`）做超时兜底（GUI / headless 速率不同会改变结局）。
- **不**在节点层缓存过期目标位姿继续判命中；**不**把 `SHOT_ABORTED` 并入 `SHOT_MISS`（复位 / 时钟回退不是物理失手，混用会污染命中率与时序统计）。
- **不**在本篇范围内实现机动目标的自适应提前量（1.5 s 窗口的滞后是已知限制）。
- **未实现 / 后续**：非协同臂包络命中提升属臂行为调参而非链路修复；小批整链诊断与出口闭合见 [ADR-0023](0023-adjudication-record-and-exit.md#top)。

## Considered Options

- **仅跟踪、不做拦截** —— 被否：拦截是研究主线的一半，仿真可实现。
- **真实 EMI 场仿真** —— 被否：无原生模型，只能行为级等价。
- **维持固定 2 m 圆面 + 穿越判据** —— 被否：现实无此形态，且强绑目标低飞。
- **移除物理捕获、仅保留行为级干扰** —— 被否：砍掉主线的一半，废弃已建载荷模型。
- **照抄现实松包络（高度 ≤60 m / 距离 100–300 m）** —— 被否：车无需逼近即可捕获，任务平凡化。
- **维持「入包络即命中」作为最终口径** —— 被否：把动态拦截降维为「接近到 R 米」，与「发射时刻判定」不符。
- **本轮直接实现火控窗口 / 瞄准提前量（占位期时）** —— 当时被否：受出口工期约束且会改动已验收口径；现已按 (g)(h) 落地。
- **维持字面「调用方完全不改」** —— 被否：会阻止异步裁决事件语义，真实弹道无法落地。
- **把 `applicable_max_alt_m` 倒调至覆盖期望目标高度** —— 被否：违反「不以结果期望倒调参数」，属数据造假。
- **在飞期间单独维护第二套弹道时钟** —— 被否：与既有 `t_fire_` / 网位姿模型重复，增加状态与漂移风险。
- **用「水平射程 reach」判可交战** —— 被否：余量极薄且存在「门真但必空」的空隙。

## Consequences

- **正面**：捕获机制物理可复核、包络可标定；每个 `SHOT_FIRED` 有唯一终局，在飞网不再悬挂；`flight_s` 与 `miss_dist_m` 回到物理上界内；交战门与命中同源，`envelope_in` 不再骗人；静止目标假速度消除。
- **代价 / 限制**：火控与门语义变更前后**数值不可混用**（`model_id` 升 v2 区分；`envelope_in` 类指标须标注生效边界）；历史 run 保留为 pre-fix 证据，**不**回溯改写；下游脚本须容忍 `SHOT_ABORTED`。
- **迁移成本**：裁决插件边界、shot 状态机、异步命中 / 失手 / 取消事件的消费与回放验收，属中至高。
- **回归防线**：`test_target_motion_filter` / `test_dynamic_fire_control` 纳入 `colcon test`；`SHOT_FIRED` 的 `vel` 字段可用于后续日志审计。

## 参考

- 项目定位与拦截主线：[ADR-0001](0001-project-positioning-and-execution-scope.md)
- 干扰授权与确认：[ADR-0015](0015-jam-authorization-and-confirmation.md)
- episode 身份与事件隔离：[ADR-0016](0016-episode-window-and-sample-validity.md)
- 整链覆盖与因果记录：[ADR-0018](0018-acceptance-and-coverage-matrix.md)
-裁定记录（含 miss 实测与决策门）：[ADR-0023](0023-adjudication-record-and-exit.md)
- 安全阈值与失效停车：[ADR-0010](0010-safety-thresholds-and-failsafe.md)
- 契约：[终态语义](0014-task-fsm-and-scenario-transaction.md#terminal-semantics)、[参数入口](0020-package-boundaries-and-runtime-topology.md#params)、[硬约束](0020-package-boundaries-and-runtime-topology.md#hard-constraints)
