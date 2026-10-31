<a id="p1-3-r1-report"></a>
# P1-3 · round-1 批次报告

- 任务 ID：`20261030-008-p1-3-observability`
- 轮次：round-1（**批次 N=6**，本批实际用 **2 轮**；K=4 未触发）
- 执行者：Worker（DeepSeek Harness，路由由 Host 钉死）
- 领取时间：2026-10-30T17:43+08:00；完成时间：2026-10-30T18:15+08:00

## 审查摘要（≤30 行）

**结论：7 条出口判据中 6 条达成、1 条（目标视觉可辨识）部分达成并停在白名单边界上报，未自行扩权。**

- **做了什么**：在 P1-2 既有骨架 `scripts/demo/` 内新增 4 个呈现模块
  （`status_map` / `panel` / `timeline` / `verdict`）并接到 `start.py`；
  三件产物随演示落盘：`timeline.txt` / `panel.txt` / `terminal_explanation.txt`。
- **真实证据**：headless `a2`、GUI `a3`、headless+pty `a4` 各跑通一次，均
  `TRACKING_SUCCESS / tracking_milestone`、退出码 0、关键节点 8 个、进程组回收 confirmed。
- **一次失败如实保留**：`a1` 因呈现层缺陷（`Timeline.state()` 缺 `at` 参数）崩溃，
  仿真进程组遗留 33 个进程，已用 `./run_demo.sh stop` 回收；已修并加"呈现层降级不终止"回归。
- **契约**：未新增话题、未改 9 消息 ABI、未改唯一执行口、未改 C10 / 终态判据 / 安全阈值；
  默认口径仍 `full + yard + s04 + observe_yaw_mode=target`（显式 oracle 指向臂，横幅与时间线双处标注）。
- **待 Leader 裁定 1 项**：目标视觉可辨识需要改 `intruder_uav.sdf.xacro`（白名单外），已停。
- **顺带发现（不在本单范围）**：`docs/plan/p1-2-一键演示入口.md` 有 2 条活跃断链
  （P1-2 报告已归档，链接仍指向 `task/`），需另派。

差异清单见「实际改动」；证据见「证据路径」；未执行项见「未执行」。

## 接单基线

| 项 | 值 |
|---|---|
| HEAD | `b627043`（`coordination: 核验 P0-5 并归档`） |
| 分支 | `main` |
| 脏文件 | 48 项（P1-1/P1-2 收尾遗留：`docs/adr/`、`scripts/episode_runner.py`、`src/agc_*` 配置等） |
| 本单是否改动既有脏文件 | **否**（白名单内文件此前均干净） |

`HEAD` 相同不能证明工作区相同，故按派工单要求：**已有改动一律未重置 / 未覆盖 / 未提交**。

## 实际改动

### 新增（白名单 `scripts/demo/**`）

| 文件 | 行数 | 作用 |
|---|---|---|
| `scripts/demo/status_map.py` | 220 | **唯一**状态语义映射：9 枚举 + 36 条 `reason_code`；C8 禁词守卫（导入期自检）+ `coverage_report()` |
| `scripts/demo/panel.py` | 272 | 2 Hz 面板：tty = 方框原地重绘，非 tty = 单行 + 心跳；`panel.txt` 同源落盘 |
| `scripts/demo/timeline.py` | 181 | `timeline.txt` 事件流；关键节点计数；不足 5 个如实说明；`summary_notes()` 只读既有字段 |
| `scripts/demo/verdict.py` | 231 | 终态判定说明：指标只读 `summary.json`，阈值只读 `params_applied.yaml` |

### 修改（白名单 `scripts/demo/**`）

