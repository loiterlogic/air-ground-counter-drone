<a id="top"></a>
# 发布边界与退役清理

## Status

accepted（2026-11-02 由 ADR-0081 / 0105 / 0107 合并；结论未变）

## 背景

项目已推送到 GitHub 公开仓库，首轮推送把**本机研发过程物**一起带了进去：`.trae/`（73 文件 / 2.6 MB，编辑器工作流与 workstream 规格）与 `experiments/`（4625 文件 / **152 MB**，逐 run 的 `config/` 快照、`git_diff.patch`、机器指纹与绝对路径）。这些既不是可复现构建所需的源码 / 文档，又会显著增大克隆体积、暴露本机路径与内部规格。

随后是三次收尾：执行宿主从 Trae 换成 DSH（技能与规格都还在 `.trae/` 下，工具名与扫描根都不再成立）；旧树归档 `reference/` 439 MB 已无任何代码读取、但仍被活文档引用；`docs/plan/PAUSED.md` 开关在工作区被删而四处文档仍指向它。清理必须**同时**处理引用，否则只是制造悬空链接与失效纪律。

## 决策

### (a) 公开仓库排除 `.trae/` 与 `experiments/`

`.gitignore` 增精确规则：

```gitignore
/.trae/
/experiments/
```

替换原先「`experiments/*/*/*` 忽略、但放行 `config/`」的规则；今后实验证据**不再随 git 推送**。首轮推送已含这些路径，故用 `git filter-branch --index-filter` 从**全部历史**删除 `.trae` 与 `experiments`，清理 `refs/original` / reflog / 不可达对象后 **force-push** `main`（仓库刚建、无协作者，历史重写风险可控）。

**保留入库**：源码（`src/`）、脚本（`scripts/`）、测试（`tests/`）、文档（`docs/`、`GLOSSARY.md`、`AGENTS.md`、Runbook）、`toolchain/README.md`、模型资产（如 `wheel.stl`）。

### (b) 规格迁入 `docs/archive/specs/`，仍然不发布

- `.trae/specs/**` 整目录迁入 `docs/archive/specs/`，**不留转发文件、不留软链**——留转发只会让 Agent 继续按旧路径读到全量历史。
- `.gitignore` 增**精确**规则 `/docs/archive/specs/`，继续不发布；**不** `git add -f` 规格，也**不**因换目录把它们静默提交。
- 允许公开的只是**归档导航**与**迁移清单 / 索引**；`docs/archive/specs/README.md`、`MIGRATION.md` 同在本目录内一并被忽略，因此公开仓库既没有规格也没有指向不存在文件的死链。
- 为什么放 `docs/archive/`：它与 Runbook、ROS1 基线同属"历史"，在一个可发现的位置；`reference/` 是旧树代码、`experiments/` 是证据，语义都不对。

### (c) 技能迁到 `.agents/skills/`，按当前 Harness 适配

4 个技能整目录迁入 `.agents/skills/<name>/`，**作为可复用项目技能入库**（无密钥、无本机路径、无生成物）。适配规则：

- 工具名换成当前真实存在的（`skill` 加载技能、`ask_user_question` 提问、`worker` / `send_message` 派工与回报、文件读取工具查事实）；
- **事实自查**：需要环境事实时自己读文件 / 跑只读命令，不把"我该查什么"推给用户；
- 工具缺失时给出**明确的文件读取回退**，不假装调用不存在的工具；
- 项目根不再"以 `.trae/` 定根"，改为以 `.git` 定位；
- `grilling` 类技能只在**用户明确要求设计访谈**时进入；普通实现任务不被强制访谈或"最终再确认"阻塞；
- `domain-modeling` / ADR 模板遵守真源与稳定锚点纪律，ADR 状态用仓库实际的 `## Status` 节（不是 frontmatter），且不强制为每个小决定写 ADR。

### (d) Runbook 与契约附录 A 归档，锚点兼容

- `docs/ROS2迁移步骤.md` → `docs/archive/ROS2迁移步骤.md`，**原路径不留转发**；`AGENTS.md` 与 plan 索引同步改指归档路径。
- 契约真源第 1–9 节**原样保留**（含 `#hard-constraints` 等全部锚点），只把附录 A 移到 `docs/archive/ros1-baseline.md`；原文件保留 `#appendix-a` 作为**导航兼容锚点**指向归档正文。
- 拆分**不改任何锚点 ID**、不改约束正文与语义。

### (e) 退役旧树归档 `reference/`

- **删除** `reference/`（用户确认另有备份）；此后本机不再保留副本。
- 活文档引用**同步改写**：`AGENTS.md` 铁律"只读旧树"改为"**无旧树**"、契约真源基线声明、`GLOSSARY.md` 的"只读旧树边界"条目、spec 模板的强制节、目录与命名规范目录树、`agc_rl/interface.py` 注释。
- **保留 `.gitignore` 的 `/reference/` 规则**与 `tests/docs_link_check.py` 的 `reference/` 排除项：用户可能从备份恢复，保留可避免再次出现 439 MB untracked。
- **不改旧 ADR 正文**：历史记录只追加、不改写。

### (f) 退役暂停开关 `PAUSED.md`

