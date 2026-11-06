<a id="top"></a>
# 空中轨迹与跟踪参数标定

## Status

accepted（2026-11-02 由 0019 / 0051 合并；C1 口径与容限结论未变，跟踪容限仍是**占位待回填**，如实标注）

## 背景

空中侧的三个数字（轨迹形状与速度、跟踪间距、高度基准）既是契约硬约束 C1 的内容，也是全部空中验收的判据。
它们最初来自旧项目的经验值，实测后发现两类问题：

1. **形状名不副实**：旧项目名为「8 字」的实为 `fixed_horizontal`（**两半圆 + 两直线**，`r=3`、`ω=0.2`、`v=0.6`），
   **并非真八字**；C1 的 `ω=0.1` / `v=0.3` 数字由 `ω·r = 0.1×3.0` 反推而来，描述的正是这一非真八字形态。
   旧项目的距离 / 速度参数**偏离真实工程量级**（standoff `2.0/3.5 m`、目标巡航偏慢），不足以支撑「贴近真实」的仿真。
2. **验收口径混用**：C1 恒速验收把**参考 / 机体估计 / 世界真值**三个指标混用；高度语义不统一——接管高度对齐使
   命令 `h` 成为**相对基准**（`z_offset_ = state.pos.z() − trajectory_->sample(0.0).pos.z()`），而对外公开的
   `base_ref` **未加** `z_offset_`，与生效 `effective` 的高度基准**静默不同**；既有检查只给 warmup 之后的速度误差 P95，
   **不能推出全程最大误差**；「恒速无加减速」若指**零向量加速度**则与曲线运动不相容。

## 决策

### (a) 轨迹形状与恒速口径（C1 改写）

- **「8 字」改为真八字（Gerono）**：`x = cx + rx·sinθ`、`y = cy + ry·sinθ·cosθ`（自交成 ∞），`rx=15`、`ry=9`、
  `h=2.5 m`；**全程恒速 `v=2.0 m/s`**（弧长参数化，无加减速）；**删去「角速度 0.1」**。
- **C1「恒速」的对象 = 参考沿弧长的切向速度**：`Figure8Trajectory` 输出 `|vel| ≡ speed = 2.0`，由
  `ParametricTrajectory` 先建 `s(θ)` 梯形积分表、再对给定 `s` 反解 θ 保证 `|dp/dt| ≡ speed`。
  实测参考 `|v|` **P95 = 2.0000**，相对目标 2.0 的 **max 偏差 ≈ 4.4e-16 m/s**（数值恒速成立）。
- **「无加减速」正名**：指**参考沿弧长的切向速度恒定（无切向加减速）**；**不**声称「零向量加速度」（曲线运动有
  向心加速度）。此与 C1 字面的差异属已挑战项，**如实记录**；**不改契约文字**。
- **容限分列**：参考 `|v|` 用**全程 max**（`c1.ref_speed_tol = 1e-3 m/s`，依据双精度浮点 + 弧长表线性内插的
  数值噪声量级）；实际恒速用**机体（world GT）warmup 之后的速度模稳态误差**（`P95` 与 `max` **分别**报告，
  `c1.body_speed_p95_tol_mps = 0.30 m/s`，**占位待回填**）。**不**以 warmup 后 P95 自证「全程最大误差」——
  evidence 显式区分 `speed_err_full_max` 与 `speed_err_steady_p95`，**max / 持续越限**单独报告。
- **模式记账**：**基准轨迹试验**（base 模式，无 `tracking_ref` / `target`）单独判 C1；**接管瞬态（warmup）/
  自保（shield 介入）/ 目标跟踪（tracking 覆盖八字）** 分模式记账，**不**纳入基准恒速判据。
- **作业区与间距**：作业区放大到 **80×80 m**（地面 200×200 不变），`agc_car` / `intruder_uav` spawn 分离 **~30 m**，
  容纳真八字足迹；**standoff 安全间距带 `8/15 m`**（水平），跟踪高度 `2.5 m`，滞回 ~1.0 m，最大水平速度 `2.0 m/s`；
  目标巡航（临时脚本）`1.0 m/s`。
- **参数溯源原则**：距离 / 速度参数取自**权威参考**而非旧项目 —— PX4 Follow-Me 保距默认 **8 m**；轻小型旋翼机间
  水平间隔标准 **≥15 m**；Nav2 以**倍数 / 时间窗**表达安全距离（`inflation 3.18×半径`、`time_before_collision
  1.2–2.0 s`）；室内四旋翼实测速度上限 **1.2–2.0 m/s**。

### (b) 唯一世界高度语义

