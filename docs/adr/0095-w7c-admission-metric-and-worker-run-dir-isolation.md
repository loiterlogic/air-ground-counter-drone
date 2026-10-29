# W7-c 扩容准入指标修正、单 worker 重复性诊断与 PX4 运行目录隔离

## Status

deferred（2026-10-25：指标修正与隔离设计已落地；A/B 门因 B3 `INFRA_FAILURE` 未通过，显式保留单 worker；W7-c 并行准入 deferred）

## Date

2026-10-25

## 背景

W7-c 在 C5 被标记 `deferred`（[ADR-0077](0077-w7c-multi-worker-isolation.md)(l)）：两 worker 试验的 worker 0 `vis_rate=0.2292` 低于 C1 串行包络下界 `0.5208`。uXRCE 已由 [ADR-0094](0094-uxrce-participant-warmup-and-px4-stagger.md) 恢复；阻塞点转为三件：

1. **准入指标口径错配**：C1/C4 比较使用 `window_fixed_v1` 的 `fire_control_opportunity_rate` / `visibility_metrics.visibility_rate`，含终态后停泊。原始产物的 active 指标（`episode_window_metrics`）为：

| run | active FCO | active 可见率 | env_occ\|visible | 窗口 enter→leave（sim s） |
|---|---:|---:|---:|---|
| `c1-serial-01` | 0.2158 | 0.9813 | 0.2199 | 30.800→46.844 |
| `c1-serial-02` | 0.0053 | 0.9841 | 0.0054 | 30.940→49.880 |
| `c1-serial-03` | 0.0779 | 0.9920 | 0.0785 | 29.360→54.032 |
| `c4-trial3/worker_0` | 0.0516 | 0.9919 | 0.0521 | 56.236→66.788 |
| `c4-trial3/worker_1` | 0.0052 | 0.9843 | 0.0053 | 29.496→46.268 |

- 串行 active FCO 自身散布 0.0053–0.2158（约 40 倍），active 可见率稳定在 0.981–0.992；差异几乎全部来自 `env_occ|visible`，即包络内停留 / 捕获时序。
- legacy 固定窗下 C4 worker 0 `vis_rate=0.2292` 低于 C1 下界 `0.5208`；active 口径下两 worker 可见率（0.9919 / 0.9843）均在串行范围内，worker 0 active FCO 0.0516 在串行范围内，worker 1 0.0052 仅低 0.0001。⇒ **C4 旧数值不能归因于并行负载**。

2. **PX4 可写运行文件仍共享**：own / intruder / warmup 三个 PX4 进程以 `cwd=build/px4_sitl_default` 启动，共用 `dataman`、`parameters*.bson`、`log/`、`eeprom/` 与 `etc/init.d-posix/px4-rc.params`。

3. **同 seed 散布未被时间线解释**：C4 worker 0 的 active 窗口起点 56.2 s，`start OK -> AIR_SEARCH` 墙钟比 worker 1 晚约 30.7 s；需区分启动状态 / 目标估计 / 物理散布。

4. **GUI / headless 未证明等价**：P1 GUI 首跑 `MISSION_FAILED(TIMEOUT)`，重跑 active FCO 0.0004（窗口 31.0→126.0 s）vs headless 0.0682（32.1→47.8 s）；P2 seed0 GUI active FCO 0.0311（32.9→56.3 s）vs headless 0.0625（31.2→44.0 s），legacy fixed FCO 0.1079 vs 0.7946。两次成功不构成等价证据。

## 决策

### (a) 准入 DV 改为 active-window 指标

- primary：`fire_control_opportunity_rate_active = episode_window_metrics.ticks_fire_control_opportunity / vis_ticks_total`；
- 可见性：`episode_window_metrics.visibility_rate`（active 窗口）；
- legacy `window_fixed_v1`（`arms.json.visibility_rate` / `fire_control_opportunity_rate`）降为**描述 / 历史**，不得用于准入判定。

### (b) C4 记录保留，不回溯改判

[ADR-0077](0077-w7c-multi-worker-isolation.md)(l) 的“DV 未通过 / 保留单 worker”原文保留。本节只说明其 legacy 数值与 active 口径不可比，**不**把 C4 改判为通过，也**不**把差异归因于并行负载。

### (c) 预声明分析计划（运行前冻结）

计划文件：[`src/agc_rl/config/w7c_admission_plan.yaml`](../../src/agc_rl/config/w7c_admission_plan.yaml)（version 1，2026-10-25，`frozen_before_runs`）。

