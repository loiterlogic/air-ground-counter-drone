# AGC Project AGENTS.md

> 本文件是项目的**唯一入口索引**，每次会话自动加载 —— **保持精简**。只做**索引与红线**，不承载内容：内容各有其家。
> **现行版，随决策持续更新**（决策时间线见 [ADR 索引](docs/adr/README.md#adr-index)）。

## 这是什么项目

AGC（空地协同反无人机仿真）：同一世界、同一时钟下，无人机 + 地面车围绕统一任务定义的协同系统。
本仓是 **ROS1(Noetic) → ROS2 Jazzy 的全新重写**（不是逐包等价迁移）。

## 开工顺序（必读只有一条）

1. `docs/plan/README.md` — **任务计划规则**：本目录是**临时工作区**（写完就删）；结论归宿表与 plan 文件最小结构见该文件

> **2026-10-29 方向裁定**：迁移推进与论文优先**暂停**，先确保项目"完成"。任务在 `docs/plan/` 立项，**结档即删**（规则见 [任务计划规则](docs/plan/README.md#plan-index)）；编排史见 Runbook 归档。（暂停事实由 [ADR-0025](docs/adr/0025-publishing-boundary-and-retirement.md#top) 承载，原开关文件 `PAUSED.md` 已于 2026-10-31 退役。）
> **术语不是每轮必读**：`GLOSSARY.md` 按任务查—— 设计/命名/写文档时读，纯执行既定步骤不读。**L1 口径 = 本文件 + `docs/plan/README.md`（规则）**—— 其他文档按任务查，不预读。

## 按需查（不预读，按任务取用）

- [术语表](GLOSSARY.md) — 项目特有概念与边界；**设计、命名、写文档时读**，纯执行既定步骤不读
- [契约真源](docs/adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints) — 不可变约束、坐标系、终态语义、接口语义（**唯一约束来源**）
- [ADR 索引](docs/adr/README.md#adr-index) — 全部决策的编号 / 标题 / Status / 结论，先扫表再点开 1–2 篇
- [归档导航](docs/archive/README.md#archive) — 只剩历史 Runbook 与 ROS1 基线盘点（规格与过程台账已于 2026-11-03 删除）
- [工程规范](docs/conventions/目录与命名规范.md#10-产物分类与生命周期) — 目录、命名、产物分类与生命周期
- [测试分层与可测性](docs/conventions/测试分层与可测性.md#layers) — **写判据前读**：四层怎么分、新 clone 只能跑 9.5%、判定逻辑怎么抽成可单测的纯类
- [**路线分支治理**](docs/conventions/路线分支治理.md#rule) — **没有用户明确允许不得创造路线分支**；现行分支台账与清退规则
- [**引用与注释纪律**](docs/conventions/引用与注释纪律.md#rule) — **代码中引用决策只允许 ADR**；注释只写做什么/为什么
- [技能](.agents/README.md#skills) — 领域建模 / 访谈类可复用技能（`.agents/skills/`）

Leader / Worker 交接见 [协作规则](.coordination/README.md#protocol)、[当前交接](.coordination/CURRENT.md#current)；协作原则见 [单任务链、决策自主、消息来源与停止条件](.coordination/README.md#协作原则)（每链一个任务；[独立链可并行](.coordination/README.md#parallel)，N=6 记录检查点 / K=4 无进展熔断）。

## 铁律

- **项目根** `/home/chen/AGC`；colcon 根即项目根。
- **真源分层**：每类信息只有一个家。约束类信息**只存在**于[契约真源](docs/adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints)，下游**只引用、不复述**。
- **引用**：跨文档一律用**稳定锚点** `<文件>#<锚点>`；**禁止** `§` 章节号。
- **无旧树**：旧树归档 `reference/` 已于 **2026-10-31 退役删除**（[ADR-0025](docs/adr/0025-publishing-boundary-and-retirement.md#top)）；任何决定**不得**再以旧树为依据，**禁止**从旧树复制代码或沿用其格式、命名、目录、任务粒度。
- **先学后做**：遇到任何问题，**先学习别人已验证的成功解法**，再动手。查参照的优先顺序：① 项目内**同版本、可运行**的同类实现（首推 Nav2：`nav2_minimal_tb3_sim` / `nav2_bringup`）→ ② ROS 2 社区同类包与官方文档 → ③ 外部搜索。**禁止**仅凭假设反复试错；**对照他人做法之后**再改自己的实现（[ADR-0003](docs/adr/0003-nav2-paradigm-absorption.md#top) 吸收原则在排障流程上的延伸）。
- **红线**：**发现任一硬约束（[#hard-constraints](docs/adr/0020-package-boundaries-and-runtime-topology.md#hard-constraints)）未被满足，立即停止并报告，不得带错继续推进。**
- **未决事项**：不得静默假设，必须显式挂到对应任务，或在 `docs/adr/` 记录。
- **路线分支**：**没有用户明确允许，不得创造路线分支**（`xxx_source` / `xxx_mode` / `xxx_backend` / `xxx_path`
  形式的参数、或"同一功能两套实现由开关选择"）。现行台账与清退规则见
  [路线分支治理](docs/conventions/路线分支治理.md#rule)；新增分支须走四项准入（含用户允许 + 退役条件），
  删分支须留防复活闸门。
