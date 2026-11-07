<a id="top"></a>
# 多 worker 隔离与扩容准入

## Status

accepted（2026-11-02 由 ADR-0077 / 0095 合并；隔离机制与准入指标已落地，但 A/B 门因 1 次 `INFRA_FAILURE` 未通过，最终结论是**显式接受单 worker**—— 结论未变，见 (f) 末条与「结果」）

## 背景

的目标是把/b 的**单 worker 串行**评估扩为**同机多 worker 并行**。实测约束（不是推测）决定了可行做法：

1. **同机两个整链实例会互相污染**：`/dev/shm/fastrtps_*` 段、DDS 发现域、PX4 实例命名空间、uXRCE agent 端口、gz 世界名、产物目录全部共享。
2. **`/dev/shm` 段会累积**（单 run 约余 100 段），累积数百段即出现 SHM 端口初始化失败。
3. **uXRCE 客户端实体创建预算仅 1 s（PX4 硬编码）**：任何额外负载 / 拥塞都直接变 infra；多实例共用一个 agent 更易超时。
4. **本机 `ROS_DOMAIN_ID` 非 0 时 lifecycle 服务数据面不通**（实测 77/81：`ChangeState` 一律超时，话题仍正常）⇒ **不能**用"每 worker 一个 domain id"隔离。
5. **清场脚本不区分 worker 归属**，并行时后启动者会杀掉先启动者的进程。

另一个背景问题是**准入口径本身错配**：P1 / P2 的比较用的是 `window_fixed_v1`（含终态后停泊）的率，与 active 窗口的
primary DV 不可比，导致的结论被错误归因为并行负载。

## 决策

### (a) 隔离单元 = 每 worker 一个 rootless user+net namespace，而非 ROS domain

约束 4 封死了"按 domain 隔离"的常规做法；独立 netns 下每 worker 拥有独立 loopback，于是所有 worker 可**统一使用
`ROS_DOMAIN_ID=0`**（规避非 0 域缺陷）、DDS 发现（`LOCALHOST`）天然不出 netns、PX4 MAVLink / agent UDP 端口在各 netns
内互不冲突。实测：`unshare -Urn`（rootless user+net namespace）可用、`ip link set lo up` 在 namespace 内成功；本机
**没有** docker / podman，`unshare -n` 单独使用被拒绝（Operation not permitted）。

`/dev/shm` 仍为**全局共享**（POSIX shm 不随 netns 隔离），故所有 worker 进程须 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`——
关掉 SHM 传输，防跨 worker 互发现。

### (b) 每 worker 独占的资源（定稿）

| 资源 | 方案 |
|---|---|
| ROS 域 | `ROS_DOMAIN_ID=0`（netns 内 loopback 隔离） |
| DDS transport | 所有 worker 进程 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` |
| gz 分区 | `GZ_PARTITION=agc_w_<worker_id>`（每 worker 唯一） |
| `/tmp` | `unshare -Urnm` + private tmpfs `/tmp`（实测 25/25 同时启动时两 worker 争同一 `/tmp/px4_lock-<instance>`） |
| uXRCE agent 端口 | `8890 + 10*worker_id` / `+1`（netns 内本可复用，显式分配便于审计） |
| PX4 实例 | worker 内仍为 0 / 1（netns + 无 SHM 后不跨 worker 冲突） |
| 产物目录 | `experiments/<campaign>/<run_id>/worker_<worker_id>/` |
| run_logger 身份 | worker 模式注入 `run_id_override=<date>-<scene>-<seed>-<HHMMSS>-w<id>-<rand>`（实测同秒启动的两个 worker 撞过 run 目录） |
| 进程归属 / 挂载 | 所有 worker 进程继承 `AGC_WORKER_ID=<worker_id>`；每 worker 独立 mount ns，退出后 private `/tmp` 自动消失 |

gz 世界：每 worker **独立 gz 进程**（世界名可同名），**不建议**共享一个 gz 多模型—— 那会破坏"同世界同时钟 + episode
独立复位"的语义。

### (c) 清场归属与 `/dev/shm`

