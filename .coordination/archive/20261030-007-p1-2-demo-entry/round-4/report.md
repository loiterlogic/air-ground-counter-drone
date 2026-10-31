# P1-2 · round-4 报告（`--duration` 主动停分支闭环）

<a id="p1-2-r4-report"></a>

- 执行者：Worker（DSH 子会话，`deepseek-v4.1-flash`，`reasoningEffort=max`）
- Worker 子会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`（round-1 起沿用同一会话）
- 任务：`20261030-007-p1-2-demo-entry` / **round-4**（最后一次 duration 补证；批次 N=6，已用第 4 轮）
- 上游：[round-4 派工单](request.md#p1-2-r4-request)；[round-3 报告](../round-3/report.md#p1-2-r3-report)
- 起止：2026-10-30 17:29 → 17:35（+08:00）
- 状态：**待审查**

<a id="p1-2-r4-summary"></a>
## 审查摘要（≤30 行）

1. **唯一任务达成：`--duration` 主动停分支闭环**。一次 `./run_demo.sh --headless --duration 8`
   在 **`GROUND_APPROACH`** 到时停住，**五项判据全部符合派工单**：

   | 派工单判据 | 实测 | 结论 |
   |---|---|---|
   | follow 到时前没有任务终态 | `terminal_reached=false`，停在 `GROUND_APPROACH`（`t=8.004 s` 到时） | ✅ |
   | `exit_reason=duration_limit` | **`duration_limit`** | ✅ |
   | `duration_branch_taken=true` | **`true`**，且 `duration_not_reached_note` 为 `null` | ✅ |
   | 退出码 3 | **`exit_code=3`** | ✅ |
   | 进程组回收 confirmed、无残留 | `confirmed=true`，清 **33** 个，`members_after=[]`，`ps` 复核 **0** | ✅ |
   | summary 存在且保留 | `20261030-s04_static_static_obs_track-0-172926-7202`（`terminal_state=GROUND_APPROACH`、`latched=false`） | ✅ |
   | headless `viz:=false` 保持 | `viz:=false`，`rviz2`/`viz_markers` 各 **0** 个 | ✅ |

2. **主动停没有被包装成成功**（这是派工单点名要防的）：三处独立证据一致 ——
   `result.verdict=not_met`、`exit_code=3`、summary `terminal_state_latched=false`。
   summary 的 `terminal_state` 是 `GROUND_APPROACH` 而非 `TRACKING_SUCCESS`。

3. **零代码改动**：派工单写"若代码无需改动就只写证据和报告"。本轮**没有改任何代码**
   （`scripts/demo/**` 与 `w6.launch.py` 全部零改动），只落证据 + 写文档/报告。
   round-3 加的 `duration_branch_taken` 记账字段在本次真实运行中**首次得到字段级验证**
   （round-3 那个 run 生成于记账代码之前，当时无此字段）。

4. **纪律**：未重跑 GUI/headless 等价、未扩样本、未动 20% 容差；
   round-2 的 `preregistration/`（16:53）与 `equivalence/`（17:12）**时间戳未变**。
   `--duration 15` 那次（round-3）**不删除、不改写**，它作为"15 s 被 13.61 s 终态抢先"的有效判别结果保留。

5. 预算：**T2 1 次 / 150 s 上限，实际墙钟 58 s**；T1 **0 次**；离线检查 6 次、总墙钟 ≈10 s；
   构建 **0 次**。

6. **P1-2 出口判据至此 8 项 + `--duration` 主动停共 9 项全部有真实证据**（
   [plan 出口判据](../../../../docs/plan/p1-2-一键演示入口.md#p1-2-exit)已更新）。
   除"真实 Gazebo 截图"（Leader 已裁定不为 FAIL）外，无遗留未验证项。

<a id="p1-2-r4-baseline"></a>
## 1. 接单基线

| 项 | 值 |
|---|---|
| HEAD | `b627043423de25e61c9ed3fb0ec8f4dd39c44d18`（**未变**） |
| 分支 | `main` |
| 工作区 | 沿用 round-1..3 的既有改动；**未 reset / clean / commit** |
| 领取时间 | 2026-10-30 17:29（+08:00） |
| 开跑前残留 | 0 个本项目特征进程；`/dev/shm/fastrtps_*` 清理至 58 段 |
| 白名单核对 | 本轮只写 `experiments/p1-2/round-4/**`、`docs/plan/p1-2-一键演示入口.md`、本 round 目录——**代码零改动**，与"白名单同 round-3"一致 |

<a id="p1-2-r4-run"></a>
## 2. 唯一一次 T2：命令与结果

### 2.1 命令

```bash
cd /home/chen/AGC
setsid ./run_demo.sh --headless --duration 8
```

（`run_demo.sh` 内部 source ROS + install、设 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、
补 `GZ_SIM_SYSTEM_PLUGIN_PATH`；实际 launch 参数见 `result.json.launch_argv`）

### 2.2 终端输出（节选，全文见证据）

```text
[00:00] 启动仿真世界 ...................... OK (pgid 33126)
[00:30] PX4 己方实例 .................... OK (air odom 新鲜（错峰 25s）)
[00:30] 任务层就绪 ....................... OK (/agc/task/start 可用且 gt/cmd/odom 新鲜)
[00:40] 任务启动 ........................ OK (started: AIR_SEARCH [evid] …)
[00:40] 当前状态：AIR_SEARCH  目标距离 11.7 m
[00:40] 当前状态：TARGET_ACQUIRED  目标距离 11.9 m
[00:40] 当前状态：GROUND_APPROACH  目标距离 12.0 m
[00:48] 已到 --duration 8.0s，主动停止
[00:51] 回收进程组 33126（SIGINT → 轮询 → SIGKILL）
[00:58] 回收进程组 ....................... OK (已清理 33 个进程，剩余 0 个（6.6s）)
[00:58] 结果：experiments/w6-task-eval/20261030-s04_static_static_obs_track-0-172926-7202/metrics/summary.json
```

### 2.3 逐项核对（派工单 5 条 + 2 条附加）

| # | 判据 | 实测值 | 出处 |
|---|---|---|---|
| 1 | follow 阶段到时前**没有**任务终态 | `terminal_reached=false`、`terminal_state=GROUND_APPROACH`；`follow.wall_s=8.004`、`duration_limit_s='8'` | `result.json` |
| 2 | `exit_reason=duration_limit` | **`duration_limit`** | `result.json` |
| 2b | `duration_branch_taken=true` | **`true`**；`duration_not_reached_note=None`（无"未触达"备注） | `result.json` |
| 3 | 退出码 3 | **`3`** | `result.json.exit_code` |
| 4 | 进程组回收 confirmed、无残留 | `reap.confirmed=true`；`cleaned_count=33`；`members_after=[]`；`ps` 复核 **0** | `result.json` + `ps` |
| 5 | summary 存在且保留 | `experiments/w6-task-eval/20261030-…-0-172926-7202/metrics/summary.json`；`terminal_state=GROUND_APPROACH`、`terminal_reason_code=""`、`terminal_state_latched=false` | `summary.json`（已复制进证据） |
| 6 | 不包装成成功 | `result.verdict=**not_met**`；`exit_code=3`；summary `latched=false` | 三处一致 |
| 7 | headless `viz:=false` 保持 | `launch_argv` 含 `viz:=false`；`launch.log` 里 `rviz2` 启动数 **0**、`viz_markers` **0** | `result.json.evidence` |

### 2.4 状态时间线（`result.json.phase1_states`，相对 follow 起点）

```text
t=0.00   AIR_SEARCH        dist=11.723
t=0.09   TARGET_ACQUIRED   dist=11.901
t=0.19   GROUND_APPROACH   dist=11.954
t=8.004  —— 到时主动停（仍在 GROUND_APPROACH，未达终态）
```

与 round-3 的对照（**这就是选 8 s 的判别依据**）：

| round | `--duration` | 终态到达 | 分支 | 结果 |
|---|---|---|---|---|
| round-3 | 15 s | **13.61 s** → `TRACKING_SUCCESS` | 未触达 | `exit_reason=terminal`、`exit_code=0` |
| **round-4** | **8 s** | 未到终态 | **触达** | **`duration_limit`**、**`exit_code=3`** |

> round-3 的 15 s 结果不是失败，是"**有效判别**"——它给出"任务在 13.6 s 内完成"这一事实，
> 据此把时限压到 8 s 才一次命中。派工单的措辞（"不是同根因盲试"）与此一致。

<a id="p1-2-r4-changes"></a>
## 3. 实际改动（全部写操作）

| 文件 | 改动 | 性质 |
|---|---|---|
| `experiments/p1-2/round-4/evidence/t2-duration8.console.log` | 完整终端输出 | 证据 |
| `experiments/p1-2/round-4/evidence/t2-duration8.result.json` | 完整 `result.json`（含进程组成员清单） | 证据 |
| `experiments/p1-2/round-4/evidence/t2-duration8.slice.json` | 决定性切片（判据字段 + 状态时间线 + 回收摘要） | 证据 |
| `experiments/p1-2/round-4/evidence/t2-duration8.summary.json` | run_logger 的 `summary.json` 原件 | 证据 |
| `experiments/p1-2/round-4/evidence/t2-duration8.evidence.json` | 运行期证据（进程 / launch.log / 无 RViz） | 证据 |
| `docs/plan/p1-2-一键演示入口.md` | ① 把 round-3 那条"`--duration` 未验证（已知缺口）"**按事实更正**为已闭环并附实测表；② 出口判据新增 `--duration` 主动停一项；③ 出口判据页首补 `round-4/` 证据根与报告链接 | 补证说明 |
| `.coordination/.../round-4/report.md` | 本文件 | 交接 |

**代码零改动**：`scripts/demo/**`、`w6.launch.py`、`episode_runner.py`、`run_demo.sh` 均未修改
（`git status` 里这些路径的条目与 round-3 结束时一致）。

**未动**：round-2 的 `preregistration/` 与 `equivalence/`（时间戳 16:53 / 17:12 未变）、
round-3 的证据与报告、任何 `.cpp`、ABI、终态判据、安全阈值。

<a id="p1-2-r4-budget"></a>
## 4. 预算

| 项 | 预算 | 实际 |
|---|---|---|
| T2 attempt | **1** | **1** |
| T2 墙钟 | **150 s** | **58 s**（launch + ready 30.4 + start 10.2 + follow 8.0 + collect ~9） |
| T1 | **0** | **0** |
| 离线检查 | 总 ≤120 s / 单次 ≤30 s | **6 次 / ≈10 s**（读 result/summary、`ps` 复核、`docs_link_check` ×2、pytest ×1） |
| 构建 | — | **0**（代码零改动） |

<a id="p1-2-r4-notdone"></a>
## 5. 未执行 / 未达成

- **无未达成项**。本轮唯一任务（duration 主动停）已闭环。
- **未**重跑 GUI/headless 等价（派工单禁止）；**未**跑 GUI（禁止）；**未**扩种子（禁止）。
- 仍然**没有**真实 Gazebo 截图——属 Leader 已裁定的"不为 FAIL"事项，与轮次无关，此处只作提醒。

<a id="p1-2-r4-ledger"></a>
## 6. 假设台账与后续建议

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 `--duration 8` 能在 s04/yard 上于终态前到时 | **已排除（确认为真）** | 本轮已做 | — |
| H2 `duration_branch_taken` 记账在真实运行中正确落盘 | **已排除（确认为真）**：`true`，且无"未触达"备注 | 本轮已做（顺带验证） | — |
| H3 主动停的退出码 3 与"任务失败 2 / 成功 0"可区分 | **已排除（确认为真）**：`exit_code=3` | 本轮已做 | — |
| H4 到时主动停后进程组能干净回收 | **已排除（确认为真）**：33 清、0 残留 | 本轮已做 | — |

**后续建议**：
1. **P1-2 已具备验收条件**：9 项判据（8 项主体 + 主动停）均有真实证据，代码零遗留。
2. 若你要继续收口"真实 Gazebo 截图"，最小代价是给 `agc_world.sdf` 加 `<plugin filename="Screenshot">`
   并配 `--gui-config`——但那会动 `src/agc_sim/**`（**不在任何 P1-2 白名单**），须另派。
3. P1-3 可以发布；P1-3 的"状态面板"会天然复用本轮的 `result.json` / `progress.log` 结构。

<a id="p1-2-r4-appendix"></a>
## 7. 附：命令与退出码

| # | 命令 | 退出码 |
|---|---|---|
| 1 | `setsid ./run_demo.sh --headless --duration 8` | **3**（`duration_limit`，主动停） |
| 2 | `ps` 复核残留 | 0 个 |
| 3 | `python3 tests/docs_link_check.py` | 0（活跃断链 0） |
| 4 | `python3 -m pytest scripts/tests/ -q`（回归未被破坏；本轮零代码改动） | 0（136 passed） |
