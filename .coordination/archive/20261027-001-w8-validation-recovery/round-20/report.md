<a id="round20-report"></a>
# 第20轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次20。

执行者：Worker 子会话 `47a2651c-e420-4218-b4c6-454837cd33fd`（复用，Leader 于2026-10-28派工）。

> 页头由Leader预置；正文由Worker按派工单追加。领取先写配对时钟并核对基线（43564项/SHA `a0c0de79…`），再改CURRENT为执行中。

## 0. 领取配对时钟（本轮第一个动作）

**本轮第一次写入**，当时 CURRENT 仍为 `待执行`。原始件：`evidence/claim-clock.txt`。

| 字段 | 值 |
|---|---|
| `claim_mono_mid_ns` | **8357612295530** |
| `claim_wall_iso` | `2026-10-28T19:38:19.381580+08:00` |
| `pair_gap_ns` | 30397 |
| `/proc/uptime` | 8357.61 s |

**同 boot 延续**：第19轮领取 7261.15 s、本轮 8357.61 s，`btime` 未变（1793179141，与 r19 的 1793179127 有 +14 s 墙钟校正偏差，**mono 不受影响**，如实记录不归因）。

## 1. 接单基线与领取核对

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `20`、`待执行` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 受保护集（刷新后） | **43564/43564**，missing 0、不符 0 | **漂移 0** |
| `git status --porcelain` | 36 项，与 baseline 逐行相同 | 一致 |

## 2. T0 离线修复与"修复前失败、修复后通过"证明

`evidence/offline-tests-r20.json`：**12/12 全部符合预测**，`all_passed=true`。

| 守卫 | round-19 实现 | round-20 实现 |
|---|---|---|
| G1 窗口锚定 probe 自身事件 + ≥1 s 余量 | **FAIL（无锚定概念）** | **PASS** |
| G1b 模拟 400 ms `source` 启动延迟 | **FAIL（无锚定窗口）** | **PASS（锚定且完整完成）** |
| G2 SIGINT 后仍写 `result.json` | **FAIL（修复前重建版）** | **PASS** |
| G3 partial 与 missing 区分 | — | **PASS** |
| G4 运行中 maps（`comm=python3`，绝不用 bash） | — | **PASS** |
| G5 默认无传输变量 | — | **PASS** |
| G6 门控拦截 / fake 在真实例被拒 | — | **PASS（2 项）** |
| G7 真实 RC 与 SIGINT 保留 | — | **PASS** |

`evidence/api-contract-check.json`：**53/53**。

### 2.1 关于 G2 基准的诚实说明

**封存的 r19 `probe_r19.py` 已含 `BaseException` 修复**（它在 A 跑完后、封存前被补上）。因此要证明"修复前失败"，必须有真正的修复前版本：`scripts/prefix_reference/probe_prefix_r19.py` 就是把封存版**仅**将该 handler 回退为 `except Exception` 的重建，文件头已注明它是**测试夹具、不是 r19 产物**。

### 2.2 离线套件当场抓出的 5 个自身缺陷（均在真实 T1 之前修掉）

1. `second['pid']` 在赋值前被引用；
2. **side 2 被 `reap()` 两次**，第二次覆盖了 SIGINT 记录（G7 最初报 `sigint: null` 的真因）；
3. `partial_summary()` 因事件 `at` 形状不一（`mono_ns` vs `mono_before_ns`）抛 `KeyError`；
4. G1b/G2 的断言把"round-19 正确失败"计成套件失败——已改为断言**预测结果**；
5. fake 收尾太快、根本触发不到截断——新增 `steady` 行为，按 `--run-seconds` 占满窗口。

## 3. 真实 T1 #1：A 有效

| 项 | 值 |
|---|---|
| 条件 | 同 boot / domain0 / LOCALHOST / **默认传输**（`FASTDDS_BUILTIN_TRANSPORTS` 在构造环境与真实 `/proc/<pid>/environ` **均不存在**） |
| 顺序 | pub 先建 endpoint（`gate.role=pub`，`gate_event_seq=4`），sub 后起 |
| 窗口 | pub 8864.924→8876.933 s（**12.01 s**）；sub 8865.457→8873.468 s（**8.01 s**，**完整落在 pub 窗口内**） |
| 锚定 | 两侧 `used_deadline = anchor + budget + 1.5 s`，`clamped_by_hard_limit=false` |
| 进程证据 | 两侧 `runtime_maps=captured`、`comm=python3`（第18轮缺陷保持修复） |
| 真实 RC | first **0**、second **0**；SIGINT 回收 |
| span / participant | 12.680 s / 2 |
| 分类 | `first_class=valid`、`second_class=valid`、`partial_sides=null` |
| T1 用量 | **1/2**，未用重跑 |

### 3.1 分层观测（`evidence/A-recount-raw.json`，**仅凭原始 events 重算**）

| 层 | pub 侧 | sub 侧 |
|---|---|---|
| graph 对端计数 | sub=**1** | pub=**0** |
| 对端 endpoint info | `subscriptions_info`=**1** | `publishers_info`=**0** |
| DDS matched | **1**（`matched_event` seq 9，seq 49 回落 0） | **0**（全程无 `matched_event`） |
| 消息 | **发布 12 条**（其中 **8 条**落在 sub 窗口内） | `heard`=**0**（32 个样本全 0） |

事件流完整性：pub 68 条、sub 39 条，两侧 `seq` 均严格 1..N、PID 各自唯一。

