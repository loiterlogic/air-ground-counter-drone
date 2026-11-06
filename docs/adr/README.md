<a id="adr-index"></a>
# ADR 索引（自动生成）

> **本文件由 `scripts/adr_index.py` 生成，请勿手改**；改了会被 `--check` 抓到。
> 规则：编号与标题取自文件名与一级标题，`Status` 与「结论」取自各篇正文，**不推断、不改写**。
> 用法：查历史决策先扫本表 → 只打开命中的 1–2 篇；**不要**靠 `grep` 全目录。
> 全量决策仍以各 ADR 正文为准；本表只是索引。状态说明见 [目录与命名规范](../conventions/目录与命名规范.md#10-产物分类与生命周期)。
> **旧编号体系已退役**：各篇正文里「由 ADR-00xx 合并」的编号属 2026-11-02 重写前的旧体系，
> 对应文件已删除；现行有效编号只有本表 0001–0032（见 [引用与注释纪律](../conventions/引用与注释纪律.md#rule)）。

## 怎么用

- **想知道某件事当初怎么定的**：按标题/结论里的关键词在表里找，再点进去看正文。
- **`Status` 是原文摘录**（可能带日期与限定语）；`accepted` 表示决策有效，不代表实施完成。
- **`deferred` 不等于废止**：表示已裁定暂缓，括号里通常写了阻塞原因。
- **合并篇的 `deferred` 写在正文里**（2026-11-02 起）：合并后每篇只保留一个 `Status`，
  其下若有某项仍暂缓，正文对应小节会以 `**deferred**` 显式标注；查暂缓项请搜正文，不要只看本表。
- **暂停的路线其 ADR 仍是 `accepted`**：暂停事实记在 plan 的开关文件，不写进 ADR 状态。

## 统计

- 合计 **32** 篇：`accepted` 30 篇、`deferred` 0 篇、其它 2 篇

## 索引表

| 编号 | 标题 | Status | 结论 |
|---|---|---|---|
| [0001](./0001-project-positioning-and-execution-scope.md) | 项目定位：全新重写、纯仿真交付与研究主线 | accepted（2026-11-02 由 ADR-0001 / 0006 / 0009 / 0013 / 0014 / 0016 / 0017 合并；各条结论均未被后续决策推翻， 仅执行范围一项已随时间失效，见「已失效的部分」） | **软著登记对象** = `src/` 下的包； **「平台搭建」交付物** = 本**仿真**平台（世界 + 车 + 无人机 + 协同栈），不是实物平台； **论文素材** = 本仓库仿真实验产物（`experiments/`），论文在本仓库内完成。 |
| [0002](./0002-docs-source-of-truth-and-reference-discipline.md) | 文档真源分层与引用纪律 | accepted（2026-11-02 由 0002 / 0066 合并；结论未变） | 不可变约束（硬约束 / 坐标系 / 终态 / 接口语义） · [契约真源](../ROS2迁移交接文档.md#hard-constraints) 当前方向 / 进度 · [`docs/plan/`](../plan/README.md#plan-index) 难以逆转的决策 · `docs/adr… |
| [0003](./0003-nav2-paradigm-absorption.md) | Nav2 范式吸收：模式全覆盖、按命令源裁剪 | accepted（2026-11-02 由 ADR-0003 / 0008 / 0060 合并；结论未变） | **地面域**真跑 Nav2 本体组件；**空中域不引入 Nav2 运行时进程**，但重写时全面采纳其架构范式（costmap 分层语义、lifecycle 节点、planner / controller server 抽象、行为树），并保留 / 优化 LQR 与自研避障。唯一执行口 `/agc/… |
| [0004](./0004-ground-control-rl-primary-and-nav2-safety.md) | 地面控制栈：RL 主控、Nav2 安全层与共享控制库 | accepted（2026-11-02 由 0004 / 0018 / 0026 合并；分层口径、`agc_control` 归属与 C6 标定值均未变） | **RL 主控**：RL 直接输出 `cmd_vel`，经 Nav2 `collision_monitor`（按多边形区域缩放 / 急停）收敛到唯一执行口 `/agc/ground/cmd_vel`。链路顺序固定为 `RL → cmd_vel_raw → collision_monitor → 唯… |
| [0005](./0005-px4-toolchain-and-link.md) | PX4 工具链：uXRCE-DDS 链路、本体依赖与 pin 清单 | accepted（2026-11-02 由 0005 / 0012 / 0065 / 0067 / 0068 合并；链路协议、本体形态与 pin 纪律结论未变，agent 版本适用值统一为 v2.4.3） | 空中链路以 Micro-XRCE-DDS Agent + `px4_msgs`（`release/1.15`，与固件 v1.15.4 同版）直连 PX4 uORB，弃用 MAVROS / MAVLink 中间层。节点需自行处理 uORB 语义：微秒时间戳、NED/FRD 与 ENU 的换算、QoS… |
| [0006](./0006-experiment-artifacts-and-evidence-discipline.md) | 实验产物与证据纪律 | accepted（2026-11-02 由 0007 / 0044 / 0045 / 0063 / 0064 合并；结论未变，其中一次真实证据丢失事故的 登记与重做义务一并保留） | 所有实验产物只落一个根，按 campaign → run 两层组织： |
| [0007](./0007-scene-geometry-single-source-and-layout.md) | 场景几何单一真源、布局范式与物理驱动 | accepted（2026-11-02 由 ADR-0010 / 0055 / 0062 / 0106 / 0112 合并；结论未变） | `agc_car` 重设为差速两驱动轮 + 2 caster，挂 `gz::sim::systems::DiffDrive`；`wheel_separation` / `wheel_radius` / `max_wheel_torque` / `max_wheel_accel` 落 `agc_si… |
| [0008](./0008-air-trajectory-and-tracking-calibration.md) | 空中轨迹与跟踪参数标定 | accepted（2026-11-02 由 0019 / 0051 合并；C1 口径与容限结论未变，跟踪容限仍是**占位待回填**，如实标注） | **「8 字」改为真八字（Gerono）**：`x = cx + rx·sinθ`、`y = cy + ry·sinθ·cosθ`（自交成 ∞），`rx=15`、`ry=9`、 `h=2.5 m`；**全程恒速 `v=2.0 m/s`**（弧长参数化，无加减速）；**删去「角速度 0.1」**。… |
| [0009](./0009-perception-truth-derived-and-vision-path.md) | 感知口径：真值派生与能力边界（视觉路径已退役） | accepted（2026-11-02 由 0020 / 0052 / 0053 / 0103 / 0110 合并；2026-11-03 新增 (a2) 真值目标指示的不确定性模型与置信度/精度解耦；**2026-11-04 视觉定位路径整体删除**，本 ADR 由"真值派生 / 视觉并行"改为"只有真值派生一条路径"。能力边界的「不做 / 不承诺」部分一并收窄登记） | `air_perception` 以**世界真值**为输入、以**通道模型**产出观测：丢包 / 突发丢失 / 几何门控（量程 + FOV）/ 遮挡 / 高斯噪声与偏置，并给出**已标定** `confidence` 与观测序号 `obs_seq`。 ⚠ **2026-11-04 起该输出无消费者… |
| [0010](./0010-safety-thresholds-and-failsafe.md) | 安全阈值、末端失效停车与安全屏障 | accepted（2026-11-02 由 ADR-0021 / 0025 / 0042 / 0048 / 0050 合并；结论未变） | 硬约束 **C2** 保留的是**顺序不变量** `紧急 < 碰撞 < 安全`；三档**绝对值**由地面安全层按实测动力学标定，属契约真源的可标定量。旧值 `0.7 / 0.9 / 2.4 m`（源自旧树无人机避障配置、为小场地慢速设定）**作废**，文档 / 报告不得再引用。 |
| [0011](./0011-interception-and-fire-control.md) | 拦截口径与火控：发射式网、交战门与在飞生命周期 | accepted（2026-11-02 由 ADR-0015 / ADR-0022 / ADR-0024 / ADR-0035 / ADR-0058 / ADR-0079 / ADR-0091 / ADR-0111 合并；结论未变。其中「入包络即命中」的占位裁决口径已被后续「预演弹道能命中才开火」替换，旧口径作废） | **物理捕获**：以发射式网的物理模型判定，终态 `INTERCEPT_CONFIRMED` + `reason_code = CAPTURE_NET`。 **电子干扰**：**行为级等价**——对入侵者强制 `RTL` / `LAND` / `HOLD`，或用「停发 Offboard 指令」触发… |
| [0012](./0012-spawn-clearance-and-reset-transaction.md) | 出生净空与场景复位事务 | accepted（2026-11-02 由 0023 / 0029 合并；出生净空下限为可标定量、候选校验为「实体对 + 边界」的统一口径均未变） | C7 拆为两条**独立**语义： |
| [0013](./0013-ground-planning-path-contract.md) | 地面规划：基线路径、重规划策略与外部规划器契约 | accepted（2026-11-02 由 ADR-0027 / 0056 / 0089 / 0092 / 0108 / 0109 合并；路径绑定、重规划触发口径与外部规划器契约的结论均未变，四项外部对接未决仍挂起） | 每次**成功**规划记录绑定三元组，仅在绑定仍有效时继续使用既有路径：**目标身份**（规划时刻 goal，`last_plan_goal_`； 当前 goal 位移 > `replan_displacement_m` → 目标变）、**地图签名**（`last_plan_map_sig_`，见… |
| [0014](./0014-task-fsm-and-scenario-transaction.md) | 任务 FSM、起始事务与终态锁存 | accepted（2026-11-02 由 ADR-0028 / 0030 / 0031 / 0037 / 0076 合并；结论未变） | `main()` 由 `rclcpp::spin` 改 `MultiThreadedExecutor`；`/agc/task/start` 与 `/agc/task/abort` 放专用 互斥回调组（`srv_cb_group_`），服务回调可在本线程阻塞等 `reset` / `reset_ph… |
| [0015](./0015-jam-authorization-and-confirmation.md) | 干扰：单一授权、真实确认与因子分离 | accepted（2026-11-02 由 ADR-0032 / ADR-0033 / ADR-0034 合并；结论未变。其中「发送即确认」与「停流 ≡ `NAV_DLL_ACT`」两处旧口径作废） | **授权**：仅当「命令合法」（`key in JAM_MAP`）**且**「作用包络**新鲜**」才产出**已校验授权事件** `JAM_*`（发布到 `/agc/task/jam_state`）并 `_send_nav_state`；未知命令 / 包络外 / 包络过期（未就绪）一律**不产出事… |
| [0016](./0016-episode-window-and-sample-validity.md) | episode 窗口统计与有效样本掩码 | accepted（2026-11-02 由 0036 / 0038 / 0043 / 0078 合并；结论未变，其中样本掩码已两次修订，正文只保留现行 `window_valid_v2` / `scan_frame_fresh_v2` 口径并注明旧口径作废） | 以 task 进入 / 离开 **active**（`AIR_SEARCH` / `TARGET_ACQUIRED` / `GROUND_APPROACH`）为事件边界： |
| [0017](./0017-time-budget-and-clock-sources.md) | 时间预算口径与时钟/源时刻 | accepted（2026-11-02 由 ADR-0039 / 0047 / 0054 合并；结论未变） | `mission_sim_budget` · `ros_sim`（`now − start_time_`） · `task_manager`（C4） · `t_max_s`（`config/w6_base.yaml` 单一注入） · **任务预算**：episode 任务超时判据（超时算失败） `… |
| [0018](./0018-acceptance-and-coverage-matrix.md) | 验收判定与整链覆盖矩阵 | accepted（2026-11-02 由 ADR-0040 / 0041 / 0046 / 0057 合并；结论未变） | `classify_acceptance_layers(result)` 输出三层布尔： |
| [0019](./0019-lifecycle-and-startup-robustness.md) | 生命周期可重建与启动健壮性 | accepted（2026-11-02 由 ADR-0049 / ADR-0072 / ADR-0080 合并；结论未变） | 基类提供 `declare_param_idempotent<T>(name, default)`：`has_parameter` 先判，已声明则直接读取。被管空中节点（`px4_adapter / takeoff_controller / trajectory_tracker / standof… |
| [0020](./0020-package-boundaries-and-runtime-topology.md) | 包边界、语言选型与运行拓扑 | accepted（2026-11-02 由 ADR-0011 / 0059 / 0061 合并；结论未变） | **C++（`ament_cmake`）**：性能 / 实时敏感域——空中链路（高频 uORB）、感知融合（高频点云 / 图像）、 地面安全层（硬约束 C6 的实时逃逸能力）。理由：低延迟、可控内存、无 GIL、可给实时保证。 **Python（`ament_python`）**：RL 与工具脚本… |
| [0021](./0021-w8-gui-headless-equivalence.md) | W8：GUI/headless 等价、确定性探针与平台冻结 | accepted（2026-11-02 由 ADR-0069 / 0096 / 0097 / 0098 / 0099 合并；结论未变——等价门仍 `not_evaluable_as_specified`、平台冻结仍 `conditional`、headless 规模统计仍未授权；模式等价设计一节按原文保留 `deferred` 状态说明） | W7-a 最小平台产出"语义正确、可复现、可被训练的环境 + 一致的 train / eval 协议"，验收锚 = 同 seed 可复现 / 指标齐全。**RL 算法、网络、奖励、训练步数、论文问题不在 W7 入口出口内**（属 W7-b：先定可证伪命题，并先用规则策略证明任务非平凡且可达）。四件… |
| [0022](./0022-w7b-research-propositions-and-decision-rule.md) | W7-b：科研命题、度量口径与判定规则 | accepted（2026-11-02 由 ADR-0070 / ADR-0074 / ADR-0084 / ADR-0086 / ADR-0088 合并；结论未变。其中「固定观测窗 + `mean ≥ MDE`」的判定口径已被后续 active-window primary 与三态 CI 规则取代，旧口径作废） | **P1 协同收益（主线）** · **协同程度 α** = {空地协同策略, 非协同（地面单体 / 空中固定航迹）} · 同传感权限 / 速度约束 / 安全层 / 终态 **P2 RL 职责分层（副线）** · **职责分层 β** = {臂 A: c2（RL 直接出 `cmd_vel`）, 臂… |
| [0023](./0023-w7b-adjudication-record-and-exit.md) | W7-b 裁定记录与出口闭合 | accepted（2026-11-02 由 0071 / 0073 / 0082 / 0083 / 0085 / 0087 / 0090 / 0093 合并；P1 = `inconclusive`、P2 = `falsified` / 保留 c2、v7 未注册、W7-b 已闭合，结论未变） | **E1** · raw / effective **同拍**归因 · 同拍配对 + 干预标注；shield=true 时 `intervened=276/439`、干预时长 13.09 s，shield=false 时 `intervened=0` **E2** · **最小动态火控** · 完… |
| [0024](./0024-w7c-multi-worker-isolation.md) | W7-c 多 worker 隔离与扩容准入 | accepted（2026-11-02 由 ADR-0077 / 0095 合并；隔离机制与准入指标已落地，但 A/B 门因 1 次 `INFRA_FAILURE` 未通过，最终结论是**显式接受单 worker**——结论未变，见 (f) 末条与「结果」） | 约束 4 封死了"按 domain 隔离"的常规做法；独立 netns 下每 worker 拥有独立 loopback，于是所有 worker 可**统一使用 `ROS_DOMAIN_ID=0`**（规避非 0 域缺陷）、DDS 发现（`LOCALHOST`）天然不出 netns、PX4 MAVL… |
| [0025](./0025-publishing-boundary-and-retirement.md) | 发布边界与退役清理 | accepted（2026-11-02 由 ADR-0081 / 0105 / 0107 合并；结论未变） | `.gitignore` 增精确规则： |
| [0026](./0026-leader-worker-collaboration-and-batch-authorization.md) | 协作机制：双模型分工与批次授权 | accepted（2026-11-02 由 ADR-0102 / 0104 合并；结论未变） | Leader · 不固定（会话内可切） · 讨论、诊断、裁定、派工、独立验收 · `worker` 创建，`send_message` 复用 Worker · 钉死：workbuddy / `deepseek-v4.1-flash` / `max` · 实施、构建、实验、如实回报 · `send_… |
| [0027](./0027-uxrce-startup-reproducibility.md) | uXRCE 启动可复现性：预热、错峰与种子协议 | accepted（2026-11-02 由 ADR-0075 / 0094 / 0100 / 0101 合并；结论未变） | 本篇只覆盖**启动可复现性**：进程清场、PX4 启动错峰、可选 warmup、空中就绪门、seed 派生与注入。 它**不**改变估计 odom 契约、**不**替代 W8 正式测量门、**不**宣称整链确定性。per-instance seed 派生 只适用于 W6 full 组合；W3 st… |
| [0028](./0028-dds-discovery-range-and-transport.md) | DDS 发现范围与传输：按 `lo` 能力探测，禁止写死 `LOCALHOST` | accepted（2026-11-04） | DDS 发现范围与传输的**唯一决定点**是 `scripts/demo/dds_transport.py`。 禁止在任何其它位置写死 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`。 |
| [0029](./0029-continuous-validation-layers.md) | 持续验证：三层回归入口与"负例加严"判定 | accepted（2026-11-04） | `tests/run_smoke.py` · 离线冒烟 7 组 · 每次提交 · 否 · ~40 s `tests/run_full_regression.py` · `full` 整链 3 场景 · 定时 · 是 · ~240 s `tests/run_n3_matrix.py` · 回归矩阵… |
| [0030](./0030-nadir-camera-capability.md) | ADR-0030：机载正下视（nadir）相机能力 | （未标注） | 新增机型取值 `gz_agc_x500_nadir`（复用**已有** launch 参数 `px4_sim_model`，**不新增 launch 参数**）。 默认 `gz_x500` 时：不加相机、不注入任何新环境变量、rcS 走原路径 —— 与改动前完全一致。 |
| [0031](./0031-target-motion-and-speed-regime.md) | 目标无人机运动规则与三主体速度体制 | accepted（2026-11-04） | 本篇同时结档两条 plan：**目标无人机运动规则** 与 **速度调研与运行节奏优化** （两者按 [任务计划规则](../plan/README.md#plan-index) 结档即删，结论只存在于本篇）。 它们共用 `intruder_driver` 与 `scenarios.yaml` 的… |
| [0032](./0032-pending-directions.md) | 待立项的后续方向（占位登记） | proposed（2026-11-06；未立项、无实施） | 以下 4 项**均未立项**，不得据本篇推定已实现、已批准或已有排期： |

## 合并映射（2026-11-02，112 → 27）

> 2026-11-02 做过一次**显式例外**的合并：同域旧 ADR 归并、去重过程叙事，结论逐条保留。
> 下表用于回答「我以前记得的 `ADR-00NN` 现在归哪篇」。映射取自各篇 `Status` 的合并说明，**不另行维护**。

| 旧编号 | 现编号 |
|---|---|
| 0001 | [0001](./0001-project-positioning-and-execution-scope.md) |
| 0006 | [0001](./0001-project-positioning-and-execution-scope.md) |
| 0009 | [0001](./0001-project-positioning-and-execution-scope.md) |
| 0013 | [0001](./0001-project-positioning-and-execution-scope.md) |
| 0014 | [0001](./0001-project-positioning-and-execution-scope.md) |
| 0016 | [0001](./0001-project-positioning-and-execution-scope.md) |
| 0017 | [0001](./0001-project-positioning-and-execution-scope.md) |
| 0002 | [0002](./0002-docs-source-of-truth-and-reference-discipline.md) |
| 0066 | [0002](./0002-docs-source-of-truth-and-reference-discipline.md) |
| 0003 | [0003](./0003-nav2-paradigm-absorption.md) |
| 0008 | [0003](./0003-nav2-paradigm-absorption.md) |
| 0060 | [0003](./0003-nav2-paradigm-absorption.md) |
| 0004 | [0004](./0004-ground-control-rl-primary-and-nav2-safety.md) |
| 0018 | [0004](./0004-ground-control-rl-primary-and-nav2-safety.md) |
| 0026 | [0004](./0004-ground-control-rl-primary-and-nav2-safety.md) |
| 0005 | [0005](./0005-px4-toolchain-and-link.md) |
| 0012 | [0005](./0005-px4-toolchain-and-link.md) |
| 0065 | [0005](./0005-px4-toolchain-and-link.md) |
| 0067 | [0005](./0005-px4-toolchain-and-link.md) |
| 0068 | [0005](./0005-px4-toolchain-and-link.md) |
| 0007 | [0006](./0006-experiment-artifacts-and-evidence-discipline.md) |
| 0044 | [0006](./0006-experiment-artifacts-and-evidence-discipline.md) |
| 0045 | [0006](./0006-experiment-artifacts-and-evidence-discipline.md) |
| 0063 | [0006](./0006-experiment-artifacts-and-evidence-discipline.md) |
| 0064 | [0006](./0006-experiment-artifacts-and-evidence-discipline.md) |
| 0010 | [0007](./0007-scene-geometry-single-source-and-layout.md) |
| 0055 | [0007](./0007-scene-geometry-single-source-and-layout.md) |
| 0062 | [0007](./0007-scene-geometry-single-source-and-layout.md) |
| 0106 | [0007](./0007-scene-geometry-single-source-and-layout.md) |
| 0112 | [0007](./0007-scene-geometry-single-source-and-layout.md) |
| 0019 | [0008](./0008-air-trajectory-and-tracking-calibration.md) |
| 0051 | [0008](./0008-air-trajectory-and-tracking-calibration.md) |
| 0020 | [0009](./0009-perception-truth-derived-and-vision-path.md) |
| 0052 | [0009](./0009-perception-truth-derived-and-vision-path.md) |
| 0053 | [0009](./0009-perception-truth-derived-and-vision-path.md) |
| 0103 | [0009](./0009-perception-truth-derived-and-vision-path.md) |
| 0110 | [0009](./0009-perception-truth-derived-and-vision-path.md) |
| 0021 | [0010](./0010-safety-thresholds-and-failsafe.md) |
| 0025 | [0010](./0010-safety-thresholds-and-failsafe.md) |
| 0042 | [0010](./0010-safety-thresholds-and-failsafe.md) |
| 0048 | [0010](./0010-safety-thresholds-and-failsafe.md) |
| 0050 | [0010](./0010-safety-thresholds-and-failsafe.md) |
| 0015 | [0011](./0011-interception-and-fire-control.md) |
| 0022 | [0011](./0011-interception-and-fire-control.md) |
| 0024 | [0011](./0011-interception-and-fire-control.md) |
| 0035 | [0011](./0011-interception-and-fire-control.md) |
| 0058 | [0011](./0011-interception-and-fire-control.md) |
| 0079 | [0011](./0011-interception-and-fire-control.md) |
| 0091 | [0011](./0011-interception-and-fire-control.md) |
| 0111 | [0011](./0011-interception-and-fire-control.md) |
| 0023 | [0012](./0012-spawn-clearance-and-reset-transaction.md) |
| 0029 | [0012](./0012-spawn-clearance-and-reset-transaction.md) |
| 0027 | [0013](./0013-ground-planning-path-contract.md) |
| 0056 | [0013](./0013-ground-planning-path-contract.md) |
| 0089 | [0013](./0013-ground-planning-path-contract.md) |
| 0092 | [0013](./0013-ground-planning-path-contract.md) |
| 0108 | [0013](./0013-ground-planning-path-contract.md) |
| 0109 | [0013](./0013-ground-planning-path-contract.md) |
| 0028 | [0014](./0014-task-fsm-and-scenario-transaction.md) |
| 0030 | [0014](./0014-task-fsm-and-scenario-transaction.md) |
| 0031 | [0014](./0014-task-fsm-and-scenario-transaction.md) |
| 0037 | [0014](./0014-task-fsm-and-scenario-transaction.md) |
| 0076 | [0014](./0014-task-fsm-and-scenario-transaction.md) |
| 0032 | [0015](./0015-jam-authorization-and-confirmation.md) |
| 0033 | [0015](./0015-jam-authorization-and-confirmation.md) |
| 0034 | [0015](./0015-jam-authorization-and-confirmation.md) |
| 0036 | [0016](./0016-episode-window-and-sample-validity.md) |
| 0038 | [0016](./0016-episode-window-and-sample-validity.md) |
| 0043 | [0016](./0016-episode-window-and-sample-validity.md) |
| 0078 | [0016](./0016-episode-window-and-sample-validity.md) |
| 0039 | [0017](./0017-time-budget-and-clock-sources.md) |
| 0047 | [0017](./0017-time-budget-and-clock-sources.md) |
| 0054 | [0017](./0017-time-budget-and-clock-sources.md) |
| 0040 | [0018](./0018-acceptance-and-coverage-matrix.md) |
| 0041 | [0018](./0018-acceptance-and-coverage-matrix.md) |
| 0046 | [0018](./0018-acceptance-and-coverage-matrix.md) |
| 0057 | [0018](./0018-acceptance-and-coverage-matrix.md) |
| 0049 | [0019](./0019-lifecycle-and-startup-robustness.md) |
| 0072 | [0019](./0019-lifecycle-and-startup-robustness.md) |
| 0080 | [0019](./0019-lifecycle-and-startup-robustness.md) |
| 0011 | [0020](./0020-package-boundaries-and-runtime-topology.md) |
| 0059 | [0020](./0020-package-boundaries-and-runtime-topology.md) |
| 0061 | [0020](./0020-package-boundaries-and-runtime-topology.md) |
| 0069 | [0021](./0021-w8-gui-headless-equivalence.md) |
| 0096 | [0021](./0021-w8-gui-headless-equivalence.md) |
| 0097 | [0021](./0021-w8-gui-headless-equivalence.md) |
| 0098 | [0021](./0021-w8-gui-headless-equivalence.md) |
| 0099 | [0021](./0021-w8-gui-headless-equivalence.md) |
| 0070 | [0022](./0022-w7b-research-propositions-and-decision-rule.md) |
| 0074 | [0022](./0022-w7b-research-propositions-and-decision-rule.md) |
| 0084 | [0022](./0022-w7b-research-propositions-and-decision-rule.md) |
| 0086 | [0022](./0022-w7b-research-propositions-and-decision-rule.md) |
| 0088 | [0022](./0022-w7b-research-propositions-and-decision-rule.md) |
| 0071 | [0023](./0023-w7b-adjudication-record-and-exit.md) |
| 0073 | [0023](./0023-w7b-adjudication-record-and-exit.md) |
| 0082 | [0023](./0023-w7b-adjudication-record-and-exit.md) |
| 0083 | [0023](./0023-w7b-adjudication-record-and-exit.md) |
| 0085 | [0023](./0023-w7b-adjudication-record-and-exit.md) |
| 0087 | [0023](./0023-w7b-adjudication-record-and-exit.md) |
| 0090 | [0023](./0023-w7b-adjudication-record-and-exit.md) |
| 0093 | [0023](./0023-w7b-adjudication-record-and-exit.md) |
| 0077 | [0024](./0024-w7c-multi-worker-isolation.md) |
| 0095 | [0024](./0024-w7c-multi-worker-isolation.md) |
| 0081 | [0025](./0025-publishing-boundary-and-retirement.md) |
| 0105 | [0025](./0025-publishing-boundary-and-retirement.md) |
| 0107 | [0025](./0025-publishing-boundary-and-retirement.md) |
| 0102 | [0026](./0026-leader-worker-collaboration-and-batch-authorization.md) |
| 0104 | [0026](./0026-leader-worker-collaboration-and-batch-authorization.md) |
| 0075 | [0027](./0027-uxrce-startup-reproducibility.md) |
| 0094 | [0027](./0027-uxrce-startup-reproducibility.md) |
| 0100 | [0027](./0027-uxrce-startup-reproducibility.md) |
| 0101 | [0027](./0027-uxrce-startup-reproducibility.md) |

## 相关

- 文档真源分层与稳定锚点 / 决策适用关系与引用纪律：[ADR-0002](./0002-docs-source-of-truth-and-reference-discipline.md#top)
- 新增 ADR 的写法：[`.agents/skills/domain-modeling/ADR-FORMAT.md`](../../.agents/skills/domain-modeling/ADR-FORMAT.md)
