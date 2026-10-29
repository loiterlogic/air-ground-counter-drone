<a id="top"></a>
# W8 P1 确定性探针与测量规格变更

## Status

accepted（2026-10-26：旧证据重核及独立 n=5 重做均观察到固定 seed 的执行级散布；W8-E1a gate 保持 `not_evaluable_as_specified`）

## Context

W8 测量规格裁定要求在继续 pilot 或正式等价前，对同一场景、同一 seed、同一模式做 n=5 确定性探针。原始证据与逐 run 产物见 [`probe.md`](../../experiments/w8-parity/20261026-w8-p1-determinism-probe/metrics/probe.md) 与 [`probe.json`](../../experiments/w8-parity/20261026-w8-p1-determinism-probe/metrics/probe.json)。

条件为 `s15_static_none_fov_capture / p1_coop / seed 5 / backend=full / mode=headless`。5 个有效 mission attempt 外，另有 1 个受限沙箱 `getifaddrs` 权限失败的 infra attempt，单列且不进入测量分母。

<a id="decision"></a>
## Decision

5 个有效 attempt 的 active FCO 为 `0.000000, 0.007163, 0.000000, 0.001958, 0.076797`，极差 **0.076797**；active window 长度为 `120.028, 23.224, 120.096, 85.108, 20.296 s`，极差 **99.800 s**。2026-10-26 重核原始整数计数和窗口边界，以上数值一致。该结果显示本条件下固定 seed 仍存在执行级散布；仅凭窗口差异不能归因为调度，也不能证明某一等价界限在数学上不可达。

当前 `δ=0.02` 的 GUI/headless 等价目标在这套测量规格下停止推进；gate 记为 `not_evaluable_as_specified`，不得记为平台 fail 或跳过。下一规格的候选为同 seed 复现率，或与终态无关的固定窗口及更长观测。**具体指标、窗口长度、容差及预算尚未裁定**，归属后续 P2/P3；本 ADR 不把候选方案写成已验证规格，不授权继续 pilot、正式等价或 W8-E2。

<a id="redo"></a>
## 2026-10-26 独立重做与判据勘误

用户要求重新完成 P1；执行规格见 [重做 spec](../archive/specs/redo-w8-determinism-probe/spec.md#scope)，生成器为 [`w8_determinism_probe.py`](../../scripts/w8_determinism_probe.py)。

原评审「spread 在 0.0–0.27」与「spread <0.01」重叠。重做前先冻结互斥判据：`<0.01` 记为探针分辨率内可重复；`0.01≤spread≤0.27` 为观察到执行级散布；`>0.27` 为超出参考范围。样本不足或缺测不判定。n=5 是描述性诊断，不是等价检验或因果识别。

旧报告的局限：仅列出 1 次有 arms 的 infra，遗漏 `headless-11` / `s15-headless-02` 两次无 arms 的沙箱启动失败，以及 `headless-01` 的目录已存在拒绝启动。无法从现存旧证据恢复完整的运行前计划及所有启动参数，不能只靠 scene/seed 标签声称全部条件已核验。旧报告与原件保持只读，新批次独立记录，不合并样本。

独立重做结果：`20261026-w8-p1-redo-r2` 取得 5 个有效 mission attempts，5/5 `INTERCEPT_CONFIRMED`，批次内 infra=0；另有批次启动前沙箱只读 ROS 日志目录失败，单列、不入 mission 分母。active FCO 极差 **0.071010**（min **0.003003** / max **0.074013**），窗口长度极差 **33.484 s**（min **11.112** / max **44.596 s**）。按冻结判据为 `execution_level_variability_observed`，与旧证据方向一致；5/5 捕获也表明窗口散布并不只来自成功/超时类别切换。

完整计划、命令、原始计数、C9 指标与逐文件哈希见 [新报告](../../experiments/w8-p1-redo/20261026-w8-p1-redo-r2/metrics/probe.md) / [JSON](../../experiments/w8-p1-redo/20261026-w8-p1-redo-r2/metrics/probe.json)；旧证据核对见 [audit](../../experiments/w8-p1-redo/20261026-w8-p1-redo-r2/metrics/old_evidence_audit.md)。本结果不外推至其他场景、seed 或模式；不授权 headless 规模统计。

## Scope and invariants

- 本 ADR 只裁定 W8-E1a 的测量规格，不改统计公式、历史产物或既有科研 verdict。
- P1 v5 `inconclusive`、P2 v3 `falsified` / 保留 c2、P2 v2 `confounded` 保持不变；W7-c 仍 `deferred`，W8-E2 未预注册，headless 规模统计仍未授权。
- `MISSION_FAILED` 按契约计入 mission attempt；infra 单列。

<a id="p2-followup"></a>
## 测量 P2 后续（2026-10-26）

指标语义已由 [ADR-0099](0099-w8-fixed-budget-mission-fco-measurement.md#metric) 裁定；本 ADR 中“P2/P3 待裁定”的指标候选状态以该后续为准。记录器实现、δ/n 与新计划仍归属 P3；gate 与历史科研 verdict 不变。
