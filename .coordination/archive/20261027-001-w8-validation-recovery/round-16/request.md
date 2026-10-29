<a id="round16"></a>
# 第16轮：环境同构 stock 对照与 loopback 通路分离

任务ID 20261027-001-w8-validation-recovery；轮次16；来源Leader，2026-10-28。复用Worker `55d8793e-4916-4045-ac19-5800e167ebfa`。

入口：[Runbook](../../../../docs/ROS2迁移步骤.md#usage)、[规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round16)、[第15轮审查](../round-15/review.md#round15-review)、[自主权限](../../../README.md#executor-autonomy)、[观测分级](../../../README.md#run-tiers)、[硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。先读第2/5/6/7/8/14轮原始事件与审查，不只取支持片段。

## 0. 本轮的判读前提（Leader 已核实，Worker 须自行复核）

第3–15轮全部是**自写探针**的失败形态（先启动方 graph/matched=1、后启动方 graph=0/matched=0、零消费，方向随顺序翻转）。但项目内已有一条**相反**的既有记录：

- `experiments/ros2-diagnostics/20261026-p3-r2/`（2026-10-26 20:35，domain 37、`LOCALHOST`、默认 env、stock `demo_nodes_cpp`/`demo_nodes_py`）**6 例中 5 例实际收到 4–5 条**，唯一 0 接收是首例 `cpp_cpp`，且该轮自评"0 字节只证明未观察到接收，不能证明未到达"。
- 即：**同一台机器、同一 rmw_fastrtps_cpp/Fast DDS、同类 LOCALHOST 配置下，stock 进程间通信曾成立**；而此后所有自写探针轮次（含 domain 0/39、SUBNET、UDPv4）全数为该单向形态。

结论边界：这**不是**根因，但把问题空间强制劈成两半——「本机当前是否还能进行任何 ROS 进程间通信」与「只有本探针形态失败」。第15轮未回答这一点，本轮先回答它。

Leader 另于本轮开工前做过只读主机检查（未起任何进程；Worker 可用 T0 命令自行复核，见 §5）：本机为 WSL2 **mirrored networking**（`/mnt/c/Users/Lenovo/.wslconfig` `networkingMode=mirrored`，`wslinfo --networking-mode` 输出 `mirrored`），`ip rule` 中存在 `from all ipproto {tcp,udp} lookup 127` 与 `lookup 128` 的低优先级规则，`table 127` 为 `127.0.0.1 via 169.254.73.152 dev loopback0 onlink`，故 `ip route get 127.0.0.1 ipproto udp` **不走 `lo`**，而经 Hyper-V 合成网卡 `loopback0` 出到 `169.254.73.152`（邻居表为 PERMANENT）；`route_localnet=1`/`accept_local=1` 亦在 `loopback0`/`eth3` 上打开。这是**待检验的机制线索**，不是根因结论。

## 1. 目标

在一次受控轮次内判定以下**三选一**，不得含糊：

1. **S-环境**：本轮同构 stock 对照也**收不到** → 故障在环境/Windows-WSL 层，与项目代码、探针形态、DDS 配置无关；后续不需要再改探针。
2. **S-探针**：stock 在**同一 clean-env** 下能收到 → 差异在自写探针/驱动侧（身份、事件回调、executor、clean-env 内容、进程树），下一轮直接剖探针而非环境。
3. **S-不定**：收得到但仅在某一种 env 下；或结果不满足判定条件 → 如实登记，禁止外推。

## 2. 授权与预算

- 整轮 **45 min monotonic**（领取至交接）。
- **T1: 3 次**，每次起进程至全回收 ≤30 s，累计 ≤90 s；每次最多 **2 个** ROS/被测进程；普通用户；独占 `/tmp/agc-w8-validation-r16-*`。
- 本轮显式允许起 **stock 官方 demo 进程**（`/opt/ros/jazzy/lib/demo_nodes_cpp/{talker,listener}`、`demo_nodes_py`）与**两个短命 Python UDP 进程**；这是诊断用进程，不等于全链实验。
- **禁止**：构建、GZ/PX4/GUI/headless/全链仿真、抓包（tcpdump/wireshark/ss 持续监控）、读 `/dev/shm` 内容、清理他人进程或共享资源、改系统/网络/库/时钟配置、root、`ros2 daemon` 常驻、新增长期 observer。
- 允许 T0 只读：`ip rule`/`ip route get`/`ip -d link`/`/proc/net/udp`/`nstata`/`dmesg`/`wslinfo`/读取既有证据。
- 有效结果不得重跑；仅进程异常退出（无有效样本）且根因明确时按协议用剩余预算重试一次。

## 3. 三次 T1 与判定树（按序，条件执行）

固定条件（三次一致，除显式变量）：`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、不设 `RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles/`FASTDDS_BUILTIN_TRANSPORTS`/`ROS_STATIC_PEERS`；仅 `source /opt/ros/jazzy/setup.bash`（**不** source 项目 `install/`）；`HOME=/home/chen`，`ROS_HOME`/`ROS_LOG_DIR` 独占；topic `/agc_r16/chatter`；listener 先起、等待 2.0 s 后起 talker，talker 运行 6 s，随后回收两端。

**A1（必做）stock 对照 / 干净环境**：使用与第14轮探针**同一种 clean-env 语义**（`env -i` 等价：仅 `PATH`、`LANG=C.UTF-8`、`HOME`、`ROS_HOME`、`ROS_LOG_DIR`、`ROS_DOMAIN_ID`、`ROS_AUTOMATIC_DISCOVERY_RANGE`），stock `demo_nodes_cpp` listener + talker。
- 判定：listener 日志出现 ≥1 条 `I heard: [Hello World: N]` → **A1 成功**；否则 **A1 失败**。

**A2（必做）stock 对照 / 继承环境**：同一对 stock 程序、同一 topic/时序，但**继承调用方环境只额外显式设上方固定变量**（不 `env -i`，不清空 `AMENT_PREFIX_PATH`/`PYTHONPATH`/`LD_LIBRARY_PATH`，仍只 source jazzy）。
- 判定同 A1。
- **A1 与 A2 合判**：
  - A1/A2 均失败 → 进 **B**，最终倾向 **S-环境**；
  - A1 失败、A2 成功 → 进 **B**，最终倾向 **S-探针（clean-env 差异）**，并把"clean-env 下究竟缺哪一项"列为本轮未解缺口；
  - A1/A2 均成功 → **跳过 B**，倾向 **S-探针**，本轮交付"环境当前可通信 + 探针形态专属"的分裂证据，B 的预算退回不执行。

**B（条件执行）纯 OS loopback 双向通路**：两个 Python 进程（`python3 -B` 单文件标准库，写在本轮新根 `scripts/`，不 import rclpy、不建 participant、不装新包）对 `127.0.0.1:UDP`（端口取 20000–30000 空闲值并记录）做**双向**请求/应答：客户端发 5 个带序号 datagram，服务端逐条回显，客户端统计收到条数与序号集合；两个方向各一次（A→B 与 B→A），总时长 ≤10 s。
- 判定：两方向各 5/5 回显 → **loopback UDP 正常**，S-环境的解释必须落在 DDS/发现层而非 IP 通路；任一方向 <5/5 或全部丢失 → **落在 IP 通路**，须记录 `ip route get 127.0.0.1 ipproto udp` 与 `nstat` 前后差值作为同批证据。
- **B 的写入约束**：脚本只在新根 `scripts/` 新增，禁止改 `src/`、旧探针、旧驱动。

## 4. 交付物（新根）

新根 `experiments/w8-validation/20261028-peer-locator-and-stock-control-r1/`，可新增 `config/`、`log/`、`report/`、`evidence/`、`cases/`、`scripts/`。

必须保存的原始件（缺一即 invalid）：

1. 每次运行**完整 argv/命令**、启动与回收配对时钟（mono+wall）、PID/PGID/starttime、退出码（真实 `wait` RC），两端 stdout/stderr 与 ROS 日志原文；
2. 每次运行的环境快照（真实 `os.environ` 键值，可脱敏路径但不得删键）、`source` 后库映射（`/proc/self/maps` 中的 `libfastrtps`/`rmw_fastrtps` 实际路径）；
3. A1/A2 listener **原始日志文本**（判定 `I heard:` 只按原文，不按退出码，不用判据替代原文）；
4. B 的脚本源码 SHA、端口、每包序号、收发计数、`nstat` 前后差；
5. `ip rule`、`ip route get 127.0.0.1 ipproto udp`、`ip route get 127.0.0.1`、`ip -d addr show loopback0`、`ip -d link show lo`、`wslinfo --networking-mode`、`/proc/net/udp`（仅本进程相关端口）、`dmesg` 中 `CheckConnection` 计数与首末时间；
6. 每次运行后的残留核对（自有 PID/PGID 无存活、无遗留、无 `__pycache__` 写入工程目录）。

`report/analysis.md` 必须：

- 逐条给 A1/A2/B 的**原始判据**与对应原文片段（可截断但须保真），失败也要写"为何失败"而不是只写"未通过"；
- 明确写出本轮**新增的排除范围**与**仍未定位**边界，不得把 stock 成功解释为"通信恢复"，也不得把 stock 失败解释为"DDS 无效"；
- 单列一节"与既有 `p3-r2` 记录的可比性"：时间、domain、env、进程树差异逐项对照；
- 若进 B，须写清 B 结果如何改变 A 的结论。

## 5. 基线与写入白名单

- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`；保留全部 dirty/untracked（36 项）；不 reset/clean/commit/push/切分支。
- 受保护集：本轮根之外的全部文件（以 `config/codex_dispatch_baseline.json` 的 1927 项为准，逐项 size/SHA 复算）。
- **预期变化**（不计漂移）：`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 round16 勾选；`.coordination/CURRENT.md`、本轮 `report.md`/`review.md` 可写。
- **禁止改**：`src/`、`scripts/`、`toolchain/`、`build/`、`install/`、`spec`/`Runbook`/`request`/`review`、旧探针、旧驱动、历史源根、归档。
- 首次封存用 `scripts/evidence_archive.py`，不 `--force`，stdout 写 `/tmp/agc-w8-validation-r16-archive/`；独立核对 manifest/tar 真实根/checksum/retrieval 与源根逐文件相等。

## 6. 停止条件

出现以下任一即停止并如实回报，不现场扩改、不换配置重试：

1. A1 或 A2 出现 invalid（进程早退、关键原件缺失、回收不完整、超 30 s）；
2. 需要 root、需要改系统/网络/时钟/库、需要读 `/dev/shm` 内容或清理共享资源；
3. 需要起 ≥3 个进程、需要 ≥31 s 观测、需要构建或全链；
4. 受保护集出现未知漂移；
5. 预算耗尽。

## 7. 完成与交回

写本轮 `report.md`、更新 `CURRENT.md` 为 `待审查`，`send_message` 通知 Leader 后结束；**不轮询、不接下一单、不自行执行 C 类候选**。S2/S3/S4/gate/headless/科研结论不变，整链不归档。
