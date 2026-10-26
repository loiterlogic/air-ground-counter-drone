# W8 P1 确定性探针与测量规格变更

## Status

accepted（2026-10-26：固定 seed 执行级不确定性经 5 个有效 mission attempt 确认；W8-E1a gate 保持 `not_evaluable_as_specified`）

## Context

W8 测量规格裁定要求在继续 pilot 或正式等价前，对同一场景、同一 seed、同一模式做 n=5 确定性探针。原始证据与逐 run 产物见 [`probe.md`](../../experiments/w8-parity/20261026-w8-p1-determinism-probe/metrics/probe.md) 与 [`probe.json`](../../experiments/w8-parity/20261026-w8-p1-determinism-probe/metrics/probe.json)。

条件为 `s15_static_none_fov_capture / p1_coop / seed 5 / backend=full / mode=headless`。5 个有效 mission attempt 外，另有 1 个受限沙箱 `getifaddrs` 权限失败的 infra attempt，单列且不进入测量分母。

## Decision

5 个有效 attempt 的 active FCO 为 `0.000000, 0.007163, 0.000000, 0.001958, 0.076797`，极差 **0.076797**；active window 长度为 `120.028, 23.224, 120.096, 85.108, 20.296 s`，极差 **99.800 s**。FCO 极差处于裁定规定的 `0.0–0.27` 执行级散布范围内，确认固定 seed 下存在执行级不确定性。窗口长度也显示终态与调度差异会显著改变可观测窗口。

因此，当前 `δ=0.02` 的 GUI/headless 等价目标在这套测量规格下放弃；gate 记为 `not_evaluable_as_specified`，不得记为平台 fail 或跳过。下一规格应在另立预声明后采用同 seed 复现率，或使用与终态无关的固定窗口并延长观测窗。确定性探针之前不得继续 pilot、正式等价或 W8-E2。

## Scope and invariants

- 本 ADR 只裁定 W8-E1a 的测量规格，不改统计公式、历史产物或既有科研 verdict。
- P1 v5 `inconclusive`、P2 v3 `falsified` / 保留 c2、P2 v2 `confounded` 保持不变；W7-c 仍 `deferred`，W8-E2 未预注册，headless 规模统计仍未授权。
- `MISSION_FAILED` 按契约计入 mission attempt；infra 单列。
