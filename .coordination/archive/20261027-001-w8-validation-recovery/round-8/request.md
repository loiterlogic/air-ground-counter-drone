<a id="round8"></a>
# W8 验证恢复 · 第 8 轮：项目默认 domain 0 对照

- 任务 ID：20261027-001-w8-validation-recovery；轮次：8；日期：2026-10-28。
- 来源：Leader。第7轮已验收，SUBNET+UDPv4仍复现旧形态；项目既有ADR-0077记录非0 domain服务数据面异常，而正常整链使用domain0。本单优先检验这一已知配置因子。
- 依据：[第7轮审查](../round-7/review.md#round7-review)、[ADR-0077](../../../../docs/adr/0077-w7c-multi-worker-isolation.md)、[整链排障速查](../../../../docs/conventions/整链排障速查.md)、[观测分级](../../../README.md#run-tiers)。

## 目标

复用已验收探针与LOCALHOST条件，仅把ROS_DOMAIN_ID由此前39改为项目实际默认0，执行pub-first/sub-first两次顺序对照，采集graph/matched/heard。检验非0 domain是否是该探针形态的必要触发条件；不把domain相关服务异常直接外推为话题根因。

固定：`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、不设FASTDDS_BUILTIN_TRANSPORTS/RMW_IMPLEMENTATION/LD_PRELOAD/profiles/ROS_STATIC_PEERS；topic `/agc_probe_domain0/chatter`、std_msgs/String、RELIABLE depth10。仅source `/opt/ros/jazzy`，env -i固定环境，HOME=/home/chen，ROS_HOME/ROS_LOG_DIR独占。

## 预授权与两次T1

显式 **T1: 2次**，每次≤30s、累计≤90s、每次最多2个ROS participant、普通用户、独占`/tmp/agc-w8-validation-r8-*`。不读/dev/shm、不清理共享资源或他人进程、不改系统/网络/库/时钟配置、不构建、不抓包、不启GZ/PX4/GUI/headless/全链、不运行额外observer/daemon。有效结果不得重跑；仅进程异常且根因明确时按协议使用剩余预算重试一次。

1. **L1 pub-first**：pub 8s、sub 6s。
2. **M1 sub-first**：sub 8s、pub 6s。

沿用第6/7轮驱动模型，但口径必须更正：现探针 `probe_start` 在 `rclpy.init()` 之前，只能称**脚本启动标记**，不是participant/endpoint就绪。等待该标记后约1s启动后启动方，只为复现旧时序，报告不得写成participant已创建/就绪。沿用set-m独立PGID可wait，真实RC与result/probe_end交叉核对；探针自行结束，不发SIGTERM。关键快照缺失、API异常、超期、残留或时序不合格即invalid并停止。

## 判读

- 两次均双向graph/matched且heard>0：domain0下探针通信成立，domain成为主要配置因子候选；仍需domain39同轮复查或机制证据才能称必要触发条件，不直接恢复工程。
- 仍复现先启动方单向匹配、后启动方不可见、heard=0：该形态不局限于非0 domain；不得归因domain或SHM。
- 双向graph/matched但heard=0：发现/匹配与消费为独立缺口。
- 其他或无效形态：如实记录，不追加未授权样本。

## 写入白名单、基线与产物

- 新根 `experiments/w8-validation/20261028-domain0-localhost-probe-r1/`，只可新增config/log/report；预置baseline/receipt只读。旧探针、历史证据与归档不得改写。
- 允许按协议更新本轮report、CURRENT，并只在round8段勾选 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 执行事实；不改spec、契约、Runbook、request/review、src/scripts/toolchain/build/install或其他协调文件。不reset/clean/commit/push/切分支。
- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main，保留既有dirty/untracked。基线由Leader派工前生成并核对实际条目数；CURRENT、本轮report/review显式mutable。第7轮授权勾选纳入基线。领取逐项核对size/SHA，未知漂移或absent重现立即停止。
- 保存两次双端事件/结果、完整驱动日志、PID/PGID/starttime、真实RC、环境、配对wall/monotonic、脚本启动标记与重叠窗口、残留、SHA、run identity和克制分析。所有时长算术封存前独立复算；封存后纠错只写report或_archive侧车。
- 使用现有 `scripts/evidence_archive.py` 首次封存，禁止 `--force`，归档stdout写/tmp；独立核对manifest、tar实际根目录、checksum、retrieval与源根逐文件SHA。

## 预算、验收与停止

整轮 **45min（领取至交接，monotonic）**。验收两次受控T1证据、domain单因子执行、正确时序口径、完整回收与克制判读；有效失败也可通过诊断取证验收。完成置待审查，send_message通知Leader后结束，不轮询、不接下一单。

本轮不开放S2/S3/S4，不改变gate、headless授权或科研结论，不结档整链。遇硬约束问题、未知基线漂移、白名单外需求、guard/权限失败或预算不足立即停止回报。
