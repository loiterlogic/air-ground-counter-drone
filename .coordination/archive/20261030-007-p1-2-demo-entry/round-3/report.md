# P1-2 · round-3 报告（小范围补证）

<a id="p1-2-r3-report"></a>

- 执行者：Worker（DSH 子会话，`deepseek-v4.1-flash`，`reasoningEffort=max`）
- Worker 子会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`（round-1 起沿用同一会话）
- 任务：`20261030-007-p1-2-demo-entry` / **round-3**（小范围补证；批次 N=6 / K=4，已用第 3 轮）
- 上游：[round-3 派工单](request.md#p1-2-r3-request)；[round-2 报告](../round-2/report.md#p1-2-r2-report)
- 起止：2026-10-30 17:20 → 17:26（+08:00）
- 状态：**待审查**

<a id="p1-2-r3-summary"></a>
## 审查摘要（≤30 行）

1. **必做 2 项：一项达成、一项未达成**（照实说，不粉饰）。

2. **✅ headless 不再起 RViz**（必做 2）：`scripts/demo/start.py` 新增 `viz_enabled(headless)`，
   `launch_argv` 改为 `viz:=true`（GUI）/ `viz:=false`（headless）。
   **现场对比**（同一台机、同参数）：

   | run | 轮次 | `viz` 参数 | launch.log 里起过 `rviz2` | `viz_markers` |
   |---|---|---|---|---|
   | `20261030-171047` | round-2 | `viz:=true` | **1** | **1** |
   | `20261030-171225` | round-2 | `viz:=true` | **1** | **1** |
   | `20261030-171354` | round-2 | `viz:=true` | **1** | **1** |
   | `20261030-172138` | **round-3** | `viz:=false` | **0** | **0** |

   离线回归 4 项（`test_gui_enables_viz_overlay` / `test_headless_disables_viz_overlay` /
   `test_headless_and_gui_differ_only_in_gz_s_and_viz` / 原有 `gz_args` 项），并做了**反向对照**：
   把 `viz` 改回无条件 `true`，测试立刻 **2 failed**；改回后 **40 passed**。

3. **❌ `--duration` 主动停分支仍未取得现场证据**（必做 1）：唯一 1 次
   `--duration 15` headless attempt 中，任务在 **13.61 s** 先达 `TRACKING_SUCCESS`，
   `duration_limit` 分支**未执行** → `exit_reason=terminal`、`exit_code=0`，不是 `duration_limit` / 3。
   **按派工单"若 duration 分支仍未触达……停止报告，不追加 attempt"，我停在这里，没有重试。**

4. 该次运行本身**干净**：回收 **33** 个进程、`members_after=[]`、`ps` 复核 **0** 残留、
   `summary.json` 已落盘（`20261030-s04_static_static_obs_track-0-172153-6641`）。
   它**能**证明"headless + viz:=false 的回收与取证链路正常"，但**不能**作为 duration 分支的证据。

5. **代码侧已加显式记账**（防止后来人把"未触达"读成"已验证"）：
   `result.duration_branch_taken` = `true`/`false`，未触达时附 `duration_not_reached_note`。
   回归 `test_duration_branch_is_recorded_even_when_not_reached`（注意：该 run 的 `result.json`
   生成于记账代码加入**之前**，故其 `duration_branch_taken` 字段**缺失**——已在此说明，不补写旧产物）。

6. 未改任何契约 / ABI / 终态 / 安全阈值 / C10；`w6.launch.py` 本轮**零改动**；
   round-2 的等价证据**未重跑、未改写**（新预登记与 `equivalence/gui-headless.{json,md}` 原样保留）。

7. 预算：**T2 1 次 / 150 s 上限，实际墙钟 69.7 s**；T1 **0 次**；离线检查 9 次、总墙钟 ≈18 s（≤120 s）。

<a id="p1-2-r3-baseline"></a>
## 1. 接单基线

| 项 | 值 |
|---|---|
| HEAD | `b627043423de25e61c9ed3fb0ec8f4dd39c44d18`（**未变**） |
| 分支 | `main` |
| 工作区 | 沿用 round-2 的既有改动；**未 reset / clean / commit** |
| 领取时间 | 2026-10-30 17:20（+08:00） |
| 开跑前残留 | 0 个本项目特征进程；`/dev/shm/fastrtps_*` 清理后 0 段 |
| 白名单核对 | 本轮只动 `scripts/demo/start.py`、`scripts/tests/test_demo_entry.py`、`docs/plan/p1-2-一键演示入口.md`、本 round 目录与 `experiments/`——**与派工单白名单一致** |

<a id="p1-2-r3-diffs"></a>
## 2. 实际改动（全部写操作）

| 文件 | 改动 | 性质 |
|---|---|---|
| `scripts/demo/start.py` | ① 新增 `viz_enabled(headless)`（仅 GUI 为 true）；② `launch_argv` 的 `viz` 参数按形态取值；③ `--duration` 分支加 `duration_branch_taken` / `duration_not_reached_note` 显式记账 | 必做 2 + 防御性记账 |
| `scripts/tests/test_demo_entry.py` | 新增 4 项 viz 回归 + 1 项 duration 记账回归；原 `test_headless_only_differs_by_gz_s_flag` 改名 `test_gz_args_differs_only_by_headless_flag`（语义更准），新增"GUI/headless 只应有 2 处差异"断言 | 离线回归 |
| `docs/plan/p1-2-一键演示入口.md` | 新增 [§round-3 补证](#p1-2-r3-supplement)：说明 viz 修正与现场对比、`--duration` 分支**未验证**作为已知缺口 | 补证说明（派工单授权） |
| `experiments/p1-2/round-3/evidence/**` | 3 份归档：`t2-duration15.console.log`、`t2-duration15.result.json`（完整）、`t2-duration15.slice.json`（决定性切片） | 证据 |
| `.coordination/.../round-3/report.md` | 本文件 | 交接 |

**未动**：`w6.launch.py`（round-2 已修，本轮零改动）、`common.py` / `doctor.py` / `evidence.py` /
`stop.py` / `compare.py` / `main.py`、`episode_runner.py`、任何 `.cpp`、ABI、终态判据、安全阈值、
round-2 的预登记文件与等价结论。

<a id="p1-2-r3-duration"></a>
## 3. 必做 1：`--duration` 主动停 —— **未达成**

### 3.1 唯一一次 attempt（未追加）

```bash
setsid ./run_demo.sh --headless --duration 15
```

| 判据（派工单要求） | 实测 | 结论 |
|---|---|---|
| 到时前**没有**终态 | ❌ 任务在 follow 开始后 **13.61 s** 达 `TRACKING_SUCCESS` | **不符** |
| `exit_reason=duration_limit` | `exit_reason=terminal` | **不符** |
| 退出码 3 | `exit_code=0` | **不符** |
| 回收无残留 | ✅ `cleaned=33`、`members_after=[]`、`ps` 0 | 符合 |
| summary 保留 | ✅ `20261030-s04_static_static_obs_track-0-172153-6641` | 符合 |

**状态序列**（`result.json.phase1_states`，时间相对 follow 起点）：

```text
t=0.00   AIR_SEARCH         dist=11.901
t=0.01   TARGET_ACQUIRED    dist=11.901
t=0.11   GROUND_APPROACH    dist=11.954
t=13.61  TRACKING_SUCCESS   dist=2.306   reason=tracking_milestone
```

时限是 **15 s**，终态在 **13.61 s** —— 差 **1.39 s**。s04 在 yard 上的任务窗口本来就只要
32–35 s 仿真秒，而 follow 起点在 `start` 成功之后，所以 `--duration` 必须**明显小于**任务时长
（round-2 两次 50 s / 42 s 同样被终态抢先）。

### 3.2 为什么不重试

派工单明确：*"若 duration 分支仍未触达或有残留，停止报告，不追加 attempt。"*
我照做：**没有**再跑第二次，也没有把这次 13.61 s 的终态"改称"成主动停。
若 Leader 要闭环，最小追加授权是 **1 次 headless attempt + `--duration 8`**
（8 s < 13.61 s，必然在 `GROUND_APPROACH` 到时），墙钟约 70 s。

### 3.3 代码侧防御（已做，不需要新运行）

`result.json` 现在会写：

- 触达时：`"duration_branch_taken": true`
- 未触达时：`"duration_branch_taken": false` +
  `"duration_not_reached_note": "--duration 15.0s 未触达：任务在 13.61s 先达终态…本次**不能**作为 duration_limit 分支的证据"`

> **诚实边界**：本轮这次运行的 `result.json` 是记账代码加入**之前**生成的，
> 所以它里面**没有** `duration_branch_taken` 字段。我不去补写旧产物（那会伪造现场）。
> 记账代码只有离线回归覆盖（`test_duration_branch_is_recorded_even_when_not_reached`），
> **未**经过真实运行的字段级验证。

<a id="p1-2-r3-viz"></a>
## 4. 必做 2：headless 不启动 RViz —— **已达成**

### 4.1 改动

```python
def viz_enabled(headless):
    """RViz 叠加层是否该起：只有 GUI 形态需要。"""
    return not headless
...
'viz:=%s' % ('true' if viz_enabled(headless) else 'false'),
```

依据：P1-2 plan §3 自己写明"脚本用 `ros2 topic echo --once` 或轻量 Python 订阅
（**不要**起 RViz 才能看状态）"；headless 用于经济快跑，多起 `rviz2`（≈257 MB）+
`viz_markers`（≈90 MB）+ `static_tf` 是纯浪费（MAP_DESIGN_PLAYBOOK 16.2 的内存实测）。

### 4.2 现场对比（同一台机、同 backend/scene/map/seed/yaw）

| run | 轮次 | `viz` 参数 | `rviz2` 起过 | `viz_markers` 起过 |
|---|---|---|---|---|
| `20261030-171047` | round-2 | `viz:=true` | **1** | **1** |
| `20261030-171225` | round-2 | `viz:=true` | **1** | **1** |
| `20261030-171354` | round-2 | `viz:=true` | **1** | **1** |
| `20261030-172138` | **round-3** | `viz:=false` | **0** | **0** |

口径：`launch.log` 的 `process started with pid` 行计数（回收后仍可查），与
`evidence.launch_log.rviz2_started` / `viz_markers_started` 一致。

### 4.3 离线回归（4 项 + 反向对照）

| 测试 | 断言 |
|---|---|
| `test_gui_enables_viz_overlay` | GUI → `viz:=true` |
| `test_headless_disables_viz_overlay` | headless → `viz:=false`，且**不得**出现 `viz:=true` |
| `test_headless_and_gui_differ_only_in_gz_s_and_viz` | 两者差异**恰好 2 处**且必为 `{gz_args, viz}`（守护"自变量可枚举"，防以后偷偷多传参数） |
| `test_gz_args_differs_only_by_headless_flag` | `gz_args` 只差 `-s` |

**反向对照**（证明断言有区分度）：把 `start.py` 的 `viz` 改回无条件 `'viz:=true'` →
`test_headless_disables_viz_overlay` + `test_headless_and_gui_differ_only_in_gz_s_and_viz`
立即 **2 failed**；还原后 **40 passed**（全套 `scripts/tests/` **136 passed**）。

### 4.4 对 round-2 等价证据的影响：**无**

- round-2 的 headless 臂**原本就不产出 GUI 证据**（`gui_claim=not_applicable`），
  等价核验里的 GUI 证据门只对 GUI 臂生效；
- 等价的自变量是"是否有渲染客户端（`gz -s`）"及其开销（体现在 RTF / 拍数 / 时长），
  而 `rviz2` 属于**演示叠加层**，不是 C3 等价的自变量；
- 本轮**没有**重跑 GUI / headless 等价，**没有**改写
  `experiments/p1-2/round-2/preregistration/**` 与 `experiments/p1-2/round-2/equivalence/**` 任何字节。

> 需 Leader 确认的判断：把 headless 的 `viz` 从 true 改 false，是否影响"等价"的可比性。
> 我的判据是**不影响**（理由如上），但这属于口径解释，**由 Leader 裁定**；
> 若判"影响"，则 round-2 的等价结论需要在新预登记下重做——那需要新的 T2 预算，不属于本轮。

<a id="p1-2-r3-budget"></a>
## 5. 预算

| 项 | 预算 | 实际 |
|---|---|---|
| T2 attempt | **1** | **1**（`--duration 15` headless） |
| T2 墙钟 | **150 s** | **69.7 s**（`phases` 求和：launch 0.0 + ready 30.7 + start 10.2 + follow 13.6 + collect 15.2） |
| T1 | **0** | **0** |
| 离线检查 | 总 ≤120 s / 单次 ≤30 s | **9 次 / ≈18 s**（pytest ×4、反向对照 ×1、docs_link_check ×1、grep/读若干） |
| 构建 | — | **0**（未改 C++ / CMake；launch 与 Python 走 symlink-install） |

<a id="p1-2-r3-notdone"></a>
## 6. 未执行 / 未达成

- **`--duration` 主动停分支（`duration_limit` + 退出码 3）仍未取得现场证据** —— 见 §3。
  这是本轮**唯一的未达成项**，不写 PASS。
- **`duration_branch_taken` 字段未经过真实运行的字段级验证** —— 记账代码加在本次 run 之后，
  该 run 的 `result.json` 无此字段（不补写旧产物）。
- 未跑 GUI（派工单禁止）、未跑第二组等价、未扩种子。

<a id="p1-2-r3-ledger"></a>
## 7. 假设台账与下一轮建议

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 `--duration 15` 能在 s04 上先到时 | **已排除**（任务 13.61 s 就到终态） | 已做 | — |
| H2 `--duration ≤ 8` 必然在 AIR_SEARCH/GROUND_APPROACH 到时 | **未排除** | 1 次 headless `--duration 8` | **1 次 T2 / ~70 s** |
| H3 headless 的 viz 修正不影响 GUI↔headless 等价可比性 | **未排除**（我的判据是不影响，属口径判断） | 无需新运行：论证 + Leader 裁定 | 无 |
| H4 `duration_branch_taken` 记账在真实运行里正确落盘 | **未排除** | 同上 H2 的一次运行即可顺带验证 | 同 H2 |

**下一轮建议（若 Leader 要闭环）**：
1. **一次 `--duration 8` headless attempt**（72 s 墙钟），同时验证 H2 与 H4 —— 一趟解决两个未验证项。
2. 若不想再加 T2：把 `duration_limit` 分支**登记为已知缺口**（与"真实 Gazebo 截图""`velocity` 下 C10 自锁"
   同类），P1-2 以现有 8 项验收 —— 该分支不影响"一条命令起、一条命令停"的主命题。

<a id="p1-2-r3-appendix"></a>
## 8. 附：命令与退出码

| # | 命令 | 退出码 |
|---|---|---|
| 1 | `python3 -m pytest scripts/tests/test_demo_entry.py -q`（改 viz 前） | 0（37 passed） |
| 2 | 同上（改 viz + 新增 4 项后） | 0（40 passed） |
| 3 | 同上（**注入**无条件 `viz:=true`） | **1**（2 failed，反向对照） |
| 4 | 同上（还原后） | 0（40 passed） |
| 5 | `setsid ./run_demo.sh --headless --duration 15` | 0（**未触达 duration 分支**；见 §3） |
| 6 | `ps` 复核残留 | 0 个 |
| 7 | `python3 -m pytest scripts/tests/ -q`（已 source） | 0（**136 passed**） |
| 8 | `python3 tests/docs_link_check.py` | 0（活跃断链 0） |
