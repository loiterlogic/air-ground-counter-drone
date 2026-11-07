<a id="top"></a>
# Nav2 范式吸收：模式全覆盖、按命令源裁剪

## Status

accepted（2026-11-02 由 ADR-0003 / 0008 / 0060 合并；结论未变）

## 背景

契约真源早期一句「Nav2 无 3D 规划器、无人机不适用」与另一句「Nav2 覆盖所有部分」互相冲突，导致「吸收 Nav2」在实践中退化成两种坏形态：要么只在文档里声明吸收、实际全是 ROS1 写法；要么用**空壳类数量 / 闲置进程数量**当吸收证据—— 例如 `command_source=rl` 时 composition 仍起 RL 根本不消费的独立 `nav2_costmap_2d` 进程。

结构评审据此提出两点校准：三条决策（进程层范围 / 代码层吸收 / 在线角色）的**适用关系不清**，以及**闲置进程充数**。本决策把「吸收」拆成**进程层**与**代码层**两个可验收的维度，并把验收口径从"数类名"改成"看行为"。

## 决策

### (a) 进程层范围：模式全覆盖、进程按域选用

**地面域**真跑 Nav2 本体组件；**空中域不引入 Nav2 运行时进程**，但重写时全面采纳其架构范式（costmap 分层语义、lifecycle 节点、planner / controller server 抽象、行为树），并保留 / 优化 LQR 与自研避障。唯一执行口 `/agc/ground/cmd_vel` 保持不变。

这条只回答**进程与架构层的范围**，不回答代码层怎么吸收（见 (b)），也不回答在线谁主控（见 (c)）。

### (b) 代码层吸收：吸收矩阵（交叉原则）

「吸收 Nav2」是**贯穿代码重构的交叉原则**：每个 workstream 重写时必须显式采纳 Nav2 对应范式，而非沿用 ROS1 写法，并在自身 spec 中列明"吸收点 + 依据"。

| workstream | 从 Nav2 吸收什么 |
|---|---|
|消息与接口 | 接口分层：topic / service / **action** 的职责划分（长时任务用 Action）；参数声明规范（`declare_parameter` + YAML 注入） |
|仿真世界与模型 | TF / 坐标系与 costmap 输入约定（`OccupancyGrid`、`PointCloud2` 语义）；sensor 类 QoS（best-effort）标定 |
|空中链路 | **lifecycle managed node**（configure / activate / deactivate / cleanup）；pluginlib 插件化；QoS 标定 |
|感知与融合 | **costmap_2d 分层语义**（static / obstacle / inflation / voxel）；map_server 与占据栅格约定 |
|地面导航与安全层 | 直接复用 `collision_monitor`（安全层）；planner / controller 的 **plugin 抽象**用于离线基线切换 |
|任务与评估 | **行为树抽象**（BehaviorTree.CPP / nav2_behavior_tree）作为 `task_manager` 候选；恢复行为（recovery）模式 |

每个 workstream 的 spec 必须含 **"Nav2 吸收点"** 一节；未采纳某范式须写明理由。评审口径不只看"能跑通"，还看"是否按矩阵吸收"。

### (c) 在线角色归地面主控决策，不在本条

