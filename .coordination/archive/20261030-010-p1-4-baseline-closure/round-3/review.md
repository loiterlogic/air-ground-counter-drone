# P1-4 baseline closure · Leader 最终审查

<a id="p1-4-baseline-final-review"></a>

## 裁定

**P1-4 仍不作全出口验收；baseline closure 收口为 PASS_WITH_NOTE / 判据未闭环。**

round-3 补齐了 A 臂 `err_eff`：A p95=0.100946 m，B p95=0.100939 m，按预登记 p95 数值门槛相对差 -0.01%，且 primary/secondary 及两臂有效性均通过。

但独立审查发现该 p95 判据被 `standoff_follower.max_step_m=0.1` 饱和：p75–p95 整段约束在 0.1 m，因而 p95 几乎必然相等，不能支撑“换相机后跟踪行为实测不变”。区分机型的 p50 相对差 -42.41%、p99 相对差 -22.62%，均超过 20% 容差。不得事后改用 p50/p99 或重新解释预登记。

## 保留成果

- prewarm/lifecycle 竞态已最小修复并由两臂真实运行验证；
- A/B 两臂均非 IDLE、task/start 成功、summary 完整、终态与 C9 正常、无残留；
- A/B 两臂 `err_eff` 已真实落盘；
- P1-4 相机链路、vision 标注、消息级降级、数据集和 ABI 证据均保留。

## 收口边界

- P1-4 计划第 4 项继续未勾选；
- 不再追加本后续任务 T2；
- 不把 p95 PASS 写成整体等价，不把 `vision_model=none` 写成视觉识别能力；
- 若未来要闭环，必须重新预登记具备判别力的指标（如解除饱和后的误差、p50+p99 或 C1 速度/高度误差），这是新任务，不得沿用本轮预登记结果。
