# P1-4 · round-5 报告（最后基线对比）

<a id="p1-4-r5-report"></a>

- 任务 ID：`20261030-009-p1-4-vision`，round-5
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- 领取：2026-10-30T20:28:44+08:00；报告：2026-10-30T20:43+08:00
- 状态：**待审查（收口）**
- 父会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`
- 派工：[round-5 request](request.md#p1-4-r5-request)

<a id="p1-4-r5-summary"></a>
## 审查摘要（≤30 行）

1. **结论：FAIL**。计划出口第 4 项（换相机模型后飞行跟踪行为实测不变）**仍未闭环**。
2. **T-A（`gz_x500`）有效**：`TRACKING_SUCCESS` / `tracking_milestone`、ticks=407、
   visibility 0.9879、RTF 0.855、C9 两项 0、`/agc/task/start` 已调用（start 阶段 ok，10.659 s）。
3. **T-B（`gz_x500_mono_cam`）无效**：`demo_error`（整链就绪超时 180 s），未就绪项 `air_odom_fresh`；
   summary 为 `IDLE`、ticks=0 → 不构成对照。
4. **T-B 根因已定位到机制**：`air_lifecycle_prewarm` **未自行退出** → `RegisterEventHandler(OnProcessExit)`
   未触发 → `lifecycle_manager_air` **从未启动**（日志 0 行）→ 空中节点 inactive → `/agc/air/odom` 无发布者。
   证据：T-A 有 `prewarm done ok=True` + `lifecycle_manager_air` 20 行；T-B 两者皆无。**与机型无关**。
5. **两臂均缺派生跟踪误差**：summary **没有**跟踪误差字段（run_logger 不订阅任何空中话题）；
   我另起采集器实测 `/agc/air/ref` × `/agc/air/odom`，但 T-A 采集器被 run_demo 回收打断（写盘时机缺陷）、
   T-B 空中节点未激活（0 样本）。按预登记"不得自造"，记为 `NOT_COLLECTED`。
6. **预算**：T2 **2/2 用满**（T-A 68 s + T-B 191 s = **259 s / 900 s**），**0 重试**。
7. **纪律**：本轮**零仓库改动**（`find src docs scripts -newermt "20:28"` → 空）；预登记 sha256 未变；
   harness 只落 `/tmp`；未跑 vision；summary 全部从 `result.json` 读取（无 glob）。
8. **可用增量**：T-A 是一次**有效的默认机型 truth 基线**，可作后续对照的 A 臂基准。

<a id="p1-4-r5-arms"></a>
## 1. 两臂结果

| 项 | T-A（`gz_x500`） | T-B（`gz_x500_mono_cam`） |
|---|---|---|
| demo 目录 | `experiments/demo/20261030-203434` | `experiments/demo/20261030-203636` |
| summary | `…-203451-0966` | `…-203654-8031` |
| 机型确认 | `x500_0` / `simulation model: x500` | `x500_mono_cam_0` / `simulation model: x500_mono_cam` |
| `/agc/task/start` | **已调用**（10.659 s） | **未到该阶段** |
| 终态 | `TRACKING_SUCCESS` / `tracking_milestone` | **`IDLE`** |
| episode ticks | 407 | **0** |
| visibility_rate | 0.987928（497 拍） | null |
| sim 窗口 | 13.08 → 48.764（35.68 s） | 12.42 → 109.18（96.76 s，超时回收） |
| C9 | 0 / 0 | 0 / 0（IDLE 臂无意义） |
| rtf | 0.854963 | 0.601846 |
| collision_count | 1 | 1 |
| 派生跟踪误差 | **NOT_COLLECTED** | **NOT_COLLECTED**（0 样本） |
| 有效性 | **PASS（G1–G5）** | **FAIL（G1/G2）** |

详见 [`evidence/comparison.md`](../../../../experiments/p1-4/round-5/evidence/comparison.md)。

<a id="p1-4-r5-rootcause"></a>
## 2. T-B 根因（关键发现）

`w6.launch.py` 的空中 lifecycle 编排依赖**预热进程退出事件**：

```python
actions.append(RegisterEventHandler(OnProcessExit(
    target_action=prewarm, on_exit=[lifecycle_manager])))
