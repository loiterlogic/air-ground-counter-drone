# W8 出口分层、GUI/headless 等价设计与执行闸门

> **现行测量状态（2026-10-26）**：gate=`not_evaluable_as_specified`。测量 P1 结果见 [ADR-0098](0098-w8-determinism-probe-and-measurement-spec-change.md#redo)，未来等价门的指标语义及集合由 [ADR-0099](0099-w8-fixed-budget-mission-fco-measurement.md#metric) 取代；以下 2026-10-25 的 pilot、设计与不可行判断保留为历史记录。新记录器和 plan v2 尚未冻结。

## Status

deferred（2026-10-25：GPU-GUI 修正 pilot 完成；项目默认 GUI 渲染后端 `auto` 已落地；RTF 与 headless 对齐，但 active FCO / 率类散布大，δ≤0.05、n≤40 下正式等价不可行；gate `not_evaluated`；headless 规模统计未授权）

## Date

2026-10-25

## 背景

W8 在 Runbook 中原写作“新旧实现同场景、同种子各跑 N 次；出对比报告；ROS1 归档只读”。该表述把两个不同问题压在一起：

1. **平台行为对照与冻结**：ROS1 / ROS2 在定义场景、种子与容差下是否行为一致，随后冻结平台；
2. **修复后科研确证**：在 [ADR-0091](0091-fire-control-inflight-lifecycle-decoupling.md) / [ADR-0092](0092-moving-target-costmap-marking-and-replan-policy.md) / [ADR-0094](0094-uxrce-participant-warmup-and-px4-stagger.md) 修复后的平台上，P1 / P2 命题是否仍成立。

两者证据不可互替：前者是平台一致性，后者是科研判定；后者须新预注册（[ADR-0086](0086-decision-rule-three-state-ci-versus-mme.md) 三态语义、[ADR-0088](0088-mme-change-governance-independent-justification-and-seed-isolation.md) MME 治理）。

同时，平台侧的 **GUI / headless 等价门实际未通过**。[ADR-0095](0095-w7c-admission-metric-and-worker-run-dir-isolation.md) 的复核只有 n=1 的成功 GUI：P1 GUI 首跑 `MISSION_FAILED(TIMEOUT)`，重跑 active FCO 0.0004 vs headless 0.0682；P2 seed0 GUI 0.0311 vs headless 0.0625；结论为“等价未建立 / 证据不足”。按 [ADR-0057](0057-c3-gui-acceptance-scope-authorization.md)，headless 仅可用于规模统计，前提是完成 GUI ↔ headless 等价核验；不能用“不显著”代替“等价”。

W7-c 已按 [ADR-0095](0095-w7c-admission-metric-and-worker-run-dir-isolation.md) **deferred**，单 worker 被显式接受。因此 W8 不等待并行扩容，直接用普通单 worker 做模式等价；B3 的 `cmd_vel_loopback_missing`（ground lifecycle 未 activate）保留为独立 infra 项。

## 决策

### (a) W8 出口分层

W8 拆为两个互不替代的出口：

- **W8-E1 平台行为对照与冻结**：GUI/headless 模式等价（前置）→ ROS1/ROS2 行为对照（同场景、同 seed、C1–C10 容差、终态语义一致）→ 平台冻结。
- **W8-E2 修复后 P1/P2 科研确证**：在修复后平台上，按**新预注册**重新检验 P1 / P2；遵循 ADR-0086 三态语义与 ADR-0088 MME 治理。

本 ADR 只覆盖 **W8-E1 的 GUI/headless 模式等价阶段**（pilot + 条件性正式等价）。ROS1/ROS2 对照与平台冻结不在本变更；W8-E2 不进入。

历史 pre-fix 结论原样保留并标注 `pre-fix`：P1 v5 = `inconclusive`、P2 v3 = `falsified` / 保留 c2、P2 v2 = `confounded`（[ADR-0093](0093-w7b-exit-closure-and-prefix-provenance.md)）。本 ADR 不改写任何 verdict。

### (b) Pilot 预声明设计

计划文件：[`src/agc_rl/config/w8_gui_headless_plan.yaml`](../../src/agc_rl/config/w8_gui_headless_plan.yaml)（version 1，2026-10-25，`frozen_before_runs`）。

- sha256：`3afa82c42041f23dd343ac17532920811fec0153c4ab554fff2f3213ca7aa292`
- 条件：P1 `s15_static_none_fov_capture` / `p1_coop` / seed 5；P2 `s08_static_none_nominal_capture` / `p2_rl_high` / seed 0；每场景每模式 **5** 次。
- 固定条件：`backend=full`、普通单 worker、`--infra-retries 0`、`--obs-horizon-s 60`、`--timeout 240`、`--ready-timeout-s 180`、`--start-timeout-s 60`；PX4 启动按 ADR-0094 默认（own 25 s / intruder 35 s / warmup 关闭 / air odom 门）。
- 唯一差异：`--mode gui|headless`（gz `-r` vs `-s -r`；ROS 节点图相同）。
- 交替：P1 `H,G,H,G,H,G,H,G,H,G`；P2 `G,H,G,H,G,H,G,H,G,H`（起始模式跨场景相反）。
- 保留：每次 attempt 新 `run_id`；全部尝试保留（含 mission failure / timeout / infra）；不重跑替代；不自动重试。

pilot 只用于估计 **within-mode 散布**与成本，**不是**等价判定，不授权 headless 规模统计。

### (c) 完整任务结果口径

逐 attempt 报：终态 / `outcome_class`、active FCO、active 可见率、`env_occ|visible`、active 窗口、首次 FCO、首次包络进入、捕获时间、首发 / 射击数、最小净空、干预段数 / 拍比例 / 时长、RTF、墙钟、硬不变量。

- 超时按契约 C4 算 mission 失败并保留在分母；infra 单列；**不**只比较成功回合。
- 未发生事件：首次 FCO / 捕获 / 发射 → `null` + `occurred=false` + occurrence rate；不插补；另报 ITT 敏感性（仅敏感）。
- 率类分母 = mission attempts（成功 + mission 失败）；infra 不进分母。

### (d) 正式等价设计

正式等价在 pilot 后以 plan v2 冻结，不得在正式结果后回填 / 放宽 δ 或 n。

- **判定规则**：`Δ = GUI − headless`；等价 iff 95% 双侧 CI 完全落入 `[−δ, +δ]`（等价检验；报告两个单侧 p）。**禁止**以“差异检验不显著”“CI 覆盖 0”“pilot Δ 小”代替等价。
- **co-primary**（全部须通过，交集-并集）：active FCO、active 可见率、超时率、捕获成功率。
- **secondary**：首次 FCO occurrence rate / 条件时间、捕获条件时间、最小净空（GUI 非劣）、干预拍比例 / 段数（GUI 非劣）、RTF / 成本（描述）。
- **δ 工程依据**：决策相关性（相对当前 MME=0.10 的量级；配对臂差中模式主效应的抵消条件）、within-mode 重复性底噪、安全非劣（净空 / 干预相对 C2 / C6 / C7 的口径）。候选锚点：FCO / 可见率 0.02；超时率 / 捕获成功率 0.05；时间 2 s；净空 0.20 m；干预比例 0.05。最终值由 pilot 后论证。
- **样本量**：`n_per_mode = ceil((z_0.975 + z_0.80)^2 (σ_GUI^2 + σ_headless^2) / (δ − |Δ_pilot|)^2)`；多个 co-primary 取最大 n；`|Δ_pilot| ≥ δ` 判为在该 δ 下不可行；率类接近 0/1 时预声明精确 / 角变换方法。
- **成本上限**：默认每场景每模式 ≤40 attempts 且每场景正式墙钟 ≤6 h；可更低；超过上限不执行正式 run。

### (e) 执行闸门与回退

- **正式 go**：每场景 / 模式至少 3 个有效 mission attempts；`|Δ_pilot| < δ`；n ≤ 成本上限。
- **等价 pass**：全部 co-primary 的 95% CI 落入 ±δ；secondary 无未解释 material difference；infra 率不高于预声明上限；硬不变量无缺陷。⇒ 授权 headless 用于 W8 规模统计，产物标 `backend` / `mode`，GUI 定性 / 关键场景验收仍保留。
- **等价 fail / 不可行**：不授权 headless 规模统计；定位模式差异（RTF / 渲染 / 调度 / 启动时序）或改用 GUI 完成相应验证并记录成本；不静默切换。

### (f) Infra 单列

B3 的 `cmd_vel_loopback_missing`（ground lifecycle 未 activate、240 s、0 shot）是独立 infra 项，不归因于 GUI/headless 或隔离栈。普通单 worker 若复发，先判断是否系统性；反复出现则专项排障，不继续扩容。W7-c 保持 `deferred`。

### (g) 项目默认 GUI 渲染后端（2026-10-25 追加）

用户裁定将 **GPU-GUI 设为项目默认**（方案 B）。实现为单一 launch 参数，而不是全局 `export`：

- **参数**：`gui_render_backend=auto|d3d12|software`，默认 **`auto`**；只在 GUI（`gz sim -r`）生效，headless（`gz sim -s`）忽略。
- **`auto`**：WSL2（内核串含 `microsoft`/`wsl`）+ `/dev/dxg` + X11（`DISPLAY` 含 `:`）→ 注入 `MESA_LOADER_DRIVER_OVERRIDE=d3d12` + `GALLIUM_DRIVER=d3d12`；原生 Linux 保持系统默认 GL（硬件 GL，无 GPU 时自然回退）；无 `/dev/dxg` 或非 X11 不强行 D3D12。
- **`d3d12`**：显式强制 Mesa D3D12 + X11（不支持时 GUI 可能起不来，属于显式选择）。
- **`software`**：显式强制 llvmpipe（`LIBGL_ALWAYS_SOFTWARE=1` + `MESA_LOADER_DRIVER_OVERRIDE=swrast` + `GALLIUM_DRIVER=llvmpipe`），用于复现软件 GUI 基线。
- **注入点**：`w6.launch.py` → `world_bringup.launch.py` 的 gz 启动前 `SetEnvironmentVariable`；选择逻辑单一来源 [`gui_render_backend.py`](../../src/agc_sim/launch/gui_render_backend.py)。
- **实际 renderer 记录**：`episode_runner` 在 GUI 启动前记录 OGRE 日志游标，启动后 / 结束后只解析**本 run 窗口内**新增的 `Device Name` / `GL_RENDERER`；`gui_renderer` + `gui_renderer_status` + 有界证据写入 `arms.json` 与 W8 `attempts.json`。读取失败 / 轮转 / 多值 → `null` + 状态，不以批次 `render_backend` 回填。
- **预注册固定**：plan v1（软件 GUI）在编排层固定 `software`；plan v1.1（GPU-GUI）固定 `d3d12`（`mesa_d3d12_x11` → `d3d12`）。这样项目默认 `auto` 不会让历史 pilot 条件漂移。
- **冒烟证据**：`d3d12` 全链 → `gui_renderer=D3D12 (NVIDIA GeForce GTX 1050 Ti)`；`software` 全链 → `gui_renderer=llvmpipe (LLVM 20.1.2, 256 bits)`；`auto`（项目默认）全链 → `gui_renderer=D3D12`；三次均 `INTERCEPT_CONFIRMED`。`auto` 的 launch 日志为 `gui_render_backend=auto -> d3d12`。

**边界**：项目默认 GPU-GUI **不改变** W8 等价闸门；headless 规模统计仍未授权，正式等价仍 `feasible=false`，ADR 状态仍 `deferred`。换到无 `/dev/dxg` 的机器时 `auto` 自动回退，不保证 GPU；需要 GPU 的证据须显式 `d3d12` 并以逐 run 有界证据记录实际 renderer。`gui_renderer` 不再读取共享日志的“最近一次”；证据限定在本 run 窗口内，日志轮转 / 并行写入时标 `ambiguous` 或 `missing`。W8 仍单 worker；W7-c 仍 `deferred`。

## 结果

### Pilot

pilot 已完成 20 个预声明 attempt（P1 `s15` / `p1_coop` / seed 5；P2 `s08` / `p2_rl_high` / seed 0；每模式 5 次）。报告：`experiments/w8-parity/20261025-w8-gui-headless-pilot/metrics/gui_headless_pilot.{json,md}`。

- P1 headless：3 capture + 1 `MISSION_FAILED(TIMEOUT)` + 1 `INFRA_FAILURE(clock_not_progressing)`；P1 GUI（默认软件渲染）：4 capture + 1 `INFRA_FAILURE(reset_failed)`（另有一次电脑中断，残缺 log 保留在 `...-p1-g-05-interrupted/`，不计入分母）。
- P2 headless：5 capture + 0 infra；P2 GUI（默认软件渲染）：4 capture + 1 `INFRA_FAILURE(cmd_vel_loopback_missing)`（B3 签名在普通单 worker 复发）。
- active FCO 描述性差：P1 Δ=−0.0660（95% CI [−0.234, +0.103]）；P2 Δ=−0.0268（95% CI [−0.123, +0.069]）。within-mode 散布很大（P1 headless SD≈0.112、GUI SD≈0.046；P2 headless SD≈0.078、GUI SD≈0.008）。
- 按候选 δ（FCO / 可见率 0.02；率 0.05）的正式设计输入：P1 全部 co-primary `infeasible（|Δ_pilot| ≥ δ）`；P2 active FCO / 可见率 `infeasible（|Δ_pilot| ≥ δ）`。⇒ 在当前软件 GUI 数据下，**两场景均不可行**。

### 渲染后端诊断（2026-10-25 追加）

用户提出“GUI 与 headless 差异可能来自电脑性能 / GUI 未走显卡”。诊断确认：

- **默认 GUI 走 llvmpipe 软件渲染**：`~/.gz/rendering/ogre2.log` 的 `Device Name: llvmpipe (LLVM 20.1.2, 256 bits)`、`GPU Vendor: unknown`；`nvidia-smi` 进程列表只有 `/Xwayland`，没有 `gz sim gui`；GUI 的 `gz sim` CPU **267–281%**，headless 仅 **22%**。
- **强制 `MESA_LOADER_DRIVER_OVERRIDE=d3d12 GALLIUM_DRIVER=d3d12`（X11）可走 GPU**：Ogre2 日志 `GL_RENDERER = D3D12 (NVIDIA GeForce GTX 1050 Ti)`；GPU util 16–18%、显存 753–754 MiB、CPU 127–141%；整链 GPU-GUI 的 RTF 0.80–0.87，接近 headless。
- **Wayland+D3D12 失败**：`libEGL warning: egl: failed to create dri2 screen`；本机 GPU-GUI 只能走 X11。
- **GPU-GUI 诊断批次**（每场景 3 次，非 pilot 分母）：P1 active FCO 0.0563 / 0.0179 + 1 `reset_failed`；P2 0.0438 / 0.0196 + 1 `TIMEOUT`；RTF 0.80–0.87。结果仍落在软件 GUI / headless 的散布范围内，n=3 不能证明“差异全部由性能造成”，也不能证明等价。

**结论**：默认 GUI 的软件渲染与 CPU 争抢是**已确认的性能混杂**；pilot 的 `mode` 变量同时混入了“渲染后端 + CPU 负载”。因此 **pilot 的软件 GUI 数值不能直接用于冻结 δ / n，也不能读作 GUI/headless 语义不等价**。详细证据：`metrics/gpu_renderer_diagnosis.{json,md}`。

### GPU-GUI 修正 pilot（2026-10-25 追加）

用户选择 **GPU-GUI 重跑**。修正计划：[`w8_gui_headless_gpu_plan.yaml`](../../src/agc_rl/config/w8_gui_headless_gpu_plan.yaml) v1.1（sha256 `f34aa10e…7f82`，run 前冻结；base plan v1 未修改）。GUI 侧设置 `MESA_LOADER_DRIVER_OVERRIDE=d3d12` + `GALLIUM_DRIVER=d3d12`（X11）；每次 GUI attempt 的 renderer 均为 `D3D12 (NVIDIA GeForce GTX 1050 Ti)`。20 attempts（P1/P2 各 5 headless + 5 GUI），全部保留；报告：`experiments/w8-parity/20261025-w8-gui-gpu-pilot/metrics/gui_headless_pilot.{json,md}`。

- **RTF 已对齐**：P1 GUI 0.9439 vs headless 0.9506，Δ=−0.0067（95% CI [−0.0298, +0.0165]）；P2 GUI 0.9517 vs headless 0.9602，Δ=−0.0084（95% CI [−0.0216, +0.0048]）。软件 GUI 的 RTF 差距（约 0.05–0.10）消失。
- **结果散布仍主导**：P1 active FCO GUI 0.0659（SD 0.0833）vs headless 0.0262（SD 0.0272），Δ=+0.0397（95% CI [−0.0621, +0.1415]）；P2 GUI 0.0784（SD 0.1308）vs headless 0.0500（SD 0.0678），Δ=+0.0284（95% CI [−0.1667, +0.2235]）。P1 两侧各 1 次 timeout；P2 GUI 1 次 `INFRA_FAILURE(air_hover_timeout)`、headless 2 次 timeout。
- **可行性**：按候选 δ（FCO / 可见率 0.02；率 0.05），P1 的 FCO / 可见率 `|Δ|≥δ`，率类（4/5 vs 4/5）所需 n≈**1256/模式**；P2 率类 `|Δ|=0.4`，FCO / 可见率 `|Δ|≥δ`。**两场景 feasible=false**。

**结论**：GPU-GUI 修复了渲染 / 性能混杂，但平台随机散布使 **δ≤0.05、n≤40/模式 下的正式等价不可判定**；闸门维持 `not_evaluated`，headless 规模统计未授权。下一步是范围裁定（配对臂差 / 模式作协变量、GUI 完成关键验证、扩大预算或换平台），不是继续硬跑正式等价。

### 正式等价

**未执行**。原因：① 默认 GUI 软件渲染混杂已由 GPU-GUI 修正，但修正后的 pilot 仍 `feasible=false`（δ≤0.05、n≤40/模式下不可判定）；② 下一步须先做范围裁定（配对臂差 / 模式作协变量、GUI 完成关键验证、扩大预算或换平台）；③ 在裁定前不冻结 plan v2。

### 闸门

`not_evaluated`。headless 规模统计**未授权**；W8-E2 未进入。GPU-GUI 修正 pilot 已完成（RTF 对齐，但 δ≤0.05 / n≤40 下等价不可行）；下一步是范围裁定（配对臂差 / 模式作协变量、GUI 完成关键验证、扩大预算或换平台）。

## 后果

- **正面**：W8 的两个问题不再混用证据；GUI/headless 判定从“单次对比”升级为预声明等价检验；headless 规模统计有明确授权条件；B3 infra 不再被误读为模式效应。
- **代价**：pilot 至少 20 次整链 run；正式等价可能需要更多；GUI 墙钟与环境噪声可能使等价不可判定，需回退到 GUI 验证并记录成本。
- **限制**：本 ADR 只覆盖 W8-E1a 模式等价阶段；W8-E1b 历史证据对照与条件平台冻结见 [ADR-0097](0097-w8-historical-parity-and-conditional-platform-freeze.md)；W8-E2 未进入。

## 参考

- 契约：[#hard-constraints](../ROS2迁移交接文档.md#hard-constraints)、[#terminal-semantics](../ROS2迁移交接文档.md#terminal-semantics)、[#execution-port](../ROS2迁移交接文档.md#execution-port)
- 前序 ADR：[ADR-0057](0057-c3-gui-acceptance-scope-authorization.md)、[ADR-0086](0086-decision-rule-three-state-ci-versus-mme.md)、[ADR-0088](0088-mme-change-governance-independent-justification-and-seed-isolation.md)、[ADR-0093](0093-w7b-exit-closure-and-prefix-provenance.md)、[ADR-0094](0094-uxrce-participant-warmup-and-px4-stagger.md)、[ADR-0095](0095-w7c-admission-metric-and-worker-run-dir-isolation.md)、[ADR-0007](0007-experiment-artifacts-convention.md)、[ADR-0064](0064-evidence-immutable-archive-and-intake-manifest.md)
- 计划：[`w8_gui_headless_plan.yaml`](../../src/agc_rl/config/w8_gui_headless_plan.yaml)
- spec：[`w8-parity-freeze`](../archive/specs/w8-parity-freeze/spec.md)

<a id="measurement-amendment"></a>
## 2026-10-26 测量 P2 修订边界

[ADR-0099](0099-w8-fixed-budget-mission-fco-measurement.md#endpoints) 取代未来设计中的 co-primary 集合：固定预算任务 FCO、完整任务捕获成功率、超时率；active FCO / 可见率降为 secondary。旧计划和既有产物不回写；P3 须先实现新记录器，再预声明新设计、界限、n 与成本。当前不执行本 ADR 历史设计中的 go 规则，不授权 headless 规模统计。
