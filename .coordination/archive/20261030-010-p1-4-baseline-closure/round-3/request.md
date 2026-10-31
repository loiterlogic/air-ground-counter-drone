# P1-4 baseline closure · round-3 最后 A 臂补证

<a id="p1-4-baseline-r3-request"></a>

## 裁定

round-2 已证明 prewarm 修复有效，两臂主指标可比；唯一缺口是 A 臂采集器 bug 导致 `err_eff` 缺失。现授权最后一次只补 A 臂误差。

## 唯一任务

- 只运行默认 `gz_x500`、`perception_path=truth` 的 A 臂；固定 `yard/s04/full/seed 0/observe_yaw_mode=target/headless`。
- 使用 round-2 已修复的 `track_err_probe.py`，确认边采边写/中断安全和 `err_eff`（生效 `tracking_ref`）输出。
- 不运行 B 臂、不运行 vision、不改代码/配置/预登记；不重做 V4/V5/V6。
- 核对 task/start、非 IDLE、summary、终态、无残留，并取得 `err_eff` p95 与样本数。
- 与 round-2 B 臂 `err_eff p95=0.1009m` 按预登记同口径比较；不得调整容差或用终态替代误差。

## 预算与收口

- 最多 1 次 T2 / 450 秒；不重试。
- 完成后无论成功或失败写报告、置待审查并收口；不开始其他任务。
- 若入口/采集器无法工作，立即报告，不改代码。
