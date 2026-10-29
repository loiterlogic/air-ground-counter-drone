<a id="round21-report"></a>
# 第21轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次21。

执行者：Worker 子会话 `47a2651c-e420-4218-b4c6-454837cd33fd`（复用，Leader 于2026-10-28派工）。

> 页头由Leader预置；正文由Worker按派工单追加。领取先写配对时钟并核对基线（43610项/SHA `aeabe5b2…`），再改CURRENT为执行中。

## 0. 领取配对时钟（本轮第一个动作）

**本轮第一次写入**，当时 CURRENT 仍为 `待执行`。原始件：`evidence/claim-clock.txt`。

| 字段 | 值 |
|---|---|
| `claim_mono_mid_ns` | **9958547223505** |
| `claim_wall_iso` | `2026-10-28T20:05:25.646051+08:00` |
| `pair_gap_ns` | 14735 |
| `/proc/uptime` | 9958.54 s |

同 boot 延续：第20轮领取 8357.61 s → 本轮 9958.54 s，`btime` 未变。

## 1. 接单基线与领取核对

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `21`、`待执行` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 受保护集（刷新后） | **43610/43610**，missing 0、不符 0 | **漂移 0** |
| `git status --porcelain` | 36 项，与 baseline 逐行相同 | 一致 |
| 探针 | 复用第20轮 `probe_r20.py`（sha `baaece49b198a8b27e9d058cc16dc4ff6113fca7b3a54b708acf56230795bd8c`），**未修改** | 合规 |

## 2. T1 两例：均 valid，形态随启动顺序翻转

| | **A（pub-first）** | **B（sub-first）** |
|---|---|---|
| 先起方 | publisher | **subscription** |
| 后起方 | subscription | **publisher** |
| **先起方** graph 对端 / endpoint info / matched | **1 / 1 / 1** | **1 / 1 / 1** |
| **先起方** heard | n/a（pub） | **0** |
| **后起方** graph 对端 / endpoint info / matched | **0 / 0 / 0** | **0 / 0 / 0** |
| **后起方** heard / sent | **0 heard** | 8 sent |
| 窗口（先/后） | 12.004 s / 8.002 s | 12.004 s / 8.002 s |
| 后起方窗口完全在先起方窗口内 | **是** | **是** |
| 分类 | `valid` / `valid` | `valid` / `valid` |

两例：`invalid=[]`；锚定 `used_deadline = anchor + budget + 1.5 s`、`clamped_by_hard_limit=false`；重叠均 **8.002 s**；四条事件流 `seq` 严格 1..N、单 PID；真实 RC **0/0**；SIGINT 回收；运行中 maps `captured`、`comm=python3`。原文重算见 `evidence/A-B-recount-raw.json`。

**判读：落在请求 §5 第 1 条——"A 复现单向且 B 翻转"。"后启动者看不到先启动者"规则成立。**

关键澄清：这**不是**角色方向规则（pub→sub 通、sub→pub 不通）。B 里先起的是 **sub**，它看得到 pub；后起的 **pub** 看不到 sub。不对称跟随的是**启动顺序**，不是 pub/sub 角色。

## 3. T0 发现端口观测（含我自己的采集缺陷）

原文：`evidence/ports-{A,B}.json`、汇总 `evidence/ports-summary.json`。

**两例观测一致**：

| 项 | 值 |
|---|---|
| 7399–7600 段 host-wide socket | **恰好 2 个**：`udp` **7410**、`udp` **7411**，绑定 `00000000` |
| 端口 7400（multicast） | **不存在** |
| udp6 段内 socket | 无（仅 323/45556/5353，无关） |
| 归属 PID | **先起方**（11 个 socket inode） |
| 后起方 PID | 快照时 **0 个 socket inode** |

### 3.1 缺陷（我自己的，如实披露）

采集闸门等的是**"两个进程都存在"**，而不是**"两个 endpoint 都已创建"**。快照因此在后起方 `endpoint_created` **之前 543.3 ms（A）/ 543.5 ms（B）** 拍下，后起方当时确实还没有 socket。

后果：

