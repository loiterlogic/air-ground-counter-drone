# P1-3 · round-1 批次派工单

<a id="p1-3-r1-request"></a>

## 目标

实现并验证 [P1-3 任务可观测与演示呈现](../../../../docs/plan/p1-3-任务可观测与演示呈现.md#p1-3-goal)：让状态、意图和结果在演示中可读。

## 前置与固定边界

- P1-1、P1-2 已验收归档。
- 复用 [run_demo.sh](../../../../run_demo.sh) 与现有 `w6.launch.py`；不复制 launch 编排。
- 默认演示口径仍为 `full + yard + s04 + observe_yaw_mode=target`；必须保留显式 oracle 指向臂说明。
- 不改 C10、唯一执行口、9 消息 ABI、终态判据、安全阈值、任务状态机。
- 不新增话题；只订阅既有 `/agc/task/state` 和读取已有 summary。不得在展示层写 `/agc/ground/cmd_vel` 或模型位姿。
- `TRACKING_SUCCESS` 只能显示“抵近并持续跟踪成功”，不得显示“拦截完成”。

## 先学后做

先读 P1-3 计划、P1-2 `scripts/demo/start.py` 的状态监测和产物写入、
`src/agc_msgs/msg/AgcTaskState.msg`、`run_logger.cpp` 的 summary 字段、
契约终态锚点与现有演示排障文档，再实施。

## 交付白名单

- `scripts/demo/**`（状态面板/时间线/终态解释的必要实现）
- `run_demo.sh`（仅必要的呈现透传，不改起停语义）
- `scripts/tests/test_demo*.py`、`tests/demo*.py`
- `docs/plan/p1-3-任务可观测与演示呈现.md`
- `.coordination/task/20261030-008-p1-3-observability/**`
- `experiments/p1-3/**`、`experiments/demo/**`

如需改 `src/agc_task/**`、消息、C++ 或任何契约文件，先停止并报告，不自行扩权。

## 必须完成的出口判据

1. 单一状态映射实现：全部状态枚举及 reason_code 有人话文案，`TRACKING_SUCCESS` 文案通过静态禁词检查。
2. 演示运行期间终端 2 Hz 面板，至少含状态、说明、目标距离、已用时；headless 也能用。
3. 状态跳变写入 `experiments/demo/<timestamp>/timeline.txt`，至少 5 个关键节点或明确记录实际节点数与原因。
4. 终态打印判定说明，所有指标来自已有 `summary.json`，不在展示层硬编码判定阈值。
5. 目标在 Gazebo 中视觉可辨识：P1-1 已提供目标颜色/几何证据；不得改物理。若需改 world，先停并报告。
6. 展示层未新增话题、未改 ABI、未新增命令者；必须有静态回归。
7. 真实 GUI/full 和 headless 各至少跑一次，确认面板/时间线/终态解释在两种模式均落盘；优先复用 P1-2 已成功口径。

## 预算与停止

- 批次 N=6、K=4；T2 总墙钟 1800 秒，真实 run/GUI/headless 总 attempt ≤6，每轮 ≤2。
- T1: 8 次 / 240 秒，仅端口/进程/文件微观测，不启 GZ/PX4/GUI。
- 离线检查 ≤300 秒；单次 ≤30 秒。
- 若 6 轮内未完成全部出口，或连续 4 轮无区分性新证据，停止提交台账；契约风险/超白名单立即停。
- 证据长期归档到 `experiments/p1-3/round-N/` 与对应 demo run；不只放 /tmp。
- 不 commit/reset/clean，不开始 P1-4。
