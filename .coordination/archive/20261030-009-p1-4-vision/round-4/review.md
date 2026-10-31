# P1-4 · Leader 最终审查报告

<a id="p1-4-review"></a>

## 结论

**P1-4 不作全出口验收，按“链路与接口已交付、基线对比未闭环”收口。**

本轮授权的最后一次 T2 已完成，且 V4/V5/V6 真实取证成立；但计划出口第 4 项“换相机模型后，飞行跟踪行为实测不变（跟踪误差与基线对比）”仍没有有效 truth 对照实验。不得以 `TRACKING_SUCCESS` 单独替代跟踪误差对比，也不得把 `vision_model.id=none` 的成功 run 作为视觉识别能力证明。

## 独立抽查结果

- `experiments/p1-4/round-4/evidence/index.json` 的 single attempt 与证据路径一致，未使用历史 summary glob。
- round-4 vision run 的 `result.json` 确实使用 `gz_x500_mono_cam`、`perception_path=vision`、`vision_detector=true`、`vision_model_id=none`，并落盘 `summary.perception_path=vision` 与模型字段。
- `camera_probe/probe.json` 记录 94 帧、640×480 rgb8、mean luma 174.363、std 44.719、11.834 Hz；满足本次取证的 ≥10 Hz 门槛，但不外推为稳定长期帧率。
- `v5-detections.txt` 为真实逐帧空 `Detection2DArray`，时间戳继承图像；`v5-status.txt` 至少真实显示 `degraded=true`、`no_model`、`detection_frames_out=77`、backend `none`。其余 JSON 被默认 echo 截断，已如实保留该边界。
- `dataset/index.jsonl` 有 10 行，所有 image/label 文件存在，最大 `dt_ms=20`；标签明确为 evaluation-only，禁止作为 vision 决策输入。
- summary 为 `TRACKING_SUCCESS` / `tracking_milestone`，C9 两项为 0，reset 未失败；回收 33→0，无残留。

## 未闭环出口

计划 [P1-4 出口判据](../../../../docs/plan/p1-4-视觉算法接入.md#p1-4-exit) 第 4 项仍未勾选：

- round-1 的相机链路取证是 `air_bringup` 层面的相机出图，不能作为 `w6` 换机后的 truth 跟踪基线误差对照；
- round-2 的一次有效 truth run 未启动 episode，`IDLE` / ticks=0，不是有效基线；
- round-3/4 是 `vision` 路径且 backend `none`，只能证明接线、标注、降级和任务链未崩，不能证明“换机后跟踪误差与基线不变”。

## 已知边界

1. 数据集落点在 `experiments/p1-4/round-4/dataset/`，与旧预登记建议目录不同，但位于 `experiments/` 证据范围内。
2. status 原始输出被默认 `ros2 topic echo` 截断，关键字段可见；完整字段依赖 round-1 A6 交叉证据。
3. 11.834 Hz 是并发取证窗口读数，稳定帧率仍引用 round-1 的 24–26 Hz。
4. `vision_model.id=none` 表示显式无模型降级；视觉识别尚未接管任务决策，任务决策仍走 truth 派生链。
5. 本结论不是 ABI 或相机链路失败；是严格出口中的 baseline comparison 缺口。

## 后续裁定

- 本任务不再追加 T2，保留当前真实证据和缺口记录。
- 不开始 P1-4 下游任务，也不宣称“视觉算法已接入任务决策”。
- 若未来要闭环，仅可新开明确授权的 baseline-comparison 任务：同一 `yard/s04/full/seed 0`、同一 `observe_yaw_mode`，分别记录默认 `gz_x500` truth 与 `gz_x500_mono_cam` truth 的跟踪误差/终态/关键指标，再重新审查出口第 4 项。