`sweep_stale_processes(worker_id)` 读取 `/proc/<pid>/environ`，**只**清理 `AGC_WORKER_ID` 等于本 worker 的进程；没有该
标记的进程**一律不杀**（属于其它 worker / 机器上其它系统）。`/dev/shm/fastrtps_*` 段清理仍为 worker 启动前的**人工 /
编排层**动作；**禁止**由 worker 自动 `rm -f /dev/shm/fastrtps_*`（会误删同机其它 worker 的段）。单 worker 模式
（`worker_id=None`）保持既有全局清场行为，不改变历史路径。

### (d) PX4 可写运行目录隔离

`main.launch.py` 提供 opt-in 参数 `px4_run_root`：设置后 own（实例 0）/ intruder（实例 1）/ warmup（实例 3）各用
`-w <root>/<instance_dir>`，各自独占 `dataman`、`parameters*.bson`、`log/`、`eeprom/`；worker 私有 `etc` 副本（含
`init.d-posix`）由 `lock_px4_failsafe_params.sh` 写入 `px4-rc.params`，共享 build 只读；缺省空值保持既有命令 / cwd /
行为，历史 run 路径不变。A/B 从同一 canonical `parameters.bson` 初态出发，初态与共享 build 前后 sha256 记入 run `config/`。

### (e) 准入指标：改用 active-window 口径

- primary：`fire_control_opportunity_rate_active = episode_window_metrics.ticks_fire_control_opportunity / vis_ticks_total`；
- 可见性：`episode_window_metrics.visibility_rate`（active 窗口）；
- legacy `window_fixed_v1`（`arms.json.visibility_rate` / `fire_control_opportunity_rate`）降为**描述 / 历史**，**不得**
  用于准入判定。

依据：串行 active FCO 自身散布 0.0053–0.2158（约 40 倍），而 active 可见率稳定在 0.981–0.992，差异几乎全部来自
`env_occ|visible`（包络内停留 / 捕获时机）。里 legacy 口径的 worker 0 `vis_rate=0.2292` 低于下界 `0.5208`，但
active 口径下两 worker 可见率（0.9919 / 0.9843）都在串行范围内、active FCO（0.0516 / 0.0052）也都在范围内 ⇒ **的
旧数值不能归因于并行负载**。的历史记录保留、**不回溯改判**，下一轮准入改用 active 指标。

### (f) 预声明的准入判据与分析计划

计划文件 `src/agc_rl/config/multi_worker_admission.yaml`（version 1，`frozen_before_runs`，sha256 `9d700069…d710`），首个
run 后不修改、偏离单独登记。条件：A 普通单 worker ×3；B 隔离单 worker ×3；A/B 交替；P 两隔离 worker ×3 对（仅门通过
时）；固定 `backend=full` / `s08_static_none_nominal_capture` / `p2_rl_high` / seed0 / headless / `--infra-retries 0`，
启动协议按错峰默认（own 25 s / intruder 35 s / warmup 关闭 / air odom 门）。

- **串行包络与下限**（实测）：`vis_rate` / `fco_rate` 取 `[串行 min, 串行 max]` 且**至少 ±0.01**；计数类 ±1 tick；
  `flight_s` ±0.05 s；重规划计数 ±1。包络：vis [0.5208, 0.9967]、fco [0.3113, 0.6139]（legacy 口径）。
- **硬不变量**：终态**类别**一致（3/3 `INTERCEPT_CONFIRMED`）；每发 `SHOT_FIRED` 恰有一个终局、无未闭合 / 重复；事件
  身份一致（`ep=2`、`shot=2-*`）；0 条身份拒收。**射击数（1–2）与逐发序列不是硬不变量**—— 它是物理 / 时序边界，
  报告须如实列出，**不**当准入硬门。
- **A/B 门**：B 硬不变量全过；共享 PX4 可写文件零写入；infra ≤ A；B active 窗口 `enter_s` 落在 A `[min−5 s, max+5 s]`；
  active 可见率 ≥0.90；active FCO 仅作粗移提示；无 `unexplained`。
- **P 门**：每 worker 硬不变量与事件身份通过；共享 build 只读；infra ≤ B 基线；窗口 / 可见率门同上；RTF 与窗口 ticks
  足够；无跨 worker 污染；无 `unexplained`。
