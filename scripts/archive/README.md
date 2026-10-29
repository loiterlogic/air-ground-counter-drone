<a id="archive"></a>
# scripts/archive/ 索引

> **语义**：**一次性**驱动 / 台架 / 探针的冻结区 —— 证据归档后**不再改动**，保留供复核（[目录与命名规范](../../docs/conventions/目录与命名规范.md#10-产物分类与生命周期)）。
> 与 [research/](../research/README.md#research) 的区别：本目录的脚本**不预期再复跑**，改动只允许修导航；research 的脚本暂停但可复跑。
> 顶层长期工具见 [scripts/README.md](../README.md#top-tools)。
> **本表由 [`scripts/tests/test_scripts_index.py`](../tests/test_scripts_index.py) 自动核对**：目录中多一个或少一个脚本都会让测试失败。
>
> 历史内容（W5 / W6 / W7 的 65 个脚本）**不改名、不改内容**，自 2026-10-18 与 P0-4 两批 curation 陆续迁入；本文件是它们的导航，首次建立于 P0-4。

<a id="legacy"></a>
<a id="legacy"></a>
## 既有历史内容（62 个，冻结）

自 2026-10-18 curation 起陆续迁入，**不改名、不改内容**。历史 run 的命令行引用的就是它们，
是那些实验产物的**唯一可追溯启动证据**：不要删、不要改写；需要复跑历史 run 时照原样执行
（路径已固化在脚本内，`ROOT=/home/chen/AGC`）。

| 文件 | 用途 |
|---|---|
| [`run_m0.sh`](run_m0.sh) | M0 最小端到端闭环入口（唯一跑法） |
| [`run_w5_fullchain.sh`](run_w5_fullchain.sh) | W5-c R10 全链回归一键跑（launch 背景 + 检查 + 清理） |
| [`run_w5_r007.sh`](run_w5_r007.sh) | W5 R-007 真实仿真验收一键跑（launch 背景 + 杀 RL 命令源 + 脚本化命令源检查 + 清理） |
| [`run_w5_r008.sh`](run_w5_r008.sh) | W5 R-008 失源失效停车故障注入一键跑（launch 背景 + 杀 RL 命令源 + 脚本化命令源检查 + 清理） |
| [`run_w5_r009.sh`](run_w5_r009.sh) | W5 R-009 执行中继 + GZ 末端失效停车一键跑 |
| [`run_w5_r010.sh`](run_w5_r010.sh) | W5 R-010 RL 输入许可与失效停车一键跑 |
| [`run_w5_r011.sh`](run_w5_r011.sh) | W5 R-011 动作方向闭环 + C6 逃逸能力标定一键跑（launch 背景 + 杀 RL 命令源 + 脚本化命令源验收 + 清理） |
| [`run_w5_r012.sh`](run_w5_r012.sh) | W5 R-012 基线路径绑定与重规划失效安全故障注入一键跑（launch 背景 + 检查 + 清理） |
| [`run_w5_safety.sh`](run_w5_safety.sh) | W5-c R9/R4/R5 场景一键跑（launch 背景 + 检查 + 清理） |
| [`run_w6_c5.sh`](run_w6_c5.sh) | W6-a R3/C5（相位复位触发）轻量验收：单独起 trajectory_tracker（无 PX4）+ 检查 + 清理 |
| [`run_w6_fsm.sh`](run_w6_fsm.sh) | W6-a R1/R3（任务状态机 / 成功失败判定）一键验收（launch 背景 + 检查 + 清理） |
| [`run_w6_full.sh`](run_w6_full.sh) | W6 双 PX4 整链一键验收（launch w6.launch.py backend:=full + 机身层检查 + 清理） |
| [`run_w6_intruder.sh`](run_w6_intruder.sh) | W6-a R4（目标 driver 三种运动）命令化验收（逐类型起 driver + 检查 + 清理） |
| [`run_w6_jam.sh`](run_w6_jam.sh) | W6 R8 干扰链（作用包络门控 + 命令输出）轻量验收（无 PX4） |
| [`run_w6_r013.sh`](run_w6_r013.sh) | 评审 R-013（起始异步事务与新鲜门禁）一键验收（launch 背景 + 检查 + 清理） |
| [`run_w6_r014.sh`](run_w6_r014.sh) | 评审 R-014（C7 出生净空统一候选校验）一键验收（launch 背景 + 检查 + 清理） |
| [`run_w6_r015.sh`](run_w6_r015.sh) | 评审 R-015（复位受控事务与失效安全）一键验收（launch 背景 + 检查 + 清理） |
| [`run_w6_r016.sh`](run_w6_r016.sh) | 评审 R-016（入侵者 episode 起点协议）一键验收（自包含 harness + 清理 + 重试） |
| [`run_w6_r017.sh`](run_w6_r017.sh) | 评审 R-017（干扰单一授权与已校验事件）一键验收（自包含 harness + 清理 + 重试） |
| [`run_w6_r018.sh`](run_w6_r018.sh) | 评审 R-018（干扰真实行为确认）一键验收（自包含 harness + 清理 + 重试） |
| [`run_w6_r019.sh`](run_w6_r019.sh) | 评审 R-019（failsafe 因子分离 + 运行时参数锁定）一键验收（自包含 harness + 清理 + 重试） |
| [`run_w6_r020.sh`](run_w6_r020.sh) | 评审 R-020（占位包络标注 + 高度含车体 + 独立干扰包络）一键验收 |
| [`run_w6_r021.sh`](run_w6_r021.sh) | 评审 R-021（捕获事件 episode 关联与一次性复位）一键验收 |
| [`run_w6_r022.sh`](run_w6_r022.sh) | 评审 R-022（FSM 命令幂等与终态锁存）一键验收 |
| [`run_w6_r023.sh`](run_w6_r023.sh) | 评审 R-023（连续跟踪 dwell 逐拍判据中断）一键验收 |
| [`run_w6_r024.sh`](run_w6_r024.sh) | 评审 R-024（三类时间口径与 RTF 记录）一键验收 |
| [`run_w6_r025.sh`](run_w6_r025.sh) | 评审 R-025（整链覆盖矩阵 + 同一 run 因果记录 + pass 命题化）一键验收 |
| [`run_w6_r026.sh`](run_w6_r026.sh) | 评审 R-026（场景轴承载者校验与覆盖记账）一键验收 |
| [`run_w6_r027.sh`](run_w6_r027.sh) | 评审 R-027（安全不可行率诚实口径与真实接触证据）一键验收 |
| [`run_w6_r028.sh`](run_w6_r028.sh) | 评审 R-028（episode 窗口统计、终态锁存与有效样本掩码）一键验收 |
| [`run_w6_r029.sh`](run_w6_r029.sh) | 评审 R-029（唯一运行身份与可复现证据）一键验收 |
| [`run_w6_r030.sh`](run_w6_r030.sh) | 评审 R-030（resetfail 证据矛盾登记与唯一新 run 重做）一键验收 |
| [`run_w6_r031.sh`](run_w6_r031.sh) | 评审 R-031（runner 三层验收判定与完整性硬门）一键验收 |
| [`run_w6_r032.sh`](run_w6_r032.sh) | 评审 R-032（C10 冻结下游封闭）一键验收 |
| [`run_w6_r033.sh`](run_w6_r033.sh) | 评审 R-033（UAV 联合安全屏障与显式不可行路径）一键验收 |
| [`run_w6_r034.sh`](run_w6_r034.sh) | 评审 R-034（生命周期可重复资源状态机与完整失效清理）一键验收 |
| [`run_w6_r035.sh`](run_w6_r035.sh) | 评审 R-035（空中控制唯一权威与控制许可）一键验收 |
| [`run_w6_r036.sh`](run_w6_r036.sh) | 评审 R-036（C1 高度语义统一与同时间证据曲线）一键验收 |
| [`run_w6_r037.sh`](run_w6_r037.sh) | 评审 R-037（传感器/车体限制声明与能力标定）一键验收 |
| [`run_w6_r038.sh`](run_w6_r038.sh) | 评审 R-038（数值模型暴露与配置合法性启动校验）一键验收 |
| [`run_w6_r039.sh`](run_w6_r039.sh) | 评审 R-039（地面 odom 源时刻分离 + 复位 epoch 速度历史）一键验收 |
| [`run_w6_r040.sh`](run_w6_r040.sh) | 评审 R-040（地图内容身份与单调更新序号）一键验收 |
| [`run_w6_r041.sh`](run_w6_r041.sh) | 评审 R-041（目标失效策略与位移阈值化重规划）一键验收 |
| [`run_w6_r2.sh`](run_w6_r2.sh) | W6-a R2（门禁与 episode 起始时序）一键验收（launch 背景 + 尽早介入 + 清理） |
| [`run_w6_r6.sh`](run_w6_r6.sh) | W6-b R6（出生净空 / seed 可复现）一键验收（launch 背景 + 检查 + 清理） |
| [`run_w6_scene.sh`](run_w6_scene.sh) | W6 R5 场景族：按 scene id 起 w6.launch.py backend:=lightweight 并校验期望终态 |
| [`run_w7_baseline.sh`](run_w7_baseline.sh) | W7-a 规则基线可达性（T5 · R5）一键验收。 |
| [`run_w7_core.sh`](run_w7_core.sh) | W7-a 核心库（T1 判定 / T2 obs 版本化 / T3 种子分解）一键核查。 |
| [`run_w7_d1.sh`](run_w7_d1.sh) | W7 入口前置 D1（时空与帧正确：R-002 / R-003）一键对拍。 |
| [`run_w7_replay.sh`](run_w7_replay.sh) | W7-a 单 worker 可重放（T4 · R4）一键验收。 |
| [`w6_r025_full_probe.py`](w6_r025_full_probe.py) | R-025 整链**同一 run 因果证据收集器**。 |
| [`w6_r028_harness.py`](w6_r028_harness.py) | R-028（episode 窗口统计 / 终态锁存 / 有效样本掩码）确定性合成 harness。 |
| [`w6_r032_bench.py`](w6_r032_bench.py) | R-032（C10 冻结下游封闭）**逻辑台架**（Phase A，实跑 trajectory_tracker）。 |
| [`w6_r033_bench.py`](w6_r033_bench.py) | R-033（UAV 联合安全屏障与显式不可行路径）**逻辑台架**（Phase A，实跑 trajectory_tracker）。 |
| [`w6_r034_bench.py`](w6_r034_bench.py) | R-034（生命周期可重复资源状态机与完整失效清理）**逻辑台架**（实跑真实节点）。 |
| [`w6_r035_bench.py`](w6_r035_bench.py) | R-035（空中控制唯一权威与控制许可）**逻辑台架**（实跑真实节点）。 |
| [`w6_r036_bench.py`](w6_r036_bench.py) | R-036（C1 高度语义统一与同时间证据曲线）**逻辑台架**（实跑真实节点）。 |
| [`w6_r037_bench.py`](w6_r037_bench.py) | R-037（传感器/车体限制声明与能力标定）**能力标定台架**（实跑 gz）。 |
| [`w6_r038_bench.py`](w6_r038_bench.py) | R-038（数值模型暴露与配置合法性启动校验）**真实节点启动期拒绝台架**。 |
| [`w6_r039_bench.py`](w6_r039_bench.py) | R-039（地面 odom 源时刻分离 + 复位 epoch 速度历史）**真实节点台架**。 |
| [`w6_r040_bench.py`](w6_r040_bench.py) | R-040（地图内容身份与单调更新序号）**真实节点台架**。 |
| [`w6_r041_bench.py`](w6_r041_bench.py) | R-041（目标失效策略与位移阈值化重规划）**真实节点台架**。 |

> 这些脚本是历史 run 的**唯一可追溯启动证据**：实验产物里的命令行引用的就是它们。**不要删、不要改写**；需要复跑历史 run 时照原样执行，路径已固化在脚本内（`ROOT=/home/chen/AGC`）。

<a id="migrated-p0-4"></a>
## P0-4 迁入（3 个，2026-10-29）

| 文件 | 原路径 | 为什么进 archive | 产物 / 依赖 |
|---|---|---|---|
| [`w7b_full_perception_probe.py`](w7b_full_perception_probe.py) | `scripts/w7b_full_perception_probe.py` | W7-b 步 1「整链评价可用」的**一次性内省取证**探针：需要外部已起 full 整链、由调用方 grep 节点日志；证据已归档，无再跑需求 | 诊断输出（非常驻产物） |
| [`w7c_ab_series.py`](w7c_ab_series.py) | `scripts/w7c_ab_series.py` | W7-c A/B 交替对照**系列编排**：串行起 A/B 两条件各 N 次并快照 PX4 参数，属一次性实验编排（W7-c 已结档） | `experiments/<campaign>/<series_id>/` |
| [`w8_measurement_p2_audit.py`](w8_measurement_p2_audit.py) | `scripts/w8_measurement_p2_audit.py` | W8 测量 P2 的只读证据审计：`OUT` 固定为**一次**归档批次 `experiments/w8-parity/20261026-w8-measurement-p2`、且 `mkdir(exist_ok=False)` 只能跑一次 | `experiments/w8-parity/20261026-w8-measurement-p2/` |

> **为什么不是全塞 research**：这三者的产出与**某一次**已归档证据一一绑定（尤其 `w8_measurement_p2_audit` 硬编码单批次目录且不可重跑），不属"暂停但可复跑"，故按一次性归档。

<a id="migration"></a>
## 迁移导航（P0-4，2026-10-29）

| 旧路径 | 新路径 |
|---|---|
| `scripts/w7b_full_perception_probe.py` | `scripts/archive/w7b_full_perception_probe.py` |
| `scripts/w7c_ab_series.py` | `scripts/archive/w7c_ab_series.py` |
| `scripts/w8_measurement_p2_audit.py` | `scripts/archive/w8_measurement_p2_audit.py` |

- 全部用 `git mv` 迁移，`git log --follow` 可追溯。
- 迁移只改路径与调用路径（`w8_measurement_p2_audit.py` 的项目根由 `parents[1]` 改 `parents[2]`；`w7c_ab_series.py` 子进程调用的两个 runner 改为 `scripts/research/...`），**未改任何算法 / 指标 / 判定行为**。
- 历史文档与 `experiments/` 内的旧命令串**保留不重写**；上表即查旧路径的映射。
