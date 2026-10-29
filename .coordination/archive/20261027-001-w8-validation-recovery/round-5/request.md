<a id="round5"></a>
# W8 验证恢复 · 第 5 轮：UDPv4 单播发现对照

- 任务 ID：20261027-001-w8-validation-recovery；轮次：5；日期：2026-10-28。
- 来源：Leader。用户要求审查工作区汇报后直接派任务；第 4 轮已由前 Leader（Codex）独立验收，但 S1 通信根因与可用配置仍阻塞。本单沿同一任务链，不开新任务流。
- 依据：[交接协议](../../../README.md#protocol)、[观测分级](../../../README.md#run-tiers)、[第4轮审查](../round-4/review.md#round4-review)、[离线诊断](../../../../experiments/w8-validation/20261027-communication-diagnosis-r2/report/diagnosis.md#diagnosis)、[同版本 participant 实现](../../../../experiments/w8-validation/20261027-communication-diagnosis-r2/config/sources/rmw_fastrtps-8.4.4-participant.cpp)。

## 目标

复用第 3/4 轮已验收探针，只改变进程级发现/传输配置，检验最小 **UDPv4 + 静态单播 peer** 配置能否消除第 4 轮的“先启动方匹配、后启动方不可见、双方零接收”。保持 pub-first/sub-first 两次顺序对照，区分“该配置下通路成立”与“失败仍持续”；不把任何单次结果升级为永久修复、完整根因或工程恢复。

已学习的机制事实：LOCALHOST 分支会关闭 builtin transports 并自建 SHM+UDPv4；OFF 分支禁用多播；`ROS_STATIC_PEERS=127.0.0.1` 提供初始单播 peer；`FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 在 OFF 分支的 builtin transport 路径上生效。本轮同时改变 discovery range/transport 是**一个候选最小配置包**，若成功不能据此拆分哪一项是必要条件。

## 固定条件与两次 T1

本单显式预授权 **T1: 2 次**，每次 ≤30 s、累计 ≤90 s、最多 2 个进程、普通用户、独占 `/tmp/agc-w8-validation-r5-*`。不读 `/dev/shm`、不清理共享资源或他人进程、不改系统/网络/库/时钟配置、不构建、不抓包、不启 GZ/PX4/GUI/headless/全链，不运行额外 graph observer/daemon。有效零接收或异常形态不得重跑；仅进程异常退出且根因明确时，按协议使用剩余预算重试一次并如实留痕。

两端共同固定：

- `ROS_DOMAIN_ID=39`、`ROS_AUTOMATIC_DISCOVERY_RANGE=OFF`、`ROS_STATIC_PEERS=127.0.0.1`、`FASTDDS_BUILTIN_TRANSPORTS=UDPv4`；
- 不设 `RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles；仅 source `/opt/ros/jazzy`；`HOME=/home/chen`；`ROS_HOME`/`ROS_LOG_DIR` 指向本 attempt 独占目录；
- topic `/agc_probe_unicast/chatter`，`std_msgs/msg/String`，RELIABLE depth10；只读复用 `experiments/w8-validation/20261027-layered-matched-probe-r1/scripts/probe_layered.py`，不复制或修改；
- 使用独立进程组，记录完整命令、环境、PID/PGID/starttime、配对 wall/monotonic、退出码、完整输出和残留。

1. **E1 pub-first（attempt-1）**：先启动 pub，约 1.0 s 后启动 sub；pub 8 s、sub 6 s，使 pub 覆盖 sub 完整窗口。
2. **F1 sub-first（attempt-2）**：先启动 sub，约 1.0 s 后启动 pub；sub 8 s、pub 6 s，使 sub 覆盖 pub 完整窗口。

两次均须有双端 `events.jsonl` 与 `result.json`。API 异常、关键快照缺失、超时或自有进程残留即 invalid，停止并保留现场；不得用旧结果替代本轮任何一侧。

## 判读

- 两次均双向 graph/matched 且订阅端 `heard>0`：该最小 UDPv4 单播配置包在本轮两次 T1 中成立，可作为后续受控回查 LOCALHOST/SHM 分离变量的候选；仍不宣称根因或工程恢复。
- 仍只有先启动方 graph/matched、后启动方不可见或 heard=0：静态单播/UDPv4 未消除原形态；不得归因 SHM、QoS、权限或 executor。
- 双侧 graph/matched>0 但 heard=0：发现与匹配成立，数据送达/消费链仍是独立缺口。
- 结果不对称、无效或与上述不同：如实记录受限观测，不强行映射根因，不追加未授权试验。

## 写入白名单、基线与产物

- 新产物根：`experiments/w8-validation/20261028-unicast-discovery-probe-r1/`，只可新增 `config/`、`log/`、`report/`。预置的 `config/codex_dispatch_baseline.json` 与 `baseline_receipt.json` 只读；不得改写历史证据、第3/4轮探针或旧归档。
- 允许按协议修改本轮 `report.md`、`.coordination/CURRENT.md`，并仅在本轮新增段勾选 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的执行事实；不得修改规格、契约、Runbook、request/review、src/scripts/toolchain/build/install 或其他协调配置。
- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`；保留全部既有 dirty/untracked，不 reset/clean/commit/push/切分支。
- 基线由 Leader 于派工前生成，1203 个冻结路径，`baseline_receipt.json` SHA `1c4ec1ab3bbb93dc03750954557913f1966ceb4b1bb45fdd0de79b550afff897`；`CURRENT`、本轮 report/review 为显式 mutable。历史删除的叫醒机制文件登记在 `absent_from_parent_or_previous_tree`，若重新出现须停止。领取时逐项核对 size/SHA、HEAD/branch 与任务/轮次/状态；未知漂移立即停止。该基线不声称全文件系统普查。
- 产物须含 run identity、两次原始双端事件/结果、运行日志、结果 SHA 与克制分析。生成 `config/evidence_manifest.json` 后，使用现有 `scripts/evidence_archive.py` 首次封存，禁止 `--force`；归档 stdout 写源根外 `/tmp`，封存后只写本轮 report 或 `_archive` 同级侧车/`/tmp`。核对 manifest、tar、checksum、retrieval 和源根逐文件 SHA。

## 预算、验收与停止

整轮 **45 min（领取至交接，monotonic）**，含核对、两次 T1、分析、报告、首次封存与取回核验。完成置 `待审查`，用 `send_message` 通知 Leader 后结束，不轮询、不接下一单。

本轮验收条件：基线/身份/范围与预算合规；E1/F1 双端原始证据完整；按运行期峰值而非退出后 final 判读 graph/matched；完整记录 heard；环境变量只作进程级改动；分析不夸大；封存与取回一致。有效失败同样可以验收“诊断取证完成”，但不开放 S2/S3/S4，不改变 `gate`、headless 授权或 P1/P2 科研结论。遇硬约束问题、未知基线漂移、白名单外需求、guard/权限失败或预算不足，立即停止并回报。