| 文件 | 改动 |
|---|---|
| `scripts/demo/start.py` | 接线三件产物；`TERMINALS` 收敛到 `status_map.TERMINAL_NAMES`（消除第二份终态副本）；`TaskMonitor` 多读 3 个**既有** `AgcTaskState` 字段（`target_obs_age_s` / `air_controller` / `ground_controller` / `tracking_milestone_met`）；`Progress` 支持面板共存（`erase()` + `block()`）；**呈现层降级**（`_safe()`，异常进 `result['presentation_errors']` 不终止演示） |

### 新增（白名单 `scripts/tests/test_demo*.py`）

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `scripts/tests/test_demo_observability.py` | **40** | 映射单一实现 / 全覆盖、C8 禁词（含"守卫必须真的会拒绝"的区分度）、面板 2 Hz 与四要素、时间线计数口径、判定说明阈值来源、无新话题 / 无 ABI 改动 / 无新命令者、呈现层降级 |

### 修改（白名单 `docs/plan/p1-3-*.md`）

- 新增 [已交付实现](../../docs/plan/p1-3-任务可观测与演示呈现.md#p1-3-implementation)、
  [出口判据结果](../../docs/plan/p1-3-任务可观测与演示呈现.md#p1-3-exit)、
  [目标视觉可辨识的现状](../../docs/plan/p1-3-任务可观测与演示呈现.md#p1-3-target-visual)。

### 未改动（明确边界）

`run_demo.sh` **一行未改**（呈现全部在 `scripts/demo/` 内，起停语义与参数透传完全不碰）；
`src/agc_task/**`、消息、C++、任何契约文件、world SDF、模型文件**均未触碰**。

## 命令、退出码与结果

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python3 -m pytest scripts/tests/test_demo_observability.py -q` | 0 | 40 passed |
| 2 | `python3 -m pytest scripts/tests/test_demo_entry.py -q`（P1-2 回归） | 0 | 40 passed, 1 skipped |
| 3 | `source /opt/ros/jazzy/setup.bash && source install/setup.bash && python3 -m pytest scripts/tests/ -q` | 0 | **176 passed** |
| 4 | `python3 tests/docs_link_check.py` | 1 | 活跃断链 **2**（均为 P1-2 文档既有断链，非本单引入；本单新增链接 0 断链） |
| 5 | `./run_demo.sh --headless`（a1） | **1** | **失败**：呈现层 TypeError → 崩溃；进程组遗留，`./run_demo.sh stop` 回收 33 进程 |
| 6 | `./run_demo.sh --headless`（a2） | 0 | `TRACKING_SUCCESS`，面板 31 帧，关键节点 8 |
| 7 | `./run_demo.sh`（a3，GUI） | 0 | `TRACKING_SUCCESS`，GUI 四类证据齐，面板 37 帧，关键节点 8 |
| 8 | `script -q -e -c "./run_demo.sh --headless"`（a4，真实 pty） | 0 | 同上 + **方框外观 28 帧** |

**T2 记账**：attempt **4 次**（a1–a4），派工单上限 6 次 ✅；总墙钟约
`43 + 71 + 79 + 66 ≈ 259 s`，预算 1800 s ✅；每轮 ≤2 已遵守（a2/a3 分两轮，a4 单独一轮）。

**T1 记账**：**0 次**用了预授权 8 次 —— 本轮全是离线静态检查与 T2 真实 run，未起端口 / 进程微观测。
**离线检查**：约 40 次、累计墙钟 < 120 s（预算 ≤300 s、单次 ≤30 s）✅。

## 证据路径

- 证据根：[`experiments/p1-3/round-1/`](../../experiments/p1-3/round-1/)，
  索引 `evidence/index.json`（机器可读）。
- 真实 run 产物（**主场**，未改写）：`experiments/demo/20261030-180701`（a2 headless）、
  `20261030-180836`（a3 GUI）、`20261030-181008`（a4 pty）。
- 期望闭环核验用 `./run_demo.sh compare <a2> <a3>`（P1-2 既有工具；本单未跑，见「未执行」）。

### 逐条出口判据证据

| 判据 | 证据 |
|---|---|
| 1 单一状态映射 | `status_map.py`；回归 `test_status_map_is_the_only_state_mapping` / `test_status_map_covers_all_nine_states` / `test_status_map_matches_msg_enum_values` |
| 2 2 Hz 面板 | a4 `panel-box-frames.txt`（28 帧方框，真实 pty）；a2/a3 `panel.txt`；`test_panel_tty_redraws_at_2hz_and_throttles_lines` |
| 3 timeline ≥5 节点 | a2/a3/a4 `timeline.txt` 尾部「关键节点：8 个（状态跳变 4 + 生命周期 4）」 |
| 4 终态判定说明 | a2/a3/a4 `terminal_explanation.txt`；阈值来源行 `params_applied.yaml`；`test_verdict_thresholds_come_from_config_not_code` |
| 5 目标视觉可辨识 | **部分达成**，见下节 |
| 6 无新话题 / ABI / 命令者 | `test_no_new_topics_in_presentation_layer` / `test_presentation_modules_never_publish` / `test_msg_abi_untouched` |
| 7 C8 禁词 | `test_c8_tracking_success_has_no_intercept_wording` / `test_c8_all_display_texts_are_clean` / `test_c8_guard_actually_fires` |

## 偏离与待裁定

### 1. 目标视觉可辨识：**部分达成**（需 Leader 裁定，属白名单外）

派工单说"P1-1 已提供目标颜色/几何证据"。逐条核对后的事实是：

| 路径 | 现状 | 观众能否看到 |
|---|---|---|
| `intruder_uav` 被动版（`controlled:=false`） | `<diffuse>1 0 0 1</diffuse>`（纯红方块） | 有颜色，但**演示不用这条** |
| `intruder_uav` 可控版（`controlled:=true`，`w6.launch.py:303` 硬写） | merge `model://x500`，PX4 官方配色（白 + 碳纤维），**无醒目色** | 机身小、无辨识色 |
| `viz_markers` 的 RViz 目标球 | SPHERE 直径 **1.2 m**、`rgba=(1.0, 0.85, 0.1, 1.0)` 暖黄 | **GUI 有；headless 无** |

- GUI 下观众**确实**能靠 RViz 暖黄球看到目标（a3 里 `viz_markers` 起得来）。
- headless 下没有该叠加层，Gazebo 里的 x500 本身没有醒目色 → **该项在 headless 不成立**。
- 要真正满足"颜色/尺寸至少一项"，必须改
  `src/agc_sim/models/intruder_uav/intruder_uav.sdf.xacro`（可控版 visual）或
  `src/agc_sim/config/maps/yard.yaml` 的视觉层 —— **都在本单白名单之外**。
- **按派工单"若需改 world，先停并报告"，停在此处。**
  **最小追加授权建议**：只允许在 `intruder_uav.sdf.xacro` 的 `<xacro:if value="$(arg controlled)">`
  分支里追加一个**纯 visual** 的高亮件（如红色指示球或加高机身贴片），
  明令不得改 collision / inertial / mass / plugin。改后需重跑一次 `a3` 同口径 GUI run 取证，
  并跑 `tests/w6_geometry_check.py` 确认几何派生链未受影响。

### 2. `confidence_min` / `target_max_age_s` 不在 `params_applied.yaml`

判定说明里 `task_manager` 段只有 `d_track_m` / `t_dwell_s` / `t_max_s` / `tracking_milestone_is_terminal`；
`confidence_min` / `target_max_age_s` 是节点 `declare_parameter` 的**代码缺省值**，未被 launch 注入，
因此快照里没有。**展示层如实标为"阈值缺口"，不猜、不补**。
这是既有事实，不是本单缺陷；若要让说明更完整，应在 `w6_base.yaml` 显式注入（**白名单外**）。

### 3. `a1` 失败的处置

- 现象：`TypeError: Timeline.state() got an unexpected keyword argument 'at'` 冒到 `run()` 之外，
  main 打印 Python 栈、退出码 1，**仿真进程组仍在跑**（33 个进程）。
- 处置：用**既有** `./run_demo.sh stop`（不是 `pkill`）按登记 PGID 回收，33 个进程全清、无残留。
- 修复：`Timeline.state()` 增 `at` 参数；并新增 `DemoRun._safe()` —— 呈现层任何异常都进
  `result['presentation_errors']` 并**继续演示**（回归 `test_presentation_failure_degrades_instead_of_killing_the_run`）。
- 如实保留：a1 的完整控制台日志在 `experiments/p1-3/round-1/t2/attempt-a1-headless.console.log`，未删除。

### 4. 双写面板去重（round-1 自查修正）

首版在非 tty 下"状态跳变时也打一行单行面板"，实测与进度行 `当前状态：…` 重复（同一状态连打两遍）。
已改为：非 tty 只按心跳 / 强制刷新出单行；状态跳变由进度行 + `timeline.txt` 各记一次。
**tty 方框外观不受影响**。

### 5. 顺带发现（不在本单范围，未处理）

`python3 tests/docs_link_check.py` 报告 `docs/plan/p1-2-一键演示入口.md:166,167` 两条**活跃断链**：
P1-2 的两份报告已随任务归档到 `.coordination/archive/`，但文档链接仍指向 `.coordination/task/`。
属 P1-2 文档，**不在本单白名单**（本单只许改 `docs/plan/p1-3-*.md`），故未修，报给 Leader 另派。

## 未执行

| 项 | 原因 |
|---|---|
| `./run_demo.sh compare <a2> <a3>` | GUI↔headless 等价核验属 **P1-2 已完成项**（已有 `EQUIVALENT` 结论）；本单只要求"两种模式各一次真实证据"，已满足。T2 预算优先留给呈现层。 |
| 目标高亮改动 | 白名单外，已按停止条件停下报告（见上）。 |
| `--duration` / Ctrl-C 分支复验 | 属 P1-2 round-3/round-4 已验收分支；本单未改起停语义，`run_demo.sh` 一行未动。 |
| Gazebo 窗口截图 | 沿用 P1-2 结论：本机无可用截图工具（`xwd`/`import`/`ffmpeg`/`scrot` 全缺），GUI 证据用既有的"进程 + OGRE renderer + X11 窗口 + 单份 RViz"四类，**不冒充截图**。 |

## 假设台账与下一轮建议（批次末）

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 终端面板在 tty 下真的呈现方框（而不只是代码里能渲染） | **已排除**（a4 真实 pty，28 帧方框，字段齐） | 已做 | — |
| H2 headless 下三件产物同样落盘 | **已排除**（a2：panel 31 帧 / timeline 8 节点 / explanation 有值） | 已做 | — |
| H3 阈值确实来自本 run 配置而非代码常量 | **已排除**（`params_applied.yaml` 段名与实际值逐项核对；缺值列为缺口） | 已做 | — |
| H4 呈现层缺陷会打断演示 | **已确认**（a1 实测），已修 + 回归 | 已做 | — |
| H5 GUI 下目标有醒目视觉标识 | **部分排除**：RViz 球有，Gazebo 实体无 | 需改模型后重跑 GUI | **白名单外：改 `intruder_uav.sdf.xacro` 的 visual** |

**下一轮建议**（若 Leader 追加授权）：只做 H5 —— 给可控版 `intruder_uav` 加纯 visual 高亮件，
重跑一次 GUI run 取证，并跑 `tests/w6_geometry_check.py`。其余判据已闭环，不建议再开轮。

**累计预算消耗**：N=6 用 **2** 轮；K=4 未触发（每轮都有区分性新证据）；
T2 用 **4/6** 次、约 **259/1800 s**；T1 用 **0/8** 次；离线约 40 次 / < 120 s。