- 定义**唯一世界高度语义** = **世界 ENU `z`（`world` frame，向上）**。world GT / PX4 估计 / base / effective /
  setpoint 五条曲线**统一回到世界 ENU z** 表达。
- PX4 `TrajectorySetpoint` 内部为**局部 NED**，曲线须反变换 `z_world = -z_ned + origin_z`（台架 `origin_pose=0`，
  故 `z_world = -z_ned`；速度 / 加速度为**自由矢量**、仅符号翻转）。
- `z_offset_` 语义 = **层高基准**（接管时刻机体高度 − 轨迹 `h`），**非**世界原点代偿（世界原点平移由
  `px4_adapter` 的 EKF 原点处理）。

### (c) `base_ref` 与 `effective` 高度基准一致且可辨

发布 `/agc/air/ref` **前**，对 `base_ref` **副本**加 `z_offset_`（`base_ref_out.pos.z() += z_offset_`）→ 对外
`base_ref` 与生效 `effective` **同一世界高度基准**；**不**改动下游使用的 `base_ref`（`/agc/air/ref` 在 `src/` 内
无消费者，改其高度基准安全）。并在 `publishTrackStatus` 的 JSON **追加显式字段** `z_offset`（数值）与
`height_datum`（`"world_enu"`）→ 差异**可辨**（既有字段保持不变）。
实测：`base_ref` ↔ `effective` 高度基准差 **P95 8.1e-8 m、max 1.2e-7 m**（修复前 `z_offset` ≈ 0.6 m）。

### (d) 取证：同时间证据曲线与三指标分别报告

- `w6_r036_bench.py` 起**真实** `trajectory_tracker`（standalone，`bond_heartbeat_period=0.0`，发
  `active_controller="trajectory_tracker"` 取得许可），**同一 run、同一 ROS 时间轴**记录 **world GT / PX4 估计
  （`/agc/air/odom`）/ base（`/agc/air/ref`）/ effective / setpoint（`/fmu/in/trajectory_setpoint`，反变换回世界 ENU）**
  5 条曲线，40 s @ `t≈0.02 s`。
- **effective 重建口径**：`effective.pos = nedToEnu(sp.position) − 0.5·acc_enu·dt²`、
  `effective.vel = nedToEnu(sp.velocity)`（`dt = 1/setpoint_rate_hz = 0.02`），即在 `publishSetpoint` 的位置前馈
  `0.5·a·dt²` 处逆运算（**不新增命令者 / 不新增诊断话题**）。
- **机体模型**为脚本化（**不消费 setpoint 的位置环**，避免以被测输出自证）：真值速度**一阶**趋近参考速度
  （隐式欧拉，任意步长稳定）+ 弱位置牵引；估计 = 真值 + **已知常量位置偏置**（z: +0.60 m）。
- 对 **base / est / gt** 三指标分别报告**高度 z** 与**速度 |v| − 2.0** 的 **P95 / max / 持续越限**（全窗 + 稳态窗）；
  产物 `<run_id>/r036/{bench.json,curves.csv}`，含 `scope_note`（**非整链 / 逻辑台架**）与 `unsupported`。
- **实测**：`z_offset` 实测 **0.60 m**（注入偏置 z=+0.60）；世界真值稳态速度误差 **P95 0.023 m/s**；
  三指标**可区分** —— `gt` 高度中位 3.100 m（= h 2.5 + z_offset 0.6）、`est` 高度中位 3.700 m（+0.60 估计偏置），
  估计偏置被如实分开统计（`est` 高度残差稳态 P95 0.600 m、持续 41.4 s；`gt` 稳态 3e-5 m）；
  同时间轴 `t` / `base` 头时间 / `sp` 接收时刻**均单调**，对齐误差 **P95 0.19 s ≤ 0.25 s**。
- **容限落 `air.yaml`**（配套，非 ABI）：`trajectory_tracker.ros__parameters.c1` 登记 `ref_speed_target` /
  `ref_speed_tol` / `height_datum_tol_m` / `body_speed_p95_tol_mps`（占位）/ `height_err_p95_tol_m`（占位）/
  `sustained_limit_eps_mps`；bench 与 check 脚本**读取**（不复制参数）。

### (e) 缺失的 `stock_rec` 材料作为未证实归因保留

W3 所述「stock PX4 + Gazebo 垂向起伏属 SITL 固有」的判据来源是 `/tmp/stock_rec{,2,3}.csv`；经核实该路径
**无文件**（`ls /tmp/stock_rec*.csv` 空）→ 外部归因**不能独立复核**。裁定：该项外部归因作为**未证实**归因**保留**——
**不**据此删除 / 重写该偏差记录，**不**把「stock 固有」当作已复核结论；如需外推须重做并**保留**原件。

