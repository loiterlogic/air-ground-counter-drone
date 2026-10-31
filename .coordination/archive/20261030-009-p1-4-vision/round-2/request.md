# P1-4 · round-2 最小集成补证派工

<a id="p1-4-r2-request"></a>

## 裁定

round-1 不验收。相机链路与 A6 降级成立，但 A4/A7/A8 未完整闭环。授权最小扩权，不允许再扩大。

## 允许新增/修改范围

- `src/agc_task/launch/w6.launch.py`：仅透传 `px4_sim_model`、`perception_path`，默认值保持既有 `gz_x500` / `truth`；不得改任务编排、终态或安全参数。
- `src/agc_task/src/run_logger.cpp`：仅在 summary 增加 `perception_path`、视觉模型标识/版本/哈希新键；不得改既有字段语义、采样和终态逻辑。
- `docs/ROS2迁移交接文档.md`：仅将 `perception_path` 作为显式参数入口记录，明确 truth 默认、vision 互斥和无模型降级；不得改其他契约。
- `docs/plan/p1-4-视觉算法接入.md`、round-2 证据/报告、必要测试。
- `experiments/p1-4/**`、`scripts/vision/**`、`scripts/tests/**`。

## 必须完成

1. 预登记 round-2（在真实启动前）记录模型、路径、话题、QoS、判据和预期字段。
2. `w6.launch.py` demo 主路径支持显式 `px4_sim_model` 与 `perception_path`，默认行为不变。
3. run_logger summary 记录 `perception_path` 与模型标识，truth/vision 产物可区分。
4. 做一次 truth 基线和一次 camera/vision 路径真实验证；均需 `yard/s04/full/seed 0` 口径或明确记录不可比原因。
5. 真实生成至少一组 image+label 数据集样本，记录同步窗口、标签来源为 evaluation-only，不得作为 vision 决策输入。
6. 无模型 vision 明确空检测 + degraded；truth 模式拒绝 vision detector 接线，不能静默混用。
7. 复跑 ABI、全套回归、geometry、docs link；不得改 9 消息 ABI。
8. 若 `perception_path` 无法在不改 ABI 前提下安全接入，立即停止并报告，不自行改消息。

## 最终追加裁定（仅一次）

round-2 原两次 T2 均无效，原因是 Worker 操作失误而非产品故障。现追加**一次且仅一次 T2 / 450 秒**：

- 必须使用已知会调用 `/agc/task/start` 的 `run_demo.sh` 主路径，或在直接 launch 后显式调用 `/agc/task/start`；不得再依赖历史 summary glob。
- 目标：`yard/s04/full/seed 0`、`px4_sim_model=gz_x500_mono_cam`、`perception_path=vision`、`vision_detector=true`。
- 同一有效运行内采集至少一组真实 image+label，并记录样本同步窗口与 evaluation-only 标签来源。
- 核对本次 run 的 `summary.json`：`perception_path=vision`、模型标识字段存在；终态/回收可如实记录。
- 若入口不支持所需参数，必须在启动前停止报告，不得临时改 CLI；可使用已授权的直接 launch + 显式 task/start 方案。
- 不再追加第二次 T2；无论成功或失败，完成后收口并置待审查。
- round-1 已用 T2 2/8、T1 8/12；本轮不重复勘察，不再使用全盘扫描；T1 不得单次超过 30 秒。
- 若任一真实 run 触及硬约束、summary 字段缺失、或清理失败，停止并报告；不开始 P2。
