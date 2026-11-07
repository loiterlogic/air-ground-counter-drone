<a id="top"></a>
# uXRCE 启动可复现性：预热、错峰与种子协议

## Status

accepted（2026-11-02 由 ADR-0075 / 0094 / 0100 / 0101 合并；结论未变）

## 背景

整链 `backend:=full` 反复被同一类 infra 挡住：own PX4 报
`ERROR [uxrce_dds_client] create entities failed: participant: 255`，此后**无任何**
`created rt/fmu/out/... data writer` → 无 `/agc/air/odom` → 不 arm → `air_hover_timeout` →
`INFRA_FAILURE`。

根因分两层，且都在**环境 / 引擎侧**、不在本项目配置：

1. PX4 侧 `uxrce_dds_client.cpp` 用 `uxr_run_session_until_all_status(&session, 1000, ...)` 等
   participant 创建，预算**硬编码 1000 ms**，失败即 `return`（不建 pubs、不重试）。
2. agent 侧 `establish_session → participant created` 的耗时**随图负载长尾**：最小链 10 次冷启动中位数
   80.6 ms，10 个 ROS 节点 75 ms，**20 个节点复现 4.86 s**；失败整链实测 1.28–3.09 s。慢的是
   **agent 侧 DDS participant 创建**（`create_client → establish_session` 恒 < 0.05 s），不是 XRCE 会话；
   同一 agent 的**首个 participant 最慢**。

另有一层**环境残留**：上一批 run 被外部终止（网络中断 / 工具宿主只杀 leader）后逃逸的孤儿进程
（`ros_gz_bridge` / `parameter_bridge` / `set_pose_bridge` / `static_transform_publisher`）占 DDS 与
`/dev/shm`，实测 6 个孤儿存活 2.5–3.3 h。它们的本体在 `/opt/ros/jazzy/lib/...`、命令行**不含**
`install/agc_` 字样，早先的清场模式漏掉了它们。

另一条与启动相关的整链故障是**时间源分裂**：uXRCE-DDS 桥默认启用桥时间同步（`UXRCE_DDS_SYNCT` 缺省
1），与仿真 `/clock` 打架时把 PX4 时间戳映射到错误纪元，下游 `rclcpp::Time(stamp)` 构造即抛
`cannot store a negative time point`，节点崩溃。

## 决策

<a id="scope"></a>
### (a) 适用范围
本篇只覆盖**启动可复现性**：进程清场、PX4 启动错峰、可选 warmup、空中就绪门、seed 派生与注入。
它**不**改变估计 odom 契约、**不**替代正式测量门、**不**宣称整链确定性。per-instance seed 派生
只适用于full 组合；standalone `air_bringup.launch.py` 直传其单实例 seed，不经该协议；直接跑
PX4 而不设变量时用其文档化兜底。上述范围澄清**不**要求改 standalone 代码。

<a id="evidence"></a>
### (b) 证据与版本边界（先分类，再下结论）
历史实现声明（「PX4 目标可构建」「launch 语法通过、mixer 稳定且实例 / 主种子可区分」）在 2026-10-26
审查时**找不到可定位的执行记录**，标为**未核验**—— 不因此断言当时没跑过，也不得把新证据回填成当时
已验证。版本归属四档，缺材料不得强标：`verified_pre_seed_protocol`（有源码 / 二进制快照能证明旧实现）、
`seed_protocol_not_attested`（只有历史叙述）、`seed_protocol_candidate_unvalidated`（当前工作区）、
`seed_protocol_v1_attested`（满足下列全部保存与日志条件后）。

升到 `seed_protocol_v1_attested` 须同时保存：主仓 HEAD + tracked diff + 相关 untracked 内容 / 哈希、
配置与安装后实际执行文件指纹、PX4 上游 HEAD / 子模块 / 完整 dirty 清单、补丁、源码及二进制哈希，
且运行 manifest 与 own/intruder 的 GPS seed 日志一致。历史科研确证 / pilot / 测量 P1/P2 **保留原件、
原 gate 与原 verdict**，审计表只加版本归属、不回写历史 manifest。**种子噪声流可追溯 ≠ 整链确定性**：
seed 内调度 / 执行重复仍是实验设计的一部分，不能删除重复后称为完全复现。

