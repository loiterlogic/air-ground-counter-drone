<a id="round18-report"></a>
# 第18轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次18。

执行者：Worker 子会话 `47a2651c-e420-4218-b4c6-454837cd33fd`（复用，Leader 于2026-10-28派工）。

> 页头由Leader预置；正文由Worker追加。领取先写配对时钟并核对刷新后的基线，再改CURRENT为执行中。

## 0. 领取配对时钟（本轮第一个动作）

单进程内 `monotonic_ns()` → `time_ns()` → 本地 ISO → `monotonic_ns()` → `time_ns()`，不插其他动作；**本轮第一次写入**，当时 `CURRENT.md` 仍为 `待执行`。原始输出：`experiments/w8-validation/20261028-stock-rclpy-mixed-r1/evidence/claim-clock.txt`。

| 字段 | 值 |
|---|---|
| `claim_mono_mid_ns` | **5615424857035** |
| `claim_wall_iso` | `2026-10-28T18:52:00.071366+08:00` |
| `pair_gap_ns` | 22694 |
| `/proc/uptime` 同时刻 | 5615.42 s（与 mono 5615.4249 s 差 <10 ms） |

写 claim 之后（13 s）才把 CURRENT 改为 `执行中`，顺序未颠倒。

## 1. 接单基线与领取核对

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `18`、`待执行` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 受保护集（刷新后） | **43448/43448**，missing 0、size/sha 不符 **0** | **漂移 0** |
| `git status --porcelain` | **36 项**，与 baseline 逐行相同 | 一致 |
| 新根 | 预置 `config/` 两件 + 空 `cases/evidence/log/report/scripts` | 一致 |

**刷新后的基线首次自洽**：`evidence/baseline-check-claim.json` `verdict=PASS`，第17轮遗留的两项 Leader 文档滞后已随本次刷新消除，本轮无需再次豁免。开跑前 `pgrep` 无 demo/probe 进程，未终止任何他人进程。

## 2. T1 三次执行

