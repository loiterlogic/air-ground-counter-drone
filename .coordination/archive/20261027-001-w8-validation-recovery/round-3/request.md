<a id="round3"></a>
# W8 验证恢复 · 第 3 轮：分层通信微观测

- 任务 ID：20261027-001-w8-validation-recovery；轮次：3；日期：2026-10-27。
- 来源：Codex 根据第 2 轮独立审查派发；用户已授权本任务链继续。DSH 实施并回报，Codex 独立验收。
- 依据：[交接协议](../../../README.md#protocol)、[观测分级](../../../README.md#run-tiers)、[第2轮审查](../round-2/review.md#round2-review)、[第2轮诊断](../../../../experiments/w8-validation/20261027-communication-diagnosis-r2/report/diagnosis.md#diagnosis) 与 [候选方案](../../../../experiments/w8-validation/20261027-communication-diagnosis-r2/report/next_probe.md#next-probe)。项目进度仍以 [Runbook](../../../../docs/ROS2迁移步骤.md#status) 为准。

## 目标

用最小 rclpy 探针直接采集 graph count、DDS matched count、incompatible QoS 事件和消费回调计数，区分第一轮缺失的层次。只交付通信诊断证据；不恢复工程验证、不进入 S2/S3/S4、不改默认配置。

第 2 轮的 A 步同进程正对照是**探针控制**，不是跨进程系统阳性证明。A 步失败时只能记为探针/同 participant 无效或不成立并停止，不能写成环境整体故障。A 步有效后才执行 B 步跨进程正对照，B 步才与第一轮 talker/listener 结构可比。

## 预授权观测与预算

本单显式预授权 **T1: 2 次**，累计最多 2 次、总墙钟最多 90 s；每次墙钟 ≤30 s、进程数 ≤2、普通用户、独占 `/tmp/agc-w8-validation-r3-*`。不得读取 `/dev/shm` 内容、清理他人进程/共享资源、修改系统/网络/库/时钟配置、启动 GZ/PX4/GUI/headless/全链仿真、抓包或构建。T1 失败不自动重跑；仅进程异常退出且根因明确时可用第 2 次重试。候选脚本和结果只写本轮新证据根。

- **A（T1 attempt-1，1 进程）**：在单个 rclpy context/participant 内创建同 QoS `std_msgs/msg/String` publisher + subscription，记录 matched 双向计数、graph 双向计数、matched/incompatible 事件和 callback `heard`；同时做一个不同 topic 或不兼容 QoS 的负对照，验证观测器能区分匹配与不匹配。A 的结论只限同进程控制。
- **B（T1 attempt-2，最多 2 进程）**：仅当 A 的正对照有效且负对照表现符合预期时执行。两个独立 rclpy 进程分别 publisher/subscription，使用同域39、LOCALHOST、独立 namespace/topic 与 A 相同 QoS；两端各记录 matched count/事件，订阅端记录 callback。B 成功/失败按跨进程 matched 与 heard 判读。
- 若 A 正对照进程异常、计数/API 抛错或负对照未能证明观测器有效，停止，不执行 B；不得把 A 的 R4/R5 直接归因发现层或环境层。

## 实现白名单与产物

允许新增：`experiments/w8-validation/20261027-layered-matched-probe-r1/` 下单个 `scripts/probe_layered.py` 及 `config/`、`log/`、`report/` 结果文件；可在该目录内添加必要的运行输出。不得修改 `src/`、既有 runner、协调脚本、旧证据、默认 pin、项目配置或历史归档。可使用已安装 `/opt/ros/jazzy` 的 rclpy/std_msgs；不需构建。脚本应以 `start_new_session`/进程组可回收方式运行，记录 PID/PGID/starttime、命令、环境、退出码、残留和每个结果文件 SHA。

观测至少包括：`sent_n`、`heard_n`、`t_first_heard_mono_ns`、publisher/subscription matched `total_count/current_count/change`、graph publisher/subscriber count、`incompatible_qos` policy、配对 wall/monotonic 样本、`invalid_reasons`。同进程与跨进程结果分开，events.jsonl 追加写，result.json 最终汇总。

## 判读

- A 正对照和负对照均有效，B matched>0 且 heard>0：本机跨进程 DDS 在该配置下成立；第一轮失败应转查其入口时序/环境差异，不能直接宣称工程恢复。
- B matched=0、graph>0：发现到 graph 但未端点匹配，优先查 QoS/type/incompatible 事件。
- B matched=0、graph=0：仅支持未发现/图不可见假说，不能单凭此定位网络或权限。
- B matched>0、heard=0：已匹配但未消费，才升级传输/回调/执行器方向。
- 任一 API/进程异常、关键快照缺失、超 30 s、残留未解决：invalid，停止并如实回报。

## 基线与停止

HEAD/branch 和本轮派工基线在 Codex 叫醒前写入新根 `config/codex_dispatch_baseline.json` 与 `baseline_receipt.json`；冻结路径覆盖既有任务、第二轮归档及新 request，mutable 为 CURRENT/report/review。领取时须逐文件核对 size/SHA、未知变化停止。不得重置跳数；本轮 DSH 完成后按协议尝试叫醒 Codex，若守卫拒绝记录真实退出码并停止。

任务链本轮预算 45 min（领取至交接，monotonic），包含脚本、T1、报告、首次封存和取回核验。归档源为 `experiments/w8-validation/20261027-layered-matched-probe-r1/`，使用现有 `evidence_archive.py`，首次封存禁止 `--force`；封存后只写本轮 report 或 `_archive` 同级侧车/​`/tmp`，不得写源根。第 2 轮诊断仍已验收，通信、S2/S3/S4 和 gate 状态不因候选方案或 T1 运行自动改变。
