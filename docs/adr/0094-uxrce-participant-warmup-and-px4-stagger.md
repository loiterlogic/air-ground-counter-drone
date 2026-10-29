# uXRCE participant 创建预热与 PX4 错峰（1 s 预算内的可复现整链启动）

## Status

accepted（A5 5 连冷启动全部 infra-free；4/5 `INTERCEPT_CONFIRMED`、1/5 `MISSION_FAILED(TIMEOUT)`，后者为 mission 终态，不是 uXRCE infra）

## Date

2026-10-24

## 背景

W7-b 闭合后，整链 `backend:=full` 被 own PX4 的

`ERROR [uxrce_dds_client] create entities failed: participant: 255`

阻塞。历史处置见 [ADR-0075](0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md)（残留孤儿 / 清场 / runner 重试）；本轮按 spec [`restore-fullchain-infra-and-w7c-admission`](../archive/specs/restore-fullchain-infra-and-w7c-admission/spec.md) 重新定位，得到三条新事实：

1. **慢阶段是 agent 侧 DDS participant 创建，不是 XRCE 会话**。失败日志中 `create_client → establish_session` 恒 < 0.05 s；`establish_session → participant created` 为 **1.28–3.09 s**。
2. **负载相关，不是 CPU 或单纯 SHM**。最小链 10 次冷启动 `participant_create_ms` 中位数 **80.6 ms**（max 85.7）；4×CPU busy loop 只升到 **87.6 ms**；10 个 ROS 节点仍为 **75 ms**；**20 个 ROS 节点**复现 **4.86 s** 与 PX4 1 s 超时；清 `/dev/shm` 后 n=10 首跑仍失败、后 9 次 543–563 ms。agent 仅 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 把长尾压到 **~0.55 s**，但图刚起时首跑仍失败。
3. **同一 agent 的“首个 participant”最慢**。失败整链中 own（首个客户端）恒慢、intruder（晚 12–13 s）恒快；20 节点探针也是第 1 跑最慢、后续 ~0.55 s。

