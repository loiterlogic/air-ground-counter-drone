<a id="round15-report"></a>
# 第15轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次15。

执行者：Worker（DSH 子会话 `55d8793e-4916-4045-ac19-5800e167ebfa`，父会话 `session-7bfaaed2-f329-4569-8dae-f795ccdba988`）。

## 0. 领取配对时钟（本轮第一个动作）

| 字段 | 值 |
|---|---|
| `claim_mono_before_ns` | `20746312169757` |
| `claim_wall_ns` | `1793167502495584285` |
| `claim_mono_after_ns` | `20746312170678` |
| `claim_pair_gap_ns` | `921` |

**口径**：唯一领取时钟依据；不用 mtime 反推。

## 1. 领取状态漏更新（如实披露，不假称此前已更新）

**事实**：本轮我在**未更新** `CURRENT.md` 的情况下就开始了实际核查。`CURRENT.md` 在本轮期间一直显示 `待执行 / 尚未领取`，直到本报告写完后才补正为 `执行中 → 待审查`。

**这不是"已领取但状态未刷新"的措辞问题，而是确实漏了领取步骤**：
- 按协议，Worker 应"核对基线、写入领取时间与执行者、把状态改 `执行中` 后才开工"。
- 我做了 claim 配对采样并写入本 report §0（这一步正确），基线 1927/1927 也核对了，但**跳过了 CURRENT 的领取状态写入**。
- 因此本轮存在一段"实际已开工但交接状态仍为待执行"的区间。该区间内**没有**任何其他 Worker 被派发该轮的证据，但我不能因此声称流程无瑕疵。

**补正方式**：按**原 claim**（mono `20746312169757` / wall `1793167502495584285`）补记执行者与领取时间，状态改为 `执行中` 再改 `待审查`；不追溯伪造时间戳。

## 2. 接单与基线

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT（实际状态，见 §1） | 轮次 `15`、`待执行` | 我在未更新状态下开工，已披露 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 基线 SHA | `b4258b1b1692ce70d62f2a725b071eb5eb4486a6d8489faf7cf373d8fb853024` | 与 receipt 一致 |
| 逐项复算 | **1927/1927**，missing 0、changed 0 | 通过 |
| `git status --porcelain` | 与 baseline `status` 逐行相同 | 通过 |

## 3. 本轮实际产出（全部为新根内容）

| 文件 | 说明 |
|---|---|
| `config/sources.md` | 版本/库 SHA/全部只读命令/两次失败网络尝试的 URL 与错误码/缺口声明 |
| `config/round15-facts.json` | 机器可读事实与候选裁定（含 6 条自我降级/更正） |
| `evidence/10-local-symbol-inspection.log` | `nm`/`strings`/`sha256sum` 原始输出 |
| `evidence/11-env-and-probe-facts.log` | 版本、第14轮五端 domain、隐藏 XML 检查、探针 API 调用数 |
| `report/analysis.md` | 机制事实、三候选、判读表、优先方向与理由 |

## 4. 核心结论（含对 Leader 指出的过度推断的核实与降级）

| 我此前的表述 | 处理 | 现表述 |
|---|---|---|
| graph 数据来自 `ros_discovery_info` | **降级** | 该字符串只在 `librmw_fastrtps_cpp.so` 出现（count=1），shared_cpp/rmw_dds_common 为 0；但**仅有符号/字符串不足以证明唯一来源**，`associate_*` 也可能由其它路径驱动 |
| typehash 会拒 graph | **降级为假设** | `parse_type_hash_from_user_data` 存在是事实；**本机无证据**表明 GraphCache 因 typehash 拒收 |
| domain 37 是"唯一成功" | **更正** | **ADR-0077 记录项目整链在 domain 0 下话题正常**，是更强反例；p3-r2 的 domain 37 成功例首例同样失败，非可靠阳性 |
| domain 37 仍失败可排除所有 domain 机制 | **更正** | 单点否证不能排除机制；且 domain 0 已在整链正常 |
| endpoint info API"无需修改即可观测" | **更正** | 当前探针 `get_publishers_info_by_topic`/`get_subscriptions_info_by_topic` 调用数 = **0**；采集它**需另轮授权修改/扩展探针** |
| C 因网络失败而"不可证伪" | **更正** | C 的 durability 标为**未知**；它可通过 DDS publication 统计或图缓存内省验证，**不是不可证伪**，只是本轮未做 |

