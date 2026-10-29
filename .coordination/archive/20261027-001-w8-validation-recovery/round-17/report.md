<a id="round17-report"></a>
# 第17轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次17。

执行者：Worker 子会话 `47a2651c-e420-4218-b4c6-454837cd33fd`（Leader 于 2026-10-28 创建，接续同一任务链）。旧 Worker `1ac7d798-9215-494f-a7e6-013518f7894d` 因父会话边界未执行本轮；本轮报告以本子会话为准。

> 本文件页头与"派工通知阻塞"段由 Leader 预置；以下正文由 Worker 追加。

## 派工通知阻塞（Leader，2026-10-28）— 原样保留

Leader 完成派工后调用 `send_message` 复用上述 Worker，工具返回：`subagent "1ac7d798-9215-494f-a7e6-013518f7894d" belongs to another parent session`。当前会话 `list_agents` 的 children/descendants 均为空，无法按协议接续原Worker。

未新建替代Worker、未启动任何实验、未将通知失败伪装为已投递。CURRENT已置阻塞；需原父Leader会话投递，或由用户明确裁定跨会话接续方式。第17轮request/规格/基线保持完整，Worker尚未领取。

> **Worker 补注（2026-10-28 18:33）**：该阻塞已由用户授权当前 Leader 新建本 Worker 接续而解除；上面这段是当时的事实记录，保留不改写。本 Worker 由 Leader 新建，`DSH_SESSION_ID=47a2651c-e420-4218-b4c6-454837cd33fd`。

## 0. 领取配对时钟（本轮第一个动作）

采样方式：单进程内 `time.monotonic_ns()` → `time.time_ns()` → 本地时区 ISO → `time.monotonic_ns()` → `time.time_ns()`，不插其他动作。**本段是本轮第一次写入**（当时 `CURRENT.md` 仍为 `待执行`）。原始输出：`experiments/w8-validation/20261028-stock-domain37-control-r1/evidence/claim-clock.txt`。

| 字段 | 值 |
|---|---|
| `claim_mono_before_ns` | 4495408886970 |
| `claim_mono_after_ns` | 4495408909463 |
| `claim_pair_gap_ns` | 22493（≈22.5 µs） |
| `claim_mono_mid_ns` | **4495408898216** |
| `claim_wall_ns` | 1793183581058394440 |
| `claim_wall_iso_observed` | `2026-10-28T18:33:01.058395+08:00` |
| `/proc/uptime` 同时刻 | 4495.41 s（与 mono 4495.4089 s 差 <10 ms，mono 即 boot-relative） |
| 采样进程 | `python3`，shell `pid=5001` |

**写 claim 之后**才把 `CURRENT.md` 改为 `执行中`（mtime `18:33:14`，**晚于** claim 13 s）。顺序未颠倒。

## 1. 接单基线与领取核对

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `17`、状态 `待执行` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 与 receipt 一致 |
| `git status --porcelain` | **36 项** | 与 receipt 一致；逐行与 baseline `git_status_porcelain` **完全相同** |
| 受保护集逐项复算 | **43407/43407** 可读，missing 0 | 见 1.1 |
| 新根目录 | 预置 `config/` 两件 + 空 `cases/evidence/log/report/scripts` | 一致 |

### 1.1 受保护集漂移：2 项，已由 Leader 裁定为已知基线滞后

`config/codex_dispatch_baseline.json` 43407 项逐项复算（`evidence/baseline-check-claim.json`、`evidence/baseline-check-preseal.json` 两次一致）：

| 文件 | baseline 记录 | 实际 | 性质 |
|---|---|---|---|
| `.coordination/task/20261027-001-w8-validation-recovery/round-17/request.md` | 7841 B / `8b852563…` | 7996 B / `fe3a353a…` | Leader 快照后补写 |
| `docs/ROS2迁移步骤.md` | 64652 B / `c6d3c750…` | 64821 B / `53a44a4f…` | Leader 快照后补写 |

**归因**（我在中期报告里已先报、Leader 已独立核对）：receipt `created_at=18:25:52`，两文件 mtime 分别 `18:28:09` / `18:29:04`，**都晚于快照、早于我的 claim（18:33:01）**；内容也对得上——request.md 中"新子会话ID由Leader写入本轮report"、Runbook 中"派工通知因原Worker属于另一父会话而失败…CURRENT为阻塞"都是快照后补写的文字。我从未写入这两个文件（均不在我的白名单内）。

