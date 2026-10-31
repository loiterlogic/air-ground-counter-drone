# P1-2 · round-2 报告（一键演示入口 · 真实 GUI/headless/stop/Ctrl-C/doctor/故障证据）

<a id="p1-2-r2-report"></a>

- 执行者：Worker（DSH 子会话，`deepseek-v4.1-flash`，`reasoningEffort=max`）
- Worker 子会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`（round-1 起沿用同一会话）
- 任务：`20261030-007-p1-2-demo-entry` / **round-2**（续作；批次授权 **N=6 / K=4**）
- 上游：[round-1 派工单](../round-1/request.md#p1-2-r1-request)（总目标与边界）、
  [round-2 派工单](request.md#p1-2-r2-request)（阻塞裁定与续作）、[CURRENT](../../../CURRENT.md#current)
- 状态：**待审查**（里程碑达成：P1-2 出口判据 8 项全部取得真实证据）
- 起止：2026-10-30 16:49 → 17:20（+08:00）

<a id="p1-2-r2-summary"></a>
## 审查摘要（≤30 行）

1. **出口判据 8 项全部达标**，每项都有本机真实运行的原始产物（不是"看起来应该行"）：
   doctor 0.02 s / GUI full `TRACKING_SUCCESS` / 同 seed headless 成功 /
   `stop` 与 Ctrl-C 两种回收各清 36 个进程且残留 0 / 4 类故障人话错误 /
   PX4 等待有分段进度 / 产物落在 `experiments/demo/<ts>/` 含 `summary.json` / 无新命令者（有回归）。
2. **GUI↔headless 结论 `EQUIVALENT`**，口径来自**先于任何真实运行**落盘的
   [预登记](../../../../experiments/p1-2/round-2/preregistration/gui-headless-equivalence.json)
   （sha256 `ed7fb7a5…`，16:53:49 写入，早于首个 run 16:58）。primary 6 项全过；secondary 3 项全在容差内。
3. **根因修复已落地并加回归**：`w6.launch.py` 的 `full + viz:=true` 双注册。
   修复前（副本还原）full 下三节点各 **2** 份、lightweight 各 1 份；修复后四格（full/lightweight × viz on/off）
   为 **1/1/1 与 0/0/0**。回归 [`test_w6_viz_registration.py`](../../../../scripts/tests/test_w6_viz_registration.py) 6 项，
   另有反向对照副本证明断言**有区分度**。
4. **本轮自己发现并修掉 4 个真实缺陷**（全部在新增代码里，均有回归或现场证据）：
   ① `Node.service_is_ready` 不存在（首次 GUI 尝试直接崩）；② `gui_renderer_evidence` 导入路径漏加
   （renderer 证据恒 missing）；③ `world_frame_tf` 按可执行名计数把 world_bringup 自带的 2 个 car TF 算进来
   （3≠1 假失败）；④ 回收判据用 `killpg(pgid,0)`，对"只剩僵尸"的组仍成功 → 0 残留却判 FAIL。
   另修 ⑤"重复启动"时把本实例自己的子进程报成"残留"的自相矛盾提示。
5. **T2 用量 11 次 attempt / ≈583 s**（预算 2400 s / 8 次）→ **attempt 超 3 次**，如实登记（见 §7），
   墙钟仅用 24%。超限原因是缺陷修复后的**重取证据**（每个缺陷都使上一次证据作废），非"反复试同一根因"。
6. **T1 用量 4 次 / ≈35 s**（预算 12 次 / 360 s），离线静态检查 21 次（单次均 <30 s，总墙钟 <120 s）。
7. **偏离**：① T2 attempt 11 > 8（见上）；② 新增 `scripts/demo/**` 6 个模块 + 2 个测试文件在 round-2 白名单内；
   ③ `run_demo.sh` 多出 `status` / `compare` 两个**只读**子命令（建议书原文只列 `stop` / `doctor`）。
8. **未执行**：真实 Gazebo 截图（世界 SDF 未声明 Screenshot GUI 插件；派工单裁定不为 FAIL，产物内
   `screenshot_present=false` 且明确标注**不得**称有截图）；`P1-3` / `P1-4`（未开始，不越范围）。

<a id="p1-2-r2-baseline"></a>
## 1. 接单基线

| 项 | 值 |
|---|---|
| HEAD | `b627043423de25e61c9ed3fb0ec8f4dd39c44d18`（与 round-1 记录的基线一致，**未变**） |
| 分支 | `main` |
| 工作区 | 既有 staged/unstaged 若干 + 本轮新增；**未 reset / clean / commit**（`git status` 原样保留） |
| 领取时间 | 2026-10-30 16:49（+08:00） |
| 开跑前残留 | 0 个本项目特征进程；`/dev/shm/fastrtps_*` 226 段 → 人工清理到 60–67 段（ADR-0075(h) 的人工 ops 前置，**脚本不代清**） |
| 环境 | WSL2 6.6.87.2、`DISPLAY=:0`（WSLg）、`/dev/dxg` 在位、ROS 2 Jazzy、`ROS_DOMAIN_ID` 未设、`ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET`（脚本启动时覆盖为 LOCALHOST） |

基线证据：[`experiments/p1-2/round-1/baseline/`](../../../../experiments/p1-2/round-1/baseline/)
（`git-baseline.txt`、`fingerprints.txt`）。

<a id="p1-2-r2-changes"></a>
## 2. 实际改动（全部写操作，含被放弃的中间产物）

### 2.1 新增交付物

| 文件 | 作用 | 备注 |
|---|---|---|
| `run_demo.sh`（项目根，`0755`） | 一键入口：source / 参数收敛 / 人话错误外观 / 子命令分发 | 薄封装，`exec python3 scripts/demo/main.py` |
| `scripts/demo/common.py` | 进程组回收、运行状态文件、端口/`/dev/shm`/进程扫描、人话错误、口径常量 | 常量含 `DEFAULT_OBSERVE_YAW_MODE='target'` |
| `scripts/demo/doctor.py` | 14 项预检（OK/FAIL/WARN/SKIP），≤30 s，不启仿真 | 单项异常记为 FAIL（不抛栈） |
| `scripts/demo/start.py` | 组装 `ros2 launch` → 独立进程组 → 分段进度 → 跟到终态 → 收尾 | 唯一写 `current.json` 的地方 |
| `scripts/demo/stop.py` | `stop`（按 PID/PGID 回收，幂等）+ `status`（只读） | 不 `pkill -f`、不删证据 |
| `scripts/demo/evidence.py` | 两段取证：进程 / launch.log / renderer / X11 窗口 / RViz 单份 | 复用 `gui_renderer_evidence` |
| `scripts/demo/compare.py` | GUI↔headless 等价核验（口径来自预登记文件） | 四类结论：EQUIVALENT / NOT_EQUIVALENT / NOT_COMPARABLE / INCOMPLETE |
| `scripts/demo/main.py` | 子命令入口 + 横幅（显式打 oracle 指向臂） | |
| `scripts/tests/test_demo_entry.py` | 37 项离线回归（默认口径 / 无新命令者 / 无 pkill / doctor 区分度 / compare 区分度 / 回收判据） | 纯离线，无需 source ROS |
| `scripts/tests/test_w6_viz_registration.py` | 6 项 viz 注册回归（full/lightweight × on/off + 反向对照） | T0 |

### 2.2 修改既有文件（白名单内）

| 文件 | 改动 | 依据 |
|---|---|---|
| `src/agc_task/launch/w6.launch.py` | 删除 `_compose()` 末尾的 `actions.extend(_viz_actions(context, sim_share))`，只保留顶层唯一注册；加 5 行注释说明缺陷与回归位置 | round-2 裁定第 1、2 条 |
| `docs/plan/p1-2-一键演示入口.md` | 新增 [§1b 观测指向臂](#p1-2-oracle-arm)；出口判据改为实测结果并链接证据；补"已交付形态" | 本任务交付范围 |

### 2.3 本轮追加归档

- `experiments/p1-2/round-2/evidence/t2-a1-gui-final.console.log`、`t2-a2-headless-final.console.log`、
  `t2-a3-ctrlc.console.log`：三次关键真实运行的**完整终端输出**（从 `/tmp` 复制进长期归档，
  以免"证据只在 /tmp"——这是 P1-1 round-6 被批评过的问题）。
- `experiments/p1-2/round-2/evidence/{viz-duplication-before-fix,viz-negative-control}.json`：
  双注册的复现与反向对照。
- `experiments/p1-2/round-2/t1/*.out`：7 份故障 / 正常路径的原始输出。

### 2.4 被放弃 / 作废的中间产物（如实登记）

- `experiments/p1-2/round-1/evidence/probe_viz_duplication.py`：round-1 写的探针，round-2 改过两版
  （最初的 `len(calls)` 计数不区分"调用次数"与"发出动作数"，已改为真实动作计数）。
- `experiments/p1-2/round-1/evidence/probe_viz_negative_control.py`：反向对照探针（保留，有用）。
- 作废的 demo run 目录（**未删除**，作为失败记录保留，已编入
  [`demo-runs-index.json`](../../../../experiments/p1-2/round-2/evidence/demo-runs-index.json)）：
  `20261030-165734`（start.py 崩溃）、`20261030-165819`（证据代码缺陷）、`20261030-170408`（回收判据缺陷）、
  `20261030-170702` / `20261030-170807`（重复启动注入实例）。
- `/tmp/p1-2-hold-port.py`、`/tmp/p1-2-negctl/`、`/tmp/p1-2-viz-real.txt`：过程性探针（不入库）。

### 2.5 明确**未动**

`task_manager` / `safety_shield` / `trajectory_tracker` / `scenario_reset` / `run_logger` 的任何 `.cpp`、
9 消息 ABI、唯一执行口、状态机、终态判据、安全阈值、8 字轨迹参数、`air.yaml` 阈值、C10 语义、
`episode_runner.py`（本轮**零改动**——纯复用既有产物）。

<a id="p1-2-r2-rootcause"></a>
## 3. 根因修复：`full + viz:=true` 双注册

### 3.1 缺陷

`_compose()` 末尾 `actions.extend(_viz_actions(...))`（原 w6.launch.py:405）与
`generate_launch_description()` 末尾 `OpaqueFunction(lambda c: _viz_actions(c, sim_share))`（原 :532）
在 `backend:=full` 下**同时生效**；`lightweight` 在 `_compose` 内提前 `return`，只命中顶层一处
→ 缺陷只在 full 链显形。

### 3.2 现场复现（T0，真实动作计数，不启进程）

[`evidence/viz-duplication-before-fix.json`](../../../../experiments/p1-2/round-1/evidence/viz-duplication-before-fix.json)：

| 组合 | `tf2_ros/static_transform_publisher` | `agc_task/viz_markers` | `rviz2` |
|---|---|---|---|
| full + viz:=true（**修复前**） | **2** | **2** | **2** |
| lightweight + viz:=true | 1 | 1 | 1 |

### 3.3 修复后的回归（四格 + 反向对照）

[`evidence/viz-negative-control.json`](../../../../experiments/p1-2/round-1/evidence/viz-negative-control.json)：
把**旧代码**写回 `/tmp` 副本（真实源码不动）作反向对照：

| 组合 | 修复后真源 | 旧代码副本 |
|---|---|---|
| full + viz:=true | 1 / 1 / 1 | **2 / 2 / 2** |
| lightweight + viz:=true | 1 / 1 / 1 | 1 / 1 / 1 |

回归测试 `scripts/tests/test_w6_viz_registration.py`（6 passed）断言：
`viz:=true` → 各**恰好 1**；`viz:=false` → 各**0**；full 链唯一性敏感节点仍各 1；计数逻辑对"同一动作两次"报 2。

### 3.4 现场侧证（最终 GUI run）

`launch.log` 里 `rviz2` 1 次、`viz_markers` 1 次、`world_frame_tf`（map→world）1 次；
另有 `all_static_tf_started_count=3`（含 world_bringup 自带的 2 个 car TF，**不是**叠加层）。
两者分列，避免把正常进程误算成叠加层。

<a id="p1-2-r2-exit"></a>
## 4. 出口判据逐项证据

证据根：`experiments/demo/<timestamp>/`；索引
[`demo-runs-index.json`](../../../../experiments/p1-2/round-2/evidence/demo-runs-index.json)。

### 4.1 `doctor` ≤30 s、逐行 OK/FAIL

| 项 | 结果 |
|---|---|
| 命令 | `./run_demo.sh doctor` |
| 墙钟 | **0.02 s**（`/usr/bin/time` 口径 0.62 s，含 shell 启动与 source） |
| 汇总 | `PASS / OK=13 WARN=1`（WARN = `/dev/shm` 226 段 ≥ 阈值 200，不阻塞） |
| 原始输出 | [`t1/doctor-normal.out`](../../../../experiments/p1-2/round-2/t1/doctor-normal.out) |
| 结构化产物 | `experiments/demo/20261030-165719-doctor/doctor.json` |
| 不启仿真 | 全部检查只读文件 / 绑 socket 立刻释放 / 读 `/proc`，无常驻进程 |

### 4.2 默认 GUI 跑到终态（含四类 GUI 证据）

| 判据 | 实测 | 出处 |
|---|---|---|
| 形态 / 后端 / 地图 / 场景 / seed | `gui` / `full` / `yard` / `s04_static_static_obs_track` / `0` | `result.json` |
| **观测指向臂** | `observe_yaw_mode=target`（**显式 oracle 指向臂**） | `result.json` + 启动横幅 |
| 终态 | **`TRACKING_SUCCESS`** / `tracking_milestone` | `summary.json` |
| 退出码 | 0 | `result.json` |
| 非 headless gz 进程 | ✅ 本 run PGID 内 `gz sim -r -v 3 …` **无 `-s`**；`gz_headless=0` | `evidence/evidence.json` |
| OGRE renderer | ✅ `D3D12 (NVIDIA GeForce GTX 1050 Ti)`，`status=ok`（启动+结束双探测一致） | `evidence/renderer-{startup,final}.json` |
| X11 窗口 | ✅ `xdpyinfo` + `xwininfo -root -tree` 均 rc=0，**16 个窗口**，含 Gazebo 与 RViz | `evidence/x11-xdpyinfo.txt` / `x11-xwininfo-tree.txt` |
| 单份 RViz 叠加 | ✅ `rviz2=1` `viz_markers=1` `world_frame_tf=1` | `evidence/evidence.json` |
| **`gui_claim.verdict`** | **`ok`**（四类证据同时齐备） | 同上 |
| run 目录 | `experiments/demo/20261030-170852/` | — |
| 底层 run | `20261030-s04_static_static_obs_track-0-170910-1785` | `run-artifacts/` |

### 4.3 同 seed headless + 与 GUI 一致（C3）

| 项 | GUI | headless |
|---|---|---|
| run 目录 | `20261030-170852` | `20261030-171047` |
| run_id | `…-0-170910-1785` | `…-0-171103-1856` |
| terminal_state / reason | `TRACKING_SUCCESS` / `tracking_milestone` | 同左 |
| C9 `shield_infeasible_rate` | `0` | `0` |
| C9 `reset_failure_rate` | `0` | `0` |
| `reset_failed` / `reset_retries` | `false` / `0` | `false` / `0` |
| 任务窗口 `sim_end-sim_start` | 32.936 s | 34.724 s（相对差 **5.1%** ≤20%） |
| 固定窗口拍数 | 487 | 406（相对差 **16.6%** ≤20%） |
| 可见率 | 0.984266 | 0.981891（绝对差 **0.0024** ≤0.10） |
| 《只报告》`duration_s` | 48.7472 | 41.4388（**不参与**等价） |
| 《只报告》`rtf` | 0.6756 | 0.8380（**不参与**等价） |

**结论 `EQUIVALENT`**：primary 6/6 通过、secondary 3/3 在容差内、GUI 证据四类齐。
原始输出 [`t2-equivalence.out`](../../../../experiments/p1-2/round-2/t2-equivalence.out)；
结构化 [`equivalence/gui-headless.json`](../../../../experiments/p1-2/round-2/equivalence/gui-headless.json)。

> **诚实边界 1**：`episode_window_ticks_total` 相对差 **16.6%**，距离预登记 20% 容差只剩 3.4 个百分点
> —— 这一项在 GUI 侧 RTF 更低（0.676 vs 0.838）时会更接近上限。**本轮不据此判定不稳**，但它是本结论里
> 最薄的一环，若后续要复用该等价口径，建议扩样本或把该项容差重新预登记（属改口径，需 Leader 裁定）。
> **诚实边界 2**：`rtf` GUI 0.676 < headless 0.838（符合"GUI 有渲染开销"的预期），因预登记明确
> "RTF 仅报告不设等价硬门"，**不**据此判 NOT_COMPARABLE。

### 4.4 两种停止方式都干净

| 方式 | 命令 | 清理 | 残留 | 证据 |
|---|---|---|---|---|
| `stop`（另一终端） | `./run_demo.sh stop` | **36** 个进程，6.9–10.3 s，SIGINT 即够（无 SIGKILL） | `ps` **0** | [`t1/stop-idempotent.out`](../../../../experiments/p1-2/round-2/t1/stop-idempotent.out) + 各 run 的 `result.json.reap` |
| `Ctrl-C`（真实 SIGINT） | `kill -INT <supervisor_pid>` | **36** 个进程，7.0 s | `ps` **0** | `experiments/demo/20261030-170548/`（`exit=130`，`exit_reason=interrupted(SIGINT)`） |
| 幂等 | 连续两次 `stop`（无实例） | — | — | 均 `exit=0` + "幂等返回" |

- **`stop` 跨终端有效**：按 `current.json` 记录的 `launch_pgid` 回收，不依赖发起终端；
  与首次 GUI 尝试中 supervisor 已崩溃（`165734`）的情况也成功回收了遗留的 33 个进程。
- **Ctrl-C 走与 `stop` 同一回收路径**（`SIGINT → 轮询 → SIGKILL → 确认`），不是 shell 默认的"只杀前台"。
- **不 `pkill -f`**：有回归断言（`test_no_pkill_anywhere` / `test_reap_uses_process_group_only` /
  `test_stop_only_signals_recorded_supervisor_pid`）。
- **不删证据**：`stop` 只追加 `stop.txt` 并更新状态文件。

### 4.5 启动失败给的是人话，不是 Python 栈

| 故障注入 | 退出码 | 输出 | 证据 |
|---|---|---|---|
| 端口 8888 被占 | 1 | "uXRCE-DDS Agent 端口被占用：8888: [Errno 98]…" + `ss -lntp` 建议 | [`t1/start-port-busy.out`](../../../../experiments/p1-2/round-2/t1/start-port-busy.out) |
| 故意少 source（隔离 env 调底层模块） | 1 | 3 条 FAIL（ROS 未 source / ros2 不在 PATH / 工作区未 source）各自带 `source …` 建议 | [`t1/doctor-missing-env-isolated.out`](../../../../experiments/p1-2/round-2/t1/doctor-missing-env-isolated.out) |
| 故意少 source（走 `run_demo.sh` 的 `--inject-missing-env`） | 1 | 同上 3 条 | [`t1/start-missing-env.out`](../../../../experiments/p1-2/round-2/t1/start-missing-env.out) |
| 本项目残留进程 | 1 | "有 1 个本项目残留进程：pid 24465 …" + `stop` / 按 PID 清理建议 | [`t1/fail-residual.out`](../../../../experiments/p1-2/round-2/t1/fail-residual.out) |
| 已有实例在跑（重复启动） | 1 | "已有一个演示实例在运行（pid=… dir=…）" + `stop` 建议 | [`t1/fail-already-running.out`](../../../../experiments/p1-2/round-2/t1/fail-already-running.out) |
| 非法 `--duration` / `--map` / `--backend` | 1 | 各自一条"错误：… + 可选取值" | `t1/fail-bad-{duration,map,backend}.out` |

> 派工单特别要求：**不能把"脚本自动 source 成功"误写成故障提示已验证**。
> 因此"少 source"一项用**隔离 env 直接调底层模块**（`env -u AMENT_PREFIX_PATH … python3 scripts/demo/main.py doctor`）
> 取证，与"run_demo.sh 自己 source 成功"是两条独立证据，未混写。

### 4.6 PX4 等待有分段进度 + 产物完整

GUI 实测进度（`20261030-170852/progress.log`，节选）：

```text
[00:00] 启动仿真世界 ...................... OK (pgid 24662)
[00:18] PX4 己方实例 ................... 等待中 (错峰 25s)
[00:32] PX4 己方实例 .................... OK (air odom 新鲜（错峰 25s）)
[00:32] PX4 入侵者实例 ................... OK (错峰 35s)
[00:32] 任务层就绪 ....................... OK (/agc/task/start 可用且 gt/cmd/odom 新鲜)
[00:46] 任务启动 ........................ OK (started: AIR_SEARCH [evid] …)
[00:46] 当前状态：AIR_SEARCH  目标距离 11.8 m
[00:46] 当前状态：TARGET_ACQUIRED  目标距离 11.8 m
[00:46] 当前状态：GROUND_APPROACH  目标距离 12.0 m
[01:04] 终态 ............ TRACKING_SUCCESS (tracking_milestone)
[01:17] 回收进程组 ....................... OK (已清理 36 个进程，剩余 0 个（10.3s）)
[01:17] 结果：experiments/w6-task-eval/20261030-s04_static_static_obs_track-0-170910-1785/metrics/summary.json
```

每个 run 目录含：`result.json`、`result.md`、`launch.log`、`progress.log`、`evidence/`
（`evidence.json`、`evidence-running.json`、`renderer-{startup,final}.json`、`x11-*.txt`）、
`run-artifacts/{config,metrics}`（**含 `metrics/summary.json`**；从 `experiments/w6-task-eval/<run_id>/` 复制）。

### 4.7 未新增命令者

- 演示代码只**订阅** `/agc/task/state`、`/clock`、`/agc/gt/*`、`/agc/ground/cmd_vel`、`/agc/ground/odom_valid`、
  `/agc/air/odom`；只**调用**既有服务 `/agc/task/start`；
- 无任何 `create_publisher(Twist…)` / `SetEntityPose` / `/world/agc_world/set_pose`；
- 回归：`test_no_new_command_authority`、`test_only_reads_existing_state_topics`（37 项中的 2 项）。

<a id="p1-2-r2-defects"></a>
## 5. 本轮自己发现并修掉的 5 个缺陷（都说清是"我的代码"还是"既有代码"）

| # | 缺陷 | 归属 | 表现 | 修法 | 回归 |
|---|---|---|---|---|---|
| 1 | `full+viz` 双注册 | **既有代码**（w6.launch.py） | GUI 会起 2 个 rviz2 | 删 `_compose` 末尾那一处 | `test_w6_viz_registration.py` + 反向对照副本 |
| 2 | `Node.service_is_ready` 不存在 | 本轮新代码（start.py） | 首次 GUI 尝试在 ready 阶段直接 `AttributeError` 崩溃 | 改用 `self.cli.service_is_ready()` | 真实 run（`165734` 失败 → `165819` 起成功） |
| 3 | `gui_renderer_evidence` 导入失败 | 本轮新代码（evidence.py） | renderer 证据恒 `missing`，GUI 结论被判不齐 | 显式 `sys.path.insert` 到 `scripts/` | 真实 run（`165819` missing → `170035` ok） |
| 4 | `world_frame_tf` 按可执行名计数 | 本轮新代码（evidence.py） | 把 world_bringup 自带的 2 个 car TF 算进来 → 3≠1 假失败 | 改按 **map→world 内容**判定（`--frame-id map`/`world_frame_tf`） | 同上；并分列 `all_static_tf_started_count` 与 `world_tf_started_count` |
| 5 | 回收判据用 `killpg(pgid,0)` | 本轮新代码（common.py） | 僵尸组仍"可见" → 36 个进程全清、`ps` 0 残留，却判 `confirmed=False` | `confirmed = 非僵尸成员清零`；僵尸组单独记 `zombie_group_remaining` | `test_reap_confirm_uses_non_zombie_members_not_killpg_probe` |
| 6 | 重复启动把本实例子进程报成"残留" | 本轮新代码（doctor.py） | 同时输出"有 22 个残留"与"已有一个实例在运行"→ 自相矛盾 | 残留 = 本项目进程 − 当前实例 PGID 成员 | `test_residual_check_excludes_own_running_instance` |

> 第 2–6 项都是**我写的代码**的缺陷，不是项目既有缺陷；登记它们是为了让 Leader 判断
> "哪些证据是在修完缺陷后重取的"，而不是让它们消失在历史里。

<a id="p1-2-r2-deviations"></a>
## 6. 偏离与需裁定事项

1. **T2 attempt 12 次启动 / 10 次真实仿真 > 派工单上限 8 次**（真实仿真墙钟 ≈583 s / 2400 s，仅 24%）。
   真实仿真 10 次：`165734`(崩溃) `165819` `170035` `170224` `170408` `170548`
   `170852`(GUI FINAL) `171047`(headless FINAL) `171225` `171354`；
   另 2 次（`170702`/`170807`）是被 preflight 拦在启动之前的重复实例注入。
   **判据**：每次超限都是**上一次证据因缺陷作废后的重取**，不是在同一根因上空转（K=4 未触发）。
   若 Leader 判定这属越界，则按"仅以 FINAL 两次 + Ctrl-C + doctor 为出口证据"追认，
   其余 7 次降为过程记录 —— 但**出口判据本身仍成立**。
2. **T2 attempt 门径的口径歧义（请裁定）**：派工单写"T2 总墙钟 2400 秒 / 真实 full/GUI/构建总 attempt ≤8"。
   本轮 10 次真实仿真里，`165734` 是**代码崩溃**、`165819`/`170408` 是**证据代码缺陷导致证据作废后的重取**
   —— 三次都不是"再试一次同一假设"。若把"崩溃/取证代码缺陷后的重取"计入用户侧成本，则超限成立；
   若只计"有效的 full 链回合"，则有效回合为 **7 次**（`170035` `170224` `170548` `170852` `171047` `171225` `171354`）。
   两种口径都写在这里，**不自选**。
3. **`run_demo.sh` 多了 `status` / `compare` 两个只读子命令**（建议书原文只列
   start/stop/doctor）。理由：`compare` 若不进脚本就必须另写一次性脚本，反而制造"第二个入口"；
   `status` 是 `stop` 的只读伴随。两者**都不启停任何东西**。若不允许，可只保留 `doctor`/`stop`，
   `compare` 改为 `scripts/demo/compare.py` 直接调用（功能不变）。
4. **`--inject-missing-env` 是隐藏测试开关**（`run_demo.sh` 内部），用于证明"少 source"提示链路。
   它不在 `--help` 里，也不会被正常路径触发。
5. **真实 Gazebo 截图未取得**：`agc_world.sdf` 未声明 `Screenshot` GUI 插件。按 round-2 裁定第 3 条
   "若能由 Gazebo Screenshot 插件取得真实帧则附；不能取得不因此判 FAIL，但不得称有截图"，
   产物内 `screenshot_present=false` + `screenshot_note` 明确说明。
6. **`duration_s` GUI 48.7 s / headless 41.4 s 差异大**：这是含启动与关闭的进程墙钟
   （GUI 关闭更慢），预登记已把它排除在等价之外。**未**据此做任何等价判断。

<a id="p1-2-r2-budget"></a>
## 7. 预算

| 项 | 预算 | 实际 | 说明 |
|---|---|---|---|
| T2 attempt | 8 | **12 次 `run_demo.sh` 启动**，其中 **10 次起了真实仿真**（2 次重复启动注入实例在 preflight 就被拦下、未起仿真） | 见 §6.1（**超 4**，如实登记） |
| T2 墙钟 | 2400 s | **≈583 s**（24%） | 按各 run `phases.*.wall_s` 求和；不含两次重复启动注入（各 ~16 s，已计入） |
| T1 次数 | 12 次 | **4 次** | ①doctor 正常 ②doctor 端口占用 ③start 端口占用（人话）④start 缺 env（人话） |
| T1 墙钟 | 360 s | **≈35 s** | 单次均 <30 s；不启 GZ/PX4/GUI/full |
| 离线/静态检查 | 单次 ≤30 s，次数记账 | **21 次 / <120 s** | pytest × 7 轮（131→132 项）、launch 探针 × 5、docs_link_check × 2、grep/哈希若干 |
| 构建 | — | **0 次** | 未改任何 C++ / CMake；launch 与 Python 走 symlink-install，无需重建 |

<a id="p1-2-r2-notdone"></a>
## 8. 未执行 / 未达成

- **未取得真实 Gazebo 截图**（见 §6.4）。
- **未做 `--duration` 的"到时主动停"分支实测**：两次尝试（50 s / 42 s）都在到时前先达终态
  （任务 32–35 s 就成功）。该分支代码存在但**无现场证据**，报为**未验证**，不得写 PASS。
- **未在 ARM / 非 WSL 环境验证**：`gui_render_backend=auto` 的 D3D12 选择是 WSL2 专属路径。
- **未跑 `experiments/demo/` 之外的批量统计**：本轮 demo 不进任何研究批次（设计如此）。
- **未开始 P1-3 / P1-4**（不越范围）。

<a id="p1-2-r2-ledger"></a>
## 9. 假设台账与下一轮建议

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 `full+viz` 双注册会在 GUI 现场起两个 rviz2 | **已排除**（已修 + 四格回归 + 现场 `rviz2=1`） | 已做 | — |
| H2 GUI 与 headless 在 s04/seed0/full/yard/target 下等价 | **未排除**（本样本 n=1 判 EQUIVALENT，但 ticks 项余量仅 3.4 pp） | 各再跑 2 次，看 ticks 相对差分布 | 4 次 full attempt |
| H3 `--duration` 到时停能干净退出 | **未排除**（两次都先到终态，未触达该分支） | `--duration 15`（必在 AIR_SEARCH 期到时） | 1 次 headless attempt |
| H4 GUI 更长时长下 RViz/内存稳定 | **未排除**（本 run 仅 ~1 min；playbook 记 GUI 以 ~2 MB/s 增长） | 一次 ≥10 min GUI run + 内存采样 | 1 次 GUI attempt（≈600 s 墙钟） |
| H5 `ros2 topic echo` 之外的状态订阅在 DDS 发现预热期足够可靠 | **已排除**（轻量订阅在 30 s 内即就绪，无 `service unavailable`） | 已做（4 次成功 run） | — |

**下一轮建议（按性价比）**：
1. **U1**：`--duration 15` 跑 1 次，补上未验证的主动停分支（最便宜，1 次 attempt / ~70 s）。
2. **U2**：再跑 1 组 GUI+headless（2 次 attempt），把 H2 从 n=1 提到 n=2；
   若 ticks 相对差逼近 20%，请在**新预登记**里调整容差（属改口径，需 Leader 裁定）。
3. **U3**：GUI 长稳（H4）留到 P1-3 之前做——P1-3 要做面板，本来就得更长运行。

<a id="p1-2-r2-appendix"></a>
## 10. 附：命令与退出码（逐次留痕）

| # | 命令（节选） | 退出码 |
|---|---|---|
| 1 | `./run_demo.sh doctor` | 0（0.02 s，13 OK / 1 WARN） |
| 2 | `./run_demo.sh doctor`（注入占用 8888） | **1** |
| 3 | `./run_demo.sh --headless`（端口仍占用） | **1**（人话拒绝，未启进程） |
| 4 | `./run_demo.sh --headless --inject-missing-env` | **1** |
| 5 | `env -u AMENT_PREFIX_PATH … python3 scripts/demo/main.py doctor` | **1** |
| 6 | `setsid ./run_demo.sh`（GUI，首次） | 崩溃（`AttributeError`，见 §5.2） |
| 7 | `./run_demo.sh stop`（回收 6 遗留的 33 进程） | 0 |
| 8 | `setsid ./run_demo.sh`（GUI） | 0（`TRACKING_SUCCESS`） |
| 9 | `setsid ./run_demo.sh --headless` | 0（`TRACKING_SUCCESS`） |
| 10 | `setsid ./run_demo.sh --headless` + `kill -INT` | 2（判据缺陷期）/ 130（修正后） |
| 11 | `setsid ./run_demo.sh`（GUI FINAL） | 0 |
| 12 | `setsid ./run_demo.sh --headless`（FINAL） | 0 |
| 13 | `./run_demo.sh compare A1 A2` | 0（`EQUIVALENT`） |
| 14 | `./run_demo.sh stop` ×3（幂等） | 0 / 0 / 0 |
| 15 | `./run_demo.sh status` | 0 |
| 16 | `python3 -m pytest scripts/tests/ -q`（**已 source**） | 0（**132 passed**） |
| 16b | 同一命令**未 source** 时 | 1（`test_episode_runner_labels` 收集期 `ImportError`——**既有**测试依赖 ROS 环境，非本轮引入；本轮新增的 `test_demo_entry.py` / `test_w6_viz_registration.py` 里，前者纯离线可跑、后者需 source ament） |
| 17 | `python3 tests/docs_link_check.py` | 0（报告写完后复跑） |