## 不做什么（边界）

- **不**改契约 C1 硬约束文字（改硬约束须另行批准）；只做口径裁定 + 证据，并如实记录与字面的差异。
- **不**改冻结 9 消息 / 服务 ABI，**不**变唯一执行口语义，**不**新增第二 ROS 命令者；`z_offset` / `height_datum`
  与 `c1.*` 均为**配套诊断 / 口径**（非 ABI、非命令者）。
- **不**用 PX4 估计（`/agc/air/odom`）当「世界真值」（会把估计偏置混入真值，仍三指标混用）。
- **不**新增专用「effective 诊断话题」直出内部 effective（会新增话题 / 表面命令者嫌疑；setpoint 反变换已可忠实重建）。
- **不**把 `z_offset` 做成固定参数（它是**每次接管实测**的层高基准，由 `tracking_status` 报告实测值）。
- **不**据未证实的 `stock_rec` 归因删改历史偏差记录。

## Considered Options

- **保留旧 `fixed_horizontal`（半圆 + 直线）** —— 被否：非真八字，几何上不成立。
- **保留 C1 原数值（`ω=0.1`、`v=0.3`、`r=3`）** —— 被否：尺寸 / 速度不切实际，且与真八字不兼容。
- **维持小场地 + 按比例缩放参数** —— 被否：用户要求贴近真实间隔，故放大作业区。
- **沿用旧 `air_follow` 的 `safe_min=2.0`** —— 被否：间距过近，旧项目在此问题突出。
- **保持现状（公开 `base_ref` 不加 offset，仅文档说明）** —— 被否：对外 `base_ref` 与生效 `effective` 基准静默不同，
  C1 验收仍混淆。
- **改契约 C1 文字为「切向恒速 + 稳态误差容限」** —— 被否：超出本批授权；改为裁定口径 + 证据并如实记录差异。
- **把 `z_offset` 做成固定参数** —— 被否：它是每次接管实测值。

## Consequences

- **正面**：真八字 + 弧长参数化使「恒速」可数值自证；对外 `base_ref` 与 `effective` **同一世界 ENU z 基准**
  （实测基准差 P95 < 1e-7 m），`z_offset` / `height_datum` 在 `tracking_status` **可辨**；同一 run 同一时间轴给出
  5 条曲线与三指标分别的 **P95 / max / 持续越限**；缺失材料作为**未证实**归因**保留**，不冒充复核。
- **代价 / 限制**：`body_speed_p95_tol_mps` / `height_err_p95_tol_m` 为**占位待回填**（W3 未标定）；台架机体为
  **脚本化**（非整链 / 非 PX4 SITL 闭环，如实 `unsupported`）；同时间对齐容限放宽至 P95 ≤ 0.25 s
  （单进程台架的 GIL / DDS 抖动，实测 P95 0.19 s）；C1 改写触发作业区放大与柱重排的连带改动。
- **未决 / 后续**：C1 容限的实测回填依赖**真实整链 / 双 PX4** run（本批不可实测 → 占位）；`ε` / `ε′` 首轮实跑后回填；
  如需外推 `stock_rec` 归因须重做并保留原件。

## 参考

- 评审：[10-风险](../reviews/agc-review-2026-10-14/10-风险.md#r-036)、
  [10-风险](../reviews/agc-review-2026-10-14/10-风险.md#x-01)
- 契约：[#hard-constraints](../ROS2迁移交接文档.md#hard-constraints)（C1）、
  [#namespace](../ROS2迁移交接文档.md#namespace)、[#execution-port](../ROS2迁移交接文档.md#execution-port)、
  [#messages](../ROS2迁移交接文档.md#messages)
- 相关决策：[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)（感知口径与机头指向）、
  [ADR-0010](0010-safety-thresholds-and-failsafe.md#top)（安全阈值与空中单一控制权）、
  [ADR-0003](0003-nav2-paradigm-absorption.md#top)（Nav2 范式吸收）、
  [ADR-0019](0019-lifecycle-and-startup-robustness.md#top)（生命周期与启动健壮性）
- Nav2 参照：`nav2_controller/plugins/{simple,position}_goal_checker.hpp`（query vs goal + 位置 / 速度容限分列）、
  `nav2_util/geometry_utils.hpp`（`euclidean_distance` 二维 / 三维显式）、`nav2_util/odometry_utils.hpp`（`OdomSmoother`）
- 实现：`trajectory_generators.cpp` / `trajectory_tracker.cpp` / `air.yaml` / `w6_r036_bench.py` / `w6_r036_check.py`
