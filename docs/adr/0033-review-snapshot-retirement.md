<a id="top"></a>
# 评审快照目录退役（`docs/reviews/`）

## Status

accepted（2026-11-06，来源：用户裁定——"docs/reviews删掉，写在plan，然后执行"）

## 背景

`docs/reviews/` 曾作为「评审快照及其结论来源证据」的归档家
（[目录与命名规范](../conventions/目录与命名规范.md#10-产物分类与生命周期) 产物分类表），
累计 5 份文件 / 915 行，全部是 2026-10-14 与 2026-10-25 两次只读评审的产物：

| 文件 | 行数 | 内容 |
|---|---|---|
| `agc-review-2026-10-14/00-总览.md` | 62 | 评审范围、开工检查点、阅读覆盖 |
| `agc-review-2026-10-14/10-风险.md` | 373 | 41 项风险（`R-0NN` 编号） |
| `agc-review-2026-10-14/20-结构.md` | 228 | 12 项结构意见（`S-NN` 编号） |
| `agc-review-2026-10-14/30-未来.md` | 110 | 17 项条件化未来意见（`F-NN` 编号） |
| `agc-review-2026-10-25/W8测量规格裁定.md` | 142 | 测量规格重算裁定 |

这些内容**已被下游吸收**：41 项风险里有结论的都进了对应 ADR（`ADR-0008` / `0009` / `0010` /
`0013` / `0016` 等的「参考」节引用 `R-0NN`），12 项结构意见进了 `ADR-0002` / `0003` / `0006`，
17 项未来意见进了 [ADR-0032](0032-pending-directions.md#top) 的未立项登记。
2026-11-06 的引用纪律裁定（代码只允许引用 ADR）之后，评审项编号本身已不再允许出现在代码里。

同时暴露出的问题：该目录是**唯一还允许编号引用存活的地方**，也是 3 份规范/2 个测试工具
必须为它开白名单的理由（`docs_link_check.py` 的 `HISTORICAL_PREFIXES`、
`test_reference_discipline.py` 的 `EXCLUDED_MARKERS`、`目录与命名规范` 的分类表）。
保留它等于永久维持一条"这里可以引用编号"的例外。

## 决策

### (a) 删除 `docs/reviews/`，内容不再保留副本

- `git rm -r docs/reviews/`，**不留转发文件、不留软链、不迁 `docs/archive/`**。
- 取回方式写在本篇：`git show d793126:docs/reviews/<路径>`，或
  `git log --all -- docs/reviews/`。该目录最后一次提交是 `d793126`（2026-11-06 14:00），
  在此之前的内容全部在历史里。
- **为什么不迁 `docs/archive/`**：归档只收「不可替代的过程编排史」（Runbook / ROS1 基线）。
  评审快照的每一条有结论的意见都已在 ADR 正文里，副本属第二真源；而 `docs/archive/` 的语义是
  「只读查阅、不重写」，迁入会把它变成又一个必须开白名单的历史目录——退役的目的正好相反。

### (b) 引用同步改写（删目录前先改，避免断链）

| 位置 | 改动 |
|---|---|
| 5 篇 ADR 的「参考」节（0002 / 0006 / 0008 / 0009 / 0016） | 删掉指向 `../reviews/...` 的链接，并把编号换成**该评审项的标题**（如「运行身份与复现」「决策有效性与引用」），保留"当时依据哪条评审意见"这一历史事实，同时让读者不查表即可读懂；再补一句"评审快照已于 2026-11-06 退役，见 [ADR-0033](0033-review-snapshot-retirement.md#top)" |
| `docs/conventions/目录与命名规范.md` | 删掉产物分类表的「评审快照」行与目录树里的 `reviews/`，在退役说明里指向本篇 |
| `docs/conventions/引用与注释纪律.md` | 历史证据清单去掉 `docs/reviews/`，补一句退役事实 |
| `docs/conventions/路线分支治理.md` | 5.3 保留项表格里 `docs/reviews/` 从"仍提及"清单移除 |
| `scripts/research/w7b_p1_adjudicate.py`、`w7b_p2_adjudicate.py` | 评审链接 `[...](../../docs/reviews/...md#f-13)` 改为纯文本 `统计冻结`（**只改链接与表述，不改判定逻辑与文本含义**） |
| `tests/docs_link_check.py` | `ACTIVE_GLOBS` 去掉 `docs/reviews/**/*.md`，`HISTORICAL_PREFIXES` 去掉 `docs/reviews/` |
| `scripts/tests/test_reference_discipline.py` | `EXCLUDED_MARKERS` 去掉 `/reviews/`，`FORBIDDEN` 去掉 `docs/reviews/` 规则 |

### (c) 防复活闸门

- [路线分支治理](../conventions/路线分支治理.md#current) 新增 **5.2.3 批次**，登记
  `docs/reviews/` 为已退役路径（处置：删除；依据：本篇）。
- `scripts/tests/test_retirement_ledger.py` 的 `DELETED_PATHS` 增 `docs/reviews`，
  并加一条断言：**规范与测试工具里不得再出现 `docs/reviews/` 的路径规则**
  （防止有人用"加白名单"的方式把它复活）。
- 该闸门进 `tests/run_smoke.py` 的 `offline` 组（已有），删除后**必须仍然绿**——
  这是"删目录不产生断链"的机器判据。

### (d) ADR「参考」节的评审项：**编号已删，改为标题**

**2026-11-07 修订**：原口径是"编号留在 ADR 正文里"（理由是"删除即伪造记录"）。该口径已废止——
编号本身**不可解析**：工作区无任何释义表，评审快照已删，读者看到一串「R-xx」无从知道它是什么。

现行做法：**删编号、保留标题**（如「运行身份与复现」）。这既保住"当时依据哪条评审意见"这一历史事实，
又不需要任何查表。标题从已退役快照取回（`git show d793126:docs/reviews/...`），不是新造。

**编号全仓零容忍**：`R-` / `S-` / `F-` / `X-` 编号在活跃区一律不得出现，见
[引用与注释纪律](../conventions/引用与注释纪律.md#rule)。

## 不做什么（边界）

- **不**把评审快照迁进 `docs/archive/`（理由见 (a)）。
- **不**改写 ADR 正文里已引用的评审项编号（历史结论只追加、不改写）。
- **不**因为删除而放宽 `test_reference_discipline.py` 对代码层编号的检查——恰恰相反，
  白名单项减少，检查面变大。
- **不**删 `docs/archive/`（它是"过程编排史"的家，与本篇无关）。

## Considered Options

- **迁入 `docs/archive/`** —— 被否：会给它再开一个历史白名单，且与 ADR 正文形成第二真源。
- **只删引用、保留目录** —— 被否：目录会继续作为"允许编号引用"的例外存在，与
  2026-11-06 的引用纪律裁定冲突。
- **改成"评审结论索引"（只留目录与标题）** —— 被否：结论已在 ADR 正文，索引不增加信息量。

## Consequences

- **正面**：少一个历史目录、少 3 处白名单例外；`docs/` 只剩 ADR / 规范 / 归档 / plan 四类；
  引用纪律的检查面变大（`/reviews/` 不再豁免）。
- **代价 / 限制**：原始评审全文不再在工作区可读，需要时按 (a) 的 `git show` 取回；
  取回的是历史文本，其内部链接指向当时的文件，**不可直接当现状读**。
- **可验证性**：E1–E2（见 plan 文件）——`git ls-files docs/reviews | wc -l` = 0、
  `docs_link_check.py` rc=0、`test_retirement_ledger.py` 通过且删目录后变红。

## 参考

- 相关决策：[ADR-0002](0002-docs-source-of-truth-and-reference-discipline.md#top)（真源分层与引用纪律）、
  [ADR-0025](0025-publishing-boundary-and-retirement.md#top)（发布边界与退役清理）、
  [ADR-0032](0032-pending-directions.md#top)（未立项方向登记，吸收了评审的 17 项未来意见）
- 台账：[路线分支治理 5.2.3](../conventions/路线分支治理.md#current)
- 产物分类：[目录与命名规范](../conventions/目录与命名规范.md#10-产物分类与生命周期)
