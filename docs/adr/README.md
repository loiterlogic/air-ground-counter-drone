<a id="adr-index"></a>
# ADR 索引（自动生成）

> **本文件由 `scripts/adr_index.py` 生成，请勿手改**；改了会被 `--check` 抓到。
> 规则：编号与标题取自文件名与一级标题，`Status` 与「结论」取自各篇正文，**不推断、不改写**。
> 用法：查历史决策先扫本表 → 只打开命中的 1–2 篇；**不要**靠 `grep` 全目录。
> 全量决策仍以各 ADR 正文为准；本表只是索引。状态说明见 [目录与命名规范](../conventions/目录与命名规范.md#10-产物分类与生命周期)。

## 怎么用

- **想知道某件事当初怎么定的**：按标题/结论里的关键词在表里找，再点进去看正文。
- **`Status` 是原文摘录**（可能带日期与限定语）；`accepted` 表示决策有效，不代表实施完成。
- **`deferred` 不等于废止**：表示已裁定暂缓，括号里通常写了阻塞原因。
- **暂停的路线其 ADR 仍是 `accepted`**：暂停事实记在 plan 的开关文件，不写进 ADR 状态。

## 统计

- 合计 **107** 篇：`accepted` 104 篇、`deferred` 3 篇

## 索引表

| 编号 | 标题 | Status | 结论 |
|---|---|---|---|
| [0001](./0001-greenfield-ros2-rewrite.md) | ROS2 全新重写，而非逐包等价迁移 | accepted | 原《ROS2迁移步骤》假设"逐包等价迁移、保留接口语义"。我们改为：新项目根 = `/home/chen/AGC`（colcon 根即项目根）；ROS2 代码、实验产物、文档三类结构**从零搭建**新规范；ROS1 旧树 `anti_drone_agc_workspace/` **降级为只读归档参… |
| [0002](./0002-docs-source-of-truth-layering.md) | 文档真源分层与稳定锚点引用 | accepted | 每类信息只归属一个"家"：契约真源 = 《交接文档》；执行编排 = 《步骤文档》（Runbook）；per-workstream 规格 = 迁移期在 `.trae/specs/<ws>/{spec,tasks,checklist}.md`（2026-10-29 起归档于 `docs/archive… |
| [0003](./0003-nav2-pattern-complete-absorption.md) | Nav2 吸收策略：模式全覆盖、进程按域选用 | accepted | 《交接文档》（契约真源）曾称"Nav2 无 3D 规划器、无人机不适用"，与"Nav2 覆盖所有部分"冲突。折中为：**地面域**真跑 Nav2 本体（costmap、全局/局部 planner、controller、行为树）；**空中域**不引入 Nav2 运行时进程，但重写时全面采纳其架构范式… |
| [0004](./0004-rl-primary-controller-nav2-safety-layer.md) | RL 主控地面运动，Nav2 退居安全层与离线基线 | accepted | 地面域采用"分层接入 c2"：RL **直接输出 `cmd_vel`**，经 Nav2 `collision_monitor`（安全层：按多边形区域缩放/急停）收敛到唯一执行口 `/agc/ground/cmd_vel`。Nav2 的 planner/controller **不作为在线主控**，… |
| [0005](./0005-px4-link-uxrce-dds.md) | PX4 链路采用 uXRCE-DDS + px4_msgs，弃用 MAVROS | accepted | 空中链路以 Micro-XRCE-DDS Agent + `px4_msgs`（release/1.15，与固件同版）直连 PX4 uORB，弃用 MAVROS / MAVLink 中间层。 |
| [0006](./0006-domain-workstream-organization.md) | 重构以职责域 workstream 组织，而非时间序 P0–P6 | accepted | 重构按**职责域**切 workstream，每个 workstream 各带规格三件套（当时位于 `.trae/specs/<ws>/`，2026-10-29 起归档于 `docs/archive/specs/`，[ADR-0105](0105-retire-trae-and-relocate-… |
| [0007](./0007-experiment-artifacts-convention.md) | 实验产物唯一落点与命名规范 | accepted | 所有实验产物只落一个根，按 campaign → run 两层组织： |
| [0008](./0008-nav2-paradigm-absorption-as-code-principle.md) | Nav2 架构范式吸收：代码重构的交叉原则 | accepted | "吸收 Nav2"（见 [GLOSSARY](../../GLOSSARY.md) 的**选择性吸收**）不只在进程与架构层生效（ADR-0003 / ADR-0004），而是**贯穿 W1–W6 代码重构的交叉原则**：每个 workstream 在重写原 ROS1 代码时，必须显式采纳 Nav… |
| [0009](./0009-sim-first-with-hardware-hooks.md) | 纯仿真优先，为实机预留接口 | accepted | 重构以**纯仿真**（GZ Sim + PX4 SITL）为唯一验收环境；传感器口径、时钟、PX4 链路按仿真标定。为实机预留可替换接口，但**不承诺**支持真机，也不为其牺牲仿真重构的自由度。 |
| [0010](./0010-ground-drive-real-physics.md) | 地面驱动采用真实物理（GZ DiffDrive） | accepted | 旧树地面车采用 `kinematic_sim`：`ground_drive_adapter` 对 `/agc/ground/cmd_vel` 做运动学积分（`x += vx·cos(yaw)·dt`、`y += vx·sin(yaw)·dt`、`yaw += wz·dt`），再经 `/gazebo… |
| [0011](./0011-node-language-policy.md) | 项目节点语言选型：C++ 实时域 / Python RL 域 | accepted | W0 的《目录与命名规范》已隐含"节点包用 `ament_cmake`（C++）、RL / 工具用 `ament_python`"， 但该划分**沿袭自旧树语言分布，未经显式论证**。本 ADR 将其**显式化并钉死**： |
| [0012](./0012-px4-body-as-toolchain-dependency.md) | PX4 本体以 toolchain 外部依赖形式纳入 | accepted | [ADR-0005](0005-px4-link-uxrce-dds.md) 只决了**链路协议**（uXRCE-DDS + `px4_msgs`）， 未决"PX4 本体是否纳入项目、以何形态"。P0 已实际落地：`toolchain/PX4-Autopilot`（v1.15.4， SITL 已构… |
| [0013](./0013-rewrite-as-deliverable-sim-only.md) | 重写即交付物：软著/平台，论文产出于纯仿真 | accepted | 本项目（大创）的软件交付物**就是本仓库本身**，而非另立的系统： |
| [0014](./0014-research-mainline-mobile-interception-system.md) | 研究主线：移动式主动拦截系统（系统论文为主，协同路径规划为核） | accepted | 论文主线定为 **移动式主动拦截系统**（系统 / 集成论文，D）为主、**空地协同路径规划 / 制导**（A）为核；二者共用本仓库仿真，不另立系统。 - **RL 地面控制（B）** 与 **多源信息融合（C）** **不放弃**，但**归入"项目结束后的后续研究"**——本仓代码与其 work… |
| [0015](./0015-interception-scope-physical-capture-and-behavioral-jamming.md) | 拦截纳入范围：物理捕获判据 + 行为级电子干扰（真实 EMI 不建模） | accepted（W6 修订，见文末「修订」） | 项目完全依托仿真后，**"干扰 / 拦截"纳入范围**，形态为 **物理拦截 + 电子干扰（行为级）**： |
| [0016](./0016-execution-scope-exit-w6.md) | 本次执行范围出口到 W6；拦截落于 W2/W6，不新增 workstream | accepted | 本次攻关范围**以 W6（任务与评估）为出口**：W3–W6 打通即"平台 / 软著"达标；**W7（RL 平台）、W8（新旧对照）归"项目结束后后续"**（与 [ADR-0014](0014-research-mainline-mobile-interception-system.md) 一致）… |
| [0017](./0017-air-ground-collaboration-loop.md) | 空地协同回路：无人机常开 standoff 跟踪 + 自保，地面自主规划 | accepted | 论文"核"为**空地协同路径规划**（[ADR-0014](0014-research-mainline-mobile-interception-system.md)）。据此定本次协同回路口径： |
| [0018](./0018-shared-control-layer-and-lqr-plugin.md) | 通用控制层与共享 LQR 插件化（`agc_control`） | accepted | 空中与地面两个域都需要**轨迹跟踪**能力：W3 空中需要 LQR 跟踪真八字与目标（standoff），W5 地面需要一个**离线对照基线**控制器（地面主控仍是 RL，[ADR-0004](0004-rl-primary-controller-nav2-safety-layer.md)）。若各… |
| [0019](./0019-uav-trajectory-and-tracking-parameter-calibration.md) | 无人机轨迹与跟踪参数标定（含 C1 修订） | accepted | 契约硬约束 **C1** 原文为「8 字轨迹全程恒速、无加减速；角速度 0.1（线速度 0.3 m/s）」。核对旧树后确认两项问题： |
| [0020](./0020-perception-as-truth-derived-simulation.md) | 感知为真值派生仿真（非真实视觉 / 雷达） | accepted | W4（感知与融合）重写旧 `air_perception` / `air_fusion` 时须定"感知到底模拟什么"。旧树的做法是**真值派生感知仿真**：从仿真世界真值出发，按通道建模**丢包 / 突发丢失 / 几何门控（量程 + FOV）/ 遮挡 / 高斯噪声与偏置**，并给出**已标定置信度… |
| [0021](./0021-ground-safety-thresholds-and-platform-recalibration.md) | 地面安全阈值重标定（C2 修订）与地面平台换装 | accepted | *问题一（C2 阈值过时）**。契约硬约束 **C2** 原为「距离阈值顺序 紧急 < 碰撞 < 安全（默认 `0.7m < 0.9m < 2.4m`）」。核对溯源：该组数值派生自旧树**无人机**规则避障配置（`reference/old_ros1/src/rl_obstacle_avoidan… |
| [0022](./0022-launched-net-capture-mechanism.md) | 物理捕获改为发射式网（交战包络由网发射物理模型的可及集推导 + 裁决器可插拔） | accepted | 原物理捕获口径（[ADR-0015](0015-interception-scope-physical-capture-and-behavioral-jamming.md) 及 W2-interception 模型）为**车载固定**直径 2 m 圆面 + "目标**穿越 2 m 圆网面** /… |
| [0023](./0023-spawn-clearance-recalibration.md) | C7 重推：出生净空为可标定量（语义拆分），不再沿用旧值 2.4 m | accepted | *问题（C7 旧值过时）**。契约硬约束 **C7** 原为「场景生成须保证**出生间距 ≥2.4 m**；复位失败最多重试 3 次且不占 episode 预算」。核对溯源：`2.4 m` 与 [ADR-0021](0021-ground-safety-thresholds-and-platfor… |
| [0024](./0024-capture-adjudication-fire-control-window.md) | 捕获裁决口径厘清：现「入包络即命中」为闭式占位，后续以「火控窗口 + 瞄准提前量」为口径 | accepted | [ADR-0022](0022-launched-net-capture-mechanism.md)(c) 定：物理捕获现阶段 = **闭式几何判定**（**发射时刻**判断目标是否落在网发射物理模型的**可及集**内），`capture adjudicator` 可插拔，后续换逐帧弹道判定器。 |
| [0025](./0025-gz-side-terminal-failstop-deadman-plugin.md) | GZ 侧末端失效停车：意图/执行分离 + System 插件死区守门人（R-009） | accepted | 在**唯一执行通道内部**（GZ 服务器进程内）建立**末端失效停车**，采用「**双话题 + 死区看门狗**」：让守门人插件成为 `DiffDrive` 命令口的**唯一写入者**，而「意图」走另一条 gz 话题。 |
| [0026](./0026-rl-action-conventions-and-ground-escape-calibration.md) | RL 动作方向 / 量纲约定与地面逃逸能力标定（C6 · R-011） | accepted | 评审风险 **R-011（动作与能力）**：`agc_rl` 的动作映射 `interface.action_to_twist` 存在**符号反转**与**量纲混用**， 且偏移参数（`min_offset` / `max_offset`）**未形成对差速车真实横向逃逸的实测**——C6（契约 [… |
| [0027](./0027-baseline-path-binding-and-replan-failstop.md) | 离线基线路径绑定与重规划失效安全（R-012） | accepted | 评审风险 **R-012（规划失败）**：`agc_ground` 的离线对照基线 `ground_baseline::plan()` 对新路径为空或抛异常 **仅打印 warning、不清旧 `path_`**；`tick` 随后继续 `lookaheadRef` **旧路径**。路径**未绑定… |
| [0028](./0028-task-start-transaction-and-freshness-gate.md) | 任务起始异步事务与新鲜门禁（R-013） | accepted | 评审风险 **R-013（起始门禁竞态）**：`/agc/task/start` 在**主单线程回调内阻塞**（`spin_until_future_complete` 于另建客户端节点），`scenario/reset` + `air/reset_phase` 等待期间任务自身的 `odom_v… |
| [0029](./0029-spawn-clearance-entity-pairs-and-boundary.md) | 出生净空统一候选校验：实体对 + 边界（不再用单一标量代理） | accepted | ### (a) 统一候选校验函数 `scenario_reset` 新增统一校验 `validateCandidate(cx, cy, tx, ty, reason)`，对**每个候选** （含随机搜索的每一轮）按序检查，任一不满足即拒并给出 `reason`： |
| [0030](./0030-scenario-reset-controlled-transaction.md) | 场景复位受控事务与失效安全（R-015；含 X-03 门控裁定） | accepted | 评审风险 **R-015（复位事务）**：`scenario_reset` 的复位只有**两次非原子 `set_pose`**——车、目标依次 写入，**目标写入失败会留下「车已移动、目标未复位」的中间态**；无写入后**读回**核验； `isResettable` **漏 `INTERCEPT_… |
| [0031](./0031-intruder-episode-start-protocol.md) | 入侵者 episode 起点协议（预热 / epoch / 起始位姿 / 切入与边界 / CLEAR 重基准） | accepted | ### (a) 预热独立于 episode 计时 节点启动即记 `warmup_t0_`（`_now_us()`）；`tw = now - warmup_t0_`。`tw > 1.0 s` 才请求 ARM；`armed_` 且 `nav_state_ != OFFBOARD(14)` 时请求 `V… |
| [0032](./0032-jam-single-authorization-and-validated-event.md) | 干扰单一授权与已校验事件（jammer 唯一裁决 / 包络新鲜度 / 复用 jam_state） | accepted | ### (a) `jammer` 为唯一授权裁决 `jammer` 是干扰授权的**唯一裁决者**：仅当「命令合法」（`key in JAM_MAP`）**且**「作用包络**新鲜**」 才产出**已校验授权事件** `JAM_*`（发布到 `state_topic`，默认 `/agc/task/… |
| [0033](./0033-jam-real-behavior-confirmation.md) | 干扰真实行为确认（证据链拆分 / ACK ≠ 效果 / 负例分类） | accepted | ### (a) 证据链拆分：意图 → 授权 → 发送 → ACK → 真实 nav 状态 → 持续行为 `jammer` 仍是干扰**授权 / 确认的唯一裁决者**（[ADR-0032](0032-jam-single-authorization-and-validated-event.md)）。… |
| [0034](./0034-failsafe-factor-separation-and-runtime-param-lock.md) | failsafe 因子分离与运行时参数锁定（三因子 / 「停流 ≠ `NAV_DLL_ACT`」更正） | accepted | ### (a) 三类独立实验因子 `jammer` 以**因子标签**（`factor`）区分三类可独立观测 / 标注的干扰因子，修正「停流 ≡ `NAV_DLL_ACT`」： |
| [0035](./0035-placeholder-envelope-labeling-and-independent-jam-envelope.md) | 占位包络标注与独立干扰作用包络（R-020：高度含车体 / 模型身份与适用范围 / 捕获≠干扰） | accepted | ### (a) 高度**含车体** `h = target.z − car.z − launcher_h`（R-020；`car.z` 取 `/agc/ground/odom`）。保留 `h ≥ 0` 与可达判据 （`vy² ≥ 2gh`，即 `disc = vy² − 2gh ≥ 0`）。 |
| [0036](./0036-capture-event-episode-isolation-and-event-identity.md) | 捕获事件 episode 隔离与事件身份（R-021：任务窗口 / 输入寿命 / 一次性复位 / 先命中者胜按时刻） | accepted | ### (a) 任务窗口门控（仅有效回合产出） `capture_adjudicator` 订阅 `/agc/task/state`（`AgcTaskState`，订阅态）；**仅当** `state == GROUND_APPROACH` （有效任务窗口）**且**输入新鲜**且**身份匹配时才… |
| [0037](./0037-fsm-command-idempotency-and-terminal-latch.md) | FSM 命令幂等与终态锁存（R-022：start/abort 允许态 / 终态锁存 + episode 关联 / 非确定性不误置） | accepted | ### (a) 允许态矩阵 \| 命令 \| 接受态 \| 拒绝态（回显当前态；不 reset / 不 fail / 不覆写） \| \|---\|---\|---\| \| `/agc/task/start` \| `IDLE` + 任一终态（`TRACKING_SUCCESS` / `INTE… |
| [0038](./0038-continuous-tracking-dwell-interruption.md) | 连续跟踪 dwell 逐拍判据中断（R-023：空数组不清 dwell / 换目标清零 / 车 odom 寿命门 / 分段有效时长） | accepted | ### (a) dwell 提升为逐拍显式判据 `GROUND_APPROACH` 分支内（capture / jam 结算之后）改为： - 本拍合法性：`car_age`（由 `last_car_odom_rx_` 到达时刻算）→ `car_ok`（`have_car_ && 0 ≤ age ≤… |
| [0039](./0039-time-budget-kinds-and-rtf-record.md) | 三类时间预算口径与 RTF 记录（R-024：mission_sim_budget / episode_wall_watchdog / 进程时长） | accepted | ### (a) 三类口径成文并命名（互不冒充） |
| [0040](./0040-full-chain-coverage-matrix-and-same-run-causal-record.md) | 整链覆盖矩阵与同一 run 因果记录（R-025：backend/mode 如实标注 + pass 命题化） | accepted | ### (a) 覆盖矩阵（backend / mode × 各轴，逐轴标注） |
| [0041](./0041-scenario-axis-carriers-and-coverage.md) | 场景轴承载者校验与覆盖记账（R-026：声明轴必须有承载者，未执行轴如实标注） | accepted | ### (a) 轴→承载者登记（`config/scenario_carriers.yaml`） |
| [0042](./0042-safety-infeasibility-honest-metric-and-contact-evidence.md) | 安全不可行率诚实口径与真实接触证据（R-027：proxy_v1 保留 + gz_contact_v1 真实碰撞） | accepted | ### (a) 保留历史字段 proxy_v1 + 口径版本标注 |
| [0043](./0043-episode-window-metrics-and-valid-sample-mask.md) | ADR-0043: episode 窗口统计、终态锁存与有效样本掩码（R-028） | accepted | ### (a) episode 事件窗口分段（窗口口径 ≠ 进程口径） |
| [0044](./0044-unique-run-identity-and-reproducible-evidence.md) | 唯一运行身份与可复现证据（R-029） | accepted | ### (a) run_id 唯一不可覆盖（保留 `-<scenario>-<seed>` 子串） |
| [0045](./0045-resetfail-evidence-contradiction-registration-and-redo.md) | resetfail 证据矛盾登记与唯一新 run 重做（R-030） | accepted | ### (a) 据实登记，不伪造、不冒充复核 |
| [0046](./0046-runner-three-layer-acceptance-and-integrity-gate.md) | runner 三层验收判定与完整性硬门（R-031） | accepted | ### (a) 三层验收判定，全必过方 `PASS` |
| [0047](./0047-c10-freeze-downstream-closure-source-time-and-offset-lifetime.md) | C10 冻结下游封闭：已获模式、源时间与 offset 寿命（R-032） | accepted | ### (a) 已获模式（`acquired_`）+ 显式 hold，**不**静默回落 `base_ref` |
| [0048](./0048-uav-joint-safety-barrier-and-explicit-infeasible-path.md) | UAV 联合安全屏障与显式不可行路径（R-033） | accepted | ### (a) 联合约束复检（**不**让后投影重新落入前约束） |
| [0049](./0049-lifecycle-repeatable-resource-state-machine-and-liveness-detection.md) | 生命周期可重复资源状态机与失联检测（R-034） | accepted | ### (a) 可重复资源状态机（configure 幂等） |
| [0050](./0050-air-control-single-authority-and-permit.md) | 空中控制唯一权威与控制许可（R-035） | accepted | ### (a) 单一权威 = 显式控制许可（lease），判据「本机是否唯一授权命令者」 |
| [0051](./0051-c1-height-semantics-and-same-time-evidence.md) | C1 高度语义统一与同时间证据曲线（R-036） | accepted | ### (a) C1 口径裁定（对齐 X-01，**不静默**） |
| [0052](./0052-sensor-and-vehicle-model-limitation-and-capability-calibration.md) | 传感器/车体限制声明与能力标定（R-037） | accepted | ### (a) 如实登记传感器高度 + 障碍族限制，并收窄安全声明 |
| [0053](./0053-lqr-numeric-model-exposure-and-config-validity.md) | LQR 数值模型暴露与配置合法性启动校验（R-038） | accepted | ### (a) LQR：精确离散化 + DARE 收敛 / 有限性失败路径 + 集中合法性校验 |
| [0054](./0054-ground-odom-source-time-and-reset-epoch-velocity.md) | 地面 odom 源时刻分离与复位 epoch 速度历史（R-039） | accepted | ### (a) 源采样时刻 = 发布时刻（方案 A：仅新样本发布，不静默外推） |
| [0055](./0055-map-content-identity-and-monotonic-update-sequence.md) | 地图内容身份与单调更新序号（R-040） | accepted | ### (a) 内容身份 hash 折入几何元数据与源版本 |
| [0056](./0056-goal-invalidation-policy-and-displacement-triggered-replan.md) | 目标失效策略与位移阈值化重规划（R-041） | accepted | ### (a) 目标失效策略裁定：「保留有期限的最后有效目标」（bounded hold-last-valid） |
| [0057](./0057-c3-gui-acceptance-scope-authorization.md) | C3 GUI 验收范围裁定：定性验收与规模统计分开授权（X-02） | accepted | 裁定采纳 **(b) 分层授权**： |
| [0058](./0058-capture-adjudicator-replacement-contract-and-event-semantics.md) | 捕获裁决器替换契约澄清：对外视图不变，**不**排除内部事件语义演进（X-05） | accepted | *(b) 收窄并澄清"调用方不改"（已采纳）**： |
| [0059](./0059-package-dependency-taxonomy-and-boundary-revision.md) | 包依赖按类别分层（修订包边界） | accepted | W0 产出的 [包边界](../conventions/包边界.md) 把**消息通信 / 库链接 / launch 依赖混成同一规则**：原文规则 1「`agc_msgs` 是唯一公共依赖」与规则 2「其余包之间不得互相依赖对方的库」照字面会**禁止必要的运行依赖**（如 `agc_task`… |
| [0060](./0060-nav2-absorption-applicability-and-command-source-trimming.md) | Nav2 吸收的适用关系与按命令源进程裁剪 | accepted | 结构评审 [S-04](../reviews/agc-review-2026-10-14/20-结构.md#s-04)（**挑战既定约束 · 已裁定正式修订**）指出：「吸收 Nav2」不应以**空壳类数量 / 闲置进程数量**验收。两处须校准： |
| [0061](./0061-w6-runtime-topology-backend-identity-and-single-parameterized-entry.md) | W6 运行拓扑 backend 身份与单一参数化入口 | accepted | 结构评审 [S-05](../reviews/agc-review-2026-10-14/20-结构.md#s-05)（**用户裁定 · 正式修订**）指出：`m0_skeleton` / `w6_task_eval` / `w6_full` **重复组装**——后两者各自内联一份**完全相同**… |
| [0062](./0062-scene-geometry-single-source-and-derivation.md) | 场景几何单一真源与按域派生 | accepted | 结构评审 [S-06](../reviews/agc-review-2026-10-14/20-结构.md#s-06)（**用户裁定 · 单一真源 + 派生**）指出：同一几何事实存在**五份独立副本**——物理世界（[`agc_world.sdf`](../../src/agc_sim/worl… |
| [0063](./0063-campaign-attribution-and-temp-file-uniqueness.md) | campaign 归属与临时文件唯一（S-07） | accepted | ### (a) 规范同实装 |
| [0064](./0064-evidence-immutable-archive-and-intake-manifest.md) | 证据不可变归档与入库 manifest（S-08） | accepted | ### (a) 入库 manifest 落 `config/evidence_manifest.json`（只索引不复述） |
| [0065](./0065-toolchain-rebuildable-pin-manifest.md) | 工具链可重建 pin 清单与一致性校验（S-09） | accepted | ### (a) `toolchain/README.md` = 唯一入库的可重建 pin 清单 |
| [0066](./0066-decision-applicability-and-reference-discipline.md) | 决策适用关系与引用纪律 | accepted | 结构评审 [S-10](../reviews/agc-review-2026-10-14/20-结构.md#s-10)（中）指出：accepted ADR 的**历史正文**与后续修订 / 下游状态**残留并存**且缺**当前适用关系**；spec / checklist **相对链接层级不符**… |
| [0067](./0067-toolchain-root-explicit-injection-and-preflight-validation.md) | 工具链根显式注入与启动前验证（S-11） | accepted | ### (a) 项目根由 launch 参数显式注入 |
| [0068](./0068-third-party-asset-provenance-license-and-hash-manifest.md) | 外部资产来源、许可与哈希清单（S-12） | accepted | ### (a) 第三方资产独立清单（人读 + 机器可读） |
| [0069](./0069-w7-entry-and-exit-definition.md) | W7 入口与出口定义：平台出口、复用当前空地仿真栈、前置以可复现证据为准 | accepted | ### (a) W7 第一个出口 = 可信实验平台，不是算法成果 |
| [0070](./0070-w7b-research-propositions-and-rl-role-adjudication.md) | W7-b 科研命题与 RL 角色裁定框架：两条单一自变量可证伪命题、最小火控与归因前置、预注册判定 | accepted | ### (a) 两条可证伪命题，各自**单一自变量** |
| [0071](./0071-w7b-adjudication-record-and-pending-arms.md) | W7-b 裁定记录：火控占位升级、射击授权为任务决策、臂可运行性证据与待建臂 | accepted | ### (a) 入口前置能力 E1–E5 已落地（每条有可复现 run 证据） |
| [0072](./0072-px4-attitude-quaternion-field-order-and-full-chain-observation-fix.md) | PX4 姿态四元数字段序（Hamilton [w,x,y,z]）解析错误与整链观测链修复 | accepted | ### (a) 事实：PX4 姿态四元数字段序为 Hamilton **[w,x,y,z]** |
| [0073](./0073-p1-arm-fairness-noncoop-fixed-trajectory.md) | P1 臂公平性修正：非协同臂 = 空中固定航迹（不订阅目标跟踪参考） | accepted | ### (a) 非协同臂按 [ADR-0070](0070-w7b-research-propositions-and-rl-role-adjudication.md) 字面「**空中固定航迹**」重新定义 |
| [0074](./0074-visibility-metric-fixed-observation-window.md) | P1 度量口径修正：可见 / 火控机会率改用**固定观测时长窗口** | accepted | `visibility_metrics`（P1 的 DV 来源）口径改为 **`window_fixed_v1`**： |
| [0075](./0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md) | 整链 uXRCE 实体创建**间歇**失败（PX4 1 s 硬预算）与 runner 级 infra 重试协议 | accepted | ### (a) 根因：agent 侧 participant 创建**间歇**超时 + PX4 客户端**硬编码 1 s** 预算 |
| [0076](./0076-capture-scenario-tracking-milestone-not-terminal.md) | capture 类场景中跟踪里程碑**不再等价终态**（捕获交火窗口不被提前关闭） | accepted | ### (a) 新增**单一注入**参数：`task_manager.tracking_milestone_is_terminal` |
| [0077](./0077-w7c-multi-worker-isolation.md) | W7-c 多 worker 隔离设计（**草案 / 未实施**） | deferred（2026-10-25：C4 legacy DV 记录保留；[ADR-0095](0095-w7c-admission-metric-and-worker-run-dir-isolation.md) 的 A/B 门因 B3 `INFRA_FAILURE` 未通过，继续保留单 worker；W7-c 批跑未启动） | W7-c 的目标是把 W7-a/b 的**单 worker 串行**评估扩为**同机多 worker 并行**（[ADR-0069](0069-w7-entry-and-exit-definition.md)「单 worker 可重放」→ 多 worker 隔离）。 |
| [0078](./0078-capture-event-episode-identity-single-source.md) | capture 事件的 episode 身份改由 task episode 单一来源（启动双复位竞态致命中被丢弃） | accepted | ### (a) episode 身份**单一来源** = `/agc/task/episode` |
| [0079](./0079-b2-fire-control-target-motion-estimation.md) | B2 火控目标运动估计：时间窗回归替代逐帧差分（含发射解算门） | accepted | ### (a) 新增 `TargetMotionFilter`（纯标准库、可单测） |
| [0080](./0080-air-lifecycle-startup-robustness.md) | 空中 lifecycle 启动健壮性：服务预热 + bond 仅在 activate 建立 | accepted | ### (a) manager 启动前预热 lifecycle 服务连接 |
| [0081](./0081-public-repo-publishing-boundary.md) | 公开仓库发布边界：`.trae` 与 `experiments` 不入版本库 | accepted | ### (a) `.gitignore` 排除 |
| [0082](./0082-w7b-p2-arm-b-rule-high-level-first.md) | W7-b P2 臂 B 先以规则高层承载（职责分层优先，训练 RL 后置） | accepted | ### (a) P2 v1 使用规则高层 |
| [0083](./0083-w7b-p2-arm-information-equivalence-and-active-window-fco.md) | W7-b P2 修正：臂信息等价 + active-window FCO 口径 | accepted | ### (a) v2 批次不作为 P2 判定证据 |
| [0084](./0084-w7b-p1-active-window-dv-recheck.md) | W7-b P1 窗口口径复核：active-window FCO 为 primary（预注册 v4） | accepted | ### (a) 新预注册 v4：P1 primary 改为 active-window FCO |
| [0085](./0085-w7b-p1-mechanism-activating-scenario-pilot.md) | W7-b P1 机制激活重测：pilot 候选场景与**先定**的选场景规则 | accepted | ### (a) 先 pilot 选场景，再写预注册 v5 |
| [0086](./0086-decision-rule-three-state-ci-versus-mme.md) | 判据语义修正：分离「最小有意义收益」与「样本量可检测效应」，判定改三态（CI vs MME） | accepted | ### (a) 术语与角色分离（新版本预注册 **SHALL** 分列两个量） |
| [0087](./0087-p1-mechanism-ablation-and-p2-arm-b-diagnosis-scope.md) | P1 机制消融（指向 × 跟踪参考 2×2）与 P2 臂 B 负向诊断的范围裁定 | accepted | ### (a) P1：2×2 析因消融（**先定规则**，独立批次） |
| [0088](./0088-mme-change-governance-independent-justification-and-seed-isolation.md) | MME 变更治理：独立工程依据、种子隔离与按判定规则重新规划 | accepted | ### (a) 禁止事后降门槛 |
| [0089](./0089-map-signature-lethal-only-for-replan-trigger.md) | 地图签名仅计 LETHAL_OBSTACLE（P2 重规划审计的地图伪触发修复） | accepted | 把 `ground_baseline::mapSignature()` 的参与判据由 `cost >= 253` 改为 **`cost == 254` （`LETHAL_OBSTACLE`）**；分层诊断计数同口径。签名仍为 FNV-1a over `sx / sy / origin_x / or… |
| [0090](./0090-w7b-post-audit-v7-gate-and-implementation-fixes.md) | W7-b 核实后的决策门：不注册 v7、保留 `inconclusive` / c2，先修火控状态机 | accepted | ### (a) 本阶段**不注册 v7** |
| [0091](./0091-fire-control-inflight-lifecycle-decoupling.md) | 火控在飞生命周期与发射资格解耦（模型身份 v2） | accepted | ### (a) 在飞优先：推进 / 落地 / 超时结算与发射资格解耦 |
| [0092](./0092-moving-target-costmap-marking-and-replan-policy.md) | 移动目标 costmap marking 与重规划触发策略（地图签名仅静态层） | accepted | `ground_baseline::mapSignature()` **只使用 `static_layer` 自身的栅格内容**（尺寸 / 原点 / `LETHAL_OBSTACLE=254` 格索引，FNV-1a 64 位）；**obstacle / voxel 层的动态 marking 不再参… |
| [0093](./0093-w7b-exit-closure-and-prefix-provenance.md) | W7-b 出口闭合、修复前溯源与剩余消融范围裁定 | accepted | ### (a) 保留历史结论，不因修复重判 |
| [0094](./0094-uxrce-participant-warmup-and-px4-stagger.md) | uXRCE participant 创建预热与 PX4 错峰（1 s 预算内的可复现整链启动） | accepted（A5 5 连冷启动全部 infra-free；4/5 `INTERCEPT_CONFIRMED`、1/5 `MISSION_FAILED(TIMEOUT)`，后者为 mission 终态，不是 uXRCE infra） | ### (a) own / intruder 错峰（主修复） |
| [0095](./0095-w7c-admission-metric-and-worker-run-dir-isolation.md) | W7-c 扩容准入指标修正、单 worker 重复性诊断与 PX4 运行目录隔离 | deferred（2026-10-25：指标修正与隔离设计已落地；A/B 门因 B3 `INFRA_FAILURE` 未通过，显式保留单 worker；W7-c 并行准入 deferred） | ### (a) 准入 DV 改为 active-window 指标 |
| [0096](./0096-w8-gui-headless-equivalence-design-bounds-and-gate.md) | W8 出口分层、GUI/headless 等价设计与执行闸门 | deferred（2026-10-25：GPU-GUI 修正 pilot 完成；项目默认 GUI 渲染后端 `auto` 已落地；RTF 与 headless 对齐，但 active FCO / 率类散布大，δ≤0.05、n≤40 下正式等价不可行；gate `not_evaluated`；headless 规模统计未授权） | ### (a) W8 出口分层 |
| [0097](./0097-w8-historical-parity-and-conditional-platform-freeze.md) | W8-E1b：ROS1 历史证据对照与条件平台冻结（旧环境不可重建） | accepted（2026-10-25：ROS1 Noetic 运行时不可用、旧树无运行产物；按评审 F-12 缩为历史证据对照；平台冻结为 conditional） | ### (a) W8-E1 拆分 |
| [0098](./0098-w8-determinism-probe-and-measurement-spec-change.md) | W8 P1 确定性探针与测量规格变更 | accepted（2026-10-26：旧证据重核及独立 n=5 重做均观察到固定 seed 的执行级散布；W8-E1a gate 保持 `not_evaluable_as_specified`） | 5 个有效 attempt 的 active FCO 为 `0.000000, 0.007163, 0.000000, 0.001958, 0.076797`，极差 **0.076797**；active window 长度为 `120.028, 23.224, 120.096, 85.108,… |
| [0099](./0099-w8-fixed-budget-mission-fco-measurement.md) | W8 测量 P2：固定预算内的任务 FCO 与终态处理 | accepted（2026-10-26：指标语义裁定完成；记录器实现与新执行计划尚未冻结，归属 P3；gate 仍为 `not_evaluable_as_specified`） | 用户授权在前置满足后执行测量 P2。[P1 独立重做](0098-w8-determinism-probe-and-measurement-spec-change.md#redo) 已完成；规格见 [P2 spec](../archive/specs/w8-measurement-p2/spec.… |
| [0100](./0100-full-chain-seed-protocol.md) | Full-chain seed protocol for PX4 and perception | accepted（2026-10-26；协议决策已接受，实施验证未闭合，见 [证据边界](0101-w8-seed-evidence-and-p3-execution-boundary.md#evidence)） | W6 `seed` is the experiment master seed. `w6_composition.py` derives one uint32 seed per PX4 process with `agc-px4-sim-seed-v1`; instance 0 is own, i… |
| [0101](./0101-w8-seed-evidence-and-p3-execution-boundary.md) | W8：种子证据、版本边界与测量 P3 派工 | accepted（2026-10-26；证据分类及执行范围已裁定，P3 实施待执行、待 Codex 审查） | 承接 [上轮交接审查](../../.coordination/archive/20261026-001-handoff-baseline/review.md#review)；补充 [ADR-0100](0100-full-chain-seed-protocol.md#scope) 的证据边界，以… |
| [0102](./0102-leader-worker-dual-model-handoff.md) | 协作机制：Leader/Worker 双模型替代 Codex+DSH | accepted（2026-10-28，来源：用户裁定；配置已实施，端到端验收待新 Leader 会话完成） | 改用**同一 DSH 进程内的双模型分工**： |
| [0103](./0103-vision-perception-decision-path.md) | 视觉识别接入任务决策路径（真值派生 → 视觉驱动） | accepted（2026-10-29，来源：用户裁定——"要接进任务决策（用视觉替代真值感知）"） | *新增"视觉驱动感知路径"作为与真值派生并行的第二条决策输入路径，二者互斥选择、显式标注、不可混读。** |
| [0104](./0104-batch-authorization-and-stall-circuit-breaker.md) | 批次授权：以唤醒次数为成本单元替代逐轮审查 | accepted（2026-10-29，来源：用户裁定——"leader 的 tokens 消耗负担不起，worker 的消耗再多也无所谓，主要是 worker 权限和自由度太低"；2026-10-29 P0-5 追加修订，见文末"修订（P0-5 实测后）"，不改前文正文） | *成本单元从"轮次"改为"唤醒次数"**，具体四改： |
| [0105](./0105-retire-trae-and-relocate-specs-skills.md) | 退役 Trae：规格迁入 `docs/archive/specs/`、技能迁入 `.agents/skills/` | accepted（2026-10-29，来源：用户裁定——"完成 P0-3；以后不再用 Trae"，并明确要求把 specs 迁出、把 4 个技能迁到 `.agents/skills` 并适配当前 Harness） | ### (a) 规格整体迁到 `docs/archive/specs/`，仍然不发布 |
| [0106](./0106-work-area-100x100-and-yard-layout-paradigm.md) | 作业区放大到 100×100 与场站式布局范式 | accepted（2026-10-29，来源：用户裁定——"我考虑到在空地协同反无人机中 80\*80 可能不太够，改成 100\*100，然后重新布局障碍物分布和数量以及样式，样式要考虑现实世界中正常情况下是怎么分布的"；并明确要求"先学习别人是怎么做的，然后设计，一定是设计好大致分布再动手"） | P1-1 首版 `yard`（80×80 作业区、19 实体）由用户 2026-10-29 两轮反馈逐步修正（删双柱、中央加内容、 引入 `sphere` 与复合 `parts`）。用户随后提出**作业区尺度不足**，并要求**按现实分布重做**。 |
| [0107](./0107-retire-old-tree-paused-switch-and-legacy-backlog.md) | 收尾清理批次：退役旧树归档、暂停开关与旧候选清单 | accepted（2026-10-31，来源：用户裁定——"删除 `.trae`、`.vscode`、`reference`，他们都没有用了"；并就逐项确认回选"确认作废 `PAUSED.md`"、"旧候选清单只留 git 历史、不再维护"、"`reference/` 直接删除，我另有备份"） | ### (a) 退役旧树归档 `reference/` |

## 相关

- 文档真源分层与稳定锚点：[ADR-0002](./0002-docs-source-of-truth-layering.md)
- 决策适用关系与引用纪律：ADR-0066（`./0066-decision-applicability-and-reference-discipline.md`，见其「背景与决策」节）
- 新增 ADR 的写法：[`.agents/skills/domain-modeling/ADR-FORMAT.md`](../../.agents/skills/domain-modeling/ADR-FORMAT.md)
