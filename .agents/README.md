<a id="skills"></a>
# .agents/ — 项目级 Agent 资产

> **角色**：本目录存放**项目级可复用 Agent 资产**（当前只有技能），随仓库入库、供任何 Agent 会话使用。
> **不是约束**：技能是"怎么做某类事"的操作手册，不是项目约束；约束见 [契约真源](../docs/ROS2迁移交接文档.md#hard-constraints)。

## 为什么在这里

2026-10-29 用户裁定**退役 Trae**（[ADR-0025](../docs/adr/0025-publishing-boundary-and-retirement.md#top)）。原 `.trae/skills/` 的 4 个技能迁到本目录：

- `.agents/skills/` 是 DSH Harness 的**默认扫描根**之一（`@deepseek-ai/dsh-skill-filesystem` 的 `project-agents`，rank 200），放在这里会话就能直接发现并加载；
- 技能是可复用的工程资产（不含密钥、本机路径或生成物），应当入库共享，而不是跟着已退役的编辑器一起忽略。

## 技能清单

| 技能 | 用途 | 何时用 |
|---|---|---|
| [`domain-modeling`](./skills/domain-modeling/SKILL.md) | 维护术语表、写 ADR | 定义/争议项目术语，或要记录难以逆转的设计决定 |
| [`grilling`](./skills/grilling/SKILL.md) | 逐轮深度访谈（设计树） | 用户要求压力测试一个计划/想法 |
| [`grill-me`](./skills/grill-me/SKILL.md) | 只访谈、不落文档 | 用户说 "grill me" |
| [`grill-with-docs`](./skills/grill-with-docs/SKILL.md) | 访谈并同步写 ADR / 术语 | 用户要边访谈边记录决定 |
| [`map-design`](./skills/map-design/SKILL.md) | 设计/修改场景地图：先设计后动手、几何闸门、材质与派生链、GUI 取证 | 新增或重做地图、加障碍、调布局材质、判断候选布局能否过核查 |

`domain-modeling` 另带两个格式资源：[ADR-FORMAT.md](./skills/domain-modeling/ADR-FORMAT.md)（本仓库实际的 `## Status` 节写法、`scripts/adr_index.py` 的用法）、[GLOSSARY-FORMAT.md](./skills/domain-modeling/GLOSSARY-FORMAT.md)（单上下文术语表写法）。

`map-design` 按需加载四个资源：[GATES.md](./skills/map-design/GATES.md)（几何可行性闸门的口径与公式）、[SCHEMA-AND-DERIVATION.md](./skills/map-design/SCHEMA-AND-DERIVATION.md)（yaml schema、材质、五条派生链）、[EVIDENCE.md](./skills/map-design/EVIDENCE.md)（取证、GUI、运行与内存陷阱）、[references/MAP_DESIGN_PLAYBOOK.md](./skills/map-design/references/MAP_DESIGN_PLAYBOOK.md)（**历史快照**：2026-10-31 从根目录迁入的原 Playbook，只用于追溯"为什么现在是这样"，其中数字会漂移，现行值以 `tests/w6_geometry_check.py` 为准）。

## 技能格式（Harness 要求）

```text
.agents/skills/<name>/SKILL.md   ← 只发现直属 <name>/SKILL.md，不递归找嵌套的 SKILL.md
```

- YAML frontmatter 必填 `name` 与 `description`；可选 `whenToUse`、`metadata`、`user-invocable`、`disable-model-invocation`。
- 其他资源（如 `ADR-FORMAT.md`）与 `SKILL.md` 同目录，技能正文用相对链接引用。
- frontmatter 写坏时，该技能会**随警告被跳过**（Harness 日志里有 warning），因此**技能目录里看不到它**；
  但模型侧**不会**收到逐技能诊断，无法区分"技能不存在"与"技能无效"。改完请确认技能仍出现在会话技能目录中，
  看不到就先查 frontmatter（`name` 须 kebab-case、`description` 必填），不要当成没生效。

## 维护原则

- **工具名必须是当前 Harness 真实存在的**（`skill`、`ask_user_question`、`worker`、`send_message`、读写与检索工具）。历史轮次里的 Trae 工具名（`Agent` / `Explore` / `AskUserQuestion`）已全部替换。
- **工具缺失要写明确回退**，不能让读者去调用不存在的工具。
- **事实自查**：技能里要求"查事实"时，自己读文件/跑只读命令，不把可查的事实推给用户。
- **不强制访谈**：`grilling` 系列只在用户明确要求设计访谈时触发；普通实现任务不应被访谈或"最终再确认"阻塞。
- **技能不做真源**：技能里不复制约束、不复述规格；指回 [契约真源](../docs/ROS2迁移交接文档.md#hard-constraints)、[ADR 索引](../docs/adr/README.md#adr-index)、[项目完成路线](../docs/plan/README.md#plan-index)。
- **技能里不钉死会漂移的事实**：易变的实测值（实体数、覆盖率、净空、内存占用）用"跑哪个命令读哪个产物"表达，历史数值只放**明确标注为历史快照**的资源里，且不再冒充现行约束。