### (c) 运行前清场（环境残留）
`episode_runner` 在 `Popen` **之前**调用 `sweep_stale_processes`（本 run 进程尚未创建 ⇒ 命中者必为
上次残留）。匹配口径 = `argv[0]` / `/proc/<pid>/exe`，**不**扫整条命令行子串（扫子串会把「命令行里
提到这些字符串」的调试父 shell 误杀）；守卫（`agc_world` / `agc_car` / `agc_world.sdf`）取自参数；
`gz sim` 因 `argv[0]` 为 `ruby` 按命令行匹配但**排除 shell**。证据入产物：`stale_swept_pids` /
`stale_swept_cmds` + 该次 run 日志追加「清场」行。诱饵 / 负例测试：`install/agc_*` 诱饵与「桥 +
`agc_world`」诱饵**被清**；无 `agc` 守卫的桥、非 AGC 进程、仅命令行提及字符串的 shell **存活**。

`/dev/shm/fastrtps_*` **不**由 runner 自动清（清场只保证本项目进程已退出，无法保证机器上无其它 DDS
系统 ⇒ 自动删段有误伤风险），仍为**人工 ops 前置**。实测段数随 run 数大致线性增长（单 run 约余 100
段，累积数百段曾致 SHM 端口初始化失败），7 个 run 从 221 → 363 无初始化失败。

### (d) PX4 错峰（主修复）
own PX4 默认延时 **12 s → 25 s**，intruder **25 s → 35 s**：25 s 避开启动发现风暴，own 作为该 agent
的**首个** participant 创建耗时实测 694–704 ms（< 1 s）；35 s 与 own 错峰 10 s，避免两个 agent 同时
创建 participant（25/25 同时启动实测 own+intruder 双双 `create entities failed`）。launch 参数
`own_px4_delay_s` / `intruder_px4_delay_s` 保留，供 A/B 与回退。

### (e) 可选 sacrificial SIH warmup（默认关闭）
`main.launch.py` 保留一个**不参与任务**的 SIH PX4 warmup（`-i 3`、`PX4_SIMULATOR=sihsim`、
`PX4_SIM_MODEL=none`、绑 `agent0_port`；t=5 s / `timeout 6.5`），但默认 `px4_warmup=false`。
A/B：warmup 组 own 640.7–752.1 ms / intruder 757.4–772.5 ms；no-warmup 组 own 694.0–703.5 ms /
intruder 742.1–750.4 ms ⇒ **25/35 错峰后 warmup 没有额外收益**，故不设为默认，保留给极端负载 / 回退。
warmup 自身允许 `create entities failed`，不计入 infra / mission。

### (f) 空中就绪门（必须）
own PX4 延后后，runner 若仍以地面门调用 start，`task_manager` 会在空中 lifecycle 就绪前调
`air/reset_phase` → `service unavailable` → 状态保持 IDLE。`episode_runner.wait_ready` 对
`backend=full` 增加 **`/agc/air/odom` 新鲜门**（`AIR_FRESH_S=1.0`）——**可观测就绪信号**，不是固定
sleep。

