<a id="round2"></a>
# W8 验证恢复 · 第 2 轮：通信分层诊断的离线收口

- 任务 ID：20261027-001-w8-validation-recovery；轮次：2；日期：2026-10-27。
- 来源：用户要求开展当前工作区第二轮，并说明 DSH 尚未启动。Codex 裁定本轮目标、派工与验收；DSH 学习同版本实现、整理证据并交回方案。
- 依照 [协议](../../../README.md#protocol)、[DSH 自主权限](../../../README.md#executor-autonomy)、[角色](../../../roles/deepseek.md#startup) 领取。先读当前指针、本单和 [第一轮审查](../round-1/review.md#round1-review)，按需展开引用。
- 项目入口：[Runbook](../../../../docs/archive/ROS2迁移步骤.md#status)；[spec](../../../../docs/archive/specs/w8-validation-recovery/spec.md#round2)、[tasks](../../../../docs/archive/specs/w8-validation-recovery/tasks.md#round2)、[checklist](../../../../docs/archive/specs/w8-validation-recovery/checklist.md#round2)。契约只引用 [硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。

## 目标与已有判断

第一轮四例均有效但接收为零，只证明该次 UDPv4 未显示改善。S2 前置尚不满足。本轮完成一次有来源支持的离线诊断，交付下一次能区分“发现/端点匹配”和“匹配后的数据/回调链路”的最小取证方案，交回 Codex 决定；不在本轮执行该方案，不另建 runner 或测试框架。四步任务链保持同一 ID，不归档整链。

Codex 已逐对读回八份实际快照并检查 launch_endpoint：两端 remap 的 namespace/topic 相同，域39/LOCALHOST 相同，关键 RMW/FastDDS 库一致。官方 listener 0.33.11 的 stdout 无缓冲，订阅 chatter/depth10。摘录与源 SHA 见新证据根 config/sources/codex_offline_inspection.json。这些只降低明显 remap/输出缓冲错误的优先级，不能据此宣称 discovery、QoS 或数据通路正常。已有记录缺直接端点匹配观测；追加同样 ABBA 的区分价值不足。

## 学习与具体交付

1. 复用 [既有离线比较](../../../../experiments/ros2-diagnostics/20261026-p3-r4/report/offline_comparison.md#analysis) 和对应 config/sources/index.json 四份官方快照，核对 SHA。第一轮只读根 experiments/w8-validation/20261027-transport-abba-r1/；较早跨语言成功的结论与限制以既有比较及第一轮审查为索引，不全量重复加载历史轮次。
2. 针对缺失观测学习本机同版本已安装 headers/包元数据，以及必要的官方源码/文档：demos 0.33.11、rmw_fastrtps 8.4.4、Fast DDS 2.14.7、ROS 2 Jazzy。可重点查 publication/subscription matched、incompatible QoS、RMW graph 与 Fast DDS 日志的实际可观测能力；不能假定普通 debug 日志必有匹配事件。允许用 curl 获取官方项目仓库/官方文档的精确版本资料，快照、URL、tag/commit、SHA、获取时间归新根；记录版本不符、拿不到或文档能力不足。禁止把未读网页或其他版本知识当已核实事实。
3. 形成 report/diagnosis.md：区分事实、Codex 已有判断与 DSH 推断；对发现/端点匹配、QoS、数据/回调链路和时序假说，逐项给支持/反证、尚缺信息及能改变判断的观测。不因全失败断言 SHM/时钟/权限根因；历史跨语言成功有残留和次序混杂，不能作干净阳性对照。
4. 形成 report/next_probe.md：推荐一个最小方案并说明排除其他候选的理由。给出准确命令或必要 API/回调、观测者是否新增 DDS participant、预期输出的原始来源、正/负/无效的判读表、控制变量、进程所有权与清理、配对时钟和停止条件。写出建议的进程数、attempt/重试/时间预算及所需权限，全部明确标“候选，未授权执行”。优先本机已有能力；若必须写小型探针、构建或抓包，说明为什么现有示例/日志不能替代，并仅列拟改白名单，不实施。观察者能看见 graph 不等于生产端点互相匹配，匹配也不等于回调执行；须解释观测局限。方案应能在一次有限取证后指导下一步，不设计通用框架。
5. 完成证据索引、命令/退出码与限制说明，交回 Codex。没有足够来源支持可执行方案时，交付具体缺口并置阻塞；不凭猜测补造命令或自行运行验证。

## 基线与写入边界

HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290 / main；保留全部已有 dirty/untracked。Codex 将在派工定稿后生成新根 config/codex_dispatch_baseline.json 与 config/baseline_receipt.json：核对回执 SHA、HEAD/branch、files 中全部 size/hash，记录 missing/changed；未知变化停止。新基线明确吸收第一轮结束后用户授权的协调脚本、职责、协议与本次派工文档变化，不修改旧基线。mutable_handoff_excluded 中的当前指针/本轮回报和审查不作为冻结路径；新 tasks/checklist 在领取核对后只追加本轮执行事实。基线是列明路径覆盖，不声称全文件系统保护。

只允许写入：

- experiments/w8-validation/20261027-communication-diagnosis-r2/ 的新 config/sources、log、report 文件；Codex 预置的 previous_current.md、codex_offline_inspection.json、dispatch baseline/receipt 只读。没有 scripts/runtime 交付目标。
- 本轮 report.md；CURRENT 按协议流转并追加来源、身份与事实；tasks/checklist 的 round2 段只勾执行事实，不代填 Codex 验收。
- /tmp/agc-w8-validation-r2-* 独占新目录及首次 experiments/_archive/w8-validation/20261027-communication-diagnosis-r2.tar、.tar.sha256、.retrieval.json。

历史证据、已验收入口/核心/测试、src/scripts/toolchain/build/install、协调脚本/协议/角色、request/review、Runbook/spec 均只读。不 commit/push/切分支/清理。不得以“离线测试”名义启动 ROS 或导入会初始化通信的模块。

## 本轮预算与停止

从首次领取配对 epoch_ns/monotonic_ns 至技术交接完成 **45 min（monotonic）**，含学习、联网等待、报告与归档。允许静态文件/包版本读取、哈希和已有 JSON/日志重算；必要的网页学习限上述官方来源。通信/官方 demo/graph observer/daemon/helper/项目节点/构建/GZ/PX4/GUI/headless/抓包均 **0 attempts**；不扫描活动端口/进程或 /dev/shm，不做系统/网络/库/时钟配置和共享资源清理。

遇基线未知漂移、缺来源、工具权限拒绝、时间不足或需要白名单外修改即保存现场交回，不扩大或重复试跑。DSH 服务启动和协调投递由 Codex 处理，不属于 ROS 实验预算。

## 验收与交接

可判定验收：来源版本/快照/哈希可复算；历史事实与推断分开；至少一个候选能提供第一轮没有的直接或明确受限的分层观测，给出精确执行需求与可判读结果；所有新运行明确未执行，相关旧代码与证据保持。候选不可行时，缺口有具体来源也可作为有效诊断交付，但不代表通信恢复或 S2 通过。Codex 独立审查后再派真实取证。

源报告/日志定稿关闭后，按既有 scripts/evidence_archive.py 对本轮新根首次归档（campaign=w8-validation、run-id=20261027-communication-diagnosis-r2），禁止 --force；归档命令输出放源根以外的 /tmp 或本轮 report.md，防自引用漂移。核对 manifest、tar、sha 与取回侧车；后续纠错、结束配对时钟、最终基线检查只追加交接回报/新侧车，不覆盖封存源。回报写明领取身份、全部实际动作/退出码、来源、差异、预算、未执行、偏离和候选限制；完成置待审查，必要条件不足置阻塞。

当前链已用 3/4 自动叫醒，本次 Codex 投递成功将用至 4/4。DSH 完成后仍按协议尝试叫醒 Codex；若退出4，记录真实守卫拒绝、保持待审查/阻塞并结束，不清零、不改上限、不换 ID 绕过。由用户手动唤醒 Codex 审查。此限制不改变本轮交付目标。

gate=not_evaluable_as_specified；headless 规模统计未授权；P1 v5 inconclusive、P2 v3 falsified/保留c2、W7-c deferred、W8-E2未预注册。S2/S3/S4仍未开放。