- **收尾**：无跨 worker 残留；`/dev/shm` 增长与 episode 数大致线性；`episode_window_metrics.ticks_total` ≥ 单 worker
  中位数的 90%（RTF 未劣化到采不满窗口）。
- **任一失败** ⇒ **显式接受单 worker**；P 通过也只记录"当前主机并行可行"，**不启动全量批跑**。

> **deferred**：本篇的**并行扩容本身**至今仍处于 deferred—— 原因是 A/B 门未通过（1 次 `INFRA_FAILURE`），不是隔离方案
> 不可行。若未来重试，须先满足本条全部门、并重新预声明容差。

## 结果

### A/B 隔离对照（2026-10-25）

`20261025-w7-rl-b-repeat-ab`：A 3/3 `INTERCEPT_CONFIRMED`（active FCO 0.1606 / 0.0435 / 0.0318，active 可见率 0.9869 /
0.9896 / 0.9825，窗口 enter 30.37 / 32.16 / 29.41 s）；B1/B2 `INTERCEPT_CONFIRMED`（active FCO 0.0137 / 0.0370，可见率
0.9863 / 0.9792），**B3 `INFRA_FAILURE`（`cmd_vel_loopback_missing`，ground lifecycle 未 activate，wall 240 s，0 shot）**。

- **隔离通过**：B 3/3 `writes_detected.any=false`（共享 build 的 `dataman` / `parameters*.bson` / `px4-rc.params` 与
  `log/` 前后不变）；私有 `instance_0/1` 各有 `dataman` / `parameters*.bson` / `.ulg`；A/B 参数初态 sha256 一致。
- **A/B 门不通过**：B3 使 `hard_invariants` 失败且 `infra` 1 > 0；B1/B2 的窗口 / 可见率在 A 范围内。
- **决策**：按预声明计划**不启动 P 两 worker 重试**，**显式保留单 worker**；B3 按协议保留、不用后续成功替代、不据此改写
  记录。隔离本身（PX4 可写文件）通过；n=3 不足以区分隔离栈与主机噪声，但按预声明门仍不通过。

### 同 seed 散布的时间线解释

- 历史3 次 active FCO 0.0053–0.2158 由 `env_occ|visible` 0.0054–0.2199 解释（active 可见率稳定 0.981–0.992），归因
  **physical_scatter**（同 seed 下进入 1 m 火控包络的时机 / 停留拍数不同）。
