<a id="round22-report"></a>
# 第22轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次22。

执行者：Worker 子会话 `47a2651c-e420-4218-b4c6-454837cd33fd`（复用，Leader 于2026-10-28派工）。

> 页头由Leader预置；正文由Worker按派工单追加。领取先写配对时钟并核对基线（43671项/SHA `bfa5b4bd…`），再改CURRENT为执行中。

## 0. 领取配对时钟（本轮第一个动作）

**本轮第一次写入**，当时 CURRENT 仍为 `待执行`。原始件：`evidence/claim-clock.txt`。

| 字段 | 值 |
|---|---|
| `claim_mono_mid_ns` | **11352080952746** |
| `claim_wall_iso` | `2026-10-28T20:28:59.892699+08:00` |
| `pair_gap_ns` | 21631 |
| `/proc/uptime` | 11352.08 s |

同 boot 延续（第21轮 9958.54 s → 本轮 11352.08 s），`btime` 未变。

## 1. 接单基线与领取核对

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `22`、`待执行` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 受保护集（刷新后） | **43671/43671**，missing 0、不符 0 | **漂移 0** |
| `git status --porcelain` | 36 项，与 baseline 逐行相同 | 一致 |
| 探针 | 复用第20轮 `probe_r20.py`（sha `baaece49…`），**未修改** | 合规 |

## 2. T1 两例：均 valid；A 重复单向，B 延长窗口仍单向

| | **A（sub-first 重复）** | **B（pub-first，延长窗口）** |
|---|---|---|
| 先起方（窗口） | sub（12.008 s） | pub（29.009 s） |
| 后起方（窗口） | pub（8.003 s） | sub（**25.009 s**） |
| 后起方窗口完全在先起方内 | 是（重叠 8.003 s） | 是（重叠 **25.009 s**） |
| **先起方** graph / endpoint-info / matched | **1 / 1 / 1** | **1 / 1 / 1** |
| **后起方** graph / endpoint-info / matched | **0 / 0 / 0** | **0 / 0 / 0** |
| **后起方** heard | —（pub，sent 8） | **0（98 样本 / 25.009 s）** |
| 分类 | `valid` / `valid` | `valid` / `valid` |

两例 `invalid=[]`、`problems=[]`；四条事件流 `seq` 严格 1..N、单 PID；真实 RC **0/0**；SIGINT 回收；运行中 maps `captured`。原文重算：`evidence/A-B-recount-raw.json`。

**B 的硬上限未被触发**：`used_deadline = anchor + 25.0 s + 1.5 s`，`clamped_by_hard_limit=false`，单例 span **29.673 s**（≤30 s）。

## 3. 判读

**落在请求 §4 第 1 条：A 复现单向、B 延长窗口仍后起方不可见 → 慢发现排除，两顺序 n≥2；下一轮才考虑进入发现通告/locator 诊断。**

- sub-first 现有 **n=2**（第21轮 B + 本轮 A），pub-first 有 **n=2**（第20轮 + 第21轮 A）。
- 后起 sub 在 **25.009 s / 98 帧**内**一次都没有**看到对方（graph_pub=0、publishers_info=0、matched=0、heard=0），且先起 pub 在整个期间 matched 且发出 29 条。这不是"晚看到"，是**从未出现**。

### 3.1 慢发现的边界（不夸大）

- 25 s 排除的是"≤25 s 内会慢发现"；Fast DDS 的 lease/重试周期理论上可超过 25 s，本轮**只测到 25 s**。
- 仍是**单 boot**、每序 n=2。
- 因此表述为"25 s 内无慢发现"，**不**表述为"永远不会有"。

## 4. T0 端口观测：本轮已完整、对称、双时点

闸门改为**两侧** `endpoint_created` 均已 fsync（两例 `both_endpoints_exist=true`）；每例采**两时点**：双 endpoint 建立后（early）与后起方自身预算 85% 处（late，仍保证双活）。原文：`evidence/ports-{A,B}.json` 与 `.late.json`。

**两例、两时点完全一致：**

