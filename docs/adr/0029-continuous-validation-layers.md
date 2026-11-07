<a id="top"></a>
# 持续验证：三层回归入口与"负例加严"判定

## Status

accepted（2026-11-04）

## 背景

项目有 57 个 `tests/` 验收核查，但长期缺三件东西：**每次提交能跑的离线门槛**、
**定时的 `full` 整链回归**、以及**回归矩阵**（N2 结档时提出的四类回归要求，一直未执行）。
后果是"改完一行代码该跑什么"没有可执行答案，而仿真类缺陷（DDS、PX4 起飞竞态）
只能靠人肉复现。

更具体的一个缺口：**无目标负例从未跑过**。矩阵要求"目标不在视场内时不得产生虚假航迹
并导向成功"—— 这是唯一能证明系统**不造假**的验证，缺了它，所有"能成功"的记录都缺少对照。

## 决策

<a id="three-layers"></a>
### (a) 三个入口，职责不重叠

| 入口 | 跑什么 | 何时 | 启仿真 | 预算 |
|---|---|---|---|---|
| `tests/run_smoke.py` | 离线冒烟 7 组 | 每次提交 | 否 | ~40 s |
| `tests/run_full_regression.py` | `full` 整链 3 场景 | 定时 | 是 | ~240 s |
| `tests/run_regression_matrix.py` | 回归矩阵 **4 格**（原 5 格；无目标负例已因无承载者移除，见 (e)） | 里程碑 | 是 | ~520 s |

三者**不得互相替代**：headless 回归替代不了 GUI 验收；离线冒烟也证明不了整链能力。

<a id="negative"></a>
### (b) 负例必须"加严"判定

只断言"终态是 `MISSION_FAILED`"是**无效**的—— 链路没起来也会失败。负例通过还须同时证明
**失败原因是看不见**：

* `visibility_rate == 0.0`（整个 episode 从未认可见目标）；
* `reason_code == TIMEOUT`；
* 无任何 `fco_exposure_s > 0`（没有"看见过"的证据）。

**2026-11-04 更正：本负例当前无有效承载者，已从矩阵移除。**

原设计用 `s17` 的"视场收窄到近零"（`perception=no_target` + `perception_sensors_no_target.yaml`
的 `hfov/vfov = 0.1°`）制造"看不见"，目标真值仍在世界里并照常发布。该机制**依赖
`air_perception` 的 `gatePoint` 被消费**。但 `air_fusion` 退役后 `/agc/air/obs` **无人订阅**，
而 `/agc/targets` 的唯一发布者 `gt_adapter` **无几何门控、不分远近** ⇒「看不见」**无法构造**。

> **旧实测记录不再作为负例成立的证据**（如实更正）：`2026-11-04` 的几次 `s17` 实跑确实落到
> `MISSION_FAILED(TIMEOUT)`，但那只是 `t_max_s = 40` 到点，**不是**被感知拒；
> 当时引用的 `gate_ok=0` / `fov_az` 是 `air_perception` 自己的诊断，而它的输出没人消费——
> 用无消费者的门控当"负例成立"的证据属**错口径**，已作废。

`s17` 现于 `scenarios.yaml` 标 `unsupported:perception`（`carrier_entry` 启动期**拒绝运行**）。
恢复需给 `gt_adapter` 加可致盲开关（`confidence < confidence_min` 或 `drop_prob = 1.0`），
属**新决策、未立项**。上面三条加严判据**保留**，作为恢复后的判据模板。

<a id="vision"></a>
### (c) 原 vision 臂已删除（视觉定位路径退役）

本 ADR 原有一节论证"vision 臂按感知代价判、不要求成功"，理由是 ADR-0009 禁止用真值补齐检测，
所以"vision 也必须 `TRACKING_SUCCESS`"是错判据。

**2026-11-04 起该节作废**：视觉定位路径整体删除（[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top) (b)），
矩阵不再有 `vision-cost` 格，因此也不再有"vision 判定口径"。

保留的教训（对将来任何"某臂不要求成功"的判据都适用）：**不要求成功的臂，必须给出
可判定的事实清单**，否则"没成功"与"没跑起来"无法区分。原 vision 臂用的三条
（证据可区分 / 代价可测 / 不得假成功）思路仍可复用，但**没有活跃承载者**。

「无目标负例」（`s17`）的加严判据见 (b)，与 vision 无关，仍然有效。

<a id="infra"></a>
### (d) infra 与能力失败分开统计

`ready=false`、`wall_watchdog_timeout`、`air_hover_timeout` 属 **infra**，标记为 `INFRA` 而非
`FAIL`。理由：把它们混进"能力失败"会让通过率失去意义，也会诱导"改预算"这种假修复。

<a id="gui"></a>
### (e) GUI 验收独立留证

`scripts/demo/capture_run.py --scene <可达终态场景>` 取三张代表帧 + 连续帧 + `capture-manifest.json`
（含 `run_exit`、帧数、skyband 判定）。**必须给可达终态的场景**：默认场景在 GUI 下偶发
`air_hover_timeout`，那时时间线无状态跳变，三张图取不到。

已知局限：固定俯视机位下"启动/跟踪"两图可能几乎相同—— 工具在 manifest 的 `notes` 里
**如实标注**，不伪装成三张不同时刻。

<a id="toolchain"></a>
### (f) toolchain pin 一致性进冒烟

`scripts/toolchain_pin_check.py` 原本只有单测、**没有接任何门槛**（等于不跑）。现接入冒烟
`toolchain` 组（实测 41/41 PASS）。pin 清单真源仍是 `toolchain/README.md` 的机器可读块
（[ADR-0005](0005-px4-toolchain-and-link.md#top)(c)），本项只负责"每次提交都验证它没漂"。

## 不做什么

- **不**把 57 个验收核查全塞进冒烟：多数需整链环境，语义是"验收"而非"冒烟"。
- **不**以 headless 回归替代 GUI 验收（契约）。
- **不**为了"看起来绿"而放宽负例判据或跳过矩阵格。
- **不**追求 PX4/toolchain 的**从空目录重建**自动化：pin 一致性与"可从零重建"是两件事，
  后者未验证，不在本篇范围内声称。

## Consequences

- 三层入口实测：冒烟、整链 3/3、矩阵（视觉臂删除后 5 格；无目标负例移除后为 **4 格**）。
- 负例判据有**自测**守护（`scripts/tests/test_dds_contract_guard.py`），防止断言被悄悄放宽成"只看终态"；
  同一文件另有 `test_vision_localization_path_is_retired` 作为**防复活闸门**。
- **已知未修**：`full` 整链偶发 `air_hover_timeout`（约 1/10，与 GUI/headless、错峰参数
  均无稳定相关；重跑即过）。根因未定位，已在
  [整链排障速查](../conventions/整链排障速查.md#dds-transport) 登记为 infra 竞态。
