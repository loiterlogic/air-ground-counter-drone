<a id="draft"></a>
# H0 高度语义与基准标定 · request 草案（未派发）

> 状态：**设计草案，不是派工单，不授权执行或运行**。Leader 编写；2026-11-01。当前 `CURRENT.md` 为空闲。正式发布须在用户确认策略后转入唯一任务 ID 的 `task/<id>/round-1/request.md`，重新核对基线和工作区。

## 候选任务

- 拟议任务 ID：`20261101-004-h0-altitude-semantics`（仅草案预留；正式派发前需核对不复用）。
- 目标：为 N1 建立可复现、语义单一且有 GUI 证据的高度基准，明确目标出生、复位、episode 相对运动/巡航，以及己方跟踪高度之间的关系；不得把不同坐标系或不同职责的高度量合并成同一参数。
- 路线依据：[H0 目标与出口](../../docs/plan/H0-目标高度语义与基准标定.md#goal)、[H0 已确认事实](../../docs/plan/H0-目标高度语义与基准标定.md#facts)、[H0 出口判据](../../docs/plan/H0-目标高度语义与基准标定.md#exit)；下游：[N1](../../docs/plan/N1-视觉驱动最小闭环.md#goal)。
- 项目约束只引用[契约真源](../../docs/ROS2迁移交接文档.md#hard-constraints)、[参数入口](../../docs/ROS2迁移交接文档.md#params)、[世界坐标系](../../docs/ROS2迁移交接文档.md#namespace)；不得在本任务复制或改写硬约束。

## 当前已核事实

1. `src/agc_task/config/spawn_layout.yaml` 的 `spawn_layout.target.z` 当前为 `2.0`；经 `w6_composition.apply_spawn_layout()`，该值作为布局缺省进入世界 spawn 与 `scenario_reset.target_z`，场景显式覆盖仍优先。
2. `src/agc_task/config/w6_base.yaml` 的 `intruder_driver.alt_m` 当前为 `2.0`。`intruder_driver._target()` 用当前 episode 原点 `oz - alt_m` 写入 PX4 局部 NED setpoint；它是相对该原点的高度变化量，不应直接当作世界系绝对巡航高度。
3. 场景配置可覆盖 `scenario_reset.target_z` 与 `intruder_driver` 运动参数。必须对照主场景与线性/机动场景，不能只读 base 值推断有效值。
4. 己方 UAV 跟踪高度另由 `air.yaml` / 空中轨迹与起飞链路承载。契约世界高度是 ENU `world z`；PX4 入侵者驱动内部为局部 NED。高度标定必须明确这些量的变换和基准，禁止把己方跟踪高度当作目标高度。
5. 既有材料：[ADR-0014 episode 起点协议](../../docs/adr/0014-task-fsm-and-scenario-transaction.md#top)、[ADR-0008 跟踪参数](../../docs/adr/0008-air-trajectory-and-tracking-calibration.md#top)、[ADR-0008 世界高度语义](../../docs/adr/0008-air-trajectory-and-tracking-calibration.md#top)、[ADR-0009 能力限制](../../docs/adr/0009-perception-truth-derived-and-vision-path.md#top)、[G2 最终边界](../archive/20261101-003-g2-placeholder-path/round-9/review.md#review)。G2 的 `s04` 双 GUI 证据可作当前基线背景，不替代 H0 的高度验证。

## 开工前决策门

- 用户须确认或修订推荐策略：[H0 推荐策略](../../docs/plan/H0-目标高度语义与基准标定.md#strategy)“场景给定高度、目标控制层执行”；场景固定的是可复现巡航高度，不把静态出生位置和相对爬升量混作同一数值。
- 本草案不选具体高度数值。数值须由相机/传感器可见性与视场、己方 standoff 跟踪安全、主地图净空和地面载荷/交战适用包络共同判定；若现有能力不可达，按不可达报告，不反向放大包络制造通过。
- 用户确认策略后，正式派工仍需复核未提交工作区与运行环境，冻结本单基线/白名单，并明确 T2 总墙钟与真实运行总时长；在正式派工前不得构建、启动仿真或采集新运行数据。

## 设计范围提案

- 允许范围（待正式派工确认）：只涉及目标高度语义及其场景配置、目标 spawn/reset/episode 驱动注入、run manifest/summary 的生效高度记录、必要测试和文档回填。
- 预期读写候选（最终白名单由正式派工单确定）：`src/agc_task/config/spawn_layout.yaml`、`src/agc_task/config/scenarios.yaml`、必要的 `src/agc_task/config/w6_base.yaml`/相关场景配置、`src/agc_task/launch/w6_composition.py`、`src/agc_task/launch/w6.launch.py` 或 `src/agc_task/scripts/intruder_driver.py`（仅在证据证明需要时）、对应任务配置/manifest 测试、H0 计划文档及必要的决策记录。
- 不在范围：修改 ROS 消息 ABI、契约硬约束、唯一执行口、任务终态、安全阈值或捕获/干扰包络；地图扩建；自主逃逸/高度随机决策；视觉识别算法；修改己方 UAV 轨迹/控制器以掩盖目标高度问题；G2 实现返工。
- 不以“出生高度、相对爬升、巡航高度都数值相同”作为目标。若决策结果保留多种语义，须有单一权威输入及显式派生关系，且禁止歧义叠加。

## 建议步骤

1. 静态梳理高度全链：源配置、场景覆盖合并、世界 spawn、reset 写入/读回、episode epoch 与 PX4 NED setpoint、目标真值/感知输入、manifest 实际生效值。画出各量的参考系、原点、符号、时间段及生产者/消费者。
2. 先学习同版本/仓内已验证实现：ADR-0014 的 episode 起点协议、ADR-0008 的世界 ENU 与 NED 转换、ADR-0008 的 standoff/轨迹参数来源；若需外部参照按 AGENTS.md 优先序查证并记录版本和具体行为，不以假设试错。
3. 在用户确认的策略下形成候选高度基准与可行性核查矩阵；逐项给来源、计算/观测证据、不确定度和不可达判据。先离线核对净空/几何/配置，不预设成功数值。
4. 实施单一有效来源及清晰派生：保证世界 spawn、reset、episode 驱动语义不重叠；主场景与目标运动场景显式记录实际生效高度，manifest 可还原配置源与换算后的世界 ENU 高度。
5. 增加有针对性的单元/配置/launch 回归，覆盖默认与场景覆盖优先级、重置一致性、episode 起点变化、NED/ENU 符号与原点变换、非有限/缺失高度拒绝或明确降级。
6. 正式派工明确授权后，按 H0 出口核对主场景及目标运动场景；真实整链验收使用 GUI。逐项检查己方起飞、standoff、相机观测与地面载荷影响，记录全链终态和实际高度。失败记录保留，不降低观测门、不改终态。
7. 完成文档与 run 元数据回填，独立审查后才可验收归档；H0 未验收前不得启动 N1 的视觉实施。

## 拟议白名单与产物

- 只允许正式 request 明列文件；建议先以配置解析、合并、spawn/reset、manifest 和目标驱动文件为候选，不自动授权整个包。
- 真实实验产物仅写 `experiments/h0-altitude-semantics/<run_id>/`，包含 config 快照、run 身份、场景/seed/backend/mode、执行前后基线、命令与起止时间、实际生效高度、终态、安全/跟踪指标和日志索引，符合 [ADR-0006](../../docs/adr/0006-experiment-artifacts-and-evidence-discipline.md#top)。
- 草案本身及其所在目录不是实验产物目录；本次未运行实验。

## 拟议验收判据

1. 出生、复位、相对爬升、巡航高度及己方跟踪高度各自定义无歧义；其参考系、原点、符号、来源与派生关系可逐项追溯。
2. 对主场景和目标运动场景，世界 spawn 与 reset 的目标位置语义一致；episode 起点/驱动不会重复叠加高度，复位后目标实际高度与登记一致。
3. 运行产物可还原每个场景/seed 的源配置、场景覆盖、目标实际世界 ENU 高度与目标运动剖面；不同量不再以同名/同字段混记。
4. 目标高度候选有传感器/相机视场、己方起飞与 standoff、安全净空及地面载荷影响核查证据；不可达项如实报告，不通过扩大既有安全/任务包络掩盖。
5. 相关自动化回归通过；正式授权的主场景 GUI 整链证据满足既有终态定义，失败及异常样本保留。
6. 不引入自主逃逸决策、不扩地图、不改硬约束/9 消息 ABI/唯一执行口/终态/阈值顺序；H0 文档和 N1 输入明确引用最终高度真源。

## 资源与停止条件提案（非授权）

- T1：草案阶段未授权（0）；正式派工若需微观测，按协作协议单独写正向时间预算与单次上限。
- T2：草案阶段未授权（0）；配置/代码构建与任何 GUI/full/lightweight 仿真均属 T2，必须由正式派工明确授权。
- 正式 request 必须给批次总墙钟、T2 真实运行总时长、单次运行时限与独占资源；建议次数只记账。
- 停止：达到任一正式总时间/资源上限即停并交回；连续 4 轮无区分性新证据即熔断并提交假设台账；发现硬约束/基线未知漂移、需要越出白名单、策略/验收口径变化或高度数值证据不足时立即停止并报告。
- 根因已明确时，只可在正式白名单和剩余授权内修复并复验；草案不授予任何此类执行权。
- 当前未授权任何 T1/T2 动作，未派发 Worker，未创建 `.coordination/task/20261101-004-h0-altitude-semantics/`。