**Leader 裁定（2026-10-28，经 `send_message` 收到）**：已读 `baseline-check-claim.json`，确认两项 SHA/size 与我的报告一致，且确为 baseline 生成后、我 claim 前补写的授权与阻塞状态；裁定为**已知且已归因的 Leader 基线快照滞后，不是未知第三方漂移，本轮可继续**；要求**不中途重建 baseline/receipt、不修改这两份文件**，在本报告登记裁定，结束时以**领取时 actual 值**作为这两项已知更正、其余 **43405 项按原 baseline 复算**，并报告之后是否有新增漂移。

**按裁定执行的结果**：43405 项复算 **0 漂移**；2 项已知更正以领取时 actual 值为准（上表"实际"列，封存前复核仍为同值，**无新增漂移**）。未重建 baseline、未修改这两份文件。

其他：`git_status` 36 项逐行相同；HEAD 与分支未变；未 reset/clean/commit/push/切分支。

### 1.2 开跑前冲突核对（只读）

`evidence/pre-run-check.txt`：`pgrep` 无 demo/probe/driver/daemon 进程；无既有 `/tmp/agc-w8-validation-r17-*`；demo 二进制 sha256 listener `f9c3d9c26887c516bedc7f4b2f4c108769047ecf3c9624a0a0d7a536d959ae2e`、talker `63c40ad0122424603a37a50adffbbb14a9a36ffedbae40e07b67012f558cf533`。**未终止任何他人进程。**

## 2. 运行记录

### 2.1 固定条件（A 例，全部由 `/proc/<pid>/environ` 实证）

只 `source /opt/ros/jazzy/setup.bash`（不 source 项目 install）；`ROS_DOMAIN_ID=37`；`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`；**未设** `RMW_IMPLEMENTATION`/`LD_PRELOAD`/`FASTRTPS_DEFAULT_PROFILES_FILE`/`FASTDDS_BUILTIN_TRANSPORTS`/`ROS_STATIC_PEERS`/`ROS_LOCALHOST_ONLY`（六个键在真实环境中**均不存在**）；`HOME=/home/chen`；每例独立 `ROS_HOME`/`ROS_LOG_DIR`；topic `/agc_r17/chatter`；listener 先起 → 2.0 s → talker 运行 6 s → SIGINT 优雅回收。

### 2.2 A（T1 #1）：domain37 stock 历史阳性条件复现 —— **有效阴性**

- 完整 argv（`cases/A/command.json` → `A-listener.argv`）：
  `bash -c 'source /opt/ros/jazzy/setup.bash && exec "$@"' bash /opt/ros/jazzy/lib/demo_nodes_cpp/listener --ros-args -r chatter:=/agc_r17/chatter`
  talker 同构，可执行换为 `…/talker`。`exec` 直替 bash，demo 二进制即直接子进程。
- PID/PGID/starttime：listener `pid=5330, pgrp=5330, starttime=478917`；talker `pid=5352`（`command.json` 全文）。
- 配对时钟：listener spawn mono `4789178602581` / `18:37:59.362784`；talker spawn mono `4791180411171` / `18:38:01.928041`（**+2.0018 s**）；talker exit mono `4797295610911`；listener exit mono `4797409592609`。**重叠 8.117 s**，listener 存活 8.231 s。
- 真实 `wait` RC：listener **0**、talker **0**；`reclaim_steps` 只有 `SIGINT`，**无** SIGTERM/SIGKILL。
- 原文（`cases/A/A-listener.listener.stderr.log`，71 字节，全文一行）：
  ```text
  [INFO] [1793183888.043490340] [rclcpp]: signal_handler(SIGINT/SIGTERM)
  ```
  `A-listener.listener.stdout.log` = **0 字节**（`sha256 e3b0c442…`）。
