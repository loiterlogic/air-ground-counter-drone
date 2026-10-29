<a id="round7-report"></a>
# 第 7 轮执行回报

- 任务 ID：20261027-001-w8-validation-recovery；轮次：7。
- 执行者：Worker（DSH 子会话 `e3e1d72b-6416-4f72-b66a-a246decef378`，沿用同一任务链）。
- 领取：2026-10-28T11:54:47+08:00（Asia/Shanghai），配对时钟 `monotonic_ns=13072396318273`、`wall_ns=1793159687515891550`、`pair_gap_ns=925`。
- 结束：2026-10-28T11:57:00+08:00，`monotonic_ns=13203291089635`、`wall_ns=1793159820939385205`、`pair_gap_ns=1329`；领取→结束 **130.895 s = 2.18 min**，在 45 min（2700 s）内。
- 领取前/后状态：`待执行` → `执行中` → `待审查`。
- 结论：**J1/K1 两次均有效完成，但旧形态完整复现。** 在 `SUBNET + ROS_STATIC_PEERS=127.0.0.1 + FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 下，两次都是「先启动方单向 matched=1、后启动方对先启动方不可见、四端 heard=0」，方向随"谁先启动"翻转。落在判读**第 2 行**：**故障不局限于 LOCALHOST 分支；不得归因 SHM 或 UDP 本身。** 分析见 [analysis.md](../../../../experiments/w8-validation/20261028-subnet-udp-probe-r1/report/analysis.md#round7-analysis)。

## 1. 接单基线

- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，与派工一致。
- 基线 `config/codex_dispatch_baseline.json` SHA256 `1bd1000f0c6b8b5fbc2deb3f2de9b665e3bfd06d81e564a33579db1bed59a4d6`，与 `baseline_receipt.json`（SHA256 `a944f812bb2291f24fafd37fa94454e06b6cb47185b0760e675304198f86b545`）所记一致。
- 逐文件重算：**实际 1254 条 = 回执 `files_count` 1254；1254/1254 相符，missing=0，changed=0**。
- `mutable_handoff_excluded` 3 项（`CURRENT.md`、本轮 `report.md`、本轮 `review.md`）确认未进入冻结集；`absent_from_parent_or_previous_tree` 为空，无历史删除文件重现。
- 第 6 轮授权变化已入基线并核对通过（round-6 勾选所在 `tasks.md`/`checklist.md` 均在冻结集内且 SHA 相符）。
- **无未知漂移**；未 reset/clean/commit/push/切分支。领取前无 `probe_layered`/`rclpy`/`fastdds` 进程，未接管他人进程。
- 探针只读复用（size 16850，SHA256 `137eeed310abd803fbbe27a4339bd7dc126ee5bd3b3e89668b81b08d73baf389`），未复制、未修改。

## 2. 实际改动（全部在白名单内）

新根 `experiments/w8-validation/20261028-subnet-udp-probe-r1/`（`config/` 预置两文件只读未改）：

| 文件 | 说明 |
|---|---|
| `config/run_identity.json` | 领取时钟、基线、配置包、T1 授权/使用、两次 attempt 汇总、双算术口径 |
| `config/run_attempt_driver.sh` | 实际使用的驱动（`probe_start` 就绪轮询 + `set -m` 可回收模型） |
| `config/evidence_manifest.json` | 归档脚本生成（首次封存） |
| `log/{j1,k1}-{pub,sub}-events.jsonl` | 四端完整原始事件流 |
| `log/10-attempt-j1.log`、`log/11-attempt-k1.log` | 驱动原始日志（就绪、RC、残留、`/proc` 环境快照） |
| `report/{j1,k1}-{pub,sub}-result.json` | 四端进程结果 |
| `report/analysis.md` | 结果、判读、机制事实与限制 |

另按协议更新：本轮 `report.md`（本文件）、`.coordination/CURRENT.md`、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 **round7 执行事实勾选**（见 §9 D1）。

## 3. 配置包与启动时序

**固定配置包（两次完全相同，仅 ROS_HOME/ROS_LOG_DIR 各自独占）**：`ROS_DOMAIN_ID=39`、`ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`、`ROS_STATIC_PEERS=127.0.0.1`、`FASTDDS_BUILTIN_TRANSPORTS=UDPv4`；不设 `RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles；topic `/agc_probe_subnet_udp/chatter`、`std_msgs/String`、RELIABLE depth10。**本包不拆分 multicast / 静态 peer / UDPv4 的必要条件。**

| attempt | 顺序 | 就绪依据 | 就绪轮询 | 就绪→启动 | 参与者间隔 | 重叠 | 覆盖 |
|---|---|---|---:|---:|---:|---:|---|
| J1 | pub-first | pub `events.jsonl` 的 `probe_start` | 0.750 s | 1.000 s | 1.574 s | 6.248 s | ✅ |
| K1 | sub-first | sub `events.jsonl` 的 `probe_start` | 0.560 s | 1.000 s | 1.534 s | 6.232 s | ✅ |

