<a id="request"></a>
# 目标无人机运动规则 + 速度调研与运行节奏 —— 批次派工单

- 任务 ID：`20261104-002-target-motion-speed`；轮次：1；派发时间 `2026-11-04T18:10:00+08:00`（Asia/Shanghai）。
- 来源：用户 2026-11-04 指示「把 `docs/plan/目标无人机运动规则.md`、`docs/plan/速度调研与运行节奏优化.md` 完成」。
- 你是本链**唯一** Worker；后续轮次复用你会话，不重新创建。

> **两个 plan 合成一条链**：它们共用 `intruder_driver` 与 `scenarios.yaml` 的同一批参数，
> 目标机速度就是运动规则的一部分。分两条链会互相踩文件，故合并。结档时**两个 plan 文件都删**。

## 一、目标（一句话）

给目标无人机一套**像真的**运动规则（不再主要是定点悬停），并在**不改契约**的前提下
把小车 / 己方机 / 目标机的运行速度调到有说服力的量级，**同时保住**既有的捕获、跟踪、
安全层与验收判据——每一条改动都要有实测证据支撑。

## 二、不可越界的口径（先读，违反即停）

1. **契约 C1 是红线**：硬约束第 1 条要求「8 字轨迹**全程恒速**、线速度 `v=2.0 m/s`」，
   其真源参数是 `agc_air/config/air.yaml` 的 `traj.speed: 2.0`（[契约真源](../../../../docs/ROS2迁移交接文档.md#hard-constraints)）。
   同时 [飞行高度分层 §2](../../../../docs/conventions/飞行高度分层与按地图定高.md#no-fixed-trajectory)
   规定**反无人机场景禁用预设固定轨迹**，所以 `traj.*` 在反无人机场景里**整段不被读取**。
   ⇒ **你可以论证并修改 `traj.speed`，但它等于改契约**：必须**停下来问**（走"阻塞/待裁定"），
   由 Leader 决定是否走用户裁定。**不得**自行改契约或 ADR-0008 的结论。
2. **不改契约文本**：`docs/ROS2迁移交接文档.md` 一字不改（除非 Leader 事后明确授权改 C1）。
3. **不造路线分支**：新增运动种类属于**场景轴取值**扩展（`axes.target_motion` + `scenario_carriers.yaml`），
   这是 [路线分支治理 §3](../../../../docs/conventions/路线分支治理.md#retire) 里**优先级最高**的载体，
   **不是**路线分支。但**禁止**新增 `xxx_mode` / `xxx_source` / `xxx_path` 形式的 launch 参数
   （`scripts/tests/test_branch_ledger.py` 会失败）。运动种类的唯一入口 = `intruder_driver.motion` 的值。
4. **不改工具链**：`toolchain/**` 只读。
5. **不削弱判据**：不得为了让新运动"跑通"而放宽 `d_track_m`、`t_dwell_s`、C2 阈值、
   `confidence_min`、`ref_max_age_s`、`safe_max`。若某条必须变，**先停报**并给出"为什么不是削弱"的推导链。
6. **不做**：不做 RL 训练、不引入新依赖、不改 RL 网络/策略结构、不改感知链路。

## 三、真源与必读

- 待结档 plan：[目标无人机运动规则](../../../../docs/plan/目标无人机运动规则.md#target-motion)、
  [速度调研与运行节奏优化](../../../../docs/plan/速度调研与运行节奏优化.md#speed)
- 代码真源：`src/agc_task/scripts/intruder_driver.py`（`_target()` 的运动学 + 起点协议 + 运行区夹持）、
  `src/agc_task/config/scenarios.yaml`、`src/agc_task/config/w6_base.yaml`（`intruder_driver` 段）、
  `src/agc_task/config/scenario_carriers.yaml`（`target_motion` 承载者表）、
  `src/agc_sim/config/car.yaml`、`src/agc_rl/config/rl.yaml`、`src/agc_air/config/air.yaml`
- 决策与口径：[ADR-0008](../../../../docs/adr/0008-air-trajectory-and-tracking-calibration.md#top)（C1）、
  [ADR-0010](../../../../docs/adr/0010-safety-thresholds-and-failsafe.md#top)（C2 与逃逸能力标定）、
  [ADR-0011](../../../../docs/adr/0011-interception-and-fire-control.md#top)（网弹道与火控门）、
  [ADR-0014](../../../../docs/adr/0014-task-fsm-and-scenario-transaction.md#top)（FSM 与 T_max）、
  [ADR-0016](../../../../docs/adr/0016-episode-window-and-sample-validity.md#top)（有效样本）、
  [ADR-0017](../../../../docs/adr/0017-time-budget-and-clock-sources.md#top)（时间预算 / RTF）
- 观测与产物：[演示可观测性与产物语义](../../../../docs/conventions/演示可观测性与产物语义.md)、
  [ADR-0006](../../../../docs/adr/0006-experiment-artifacts-and-evidence-discipline.md#top)
- 同类实现（**先学后做**，逐条对照后动手）：
  - PX4 Offboard 位置控制的官方范式（`px4_msgs/TrajectorySetpoint` 语义、Offboard 流前置条件）
  - MAVROS/PX4 的 `SET_POSITION_TARGET_LOCAL_NED` 与速度 vs 位置 setpoint 的选择争议
  - ArduPilot `GUIDED` 模式的 `SET_POSITION_TARGET` 行为（作为"位置 setpoint 会掩盖速度语义"的对照）
  - 搜"无人机机动目标仿真 轨迹生成 lissajous / waypoint / evasive" 的外部做法与量级

## 四、基线（改动前先测）

- 分支 `main`，HEAD `49e099c`；工作区很脏（592 项未提交改动）。**不得** reset / checkout /
  stash / clean；只写白名单，改动前先记文件哈希。
- 现状（Leader 已核，你须复核）：车 RL `reference_speed 1.0` / `fast_speed 1.3`，
  车限速 `max_linear_velocity 1.5`；己方机 `traj.speed 2.0`（C1）；
  目标机场景常见 `speed_mps 0.5`；`t_max_s 120`、`d_track_m 3.0`、`t_dwell_s 3.0`。
- 上一轮 GUI 实测参考（只作量级，不作结论）：`experiments/demo/20261104-120212/result.md`，
  `duration_s 149.5 / sim 116.4 s`、`rtf 0.776`、`collision_count 1`。
- **已知遗留**：pid 159340/159341 两个 `air_perception`/`map_adapter` 孤儿进程，
  **不是你的**，**不得** kill。

## 五、必须交付

### 阶段 1：调研（先出结论，再动手）

两条调研都要给**外部依据 + 本仓约束推导**，不是主观偏好：

**R1 目标运动规则**
1. 现状三种（`static` / `linear` / `maneuver` 圆周）各自在任务里的作用与缺陷
   （`maneuver` 的半径 `radius_m` 与运行区 `run_region_radius_m 15` 的关系、起步点是 `(ox+r, oy)`）。
2. 目标运动对**下游**的影响链，逐条量化：
   - 感知：`ref_max_age_s 0.5` / `confidence_min 0.5`（C10）——多快会失效？
   - 跟踪：`standoff_follower` 的安全带 `[safe_min 8.0, safe_max 11.2]`、`max_step_m 0.1 @20 Hz = 2.0 m/s` 上限
     —— **己方机最大追赶速度是 2.0 m/s**。目标速度超过它会发生什么？给出不等式。
   - 火控：`capture_adjudicator` 的 `target_fit_min_s 0.75` / `min_samples 8` / `target_static_speed_eps_mps 0.15` /
     `target_max_lead_m 1.5` —— 目标速度对提前量与"可开火窗口"的影响。
   - 网弹道：`net_v0/angle/timeout` 与目标高度/速度的关系（`capture_adjudicator` 的预演命中判据）。
3. 候选运动规则（**至少 4 个**，各有可行性判据），例如：多航点折线、Lissajous/正弦摆、
   绕点螺旋、变速**规避式**（远离己方机方向的反制机动）、高度微变。
   每个必须给：可解析的**时间参数化**（确定性、可复现、t=0 连续切入）、越界安全性
   （`run_region_radius_m` 夹持的语义）、对上面 4 条影响链的量化、以及**演示观感**预期。
4. 选定**一条**（可带参数）落地，并说明为什么不是其他三条。

**R2 速度与运行节奏**
1. 三主体速度的**上限来源**逐条列出：车（`max_linear_velocity 1.5` + C2 逃逸标定 `max_offset 1.0`
   @ `T=2.0 s`，**该标定是在 1.3 m/s 满速下测的**）、己方机（C1 的 2.0 + `max_step_m` 2.0 上限 +
   LQR `acc_max 4.0`）、目标机（己方机追赶能力上限）。
2. 外部量级参照（真实共轴/多旋翼无人机与差速 UGV 的巡航速度、追踪速度），标明来源与适用性边界
   （**法规/厂商数据只作量级参照，不构成任何合规声明**）。
3. **运行节奏**：当前一轮 `t_max_s 120` 但实测 `duration 149.5 s` 才有终态；RTF 0.776（<1）。
   给出"演示观感"的量化口径（例如：从 START 到终态的墙钟时间、状态跳变事件数），
   并说明提速后**哪些等待是仿真 RTF 造成的、哪些是任务参数造成的**（这两者不能混谈：
   改任务参数不会让 RTF 变快）。
4. 给出**一组**推荐速度（车/己方/目标）与**推导链**（从约束反解，不是拍数），
   含每条的余量与失效边界。

### 阶段 2：实现

- `intruder_driver.py`：新增运动学的**解析时间参数化**实现（沿用现有 `_target(t)` 单一函数风格），
  保持：起点协议（`_start_pose` = `_target(0)`）、运行区夹持（`_apply_region`）、
  `static`/`linear`/`maneuver` **行为逐值不变**（这是历史基线，不得回归）。
- `scenarios.yaml` + `scenario_carriers.yaml`：新运动种类作为 `target_motion` 轴新取值登记；
  至少 1 个**活跃场景**用它（否则 [路线分支治理 §2.2②](../../../../docs/conventions/路线分支治理.md#rule) 的"当前有消费者"不成立）。
- 速度：改配置值，**同步**核对受影响的派生量与判据（见验收 A5），逐条给"变/不变"与理由。
  若某条必须改判据才成立 → **停报**，不要静默改。
- 单测：`src/agc_task/test/test_target_motion_filter.cpp` 等既有测试必须全绿；
  新增运动学的**离线性/边界**测试（Python 侧或 C++ 侧，按现有测试组织方式放对位置）。

### 阶段 3：真实运行验证（T2，占独占资源，必须持锁）

- 每次真实运行必须
  `flock -w 1800 /home/chen/AGC/.coordination/locks/sim.lock -c "<命令>"`
  （另一条链也用这把锁；**拿不到锁就等，不要抢、不要 kill 别人的进程**）。
- 至少这些 run（同一 seed 便于比较，`seed=0`；GUI 与 headless 均可，但**关键场景**按
  [契约 C3](../../../../docs/ROS2迁移交接文档.md#hard-constraints) 用 GUI 定性并留记录）：
  1. **基线对照**：改动前跑一次主场景 `s04`（yard），记录终态与时长；
  2. 新运动规则的场景（至少 2 次，同配置同 seed → 看可复现性）；
  3. **捕获场景仍可达**：`s08`（静态，`t_max 120`）与 `s13`（linear）至少各 1 次，
     证明结局不被新运动/速度破坏（`INTERCEPT_CONFIRMED/CAPTURE_NET`）；
  4. 提速后的主场景 1 次，记录新时长与 RTF。
- 每 run 写 `experiments/target-motion-speed/<run-id>/`，日志只留路径。

### 阶段 4：文档归位

- 新 ADR `docs/adr/0031-target-motion-and-speed-regime.md`：Status / 背景 / 决策（运动规则 +
  三主体速度 + 推导链 + 不做什么）/ Consequences（含失效边界、回滚方式、对既有 ADR 的影响）。
- 若改动了任何**工程规范**层面的口径（如运行节奏的可观测判据），写进
  `docs/conventions/演示可观测性与产物语义.md`，不要塞进 ADR。
- 更新根 `README.md` 的「已知边界」（若新运动/速度引入新的适用边界）。
- **删除** `docs/plan/目标无人机运动规则.md` 与 `docs/plan/速度调研与运行节奏优化.md`，
  确保无断链（`tests/docs_link_check.py` PASS）。ADR 索引重生成**必须持文档锁**：
  `flock -w 300 /home/chen/AGC/.coordination/locks/docs.lock -c "python3 scripts/adr_index.py"`。

## 六、白名单（只写这些；其余只读）

```
src/agc_task/scripts/intruder_driver.py
src/agc_task/config/scenarios.yaml
src/agc_task/config/scenario_carriers.yaml
src/agc_task/config/w6_base.yaml                # 仅 intruder_driver 段（若需）
src/agc_sim/config/car.yaml                     # 仅速度类参数
src/agc_rl/config/rl.yaml                       # 仅 speed 类参数
src/agc_air/config/air.yaml                     # 仅 speed 类参数（**不含** traj.speed，除非获授权）
src/agc_task/test/**                            # 既有测试 + 新增测试
scripts/tests/test_*.py                         # 仅新增的闸门测试
docs/adr/0031-*.md                              # 新建
docs/adr/README.md                              # 仅由 adr_index.py 生成
docs/conventions/演示可观测性与产物语义.md        # 仅运行节奏口径（如确需）
README.md                                       # 仅「已知边界」
docs/plan/目标无人机运动规则.md                   # 删除
docs/plan/速度调研与运行节奏优化.md               # 删除
experiments/target-motion-speed/**              # 新建
```

**禁区**：`toolchain/**`、`docs/ROS2迁移交接文档.md`、`src/agc_task/launch/**`（除非只是
carrier 断言，需先报）、`src/agc_perception/**`、`src/agc_sim/config/bridge.yaml`、
`src/agc_sim/models/**`、`src/agc_sim/config/world_geometry*.yaml` 与 `maps/**`（**高度归地图**，
属另一条链与既有裁定）、`.coordination/CURRENT.md`、另一条链
（`20261104-001-nadir-camera`）的任何文件。

## 七、资源授权

- **T0**：默认自主。
- **T1**：总墙钟 **1200 s**，单次 ≤30 s、进程 ≤2、独占 `/tmp/20261104-002-*`；次数只记账。
- **T2**：总墙钟 **5400 s**，次数只记账；**未派发不启动**；每次真实进程计时入账。
  构建（`colcon build --symlink-install --packages-select agc_task` 等）同样计入 T2。
  单次 launch 时长上限 **≤ 420 s**（含启动等待），超时即按失败登记并留证。

## 八、验收判据（可判定，缺一不算完成）

| # | 判据 | 证据 |
|---|---|---|
| A1 | 目标机运动**不停留在悬停**：新运动场景下 `/agc/gt/intruder_uav` 的轨迹位移包络达标（自定阈值并给推导），且 ≥2 次同 seed 结果一致 | 轨迹 CSV + 复现对比 |
| A2 | `static` / `linear` / `maneuver` 行为**逐值不变**（回归） | 参数与代码 diff + 一次回归 run |
| A3 | 新运动**不越界**：水平位移恒 ≤ `run_region_radius_m`；t=0 与起始位姿连续（无跳变） | 轨迹 CSV 断言 + 单测 |
| A4 | 捕获仍可达：`s08` 与 `s13` 各 ≥1 次达 `INTERCEPT_CONFIRMED/CAPTURE_NET` | `summary.json` terminal_state/reason |
| A5 | 速度改动**逐条**有推导与核验：C2 逃逸标定（`max_offset` @1.3 m/s）、网弹道提前量、`d_track` 可达性、`t_max` 预算，四项各给"变/不变 + 理由 + 证据" | 报告表格 + 实测 |
| A6 | 运行节奏可量化改善（给出改前/改后的终态墙钟与事件数），且**明确区分** RTF 因素与任务参数因素 | 两 run 对照表 |
| A7 | C1 未被越过：`traj.speed` 要么未改（给出"为什么不需要改"），要么已获 Leader/用户裁定（附授权来源） | git diff + 授权记录 |
| A8 | 契约**一字未改**；未新增 launch 参数（`test_branch_ledger.py` 绿）；未触碰 `toolchain/**` | 命令输出 + `git status` 白名单比对 |
| A9 | 新运动种类在 `scenario_carriers.yaml` 登记且 ≥1 活跃场景使用；离线测试全绿；`run_smoke` offline/docs/index 组绿 | pytest + run_smoke 摘要 |
| A10 | ADR-0031 落盘、索引 `--check` 通过；两个 plan 文件已删且 `docs_link_check.py` PASS | 命令输出 |

## 九、预登记停止条件（强制）

1. **资源/总时间**：T2 **5400 s**、T1 **1200 s** 用尽即停，交回已完成项与未完成项；
2. **无进展**：连续 **4 轮**（K=4）无区分性新证据即熔断并提交假设台账；
3. **根因已锁定时**，允许在同一白名单、同一资源总量内**修完并验完**，不因轮数或建议次数停工；
4. **N=6**：累计第 6 轮写一次"本轮小结 + 资源账目"，**不停止**；
5. **必须停下来问 Leader 的三件事**（属"待裁定"，不要自行决定）：
   a. 是否需要改 `traj.speed`（= 改契约 C1）；
   b. 是否需要改任何**判据阈值**（`d_track` / `t_dwell` / C2 / `safe_max` / 网弹道）；
   c. 目标速度若超过己方机 2.0 m/s 追赶上限，是否接受"必然跟丢"的演示后果。
6. 阻塞（需越白名单/契约、缺必要来源、并行资源冲突）→ 立即停并 `send_message` 通知 Leader。

## 十、回报要求

批次末（或四类触发事件）写本轮 `report.md`，**开头 ≤30 行审查摘要**：结论、差异清单、
证据链接、未决项。另须含：假设台账、下一轮建议、累计资源账目（T1/T2 次数与总时长、墙钟）。
`CURRENT.md` 由 Leader 独占写，你**不写**。