上游依据：PX4 v1.15.4 [`uxrce_dds_client.cpp`](../../toolchain/PX4-Autopilot/src/modules/uxrce_dds_client/uxrce_dds_client.cpp) 的 participant 创建预算为**硬编码 1000 ms**，失败即 `return`、不重试；topic writer 预算同为 1000 ms（[`utilities.hpp`](../../toolchain/PX4-Autopilot/src/modules/uxrce_dds_client/utilities.hpp)）。Micro-XRCE-DDS-Agent v2.4.3 最终调用 `DomainParticipantFactory::create_participant(domain_id, qos)`（[`FastDDSEntities.cpp`](../../toolchain/Micro-XRCE-DDS-Agent-2.4.3/src/cpp/middleware/fastdds/FastDDSEntities.cpp)）。Fast DDS 2.14 新 participant 默认创建 SHM transport（[Transport Layer](https://fast-dds.docs.eprosima.com/en/2.14.x/_sources/fastdds/transport/transport.rst.txt)），`FASTDDS_BUILTIN_TRANSPORTS` 可改 builtin transport（[Troubleshooting](https://fast-dds.docs.eprosima.com/en/stable/fastdds/troubleshooting/troubleshooting.html)）。

## 决策

### (a) own / intruder 错峰（主修复）

own PX4 默认延时由 **12 s → 25 s**，intruder 由 **25 s → 35 s**：

- **25 s**：避开启动发现风暴；own 作为该 agent 的**首个** participant，创建耗时实测 **694–704 ms**（< 1 s）；
- **35 s**：与 own 错峰 10 s，避免两个 agent 同时创建 participant（25/25 同时启动实测 own+intruder 双双 `create entities failed`）。

launch 参数 `own_px4_delay_s` / `intruder_px4_delay_s` 保留，供 A/B 与回退。

### (b) sacrificial SIH warmup（可选，非默认）

`w6.launch.py` 保留一个 **不参与任务** 的 SIH PX4 warmup（`-i 3`、`PX4_SIMULATOR=sihsim`、`PX4_SIM_MODEL=none`、绑 `agent0_port`；t=5 s / `timeout 6.5`），但**默认关闭**（`px4_warmup=false`）。

A/B 结果：warmup 组（A5b）own 640.7–752.1 ms / intruder 757.4–772.5 ms；no-warmup 组（A4）own 694.0–703.5 ms / intruder 742.1–750.4 ms。**25/35 错峰后 warmup 没有额外收益**，故不设为默认；保留给极端负载 / 回退。warmup 自身允许 `create entities failed`，不计入 infra / mission。

### (c) 空中就绪门（必须）

own PX4 延后后，runner 若仍以地面门（`/agc/task/start` 服务 + gt 新鲜 + `cmd_vel` 回环 + `odom_valid`）调用 start，`task_manager` 会在空中 lifecycle 就绪前调 `air/reset_phase` → `service unavailable` → 状态保持 IDLE（`20261024-w7-rl-b-a5-cold-02` 实测）。

[`scripts/episode_runner.py`](../../scripts/episode_runner.py) 的 `wait_ready` 增加 **`/agc/air/odom` 新鲜门**（`AIR_FRESH_S=1.0`），仅对 `backend=full` 启用；这是**可观测就绪信号**，不是固定 sleep。

### (d) 不修改 PX4 / agent pin

未改 PX4 源码、子模块 SHA、agent 版本；`FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 只作为诊断 / 备选，**不设为默认**（首跑仍失败，且改变 transport 语义 / 吞吐）。若未来仍需放宽 1 s 预算，另立 ADR + patch + 构建脚本 + pin 更新。

### (e) 验收

以 `backend:=full`、`--infra-retries 0`、连续 **5 次冷启动**、每次正常 SIGINT 收尾验收；每次要求：

- own / intruder PX4 均出现 `created .../vehicle_odometry data writer`，无 `create entities failed`；
- own / intruder 的 `establish_session → participant created` **< 1000 ms**；
- episode 到达任务终态（`MISSION_*` / `TRACKING_*` / `INTERCEPT_*` 等；**不是** `INFRA_FAILURE`）；
- 收尾后无本项目 / ROS 残留，`/dev/shm` 段数可解释。

> 注：5/5 指**没有 uXRCE infra**，不要求 5/5 mission 成功；mission 结果照实报告（见下表 mission 失败行）。

## 证据（A4 / A5，2026-10-24）

### A4 no-warmup（默认修复候选）

| run | own participant_ms | intruder participant_ms | 终态 | 备注 |
|---|---:|---:|---|---|
| `a4-nowarmup-01` | 694.0 | 750.4 | `INTERCEPT_CONFIRMED` | 无 warmup |
| `a4-nowarmup-02` | 697.3 | 749.5 | `INTERCEPT_CONFIRMED` | 无 warmup |
| `a4-nowarmup-03` | 699.6 | 742.1 | `INTERCEPT_CONFIRMED` | 无 warmup |
| `a4-nowarmup-04` | 703.5 | 743.3 | `MISSION_FAILED(TIMEOUT)` | infra-free；mission 终态照实报告 |
| `a4-nowarmup-05` | 701.0 | 749.1 | `INTERCEPT_CONFIRMED` | 无 warmup |

- **5/5 infra-free**：own 694.0–703.5 ms、intruder 742.1–750.4 ms，均 < 1000 ms、无 `create entities failed`。

### A5b warmup（A/B 对照）

| run | own participant_ms | intruder participant_ms | warmup participant_ms | 终态 |
|---|---:|---:|---:|---|
| `a5b-cold-01` | 640.7 | 757.4 | 10030.8 | `INTERCEPT_CONFIRMED` |
| `a5b-cold-02` | 642.0 | 764.2 | 14448.6 | `INTERCEPT_CONFIRMED` |
| `a5b-cold-03` | 650.6 | 759.3 | 10202.4 | `INTERCEPT_CONFIRMED` |
| `a5b-cold-04` | 752.1 | 762.6 | 10254.7 | `INTERCEPT_CONFIRMED` |
| `a5b-cold-05` | 643.0 | 772.5 | 13195.8 | `MISSION_FAILED(TIMEOUT)` |

- warmup 自身每回合 1 次 `create entities failed`（预期）；own/intruder 均 < 1 s。
- 失败样本（修复前）：`20261024-w7-rl-b-firectl-s15-s5-headless*` 的 own 为 1.28–3.09 s；intruder 0.72–0.76 s。
- 冷启动期间 `/dev/shm` fastrtps 段数：A5b 221 → 325；A4 173 → 242（未手工清理；增长与 run 数大致线性，无 SHM 初始化失败）。
- **最终默认配置回归（A7，`px4_warmup=false` / own 25 s / intruder 35 s，不显式传参）**：`a7-final-default-01` own 701.3 / intruder 737.2 ms；`a7-final-default-02` own 701.2 / intruder 751.0 ms；均 `INTERCEPT_CONFIRMED`、`create entities failed` 0、infra 0；shm 251 → 259。
- 诊断报告：[`experiments/w7-rl-b/20261024-w7-rl-b-uxrce-diagnosis/metrics/uxrce_diagnosis.md`](../../experiments/w7-rl-b/20261024-w7-rl-b-uxrce-diagnosis/metrics/uxrce_diagnosis.md)。
- 探针：[`scripts/uxrce_participant_probe.py`](../../scripts/uxrce_participant_probe.py)；各条件 JSON 见诊断报告索引。

## 备选

1. **仅放宽 PX4 1 s 预算**（patch 到 5 s）——否决（本变更内）：命中 PX4 pin 红线；需独立 ADR / patch / 构建 / pin 更新。
2. **仅依赖 runner 重试**（ADR-0075 方案 B）——否决：持续偏高时 4/4 失败，且违反“不能只靠某次重试成功”的验收。
3. **仅 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`**——不采纳为默认：20 节点下首跑仍 `create entities failed`；长尾虽降到 ~0.55 s，但不足以单独保证 1 s 预算。
4. **仅错峰 12/25、不加 warmup**——不足：12 s 时 own 仍是首个 participant，实测 1.28–3.09 s；**25/35 错峰（不加 warmup）已足够**（A4 5/5，own 694–704 ms）。
5. **warmup + 25/25 同时启动**——否决：实测 own+intruder 双双超时（`20261024-w7-rl-b-a4-warmup-delay25`）。
6. **warmup + 12/25**——部分有效（`20261024-w7-rl-b-a4-warmup-smoke` 成功），但 own 仍 1.54 s；不作为默认。

## 后果

- **正面**：整链在连续冷启动下可复现地进入 1 s 内；无需改 PX4 pin；infra 不再依赖重试。
- **代价 / 限制**：
  - 启动墙钟增加约 13 s（own 12→25）/ 10 s（intruder 25→35）；单 episode 墙钟约 110–130 s，`w7b_arms_runner --timeout` 默认提高到 240 s。
  - warmup 默认关闭；若显式开启，每回合多一个 SIH 进程（约 6.5 s 生命周期），并短暂产生 `/px4_3/fmu/out/*` 话题。
  - 25/35 错峰把启动墙钟后移；报告须记录 own/intruder participant_ms（以及开启 warmup 时的 warmup participant_ms）。
- **未决**：
  - W7-c 多 worker 下 warmup / 错峰是否仍成立（每 worker 独立 agent / netns 后应成立，需 C 阶段验证）。
  - 若未来必须恢复 12/25 启动时序，需另立 ADR 并给出新的 1 s 预算方案。
- **不改变**：P1 / P2 verdict、预注册阈值 / N / 种子、契约 ABI、执行口、安全层 / 终态语义。

## 参考

- 前序：[ADR-0075](0075-uxrce-entity-creation-intermittent-failure-and-infra-retry.md)、[ADR-0093](0093-w7b-exit-closure-and-prefix-provenance.md)。
- 代码：[`w6.launch.py`](../../src/agc_task/launch/w6.launch.py)、[`episode_runner.py`](../../scripts/episode_runner.py)、[`w7b_arms_runner.py`](../../scripts/w7b_arms_runner.py)。
- spec：[`restore-fullchain-infra-and-w7c-admission`](../archive/specs/restore-fullchain-infra-and-w7c-admission/spec.md)。
- 运维：[`整链排障速查`](../conventions/整链排障速查.md)。
