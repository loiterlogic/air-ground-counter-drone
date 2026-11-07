<a id="top"></a>
# 裁定记录与出口闭合

## Status

accepted（2026-11-02 由 0071 / 0073 / 0082 / 0083 / 0085 / 0087 / 0090 / 0093 合并；P1 = `inconclusive`、P2 = `falsified` / 保留 c2、v7 未注册、已闭合，结论未变）

## 背景

的科研设计（命题 / 变量 / 对照 / 判定规则）由 [ADR-0022](0022-research-propositions-and-decision-rule.md#top) 承载。本篇记录**执行过程中产生的裁定与证据**：入口前置能力落地、火控占位升级带来的行为变更、臂定义与公平性修正、两轮 pilot 选场景、P1 / P2 的历次判定与修正、机制消融与负向诊断，最后是出口闭合与修复前溯源。

执行中反复出现的模式是：**一次 run 的结论往往被下一次审计推翻**（臂信息不等价、DV 被终态后停泊污染、火控状态机缺陷、地图签名伪触发）。因此本篇的原则是：**历史 verdict 逐字保留、标注污染来源、只让最后一轮可采信的判定作为现行结论**，而不是把旧数字删掉假装没发生。

## 决策

### (a) 入口前置能力 E1–E5 已落地（各有可复现 run）

| # | 能力 | 判据 |
|---|---|---|
| **E1** | raw / effective **同拍**归因 | 同拍配对 + 干预标注；shield=true 时 `intervened=276/439`、干预时长 13.09 s，shield=false 时 `intervened=0` |
| **E2** | **最小动态火控** | 完整射击闭环 + 逐帧与 GZ 真值位姿比对（`SHOT_FIRED` → 0.70–0.75 s 后 `CAPTURE_HIT`） |
| **E3** | 可见性度量按 **active 窗口** | 分母 = 窗口拍数（而非整段） |
| **E4** | `obs_version` **v2** | v1 **逐位**可回放；v2 = v1 + 4 维；元数据可区分，旧权重不静默失效 |
| **E5** | **离线数据集** | 条目带 `run_id` / `sha256`，可重建（mismatch=0） |

证据：`experiments/w7-rl-b/` 下对应 run（`e4-obs-versioning/metrics/e4.json` 等）。

### (b) 射击授权 = 任务决策，不自动开火

闭式包络占位与最小动态火控在「跟踪类」场景会给出**不同结局**（网的飞行使捕获可在车体抵达早前判据距离前发生），曾使 `s02` 由 `TRACKING_SUCCESS` 变为 `INTERCEPT_CONFIRMED`。

裁定：捕获裁决的**射击时刻**属**任务决策**，**非自动**—— 参数 `interception_authorized`（缺省 `false`，由场景按 `outcome` 轴覆盖：`capture` 场景授权，跟踪类不授权）。因此跟踪类场景结局不变（回归保持），`capture` 场景在授权下按动态火控判定。**不改**网 / 高度 / 适用参数（逐字沿用既有值），只把「何时开火」显式化为任务决策—— 这是「替换后冻结任务难度再训练」在本段的落地方式。

### (c) P1 臂定义：非协同臂 = 空中固定航迹

首轮 P1 曾出现**臂定义混淆**：两臂仅差 `observe_yaw_mode`，但都跑同一 `standoff_follower` 跟踪栈。非协同臂接管瞬间短暂获目标后丢失，触发 [硬约束 hc-10](0020-package-boundaries-and-runtime-topology.md#hc-10) 的「已获目标后不回落八字」hold → `vel=0` 停在空中、机头不再转动 → 目标永久出视场 → **自我锁死** → `MISSION_FAILED(TIMEOUT)`（实测冻结 42 s、yaw 冻结 −107.8°、目标方位差 ≈+140° 远超 FOV）。α 因此由「观测指向」退化为「能否持续观测」，结论偏乐观，该轮作废（产物保留为反例证据）。

修正后：

- `main.launch.py` 新增 `air_tracking_ref := on|off`（缺省 `on`，既有行为不变）；非协同臂取 `off`—— 把 `trajectory_tracker.tracking_ref_topic` 指向未使用话题 → tracker 永不 `acquired_` → 只飞基础 figure-8，**不**触发 hold。
- **不改**/ hold 语义（红线保持），只改「本臂是否喂入跟踪参考」。协同臂保持 `tracking_ref` on + `observe_yaw_mode=target`。
- 于是 α = {协同：跟踪 + 指向；非协同：固定航迹 + 不指向}，对齐命题的 α 定义；α 是**两项差异的组合**，属设计内。
- 修正后非协同臂 `vis_rate` 亦 ≈0.98—— 固定窗口口径下该 DV 在「早成功」臂上**饱和**，这直接促成了 DV 口径复核（见 (d)）。

### (d) P1 判定口径：固定窗口降为 legacy，active-window 为 primary

- 固定观测窗（`window_fixed_v1`，自首个 active 拍起 60 s）**不随终态截断**，约 92% 的 FCO 机会拍来自终态后停泊 ⇒ 该口径下 P1「成立」是**终态后停泊污染的产物**。P1 v4 起 primary 改为 `fire_control_opportunity_rate_active`（分母 / 分子只覆盖 `GROUND_APPROACH → 终态`），固定窗口量降为 legacy / 描述量。
- **失败 / infra / 缺值一律按 0 计入分母**（`keep_all_failures_and_infra`、`primary_honored=true`）；剔除对数须为 0；零填个数如实登记。
- **infra 单列**：终态 infra 与重试次数属机器特性，不计作臂效应（见 [ADR-0027](0027-uxrce-startup-reproducibility.md#top)）。
- **场景选择规则先于 pilot 写定**（防止「挑一个出效果的」）：新增候选场景，先以 3 seeds × 2 臂 pilot 观测「机制是否激活 + 任务是否可解」，按**机制层**判据选场景——① 可解性（协同臂 ≥2/3 达 `INTERCEPT_CONFIRMED`，且非协同臂 ≥1/3 达终态，避免「非协同臂完全失明」的退化场景）；② 机制响应（两臂 active 可见率之差 ≥ 10 pt，或非协同臂 active FCO 相对下降 ≥ 30%）；③ 优先级（都满足取改动更小的，都不满足则写「现场景族无法激活 α」的边界结论）。pilot 结果只用于选场景与估计 SD，**不作任何判定证据**。
- 两轮 pilot 的实际结局：linear 候选因 `rmax`（量程 > 12 m）+hold 自锁**几何崩塌**（协同臂 1/3，非协同臂反而 2/3 成功）；dropout 候选在 active 窗口几乎不降可见率（0.979 vs 0.979）而**机制未激活**；最终选 **`s15_static_none_fov_capture`**（static + 窄视场 30°/20°，active 可见率 0.359 vs 0.173，Δ≈+19 pt）。

### (e) P2 臂 B 先以规则高层承载（训练 RL 后置）

P2 的自变量是**职责分层**（命令权在高层还是端到端），不是学习算法；两臂训练 / 调参预算均为 0 时该自变量才可干净识别。故 P2 的臂 B 使用**现行规则高层**（目标预测拦截点 + 成熟低层 `Navfn` + 自研 LQR），**不先训练 RL**。

- **结论域收紧**：P2 结论**只**覆盖「职责分层 vs c2」，**不得**表述为「训练 RL 优于 c2」或「高层 RL 成立」。产物 `arm` 标识沿用 `p2_rl_high`（保持 run 身份可对齐），但报告 / 图表 / 裁定文档**必须**标注「规则高层」。
- **等预算口径**：训练 / 调参预算两臂均为 0；评估预算同场景 / 同 seed 集合 / 同 timeout / 同 episode 数；推理算力（B 多一层规划 + LQR）属**架构成本**，如实单列，**不**声称等算力。
- **训练 RL 的后置触发条件**（满足任一才启动，且须新预注册 + 两臂同等训练 / 调参预算）：① 规则高层在 P2 或消融中不达任务出口；② 后续 workstream 明确新的「学习 vs 规则」命题。**禁止**静默把臂 B 替换为训练策略—— 替换即新臂、新预注册、新证据。

### (f) P2 臂信息等价与 primary DV 修正

P2 v2 批次判定后被审计出两处缺陷，**不能**作为「职责分层 vs c2」的公平证据：

1. **臂信息不等价（致命）**：臂 A 的 c2 策略只订阅 `/agc/ground/goal`，不订阅 `/agc/targets`；`s08` 的 `goal_follow_target=false` 且固定目标与目标真值同点，`publishGoal` 在固定模式下与感知无关 ⇒ A 是**oracle 目标臂**，B 是**感知驱动臂**，「两臂只差命令源」不成立。
2. **primary DV 被终态后停泊污染（严重）**：v2 中约 97%（A）/ 100%（B）的机会拍发生在终态之后，实际测的是「任务结束后车停在包络里多久」，且被终态时刻驱动（`corr(Δfco, Δterminal_ticks) = -0.51`）。

修正（P2 v3）：

- **两臂信息等价**：统一 `goal_follow_target=true`—— 臂 A 的任务目标由 `task_manager` 按 `/agc/targets` 生成（与 B 同源感知目标），两臂都经同一安全层 / 唯一执行口，A 不再获得目标真值坐标。残余差异如实登记：`goal_hold_valid_s=1.0 s` vs 高层 `target_max_age_s=0.5 s`（方向不偏向 B）；`rl_high` 模式下低层仍消费 `/agc/ground/goal_info`，可能在高层的目标仍有效时被全局 `valid=0` 停车。
- **primary 改为 `fire_control_opportunity_rate_active`**：`episode_window_metrics.ticks_fire_control_opportunity / vis_ticks_total`，只覆盖 `GROUND_APPROACH → 终态`；固定窗口量降为 legacy，不参与判定。这是**新预注册版本**，不是事后改主量。
- **高层目标抖动修复（不改 IV）**：`air_fusion` 的 twist 是融合位置差分，单帧位置尖峰经 `lead_s` 外推后使目标点跳动 > `replan_displacement_m`，低层每帧重规划（实测 B 单回合 175 次「重规划触发：目标身份变」）。修法：高层取**置信度最高**航迹（不再 `front`）、目标位置 / 速度一阶低通（`target_tau_s=0.5`、断流 `target_gap_reset_s=1.0` 重置）、前向位移限幅 `max_lead_m=1.0 m`；仍为规则高层，不引入学习。复验后 175 → 11。

### (g) P1 2×2 机制消融（估计型，不改 verdict）

α 在实现上是两项开关的组合：`observe_yaw_mode ∈ {target, velocity}`（机头**指向**）与 `air_tracking_ref ∈ {on, off}`（空中**跟踪参考**）。原两臂同时改变二者，**无法归因**，故补 2×2：

| cell | `observe_yaw_mode` | `air_tracking_ref` | 臂名 |
|---|---|---|---|
| ① | `target` | `on` | `p1_coop` |
| ② | `velocity` | `off` | `p1_noncoop` |
| ③ | `target` | `off` | `p1_point_only` |
| ④ | `velocity` | `on` | `p1_track_only` |

- **先定规则**：同批四 cell 单 run、每 cell N=20、seeds 0–19、CRN 逐 seed 配对，**不**跨 run 拼 cell；分析为**估计型**（析因对比 + 置信区间），**不设门槛判定**；DV = **真实过程 FCO**（失败回合保留真实值、缺测配对剔除，**不等于**判定口径的失败置零）；pilot 先行（3 seeds × 4 cell）确认可承载。
- **预登记的已知风险**：cell ④ 会触发 [硬约束 hc-10](0020-package-boundaries-and-runtime-topology.md#hc-10) hold 自锁而退化；若退化，照实报告并把「跟踪主效应」只按 pointing=target 一侧解读，**不得**把退化 cell 当公平基线。
- **结果（80 episodes）**：**指向主效应** +0.0658（tracking=on，p=0.0019）与 +0.1347（tracking=off，p=5.6e-05）；**跟踪主效应**（pointing=target）**−0.0719**（p=0.011，跟踪参考无收益、反而降低 FCO）；tracking=velocity 侧 +0.0006（p=0.949，该侧退化严重）；**交互 −0.0667**（负交互）；对角总差 +0.0628。
- cell ④ 如预登记退化（4/20 捕获），其成功回合 FCO 0.094（n=4）说明该组合并非「无能力」，而是**任务成功率崩塌**。
- **诚实边界**：收益主要来自「指向」；「跟踪位置」在本场景（静止目标）无收益且在指向开启时有害，**限 s15 静止目标**，不得外推到移动目标；③ 的 FCO 优势（0.155 vs 0.083）**伴随更低的任务成功率**（15/20 vs 19/20），本消融的 DV 只有 FCO，**不** adjudicate 成功率。证据 `experiments/w7-rl-b/20261023-w7-rl-b-p1abl-n20/metrics/p1_ablation.{json,md}`。

### (h) P2 臂 B 负向诊断（只归因，不改 verdict）

用 v3 run 既有产物拆 B 的负向：B 的 active FCO 0.0571 vs A 0.1108；active 窗口 **41.2 s vs 16.4 s**（2.5×）；重规划 **23.7 次/回合 vs 0**；可见拍中包络占比 **0.0587 vs 0.1135**（腰斩）；安全层干预拍 901 vs 279、时长 34.2 s vs 12.5 s（**但按窗口归一化后单位时间干预密度仅高 ~16%，累计 3.2× 主要来自窗口更长**）；发射时 `pred` 与目标真值水平偏差中位相近（0.26 vs 0.20 m），但 **26%（10/38）的发射偏差 > 网半径 0.5 m**（最大 8.7 m），A 仅 8%。两臂 `min_clearance` 相当（4.73 vs 4.64 m），**不支持**「B 更危险」。

归因（按量级）：① 抵近过慢 + 重规划退化（窗口变长、包络占用被摊薄）；② 安全层持续纠偏；③ 发射质量重尾（在目标估计劣化时仍开火）。结论：B 的负向**可归因**，**不是**「分层架构必然更差」。**v3 判定不改写**；诊断**不得**以「调到 B 赢」为目标。

后续复核（不改判定，真值仅用于离线评估）：v3 的 8.7 m 离群在 `max_lead_m` 上限下**目标估计至少占 7.241 m**，不是高层 lead 或火控提前量；单航迹通道下 `tracks.front` 与「最高置信度」在构造上一致，无证据表明其为主因。3 seeds 定向 run 中 8.7 m **未复现**（6 发 `pred` 误差均值 0.221 m、>0.5 m 为 0/6），但样本量不足以推翻 v3。新发现的 miss 回合 `flight − t_est` 为 +1.21～+1.34 s，指向**火控状态机时序**而非估计精度。本次不建议加运行时一致性门（无正样本可评估区分力）。

### (i) 现行 verdict（只认最后一轮）

| 命题 | 现行结论 | 关键数字 | 状态 |
|---|---|---|---|
| P1（协同观测 > 非协同观测） | **`inconclusive`（未通过门槛）** | s15 active FCO **+0.0804**、CI [+0.0281, +0.1328]、p=0.0046；CI **覆盖** MME 0.10 | 方向与假设一致且显著，但未支持「收益 ≥ 10 pt」、也未排除之 |
| P2（规则高层职责分层 vs c2） | **`falsified`，保留 c2** | active FCO **−0.0561**、CI [−0.0971, −0.0151]、p=0.010 | 方向为负且显著，但效应量 < MDE 0.10 |
| P2 v2 批次 | **`confounded`** | — | 臂信息不等价 + 终态后污染，不作判定证据 |

- **P1 的三态读法**：CI 覆盖 MME ⇒ `inconclusive`——**不得**称「协同无效」（效应方向一致、显著），也**不得**称「收益达到 10 pt」；须并列报告点估计 + CI + 决断所需样本量（MME 0.10、σ≈0.112 时余量 0.03 → N≈109，余量 0.02 → N≈246）。
- **解释边界**：协同臂为**显式 oracle 指向臂**（`observe_yaw_mode=target` 的指向信息取真值方位），**测量**仍走真实感知通道（噪声 / 丢包 / FOV 照常生效）⇒ 结论限「oracle 指向条件下」，不涉真实检测 / sim-to-real。
- **P1 v5 的机制边界**：s15 下 active 可见率 0.473 vs 0.066（Δ≈41 pt），机制确被激活；但可见率并未等比例转化为火控机会（可见拍中包络占比 0.134 vs 0.227），故 +41 pt 可见率只换来 +8 pt 计分。
- 历史读法保留：fixed-window 的 +0.2988 与 s08 的 +0.0278 各为**其固定条件下的历史结论**，已被 active-window 口径取代，不再作为现行结论。

### (j) 不注册 v7、不进在线 RL

- **不注册 v7**：没有独立工程 / 科学理由降低 MME，也没有预先定义的任务成功率保障；诊断 run 未复现旧失败（`p1_point_only` 的 5 个超时 seeds 在 2026-10-24 诊断中多数转为捕获），不构成「仅指向足够」的新证据；不得仅为消除 `inconclusive` 而立项或投入上百对重跑。
- **MME 与历史记录不变**：MME 0.10、α=0.05、power=0.80、N=20 与三态判据不变；**不**因观测 0.0804 倒推门槛；所有历史 verdict 与 `executed_*` 字段保持原文（治理规则见 [ADR-0022](0022-research-propositions-and-decision-rule.md#top)）。
- **不进在线 RL**：P1 `inconclusive` + P2 `falsified` + 火控状态机缺陷未修 ⇒ 规则高层的后置触发条件未满足，维持「规则高层优先」。

### (k) 出口闭合与修复前溯源（pre-fix）

出口 = **命题卡 + 臂可运行证据 + 裁定文档**，**不含**论文级统计结论（属）。闭合状态：P1 v5 = `inconclusive`；P2 v3 = `falsified` / c2；P2 v2 = `confounded`；**v7 未注册、在线 RL 未进入、与未开始**。

**pre-fix 溯源**：全部 P1 / P2 确证 run、消融与诊断批次都在两项修复**之前**执行——① 火控在飞生命周期缺陷（[ADR-0011](0011-interception-and-fire-control.md#top)，`model_id=net_ballistic_frame_v2`）；② 移动目标 costmap marking 的地图签名口径（[ADR-0013](0013-ground-planning-path-contract.md#top)，签名只计静态层）。因此这些 run 的**射击 / 命中时序证据**受缺陷影响，P2 v3 的重规划计数还受旧签名口径影响（含 `NO_INFORMATION=255` 与 `INSCRIBED_INFLATED_OBSTACLE=253` 的伪触发）。历史 verdict 是**当时实现的判定**：**不**以修复后的小批 / 诊断结果重判，**不**改写任何 `executed_*` 字段，只追加溯源注记。

修复后的可用证据（不改变出口结论）：`test_dynamic_fire_control` 13 项全过；节点级生命周期检查 A–F 全过；lightweight E2 的 GUI / headless 各批 `SHOT_FIRED` 均有唯一终局、`flight` 在 1.30 s 级（≤3.15 s）、无千米级 `miss_dist`；整链小批在 infra 恢复后 6/6 shot 命中、`flight` 0.496–1.000 s。

### (l) 剩余消融的显式范围裁定

P2 侧「协同观测」与「目标预测」消融**未执行**，裁定：**不纳入出口，留待/ 新战役**。理由：① 在 B 臂内部再开关这两项得到的是**新假设 / 新臂**，不是对已注册假设的重读，不能改变已登记 verdict；② 修复前执行会被火控与地图签名缺陷污染，修复后执行则须**新预注册 + 新种子 + 重新规划 N**，不能与 v3 混用；③出口不是论文级机制消融全集；④ 若未来要主张「仅指向足够 / 协同观测足够 / 目标预测足够」，须同时提供**机会收益 + 预先定义的任务成功率保障 + 净空 / 干预指标**，并按实际判定规则重新规划 N。

## 不做什么（边界）

- 不让火控自动开火，也不按场景 outcome 直接改 `expected_terminal`（等于把模型升级掩盖为「基线调整」）。
- 不在轻量栈内伪造「协同」（无空中域即无协同，属静默假设）。
- 不把 P2 结论表述为「训练 RL 优于 c2」；不静默把臂 B 替换为训练策略。
- 不用诊断 run / 修复后小批重判 P1 / P2；不事后改 primary 或阈值。
- 不把 infra 失败混入成功率，也不把 cell ④ 当作公平基线。
- 不把「移动目标 marking 触发」与「火控状态机修复」合并为一次改动（每次只修一个原因）。
- 本篇**不产生新 verdict**，不修改任何判定 JSON 的结论字段。

## Considered Options

- **让火控自动开火（不改任务难度）** —— 被否：会使跟踪类场景结局漂移、回归破，且要求替换后冻结难度。
- **两臂都跑跟踪栈（只差 `observe_yaw_mode`）** —— 被否：会把「停机自锁」当作协同收益，命题失去可证伪性。
- **改 tracker 的 hold 行为（丢失后回落八字）** —— 被否：违反的自保语义，不得为实验方便而改。
- **先训练高层 RL / 两臂都训练 RL** —— 被否：违反规则优先顺序，无训练管线，「训练 vs 规则」使等预算无法定义，会把学习效应混入职责分层自变量。
- **保留 v2，仅补 active-window 敏感性 / 只修 DV 不改臂信息** —— 被否：信息不等价是臂构造缺陷，统计敏感性无法补救。
- **注册 v7（同场景新种子加大 N）/ 直接下调 MME 使 v5 变 `supported`** —— 被否：前者无独立工程理由且成本 5–10 h，后者是事后改门槛。
- **用 3-seed 定向 run 重判 P2** —— 被否：样本量不足，且受火控时序缺陷污染。

## Consequences

- **正面**：臂可运行、火控行为变更被显式裁定而非静默；两处污染（臂信息、窗口口径）在成为结论前被审计拦下；P1 的两项贡献可归因；「不进 RL / 不注册 v7」是显式裁定而非默认；剩余消融有范围裁定而非沉默跳过；历史 verdict 完整、修复前后以 `model_id` 明确分离。
- **代价 / 限制**：P1 停在 `inconclusive`、P2 停在 `falsified`，本篇未取得论文级结论；修复前 run 的射击时序不可与修复后直接混用；`p1_track_only` 退化使「跟踪主效应」只能单侧解读；P2 侧机制消融与整链小批留待。
- **未决 / 后续**：P2 侧协同观测 / 目标预测消融（须新预注册）；若主张「仅指向足够」须预注册 v7 + 新种子（seeds ≥ 20）+ 重新规划 N + 成功率保障；移动目标 marking 触发的独立处置；多 worker（[ADR-0024](0024-multi-worker-isolation.md#top)）；对照与冻结（[ADR-0021](0021-gui-headless-equivalence.md#top)）。

## 参考

- [ADR-0022](0022-research-propositions-and-decision-rule.md#top) 科研命题、度量口径与判定规则（含三态判据与 MME 治理）
- [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top) 地面控制栈（c2 现状）
- [ADR-0011](0011-interception-and-fire-control.md#top) 拦截与火控（在飞生命周期修复）
- [ADR-0013](0013-ground-planning-path-contract.md#top) 地面规划与地图签名
- [ADR-0027](0027-uxrce-startup-reproducibility.md#top) uXRCE 启动可复现性与 infra 重试
- [ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top) 实验产物与证据纪律（归档 manifest）
- 预注册单一来源：`src/agc_rl/config/research_prereg.yaml`；分析脚本：`scripts/research/w7b_p1_adjudicate.py`、`w7b_p2_adjudicate.py`、`w7b_p1_ablation.py`、`w7b_p2_arm_b_diagnose.py`、`w7b_p1_decompose_fco.py`