- **删除** `docs/plan/PAUSED.md`；**暂停事实不变**，状态改由[当前方向](../plan/README.md#plan-index)单一承载。
- 引用同步改写：`AGENTS.md`、当前方向、spec 模板、`scripts/research/README.md`，以及 `scripts/adr_index.py` 与 ADR 模板中"暂停记在 plan 的**开关文件**里"的措辞（改为"plan 的**方向索引**"）。
- **显式澄清**：退役开关文件**不等于**恢复迁移。迁移推进、论文优先与 W8 的恢复仍须用户**显式裁定**；当前仍为暂停。

### (g) 作废旧候选清单 A1–E2

用户裁定**只留 git 历史、不再维护**：这批候选不再进入计划索引，也不另行迁移。如需重启，从提交 `5434207` 取回原文。`experiments/` 证据的清理**不在**本决策范围。

### (h) 本地残留与缓存治理

- 删除 `.trae/`、`.vscode/`（均被 `.gitignore` 排除，删除不影响版本库内容）、`.coordination/wake/` 残留回执。
- 删除 `.pytest_cache/` 与 `__pycache__/`（纯缓存，会自动再生）；并把 `.pytest_cache/` **显式加入** `.gitignore`——它原先只靠 pytest 自写的 `.pytest_cache/.gitignore`（内容为 `*`）隐式隐身，规则来源不显式、易被误读为"未忽略"；显式化后与 `__pycache__/` 同口径。
- `build/`、`install/`、`log/`、`experiments/`、`toolchain/` **不删**：分别是可重建的构建产物、实验证据与 PX4 外部依赖。

### (i) 「无活跃引用指向归档」的判据

解释为**没有旧路径、没有把历史当当前执行入口**：

- 允许**明确标注为历史**的按需链接（例如"归档 Runbook 的硬约束挂载表，历史编排记录"）。
- 不追求"零命中"：为凑零命中而删掉有效历史引用，等于伪造记录。
- 旧路径出现在**历史命令 / 原始基线代码块**中时保留，并在归档说明里区分"这是当时命令"。
- `docs/archive/` 与 `.coordination/archive/` 内对 `PAUSED.md` 与 `reference/` 的历史链接**保持原样**（历史范围，改写即伪造记录）。

### (j) 索引由脚本生成，不手改

`docs/adr/README.md` 由 `scripts/adr_index.py` 生成，`--check` 是防漂移护城河；**不**手改索引。

## 不做什么（边界）

- **不**发布 `.trae/` 与 `experiments/`，**不** `git add -f` 规格，**不**因换目录静默提交。
- **不**在 `.trae/` 留转发文件或软链（Agent 会继续按旧路径读到全量历史，瘦身等于没做）。
- **不**把规格删掉（它们是验收与结论的来源证据，删除即销毁可追溯性）。
- **不**把 4 个技能合并成 1 个（用途不同，合并会让"按需加载"失效）。
- **不**改写旧 ADR 正文里的旧树 / 旧路径引用（架构决策记录只追加、不改写）。
- **不**手改 ADR 索引。
- **不**删 `build/` / `install/` / `log/` / `experiments/` / `toolchain/`。
- **不**把"退役开关文件"读成"恢复迁移"。

## Considered Options

- **只新增停止跟踪提交（不重写历史）** —— 被否：GitHub 历史提交仍可见，未达"不推送"目的。
- **保留 experiments 的 config 快照 / 用 Git LFS 存 experiments** —— 被否：152 MB 且含机器指纹与绝对路径；无跨机器分发需求，需要时用 Release 资产更直接。
- **规格转正入库公开** —— 被否：与发布边界相悖，且规格含本机路径与内部过程。
- **技能原样搬到 `.agents/skills/`** —— 被否：Trae 工具名在 DSH 下不存在，搬过去只是把坏调用换个位置。
- **保留 `reference/` 只删引用** —— 被否：用户明确要删，且 W8 已关闭、439 MB 无使用场景。
- **保留 `PAUSED.md` 只改文档引用** —— 被否：用户裁定开关文件作废，暂停状态已由 plan 索引承载。
- **为凑"零命中"删掉所有历史链接** —— 被否：等于伪造记录。

## Consequences

- **正面**：公开仓库只含源码 / 文档，克隆体积从 ~150 MB 降到源码量级，本机路径与内部规格不外泄；规格、Runbook、ROS1 基线统一在 `docs/archive/` 且可被索引；技能在 DSH 默认扫描根下直接可用；"暂停"回到单一真源；仓库减约 439 MB 字节 + 约 2 MB 缓存。
- **代价 / 限制**：公开 clone **不含** specs / workstream 规格，需要时必须在本机仓库操作；**旧树事实本机不可再核对**——对旧树的溯源只能引既有 ADR 正文记录，日后若须重做 W8 对照，须先从用户备份恢复旧树；历史链接在 `docs/archive/` 与 `.coordination/archive/` 内保持原样（有意残留）。
- **可验证性**：迁移逐文件 `sha256` 一致、链接由脚本按解析后的绝对目标重算；`tests/docs_link_check.py` 迁移前后对比活跃范围断链为 0。
- **不放松**：独立验收、契约真源、硬约束红线均不变。

## 参考

- 相关决策：[ADR-0002](0002-docs-source-of-truth-and-reference-discipline.md#top)（文档真源分层与引用纪律）、[ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与证据纪律）、[ADR-0001](0001-project-positioning-and-execution-scope.md#top)（项目定位）、[ADR-0021](0021-w8-gui-headless-equivalence.md#top)（W8 关闭与平台冻结）、[ADR-0026](0026-leader-worker-collaboration-and-batch-authorization.md#top)（协作机制）
- 归档导航：[`docs/archive/README.md`](../archive/README.md#archive)；技能目录：[`.agents/README.md`](../../.agents/README.md#skills)
- 入口索引：[`AGENTS.md`](../../AGENTS.md)