### (g) runner 级 infra 重试（二级保险，不再是主要手段）
判据唯一来源 = `agc_rl.termination.classify_episode_outcome` 的 `classification`：
`infra`（`INFRA_FAILURE` / 未达终态的墙钟截断）→ 按上限**重跑**该 (arm, seed)；`mission`
（含 `MISSION_FAILED(TIMEOUT)`，超时属**任务终态**）→ **一律不重试**。实现：
`episode_runner.run_episode_with_infra_retry`（`infra_retries=0` = 关闭、既有行为不变）+
`w7b_arms_runner --infra-retries`（缺省 3）。证据纪律：每次尝试**各留产物**—— 首试沿用原 `log_tag`，
第 k 次重试追加 `.r<k>` 后缀，逐次 `run_id` / 终态 / 原因记入 `infra_attempts`；上报结果 = **最后一次
尝试**。两臂施加**同一**协议 ⇒ 不构成自变量差异。预注册 `keep_all_failures_and_infra` 不变：重试耗尽
的 infra **仍计入分母**（primary DV 记失败），阈值 / 样本量 / 自变量均未改，infra 率与重试次数须在
报告中如实报出、**不得**被读作臂效应。

### (h) 种子协议（full-chain）
`seed` 是**实验主种子**。`composition.py` 以 `agc-px4-sim-seed-v1` 为每个 PX4 进程派生一个
uint32 seed：实例 0 = own、实例 1 = intruder、实例 3 = 可选 warmup；派生值经 `AGC_PX4_SIM_SEED` 传入
并记入 run manifest 的 `effective_params.seed_protocol`。`sensor_gps_sim` 改用模块私有 xorshift32 +
Box-Muller 流，**不用** libc 的进程全局 `rand`：变量未设 = 确定性 standalone 种子，值非法则**拒绝模块
启动**；GPS 噪声模型与其配置幅度不变。同一主种子经显式 `perception_bringup` launch 参数传给
`air_perception`，**只有** `air_perception` 收该参数（无关节点不得收到未声明参数）。
（2026-11-06：`air_perception` 已退役，该 seed 通道随之删除；主种子仍经 `scenario_reset.spawn_seed` /
`run_logger.seed` 两个强类型 `int` 参数进入整链。）

### (i) 时间源加固：仿真唯一时间源 + 生产者侧校验
三层处置（**生产者修复为主，消费端只做纵深防御**）：

- **仿真唯一时间源**：`UXRCE_DDS_SYNCT: 0` 纳入 `src/agc_task/config/px4_failsafe_lock.yaml` **单一
  真源**，由 `scripts/lock_px4_failsafe_params.sh` 注入 SITL 启动参数文件
  （`param set UXRCE_DDS_SYNCT 0`）；各 ROS 节点一律 `use_sim_time=true` 走 `/clock`。依据 PX4 官方
  文档「桥时间同步在仿真中应禁用」—— 仿真里时钟真源只能是 `/clock`，不能让桥再引入第二个。
- **生产者侧加固**：`Px4TimeMapper` 新增 `reset`；`observe` 中**偏移跳变 > 0.1 s 即重锚**（不再
  EMA 混合，避免旧偏移把新纪元拉回错误区间）。`px4_adapter.cpp` 对映射结果做合理性校验—— 须**非负**
  且与 `now` 偏差 ≤ `stamp_max_skew_s`（单一真源 `src/agc_air/config/air.yaml`，默认 **5.0 s**）；
  超界即**拒发该帧 + 一次性如实告警 + 重锚**，**不静默替换时间戳**。EKF `reset_counter` 变化同样触发
  重锚（局部原点 / 姿态跳变时世界坐标须重新标定）。
- **消费端不替代生产者**：`air_perception.cpp` 对入站 `Header.stamp` 加 `sec < 0` **前置守卫**
  （拒收 + 一次告警），只防崩溃、**不是根因修复**—— 时间戳的正确性责任仍在生产者侧。

