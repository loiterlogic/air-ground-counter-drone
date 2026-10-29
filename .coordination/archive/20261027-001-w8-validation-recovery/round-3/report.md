<a id="round3-report"></a>
# 第 3 轮执行回报

- 任务 ID：20261027-001-w8-validation-recovery；轮次：3。
- 执行者：DSH（dsh）；领取 2026-10-27T21:11:17+08:00；技术交接 2026-10-27T21:18+08:00。
- 配对时钟：领取 `epoch_ns=1793106677248411163`、`monotonic_ns=44304424396822`；结束见 §8。
- 结论：**A 步探针控制有效（R1），B 步出现单侧匹配不对称 + 零消费。** 本轮用满 `T1: 2 次`，未重跑。通信未恢复，S2/S3/S4 未开放，`gate` 不变。分析见 [analysis.md](../../../experiments/w8-validation/20261027-layered-matched-probe-r1/report/analysis.md#round3-analysis)。

## 1. 接单基线

- CURRENT 领取前：任务 `20261027-001-w8-validation-recovery`、轮次 `3`、状态 `待执行` → 协议允许接单。
- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，与派工单一致。
- 派工基线 `codex_dispatch_baseline.json` SHA256 `2f8a0d1ae74286356df99577d8b040cdee176de8ae93bbea110f9ba530556358`，与 `baseline_receipt.json` 相符（`files_count 1138`）。
- 全量逐文件重算：**1138/1138 相符，missing=0，changed=0**；`mutable_handoff_excluded` 三项未参与冻结。**无未知漂移。**
- 既有 dirty/untracked 全部保留；未 reset/clean/commit/切分支。

## 2. 实际改动（全部新增）

新根 `experiments/w8-validation/20261027-layered-matched-probe-r1/`：

| 文件 | 说明 |
|---|---|
| `scripts/probe_layered.py` | 单文件 rclpy 探针（`a`/`pub`/`sub` 三模式），无第三方依赖 |
| `config/run_identity.json` | 领取时钟、HEAD、T1 授权/使用、attempt 汇总 |
| `report/analysis.md` | 分层结果与判读 |
| `report/attempt-a1-result.json`、`attempt-b1-pub-result.json`、`attempt-b1-sub-result.json` | 三次进程的结果汇总 |
| `log/attempt-a1-events.jsonl`(166)、`attempt-b1-pub-events.jsonl`、`attempt-b1-sub-events.jsonl` | 追加式事件流 |
| `log/10-attempt-a1.log`、`log/11-attempt-b1.log` | 运行日志（含 PID/PGID/starttime/RC/残留） |
| `config/evidence_manifest.json` | 归档脚本生成 |

- 未修改：`src/`、既有 runner、协调脚本、旧证据、默认 pin、项目配置、历史归档、`.trae` 规格。

## 3. T1 attempt 与命令

| # | attempt | 进程 | 命令 | 退出码 | 墙钟 |
|---|---|---|---:|---|---:|
| 1 | A（正/负对照） | 1 | `setsid python3 probe_layered.py --mode a --out … --pos-seconds 3.0 --neg-seconds 2.0` | 0 | 7.602 s |
| 2 | B（pub+sub） | 2 | `--mode sub --run-seconds 6.0` 先起，1.0 s 后 `--mode pub --run-seconds 5.0` | pub 0 / sub 0 | 6.536 s |

- 环境两端一致：`ROS_DOMAIN_ID=39`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、无 `FASTDDS_BUILTIN_TRANSPORTS`、无 `RMW_IMPLEMENTATION`、无 `LD_PRELOAD`、无 profiles。
- 进程以 `setsid` 独立进程组启动，记录 PID/PGID/starttime；结束后复核 **3 个 PID 全部 gone，无残留**。
- 累计墙钟 **14.138 s**（上限 90 s）；单次均 <30 s。

## 4. 结果

### A 步（探针控制，1 进程）

| 阶段 | `sent_n` | `heard_n` | matched pub/sub | graph pub/sub | incompatible |
|---|---:|---:|---|---|---:|
| pos（同 topic 同 QoS） | 6 | **6** | 1 / 1 | 1 / 1 | — |
| neg1（pub BEST_EFFORT / sub RELIABLE） | 4 | 0 | **0 / 0** | 1 / 1 | **1** |
| neg2（不同 topic） | 4 | 0 | **0 / 0** | 1/0 与 0/1 | — |

→ **R1 + 两个负对照均有效**。仅证明探针在同 participant 内可区分三层；按派工单不当作跨进程系统阳性证明。

### B 步（跨进程，2 进程）

| 端 | `sent_n` | `heard_n` | matched | graph pub | graph sub |
|---|---:|---:|---:|---:|---:|
| pub | 99 | 0 | **0**（99 次采样恒 `(0,0,1)`，0 次 matched 事件） | 1 | **0** |
| sub | 0 | 0 | **1**（+1.170 s 时 `matched_event` total=1/current=1） | **1** | 1 |

→ **单向发现 + 单向匹配 + 零消费**。sub 能发现并匹配 pub；pub 全程看不到 sub；即使 sub 自认已匹配，`heard_n=0`。

- 该形态**不落在派工单判读表的任一单行**，已在 analysis §2 如实说明，未强行套用。
- 【推断，非结论】可能与"发布端未把订阅端纳入 matched reader 集合"一致，也可能是 1.017 s 启动时序差所致；**单次运行不足以定位**，按停止条件交 Codex 裁定。

## 5. 负向对照与回归

- 探针有效性自审 7/7 PASS：正对照 `heard>0` 且 matched>0；neg1 未匹配且 `incompatible` 事件=1；neg2 未匹配且 graph 各侧只见自己。证明观测器**不是恒返回 0**。
- `python3 -m py_compile` 通过；脚本静态检查无 `dev/shm` 读取、无 `killpg`/`os.kill`、无 `subprocess`、无 `rmtree`。
- B 结果独立重算复核一致。

## 6. 封存

- `python3 scripts/evidence_archive.py --campaign w8-validation --run-id 20261027-layered-matched-probe-r1`，退出码 0，`artifacts=15 verify=True files=16 mismatches=0`，**未用 `--force`**。
- tar SHA `ee1beb75a5a0805d10b731abc6c7700d0ab4e24bfd08d81079e313d9f4a05c3d`，与 `.tar.sha256` 及 `.retrieval.json` 的 `archive_sha256` 三处一致。
- 取回侧车 `verified=true`、`files_checked=16`、`mismatches=[]`。
- 源根与 tar 逐文件 SHA 比对：`root==tar: True`，16/16，无差异。
- 归档命令输出写在源根之外 `/tmp/agc-w8-r3-archive.log`。

## 7. 未执行项

- **未执行第 3 次 T1**：预算 2 次已用尽。
- **未重跑 A 或 B**：无进程异常（两 attempt 均 exit 0、无 invalid），不满足"T1 失败不自动重跑"与"有明确根因才重跑"。
- 未改 `ROS_AUTOMATIC_DISCOVERY_RANGE`、未加 `ROS_STATIC_PEERS`、未改任何配置。
- 未读 `/dev/shm` 内容、未清理共享资源、未构建、未抓包、未启动 GZ/PX4/GUI/headless/全链。
- `.trae/specs` round3 段未勾选，留 Codex 审查。

## 8. 预算与结束时钟

- 领取→交接 monotonic ≈ **7 min**（远低于 45 min）；T1 墙钟 14.138 s / 90 s。
- 结束配对时钟见下方追加段（封存后只追加，不写源根）。

## 9. 偏离与限制

- **D1**：B 步 pub/sub 启动相差 1.017 s（sub 先起）。这是为让消费者先就位而刻意安排的，但它引入"pub 启动时 sub 是否已被发现"的时序解释，**无法由单次运行排除**。已列为 L1。
- **L1**：无法区分"结构性单向匹配"与"启动时序导致的单向发现"。
- **L2**：matched 是**本进程视角**；sub matched=1 只表示 sub 认为自己配对了 pub，不证明 pub 侧对称成立。
- **L3**：B 步结果不落在判读表任一单行，属新的混合形态；已在 analysis 明示，未强行归类。
- **L4**：单次 B 运行，无重复，不能估计偶发性。

## 10. 交接

- 本轮只交付**分层通信证据**，不构成通信恢复、S2 通过或整链完成。
- B 步的单向匹配不对称需要 Codex 裁定下一步（是否增加重复、是否调整启动顺序、是否查发现层），DSH 不自行扩展诊断链。
- 状态置 `待审查`，已按 [自动叫醒](../../../README.md#auto-wake) 尝试叫醒 Codex，回执见下方追加段。

### 结束配对时钟（封存后追加）

- 结束：`epoch_ns=1793107103643068895`、`monotonic_ns=44694415700620`。
- 领取→结束 monotonic 差值 **389.913 s = 6.50 min**，在 45 min（2700 s）预算内。
- 记录存于源根之外（本节即为侧车位置，按 [封存后侧车](../../../README.md#post-archive-sidecar)）。
- 封存后最终基线复核：重算 1138 路径 → `verified=1138 / missing=0 / changed=0`。

### 叫醒回执

- 命令：`python3 .coordination/scripts/coordination_wake.py codex --note "…"`；**退出码 0**。
- 回执：`.coordination/wake/20261027T211845.codex.json`；日志：`.coordination/wake/20261027T211845.codex.log`
- 链 `753672afe16e` 第 **4/4** 跳（用满默认上限）；投递 `queue-live-thread` → 会话 `01a17d22-150a-77d0-a8e1-02948d833dc1`，`live_thread_verified=true`。
- **已叫醒 Codex，回执 `.coordination/wake/20261027T211845.codex.json`。**
- 按协议：叫醒后本会话结束本轮，不读 `review.md`、不轮询、不接下一单。
