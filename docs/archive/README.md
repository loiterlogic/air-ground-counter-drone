<a id="archive"></a>
# docs/archive/ — 历史归档导航

> **角色**：本目录存放**已退出当前执行路径**的历史文档。它们仍是有效证据，但**不是当前入口、不是约束、不是进度真源**。
> **当前方向**见 [项目完成路线](../plan/README.md#plan-index)；活约束见 [契约真源](../ROS2迁移交接文档.md#hard-constraints)。
> **引用纪律**：可以**明确标注为历史**地按需链接；不得把这里的内容当作现行规定，也不得为了让链接"看起来干净"而删掉有效的历史引用（[ADR-0105](../adr/0105-retire-trae-and-relocate-specs-skills.md)）。

## 归档了什么

| 内容 | 位置 | 归档原因 | 是否发布 |
|---|---|---|---|
| 迁移 Runbook（原 `docs/ROS2迁移步骤.md`，347 行） | [ROS2迁移步骤.md](./ROS2迁移步骤.md#top) | 迁移动员令已暂停，它是 W0–W8 的编排史，不是"现在做什么" | ✅ 入库 |
| ROS1 基线盘点（原契约附录 A，47 行） | [ros1-baseline.md](./ros1-baseline.md#appendix-a-archived) | 纯历史，混在契约真源里会让每次开工都读到历史 | ✅ 入库 |
| 历史 workstream 规格（原 `.trae/specs/`，32 目录 / 97 文件） | 仅**本地完整工程**存在：`docs/archive/specs/README.md`（索引）、`docs/archive/specs/MIGRATION.md`（迁移清单） | Trae 已退役（用户 2026-10-29 裁定）；规格仍是历史证据 | ❌ **不发布**（`.gitignore` 精确忽略，保持原边界） |

> **规格路径只在本地完整工程里可解析**。`docs/archive/specs/` 被 `.gitignore` 精确排除，
> 因此**公开 clone 中没有该目录，也没有它的索引**；上面两个路径是**本地相对路径说明**，不是公开链接。
> 这是**沿用原边界**而不是新增限制：`.trae/` 本来就整体在 `.gitignore` 里（[ADR-0081](../adr/0081-public-repo-publishing-boundary.md)）。
> 校验口径：`tests/docs_link_check.py` 把指向该目录的链接单列统计（"本地可解析 N 条 / 本地也缺失 0 条"），
> **不计入断链，也不宣称公开 clone 可导航**。

## 怎么查

- **想知道某历史 workstream 当时承诺了什么** → 在**本地完整工程**里读 `docs/archive/specs/README.md` 的目录表（公开 clone 无此文件），只打开命中的那一两个文件。
- **想知道某轮为什么这么改** → 决策看 [ADR 索引](../adr/README.md#adr-index)，交接过程看 `.coordination/archive/`。
- **想对照旧系统行为** → [ROS1 基线盘点](./ros1-baseline.md#appendix-a-archived)；代码侧的旧树在 `reference/`（只读）。

## 边界

- 归档 ≠ 删除。所有移动都用 `git mv`（tracked）或受检 `mv`（ignored），未被删除。
- 归档文档的**正文结论、数字、哈希与命令证据不重写**；只允许修纯路径与导航（[ADR-0066](../adr/0066-decision-applicability-and-reference-discipline.md)）。
- 归档文档内部仍可能残留指向**当时**路径的链接（例如 `.coordination/task/` 在归档后改名）。这些是历史事实，逐条列在 [P0-3 出口判据](../plan/p0-3-文档瘦身与入口重构.md#p0-3-exit) 的"已知历史缺失"里，不用宽泛忽略掩盖。