**证据**：修后 `negative time point` 崩溃 0、`px4_adapter` 映射告警 0；EKF 复位计数逐次重锚记录。
**未决（如实登记）**：修后**观测链仍间歇**（`standoff_follower` 目标过期冻结），疑为机体固连前视
偏航丢目标—— 该现象**本轮不修**，属研究问题，交接给 [ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)。
PX4 四元数字段序 `[w,x,y,z]` 的处置见 [ADR-0019](0019-lifecycle-and-startup-robustness.md#top)，本篇不重复。

### (j) 保存与提交边界
主仓保存**小补丁**、`toolchain/README.md` 保存**唯一 pin 清单**、外部 PX4 工作树继续忽略。补丁必须
能从清单基准还原（不能只保存本机绝对路径）；校验须覆盖补丁 sha256、应用后源内容、全部意外
dirty/untracked 改动及子模块状态，**不放行**额外未登记改动（`toolchain_pin_check.py` 的
`local_patches` 项）。P3 基于显式 dirty 基线执行、无须先提交；**不自动** commit / push / merge /
切分已有补丁，同一文件跨组改动需人工审阅后选择性提交。

<a id="p3"></a>
### (k) P3 执行顺序与门
1. **先补前置验证**：校验保存的补丁，补齐 seed 派生与 launch 注入、实际 GPS RNG 的同 seed 重启 /
   异 seed / 私有状态 / 非法值 / 零值验证；扩展 checker 并验证正常 / 篡改 / 额外 dirty 负例；对含补丁
   的 GPS 模块作**有可定位编译步骤**的构建（禁止零编译 no-op 或旧二进制替代）；保存输入 / 产物对应
   关系后显式更新 README 二进制 pin，再重跑校验。
2. **再实现并验证记录器**：先研究同版本 run_logger 回调、`task_manager` 状态发布时间与既有 gtest
   结构；新指标独立字段、逐区间账本与完整性审计；ABI 与旧统计字段原语义保留；端到端验证必须覆盖
   正常 ROS 回调链，不能只测孤立数学函数。
3. **最后两次 GUI 工程验证**：前两项通过且无额外异常后，串行 full / d3d12，P1
   `s15/p1_coop/seed5` 一次、P2 `s08/p2_rl_high/seed0` 一次，总预算 2 attempts、infra 重试 0。这是
   **工程验证**，不是模式 pilot / 等价或科研样本；失败尝试不以补跑替代。第一场同时完成 seed 运行证据
   核对，缺失或不符则第二场不启动；无 GUI 或渲染后端不符则回报，**不改用 headless**。
4. **交回新设计草案**：覆盖 [ADR-0021](0021-gui-headless-equivalence.md#top) 的全部待办；草案标
   `draft_pending_codex_review`，**不得自动冻结**执行计划。缺测处理先采用保守门：任何 mission 的新
   FCO 存在未知区间或拒算，正式门**不得**宣布等价；保留该任务及识别界，不做 available-case 删除。
   前置失败须阻塞后续；需要改 PX4 RNG / seed 协议或控制行为则交回裁定，不在本单试改。Gate 仍为
   `not_evaluable_as_specified`；正式等价、新 pilot、headless 规模统计与扩容均须后续独立派工。

## 不做什么（边界）
- **不**改 PX4 源码 / 子模块 SHA / agent 版本（放宽 1 s 预算命中 pin 红线；若要做须另立 ADR +
  patch + 构建脚本 + pin 更新）。
- **不**把 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 设为默认（只作诊断 / 备选：长尾压到 ~0.55 s，但图刚起
  时首跑仍失败，且改变 transport 语义与吞吐）。
- **不**用 watchdog 重启 own PX4（被 SIGKILL 后 gz 模型失去控制会失稳 / 坠落，重挂很可能接上已失稳
  模型并牵连 arm / 起飞时序）。
- **不**重试至成功、**不**把 infra 记为成功（改写终态语义，违反与 infra 单列原则）。
- **不**由 runner 自动清 `/dev/shm`；**不**以清场替代多 worker 隔离；**不**宣称「种子流可追溯」
  等于整链确定性。

## Considered Options
- **只放宽 PX4 1 s 预算** —— 根治且近 100% 成功，但命中 pin 红线，需独立 ADR / patch / 构建 / pin 更新。
- **只依赖 runner 重试** —— 被否：持续偏高时 4/4 全失败（own 1.47 / 1.79 / 2.14 / 2.53 s），重试解决
  的是**间歇**尖峰而非持续污染。
- **只调 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`** —— 不采纳为默认（见边界）。
- **只错峰 12/25、不加 warmup** —— 不足：12 s 时 own 仍是首个 participant，实测 1.28–3.09 s。
- **warmup + 25/25 同时启动** —— 被否：实测 own+intruder 双双超时。
- **清场扫整条命令行子串** —— 被否：会误杀仅提及这些字符串的 shell。

## Consequences
- **正面**：整链在连续冷启动下可复现地进入 1 s 内（A4 no-warmup 5/5：own 694.0–703.5 ms、
  intruder 742.1–750.4 ms；A7 最终默认配置 own 701.3 / 701.2 ms、intruder 737.2 / 751.0 ms，均
  `INTERCEPT_CONFIRMED`、`create entities failed` 0、infra 0）；间歇 infra 由「整轮作废 / 人工重跑」
  降级为自动恢复且逐次可审计；无需改 PX4 pin。
- **代价 / 限制**：启动墙钟增加约 13 s（own 12→25）/ 10 s（intruder 25→35），单 episode 约 110–130 s，
  `w7b_arms_runner --timeout` 默认提高到 240 s；单 episode 最坏墙钟 ×(K+1)（K=3），报出的成功率含
  「重试后成功」⇒ **infra 率与重试分布必须随报告一并报出**；本篇**不**消除根因。若显式开启 warmup，
  每回合多一个 SIH 进程（约 6.5 s）并短暂产生 `/px4_3/fmu/out/*` 话题。
- **证据**：诊断报告 `experiments/w7-rl-b/20261024-w7-rl-b-uxrce-diagnosis/metrics/uxrce_diagnosis.md`；
  R1 静态 / 构建验证日志 `experiments/w8-parity/20261026-w8-measurement-p3/log/pytest_r1.log`、
  `.../log/px4_build.log`、`.../metrics/pin_check_after.json`（41 PASS / 0 FAIL / 0 SKIP）；种子协议
  13 项测试通过（同 seed 重启一致、异 seed 区分、实例 0/1/3 私有、seed=0 映射 `0x6D2B79F5`、
  unset=1、非法值拒绝、uint32 边界接受）。
- **未决**：① 多 worker（[ADR-0024](0024-multi-worker-isolation.md#top)）下 warmup / 错峰是否仍成立（每 worker 独立 agent / netns 后应成立，需
  验证）；② 若必须恢复 12/25 启动时序，须另立 ADR 并给出新的 1 s 预算方案；③ **清场与并行 worker
  冲突**——`sweep_stale_processes` 按本项目特征 SIGKILL、**不区分进程属于哪个 worker**，同机并行时
  后启动者会杀掉先启动者的进程，故在隔离手段（独立 `ROS_DOMAIN_ID` 前缀 + 进程标记 + 或每 worker
  独占容器 / 网络命名空间）落地前**只允许单 worker 串行**；④ 残留孤儿的来源尚未定性（已确证「有孤儿
  → 时延恶化 → infra」与「清场 → 恢复」，但未能区分外部终止与其它异常退出路径），当前由运行前清场
  兜底；⑤ 运行生效核验（manifest `seed_protocol`、own/intruder GPS seed 日志）须在环境恢复后补验，
  在此之前种子协议仍是 `seed_protocol_candidate_unvalidated`。
## 参考
- [ADR-0005](0005-px4-toolchain-and-link.md#top)（PX4 工具链与 uXRCE-DDS 链路）
- [ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与证据纪律）
- [ADR-0018](0018-acceptance-and-coverage-matrix.md#top)（验收判定与三层闸门）
- [ADR-0021](0021-gui-headless-equivalence.md#top)（测量门与 P3 待办）
- [ADR-0023](0023-adjudication-record-and-exit.md#top)（出口闭合）
- [ADR-0024](0024-multi-worker-isolation.md#top)（多 worker 隔离与扩容准入）
