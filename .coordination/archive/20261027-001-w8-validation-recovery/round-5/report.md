<a id="round5-report"></a>
# 第 5 轮执行回报

- 任务 ID：20261027-001-w8-validation-recovery；轮次：5。
- 执行者：Worker（DSH 子会话 `e3e1d72b-6416-4f72-b66a-a246decef378`）。
- 领取：2026-10-28T11:18:51+08:00（Asia/Shanghai），配对时钟 `monotonic_ns=10962867788113`、`wall_ns=1793157531928272741`、`pair_gap_ns=1360`。
- 结束：2026-10-28T11:33:50+08:00，`monotonic_ns=11838843632734`、`wall_ns=1793158430975036101`、`pair_gap_ns=1045`；领取→结束 **875.976 s = 14.60 min**，在 45 min（2700 s）内。
- 领取前/后状态：`待执行` → `执行中` → `待审查`（任务 ID、轮次与派工单一致）。
- 结论：**两次 T1 均有效完成，但结果为「对称性完全隔离」——不是派工单预设的任一形态。** 在 `OFF + ROS_STATIC_PEERS=127.0.0.1 + FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 下，两 participant **互不发现、互不匹配、互不送达**（双向 `graph` 互不可见、全端 `matched=0`、全端 `heard=0`），pub-first 与 sub-first **同形**，第 4 轮"先启动方匹配"形态**未复现**。分析见 [analysis.md](../../../../experiments/w8-validation/20261028-unicast-discovery-probe-r1/report/analysis.md#round5-analysis)。

## 1. 接单基线

- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，与派工单一致。
- 派工基线 `config/codex_dispatch_baseline.json` SHA256 `3bfa1a364349a49c0aedd318d5f090e87841bfc0b82716814f23f24f3c8968f3`，与 `baseline_receipt.json`（SHA256 `54099d72c5c2c1c615d5cd1a8dbe4e496573e834eafbf3d41f39a965d3f65b88`）所记相符。
- 逐文件重算：**1204/1204 相符，missing=0，changed=0**；`mutable_handoff_excluded` 3 项确认未进入冻结集；`absent_from_parent_or_previous_tree` 9 项确认**均未重新出现**。**领取时无未知漂移。**
- **元数据不一致（已记录，非文件漂移）**：派工单与 `baseline_receipt.json` 均写 `files_count = 1203`，而 `codex_dispatch_baseline.json` 的 `files` 实际含 **1204** 个路径（无重复键、无自引用、无绝对路径或 `..`）。1204 条 size/SHA 全部可复算通过，属**回执计数字段与基线内容的 ±1 记录差异**，不影响任何被保护文件完整性。本轮按**实际 1204 条全核对**执行，交 Leader 裁定回执口径。
- 既有 dirty/untracked 全部保留；未 reset/clean/commit/push/切分支。
- 领取前检查既有运行：无 `ros2`/`rclpy`/`fastdds`/`probe_layered`/`gz sim`/`px4` 进程；未接管、未终止任何他人进程。

## 2. 实际改动（全部为本单白名单内）

新产物根 `experiments/w8-validation/20261028-unicast-discovery-probe-r1/`（`config/` 预置两文件**只读未改**）：

| 文件 | 说明 |
|---|---|
| `config/run_identity.json` | 领取时钟、基线、T1 授权/使用、两次 attempt 汇总、异常登记 |
| `config/run_attempt_driver.sh` | 实际使用的驱动（v5，已修正 E1 缺陷） |
| `config/evidence_manifest.json` | 归档脚本生成（首次封存） |
| `log/e1-{pub,sub}-events.jsonl`、`log/f1-{pub,sub}-events.jsonl` | 四端完整原始事件流 |
| `log/10-attempt-e1.log`、`log/11-attempt-f1.log` | 驱动原始日志（E1 含已登记缺陷字段，**原样保留未覆盖**） |
| `log/10-attempt-e1.CORRECTION.json` | E1 驱动缺陷说明 + 权威值来源 |
| `report/e1-{pub,sub}-result.json`、`report/f1-{pub,sub}-result.json` | 四端进程结果 |
| `report/analysis.md` | 结果、判读、机制事实与限制 |

另按协议更新：本轮 `report.md`（本文件）、`.coordination/CURRENT.md`、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 **round-5 执行事实勾选**（见 §10 D1）。

- **探针未复制未修改**：只读复用 `experiments/w8-validation/20261027-layered-matched-probe-r1/scripts/probe_layered.py`（size 16850，SHA256 `137eeed310abd803fbbe27a4339bd7dc126ee5bd3b3e89668b81b08d73baf389`）。
- 未改 `src/`、`scripts/`、`toolchain/`、`build/`、`install/`、旧证据、历史归档、`request.md`、`review.md`、`spec.md`、契约与 Runbook。

## 3. T1 attempt 与命令

| # | attempt | 顺序 | 进程 | 参与者启动间隔 | 重叠窗口 | 退出码 | attempt 墙钟 |
|---|---|---|---:|---:|---:|---|---:|
| 1 | E1 | pub 先起（8 s）→ sub（6 s） | 2 | **0.223 s** | 6.234 s | pub 0 / sub 0 | 9.502 s |
| 2 | F1 | sub 先起（8 s）→ pub（6 s） | 2 | 1.079 s | 6.245 s | pub 0 / sub 0 | 9.028 s |

- 命令模板（两次相同，仅 `--mode`/`--run-seconds`/顺序与 tag 不同）：
  `env -i ROS_DOMAIN_ID=39 ROS_AUTOMATIC_DISCOVERY_RANGE=OFF ROS_STATIC_PEERS=127.0.0.1 FASTDDS_BUILTIN_TRANSPORTS=UDPv4 HOME=/home/chen ROS_HOME=<tmp>/ros_home ROS_LOG_DIR=<tmp>/ros_log PATH=... bash -c "source /opt/ros/jazzy/setup.bash && exec python3 probe_layered.py --mode <pub|sub> --out <tmp>/<side> --topic /agc_probe_unicast/chatter --namespace-tag <tag> --run-seconds <s>"`
- 仅 source `/opt/ros/jazzy`；未设 `RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles；`env -i` 保证**仅进程级**改动、不继承父 shell 的 `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`。
- 每探针独立 PGID（E1：10016/10041；F1：10525/10545），PID/PGID/starttime 与 `/proc/<pid>/environ` 逐进程快照留痕。
- **累计 T1 墙钟 18.530 s / 90 s**（9.502 + 9.028）；单次均 ≤30 s；每次恰 2 个参与进程；普通用户；临时目录独占 `/tmp/agc-w8-validation-r5-{e1,f1}/`。
- 两次均**未**重跑；`T1: 2 次` 用尽，无第 3 次。

