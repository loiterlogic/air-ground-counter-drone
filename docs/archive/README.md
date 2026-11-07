<a id="archive"></a>
# docs/archive/ — 历史归档导航

> **角色**：本目录存放**已退出当前执行路径**的历史文档。它们仍是有效证据，但**不是当前入口、不是约束、不是进度真源**。
> **任务计划规则**见 [任务计划规则](../plan/README.md#plan-index)；活约束见 [契约真源](../adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints)。
> **引用纪律**：可以**明确标注为历史**地按需链接；不得把这里的内容当作现行规定（[ADR-0025](../adr/0025-publishing-boundary-and-retirement.md#top)）。

## 归档了什么

只剩两份**不可替代**的历史材料：

| 内容 | 位置 | 为什么还留着 |
|---|---|---|
| 迁移 Runbook（原 `docs/ROS2迁移步骤.md`） | [ROS2迁移步骤.md](./ROS2迁移步骤.md#top) | 它是 W0–W8 的**编排史**，回答"当年按什么顺序推、每段出口是什么"，ADR 不承载编排顺序 |
| ROS1 基线盘点（原契约附录 A） | [ros1-baseline.md](./ros1-baseline.md#appendix-a-archived) | 旧树已删（`reference/` 2026-10-31 退役），这是**唯一**的旧系统行为记录 |
| 预注册冻结快照（6 份） | [frozen-prereg-snapshots/](./frozen-prereg-snapshots/) | 见下节：它们是**冻结时的原文字节**，供按原文复核研究预注册 |

## 预注册冻结快照：**故意与活跃配置不同**

`frozen-prereg-snapshots/` 里的 6 份 YAML 是 2026-11-06「代码层编号清零」**改写前**的原文字节。
它们与 `src/agc_rl/config/` 下的同名活跃配置**内容不同**，这是**有意的**，不是漂移：

差异分**两类**，都是预期的：

| 类别 | 差异 | 冻结快照 | 活跃配置 |
|---|---|---|---|
| **措辞** | 过程编号（`W8` / `W7-c` / `F-04` 等） | **保留**（当时就是这样写的） | 已清除 |
| **措辞** | 契约引用形式 | 当时的历史路径 | 现行 `ADR-NNNN` |
| **版本** | 预注册版本号与执行状态 | 冻结那一刻的版本（多为 v1 / `pre_registered`） | 现行版本（如 `research_prereg.yaml` 已到 v6 / `executed`） |

**版本差异不是缺陷**：预注册按版本演进（v1 → v6），活跃配置跟着走，而快照**永远停在 v1**。
这正是"冻结"的含义——历史判定必须能按当时的规则复核，不能拿 v6 的阈值去解释 v1 的 run。

**为什么不直接改快照去对齐**：快照的用途是"研究预注册可按原文复核"（[ADR-0021](../adr/0021-gui-headless-equivalence.md#top)、
[ADR-0024](../adr/0024-multi-worker-isolation.md#top)）。改写它就等于让复核对象消失，
而过程编号在**历史证据**里是合法的（[ADR-0002](../adr/0002-docs-source-of-truth-and-reference-discipline.md#top)：历史不改写）。

**守护**：[`scripts/tests/test_frozen_prereg_snapshots.py`](../../scripts/tests/test_frozen_prereg_snapshots.py)
把 6 份的 sha256 **钉死**，并断言它们能由登记的冻结提交逐字节复现、且与 ADR 正文记录的短哈希一致。
改一个字节即失败。

## 2026-11-03 删除的内容（不再保留）

| 已删 | 曾经是什么 | 为什么删 | 结论去了哪 |
|---|---|---|---|
| `docs/archive/specs/`（98 文件） | 迁移期 per-workstream 规格三件套 | 决策结论已被 ADR 吸收；验收判据已固化成 `tests/` 的可执行核查；**未入库**，删除即不可 git 恢复 | [ADR 索引](../adr/README.md#adr-index) + `tests/` |
| `docs/archive/completion-20261031/`（11 文件） | 收尾路线 P0–P2 逐任务记录 | 结论已并入 `docs/conventions/` 与 ADR；批次已完成 | ADR + `docs/conventions/` |
| `docs/archive/improvements-20261031/`（5 文件） | 临时改进批次 F1–F4 | 结论已归位：F1 出生布局 → [ADR-0007 (i)](../adr/0007-scene-geometry-single-source-and-layout.md#spawn-layout)；F2 架构图 → `docs/conventions/系统结构图.md`；F3 协作规则 → [ADR-0026](../adr/0026-leader-worker-collaboration-and-batch-authorization.md#top)；F4 地图技能 → `.agents/skills/map-design/` | ADR + `docs/conventions/` + 技能目录 |
| `.coordination/archive/`（249 文件） | Leader/Worker 逐轮派工 / 回报 / 审查台账 | 绝大部分是过程叙事；同一决策在 ADR 里已有最终口径 | ADR + `CURRENT.md` |

> **删除前的必做检查**（本次的教训）：先确认「活文档引用了归档里的**哪些具体数字**」。
> 本次就发现 P1-4 的判据饱和结论（`err_eff p95` 被 `max_step_m=0.1` 饱和，真正区分度在 p50/p99）
> 只存在于归档里，已先补进 [README 已知边界](../../README.md#已知边界当前能力范围) 再删。

## 怎么查

- **想知道某轮为什么这么改** → 决策看 [ADR 索引](../adr/README.md#adr-index)（含「合并映射」表可查旧编号）。
- **想对照旧系统行为** → [ROS1 基线盘点](./ros1-baseline.md#appendix-a-archived)。
- **想复现某条验收** → `tests/` 下同名 `*_check.py`；找不到说明该判据已随规格删除、只剩 ADR 结论。

## 边界

- **归档 ≠ 可改写**。归档文档的正文结论、数字、哈希与命令证据**不重写**；只允许修纯路径与导航（[ADR-0002](../adr/0002-docs-source-of-truth-and-reference-discipline.md#top)）。
- **新内容不再进本目录**：结档结论并入 ADR 或 `docs/conventions/`，过程台账不保留。
- 归档文档内部可能残留指向**当时**路径的链接，那是历史事实，不用宽泛忽略掩盖。