- talker 确实发布 5 条（`cases/A/B-talker.talker.stderr.log`，416 字节）：`Hello World: 1..5` 逐条带时间戳，随后是 `signal_handler` 行。
- `A-listener.listener.stdout.log` 与 stderr 独立重数：**`I heard:` = 0**（`evidence/verdict-A-recount.json`，不采信驱动自述）。`ros_log/` 内 `listener_5330_…log` 71 B 与 stderr 同 sha，`I heard:` 亦 0。
- 库映射：两侧各 **120 条**匹配 VMA，含 `libfastrtps.so.2.14.7`、`librmw_fastrtps_cpp.so`、`librmw_fastrtps_shared_cpp.so`、`librclcpp.so`。
- 残留：自有 PGID 无存活成员、`ps` 无 demo 进程、无 `__pycache__`。

**判定：A 有效阴性 → 按 request `## 4` 跳过 B 和 C，本轮停止。**

### 2.3 环境构造与真实环境（request 要求的区分）

- 构造 11 键（`command.json` → `env_constructed`，**恰好 11 键**，即 p3-r2 `env_exported` 集合）：HOME/LANG/LC_ALL/LOGNAME/PATH/ROS_AUTOMATIC_DISCOVERY_RANGE/ROS_DOMAIN_ID/ROS_HOME/ROS_LOG_DIR/SHELL/USER。
- 真实 `/proc/<pid>/environ`：**22 键**，两端 sha256 完全相同（`d4c05cb75dadae65…`）。11 键全部在，**唯一值差异是 `PATH`** 被 `source` 前置了 `/opt/ros/jazzy/opt/gz_*_vendor/bin:…:/opt/ros/jazzy/bin:`；另注入 11 键 `AMENT_PREFIX_PATH / CMAKE_PREFIX_PATH / GZ_CONFIG_PATH / GZ_SIM_RESOURCE_PATH / LD_LIBRARY_PATH / PWD / PYTHONPATH / ROS_DISTRO / ROS_PYTHON_VERSION / ROS_VERSION / SHLVL`。
- **不把 11 键伪称为最终环境**：如上，真实是"11 构造键 + source 注入"。注入项里**没有**任何被禁止的 RMW/transport/profile/peer 键。
- 真实 domain/range：两端均 `ROS_DOMAIN_ID=37`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`。

### 2.4 驱动来源与最小改动（request `## 5` 要求）

`scripts/run_stock_case_r16_source.py` = 第16轮 `run_stock_case.py` **逐字节拷贝**（sha256 `3c4be86dedcb3a6b12ec016979cd364b567504375e2277c9df5a2734518107d7`，与源文件一致）。本轮驱动器 `scripts/run_stock_case.py`（sha256 `ce4667f0…`）以它为基线，`evidence/driver-derived.diff` 全文留痕（76 删除行 / 142 新增行）。改动**仅限** request 允许的参数化：

1. `--domain`（原硬编码 0）；
2. `--topic`（原硬编码 `/agc_r16/chatter`）；
3. `--env-profile hist11`（原 7 键 clean / 52 键 inherit）；
4. 本轮 case/root/scratch 命名；
5. `--netsnap {auto,off}`。

**控制语义未变**：直接 `exec`、listener 先起、2.0 s、talker 6 s、SIGINT 优雅回收、真实 `wait` RC、原文捕获、`/proc` 快照、`I heard:` 判据。新增只读派生字段（`env_provenance`、`talker_publishing`、`driver_sha256`），不改变任何判定。

### 2.5 B / C：按停止门跳过（不是失败、不是遗漏）

| 例 | 状态 | 原因 |
|---|---|---|
| B（domain0 单变量对照） | **未执行** | request：A 有效阴性 → 跳过 B |
| C（同域既有探针 pub-first） | **未执行** | request：C 仅在 A 阳性且 B 有效后执行 |

因此 **T1 实际使用 1/3**；剩余 2 次**不结转**、不视为可用额度。未触碰第14轮探针/driver/gate（只读，未改），未扫描 domain，未扩写 endpoint-info。

## 3. 判读

**结论：历史 `p3-r2` stock 阳性在本轮条件（domain37 / LOCALHOST / 11 键构造 / 直接 exec）下未复现；A 为有效阴性。**

### 3.1 直接支持

1. **domain37 也不再成功**：相同 stock 二进制、相同 domain37、相同 range、相同 11 键构造、相同 2 s/6 s 时序下，listener 全程存活且 `I heard:` = **0**（5 条已发布）。
2. **第16轮的阴性不能只用 domain0 解释**：第16轮 domain0 失败、本轮 domain37 失败，"domain"已不再是区分两次结果的自变量。
3. **本轮阴性不是日志捕获假象**：同一 stderr 文件确实写入了 SIGINT `signal_handler` 行（71 B），说明输出通路在存活期是刷盘的；这一点正是 `p3-r2` 首例 0 字节所无法主张的（第16轮已更正的时序事实）。