## 4. 结果（按运行期峰值）

| attempt | 顺序 | pub sent/heard | pub matched 峰值 | pub graph(pub/sub) | sub matched 峰值 | sub graph(pub/sub) | matched 事件 | incompatible QoS |
|---|---|---|---:|---|---:|---|---:|---:|
| **E1** | pub-first | 158 / **0** | **0** | 1 / **0** | **0** | **0** / 1 | **0 / 0** | 0 / 0 |
| **F1** | sub-first | 119 / **0** | **0** | 1 / **0** | **0** | **0** / 1 | **0 / 0** | 0 / 0 |

- 四端 `exit_code` 全 0，`invalid_reasons` 全空，采样帧 119–158/端，事件流完整（含 `probe_start`/`phase_begin`/`sample`/`phase_end`/`probe_end`）。
- 两端各自**只看见自己**的端点：pub 见 `graph_pub_count=1, graph_sub_count=0`；sub 见 `graph_sub_count=1, graph_pub_count=0`。
- **双向 `matched` 峰值恒 0**，四端**零 `matched_event`**、零 `incompatible_qos_event`。
- **四端 `heard_n` 全 0**。
- 顺序翻转后**结果同形**：两次都**没有**"先启动方匹配"。

> **口径**：上表为**运行期峰值**（全部 `sample` 帧的 max），非 `result.json.final`。本次两口径恰好一致（全程恒 0），不存在第 4 轮的 final/peak 误读风险。