- sha256：`9d70006925cd40f9849c5c3a0fd708c3657b5a737ebe2086fb593c715070d710`
- 条件：A 普通单 worker ×3；B 隔离单 worker ×3；A/B 交替；P 两隔离 worker ×3 对（仅门通过时）。
- 固定条件：`backend=full` / `s08_static_none_nominal_capture` / `p2_rl_high` / seed0 / headless / `--infra-retries 0`；启动协议按 ADR-0094 默认（own 25 s / intruder 35 s / warmup 关闭 / air odom 门）。
- 指标、分解、时间线轴、硬不变量、粗移门、归因规则、全部尝试保留、回退均见计划文件；首个 run 后不修改，偏离单独登记。

### (d) PX4 可写运行目录隔离

当 `px4_run_root` 显式设置时：

- own（实例 0）/ intruder（实例 1）/ warmup（实例 3）各用 `-w <root>/<instance_dir>`，各自独占 `dataman`、`parameters*.bson`、`log/`、`eeprom/`；
- worker 私有 `etc` 副本（含 `init.d-posix`）由 `lock_px4_failsafe_params.sh` 写入 `px4-rc.params`，共享 build 只读；
- 缺省空值保持既有命令 / cwd / 行为，历史 run 路径不变；
- A/B 从同一 canonical `parameters.bson` 初态出发，初态与共享 build 前后 sha256 记入 run `config/`。

### (e) 决策门

- **A/B 门**：B 硬不变量全过；共享 PX4 可写文件零写入；infra ≤ A；B active 窗口 `enter_s` 落在 A `[min−5 s, max+5 s]`；active 可见率 ≥0.90；active FCO 仅作粗移提示；无 `unexplained`。
- **P 门**：每个 P worker 硬不变量与事件身份通过；共享 build 只读；infra ≤ B 基线；窗口 / 可见率门同上；RTF 与窗口 ticks 足够；无跨 worker 污染；无 `unexplained`。
- 任一失败 → **显式接受单 worker**；P 通过只记录“当前主机并行可行”，不启动 W7-c 全量批跑。
- 若接受单 worker，另立 W8 执行规格（单 worker 吞吐 / 成本 / GUI 重复方案）。

## 结果（2026-10-25）

### A/B 隔离对照

run `20261025-w7-rl-b-repeat-ab`（A1–A3 / B1–B3，同 `s08` / `p2_rl_high` / seed0 / headless / `--infra-retries 0`，A/B 交替；canonical 参数初态 `b9addc2b…`）：

| 条件 | run | 终态 | active FCO | active 可见率 | 窗口 enter→leave（s） | 共享 build 写入 |
|---|---|---|---:|---:|---|---|
| A | a1 | `INTERCEPT_CONFIRMED` | 0.1606 | 0.9869 | 30.37→53.21 | 预期（A 走共享 cwd） |
| A | a2 | `INTERCEPT_CONFIRMED` | 0.0435 | 0.9896 | 32.16→51.32 | 预期 |
| A | a3 | `INTERCEPT_CONFIRMED` | 0.0318 | 0.9825 | 29.41→50.37 | 预期 |
| B | b1 | `INTERCEPT_CONFIRMED` | 0.0137 | 0.9863 | 29.56→44.22 | 0 |
| B | b2 | `INTERCEPT_CONFIRMED` | 0.0370 | 0.9792 | 31.36→45.68 | 0 |
| B | b3 | **`INFRA_FAILURE`** | — | — | — | 0 |

- **隔离通过**：B 3/3 `writes_detected.any=false`；私有 `instance_0/1` 各有 `dataman` / `parameters*.bson` / `.ulg`；A/B 参数初态 sha256 一致。
- **A/B 门不通过**：B3 为 `INFRA_FAILURE`（`cmd_vel_loopback_missing`，ground lifecycle 未 activate，wall 240 s，0 shot），导致 `hard_invariants` 失败与 `infra` 1>0；B1/B2 的窗口 / 可见率在 A 范围内，active FCO 粗移提示 false。
- **决策**：按预声明计划**不启动 P 两 worker 重试**，**显式保留单 worker**；W7-c 继续 `deferred`。B3 是 infra 事件，保留、不用成功重跑替代；隔离（PX4 可写文件）本身通过。B3 是隔离单 worker 条件下观测到的 ground lifecycle 激活失败 infra；n=3 不足以区分隔离栈与主机噪声，但按预声明门仍不通过。

### 同 seed 时间线解释

诊断报告 `experiments/w7-rl-b/20261025-w7-rl-b-repeat-ab-diagnosis/metrics/worker_repeatability.md`：

