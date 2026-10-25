# W7-c 多 worker 隔离设计（**草案 / 未实施**）

## Status

deferred（2026-10-25：C4 legacy DV 记录保留；[ADR-0095](0095-w7c-admission-metric-and-worker-run-dir-isolation.md) 的 A/B 门因 B3 `INFRA_FAILURE` 未通过，继续保留单 worker；W7-c 批跑未启动）

## Date

2026-10-20

## 背景

W7-c 的目标是把 W7-a/b 的**单 worker 串行**评估扩为**同机多 worker 并行**（[ADR-0069](0069-w7-entry-and-exit-definition.md)「单 worker 可重放」→ 多 worker 隔离）。

现状约束（均为**实测**结论，不是推测）：

1. **同机两个整链实例会互相污染**：`/dev/shm/fastrtps_*` 段、DDS 发现域、PX4 实例命名空间、uXRCE agent 端口、gz 世界名、实验产物目录**全部共享**。
2. **`/dev/shm` 段会累积**（单 run 约余 100 段）；累积数百段即出现 SHM 端口初始化失败（[ADR-0075](0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md)）。
3. **uXRCE 客户端实体创建预算仅 1 s（PX4 硬编码）**：任何额外负载/拥塞都会直接变 infra；多实例共用一个 agent 更易超时（已改为按实例分端口）。
4. **本机 `ROS_DOMAIN_ID` 非 0 时 lifecycle 服务数据面不通**（实测 77/81：`ChangeState` 一律超时，话题仍正常）→ **不能**用"每 worker 一个 domain id"作为隔离手段（除非先解决该缺陷）。
5. **`sweep_stale_processes`（[ADR-0075](0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md)(i)）不区分 worker 归属**，并行时后启动者会杀掉先启动者的进程。

## 决策（草案，待评审后转 accepted）

### (a) 隔离单元 = **网络命名空间**（每 worker 一个），而非 ROS domain

理由：约束 4 封死了"按 domain 隔离"的常规做法；而**独立 netns 下每 worker 拥有独立 loopback**，于是：

- 所有 worker 可**统一使用 `ROS_DOMAIN_ID=0`** → 规避缺陷 4；
- DDS 发现（`LOCALHOST`）天然不出 netns → 无跨 worker 串扰；
- PX4 MAVLink / agent UDP 端口（8888/8889/14550…）在各 netns 内**互不冲突**，无需改端口分配；
- `/dev/shm` 仍为**全局共享**（POSIX shm 不随 netns 隔离）→ 见 (c)。

候选实现（按落地成本排序，择一）：
1. **容器**（每 worker 一容器，`--network=none` 或默认 bridge + 独立 IPC）——最干净，但需镜像/挂载规划；
2. `unshare -n` + 显式挂载/回环配置 —— 轻量，但需要 root 或 user-ns 支持，且要与 `ros2 launch` 进程组回收配合；
3. 若 1/2 都不成立 → **退回单 worker**（明确不做 W7-c 并行）。

### (b) 每 worker 独占的资源

| 资源 | 方案 |
|---|---|
| ROS 域 | 统一 `0`（依赖 netns 隔离） |
| uXRCE agent 端口 | 沿用"按 PX4 实例分端口"（own 8888 / 入侵者 8889，[ADR-0075](0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md)）；netns 内不冲突 |
| PX4 实例 | `px4 -i N` → 命名空间 `px4_N`（各 worker 内部编号可相同，因 netns 隔离） |
| gz 世界 | 每 worker **独立 gz 进程**（世界名可同名）；不建议共享一个 gz 多模型（会破坏"同世界同时钟"的 episode 语义） |
| 产物目录 | `experiments/<campaign>/<run_id>/worker_<id>/`；或 campaign 名带 worker 后缀——**须单一约定**，避免混批 |
| 进程组 | 每 episode 一个 session（已有 `start_new_session=True`）；**worker 级**再加一层可识别标记（环境变量 / 参数前缀）供清场按归属过滤 |

