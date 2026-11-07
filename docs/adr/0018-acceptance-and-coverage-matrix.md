<a id="top"></a>
# 验收判定与整链覆盖矩阵

## Status

accepted（2026-11-02 由 ADR-0040 / 0041 / 0046 / 0057 合并；结论未变）

## 背景

评审同时指出三类「绿灯不可信」：

- **runner 假绿**：回合判定只看终态字符串（`expected_match`），`started` / 缺 `summary` / 子进程退出码 / 指标有效性都不进入 PASS；缺 summary 的回合被剔出均值分母，空集合 `sum/max(len,1)` 返回 0；按状态字符串等待**无本 run 关联**；`SIGKILL` 后**无 `wait` 确认**。
- **验收整链范围**：批量入口跑的是**轻量栈**（任务层 + 裁决器，无 PX4 / 空中链路），却把「期望终态匹配」呈现为整链完成；「轻量 PASS」可能被误读为「双 PX4 整链 / GUI 验收」。
- **场景轴未执行**：`scenarios.yaml` 登记 `target_motion × obstacle × perception × outcome`，但运行参数没有对应实验因子——`dynamic` 无障碍驱动覆盖、`s06/s07` 无 drop / fov 参数、`none/static` 用同一世界、空中节点读独立 `air.yaml`、轻量栈不起 `intruder_driver`；名义 12 场景可能实为少量配置变种。

