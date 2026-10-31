# P1-4 · round-5 最后基线对比返工

<a id="p1-4-r5-request"></a>

## 目的

P1-4 已完成相机、vision 标注、降级消息和 image+label 取证，但计划出口第 4 项仍缺有效 truth 基线对比。本轮只补这一项。

## 唯一任务

使用同一 `yard/s04/full/seed 0/observe_yaw_mode=target` 和同一任务入口，分别取得：

1. 默认 `px4_sim_model=gz_x500`、`perception_path=truth` 的有效 truth 基线；
2. `px4_sim_model=gz_x500_mono_cam`、`perception_path=truth` 的有效 truth 对照。

两次都必须确认 `/agc/task/start` 已调用且 episode 非 IDLE；summary 必须存在并包含可比的终态、任务窗口、tracking/visibility/odom 等现有指标。若能取得统一 tracking error 字段则记录；没有该字段不得自造。

## 证据口径

- 预登记必须在两次真实运行前落盘，写明固定参数、字段路径、比较规则和不可比条件。
- 比较以已有 summary 字段为准；只比较同义、同口径字段。`TRACKING_SUCCESS` 不是误差等价的替代物。
- 记录相机增量对 truth 基线的相对差；若终态不同或关键字段缺失，判不通过并如实报告。
- 本轮不运行 vision backend，不重做 V4/V5/V6。

## 约束与预算

- 仅允许改本 round 证据/报告/预登记和 P1-4 计划勾选；不得改代码、配置、ABI、终态、安全阈值。
- 最多 2 次 T2 / 900 秒；每次必须使用 run_demo 主路径并通过其任务启动；失败不追加超过 2 次。
- 完成后无论通过或失败都置待审查并收口；不得开始新的下游任务。
