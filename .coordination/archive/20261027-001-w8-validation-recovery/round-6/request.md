<a id="round6"></a>
# W8 验证恢复 · 第 6 轮：LOCALHOST 下 UDPv4 单变量对照

- 任务 ID：20261027-001-w8-validation-recovery；轮次：6；日期：2026-10-28。
- 来源：Leader。第 5 轮已作为受限配置语义负对照验收；其 OFF+静态 peer 未实现静态发现，不得解释为 UDPv4 无效。本轮回填真正生效的 LOCALHOST 传输变量，沿用同一 Worker 与任务链。
- 依据：[第5轮审查](../round-5/review.md#round5-review)、[第4轮审查](../round-4/review.md#round4-review)、[离线诊断](../../../../experiments/w8-validation/20261027-communication-diagnosis-r2/report/diagnosis.md#diagnosis)、[同版本 participant 实现](../../../../experiments/w8-validation/20261027-communication-diagnosis-r2/config/sources/rmw_fastrtps-8.4.4-participant.cpp)、[观测分级](../../../README.md#run-tiers)。

## 目标与单变量

复用已验收探针和第 4 轮顺序设计，比较 **G=`FASTDDS_BUILTIN_TRANSPORTS` 未设置** 与 **H=`FASTDDS_BUILTIN_TRANSPORTS=UDPv4`**。其余条件保持第 4 轮：`ROS_DOMAIN_ID=39`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、topic、类型、RELIABLE depth10、默认 RMW、无 profiles/LD_PRELOAD。`ROS_STATIC_PEERS` 可显式设为 `127.0.0.1`；它与 LOCALHOST 自动注入的 localhost peer 语义相同，不作为新增独立变量。

已学习的实现：LOCALHOST 自建 SHM+UDPv4 且 `use_builtin_transports=false`，所以本版本下 H 很可能不改变实际 transport；本轮以 graph/matched/heard 的结果验证这一判断，不把环境变量名称当成实配回读。若 G/H 同形，只能记为该可观测结果不支持 UDPv4 环境变量改善；不能据此单独证明 SHM 根因。

## 预授权与顺序

本单显式预授权 **T1: 3 次**，每次 ≤30 s、累计 ≤90 s、每次最多 2 个 ROS participant 进程、普通用户、独占 `/tmp/agc-w8-validation-r6-*`。不读 `/dev/shm`、不清理共享资源或他人进程、不改系统/网络/库/时钟配置、不构建、不抓包、不启 GZ/PX4/GUI/headless/全链、不运行额外 observer/daemon。有效结果不得重跑；仅进程异常且根因明确时按协议使用剩余预算重试一次。

1. **G1（attempt-1，pub-first）**：不设 `FASTDDS_BUILTIN_TRANSPORTS`；pub 8 s、sub 6 s。
2. **H1（attempt-2，pub-first）**：两端设 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`；时序与 G1 相同。
3. **G2（attempt-3，sub-first）**：不设置该变量；sub 8 s、pub 6 s，复现第 4 轮反向顺序。

topic `/agc_probe_transport/chatter`；只读复用 `experiments/w8-validation/20261027-layered-matched-probe-r1/scripts/probe_layered.py`。仅 source `/opt/ros/jazzy`，使用 `env -i` 固定进程环境；`HOME=/home/chen`，ROS_HOME/ROS_LOG_DIR 独占。探针自行运行到结束；不得发 SIGTERM 促收。

**启动时序要求**：以先启动方 `events.jsonl` 的 `probe_start` 为就绪事件，再等待约 1.0 s 启动后启动方；不得从 shell wrapper 的 `$!`/启动时刻代替 participant 就绪。等待就绪总开销包含在单次 30 s 上限内；若无法在预算内捕获就绪事件，记 invalid 并停止。使用第 5 轮修正后的可回收驱动模型（每探针独立 PGID 且可由 shell `wait`），回收真实 RC，并与探针 result/probe_end 交叉核对。

## 判读

- G 复现先启动方单向 graph/matched、H 双向 graph/matched 且 heard>0：支持该配置包改变通信形态；仍需独立实配与重复性验证，不宣称根因或工程恢复。
- G/H 均同形：本版本环境变量未显示改善，与 LOCALHOST 覆盖 builtin transport 的机制一致；不据此归因 SHM。
- 双向 graph/matched 但 heard=0：发现/匹配与数据消费仍是独立缺口。
- G 未复现第 4 轮形态：如实记为重复性不足，H 不作简单有效/无效比较，不追加未授权样本。
- 任一 API 异常、关键快照缺失、超期、残留、启动时序不合格：invalid，停止并保留现场。

## 写入白名单、基线与产物

- 新根：`experiments/w8-validation/20261028-localhost-udp-abba-r1/`，只可新增 `config/`、`log/`、`report/`。预置 `config/codex_dispatch_baseline.json` 与 `baseline_receipt.json` 只读；旧探针、历史证据与归档不得改写。
- 允许按协议更新本轮 report、CURRENT，并只在 round6 段勾选 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 执行事实；不改 spec、契约、Runbook、request/review、src/scripts/toolchain/build/install 或其他协调文件。不 reset/clean/commit/push/切分支。
- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，保留既有 dirty/untracked。基线由 Leader 派工前生成并核对实际条目数；CURRENT、本轮 report/review 显式 mutable。第 5 轮已授权 tasks/checklist 变化及封存后侧车纳入新基线。领取逐项核对 size/SHA，未知漂移或 absent 文件重现立即停止。
- 保存三次双端事件/结果、完整驱动日志、PID/PGID/starttime、真实 RC、环境、配对 wall/monotonic、启动就绪与重叠窗口、残留、SHA、run identity 和克制分析。所有时长算术在封存前独立复算；若封存后才发现错误，只写本轮 report 或 `_archive` 同级侧车，不改封存源。
- 使用现有 `scripts/evidence_archive.py` 首次封存，禁止 `--force`，归档 stdout 写 `/tmp`；独立核对 manifest、tar 实际根目录、checksum、retrieval 与源根逐文件 SHA。

## 预算、验收与停止

整轮 **45 min（领取至交接，monotonic）**。验收的是三次受控 T1 的证据、单变量执行、正确就绪时序、完整回收与克制判读；有效失败也可通过诊断取证验收。完成置待审查，`send_message` 通知 Leader 后结束，不轮询、不接下一单。

本轮不开放 S2/S3/S4，不改变 gate、headless 授权或科研结论，不结档整链。遇硬约束问题、未知基线漂移、白名单外需求、guard/权限失败或预算不足立即停止回报。
