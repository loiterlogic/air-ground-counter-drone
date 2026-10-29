<a id="top"></a>
# 协作机制：Leader/Worker 双模型替代 Codex+DSH

## Status

accepted（2026-10-28，来源：用户裁定；配置已实施，端到端验收待新 Leader 会话完成）

<a id="context"></a>
## 背景

原机制为跨工具交接：Codex（项目主导者）与 DSH（工程执行者）分属两个进程，靠 `.coordination/scripts/coordination_wake.py` 双向叫醒，并带状态守卫、固定会话绑定与 4 跳链式预算。

该机制的成本随使用暴露：

- 需要维护 `targets.json` 的会话 ID 绑定、`chain.json` 的跳数账、`wake/dsh-url` 的私有 token 交换；
- 叫醒依赖外部 CLI（`codex queue`、DSH Web `session/prompt`）与进程判活，任一环节失效都会静默丢消息；
- 用户需在两套工具间切换上下文，且 DSH 侧会话必须预先绑定，不能自然延续。

2026-10-28 实测确认：当前 `51234` 服务的 token 与 `wake/dsh-url` 及 `~/.dsh/web.log` 记录均不匹配（两者均返回 401），说明该链路已实际失效。

<a id="decision"></a>
## 决策

改用**同一 DSH 进程内的双模型分工**：

| 角色 | 模型 | 职责 | 交接方式 |
|---|---|---|---|
| Leader | 不固定（会话内可切） | 讨论、诊断、裁定、派工、独立验收 | `worker` 创建，`send_message` 复用 |
| Worker | 钉死：workbuddy / `deepseek-v4.1-flash` / `max` | 实施、构建、实验、如实回报 | `send_message` 通知审查 |

核心约束：**一个任务只创建一个 Worker，后续所有轮次复用同一子会话**。子会话一轮结束只是 inactive，冷恢复保留全部上下文。

执行者与 Leader 的模型解耦，由 Host 侧 `tool-worker` 行的 `agentOptions` 决定；Leader 不靠 `agent-default-model` 约束自己。

<a id="mechanism"></a>
## 机制事实（已实测）

- 子会话与 Leader 共享工作区 `/home/chen/AGC`，能读项目 `AGENTS.md`；但**看不到 Leader 的对话历史**，派工单必须自包含。
- 子会话第二轮 `send_message` 可准确复述第一轮内容（2026-10-28 实测，子会话 `bec5e577-…`）。
- 子会话不出现在 Web 侧栏，挂在 Leader 会话头部的子会话目录中；这是 DSH 设计，非缺陷。
- **执行者路由钉死**（2026-10-28 实测，子会话 `a694e295-…`）：`worker` 工具创建的子会话 descriptor 记录 `agentProvider: @huai_xin/dsh-workbuddy/cn`、`agentModel: deepseek-v4.1-flash`、`agentReasoningEffort: max`，与 Leader 当下模型无关；冷恢复按 descriptor 还原。
- **继承不是默认**：不带 `agentOptions` 的 `subagent` 复制 Leader 最后一次请求的 provider/model/effort（`resolveChildAgentOptions`），所以派工默认必须用 `worker`。
- 白名单 `subagent-model-selection-settings` 只约束**显式选择**：`assertAllowedModelSelection` 在无 model request 时直接放行，拦不住"继承 Leader 的非白名单路由"。放行路由现为 workbuddy 与 trae 两条 `deepseek-v4.1-flash`。
- 该白名单**只对新会话生效**：已存在会话不补采样，切换后需新开 Leader 会话。
- **孙代可绕过白名单**（2026-10-28 实测，孙代 `e3ea1c5d-…`）：`workflow` 引擎直接调 `startActivation()`，其 `agent()` 的 `provider`/`model` 不经 `tool-subagent` 检查，实测孙代以 Leader 级 `kimi-k3.1-pro` 跑通并返回。
- **孙代守卫已生效**（2026-10-28 实测，孙代 `49dd4d7a-…`）：`worker-route-guard` 挂在 `llm/stream`，按会话 header 的 `delegationDepth` 判定，`depth >= 2` 只允许白名单路由，其余在 adapter 派发前以 `finish{kind:'error', code:'ROUTE_NOT_ALLOWED'}` 拒绝，不消耗 token。同一探针在守卫生效前返回 `GUARD-BYPASSED`、生效后返回 `null`。
- **守卫需重启才激活**：新增的插件行不走 HMR（已加载模块的热替换不覆盖"新行激活"）；工具类行会热生效，插件行不会。改 `worker-route-guard` 代码后同样需重启。

