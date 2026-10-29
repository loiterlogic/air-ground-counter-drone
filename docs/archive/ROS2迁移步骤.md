<a id="top"></a>
# ROS2 重构 Runbook（历史归档）

> **历史归档（2026-10-29 起）**：迁移推进已暂停（[开关](../plan/PAUSED.md#paused)），本文**不再作为执行入口**，只作编排史查阅。
> **当前方向见** [项目完成路线](../plan/README.md#plan-index)。本文的状态表（[#status](#status)）**不再是进度真源**。
> 归档原因与位置变更见 [ADR-0105](../adr/0105-retire-trae-and-relocate-specs-skills.md)；原路径 `docs/ROS2迁移步骤.md` 不留转发文件。

---

> **原文角色（归档前）**：本项目唯一的**执行入口（Runbook）**（见 [GLOSSARY](../../GLOSSARY.md)）。只编排"现在做什么、如何验收"。
> **不承载**：任何约束 —— 约束一律**引用**契约真源 [ROS2迁移交接文档](../ROS2迁移交接文档.md)，不复述（[ADR-0002](../adr/0002-docs-source-of-truth-layering.md)）。
> **读者**：agent（按本文推进，每步须可判定）为主，人工以检查视角复核。
> **引用约定**：跨文档引用用稳定锚点（`<文件>#<锚点>`），禁止 §章节号。
> **基线**：ROS1 参考实现已冻结只读，**不得删改，不得复制代码**（[ADR-0001](../adr/0001-greenfield-ros2-rewrite.md)）。

---

<a id="usage"></a>
## 0. 用法

1. 按 workstream 推进；每个 workstream 各有规格 `.trae/specs/<ws>/{spec,tasks,checklist}.md`（**现址**：[规格归档索引](specs/README.md#specs-index)）。
2. 卡片的"验收"必须**可命令化判定**；不通过的 workstream 不得进入其下游。
3. 完成一个 workstream，就在 [状态表](#status) 打勾。
4. 遇到约束问题，查契约真源对应锚点，**不改约束、改实现**。
5. Leader（DSH 高质量模型）主导、Worker（DSH 一般模型）实施的交接，按 [协作规则](../../.coordination/README.md#protocol)、[交接与复用](../../.coordination/README.md#auto-wake) 和 [当前交接](../../.coordination/CURRENT.md#current) 进行；交接单引用本入口及对应规格，不另立执行路线。

<a id="principles"></a>
## 1. 原则

- **单一项目根** `/home/chen/AGC`（colcon 根即项目根）。
- **全新重写**：旧树只读归档，仅作 W8 行为对照。
- **Walking Skeleton 先行**（[M0](#m0)）：先打通一条最小端到端闭环，再逐域加厚。
- **Nav2 吸收**：按 [ADR-0008](../adr/0008-nav2-paradigm-absorption-as-code-principle.md) 的吸收矩阵，在 W1–W6 **代码层**落地，每个 workstream spec 必须含"Nav2 吸收点"一节。
- **纯仿真优先**，为实机预留接口（[ADR-0009](../adr/0009-sim-first-with-hardware-hooks.md)）。

<a id="status"></a>
## 2. Workstream 总览与状态

| WS | 名称 | 前置 | 挂载硬约束 | 状态 |
|---|---|---|---|---|
| 环境 | P0 工具链（Jazzy/ros_gz/Nav2/PX4/uXRCE） | — | — | ✅ 已就绪（附录 B） |
| **W0** | 仓库与工程规范 | 环境 | C2 | ✅ |
| **W1** | 消息与接口（`agc_msgs`） | W0 | C2 | ✅ |
| **M0** | 最小端到端闭环（Walking Skeleton） | W0·W1·W2(最小)·W5(桩) | — | ✅ |
| **W2** | 仿真世界与模型 | W0 | C3·C7(场景层) | ✅ |
| **W3** | 空中链路 | W2 | C1·C10 | ✅ |
| **W4** | 感知与融合 | W2 | — | ✅ |
| **W5** | 地面导航与安全层 | W2·W4 | C6 | ✅ |
| **W6** | 任务与评估 | W5 | C4·C5·C7·C8·C9 | ✅ |
| **W7** | RL 平台 | W2-full·W4·W5·W6（已验收证据，[ADR-0069](../adr/0069-w7-entry-and-exit-definition.md)） | — | ✅ W7-b 已闭合（2026-10-24；W7-a ✅；W7-b **P1 v5 = `inconclusive`**（CI [+0.0281, +0.1328] 覆盖 MME 0.10；[ADR-0086](../adr/0086-decision-rule-three-state-ci-versus-mme.md) / [ADR-0071](../adr/0071-w7b-adjudication-record-and-pending-arms.md)(l)）；**P1 机制消融（2×2）已完成：收益主要来自"指向"，跟踪参考在静止目标下无收益且为负**（[ADR-0087](../adr/0087-p1-mechanism-ablation-and-p2-arm-b-diagnosis-scope.md)(f)）；P2 v3 = `falsified` → 保留 c2，且 B 负向已归因（重规划/窗口/干预/预测重尾，(d)）；P2 侧剩余消融显式范围裁定；W7-c `deferred`；W8 进行中（[spec](specs/w8-parity-freeze/spec.md)）；见 [ADR-0093](../adr/0093-w7b-exit-closure-and-prefix-provenance.md)） |
| **W8** | 对照与冻结 | W6·W7 | C1–C10（容差） | 进行中（W8-E1a 当前 gate `not_evaluable_as_specified`，测量 P1 重做见 [ADR-0098](../adr/0098-w8-determinism-probe-and-measurement-spec-change.md#redo)，测量 P2 已裁定（[ADR-0099](../adr/0099-w8-fixed-budget-mission-fco-measurement.md#metric)），P3 首轮阻塞，第二轮取证未验收，第三轮通用取证已审查、根因未定位；第 4 轮 runner 异常导致无效对照，第 5 轮部分修复未验收，第 6 轮部分修复仍未验收，第 7 轮部分修复未验收且真实 helper 越界，第 8/9 轮部分修复未验收，第 10 轮离线资源归属修复已验收，第 11/12 轮适配部分通过未验收，第 13 轮端口格式离线修复已验收，第 14 轮真实运行越界且入口未验收，第 15 轮配置/pin/入口 ABBA 部分通过，第 16/17 轮入口 owner 收口已验收、旧任务已结档；新四步验证恢复链 S1 第1轮取证已审查、四例无接收，第2轮离线分层诊断已验收，第3轮 T1 分层微观测已派发（[规格](specs/w8-validation-recovery/spec.md#round3)），工程验证继续阻塞（[范围](specs/w8-measurement-p3/spec.md#infra-diagnosis)），headless 未授权；W8-E1b 历史证据对照完成，平台冻结 `conditional`，`live_ros1_parity = not_established`；W8-E2 未预注册）· [spec](specs/w8-parity-freeze/spec.md) |

### 依赖图

```
W0 ─┬─> W1 ─────────┐
    │               ├─> M0 骨架闭环 ──> 逐域加厚
    └─> W2 ─┬───────┘
            ├─> W3 空中链路
            └─> W4 感知融合 ─┐
                             └─> W5 地面导航 ──> W6 任务评估 ──> W7 RL 平台（W7-a/W7-b 已闭合；W7-c deferred）──> W8 对照与冻结（进行中：E1a gate not_evaluable_as_specified；E1b conditional freeze）
```

> **当前范围**：W6 出口（[ADR-0016](../adr/0016-execution-scope-exit-w6.md)）已完成；W7 已闭合（W7-c `deferred`，单 worker）；W8 进行中（E1a gate `not_evaluable_as_specified`、E1b 平台冻结 `conditional`、E2 未预注册）。W5 的地面主控**维持 [ADR-0004](../adr/0004-rl-primary-controller-nav2-safety-layer.md)**，本次以 **RL 最小版**落地；研究主线见 [ADR-0014](../adr/0014-research-mainline-mobile-interception-system.md)。

---

<a id="workstreams"></a>
## 3. Workstream 卡片

### W0 · 仓库与工程规范
- **目标**：确定目录骨架、包边界、命名与产物规范、git 与 `.gitignore`。
- **产出**：目录骨架 + 规范文档 + git 初始化 + `.gitignore` + 旧树归档至 `reference/old_ros1/`。
- **非目标**：CI/CD 流水线（另立 workstream）。
- **验收**：`colcon list` 只列出预期包；`experiments/**/config/` 可入库而其余被忽略（[ADR-0007](../adr/0007-experiment-artifacts-convention.md)）。
- **Nav2 吸收点**：参数声明规范、接口分层约定。
- **spec**：`.trae/specs/w0-repo-and-conventions/`

### W1 · 消息与接口
- **目标**：`agc_msgs` 独立包 + 9 个 rosidl 消息，字段级对齐契约。
- **产出**：`agc_msgs`。
- **验收**：`ros2 interface show agc_msgs/msg/AgcTaskState` 与契约 [消息](../ROS2迁移交接文档.md#messages) **逐字段一致**。
- **Nav2 吸收点**：topic/service/**action** 职责划分。
- **spec**：`.trae/specs/w1-msgs/`

<a id="m0"></a>
### M0 · 最小端到端闭环（Walking Skeleton）
- **目标**：起世界 → 出 odom → 收任务门控 → 下发 `cmd_vel`（占位/直通策略）→ 落一条评估。
- **前置**：W0、W1、W2（最小）、W5（桩）。
- **产出**：一条可复现的 run。
- **验收**：一条 `ros2 launch` 起全链；`/agc/ground/cmd_vel` 有输出；产物落 `experiments/<campaign>/<run_id>/`。
- **意义**：闭环一旦存在，后续硬约束才有**可验证**的载体（[ADR-0006](../adr/0006-domain-workstream-organization.md)）。
- **spec**：`.trae/specs/m0-walking-skeleton/`

### W2 · 仿真世界与模型
- **目标**：`agc_world` + 车 / UAV 模型迁 GZ Sim；`ros_gz` 桥；传感器链路。地面车为**真实物理**驱动（[ADR-0010](../adr/0010-ground-drive-real-physics.md)）。**分段交付**：W2-min（世界 + 车 + target 被动模型 + 桥最小集）→ W2-full（传感器链路 / costmap 输入数据 / 世界打磨）→ W2-interception（目标可控化 + 地面拦截载荷模型）。**拦截相关**：`intruder_uav` 升级为**可脚本化 / 可控**模型、`agc_car` 增**拦截载荷**（捕获网面 + 干扰载荷）模型（供 W6 干扰注入与捕获裁决，[ADR-0015](../adr/0015-interception-scope-physical-capture-and-behavioral-jamming.md)、[ADR-0016](../adr/0016-execution-scope-exit-w6.md)）。
- **产出**：可加载的世界与模型、桥配置（W2-min 供 M0；W2-full 供 W4/W5）。
- **验收**：无头 / GUI 均可起；`/clock` 同步；点云话题有数据（QoS 见 [风险](#risks)）。
- **挂载**：C3（非无头验收）、C7（出生间距，场景层）。
- **Nav2 吸收点**：TF / costmap 输入约定（`OccupancyGrid`、`PointCloud2`）、sensor QoS。
- **spec**：`.trae/specs/w2-sim-world/`

### W3 · 空中链路
- **目标**：PX4 uXRCE-DDS 链路 + 共享 LQR 轨迹跟踪 + **对目标常开 standoff 跟踪（含自避障）**（[ADR-0005](../adr/0005-px4-link-uxrce-dds.md)、[ADR-0017](../adr/0017-air-ground-collaboration-loop.md)、[ADR-0018](../adr/0018-shared-control-layer-and-lqr-plugin.md)、[ADR-0019](../adr/0019-uav-trajectory-and-tracking-parameter-calibration.md)）；PX4 本体以 [toolchain 外部依赖](../adr/0012-px4-body-as-toolchain-dependency.md) 形态使用。
- **分段**：**W3-a** 链路打通（PX4 以 `PX4_GZ_STANDALONE` 挂 `agc_world` + 起飞 / 悬停 / Offboard 接管）→ **W3-b** 共享 LQR + 真八字（C1）→ **W3-c** 常开 standoff 跟踪 + 自避障（C10）。
- **产出**：`agc_control`（通用控制层）+ `agc_air` 飞行闭环；前置 **W2 打补丁**（PX4 系统插件 + 作业区放大）。
- **验收**：悬停稳定、Offboard 可切；C1 真八字恒速 `v=2.0`；C10 跟踪常开 / 安全间距 `8/15 m` / 新鲜度冻结 / 自保。
- **挂载**：C1（真八字恒速）、C10（**跟踪常开** / 安全间距 / 新鲜度冻结）。
- **Nav2 吸收点**：**lifecycle managed node**、pluginlib（`agc_control`）、QoS 标定。
- **spec**：`.trae/specs/w3-air-link/`

### W4 · 感知与融合
- **目标**：odom / gt / perception / fusion / map 适配节点。
- **产出**：各话题与频率。
- **验收**：各话题频率与契约口径一致（±容差）。
- **Nav2 吸收点**：**costmap 分层语义**（static/obstacle/inflation/voxel）、map_server 约定。
- **spec**：`.trae/specs/w4-perception-fusion/`

### W5 · 地面导航与安全层
- **目标**：`RL → cmd_vel → collision_monitor → /agc/ground/cmd_vel`（[ADR-0004](../adr/0004-rl-primary-controller-nav2-safety-layer.md)；本次为 **RL 最小版**）。
- **分段**：**W5-a** 安全层真化（`collision_monitor` 点云源 + costmap 组装 + C2 三档承载）→ **W5-b** RL 最小版（`agc_rl` 接口 + 推理节点接入唯一执行链）→ **W5-c** 离线对照基线（Nav2 planner/controller + `agc_control` LQR 切换）+ 全链回归。
- **前置补丁**：**W2 打补丁**（地面平台保形换装为差速 UGV + 实测顶速，[ADR-0021](../adr/0021-ground-safety-thresholds-and-platform-recalibration.md)）。
- **产出**：RL 主控链路 + Nav2 `collision_monitor` 安全层 + 离线对照基线接入。
- **验收**：全程仅 [唯一执行口](../ROS2迁移交接文档.md#execution-port) 一个；**无第二命令者**；安全层触发可复现。
- **挂载**：C6（安全滤波器真实逃逸能力）；C2（三档阈值行为承载，[ADR-0021](../adr/0021-ground-safety-thresholds-and-platform-recalibration.md)）。
- **说明**：车体为真实物理驱动（[ADR-0010](../adr/0010-ground-drive-real-physics.md)），C6 的"真实逃逸能力"据此判定。
- **Nav2 吸收点**：直接复用 `collision_monitor`；planner/controller 的 **plugin 抽象**（用于离线基线切换）；costmap 分层语义组装（承接 W4 遗留）。
- **spec**：`.trae/specs/w5-ground-nav-safety/`

### W6 · 任务与评估
- **目标**：`task_manager`、`agc_run_logger`、12 个场景、评估口径；修复已知竞态（契约 [不可回退教训](../ROS2迁移交接文档.md#lessons)）。**拦截裁决**（物理捕获判据 + 行为级干扰注入）与"捕获 / 干扰"**终态语义扩展**（[ADR-0015](../adr/0015-interception-scope-physical-capture-and-behavioral-jamming.md)），并消解契约 [终态语义](../ROS2迁移交接文档.md#terminal-semantics) 的旧口径。
- **产出**：状态机 + 日志 + 场景 + 评估脚本。
- **验收**：终态语义正确；报告含 `shield_infeasible_rate` 与 `reset_failure_rate`。
- **挂载**：C4（超时算失败）、C5（相位复位 t=0）、C7（出生净空 / 复位重试，[ADR-0023](../adr/0023-spawn-clearance-recalibration.md)）、C8（终态语义）、C9（报告指标）。
- **Nav2 吸收点**：**行为树抽象**（`task_manager` 候选 → **已决议**：自研 C++ 状态机**吸收其模式**，不引入 `bt_navigator`）、恢复行为模式。
- **前置 P**：W2-interception 回退（`intruder_uav` **PX4 化**，[ADR-0015](../adr/0015-interception-scope-physical-capture-and-behavioral-jamming.md) 修订）+ 可行性闸门（双 PX4 同世界 + mode 注入）。
- **已决**：`task_manager` 架构 = 自研确定性 C++ 状态机；拦截 = 物理捕获（发射式网，[ADR-0022](../adr/0022-launched-net-capture-mechanism.md)）+ 行为级干扰（[ADR-0015](../adr/0015-interception-scope-physical-capture-and-behavioral-jamming.md) 修订）。
- **spec**：`.trae/specs/w6-task-eval/`

### W7 · RL 平台（**后续**，不在本次出口）
- **目标**：策略、训练 / 评估流水线、论文产线。
- **前置**：W2-full · W4 · W5 · W6 —— **逐项以已验收 run 证据为准**（每项指向 `run_id` + 验收命题，[ADR-0069](../adr/0069-w7-entry-and-exit-definition.md)）。
- **分段**：**W7-a** 最小平台（入口前置证据 + obs / action 版本化 + train / eval 协议 + 种子分解 + 单 worker 可重放 + **规则基线可达性**）→ **W7-b** 科研路线（选可证伪命题，[ADR-0070](../adr/0070-w7b-research-propositions-and-rl-role-adjudication.md)）→ **W7-c** 扩容（多 worker 隔离）。
- **产出**：可复现的训练与评估。
- **验收（W7-a）**：可信实验平台 —— 同 seed 可复现；train / eval 协议与评估一致；**不含**算法 / 论文（属 W7-b）。
- **未决**：算法 / 环境 / 指标 / 论文方向 —— 在 W7 spec 内定夺（W7-b）。
- **进度（2026-10-19）**：**W7-a 已落地** —— T1–T5 + 横切核查完成；证据 `experiments/w7-rl/{20261019-w7-core-final, 20261019-w7-replay-0001, 20261019-w7-baseline-0001}`。**W7-b 进行中** —— 科研裁定 [ADR-0070](../adr/0070-w7b-research-propositions-and-rl-role-adjudication.md) + 规格 `.trae/specs/w7-rl-b/`：**入口前置 E1–E5 已落地并取证**；臂与消融**可运行子集已跑**（基线锚 / P2 两臂 / 消融·安全干预），**P1 协同臂待整链**、确证判定未执行 —— 裁定记录 [ADR-0071](../adr/0071-w7b-adjudication-record-and-pending-arms.md)。W7-c **未开始**。
  - **补充（2026-10-19 晚）**：整链（`backend:=full`）**步 1「评价可用」已落地** —— 空中控制权交接（`task_manager` 在悬停后调 `/agc/air/release_control`，甲-1）+ `px4_adapter` 姿态四元数字段序修复（[ADR-0072](../adr/0072-px4-attitude-quaternion-field-order-and-full-chain-observation-fix.md)）：full `s08` 同 run 达真实终态 `TRACKING_SUCCESS`、`visibility_rate=0.982`（`run_id w7-rl-b/20261019-w7-rl-b-224947-6509`）。**P1 两臂配对 / 判定仍未执行**；依赖 `/agc/air/odom` 姿态的旧空中证据**须重验**。
  - **补充（2026-10-20）**：W7-b **步 2–3 推进** —— 依次落地三处前置并各自留痕：臂公平性（非协同臂改固定航迹，[ADR-0073](../adr/0073-p1-arm-fairness-noncoop-fixed-trajectory.md)）、DV 口径（可见 / 火控机会率改**固定观测窗口** `window_fixed_v1`，[ADR-0074](../adr/0074-visibility-metric-fixed-observation-window.md)）、整链 infra 处置（**运行前清场** + infra 重试协议，[ADR-0075](../adr/0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md)：本机残留孤儿进程使 uXRCE 实体创建 > PX4 硬编码 1 s 预算）。随后 P1 两臂 **CRN 配对 N=20** 已跑（`run_id w7-rl-b/20261020-w7-rl-b-150408-8486`，40 episodes / 1.32 h / infra 0/40），判定 [ADR-0071](../adr/0071-w7b-adjudication-record-and-pending-arms.md)(h) 主 DV 成立（Δ`fire_control_opportunity_rate`=+0.2885、95% CI [+0.202, +0.375]、p=1e-06、n=20）。**但**该批次暴露 capture 场景终态语义缺陷（跟踪里程碑提前锁存 `TRACKING_SUCCESS`，捕获永不发生）→ 已由 [ADR-0076](../adr/0076-capture-scenario-tracking-milestone-not-terminal.md) 修正（`tracking_milestone_is_terminal`，仅 capture 场景）→ **旧批次数值不可作为最终判定**，须在新语义下重跑 N=20 后定论；协同臂为**显式 oracle 指向臂**（适用边界）。W7-c（多 worker）**未开始**；W8 **未开始**。
  - **补充（2026-10-21）**：**新终态语义下 P1 N=20 重跑完成并判定成立** —— 现行结论 `run_id w7-rl-b/20261021-w7-rl-b-175313-3256`（`backend:=full` / `s08` / seeds 0–19 / 40 episodes / 1.58 h / infra 终态 0/40 / 7 次 infra 重试 / **0 条事件拒收**）；判定产物 `metrics/p1_adjudication.json`，结论见 [ADR-0071](../adr/0071-w7b-adjudication-record-and-pending-arms.md)(h) 最终重跑子节：primary `fire_control_opportunity_rate` 均值配对差 **+0.2988**（95% CI [+0.149, +0.449]、p=5.1e-04、n=20）≥ MDE 0.10 → **成立**；secondary `min_clearance` 不显著（−0.1704、p=0.417，如实登记）。**过程留痕**：① 首个新语义批次 `20261021-w7-rl-b-104120-1456` 暴露启动双复位竞态（4 例共 **41 次 `CAPTURE_NET` 被静默拒收**）→ [ADR-0078](../adr/0078-capture-event-episode-identity-single-source.md) 修复；② 修复后批次暴露 B2 火控目标速度假噪声（静态目标被逐帧差分成 1–2 m/s，预测点偏 1–2.5 m）→ [ADR-0079](../adr/0079-b2-fire-control-target-motion-estimation.md) 修复（时间窗回归 + 静止阈值 + 发射解算门），本批仅剩 2 个非协同超时（固定航迹下几乎无开火机会，属臂行为）。旧批次 `150408` / `104120` / `133724` 数值不得引用。协同臂仍为**显式 oracle 指向臂**；成功率 20/20 vs 18/20 仅作画像。**另（B1 观测饥饿）**：诊断确认为空中 lifecycle 启动期 manager 卡死 + 节点 bond 在 configure 过早计时（`px4_adapter` 失效停机 → `no_pose` 全拒），已由 [ADR-0080](../adr/0080-air-lifecycle-startup-robustness.md) 修复（lifecycle 服务预热 + bond 改在 activate）并红-绿；**感知量程 12 m < 站距上限 15 m** 的几何盲区**已裁定保留为环境边界**（对两臂对称、已计入可见率；不修改参数、不重跑），批次产物 `metrics/perception_health.json` 自动报告 `rmax/no_pose/fov` 占比。W7-b 剩余（协同观测 / 目标预测消融）与 W7-c、W8 **未开始**。
  - **补充（2026-10-22）**：**P2 v2 判定审计 → confounded；v3 已执行并判定：证伪（保留 c2）** —— 审计发现两处缺陷：①**臂信息不等价**：臂 A 的 c2 只订 `/agc/ground/goal`，s08 `goal_follow_target=false` 且固定目标 = 目标真值 `(4.5,3.0)`，臂 B 订 `/agc/targets`（感知）→ A 为 oracle 目标臂，“只差命令源”不成立；②**primary DV 终态后污染**：`window_fixed_v1` 的 60 s 窗包含终态后停泊，v2 约 **97%（A）/100%（B）** 的机会拍在终态之后。修复已落地（[ADR-0083](../adr/0083-w7b-p2-arm-information-equivalence-and-active-window-fco.md)）：两臂 `goal_follow_target=true` 同源感知目标、primary 改 **active-window FCO**（`episode_window_metrics`）、B 高层加目标低通 + 前向限幅（冒烟发现单回合 **175 次**目标身份变重规划）；预注册升 **v3**（MDE 0.10），v2 run `20261022-w7-rl-b-112833-1155` 标记 `invalidated_runs`。**v3 结果**：run `20261022-w7-rl-b-v3-n20r`（40 episodes / 2.39 h / 终态 infra 0/40）；primary active FCO **Δ=−0.0561**（95% CI [−0.097, −0.015]、p=0.010、n=20），未达 MDE 0.10 且方向为负 → **P2 证伪、保留 c2**；A 19/20、B 17/20（B seed1/5/15 timeout；seed5 `min_clearance=0.685 m`）；legacy fixed 窗 Δ=−0.400（仅描述，印证终态后污染）。现行结论见 [ADR-0071](../adr/0071-w7b-adjudication-record-and-pending-arms.md)(j)。**P1 结论不变（v1）**，但同一固定窗口径的敏感性（active Δ=+0.056、p=0.098 vs fixed +0.299、p=0.0005）登记为 W8 前必须复核的风险。
  - **补充（2026-10-23）**：**P1 v4 窗口口径复核已执行并判定：证伪** —— 预注册升 v4（[ADR-0084](../adr/0084-w7b-p1-active-window-dv-recheck.md)）：primary 由 `window_fixed_v1` 的 `fire_control_opportunity_rate` 改为 **active-window 的 `fire_control_opportunity_rate_active`**（`GROUND_APPROACH → 终态`，不含终态后停泊）；N=20 / α=0.05 / MDE=0.10 / 臂定义**不变**；v1 结论保留为历史、不回溯改写。承载 run `w7-rl-b/20261023-w7-rl-b-p1v4-n20`（40 episodes / 墙钟 1.73 h / 终态 infra 0/40 / 9 次 infra 重试）：primary **Δ=+0.0278**（95% CI [−0.0113, +0.0669]、p=0.153、n=20）→ **未达 MDE 0.10 且不显著 → 证伪**（**现行 P1 结论**）；legacy fixed Δ=+0.2812（p=1.8e-04）仅作描述，同向印证终态后停泊污染；协同 18/20、非协同 19/20（仅作画像）。结论见 [ADR-0071](../adr/0071-w7b-adjudication-record-and-pending-arms.md)(k)。**边界**：自变量是"观测指向 + 跟踪参考"的组合，协同臂为**显式 oracle 指向臂**——不得表述为"协同策略无效"。**未决**：是否以新决策终点（任务成功率 / 捕获时长 / 首次火控机会时间）另立预注册 v5；P2 消融与 W7-c 仍未执行。
  - **补充（2026-10-23 续）**：**P1 v5 机制激活重测已执行** —— 按 [ADR-0084](../adr/0084-w7b-p1-active-window-dv-recheck.md)(f) 的机制边界（s08 不足以激活 α：包络占用由固定目标决定、可见仅差 6 pt），以 [ADR-0085](../adr/0085-w7b-p1-mechanism-activating-scenario-pilot.md) **先定规则**的两轮 pilot（候选 s13 linear / s14 linear+fov / **s15 static+fov** / s16 static+dropout；产物 `w7-rl-b/20261023-w7b-pilot-s13/s14/s15/s16`）选场景：linear 候选因 **`rmax`（>12 m 量程）超限 + C10 hold 自锁**退化，dropout 候选 active 可见率饱和 ⇒ 均排除；**选中 s15**（static + 窄视场 30°/20°）。预注册 v5 先行写定（`scene=s15`、primary=active-window FCO、N=20 / α=0.05），随后 run `w7-rl-b/20261023-w7-rl-b-p1v5-n20`（40 episodes / 终态 infra 1 / 14 次 infra 重试）：primary **Δ=+0.0804**（95% CI [+0.0281, +0.1328]、p=0.0046、n=20）；机制激活实测 active 可见率 **协同 0.473 vs 非协同 0.066（Δ≈41 pt）**；协同 15/20、非协同 13/20。**新增场景** `s13/s14/s15/s16` 已登记于 [`scenarios.yaml`](../../src/agc_task/config/scenarios.yaml)（capture 语义不变量由 `test_scene_config_invariants.py` 守护）。结论读法见下条（三态修正）。
  - **补充（2026-10-23 再续）**：**判据语义修正（[ADR-0086](../adr/0086-decision-rule-three-state-ci-versus-mme.md)）：MME 与规划量分列 + 三态判定** —— 审计发现旧口径把同一 `MDE=0.10` 同时当**样本量规划参数**与**"实测均值必须达到"的判定门槛**；v5 的 CI [+0.0281, +0.1328] **覆盖** 0.10 ⇒ 旧标签"证伪"语义过强。修正后：`decision.*.minimum_meaningful_effect`（MME，决策门槛，显式裁定）与 `statistics.*.planning`（规划可检测效应 = `(z_{1−α/2}+z_{1−power})·σ/√n`，v5 口径 ≈0.070）**分列**；判定改**三态**（CI95 下限 > MME → `supported`；上限 < MME → `falsified`；覆盖 → `inconclusive`）。**据此的现行读法（历史 verdict 字段不改写）**：**P1 v5 = `inconclusive`（未通过门槛）**——既未支持"收益 ≥ 10 pt"，也未排除它；**P1 v4（s08）= `falsified`**（CI 上限 0.067 < 0.10，可排除达到门槛的效应）；**P2 v3 = `falsified` 不变**（其 CI [−0.097, −0.015] 完全低于 0.10）。**决断所需的样本量**（σ≈0.112、MME=0.10）：余量 0.03 → N≈109、余量 0.02 → N≈246（每对 ≈2 episodes ≈3–6 min ⇒ N≈100 量级 ≈5–10 h）。复算：`python3 scripts/w7b_p1_adjudicate.py --run-id 20261023-w7-rl-b-p1v5-n20`。**未决**：是否以 v7（同场景、加大 N；须满足 [ADR-0088](../adr/0088-mme-change-governance-independent-justification-and-seed-isolation.md)：独立工程依据 + 新种子 seeds ≥20 + 按实际规则重算 N）取得决断性结论；P2 消融与 W7-c 未执行。
  - **补充（2026-10-24）**：**P1 机制消融（2×2）N=20 完成 + P2 臂 B 负向诊断完成**（[ADR-0087](../adr/0087-p1-mechanism-ablation-and-p2-arm-b-diagnosis-scope.md)）—— P1 新增 `p1_point_only`（target+off）与 `p1_track_only`（velocity+on），四 cell 单批 run `w7-rl-b/20261023-w7-rl-b-p1abl-n20`（80 episodes / 墙钟 5.0 h / 45 次 infra 重试）。**结果（估计型，不改 verdict）**：**指向主效应显著为正**（tracking=on：+0.0658、p=0.0019；tracking=off：+0.1347、p=5.6e-05）；**跟踪主效应在 pointing=target 时为负**（①−③ = −0.0719、p=0.011）；交互 −0.0667；`p1_point_only` 的 active FCO 0.155 ≈ `p1_coop` 0.083 的 1.9×，但成功率 **15/20 vs 19/20**（权衡，未 adjudicate）；`p1_track_only` 如预登记退化（4/20 捕获 + 2 infra ACTIVE，C10 hold 自锁再实证）。⇒ **收益主要来自"指向"**；**限 s15 静止目标**，不得外推到移动目标；"跟踪对运动目标的价值"**未测**。产物 `metrics/p1_ablation.{json,md}`（[`scripts/w7b_p1_ablation.py`](../../scripts/w7b_p1_ablation.py)）。P2 诊断（[`scripts/w7b_p2_arm_b_diagnose.py`](../../scripts/w7b_p2_arm_b_diagnose.py) → `20261022-w7-rl-b-v3-n20r/metrics/p2_arm_b_diagnosis.{json,md}`）：B 负向可归因——重规划 **23.7 次/回合**（A 为 0）、active 窗口 **2.5×**、安全层干预 **3.2×**、可见拍中包络占比腰斩（0.059 vs 0.114）、**26%** 发射的 `pred` 偏差 > 网半径（最大 8.7 m）；`min_clearance` 两臂相当（4.64 vs 4.73 m）。**v3 判定不改写**；是否改进高层待裁（先判"重规划振荡是否属实现缺陷"）。**不进在线 RL**（[ADR-0082](../adr/0082-w7b-p2-arm-b-rule-high-level-first.md)(d) 触发条件未满足）。
  - **补充（2026-10-24 续）**：**核实子阶段完成 —— 判据勘误、口径标注、P2 审计、P1 复现与 v7 决策门**（spec [`verify-w7b-p1-p2-before-v7`](specs/verify-w7b-p1-p2-before-v7/spec.md)；决策 [ADR-0090](../adr/0090-w7b-post-audit-v7-gate-and-implementation-fixes.md)）。① **判据勘误**：[ADR-0086](../adr/0086-decision-rule-three-state-ci-versus-mme.md)(b) 的等价表述改为「95% 双侧 CI 下限 > MME ⇔ 对 MME 的单侧 p < α/2（α=0.05 时 0.025）」，`w7b_prereg.yaml` 注释同步；CI 三态规则、MME=0.10、N=20、α / power 与历史 verdict **均不变**。② **消融口径**：[ADR-0087](../adr/0087-p1-mechanism-ablation-and-p2-arm-b-diagnosis-scope.md)(a)(f) 的 DV 标注为「**真实过程 FCO**」（失败回合保留真实值、缺测配对剔除），并注明**不等于** v5 的失败置零判定口径；既有数值、CI、p、n 逐项不变，**不**重跑分析。③ **P2 重规划审计** `20261024-w7-rl-b-p2-replan-audit`：受控台架确认「目标身份变」实际是位移阈值（非 `target_id`，非缺陷），「地图变化」的 `cost >= 253` 会把未知 255 / inflation 253 当硬障碍（C5 4 s 内 14 次伪触发）→ [ADR-0089](../adr/0089-map-signature-lethal-only-for-replan-trigger.md) 修为 `cost == 254`：C5 **14→0**、C4 真实增障仍 **1** 次、W6 R-041 回归 PASS；全链 `20261024-w7-rl-b-p2-predchain-retry2` 剩余地图触发 30 次全部 `hard_cells 7–14`（`static_layer=0`、`obstacle_layer=136`、`voxel_layer=320`），来自**移动目标 obstacle / voxel lethal marking 迁移**，属 ADR-0089 明确不消除的**另一原因**。④ **P2 预测链**：v3 的 8.7 m 离群中目标估计至少占 **7.241 m**（非高层 lead / 火控提前量）；retry2（B 臂 3 seeds）**3/3 捕获**、6 发 `pred` 误差均值 **0.221 m**、>0.5 m **0/6**、8.7 m **未复现**——仅 3 seeds，**不推翻 v3**；同时发现**火控状态机时序缺陷**（`step()` 的在飞分支前提前返回 ⇒ `flight > 3 s`、`miss_dist` 最大 5007 m、落地判定延迟），须独立 ADR + 回归修复。⑤ **P1 五失败复现核对**：`p1_point_only` 的 5 个超时 seeds（1/4/8/10/18）在 `20261024-w7-rl-b-p1fail-smoke` / `-diag` **未复现**（seed8 冒烟捕获；1/4/10 诊断捕获；18 infra 耗尽）；同类盲 / 低高度失败反而出现在协同臂 ⇒ 指向运行期靶机 / 几何随机性或 infra，**不是**「仅指向」的稳定臂属性（`20261023-w7-rl-b-p1abl-n20/metrics/p1_point_only_failures.{json,md}`）。⑥ **v7 决策**：**不注册 v7**——P1 维持 `inconclusive`、P2 v3 维持 `falsified` 并保留 c2；无独立工程理由降低 MME、无预先定义的任务成功率保障，不得仅为消除 `inconclusive` 立项；修复前不注册新的 P2 确证 run；**不进在线 RL**（[ADR-0090](../adr/0090-w7b-post-audit-v7-gate-and-implementation-fixes.md)）。⑦ **证据归档**（[ADR-0064](../adr/0064-evidence-immutable-archive-and-intake-manifest.md)）：`p1abl-n20`、`v3-n20r`、`p1v5-n20`、`p2-replan-audit`、`p2-predchain-retry2`、`p1fail-smoke`、`p1fail-diag` 及 infra 失败 run `p2-predchain` / `-r2` / `-retry`，产物落 `experiments/_archive/w7-rl-b/<run_id>.tar`（manifest / `.sha256` / `.retrieval.json`）。本补充**不改**既有状态结论、**无新 verdict**。
  - **补充（2026-10-24 闭合）**：**W7-b 已闭合（[ADR-0093](../adr/0093-w7b-exit-closure-and-prefix-provenance.md)）** —— ① **火控在飞生命周期修复**（[ADR-0091](../adr/0091-fire-control-inflight-lifecycle-decoupling.md)）：`step()` 在飞优先、目标无效不判命中但照常落地 / 超时结算、`SHOT_ABORTED`（episode_reset / clock_regression）、`model_id=net_ballistic_frame_v2`；13 项确定性 gtest + 节点级 A–F 全过；lightweight `s08` / `s15 seed5` 的 GUI + headless E2 全部 shot 闭合、`flight` 在 1.30 s 级、无 5007 m `miss_dist`。整链小批（P1 s15 seed5 / P2 B s08 seeds 0–2）受 uXRCE `create entities failed: participant: 255`（agent participant 创建 1.5–1.9 s > PX4 1 s 预算）阻塞，**infra 单列**（`20261024-w7-rl-b-firectl-fullchain-infra`），待环境恢复补跑。② **移动目标地图触发独立处置**（[ADR-0092](../adr/0092-moving-target-costmap-marking-and-replan-policy.md)）：地图签名只计 static 层；C7 动态 marking 4→0、C8 真实静态增障 4→1、C1–C6 不变、R-041 PASS。③ **出口闭合**：P1 v5 = `inconclusive`、P2 v3 = `falsified` / 保留 c2、P2 v2 = `confounded`，原文保留；全部确证 / 消融 / 诊断 run 标注 **pre-fix**（火控 ADR-0091；P2 v3 亦早于 ADR-0089）；P2 侧协同观测 / 目标预测消融**显式范围裁定**不纳入 W7-b 出口（不能改变 v3 verdict / 属新假设 / 待 W8 或新预注册）。**v7 未注册；在线 RL 未进入；W7-c / W8 未开始。**
  - **补充（2026-10-24 整链 infra 恢复）**：**uXRCE participant 创建长尾已修复**（[ADR-0094](../adr/0094-uxrce-participant-warmup-and-px4-stagger.md)）—— 慢阶段 = agent 侧 DDS participant 创建（own 1.28–3.09 s）；最小链 80 ms、20 节点 DDS 负载复现 4.86 s；处置 = **own 25 s / intruder 35 s 错峰** + `backend=full` 的 `/agc/air/odom` 就绪门；sacrificial warmup 保留为可选、默认关闭（A4 no-warmup 5/5 证明不需要）。验收：A4 no-warmup 5 连（own 694–704 ms、intruder 742–750 ms）+ A5b warmup 5 连（own 640–752 ms）+ A7 最终默认 2 连（own 701 ms、intruder 737–751 ms），均 `--infra-retries 0`、无 `create entities failed`；4/5 + 4/5 + 2/2 `INTERCEPT_CONFIRMED`，各 1/5 `MISSION_FAILED(TIMEOUT)`（mission 终态，非 infra）；`toolchain_pin_check.py` 25 PASS/0 FAIL。**P1/P2 verdict 不变**；修复后小批补跑与 W7-c 准入见 spec `restore-fullchain-infra-and-w7c-admission`。
  - **补充（2026-10-24 修复后小批 B）**：P1 `s15` `p1_coop` seed5 + P2 `s08` `p2_rl_high` seeds0–2 + GUI，全部 infra 0；6/6 shot 命中、`flight` 0.496–1.000 s、事件 `ep=2` / `shot=2-1`、地图触发 0、P2 周期规划 24/12 次。P1 GUI 首跑 `MISSION_FAILED(TIMEOUT)`（mission 终态，非 infra），同参数重跑 `-r2` 达 `INTERCEPT_CONFIRMED`。报告 `experiments/w7-rl-b/20261024-w7-rl-b-b-p2-s08-s012-headless/metrics/fix_verification.md`；**P1/P2 verdict 不变**。
  - **补充（2026-10-25 W7-c 准入）**：C1 串行重放 3/3 终态 `INTERCEPT_CONFIRMED`（射击数 1–2，属物理边界）；[ADR-0077](../adr/0077-w7c-multi-worker-isolation.md) 定稿 rootless netns + private `/tmp` + UDPv4 + `AGC_WORKER_ID` + `run_id_override`。C4 两 worker 试验（`20261025-w7-rl-b-c4-trial3`）：双方 `INTERCEPT_CONFIRMED`、infra 0、事件 `ep=2`、隔离 / PX4 lock / run_id 均正常；但 worker 0 `vis_rate=0.2292` 低于 C1 串行包络下界 `0.5208` → **DV 未通过**。按 ADR-0077 **deferred，保留单 worker**；W7-c 批跑未启动，W8 未开始。
  - **补充（2026-10-25 单 worker 重复性诊断与隔离）**：新增 [ADR-0095](../adr/0095-w7c-admission-metric-and-worker-run-dir-isolation.md)，准入 primary 改用 **active-window FCO**（`episode_window_metrics`），legacy 固定窗仅作描述；C4 的“不准入 / 保留单 worker”记录保留，不回溯改判（legacy `vis_rate=0.2292` 与 active 口径不可比）。预声明分析计划 `src/agc_rl/config/w7c_admission_plan.yaml`（sha256 `9d7000…d710`）在任何对照 run 前冻结。PX4 可写运行目录隔离已落地：`px4_run_root` + 每实例 `-w` + 私有 `etc`（锁脚本 `AGC_PX4_ETC_DIR`）；smoke `20261025-w7-rl-b-smoke-isolation` → `INTERCEPT_CONFIRMED`、infra 0、共享 build 零写入、私有 `instance_0/1` 各有 `dataman` / `parameters*.bson` / `.ulg`。A/B 交替系列 `20261025-w7-rl-b-repeat-ab`：A 3/3 `INTERCEPT_CONFIRMED`；B1/B2 `INTERCEPT_CONFIRMED`、B3 **`INFRA_FAILURE`（`cmd_vel_loopback_missing`，ground lifecycle 未 activate）**；B 的 3 次共享 build 均零写入；B1/B2 active 窗口 / active 可见率在 A 范围内，A/B 门因 B3 infra（1 > A 0）与终态类别不一致 **未通过**。按预声明计划**不启动 P 两 worker 重试，显式保留单 worker**；W7-c 仍 `deferred`，W8 未开始。诊断报告 `experiments/w7-rl-b/20261025-w7-rl-b-repeat-ab-diagnosis/metrics/worker_repeatability.md`；GUI/headless 复核 `20261025-w7-rl-b-gui-headless-recheck/metrics/gui_headless.md` 结论为**等价未建立 / 证据不足**；**P1/P2 verdict 不变**。

### W8 · 对照与冻结（进行中：W8-E1 模式等价阶段）

- **验证恢复第23轮审查 / 第24轮派工（2026-10-28，Leader接管）**：原Worker因限流连续中断，Leader接管执行。A首次0 participant路径错误后按协议修复；修复A运行但XSD通过的log profile触发Fast DDS运行时XMLPARSER Error，故无discovery日志证据。B address-only `ROS_STATIC_PEERS=127.0.0.1`有效阴性，后起方仍0/0/0；port==0消费语义未完全闭合。58文件封存、tar SHA `748ad620…`、43732项基线漂移0。第24轮必须由新Worker先修复日志机制/闭合port语义，T0不通过不跑T1；通过后只做一个pub-first日志观测，不重复无信息样本。S2/S3/S4/gate/headless/科研不变。

- **验证恢复第22轮审查 / 第23轮派工（2026-10-28，Leader）**：第22轮A sub-first与B pub-first延长均valid，两顺序各n≥2；后起sub在完整25.38s窗口内一次都未看到先起pub，慢发现在≤25s尺度排除。端口已按双endpoint fsync闸门双PID双时点采集（p0=7410/7411、p1=7412/7413、无7400、inode不变），端口绑定层无不对称；rcl→rmw交接点定位到`rmw_discovery_options_t`。55文件封存与43671项基线复核通过。仅派[第23轮发现通告机制判别](specs/w8-validation-recovery/spec.md#round23)：T0定位discovery日志启用机制与ROS_STATIC_PEERS语义，T1两例均pub-first——A仅加discovery日志观测通告发出/收到/拒绝，B仅给后起方显式initial peer指向先起方metatraffic unicast；判读区分发送层/路径接收层/处理层与注入后可发现/仍不可发现，诊断条件下恢复不得称工程恢复。S2/S3/S4/gate/headless/科研不变。

- **验证恢复第21轮审查 / 第22轮派工（2026-10-28，Leader）**：第21轮A pub-first与B sub-first均valid，后启动参与者在完整8.002s窗口中看不到先启动参与者，形态随启动顺序而非角色翻转；第20轮pub-first同结果使该顺序n=2。端口T0因快照早于后起endpoint_created 543ms而不完整，不能支持方向结论；55文件封存与43610项基线复核通过。仅派[第22轮sub-first重复与延长窗口发现判别](specs/w8-validation-recovery/spec.md#round22)：A sub-first同窗重复，B pub-first将后起sub窗口延长约25s，双endpoint建立后补采双PID端口；若延长仍单向且两顺序n≥2，第23轮再授权发现通告/locator诊断。本轮不改传输配置。S2/S3/S4/gate/headless/科研不变。

- **验证恢复第20轮审查 / 第21轮派工（2026-10-28，Leader）**：第20轮修复回收锚定后，当前boot/domain0/LOCALHOST/default下rclpy pub-first完整窗口正式复现历史单向形态：pub侧graph_sub=1、matched=1，sub侧8.01s全程graph_pub=0、matched=0、heard=0；40文件封存与43564项基线复核通过。单侧结果支持发现通告方向分支，但不是根因、不是UDPv4/SHM结论。仅派[第21轮单向发现形态稳定性与方向性对照](specs/w8-validation-recovery/spec.md#round21)，A重复pub-first、B翻转sub-first，T1两次/45min，并做发现端口T0观测与Fast DDS LOCALHOST机制离线研究；本轮不改传输配置。S2/S3/S4/gate/headless/科研不变。

- **验证恢复第19轮审查 / 第20轮派工（2026-10-28，Leader）**：第19轮A（rclpy↔rclpy默认传输）因Worker驱动回收竞态invalid——driver按spawn计时而probe按自身启动计时，170.5ms source偏差使SIGINT打在spin窗口内、result未写；B/C按门未执行，无UDPv4/数据面结论。非权威partial观测显示pub侧matched=1、sub侧7.42s全0，属历史单向形态但窗口截断不作发现。38文件封存与43520项基线复核通过。仅派[第20轮修复回收竞态并重做rclpy跨进程基线](specs/w8-validation-recovery/spec.md#round20)，离线守卫通过后重做A，T1两次/45min；UDPv4分支本轮不开放。S2/S3/S4/gate/headless/科研不变。

- **验证恢复第18轮审查 / 第19轮派工（2026-10-28，Leader）**：当前boot/domain0/LOCALHOST的stock↔rclpy两方向均graph/endpoint可见、matched=1持续但零送达；C0同进程heard=59，类型hash/QoS兼容，断点下移至跨进程数据面/回调层。66文件封存与43448项基线复核通过；maps早采集、C0两次失败尝试和派生计数缺陷均披露并不改判。仅派 [第19轮跨进程数据面与UDPv4单变量对照](specs/w8-validation-recovery/spec.md#round19)，A同boot rclpy↔rclpy默认，B/C纯UDPv4-only条件对照，T1三次/45min；显式授权UDPv4变量，不称永久修复。S2/S3/S4/gate/headless/科研不变。

- **验证恢复第17轮审查 / 第18轮派工（2026-10-28，Leader）**：历史stock阳性在当前boot/domain37/11键/直接exec下未复现，A有效阴性，B/C按停止门跳过；35文件封存与43405项新增漂移复核通过。第16/17轮间确认发生boot切换，不作根因归因，不新增domain0/探针结论。仅派 [第18轮stock↔rclpy混合端点分层观测](specs/w8-validation-recovery/spec.md#round18)，C0控制后A/B两方向采集graph/matched/endpoint info/QoS/heard，T1三次/45min；S2/S3/S4/gate/headless/科研不变。

- **验证恢复第16轮审查 / 第17轮派工（2026-10-28，Leader）**：官方stock在domain0的clean/继承环境均零接收，OS loopback UDP双向5/5；1926保护项无漂移，原始证据与封存验收通过。“仅自写探针失败”及本轮输出缓冲/listener早退/UDP整体不通被排除，DDS内部断点未定位。历史stock阳性与本轮存在domain/env/进程树不可比，仅派 [第17轮历史阳性复现与受控domain对照](specs/w8-validation-recovery/spec.md#round17)，T1三次/45min；stock37失败即停止，成功后才同域检查既有探针。S2/S3/S4/gate/headless/科研不变。派工通知因原Worker属于另一父会话而失败，尚未领取；CURRENT为阻塞，待原父会话投递或用户裁定跨会话接续，不静默新建Worker。

- **验证恢复第14轮审查 / 第15轮派工（2026-10-28，Leader）**：A正负控制与endpoint门控双向顺序取证验收通过，1865保护项/56文件封存通过；旧单向形态仍在，通信未恢复，仅排除后方启动时先方endpoint尚未创建，不排除DDS发现时序。仅派 [第15轮同版本机制核查](specs/w8-validation-recovery/spec.md#round15)，T1=0、45min，给可区分候选不执行；S2/S3/S4/gate/headless/科研不变。

- **验证恢复第13轮审查 / 第14轮派工（2026-10-28，Leader）**：A因编排模板误带--second于argparse阶段退出，0participant、B/C未执行，无通信结论；1843保护项/16文件封存通过。第14轮仅修新根编排并以真实parser做零ROS参数预检，通过后同轮 [T1三次A/B/C](specs/w8-validation-recovery/spec.md#round14)，45min，无追加重跑；第12轮脚本与历史证据不改，S2/S3/S4/gate/headless/科研不变。

- **验证恢复第12轮审查 / 第13轮派工（2026-10-28，Leader）**：helper身份与回收定点修复验收通过，1562保护项/275文件封存核验通过，结束离线返工。仅派 [第13轮真实A/B/C](specs/w8-validation-recovery/spec.md#round13)，固定domain0/LOCALHOST，同进程正负控制后endpoint创建返回事件门控双向顺序，T1三次/45min；旧探针/证据只读，S2/S3/S4/gate/headless/科研不变。

- **验证恢复第11轮审查 / 第12轮返工（2026-10-28，Leader）**：1343保护项/213文件封存通过，多数边界修复通过；helper回收传缺失预期身份、信号函数跳过比对且回收记录丢弃仍未闭合。仅派 [第12轮helper身份收口](specs/w8-validation-recovery/spec.md#round12)，T1=0、45min，不扩其他诊断方向；真实A/B/C、S2/S3/S4未开放，gate/headless/科研不变。

- **验证恢复第10轮审查 / 第11轮返工（2026-10-28，Leader）**：1322保护项/15文件封存通过，有限等待框架与门控后存活复核部分通过；独立反例发现坏事件末行/必填字段缺失被接受、身份缺失仍发信号，另有helper截止与失败RC丢失缺口。仅派 [第11轮离线收口](specs/w8-validation-recovery/spec.md#round11)，T1=0、45min；真实A/B/C尚不放行，S2/S3/S4、gate/headless/科研结论不变。

- **验证恢复第9轮审查 / 第10轮返工（2026-10-28，Leader）**：A因新探针记录函数参数冲突invalid，B/C未执行，无通信结论；1299保护项和17文件封存独立核验通过。驱动存在无界wait、A回收证据缺口及门控后存活检查缺口，先派 [第10轮离线返工](specs/w8-validation-recovery/spec.md#round10)，T1=0、45min，新根修复不改旧证据；真实A/B/C另轮授权。S2/S3/S4、gate/headless/科研结论不变。

- **验证恢复第 8 轮审查 / 第 9 轮派工（2026-10-28，Leader；用户授权）**：第8轮证据与封存核验通过，domain0下旧形态仍复现，关闭继续替换domain/discovery/transport名称的配置分支。第9轮仅派 [独立endpoint标记探针](specs/w8-validation-recovery/spec.md#round9)：先同进程正负控制，再以endpoint创建API返回事件控制双向顺序；T1三次、45min。旧探针与历史证据不改，S2/S3/S4、gate、headless与科研结论不变。

- **验证恢复第 7 轮审查 / 第 8 轮派工（2026-10-28，Leader）**：第7轮独立复核通过，SUBNET+静态peer+UDPv4仍复现旧形态，排除LOCALHOST分支的单独解释。项目既有记录提示非0 domain服务数据面异常，第8轮仅派 [domain0 LOCALHOST对照](specs/w8-validation-recovery/spec.md#round8)，T1两次、45min；更正probe_start只是脚本启动标记而非participant就绪。S2/S3/S4、gate、headless与科研结论不变。

- **验证恢复第 6 轮审查 / 第 7 轮派工（2026-10-28，Leader）**：第6轮独立复核通过，G/H同形，LOCALHOST下UDPv4环境变量未显示改善，G再次复现启动方向不对称；结束该变量分支，不归因SHM。第7轮仅派 [SUBNET下UDPv4双向顺序对照](specs/w8-validation-recovery/spec.md#round7)，T1两次、45min，沿用同一Worker；S2/S3/S4、工程/设计、gate、headless与科研结论不变。

- **验证恢复第 5 轮审查 / 第 6 轮派工（2026-10-28，Leader）**：第 5 轮原始证据与封存通过，但 OFF 不消费静态 peer，仅验收为配置语义负对照，不评价 UDPv4 有效性；回执 1203/实际1204及17.137/18.530 s 的更正均保留。第 6 轮仅派 [LOCALHOST 下 UDPv4 单变量对照](specs/w8-validation-recovery/spec.md#round6)，T1 三次、45 min，沿用同一 Worker；S2/S3/S4、工程/设计、gate、headless 与科研结论不变。

- **验证恢复第 5 轮派工（2026-10-28，Leader）**：第 4 轮启动顺序诊断已由前 Leader 独立验收，通信根因/可用配置仍阻塞。本轮仅派 [UDPv4 单播发现对照](specs/w8-validation-recovery/spec.md#round5)，T1 两次、45 min，沿用同一任务链；S2/S3/S4 仍关闭，工程/设计、gate、headless 与科研结论不变。

- **验证恢复第二轮派工（2026-10-27，Codex）**：用户要求开展第二轮；第一轮取证有效但四组均无接收，通信未恢复。本轮仅同版本源码/官方资料核查及最小分层取证方案，45 min、0 ROS/构建/仿真，候选执行另轮派发；见 [规格](specs/w8-validation-recovery/spec.md#round2) 与 [派工](../../.coordination/archive/20261027-001-w8-validation-recovery/round-2/request.md#round2)。S2/S3/S4仍关闭，工程/设计阻塞，原gate/headless/科研结论不变。
- **验证恢复第二轮审查与第三轮派工（2026-10-27，Codex）**：第2轮离线诊断已独立验收。其静态证据确认匹配成功日志在本机 release 库中不可观测，并指出 LOCALHOST 分支使第一轮 A/B transport 变量很可能未生效；通信仍未恢复。第3轮仅授权 `T1: 2 次` 分层微观测（同进程正/负控制，条件跨进程对照），A 失败不得归因环境整体；见 [审查](../../.coordination/archive/20261027-001-w8-validation-recovery/round-2/review.md#round2-review)、[派工](../../.coordination/archive/20261027-001-w8-validation-recovery/round-3/request.md#round3)。S2/S3/S4仍关闭，工程/设计阻塞，原gate/headless/科研结论不变。

- **2026-10-27 新验证恢复链（Codex，来源：用户授权四点推进）**：前任务 R17 离线入口 owner 收口已验收并结档。按 [四步规格](specs/w8-validation-recovery/spec.md#stages) 依次进行官方通信、节点测量、两场 GUI、设计裁定；当前只派 S1 一次 ABBA/最多4例/0重试，后续逐轮验收派发。真实通信根因未知，原 P3 工程/设计未验收，gate/headless/科研 P1/P2 不变。当前交接只见 [CURRENT](../../.coordination/CURRENT.md#current)，不以离线152项通过代表真实通信恢复。

- **验证恢复第三轮审查与第四轮派工（2026-10-27，Codex）**：第3轮 T1 证据已独立验收。A 正/负控制有效；B 跨进程出现单向发现、单向 matched 与零消费，单次且存在启动顺序差，不能定位根因。第4轮只授权 pub-first/sub-first 两次 T1 顺序对照，固定其余配置；自动叫醒链已达4/4，DSH 若回报后被守卫拒绝须保留退出码4。见 [审查](../../.coordination/archive/20261027-001-w8-validation-recovery/round-3/review.md#round3-review)、[派工](../../.coordination/archive/20261027-001-w8-validation-recovery/round-4/request.md#round4)。S2/S3/S4仍关闭，工程/设计阻塞，原gate/headless/科研结论不变。

> **当前测量状态（2026-10-26）**：E1a gate = `not_evaluable_as_specified`，依据 [ADR-0098](../adr/0098-w8-determinism-probe-and-measurement-spec-change.md#decision)。测量 P1 独立重做见 [spec](specs/redo-w8-determinism-probe/spec.md#scope)；测量 P2 已完成（[ADR-0099](../adr/0099-w8-fixed-budget-mission-fco-measurement.md#metric)），P3 **部分执行、阻塞**（R2 节点级合成未通过、R3 GUI 未执行；见下条，[规格](specs/w8-measurement-p3/spec.md#scope)），headless 规模统计未授权。下列 2026-10-25 的 `not_evaluated` 为历史 pilot 状态。

- **测量 P3 第 14 轮审查 / 第 15 轮派工（2026-10-27）**：R14 未验收，实际授权入口越界启动 ROS；无 pytest/入口测试/guard/封存。A1 库名不符 invalid、后三例未执行，无通信结论，原件保留；实际约 4 s 提前收尾、DSH 更名基线变化及时间纠正见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round14-evidence)。下一步仅 [入口离线返工](specs/w8-measurement-p3/spec.md#round15-entry-rework)，修固定 canonical 库配置/默认 pin 来源/main owner 并补完整离线证据。0 ROS/通信/活动扫描/真实被测进程/helper/工程/仿真，不清共享资源；R13 验收保持。入口通过后另派真实通信；原工程/设计阻塞、通信根因未知，gate/headless/P1/P2 不变。
- **测量 P3 第 13 轮审查 / 第 14 轮派工（2026-10-27，历史）**：端口格式离线修复验收通过；独立坏表拒绝、官方内核合法布局、边界和 ABBA 核实，115 项原始测试、902 路径保护、21 文件归档及预算相符，见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round13-evidence)。下一步仅 [真实运行入口准备与离线验证](specs/w8-measurement-p3/spec.md#round14-entry)，0 ROS/通信/活动扫描/真实被测进程/helper/工程/仿真。入口通过后另派真实通信；原工程/设计阻塞、通信根因未知，gate/headless/P1/P2 不变。
- **测量 P3 第 12 轮审查 / 第 13 轮派工（2026-10-27，历史）**：94 项原始测试、878 路径保护、21 文件归档及预算核实；独立 pin、日志有效性/归属与最终来源修复通过，整轮未验收。残缺端口表头和非法地址/端口记录仍被放行，见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round12-evidence)。只派 [端口表格式收口](specs/w8-measurement-p3/spec.md#round13-udp-rework)，0 ROS/通信/真实扫描/helper/工程/仿真；R12 epoch 实差 828.480140249 s（旧回报多算 100 s），旧证据不改。通信根因未知，原工程/设计继续阻塞，gate/headless/P1/P2 不变。
- **测量 P3 第 11 轮审查 / 第 12 轮派工（2026-10-27，历史）**：79 项最终原始测试、851 路径保护、24 文件归档与预算核实；整轮未验收。独立反例发现空/无头端口表漏检、observed 自动作为 binary pin、损坏日志误计零接收、其他 case 日志误计成功，且最终来源元数据丢失，见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round11-evidence)。只派 [适配定点离线返工](specs/w8-measurement-p3/spec.md#round12-adapter-rework)，0 ROS/通信/真实 helper/工程/仿真；R10 owner 修复不重开，通信根因未知、原工程/设计继续阻塞，gate/headless/P1/P2 不变。
- **测量 P3 第 10 轮审查 / 第 11 轮派工（2026-10-27，历史）**：批返回/GC 后实际 owner 转交、恢复释放、独立清理与磁盘/回执一致性通过；55 项原始测试、835 路径保护及 13 文件归档核实，结束该项离线返工，见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round10-evidence)。随后仅派 [运行适配候选](specs/w8-measurement-p3/spec.md#round11-adapter)，CLI 拒绝真实运行，0 ROS/真实 helper/工程/仿真；通信根因未知，P3 工程/设计仍未验收，原 gate/headless/P1/P2 不变。
- **测量 P3 第 9 轮审查（2026-10-27）**：52 passed 原始日志/最终指纹、819 路径保护及 13 文件归档核验通过；四个最终读回 OSError/JSONDecodeError 的瞬时/持续失败收尾与 batch receipt 首次失败后的返回/盘面/回执 3/3/3 经独立检查成立。整轮未验收：run_case 有实际 owner，但 run_batch 丢弃 owner，持续 close 失败 handle 在批返回/GC 后不可达，见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round9-evidence)。只派 [第 10 轮](../../.coordination/archive/20261026-002-w8-measurement-p3/request.md#round10) 补该归属转交；0 ROS/真实 helper/工程/仿真，通信根因未知，工程阻塞、原 gate/headless/P1/P2 不变。
- **测量 P3 第 8 轮审查（2026-10-27）**：43 passed 原始日志/最终指纹、804 路径保护及 12 文件封存核验通过；端点记录、慢回执/真正慢读回超期拒绝、二进制/库身份、未知 variant 修复成立。整轮仍未验收：实际句柄归属丢失、读回异常遗留成功盘面、batch 回执首次失败后返回 3/磁盘及回执 0，见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round8-evidence)。只派 [第 9 轮](../../.coordination/archive/20261026-002-w8-measurement-p3/request.md#round9) 闭合这三项；0 ROS/真实 helper/工程/仿真，通信根因未知，工程阻塞、原 gate/headless/P1/P2 结论不变。
- **测量 P3 第 7 轮审查（2026-10-27）**：797 路径保护基线通过；两次测试共 4 次真实 helper（授权 0），最终删除 helper 后的 33 项未重跑、未封存。假进程复现端点记录缺失、case/batch 慢回执越限仍成功、预期二进制未绑定及未知 variant 磁盘非终态，详见 [独立审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round7-evidence)。整轮未验收，只派 [第 8 轮有限离线返工](../../.coordination/archive/20261026-002-w8-measurement-p3/request.md#round8)，不启动 ROS/真实 helper/工程/仿真；通信根因未知，工程继续阻塞、原 gate 与科研结论不变。
- **测量 P3 派工基线（2026-10-26，历史）**：先完成 [证据与版本边界裁定](../adr/0101-w8-seed-evidence-and-p3-execution-boundary.md#evidence)；派工时 PX4 binary pin 校验 24 PASS / 1 FAIL，seed 实施未验收。按 [P3 规格](specs/w8-measurement-p3/spec.md#scope) 先补前置构建/测试/版本取证，再实现记录器并作最多两次指定 GUI 工程验证，交回新设计草案；正式等价/新 pilot 未授权。派工前未启动新 run，gate 不变。本轮实际结果见下条。
- **测量 P2 完成（2026-10-26）**：指标口径见 [ADR-0099](../adr/0099-w8-fixed-budget-mission-fco-measurement.md#metric)；active FCO / 可见率降为过程指标，新固定预算指标尚需 P3 实现及验证。只读审计与科研 P2 v3 敏感性复算完成，历史 verdict 不变；未启动新 run。下一执行规格覆盖 [P3 待办](../adr/0099-w8-fixed-budget-mission-fco-measurement.md#next)。
- **测量 P1 重做完成（2026-10-26）**：同 s15 / p1_coop / seed5 / full / headless 串行 n=5，5/5 捕获、批次 infra=0；active FCO 极差 0.071010、窗口极差 33.484 s，观察到执行级散布。旧 5 次计数复算一致，补记遗漏的启动失败；计划 / 脚本 / 原始证据见 [ADR-0098](../adr/0098-w8-determinism-probe-and-measurement-spec-change.md#redo)。P1/P2 科研 verdict 保持不变。
- **测量 P3 部分执行（2026-10-26，阻塞）**：R1 完成——checker 扩展 `local_patches` 后 **41 PASS / 0 FAIL**，GPS 模块由补丁源码强制重编（exit 0）并显式更新 binary pin；生产 `SensorGpsSim` RNG harness 13 项、checker 正负例 7 项通过。R2 完成独立积分器 + `run_logger` 字段/区间账 + 手算 gtest 12/12 + 只读审核器 6/6。**节点级合成测试与 R3 GUI 未通过/未执行**：执行者怀疑 C++ DDS 发现问题，但 stock demo 对照缺原始命令/双端日志，根因尚未证实；已确认节点测试匹配数为 0，0 GUI attempts。R4 草案已交回 `draft_pending_codex_review`，按现行 40/模式、6 h/场景 cap 判 **`infeasible_as_specified`**（率类 co-primary n≈190–393/模式；FCO 单指标 δ=0.10 需 36/模式但等于 MME，依据待裁）。gate 仍 `not_evaluable_as_specified`，headless 未授权；P1/P2 verdict 不变。
- **目标**：新旧实现同场景、同种子各跑 N 次；出对比报告；ROS1 归档只读。
- **验收**：频率 / 数值差异在容差内；终态语义一致。
- **挂载**：C1–C10 全量容差复核。
- **spec**：`.trae/specs/w8-parity-freeze/`
- **进度（2026-10-25）**：W8 拆为 **W8-E1a**（GUI/headless 模式等价）、**W8-E1b**（ROS1 历史证据对照与条件平台冻结）、**W8-E2**（修复后 P1/P2 科研确证；另行预注册）。本阶段先做 E1a 的 **GUI/headless 等价 pilot**（[spec](specs/w8-parity-freeze/spec.md)、[ADR-0096](../adr/0096-w8-gui-headless-equivalence-design-bounds-and-gate.md)）：pilot 20 attempts 完成；**默认 GUI 被确认走 llvmpipe 软件渲染**（Ogre2 log；CPU 267–281% vs headless 22%），是已确认的性能混杂。随后按用户裁定执行 **GPU-GUI 修正 pilot**（plan v1.1，`MESA_LOADER_DRIVER_OVERRIDE=d3d12` + `GALLIUM_DRIVER=d3d12`，X11；20 attempts，GUI renderer 均为 `D3D12 (NVIDIA GeForce GTX 1050 Ti)`）：**RTF 与 headless 对齐**（P1 Δ≈−0.007、P2 Δ≈−0.008），但 active FCO / 率类散布大，**δ≤0.05、n≤40/模式下正式等价不可行**。gate = `not_evaluated`，headless 规模统计**未授权**，plan v2 **未冻结**。**项目默认 GUI 渲染后端已落地**：`gui_render_backend=auto`（WSL2 + `/dev/dxg` + X11 自动 D3D12；`d3d12` / `software` 可显式固定），经 auto / d3d12 / software 全链冒烟验证（auto 与 d3d12 → `gui_renderer=D3D12 (NVIDIA GeForce GTX 1050 Ti)`；software → `llvmpipe`）。**W8-E1b 历史证据对照已完成**：本机无 ROS1 Noetic 运行时、旧树无 bag / 日志 / metrics → 按评审 F-12 缩为历史证据对照；A 类 8 项可比事实冻结、B 类 8 项变更设计不可数值对照、C 类 4 项无证据；平台冻结 `conditional`，`live_ros1_parity = not_established`。报告：[`historical_parity.md`](../../experiments/w8-parity/20261025-w8-historical-parity/report/historical_parity.md)、[ADR-0097](../adr/0097-w8-historical-parity-and-conditional-platform-freeze.md)。下一步为范围裁定（配对臂差 / 模式作协变量、GUI 完成关键验证、扩大预算或换平台）。报告：[`gpu_renderer_diagnosis.md`](../../experiments/w8-parity/20261025-w8-gui-headless-pilot/metrics/gpu_renderer_diagnosis.md)、[`GPU-GUI status_summary.md`](../../experiments/w8-parity/20261025-w8-gui-gpu-pilot/metrics/status_summary.md)。P1/P2 pre-fix 结论不变（P1 v5 `inconclusive`、P2 v3 `falsified` / 保留 c2）；v7 未注册；在线 RL 未进入；W7-c 仍 `deferred`。

---

<a id="hard-constraint-mounting"></a>
## 4. 硬约束挂载表

> 约束原文见契约 [硬约束](../ROS2迁移交接文档.md#hard-constraints)（C1–C10 即其 1–10 条）。**原则：挂到"首次使其可验证"的 workstream，未到该 workstream 前不强行回归。**

| ID | 约束摘要 | 挂载点 |
|---|---|---|
| C1 | 真八字轨迹恒速 `v=2.0` | W3 |
| C2 | 距离阈值顺序（紧急<碰撞<安全） | W0·W1（顺序）· W5（行为承载，[ADR-0021](../adr/0021-ground-safety-thresholds-and-platform-recalibration.md)） |
| C3 | 实证/验收用非无头（GUI） | W0（规范）· W2（实测） |
| C4 | 超时算失败、显式完成才算成功 | W6 |
| C5 | 每 episode 相位复位 t=0 | W6 |
| C6 | 安全滤波器用真实逃逸能力 | W5 |
| C7 | 出生净空 ≥ 可标定下限（[ADR-0023](../adr/0023-spawn-clearance-recalibration.md)）；复位失败 ≤3 次不占预算 | W2（场景层）· W6 |
| C8 | 终态"抵近并持续跟踪"；`SUCCESS` 不得称"拦截完成" | W6 |
| C9 | 报告含 `shield_infeasible_rate`、`reset_failure_rate` | W6 |
| C10 | 无人机跟踪常开；安全间距；`ref_max_age_s=0.5`、`confidence≥0.5` 冻结 | W3 |

---

<a id="risks"></a>
## 5. 风险清单

| 级别 | 风险 | 缓解 |
|---|---|---|
| 高 | Nav2 仅 2D，空中不可用 | 已定"模式全覆盖·进程按域选用"（[ADR-0003](../adr/0003-nav2-pattern-complete-absorption.md)）；空中保留 LQR + 自研避障 |
| 高 | PX4 由 MAVROS 换 uXRCE-DDS，控制时序/模式切换需重调 | W3 单列里程碑，先打通悬停再接管 |
| 高 | Gazebo Classic → GZ Sim 语义差异大 | W2 先迁世界与模型，再补传感器 |
| 中 | uORB 语义（微秒时间戳、NED/FRD↔ENU、QoS）易错 | W3 内建语义映射测试 |
| 中 | QoS 默认不兼容（sensor/reliable） | 逐话题标定 profile |
| 中 | RL 主控与安全层耦合 | 安全层独立可测，接口先行 |
| 中 | 残留孤儿进程（桥 / tf）占 DDS + shm → uXRCE 实体创建超 PX4 的 1 s 预算 → 整链 infra | 运行前清场 + infra 重试（[ADR-0075](../adr/0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md)）；速查 [`conventions/整链排障速查.md`](../conventions/整链排障速查.md) |
| 中 | 时序 / executor 选择致频率数值漂移 | W8 同场景实跑对比，未验证不删旧实现 |
| 低 | `package.xml` / 依赖声明不完整 | `colcon` 逐包构建定位 |

---

<a id="rollback"></a>
## 6. 回滚与冻结策略

- 每 workstream 用 git 分支隔离（如 `ws/w0-conventions`），验收通过再合并。
- 旧树在 W8 通过前**保持可运行，不得删改**。
- 未完成新旧对比前，不得停用旧实现。
- 关键产物（对比报告、验收记录）落 `docs/`，实验产物落 `experiments/`（[ADR-0007](../adr/0007-experiment-artifacts-convention.md)）。

---

<a id="appendix-a"></a>
## 附录 A：ROS1 → ROS2 映射表

> **免责**：仅供迁移参考，**不作为代码或规范来源**；具体吸收点以各 workstream spec 的「Nav2 吸收点」节为准。

| ROS1 | ROS2 | 说明 |
|---|---|---|
| `catkin` / `catkin_tools` | `ament_cmake` / `ament_python` / colcon | `package.xml` 升 format 3 |
| `roscpp` | `rclcpp` | 逐节点改写 |
| `rospy` | `rclpy` | RL / 工具脚本 |
| `ros::init` / `NodeHandle` | `rclcpp::init` / `Node` | 生命周期与 executor 需重设 |
| `message_generation` / `message_runtime` | `rosidl_default_generators` / `rosidl_default_runtime` | `.msg`/`.srv` + rosidl |
| XML `.launch` + `rosparam` | `launch.py` + `parameters=[{}]` | 参数 YAML 结构重排 |
| `ros::param` / `getParam` | 声明式参数 `declare_parameter` | 需显式声明与类型 |
| `tf` | `tf2_ros` | 帧约定不变 |
| `/use_sim_time` | `use_sim_time` 参数 + `/clock` | ros_gz 桥接 |
| `gazebo_msgs` | `ros_gz_interfaces` / `ros_gz_sim` | `gt_adapter`、`scenario_reset` 重写 |
| `mavros_msgs` | `px4_msgs` + uXRCE-DDS | 空中链路重写 |
| Gazebo Classic 传感器插件 | gz-sim 插件 + `ros_gz_bridge` | Velodyne 链路重做 |
| `rosrun` / `roslaunch` | `ros2 run` / `ros2 launch` | 脚本全面改写 |
| `rostopic` / `rosservice` / `rosbag` | `ros2 topic` / `service` / `bag` | 评测与 CI 脚本改写 |

---

<a id="appendix-b"></a>
## 附录 B：环境就绪状态（已完成）

| 项 | 状态 |
|---|---|
| ROS 2 Jazzy + colcon + ros_gz | 已装；`gz sim` 为 Harmonic 8.15.0（来自 `ros_gz` vendor，**须先 `source /opt/ros/jazzy/setup.bash`**） |
| Nav2 | `ros-jazzy-nav2-bringup` 已装 |
| PX4-Autopilot | v1.15.4（含所需子模块），SITL 可执行文件已构建 |
| micro-XRCE-DDS Agent | **v2.4.3**（对系统 Fast DDS 2.14 构建，与 ROS 2 Jazzy 同源）；入口 `toolchain/bin/MicroXRCEAgent`。v2.4.2 已弃用（自建 DDS 2.11 跨版本不互通）。配方见 `toolchain/README.md` |
| `px4_msgs` | release/1.15，已在 `src/` 且通过 colcon build |
| 工作空间 | colcon 根 = `/home/chen/AGC`；`anti_drone_agc_workspace/`、`toolchain/` 各放 `COLCON_IGNORE` |

**环境坑（复现须知）**

1. 本机无需也无法单独 `apt install gz-harmonic`；Harmonic 随 `ros_gz` vendor 引入，**必须先 source** 否则 `libgz-sim8-gui.so.8` 找不到。
2. Micro-XRCE-DDS Agent 需 `-include` 一个 `fmt` 兼容头（fmt 9 移除了隐式 ostream formatter），并对系统 spdlog/fastcdr/fastrtps 构建、关闭 SuperBuild；**须用 v2.4.3**（v2.4.2 源码为 fastcdr 1.x camelCase API，无法对 fastcdr 2.x 编译）。
3. PX4 浅克隆若缺 tag，CMake 的 `git describe` 会失败 → 需 fetch 对应 tag。
4. 本机直连 GitHub 极慢（~25 KB/s）→ 外部仓库统一走 Gitee 镜像，pip 走清华源。

---

<a id="appendix-c"></a>
## 附录 C：目录速览

| 路径 | 作用 |
|---|---|
| `GLOSSARY.md` | 术语表 |
| `AGENTS.md` | 入口索引与铁律（每次会话自动加载） |
| `docs/ROS2迁移交接文档.md` | 契约真源（不变量） |
| `docs/ROS2迁移步骤.md` | 本 Runbook |
| `docs/adr/` | 架构决策记录 |
| `docs/conventions/` | 工程规范（W0 产出） |
| `.trae/specs/<ws>/` | per-workstream 规格三件套 |
| `.coordination/` | Leader / Worker 交接单、执行回报与审查记录；仅交接状态，不承载项目进度真源 |
| `src/` | ROS2 包（`agc_msgs`·`agc_sim`·`agc_control`·`agc_air`·`agc_perception`·`agc_ground`·`agc_task`·`agc_rl` + 第三方 `px4_msgs`） |
| `experiments/` | 实验产物唯一落点 |
| `reference/` | 归档旧树（只读） |
| `toolchain/` | 外部仓库 / 工具链 |

- **P3 阻塞复核（2026-10-26，Codex）**：首轮未验收，第二轮只做 [通用 ROS 2 通信取证](specs/w8-measurement-p3/spec.md#infra-diagnosis)，暂不恢复工程节点或仿真。已独立核对 tar 的 49 个文件及哈希；工作目录归档输出日志与 manifest 的打包后漂移另留侧车。审查与返工范围见 [交接审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round1-evidence)。实现、设计与原有 gate 不因这次基础设施诊断获验收或改变。

- **P3 第二轮复核（2026-10-26，Codex）**：五组官方 demo 通信观察与 43 文件最终归档完整性已核实；真实 listener 跨例残留、逐例超限，整轮未验收。第三轮仅做通用诊断进程管理/证据更正与至多一次官方 demo 对照，见 [规格](specs/w8-measurement-p3/spec.md#round3-correction) 与 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round2-evidence)；工程验证继续暂停，既有 gate 不变。

- **P3 第三轮复核（2026-10-26，Codex）**：官方 demo 真实端点 12.152 秒内回收、最终 12 文件归档核对通过，单次 C++ 对照仍未观察到接收。总诊断预算/封存覆盖和时钟推断限制见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round3-evidence)；停止追加运行，后续先离线形成区分假说的最小方案再派工。当前任务阻塞，未恢复项目工程验证，gate 不变。

- **P3 第四轮派工（2026-10-26，Codex）**：先完成成功/失败离线比较与精确版本官方做法核查，见 [分析](../../experiments/ros2-diagnostics/20261026-p3-r4/report/offline_comparison.md#analysis)；仅新授权官方 C++ talker/listener 的默认/UDPv4 ABBA 通用对照，见 [规格](specs/w8-measurement-p3/spec.md#round4-transport)。未运行、未验收；工程继续阻塞，原 gate 不变。

- **P3 第四轮复核 / 第五轮派工（2026-10-26，Codex）**：A1 runner 关闭已关闭日志抛异常，快照丢失，后 3 例未运行；19 文件封存核对通过，传输对照无效。见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round4-evidence)。仅派 [通用 runner 离线修复及故障注入](specs/w8-measurement-p3/spec.md#round5-offline-runner)，不授权 ROS demo 新 attempt，工程继续阻塞、gate 不变。

- **P3 第五轮复核 / 第六轮返工（2026-10-26，Codex）**：10 文件归档与 772 路径保护基线核对通过；18 passed 不能证明失败退出、统一期限、资源归属与实际校验闭合。helper 可核实 4 次、台账仅后两次，历史不补造。见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round5-evidence)。只派 [离线 runner 返工](specs/w8-measurement-p3/spec.md#round6-offline-rework)，0 ROS/通信/工程/仿真 attempts，工程继续阻塞、gate 不变。

- **P3 第六轮复核 / 第七轮返工（2026-10-26，Codex）**：785 路径与 9 文件归档通过；24 passed 未覆盖全部失败路径，假进程检查复现写盘/期限后启动、非零退出误成功、登记窗口及库路径缺口。helper 两轮共 4 次、仅后两次台账保留，不补造历史。见 [审查](../../.coordination/archive/20261026-002-w8-measurement-p3/review.md#round6-evidence)。只派 [定点离线返工](specs/w8-measurement-p3/spec.md#round7-offline-rework)，0 ROS/真实 helper/工程/仿真，原 gate 不变。