### 3.2 存在但**不主张为原因**的可比性断裂：宿主已重启

| 证据 | `p3-r2`（10-26 20:35） | 第16轮（10-28 15:26） | 本轮（10-28 18:33） |
|---|---|---|---|
| `/proc/uptime` 领取时 | 未记录 | 25551.06 s | **4972.50 s** |
| `btime` → 启动墙钟 | — | — | **2026-10-28 17:18:11 +0800** |
| `dmesg -T` 首行 | — | — | `[Wed Oct 28 17:18:13 2026]` |
| `dmesg | grep -c CheckConnection` | — | 53 | **3** |

第16轮自己的记录是"10-28 15:26 时 uptime 25551 s"，本轮"18:33 时 uptime 4972 s"——同一台机器同一天不可能同时成立；全 boot 的 `CheckConnection` 计数 53 → 3 独立佐证**第16轮与本轮之间发生过重启**（宿主 17:18:11 开机）。证据：`evidence/boot-provenance.txt`、`evidence/reboot-corroboration.txt`。

这条**只是限制，不是发现**：

- 它**不能**救回"domain37 是差异"这一假设——domain37 恰恰是本轮条件，且失败了；
- 但它确实意味着"历史阳性未复现"**不能**被改写成"机器永久损坏"或"domain37 也坏了"：重启后的机器状态只是若干候选之一，本轮**没有**重启前 domain37 的对照；
- request 早已预防这一层过度推断（"不把单次结果升级为永久环境损坏"）。

### 3.3 明确**未**成立的推论

- **不是**"domain0 坏了"，也**不是**"domain37 坏了"：B 未执行；domain0 的最后实测在第16轮、属于**上一个 boot**。
- **不是**关于既有 endpoint 探针的任何新结论：C 未执行，本轮对探针侧 graph/matched/heard 无新增证据。
- **不是**根因。断点仍只能定位到"discovery / matching / delivery 之间"，与第16轮相同，无推进。
- **不是**项目自身节点的证据：未跑任何项目节点、GZ、PX4、GUI、headless、构建。

### 3.4 仍未排除项（供下一轮设计，不在本轮解决）

1. 当前 boot 内 domain37 与 domain0 的**受控配对**是否都失败（可把"domain"与"boot"分开）。
2. 第14轮 endpoint 探针在**当前 boot** 是否仍单向 graph/matched + 零消费。
3. 重启是否清掉了重启前的进程或 `/dev/shm` 残留（本轮只观测到计数 1 → 2，未读内容、未清理，不作归因）。
4. DDS 内部断点（participant discovery / SEDP matching / 数据面 / 回调），本层仍无观测。

## 4. 预算

| 项 | 值 | 上限 | 判定 |
|---|---|---|---|
| T1 次数 | **1**（A；B/C 按门跳过） | 3 | 合规 |
| A 墙钟（首次 spawn → 全回收） | **8.231 s** | 30 s | 合规 |
| A 包装墙钟（含解释器启动） | 8.342 s（mono 口径；同段 wall 差 8.906 s，仅报告） | — | 仅报告 |
| 累计 T1 墙钟 | **8.231 s** | 90 s | 合规 |
| 每次被测进程 | **2**（listener + talker） | 2 | 合规 |
| 整轮 mono（claim → end） | **571.734 s = 9.529 min** | 45 min | 合规 |
| 整轮 wall | 580.616 s | — | 仅报告，不归因 |

**无重跑、无无效样例**：唯一一次 A 即为有效样本，request 规定有效结果不重跑，故本轮没有"invalid attempt"行。

## 5. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_before_ns` | 5067142863047 |
| `end_wall_ns` | 1793184161674349043 |
| `end_wall_iso` | `2026-10-28T18:42:41.674349+08:00` |
| `end_pair_gap_ns` | 19473 |
| 整轮 mono | **571733974567 ns = 571.734 s = 9.529 min** |
| 整轮 wall | 580.616 s |

原始输出：`evidence/end-clock.txt`。

## 6. 首次封存与取回核验

