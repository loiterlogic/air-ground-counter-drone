# P1-4 · round-1 批次派工单

<a id="p1-4-r1-request"></a>

## 目标

实现并验证 [P1-4 视觉算法接入](../../../../docs/plan/p1-4-视觉算法接入.md#p1-4-goal)：建立“仿真图像 → 可插拔识别 → 明确接口/回退”的链路，为视觉同学提供可运行基础。

## 前置与不可变边界

- P1-1、P1-2、P1-3 已验收归档。
- 本轮不宣称“真实视觉识别已接入任务决策”；必须遵循 ADR-0103 的 `truth` / `vision` 互斥路径。
- 不改变既有 9 消息 ABI、C10、终态判据、安全阈值、唯一执行口；truth 默认路径保持可运行。
- `vision` 路径不得以真值坐标静默补齐检测；无模型必须显式降级并留证。

## 先学后做

先读：P1-4 计划、ADR-0103、ADR-0020、`src/agc_sim/config/bridge.yaml`、
`src/agc_air/launch/air_bringup.launch.py`、`w6.launch.py`、PX4 `x500_mono_cam` 模型、
现有消息/接口和实验产物规则。先验证实际 GZ camera topic，再写 bridge 配置，禁止猜话题名。

## 交付白名单

- `src/agc_air/**`、`src/agc_sim/config/bridge.yaml`、必要的 `src/agc_sim/launch/**`
- `src/agc_perception/**`（仅视觉输入/回退链必要改动）
- `src/agc_msgs/**`（仅若现有 ABI 无法表达接口；先停并报告，不自行改 9 消息）
- `scripts/vision/**`、`scripts/tests/**`、`tests/**`
- `docs/plan/p1-4-视觉算法接入.md`、必要 ADR/接口文档
- `.coordination/task/20261030-009-p1-4-vision/**`
- `experiments/p1-4/**`

## 必须完成的出口判据

1. 指定载体挂载相机；`gz topic -l` 实测出现 image 话题。
2. `/agc/air/camera/image_raw` 在 ROS 侧真实可用，`ros2 topic hz` 稳定 ≥10 Hz；记录实际 QoS/话题。
3. 用 `rqt_image_view` 或等价原始采样证明图像有内容、非黑屏；保存采样证据。
4. 相机模型变化后，truth 基线跟踪行为与 P1-2/P1-3 口径对比，不能静默退化；必要时记录误差/终态。
5. 识别接口文档完成：输入、输出、频率、坐标、回退、模型标识与版本。
6. 无模型时 `vision` 路径显式输出空检测/降级状态，不偷偷回退 truth；truth 默认主场景仍跑通。
7. 9 消息 ABI 与既有真值派生链未改；新增视觉路径与 truth 互斥且产物记录 `perception_path`。
8. 数据集录制脚本或最小可用采样工具能产出 image + label 对，写明同步/来源。

## 批次预算与停止

- N=6、K=4；T2 总预算 2400 秒，最多 8 次真实启动（GUI/headless/工具各算一次）；每轮最多 2 次。
- T1: 12 次 / 360 秒；离线 ≤600 秒，单次 ≤30 秒。
- 第一轮先做环境/现状勘察、相机模型和 GZ topic 实测；若发现需改 9 消息 ABI 或无法在白名单内完成，立即停止并报告。
- 真实启动前必须写预登记（模型、话题、QoS、truth/vision 路径和验收指标）。
- 不 commit/reset/clean；完成后写报告并置待审查；未验收不得派发后续轮次或宣称视觉识别决策已通过。
