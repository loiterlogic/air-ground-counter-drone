<a id="research"></a>
# scripts/research/ 索引

> **语义**：**暂停但未废弃**的研究期工具。它们为 W7 / W8 的判定、诊断、取证与复跑服务；迁移推进与论文优先已暂停（暂停事实见 [当前方向](../../docs/plan/README.md#plan-index)；原 `PAUSED.md` 开关已于 2026-10-31 退役，[ADR-0025](../../docs/adr/0025-publishing-boundary-and-retirement.md#top)），当前阶段不调用，但**脚本可复跑、可复核，一个都不删**（研究脚本是证据链的一部分）。
> **与 [archive/](../archive/README.md#archive) 的区别**：`archive/` 是"一次性、证据归档后冻结"；本目录是"研究暂停、仍可重跑"。混在一起会稀释 archive 的冻结语义。
> 顶层长期工具见 [scripts/README.md](../README.md#top-tools)；规则见 [目录与命名规范](../../docs/conventions/目录与命名规范.md#10-产物分类与生命周期)。
> **本表由 [`scripts/tests/test_scripts_index.py`](../tests/test_scripts_index.py) 自动核对**：目录中多一个或少一个脚本都会让测试失败。

<a id="tools"></a>
## 工具清单（20 个）

| 文件 | 用途 | 产物 / 依赖 |
|---|---|---|
| [`w7_episode_runner.py`](w7_episode_runner.py) | W7-a 单 worker 可重放 runner（spec R4）；复用 `episode_runner` 的进程组回收 | `experiments/w7-rl/` |
| [`w7b_arms_runner.py`](w7b_arms_runner.py) | W7-b T6：臂与消融批量跑（R1–R3；P1 需整链双 PX4） | 复用顶层 `episode_runner` |
| [`w7b_worker_repeatability.py`](w7b_worker_repeatability.py) | **只读**单 worker 重复性 / 时间线诊断（ADR-0024）；被 `w7b_gui_headless_recheck` / `w8_gui_headless_pilot` 复用的解析库 | `metrics/*.json,md` |
| [`w7b_gui_headless_recheck.py`](w7b_gui_headless_recheck.py) | **只读** GUI / headless 同口径复核（ADR-0024 R5）；不新增 run、不改写既有报告 | `metrics/gui_headless.{json,md}` |
| [`w7b_p1_adjudicate.py`](w7b_p1_adjudicate.py) | 按**预注册规则**裁定 P1（协同 vs 非协同）；`w7b_p2_adjudicate` 复用其 DV 规约 | `metrics/p1_adjudication.json` |
| [`w7b_p2_adjudicate.py`](w7b_p2_adjudicate.py) | 按**预注册规则**裁定 P2（臂 B 规则高层 vs 臂 A `c2`） | `metrics/p2_adjudication.json` |
| [`w7b_p1_ablation.py`](w7b_p1_ablation.py) | P1 机制消融（指向 × 跟踪参考 2×2）的**估计算**分析（ADR-0023） | `metrics/p1_ablation.{json,md}` |
| [`w7b_p2_arm_b_diagnose.py`](w7b_p2_arm_b_diagnose.py) | P2 臂 B（`p2_rl_high`）**负向结果**诊断（ADR-0023） | `metrics/p2_arm_b_diagnosis.{json,md}` |
| [`w7b_p1_decompose_fco.py`](w7b_p1_decompose_fco.py) | **描述性**拆解 P1 primary DV（FCO）组成（ADR-0022/0087）；不参与判定 | `metrics/p1_fco_decomposition.{json,md}` |
| [`w7b_p1_point_only_failures.py`](w7b_p1_point_only_failures.py) | P1 消融③（仅指向）失败回合**描述性**诊断（ADR-0023） | `metrics/p1_point_only_failures.{json,md}` |
| [`w7b_p2_prediction_chain.py`](w7b_p2_prediction_chain.py) | P2 射击 `pred` 误差的预测链分解（ADR-0023） | `metrics/p2_prediction_chain.{json,md}` |
| [`w7b_p2_map_trigger_audit.py`](w7b_p2_map_trigger_audit.py) | P2 臂 B「地图变化」触发来源 / 路径影响审计（ADR-0013） | `metrics/p2_map_trigger_audit.{json,md}` |
| [`w7b_fire_control_lifecycle.py`](w7b_fire_control_lifecycle.py) | 逐 shot 火控生命周期分析（ADR-0011 / FL-5） | `metrics/fire_control_lifecycle.{json,md}` |
| [`w7b_p2_replan_bench.py`](w7b_p2_replan_bench.py) | P2 臂 B「重规划触发」**受控台架**（C1–C8，ADR-0007/0056/0092） | 台架结论写 ADR，非 run 产物 |
| [`w7b_build_offline_dataset.py`](w7b_build_offline_dataset.py) | W7-b T5：从既有 run 产物构建离线数据集 / 回放库索引（可重建） | `config/dataset_manifest.json`、`metrics/dataset.json` |
| [`w7c_worker_run.py`](w7c_worker_run.py) | W7-c 单 worker 启动器（rootless netns + 归属环境）；子进程调 `research/w7b_arms_runner.py` | `experiments/<campaign>/<run>/worker_<n>/` |
| [`w8_determinism_probe.py`](w8_determinism_probe.py) | W8 P1 串行固定条件确定性探针（不可变输入、计数式报告）；子进程调 `research/w7b_arms_runner.py` | `experiments/w8-p1-redo/<batch>/` |
| [`w8_gui_headless_pilot.py`](w8_gui_headless_pilot.py) | W8-E1 GUI / headless 模式等价 pilot 编排与报告（ADR-0021）；子进程调 `research/w7b_arms_runner.py` | `metrics/gui_headless_pilot.{json,md}` |
| [`w8_mission_fco_audit.py`](w8_mission_fco_audit.py) | ADR-0021 `mission_fco_fixed_budget_v1` 证据的**只读**审计 | 只读，不落 run 产物 |
| [`uxrce_participant_probe.py`](uxrce_participant_probe.py) | uXRCE「agent 侧 participant 创建耗时」重复测量探针（ADR-0027） | 诊断 JSON（见 ADR 索引） |

> **为什么这 20 个在 `research/` 而不是顶层**：它们都绑定某次 W7/W8 workstream 的判定 / 诊断口径（多为 ADR-0023…0099 的产物生成器），当前阶段不调用；但判定可复核、run 可复跑，属"暂停未废弃"，既不能删也不该挤占顶层。

<a id="deps"></a>
## 迁移后的路径约定（P0-4）

移入子目录只改了**路径**，没有改任何算法 / 指标 / 判定行为。三处机制：

| 机制 | 说明 |
|---|---|
| **项目根** | `w8_determinism_probe.py` 原用 `Path(__file__).parents[1]` 推项目根，迁移后为 `parents[2]`。其余脚本沿用固定的 `ROOT = '/home/chen/AGC'`（与迁移前一致，不受层级影响）。 |
| **同级导入** | `w7b_p2_adjudicate.py`（`from w7b_p1_adjudicate`）、`w7b_gui_headless_recheck.py` 与 `w8_gui_headless_pilot.py`（`import w7b_worker_repeatability`）用 `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` —— 用自身目录，迁移后自动指向 `scripts/research/`，无需改动。 |
| **复用顶层库** | `w7_episode_runner.py` / `w7b_arms_runner.py` 以 `sys.path.insert(0, os.path.join(ROOT, 'scripts'))` 导入顶层 `episode_runner`，路径仍正确。 |
| **子进程脚本路径** | `w7c_worker_run.py`、`w8_determinism_probe.py`、`w8_gui_headless_pilot.py` 调用 `w7b_arms_runner.py` 的路径已改为 `scripts/research/...`。 |

<a id="migration"></a>
## 迁移导航（P0-4，2026-10-29）

旧路径（历史命令证据中仍可能出现）→ 新路径：

| 旧路径 | 新路径 |
|---|---|
| `scripts/w7_episode_runner.py` | `scripts/research/w7_episode_runner.py` |
| `scripts/w7b_arms_runner.py` | `scripts/research/w7b_arms_runner.py` |
| `scripts/w7b_worker_repeatability.py` | `scripts/research/w7b_worker_repeatability.py` |
| `scripts/w7b_gui_headless_recheck.py` | `scripts/research/w7b_gui_headless_recheck.py` |
| `scripts/w7b_p1_adjudicate.py` | `scripts/research/w7b_p1_adjudicate.py` |
| `scripts/w7b_p2_adjudicate.py` | `scripts/research/w7b_p2_adjudicate.py` |
| `scripts/w7b_p1_ablation.py` | `scripts/research/w7b_p1_ablation.py` |
| `scripts/w7b_p2_arm_b_diagnose.py` | `scripts/research/w7b_p2_arm_b_diagnose.py` |
| `scripts/w7b_p1_decompose_fco.py` | `scripts/research/w7b_p1_decompose_fco.py` |
| `scripts/w7b_p1_point_only_failures.py` | `scripts/research/w7b_p1_point_only_failures.py` |
| `scripts/w7b_p2_prediction_chain.py` | `scripts/research/w7b_p2_prediction_chain.py` |
| `scripts/w7b_p2_map_trigger_audit.py` | `scripts/research/w7b_p2_map_trigger_audit.py` |
| `scripts/w7b_fire_control_lifecycle.py` | `scripts/research/w7b_fire_control_lifecycle.py` |
| `scripts/w7b_p2_replan_bench.py` | `scripts/research/w7b_p2_replan_bench.py` |
| `scripts/w7b_build_offline_dataset.py` | `scripts/research/w7b_build_offline_dataset.py` |
| `scripts/w7c_worker_run.py` | `scripts/research/w7c_worker_run.py` |
| `scripts/w8_determinism_probe.py` | `scripts/research/w8_determinism_probe.py` |
| `scripts/w8_gui_headless_pilot.py` | `scripts/research/w8_gui_headless_pilot.py` |
| `scripts/w8_mission_fco_audit.py` | `scripts/research/w8_mission_fco_audit.py` |
| `scripts/uxrce_participant_probe.py` | `scripts/research/uxrce_participant_probe.py` |

- 全部用 `git mv` 迁移，`git log --follow scripts/research/<name>.py` 可追溯迁移前的历史。
- 历史文档（ADR / 归档规格 / 归档报告 / `experiments/` 内命令串）**保留旧路径不重写**；本表即查旧路径的映射。
- 迁移前 `scripts/` 顶层 33 个执行脚本（32 `.py` + 1 `.sh`），不是现行状态；现行状态见 [scripts/README](../README.md#top-tools)。