命令（**不** `--force`，stdout 落新根之外）：

```text
python3 -B scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-stock-domain37-control-r1
```

stdout 原文（`/tmp/agc-w8-validation-r17-archive/archive-stdout.txt`，rc=0）：

```text
ok     w8-validation/20261028-stock-domain37-control-r1 artifacts=34 verify=True files=35 mismatches=0

archived=1 skipped=0 error=0 retrieval_failed=0
```

独立核对（**未依赖脚本自述**，逐项亲自复算）：

| 核对项 | 实测值 | 结果 |
|---|---|---|
| manifest `artifacts` 数 | **34**，逐项 size/sha256 重算 | **0 mismatch** |
| tar 成员数 | **35**（34 产物 + manifest 自身） | — |
| tar 真实根 | 唯一 `20261028-stock-domain37-control-r1/` | 正确 |
| tar 独立重算 sha256 | `2048fc4b37ab8050419742f919dab52411343481851f7fed877baff4d98c3435` | 与 `.tar.sha256` **一致** |
| 逐文件相等（tar vs 源根） | **35/35** | missing 0、mismatch 0 |
| `root_only` / `tar_only` | `[]` / `['config/evidence_manifest.json']` | 符合脚本设计 |
| retrieval 记录 | `verified=true`、`files_checked=35`、`mismatches=[]` | 通过 |
| **独立解包取回**（另一路径） | 35 个文件逐个哈希 | **0 mismatch**，临时目录已删 |
| 归档权限 | tar `0444` | 只读 |
| **封存后源根复核** | 35 个文件与 tar 逐成员比对 | **0 差异、无 root-only** → 封存后**未再写入源根** |

## 7. 未执行 / 偏离 / 阻塞

### 7.1 未执行

- **B、C 按停止门跳过**（见 2.5），原因已写明，**不计为失败**。
- 未开 S2/S3/S4；未做 gate/headless/科研；未扫描 domain；未改探针；未构建/仿真/抓包。

### 7.2 偏离（逐条如实登记）

1. **受保护集 2 项已知漂移**（见 1.1）：非我所为，Leader 已裁定为已知基线滞后；按裁定以领取时 actual 值登记，未重建 baseline。
2. **新增 `scripts/run_case.py` 包装**：request 允许新根 `scripts/` 新增内容；该包装只做编排（无 DDS participant），用于把 argv/配对时钟/真实 RC 落到 `evidence/`，避免把编排动作混进被测进程树。它不改变驱动控制语义。
3. **`--netsnap` 参数化**：为不改变"只起 2 个被测进程"的语义，网络快照仍默认 `auto` 执行（本轮实际执行）；该参数只是显式化，未用于跳过任何 A 例观测。
4. **`/dev/shm` 计数 1 → 2**：只记录计数，**未读内容、未清理**（派工禁止）。不作归因。
5. **`report/analysis.md` 第 125 行的口径不够精确，但封存后未改写**：该行写 "Wrap-level span including interpreter start: 8.342 s"，未标明这是 **mono 口径**；同一段的 wall 差实为 8.906 s。此差异属措辞不精确，不改变任何判据或预算判定（预算按 mono 计），且源根已封存只读，故**按规矩不在源根改**，只在本报告 §4 更正口径。封存前的正确写法本应加上"mono 口径"。

### 7.3 阻塞

**无。** 未触发 request `## 7` 的停止条件：无 guard 拦截、无预算超限、无共享资源冲突、无白名单外修改、无关键证据缺失、无未知保护漂移（2 项已裁定）。

## 8. 交付物与证据路径

新根 `experiments/w8-validation/20261028-stock-domain37-control-r1/`（34 个产物，全部在封存内）：

