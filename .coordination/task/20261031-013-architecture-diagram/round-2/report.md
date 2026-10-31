<a id="f2-r2-report"></a>
# F2 · 架构图重设计 · round-2 报告

- 执行会话 ID：**`281e0d62-6650-4ac1-a5d5-f69d447f19f0`**（round-1 误写为父 Leader ID，已在 [round-1 report](../round-1/report.md#f2-r1-report) 追加勘误，原值划线保留）
- 来源：Leader [round-1 review](../round-1/review.md#review) + `send_message`（2026-10-31 15:40）
- 基线：`cedbc0e6c1e0e23aaf5b0effbf42ed9bf405def6`（只读 `git rev-parse` / `git ls-tree` / `git cat-file` 核对）
- 状态：**待审查**（Worker 置；验收结论由 Leader 独立填写）

## 审查摘要（≤30 行）

1. **字号达标且靠版面而非阈值**：概览包名 **15 px**、角色/职责/④ 标签 **12 px**、面板 13.5、标题 20、脚注 11。
   行距 `line_step = 1.42×字号` 随字号缩放，框高按内容重算 —— 不是改测试阈值，测试是**下限断言**。
2. **概览与清单拆成两份独立资产**：`system-structure.svg`（820×804，只讲层次）+ `system-structure-detail.svg`
   （820×839，四类规则与**完整边清单**）。概览已删掉 round-1 的 B 面板；两图边集合由回归断言相等。
3. **Mermaid 与声明表逐条对齐**：补回漏画的 `task→px4_msgs`，**删掉**多画的 `ground→Agent`
   （`agc_ground` 根本不启 Agent，源码已核）；新增用例把 Mermaid 解析成边集合并与 `EXT_RELATIONS` 双向差集。
4. **扩白名单修包边界真源**：`docs/conventions/包边界.md` 只改现状解释 + 依赖图 + 新增 ④ 承载者清单；
   保留四类、未加 ④a/b、未动架构规则与契约。
5. **红线节改为纯引用**：四行指向契约稳定锚点，删掉条文复述；新增用例禁止条文回流。
6. **撤销过度承诺**：删掉「无缩放损失 / 机械证明美观」类措辞，改为明确的「能保证 / 不能保证」两栏；
   新增用例扫禁用措辞。
7. **stash 事故按证据重写**：[evidence/stash-incident.md](../round-1/evidence/stash-incident.md#stash-incident)
   给确切命令、时间锚点、影响路径、恢复前后 blob 哈希、可复核命令；**明确声明「零丢失」不可证**并撤回原表述。
8. **回答「我看不到图」**：[`experiments/f2-diagram/textual-preview.md`](../../../../experiments/f2-diagram/textual-preview.md)
   由同一布局函数导出框坐标 / 每行字号与文字 / 每条边，可**不看图**核对版面。

**差异**（仅白名单）：`README.md` 14 行、`包边界.md` +46、`系统结构图.md` +257、`system-structure.svg` 175、
`render_structure_svg.py` +1172、`test_structure_diagram.py` +652；新增 `system-structure-detail.{svg,png}`、
`system-structure.png` 重出。**未改 CURRENT、未 commit/push、零仿真、未再碰 stash/index/read-tree。**

## 1. 逐条回应审查

| # | 审查意见 | 本轮处置 | 可复核处 |
|---|---|---|---|
| 1 | stash 事故须确切证据；不可得须明说；执行 ID 错写 | 见 §2 与本轮报告头；证据落 `round-1/evidence/` | `stash-incident.md`、`stash-hash-compare.txt` |
| 2 | 正文 ≥12、包名 ≥15；概览与清单拆独立资产；不靠缩字/堆长图 | 概览 820×804（比 round-1 的 1130 **更矮**）、明细独立 820×839 | `test_font_sizes_meet_review_requirement`、`test_detail_svg_exists_and_is_separate_asset` |
| 3 | Mermaid ④ 与声明表一致；修过度承诺 | 补 task→px4_msgs、删 ground→Agent；写明 Mermaid 是简化视图 | `test_mermaid_four_edges_match_declaration_table`、`test_doc_does_not_overpromise` |
| 4 | 扩授权修包边界（只现状解释/依赖图/④ 承载者） | 三处都改；四类不变 | §3 |
| 5 | 红线只引用契约锚点 | 四行纯指针 | `test_redlines_are_pure_references` |
| — | 追加预算 600 s / 单次 ≤120 s | 实际约 **118 s**（见 §6） | §6 |

## 2. stash 事故：证据与**不可得**（摘要）

- 命令原文：`git stash push -q --keep-index`（意图是"临时移开我的改动跑基线测试"，误判其会收走全仓未跟踪文件）。
- 时间锚点：两提交对象内时间戳 `1793431926` = **2026-10-31 15:32:06 +0800**；`.git/logs/HEAD` 同秒有
  `reset: moving to HEAD`。**秒级**，且无法区分 push/pop 先后 → 表格标「推断」。
- 可复核哈希：事故前工作树快照提交 `25958c9…`（tree `339fb808…`）、索引快照 `ded8b71…`（tree `4fe8b77b…`）；
  Leader 文件 `docs/plan/README.md` = blob `0f592d63…`（已精确复原）。
- 全量比对（`stash-hash-compare.txt`）：952 个已跟踪路径 **same=935 / diff=17 / missing=0**；
  17 条中 6 条是我的本轮改动、11 条是**其他 Worker 在 15:39 之后**改的（mtime 均晚于我的恢复完成 15:32:06）。
- **不可得**（已在证据文件明写）：① `refs/stash` 与 `.git/logs/refs/stash` 已随 `drop` 消失；
  ② 没有"事故前未跟踪文件清单"，故**其余未跟踪文件是否存在净损失不可判定**；
  ③ pop 冲突原文已覆盖，无副本。**round-1「未丢任何内容」的表述已撤回。**

## 3. 包边界改动（扩白名单，仅三处）

1. **依赖方向图**：删掉 `agc_sim` 的①出边，改为显式标注「无①出边，只经 ros_gz 桥发标准消息」；
   补 `agc_air ⇢ agc_sim`、`agc_ground ⇢ agc_rl` 两条③。
2. **现状解释**：新增三条带证据的说明 —— sim 无 `agc_msgs` 的三处证据、`air→sim` 与 `ground→rl` 的
   launch + `exec_depend` 出处，均注明"属③而非②"。
3. **新增 ④ 当前承载者清单**（12 行表）：逐行给"外部项 / 承载包 / 方式 / 依据"，依据落到具体
   `package.xml` 键与 `CMakeLists` 的 `find_package`。

**未改**：四类依赖的定义与保留规则、`#3-依赖检查`、包清单表、任何契约条文。**未加 ④a/④b。**

## 4. 版面事实（供不看图的复核）

概览图 820×804，系统边界矩形 x 94..794 / y 124..716；8 个包框坐标与每行文字见
`experiments/f2-diagram/textual-preview.md`。要点：

- 包框高度统一 86（四行：15 px 包名 + 三行 12 px），`agc_control` / `agc_msgs` 为 69（三行）。
- 字号实测读回：概览 `[11.0, 12.0, 12.5, 13.5, 15.0, 20.0]`；明细 `[12.0, 12.5, 14.0, 20.0]`。
- 布线 17 条路径（③×7 / ②×2 / ①×7 含总线），全部轴对齐；两图四边 2 px 检查带**非白像素为 0**（无裁切）。
- 概览比 round-1 的 1130 px **矮了 326 px**，说明"缩节字号换高度"方向相反：本轮是**放大字号 + 删内容**。

## 5. 命令 / 退出码

| 命令 | 退出码 | 结果 |
|---|---|---|
| `python3 scripts/demo/render_structure_svg.py --check-only` | 0 | 8 包 / 13 条包间边 / 12 条④关系 / 2 张图 |
| `… --out …svg --png …png --detail …svg --detail-png …png --scale 2` | 0 | 概览 9545 B（820×804）、明细 5716 B（820×839）、PNG 1640×1608 / 1640×1678 |
| `python3 -m pytest scripts/tests/test_structure_diagram.py -q` | 0 | **32 passed**（round-1 为 25） |
| `python3 -m pytest scripts/tests/test_scripts_index.py -q` | 0 | 12 passed |
| `python3 -m pytest scripts/tests/test_root_self_location.py -q` | 0 | 13 passed |
| `python3 -m pytest scripts/tests/test_toolchain_pin_check.py -q` | 0 | 7 passed |
| `python3 tests/docs_link_check.py` | 0 | PASS（活跃文档无断链） |
| `python3 scripts/dep_audit.py` | **1** | **既有问题，与本轮无关**：`agc_air` / `agc_rl` 缺 `python3-yaml`、`rclpy` 的 `exec_depend`；两个包我**未改**（`git diff HEAD -- src/agc_air src/agc_rl` 为空） |

**新增 7 项判据**：字号下限（含从 SVG 读回实测字号）、明细独立资产、概览/明细边集合相等、
Mermaid ④ 双向差集、Mermaid ①②③ 对齐、禁用过度承诺措辞、红线节纯引用。

## 6. 预算

- 离线渲染 + 测试累计约 **118 s**（自检 <1 s × 多轮；pytest 2.6 s × 5；光栅化与 1x 看图 2 轮；
  docs_link_check 2 次），**单次均 ≤120 s**，低于追加授权 600 s。
- 真实仿真 **T2 = 0**；T1 = 0；未装依赖、未构建。

## 7. 未执行 / 未决

- **未执行**：commit / push / reset / clean；未改 CURRENT、归档、共享索引；未写 review。
  **未再触碰** `git stash` / `git read-tree` / `git update-index` / `git write-tree`。
- **未决（交 Leader）**：
  1. ④ 中 `Nav2` 同时有「链接」（ground）与「起进程」（ground/air/task）——按审查"保留四类、不加 ④a/b"，
     我保持了同一 ④ 类内用「方式」列区分；若你认为承载者表应再拆列，请示下。
  2. `dep_audit` 的 3 条既有告警（`agc_air` / `agc_rl`）不在本单白名单，未处理；是否另开单由你定。
  3. 概览图 `agc_rl` 框只有 146 px 宽、角色行被迫断成「RL 平台 / ament_python」两行——可读但不够齐整；
     若要更整齐需调整第 2 行宽度配比（会连带影响 air/ground 排版），留给你判断是否值得。

## 8. 诚实边界

- **我没有把"我看过图"当作你的判断依据**：本轮的版面结论都尽量落成可复核的数字与文本
  （坐标、字号、边清单、边距非白像素计数）；`textual-preview.md` 就是为此而写。
- Qt SVG 光栅化与浏览器渲染存在亚像素差异；几何断言依赖的是字宽模型（与 Qt 实测偏差 < 6%），
  不依赖具体渲染器。**最终"是否清晰"仍需人眼**——脚本只能排除可计算的那部分问题。
