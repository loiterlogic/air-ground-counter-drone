<a id="top"></a>
# 退役 Trae：规格迁入 `docs/archive/specs/`、技能迁入 `.agents/skills/`

## Status

accepted（2026-10-29，来源：用户裁定——"完成 P0-3；以后不再用 Trae"，并明确要求把 specs 迁出、把 4 个技能迁到 `.agents/skills` 并适配当前 Harness）

## 背景

本项目的规格与技能原先都放在 `.trae/` 下：

- `.trae/specs/<ws>/{spec,tasks,checklist}.md`：32 个 workstream / 97 个文件，是 W0–W8 的 per-workstream 规格；
- `.trae/skills/{domain-modeling,grilling,grill-me,grill-with-docs}`：4 个可复用技能。

`.trae/` 整体在 `.gitignore` 中（[ADR-0081](0081-public-repo-publishing-boundary.md)），即**规格本来就不发布**。

用户已不再使用 Trae 作为执行宿主。现行宿主是 DSH，其 skill 扫描根之一是 `<projectRoot>/.agents/skills`（`@deepseek-ai/dsh-skill-filesystem` 的默认 rank 200），只发现**直属** `<name>/SKILL.md`（或平铺 `<name>.md`），frontmatter 必填 `name` / `description`。技能正文里原本写的是 Trae 专用工具名（`Agent` / `Explore` / `AskUserQuestion`）和"以 `.trae/` 定根"，在 DSH 下这些名字不存在，照抄会调用失败或让 Agent 去猜。

同时 [P0-3](../archive/completion-20261031/p0-3-文档瘦身与入口重构.md#p0-3-goal) 要把"每次必读"压到最小：迁移 Runbook 与契约附录 A 是历史，不该继续占据真源与入口。

## 决策

### (a) 规格整体迁到 `docs/archive/specs/`，仍然不发布

- `.trae/specs/**` 整目录迁入 `docs/archive/specs/`，**不留转发文件、不留软链**：留转发只会让 Agent 继续按旧路径读到全量历史。
- `.gitignore` 增**精确**规则 `/docs/archive/specs/`，继续不发布；**不** `git add -f` 规格，也**不**因换目录把它们静默提交。
- 允许公开的只是**归档导航**（[`docs/archive/README.md`](../archive/README.md#archive)）与**迁移清单/索引**：索引写在本机，`docs/archive/specs/README.md`、`MIGRATION.md` 同在本目录内一并被忽略，因此公开仓库既没有规格也没有指向不存在文件的死链。

> 为什么放 `docs/archive/`：它和 Runbook、ROS1 基线同属"历史"，在一个可发现的位置；`reference/` 是旧树代码、`experiments/` 是证据，语义都不对。

### (b) 技能迁到 `.agents/skills/`，按当前 Harness 适配

- 4 个技能整目录迁入 `.agents/skills/<name>/`，**作为可复用项目技能入库**（无密钥、无本机路径、无生成物）。
- 适配规则：
  - 工具名换成当前真实存在的：`skill`（加载技能）、`ask_user_question`（向用户提问）、`worker` / `send_message`（派工与回报）、文件读取工具（查事实）。
  - **事实自查**：需要环境事实时自己读文件/跑只读命令，不把"我该查什么"推给用户。
  - 工具缺失时给出**明确的文件读取回退**，不假装调用不存在的工具。
  - 项目根不再"以 `.trae/` 定根"，改为以 `.git` 定位。
  - `grilling` 类技能只在**用户明确要求设计访谈**时进入；普通实现任务不被强制访谈或"最终再确认"阻塞。
  - `domain-modeling` / ADR 模板遵守项目真源与稳定锚点纪律，ADR 状态用仓库实际的 `## Status` 节（不是 frontmatter），且不强制为每个小决定写 ADR。
- 组合技能（`grill-with-docs`）按需加载被组合的技能，避免循环调用。

### (c) Runbook 与契约附录 A 归档，锚点兼容

- `docs/ROS2迁移步骤.md` → `docs/archive/ROS2迁移步骤.md`，**原路径不留转发**；`AGENTS.md` 与 plan 索引同步改指归档路径。
- 契约真源第 1–9 节**原样保留**（含 `#hard-constraints` 等全部锚点），只把附录 A 移到 `docs/archive/ros1-baseline.md`；原文件保留 `#appendix-a` 作为**导航兼容锚点**，指向归档正文。
- 拆分**不改任何锚点 ID**、不改约束正文与语义。

### (d) "无活跃引用指向归档"的判据

解释为**没有旧路径、没有把历史当当前执行入口**：

- 允许**明确标注为历史**的按需链接（例如"归档 Runbook 的硬约束挂载表，历史编排记录"）。
- 不追求"零命中"：为凑零命中而删掉有效历史引用，等于伪造记录。
- 旧路径出现在**历史命令 / 原始基线代码块**中时保留，并在归档说明里区分"这是当时命令"。

## Considered Options

- **规格转正入库公开** —— 被否：与 [ADR-0081](0081-public-repo-publishing-boundary.md) 相悖，且规格含本机路径与内部过程。
- **把规格删掉** —— 被否：它们是验收与结论的来源证据，删除即销毁可追溯性。
- **在 `.trae/` 留转发或软链** —— 被否：Agent 仍会按旧路径读到 347 行 Runbook / 96 个规格文件，P0-3 等于没做。
- **技能原样搬过去** —— 被否：Trae 工具名在 DSH 下不存在，搬过去只是把坏调用换个位置。
- **把 4 个技能合并成 1 个** —— 被否：它们的用途不同（访谈 / 访谈+落文档 / 领域建模），合并会让"按需加载"失效。

## Consequences

- **正面**：`.trae/` 不再承载任何工作流；规格、Runbook、ROS1 基线统一在 `docs/archive/` 且可被索引；技能在 DSH 默认扫描根下直接可用。
- **代价 / 限制**：公开 clone 仍**不含** specs（与原边界一致）；需要规格时必须在本机仓库操作。
- **可验证性**：迁移逐文件 sha256 一致、链接由脚本按解析后的绝对目标重算；`tests/docs_link_check.py` 迁移前后对比活跃范围断链为 0。
- **不放松**：独立验收、契约真源、硬约束红线均不变。

## 参考

- 发布边界：[ADR-0081](0081-public-repo-publishing-boundary.md)
- 引用纪律与"不重写历史"：[ADR-0066](0066-decision-applicability-and-reference-discipline.md)
- 迁移清单与逐文件哈希：[`docs/archive/specs/MIGRATION.md`](../archive/specs/MIGRATION.md#migration)（本机）
- 归档导航：[`docs/archive/README.md`](../archive/README.md#archive)
- 技能目录：[`.agents/README.md`](../../.agents/README.md#skills)