| 端口 | 类别（按已安装头文件） | 归属 |
|---|---|---|
| **7410** | metatraffic unicast（`d1`），participant **0** | 先起方 PID |
| **7411** | **user data**（`d3`），**同一** participant 0 | 先起方 PID |
| **7412** | metatraffic unicast（`d1`），participant **1** | 后起方 PID |
| **7413** | **user data**（`d3`），同一 participant 1 | 后起方 PID |
| 7400 | multicast metatraffic | **不存在** |

逐 PID：各 **2 个 socket / 11 个 inode**，绑定 `0.0.0.0`；**early 与 late 两时点 inode 不变**（如 A 的 91213/91219 与 91252/91255）。

**这是对第21轮缺口的关键修复**：第21轮只覆盖先起方（早 543 ms），本轮**两侧都覆盖且对称**。由此得到的边界必须说清楚：

- **两方都成功绑定**了各自 participant index 的完整预期端口集，**端口绑定层没有不对称**；
- 因此第 2 节的单向失败**不能**用"后起方没建发现 socket"解释——在 `/proc/net/udp` 层面两侧都健康；
- "无 7400"现在对**两方、两时点**都成立（仍只是 socket 层事实：未持有 multicast socket，不等于未通过 multicast 能力收发）。

**端口数据不参与 graph/matched 判读**；第 2 节结论只来自探针事件流。

## 5. T0 研究：rcl → rmw_fastrtps 交接点**已定位**

第21轮只能说明 `ROS_AUTOMATIC_DISCOVERY_RANGE` 在 `librcl.so` 而不在 `rmw_fastrtps_shared_cpp.so`。本轮找到实际接口。原文：`evidence/handoff-t0.txt`。

**接口是结构体而非环境变量**：`/opt/ros/jazzy/include/rmw/rmw/discovery_options.h` 定义
`rmw_automatic_discovery_range_t`（`LOCALHOST = 2` 等）与
`rmw_discovery_options_t { automatic_discovery_range; static_peers; static_peers_count; allocator; }`。

**符号级链路（全部取自已安装 `.so`）：**

| 组件 | 证据 |
|---|---|
| `librcl.so` | 导出 `rcl_get_automatic_discovery_range` / `rcl_get_localhost_only` / `rcl_get_discovery_static_peers`；**导入** `rmw_discovery_options_init` |
| `librmw.so` | 定义 `rmw_get_zero_initialized_discovery_options`、`rmw_discovery_options_{init,copy,fini,equal}` |
| `librmw_fastrtps_shared_cpp.so` | 导入上述助手，**并导出** `rmw_fastrtps_shared_cpp::create_participant(..., const rmw_discovery_options_s*, ...)` |
| `librmw_fastrtps_cpp.so` | 导入该 `create_participant` |

⇒ `ROS_AUTOMATIC_DISCOVERY_RANGE` 在 **rcl** 解析 → 生成 `rmw_discovery_options_t` → **以指针传入 Fast DDS participant 创建**。交接**点**由此成立，不是推测。

**仍未定位（不凭记忆补）**：① `create_participant` 如何把 `LOCALHOST` 变成 peer 列表/multicast 选择（本机无 Fast DDS 源码，本轮未反汇编）；② `LOCALHOST` 下 SPDP 是否仍用 multicast（端口公式已知，选择未知；"无 7400 socket"≠"无 multicast 流量"）；③ 通告是否单播确认；④ 本机 metatraffic 是否走 SHM。

## 6. 明确未成立

- **不是机制**："启动顺序"仍是区分变量，从"后起参与者"到"先起方始终不知其存在"的因果链未定位。
- **不能**说"后起方没发"：端口对称，本轮无法区分未发/未被听到/被听到但拒绝。
- **不是** UDPv4/SHM 结论（未测，`FASTDDS_BUILTIN_TRANSPORTS` 缺省且已记录）。
- **不是**发生率（每序 n=2、单 boot）；**不覆盖 >25 s** 的时间尺度。
- 不是工程恢复、不是项目节点结果。

## 7. 预算

