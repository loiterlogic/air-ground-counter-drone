# P0-3 文档瘦身、规格迁移与技能适配 · 批次首轮

- 任务 ID：`20261029-003-p0-3-docs-and-skills`
- 轮次：1；来源：Leader，用户明确授权继续 P0-3，并要求迁出 Trae specs/skills，以后不再使用 Trae。
- 根：`/home/chen/AGC`；分支 `main`；HEAD `6aeba4b49609467cd9ffb4bfdea99eed0e985336`；派工前工作区干净（本单交接记录除外）。

## 目标与真源

完成 [P0-3](../../../../docs/plan/p0-3-文档瘦身与入口重构.md#p0-3-goal)，纳入用户新增的 Trae 退役要求。入口 [路线](../../../../docs/plan/README.md#plan-index)、[协议](../../../README.md#protocol)、[契约](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。P0-2 已验收。先读完整相关条目与现有实现再改；不预读无关历史正文。

## Leader 已裁定的边界

1. `.trae/specs/` **整体迁往 `docs/archive/specs/`**，建索引；不留 `.trae` 转发/软链。保持 specs 原先不发布的边界：`.gitignore` 加精确 `/docs/archive/specs/`，不 force-add 规格。允许公开的简短归档导航另放 `docs/archive/README.md`，说明规格随本地工程保留。不能因为换目录把历史本地规格静默提交。
2. `.trae/skills/` 的 4 个技能及 2 个格式资源迁往 `.agents/skills/<name>/`；作为可复用项目技能入库。已核实本机 Harness `@deepseek-ai/dsh-skill-filesystem/README.zh.md` 的默认扫描根含 `.agents/skills`，只发现直属 `<name>/SKILL.md`，name/description 必填。可读取该包文档，**不得修改 Harness 或全局配置**。
3. 技能适配：保留用途，中文指令；去掉 Trae 专用 `Agent Explore`/`AskUserQuestion` 假工具名、以 `.trae` 定根等；使用当前实际 `skill`、`ask_user_question`、`worker`/`send_message` 等工具，工具缺失时明确文件读取回退。事实自行查，用户既有授权不得重问，范围内决定由 Leader 自主；只有用户明确请求设计访谈才进入 grilling，不让普通实现被强制访谈/最终再确认阻塞。domain-modeling 与 ADR 模板遵守项目真源、稳定锚点、实际 `## Status`，不重述约束、不强制无价值 ADR。组合技能按需加载，避免循环调用。
4. Runbook 移 `docs/archive/ROS2迁移步骤.md`；原路径不留转发。契约正文约束/锚点/语义保持，附录历史移 `docs/archive/ros1-baseline.md`，原 `#appendix-a` 留导航兼容。
5. “无活跃引用指向归档”解释为**无旧路径/无把历史当当前执行入口**；允许明确标注历史的按需链接。否则按需查历史与归档要求互相矛盾。不要为追求零命中删除有效历史引用。
6. 保留 ADR、评审、协作历史结论；允许纯路径/导航修正，不重写判定、数字、哈希或原命令证据。旧路径出现在历史命令/原始基线代码块可保留并在迁移说明区分。既有坏链先记录；可修有确定目标的错误，无法确认的历史缺证列明，不造文件/锚点骗通过。

## 修改白名单

- `AGENTS.md`、`GLOSSARY.md`、`.gitignore`
- `docs/plan/*.md`（仅任务范围/状态、旧路径与导航一致性）
- `docs/ROS2迁移交接文档.md`、迁移 Runbook 及上述 `docs/archive/` 目标
- `docs/adr/README.md`；既有 ADR/评审仅纯路径导航修正；必要时新增一条 ADR 记录用户退役 Trae 与新位置/发布边界，不改旧决策正文
- `docs/conventions/*.md`（结构、模板与入口路径适配）
- `src/**/README.md`、`scripts/README.md`、`toolchain/README.md` 仅文档引用修正
- `.coordination/README.md`、`roles/*.md`、CURRENT、本任务记录；其他归档记录只允许修路径，不改结论
- `.trae/specs/**` 与 `.trae/skills/**` 的迁移；`.agents/skills/**`
- `scripts/adr_index.py`、`tests/docs_link_check.py` 及必要的小型离线测试

不得修改工程代码、launch、仿真配置、实验产物、reference 或外部用户目录。迁移前核实源/目标绝对路径、目标不覆盖；tracked 用 git mv，ignored 用受检 mv，建立迁移前后清单/哈希，保证规格无损（必要相对链接变更另记）。不 rm 历史。

## 交付与验收

- AGENTS ≤40 行，7 条铁律逐一保留；L1=AGENTS+路线 ≤200 行，相对原619下降≥60%；术语/契约/历史按任务读取。
- 活约束及稳定锚点保留，附录历史分离；Runbook 无原路径残留文件，入口只按需指向归档。
- `.trae` 不再有 specs/skills 文件；全量规格有迁移清单、归档索引与正确相对引用；发布忽略边界有效。
- 4 技能在 `.agents/skills`，frontmatter 正确、资源链接有效、无 Trae 工具依赖；可验证 Harness loader 实际发现/加载则留证；不可用则明确区分静态合规与实际加载未验，不伪报。
- ADR 自动索引含编号/标题/Status/结论/适用状态，`--check` 通过；不得猜 accepted 状态或把暂停等同废止。生成规则确定且结果可重跑。
- docs_link_check 处理本地链接/显式锚点/标题 slug、代码块与模板排除边界，迁移前后有对比，新增/迁移坏链为0；历史缺失单列具体清单，不用宽泛忽略。
- P0-3 写实际出口判据、测量数据、已知遗留；不声称项目完成。

## 预算、提交与停止

- N=6，K=4；批次自主续轮，里程碑/阻塞/预算耗尽/契约风险时才唤醒。
- 允许离线文档脚本/小测试/索引/哈希验证 **最多12次、每次≤30s、总≤360s**，无 ROS/GZ/PX4/构建/网络/共享资源；超时先报告，不无限全仓扫 build/install/log/reference/experiments/toolchain依赖树。产物 `/tmp/agc-p0-3-*` 或本单证据目录。
- T1 系统观测=0，T2=0；上述离线检查为本单明确授权，保留完整命令/退出码。
- 允许明确路径 git add、分主题本地 commit；禁止 push/reset/clean/stash/amend/rebase。提交前审清单不含 ignored specs、私密或生成物。不要为“记录当前提交自身哈希”循环追加提交；记录一个固定测量时点即可。
- **若3轮结束仍无法形成无损迁移+新入口+可运行静态验证工具，停止并列可判别缺口；K=4无新证据熔断；总N=6。** 硬约束疑似违规、未知基线漂移、需扩大白名单/预算立即停止。
- CURRENT 本任务期间按协议执行中/待审查，不能为“task为空”提前归档；Leader验收后归档清空。
- 报告≤30行审查摘要开头，含文件变化、迁移清单/哈希、命令退出码、阅读量前后、技能验证、预算、未决项。完成置待审查并 send_message Leader，随后结束，不自行验收/开下一任务。