- 逐 PID 归属**只覆盖先起方**；
- "无 7400 multicast"只对先起方该时刻成立，**不能**外推为"本设置不用 multicast"；
- **不得**从端口数据得出任何方向性结论。第 2 节的单向结果建立在 graph/matched/heard 层，与这些端口无关。

已修复（闸门改为等后起方 fsync 的 `endpoint_created`，离线以 P2 断言），但**未重跑**——预算已用于两例有效结果，有效结果不得重跑。上述两条实测照原样保留。

## 4. 离线研究：Fast DDS 2.14.7 在 LOCALHOST 下的发现机制

以下事实**全部出自本机已安装文件**，非记忆。原始采集：`evidence/discovery-mechanism-local.txt`。

**版本**：`ros-jazzy-fastrtps 2.14.7-1noble`、`rmw-fastrtps-cpp 8.4.4`；
`libfastrtps.so.2.14.7` sha256 `2b80489f57d87ce4832766371c5e9f4b0c6b035dc850b284b9f6afcad4962929`。

**默认传输**（`BuiltinTransports.hpp`，逐字）：

```cpp
DEFAULT = 1,   //< Default value that will instantiate UDPv4 and SHM transports
UDPv4   = 4,   //< Instantiate UDPv4 transport only
```

→ 未设 `FASTDDS_BUILTIN_TRANSPORTS` 时，**UDPv4 与 SHM 同时存在**，第19/20轮的"默认传输"并非单一传输。

**发现端口是 domain/participant 的纯函数**（`PortParameters.h`，逐字）：

```cpp
getMulticastPort: 7400 + 250*domainId + 0
getUnicastPort  : 7400 + 250*domainId + 10 + 2*participantId
defaults: portBase=7400, domainIDGain=250, participantIDGain=2,
          offsetd0=0, offsetd1=10, offsetd2=1, offsetd3=11
```

对 **domain 0 / participant 0**：multicast **7400**、metatraffic unicast **7410**；**7411** 是**同一个 participant** 的用户数据端口（`+offsetd3`），**不是第二个参与者**。这与实测 `{7410, 7411}` 同属一个 PID 精确吻合——也反证观测器读到的是真实 DDS socket。

**LOCALHOST 在哪一层解释**：`librcl.so` 含 `RMW_AUTOMATIC_DISCOVERY_RANGE_{LOCALHOST,SUBNET,SYSTEM_DEFAULT,OFF}`、`rcl_get_automatic_discovery_range`、`rcl_get_localhost_only`、`rcl_get_discovery_static_peers`，以及 `"./src/rcl/localhost.c"`；而 **`rmw_fastrtps_shared_cpp.so` 完全不含 `ROS_AUTOMATIC_DISCOVERY_RANGE` 字符串**。

→ 支持：LOCALHOST 作用域在 **rcl 层**解析后交给 RMW，未在 Fast DDS 传输层被重新解释。
→ **不支持**：LOCALHOST 如何被翻译成 peer 列表或 multicast/unicast 选择，本静态证据无法确定；且 `rmw_fastrtps*` 均**未**对 `rcl_get_*` 出现 undefined 引用，**交接点未定位**。

**明确未知（不臆造）**：① LOCALHOST 下 SPDP 仍走 multicast 还是改单播 peer 列表（头文件只证明端口公式，不证明选择）；② 通告是否为单播确认（SEDP 走可靠 builtin endpoint，其确认行为本轮未验证）；③ 后起参与者为何不被先起方得知——本轮只把变量收窄到"启动顺序"，未到机制；④ 本机 metatraffic 是否用 SHM（7400 段 UDP socket 存在说明 UDP metatraffic socket 被创建，但 SHM 段内容不可读，未观测）。

## 5. 明确未成立

- **不是机制**。"启动顺序"是本轮找到的**区分变量**，后起方的通告为何到不了先起方仍未定位。
- **不能**断定"通告没发出"：本轮无法区分"未发/未被听到/被听到但拒绝"。
- **不是** UDPv4/SHM 结论（未测）。
- **不是**发生率：一序一例、同 boot。
- 不是工程恢复、不是 domain/系统结论、不是项目节点结果。

## 6. 预算