## 5. 判读（对照派工单判读表）

本轮**不落在派工单预设的任一行**，按末行"与上述不同：如实记录受限观测，不强行映射根因"处理：

| 派工单预设行 | 本轮实测 |
|---|---|
| 两次均双向 graph/matched 且 `heard>0` → 该配置包成立 | ✗ 无 matched、无 heard |
| 仍只有先启动方 graph/matched、后启动方不可见 → 未消除原形态 | ✗ **连先启动方也没有 matched** |
| 双侧 graph/matched>0 但 `heard=0` → 发现成立、送达是独立缺口 | ✗ 双侧 matched 均 0、双向 graph 互不可见 |

准确表述：**对称性完全隔离**（symmetric total isolation）——两次顺序对照同形，两个 participant 互不发现、互不匹配、互不送达；第 3/4 轮在 `LOCALHOST` 下观测到的"先启动方 matched=1"**未在本配置包下复现**。

因此本轮**不能**被读作：
- ✗ "UDPv4 单播消除了原形态"（原形态并未出现，谈不上消除）；
- ✗ "SHM/UDP/权限/QoS 是根因"（本轮 0 matched，连发现层都未建立）；
- ✗ "通信已恢复"（`heard` 全 0）。

可支持的克制结论：**该最小配置包在本轮两次 T1 中未能建立任何跨进程发现通路**；至于"是否只因此配置包选错"而非"环境另有问题"，本轮**不足以判定**（见 §6 L2）。

## 6. 机制层面事实（离线读取既有已验收材料；非本次运行观测）

以下三点用于解释"为何该结果在预期之内"，**不作为根因结论**，也不替代运行期证据：

1. **`OFF` 分支不消费静态 peer**：`rmw_fastrtps 8.4.4 participant.cpp` 第 172–184 行的 `RMW_AUTOMATIC_DISCOVERY_RANGE_OFF` 分支只做三件事——participant 分配上限锁 1、清空 `metatrafficMulticastLocatorList`、补一个单播定位器；**既不读 `static_peers_count`、也不写 `initialPeersList`**（该分支内无 `static_peers`/`initialPeers` 任何引用）。
2. **静态 peer 只在 `LOCALHOST`/`SUBNET` 下注入**：同文件第 221–245 行，`initialPeersList` 填充被 `if (LOCALHOST || SUBNET)` 包住。故 `ROS_STATIC_PEERS=127.0.0.1` 在 `OFF` 下被 rcl 解析并传给 rmw（`rcl-jazzy-discovery_options.c` 第 34、110–172 行），**但到不了 participant QoS**。
3. **官方文档同口径**：`jazzy-discovery.html`（SHA256 `7f5b1167d8ab9a7689064cdadd847f917dcc5efab0a18e7f2bb38c2380eb8316`）写明 "OFF means the node won't discover any other nodes, even on the same machine"，且同主机矩阵中 **Off 行/列全为 X**（无论有无 static peer）。

【推断】`ROS_AUTOMATIC_DISCOVERY_RANGE=OFF` 与 `ROS_STATIC_PEERS=127.0.0.1` 在本版本 rmw 下**互相抵消**：本轮配置包实际上等于"关闭全部发现"。若后续要检验"静态单播能否替代多播发现"，语义上应使用 **`LOCALHOST`（或 `SUBNET`）+ 静态 peer**，而非 `OFF` + 静态 peer——但**这属于下一轮的范围/口径决定，归 Leader，本轮未执行也未自行改配置**。

## 7. 明确的限制