### (c) `/dev/shm` 与清场

- **段清理**：仍为 worker 启动前的**人工 / 编排层**动作；**禁止**由 worker 自动 `rm -f /dev/shm/fastrtps_*`（会误删同机其它 worker 的段）。
- **清场**：`sweep_stale_processes` 必须增加**归属判据**（例如进程环境变量 `AGC_WORKER_ID`，或 `ROS_DOMAIN_ID`/netns inode），**只清本 worker**；否则禁止启用并行。

### (d) 准入判据（并行前必须全部满足）

1. 单 worker 串行跑出**可复现**基线（同一 seed 两次 run 的终态与 DV 一致）；
2. 两 worker 并行跑**同一 (scene, seed)** 各一次 → 终态一致、DV 差异在**预先声明**的容差内、`infra` 不高于单 worker 基线；
3. 并行跑完 `ps` 无跨 worker 残留、`/dev/shm` 段增长与 episode 数线性（可解释）；
4. RTF 未因并行劣化到影响 `--obs-horizon-s` 采满（否则窗口采不满 → DV 失真）。

### (e) 明确**不**做的事

- **不**改实验语义：每 worker 仍跑完整的 `w6.launch.py backend:=full`（不做"共享一个仿真、多策略"的省资源变体）；
- **不**用"多线程跑多个 episode 共享一个 gz"——违反"同世界同时钟 + episode 独立复位"的前提；
- **不**在 W7-c 内改判定阈值 / 样本量（预注册纪律不变）。

## 更新（2026-10-24）——准入实测与定稿

> 本节把草案的未决项（隔离选型 / 清场归属 / 容差）按本机实测写定；状态在两 worker 试验后决定。

### (f) 本机隔离能力（实测）

- `unshare -Urn`（rootless user+net namespace）**可用**；`ip link set lo up` 在 namespace 内成功。
- **没有** docker / podman；`unshare -n` 单独使用被拒绝（Operation not permitted）。
- ⇒ 隔离单元 = **每 worker 一个 rootless user+net namespace**；**不**用 `ROS_DOMAIN_ID` 隔离（保持 0，规避非 0 域 lifecycle 服务数据面缺陷）。

### (g) 每 worker 资源（定稿）

