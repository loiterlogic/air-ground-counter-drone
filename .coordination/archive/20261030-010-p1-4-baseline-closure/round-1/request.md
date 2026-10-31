# P1-4 · baseline closure 后续任务

<a id="p1-4-baseline-r1-request"></a>

## 目标

仅闭环 [P1-4 出口第 4 项](../../../../docs/plan/p1-4-视觉算法接入.md#p1-4-exit)：证明同一
`yard/s04/full/seed 0/observe_yaw_mode=target` 下，默认 `gz_x500` truth 与
`gz_x500_mono_cam` truth 的飞行跟踪行为可比，记录真实误差/终态/关键指标。

P1-4 既有相机、vision、降级、数据集成果保持原样；本任务不重做它们。

## 第一阶段：先学后修

先读并对照本仓 Nav2 lifecycle 编排成功实现、现有 `air_lifecycle_prewarm` 的退出协议、
`w6.launch.py` 的 `OnProcessExit` 依赖和 run_demo 的进程组回收路径。先用最小 T0/T1
证明竞态：prewarm 是否在两种机型上退出、lifecycle_manager 是否启动、air odom 是否新鲜。
不得直接盲改。

## 允许范围

- `src/agc_task/launch/w6.launch.py`：仅修复 prewarm/lifecycle 启动竞态；不得改变任务参数、终态、C10、控制链。
- `scripts/vision/**` 或 `scripts/baseline/**`：仅修复采集器边采边写、短窗口和中断安全落盘。
- `scripts/tests/**`：针对竞态和采集器增加离线守卫。
- 本任务 docs、experiments、coordination 证据。

如发现需要改 C++/ABI/安全阈值/消息或改变 launch 语义，立即停止并报告，不自行扩权。

## 验收要求

1. 修复前后证据：T0/T1 证明 prewarm 完成、`lifecycle_manager_air` 启动、两种机型 `/agc/air/odom` 新鲜。
2. 采集器按周期/边采边写，SIGINT/SIGTERM 仍保留有效 JSON；不得等循环结束才写唯一结果。
3. 预登记必须先于真实运行，固定两臂参数、字段路径和比较规则。
4. 两次有效 T2：默认 `gz_x500` truth 与 `gz_x500_mono_cam` truth，均非 IDLE、task/start 已调用、summary 完整、无残留。
5. 记录相同口径字段：终态、reason、reset、C9、task window、visibility、RTF、odom，以及真实 tracking error 样本/统计。不得用终态替代误差。
6. 对比结论仅在字段同义且预登记容差内时成立；若不一致则如实 FAIL，不调整口径。
7. 完整回归、geometry、docs link；不改视觉路径和已有 P1-4 证据。

## 预算与停止

- N=6/K=4；最多 2 轮，每轮最多 2 次 T2，总 T2 ≤4 次 / 1200 秒；T1 ≤8 次 / 240 秒；离线 ≤300 秒。
- 每轮真实运行前必须预登记；任何一次无效运行须计账，不得用历史 summary 顶替。
- 成功或失败均写报告；若第 4 项仍未闭环，任务收口为已知缺口，不再无限追加。