## 4. 判读

**落在请求 §5 第 3 条：完整窗口下 pub 侧看到 sub 而 sub 侧 graph/matched=0 —— 正式复现历史 rclpy↔rclpy 单向发现形态。**

- 第19轮该形态是**非权威**的（窗口被截断）。本轮窗口**完整且完全被 pub 窗口包含**，32 个样本跨满 8.01 s，期间 8 条消息发出，sub 侧仍全 0。**"后来者启动太早"与"窗口被截断"两种解释均被排除。**
- 方向不对称：**pub→sub 通告成功，sub→pub 通告未发生**（本样本）。

### 4.1 明确未成立

- **不是根因**。层面是"sub→pub 方向的发现通告"，**为何**该方向失败（SPDP/SEDP、participant 顺序、WSL mirrored `loopback0`、SHM/UDP、rmw 内部）完全未触及。
- **不是** UDPv4/SHM 结论：本轮**未测**（Leader 明确暂不开放）。SHM 结论仍为零。
- **不是** stock↔rclpy 混合对结论：本例两侧都是 rclpy。
- **不是**工程恢复、不是 domain 结论、不是项目节点结果。
- **单样本**：仅一个有效 case。它与第3–14轮及第19轮非权威 partial 一致，但单样本不能给出发生率，也不能排除时变性。

## 5. 预算

| 项 | 值 | 上限 | 判定 |
|---|---:|---:|---|
| T1 次数 | **1**（A，valid） | 2 | 合规 |
| A span | 12.680 s | 30 s | 合规 |
| 累计 T1 | 12.680 s | 60 s | 合规 |
| participant | 2 | 2 | 合规 |
| 整轮 mono | **615.138 s = 10.252 min** | 45 min | 合规 |

无重跑（A 一次即 valid，修复重跑额度未使用）。

## 6. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_mid_ns` | 8972750490058 |
| `end_wall_iso` | `2026-10-28T19:48:43.341904+08:00` |
| `pair_gap_ns` | 19963 |
| 整轮 mono | **615.138 s = 10.252 min** |

## 7. 首次封存与取回

```text
python3 -B scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-rclpy-cross-process-recheck-r1
```

stdout 原文（`/tmp/agc-w8-validation-r20-archive/archive-stdout.txt`，rc=0）：

```text
ok     w8-validation/20261028-rclpy-cross-process-recheck-r1 artifacts=39 verify=True files=40 mismatches=0

archived=1 skipped=0 error=0 retrieval_failed=0
```

| 核对项 | 实测 | 结果 |
|---|---|---|
| manifest artifacts | **39**，逐项 size/sha 重算 | 0 mismatch |
| tar 成员 / 真实根 | **40** / 唯一 `20261028-rclpy-cross-process-recheck-r1/` | 正确 |
| tar 独立重算 sha256 | `4040841e071e26fbfa9fc1ad75de944808bcd4cbe1d3baae5796ca87f47c4d67` | 与 `.tar.sha256` 一致 |
| 逐文件相等 | `root_only=[]`、`tar_only=[]`、differing 0 | 40/40 |
| retrieval | `verified=true`、`files_checked=40`、`mismatches=[]` | 通过 |
| 独立解包取回 | 40 文件逐个哈希 | 0 mismatch，临时目录已删 |
| 归档权限 / 封存后源根 | tar `0444` / 源根 0 写入 | 通过 |

封存前基线：**43564/43564，drift 0**。

## 8. 实际改动（覆盖全部写操作）

**新根内新增**：`scripts/` 9 个（含 `round19_reference/` 与 `prefix_reference/` 两个测试基准）、`evidence/` 7 个、`report/analysis.md`、`cases/A/` 全套原件，封存时 `config/evidence_manifest.json`；共 **39** 个产物。

**新根外**：本轮 `report.md`、`CURRENT.md`（待执行→执行中→待审查）、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 round20 勾选（各 4 项 / 5 项）、`experiments/_archive/w8-validation/20261028-rclpy-cross-process-recheck-r1.tar{,.sha256,.retrieval.json}`、`/tmp/agc-w8-validation-r20-*`。

**过程性清理**：删除了我自己创建的 `/tmp/agc-w8-g7*`、`/tmp/agc-w8-validation-r20-g7dbg`、`-r19src` 及离线 shim 目录（均为本单独占前缀、本人创建，非共享资源）。

**未改**：`src/`、项目 `scripts/`、`toolchain/`、`build/install`、spec/Runbook/request/历史 review、第19轮脚本与源根、历史归档；未 reset/clean/commit/push/切分支；全程 `python3 -B`，无 `__pycache__`。

## 9. 待裁定

1. **单向形态应如何下一轮处置**：本样本已排除"窗口截断/启动太早"，但仍是**单样本**。是按请求 §5 进入"UDPv4 或发现层分支"之一，还是先做同 boot 重复以获得方向稳定性，属 Leader 裁定。
2. **`prefix_reference/` 夹具是否保留**：它使 G2 的 before/after 可复算，但属"重建的修复前代码"。若 Leader 希望归档中不保留重建件，我可移除并在分析中只留文字说明。
3. **单侧成立是否足以支撑"发现层"分支**：pub 能看到 sub，说明 sub 的参与者已被 pub 发现；而 sub 看不到 pub。这一不对称对 SPDP/SEDP 的进一步分层（谁的通告没发出 vs 谁没接受）需要 endpoint-info 之外的手段，可能触及第15轮/B 候选。