### 已核实的机制事实
- graph 计数与 matched 计数走**不同实现入口**（`__rmw_count_publishers/__rmw_count_subscribers` + `rmw_dds_common::GraphCache` vs DDS matched 状态）。这是把"单向 graph"与"单向 matched"分开讨论的基础。
- 第14轮**五端**均 `ROS_DOMAIN_ID=0` + `LOCALHOST`；**无**隐藏 `DEFAULT_FASTRTPS_PROFILES.xml`。

### 候选裁定（最多 3，均未执行）
- **A（domain 换数字）：淘汰**。仅换数字，缺相对已关闭分支（第8轮 0/39）的新增区分证据；且 ADR-0077 显示 domain 0 话题正常。
- **B（endpoint info type/QoS 对照）：优先，但附前置**。可在一次 T1 内用已存在 rclpy API 干净排除类型层；**前置=需另轮授权改探针**。
- **C（`ros_discovery_info` durability/重发）：机制最贴合但本阶段条件未知**。需新工具/新探针，成本未定。

**优先方向 = B**，理由见 `analysis.md` §4：A 已淘汰；C 的关键参数本机未暴露且上游未取回，现在推进等于在未知条件上设计实验；B 是唯一能一次 T1 产出可判定结果的方向。

## 5. 未取回 / 明确缺口

- **上游 rmw_fastrtps 8.4.4 源码未取回**：两次尝试（`web_fetch` → `TypeError: fetch failed`；`curl --max-time 35` → 超时 35002 ms、HTTP 000、0 字节）。按 Leader 指令**停止重复尝试**，**不以记忆或邻近版本重造**。
- `ros_discovery_info` 的 durability/history：**未知**。
- `GraphCache` 在 typehash 不符时的行为：**未知**。
- 后启动方 graph=0 属"通告未送达"还是"缓存未接受"：**未知**，现有 rclpy API 无法区分。

## 6. 预算

| 口径 | 值 |
|---|---|
| T1 | **0/0**（派工为 0 次） |
| ROS / participant / 构建 / 仿真 / 抓包 | 全部 **0** |
| 新探针 / runner / 配置改动 | **无** |
| 网络尝试 | 2 次，均失败（已停止） |
| 整轮 mono | **544.724 s ≈ 9.08 min**（≪ 45 min），见 §8 |

## 7. 判读边界

- 本轮**未新增任何实测排除**；仅确认既有排除（第14轮门控条件）与"无隐藏 XML"。
- 不称"启动太早已整体排除"；不称 A 的同进程有效可外推到跨进程。
- 不承诺根因；候选执行需 Leader 另轮授权。
- S2/S3/S4 关闭；`gate=not_evaluable_as_specified`；headless 未授权；整链不归档。

## 8. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_ns` | `21291035946475` |
| `end_wall_ns` | `1793168056938923647` |
| 整轮 mono | **544.724 s ≈ 9.08 min** |
| wall | 555.194 s |

wall/mono 偏移变化如实记录，不假设原因、未改系统时钟。

## 9. 首次封存与取回实测值

首次封存，**未** `--force`；stdout 写 `/tmp/agc-w8-validation-r15-archive/archive.log`。

```
ok     w8-validation/20261028-discovery-mechanism-review-r1 artifacts=7 verify=True files=8 mismatches=0
archived=1 skipped=0 error=0 retrieval_failed=0
```

| 核对项 | 实测值 | 结果 |
|---|---|---|
| manifest artifacts | **7** | 逐个 size/SHA 复算，**0 mismatch** |
| tar 真实根 | `20261028-discovery-mechanism-review-r1/`（唯一） | 正确 |
| tar 成员数 | **8**（7 源文件 + manifest 自引用） | 差集为空 |
| `root_only` / `tar_only` | `[]` / `['config/evidence_manifest.json']` | 符合脚本设计 |
| tar SHA256 | `d3045dfa019c354c4f6015eb83ef186a559134c1980cf554ec48f6306e52205f` | 与 checksum 一致 |
| retrieval | `verified=true`、`files_checked=8`、`mismatches=0` | 通过 |
| tar vs 源根逐文件 | **0 处不一致** | 通过 |
| 封存后源根写入 | **无** | 合规 |
| 封存前基线复算 | **1927/1927**，status 逐行相同 | 通过 |
| `__pycache__` | 无（全程 `python3 -B`） | 合规 |

**过程偏离（如实）**：
1. **领取状态漏更新** —— 本轮在未把 CURRENT 改为"执行中"时即开始核查（§1），已按原 claim 补记并披露，不假称此前已更新。
2. **网络两次失败**（`net-01`/`net-02`，见 `config/sources.md` §3），上游源码未取回；按指令停止重试，**不以记忆重造**，缺口已逐项列出。
