<a id="top"></a>
# 收尾清理批次：退役旧树归档、暂停开关与旧候选清单

## Status

accepted（2026-10-31，来源：用户裁定——"删除 `.trae`、`.vscode`、`reference`，他们都没有用了"；并就逐项确认回选"确认作废 `PAUSED.md`"、"旧候选清单只留 git 历史、不再维护"、"`reference/` 直接删除，我另有备份"）

## 背景

2026-10-31 收尾清理时发现三类**已无实际用途、但仍被活文档引用**的字节与文档，且工作区处于"文件已删 / 文档仍指向它"的互相矛盾状态。按真源分层（[ADR-0002](./0002-docs-source-of-truth-layering.md)），清理必须**同时**处理引用，否则制造悬空链接与失效纪律。

事实：

- `reference/old_ros1/`（旧树归档）**439 MB**，被 `.gitignore` 的 `/reference/` 排除，**不在版本库**（删除不可从 git 恢复）；本仓 `src/` / `tests/` / `scripts/` 中**没有任何代码读取它**，引用只存在于文档与注释。W8 已按"已关闭（非验收）"归档（[ADR-0097](./0097-w8-historical-parity-and-conditional-platform-freeze.md)），旧树用途随之消失。
- `docs/plan/PAUSED.md`（迁移暂停开关）在工作区被删，但 [AGENTS.md](../../AGENTS.md)、[当前方向](../plan/README.md#plan-index)、[spec 模板](../conventions/spec模板.md)、[scripts/research/README.md](../../scripts/research/README.md#research) 仍在指向它。
- HEAD 版 `docs/plan/README.md` 的候选清单 A1–E2（B1–B5 已登记缺口、C1–C5 能力扩展、D1–D3 暂停方向、E1–E2 协作压测）在工作区重写时被整段删除，**未迁往任何别处**。
- 本地残留：`.trae/`（空目录，Trae 已于 [ADR-0105](./0105-retire-trae-and-relocate-specs-skills.md) 退役）、`.vscode/`（个人设置）、`.pytest_cache/`、`__pycache__/`，以及 `.coordination/wake/` 旧回执（叫醒机制已于 [ADR-0102](./0102-leader-worker-dual-model-handoff.md) 退役）。

## 决策

### (a) 退役旧树归档 `reference/`

- **删除** `reference/`（用户确认另有备份）；此后本机不再保留副本。
- 活文档引用**同步改写**：[AGENTS.md](../../AGENTS.md) 铁律"只读旧树"改为"**无旧树**"、[契约真源](../ROS2迁移交接文档.md) 基线声明、[GLOSSARY](../../GLOSSARY.md) 的"只读旧树边界"条目、[spec 模板](../conventions/spec模板.md) 的强制节、[目录与命名规范](../conventions/目录与命名规范.md) 目录树、[`agc_rl/interface.py`](../../src/agc_rl/agc_rl/interface.py) 注释。
- **保留 `.gitignore` 的 `/reference/` 规则**：用户可能从备份恢复，保留可避免再次出现 439 MB untracked。同理保留 `tests/docs_link_check.py` 的 `reference/` 排除项。
- **不改旧 ADR 正文**（[ADR-0066](./0066-decision-applicability-and-reference-discipline.md)）：历史记录只追加、不改写；[ADR-0097](./0097-w8-historical-parity-and-conditional-platform-freeze.md) 以"追加记录"说明其旧树链接已不可解析。

### (b) 退役暂停开关 `PAUSED.md`

- **删除** `docs/plan/PAUSED.md`；**暂停事实不变**，状态改由 [当前方向](../plan/README.md#plan-index) 单一承载。
- 引用同步改写：[AGENTS.md](../../AGENTS.md)、当前方向、[spec 模板](../conventions/spec模板.md)、[scripts/research/README.md](../../scripts/research/README.md#research)，以及 `scripts/adr_index.py` 与 [ADR-FORMAT.md](../../.agents/skills/domain-modeling/ADR-FORMAT.md) 中"暂停记在 plan 的**开关文件**里"的措辞（改为"plan 的**方向索引**"）。
- **显式澄清**：退役开关文件**不等于**恢复迁移。迁移推进、论文优先与 W8 的恢复仍须用户**显式裁定**；当前仍为暂停（[能力闭环路线](../plan/能力闭环路线.md#roadmap) 亦写明"不恢复迁移、W8 或论文批量实验"）。

### (c) 作废旧候选清单 A1–E2

- 用户裁定**只留 git 历史、不再维护**：这批候选不再进入计划索引，也不另行迁移。
- 如需重启，从提交 `5434207` 取回原文；`experiments/` 证据的清理**不在**本 ADR 范围（[ADR-0081](./0081-public-repo-publishing-boundary.md)、[ADR-0064](./0064-evidence-immutable-archive-and-intake-manifest.md)）。

### (d) 退役本地残留与缓存治理

- 删除 `.trae/`、`.vscode/`（均被 `.gitignore` 排除，删除不影响版本库内容）、`.coordination/wake/` 残留回执。
- 删除 `.pytest_cache/` 与 `__pycache__/`（纯缓存，会自动再生）；并把 `.pytest_cache/` **显式加入** `.gitignore`——它原先只靠 pytest 自写的 `.pytest_cache/.gitignore`（内容为 `*`）隐式隐身，**从未**出现在 `git status`，但规则来源不显式、易被误读为"未忽略"（本轮即误读过一次）；显式化后与 `__pycache__/` 同口径。
- `build/`、`install/`、`log/`、`experiments/`、`toolchain/` **不删**：分别是可重建的构建产物、实验证据与 PX4 外部依赖。

## Considered Options

- **保留 `reference/` 只删引用** —— 被否：用户明确要删，且 W8 已关闭、439 MB 无使用场景。
- **保留 `PAUSED.md` 只改文档引用** —— 被否：用户裁定开关文件作废；暂停状态已由 plan 索引承载。
- **手改 `docs/adr/README.md` 索引** —— 被否：索引由 `scripts/adr_index.py` 生成，`--check` 是防漂移护城河。
- **改写旧 ADR 正文里的旧树引用** —— 被否：架构决策记录只追加、不改写（ADR-0066）。

## Consequences

- **正面**：仓库减约 439 MB 字节 + 约 2 MB 缓存；活文档不再指向不存在的路径；"暂停"回到单一真源。
- **代价 / 限制**：旧树事实**本机不可再核对**——[ADR-0021](./0021-ground-safety-thresholds-and-platform-recalibration.md) 等对旧树的溯源只能引其正文记录；日后若须重做 W8 对照，须先从用户备份恢复旧树。
- **残留（有意）**：`docs/archive/` 与 `.coordination/archive/` 内对 `PAUSED.md` 与 `reference/` 的历史链接**保持原样**（历史范围，改写即伪造记录，见 [ADR-0066](./0066-decision-applicability-and-reference-discipline.md)）。

## 参考

- 文档真源分层：[ADR-0002](./0002-docs-source-of-truth-layering.md)
- 决策适用关系与引用纪律：[ADR-0066](./0066-decision-applicability-and-reference-discipline.md)
- 前序退役：[ADR-0105](./0105-retire-trae-and-relocate-specs-skills.md)（Trae）、[ADR-0102](./0102-leader-worker-dual-model-handoff.md)（叫醒机制）
- 旧树与证据相关：[ADR-0001](./0001-greenfield-ros2-rewrite.md)、[ADR-0097](./0097-w8-historical-parity-and-conditional-platform-freeze.md)、[ADR-0064](./0064-evidence-immutable-archive-and-intake-manifest.md)、[ADR-0081](./0081-public-repo-publishing-boundary.md)
- 当前方向：[plan 索引](../plan/README.md#plan-index)、[能力闭环路线](../plan/能力闭环路线.md#roadmap)