(b) 矩阵行的「直接复用 `collision_monitor`」与「planner / controller 的 plugin 抽象用于**离线基线**切换」按[地面控制栈决策](0004-ground-control-rl-primary-and-nav2-safety.md#top)的**在线角色**执行：RL **直接出 `cmd_vel`** 为地面主控，Nav2 planner / controller 降为**离线对照基线**。

(a) 早期正文「地面域真跑 Nav2 本体（costmap、全局/局部 planner、controller、行为树）」中的**在线主控角色已由该决策取代**，该句**仅**在"进程层真跑 Nav2 组件"意义上继续适用。的「行为树」在线候选已决议为**自研确定性 C++ 状态机**（**吸收**其模式，**不引入** `bt_navigator`）。

### (d) 适用关系（三条决策的分工）

- **[ADR-0003](0003-nav2-paradigm-absorption.md#top)**（本篇）= **进程 / 架构层范围**：「模式全覆盖 · 进程按域选用」。
- **本篇 (b) 矩阵** = **代码层怎么吸收**：补充（amends）进程层结论的代码层落法，不改变其进程层结论。
- **在线角色**归 [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top) + 自研 FSM。
- 下游**只链接现行适用**的决策，不链接已被取代的口径。

### (e) 验收口径 = 已验证行为，不以类名 / 节点计数

按模式给**实际责任 / 运行必要性 / 失败验收**，**不以**类名 / 节点计数验收。**保留** Nav2 `collision_monitor`（安全层）与离线基线（`ground_baseline`）组件。

### (f) 按 `command_source` 只开所需进程

`rl` 主控**不消费** costmap（`inference_node.py` 仅订阅 odom / scan / goal / state；`interface.py` 的 obs = 扇区（scan）+ 位姿 + 距目标 + 上一动作，**无** costmap）→ `rl` 下**不**起独立 `nav2_costmap_2d` 进程；`baseline` 由 `ground_baseline` **自持**内建 `Costmap2DROS`（同一 `config/costmap.yaml` 参数源），本就不起独立进程。安全层与唯一执行口中继**不受影响**。

运行拓扑按**命令源**如实裁剪：

- `rl`：TF + `scan_self_filter` + `collision_monitor` + `ground_drive_relay` + RL 推理；
- `baseline`：TF + `scan_self_filter` + `collision_monitor` + `ground_drive_relay` + `ground_baseline`（自持 costmap）。

### (g) 路径输入扩展不推翻进程裁剪

`command_source=rl` 下仍**不**起独立 `nav2_costmap_2d` 进程。占位全局规划器与路径消费者**不以** costmap 为前提—— 路径质量门按[地面规划决策](0013-ground-planning-path-contract.md#top)的定义执行（含"无 costmap 时不按 costmap 边界截断"这一已知空缺）。新增进程的归属须**显式声明**，本篇**不预批**任何新进程，也不因新增路径而放宽"闲置进程不计吸收"的验收口径。

**命令源缺失边界**：`collision_monitor` 的失源保护只覆盖**感知源**，不覆盖**命令源**（命令源完全缺失时它不主动发零速）。该事实与进程裁剪结论并存，须在对应闭环任务中用行为证据闭合。

## 不做什么（边界）

- **不**在空中域引入 Nav2 运行时进程（不接 Nav2 3D planner / controller 插件）。
- **不**保留独立 `nav2_costmap_2d` 进程「以备将来 RL 观测」—— 当前无消费者，属闲置进程。
- **不**全面拆掉 Nav2 组件回归纯自研（牺牲安全层与离线基线的复用价值）。
- **不**以类名 / 节点计数验收吸收；**不**预批新进程。
- **不**改冻结 9 消息 / 服务 ABI、唯一执行口语义、硬约束–。

## Considered Options

- **空中也接 Nav2（自研 3D planner / controller 插件）** —— 被否：成本高、收益薄。
- **仅地面用 Nav2（维持契约原意）** —— 被否：不满足"全范围吸收其方法"。
- **保留独立 costmap 进程「以备将来 RL 观测」** —— 被否：当前无消费者，属闲置进程；若将来确实需要，届时按消费者出现再引入。
- **全面拆掉 Nav2 组件、回归纯自研** —— 被否：违背代码层吸收原则，且牺牲 `collision_monitor` 与离线基线的复用价值。
- **不改、仅补文档** —— 被否：闲置进程现象仍在，验收口径仍未校准。

## Consequences

- **正面**：进程层与代码层各有可验收的落点；运行拓扑按命令源如实裁剪，只含**实际责任**节点；吸收验收改看**行为**（责任 / 必要性 / 失败验收）；空中链路不依赖 Nav2 运行时，Nav2 升级 / 替换不阻塞空中域。
- **代价 / 限制**：「选择性吸收」成为空中域重写的默认判据（每次须论证采纳 / 不采纳）；矩阵各行的落点判定依赖"实际责任"这类需要读实现的证据，比数节点更费工。
- **未决 / 后续**：`collision_monitor` 不覆盖命令源缺失这一空缺待用行为证据闭合；新增规划器进程的归属由对应任务裁定，本篇不预批。

## 参考

- 契约：[#execution-port](0020-package-boundaries-and-runtime-topology.md#execution-port) / [#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints) / [#messages](0020-package-boundaries-and-runtime-topology.md#messages) / [#params](0020-package-boundaries-and-runtime-topology.md#params)
- 相关决策：[ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)（地面主控与安全层）、[ADR-0020](0020-package-boundaries-and-runtime-topology.md#top)（包边界与运行拓扑）、[ADR-0013](0013-ground-planning-path-contract.md#top)（地面规划与路径契约）、[ADR-0010](0010-safety-thresholds-and-failsafe.md#top)（安全阈值与安全屏障）、[ADR-0019](0019-lifecycle-and-startup-robustness.md#top)（生命周期与启动健壮性）
- 术语：`GLOSSARY.md` 的「选择性吸收」