- 历史 C1 3 次的 active FCO 0.0053–0.2158 由 `env_occ|visible` 0.0054–0.2199 解释，active 可见率稳定 0.981–0.992；归因 **physical_scatter**（同 seed 下进入 1 m 火控包络的时机 / 停留拍数不同）。
- C4 worker 0 的 active 窗口晚至 56.24 s 归因 **startup_state**：release/start 墙钟晚约 30.7 s，start OK 仿真时刻仅差 0.97 s，窗口相对 start OK 晚 25.77 s；同期 own PX4 44 次 `invalid setpoints / Failsafe: blind land`。该证据只说明时间线因果链，不证明并行负载因果；C4 历史记录保持原样。
- A/B 的 6 个 case 中 B3 无窗口；其余归因见报告，`unexplained=[]`。

### GUI / headless

`experiments/w7-rl-b/20261025-w7-rl-b-gui-headless-recheck/metrics/gui_headless.md`：全部 7 个尝试保留（含 P1 GUI 首跑 `MISSION_FAILED(TIMEOUT)`，属 mission 终态、非 infra）；P1 headless active FCO 0.0682 vs GUI 重跑 0.0004，P2 seed0 headless 0.0625 vs GUI 0.0311；结论 **GUI / headless 数值等价未建立 / 证据不足**。

### W8 输入（因保留单 worker）

- 单 worker 吞吐：整链 headless 单 run 墙钟约 100–130 s（本次 A/B 的 A 侧 3 次均正常；B3 infra 240 s 不计入吞吐）。
- 成本：W8 若做 GUI/headless 等价，每条件至少 3 次（建议 5 次），同 scene / arm / seed，交替执行、全部尝试保留；primary 用 active FCO / active 可见率 / 窗口 / 首次 FCO，legacy 固定窗只作描述。
- W8 的样本量与 GUI 重复方案在独立 spec 中定稿；本 ADR 只输出输入。


## 后果

- **正面**：准入口径与 P2 v3 / P1 v4 的 primary 对齐；C4 的历史记录与勘误可区分；PX4 可写状态不再跨 worker / 跨 run 污染；同 seed 散布有可核验的时间线解释。
- **代价**：每次隔离 run 增加私有 `etc` 拷贝与 PX4 运行目录；A/B 需要 6 次整链 run + 1 次 smoke；n=3 只能做粗移检测，不能宣称数值等价。
- **未决**：参数初态形式（canonical 拷贝或空初态）按计划执行；W8 规格另立。

## 参考

- 契约：[#hard-constraints](../ROS2迁移交接文档.md#hard-constraints)、[#execution-port](../ROS2迁移交接文档.md#execution-port)、[#params](../ROS2迁移交接文档.md#params)
- 前序 ADR：[ADR-0077](0077-w7c-multi-worker-isolation.md)、[ADR-0083](0083-w7b-p2-arm-information-equivalence-and-active-window-fco.md)、[ADR-0084](0084-w7b-p1-active-window-dv-recheck.md)、[ADR-0074](0074-visibility-metric-fixed-observation-window.md)、[ADR-0094](0094-uxrce-participant-warmup-and-px4-stagger.md)、[ADR-0064](0064-evidence-immutable-archive-and-intake-manifest.md)
- 计划：[`w7c_admission_plan.yaml`](../../src/agc_rl/config/w7c_admission_plan.yaml)

## W8 输入（追加，2026-10-25）

本节只追加 W8 的输入链接，**不改写**上文 A/B 结果、W7-c `deferred` 结论与历史原文。

- W8 拆为 **W8-E1**（ROS1/ROS2 行为对照与平台冻结）与 **W8-E2**（修复后 P1/P2 科研确证）；本阶段只做 W8-E1 的 **GUI/headless 模式等价 pilot**。
- 预声明计划：[`w8_gui_headless_plan.yaml`](../../src/agc_rl/config/w8_gui_headless_plan.yaml)（v1，sha256 `3afa82c4…a292`）；决策与闸门：[ADR-0096](0096-w8-gui-headless-equivalence-design-bounds-and-gate.md)；spec：[`.trae/specs/w8-parity-freeze/`](../archive/specs/w8-parity-freeze/spec.md)。
- 渲染后端诊断：默认 GUI = llvmpipe 软件渲染（性能混杂）；GPU-GUI 可经 Mesa D3D12 + X11。产物 `experiments/w8-parity/20261025-w8-gui-headless-pilot/metrics/gpu_renderer_diagnosis.{json,md}` 与 `status_summary.md`；gate `not_evaluated`，headless 未授权。
- 本 ADR 的 B3 `INFRA_FAILURE`（`cmd_vel_loopback_missing`）在 W8 中作为**独立 infra 项**登记，不归因于 GUI/headless 或隔离栈。
- W7-c 仍 `deferred`；单 worker 保持接受；本阶段不启动并行扩容。
