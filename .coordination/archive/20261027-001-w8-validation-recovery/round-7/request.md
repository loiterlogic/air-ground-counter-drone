<a id="round7"></a>
# W8 验证恢复 · 第 7 轮：SUBNET 下 UDPv4 双向顺序对照

- 任务 ID：20261027-001-w8-validation-recovery；轮次：7；日期：2026-10-28。
- 来源：Leader。第 6 轮已验收，LOCALHOST 下 UDPv4 环境变量无可观测改善，结束该分支；本单检验真正使用 builtin transport 路径的 SUBNET 候选配置。
- 依据：[第6轮审查](../round-6/review.md#round6-review)、[第4轮审查](../round-4/review.md#round4-review)、[离线诊断](../../../../experiments/w8-validation/20261027-communication-diagnosis-r2/report/diagnosis.md#diagnosis)、[同版本 participant 实现](../../../../experiments/w8-validation/20261027-communication-diagnosis-r2/config/sources/rmw_fastrtps-8.4.4-participant.cpp)、[观测分级](../../../README.md#run-tiers)。

## 目标与配置语义

复用已验收探针，在 **SUBNET + `ROS_STATIC_PEERS=127.0.0.1` + `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`** 下做 pub-first/sub-first 两次对照，直接观测 graph/matched/heard。与 LOCALHOST 相比，SUBNET 分支保留 `use_builtin_transports` 默认路径，官方环境变量具备生效语义；静态 peer 也会被注入，并附加 multicast initial peer。该配置包用于判断“非 LOCALHOST 自定义栈 + UDPv4”能否形成双向通信，不用于拆分 multicast/静态peer/UDP 各自的必要条件。

已学习同版本实现：LOCALHOST 会强制自建 SHM+UDPv4；SUBNET 不覆盖 builtin transport。故本单不是重复第6轮变量，也不声称已做transport实配回读。

## 预授权与两次 T1

本单显式预授权 **T1: 2 次**，每次 ≤30 s、累计 ≤90 s、每次最多 2 个 ROS participant、普通用户、独占 `/tmp/agc-w8-validation-r7-*`。不读 `/dev/shm`、不清理共享资源或他人进程、不改系统/网络/库/时钟配置、不构建、不抓包、不启 GZ/PX4/GUI/headless/全链、不运行额外 observer/daemon。有效结果不得重跑；仅进程异常且根因明确时按协议使用剩余预算重试一次。

两端共同固定：`ROS_DOMAIN_ID=39`、`ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`、`ROS_STATIC_PEERS=127.0.0.1`、`FASTDDS_BUILTIN_TRANSPORTS=UDPv4`；不设 RMW_IMPLEMENTATION/LD_PRELOAD/profiles；仅 source `/opt/ros/jazzy`，`env -i` 固定环境，HOME=/home/chen，ROS_HOME/ROS_LOG_DIR 独占。topic `/agc_probe_subnet_udp/chatter`，std_msgs/String，RELIABLE depth10。只读复用第3轮 probe_layered.py。

1. **J1 pub-first（attempt-1）**：pub 8 s、sub 6 s。
2. **K1 sub-first（attempt-2）**：sub 8 s、pub 6 s。

必须以先启动方 `events.jsonl` 的 `probe_start` 为就绪事件，再等待约1.0 s启动后启动方；等待与轮询计入30 s。沿用第6轮 set-m 独立PGID且可wait的驱动模型，真实RC与result/probe_end交叉核对。探针自行结束，不发SIGTERM；关键快照缺失、API异常、超期、残留或就绪不合格即invalid并停止。

## 判读

- 两次均双向graph/matched且heard>0：该SUBNET+UDPv4配置包在本轮两次T1中成立，是S1可用配置候选；仍须后续受控复核，不能宣称永久修复或工程恢复。
- 仍复现先启动方单向匹配、后启动方不可见、heard=0：故障不局限于LOCALHOST分支；不得归因SHM或UDP本身。
- 双向graph/matched但heard=0：发现与匹配成立，数据送达/消费是独立缺口。
- 其他形态或G旧形态未复现：如实记录，不追加未授权样本，不强行映射根因。

## 写入白名单、基线与产物

- 新根 `experiments/w8-validation/20261028-subnet-udp-probe-r1/`，只可新增config/log/report；预置baseline与receipt只读。旧探针、历史证据与归档不得改写。
- 允许按协议更新本轮report、CURRENT，并只在round7段勾选 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 执行事实；不改spec、契约、Runbook、request/review、src/scripts/toolchain/build/install 或其他协调文件。不reset/clean/commit/push/切分支。
- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main，保留既有dirty/untracked。基线由Leader派工前生成并核对实际条目数；CURRENT、本轮report/review显式mutable。第6轮授权勾选纳入基线。领取逐项核对size/SHA，未知漂移或absent重现立即停止。
- 保存两次双端事件/结果、完整驱动日志、PID/PGID/starttime、真实RC、环境、配对wall/monotonic、probe_start就绪与重叠窗口、残留、SHA、run identity和克制分析。所有时长算术在封存前独立复算；封存后纠错只写report或_archive侧车。
- 使用现有 `scripts/evidence_archive.py` 首次封存，禁止 `--force`，归档stdout写/tmp；独立核对manifest、tar实际根目录、checksum、retrieval与源根逐文件SHA。

## 预算、验收与停止

整轮 **45 min（领取至交接，monotonic）**。验收两次受控T1的证据、配置语义、正确就绪时序、完整回收与克制判读；有效失败也可通过诊断取证验收。完成置待审查，`send_message`通知Leader后结束，不轮询、不接下一单。

本轮不开放S2/S3/S4，不改变gate、headless授权或科研结论，不结档整链。遇硬约束问题、未知基线漂移、白名单外需求、guard/权限失败或预算不足立即停止回报。