- [硬约束 hc-4](0020-package-boundaries-and-runtime-topology.md#hc-4) 的 worker 0 active 窗口晚至 56.24 s 归因 **startup_state**：release / start 墙钟晚约 30.7 s，start OK 仿真时刻仅差
  0.97 s，窗口相对 start OK 晚 25.77 s；同期 own PX4 有 44 次 `invalid setpoints / Failsafe: blind land`。该证据只说明时间
  线因果链，**不证明**并行负载因果。
- A/B 的 6 个 case 中 B3 无窗口，其余归因见报告，`unexplained=[]`。

### 两 worker 试验

`20261025-w7-rl-b-c4-trial3`：两 worker 终态均 `INTERCEPT_CONFIRMED`、各 1 发命中、infra 0，run_id 各自唯一（修复前同秒
碰撞）、私有 `/tmp` 使 `/tmp/px4_lock-0` 不再冲突、`GZ_PARTITION` 独立、node list 无对方节点。**但 DV 未通过**（worker 0
legacy `vis_rate=0.2292` < 串行包络下界）—— 按 (f) 回退保留单 worker。事后勘误（上述 (e)）说明该数值是口径错配，**不回溯
改判**。

### 输入

单 worker 吞吐：整链 headless 单 run 墙钟约 100–130 s。GUI / headless 数值等价的初核结论是"未建立 / 证据不足"
（P1 GUI 首跑 `MISSION_FAILED(TIMEOUT)`、重跑 active FCO 0.0004 vs headless 0.0682；P2 seed0 GUI 0.0311 vs headless
0.0625）；两组成功不构成等价证据，后续由 [ADR-0021](0021-gui-headless-equivalence.md#top) 承接。B3 的
`cmd_vel_loopback_missing` 在中作为**独立 infra 项**登记，不归因于 GUI / headless 或隔离栈。

## 不做什么（边界）

- **不**启动全量批跑；当前显式接受单 worker，不等待并行扩容。
- **不**用 `ROS_DOMAIN_ID` 隔离（非 0 域 lifecycle 服务面缺陷未修）；若将来修好，该方案可复活且更轻量。
- **不**共享一个 gz 世界 + 多套感知 / 节点（破坏 episode 隔离与复位语义）。
- **不**改实验语义：每 worker 仍跑完整 `main.launch.py backend:=full`，不做"共享一个仿真、多策略"的省资源变体。
- **不**在内改判定阈值 / 样本量（预注册纪律不变）；worker **不得**自动删 `/dev/shm/fastrtps_*`。
- 不改冻结 ABI、唯一执行口语义、规划器 / 控制律 / 安全层 / 终态语义；不新增第二 ROS 命令者。

## Considered Options

- **每 worker 一个 `ROS_DOMAIN_ID`** —— 被否：本机实测非 0 域 lifecycle 服务面不通；修好该缺陷后可复活。
- **共享一个 gz 世界 + 多套感知 / 节点** —— 被否：破坏 episode 隔离与复位语义。
- **容器（每 worker 一容器）** —— 未采用：本机无 docker / podman；`unshare -Urn` 已实测可用且更轻。
- **串行但流水线化（预启动下一个 gz）** —— 保留备选：收益小、复杂度不低；若并行隔离成本过高可退此方案。
- **继续用 legacy `window_fixed_v1` 率作准入 DV** —— 被否：含终态后停泊，与 primary DV 不可比，曾造成误归因。
- **把射击数当并行准入硬门** —— 被否：它是物理 / 时序边界而非 seed 级不变量。

## Consequences

- **正面**：隔离边界清晰（netns + 无 SHM + 私有 `/tmp`），不依赖脆弱的 domain 切换；PX4 可写状态不再跨 worker / 跨 run
  污染；准入口径与 P1 / P2 的 primary 对齐，的历史记录与勘误可区分；同 seed 散布有可核验的时间线解释。
- **代价 / 限制**：单机 CPU / 内存成为首要瓶颈（每 worker = 1 gz + 2 PX4 + 全链路节点）；每次隔离 run 增加私有 `etc` 拷贝
  与 PX4 运行目录；A/B 需 6 次整链 run + 1 次 smoke；n=3 只能做粗移检测，**不能**宣称数值等价；本机并行可行性未被证明。
- **未决**：若未来在独占主机或单 worker DV 稳定后重试，须**新决策 + 重新预声明容差**；两 worker 曾共用 PX4
  `build/px4_sitl_default` 工作目录的问题已由 (d) 处理。

## 参考

- 契约：[#hard-constraints](0020-package-boundaries-and-runtime-topology.md#hard-constraints)、[#params](0020-package-boundaries-and-runtime-topology.md#params)、
  [#namespace](0020-package-boundaries-and-runtime-topology.md#namespace)、[#execution-port](0020-package-boundaries-and-runtime-topology.md#execution-port)
- 相关决策：[ADR-0027](0027-uxrce-startup-reproducibility.md#top)（uXRCE 预热与错峰）、
  [ADR-0005](0005-px4-toolchain-and-link.md#top)（PX4 工具链 pin）、
  [ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与 run 身份）、
  [ADR-0016](0016-episode-window-and-sample-validity.md#top)（episode 窗口指标）、
  [ADR-0021](0021-gui-headless-equivalence.md#top)（输入与等价门）
- 证据：`experiments/w7-rl-b/20261025-w7-rl-b-repeat-ab/ab_series.json`（A/B 环境与参数初态）、
  `experiments/w7-rl-b/20261025-w7-rl-b-repeat-ab-diagnosis/metrics/worker_repeatability.json`、
  各 B run 的 `worker_0/metrics/px4_writable_isolation.json`、`20261025-w7-rl-b-c4-trial3`、`20261025-w7-rl-b-smoke-isolation`
- 计划与运维：`src/agc_rl/config/multi_worker_admission.yaml`、`docs/conventions/整链排障速查.md`
