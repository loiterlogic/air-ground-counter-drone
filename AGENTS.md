# AGC Project AGENTS.md

> 本文件是项目的**唯一入口索引**，每次会话自动加载 —— **保持精简**。只做**索引与红线**，不承载内容：内容各有其家。
> **现行版，随决策持续更新**（决策时间线见 [ADR 索引](docs/adr/README.md#adr-index)）。

## 这是什么项目

AGC（空地协同反无人机仿真）：同一世界、同一时钟下，无人机 + 地面车围绕统一任务定义的协同系统。
本仓是 **ROS1(Noetic) → ROS2 Jazzy 的全新重写**（不是逐包等价迁移）。

## 开工顺序（必读只有一条）

1. `docs/plan/README.md` — **当前方向**：当前无在办任务；候选后续与新批次入口见该索引

> **2026-10-29 方向裁定**：迁移推进与论文优先**暂停**（[开关](docs/plan/PAUSED.md#paused)），先确保项目"完成"。当前执行入口是 `docs/plan/`，**不是** Runbook。
> **术语不是每轮必读**：`GLOSSARY.md` 按任务查——设计/命名/写文档时读，纯执行既定步骤不读。**L1 口径 = 本文件 + `docs/plan/README.md`**（[P0-3 出口判据](docs/archive/completion-20261031/p0-3-文档瘦身与入口重构.md#p0-3-exit)）。

## 按需查（不预读，按任务取用）

- [术语表](GLOSSARY.md) — 项目特有概念与边界；**设计、命名、写文档时读**，纯执行既定步骤不读
- [契约真源](docs/ROS2迁移交接文档.md#hard-constraints) — 不可变约束、坐标系、终态语义、接口语义（**唯一约束来源**）
- [ADR 索引](docs/adr/README.md#adr-index) — 106 篇决策的编号 / 标题 / Status / 结论，先扫表再点开 1–2 篇
- [归档导航](docs/archive/README.md#archive) — 历史 Runbook、ROS1 基线盘点、历史 workstream 规格索引
- [工程规范](docs/conventions/目录与命名规范.md#10-产物分类与生命周期) — 目录、命名、产物分类与生命周期
- [技能](.agents/README.md#skills) — 领域建模 / 访谈类可复用技能（`.agents/skills/`）

Leader / Worker 交接见 [协作规则](.coordination/README.md#protocol)、[当前交接](.coordination/CURRENT.md#current)；协作原则见 [单任务链、决策自主、消息来源与停止条件](.coordination/README.md#协作原则)（每链一个任务；[独立链可并行](.coordination/README.md#parallel)，N=6 记录检查点 / K=4 无进展熔断）。

## 铁律

- **项目根** `/home/chen/AGC`；colcon 根即项目根。
- **真源分层**：每类信息只有一个家。约束类信息**只存在**于[契约真源](docs/ROS2迁移交接文档.md#hard-constraints)，下游**只引用、不复述**。
- **引用**：跨文档一律用**稳定锚点** `<文件>#<锚点>`；**禁止** `§` 章节号。
- **只读旧树**：`reference/`（旧树归档）仅可读以对齐**行为 / 契约事实**；**禁止**作为格式、命名、目录、任务粒度的来源；**禁止**复制其代码。
- **先学后做**：遇到任何问题，**先学习别人已验证的成功解法**，再动手。查参照的优先顺序：① 项目内**同版本、可运行**的同类实现（首推 Nav2：`nav2_minimal_tb3_sim` / `nav2_bringup`）→ ② ROS 2 社区同类包与官方文档 → ③ 外部搜索。**禁止**仅凭假设反复试错；**对照他人做法之后**再改自己的实现（[ADR-0008](docs/adr/0008-nav2-paradigm-absorption-as-code-principle.md) 吸收原则在排障流程上的延伸）。
- **红线**：**发现任一硬约束（[#hard-constraints](docs/ROS2迁移交接文档.md#hard-constraints)）未被满足，立即停止并报告，不得带错继续推进。**
- **未决事项**：不得静默假设，必须显式挂到对应任务，或在 `docs/adr/` 记录。
