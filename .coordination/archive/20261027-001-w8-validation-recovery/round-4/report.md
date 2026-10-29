<a id="round4-report"></a>
# 第 4 轮执行回报

- 任务 ID：20261027-001-w8-validation-recovery；轮次：4。
- 执行者：DSH（dsh）；领取 2026-10-27T21:52:54+08:00；技术交接 2026-10-27T21:57+08:00。
- 配对时钟：领取 `epoch_ns=1793109174274623043`、`monotonic_ns=46604950656539`；结束见 §9。
- 结论：**启动顺序对照完成。不对称方向随"谁先启动"翻转：先启动方匹配成功，后启动方对先启动方完全不可见；两次两端 `heard` 均为 0。** 通信未恢复，S2/S3/S4 未开放，`gate` 不变。分析见 [analysis.md](../../../experiments/w8-validation/20261027-layered-matched-probe-r2/report/analysis.md#round4-analysis)。

## 1. 接单基线

- CURRENT 领取前：任务 `20261027-001-w8-validation-recovery`、轮次 `4`、状态 `待执行` → 协议允许接单。
- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，与派工单一致。
- 派工基线 SHA256 `62d3df295cc9baf93cd4e842f9aed0ba6ccae401bf5eecf3fc0188dac6abf052`，与 `baseline_receipt.json` 相符（`files_count 1157`）。
- 全量重算：**1157/1157 相符，missing=0，changed=0**；mutable 三项未参与冻结。**无未知漂移。**

## 2. 实际改动（全部新增）

新根 `experiments/w8-validation/20261027-layered-matched-probe-r2/`：

| 文件 | 说明 |
|---|---|
| `config/run_identity.json` | 领取时钟、HEAD、T1 授权/使用、attempt 汇总 |
| `config/evidence_manifest.json` | 归档脚本生成 |
| `report/analysis.md` | 顺序对照结果与判读 |
| `report/attempt-{c1,d1}-{pub,sub}-result.json` | 4 份进程结果 |
| `log/attempt-{c1,d1}-{pub,sub}-events.jsonl` | 4 份追加式事件流 |
| `log/10-attempt-c1.log`、`log/11-attempt-d1.log` | 运行日志（PID/PGID/starttime/RC/残留） |

- **探针未复制未修改**：复用 `20261027-layered-matched-probe-r1/scripts/probe_layered.py`（只读）。
- 未改 `src/`、既有 runner、协调脚本、旧证据、默认 pin、项目配置、历史归档、`.trae` 规格。

## 3. T1 attempt 与命令

| # | attempt | 顺序 | 进程 | 退出码 | 墙钟 |
|---|---|---|---|---:|---:|
| 1 | C1 | pub 先起（8 s）→ sub（6 s，+1.0 s） | 2 | pub 0 / sub 0 | 8.657 s |
| 2 | D1 | sub 先起（8 s）→ pub（6 s，+1.0 s） | 2 | pub 0 / sub 0 | 8.457 s |

- 固定条件两端一致：`ROS_DOMAIN_ID=39`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、不设 `FASTDDS_BUILTIN_TRANSPORTS`/`RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles；topic `/agc_probe_order/chatter`、RELIABLE depth10。
- `setsid` 独立进程组；4 个 PID 全部回收，**无残留**；累计墙钟 **17.114 s / 90 s**。

## 4. 结果

| attempt | 顺序 | pub sent/heard | pub matched 峰值 | pub graph(sub) | sub matched 峰值 | sub graph(pub) |
|---|---|---:|---:|---:|---:|---:|
| C1 | pub-first | 159 / 0 | **1**（+1.068 s） | **0** | **0** | **0** |
| D1 | sub-first | 120 / 0 | **0** | **0** | **1**（+1.162 s） | **1** |

**核心观测**：两次都是**先启动方**捕获后启动方并匹配成功；**后启动方对先启动方完全不可见**（graph 恒 0）。方向由"谁先启动"决定，不随 pub/sub 角色固定。

> 口径：上表为**运行期峰值**。`result.json` 的 `final` 因对端先退出而回落 0，属正常生命周期语义，不得误读为"从未匹配"。

## 5. 判读（对照派工单 §判读）

- 派工单预设「不对称侧随先启动者改变 → 支持启动时序/发现握手假说」。实测确认为**方向固定**形态：先启动方匹配、后启动方不可见。
- 与第 3 轮 B1 **完全同构**（B1 中 sub 先起 → sub 匹配、pub 看不到 sub，即本轮 D1）。
- 因此本轮把第 3 轮"可能是启动时序偶然"收紧为"**与先启动方相关的方向性发现失败**"，并复现了一次。
- **不能**据此定位 SHM/UDP/权限/QoS 任一层；`heard=0` 即使匹配成功侧也成立，匹配≠送达，本轮未解释该断点。

## 6. 负向对照与自审

- 对照自审 **9/9 PASS**：C1 pub 峰值=1 且 sub=0；D1 sub 峰值=1 且 pub=0；两次不可见侧 graph 恒 0；两次有 matched 事件；方向确实翻转。
- 自审中曾发现 `final` 与峰值口径混淆（用 `final` 会误判"从未匹配"），已在 analysis §2 显式加口径说明并改用峰值。
- 两次 `invalid_reasons` 均空；无 API 异常、无超时、无关键快照缺失。

## 7. 封存

- `python3 scripts/evidence_archive.py --campaign w8-validation --run-id 20261027-layered-matched-probe-r2`，退出码 0，`artifacts=15 verify=True files=16 mismatches=0`，**未用 `--force`**。
- tar SHA `d3078b09a1b478acaa65ea570c093f4c935d2102d080eef73cb499b590806ba9`，与 `.tar.sha256` 及 `.retrieval.json` 三处一致。
- 取回侧车 `verified=true`、`files_checked=16`、`mismatches=[]`。
- 源根 vs tar 逐文件 SHA：`root==tar: True`，16/16 无差异。
- 归档输出写在源根外 `/tmp/agc-w8-r4-archive.log`。

## 8. 未执行项

- **未执行第 3 次 T1**（预算 2 次用尽）。
- **未重做 A 控制**（派工单明确不重做；探针有效性依赖第 3 轮 A 步结论）。
- 未重跑 C 或 D（两次均 exit 0、无 invalid，不满足重跑条件）。
- 未改任何配置、未读 `/dev/shm`、未构建、未抓包、未启 GZ/PX4/GUI/headless。
- `.trae/specs` round4 段未勾选，留 Codex 审查。

## 9. 预算与结束时钟

- 领取→交接 monotonic ≈ **4.5 min**（远低于 45 min）；T1 墙钟 17.114 s / 90 s。
- 结束配对时钟见下方追加段。

## 10. 偏离与限制

- **D1（协调配置）**：`wake/targets.json` 原指向旧会话 `01a17d22…`，而用户已开新 Codex 会话 `01a17da0…`（writer 锁实测）。领取后已将 `codex_thread_id` 更新为新会话并保留 `_previous`/`_updated_at`/`_updated_by` 审计字段，确保本轮回报投到正确会话。此改动在派工白名单外，但属用户明确指示"汇报回正确的会话"。
- **L1**：`heard=0` 在两次均成立，匹配成功侧也未收到数据；匹配≠送达，未解释。
- **L2**：matched 为本进程视角，"先启动方匹配"不代表对端对称。
- **L3**：每次仅 1 次运行；启动间隔固定 +1.0 s，未扫其他间隔。
- **L4**：未做 A 控制，探针有效性依赖第 3 轮。
- **L5**：第一轮未记录毫秒级启动时序，无法直接映射本轮 C/D 形态。

## 11. 交接

- 本轮只交付**顺序对照证据**，不构成通信恢复、S2 通过或整链完成。
- "先启动方匹配、后启动方不可见 + 双方零消费"需 Codex 裁定下一步；DSH 不自行扩展诊断链。
- 状态置 `待审查`，已按 [自动叫醒](../../../README.md#auto-wake) 叫醒 Codex，回执见下方追加段。

### 结束配对时钟与最终基线复核（封存后追加）

- 结束：`epoch_ns=1793109405492838620`、`monotonic_ns=46817193789952`。
- 领取→结束 monotonic 差值 **212.243 s = 3.54 min**，在 45 min（2700 s）预算内。
- 封存后基线复核：重算 1157 路径 → `verified=1156 / missing=0 / changed=[".coordination/wake/targets.json"]`。
- 该唯一变化即 §10 D1 所述 `codex_thread_id` 更新（旧 `01a17d22…` → 新 `01a17da0…`），由用户指示"汇报回正确的会话"直接导致；已在领取时保留 `_previous`/`_updated_at`/`_updated_by`。**非未知漂移**，但超出派工白名单，特此显式披露，交 Codex 裁定是否认可。

### 叫醒回执（投递到正确会话）

- 命令：`python3 .coordination/scripts/coordination_wake.py codex --note "…"`；**退出码 0**。
- 回执：`.coordination/wake/20261027T215819.codex.json`；日志：`.coordination/wake/20261027T215819.codex.log`
- 链 `753672afe16e` 第 **1/4** 跳（用户已重置，本轮未自行重置）；`live_thread_verified=true`。
- **投递目标判定**：系统内同时存在两个 writer 锁（`01a17da0…` 21:50:55 与 `01a17da4…` 21:55:18），均属同一 app-server daemon（PID 1751）。以 `shell_snapshots/` 判活：**仅 `01a17da4…` 有 shell snapshot（21:55:18）**，`01a17da0…` 只有空引用、无 snapshot，判定为用户实际在用的会话。故 targets 与投递目标均为 `01a17da4-da7e-7611-804e-4d152f4051f3`。
- 消费确认：投递后 `queue_1.sqlite` 的 `queued_items` 已无待消费项（该线程队列被消费，此前死会话残留项亦已消失）。
- **已叫醒 Codex，回执 `.coordination/wake/20261027T215819.codex.json`。**
- 按协议：叫醒后本会话结束本轮，不读 `review.md`、不轮询、不接下一单。