| 资源 | 方案 |
|---|---|
| ROS 域 | `ROS_DOMAIN_ID=0`（netns 内 loopback 隔离） |
| DDS transport | 所有 worker 进程 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`——`/dev/shm` 不随 netns 隔离，必须关 SHM 防跨 worker 互发现 |
| gz 分区 | `GZ_PARTITION=agc_w_<worker_id>`（每 worker 唯一） |
| `/tmp` | `unshare -Urnm` + private tmpfs `/tmp`（PX4 `/tmp/px4_lock-<instance>` 不跨 worker；实测 25/25 同时启动时两 worker 争同一 lock） |
| uXRCE agent 端口 | `8890 + 10*worker_id` / `+1`（netns 内本可复用，显式分配便于审计） |
| PX4 实例 | worker 内仍为 0 / 1（netns + 无 SHM 后不跨 worker 冲突） |
| 产物目录 | `experiments/<campaign>/<run_id>/worker_<worker_id>/` |
| run_logger 身份 | worker 模式注入 `run_id_override=<date>-<scene>-<seed>-<HHMMSS>-w<id>-<rand>`；避免同秒启动的两个 worker 撞 `experiments/w6-task-eval/<run_id>/`（实测 `091552-6372` 碰撞） |
| 进程归属 | 所有 worker 进程继承 `AGC_WORKER_ID=<worker_id>` |
| 挂载命名空间 | 每 worker 独立 mount ns（`-Urnm`）；worker 退出后 private `/tmp` 自动消失，不在宿主留 PX4 lock |

### (h) 清场归属（定稿）

- `sweep_stale_processes(worker_id)` 读取 `/proc/<pid>/environ`，**只**清理 `AGC_WORKER_ID` 等于本 worker 的进程；
  没有该标记的进程**一律不杀**（属于其它 worker / 机器上其它系统）。
- `/dev/shm/fastrtps_*` 仍为**人工 / 编排层**动作；worker **不得**自动删除段（会误伤同机其它 worker）。
- 单 worker 模式（`worker_id=None`）保持既有全局清场行为，不改变历史 W7-b 路径。

### (i) 串行重放与数值容差（C1 实测）

C1：同一 `(s08_static_none_nominal_capture, seed=0, p2_rl_high)` 串行 3 次：

| run | 终态 | 射击数 | vis_rate | fco_rate |
|---|---|---:|---:|---:|
| `c1-serial-01` | `INTERCEPT_CONFIRMED` | 2 | 0.5208 | 0.3148 |
| `c1-serial-02` | `INTERCEPT_CONFIRMED` | 1 | 0.9950 | 0.3113 |
| `c1-serial-03` | `INTERCEPT_CONFIRMED` | 2 | 0.9967 | 0.6139 |

- **硬不变量**：终态**类别**一致（3/3 `INTERCEPT_CONFIRMED`）；每发 `SHOT_FIRED` 恰有一个终局、无未闭合 / 重复；事件身份一致（`ep=2`、`shot=2-*`）；0 条身份拒收。
- **非硬不变量**：射击数（1–2）与逐发序列。它是物理 / 时序边界，不是 seed 级不变量；报告须如实列出，**不**把它当并行准入的硬门。
- **连续 DV 容差**：以 C1 串行包络为准，并设下限——`vis_rate` / `fco_rate` 取 `[串行 min, 串行 max]` 且至少 ±0.01；计数类 ±1 tick；`flight_s` ±0.05 s；重规划计数 ±1。C1 包络：vis [0.5208, 0.9967]、fco [0.3113, 0.6139]。
- `infra` 基线 = 0/3；并行试验的 infra 不得高于该基线。

### (j) 两 worker 试验判据（定稿）

- 两个 worker 各跑同一 `(scene, seed, arm)`；`worker_id=0/1`，共享 `run_id`，产物落 `worker_<id>/`。
- **硬不变量**：终态类别一致；每发唯一终局；事件身份一致；0 拒收。
- **DV**：在 (i) 的串行包络 + 下限内；射击数在 [1, 2] 内（若超出记缺陷）。
- **隔离**：在每个 netns 内 `ros2 node list` 只有一个 `task_manager`（无重复）；`gz topic -l` 只看到本 worker 的 `agc_w` 分区；两 worker 的日志无对方 node / topic。
- **收尾**：无跨 worker 残留；`/dev/shm` 增长与 episode 数大致线性；`episode_window_metrics.ticks_total` ≥ 单 worker 中位数的 90%（RTF 未劣化到采不满窗口）。
- **回退**：netns 下 gz / GUI / RTF 不可用，或试验失败 → 保留单 worker；ADR-0077 记 `deferred`，不启动 W7-c 批跑。

### (k) 状态

- `deferred`（2026-10-25）：C4 两 worker 试验的 **DV 容差未通过**（见 (l)）；本机保留单 worker，不启动 W7-c 批跑。

### (l) C4 两 worker 试验结果（2026-10-25）

run：`20261025-w7-rl-b-c4-trial3`（`worker_0` / `worker_1`，同 `s08` / `p2_rl_high` / seed0 / headless）。

| 项 | worker 0 | worker 1 |
|---|---|---|
| 终态 | `INTERCEPT_CONFIRMED` | `INTERCEPT_CONFIRMED` |
| 射击 | 1 发 `2-1`、命中 | 1 发 `2-1`、命中 |
| flight_s | 0.832 | 0.792 |
| vis_rate | **0.2292** | 0.9953 |
| fco_rate | 0.0329 | 0.0593 |
| infra | 0 | 0 |
| RTF | 0.786 | 0.756 |
| `episode_window_ticks` | 368 | 573 |
| `visibility_metrics.ticks_total` | 1885 | 1907 |
| run_id | `...-092502-w0-4916` | `...-092502-w1-9051` |

- **隔离通过**：两 worker 的 run_id 各自唯一（修复前同秒碰撞为 `091552-6372`）；私有 `/tmp` 使 `/tmp/px4_lock-0` 不再冲突；无跨 worker 残留、宿主无 `/tmp/px4_lock*`；`GZ_PARTITION` 独立；两 worker 的 node list 无对方节点重复。
- **硬不变量通过**：终态类别一致、每发唯一终局、事件 `ep=2` / `shot=2-1`、0 拒收。
- **DV 未通过**：worker 0 `vis_rate=0.2292` < C1 串行包络下界 `0.5208`；worker 1 在包络内。
- **结论**：按 (j) 回退——**保留单 worker**；不启动 W7-c 批跑。失败不能归因于跨 worker 污染（隔离项均通过），更可能是 4 核主机并行下的 RTF / 任务时序差异；若未来在独占主机或单 worker DV 稳定后重试，须新 ADR + 重新预声明容差。
- **未决**：两 worker 仍共用 PX4 `build/px4_sitl_default` 工作目录（`dataman` / `parameters` / `log`）。本轮未观察到 lock 冲突（`/tmp` 已私有化），但这是 W7-c 批跑前必须处理的共享资源；候选 = 每 worker 独立 rootfs 副本 / 唯一实例 id + `PX4_HOME`。worker 0 的低 vis 不能唯一归因（4 核 RTF 0.786、共享 PX4 cwd、任务时序均为候选）。


### (m) 指标勘误（2026-10-25，追加）

- C4 比较使用的 `arms.json.visibility_rate` / `fire_control_opportunity_rate` 是 `window_fixed_v1`（含终态后停泊），与 active 窗口的 primary DV 不可比。
- 原始产物的 active 指标：串行 active FCO 0.2158 / 0.0053 / 0.0779；C4 worker 0 / 1 = 0.0516 / 0.0052。串行自身散布约 40 倍，active 可见率 0.981–0.992（C4 0.9919 / 0.9843），差异几乎全部来自 `env_occ|visible`。
- ⇒ C4 的 legacy `vis_rate=0.2292` 低于 `0.5208` 不能归因于并行负载；**保留 (l) 的“不准入 / 保留单 worker”过程记录，不回溯改判**。下一轮准入改用 active 指标，并先写定分析计划（[ADR-0095](0095-w7c-admission-metric-and-worker-run-dir-isolation.md)）。

### (n) PX4 可写运行目录隔离（2026-10-25，追加）

- 实现（[ADR-0095](0095-w7c-admission-metric-and-worker-run-dir-isolation.md)(d)）：`w6.launch.py` opt-in `px4_run_root`；own / intruder / warmup 各用 `-w <root>/instance_N`，各自独占 `dataman` / `parameters*.bson` / `log/` / `eeprom/`；worker 私有 `etc` 副本由 `lock_px4_failsafe_params.sh` 写入 `px4-rc.params`；共享 build 只读。
- 隔离 smoke：`20261025-w7-rl-b-smoke-isolation`（worker 0）→ `INTERCEPT_CONFIRMED`、infra 0、`writes_detected=false`；私有 `instance_0` / `instance_1` 各有 `dataman`、`parameters*.bson`、1 个 `.ulg`。
- (l) 的“未决：两 worker 仍共用 PX4 工作目录”由本节处理；是否保留单 worker由 A/B 门与 P 试验决定。


### (o) A/B 隔离对照结果与决策（2026-10-25，追加）

- run：`20261025-w7-rl-b-repeat-ab`（A1/A2/A3 + B1/B2/B3，同 `s08` / `p2_rl_high` / seed0 / headless / `--infra-retries 0`；A/B 交替；参数初态 canonical `b9addc2b…`）。
- A：3/3 `INTERCEPT_CONFIRMED`；active FCO 0.1606 / 0.0435 / 0.0318，active 可见率 0.9869 / 0.9896 / 0.9825，窗口 enter 30.37 / 32.16 / 29.41 s；共享 build 的 PX4 日志按预期增加（A 走共享 cwd）。
- B：B1/B2 `INTERCEPT_CONFIRMED`（active FCO 0.0137 / 0.0370，active 可见率 0.9863 / 0.9792，窗口 enter 29.56 / 31.36 s）；**B3 `INFRA_FAILURE`（`cmd_vel_loopback_missing`，ground lifecycle 未 activate，wall 240 s，无 shot）**。
- 隔离：B 3/3 `writes_detected.any=false`（共享 build 的 `dataman` / `parameters*.bson` / `px4-rc.params` 与 `log/` 前后不变）；私有 `instance_0/1` 均有 `dataman` / `parameters*.bson` / `.ulg`；A/B 参数初态 sha256 一致。
- 门：`shared_px4_writable` pass；`hard_invariants` fail（B3 terminal 类别 `INFRA_FAILURE`）；`infra` fail（B 1 > A 0）；B1/B2 的窗口 / 可见率在 A 范围内；active FCO 粗移提示 false。**A/B 门不通过**。
- 决策：按预声明计划**不启动 P 两 worker 重试**，**显式保留单 worker**；W7-c 继续 `deferred`。B3 是 infra 事件（不是 mission 失败），按协议保留、不用后续成功替代、不据此改写 C4 记录。隔离本身（PX4 可写文件）通过；B3 是隔离单 worker 条件下观测到的 ground lifecycle 激活失败 infra，n=3 不足以区分隔离栈与主机噪声，但按预声明门不通过。
- 证据：`experiments/w7-rl-b/20261025-w7-rl-b-repeat-ab-diagnosis/metrics/worker_repeatability.{json,md}`；隔离 JSON 在各 B run 的 `worker_0/metrics/px4_writable_isolation.json`；A/B 环境与参数初态在 `experiments/w7-rl-b/20261025-w7-rl-b-repeat-ab/ab_series.json` 与各 run `config/`。


## 备选

1. **每 worker 一个 `ROS_DOMAIN_ID`** —— 否决（本机实测缺陷 4：非 0 域 lifecycle 服务面不通）；若将来修好该缺陷，本方案可复活且更轻量。
2. **共享一个 gz 世界 + 多套感知/节点** —— 否决：破坏 episode 隔离与复位语义。
3. **串行但流水线化（预启动下一个 gz）** —— 保留备选：收益小、复杂度不低；若并行隔离成本过高可退此方案。

## 后果（若采纳）

- **正面**：获得真正的并行扩容；隔离边界清晰（netns），不依赖脆弱的 domain 切换。
- **代价 / 限制**：需要容器或 netns 的运维能力；`/dev/shm` 与清场归属仍需显式处理；单机 CPU/内存成为首要瓶颈（每 worker = 1 gz + 2 PX4 + 全链路节点）。
- **未决**：① netns 方案（容器 vs `unshare`）的落地选型；② 清场归属标记的具体字段；③ 并行容差与准入判据的数值（须**先于**并行 run 写定）；④ 产物目录命名约定；⑤ 是否需要在 `w6.launch.py` 增加 `worker_id` 参数（单一注入）。

## 参考

- 契约：[#hard-constraints](../ROS2迁移交接文档.md#hard-constraints)、[#params](../ROS2迁移交接文档.md#params)、[#namespace](../ROS2迁移交接文档.md#namespace)、[#execution-port](../ROS2迁移交接文档.md#execution-port)
- 前序 ADR：[ADR-0005](0005-px4-link-uxrce-dds.md)、[ADR-0007](0007-experiment-artifacts-convention.md)、[ADR-0069](0069-w7-entry-and-exit-definition.md)、[ADR-0075](0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md)
- 运维速查：[`docs/conventions/整链排障速查.md`](../conventions/整链排障速查.md)