- **L1**：`matched=0` 与 `heard=0` 同时成立，本轮**无法区分**"未发现"与"已发现但未匹配/未送达"；发现层未建立已足以解释全部现象。
- **L2**：`OFF`、`ROS_STATIC_PEERS`、`FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 是一个**配置包**，本轮不拆分必要条件（派工单已限定不得拆分）。特别是：`UDPv4` 的传输效果**未被单独验证**（无 transport 配置回读），因此本轮**不能**说"UDPv4 无效"。
- **L3**：两次各仅 1 次运行；未扫启动间隔、未扫 domain、未扫 QoS、未扫其他发现范围。
- **L4**：未做 A 同进程正/负控制（派工单要求复用已验收探针、不重做 A），探针有效性依赖第 3 轮已验收的 A 步结论。
- **L5**：`matched`/`graph` 均为**本进程视角**；"互不可见"是两端各自视角的合并陈述。
- **L6**：本轮无 middleware 日志可读（既有诊断已证 release 库不编译匹配成功 INFO），观测面仍只有 `graph`/`matched`/`heard` 三层。

## 8. 时钟、驱动缺陷与追加核验

- **墙钟跳变**：E1 pub 侧 `wall_minus_mono` 在 +~1.2 s 处单步 **+1.228 s**；F1 sub 侧 **+0.842 s**；其余端稳定（<1 µs）。因此**所有间隔/重叠/超时判读一律用 monotonic**。
- **驱动缺陷（仅影响 E1 的驱动日志字段，不影响探针证据）**：E1 驱动 v1 用 `setsid … &` 启动探针，`setsid` 会 fork，`$!` 指向**瞬时父进程**而非探针，导致 `wait` 返回 127、残留检查命中已退出的父进程。故 `log/10-attempt-e1.log` 中的 `PUBRC/SUBRC=127`、`RESIDUE=2`、`WALL_S=1.166` **均为驱动缺陷，不是探针结果**。
  - 原始日志**原样保留、未覆盖**；更正与权威来源见 `log/10-attempt-e1.CORRECTION.json`。
  - 权威值取自探针自身产物（`result.json` 与 `probe_end` 事件互证）：pub exit 0 / 8.274 s / PID 10016 / PGID 10016；sub exit 0 / 6.234 s / PID 10041 / PGID 10041。
  - **残留复核**：2026-10-28T11:23:02 与 11:29:24 两次独立扫描均**无** `probe_layered`/`rclpy` 进程。
- **驱动修正与自测**：E1 后改为 `set -m`（每探针独立 PGID 且仍可被 `wait` 回收），并在执行 F1 **之前**用假探针在 `/tmp` 沙箱自测（**不涉及 ROS、不占 T1、未写产物根**），确认退出码、PGID、env 快照均正确；F1 的 `WAIT_RC_PUB=0 WAIT_RC_SUB=0` 与 `result.json` 交叉一致。
- **E1 启动间隔偏小（0.223 s，派工意图约 1.0 s）**：`sleep 1.0` 从父进程启动开始计时，而先起方还承担 `bash -c` + `source setup.bash` + Python/rclpy 冷启动。两次重叠窗口均 >6.2 s 且后启动方完整落在先启动方窗口内（`coverage=true`），故不影响"互不可见"判读。

## 9. 封存与取回核验

- 首次封存：`python3 scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-unicast-discovery-probe-r1`，**退出码 0**，`artifacts=16 verify=True files=17 mismatches=0`；**未用 `--force`**。归档 stdout 写源根外 `/tmp/agc-w8-validation-r5-archive.log`。
- tar SHA `b5a52c97047b1b7488b9517ca174096cbf5144482a4640e702f14c82918749f8`，与 `.tar.sha256` 及 `.retrieval.json` 的 `archive_sha256` **三处一致**。
- 取回侧车：`verified=true`、`files_checked=17`、`mismatches=[]`。
- **独立复核（非仅读脚本输出）**：重算 manifest 所列 16 个 artifact 的 size/SHA → **0 不符**；`tar -tf` 17 条目与源根文件集**完全相等**（无缺无多）；解包到另一路径逐文件哈希比对 → **root==tar，17/17 一致**。
- 源根现仅 17 个文件（16 artifact + `config/evidence_manifest.json`），**无多余散落文件**；封存后**未再写源根**（本回报、`CURRENT.md`、规格勾选均在源根之外）。

## 10. 偏离与待裁定

- **D1（白名单内，但需 Leader 知悉基线口径）**：本轮按派工单"仅在本轮新增段勾选"更新了 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 round-5 条目。这两个文件**在派工基线 1204 条冻结路径之内**，因此**封存后基线复核会显示这 2 个文件 changed**。该写入由派工单白名单显式许可，**不是未知漂移**；除此之外无任何受保护文件变化。若 Leader 认为规格文件应完全冻结，请以本段为准回退该两项勾选。
- **D2（回执计数）**：见 §1，`files_count` 写 1203、实际 1204。**未改动**基线或回执（二者均在冻结集内）。
- **D3（驱动缺陷）**：见 §8。已保留原始日志 + 更正记录，未删除失败记录。
- **D4（判读形态）**：本轮结果不落在派工单任一预设行，已按末行处理并如实记录，**未强行映射根因**。

## 11. 未执行项

- **未执行第 3 次 T1**（预算 2 次用尽）。
- **未重做 A 同进程正/负控制**（派工单明确不重做）。
- **未重跑 E1/F1**（两次均 exit 0、无 `invalid_reasons`，不满足重跑条件；有效观测不得重跑）。
- **未修改任何配置**（`OFF`/静态 peer/`UDPv4` 仅进程级 `env -i` 数据集，进程结束后不残留）。
- 未读 `/dev/shm`、未清理共享资源或他人进程、未构建、未抓包、未启 GZ/PX4/GUI/headless/全链、未运行额外 graph observer/daemon、未用 root。
- 未修改 `spec.md`、`request.md`、`review.md`、契约、Runbook、`src/`、`scripts/`、`toolchain/`、`build/`、`install/`、旧证据或历史归档。
- 未改 `gate`（仍 `not_evaluable_as_specified`）、headless 授权、P1 v5 `inconclusive`、P2 v3 `falsified`/保留 c2、W7-c `deferred`、W8-E2 未预注册；**S2/S3/S4 未开放**。

## 12. 交接

- 本轮只交付**UDPv4 + 静态单播配置包的发现层对照证据**，不构成通信恢复、S2 通过、整链完成或任何工程验收。
- 需 Leader 裁定的三点：① `OFF + ROS_STATIC_PEERS` 在本版本 rmw 下互相抵消（§6），是否需要以 `LOCALHOST`/`SUBNET` + 静态 peer 重设下一轮口径；② D1 规格勾选是否保留；③ D2 回执计数口径。
- 状态已置 `待审查`，已用 `send_message` 通知 Leader 审查。按协议：**不等待、不轮询、不接下一单**。

### 追加自查更正（封存后，2026-10-28T11:35+08:00）

触发来源：Worker 在写完 §12 后复核 `config/run_identity.json` 的算术，发现封存源内一处**口径写错**。按 [事实错误的追加更正](../../../README.md#self-correction) 与 [封存后侧车](../../../README.md#post-archive-sidecar) 处理，**不改封存源、不改状态、不改验收结论**。

- **错项**：封存源 `config/run_identity.json` 的 `total_attempt_wall_s` 写作 `17.137`。
- **正确值**：**18.530 s** = E1 attempt span `9.502 s` + F1 attempt span `9.028 s`（本回报 §3 表格、§8 时钟段引用的已是正确值）。
- **成因**：写 `run_identity.json` 时把两次**进程级** `wall_s`（8.274+6.234+6.245+8.187）与**attempt 级** span 混算，仅覆盖了部分口径。
- **影响**：不影响任何 T1 合规判定——正确总值 18.530 s 仍远低于 90 s，单次 9.502/9.028 s 均低于 30 s；不改变任何 graph/matched/heard 观测值。
- **落盘位置**：封存源根之外 `experiments/_archive/w8-validation/20261028-unicast-discovery-probe-r1.post-archive-run-identity-walls.json`（不在 `list_runs()` 扫描范围，不触发重归档，未用 `--force`）。封存源内该字段保持原样，**以本条与侧车为准**。

同段另确认：封存后对源根的写入**为零**（源根 17 文件与封存时逐一 SHA 相同）；本轮唯一被封存后改动仍在源根之外的受保护文件是本回报 §10 D1 所述的两个规格文件。
