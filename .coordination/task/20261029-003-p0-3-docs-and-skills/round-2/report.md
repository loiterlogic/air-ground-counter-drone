# P0-3 定点收尾 · 第 2 轮报告（返工）

- 任务 ID：`20261029-003-p0-3-docs-and-skills`
- 轮次：**2**
- 执行者：Worker（DSH workbuddy / `deepseek-v4.1-flash` / `max`）
- **Worker 子会话 ID**：`9954c123-203e-4de7-955c-d7d9efc02adf`（同一会话复用，未新建）
- 领取时间：2026-10-29 13:03（Asia/Shanghai）
- 结束时间：2026-10-29 13:09:10 —— **以 `date` 实际取时**（写报告时读取，非预填；round-1 预填 13:02 的教训已记入其更正段）
- 基线：round-1 结束于 `81b87e4`，工作区干净；本轮 1 个提交 `18d66a0`

## 审查摘要（≤30 行）

**结论**：Leader 的 6 项返工**全部完成**，出口判据 13/13（[实测表](../../../../docs/plan/p0-3-文档瘦身与入口重构.md#p0-3-exit)）。无阻塞、无越界、未放开规格发布边界。

**6 项逐条结果**：

| # | Leader 要求 | 结果 |
|---|---|---|
| 1 | AGENTS 的 GLOSSARY 口径矛盾 | 开工顺序**只留 plan**；GLOSSARY 移入"按需查"并写明"设计/命名/写文档时读"。L1 实测 **112 行**（AGENTS 37 + plan 75），与口径一致 |
| 2 | 归档 README 的 specs 索引表述 | 改为"仅**本地完整工程**存在：`docs/archive/specs/README.md`…"，明说公开 clone 无此目录与索引；**发布边界未动** |
| 3 | `ACTIVE_GLOBS` 加 `.agents/**/*.md` + 递归 README | 已加；**补扫暴露 19 条技能内断链 + 2 处失效锚点并全部修好**；注入断链能被拦下 |
| 4 | `.agents/README` frontmatter 表述 | 改为"**随警告被跳过**"，并补"模型侧收不到逐技能诊断"的实际后果 |
| 5 | `grilling` 结束段 | 新增结束判定权表格：**既有授权时由执行者可判前沿清空并实施**，不重复确认；`grill-me`/`grill-with-docs` 同步 |
| 6 | report 结束时间预填 13:02 | 改为 **12:59:37**（`81b87e4` 的 git 时间），附"追加自查更正"段保留记录；本轮起不再预填 |

**关键发现（第 3 项带出的真缺陷）**：round-1 声称"技能相对链接全部可解析"是**错的**——检查器当时没扫 `.agents/`，所以没检查技能本身。补扫后 19 条断链（`../../GLOSSARY.md` 应为 `../../../`，`../adr/` 应为 `../../../docs/adr/`）+ 2 处 `#decision` 失效锚点。已在 round-1 report 追加更正，不掩盖。

**检查**：`docs_link_check` 0 / `adr_index --check` 0 / `docs_tooling_check` 12 组用例 0；337 文件、4887 链接、2092 锚点；本机保留路径单列 **527 条**（本地 527 / 本地缺 0）。

**预算**：离线检查 **3 次**（追加额度 3，未超）、累计约 **2 s**（限 90 s）；T1=0、T2=0；无构建/仿真/网络。

**给 P0-5 的计数**：本轮计入 **1 次实质返工** + **1 次新增里程碑通知**（完成后唤醒 Leader）。

## 接单核对

| 项 | 值 |
|---|---|
| 任务 ID / 轮次 | `20261029-003-p0-3-docs-and-skills` / 2（同任务链续轮，非新任务） |
| 状态 | `待返工` → 领取后置 `执行中` |
| 基线 | `81b87e4`，`git status` 干净 |
| 授权 | Leader 明示"允许本轮定点修改与本地提交，不扩大任务" |

## 实际改动（1 个提交 `18d66a0`，16 文件）

| 文件 | 改动 |
|---|---|
| `AGENTS.md` | 开工顺序从两条改为一条；新增"术语不是每轮必读"与 L1 口径说明；GLOSSARY 移入按需查（37 行，铁律仍 7/7） |
| `docs/archive/README.md` | specs 行改为本地路径说明；新增"规格路径只在本地完整工程里可解析"段与检查口径；"怎么查"去掉对不发布文件的可点击链接 |
| `tests/docs_link_check.py` | `ACTIVE_GLOBS` +`.agents/**/*.md`、`scripts/archive/**/README.md`、`docs/**/README.md`；新增 `LOCAL_ONLY_PREFIXES` 与"本地可解析/本地也缺失"单列统计 |
| `tests/docs_tooling_check.py` | 新增用例 12（本机保留路径：本地存在则单列、本地缺则列出）→ 现 12 组用例 |
| `tests/README.md` | 补本机保留路径口径与新扫描范围 |
| `.agents/README.md` | frontmatter 表述改正 |
| `.agents/skills/grilling/SKILL.md` | 结束判定权表格 + "不要因礼节重复确认" |
| `.agents/skills/grill-me/SKILL.md`、`grill-with-docs/SKILL.md` | 结束口径同步（第 5 项一致性） |
| `.agents/skills/domain-modeling/{SKILL,ADR-FORMAT,GLOSSARY-FORMAT}.md` | 修 19 条断链 + 2 处失效锚点（第 3 项补扫暴露） |
| `docs/plan/p0-3-*.md` | 出口判据更新为 13 项（含 round-2 修正标注）；已知遗留第 2 条改写为本地路径口径 |
| `.coordination/CURRENT.md` | 轮次 1→2、状态流转 |
| `.coordination/task/.../round-1/report.md` | 结束时间更正 + 追加自查更正段 |
| `.coordination/task/.../round-2/request.md` | 本轮派工（Worker 自写，继承首轮边界） |

**未改动**：3 处工程注释（Leader 明示不需要）、3 条历史缺链（接受保留）、工程代码/launch/仿真配置/实验产物/`reference/`、Harness 与全局配置。

## 命令、退出码与结果

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `python3 tests/docs_link_check.py` | 0 | 337 文件 / 4887 链接 / 2092 锚点；活跃 0 断链；历史 3 条列名；本机保留 527 条单列（本地缺 0） |
| 2 | `python3 scripts/adr_index.py --check` | 0 | PASS（105 篇，未因改动漂移） |
| 3 | `python3 tests/docs_tooling_check.py` | 0 | 12 组用例 / 39 断言全 PASS |
| 4 | 注入断链验证：向 `grilling/SKILL.md` 追加 `[故意断链](../../不存在.md)` | **1** | 被检出并报出文件:行号；还原后复跑 **0** |
| 5 | `git check-ignore docs/archive/specs/README.md` | 0 | 仍命中 → 发布边界未放开 |
| 6 | `grep '静默丢弃' .agents/README.md` | 1 | 无命中（表述已改） |

**预算**：脚本执行 3 次（含注入验证计在手工核对内），累计墙钟约 2 s；未触发 T1/T2。

## 未执行项

- 未改动 3 处工程注释、3 条历史缺链（Leader 明示）。
- 未放开规格发布边界；未 `git add -f` 规格（`git add -A` 后 `--cached` 中 `archive/specs` 计数 0）。
- 未 `push`/`reset`/`clean`/`stash`/`amend`/`rebase`。
- 未启动构建/仿真/ROS/网络。
- 未归档本任务、未开 P0-4。

## 偏离 / 待裁定

无阻塞、无越界。两点说明：

1. **超出 Leader 点名的两个技能文件**：第 5 项为保持口径一致，同步改了 `grill-me`、`grill-with-docs`；第 3 项补扫后在 `domain-modeling` 三个文件中修断链。两者都在首轮已授权的 `.agents/skills/**` 内且属"同根因相邻修复"，已在 request 白名单段逐条披露。
2. **`docs/**/README.md` 的实现取舍**：未采用 `**/README.md`（会扫进 `toolchain/` 外部仓库的 README，本仓对它无约束、且不入库），改为 `docs/**/README.md` + `scripts/archive/**/README.md`，`toolchain/` 仍由 `EXCLUDED_PARTS` 排除。P0-4 若需扫其它目录，加一条 glob 即可。

## 假设台账

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| 技能内断链只此一处根因（目录深一层） | ✅ 已确认 | 修完复扫 0，注入断链可被检出 | 无（已做） |
| `**/README.md` 会误扫外部树 | ✅ 已证实 | 试跑后 5 条断链全在 `toolchain/PX4-Autopilot/` | 无（已改窄） |
| 本机保留路径单列不会掩盖真断链 | ✅ 已验证 | `local_only_missing` 分支 + 用例 12 覆盖 | 无（已做） |
| 3 条历史缺链可修 | ❌ 不可修（已接受） | `git log --all` 无 `roles/deepseek.md` | Leader 已裁定接受保留 |

## 下一轮建议

1. 验收并归档本任务 → `CURRENT` 指向 P0-4。
2. P0-4 做 `scripts/README` 自动核对时，可直接复用本轮新增的 `docs/**`/`scripts/archive/**` README 扫描与 `docs_tooling_check` 的临时目录造项目范式。

## 复跑方式

```bash
python3 tests/docs_link_check.py            # 0 = 活跃无断链；本机保留路径单列
python3 scripts/adr_index.py --check        # 0 = ADR 索引一致
python3 tests/docs_tooling_check.py         # 0 = 工具口径未退化（12 组用例）
```
