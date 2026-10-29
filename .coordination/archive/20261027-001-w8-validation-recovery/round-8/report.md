<a id="round8-report"></a>
# 第 8 轮执行回报

- 任务 ID：20261027-001-w8-validation-recovery；轮次：8。
- 执行者：Worker（DSH 子会话 `e3e1d72b-6416-4f72-b66a-a246decef378`，沿用同一任务链）。
- 领取：2026-10-28T12:04:23+08:00（Asia/Shanghai），配对时钟 `monotonic_ns=13635892646817`、`wall_ns=1793160263093382546`、`pair_gap_ns=1100`。
- 结束：2026-10-28T12:06:18+08:00，`monotonic_ns=13749812510176`、`wall_ns=1793160378792109359`、`pair_gap_ns=942`；领取→结束 **113.920 s = 1.90 min**，在 45 min（2700 s）内。
- 领取前/后状态：`待执行` → `执行中` → `待审查`。
- 结论：**L1/M1 两次均有效完成，旧形态在 domain 0 下完整复现。** `ROS_DOMAIN_ID=0 + LOCALHOST`（不设 `FASTDDS_BUILTIN_TRANSPORTS`/`ROS_STATIC_PEERS`）下，两次都是「先启动方单向 matched=1、后启动方对先启动方 graph 恒 0、四端 heard=0」，方向随"谁先启动"翻转。落在判读**第 2 行**：**该形态不局限于非 0 domain；不得归因 domain 或 SHM。** 分析见 [analysis.md](../../../../experiments/w8-validation/20261028-domain0-localhost-probe-r1/report/analysis.md#round8-analysis)。

## 1. 接单基线

- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，与派工一致。
- 基线 `config/codex_dispatch_baseline.json` SHA256 `8454950d1685fdc461e38ddbd2883250acff0bebed215e28b75632d09ce2001f`，与 `baseline_receipt.json`（SHA256 `5773d0125fb59998e38b8586c240d7a19a730d72e696d0aada1b5c7f20e5e7d7`）所记一致。
- 逐文件重算：**实际 1276 条 = 回执 `files_count` 1276；1276/1276 相符，missing=0，changed=0**。
- `mutable_handoff_excluded` 3 项（`CURRENT.md`、本轮 `report.md`、本轮 `review.md`）确认未进入冻结集；`absent_from_parent_or_previous_tree` 为空，无历史删除文件重现。
- 第 7 轮授权勾选已入基线并核对通过（`tasks.md`/`checklist.md` 均在冻结集内且 SHA 相符）。
- **无未知漂移**；未 reset/clean/commit/push/切分支。领取前无 `probe_layered`/`rclpy`/`fastdds` 进程，未接管他人进程。
- 探针只读复用（size 16850，SHA256 `137eeed310abd803fbbe27a4339bd7dc126ee5bd3b3e89668b81b08d73baf389`），未复制、未修改。

## 2. 实际改动（全部在白名单内）

新根 `experiments/w8-validation/20261028-domain0-localhost-probe-r1/`（`config/` 预置两文件只读未改）：

| 文件 | 说明 |
|---|---|
| `config/run_identity.json` | 领取时钟、基线、配置、T1 授权/使用、两次 attempt 汇总、时序语义声明、ADR-0077 边界 |
| `config/run_attempt_driver.sh` | 实际使用的驱动（`SCRIPT_MARK_*` 术语已更正） |
| `config/evidence_manifest.json` | 归档脚本生成（首次封存） |
| `log/{l1,m1}-{pub,sub}-events.jsonl` | 四端完整原始事件流 |
| `log/10-attempt-l1.log`、`log/11-attempt-m1.log` | 驱动原始日志（脚本标记、RC、残留、`/proc` 环境快照） |
| `report/{l1,m1}-{pub,sub}-result.json` | 四端进程结果 |
| `report/analysis.md` | 结果、判读、ADR-0077 边界、限制 |

另按协议更新：本轮 `report.md`（本文件）、`.coordination/CURRENT.md`、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 **round8 执行事实勾选**（见 §9 D1）。

## 3. 配置与时序口径

**固定条件（两次相同，仅 ROS_HOME/ROS_LOG_DIR 各自独占）**：`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`；**未设** `FASTDDS_BUILTIN_TRANSPORTS`/`ROS_STATIC_PEERS`/`RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles；topic `/agc_probe_domain0/chatter`、`std_msgs/String`、RELIABLE depth10。`probe_start.env` 与 `/proc` 快照互证（`FASTDDS_BUILTIN_TRANSPORTS` 快照为 null 且 `/proc` 无该键）。

**时序口径更正（按派工要求）**：源码 `probe_layered.py` 第 **339–345** 行写 `probe_start`，而 `rclpy.init()` 在第 **350** 行——**写入位于创建 participant 之前**。因此本回报一律称其为「**脚本启动标记**」，**不称** participant/endpoint 就绪。等待它 ~1.0 s 仅为**复现第 3–7 轮旧时序**。

| attempt | 顺序 | 脚本启动标记依据 | 标记轮询 | 标记→启动后起方 | 参与者启动间隔 | 重叠 | 覆盖 |
|---|---|---|---:|---:|---:|---:|---|
| L1 | pub-first | pub `events.jsonl` 的 `probe_start` | 0.660 s | 1.000 s | 1.643 s | 6.262 s | ✅ |
| M1 | sub-first | sub `events.jsonl` 的 `probe_start` | 0.610 s | 1.000 s | 1.692 s | 6.208 s | ✅ |

- 驱动字段已改名 `SCRIPT_MARK_MONO_NS`/`SCRIPT_MARK_BASIS`/`MARK_TO_LAUNCH_S`，并显式写入 `SCRIPT_MARK_IS_NOT_PARTICIPANT_READY=true`，避免沿用"就绪"表述。

## 4. 两次结果（运行期峰值）

| attempt | 顺序 | pub sent/heard | pub matched | pub graph(p/s) | sub matched | sub graph(p/s) | matched 事件(pub/sub) |
|---|---|---|---:|---|---:|---|---|
| **L1** | pub-first | 158 / **0** | **1** | 1/1 | **0** | 0/1 | 2 / 0 |
| **M1** | sub-first | 118 / **0** | **0** | 1/0 | **1** | 1/1 | 0 / 2 |

- 四端 `exit_code` 全 0，`invalid_reasons` 全空，采样 118–159/端，事件流完整，零 `incompatible_qos_event`。
- **每次都是先启动方 matched=1、后启动方 matched=0**，方向随"谁先启动"翻转。
- 先启动方 matched 事件：`total=1,current=1` 于 +1.850 s（L1 pub）/ +1.892 s（M1 sub）；`current=0` 回落于 +7.901 s / +7.895 s（对端退出）。
- **四端 `heard_n` 全 0**；**后启动方对先启动方 graph 恒 0**。

> **口径**：上表为**运行期峰值**，非 `result.json.final`。先启动方 `final.matched_*=0` 是对端先退出后的正常回落，**不得**误读为"从未匹配"。

## 5. 判读（对照派工单第 23–28 行）

落在**第 2 行**——"仍复现先启动方单向匹配、后启动方不可见、`heard=0`：该形态不局限于非 0 domain；不得归因 domain 或 SHM"。

- ✗ 非"两次均双向且 `heard>0`"：**domain 0 下探针通信未成立**。
- ✗ 非"双向 graph/matched 但 heard=0"：始终单向。
- ✗ 非"其他或无效形态"：旧形态完整复现。

可支持的克制结论：
1. **把 `ROS_DOMAIN_ID` 由 39 改为项目默认 0，未改变该形态。**
2. 该形态**不局限于非 0 domain**；**不能**归因 domain。
3. 结合第 7 轮（SUBNET 非 LOCALHOST 分支亦复现），该形态在 **domain ∈ {0, 39} × discovery ∈ {LOCALHOST, SUBNET}** 四种组合下均出现。
4. **仍不能**归因 SHM/UDP/QoS/权限/executor；**未**定位"为何先启动方能匹配、后启动方不可见"。

## 6. 与 ADR-0077 的关系（严格区分，不外推）

- 【既有事实】ADR-0077 背景约束 4：本机 **非 0 domain 的 lifecycle 服务数据面不通**（实测 77/81 `ChangeState` 超时），**而话题仍正常**；故整链统一用 domain 0。该 ADR Status 为 `deferred`（草案/未实施）。
- 【本轮实测】domain 0 下**本探针的话题层**仍出现先启动方单向匹配 + 零消费。
- 【边界】**两者不矛盾**：ADR-0077 描述的是**非 0 域的 service 异常、topic 正常**；本轮描述的是 **domain 0 下 topic 探针仍单向**。本探针**不涉及 service 调用**，故本轮**既未复现也未否证** ADR-0077 的服务异常。
- **不把**服务异常外推为话题根因，也**不把**本轮结果外推为"ADR-0077 记录错误"。

## 7. 限制

- **L1**：`heard=0` 四端全成立；匹配 ≠ 送达，本轮未解释该断点。
- **L2**：matched/graph 为本进程视角；"先启动方匹配"不代表对端对称。
- **L3（最实质缺口）**：**无 post-init/post-endpoint 标记**，无法区分"participant 未就绪"与"已就绪但发现失效"。需另写带显式标记的探针才能闭合；本轮不得修改探针。
- **L4**：未回读 transport / discovery 实配。
- **L5**：L1/M1 各仅 1 次，无重复；未扫启动间隔与其他 domain。
- **L6**：未做 A 同进程正/负控制，探针有效性依赖第 3 轮已验收结论。
- **L7**：本轮**只有 domain 0 一个取值**，**无同轮 domain 39 对照**（派工未授权）。严格说本轮证明"domain 0 下仍复现"，而非"domain 0 与 39 严格等价"。
- **L8**：本探针不涉 service，对 ADR-0077 服务异常既无支持也无反驳。

## 8. 时钟、回收与封存

- **时钟**：四端 `wall_minus_mono` 漂移均 <1 µs，`pair_gap` 最大 17.4 µs。**无墙钟跳变**。
- **真实 RC**：`set -m` 下两次 `WAIT_RC_PUB/SUB` 均 0，与 `result.json`/`probe_end` 的 `exit_code=0` **交叉一致**，`PIDS_MATCH=true`。
- **残留**：两次 `RESIDUE=0`、`STRAY=[]`；结束后扫描无 `probe_layered`/`rclpy`。未发 SIGTERM，探针自行结束。
- **算术复核（封存前完成）**：L1 span 9.040 s、M1 span 8.970 s，**单次均 <30 s**。合计两口径：**驱动 attempt span 之和 = 18.010 s**；**各次两端进程 wall 最大值之和 = 16.420 s**。两口径**均 <90 s**，差异来源为脚本标记轮询与 1.0 s 间隔，未混用。
- **封存**：`python3 scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-domain0-localhost-probe-r1`，**RC 0**，`artifacts=15 verify=True files=16 mismatches=0`，**未用 `--force`**；stdout 写源根外 `/tmp/agc-w8-validation-r8-archive.log`。
- tar SHA `4035da92369a0f998a0aafda6a4e558e0c44393b7edd7418316479217e0af63d`，与 `.tar.sha256` 及 `.retrieval.json.archive_sha256` **三处一致**；tar 实际根 `20261028-domain0-localhost-probe-r1/`。
- **独立复核**：manifest 15 项 size/SHA **0 不符**；`tar -tf` 16 条目与源根文件集**完全相等**；解包至另一路径逐文件哈希 → **root==tar，16/16 一致**；retrieval `verified=true`、`files_checked=16`、`mismatches=[]`。

## 9. 偏离与待裁定

- **D1（白名单内的冻结文件变化）**：按派工"只在 round8 段勾选"更新了 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md`。两文件在本轮冻结集内（前几轮已裁定"勾选保留、下一轮基线显式接纳"），封存后基线复核会显示这 2 个文件 changed，属**已授权预期变化**；除此之外无任何受保护文件变化。
- **D2（时序口径）**：已按派工全面改称"脚本启动标记"，并在驱动与 run identity 中固化为机器可读字段；未在任何处声称 participant 就绪。
- **D3（算术口径）**：18.010 / 16.420 s 并列，未混用。

## 10. 未执行项

- **未执行第 3 次 T1**（预算 2 次用尽）。
- **未重跑 L1/M1**（均 exit 0、无 `invalid_reasons`，不满足重跑条件）。
- **未做同轮 domain 39 对照**（派工未授权）。
- **未另写带 post-init/post-endpoint 标记的探针**（本轮禁改探针；已在 L3 登记为后续需求）。
- 未回读 transport 实配、未做 A 同进程控制。
- 未读 `/dev/shm`、未清理共享资源或他人进程、未构建、未抓包、未启 GZ/PX4/GUI/headless/全链、未用 root、未发 SIGTERM。
- 未改 `spec.md`、`request.md`、`review.md`、契约、Runbook、`src/`、`scripts/`、`toolchain/`、`build/`、`install/`、旧证据或历史归档。
- 未改 `gate`（仍 `not_evaluable_as_specified`）、headless 授权、P1 v5 `inconclusive`、P2 v3 `falsified`/保留 c2、W7-c `deferred`、W8-E2 未预注册；**S2/S3/S4 未开放**。

## 11. 交接

- 本轮只交付 **domain 0 下的探针级顺序对照证据**，不构成通信恢复、S2 通过、整链完成或工程验收。
- 需 Leader 裁定的三点：① domain 已成为**可排除**的配置因子（至少对本探针形态）；是否还有配置因子值得继续换，或应转向探针可观测性（L3 的 post-init/post-endpoint 标记）；② 若要主张"domain 0 与 39 严格等价"，需同轮对照，属新派工；③ ADR-0077 的服务异常与本探针话题形态的关系，本轮未闭合。
- 状态已置 `待审查`，已用 `send_message` 通知 Leader。按协议：**不等待、不轮询、不接下一单**。
