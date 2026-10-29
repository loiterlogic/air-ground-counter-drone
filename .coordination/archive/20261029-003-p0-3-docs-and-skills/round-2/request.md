# P0-3 定点收尾 · 批次第 2 轮（返工）

- 任务 ID：`20261029-003-p0-3-docs-and-skills`
- 轮次：**2**（同任务链续轮；Leader 于 2026-10-29 裁定"暂不验收，定点收尾"）
- 来源：Leader（独立复跑 3 项检查通过后提出 6 项返工要求）；授权范围：本轮**仅**做这 6 项，不扩大任务。
- 根：`/home/chen/AGC`；分支 `main`
- 基线：round-1 结束于 `81b87e4`，工作区干净；本轮起点即 `81b87e4`

## 本轮目标（Leader 原文 6 项，逐项对应）

1. **AGENTS 的 GLOSSARY 口径矛盾**：开工顺序仍把 `GLOSSARY.md` 列为必读，与"L1 = AGENTS + plan = 112 行"的统计口径不符。
   - 采用 Leader 推荐方案：**改为任务按需读术语**，不动 L1 口径（原目标已明确 L1 = 两文件）。
2. **`docs/archive/README.md` 的本地 specs 索引表述**：改成明确"**仅本地完整工程存在**"的代码路径说明；
   **不得**把"公开 clone 缺链"称已通过；**不放开**规格发布边界。
3. **`docs_link_check.py` 的 `ACTIVE_GLOBS`**：加 `.agents/**/*.md` 与递归 archive/research README（后者供 P0-4），
   让**技能资源本身**被检查，而不只检查"别人指向技能"。
4. **`.agents/README.md:33`** 声称 frontmatter 错误"静默丢弃且不报错"，与已读 Harness 文档不符（实为**随警告被跳过**），改正。
5. **`grilling` 结束段**须明确：**已有授权可由 Leader 判定访谈结束并实施**，不一律要求用户再次确认。
6. **round-1 report 结束时间**：`13:02` 是未来预填，按实际取时修正；**保留更正记录**。今后不再预填。

Leader 明确**不需要**改的：3 处工程注释（`src/agc_air/config/air.yaml`、`CMakeLists.txt`、`src/agc_sim/config/bridge.yaml`）、
以及 3 条历史缺链（接受保留）。

## 白名单（继承首轮 + Leader 补充）

- **补充授权**：`.agents/README.md`、`.agents/skills/grilling/SKILL.md`
- 其余继承首轮：`AGENTS.md`、`docs/plan/*.md`、`docs/archive/**`、`docs/adr/`（纯路径/导航）、
  `docs/conventions/*.md`、`src/**/README.md`、`scripts/README.md`、`toolchain/README.md`、
  `.coordination/**`、`scripts/adr_index.py`、`tests/docs_link_check.py`、必要的小型离线测试。
- **本轮实际额外触及（同属既有授权范围的相邻文件，逐条披露）**：
  - `.agents/skills/grill-me/SKILL.md`、`.agents/skills/grill-with-docs/SKILL.md` —— 第 5 项一致性；
  - `.agents/skills/domain-modeling/{SKILL,ADR-FORMAT,GLOSSARY-FORMAT}.md` —— 第 3 项补扫暴露的断链修复（技能资源自身）；
  - `tests/docs_tooling_check.py` —— 首轮已授权的小型离线测试，本轮加 1 组用例。
- **不修改**：工程代码、launch、仿真配置、实验产物、`reference/`、`toolchain/` 实体、Harness 与全局配置。

## 预算

- 离线检查（脚本 / 文档小测试 / 索引 / 哈希）：**追加最多 3 次、每次 ≤ 30 s、总 ≤ 90 s**（Leader 明确追加额度）。
- **T1 系统观测 = 0；T2 = 0**。不构建、不仿真、不联网、不碰共享资源。
- 允许本轮**定点修改与本地提交**（不 push / reset / clean / stash / amend / rebase）。

## 可判定验收

| # | 判据 | 判定方式 |
|---|---|---|
| 1 | `AGENTS.md` 开工顺序只剩 plan；GLOSSARY 移入"按需查"且写明何时读 | 读文件 + L1 = AGENTS + plan 行数 |
| 2 | `docs/archive/README.md` 对 specs 只给本地路径说明，明说公开 clone 无此目录；发布边界未变 | 读文件 + `git check-ignore` 仍命中 |
| 3 | `ACTIVE_GLOBS` 含 `.agents/**/*.md`；**注入一条技能内断链能被检出** | 自检用例 + 手工注入验证 |
| 4 | `.agents/README.md` 表述为"随警告被跳过" | grep 不再出现"静默丢弃" |
| 5 | `grilling` 结束段含"既有授权由执行者可判结束并实施" | 读文件 |
| 6 | round-1 report 结束时间 = `81b87e4` 的 git 时间，且有更正记录 | 读文件 + `git log` |
| 7 | 三项检查复跑均退出码 0；活跃断链 0；技能自身断链 0 | 命令退出码 |
| 8 | 本机保留路径链接单列、不谎称公开可导航 | 检查器输出 |
| 9 | ADR 索引仍 `--check` 通过（未因改动漂移） | 命令退出码 |

## 停止条件（预登记）

- 若 **2 轮内**（含本轮）无法让上述 1–8 全部可判定成立，则停止并列出**具体不可判定缺口**，不再自开轮次。
- 触及白名单外改动、需放宽发布边界、需真实实验、或发现硬约束疑似违规 → 立即停止并唤醒 Leader，不自行扩大。
- K=4：本轮若未产出能区分现状的新证据即触发熔断（当前判断：无需熔断，6 项均为确定性修改）。

## 交接

- 完成后 `CURRENT` 置 `待审查` 并用 `send_message` 通知 Leader；**不自行验收、不归档、不开 P0-4**。
- 报告须计入本轮为**一次实质返工**与**一次新增里程碑通知**，供 P0-5 统计。
