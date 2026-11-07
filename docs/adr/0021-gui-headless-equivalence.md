<a id="top"></a>
# GUI/headless 等价、确定性探针与平台冻结

## Status

accepted（2026-11-02 由 ADR-0069 / 0096 / 0097 / 0098 / 0099 合并；结论未变—— 等价门仍 `not_evaluable_as_specified`、平台冻结仍 `conditional`、headless 规模统计仍未授权；模式等价设计一节按原文保留 `deferred` 状态说明）

## 背景

原写作"新旧实现同场景、同种子各跑 N 次；出对比报告；ROS1 归档只读"，把两个不同问题压在一起：**平台行为对照与冻结**、**修复后科研确证**；两者证据不可互替，后者须新预注册。同时平台侧的 **GUI / headless 等价门实际未通过**：初核只有 n=1 的成功 GUI，重跑数值差一个量级。按契约，headless 仅可用于规模统计，**前提是完成 GUI ↔ headless 等价核验**；不能用"差异检验不显著"代替"等价"。另一条约束：本机**没有**旧运行时，旧树内也没有旧 run 的 bag / 日志 / metrics，历史结论是文档固定样例验收（如 4/4、51/51）而非可重算总体估计 ⇒ live 新旧对照不可做。

## 决策

<a id="decision"></a>
### (a) 入口出口：第一出口是可信实验平台，不是算法成果

