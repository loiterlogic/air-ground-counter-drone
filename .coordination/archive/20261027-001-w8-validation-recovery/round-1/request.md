<a id="round1"></a>
# W8 验证恢复 · 第 1 轮：官方通信 ABBA

- 任务 ID：20261027-001-w8-validation-recovery；轮次：1；日期：2026-10-27。
- 来源：用户要求按四点开始新一轮任务流；Codex 派工与技术裁定，DSH 实施/回报，Codex 独立验收。
- 前任务已结档，见 [R17](../../../archive/20261026-002-w8-measurement-p3/review.md#round17-evidence)。仅其离线入口通过；原 P3 工程/设计仍阻塞。
- 先按共同开工顺序读取 [Runbook](../../../../docs/ROS2迁移步骤.md#status)、[spec](../../../../.trae/specs/w8-validation-recovery/spec.md#scope)、[tasks](../../../../.trae/specs/w8-validation-recovery/tasks.md#round1)、[checklist](../../../../.trae/specs/w8-validation-recovery/checklist.md#round1)，遵循 [自主权限](../../../README.md#executor-autonomy)。

<a id="chain"></a>
## 四步任务链与本轮边界

同一任务依次 S1 官方通信 → S2 节点测量 → S3 两场 GUI → S4 设计裁定；每步验收后 Codex 在同任务 ID 增加轮次与三件套。当前只派 S1，S2/S3/S4 不可自行执行。**S1 验收不等于整链验收，不因通用叫醒提示中的“通过归档”提前结档本任务。** 用户已授权四步目标，阶段转换由 Codex 审查后派发，遇需改变预算/契约/目标的取舍再报告用户。默认四次叫醒上限不调整，不用新任务 ID 绕过跳数守卫。

## 已学习来源与接单基线

先读 [离线比较](../../../../experiments/ros2-diagnostics/20261026-p3-r4/report/offline_comparison.md#analysis)，以及该根 config/sources/index.json 的官方 listener 0.33.11、Fast DDS 2.14.7 env/SHM、Jazzy discovery 四份快照。Codex 本次重算四份 SHA 均相符，阅读并核对已验收入口/核心的生产配置与 CLI。无 Nav2 新引入，不读 reference/；无新 runner 实施目标。

HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290，main。已有 dirty/untracked 保留；精确状态与文件 SHA 以新根 config/codex_dispatch_baseline.json 及 baseline_receipt.json 为准（均由 Codex 派工后、叫醒前生成）。必须核对回执 SHA、HEAD/branch 与每个 files 路径，记录 missing/changed；不能用 HEAD 相同代替工作区相同。旧归档移位路径在新基线显式映射，不改旧基线。未列新路径的范围边界仍生效，本基线不声称覆盖全部文件系统。首次核对时保存领取配对 epoch_ns/monotonic_ns，写明实际执行者/会话，将 CURRENT 置执行中；唯一执行会话接单。

### Codex 基线补充（用户要求 DSH 可见会话）

原后台叫醒未完成接单，用户确认任务启动失败；Codex 核对宿主机进程未见 DSH，CURRENT 仍待执行。旧回执与旧基线保持，不重置跳数。原基线之后，以下协调功能按用户要求修改，领取核对仅允许这三项相对旧基线变化，并必须匹配下列新 SHA256：

- `.coordination/README.md`：`605f0a47637d0dc5339661fd9296359b5907ecf91227d07af0b1abeb02264b81`
- `.coordination/scripts/coordination_wake.py`：`20be648c5d104ba08be9c108d39116eeb7000d0dac059e0cd2eca703af50120f`（就绪探测 cookie 与网页 RPC 路径已修复；此前请求收到 404，未送达任务）
- `.coordination/scripts/tests/test_coordination_wake.py`：`be265d499e4ecbcfd34e58bbb263c0a0525fcbd501fb4388c553e9b3db4980b0`

新文件 `.coordination/scripts/start_dsh_web.py` SHA256 `ea0f750a28f6b9a7f8c8f093f956d7df5b6f2fa7336090e762f4403d31018877`。本 request 追加本补充，旧基线的本文件哈希相应变化；以本补充和本次正式派工为准，不回写旧基线/回执。其余保护路径有未知变化或缺失立即停止。双方交接仍遵循唯一任务链，DSH 网页服务自身及协调叫醒不计 ROS demo 试次。

冻结并直接调用的已验收版本：experiments/ros2-diagnostics/20261027-p3-r16/scripts/（R17 已原位更新 adapter）：

| 文件 | SHA256 |
|---|---|
| runtime_adapter.py | 91c6b79ca6011010490c71e1fae0f87f7ac55768fcb12bf9a7a15f4ee5e858d8 |
| runner_candidate.py | c3f7d1a1c63d79b15661a584092ee44b39fcfb3854b33903f6d79234c606ce29 |
| tests/test_runtime_adapter.py（相对 R16 根） | 5c71516826381359afd48e3ea98aafb31f992b74352aa559f6b3db7ae11b3cf9 |

核心测试与 guard 也冻结，完整指纹在基线中。原152项通过的证据只引用 R17，本轮无代码变化，无须重跑该全套，更不可为故障现改入口或掩盖 pin 变化。

## 写入白名单

- 新证据根 experiments/w8-validation/20261027-transport-abba-r1/ 下可新增 config/log/report/runtime 等文件；Codex 预置的 config/codex_dispatch_baseline.json、baseline_receipt.json、config/sources/previous_current.md 只读。
- 本轮 report.md 由 DSH 写；CURRENT 仅按协议流转、追加执行事实；新 tasks/checklist 只在 S1 段勾选或追加事实，不改验收口径。
- 正式 CLI 独占临时目录固定为 /tmp/agc-p3-r16-w8transport-20261027-r1-work 与对应 -ros-home（实际旧前缀是已验收代码的固定命名，允许这两个本轮新路径）。其它报告/归档临时目录限 /tmp/agc-w8-validation-r1-*。不得复用既有目录，碰撞停止。
- 首次新增 experiments/_archive/w8-validation/20261027-transport-abba-r1.tar、.tar.sha256、.retrieval.json；只用现有 evidence_archive.py，禁止 --force。
- 不改任何历史实验/归档、入口/核心/测试、src/scripts/toolchain/build/install、协议/角色/AGENTS、Runbook/spec 或本轮 request/review。不提交、推送、切分支、清理工作区。需要工程改动则交回 Codex 在同链另轮派发。

## 一次正式运行与新预算

1. 整轮从首次领取核对至完整技术交接上限 **45 min（monotonic）**，含学习/预检/工具等待/采集/报告/归档。静态学习、hash 和 --help 可自主安排。只读包/库/版本和活动 /proc/端口/环境检查仅为本轮正式预检与端点快照服务；不打印无关凭据，不运行 graph 观察者/daemon、packet capture 或另一个通信 helper。
2. 允许 **一次授权 CLI 调用**，其中固定 A1→B1→B2→A2，最多4 cases、8个真实 demo 端点启动、重试0。拒绝/启动失败也消耗本次调用，不换 ID 重试。A不设 FASTDDS_BUILTIN_TRANSPORTS，B两端仅设 UDPv4。域39、LOCALHOST、默认RMW、仅 source Jazzy underlay、固定空 CWD/私有 ROS_HOME，binary pin 与 canonical 库配置均不变。
3. 先创建本轮 evidence/log 与 runtime 父目录（目录必须独占且是新建），保存完整 shell 命令、起止、stdout/stderr 和 exit code。实际调用为：

    PYTHONDONTWRITEBYTECODE=1 python3 -B experiments/ros2-diagnostics/20261027-p3-r16/scripts/runtime_adapter.py --authorize-ros-run --out-root /home/chen/AGC/experiments/w8-validation/20261027-transport-abba-r1/runtime --attempt-id w8transport-20261027-r1

   这是本次新派的真实通信授权；旧 R14 越界运行不追认，旧轮预算不复活。--help 可先读；不要在测试 guard 下启动正式运行，也不要注入 Python seam/改默认 pin/重写另一个 launcher。正式 CLI 自身采集进程/端口与源环境、创建自有子进程并回收，均在本轮授权内。
4. 正式入口运行期总预算 **600 s**（以其 preflight 起点计，外部整轮45 min自领取计）。每例 listener t0、talker +2 s、快照 +4 s、SIGTERM +12 s、必要 SIGKILL +15 s、最迟 +20 s 回收/完成证据；使用现有核心的共享绝对期限。核心没有固定例间2 s等待，Codex 接受实际回收/落盘后串行进入下一例，不修改核心以凑旧 R4 间隔。运行期阻塞 I/O 不可抢占的限制照实报告，不声称硬实时保证。
5. 预检遇相关活动进程、域端口占用、权限/不可读、XML覆盖、pin不符或目录冲突，立即停止并回报。可由正式适配器做必要活动扫描，但**不扫描/删除 /dev/shm、不停其他进程、不修改 daemon/网络/隔离/时钟/库/系统配置，不改域绕冲突**。只向当前 runner 可核实 PID/PGID/starttime 所属的自有端点发信号与回收；历史 R14 或他人资源保持。中途无效/超期/清理不完整/证据缺失后例不得启动。
6. 工程节点/构建、GZ/PX4、GUI/headless、节点合成测试、科研实验均 **0 attempts**。本轮异常按现有失败收尾，不为“继续试”临时修代码或重复通信矩阵。

## 可判定验收与结果解释

- 独立记录各例真实 PID/PGID/starttime、cmdline/exe/cwd、最终允许环境、UID/net/ipc/mnt/user、实际 RMW/FastDDS 库路径/哈希及二进制 pin 来源。canonical 路径应为 libfastrtps.so.2.14.7；默认 trusted_binary_source 应为 r4_dispatch_pin。不得从观察值生成 expected 消除失败。
- 保存成对 wall/mono 样本、signal/returncode/reaped/残留、双端 console/ROS 日志，关闭后求 bytes/SHA；唯一发布/接收编号对照，console/ROS 去重。回执 hash/verified、message_source 相对路径/角色/bytes/hash/topic_source、case/batch 状态与 CLI 返回一致或具体登记差异。预检拒绝若还没建 attempt，保留 CLI stderr/exit及已有外部记录，不伪造快照或 case。
- 至少3个匹配唯一接收编号为 success，0为 failure，1–2为 partial；发布不足3、早退出、缺关键快照、超期/残留或证据无效为 invalid，停后例；未启动为 not_executed。纯0接收通信失败不是自动终止矩阵的理由，按已验收核心完成有效对照；invalid 必须停止。
- A失败/B成功/B成功/A失败只支持传输配置依赖；全成功=本轮未复现；全失败=UDPv4本轮未显示改善；其余/partial=时序/间歇性未解；无效=不可解释。任一结果都不等于已确证 SHM/权限/discovery 根因，不估计长期可靠率，不能自动恢复工程验证。判读参照离线表，但新时序/预算单列，不合并历史样本。
- 四例有效且如实分类可验收“本轮取证完成”，通信全部失败也可交付有效取证；这不代表 S2 前置已经满足。Codex 审查决定可用配置、是否在同链定向诊断或派 S2。遇明确配置依赖也先审查，不自行永久修改项目默认配置。

## 报告、封存与状态

每个离线证据检查保留唯一编号日志/命令/退出码；不覆盖失败记录。不要求为纯记录操作新增测试。report/transport_result.md 定稿需含四步链位置、实际来源/基线、前置条件/运行数、逐例表/日志与版本、配对时钟算术、未执行/偏离/限制和建议；相关新 JSON 可另存。正式运行日志结束关闭后，保存 baseline_before_archive 与唯一验证结束配对时钟，完成源报告。只执行一次：

    python3 -B scripts/evidence_archive.py --campaign w8-validation --run-id 20261027-transport-abba-r1

归档输出写封存外本轮 report.md 或专用 /tmp；核对 manifest/artifacts/tar/侧车/取回文件数量与 SHA。封存后纠错、完整交接结束配对 epoch_ns/mono_ns、baseline_handoff 与归档摘要仅追加本轮交接 report.md 或新侧车，不覆写源根/旧样本，不声称封存覆盖之后的活动。mono/epoch 分列，不能用时钟跳变修补预算或归因通信。

完成置待审查；必要条件缺失置阻塞。按协议自动叫醒 Codex 后结束，不轮询、不自行接后续步骤。基线未知变化、预算耗尽、白名单外需求或共享资源风险立即保留现场回报，不隐式清场或扩张。**整链未结束、gate/headless/P1/P2 不变。**