固定条件（三例一致）：当前 boot、`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、topic `/agc_r18/chatter`、rclpy QoS depth10/RELIABLE/VOLATILE/KEEP_LAST、仅 `source /opt/ros/jazzy/setup.bash`；未设 RMW/LD_PRELOAD/profiles/builtin transports/static peers（两端 `/proc/<pid>/environ` 实证 `RMW_IMPLEMENTATION=None`、`LD_PRELOAD=None`）。

| # | 例 | 结果 | span | participant | 真实 RC |
|---|---|---|---:|---:|---|
| 1 | **C0** 同进程正负控制 | **有效通过** | 7.577 s | 1 | 0 |
| 2 | **A** stock talker→rclpy sub | **有效**（matched 但零接收） | 12.570 s | 2 | rclpy 0 / stock 0 |
| 3 | **B** rclpy pub→stock listener | **有效**（matched 但零接收） | 12.571 s | 2 | rclpy 0 / stock 0 |

累计 T1 **32.718 s**（≤90 s，≤本单目标 75 s）。

### 2.1 C0（请求 §4）

三相位同一进程；判据**从原始 `events.jsonl` 重算**（`evidence/recount-C0-attempt2-raw.json`）：

| 相位 | graph pub/sub 峰值 | 自身 matched 峰值 | heard | incompatible 事件 | 判据 |
|---|---|---:|---:|---:|---|
| pos 同 topic 兼容 QoS | 1 / 1 | 1 / 1 | **59** | 0 | **通过** |
| neg_diff_topic | 1 / 0 | 0 / 0 | **0** | 0 | **通过** |
| neg_qos BEST_EFFORT→RELIABLE | 1 / 1 | 0 / 0 | **0** | **2** | **通过** |

事件流完整性：58 条事件、`seq` 严格 1..58、单一 PID 6802、无坏行。

### 2.2 A（stock talker → rclpy subscription）

`cases/A/`，48 个采样帧（`evidence/recount-A-raw.json`）：

| 层 | 观测 | 值 |
|---|---|---|
| 发现视图 | `count_publishers` | **1** |
| endpoint info | `get_publishers_info_by_topic` | **1 条**，`ok=true` |
| 实体识别 | `endpoint_type` / GID | `PUBLISHER` / `010fc2ed751cc7280000000000001403` |
| 类型一致 | `topic_type` / hash | `std_msgs/msg/String` / `RIHS01_df668c74…6b1a18` |
| QoS | 对端 qos_profile | RELIABLE / VOLATILE |
| **DDS 匹配** | `get_publisher_count()` | **1**（48 帧中 22 帧），`matched_event` ×2 |
| **用户数据** | `heard_n` | **0**（全部 48 帧） |
| incompatible | — | 0 |

**时序（用 `btime=1793179117` 与 stock 自身日志时间戳重算）**：talker 起于 uptime 6177.605，首条发布 6177.746，**首次 matched=1 在 6178.104**，最后一次 matched=1 在 6183.476。即匹配在 talker 启动后 **499 ms** 建立，之后又发布了 **4 条**（6178.746/6179.746/6180.746/6181.746）全部落在 matched 窗口内 —— **不是"首条抢跑"**。

### 2.3 B（rclpy publisher → stock listener）

`cases/B/`，48 个采样帧（`evidence/recount-B-raw.json`）：

| 层 | 观测 | 值 |
|---|---|---|
| 发现视图 | `count_subscribers` | **1** |
| endpoint info | `get_subscriptions_info_by_topic` | **1 条**，`ok=true` |
| 实体识别 | `endpoint_type` / GID | `SUBSCRIPTION` / `010fc2edf81cde5e0000000000001404` |
| 类型一致 | `topic_type` / hash | `std_msgs/msg/String` / `RIHS01_df668c74…6b1a18` |
| **DDS 匹配** | `get_subscription_count()` | **1**（22/48 帧），`matched_event` ×2 |
| rclpy 已发 | `sent_n` | **12** 条（~1 Hz） |
| **stock 接收** | stock 原文 `I heard:` | **0**（stdout 0 B，stderr 71 B 仅 shutdown 行） |
| incompatible | — | 0 |

**时序**：listener 起于 uptime 6227.815，首次 matched=1 在 6228.323（+508 ms），last matched 6233.653（窗口 5.33 s），其间 sent 计数 1→6，即至少 **5 条在 matched 期间发出**，全部无接收。

## 3. 判读

**结论：stock↔rclpy 混合端点在两个方向上都能完成发现与 DDS 匹配，但在两个方向上零消息送达。断点已从"发现/匹配"下移一层，落在数据面/回调路径。**

### 3.1 本轮新增（相对第14–17轮）

1. **首次取得"匹配成立但无数据"的跨 stock/rclpy 证据**：此前各轮无法区分"没发现"与"匹配了但没数据"；本轮两端 `matched=1`、对端 endpoint 可见、type hash 相同、QoS 兼容，仍然零接收。
2. **类型层与 QoS 层可排除（就这两个样本而言）**：靠实际字段值（`topic_type`、`RIHS01_…`、RELIABLE/VOLATILE），不是字符串猜测；且 incompatible 事件为 0。
3. **第3–14轮的"后启动方 graph/matched 恒 0"单侧形态未复现**：本轮 rclpy 先起，两个方向都达到 `matched=1`，rclpy 侧都看得到对端。剩下的问题不是"谁先起"，而是"匹配之后数据去哪了"。
4. **同一 boot 内的完整对照**：r16/r17 跨 boot，本轮 claim 与两例同一 boot（`/proc/uptime` 5615→6316 s）。

### 3.2 明确**未**成立

- **不是根因**。"数据面/回调之下"是**层**，不是机制。仍开放：SHM 传输路径（LOCALHOST 隐含 SHM+UDPv4）、r16 测得的 mirrored WSL `loopback0` 拓扑、进程内/进程外投递差异、序列化交接、executor/回调派发。
- **不是工程恢复**：两方向零接收。
- **不是** domain 无关的结论：本轮只测 domain0 一个点。
- **不是**项目节点的证据：未跑任何项目节点/GZ/PX4/GUI/headless/构建。
- `_NODE_NAME_UNKNOWN_` / `_NODE_NAMESPACE_UNKNOWN_` 是 stock demo 的正常表现，**不**当作缺陷。

## 4. 预算

| 项 | 值 | 上限 | 判定 |
|---|---:|---:|---|
| T1 次数 | **3**（C0/A/B） | 3 | 合规 |
| C0 span | 7.577 s | 15 s | 合规 |
| A span | 12.570 s | 30 s | 合规 |
| B span | 12.571 s | 30 s | 合规 |
| 累计 T1 | **32.718 s** | 90 s（本单 75 s） | 合规 |
| participant 峰值 | 1 / 2 / 2 | 2 | 合规 |
| 整轮 mono | **701.094 s = 11.685 min** | 45 min | 合规 |

## 5. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_mid_ns` | 6316519082942 |
| `end_wall_iso` | `2026-10-28T19:03:53.551997+08:00` |
| `pair_gap_ns` | 14404 |
| 整轮 mono | **701.094 s = 11.685 min** |