| 项 | 值 | 上限 | 判定 |
|---|---:|---:|---|
| T1 次数 | **2**（A、B，均 valid） | 2 | 合规 |
| A span / B span | 12.649 s / **29.673 s** | 30 s | 合规（B 贴近上限但未触硬钳制） |
| 累计 T1 | **42.322 s** | 60 s | 合规 |
| participant | 各 2 | 2 | 合规 |
| 整轮 mono | **193.444 s = 3.224 min** | 45 min | 合规 |

无重跑。

## 8. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_mid_ns` | 11545524873936 |
| `end_wall_iso` | `2026-10-28T20:32:16.886235+08:00` |
| `pair_gap_ns` | 21830 |
| 整轮 mono | **193.444 s = 3.224 min** |

## 9. 首次封存与取回

```text
python3 -B scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-order-repeat-window-r1
```

stdout 原文（`/tmp/agc-w8-validation-r22-archive/archive-stdout.txt`，rc=0）：

```text
ok     w8-validation/20261028-order-repeat-window-r1 artifacts=54 verify=True files=55 mismatches=0

archived=1 skipped=0 error=0 retrieval_failed=0
```

| 核对项 | 实测 | 结果 |
|---|---|---|
| manifest artifacts | **54**，逐项 size/sha 重算 | 0 mismatch |
| tar 成员 / 真实根 | **55** / 唯一 `20261028-order-repeat-window-r1/` | 正确 |
| tar 独立重算 sha256 | `2669ec6d3b22cde0d16a4a64158cd8bf75d57506e27c9a1a58b207141d76266c` | 与 `.tar.sha256` 一致 |
| 逐文件相等 | `root_only=[]`、`tar_only=[]`、differing 0 | 55/55 |
| retrieval | `verified=true`、`files_checked=55`、`mismatches=[]` | 通过 |
| 独立解包取回 | 55 文件逐个哈希 | 0 mismatch，临时目录已删 |
| 归档权限 / 封存后源根 | tar `0444` / 源根 0 写入 | 通过 |

封存前基线：**43671/43671，drift 0**。

## 10. 离线守卫（T1=0）

`evidence/offline-tests-r22.json`：**8/8**。Q1 闸门要求**两侧** endpoint；Q2 early+late **两个时点都落盘**；Q3 双时点均扫描双 PID、**Q3b late 时点双活**；Q3c 归属能命中受控 socket；Q4 端口类别**从头文件重新推导**（7400 multicast / 7410 `d1` / 7411 `d3` 同一 participant；participant 1 应是 **7412**）；Q5 窗口长度被记录、transport 仍缺省。

**一条断言首轮失败，暴露了真实设计缺陷**：原先"回收前采样"会采不到活着的探针（1.5 s 余量让探针先自行退出）。现改为锚定在探针自身预算的 **85%**，由 Q3b 断言双活。这正是本轮两个端口时点得以成立的原因。

## 11. 实际改动（覆盖全部写操作）

**新根内新增**：`scripts/` 4 个、`evidence/` 8 个、`report/analysis.md`、`cases/{A,B}/` 全套原件，封存时 `config/evidence_manifest.json`；共 **54** 个产物。

**新根外**：本轮 `report.md`、`CURRENT.md`（待执行→执行中→待审查）、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 round22 勾选（各 4 / 5 项）、`experiments/_archive/w8-validation/20261028-order-repeat-window-r1.tar{,.sha256,.retrieval.json}`、`/tmp/agc-w8-validation-r22-*`。

**未改**：`src/`、项目 `scripts/`、`toolchain/`、`build/install`、spec/Runbook/request/历史 review、第20轮探针（sha 不变）与历史源根/归档；未 reset/clean/commit/push/切分支；全程 `python3 -B`，无 `__pycache__`。

## 12. 待裁定

1. **是否进入发现通告/locator 诊断**：按请求 §1，需"延长窗口仍复现单向且两序 n≥2"——本轮两条均已满足，**前置条件已达成**，故第23轮可考虑显式授权。
2. **端口对称这一结果如何使用**：它排除了"后起方未绑定发现端口"，把嫌疑进一步推向**通告发出/接收**而非端口创建。是否据此优先选择 locator 层（而非 Fast DDS 日志）作为下一步，请 Leader 裁定。
3. **>25 s 的时间尺度**是否需要在后续轮次覆盖（本轮只到 25 s）。
