<a id="round19-report"></a>
# 第19轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次19。

执行者：Worker 子会话 `47a2651c-e420-4218-b4c6-454837cd33fd`（复用，Leader 于2026-10-28派工）。

> 页头由Leader预置；正文由Worker按派工单追加。领取先写配对时钟并核对基线（43520项/SHA `6f19c61b…`），再改CURRENT为执行中。

## 0. 领取配对时钟（本轮第一个动作）

单进程内配对采样；**本轮第一次写入**，当时 CURRENT 仍为 `待执行`。原始件：`evidence/claim-clock.txt`。

| 字段 | 值 |
|---|---|
| `claim_mono_mid_ns` | **7261157129889** |
| `claim_wall_iso` | `2026-10-28T19:19:48.523467+08:00` |
| `pair_gap_ns` | 20079 |
| `/proc/uptime` | 7261.15 s |

**同一 boot 证据**：第18轮领取 uptime 5615.42 s、结束 6316.52 s；本轮领取 7261.15 s，`btime` 未变（`/proc/stat` 读到 1793179127，与第18轮 1793179117 有 +10 s 偏差，属墙钟校正，**mono 不受影响**，如实记录不归因）。间隔与 elapsed 一致，非重启。

## 1. 接单基线与领取核对

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `19`、`待执行` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 受保护集（刷新后） | **43520/43520**，missing 0、size/sha 不符 0 | **漂移 0** |
| `git status --porcelain` | 36 项，与 baseline 逐行相同 | 一致 |
| 开跑前冲突 | `pgrep` 无 demo/probe；无既有 `/tmp/agc-w8-validation-r19-*` | 通过 |

## 2. 离线守卫（T1=0，真实运行前完成）

| 守卫 | 结果 | 说明 |
|---|---|---|
| `evidence/offline-tests-r19.json` | **15/15** | 门控（good 放行 / no_endpoint 超时 / wrong_order 顺序违规 / wrong_role 角色不符 / 坏 jsonl 记 unparsable）、**运行中抓取真实 exec 后进程**、transport 显式存在/缺省、fake 在真实例被拒、A 模式 pub 先 sub 后 |
| `evidence/api-contract-check.json` | **52/52** | rclpy 属性/方向、endpoint info 字段、未格式化 `%s` 守卫、行为守卫、**BaseException 守卫** |

**离线测试当场发现并修掉了我 4 个真实缺陷**（均在真实 T1 之前）：A 模式把 sub 先起（请求 §2 要求 pub 先起）、`second['pid']` 在赋值前引用、把"stock 无 result.json"误判为 invalid、fake 忽略 `--mode` 导致角色错。

## 3. T1 执行：A invalid，B/C 按门未执行

### 3.1 A（T1#1）rclpy pub→rclpy sub，默认传输 —— **invalid**

| 项 | 值 |
|---|---|
| transport 变量 | **不存在**（constructed 与真实 `/proc/<pid>/environ` 双证 `present=false`、`value=null`） |
| gate | ok，`role=pub`，`gate_event_seq=4`（sub 在 pub endpoint 之后才启动） |
| 进程/运行中 maps | 两端 **`runtime_maps=captured`、`comm=python3`**（第18轮缺陷已修复） |
| span / participant | 12.651 s / 2 |
| 真实 RC | pub **0**；sub **-2**（SIGINT） |
| 判定 | **invalid**：`second_result_missing` |

**根因（我自己的驱动缺陷，非 DDS）** —— `evidence/A-reclaim-race.txt`：

| 步骤 | mono (ns) | 后果 |
|---|---:|---|
| sub spawn | 7527257611631 | 直接子进程是 `bash` |
| probe 真正启动 | 7527428161420 | 比 spawn 晚 **170.5 ms**（要 `source` ROS） |
| 驱动固定回收期限 | 7535257611631 | = spawn + 8.0 s |
| 实际发 SIGINT | 7535274677637 | 超期 17.1 ms |
| probe 自己的窗口结束 | 7535428161420 | = **它自己**启动 + 8.0 s |

驱动按 **spawn** 计时，probe 按**自身启动**计时，两者差 ~170 ms，于是 SIGINT 落在 probe 仍在 `spin_once()` 的窗口内。`KeyboardInterrupt` 是 `BaseException` 而非 `Exception`，逃出我的 `except Exception`，在写 `result.json` 之前杀掉进程 → 无 result → invalid。

**已修复且加了守卫**（修复不能用于重跑，见 §4）：probe 改为捕获 `BaseException`、记 `probe_interrupted`、仍写 `result.json`；`check_api_contract.py` 增加静态守卫，**修复前该守卫 fail、修复后 52/52 通过**，证明它确实能抓这一类。

### 3.2 B / C：**未执行**

请求 §2 明文：A 有效阴性不跳过 B，但 **A invalid 停止 B**；B invalid 才停 C。A 为 invalid，故 B、C 依门未启动。**UDPv4 单变量本轮没有任何样本，SHM 结论为零**。

## 4. 为什么不重跑（预算未用尽但不得用）

- 本轮 T1 实际 **1/3**，累计 **12.651 s**（限 90 s），剩余预算存在。
- 请求允许的"修复一次"仅限"**启动前编排异常且 0 被测进程**"。本次失败有 **2 个 participant 存活、跑满 12.651 s**，不符合该条件。
- 用剩余预算重跑，等于把一个明确属于 Worker 的缺陷静默改写成一次"测量结果"。故**不重跑**，如实记为 invalid。

## 5. 判读

**本轮未取得有效数据面测量。**

### 5.1 有效成立的部分