- 两次均**实际等到先启动方 `probe_start`** 后才等 ~1.0 s 启动后启动方（`READY_BASIS`/`READY_TO_LAUNCH_S` 留痕），就绪轮询计入 30 s。
- 沿用了第 6 轮 `set -m` 独立 PGID 且可 `wait` 的驱动模型。

**环境证据口径（重要）**：探针 `probe_layered.py` 的 `probe_start.env` 硬编码只采 6 个键，**不含 `ROS_STATIC_PEERS`**（源码第 341–344 行）。该变量的权威证据是**驱动对 `/proc/<pid>/environ` 的逐进程快照**（两份 log 各四行 `ENV=[...ROS_STATIC_PEERS=127.0.0.1...]`）。两份证据在共同键上一致；**未**把探针缺失该键误读为"未设置"。

## 4. 两次结果（运行期峰值）

| attempt | 顺序 | pub sent/heard | pub matched | pub graph(p/s) | sub matched | sub graph(p/s) | matched 事件(pub/sub) |
|---|---|---|---:|---|---:|---|---|
| **J1** | pub-first | 158 / **0** | **1** | 1/1 | **0** | 0/1 | 2 / 0 |
| **K1** | sub-first | 119 / **0** | **0** | 1/0 | **1** | 1/1 | 0 / 2 |

- 四端 `exit_code` 全 0，`invalid_reasons` 全空，采样 119–159/端，事件流完整，零 `incompatible_qos_event`。
- **每次都是先启动方 matched=1、后启动方 matched=0**，方向随"谁先启动"翻转。
- 先启动方 matched 事件：`total=1,current=1` 于 +1.774 s（J1 pub）/ +1.722 s（K1 sub）；`current=0` 回落于 +7.819 s / +7.760 s（对端退出）。
- **四端 `heard_n` 全 0**；**后启动方对先启动方 graph 恒 0**（J1 sub 的 `graph_pub_count`、K1 pub 的 `graph_sub_count` 全程不可见）。

> **口径**：上表为**运行期峰值**，非 `result.json.final`。先启动方 `final.matched_*=0` 是对端先退出后的正常回落，**不得**误读为"从未匹配"。

## 5. 判读（对照派工单第 26–30 行）

落在**第 2 行**——"仍复现先启动方单向匹配、后启动方不可见、`heard=0`：故障不局限于 LOCALHOST 分支；不得归因 SHM 或 UDP 本身"。

- ✗ 非"两次均双向且 `heard>0`"：**该配置包未成立为可用配置**。
- ✗ 非"双向 graph/matched 但 heard=0"：始终单向，从未双向。
- ✗ 非"其他形态 / 旧形态未复现"：**旧形态确实完整复现**（两次方向对称翻转）。

可支持的克制结论：
1. **`SUBNET + 静态 peer + UDPv4` 未形成双向通信**；第 4/6 轮的形态**完整复现**。
2. 该形态**不局限于 LOCALHOST 自定义栈**：本轮改用非 LOCALHOST 的 discovery range，`use_builtin_transports` 走默认路径、环境变量具备生效语义、静态 peer 被注入并附加 multicast initial peer（§6），结果**不变**。
3. 因此**不能**把既往观测归因于"LOCALHOST 分支自建 SHM+UDPv4 栈"这一实现细节。
4. **仍不能**归因 SHM、UDP 本身、QoS、权限或 executor；**未**定位"为何先启动方能匹配、后启动方不可见"。

## 6. 机制层面事实（离线读已验收材料；非本次运行观测）

