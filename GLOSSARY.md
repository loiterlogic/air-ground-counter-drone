# AGC 空地协同（Anti-Drone AGC）

空地协同反无人机仿真项目的领域语言。本文只收录本项目特有的概念，不含通用编程术语。定义用中文表述，术语键保留原始形式。

## 语言

> **阅读提示**：带「研究期术语」标注的条目属于研究期（[ADR-0021](docs/adr/0021-gui-headless-equivalence.md#top) 等）的度量口径，**当前收尾阶段非必读**，只在追溯研究结论时查；未标注的条目仍是现行项目的共同语言。
> 术语只定义"是什么"；约束类信息（坐标系、唯一执行口、硬约束、终态语义）**只在** [契约真源](docs/adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints)，本表不复述。

**AGC**:
空地协同（Air-Ground Collaboration）—— 在同一世界、同一时钟下，无人机与地面车围绕统一任务定义构成的协同系统。
_Avoid_: 空地系统、飞机地面

**选择性吸收（Selective Absorption）**:
ROS2 重构中对待外部既有能力的既定方式：优先复用/吸收成熟方法（如 Nav2）的架构范式与实现经验来优化本仓库原代码，而非整包照搬或另起炉灶。
_Avoid_: 替代、迁移、照搬

**模式全覆盖·进程按域选用（Pattern-Complete, Process-Scoped）**:
把"Nav2 覆盖所有部分"落成的可执行表述—— 地面域真跑 Nav2 本体；空中域不引入 Nav2 运行时进程，但全面采纳其架构范式（costmap 分层语义、lifecycle 节点、planner/controller server 抽象、行为树）。
_Avoid_: Nav2 全覆盖（含义不清）

**契约真源（Contract Source of Truth）**:
不可变约束的唯一归属地——[ADR-0020](docs/adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints)，承载坐标系、唯一执行口、硬约束、终态语义、接口语义。其它文档只能引用、不得复述。
_Avoid_: 合同、基线文档

**唯一执行口（Sole Execution Port）**:
运动中唯一可**命令车体运动**的通道，即 `/agc/ground/cmd_vel`；任何其它节点均不得命令车体运动。车体位姿由 GZ Sim 物理引擎产生，复位写入为唯一例外。语义与例外以契约真源为准。
_Avoid_: 执行入口（与"Runbook"混淆）

**安全层（Safety Layer）**:
地面域中位于控制输出与唯一执行口之间的兜底屏障，按配置区域对速度强制缩放或急停；默认由 Nav2 `collision_monitor` 实现，空中域由自研避障/滤波器承担。它**不做绕行规划**，因此不等于**局部避障**；其感知可见性边界以 [ADR-0009](docs/adr/0009-perception-truth-derived-and-vision-path.md#top) 为准。
_Avoid_: 保护层、shield（指标口径另见契约真源）、避障（会被误读为局部避障）

**职责分层（Role Stratification）**:
P2 的架构自变量：高层只出**决策目标**（拦截点 / 火控窗口 / 局部偏移），由成熟低层控制器执行；与"训练 RL"不同——P2 v1 的对照臂以**规则高层**承载（[ADR-0023](docs/adr/0023-adjudication-record-and-exit.md#top)）。
_研究期术语，当前阶段非必读。_
_Avoid_: 高层 RL（未经训练时）、端到端（含义相反）

**有效火控机会（Fire-Control Opportunity, FCO）**:
目标**同时**满足「可见（感知新鲜）+ 在网发射可及集内」的拍；其占比是 P1/P2 的主 DV。P1 v1 用 `window_fixed_v1`（自首个 active 拍起 60 s，**含终态后停泊**）；P2 v3 用 **active-window FCO**（仅 `GROUND_APPROACH → 终态`，[ADR-0023](docs/adr/0023-adjudication-record-and-exit.md#top)）。
_研究期术语，当前阶段非必读。_
_Avoid_: 开火率、命中率（不同量）

**oracle 目标臂（Oracle-Goal Arm）**:
任务目标直接取**目标真值坐标**（而非感知输出）的对照臂；须显式标注，不能与感知驱动臂混读为同一自变量（[ADR-0023](docs/adr/0023-adjudication-record-and-exit.md#top)）。
_研究期术语，当前阶段非必读。_
_Avoid_: 真值臂（未标注时）、感知臂（含义相反）

**无人机跟踪（UAV Standoff Tracking）**:
己方无人机对入侵目标的**常开**跟踪：保持**安全间距**（不紧贴），目的是**不丢失目标**并持续提供观测，同时负责自身飞行安全。与"编队跟随"不同。
_Avoid_: 跟随、伴飞、编队

**航迹指向（Track-Driven Aiming）**:
观测偏航模式之一：机头朝向由**感知航迹**（`/agc/targets` 的 fresh 目标）决定；无可用航迹时执行**确定性搜索**而非退回随速度。与 **oracle 目标臂**的分界是**指向源**—— 本模式不读真值；与**协同感知**的关系是：它是"空中持续对准目标"这一职责的机头层实现。
_Avoid_: 视觉指向（当前航迹仍是真值派生）、自动跟踪（含义含平移）、oracle 指向

**协同感知（Collaborative Perception）**:
无人机提供空中观测（全局视野），地面平台据此**自主规划**自身路径；二者不共享单一规划器。这里的"自主规划"指**地面侧**承担全局路径决策，不指地面内部某一个具体规划器实现。
_Avoid_: 跟随、编队、主从

**全局路径规划（Global Path Planning）**:
地面侧决定"从当前位置沿哪条线到目标"的规划职责，产出一条供局部策略消费的路径。与**局部避障**分工不同：它不做逐步避让，也不承担安全兜底；具体话题、消息与坐标系归决策记录，不在本表。
_Avoid_: 全局导航（含义含执行）、路径跟随（那是局部策略的事）

**路径输入缝（Path Input Seam）**:
把全局路径送进局部策略的**接入边界**；它有三层且互不蕴含—— 路径在 ROS 上的传输（传输缝）、有消费者真的按路径出速度（占位消费）、训练策略的固定维观测里含路径信息（模型观测缝）。判据与后果以 [ADR-0013](docs/adr/0013-ground-planning-path-contract.md#top) 为准。
_Avoid_: 路径跟踪能力（那是训练与验证之后的结论）、RL 已会跟路径

**局部避障（Local Obstacle Avoidance）**:
局部策略**主动绕开**障碍的在线决策能力，属 RL 承担（R4），输出可执行速度；它与**安全层**不是同一件事—— 后者只对已生成的速度做裁剪或清零，不产生绕行。
_Avoid_: 安全层、shield、兜底避障

**可控目标（Controllable Target）**:
入侵目标（`intruder_uav`）在仿真中**可被脚本化驱动**的能力—— 外部经速度指令改变其运动，用于的脚本化轨迹与干扰注入；与"被动刚体"相对。
_Avoid_: 主动目标、自主目标

**拦截载荷（Interception Payload）**:
地面平台（`agc_car`）搭载的拦截附件总称，含**捕获网面**与**干扰载荷**两类（ADR-0011）。
_Avoid_: 武器、装备

**捕获网面（Capture Net）**:
车载**网发射器 / 发射的网**的几何载体（原为固定直径 2 m 圆面；[ADR-0011](docs/adr/0011-interception-and-fire-control.md#top) 起改为**发射式网**）；车体模型层只提供几何与位姿，捕获裁决属 [ADR-0011](docs/adr/0011-interception-and-fire-control.md#top)。
_Avoid_: 网兜、拦截网

**发射式网捕获（Launched-Net Capture）**:
物理捕获机制：**网由车载发射器射出并展开**、作用于目标（非"目标穿越固定网框"）；**交战包络由网发射物理模型的"可及集"推导**。真实弹道属后续，现阶段以**可插拔裁决器**做闭式判定（[ADR-0011](docs/adr/0011-interception-and-fire-control.md#top)）。
_Avoid_: 固定网面、穿越判据

**出生净空（Spawn Clearance）**:
场景生成中"任意两实体出生后互不侵入各自初始安全包络"的约束；其下限为**可标定量**（按新安全档 + 实体外伸推导，[ADR-0012](docs/adr/0012-spawn-clearance-and-reset-transaction.md#top)），与"复位重试预算"为两条独立语义。
_Avoid_: 出生间距（旧 `2.4 m` 口径）

**干扰载荷（Jammer Payload）**:
车载**行为级电子干扰**发射器：以对目标行为的干预体现（EMI 不建模）；行为与接口属 [ADR-0015](docs/adr/0015-jam-authorization-and-confirmation.md#top)。
_Avoid_: 电磁武器、EMI 设备

**证据层（Evidence Layer）**:
感知地图中**累积观测证据**的栅格层（当前 0.25 m），承载逐格 log-odds 概率与连续的**几何占据率**；carving、衰减、生命周期都在它上面进行。它回答"这一格有多少比例被障碍覆盖、这个判断有多可靠"。
_Avoid_: 感知真源（与文档真源混淆）、高精度地图（未定义）、栅格层（与规划层不分）
**规划层（Planning Layer）**:
由**证据层派生**的栅格层（当前 0.5 m），只服务规划安全：任一子格确认占据即整格占据（max-pool），并可叠加**米制**安全膨胀。它**不代表真实几何**，因此不得用于评价感知精度。`/agc/map` 就是这一层。
_Avoid_: 规划图（含义含路径）、代价图（本仓未在 `/agc/map` 上表达代价梯度）
**分层评价（Layered Evaluation）**:
把地图质量拆成四套**互不冒充**的口径：**几何重建**（对真值几何的 precision / recall / IoU / 边界距离）、**规划可用性**（漏掉危险障碍 vs 误阻塞）、**实例稳定性**（按实例 id 的中心位移与边界位移）、**栅格可达率**（图上通不通）。稳定性**主判据**自 ADR-0042/0043 起是三条空间量：集合 IoU p50 / 已知区边界抖动 p90 / **实例中心位移 p50**，不再只看 `occupied` 数量差。实例位移取 **p50 而非 p90**：p90 被少数大实例的边缘翻转支配，而那是深度噪声的正常现象（单帧 `|Δocc|` ≈ 130 格）。口径与取舍以 [ADR-0040](docs/adr/0040-perception-multi-resolution-evidence-and-planning-layers.md#top) / [ADR-0042](docs/adr/0042-point-uncertainty-arbitrary-resolution-and-reachability.md#top) 为准。
_Avoid_: 感知精度（会被读成单一数字）、地图质量（未区分层）、规划成功率（见「栅格可达率」）

**栅格可达率（Grid Reachability）**:
在**风险图**上做真实栅格搜索（8 邻域 A*），回答"从起点到终点存不存在一条可通行路径"。口径与 `planning_policy.hpp` 的 `classifyCell` 一致：`0` 可通行、`1–99` 可通行但有代价、`>=100` 不可通行、`-1` 默认不可通行。**不含动力学**（加减速 / 转弯半径 / 倒车），因此**不得**表述为"规划成功率"。
_Avoid_: 规划成功率（会让人以为量的是"车能不能真的开过去"）、可达性（与图论可达性混淆）

**逐格元数据（Per-cell Metadata）**:
`/agc/map/cell_meta` 上的五元组：**占据比例**（0..1，被占了多少）/ **置信度**（0..1，判断有多可靠）/ **最近观测**（秒）/ **来源实例**（稳定 id）/ **完整可见**（`unknown` 是"没看过"还是"看不清"）。它回答 `OccupancyGrid.data` 一个 int8 装不下的问题 —— 后者只能回答"这一格算不算占据"。口径见 [ADR-0042](docs/adr/0042-point-uncertainty-arbitrary-resolution-and-reachability.md#top)。
_Avoid_: 概率图（占多少与有多可信是两件事）、代价图（那是 `/agc/map` 的风险分档）

**逐点不确定度（Per-point Uncertainty）**:
几何层里**每个点**自带的位置 2×2 协方差（world XY 上三角）与观测视角余弦，由位姿位置 / 位姿偏航 / 深度轴向 / 像素落位四项误差源解析传播相加得出。用途是**门控**（σ 超过半格宽的点本帧不进 hit 证据），不是逐点权重 —— 后者会让证据强度依赖像素采样密度。口径见 [ADR-0042](docs/adr/0042-point-uncertainty-arbitrary-resolution-and-reachability.md#top)。
_Avoid_: 置信度（那是 `confidence.hpp` 的声明值，与几何精度不是一回事）、误差椭圆（只描述了形状没描述来源）

**Runbook（步骤文档）**:
**历史**：迁移期唯一指导执行重构流程的入口文档，已归档为 [`docs/archive/ROS2迁移步骤.md`](./docs/archive/ROS2迁移步骤.md#top)；只编排"当时做什么、如何验收"，不承载约束。当前执行入口是 [当前方向](./docs/plan/README.md#plan-index)。
_Avoid_: 执行入口、执行口（迁移已暂停，Runbook 不再是任一任务的入口）

**workstream**:
本项目的独立可验收工作单元，每个 workstream 对应一份 spec/tasks/checklist 三件套；迁移期规格已随 Trae 退役删除（2026-11-03）；现行工作单元由 [当前方向](./docs/plan/README.md#plan-index) 索引。
_Avoid_: 阶段、phase、P0–P6（P0–P2 是**收尾阶段**，不是 workstream）

**只读旧树边界（Read-Only Archive Boundary，已退役）**:
**历史**：旧树归档 `reference/` 已于 2026-10-31 退役删除（[ADR-0025](docs/adr/0025-publishing-boundary-and-retirement.md#top)），本机已无旧树可读，该读取纪律随之失效；保留本条只为读懂历史文档。**继承其意**：任何决定**不得**再以旧树为依据，禁止复制旧代码或沿用其格式、命名、目录、任务粒度。
_Avoid_: 参考旧项目、沿用旧实现