| 内容 | 路径 |
|---|---|
| 逐例判据与可比性分析 | `report/analysis.md` |
| A 完整原件 | `cases/A/command.json`、4 个原文捕获日志、2 个 `environ.json`、2 个 `maps.txt`、`ros_log/`、`netsnap-{before,after}.txt` |
| 领取/结束配对时钟 | `evidence/claim-clock.txt`、`evidence/end-clock.txt` |
| 基线复算（领取/封存前） | `evidence/baseline-check-{claim,preseal}.json` |
| 重启佐证 | `evidence/boot-provenance.txt`、`evidence/reboot-corroboration.txt` |
| 独立判据重数 | `evidence/verdict-A-recount.json` |
| 驱动派生 diff | `evidence/driver-derived.diff` |
| 开跑前/后残留核对 | `evidence/pre-run-check.txt`、`evidence/post-run-residue.txt` |
| `nstat` 前后差（仅上下文） | `evidence/nstat-deltas-A.json` |
| 驱动源码 | `scripts/run_stock_case.py`、`scripts/run_stock_case_r16_source.py`、`scripts/run_case.py`、`scripts/verify_baseline.py` |
| 入库 manifest | `config/evidence_manifest.json` |
| 归档与侧车 | `experiments/_archive/w8-validation/20261028-stock-domain37-control-r1.tar{,.sha256,.retrieval.json}` |

## 9. 实际改动（覆盖全部写操作）

**新根内新增**：`scripts/` 4 个脚本、`evidence/` 15 个、`report/analysis.md`、`cases/A/` 13 个原件、封存时由 `evidence_archive.py` 新增 `config/evidence_manifest.json`，共 **34** 个产物。

**新根外**：

- `.coordination/task/20261027-001-w8-validation-recovery/round-17/report.md`（本文件）。
- `.coordination/CURRENT.md`：`待执行` → `执行中`（领取）→ `待审查`（交回），并写入执行者与领取时间。
- `.trae/specs/w8-validation-recovery/tasks.md`：round17 段 **4 项**勾选（仅 `[ ]`→`[x]`，第2项追加跳过说明）。
- `.trae/specs/w8-validation-recovery/checklist.md`：round17 段 **5 项**勾选（仅 `[ ]`→`[x]`，第2项追加跳过说明）。
- `experiments/_archive/w8-validation/20261028-stock-domain37-control-r1.tar` 及 `.sha256`、`.retrieval.json`（ADR-0064 位置）。
- `/tmp/agc-w8-validation-r17-{A,archive}/`：A 的 ROS_HOME 与归档 stdout；`/tmp/agc-w8-validation-r17-{tasks,checklist}.before.md`：勾选前快照（用于自查 diff）。取回验证的临时目录已删除。

**未改**：`src/`、项目 `scripts/`、`toolchain/`、`build/`、`install/`、`spec.md`、Runbook、request、历史 review、第14轮探针/driver/gate、历史源根与归档内文件；`.coordination/task/…/round-17/request.md` 与 `docs/ROS2迁移步骤.md` **未被我改动**（漂移见 1.1）；未 reset/clean/commit/push/切分支；未产生 `__pycache__`（全程 `python3 -B`）。

## 10. 待裁定

1. **重启这一混杂因素如何进入下一轮口径**：本轮证明 domain37 在当前 boot 失败，但没有重启前 domain37 的对照。下一轮若要在**当前 boot**内用 domain37/domain0 受控配对区分"domain"与"boot"，需 Leader 明确授权（本轮 T1 已按停止门截止，不自行追加）。
2. **C 是否仍值得派**：本轮未取得任何新的 stock 阳性，按 request 的判读树，C 的前提（stock37 阳性）**不成立**；若仍要检查探针，需作为独立命题重新派工，不能沿用本轮判定。
3. **两项基线滞后是否需要在下一轮重新生成 baseline**：本轮按裁定未重建；若下一轮仍需 43407 项自证，建议由 Leader 在派工时重新生成 receipt（我下轮无法自证已被裁定为"已知"的漂移是否仍是原值）。

## 11. 本轮与第16轮的新增信息（对照）

| 维度 | 第16轮 | 第17轮 | 新增 |
|---|---|---|---|
| domain | 0（clean 7 键 / 继承 52 键） | **37（11 键构造）** | 历史阳性条件首次按原 domain 复现 |
| 进程树 | 直接 exec | 直接 exec | **可比**（消除第16轮列出的不可比项之一） |
| 环境 | 7 / 52 键 | 11 键构造（真实 22 键） | **可比于 p3-r2 的 11 键** |
| 结果 | 0/2 接收 | **0/1 接收** | domain37 同样失败 |
| 新增排除 | 仅探针失败/clean-env/早退/缓冲/UDP 整体 | **"阴性只由 domain0 造成"** | 见 3.1 |
| 新增限制 | — | **宿主在本轮前已重启** | 见 3.2 |
