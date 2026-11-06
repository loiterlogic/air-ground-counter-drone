<a id="top"></a>
# 地面控制栈：RL 主控、Nav2 安全层与共享控制库

## Status

accepted（2026-11-02 由 0004 / 0018 / 0026 合并；分层口径、`agc_control` 归属与标定值均未变）

## 背景

地面域要同时满足两件互相拉扯的事：RL 必须是一等公民（研究主线要有端到端的控制信号），而工程上又必须有唯一的执行口与可信的安全收敛层。同时空中与地面都需要轨迹跟踪能力—— 空中要 LQR 跟踪真八字与目标（standoff），地面需要一个离线对照基线控制器；若各域各自实现，会重复造轮子并引入行为不一致。

另有两处实现缺陷必须先定死口径：动作映射 `action_to_twist` 存在**转向符号反转**（`left` 实际输出负 `angular.z`）与**量纲混用**（无量纲 `forward_min` 与米制 `clearance_norm` 混算，改变雷达量程会无理由改变动作强度）；偏移参数 `max_offset` 是**按名称推定**的横向逃逸量，从未实测差速车能否做到，而契约要求安全滤波器参数须用真实逃逸能力。

## 决策

### (a) 分层：RL 直接出速度，Nav2 只做安全层与离线基线

- **RL 主控**：RL 直接输出 `cmd_vel`，经 Nav2 `collision_monitor`（按多边形区域缩放 / 急停）收敛到唯一执行口 `/agc/ground/cmd_vel`。链路顺序固定为 `RL → cmd_vel_raw → collision_monitor → 唯一执行口`。
- **Nav2 定位**：planner / controller **不作为在线主控**，改作可切换的**离线对照基线**；论文基线取自 Nav2 控制 / 避障。
- **空中域**：Nav2 不适用（无 3D），保留 / 优化 LQR + 自研避障，按 [ADR-0003](0003-nav2-paradigm-absorption.md#top) 的「模式全覆盖」执行。
- **路径输入扩展（2026-11-01）**：地面侧全局规划器产出的路径（`/agc/ground/path` 的 `nav_msgs/Path`）作为**局部策略的传输缝**输入，见 [ADR-0013](0013-ground-planning-path-contract.md#top)。这**不改变**三件事：RL 的 obs 里**没有** costmap（[ADR-0003](0003-nav2-paradigm-absorption.md#top) 的按命令源裁剪继续有效）；不引入 Nav2 controller；上述链路顺序与唯一性不变。路径进 ROS **不等于**路径进训练策略的固定维观测。
- 安全层复用既有 shield 口径（`shield_infeasible_rate`）。
- **用户裁定 R4（2026-10-31）：局部精确避障要做，且由强化学习实现（用户本人负责范围）**
  - **裁定**：局部避障**不是只靠安全层兜底**，要作为**独立能力**实现，**实现手段 = 强化学习**，
    属**用户本人负责范围**；载体预期为 `agc_rl` 在线策略（上文 (a) 的"RL 地面主控"地位**不变**）。
  - **架构后果（必须显式，不得静默）**：现状 RL 策略只订 `/agc/ground/odom` / `scan` / `goal` / `state`
    并**直接出 `cmd_vel_raw`**，**没有路径输入**。要实现"跟踪全局路径 + 局部避障"，须**新增"路径 → 局部策略"
    输入缝**：全局规划器（占位 → 外部节点）→ 路径 → RL 局部策略 → `cmd_vel_raw` → `collision_monitor`
    （安全层，**仍是最后屏障，但不等于局部避障**）→ 唯一执行口。
  - **边界（不得夸大）**：`collision_monitor` 是**按速度多边形的减速 / 急停屏障**，不是绕障规划；
    其感知为 `z≈0.48 m` 单水平面，低障碍 / 悬空结构**不可见**、薄障碍受 `min_points=2` 限制
    （[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)）。RL 局部避障落地后，
    仍须**如实登记**它相对该可见性族的边界，**不得**写成通用避障保证。
  - **执行时须回改**（未落地）：本 ADR (a) 的策略输入由"goal"扩展为"路径 + goal"；
    [ADR-0003](0003-nav2-paradigm-absorption.md#top) 的"`command_source=rl` 不消费 costmap"是否仍成立；
    `rl.yaml` 与 `ground.yaml` 的链路注释；`GLOSSARY.md`（新增"局部避障 vs 安全层"条目）；架构图资产。

### (b) 共享控制库 `agc_control`：一份实现、pluginlib 两类插件

- **归属**：新建 `agc_control` 包（`ament_cmake`），**不**塞入现有包（避免 `agc_ground → agc_air` 之类错误依赖）；同步更新包边界约定。
- **两类插件**：① 轨迹生成器（`linear` / `circular` / `helical` / `figure8` / `hover` / `step`）；② 控制器（**LQR**）。
- **接口与执行器解耦**：入参 = 当前 `state(pos, vel)` + 参考 `ref(pos, vel, acc)`，出参 = **加速度指令** `acc_cmd`（世界系 ENU/FLU）。消费者自行转执行量——air 转 PX4 位置 / 速度 setpoint，ground 转 `cmd_vel`；控制频率由消费者 pump。
- 该形态同时命中 [ADR-0003](0003-nav2-paradigm-absorption.md#top) 要求的 pluginlib 吸收点；LQR 在地面**仅作基线**，唯一执行口语义不变（地面须经安全层后由唯一执行口下发）。

### (c) 动作方向约定：`left` = 正 `angular.z`

对齐 ROS 2 / REP-103 约定（车体系 + 左 = 逆时针 = 正 `angular.z`；`sensor_msgs/LaserScan.msg` 明示 positive Z 为逆时针）：`left` / `left_fast` → **正 `angular.z`（左转）**，`right` / `right_fast` → **负 `angular.z`（右转）**。航向项与横向项**同号**：

```
w = k_heading*heading_err + k_lateral*lateral # 正 lateral = 左 = 正 angular.z
```

### (d) 净空量纲一致：米，且与量程解耦

净空改为**米**并引入参考值 `clearance_ref_m`（config，米），二者同量纲：

```
ratio = clamp((clearance_ref_m - forward_clearance_m) / clearance_ref_m, 0, 1)
magnitude = min_offset + ratio*(max_offset - min_offset)
forward_clearance_m = forward_clearance(sectors, ..., half) * lidar_max_range # 归一值乘量程还原为米
```

`action_to_twist` 签名为 `(action, heading_err, forward_clearance_m, params)`，**不再**接触任何量程参数；参数经 config 单一注入。

### (e)逃逸标定：`max_offset` 由 1.2 下调至 1.0 m

口径：反应窗口 `T = 2.0 s`（Nav2 `time_before_collision` 上界，`t_before ∈ [1.2, 2.0] s`）；理论界（常 yaw 率圆弧）`lateral(T) ≈ (v/ω)*(1 - cos(ω*T))`。

- **实测（GUI，`agc_world`）**：Husky 级 4 轮滑移差速车（`v_max = 1.5`、`ω_max = 2.0`），车前净空置 0 使 `magnitude = max_offset` 满偏。`max_offset = 1.2` 时 3 轮最大横向可达 `1.065 / 0.997 / 1.293 m`（多数 < 1.2，常速左转稳定 ~0.99 m）→ **不可达**；`max_offset = 1.0` 时 4 轮为 `1.043 / 1.287 / 1.083 / 1.017 m`，**均 ≥ 1.0 m** → **可达**。
- **决策**：`max_offset: 1.2 → 1.0`（`src/agc_rl/config/rl.yaml` 单一注入）；`min_offset = 0.3 m` 不变；新增 `control.clearance_ref_m: 1.0`（米）。
- **物理解释**：实测横向 ≈ 理想圆弧界的 ~0.72×——4 轮滑移底盘（横向 μ2=0.2）转弯时侧滑削刮，实际横向小于理想滚动圆弧，故**不得**用理想弧模型推定。`max_yaw_rate = 1.0` 未构成瓶颈（本测 `w = k_lateral*max_offset = 0.8 < 1.0`，未截）。
- **方向闭环**：所有采样中 `left` / `left_fast` → 世界 yaw 增且横向 y 为正，`right` / `right_fast` 反向——ROS 约定经安全层 + 唯一执行中继端到端成立、可复现。
- 证据：`experiments/w5-ground-nav-safety/20261015-w5-r011-0/metrics/r011.json`（最终配置 PASS）；标定前 FAIL 批次 `20261015-w5-r011-precalib-0`；单测 `python3 -m pytest src/agc_rl/test/ -q` → 11 passed。

## 不做什么（边界）

- 不让 Nav2 planner / controller 回到在线主控位置；不在空中域引入 Nav2 运行时进程。
- 不把 costmap 放进 RL 的 obs；路径进 ROS 不宣称任何训练能力。
- 不提高 `k_lateral` 去「榨取」更大横向（侧滑削刮下增益有限、易致失稳）。
- 不由下游纠正动作符号（学习接口一旦冻结会学会补偿错误标签，必须在接口层修）。
- 不为「未来第三方调用」预建框架（YAGNI）；不做厚 `HardwareHooks` 抽象层。
- 本轮不改契约硬约束、不改冻结消息 / 服务 ABI；RL 节点仍不写 `/agc/ground/cmd_vel`。

## Considered Options

- **c1：RL 只出高层目标、Nav2 planner/controller 主控** —— 被否：RL 控制信号降级，削弱其作为一等公民的研究价值。
- **独立节点 + service/action 调用控制层** —— 被否：引入通信时延，不适合高频控制内环。
- **各域各自实现跟踪 / LQR** —— 被否：重复实现、行为漂移，违背「只实现一次」。
- **保留 `max_offset = 1.2`（或按理想弧 / 名称推定）** —— 被否：实测多数不可达，属「命名 1.2 m 横移但差速车实际不可达」的失配，违。
- **把净空参考继续取无量纲值 / 动作符号交由下游纠正** —— 被否：前者量纲混用、强度随量程漂移；后者污染学习接口。

## Consequences

- **正面**：地面控制只有一个执行口且安全层位置固定；跟踪能力只实现一次、两域共用；动作左右方向与逃逸量都有实测依据，`max_offset` 有可复现标定值。
- **代价 / 限制**：需维护 `RL → cmd_vel → collision_monitor → 唯一执行口` 链路与 `agc_control` 包；`max_offset = 1.0` 是**该底盘在该摩擦面**下的标定值，换底盘 / 摩擦须重标；实测横向约为理想圆弧的 0.72×，任何按理想模型的规划都会偏乐观。
- **表述纪律**：RL 动作左右方向与净空参考一律引用本篇；`max_offset` 一律引用标定值 1.0 m，**不得**再以名称 / 理想横移推定横向逃逸。

## 参考

- [ADR-0003](0003-nav2-paradigm-absorption.md#top) Nav2 范式吸收与按命令源裁剪
- [ADR-0013](0013-ground-planning-path-contract.md#top) 地面规划：基线路径、重规划与外部规划器契约
- [ADR-0010](0010-safety-thresholds-and-failsafe.md#top) 安全阈值与安全屏障
- [ADR-0020](0020-package-boundaries-and-runtime-topology.md#top) 包边界（`agc_control` 归属）
- 实现：`src/agc_rl/agc_rl/interface.py`、`src/agc_rl/agc_rl/inference_node.py`、`src/agc_rl/config/rl.yaml`、`src/agc_rl/test/test_interface.py`、`scripts/archive/run_w5_r011.sh`、`tests/check_action_direction_escape.py`