```

| 证据 | T-A | T-B |
|---|---|---|
| prewarm 四节点 | 全 ok | 全 ok |
| prewarm 自行退出 | `done ok=True` | **无 `done`**；仅 SIGINT 后 `exit -9` |
| `lifecycle_manager_air` 日志行 | **20** | **0** |
| `/agc/air/odom` | 有 | 无 → 就绪门 180 s 超时 |

即 **prewarm 进程在 T-B 里挂住没退**，`OnProcessExit` 永不触发，空中节点停在 inactive。
`gz_x500_mono_cam` 只多一个 0.05 kg 相机，**不影响 DDS/lifecycle 服务发现**，故这是**启动期偶发竞态**，
不是换机导致的行为退化。

> **注意**：这条是 `w6.launch.py` 编排层的既有脆弱点（`OnProcessExit` 单事件依赖），
> 本轮授权**不允许改代码**，故只记录不修复。

<a id="p1-4-r5-error"></a>
## 3. 派生跟踪误差：为什么没拿到

1. **summary 里没有这个字段**（已核实）：`run_logger` 的 `create_subscription` 只有地面侧话题，
   41 个顶层键中无 track/err 类字段。
2. 我另写采集器（`/tmp`，未入库）订阅 `/agc/air/ref`（`MultiDOFJointTrajectory`）与
   `/agc/air/odom`（`Odometry`），按最近邻 ≤20 ms 配对算水平误差。
3. **T-A**：采集器 `timeout 60 … 45` 的窗长比 `run_demo` 的存活时间（≈55 s）长，
   被回收时的 SIGTERM 打断在 `spin_once` 中，**JSON 未写**（写盘在循环之后）。
4. **T-B**：空中节点未激活 → `/agc/air/ref` 从未发布 → `ref_samples=0`。
5. 按预登记 `tracking_error.policy`（**不得自造**），记为 `NOT_COLLECTED`，**不推断、不估算**。

**我的缺陷**：T-A 的采集器应先落盘再采样、窗长应短于 run 存活时间。这是 harness 设计失误。

<a id="p1-4-r5-budget"></a>
## 4. 预算

| 项 | 用量 / 授权 |
|---|---|
| T2 | **2 / 2 次**（上限用满）；**259 s / 900 s** |
| T-A | 68 s（成功） |
| T-B | 191 s（含 180 s 就绪超时，失败） |
| 重试 | **0** |
| T1 | 0 次 |
| 离线 | 约 6 次（prereg 校验、summary 解析、对比表、链接、指纹），均 ≤30 s |
| 仓库改动 | **0** |

<a id="p1-4-r5-conclusion"></a>
## 5. 结论

**FAIL —— 出口第 4 项未闭环**，原因是：

1. T-B 因**编排层偶发竞态**（prewarm 未退出）未能启动 episode，没有可比对照；
2. 两臂都缺跟踪误差指标，且 summary 本身不提供该字段。

**可用的真实增量**：T-A 提供了一次**有效的默认机型 truth 基线**（终态、窗口、可见率、RTF、C9 全齐），
可作为未来对照实验的 A 臂基准。

**建议**（供 Leader 裁定，我不自行执行）：

- **若要闭环出口第 4 项**，需新开明确授权任务，且至少解决两件事：
  ① 采集器写盘时机（先落盘/边采边写、窗长 < run 存活时间）——属 harness，不改仓库代码；
  ② T-B 的 prewarm 竞态：可在 `run_demo` 重试一次（同一授权内），或作为既有编排脆弱点单独记录。
- **若接受"基线对比未闭环"作为已知缺口**，则 P1-4 按 round-4 审查的结论收口即可。

## 6. 状态

- **待审查**；未 commit（派工单禁止）。

<a id="p1-4-r5-addendum"></a>
## 7. 追加自查（发通知前）

| 项 | 事实 |
|---|---|
| 仓库改动 | **仅** `docs/plan/p1-4-视觉算法接入.md`（授权允许的"计划勾选"）：7 项打勾 + 第 4 项加未闭环说明 + 新增 `<a id="p1-4-exit"></a>` 锚点；`git diff` 的删除行仅为那 8 个复选框，无其它内容删除 |
| 其它仓库文件 | `find src docs scripts -newermt "20:28"` → 只有上述 1 个文件 |
| 预登记 | sha256 `2a98ff90…cc2e` 未变；mtime 20:33:16 **早于** T-A 起 20:34:34 |
| harness | 只在 `/tmp/p1-4-r5-{arm.sh,track_err.py}`（过程性产物，不入库） |
| 残留 | `ps` 无 gz / px4 / MicroXRCE / 采集器 |
| 文档链接 | `tests/docs_link_check.py` → **活跃断链 0**（PASS） |
| 指纹 | `prereg-v1.json`=`2a98ff90…cc2e`、`evidence/index.json`=`093c46e9…ca41`、`p1-4 计划`=`db23e2f5…7897` |

### 两处 harness 缺陷（我的，已如实记录）

1. **T-A 采集器写盘时机**：JSON 写在采样循环**之后**，窗长 45 s 又长于 run 存活（≈55 s 但采集器起得早），
   被回收时 SIGTERM 打断 → 无输出。**改进方向**：边采边写 + 窗长 < run 存活时间（T-B 已改，但 T-B 因空中节点未激活仍是 0 样本）。
2. **T-B 的 `gz topic list` 就绪判断**：用 `/agc/air/odom` 出现即起采集器，但该臂空中节点从未激活，
   话题根本没出现 → 采集器空转到超时。

> 这两条都不影响 summary 级判据（那些来自 run_demo 自身产物），只影响派生误差指标。
