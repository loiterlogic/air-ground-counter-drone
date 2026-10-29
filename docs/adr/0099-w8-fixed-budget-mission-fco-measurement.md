<a id="top"></a>
# W8 测量 P2：固定预算内的任务 FCO 与终态处理

## Status

accepted（2026-10-26：指标语义裁定完成；记录器实现与新执行计划尚未冻结，归属 P3；gate 仍为 `not_evaluable_as_specified`）

<a id="context"></a>
## 依据与适用范围

用户授权在前置满足后执行测量 P2。[P1 独立重做](0098-w8-determinism-probe-and-measurement-spec-change.md#redo) 已完成；规格见 [P2 spec](../archive/specs/w8-measurement-p2/spec.md#scope)。契约仅引用 [硬约束](../ROS2迁移交接文档.md#hard-constraints) 与 [终态](../ROS2迁移交接文档.md#terminal-semantics)。

本裁定只取代 [ADR-0096](0096-w8-gui-headless-equivalence-design-bounds-and-gate.md#measurement-amendment) 中未来 W8-E1a 等价设计的指标集合及定义；旧计划、历史分析及科研命题的 DV 保持原样。

先检查本项目同版本已运行实现：[`run_logger.cpp`](../../src/agc_task/src/run_logger.cpp) 的 `evaluateVisibility()` 同时累计 active 拍比例和终态后仍继续的 `window_fixed_v1`。后者由 [ADR-0074](0074-visibility-metric-fixed-observation-window.md#top) 定义，会包含终态后停泊；两者均不能直接改名为下述新指标。`obs_horizon_s=60` 也不是“终态前至少运行 60 秒”的保证。

只读审计 40 个历史 pilot attempts + P1 独立重做 5 次：41 个有 active 窗的有效 mission，**35 个 active 窗短于 60 s，最短 10.316 s**。因此评审所述“最短约 72 s”不能作为 active 窗内固定 60 s 的依据；必须对齐首个 active 时刻，不能使用含预热的总时长。输入路径、哈希及 C9 两项见 [audit](../../experiments/w8-parity/20261026-w8-measurement-p2/metrics/audit.md) / [JSON](../../experiments/w8-parity/20261026-w8-measurement-p2/metrics/audit.json)。

<a id="metric"></a>
## 裁定：固定任务预算内累计机会时间

新定义版本 **`mission_fco_fixed_budget_v1`**：

- `t0` 为首个 `GROUND_APPROACH` 状态转换的仿真时刻；缺少可验证转换则不可计算，不用首个 logger timer 拍代替。
- 固定评估预算 **T=60 仿真秒**，区间 `[t0,t0+T)`；这是任务机会预算，沿用既有 60 s 预算尺度，**并非**声称所有任务能存活 60 s，也非据结果选择一个短于最短回合的新窗口。
- `τ` 为该任务首个已确认 mission 终态时刻。`I_FCO(t)` 沿用现有“新鲜目标可见且新鲜包络内”的布尔谓词及参数，须记录各源时间戳和实际新鲜度阈值。
- `fco_exposure_s = ∫[t0,t0+T) 1(t<τ) I_FCO(t) dt`；`mission_fco_fraction = fco_exposure_s / T`。单回合取值 `[0,1]`，跨回合等权，禁止把所有回合拍数合并成总比例。
- 到达 T 仍未终态时，关闭**测量积分**，任务照常继续至场景原有预算，不把 T 当超时，也不更改捕获/失败裁决。终态结果另按原场景完整任务预算统计。

终态后的剩余预算是**任务已结束、无新的任务机会**，按定义贡献 0；这与“传感器缺测填零”不同。已确认早终态无需为了测量继续物理仿真到 T；必须记录终态证据和 `post_terminal_budget_s`。终态前的真实机会不因任务最终失败被抹零。`ABORTED` / infra 不静默当作正常早终态，须单列原因与可计算性。

这是**任务结束前累计可用机会占预算的比例**，不是持续跟踪能力或捕获效率。早捕获会缩短积累机会的时间，可能使此值更低；这一权衡不能靠分母固定消除。必须联合完整任务成功率和超时率解释，不能单独用 FCO 高低判断系统优劣。该新 estimand 不与科研 P1/P2 原 DV 混读。

<a id="missing"></a>
## 时间权重、缺测与记录要求

积分必须按仿真时间加权，不能把 `ticks_fire_control_opportunity / window_s` 当 FCO/s：那是受 timer 频率影响的“采样拍/秒”。`FCO_seconds / active_window_s` 仍有终态相关分母，也不采用。

实现须记录 `t0`、τ、T、逐区间起止仿真时间、各源时间戳、FCO 谓词及其已知性。区间跨新鲜度到期时刻、终态或 T 时必须截断；不得跨长间隙无限前向保持。源过期而监听链仍正常是可观测的“不可用”，按既有谓词计 0；logger 掉线、时钟回退、源流/终态证据无法核验则是测量缺失。

记录 `known_preterminal_s`、`missing_preterminal_s`、`post_terminal_budget_s`，三者覆盖固定 T；时序或覆盖不一致则拒绝计算。存在未知区间时点估计为 `null`，同时给出 `[known_fco_s/T, (known_fco_s+missing_preterminal_s)/T]` 识别界，不能删除缺测回合再宣称等价。缺测纳入等价门的完整性审查；如何把识别界用于保守推断或触发不判定，须在 P3 预声明，禁止事后决定。

现有 summary 只有聚合计数，无法恢复精确积分与未知区间；本次**不重建**历史新指标。未来实现须新增带版本的独立字段，保留 `visibility_metrics` / `episode_window_metrics` 原语义。发布前用“早成功、晚成功、超时、终态后停泊、非均匀采样、长间隙/缺测、时间回退”做确定性验证，再做 GUI 关键验证；不能仅改 YAML 指标名。

<a id="endpoints"></a>
## 等价门的指标集合

| 地位 | 指标 | 分母 / 角色 |
|---|---|---|
| co-primary | `mission_fco_fraction` | 固定 60 仿真秒；新定义见上 |
| co-primary | 捕获成功率 | 完整任务的全部 mission attempts，包括失败；不按捕获者筛选 |
| co-primary | 超时率 | 同一组全部 mission attempts；超时按既有契约裁决 |
| secondary | active FCO、active 可见率、`env_occ_given_visible`、首次 FCO / 捕获条件时间 | 过程解释；报告实际窗口及事件未发生情况，不用于单独宣布等价 |
| 安全 / 完整性门 | 净空、干预、`shield_infeasible_rate`、`reset_failure_rate`、infra / 缺测率 | 沿用原记录定义；具体非劣界限及完整性界限由 P3 预声明 |

率类分母是任务数，虽其**值**依赖终态，其**分母**不依赖成功/超时类别。co-primary 之间可以相关；“全部通过”不要求彼此统计独立。只有捕获/超时两类结果时两率互补，P3 应识别冗余而非当作独立证据。active 可见率降为 secondary 是测量目的裁定，不能解释成由某个已观察方差证明任何预算下都不可能等价。

<a id="history"></a>
## 科研历史结论保留

只读复算原科研 P2 v3 配对（从 a/b 原值求差，非已四舍五入的 delta）：

| 口径 | n | B−A | 95% CI |
|---|---:|---:|---|
| 原配对 | 20 | −0.056082 | [−0.097101, −0.015063] |
| 剔除 degraded，事后敏感性 | 17 | −0.054488 | [−0.102454, −0.006522] |

敏感性 CI 上限约 **−0.0065**，仍低于历史 MME=0.10；但事后筛选不替代预注册判定，也不代表已消除全部偏差。**P2 v3 `falsified` / 保留 c2、P1 v5 `inconclusive`、P2 v2 `confounded` 均保持不变**；不重开预注册、不修改 adjudication 原件，也不把新指标回套历史 verdict。

<a id="next"></a>
## P2 出口与 P3 待办

P2 完成的是指标语义和历史边界裁定。**gate 仍为 `not_evaluable_as_specified`，headless 规模统计未授权**；W7-c 仍 deferred、W8-E2 未进入。

P3 需：实现并验证上述记录器；预声明新 seed 网格及 seed 内执行重复如何建模；选择等价界限、缺测规则及适用的多指标推断方法；重新规划 n 与成本，明确解决 ADR-0096 中容差 / n 上限 / 公式的冲突。旧 n 公式与 pilot 差值门不因本 ADR 获得新的有效性。本任务不冻结 plan v2、不启动新 pilot / 正式等价、不授权在线 RL。