1. **同 boot 确认**（§0），排除了第17轮那种跨 boot 混淆。
2. **UDPv4 变量可被显式记录**：A 例中该键在构造环境与真实进程环境**均不存在**，证明"缺省"是证据而非意图；B/C 未跑故无 UDPv4 值。
3. **第18轮 maps/stat 缺陷已修复并验证**：运行中抓取到真实 `python3` 进程（`comm=python3`、maps 非空），离线守卫同时断言"识别不了就记 `runtime_maps: missing`，不用 bash maps 替代"。
4. **门控语义正确**：sub 只在 pub `endpoint_created`（flush/fsync）之后启动。

### 5.2 不作为结论保留的原始观测

`evidence/A-observation-nonauthoritative.json`（**明确标为非权威**）：pub 侧 47 样本 `matched=1`、`graph_sub=1`、`sub_info=1`、2 次 `matched_event`；sub 侧 30 样本跨 7.42 s，`graph_pub=0`、`pub_info=0`、`matched=0`、`heard=0`。

这是第3–14轮熟悉的**单向**形态，但**不能据此立论**：① 该样本本身 invalid；② sub 窗口被回收竞态截断，若本 boot 的 pub→sub 发现本就慢于 7.42 s，会得到同样图像。故仅作原始留存与下一轮设计输入。

### 5.3 明确非结论

- **SHM vs UDPv4：零结论**（B/C 未跑，无任何 UDPv4 样本）。
- **一般跨进程数据面：零结论**（A invalid）。
- 不是工程恢复、不是永久配置、不是 domain 结论；S2/S3/S4、gate、headless、科研结论未动。

## 6. 预算

| 项 | 值 | 上限 | 判定 |
|---|---:|---:|---|
| T1 次数 | **1**（A，invalid） | 3 | 未用尽 |
| A span | 12.651 s | 30 s | 合规 |
| 累计 T1 | 12.651 s | 90 s | 合规 |
| participant | 2 | 2 | 合规 |
| 整轮 mono | **505.840 s = 8.431 min** | 45 min | 合规 |

无重跑、无臆造样本。

## 7. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_mid_ns` | 7766996873933 |
| `end_wall_iso` | `2026-10-28T19:28:19.695940+08:00` |
| `pair_gap_ns` | 31473 |
| 整轮 mono | **505.840 s = 8.431 min** |

## 8. 首次封存与取回

命令（不 `--force`，stdout 在新根外）：

```text
python3 -B scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-transport-data-plane-r1
```

stdout 原文（`/tmp/agc-w8-validation-r19-archive/archive-stdout.txt`，rc=0）：

```text
ok     w8-validation/20261028-transport-data-plane-r1 artifacts=37 verify=True files=38 mismatches=0

archived=1 skipped=0 error=0 retrieval_failed=0
```

独立核对（不依赖脚本自述）：

| 核对项 | 实测 | 结果 |
|---|---|---|
| manifest artifacts | **37**，逐项 size/sha 重算 | 0 mismatch |
| tar 成员 / 真实根 | **38** / 唯一 `20261028-transport-data-plane-r1/` | 正确 |
| tar 独立重算 sha256 | `f36e39681fc211bdd98c7fee6739ac748b70207e4837a9ebf9347c7a63b3ad36` | 与 `.tar.sha256` 一致 |
| 逐文件相等 | `root_only=[]`、`tar_only=[]`、differing 0 | 38/38 |
| retrieval | `verified=true`、`files_checked=38`、`mismatches=[]` | 通过 |
| 独立解包取回 | 38 文件逐个哈希 | 0 mismatch，临时目录已删 |
| 归档权限 / 封存后源根 | tar `0444` / 源根 0 写入 | 通过 |

封存前基线复算：**43520/43520，drift 0**。

## 9. 实际改动（覆盖全部写操作）

**新根内新增**：`scripts/` 8 个、`evidence/` 6 个、`report/analysis.md`、`cases/A/` 全套原件，封存时 `config/evidence_manifest.json`；共 **37** 个产物。

**新根外**：本轮 `report.md`、`CURRENT.md`（待执行→执行中→待审查）、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 round19 勾选、`experiments/_archive/w8-validation/20261028-transport-data-plane-r1.tar{,.sha256,.retrieval.json}`、`/tmp/agc-w8-validation-r19-*`。

**勾选如实性**：`tasks.md` 4 项全勾（第2项注明 A invalid、B/C 未执行、T1 用 1 次）；`checklist.md` **第 1 项保持未勾**，因为"A 有效 + B/C 按门执行 + UDPv4 变量"本轮确实未达成——不勾选造假。

**未改**：`src/`、项目 `scripts/`、`toolchain/`、`build/install`、spec/Runbook/request/历史 review、第18轮探针/驱动、历史源根/归档；未 reset/clean/commit/push/切分支；全程 `python3 -B`，无 `__pycache__`。

## 10. 待裁定

1. **回收窗口口径必须在下轮前修好**：驱动应按 probe 自身 `process_entry`/`endpoint_created` 时间戳计时，或给 probe 的预算大于驱动回收期限；否则每个 rclpy 侧用例都可能在不确定点被截断（本轮即此）。
2. **"无 result 但有 events"应记为 partial 而非缺失测量**：否则有信息量的部分观测会被整体作废。
3. **A/B/C 门顺序是否该重审**：A 一旦 invalid 就整轮作废，即使其原始证据恰是本轮想拿的判别观测。部分证据能否用于下一轮设计，属 Leader 裁定。
4. 若重派 A，仍应保持同 boot/domain0/LOCALHOST/默认传输；**UDPv4（B/C）至今零样本**。