最小平台产出"语义正确、可复现、可被训练的环境 + 一致的 train / eval 协议"，验收锚 = 同 seed 可复现 / 指标齐全。**RL 算法、网络、奖励、训练步数、论文问题不在入口出口内**（属 [ADR-0022](0022-research-propositions-and-decision-rule.md#top)：先定可证伪命题，并先用规则策略证明任务非平凡且可达）。四件套：obs / action 版本化（`obs_version` + 归一化 + checkpoint 元数据 + 旧版本回放）、train / eval 终止与预算（复用三类时间预算口径，超时一律失败、infra 单列不吞）、种子分解（spawn / sensor / channel / target / policy / physics 分离 + 派生规则）、单 worker 可重放（多 worker 隔离属 [ADR-0024](0024-multi-worker-isolation.md#top)）。

训练环境 = 现-full +++拓扑，**不建**独立简化训练环境（headless / 降配只作为同一栈的参数化"训练视图"，差异写入 spec）—— 最致命的一类风险正是 train / eval 语义分叉。每条前置依赖**须**指向 `run_id` + 验收命题，**不**以"代码 / ADR 已记录"为满足。并行 / 向量化不在入口范围；包边界不动，仅在真实异步裁决（火控发射 / 命中）或多 worker 资源管理出现时按职责增包。

### (b) 出口分层：两个互不替代的出口

- **出口一：平台行为对照与冻结**：GUI / headless 模式等价（前置）→ 新旧行为对照（同场景、同 seed、
  [硬约束](../adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints) 的容差、终态语义一致）→ 平台冻结。
- **出口二：修复后科研确证**：在修复后平台上按**新预注册**重新检验 P1 / P2，遵循三态语义与 MME 治理。

本组只覆盖**出口一**；出口二未进入。历史 pre-fix 结论原样保留并标 `pre-fix`：P1 v5 = `inconclusive`、P2 v3 = `falsified` / 保留 c2、P2 v2 = `confounded`——**不改写任何 verdict**。

### (c) 模式等价：预声明设计、判定规则与执行闸门

- **pilot 预声明**：`src/agc_rl/config/gui_headless_plan.yaml`（version 1，`frozen_before_runs`，sha256 `3afa82c4…a292`）；P1 `s15_static_none_fov_capture` / `p1_coop` / seed 5、P2 `s08_static_none_nominal_capture` / `p2_rl_high` / seed 0，每场景每模式 5 次；固定 `backend=full`、普通单 worker、`--infra-retries 0`、`--obs-horizon-s 60`、`--timeout 240`、`--ready-timeout-s 180`、`--start-timeout-s 60`；**唯一差异**是 `--mode gui|headless`（gz `-r` vs `-s -r`，ROS 节点图相同），起始模式跨场景相反交替。每次 attempt 新 `run_id`，全部尝试保留（含 mission failure / timeout / infra），不重跑替代、不自动重试。pilot 只估 within-mode 散布与成本，**不是**等价判定。
- **结果口径**：逐 attempt 报终态 / `outcome_class`、active FCO、active 可见率、`env_occ|visible`、active 窗口、首次 FCO、首次包络进入、捕获时间、首发 / 射击数、最小净空、干预段数 / 拍比例 / 时长、RTF、墙钟、硬不变量。超时按契约算 mission 失败并留在分母；infra 单列；率类分母 = mission attempts；未发生事件记 `null` + `occurred=false` + occurrence rate，不插补。
- **判定**：`Δ = GUI − headless`；等价 iff 95% 双侧 CI **完全落入** `[−δ, +δ]`（等价检验，报两个单侧 p）。**禁止**以"差异检验不显著""CI 覆盖 0""pilot Δ 小"代替等价。co-primary（全部须通过）：active FCO、active 可见率、超时率、捕获成功率；secondary：首次 FCO、捕获条件时间、最小净空（GUI 非劣）、干预拍比例 / 段数（GUI 非劣）、RTF / 成本（描述）。δ 候选锚点：FCO / 可见率 0.02、率类 0.05、时间 2 s、净空 0.20 m、干预比例 0.05。样本量 `n_per_mode = ceil((z_0.975 + z_0.80)^2 (σ_GUI^2 + σ_headless^2) / (δ − |Δ_pilot|)^2)`，多 co-primary 取最大 n；`|Δ_pilot| ≥ δ` 判为在该 δ 下不可行；成本上限每场景每模式 ≤40 attempts 且每场景正式墙钟 ≤6 h。plan v2 须在 pilot 后冻结，**不得**在正式结果后回填 / 放宽 δ 或 n。
- **闸门**：**go** = 每场景 / 模式至少 3 个有效 mission attempts、`|Δ_pilot| < δ`、n ≤ 成本上限。**pass** = 全部 co-primary 的 CI 落入 ±δ、secondary 无未解释 material difference、infra 率不高于预声明上限、硬不变量无缺陷 ⇒ 授权 headless 用于规模统计，产物标 `backend` / `mode`，GUI 定性 / 关键场景验收仍保留。**fail / 不可行** = **不**授权，定位模式差异（RTF / 渲染 / 调度 / 启动时序）或改用 GUI 完成验证并记录成本，**不静默切换**。
- **infra 单列**：`cmd_vel_loopback_missing`（ground lifecycle 未 activate、240 s、0 shot）是独立 infra 项，**不归因于** GUI / headless 或隔离栈；单 worker 若复发先判系统性，反复出现则专项排障，不继续扩容。

**deferred**：本节的正式等价设计**至今未执行**—— 原因是 GPU-GUI 修正后 pilot 仍 `feasible=false`（δ≤0.05、n≤40/模式下不可判定），且下一步须先做范围裁定；因此 headless 规模统计未获授权、plan v2 未冻结。这与"方案不可行"不是一回事。

### (d) GUI 渲染后端：项目默认 GPU-GUI，但只是部署默认

`gui_render_backend=auto|d3d12|software`，默认 **`auto`**；只在 GUI（`gz sim -r`）生效，headless 忽略。注入点为 `main.launch.py` → `world_bringup.launch.py` 的 gz 启动前 `SetEnvironmentVariable`，选择逻辑单一来源 `src/agc_sim/launch/gui_render_backend.py`。**`auto`**：WSL2（内核串含 `microsoft`/`wsl`）+ `/dev/dxg` + X11（`DISPLAY` 含 `:`）→ 注入 `MESA_LOADER_DRIVER_OVERRIDE=d3d12` + `GALLIUM_DRIVER=d3d12`；原生 Linux 保持系统默认 GL；无 `/dev/dxg` 或非 X11 不强行 D3D12。**`d3d12`**：显式强制 Mesa D3D12 + X11（不支持时 GUI 可能起不来）。**`software`**：显式强制 llvmpipe（`LIBGL_ALWAYS_SOFTWARE=1` + `MESA_LOADER_DRIVER_OVERRIDE=swrast` + `GALLIUM_DRIVER=llvmpipe`）。

**实际 renderer 必须逐 run 记录**：`episode_runner` 在 GUI 启动前记 OGRE 日志游标，启动后 / 结束后只解析**本 run 窗口内**新增的 `Device Name` / `GL_RENDERER`，写入 `arms.json` 与`attempts.json`；读取失败 / 轮转 / 多值 → `null` + 状态，**不以批次 `render_backend` 回填**。plan v1 固定 `software`、plan v1.1 固定 `d3d12`，使默认 `auto` 不会让历史 pilot 条件漂移。

<a id="redo"></a>
### (e) 确定性探针：固定 seed 仍存在执行级散布

对同一场景 / seed / 模式（`s15` / `p1_coop` / seed 5 / `backend=full` / `mode=headless`）做 n=5 探针。首批 5 个有效 attempt 的 active FCO 为 `0.000000, 0.007163, 0.000000, 0.001958, 0.076797`（极差 **0.076797**），active window 长度 `120.028, 23.224, 120.096, 85.108, 20.296 s`（极差 **99.800 s**）；重核原始整数计数与窗口边界后数值一致。

**独立重做与判据勘误**：原评审的"spread 在 0.0–0.27"与"spread <0.01"重叠，故重做前先冻结互斥判据——`<0.01` 记为分辨率内可重复；`0.01 ≤ spread ≤ 0.27` 为**观察到执行级散布**；`>0.27` 为超出参考范围；样本不足或缺测不判定。n=5 是描述性诊断，**不是**等价检验或因果识别。旧报告还有遗漏：两次无 arms 的沙箱启动失败与一次目录已存在拒绝启动未登记，且无法从现存证据恢复完整运行前计划与全部启动参数，不能只靠 scene / seed 标签声称条件已核验；旧报告与原件保持只读，新批次独立记录，**不合并样本**。

重做（`20261026-w8-p1-redo-r2`）：5 个有效 mission attempts、5/5 `INTERCEPT_CONFIRMED`、批次内 infra=0；active FCO 极差 **0.071010**（min `0.003003` / max `0.074013`）、窗口长度极差 **33.484 s** ⇒ 按冻结判据为 `execution_level_variability_observed`，与旧证据方向一致；5/5 捕获也说明窗口散布不只来自成功 / 超时类别切换。结果不外推至其它场景 / seed / 模式。

**结论**：`δ=0.02` 的等价目标在这套测量规格下停止推进，gate 记为 **`not_evaluable_as_specified`**——**不得**记为平台 fail 或跳过。仅凭窗口差异不能归因为调度，也不能证明某一等价界限在数学上不可达。下一规格候选为同 seed 复现率、或与终态无关的固定窗口 / 更长观测；**具体指标、窗口长度、容差及预算由 (g)(i) 裁定**。

<a id="measurement-amendment"></a>
### (f) 测量 P2 修订边界：co-primary 集合被取代

未来设计中的 co-primary 集合由 (i) 取代：**固定预算任务 FCO、完整任务捕获成功率、超时率**为 co-primary，active FCO / 可见率降为 secondary。旧计划与既有产物**不回写**；P3 须先实现新记录器，再预声明新设计、界限、n 与成本。当前**不执行**历史设计中的 go 规则，**不授权** headless 规模统计。

<a id="metric"></a>
### (g) 固定预算任务 FCO 的度量口径（`mission_fco_fixed_budget_v1`）

- `t0` = 首个 `GROUND_APPROACH` 状态转换的仿真时刻；缺少可验证转换则不可计算，**不用**首个 logger timer 拍代替。
- 固定评估预算 **T=60 仿真秒**，区间 `[t0, t0+T)`；这是**任务机会预算**，沿用既有 60 s 尺度，**并非**声称所有任务能存活 60 s，也非据结果选择一个短于最短回合的新窗口。
- `τ` = 该任务首个已确认 mission 终态时刻；`I_FCO(t)` 沿用现有"新鲜目标可见且新鲜包络内"的布尔谓词及参数，须记录各源时间戳与实际新鲜度阈值。
- `fco_exposure_s = ∫[t0,t0+T) 1(t<τ) I_FCO(t) dt`；`mission_fco_fraction = fco_exposure_s / T`。单回合取值 `[0,1]`，跨回合等权，**禁止**把所有回合拍数合并成总比例。到达 T 仍未终态时**只关闭测量积分**，任务照常继续至场景原有预算，不把 T 当超时，也不更改捕获 / 失败裁决。

语义边界：终态后的剩余预算是"任务已结束、无新的任务机会"，按定义贡献 0（这与"传感器缺测填零"不同）；已确认早终态无需为测量继续物理仿真到 T，但须记录终态证据与 `post_terminal_budget_s`；终态前的真实机会**不因任务最终失败被抹零**；`ABORTED` / infra 不静默当作正常早终态，须单列原因与可计算性。该指标是**任务结束前累计可用机会占预算的比例**，不是持续跟踪能力或捕获效率—— 早捕获会缩短积累机会的时间、可能使该值更低，此权衡不能靠分母固定消除；必须联合完整任务成功率与超时率解释，**不能单独用 FCO 高低判断系统优劣**，也不与科研 P1 / P2 原 DV 混读。

<a id="missing"></a>
### (h) 时间权重、缺测与记录要求

积分必须按**仿真时间**加权，不能把 `ticks_fire_control_opportunity / window_s` 当 FCO/s（那是受 timer 频率影响的"采样拍/秒"）；`FCO_seconds / active_window_s` 仍有终态相关分母，也不采用。实现须记录 `t0`、τ、T、逐区间起止仿真时间、各源时间戳、FCO 谓词及其已知性；区间跨新鲜度到期时刻、终态或 T 时必须截断，**不得跨长间隙无限前向保持**。源过期而监听链仍正常是可观测的"不可用"，按既有谓词计 0；logger 掉线、时钟回退、源流 / 终态证据无法核验则属**测量缺失**。

记录 `known_preterminal_s`、`missing_preterminal_s`、`post_terminal_budget_s`，三者须覆盖固定 T，时序或覆盖不一致则拒绝计算。存在未知区间时点估计为 `null`，同时给出 `[known_fco_s/T, (known_fco_s+missing_preterminal_s)/T]` 识别界，**不能删除缺测回合再宣称等价**；缺测纳入等价门的完整性审查，识别界如何用于保守推断或触发不判定须在 P3 预声明，**禁止事后决定**。现有 summary 只有聚合计数，本次**不重建**历史新指标；未来实现须新增带版本的独立字段，保留 `visibility_metrics` / `episode_window_metrics` 原语义。发布前用"早成功、晚成功、超时、终态后停泊、非均匀采样、长间隙 / 缺测、时间回退"做确定性验证，再做 GUI 关键验证—— 不能仅改 YAML 指标名。

<a id="endpoints"></a>
### (i) 等价门的指标集合

| 地位 | 指标 | 分母 / 角色 |
|---|---|---|
| co-primary | `mission_fco_fraction` | 固定 60 仿真秒；定义见 (g) |
| co-primary | 捕获成功率 | 完整任务的全部 mission attempts，含失败；不按捕获者筛选 |
| co-primary | 超时率 | 同一组全部 mission attempts；超时按既有契约裁决 |
| secondary | active FCO、active 可见率、`env_occ_given_visible`、首次 FCO / 捕获条件时间 | 过程解释；不单独宣布等价 |
| 安全 / 完整性门 | 净空、干预、`shield_infeasible_rate`、`reset_failure_rate`、infra / 缺测率 | 沿用原定义；界限由 P3 预声明 |

率类分母是任务数：其**值**依赖终态，其**分母**不依赖成功 / 超时类别。co-primary 之间可以相关，"全部通过"不要求彼此统计独立；只有捕获 / 超时两类结果时两率互补，P3 应识别冗余而非当作独立证据。active 可见率降为 secondary 是测量目的裁定，**不能**解释成由某个已观察方差证明任何预算下都不可能等价。

<a id="next"></a>
### (j) 出口状态与 P3 待办

gate 仍为 **`not_evaluable_as_specified`**；headless 规模统计**未授权**；出口二未进入；仍 `deferred`。P3 需：实现并验证上述记录器；预声明新 seed 网格及 seed 内执行重复如何建模；选择等价界限、缺测规则及适用的多指标推断方法；重新规划 n 与成本，明确解决旧设计中容差 / n 上限 / 公式的冲突。旧 n 公式与 pilot 差值门**不因本组获得新的有效性**。本组不冻结 plan v2、不启动新 pilot / 正式等价、不授权在线 RL。

### (k) 历史证据对照与条件平台冻结（旧环境不可重建）

不执行 live 新旧对照，只对照**可比行为事实**、明确列出**不可比项**，对新平台做 **conditional freeze**。

**可比 / 可冻结（行为事实）**：① `/agc/` 命名空间、`agc_world` 唯一基准、`drone/base_link` / `car/base_link`（禁止裸 `base_link`）；② `task_manager` 单一任务状态机，`TRACKING_SUCCESS` = "抵近并持续跟踪"，不得表述为"拦截完成"；③ 超时一律算失败，只有显式完成才算成功；④ 每 episode 轨迹相位复位到 t=0、`/use_sim_time=true`；⑤ 评估报告含 `shield_infeasible_rate` / `reset_failure_rate`；⑥ 尝试记账 `attempted = valid_task + infra_failure + aborted`、`valid_task = tracking_success + mission_failure`，固定样例（4/4、51/51）**不代表**总体成功率。

**不可比 / 不得做数值对照**：① 中间件 / 仿真器 / 飞控不同（旧 Noetic + Gazebo Classic + MAVROS + `iris_3d_lidar` vs 现 Jazzy + GZ Harmonic + uXRCE-DDS + `px4_msgs` + `gz_x500`）；② 终态集合不同—— 旧阶段 A **禁用** `INTERCEPT_CONFIRMED`，当前阶段 B 启用（`CAPTURE_NET` / 行为级干扰），旧"成功率"与当前"捕获率"不是同一口径；③ 安全阈值绝对值（旧 `0.7 / 0.9 / 2.4 m` 作废，现 `1.0 / 2.0 / 4.0 m`），顺序不变量可比、绝对值不可比；④ 出生净空旧 `2.4 m` 作废；⑤ RL 栈不同（旧 DQN / 33 维 LiDAR vs 现 `agc_rl`）；⑥ 指标只可映射定义、不可对照数值；⑦ 场景集不同（旧固定场景 vs 现 12 场景登记表）；⑧ 历史 98–100% 成功率是探索性结果（单策略种子、少量布局、LiDAR 代理碰撞），**不得**与当前正式结果混合汇总。

**不可比 / 无证据**：本机无旧运行时；旧树内无 bag / 日志 / metrics；历史结论是文档固定样例验收而非可重算总体估计；无同物理 / 同中间件控制变量。同源教训是**未证实归因不得当结论**—— 历史材料缺失时只登记「未证实」、不进入任何结论；高度与坐标系口径同理必须统一到**世界 ENU** 表达，不允许参考 / 机体估计 / 世界真值三个口径混用（缺陷清单与取证见 [ADR-0008](0008-air-trajectory-and-tracking-calibration.md#top)）。

**冻结**：范围 = 当前契约（9 消息 / 服务、命名空间、坐标系、终态语义、唯一执行口、安全层、–）。`gui_render_backend=auto` 是**部署默认、非冻结条件**—— 会随机器自动选择或回退；冻结的是**选择逻辑**与"实际 renderer 必须逐 run 记录"这一证据要求，`auto` 本身不代表 GPU 生效。冻结状态 **`conditional`**：可比行为事实冻结，**live 新旧 parity = `not_established`**。**不做**：不冒充"新旧等价通过"；不把历史固定样例当总体成功率；不复活 MAVROS；不复制旧树代码 / 目录 / 命名（旧树归档已于 2026-10-31 整体退役删除，见 [ADR-0025](0025-publishing-boundary-and-retirement.md#top)，此前引用旧树路径的记录按"只追加、不改写"保留）。**重新开启条件**：若获得可运行旧环境或可信旧 run 产物，另立对照任务按同场景 / 同 seed / 同口径重做。

## 结果

- **pilot（软件 GUI）**：20 个预声明 attempt。P1 headless 3 capture + 1 `MISSION_FAILED(TIMEOUT)` + 1 `INFRA_FAILURE(clock_not_progressing)`；P1 GUI 4 capture + 1 `INFRA_FAILURE(reset_failed)`；P2 headless 5 capture；P2 GUI 4 capture + 1 `INFRA_FAILURE(cmd_vel_loopback_missing)`。active FCO 描述性差 P1 Δ=−0.0660（CI [−0.234, +0.103]）、P2 Δ=−0.0268（CI [−0.123, +0.069]），within-mode 散布很大 ⇒ 按候选 δ 两场景均 `infeasible`。
- **渲染后端诊断**：默认 GUI 走 **llvmpipe 软件渲染**（`Device Name: llvmpipe (LLVM 20.1.2, 256 bits)`、`GPU Vendor: unknown`），`gz sim` CPU 267–281% vs headless 22%；强制 D3D12 + X11 后 `GL_RENDERER = D3D12 (NVIDIA GeForce GTX 1050 Ti)`、GPU util 16–18%、整链 RTF 0.80–0.87；Wayland + D3D12 失败（`failed to create dri2 screen`），本机 GPU-GUI 只能走 X11。⇒ 软件渲染 + CPU 争抢是**已确认的性能混杂**，pilot 的 `mode` 变量同时混入"渲染后端 + CPU 负载"，其数值**不能**直接用于冻结 δ / n，也**不能**读作语义不等价。
- **GPU-GUI 修正 pilot（plan v1.1）**：20 attempts，GUI 侧 renderer 均为 `D3D12`。RTF 已对齐（P1 Δ=−0.0067，CI [−0.0298, +0.0165]；P2 Δ=−0.0084，CI [−0.0216, +0.0048]），但结果散布仍主导（P1 active FCO Δ=+0.0397、P2 Δ=+0.0284）；按候选 δ，P1 率类所需 n≈**1256/模式**、P2 率类 `|Δ|=0.4` ⇒ **两场景 feasible=false**。
- **正式等价未执行**：软件渲染混杂已由 GPU-GUI 修正，但修正后 pilot 仍 `feasible=false`（δ≤0.05、n≤40/模式下不可判定）；下一步须先做范围裁定（配对臂差 / 模式作协变量、GUI 完成关键验证、扩大预算或换平台），裁定前**不冻结 plan v2**。
- **测量 P2 的历史边界**：只读审计 40 个历史 pilot attempts + P1 重做 5 次，41 个有 active 窗的有效 mission 中 **35 个 active 窗短于 60 s（最短 10.316 s）** ⇒ 评审所述"最短约 72 s"不能作为 active 窗内固定 60 s 的依据，必须对齐首个 active 时刻。P2 v3 配对的只读复算（原配对 n=20、B−A=−0.056082、CI [−0.097101, −0.015063]；剔除 degraded 的事后敏感性 n=17、CI 上限约 −0.0065）**不替代**预注册判定，不重开预注册、不改 adjudication 原件。
- **证据**：`experiments/w8-parity/20261025-w8-gui-headless-pilot/metrics/gui_headless_pilot.json`、`.../metrics/gpu_renderer_diagnosis.json`、`experiments/w8-parity/20261025-w8-gui-gpu-pilot/metrics/gui_headless_pilot.json`、`experiments/w8-parity/20261026-w8-p1-determinism-probe/metrics/probe.json`、`experiments/w8-p1-redo/20261026-w8-p1-redo-r2/metrics/probe.json`、`experiments/w8-parity/20261026-w8-measurement-p2/metrics/audit.json`、`experiments/w8-parity/20261025-w8-historical-parity/metrics/comparison_matrix.json`。

## 不做什么（边界）

- 不授权 headless 规模统计；不进入出口二；不注册 v7；不进入在线 RL；保持 `deferred`。
- 不把 `not_evaluable_as_specified` 记为平台 fail 或跳过；不用"不显著"代替"等价"。
- 不在正式结果后回填 / 放宽 δ、n 或窗口长度；不删除缺测回合再宣称等价；不重建历史新指标。
- 不冒充新旧等价通过；不复活 MAVROS；不复制旧树代码 / 目录 / 命名；不把历史固定样例当总体成功率。
- 不以 `auto` 代表 GPU 生效；不以批次 `render_backend` 回填逐 run renderer；不把 infra 归因于模式或隔离栈。
- 不在入口阶段引入 vectorize / 重构包边界；不为直接绑定算法或论文成果。

## Considered Options

- **直接绑定算法 / 论文成果** —— 被否：主线是系统论文、RL 为手段，会把未定科研问题写成隐式 ADR。
- **另建专用训练环境** —— 被否：语义分叉 + 转移验证成本高。**前置以"ADR 已记录"为准** —— 被否：与"实现已改 ≠ 证据已复现"矛盾。**现在就 vectorize / 重构包边界** —— 被否：成本高、收益未证。
- **用单次 GUI/headless 对比代替等价检验** —— 被否：n=1 的成功 GUI 已实测不可复现，"不显著"不能顶替等价。
- **继续硬跑正式等价** —— 被否：修正后 pilot 仍 `feasible=false`，应先做范围裁定。
- **复活旧环境做 live 对照** —— 被否：本机无旧运行时、旧树无运行产物；范围缩为历史证据对照 + 条件冻结。

## Consequences

- **正面**：本篇的两个问题不再混用证据；等价判定从"单次对比"升级为预声明等价检验；headless 规模统计有明确授权条件；infra 不再被误读为模式效应；平台冻结有明确的可比 / 不可比清单，避免用异构物理 / 终态差异伪造"迁移等价"。
- **代价 / 限制**：pilot 至少 20 次整链 run，正式等价可能需要更多；GUI 墙钟与环境噪声可能使等价不可判定，需回退到 GUI 验证并记录成本；原始 live 对照目标未达成，若后续需要真实新旧数值对照须重建旧环境或取得可信旧产物。
- **风险**：conditional freeze 容易被误读成"本平台已通过"—— 相关记录必须显式写 `not_established`。

## 参考

- 契约：[#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints)、[#terminal-semantics](0014-task-fsm-and-scenario-transaction.md#terminal-semantics)、[#execution-port](0020-package-boundaries-and-runtime-topology.md#execution-port)
- 相关决策：[ADR-0024](0024-multi-worker-isolation.md#top)（单 worker 与扩容准入）、[ADR-0022](0022-research-propositions-and-decision-rule.md#top)（三态判据与 MME 治理）、[ADR-0023](0023-adjudication-record-and-exit.md#top)（pre-fix verdict）、[ADR-0027](0027-uxrce-startup-reproducibility.md#top)（启动协议与错峰）、[ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与证据纪律）、[ADR-0018](0018-acceptance-and-coverage-matrix.md#top)（GUI 验收范围）、[ADR-0025](0025-publishing-boundary-and-retirement.md#top)（旧树退役）
- 计划与规格：`src/agc_rl/config/gui_headless_plan.yaml`、`gui_headless_gpu_plan.yaml`、`docs/archive/specs/w8-parity-freeze/spec.md`、`docs/archive/specs/w8-measurement-p2/spec.md`