| 项 | 值 | 上限 | 判定 |
|---|---:|---:|---|
| T1 次数 | **2**（A、B，均 valid） | 2 | 合规 |
| A span / B span | 12.685 s / 12.682 s | 30 s | 合规 |
| 累计 T1 | **25.367 s** | 60 s | 合规 |
| participant | 各 2 | 2 | 合规 |
| 整轮 mono | **382.448 s = 6.374 min** | 45 min | 合规 |

无重跑。

## 7. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_mid_ns` | 10340994951011 |
| `end_wall_iso` | `2026-10-28T20:11:54.685468+08:00` |
| `pair_gap_ns` | 31826 |
| 整轮 mono | **382.448 s = 6.374 min** |

## 8. 首次封存与取回

```text
python3 -B scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-one-way-discovery-recheck-r1
```

stdout 原文（`/tmp/agc-w8-validation-r21-archive/archive-stdout.txt`，rc=0）：

```text
ok     w8-validation/20261028-one-way-discovery-recheck-r1 artifacts=54 verify=True files=55 mismatches=0

archived=1 skipped=0 error=0 retrieval_failed=0
```

| 核对项 | 实测 | 结果 |
|---|---|---|
| manifest artifacts | **54**，逐项 size/sha 重算 | 0 mismatch |
| tar 成员 / 真实根 | **55** / 唯一 `20261028-one-way-discovery-recheck-r1/` | 正确 |
| tar 独立重算 sha256 | `419a01cbb8c1a0bf39604e3bd65311820d3d76a3c05882e23d903df0c48e5fbe` | 与 `.tar.sha256` 一致 |
| 逐文件相等 | `root_only=[]`、`tar_only=[]`、differing 0 | 55/55 |
| retrieval | `verified=true`、`files_checked=55`、`mismatches=[]` | 通过 |
| 独立解包取回 | 55 文件逐个哈希 | 0 mismatch，临时目录已删 |
| 归档权限 / 封存后源根 | tar `0444` / 源根 0 写入 | 通过 |

封存前基线：**43610/43610，drift 0**。

## 9. 离线守卫（T1=0）

`evidence/offline-tests-r21.json`：**9/9**。P1 观测器能把真实 socket 归属到正确 PID、且**不**给没有 socket 的 PID 编造条目；P2 闸门等后起方 endpoint 且其后仍扫描该 PID；P3 端口公式**从已安装头文件重新推导**并证明 `{7410,7411}` 属**同一** participant；P3b `BuiltinTransports::DEFAULT` 确为 UDPv4+SHM；P4 启动顺序接线正确。

**其中 2 条断言我最初写错了**（把 7411 误当第二个 participant；要求不建 socket 的 fake 也必须非零 inode）。两处均已改正并保留在此，未静默删除。

## 10. 实际改动（覆盖全部写操作）

**新根内新增**：`scripts/` 4 个、`evidence/` 8 个、`report/analysis.md`、`cases/{A,B}/` 全套原件，封存时 `config/evidence_manifest.json`；共 **54** 个产物。

**新根外**：本轮 `report.md`、`CURRENT.md`（待执行→执行中→待审查）、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的 round21 勾选（各 4 / 5 项）、`experiments/_archive/w8-validation/20261028-one-way-discovery-recheck-r1.tar{,.sha256,.retrieval.json}`、`/tmp/agc-w8-validation-r21-*`。

**未改**：`src/`、项目 `scripts/`、`toolchain/`、`build/install`、spec/Runbook/request/历史 review、第20轮探针（sha 不变）与源根、历史归档；未 reset/clean/commit/push/切分支；全程 `python3 -B`，无 `__pycache__`。

## 11. 待裁定

1. **下一轮分支**：按"后启动者看不到先启动者"，是进**发现通告/locator**分支，还是先做**同序重复以估发生率**（当前每个顺序各 1 例）。
2. **端口观测是否重做**：本轮闸门缺陷使后起方端口未知；若 Leader 认为必要时可在下轮以"等两个 endpoint"的闸门重采（已修复并离线验证，未真实跑过）。
3. **`7411` 语义**已由头文件确定（同一 participant 的 user 端口），下一轮若依赖端口判读应以此为准，不要再按"两个 participant"解读。
