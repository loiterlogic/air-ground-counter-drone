<a id="bootstrap"></a>
# 职责加载

共同项目规则与角色职责分开保存：

| 使用者 | 入口 | 职责文件 |
|---|---|---|
| Leader（DSH 高质量模型） | 用户对话会话 | [项目主导者](leader.md#role) |
| Worker（DSH 一般模型，路由钉死） | Leader 用 `worker` 创建 | [工程执行者](worker.md#role) |
| 双方 | 根目录 `AGENTS.md` | 共同规则、开工顺序与项目真源索引 |

两个角色都在同一 DSH 进程、同一工作区，交接用原生 `worker` / `send_message`，见 [交接与复用](../README.md#auto-wake)。**不需要** `AGENTS.override.md` 之类的独立入口文件：Worker 由 Leader 创建时会收到自包含派工单，项目规则经根目录 `AGENTS.md` 自动加载。

给 Worker 的完整派工用语（Leader 创建子会话时写入 `prompt`）：

> 先读 `.coordination/roles/worker.md`，再按其要求读取共同项目规则、交接协议及 CURRENT，核对任务 ID 和轮次。只执行当前派工单；完成或阻塞后写回报告和状态，不自行开始下一任务。

<a id="verification"></a>
## 配置核查与边界

2026-10-28：机制从 Codex+DSH 跨进程交接改为 Leader/Worker 同进程双模型，决策与实测依据见 [ADR-0026](../../docs/adr/0026-leader-worker-collaboration-and-batch-authorization.md#top)。已删除 `codex.md`、`deepseek.md` 及根目录 `AGENTS.override.md`；历史轮次署名保留原样。

2026-10-26 记录（历史，保留供追溯）：本机 `codex-cli 0.164.0` 程序包含 `AGENTS.override.md → AGENTS.md → 配置的后备文件名` 的项目指令优先级说明。该入口机制已随 Codex 退役，不再适用。

配置前观察到 `AGENTS.md` 的 SHA256 为 `7b9bb7d6a13989608b29c2d96b928a450bf8b6891d2035ed36f1f658aa649dbf`，已与 P3 派工保存的历史指纹不同；这是当时已存在的差异，来源尚未核实。本次修改 `AGENTS.md` 后该指纹再次变化，属本次机制迁移的预期改动，仍不重写历史指纹。