<a id="rejected"></a>
## 未采用的方案

- **固定会话 ID 绑定**：要求用户每次手动指定 Worker 会话，违背"Leader 自行创建并复用"的诉求，且延续了原机制的脆弱点。
- **整行替换 `preset-standard`**：可在 `tool-subagent.agentOptions` 写死子模型默认值，但 preset 内部插件无法按嵌套 id patch（`applyEntryPatches` 只递归 `group` 条目），只能整行复制，DSH 升级时极易失效。实际改用**根级 `insert` 新增 `tool-worker` 行**：同样落在 `agentOptions`，但不复制 preset 内容。
- **保留叫醒脚本作兼容层**：其投递路径依赖已失效的 token 与外部 CLI，保留只会制造"看似可用"的假象。

<a id="consequences"></a>
## 后果

**删除**：`coordination_wake.py`、`start_dsh_web.py`、`dsh_workspace.py`、其两个测试、`wake/targets.json`、`wake/chain.json`、`AGENTS.override.md`（Codex 专用入口）。

**保留**：三件套（`request`/`report`/`review`）、状态机、单任务链、独立验收、T0/T1/T2 观测分级、Worker 自主权限边界。这些是项目资产，不随工具更换。

**取消**：4 跳链式预算。原硬闸用于防跨进程无人工回路；现在 Leader 在每个审查点亲自裁定，防失控改由派工边界与用户授权承担。这是**放松**，需在审查中自觉维持单任务链纪律。

**风险**：Leader 与 Worker 同进程，Worker 的错误上下文不会自动进入 Leader 视野，全靠 `report.md` 传递。派工单与回报的完整性要求因此比原机制更高。

<a id="waiting-cost"></a>
**等待成本**（2026-10-28 实测，来源：Leader）：`worker`/`subagent` 工具立即返回子会话 ID，不阻塞；子会话结束时 `notifySettlement` 把 `subagent-settled` 消息投进 Leader 收件箱（`parent.status === "idle"` 走 `queue`，否则 `steer`），不需要轮询。

- Leader 每醒一次都要重付整个会话上下文。实测 14 次空转轮询：输入 4,354 token，但每次 `cacheRead` 约 22 万 token。
- idle 时零消耗，被结算通知唤醒只付 1 次短请求。
- 结论：**派工即结束本轮**；需多任务时同一条消息并发派出。该规则对 Worker 派孙代同样适用。

<a id="open"></a>
## 未决

- 端到端验收（新 Leader 会话 → 创建 Worker → 两轮复用 → 越权模型请求被拒）尚未执行，待用户切换会话后完成。
- 已验证「创建 + 固定路由 + 冷恢复」：子会话 `a694e295-…` 两轮 config 均为 workbuddy/`deepseek-v4.1-flash`/`max`。**新会话下的显式选择与越权拒绝**仍待验证。
- 白名单只对新会话生效；本机既有会话（含当前 Leader）session 级策略为 `null`，`subagent` 不暴露模型参数属预期，须新开 Leader 会话才能用显式选择。
- 孙代**深度**仍不受限：`workflow` 不传 `maxDepth`，可继续向下派；当前只保证模型路由受守卫约束，深度靠 Worker 规则约束。
- `worker-route-guard` 是本地 bundle（`/home/chen/.dsh-plugins-worker-route-guard/`），以绝对路径挂在 profile 补丁里；DSH 升级后需确认 `llm/stream` 与 `SessionHeader.delegationDepth` 契约未变。
- 当前阻塞任务 `20261027-001-w8-validation-recovery` 未迁移到新机制；其通信根因仍需用户与新 Leader 重新讨论。
- 历史轮次中的 Codex/DSH 署名保留原样，不追溯改写。