契约真源见 [#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints)、[#terminal-semantics](0014-task-fsm-and-scenario-transaction.md#terminal-semantics)、[#params](0020-package-boundaries-and-runtime-topology.md#params)（单一注入）。

## 决策

### (a) 三层验收判定，全必过方 PASS

`classify_acceptance_layers(result)` 输出三层布尔：

- `layer_integrity`：`started` **且** 子进程退出确认（`proc_exit_confirmed`）**且** `summary` 存在（`summary_present`）**且** 同 run 关联（`same_run_verified` + `state_run_verified`）；
- `layer_proposition`：`expected_match`（`expected_terminal` + `expected_reason`）；
- `layer_metrics`：两指标为**有效数值**（非 `None` / 非 `not_applicable`）。

`pass = layer_integrity and layer_proposition and layer_metrics`；`expected_match` 仅属命题层，**不再**单独决定 PASS。`main` 退出码以 `pass_count == n_episodes`（且 `n_episodes > 0`）为准。这就是**完整性**硬门（r-031）：任一基础设施失败都不允许呈现绿灯。

### (b) 缺 summary / 空指标集合诚实记账（不剔分母、不以 0 冒充）

`summarize_metrics(episodes)`（**不**剔除任何回合）：对每指标统计 `valid_count` / `missing_count` / `missing_ratio`；均值**仅基于有效样本**；**空有效集合 → `value='not_applicable'`**（**不**返回 0）。新增 `metric_completeness` 块承载完整性与缺失比例；`summary_missing_episodes` / `integrity_failures` 如实列出失败场景（**不含** `unsupported` 回合）。

### (c) 同一 run 关联与进程组回收

- **summary 唯一 id**：沿用 `same_run_verified`（`run_id` 含 `-<scenario>-<seed>-`）；**新增** `state_run_verified`：`Monitor` 记录**首个终态观测的墙钟时刻**（`terminal_wall`），要求终态在**本次 start 调用之后**观测（越窗终态 = 旧回合污染 → `false`）；未达终态记 `true`。
- **受限进程组回收 + `wait` 确认**：`pgid` 在 Popen 后即取（防 leader 先死无法反查组）；`killpg(SIGINT)` → `proc.wait(REAP_SIGINT_S)` → **无论 launch 是否已退，都补发组 `killpg(SIGKILL)`** 清理忽略 SIGINT 的游离子进程（如 gz sim）→ `proc.wait(REAP_SIGKILL_S)` → 轮询 `killpg(pgid,0)` 至整组回收；返回 `(exit_confirmed, returncode)`。仅回收 **Popen `start_new_session=True` 的本 run 进程组**；**不**匹配裸名、**不**杀其它会话、**不**用 `rm -rf`。`wait` 取代原固定 `sleep(5)`——`ros2 launch` 在 SIGINT 下先关闭节点（finalize 写 summary）再退出，故 `wait` 返回即 summary 已落盘。
- **就绪门槛 = 服务就绪 + 真值新鲜**：`wait_ready(mon, timeout_s)` 要求「`/agc/task/start` 服务就绪 **且** 车 / 目标真值旁路新鲜」（`Monitor` 订 `/agc/gt/agc_car` 与 `/agc/gt/intruder_uav`，两者接收年龄均 `< GT_FRESH_S`）。原因：`scenario_reset` 复位前置要求 gt 年龄 ≤ `readback_max_age_s` = 0.5 s，仅看服务存在会让 `start` 早于 gt / 桥就绪 → `gt_stale` → 重试耗尽 → `reset_failed` 假 infra。**不以固定 `sleep` 代就绪**。

### (d) 覆盖矩阵：backend / mode × 各轴，逐轴标注

以 `lightweight / full` × `GUI(headless / gui)` × `task_start` × `own_takeover(release_control)` × `target_motion` × `real_terminal` 构造**覆盖矩阵**；每格标 **covered / uncovered / not_applicable** + **evidence 出处**（产物路径 / 源文件事实）+ 未覆盖的**如实原因**。矩阵由 `check_coverage_matrix.py` 静态核验源文件（后端能力列）+ 读产物生成，落 `<run_id>/coverage_matrix.md`。

- **backend 能力列**（源文件事实）：`lightweight` = 0 PX4 实例 / 0 Agent / 无空中节点 / 无 takeover 服务端；`full` = 2 PX4 实例 / 2 Agent / 4 空中节点（`px4_adapter` / `takeoff_controller` / `trajectory_tracker` / `standoff_follower`）/ 有 takeover 服务端。
- **未执行轴一律标 uncovered 并写明原因**；`own_takeover` 在轻量为 **not_applicable**（源事实：轻量栈不含空中链路），**不**以命名推定已覆盖。

### (e) 同一 run 因果记录（探针，非节点代码）

`w6_r025_full_probe.py` 在**已运行**的整链 launch 上执行，在**同一 run**（同一 `run_id` / 同一进程时间线）回答全部 5 问：

1. 等 `/agc/air/active_controller` 出现（`takeoff_controller`）→ 再额外等己方起飞到悬停；
2. 调 `/agc/air/release_control`（Trigger）→ 等 `active_controller` 翻转为 `trajectory_tracker`（**己方接管证据**）；
3. 调 `/agc/task/start`（Trigger）→ 记 `success` + `message`（`started: AIR_SEARCH` = **start OK**）；
4. **墙钟**看门狗等**任一终态**（超时则如实 `terminal_reached=false`）；
5. 全程记时间线（各事件墙钟时刻 + 仿真时刻 `/clock`）。

产物 `<run_id>/same_run.json`：`causal_record.start_ok` / `own_takeover`（`active_controller_before/after` + `takeover_ok`）/ `target_motion`（`classified` + `stats`）/ `capture` / `jam` / `terminal`（`state_name` + `reason_code` + `reached`），外加 `equipment`（双 PX4 配置 / 2 Agent / 入侵者 armed + nav_state）与 `full_chain_executed`。**所有 bool 均取自真实观测**，**不**伪造。

### (f) pass 命题化（pass ↔ 明确验收命题强绑定）

- `episode_runner.py`：每 episode 与 campaign report 加 `backend="lightweight"` / `launch=` 标注；每 episode 加 `proposition`（由 `expected_terminal` / `expected_reason` / `backend` 生成，如「轻量栈（headless）在 s08 达 `INTERCEPT_CONFIRMED(CAPTURE_NET)`（**非整链 / 非GUI 验收**）」）与 `pass`（= `expected_match` **且** backend 已标注）；report 加 `coverage` 汇总块（逐轴 value + evidence）。
- `same_run.json` 亦给 `proposition` 与 `pass`。
- **不**把「期望字符串匹配」自动等价为整链 /GUI 验收。

### (g) 轴 → 承载者登记与启动时校验（r-026）

新增 `src/agc_task/config/scenario_carriers.yaml`，逐轴值映射到承载它的**节点 / 参数 / 文件**，并标 `supported` 与 `requires_air_link`：

- **target_motion** `static|linear|maneuver` → `intruder_driver`（`px4_ns=px4_1`），`requires_air_link`；
- **obstacle** `none|static` → 世界障碍生成（`world_obstacles`）+ `obstacles_file`；`dynamic` → `supported: false`（**无承载者**）；
- **perception** `nominal|dropout|fov` → ~~`target_source=air_fusion` + 传感器通道文件（`sensors_file`），`requires_air_link`~~
  **（2026-11-04 失效，见下）**：`air_fusion` 已退役，两 backend 的 `target_source` 均为 `gt_adapter`；
  **2026-11-06 续**：`air_perception` 节点连同 `sensors_file` 与整条 `perception` 轴**已删除**
  （此前三档行为即已相同）；`no_target` 档的 `content` 登记一并移除（`s17` 已不在回归矩阵中）。
  详见 [`路线分支治理.md`](../conventions/路线分支治理.md#rule) 的退役台账与 ADR-0009 (b)；
- **outcome** → `task_manager`（+ `capture_adjudicator` / `jammer`）。

各场景在 `scenarios.yaml` 增 `support_status`（`supported` / `unsupported:<axis>`）；`s05` / `s12`（`obstacle=dynamic`）标 `unsupported:obstacle`。

**启动时校验 + 显式拒绝运行**：顶层 launch 对每个声明轴值查承载者登记；**无登记 / `supported:false` / `unsupported:<axis>` → `raise`（拒绝运行）**并给出显式原因。**SHALL NOT** 以命名当执行。

### (h) 正负对照的承载实现

- **perception**：`perception_bringup.launch.py` 增 `sensors_file` / `obstacles_file` 两个 launch 参数（缺省 = 包内默认）；`nominal` → `perception_sensors.yaml`（`drop_prob=0`、标称 FOV）、`dropout` → `perception_sensors_dropout.yaml`（`drop_prob=0.3`、`drop_burst_*`）、`fov` → `perception_sensors_fov.yaml`（`hfov 30 / vfov 20`）。
  ~~整链以 `target_source=air_fusion` 承载（通道模型经 `/agc/air/obs` 落入 `/agc/targets`）~~
  **2026-11-04 失效**：`air_fusion` 退役后 `/agc/air/obs` 无人订阅，上述三档**只改配置不改行为**。
- **obstacle**：`world_bringup.launch.py` 增 `world_obstacles` 选择——`static` 用原世界；`none` 由**单一真源** `world_geometry.yaml` / base world **按域派生**生成运行期世界（**不**手写第二份完整 world、**不**改世界物理）；`obstacles_file` 对应 `obstacles_none.yaml`（空）/ `obstacles.yaml`。
- **target_motion**：整链由 `intruder_driver` 承载；整链空中节点参数改为 `air.yaml` 基参 + `scenarios.yaml` 场景覆盖**合并后注入**（不再是独立 `air.yaml`）。

### (i) 运行时证据 `scene_manifest` 与「实际 == 声明」

顶层 launch 生成 `scene_manifest.json`（声明轴 + 承载者 + 状态 + 实际生效参数 / 文件 + 断言 + `support_status`），经参数 `scene_manifest_file`（及 `params_file`）**单一注入**给 `run_logger`，由 run_logger 拷入 run 的 `config/`。launch 内**断言**实际生效参数 == 声明轴，不符即拒绝运行。

**轻量栈覆盖账本 `not_carried`**：承载者需空中链路而后端为轻量栈时，运动轴与感知轴在 manifest 与 runner 报告中标 **`not_carried`**；runner 对 `unsupported` 场景**拒绝运行**（跳过并记原因）。**不**把轻量栈的声明轴谎称为已执行。

### (j) 未覆盖轴的边界与验证

- 本修复**只**在 run 产物（`report.json` / `same_run.json` / `coverage_matrix.md`）如实标注后端与模式，**不改**契约文字；headless 产物**只作辅助证据**，定性验收仍需 GUI 材料。
- 新增的仅为**非 ROS 接口**的 run 产物与**只读**探针；`/agc/task/capture_event` / `/agc/task/jam_confirm` 仍是 `std_msgs/String` **配套事件**（**非**命令者）；`/agc/task/capture_hit` 仍**恰为** `CAPTURE_NET`；**未**新增第二 ROS 命令者；冻结 **9 消息**（`src/agc_msgs/`）字段 / 顺序**未改**。
- 验收脚本：`run_w6_r025.sh`（Phase A 轻量 → Phase B 整链 → Phase C 核查）、`run_w6_r026.sh` + `check_scene_axis_carriers.py`（轻量实跑 none/static/linear/maneuver/dropout/fov 采集 manifest 与「none 世界生成」产物，验证 dynamic 拒绝运行）、`run_w6_r031.sh` + `check_runner_acceptance_layers.py`（三层判定 / 缺 summary / 空集合 / 报告三层全过 / 脚本卫生 / 9 消息 ABI）。产物落 `experiments/w6-task-eval/<run_id>/{manifests,worlds,runner,lightweight,metrics/*.json,log}`。

## 不做什么（边界）

- **不**把「期望字符串匹配」当整链 / GUI 验收；**不**把轻量栈声明轴谎称为已执行。
- **不**改契约文字以允许 headless 验收（属契约裁定，非本批）。
- **不**把整链整段纳入批量 runner（需双 PX4，成本高）；改用**同一 run 探针**补证。
- **不**为 `obstacle=dynamic` 新建执行节点、**不**改世界物理；显式 `unsupported` 更诚实。
- **不**剔除缺 summary 回合的分母，**不**以 0 冒充空集合。
- **不**用裸名 `pkill` / `rm -rf`；**不**改冻结 9 消息 ABI、**不**新增第二 ROS 命令者。

## Considered Options

- **继续只看 `expected_match`** —— 被否：缺 summary / 缺日志 / 基础设施失败仍可假绿。
- **缺 summary 剔除分母** —— 被否：选择性减少分母会系统性抬高成功率。
- **`wait_terminal` 仅看状态字符串** —— 被否：无法区分本回合终态与旧回合污染。
- **`SIGINT` 后固定 `sleep` 再 `SIGKILL`** —— 被否：不确认退出，且固定等待非就绪协议。
- **维持现状（轻量 PASS 视同整链完成、无 backend/mode 标注）** —— 被否：即整链范围的缺口。
- **仅文档标注、不改参数流** —— 被否：声明轴仍与执行脱节，因果结论仍无效。
- **为动态障碍新建执行节点 / 改世界物理** —— 被否：新增命令者或改物理触红线，且只需如实标注。
- **在 `scenarios.yaml` 内联承载者** —— 被否：承载者与场景登记耦合、多场景共享轴值会重复。

## Consequences

- **正面**：回合 PASS 需三层全必过；缺 summary 不剔分母且如实报缺失比例；终态以本 episode 窗口关联；进程组每步 `wait` 确认；声明轴必有承载者（缺则拒启动）；`dynamic` 明确 `unsupported`；`none/static`、`nominal/dropout/fov` 有真实正负对照；轻量栈未执行轴如实标 `not_carried`；整链证据含 `start OK` + 己方接管 + 目标运动 + 捕获 / 干扰 + 真实终态，且与 `equipment` 同源。
- **代价 / 限制**：新增字段（`layer_*` / `metric_completeness` / `summary_present` / `proc_exit_confirmed` / `state_run_verified`）均为 run 产物字段，未改 ABI；轻量栈**仍不执行**运动轴与感知轴（如实标注，非冒充）；整链 `perception=dropout|fov` 的**观测级**证据需双 PX4 实跑方可产出，本批只保证承载接线与 manifest 落地。
- **未决 / 后续**：整链 runner 调用（含 GUI / full）属后续；`w6_r031_check` 的 Case b/c 为**纯函数级**逻辑验证（不跑仿真），已如实标注。

## 参考

- 契约：[#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints) / [#terminal-semantics](0014-task-fsm-and-scenario-transaction.md#terminal-semantics) / [#params](0020-package-boundaries-and-runtime-topology.md#params) / [#messages](0020-package-boundaries-and-runtime-topology.md#messages)
- 相关决策：[ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与证据纪律）、[ADR-0016](0016-episode-window-and-sample-validity.md#top)（episode 窗口与样本有效性）、[ADR-0014](0014-task-fsm-and-scenario-transaction.md#top)（任务 FSM 与终态）、[ADR-0021](0021-gui-headless-equivalence.md#top)（GUI / headless 等价与平台冻结）、[ADR-0007](0007-scene-geometry-single-source-and-layout.md#top)（场景几何真源）
- 证据：`experiments/w6-task-eval/20261016-w6-r025-0/`（`coverage_matrix.md` / `same_run.json` / `metrics/r025.json`）、`<run_id>/metrics/r026.json`、`<run_id>/metrics/r031.json`
