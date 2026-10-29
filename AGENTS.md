# AGC Project AGENTS.md

> 本文件是项目的**唯一入口索引**，每次会话自动加载 —— **保持精简**。只做**索引与红线**，不承载内容：内容各有其家。
> **现行版，随决策持续更新**（决策时间线见 `docs/adr/` 的 Status）。

## 这是什么项目

AGC（空地协同反无人机仿真）：同一世界、同一时钟下，无人机 + 地面车围绕统一任务定义的协同系统。
本仓是 **ROS1(Noetic) → ROS2 Jazzy 的全新重写**（不是逐包等价迁移）。

## 开工顺序（必须依次读）

1. `docs/plan/README.md` — **当前方向**：项目收尾路线（P0→P2 优先级、出口判据）
2. `GLOSSARY.md` — 术语
3. `docs/ROS2迁移交接文档.md` — **契约真源**：不可变约束、坐标系、终态语义、接口语义
4. `docs/ROS2迁移步骤.md` — **Runbook**：workstream 编排（**迁移已暂停，按需查、不预读**）
5. `.trae/specs/<ws>/{spec,tasks,checklist}.md` — 当前 workstream 规格（**迁移已暂停，按需查**）

> **2026-10-29 方向裁定**：迁移推进与论文优先**暂停**，先确保项目"完成"。当前执行入口是 `docs/plan/`，不再是 Runbook。

Leader / Worker 交接见 [协作规则](.coordination/README.md#protocol)（角色见 [Leader](.coordination/roles/leader.md#role) / [Worker](.coordination/roles/worker.md#role)，交接机制见 [交接与复用](.coordination/README.md#auto-wake)）与 [当前交接](.coordination/CURRENT.md#current)；项目执行以 [当前方向](docs/plan/README.md#plan-index) 为入口。

协作原则见 [单任务链、决策自主、消息来源与停止条件](.coordination/README.md#协作原则)。一次循环只处理一个任务；Leader 可在已批准边界内自主裁定重大技术方案，超出边界或需要用户明确授权时暂停。

## 铁律

- **项目根** `/home/chen/AGC`；colcon 根即项目根。
- **真源分层**：每类信息只有一个家。约束类信息**只存在**于契约真源，下游**只引用、不复述**。
- **引用**：跨文档一律用**稳定锚点** `<文件>#<锚点>`；**禁止** `§` 章节号。
- **只读旧树**：`reference/`（旧树归档）仅可读以对齐**行为 / 契约事实**；**禁止**作为格式、命名、目录、任务粒度的来源；**禁止**复制其代码。
- **先学后做**：遇到任何问题，**先学习别人已验证的成功解法**，再动手。查参照的优先顺序：① 项目内**同版本、可运行**的同类实现（本项目首推 Nav2：`nav2_minimal_tb3_sim` / `nav2_bringup`）→ ② ROS 2 社区同类包与官方文档 → ③ 外部搜索。**禁止**仅凭假设反复试错；**对照他人做法之后**再改自己的实现。此为 `docs/adr/0008-*.md` 吸收原则在**排障与实现流程**上的延伸。
- **红线**：**发现任一硬约束（契约** **`#hard-constraints`）未被满足，立即停止并报告，不得带错继续推进。**
- **未决事项**：不得静默假设，必须显式挂到对应 workstream 或在 `docs/adr/` 记录。
