<a id="request"></a>
# 20261026-001：交接试运行与工作区基线核对

- 派工方：Codex；执行方：Trae / DeepSeek；轮次：1。
- 日期：2026-10-26（Asia/Shanghai）。
- 目标：验证“读取任务 → 核对现场 → 写回证据 → 交回审查”的人工交接闭环，并为下一轮工程派工提供当前工作区事实。
- 性质：行政交接核对，非新工程 workstream；本轮不实施 W8 测量 P3。

## 阅读入口与参照

先按项目入口开工顺序阅读，再核对：

- [Runbook 用法](../../../docs/ROS2迁移步骤.md#usage) 与 [当前进度](../../../docs/ROS2迁移步骤.md#status)。
- 关联当前已完成的测量 P2：[spec](../../../.trae/specs/w8-measurement-p2/spec.md#scope)、[tasks](../../../.trae/specs/w8-measurement-p2/tasks.md#tasks)、[checklist](../../../.trae/specs/w8-measurement-p2/checklist.md#checklist)。
- 上游 W8：[spec](../../../.trae/specs/w8-parity-freeze/spec.md#top)，同目录 tasks/checklist 按其 Markdown 标题读取。
- [P3 待办](../../../docs/adr/0099-w8-fixed-budget-mission-fco-measurement.md#next) 与 [seed 协议](../../../docs/adr/0100-full-chain-seed-protocol.md#top)。
- 同版本已存在的 P2 回报方式：沿上述 spec 与 ADR 的链接读取现有审计摘要，不重新运行审计脚本。
- 硬约束仅引用 [契约](../../../docs/ROS2迁移交接文档.md#hard-constraints)。

## 派工基线

HEAD：`d5072aaff33276bcd1c5e7d38b5caa75fe45a290`；分支：`main`。工作区非干净，以下是创建交接前的已存在改动；它们的作者、完整性和验收状态待核对，不能因文件存在或 ADR 写 accepted 就认定已验证。

```text
 M docs/ROS2迁移步骤.md
 M docs/adr/0074-visibility-metric-fixed-observation-window.md
 M docs/adr/0096-w8-gui-headless-equivalence-design-bounds-and-gate.md
 M docs/adr/0098-w8-determinism-probe-and-measurement-spec-change.md
 M src/agc_air/launch/air_bringup.launch.py
 M src/agc_perception/launch/perception_bringup.launch.py
 M src/agc_task/launch/m0_skeleton.launch.py
 M src/agc_task/launch/w6.launch.py
 M src/agc_task/launch/w6_composition.py
?? docs/adr/0099-w8-fixed-budget-mission-fco-measurement.md
?? docs/adr/0100-full-chain-seed-protocol.md
?? docs/reviews/agc-review-2026-10-25/
?? scripts/tests/test_w8_determinism_probe.py
?? scripts/w8_determinism_probe.py
?? scripts/w8_measurement_p2_audit.py
```

本次建立交接并按用户要求将当前任务固定放在 `.coordination/task/`、结档记录放在 `.coordination/archive/<任务ID>/`；另修改 `AGENTS.md` 的交接索引及 Runbook 用法/目录索引；这是预期变化。最终交接指纹见下方基线指纹节，用来识别 HEAD 未变但内容变化的情况。

## 修改白名单与预算

- 只可修改本任务 `report.md` 及 `.coordination/CURRENT.md` 的领取信息和交接状态。
- 其余项目文件只读；不生成独立实验产物，不修改 request/review，不自动修复发现的问题。
- 实验、构建、测试、审计脚本运行预算均为 0；仅运行只读查询（如 git status/diff、rg、文件读取、sha256sum）。
- 不读取或修改 reference/；不读取运行时会话数据库或凭据；不启动新 worker 或进程清场。

## 执行步骤

1. 检查当前 ID、轮次、状态与基线；领取任务，将交接状态改为 `执行中`。
2. 记录 `git rev-parse HEAD`、`git branch --show-current`、`git -c core.quotePath=false status --short`、相关 `git diff --stat` 和关键文件 SHA256。对照派工基线，区分原有改动、交接新增与未知变化。
3. 只读核对 Runbook、测量 P2 三件套、ADR-0099/0100 及相关 launch 差异。分别报告“文档声称完成”“代码中可见”“有可定位运行证据”“尚无法核验”；不把源码阅读写成运行验证，不把本轮核对扩写成全面审计。
4. 核对 ADR-0099 引用的审计摘要是否可访问，并记录所读取摘要的路径与 SHA256。未发现则报证据缺失，不重跑生成。
5. 指出下一轮派发 P3 前需澄清的事项，尤其现有 seed 协议改动与验证记录是否已闭合；只提出问题，不实施或冻结新计划。
6. 填写本轮执行回报；完成设为 `待审查`。若基线影响执行或出现其他阻塞，写回原因并设为 `阻塞`。

## 验收条件

- 回报包含本任务 ID、轮次、执行者、起止时间及实际工作区基线。
- 至少提供上述只读查询的命令、退出码和结果摘要，以及已读取关键文件的 SHA256。
- 结论均有可定位依据，明确区分历史记录与本轮实际验证，列出缺失证据和待裁定项。
- 只产生白名单内的改动；未运行仿真、构建或测试，未变更工程 gate/历史 verdict。
- 交接状态为 `待审查` 或有明确原因的 `阻塞`；未代填 Codex 验收。

## 停止条件

按 [交接边界](../../README.md#protocol) 处理。对影响本任务的未知工作区变化或互相矛盾的前置依据，停止相关核对、保留现场并报告；不能为了交接成功强行写“通过”。

<a id="fingerprints"></a>
## 基线指纹

由 Codex 在发布时补齐；本节不包含执行者允许更新的 CURRENT/report，也不包含本文件自身。

```text
5cb7962c7347188f28a97ce7b78430727fea349df7b6401f6ebf17df873a662c  .coordination/README.md
25bd518fe6e71629805214b40b2fa15791e4683f4f3d3e2b0cad51a7706feb3d  .coordination/task/review.md
15d9c50d74cbaf3a093eb5530734ca35981220c7326dc8055032d45f5fa35c33  AGENTS.md
bcf41bed4f21777c180823ef2ed6bf4ad4adb05a1b23dfce081d1f0605ae50bf  docs/ROS2迁移步骤.md
e4da9f232b2f3403b7d9321f7939da653cf449e55541addf6399161a98b99b0b  docs/adr/0074-visibility-metric-fixed-observation-window.md
c77cd69b89dbba40b725ed7cb82693da892dd53c6c573e685010e7021ba8acf9  docs/adr/0096-w8-gui-headless-equivalence-design-bounds-and-gate.md
57a3a5aec29cd6048d702bc3456dffe392feccf4790fc2962d210e465942a484  docs/adr/0098-w8-determinism-probe-and-measurement-spec-change.md
a6165c2cd39f81cb92adc79b3d01550d7ba420a23ca69f958cf4e86e866610ef  docs/adr/0099-w8-fixed-budget-mission-fco-measurement.md
7dc1997a842f16e8a230be8afcc54c2c36c0189cf599ac85e0abc5838a85be97  docs/adr/0100-full-chain-seed-protocol.md
ed8238cabe9e7d2213375a5c661c4a637ca6518f2d8b2278ade80298f53cfad2  scripts/tests/test_w8_determinism_probe.py
62876a0b9bec3f0a700fe208ea745f35b97fc856548af23831a637998319fb0a  scripts/w8_determinism_probe.py
39292aa0a38ce39251ba1d2c600f79c1aeba6c16dd7d5d5243f93333b86d3023  scripts/w8_measurement_p2_audit.py
104c572ca3600f4d8761acc9e86e02538a83fba29ae13f10663eed15f473e28c  src/agc_air/launch/air_bringup.launch.py
a4b50fa677412787b1a86cd469212e64338771de5810f25bc4b5621023ebc100  src/agc_perception/launch/perception_bringup.launch.py
e60cd5bc3948b2494fb3343a5b5174999aa8f5629041ac1e2b3a4c40d72a5abc  src/agc_task/launch/m0_skeleton.launch.py
12c46150bbb17390f321632348c7b8e64176f7b5bde3b6926249cc1865fc975d  src/agc_task/launch/w6.launch.py
fea24486b0623c6c09180265c21e069cea26c2019d28f2637f5f9d07e22c8337  src/agc_task/launch/w6_composition.py
```
