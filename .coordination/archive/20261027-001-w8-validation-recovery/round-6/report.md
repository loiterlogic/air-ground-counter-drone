<a id="round6-report"></a>
# 第 6 轮执行回报

- 任务 ID：20261027-001-w8-validation-recovery；轮次：6。
- 执行者：Worker（DSH 子会话 `e3e1d72b-6416-4f72-b66a-a246decef378`，沿用同一任务链）。
- 领取：2026-10-28T11:41:20+08:00（Asia/Shanghai），配对时钟 `monotonic_ns=12279030175106`、`wall_ns=1793158880850132296`、`pair_gap_ns=980`。
- 结束：2026-10-28T11:44:39+08:00，`monotonic_ns=12473944898669`、`wall_ns=1793159079465550205`、`pair_gap_ns=809`；领取→结束 **194.915 s = 3.25 min**，在 45 min（2700 s）内。
- 领取前/后状态：`待执行` → `执行中` → `待审查`。
- 结论：**G1/H1/G2 三次全部有效完成；G 与 H 同形。** 在 `LOCALHOST` 下，`FASTDDS_BUILTIN_TRANSPORTS` 未设置（G）与设为 `UDPv4`（H）**无可观测差异**：都是「先启动方单向 matched=1、后启动方 matched=0、六端 heard=0」。落在派工单判读**第 2 行**（本版本该环境变量未显示改善），**不据此归因 SHM**。分析见 [analysis.md](../../../../experiments/w8-validation/20261028-localhost-udp-abba-r1/report/analysis.md#round6-analysis)。

## 1. 接单基线

- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，与派工一致。
- 基线 `config/codex_dispatch_baseline.json` SHA256 `90b3743d3b1f29b9c336c18a774909ce5b400e74cd001a92d330675c622140d5`，与 `baseline_receipt.json`（SHA256 `b1dd02c4283d36154b2a843670f36de15bdf64cc78777ee15667d938722b1cc3`）所记相符。
- 逐文件重算：**实际 1227 条 = 回执 `files_count` 1227；1227/1227 相符，missing=0，changed=0**。回执计数与实际条目数本轮**已一致**（第 5 轮 1203/1204 元数据差已修正，D2 落实）。
- `mutable_handoff_excluded` 3 项（`CURRENT.md`、本轮 `report.md`、本轮 `review.md`）确认未进入冻结集；`absent_from_parent_or_previous_tree` 为空，无历史删除文件重现。
- 第 5 轮授权变化已入基线并核对通过：`tasks.md`/`checklist.md` 的 round-5 勾选、`_archive/.../20261028-unicast-discovery-probe-r1.post-archive-run-identity-walls.json` 侧车（D1/封存算术更正落实）。
- **无未知漂移**；未 reset/clean/commit/push/切分支。领取前无 `probe_layered`/`rclpy`/`fastdds` 进程，未接管他人进程。
- 探针只读复用（size 16850，SHA256 `137eeed310abd803fbbe27a4339bd7dc126ee5bd3b3e89668b81b08d73baf389`），未复制、未修改。

## 2. 实际改动（全部在白名单内）

新根 `experiments/w8-validation/20261028-localhost-udp-abba-r1/`（`config/` 预置两文件只读未改）：

| 文件 | 说明 |
|---|---|
| `config/run_identity.json` | 领取时钟、基线、T1 授权/使用、三次 attempt 汇总、双算术口径 |
| `config/run_attempt_driver.sh` | 实际使用的驱动（含就绪轮询 + `set -m` 可回收模型） |
| `config/evidence_manifest.json` | 归档脚本生成（首次封存） |
| `log/{g1,h1,g2}-{pub,sub}-events.jsonl` | 六端完整原始事件流 |
| `log/10-attempt-g1.log`、`11-attempt-h1.log`、`12-attempt-g2.log` | 驱动原始日志（就绪、RC、残留、环境） |
| `report/{g1,h1,g2}-{pub,sub}-result.json` | 六端进程结果 |
| `report/analysis.md` | 结果、判读、机制事实与限制 |

另按协议更新：本轮 `report.md`（本文件）、`.coordination/CURRENT.md`、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 **round6 执行事实勾选**（见 §9 D1）。

## 3. 单变量与启动时序

**单变量核对（机器比对三次 `probe_start.env`）**：G1 与 H1 的唯一实质差异是 `FASTDDS_BUILTIN_TRANSPORTS`（未设 vs `UDPv4`）；G1 与 G2 该变量相同。`ROS_HOME`/`ROS_LOG_DIR` 指向各 attempt 独占目录，属隔离要求非自变量。本轮**未设 `ROS_STATIC_PEERS`**（派工允许但不要求；LOCALHOST 已自动注入同值 peer，不设以缩小变量面）。

| attempt | 顺序 | transport | 就绪依据 | 就绪轮询 | 就绪→启动 | 参与者间隔 | 重叠 | 覆盖 |
|---|---|---|---|---:|---:|---:|---:|---|
| G1 | pub-first | 未设 | pub `events.jsonl` 的 `probe_start` | 0.530 s | 1.000 s | 1.599 s | 6.216 s | ✅ |
| H1 | pub-first | `UDPv4` | pub `events.jsonl` 的 `probe_start` | 0.530 s | 1.010 s | 1.524 s | 6.217 s | ✅ |
| G2 | sub-first | 未设 | sub `events.jsonl` 的 `probe_start` | 0.530 s | 1.000 s | 1.550 s | 6.219 s | ✅ |

- **关键修正已落实**：三次均**实际读到先启动方 `probe_start` 后**再等 ~1.0 s 启动后启动方；`READY_BASIS` 与 `READY_TO_LAUNCH_S` 逐次留痕。**未**用 wrapper `$!` 或 shell 启动时刻代替 participant 就绪（第 5 轮 E1 的 0.223 s 偏差未复现；本轮参与者间隔 1.524–1.599 s）。
- 就绪轮询 0.530 s 计入各次 <30 s 上限（三次 attempt span 8.830/8.880/8.830 s），未超期。

## 4. 三次结果（运行期峰值）

| attempt | 顺序 | transport | pub sent/heard | pub matched | pub graph(p/s) | sub matched | sub graph(p/s) | matched 事件(pub/sub) |
|---|---|---|---:|---:|---|---:|---|---|
| **G1** | pub-first | 未设 | 158 / **0** | **1** | 1/1 | **0** | 0/1 | 2 / 0 |
| **H1** | pub-first | `UDPv4` | 159 / **0** | **1** | 1/1 | **0** | 0/1 | 2 / 0 |
| **G2** | sub-first | 未设 | 119 / **0** | **0** | 1/0 | **1** | 1/1 | 0 / 2 |

- 六端 `exit_code` 全 0，`invalid_reasons` 全空，采样 119–160/端，事件流完整，零 `incompatible_qos_event`。
- **每次都是先启动方 matched=1、后启动方 matched=0**，方向随"谁先启动"翻转；先启动方 matched 事件在 +1.7 s 左右（`total=1,current=1`），在 +7.7 s 左右回落 `current=0`（对端退出）。
- **六端 `heard_n` 全 0**。
- **G1 与 H1 毫秒级同形**：matched 出现 1.780 vs 1.705 s，回落 7.811 vs 7.736 s。

> **口径**：上表为**运行期峰值**；先启动方 `final.matched_*=0` 是对端先退出后的正常回落，**不得**误读为"从未匹配"。

## 5. 判读（对照派工单第 26–32 行）

落在**第 2 行**：G/H 同形 → 本版本环境变量未显示改善，与 LOCALHOST 覆盖 builtin transport 的机制一致；**不据此归因 SHM**。

- ✗ 不是"G 单向、H 双向且 `heard>0`"（H 未变双向，heard 仍全 0）。
- ✗ 不是"双向 graph/matched 但 heard=0"（始终单向）。
- ✗ 不是"G 未复现第 4 轮形态"——**G 复现了**（G1 pub-first 与第 4 轮 C1 同形；G2 sub-first 与 D1 同形），构成该形态的又一次独立复现。

可支持的克制结论：**在 LOCALHOST 下设置 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 未改变可观测的发现/匹配/消费形态。** 不能推出 UDPv4 本身无效、SHM 是根因或通信已恢复。

## 6. 机制层面事实（离线读已验收材料；非本次运行观测）

1. `rmw_fastrtps 8.4.4 participant.cpp` 第 185–206 行 LOCALHOST 分支设 `use_builtin_transports = false`（第 193 行），并手动挂载 `SharedMemTransportDescriptor` 与 `UDPv4TransportDescriptor`（`maxInitialPeersRange=32`）。
2. `FASTDDS_BUILTIN_TRANSPORTS` 仅在 `use_builtin_transports=true` 的 builtin 路径生效；官方 2.14.7 快照写明其它情况 "no effect"（第 2 轮诊断 §2.2 已记录）。
3. 静态 peer 在 LOCALHOST 下自动注入 `127.0.0.1`（第 247–252 行）。

【推断】H 与 G 预期同形，两组实跑同一套 SHM+UDPv4 栈；本轮观测与之一致。**但本轮未回读 transport 实配**，故不宣称"已确认两者 transport 完全相同"。

## 7. 限制

- **L1**：`heard=0` 六端全成立；即使匹配成功侧也未收数据，匹配 ≠ 送达，本轮未解释该断点。
- **L2**：matched/graph 为本进程视角，"先启动方匹配"不代表对端对称。
- **L3**：`FASTDDS_BUILTIN_TRANSPORTS` 的**实际生效状态未回读**（无 transport 读回，release 库不编译匹配 INFO）。本轮只观测到"设与不设，可观测结果无差别"。
- **L4**：G 有两次（pub-first/sub-first）互相印证；**H 仅 1 次（pub-first）无重复**。若要主张 H 与 G 严格同形，仍需 H 的 sub-first 对照片，**本轮预算不含**。
- **L5**：未做 A 同进程正/负控制，探针有效性依赖第 3 轮已验收结论。
- **L6**：LOCALHOST 下 SHM 与 UDPv4 并存，本轮无手段区分二者，**不据此归因 SHM**。

## 8. 时钟、回收与封存

- **时钟**：六端 `wall_minus_mono` 漂移均 <1 µs，`pair_gap` 最大 3.6 µs。**本轮无墙钟跳变**（不同于第 5 轮的 +1.228 s / +0.842 s），wall 与 monotonic 同值，间隔判读不受影响。
- **真实 RC**：驱动用 `set -m`（每探针独立 PGID 且可被 `wait` 回收）；三次 `WAIT_RC_PUB/SUB` 均 0，与 `result.json`/`probe_end` 的 `exit_code=0` **交叉一致**，`PIDS_MATCH=true`。未重复第 5 轮 `setsid` 父 PID 缺陷。
- **残留**：三次 `RESIDUE=0`、`STRAY=[]`；全部结束后（11:43:13、11:44:39）扫描无 `probe_layered`/`rclpy`。未发 SIGTERM。
- **算术复核（封存前完成）**：三次 attempt span 8.830/8.880/8.830 s，**单次均 <30 s**。合计口径二选：
  - **驱动 attempt span 之和 = 26.540 s**（含就绪轮询与 1 s 间隔）；
  - **各次两端进程 wall 最大值之和 = 24.547 s**（≈participant 生命周期）。
  - 本报告开头用 **24.547 s** 汇总；§8 同时给出 26.540 s 驱动口径。**两口径均 <90 s**，不矛盾。
- **封存**：`python3 scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-localhost-udp-abba-r1`，**RC 0**，`artifacts=20 verify=True files=21 mismatches=0`，**未用 `--force`**；stdout 写源根外 `/tmp/agc-w8-validation-r6-archive.log`。
- tar SHA `d9f53a9bca443fe808ce8d21dfbe40048d5dfcba14e55cc032bfbdf2f5503d2b`，与 `.tar.sha256` 及 `.retrieval.json.archive_sha256` **三处一致**；tar 实际根目录 `20261028-localhost-udp-abba-r1/`。
- **独立复核**：manifest 20 项 size/SHA 逐项重算 **0 不符**；`tar -tf` 21 条目与源根文件集**完全相等**（无缺无多）；解包至另一路径逐文件哈希 → **root==tar，21/21 一致**；retrieval `verified=true`、`files_checked=21`、`mismatches=[]`。

## 9. 偏离与待裁定

- **D1（白名单内的冻结文件变化）**：按派工"只在 round6 段勾选"更新了 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md`。这两文件在本轮冻结集内（第 5 轮 D1 已裁定"勾选保留、下一轮基线显式接纳"），因此**封存后基线复核会显示这 2 个文件 changed**，属**已授权预期变化，非未知漂移**；除此之外无任何受保护文件变化。
- **D2（算术口径）**：见 §8，给出两个口径并明确差异来源，未混用。
- **D3（H 无重复）**：见 L4。本轮按预算只跑 1 次 H，未追加未授权样本。

## 10. 未执行项

- **未执行第 4 次 T1**（预算 3 次用尽）。
- **未重跑 G1/H1/G2**（三次均 exit 0、无 `invalid_reasons`，不满足重跑条件；有效结果不得重跑）。
- **未做 A 同进程正/负控制**（派工要求复用已验收探针）。
- **未回读 transport 实配**（无回读手段且派工限定不新增 observer/daemon）。
- 未读 `/dev/shm`、未清理共享资源或他人进程、未构建、未抓包、未启 GZ/PX4/GUI/headless/全链、未用 root、未发 SIGTERM。
- 未改 `spec.md`、`request.md`、`review.md`、契约、Runbook、`src/`、`scripts/`、`toolchain/`、`build/`、`install/`、旧证据或历史归档。
- 未改 `gate`（仍 `not_evaluable_as_specified`）、headless 授权、P1 v5 `inconclusive`、P2 v3 `falsified`/保留 c2、W7-c `deferred`、W8-E2 未预注册；**S2/S3/S4 未开放**。

## 11. 交接

- 本轮只交付 **LOCALHOST 下 builtin transport 单变量的探针级对照证据**，不构成通信恢复、S2 通过、整链完成或工程验收。
- 需 Leader 裁定的两点：① G/H 同形是否足以结掉"UDPv4 环境变量"这一候选分支（本轮只支持"该变量无改善"，不支持 UDPv4 机制本身无效）；② 若需 H 的 sub-first 重复以完成 G/H 严格同形比对，须另派轮次（本轮预算不含）。
- 状态已置 `待审查`，已用 `send_message` 通知 Leader。按协议：**不等待、不轮询、不接下一单**。
