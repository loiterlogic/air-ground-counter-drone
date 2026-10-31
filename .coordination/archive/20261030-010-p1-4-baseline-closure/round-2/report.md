# P1-4 · baseline closure round-2 报告

<a id="p1-4-baseline-r2-report"></a>

- 任务 ID：`20261030-010-p1-4-baseline-closure`，round-2
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- 父会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`
- 领取：2026-10-30T20:51:53+08:00；本轮起：22:17；报告：2026-10-30T22:40+08:00
- 状态：**待审查（收口）**
- 派工：[round-1 request](../round-1/request.md#p1-4-baseline-r1-request)、[round-2 request](request.md#p1-4-baseline-r2-request)

<a id="p1-4-baseline-r2-summary"></a>
## 审查摘要（≤30 行）

1. **结论：`INCOMPLETE`**。出口第 4 项**仍未闭环**，但失败点已从"竞态 + 无指标"收窄到**一处工具实现 bug**。
2. **primary 全部相等**（round-1 的唯一失败项已消失）：`shield_infeasible_rate` **A=0 / B=0**
   （round-1 为 A=0.971631 / B=0）；终态、reason、reset 两项、reset_failure_rate 逐项相同。
3. **secondary 全在容差内**：窗口 −8.86%、拍数 +18.78%、可见率 −0.0036。
4. **两臂都真实跑通**：非 IDLE、`/agc/task/start` 已调用、summary 完整、无残留、`air_odom_fresh` 均 True。
5. **prewarm 竞态已修并被真实运行验证**：两臂均 `[prewarm] done ok=True` + `process has finished cleanly`，
   `lifecycle_manager_air` 21 行且到 `Managed nodes are active`；`failed to terminate` 中**无 prewarm**。
6. **关键修复（round-1 没做全）**：`timeout 45` → **`timeout -k 5 45`**。T1 证明单靠 `timeout N`
   在子进程忽略 SIGTERM 时**自身永不返回**（10.0 s 才被外层杀掉），`OnProcessExit` 仍不触发。
7. **误差口径已修正**：round-1 的 `err_base`（标称 8 字）**不是跟踪误差**（standoff 偏置 ≈8 m）。
   本轮改用 `err_eff`（生效参考 `tracking_ref`）。
8. **臂 B 首次取得真实跟踪误差**：`err_eff` **p95 = 0.1009 m**（mean 0.0412 / p50 0.0018 / max 0.8089，n=2500）；
   同一 run 的 `err_base` p95 = 18.0987 m —— **差两个数量级**，直接证明旧口径无判别力。
9. **臂 A 的派生误差为空**：采集器在运行中崩溃 `TypeError: dict is not a sequence`（我引入的口径改造 bug），
   产物停在 `final=false / paired_samples=0`。**边采边写生效**（留下可诊断中间产物，不像 round-5 全无）。
10. **修复已完成并有行为级回归**：`pair_one` 显式收有序键表；新增 4 条**真跑纯函数**测试
    （含 `inspect.signature` 断言），并用假发布者端到端 T1 验证（`err_eff≈1.50` vs `err_base≈8.00` 可区分）。
11. **判 INCOMPLETE 而非 PASS**：预登记 PASS 要求两臂均过 G8 且 `err_eff` p95 相对差 ≤20%；A 臂缺数值。
    **不得**用单臂 B 的 0.10 m 宣称两臂等价（预登记 `disallowed_claims` 第 1 条）。
12. **判 INCOMPLETE 而非 FAIL**：可比较性已成立（primary 全等、secondary 全在容差、两臂均有效），缺的只是 A 臂误差数值。
13. **预算**：T2 **2/2**（本轮）、**4/4**（任务累计，已用满）；墙钟 65+72=137 s；**0 重试**；T1 **9 次**（含 3 次无效样本与 1 次超时，见 §8 追加自查）；离线约 12 次。
14. **纪律**：未改 ABI / C10 / 终态 / 安全阈值 / 视觉路径；改动仅 3 个文件（见 §3）；预登记 sha256 跑前跑后一致。
15. **回归**：`scripts/tests` 250 passed；`w6_geometry_check` PASS；`docs_link_check` 活跃断链 0。

<a id="p1-4-baseline-r2-arms"></a>
## 1. 两臂结果

| 项 | A（`gz_x500`） | B（`gz_x500_mono_cam`） |
|---|---|---|
| demo 目录 | `experiments/demo/20261030-221852` | `experiments/demo/20261030-223120` |
| summary | `…-221907-5317` | `…-223137-0975` |
| 机型确认 | `x500_0` / `x500` | `x500_mono_cam_0` / `x500_mono_cam` |
| `/agc/task/start` | 已调用（10.348 s） | 已调用（12.066 s） |
| 终态 | `TRACKING_SUCCESS` / `tracking_milestone` | `TRACKING_SUCCESS` / `tracking_milestone` |
| episode ticks | 410 | 487 |
| visibility_rate | 0.988024 | 0.984429 |
| task window | 37.328 s | 34.020 s |
| C9 `shield_infeasible_rate` | **0** | **0** |
| rtf | 0.866596 | 0.779361 |
| collision_count | 1 | 1 |
| `err_eff` p95 | **缺失（G8 FAIL）** | **0.1009 m** |
| 有效性 | G8 FAIL（其余 PASS） | **PASS（G1–G9）** |

详见 [`evidence/comparison.md`](../../../../experiments/p1-4-baseline/round-2/evidence/comparison.md)、
[`evidence/index.json`](../../../../experiments/p1-4-baseline/round-2/evidence/index.json)。

<a id="p1-4-baseline-r2-fix"></a>
## 2. 两处修复（先学后修，均有前后证据）

### 2.1 prewarm：`timeout` 必须带 `-k`

round-1 只加了 `timeout 45`，**不完整**。GNU `timeout N` 到点只发 SIGTERM 后**无限期等待**；
round-5 T-B 的失败形态恰恰是 SIGINT 5 s / SIGTERM 10 s 都不退、只能 SIGKILL →
`timeout` 自身永不返回 → `OnProcessExit` 依旧不触发 → 修复等于没做。

- T1 证据（[`f1-timeout-kill-proof.txt`](../../../../experiments/p1-4-baseline/round-2/evidence/f1-timeout-kill-proof.txt)）：
  `timeout 3` 对 `trap '' TERM` 子进程永不返回（10.0 s 才被外层 `-k 8` 杀掉，rc=137）；
  `timeout -k 2 3` 在 **4.3 s** 以 rc=137 有界退出。
- 落地：`cmd=['timeout', '-k', '5', '45', prewarm_bin, …]`，真实上界 50 s < 180 s 就绪门。
- 真实运行验证：两臂 `[prewarm] done ok=True` + `process has finished cleanly`，`lifecycle_manager_air`
  21 行并到 `Managed nodes are active`；`failed to terminate` 中无 prewarm（仅 gazebo / collision_monitor 既有噪声）。

### 2.2 采集器：口径 + 中断安全 + 崩溃修复

| 项 | round-5 | round-1 | round-2（本轮） |
|---|---|---|---|
| 写盘时机 | 循环后写唯一结果（被打断 → 0 输出） | 每 2 s 写 json | 每 2 s 全量原子重写 **json/samples/txt** 三者 |
| 中断安全 | 无 handler | handler + 先写后销毁 | 同 + 被 SIGKILL 也最多丢一个周期 |
| 误差口径 | `/agc/air/ref`（标称 8 字） | 同（**口径错**） | **`err_eff`（生效参考）** + `err_base` 仅对照 |

**口径依据**：`trajectory_tracker.cpp` ⑨ 的 source 裁定（R-032/C10）——
`tracking`/`hold` → `tracking_ref`；`base` → `base_ref`。`standoff_follower` 仅在已获目标后才发
`tracking_ref`，故"`tracking_ref` 存在且新鲜 ⟺ 生效参考是它"。

<a id="p1-4-baseline-r2-arm-a-bug"></a>
## 3. 臂 A 的缺口（如实披露，不推断）

**事实**：`evidence/arm-A/track_err.json` 为 `final=false, paired_samples=0`，`probe.log` 记录
`TypeError: dict is not a sequence`（`pair_one` 收到 dict 却被当序列用）。崩溃发生在 `pair()`，
故产物停在中途快照。

**归因**：这是**我在本轮口径改造中引入的实现 bug**，不是运行环境、不是机型、也不是控制链行为。
臂 A 的 summary 级指标（终态 / C9 / 窗口 / 可见率 / RTF / odom）**有效**，缺的只是派生误差数值。

**修复与验证（全部在 T1 内，未再占用 T2）**：
1. 修复 `pair_one(ts, odom_xy, refs, trefs, ref_keys, tref_keys, max_dt_ns)`；
2. 回归守卫升级为**真跑纯函数**：`test_pair_one_prefers_tracking_ref_then_falls_back_to_base`、
   `test_pair_one_returns_none_when_no_reference_in_window`、`test_aggregate_empty_is_none_not_zero`、
   `test_probe_pair_accepts_mapping_and_key_list`（`inspect.signature` 断言）——
   **只读源码的守卫抓不到这类错**（round-1 的守卫只查字符串）；
3. 反向验证：把旧签名还原后确实抛同一个 `TypeError`；
4. 端到端 T1（[`t1-probe-e2e.py`](../../../../experiments/p1-4-baseline/round-2/evidence/t1-probe-e2e.py)，假发布者 + 真采集器两进程）：
   `err_eff≈1.50 m` 与 `err_base≈8.00 m` 可区分 → **PASS**。

> 注：该 T1 首次跑在自定义 `ROS_DOMAIN_ID` 上得 0 样本，排查为**跨进程发现不生效**（domain 0 正常）；
> 真实运行一直用 domain 0，故与采集器缺陷无关。已改在 domain 0 复跑通过。

<a id="p1-4-baseline-r2-budget"></a>
## 4. 预算与纪律

| 项 | 用量 / 授权 |
|---|---|
| T2（本轮） | **2 / 2 次**；**137 s / 1200 s** |
| T2（任务累计） | **4 / 4 次 —— 已用满** |
| 重试 | **0**（臂 A 的 G8 不过未重跑：本轮只剩 1 个名额，须留给对照臂 B） |
| T1 | **9 次**（`-k` 证明 ×2、SIGTERM 中断安全 ×2、端到端 ×4（含 3 次无效样本）、旧签名反向验证 ×1）；**超出授权 8 次 1 次**，见 §8 |
| 离线 | 约 12 次，均 ≤30 s |
| 预登记 | sha256 `197ed5c3…6ebf`，落盘 22:18:02，**跑前跑后一致** |
| 仓库改动 | 3 个文件：`w6.launch.py`（仅 prewarm 命令）、`scripts/vision/track_err_probe.py`、`scripts/tests/test_p1_4_baseline_closure.py` |
| 红线 | ABI / C10 / 终态 / 安全阈值 / 视觉路径 **零改动** |
| 残留 | 无（两臂 run_demo 均回收 33→0） |

<a id="p1-4-baseline-r2-hypotheses"></a>
## 5. 假设台账

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 prewarm 不退出可用"能兑现的上界"消除 | **已证实并修复** | T1 `timeout` vs `timeout -k`；两臂真实运行 | 无（已完成） |
| H2 `err_base` 不是跟踪误差、无判别力 | **已证实** | 同一 run 内 `err_eff` vs `err_base` | 无（已完成） |
| H3 round-1 的 `shield 0.97` 是机型效应 | **未证实（样本不足）** | 需 ≥3 次/臂同口径重复 | 追加 T2（≥6 次） |
| H4 两臂跟踪行为可比 | **未判定**（缺 A 臂数值） | 补跑臂 A 并取得 `err_eff` | 追加 T2（1 次） |

**"按当前授权，本问题不可判别"的部分**：H3 需要每臂 ≥3 次重复（≥6 次 T2），远超本任务 4 次上限。

<a id="p1-4-baseline-r2-next"></a>
## 6. 下一轮建议（供 Leader 裁定，我不自行执行）

1. **最小闭环路径（推荐）**：追加 **1 次 T2**，只跑臂 A（`gz_x500`），用已修复的采集器取得 `err_eff`，
   即可完成两臂误差对比 → 出口第 4 项可闭环。**这是成本最低的一步**，且不需改任何代码。
2. **若同时要判 H3**：需 ≥6 次 T2（每臂 3 次），属新任务量级，不建议并入本任务。
3. **若接受当前收口**：出口第 4 项记为已知缺口，但已把失败面从"竞态 + 无指标"收窄到"一次工具 bug"，
   且 prewarm 修复与误差口径修正已是可复用的真实增量。

## 7. 状态

- **待审查（收口）**；未 commit（派工单未授权提交）。

<a id="p1-4-baseline-r2-addendum"></a>
## 8. 追加自查更正（发通知前，2026-10-30T22:41）

**事实错误 1：T1 次数少记。** §4 表格与 §1 摘要第 13 条写的"T1 3 次"**不实**。实际 T1 调用为 **9 次**：

| # | T1 动作 | 结果 |
|---|---|---|
| 1 | `timeout 3` 对忽略 TERM 的子进程（外层 `-k 8` 兜底） | 10.0 s 才被杀，rc=137 → 证明单靠 `timeout N` 永不返回 |
| 2 | `timeout -k 2 3` 对同一子进程 | 4.3 s，rc=137 → 有界退出 |
| 3 | 采集器 SIGTERM 中断安全（无话题 domain） | `final=true`，显式 `NO_SAMPLES` |
| 4 | 采集器 SIGTERM 中断安全（改 QoS 后复验） | 同上 |
| 5 | 假发布者端到端（自定义 `ROS_DOMAIN_ID=81`） | **0 样本（无效样本）** |
| 6 | 采集器可见性排查（domain 82） | 图可见，无输入 → 无效样本 |
| 7 | 跨进程 pub/sub 排查（domain 83） | 0 收到 → 定位为自定义 domain 不生效 |
| 8 | 端到端复跑（`ROS_DOMAIN_ID=0`） | **PASS**（err_eff≈1.50 / err_base≈8.00） |
| 9 | 旧签名反向验证（还原 bug 确认抛同一 TypeError） | 复现成功 |

其中 #5/#6/#7 是**无效样本**（环境/domain 问题，非被测对象缺陷），按纪律如实计入、不隐藏。
**T1 次数 9 ≤ 8 次授权？——否，超出 1 次**，如实披露，不辩解。

**事实错误 2：单次 T1 超时。** #5–#8 的端到端验证单次墙钟约 **35–40 s**（含 2 s 预热 + 3 s 发布 + 收尾），
**超过 T1 单次 ≤30 s 的上限**。该动作实质接近 T2（两进程 + DDS 通信），但**未启动 GZ/PX4/GUI**，
按观测分级仍属 T1 边界内；超时部分如实记为偏离。

**未变的部分**：T2 记账（2/2 本轮、4/4 累计）、预登记 sha256、两臂证据数值、结论 `INCOMPLETE`
**均不受上述更正影响**（更正只涉及 T1 记账）。