原始输出：`evidence/end-clock.txt`。

## 6. 三次 C0 尝试如实登记（含两次非测量样本）

| 尝试 | 现场 | span | participant | 性质 |
|---|---|---:|---:|---|
| `C0-attempt0-preflight-failure` | 探针 `ModuleNotFoundError: rclpy` | 0.093 s | **0** | 启动前编排异常，被测进程未起 → 协议允许修复 1 次 |
| `C0-attempt1-probe-api-bug` | `AttributeError: 'Publisher' object has no attribute 'get_publisher_count'` | 0.574 s | 1 | **我新写代码的缺陷**，未产出测量 → 计入尝试、不隐瞒 |
| `C0`（有效） | 正常完成三相位 | 7.577 s | 1 | 有效测量 |

**根因与修复（均留原件）**：
1. clean-env 缺 `PYTHONPATH`，rclpy 侧未像 stock 侧那样经 `source` 包装 → 两侧统一用 `bash -c 'source … && exec …'`。
2. 我把匹配计数 API 写反（`Publisher.get_publisher_count` 不存在，真名是 `get_subscription_count`）→ 静态读取真名后修正。
3. （第 3 次有效测量之后）`run_phase` 里 `'%s_pub_incompatible_total'` **未做 %-格式化**，`.get()` 永远返回默认 0 → 修复，并**从原始 events 重算** C0/A/B 判据，不再依赖派生 summary。**没有为此追加 T1**。

第 2、3 项本可由离线检查拦住，故新增两道离线防线（见 §7），其中行为级守卫可在 ~1 s 内离线复现该记账缺陷。

## 7. 离线（T1=0）验证

- `evidence/offline-gate-tests.json`：门控 **8/8** 通过（仅用 fake，**非真实样本**）——good 放行；no_endpoint → `gate_timeout`；wrong_order → `lifecycle_order_violation`；wrong_role → `endpoint_role_mismatch`；坏 jsonl → `events_unparsable`（不当作"无端点"）；sleep_long → 超时且 **stock 从未启动**；fake 探针在真实例中被拒 rc=2；探针 RC 被记录。
- `evidence/api-contract-check.json`：**45/45**——探针用到的每个 rclpy 属性在本机存在且方向正确（含 pub→subscription / sub→publisher 配对）、`TopicEndpointInfo`/`TypeHash`/`QoSProfile` 字段齐全、AST 守卫禁止 `.get()` 键里残留未格式化 `%s`、行为守卫用 stub 驱动 `run_phase` 验证 incompatible 计数真的进入相位结果。

## 8. 首次封存与取回

命令（**不** `--force`，stdout 落新根之外）：

```text
python3 -B scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-stock-rclpy-mixed-r1
```

