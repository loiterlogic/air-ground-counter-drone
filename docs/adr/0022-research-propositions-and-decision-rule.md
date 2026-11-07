<a id="top"></a>
# 科研命题、度量口径与判定规则

## Status

accepted（2026-11-02 由 ADR-0070 / ADR-0074 / ADR-0084 / ADR-0086 / ADR-0088 合并；结论未变。其中「固定观测窗 + `mean ≥ MDE`」的判定口径已被后续 active-window primary 与三态 CI 规则取代，旧口径作废）

## 背景

出口是**可信实验平台**，算法 / 网络 / 奖励 / 训练步数 / 论文结论属 [ADR-0023](0023-adjudication-record-and-exit.md#top)。若不在实验前把「自变量是什么、因变量怎么量、什么算成立」写死，就会留下三处**隐式 ADR**：无法归因的协同收益、按占位包络训练的捕获奖励、事后拟合的判定规则。本组决策只做科研设计裁定（命题 / 变量 / 对照 / 前置能力 / 判定规则），不定算法与网络。

## 决策

### (a) 两条可证伪命题，各自**单一自变量**

| 命题 | 自变量（IV） | 固定条件 |
|---|---|---|
| **P1 协同收益（主线）** | **协同程度 α** = {空地协同策略, 非协同（地面单体 / 空中固定航迹）} | 同传感权限 / 速度约束 / 安全层 / 终态 |
| **P2 RL 职责分层（副线）** | **职责分层 β** = {臂 A: c2（RL 直接出 `cmd_vel`）, 臂 B: 高层 RL（拦截点 / 火控窗口 / 局部偏移 + 成熟低层控制）} | 固定为「协同」；其余同 P1 |

多变量不可归因，故每条命题只有一个 IV。主线必须是**协同**—— 把「用了哪种 RL」当主线等于以手段替代贡献。臂 A / 臂 B **同安全层、同唯一执行口、同预算**；裁定前默认遵守 c2（RL 主控，见 [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md)），不预断臂 B 胜出；任何臂**不得**在同一任务引入第二命令者。

### (b) 因变量：**分层多指标**，禁止单一成功率

- **主量**：任务出口（`TRACKING_SUCCESS` / `CAPTURE_NET`）；**超时一律失败**（[硬约束 hc-4](0020-package-boundaries-and-runtime-topology.md#hc-4)）。
- **辅量·捕获机会代理**：进入捕获包络的**停留时长**、**有效火控窗口时长**。
- **辅量·净空**：最小安全距离、碰撞率、shield **干预量 / 干预时长**（[硬约束 hc-9](0020-package-boundaries-and-runtime-topology.md#hc-9) 代理率）。
- **infra / 复位失败单列**，不吞入成功率（[ADR-0018](0018-acceptance-and-coverage-matrix.md)）。

**FCO（火控机会）门的定义**：`包络内 ∧ 目标可见`（`run_logger` 的 `evaluateTick`）；**净空是独立指标，不入此门**。这个定义决定了后续所有 FCO 口径的读法—— 包络占用由**地面路径**决定，可见由**观测指向**决定。

### (c) 观测窗口：固定时长窗口 `window_fixed_v1`

原 `visibility_metrics` 分母 = episode active 窗口（start → 终态），而两臂都约 16 s 达 `TRACKING_SUCCESS`，窗口**恰在「可见」时被截断** → `visibility_rate` 在早成功臂上饱和（协同 0.976–0.984、固定航迹非协同 0.986 → 无差），且含「成功需可见」的选择效应 → 据此判 P1 会出**假阴性**。

现口径（`definition_version = window_fixed_v1`）：

- **分母** = 自首个 active 拍起固定 `obs_window_s` 秒内的拍数，**不**随终态 / IDLE 截断；`run_logger` 参数 `obs_window_s` 缺省 **60.0**，单一注入 `base.yaml`（节点不得覆写）。
- `episode_runner` 在终态后**不立即拆除**，继续采到该固定时长（按**仿真钟**；上限仍受**墙钟看门狗**约束，超限如实早停并记 `obs_horizon_reached`）；CLI `--obs-horizon-s`（缺省 60.0）**须与 `obs_window_s` 同值**，否则窗口采不满。
- 同一 active 窗口口径的其它指标（`episode_window_metrics`）**保持不变**（`window_active_v1` 仍在，供逐窗对照，见 [ADR-0016](0016-episode-window-and-sample-validity.md)）。
- 阈值 / 样本量 / 显著性均未改动；口径版本化并记 `window_s`，新旧数值**不可逐值对照**。

### (d) P1 primary 改 active-window FCO（现行口径）

`window_fixed_v1` 的机会拍有约 **92%（协同）/ 86%（非协同）** 落在**终态之后**——fixed-window 的「成立」可能只是「任务结束后在包络里停了多久」的代理；而 P2 的 primary 已改 active-window，跨命题必须同口径。

现行 P1 预注册口径：

- **primary** = `fire_control_opportunity_rate_active`（`episode_window_metrics.ticks_fire_control_opportunity / vis_ticks_total`，窗口 `GROUND_APPROACH → 终态`，不含终态后停泊）；
- **secondary** = `min_clearance_m`（只报告，不参与判定）；
- **legacy** = `fire_control_opportunity_rate`（`window_fixed_v1`）降为**描述量**，不参与判定；
- **样本 / 显著性不变**：N=20 配对 / α=0.05 / power=0.80 / **MME=0.10**，不因观测到更小效应而下调；
- **臂定义不变**：`p1_coop`（`target` + `air_tracking_ref=on`）vs `p1_noncoop`（`velocity` + `air_tracking_ref=off`），同场景 / 同 seed / 同安全层 / 同终态。

同一 run 的双口径对照（说明差异的来源）：fixed `+0.2988`（CI [+0.1490, +0.4485], p=5.1e-04）vs active `+0.0561`（CI [−0.0070, +0.1192], p=0.097）；后续 clean-DV run 为 fixed `+0.2812` vs active `+0.0278`。

**历史不改写**：fixed-window 的旧判定作为**历史记录**保留、不删不改；两套口径并列报告。primary 的失败 / infra / 缺值按 **0 计入分母**（零填如实登记），N 与预注册一致。

### (e) 预注册与门禁

- 预注册（`research_prereg.yaml`）在**确证 run 之前**写定：预注册文件提交时间**早于** run 目录；承重实验**不得**事后改阈值。
- 判定由 `scripts/research/w7b_p1_adjudicate.py` / `w7b_p2_adjudicate.py` 按 `decision.<命题>` / `statistics.<命题>` 执行，脚本**不硬编码阈值**。
- 若需改以任务成功率 / 捕获时长 / 首次火控机会时间为决策终点，须**新预注册版本**（版本号顺延，不得复用已用版本）并重新匹配样本量与 MME；**禁止**事后改 primary。
- **门禁**：出口一的对照与冻结 **SHALL NOT** 在 P1 现行口径结果落盘前冻结 P1 结论；fixed / active 双口径数值、现行判定与证据 `run_id` 必须一并进入对照报告（[ADR-0021](0021-gui-headless-equivalence.md)）。

### (f) 判定规则：三态（CI vs MME），MME 与规划量**分列**

旧规则「双侧配对 t `p < α` **且** `mean(Δ) ≥ MDE=0.10`」把两个统计上不同的角色压在同一个数上：**样本量规划参数**（算出来的）与**判定门槛**（研究 / 工程意义的裁定）。后果是把「未能确认收益达到 0.10」误标成「真实收益低于 10 pt」——`证伪` 作为标签**过强**。

新版本预注册 **SHALL** 分列两个量：

| 量 | 字段 | 角色 |
|---|---|---|
| **最小有意义收益（MME / MCID）** | `decision.<命题>.minimum_meaningful_effect` | **决策门槛**，研究 / 工程意义的显式裁定，不随数据变 |
| **样本量可检测效应（规划量）** | `statistics.<命题>.planning.*` | **仅规划**，由 `(z_{1−α/2} + z_{1−power})·σ/√n` 计算 |

**判定三态**（只对 primary，按 95% CI 与 MME 的关系）：

| 判定 | 判据 | 含义 |
|---|---|---|
| `supported` | **CI 下限 > MME** | 收益**达到**最小有意义量 |
| `falsified` | **CI 上限 < MME** | 可**排除**「收益达到 MME」 |
| `inconclusive` | CI **覆盖** MME | 既未支持也未排除；须报告点估计 + CI + **决断所需 N** |

等价表述：`supported` ⇔ 95% **双侧** CI 下限 > MME ⇔ 对 MME 的**单侧检验** `p < α/2`（α=0.05 时 **0.025**，`H₀: Δ ≤ MME`），该单侧 p 一并报告；若改用**单侧 95% CI**（下限只留 5% 尾）才等价于 `p < α`。样本量公式仍按**双侧 CI** 口径用 `z_{1−α/2} + z_{1−power}`。secondary DV 仍只报告、不参与判定。

**`inconclusive` 是一等结果**：附「决断所需 N」，不得把「证据不足」误报为「效应不存在」，也不得读作「接近成立」。

### (g) 样本量规划（"可检测"≠"能通过门槛"）

```
n ≈ ((z_{1−α/2} + z_{1−power}) · σ / (Δ_true − MME))² （双侧 CI 口径）
```

以 σ≈0.112（配对差 SD）计，所需配对数只随**余量** `Δ_true − MME` 变化：

| 余量 | 0.02 | 0.03 | 0.04 | 0.05 |
|---|---|---|---|---|
| 配对数 n | 246 | 109 | 62 | 39 |

（每对 ≈ 2 episodes ≈ 3–6 min 墙钟 ⇒ N=100 量级 ≈ 5–10 h。）MME 越接近预期真实效应，决断所需 N **非线性增长**。

**"可检测"不等于"能通过门槛"**：N=20、σ=0.112 的 `detectable_effect_two_sided` ≈ **0.070**，那是「给定 α / power 能检测到非零效应」的最小量，**不是**「样本均值 ≥ MME」的通过概率。沿用 legacy `mean ≥ MME` 规则时，真实效应恰等于 MME 的通过概率仅约 **50%**；要达到 `power` 需 `Δ_true ≥ MME + z_{power}·σ/√N`。故**不得**用「N=20 可检测 ≈0.072」论证「能通过 0.08 门槛」。

### (h) MME 变更治理

- **禁止事后降门槛**：观测到的效应值（如 `+0.0804`）**不构成**把 MME 改成 0.08 的依据；无独立工程依据时**维持 MME=0.10**，并接受 `inconclusive` / `falsified` 作为结论。
- **版本号不得复用**：三态判据已占用一版；任何「降低 MME」的新版本须**顺延**（现行为 **v7**），不得复用该版号。
- **v7 立项须同时满足**：① 独立工程 / 科学价值说明，写在**新 run 之前**且**不以本次观测效应为理由**（说明为何更小的 FCO 提升在任务意义上值得主张，并给出可检验的预期量级）；② **新种子（种子隔离）**—— 不得复用参与过场景选择或判据调整的种子：s13–s16 pilot 用 seeds 0–2、P1 v5 用 seeds 0–19、P1 机制消融用 seeds 0–19 ⇒ v7 **SHALL** 用 **seeds ≥ 20**（或事先声明的另一组未用种子）并写入预注册；③ **按实际判定规则重新规划 N**（三态 CI 规则用 (g) 的公式；若仍用 legacy `mean ≥ MME` 则须满足 `P(mean ≥ MME) ≥ power`，即 `Δ_true ≥ MME + z_{power}·σ/√N`）；④ 新预注册写定 scene / arms / DV / MME / N / α / 种子集。
- **允许**：维持 MME=0.10 并加大 N 取得决断性结论（这不是改门槛，但须新预注册 + 新种子 + 按规则重算 N）；**不做** v7、保留 `inconclusive` 也是允许的默认路径。
- **禁止**：用新规则回溯改写历史 verdict；把「事后解读」当作判定证据。历史 verdict 字段保留原文，只**追加读法标注**。

### (i) 捕获奖励前置：最小动态火控

含「捕获机会 / 命中」的因变量 **SHALL** 先由**最小动态火控闭环**承载，替换闭式占位包络（可插拔抽象的 I/O 契约不变）。网的弹道在本节点逐帧积分（**非** GZ 物理刚体），「与 GZ 交叉核验」= 逐帧与 GZ 目标 / 车真值位姿比对。**替换后先冻结任务难度再训练**。**禁止**以占位包络训练后宣称「移动式主动拦截」。口径细节见 [ADR-0011](0011-interception-and-fire-control.md)。

### (j) 入口前置能力（先建、后实验）

- **E1** raw / effective 命令**同拍**记录：同一采样瞬时取安全层输入与输出快照，**如实标注** `header.stamp` 是否被安全层保持；记干预量 / 干预时长 / 实际净空 / 任务结果，并支持 with-shield 与**等预算**对照臂（纯仿真无 shield 臂须明标范围）。
- **E2** 最小动态火控裁决（见 (i)）。
- **E3** 可见性度量口径修复：按 active / 稳定任务窗口重算可见率、最长失联、恢复时长、有效火控机会（旧 `tgt_age` 未按任务窗口切分，分母失真）。
- **E4** `obs_version` v2：新增目标 **bearing / 相对速度 / 观测年龄**（yaw / 朝向交由确定控制器），并保留 v1 与旧权重回放。
- **E5** 离线数据集 / 回放库（由可复现 run 归档的轨迹构建）。

协同通道**复用**现空地仿真栈，不另建。

### (k) 臂与消融清单

1. **基线锚**：「**Navfn + 自研 LQR**」（复现既有证据；**不**称「Nav2 controller 完整配置」）。
2. **P1 两臂**：协同 / 非协同。
3. **P2 两臂**：c2 / 高层 RL。
4. **消融**：协同观测、目标预测、安全干预（with / without shield，等预算）。

每臂同传感权限 / 速度约束 / 安全层 / 终态语义。**本段不新增**「成熟 Nav2 controller 臂」（留对照冻结）。

### (l) 统计与配对协议、结论域边界

- 沿用**三级种子**（scene / episode / attempt）+ 六流（见 [ADR-0027](0027-uxrce-startup-reproducibility.md)）；配对比较用 **CRN**（外生五流不随 attempt 变）；预算复用三类口径（[ADR-0017](0017-time-budget-and-clock-sources.md)）；超时一律失败、infra 单列；报告**有效 episode 数 + 保留全部失败与 infra 总数 + 置信区间**；**不承诺** bitwise 物理一致，RTF 差异边界成文。
- 结论**仅对已验证通道族**（在独立噪声 / 共同偏置 / 突发丢包 / 延迟 / 乱序 / 假阳性 / 身份交换中**实际建模并验收者**）成立；**不得**据此声称真实检测或 sim-to-real；**GT 不进普通策略观测**，仅评估 / 显式 oracle 臂。
- **算法路径：离线优先**—— 先建离线数据集 / 回放库与规则臂；**仅当**规则基线在各消融下不达出口，才引入在线 RL（CPU / 单卡小网络预算内）。本段不锁网络细节、奖励与训练步数。
- **出口** = 命题卡 + 臂可运行证据 + 裁定文档，**不含**论文级统计结论（后者属冻结）。

## 不做什么（边界）

- **不**把「单一成功率」当唯一判据。
- **不**以占位包络训练捕获奖励。
- **不**在 run 后改 primary / MME / N / 种子集；**不**回溯改写历史 verdict。
- **不**把「可检测效应」当「通过门槛的概率」。
- **不**复用参与过场景选择或判据调整的种子（v7 起 seeds ≥ 20）。
- **不**把 `window_fixed_v1` 数值当现行 P1 结论（已降为 legacy 描述量）。
- **不**声称真实检测 / sim-to-real；**不**把 GT 放进普通策略观测。
- **不**在本段新增「成熟 Nav2 controller 对照臂」。
- **未实现 / 后续**：P2 消融、多 worker（[ADR-0024](0024-multi-worker-isolation.md)）、v7 立项与否、论文级统计冻结。

## Considered Options

- **以 RL 职责分层（β）为主线命题** —— 被否：系统论文主线是协同，以「用了哪种 RL」当主线是以手段替代贡献。
- **把可见性 / 安全干预并列成三条候选命题** —— 被否：它们更适为 P1 的受控子指标，并列会稀释主线承重。
- **以占位包络训练捕获奖励** —— 被否：学的是占位边界，结论不能用于主动拦截主线。
- **直接训 DQN / PPO 比成功率** —— 被否：那是「优化占位裁决」的陷阱，算法须由命题倒推。
- **保持 active 窗口口径、改用其它 DV** —— 被否（本段）：首获目标时延、最长失联同样受「何时终止」影响，而 P1 预注册的 DV 是火控机会率 / 净空。
- **换到移动目标场景以拉长窗口** —— 被否（本段）：支持的 capture 场景仅静态 s08；线性 capture 场景当时为 `unsupported:obstacle`。
- **让 episode 永远跑满墙钟看门狗** —— 被否：每回合固定约 200 s，代价高且改变时长语义。
- **不重跑、直接用旧 run 重算 active-window** —— 被否：新 primary 在数据已被观测后才写定，预注册强度不足。
- **保留 fixed-window 结论、只把敏感性写进限制** —— 被否：与 P2 的处置不一致，/ 论文会冻结一个已知被污染的主结论。
- **下调 MME 让结果更易通过** —— 被否：事后改阈值。
- **改臂定义（如两臂都关 `tracking_ref`）混入口径复核** —— 被否：臂定义变更属新命题 / 新预注册，留待 P1 消融。
- **维持「均值 ≥ MDE」** —— 被否：该式不是统计检验（未对抽样不确定性作推断），且混淆规划量与决策门槛。
- **只报 CI、不给判定** —— 被否：违背「预注册可判定」。

## Consequences

- **正面**：科研变量、对照、前置与判定**显式可判定**；DV 与「何时终止」解耦，消除饱和与选择效应；`inconclusive` 成为一等结果，避免把证据不足误报为效应不存在；P1 / P2 使用同一套 clean DV，跨命题比较恢复一致。
- **代价 / 限制**：每 episode 至少观测 60 s，run 墙钟变长；`obs_window_s` 与 `--obs-horizon-s` 必须同值；口径变更使新旧数值不可逐值对照（版本化 + note 标注）；只出证据与裁定、不出论文结论；最小火控 / 归因 / 可见性口径是**新增工程量**（E1–E5），先于任何策略对照；若要做 v7，成本按 N≈39–246 量级。
- **现行结论位置**：P1 / P2 的判定数值、机制边界与出口闭合见 [ADR-0023](0023-adjudication-record-and-exit.md)。

## 参考

- 拦截与火控口径：[ADR-0011](0011-interception-and-fire-control.md)
- episode 窗口统计与有效样本掩码：[ADR-0016](0016-episode-window-and-sample-validity.md)
- 时间预算口径：[ADR-0017](0017-time-budget-and-clock-sources.md)
- 验收判定与整链覆盖：[ADR-0018](0018-acceptance-and-coverage-matrix.md)
-冻结与对照：[ADR-0021](0021-gui-headless-equivalence.md)
- 裁定记录与出口闭合：[ADR-0023](0023-adjudication-record-and-exit.md)
- 种子协议：[ADR-0027](0027-uxrce-startup-reproducibility.md)
- 预注册真源：`src/agc_rl/config/research_prereg.yaml`；判定脚本 `scripts/research/w7b_p1_adjudicate.py` / `w7b_p2_adjudicate.py`
- 契约：[硬约束](0020-package-boundaries-and-runtime-topology.md#hard-constraints)、[终态语义](0014-task-fsm-and-scenario-transaction.md#terminal-semantics)、[参数入口](0020-package-boundaries-and-runtime-topology.md#params)