1. **SUBNET 不覆盖 builtin transport**：`rmw_fastrtps 8.4.4 participant.cpp` 第 209–211 行 `RMW_AUTOMATIC_DISCOVERY_RANGE_SUBNET` 分支仅 "Nothing to do; use the default FastDDS behaviour"，**不设** `use_builtin_transports = false`（该赋值只出现于 LOCALHOST 分支第 193 行）→ `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 本轮**具备生效语义**。
2. **静态 peer 在 SUBNET 下会注入**：第 221–245 行 `if (LOCALHOST || SUBNET)` 覆盖 SUBNET，`initialPeersList` 被填充 `127.0.0.1`。
3. **SUBNET 且已有静态 peer 时追加 multicast initial peer**：第 254–263 行在 `SUBNET && initialPeersList.size()` 时 push `239.255.0.1`。

【推断】本轮配置确实是"真正让 builtin UDPv4 + 静态 peer + 多播 initial peer 生效"的组合，与第 6 轮 LOCALHOST 覆盖变量的情形**不同**。在此前提下结果仍为单向/零消费，说明该形态**不由 LOCALHOST 分支解释**。**但未做 transport 实配回读**，故不宣称"已确认实际 transport 栈与预期完全一致"。

## 7. 限制

- **L1**：`heard=0` 四端全成立；即使匹配成功侧也未收数据。匹配 ≠ 送达，本轮未解释该断点。
- **L2**：matched/graph 为本进程视角；"先启动方匹配"不代表对端对称。
- **L3**：**未回读 transport 实配**，只确保"配置语义上环境变量应生效"。
- **L4**：J1/K1 各仅 1 次，无重复；未扫启动间隔、domain、QoS。
- **L5**：未做 A 同进程正/负控制，探针有效性依赖第 3 轮已验收结论。
- **L6**：**不拆分** multicast / 静态 peer / UDPv4 必要条件（派工明确要求），故无法判断哪一项或组合导致结果。
- **L7**：两次 T1 不足以排除 1.5 s 附近启动间隔的时序效应。

## 8. 时钟、回收与封存

- **时钟**：四端 `wall_minus_mono` 漂移均 <1 µs，`pair_gap` 最大 3.5 µs。**无墙钟跳变**。
- **真实 RC**：`set -m` 下两次 `WAIT_RC_PUB/SUB` 均 0，与 `result.json`/`probe_end` 的 `exit_code=0` **交叉一致**，`PIDS_MATCH=true`。
- **残留**：两次 `RESIDUE=0`、`STRAY=[]`；全部结束后（11:55:48、11:57:00）扫描无 `probe_layered`/`rclpy`。未发 SIGTERM，探针自行结束。
- **算术复核（封存前完成）**：J1 span 9.170 s、K1 span 8.870 s，**单次均 <30 s**。合计两口径：
  - **驱动 attempt span 之和 = 18.040 s**；
  - **各次两端进程 wall 最大值之和 = 16.453 s**。
  - 两口径**均 <90 s**；本回报 §3 引用单次驱动口径，§8 与 analysis §9 同时给出两口径，未混用。
- **封存**：`python3 scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-subnet-udp-probe-r1`，**RC 0**，`artifacts=15 verify=True files=16 mismatches=0`，**未用 `--force`**；stdout 写源根外 `/tmp/agc-w8-validation-r7-archive.log`。
- tar SHA `aac4341e2d4736a59fa47b81320067035e21ab715f3cec942cac5a9eb2e7421d`，与 `.tar.sha256` 及 `.retrieval.json.archive_sha256` **三处一致**；tar 实际根 `20261028-subnet-udp-probe-r1/`。
- **独立复核**：manifest 15 项 size/SHA **0 不符**；`tar -tf` 16 条目与源根文件集**完全相等**；解包至另一路径逐文件哈希 → **root==tar，16/16 一致**；retrieval `verified=true`、`files_checked=16`、`mismatches=[]`。

## 9. 偏离与待裁定

- **D1（白名单内的冻结文件变化）**：按派工"只在 round7 段勾选"更新了 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md`。这两文件在本轮冻结集内（第 5/6 轮已裁定"勾选保留、下一轮基线显式接纳"），封存后基线复核会显示这 2 个文件 changed，属**已授权预期变化，非未知漂移**；除此之外无任何受保护文件变化。
- **D2（环境证据口径）**：见 §3，`ROS_STATIC_PEERS` 的权威证据为驱动 `/proc` 快照而非探针 env 列表。此为探针只读复用（不得修改）的既有约束，非本轮缺陷；已显式披露避免误读。
- **D3（算术口径）**：两口径 18.040 / 16.453 s 并列，差异来源为就绪轮询与 1.0 s 间隔，未混用。

## 10. 未执行项

- **未执行第 3 次 T1**（预算 2 次用尽）。
- **未重跑 J1/K1**（均 exit 0、无 `invalid_reasons`，不满足重跑条件；有效结果不得重跑）。
- **未拆分配置包必要条件**（派工明确禁止）。
- **未回读 transport 实配**（无回读手段，且派工禁新增 observer/daemon）。
- 未做 A 同进程正/负控制（派工要求复用已验收探针）。
- 未读 `/dev/shm`、未清理共享资源或他人进程、未构建、未抓包、未启 GZ/PX4/GUI/headless/全链、未用 root、未发 SIGTERM。
- 未改 `spec.md`、`request.md`、`review.md`、契约、Runbook、`src/`、`scripts/`、`toolchain/`、`build/`、`install/`、旧证据或历史归档。
- 未改 `gate`（仍 `not_evaluable_as_specified`）、headless 授权、P1 v5 `inconclusive`、P2 v3 `falsified`/保留 c2、W7-c `deferred`、W8-E2 未预注册；**S2/S3/S4 未开放**。

## 11. 交接

- 本轮只交付 **SUBNET + 静态 peer + UDPv4 配置包的探针级顺序对照证据**，不构成通信恢复、S2 通过、整链完成或工程验收。
- 需 Leader 裁定的两点：① 该配置包已失败，是否还有值得派的 discovery 配置分支（本轮已排除"LOCALHOST 实现细节"这一解释）；② 若下一轮要拆分 multicast/静态 peer/UDP 或回读 transport 实配，需显式改派工口径（本轮明确禁止）。
- 状态已置 `待审查`，已用 `send_message` 通知 Leader。按协议：**不等待、不轮询、不接下一单**。