stdout 原文（`/tmp/agc-w8-validation-r18-archive/archive-stdout.txt`，rc=0）：

```text
ok     w8-validation/20261028-stock-rclpy-mixed-r1 artifacts=65 verify=True files=66 mismatches=0

archived=1 skipped=0 error=0 retrieval_failed=0
```

独立核对（**未依赖脚本自述**）：

| 核对项 | 实测值 | 结果 |
|---|---|---|
| manifest `artifacts` | **65**，逐项 size/sha256 重算 | **0 mismatch** |
| tar 成员数 | **66**（65 产物 + manifest 自身） | — |
| tar 真实根 | 唯一 `20261028-stock-rclpy-mixed-r1/` | 正确 |
| tar 独立重算 sha256 | `cd441c3729c6e7ad0abcdca8680d6105a4fb15d23c431db13420f80fc6472c00` | 与 `.tar.sha256` 一致 |
| 逐文件相等 | **66/66**，`root_only=[]`、`tar_only=[]` | 0 差异 |
| retrieval | `verified=true`、`files_checked=66`、`mismatches=[]` | 通过 |
| **独立解包取回**（另一路径） | 66 文件逐个哈希 | **0 mismatch**，临时目录已删 |
| 归档权限 | tar `0444` | 只读 |

封存前基线复算：**43448/43448，drift 0**（`evidence/baseline-check-preseal.json`）。

## 9. 已知证据缺陷（如实披露，未回补）

**每例的 `*.maps.txt` 只有 4 行（全部 `ld-linux-x86-64.so.2`）**：驱动在 spawn 后**立即**抓 `/proc/<pid>/maps`，此时直接子进程还是尚未 `exec` 的 `bash` 包装。同理 `*.stat.json` 的 `comm` 为 `bash`、`starttime` 属包装进程。

- 因此本轮 `maps` **不能**当作"libfastrtps/librclcpp 已加载"的证据，不能与 r16/r17 的 120 行 maps 并列。
- PID/PGID/starttime 属包装进程；但 `exec` 原地替换，**真实 wait RC 与回收证据仍然有效**。
- 补偿性静态证据：`evidence/static-dt-needed.txt` 记录两个 demo 二进制声明的 `DT_NEEDED`（`librclcpp.so` 等），属**静态**链接声明，**不是**运行时观测。
- T1 预算已尽、源根已封存，故**未尝试修复**，仅披露。后续轮应改为 `exec` 后再抓（轮询 `comm != bash`）。

## 10. 实际改动（覆盖全部写操作）

**新根内新增**：`scripts/` 9 个脚本、`evidence/` 10 个、`report/analysis.md`、`cases/{C0,A,B}/` 全套原件、两个保留的失败 C0 目录，封存时新增 `config/evidence_manifest.json`，共 **65** 个产物。

**新根外**：本轮 `report.md`（本文件）、`CURRENT.md`（待执行→执行中→待审查）、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 round18 勾选（各 4/5 项，仅 `[ ]`→`[x]` 并附注）、`experiments/_archive/w8-validation/20261028-stock-rclpy-mixed-r1.tar{,.sha256,.retrieval.json}`、`/tmp/agc-w8-validation-r18-*`。

**未改**：`src/`、项目 `scripts/`、`toolchain/`、`build/install`、spec/Runbook/request/历史 review、第14轮探针/driver/gate（只读）、历史源根/归档；未 reset/clean/commit/push/切分支；全程 `python3 -B`，无 `__pycache__`。

## 11. 待裁定

1. **maps 缺陷是否需要在下一轮补测**（我未擅自回补）。
2. **下一步分层方向**：同一 boot 内 (a) rclpy↔rclpy 同 boot 重测、(b) domain37 同 boot 对照、(c) 仅 UDPv4 排除 SHM —— (c) 属配置变更，需显式授权。
3. C0 的两次失败尝试是否按"1 次有效 T1 + 2 次无效"计入下一轮口径（本轮按协议记为 3/3 已用尽）。
