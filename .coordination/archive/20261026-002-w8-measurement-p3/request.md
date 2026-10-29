<a id="request"></a>
# P3 派工：版本前置验证、固定预算 FCO 记录器与设计草案

> **当前仅执行 [第 15 轮入口离线返工](#round15)**。R14 未验收且实际运行越界，旧授权终止；R13 既定离线修复保持。R1–R14 为历史、不可重领。本轮 0 ROS/通信/活动扫描/被测真实进程/helper/工程/仿真 attempts；顶部第 1 轮元数据仅为历史。

- 任务 ID：`20261026-002-w8-measurement-p3`
- 轮次：1
- 日期：2026-10-26（Asia/Shanghai）
- 派工：Codex；执行：Trae / DeepSeek（接单后填写实际模型身份及时间）
- 目标：先闭合 seed/toolchain 前置验证，再完成新记录器及限定 GUI 工程验证，交回新等价设计草案；本轮由 Codex 审查，不自行冻结或执行正式计划。

<a id="sources"></a>
## 执行依据

按 [项目入口](../../../AGENTS.md#铁律) 的开工顺序阅读，Runbook [当前进度](../../../docs/ROS2迁移步骤.md#status) → [P3 spec](../../../.trae/specs/w8-measurement-p3/spec.md#scope) / [tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#tasks) / [checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#checklist)。指标见 [ADR-0099](../../../docs/adr/0099-w8-fixed-budget-mission-fco-measurement.md#metric)，证据/版本裁定见 [ADR-0101](../../../docs/adr/0101-w8-seed-evidence-and-p3-execution-boundary.md#evidence)，种子范围见 [ADR-0100](../../../docs/adr/0100-full-chain-seed-protocol.md#scope)，工具链 pin 只见 [README](../../../toolchain/README.md#pins)。契约只引用 [硬约束](../../../docs/ROS2迁移交接文档.md#hard-constraints)。

已学习的项目同版本成功实现：run_logger 的 episode/终态锁存/target 与 Bool 包络回调；task_manager 的状态 header 时间；test_epoch_seconds / test_dynamic_fire_control 的 gtest 结构；既有 runner 的臂参数和 GUI renderer 记录。执行者须实际对照后实现，不自行重写另一份任务编排。来源分类与旧树边界见规格。

<a id="baseline"></a>
## 接单基线

- 主仓分支 `main`，HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290`。
- PX4 HEAD、补丁/两文件/二进制值只引用工具链 pin 清单及下方指纹；当前状态为候选未验收，checker 已知 **24 PASS / 1 FAIL**（仅 binary SHA 漂移）。这是已知前置修复目标，不是允许忽略 FAIL。
- 已有主仓改动包括 W8 文档/审计、5 个 seed launch、评审目录、交接设施及本次 ADR/补丁；接单不得重置、覆盖或当成本人新增成果。PX4 只有 GPS cpp/hpp 两处既有 tracked 脏改动。
- 接单先保存 `git status --short`、tracked diff 与相关 untracked 内容/哈希；核对下面全部指纹（白名单文件也须核对）。接单不一致且无法由本单预期变化解释时阻塞。
- 本次边界核查不是实验：`experiments/w8-parity/20261026-w8-p3-boundary-review/`。不要覆盖、补写为本轮构建证据。

派工时完整机器可读基线：`experiments/w8-parity/20261026-w8-p3-boundary-review/config/dispatch_baseline.json`。以下文件接单逐项重算；工作区补丁快照保存在同目录，交接可变文件单列不纳入自引用哈希。

| 文件 | SHA256 |
|---|---|
| `.coordination/README.md` | `5cb7962c7347188f28a97ce7b78430727fea349df7b6401f6ebf17df873a662c` |
| `.trae/specs/w8-measurement-p3/checklist.md` | `3cbc713381c97ee558dbd95d1daa19921caf65b19cb51cf7ba34b96409fb056d` |
| `.trae/specs/w8-measurement-p3/spec.md` | `578c0b499a5b35572c2b308d878d840e31e14edc859dedf2c87ae8648a14d954` |
| `.trae/specs/w8-measurement-p3/tasks.md` | `4d04ee5cc2c1f449970ed43a20d39e1c463f02b5d248797d6017a31b88c0656e` |
| `AGENTS.md` | `15d9c50d74cbaf3a093eb5530734ca35981220c7326dc8055032d45f5fa35c33` |
| `docs/ROS2迁移步骤.md` | `f4afe412133143a0ab7a2add06531aed577f1547cd6dc3a168b1fa9ff0e42003` |
| `docs/adr/0074-visibility-metric-fixed-observation-window.md` | `e4da9f232b2f3403b7d9321f7939da653cf449e55541addf6399161a98b99b0b` |
| `docs/adr/0096-w8-gui-headless-equivalence-design-bounds-and-gate.md` | `c77cd69b89dbba40b725ed7cb82693da892dd53c6c573e685010e7021ba8acf9` |
| `docs/adr/0098-w8-determinism-probe-and-measurement-spec-change.md` | `57a3a5aec29cd6048d702bc3456dffe392feccf4790fc2962d210e465942a484` |
| `docs/adr/0099-w8-fixed-budget-mission-fco-measurement.md` | `a6165c2cd39f81cb92adc79b3d01550d7ba420a23ca69f958cf4e86e866610ef` |
| `docs/adr/0100-full-chain-seed-protocol.md` | `8d11bbc9daa34a3c9c4ac53550218ba117f2fd25c6bea1f451691b607fd689c6` |
| `docs/adr/0101-w8-seed-evidence-and-p3-execution-boundary.md` | `23fcd1eb56ebbdc235d0e3d6c4af114711021df976bcbf7b21a0555589fa4a7d` |
| `docs/reviews/agc-review-2026-10-25/W8测量规格裁定.md` | `6f49a10dde0892e46b6a0687bfb9280aa4f3b18472af28941288d448e846f6ca` |
| `docs/toolchain/PX4-NOTICE.md` | `b6b8ae5a5fc5e1df553d1ae2961cf236944071cc9e4eea3e847b99eff93e1349` |
| `docs/toolchain/px4-gps-seed-v1.patch` | `f8f13e7b696654ea5582844f11650fead362b71a154f15b12386f0ea539b3999` |
| `scripts/episode_runner.py` | `8ecd0fb648d246e9e21a238627ea618d169e81bbbb61f55f08d85c638b3e549d` |
| `scripts/tests/test_w8_determinism_probe.py` | `ed8238cabe9e7d2213375a5c661c4a637ca6518f2d8b2278ade80298f53cfad2` |
| `scripts/toolchain_pin_check.py` | `c784cc5d58a3d665edb5eea72e08378f6a92cfdca40e5243344a17006c9ed729` |
| `scripts/w7b_arms_runner.py` | `8ff4def905070451895b78ef90f9c69f6cb8078a4fda47c41cc8b3481958c49b` |
| `scripts/w8_determinism_probe.py` | `62876a0b9bec3f0a700fe208ea745f35b97fc856548af23831a637998319fb0a` |
| `scripts/w8_measurement_p2_audit.py` | `39292aa0a38ce39251ba1d2c600f79c1aeba6c16dd7d5d5243f93333b86d3023` |
| `src/agc_air/launch/air_bringup.launch.py` | `104c572ca3600f4d8761acc9e86e02538a83fba29ae13f10663eed15f473e28c` |
| `src/agc_perception/launch/perception_bringup.launch.py` | `a4b50fa677412787b1a86cd469212e64338771de5810f25bc4b5621023ebc100` |
| `src/agc_task/CMakeLists.txt` | `149fe518f4ee2c10d657c4ee0540c7ddcae8d2cbd04dbb1d6a0479b2df94e922` |
| `src/agc_task/launch/m0_skeleton.launch.py` | `e60cd5bc3948b2494fb3343a5b5174999aa8f5629041ac1e2b3a4c40d72a5abc` |
| `src/agc_task/launch/w6.launch.py` | `12c46150bbb17390f321632348c7b8e64176f7b5bde3b6926249cc1865fc975d` |
| `src/agc_task/launch/w6_composition.py` | `fea24486b0623c6c09180265c21e069cea26c2019d28f2637f5f9d07e22c8337` |
| `src/agc_task/package.xml` | `fa36ba2f978e1ac14b4eb3bebe31c7a338b9a8210d03f82992d7950c4d8c6b34` |
| `src/agc_task/src/run_logger.cpp` | `d823030a7bdd3775105754bdcebc0894729849276179b8ea50f2481ead6be6a5` |
| `src/agc_task/src/task_manager.cpp` | `09972e7470c1af10bfc98d019587fffff0bf00e7dd6bd7c07944609bef92a50e` |
| `src/agc_task/test/test_dynamic_fire_control.cpp` | `7e86d78a748a8b09c7aac7b9e5c67c863baf2efb9bc2064c84509d64a5d4457c` |
| `src/agc_task/test/test_epoch_seconds.cpp` | `02676a7cd8827b0a58b1ae0c1d82dedb3077b8205912a651d57b7157f214dd57` |
| `toolchain/PX4-Autopilot/build/px4_sitl_default/bin/px4` | `0c2be6189fc6a0ee857379127bfc46ce516c509b16605dd5ab6dc0b6aa8863f5` |
| `toolchain/PX4-Autopilot/src/modules/simulation/sensor_gps_sim/SensorGpsSim.cpp` | `ad4bae3a38518e2e957cbb022052e4e0617b3d464bc144ef8b5ca725ec750d3e` |
| `toolchain/PX4-Autopilot/src/modules/simulation/sensor_gps_sim/SensorGpsSim.hpp` | `4d3f8302175bead59e62a71551c9165420fd27ca8cb4b2adf1565430342a6e2e` |
| `toolchain/README.md` | `3d7cfb038f475040c7e67c2c824acf240933ced77dfb3f7e62616500c221f8df` |

<a id="whitelist"></a>
## 修改白名单

仅允许以下路径，新增文件限定于列出的名字/目录：

- `scripts/toolchain_pin_check.py`、`toolchain/README.md`：补丁/dirty 覆盖与已验证构建后的显式 binary pin 更新；上游/子模块/Agent pin 不变。
- `scripts/tests/test_toolchain_pin_check.py`、`scripts/tests/test_full_chain_seed_protocol.py`、`scripts/tests/fixtures/px4_gps_seed/`：前置测试/生产 RNG harness，可在夹具引用/编译生产源，不能用重写 RNG 冒充生产测试。
- `src/agc_task/src/run_logger.cpp`、`src/agc_task/include/agc_task/mission_fco_fixed_budget.hpp`、`src/agc_task/test/test_mission_fco_fixed_budget.cpp`、`src/agc_task/test/test_run_logger_mission_fco.py`、`src/agc_task/CMakeLists.txt`、`src/agc_task/package.xml`（仅测试依赖/测试注册及新组件连接）。
- `scripts/w8_mission_fco_audit.py`、`scripts/tests/test_w8_mission_fco_audit.py`：只读审核器及必要的关键错误案例。
- `src/agc_rl/config/w8_mission_fco_equivalence_draft.yaml`：只写设计草案，状态按规格，execution_authorized=false。
- `.trae/specs/w8-measurement-p3/{spec,tasks,checklist}.md`：仅追加实现细节、证据索引、未决与勾选，不能改需求/预算/裁定。
- `docs/adr/0100-full-chain-seed-protocol.md`：只追加本轮可定位验证证据及状态解释，不回写历史声明为当时已验证。
- `docs/ROS2迁移步骤.md`：仅同步本轮实际进度和证据，不改 gate、历史结论。
- `.coordination/task/report.md`、`.coordination/CURRENT.md`：按交接规则填写本轮，不写 request/review，不归档任务。

**只读保护**：既有五个 seed launch/composition、PX4 cpp/hpp、保存的 patch/NOTICE、ADR-0099/0101、历史计划/产物/科研 adjudication、任务管理/控制/火控代码。前置检查发现需要修这些代码时，登记规格未决并阻塞，不能临时修补。临时 harness/应用补丁只能在隔离夹具，不能重置活动树。

**产物目录授权**：`experiments/w8-parity/20261026-w8-measurement-p3/`（config/log/metrics/report）；两个 GUI 对应 runner 自然生成的 `experiments/w6-task-eval/<新run_id>/`（逐个记录身份）；`experiments/_archive/w8-parity/20261026-w8-measurement-p3*`（新归档/侧车/取回目录）。构建可写 `build/`、`install/`、`log/`；PX4 仅可写自身既有 `build/px4_sitl_default/` 构建/运行产物；临时文件 `/tmp/agc-w8-p3-*`。已有同名证据目录则停止回报，不覆盖。保存 manifest 和哈希覆盖主目录、子 run、原始日志/区间；按 ADR-0064 归档并独立取回核验。

<a id="steps"></a>
## 顺序与预算

1. 领取、记录时间/模型与基线，CURRENT 设执行中；按规格 R1 补齐前置。保存实际 GPS 编译步骤，验证成功后才改 binary pin、重跑 checker。旧失败与新通过记录同时保留。
2. R1 通过后实施 R2。对生产积分器做手算确定性测试，并做真实 run_logger 节点合成 /clock+消息测试；本步不启 GZ/PX4。保留完整命令/退出码/失败原因，修复限 R2 白名单。
3. R1/R2 通过后，按 R3 依次 GUI：s15/p1_coop/seed5 → s08/p2_rl_high/seed0。**总计最多 2 attempts，重试 0，headless 0，lightweight 0，GUI 阶段墙钟 ≤30 分钟**；启动失败也占数。首场 seed/完整性/renderer/infra 异常则不启动第二场。沿用 spec 固定参数，`--help` 已核对 runner 支持；实际命令与 renderer 留证。
4. 测试/构建可因本任务白名单内实际修复后重跑相关项，不能无关全量扫测或启动额外系统实验。无网络下载/安装/升级/清理共享 shm，不自动终止活动或他人进程。runner 有 sweep，先核查其匹配范围与现有进程，冲突即阻塞。
5. 按 R4 交回草案。正常通过路径完成 T1–T6，回报与 CURRENT 设待审查；不可行设计如实交回，不视为允许放宽容差。前置/验证受阻则写清现场与规格未决，CURRENT 设阻塞，不能虚报完成。

正式等价、新 pilot、P1/P2 科研重跑、W8-E2、新预注册、在线 RL、W7-c 并行均为 0。不自动 commit/push/merge/reset/clean，不切换分支。任何需要超范围修改、额外 attempt 或预算变更须交回 Codex。

<a id="acceptance"></a>
## 可判定验收与回报

- R1 有真实生产测试、可定位编译日志、输入/产物指纹与 checker 新覆盖的正负例；当前 FAIL 不靠直接改哈希掩盖。
- R2 测试、真实回调链与 GUI 产物可相互核验；覆盖账和积分、null/识别界、新旧字段边界正确；新指标未回套历史。
- R3 至多两次、指定参数、全部尝试保留，有 GUI 可视证据、D3D12 日志、seed 与版本取证、独立区间审计、完整任务/安全/infra 字段。未完成项明确写“未执行/未通过”。
- R4 有方法和工程依据及可复算预算；不把两个工程 run 当正式样本；草案可为不可行/有待裁定，但不能伪称冻结或等价通过。
- 回报区分原有与本次 diff，含实际命令/退出码/测试数/attempt 数/证据相对路径/关键 SHA256/归档取回结果/未执行与偏离。保护文件指纹结束时再核对。
- 工程实现最终验收及下一步由 Codex 独立审查；执行者不能代填 review，不开始下一任务。

发现契约硬约束违规按项目入口停止；超范围根因与证据不足写入 [规格未决](../../../.trae/specs/w8-measurement-p3/spec.md#unresolved)，回报阻塞原因和已耗预算，不带错继续。

<a id="round2"></a>
## 第 2 轮：仅通用 ROS 2 通信诊断与证据补全

- 同一任务 ID，当前轮次 **2**；2026-10-26，Codex 派发，Trae / DeepSeek 执行。
- 依据：[首轮审查](review.md#round1-evidence)、[限定规格](../../../.trae/specs/w8-measurement-p3/spec.md#infra-diagnosis) / [tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#tasks) / [checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#checklist)、[Runbook](../../../docs/ROS2迁移步骤.md#status)。先读 [执行者职责](../../roles/deepseek.md#role)。
- 目标：用官方 stock demo 核实是否存在可复现的 ROS 2 通信异常，补齐环境与双端原始证据。允许交回“未复现/尚不能定位”；禁止以残留段、graph 为空或超时直接认定根因。

### 基线与写入范围

HEAD/分支仍为首轮记录值。Codex 已创建本轮产物根 `experiments/ros2-diagnostics/20261026-p3-r2/`，其中仅有 `config/codex_dispatch_baseline.json`；本文件记录 692 个现有文件/链接与工作区状态，SHA256 为 `127bdd761c38fb315101e8e7f792988dc080621d94b6bbc340571520498572af`。接单核对基线；这是第二轮观察快照，不覆盖第一轮基线，不表示接受既有工程改动。`AGENTS.md` 的已知差异与 Codex 新增角色文件见首轮审查，不自行恢复或删除。

本轮只允许写：

- `.coordination/task/report.md` 追加第 2 轮；`.coordination/CURRENT.md` 按协议更新。不得修改 request/review。
- 上述新产物根下 `config/`、`log/`、`report/` 的新文件；不得改动 `codex_dispatch_baseline.json`。临时诊断脚本、日志及本轮进程的 `ROS_LOG_DIR` 放该目录或 `/tmp/agc-p3-r2-*`。
- `.trae/specs/w8-measurement-p3/{spec,tasks,checklist}.md` 仅追加本轮取证结果/证据链接与勾选；不改预算或原有工程要求。
- 若使用既有归档工具，仅允许新增 `experiments/_archive/ros2-diagnostics/20261026-p3-r2*` 及其新取回临时目录；归档命令 stdout/stderr 留在 `/tmp/agc-p3-r2-*`，不能把一个仍在写的日志打包再继续写入。不得覆盖历史归档或 manifest。

工程源码、现有脚本、系统文件、全局 shell/ROS 配置、旧实验产物、共享 `/dev/shm` 均不在写入范围。本轮不构建、不安装/升级，不改 RMW 或传输实现，不清理 shm、不停止 ROS daemon/他人进程；不启动项目节点、GZ/PX4、GUI/headless 或业务实验。仅允许回收本轮自身创建且记录了 PID/归属的 demo 子进程；未知进程不动。

### 学习与取证步骤

1. 先对照本机 `/opt/ros/jazzy/lib/demo_nodes_cpp/{talker,listener}` 与 `demo_nodes_py` 同类可执行入口、包版本和 [Jazzy 官方发现配置](https://docs.ros.org/en/jazzy/Tutorials/Advanced/Improved-Dynamic-Discovery.html)。同版本 Nav2 包未提供可直接解释此问题的配置，使用 ROS 2 官方 demo 作为独立参照，不猜测环境变量支持范围。
2. 记录实际执行位置：宿主终端或工具沙箱、UID、网络/IPC namespace、所用 shell/source 顺序、ROS 发行版、包/可执行路径、RMW 与发现配置。仅保存相关 ROS/RMW/库搜索路径变量，不导出完整环境或凭据；记录变量 unset 与默认值的区别。不能把沙箱通信失败解释为宿主机损坏；若无法获得宿主执行权限，报告此限制，不绕过权限。
3. 统一双方配置、唯一诊断 namespace/topic、核对未使用的专用 `ROS_DOMAIN_ID`，使用 stock String 消息；不使用项目话题。先在仅加载 `/opt/ros/jazzy/setup.bash` 的环境做四个方向：C++→C++、C++→Python、Python→C++、Python→Python。双方显式使用同一 domain/发现配置及本机已安装默认 DDS RMW；不另外切换 RMW、设置新 XML 或 transport 变量来试错。每个 case 保存双端完整命令、相关环境、PID、输出和退出码；成功须有 listener 实际收到相符文本，不能仅看 publisher 自报发送或 `ros2 node list`。
4. 仅在前四组有明确结果且预算充足时，补两个对照：当前 inherited/overlay 环境下 C++→C++ 与 Python→Python，保持其余参数一致；明确与 underlay 的变量/可执行路径差异。测试前后的退出由本轮进程自身管理，不停止共享 daemon；工具权限错误记录后停止该分支，不重复碰运气。
5. 结合证据区分应用未启动/早退出、双方配置不一致、执行环境隔离与尚未定位的通信故障。不能因 Python 正常就排除 DDS，也不能因 C++ 零接收断言 C++ 整体故障。需要额外配置、抓包权限、软件安装或清理时仅提出后续最小方案，不执行。
6. 在新报告中说明首轮 `log/evidence_archive_final.log` 的 manifest/tar 哈希与当前哈希及字节数差异：tar 中为空，当前含归档输出。只留新侧车，历史不改。追加本轮回报，列出所有 case 及未执行项、证据路径、根因置信度；诊断结束设待审查，权限/环境仍阻止取证则设阻塞。不得自动继续第 1 轮工程动作。

### 预算、验收与停止

- 最多 **6 个通信 case**，每组双端运行不超过 **20 秒**，不自动重试；诊断墙钟上限 **12 分钟**。失败也计数，未完成的如实记录。工程/仿真 attempts 为 **0**。
- 验收看可复核证据链：基线一致、环境明确、每次命令/退出码/双端输出齐全、接收与假说区分、完整 attempt 清单及新侧车；不要求强行得出某个根因，不将诊断通过视为项目工程验收。
- 超预算、需越权写入/清理、现存任务受影响、保护文件出现未知变化或契约红线触发即停。回报保留现场；下一步由 Codex 根据实际证据另行裁定。

<a id="round3"></a>
## 第 3 轮：仅修正通用诊断进程管理与证据

任务 ID `20261026-002-w8-measurement-p3`，轮次 **3**；2026-10-26，Codex 派发，Trae / DeepSeek 执行。先读 [执行职责](../../roles/deepseek.md#role)、[Runbook](../../../docs/ROS2迁移步骤.md#status)、[规格](../../../.trae/specs/w8-measurement-p3/spec.md#round3-correction) / [tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round3) / [checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round3)、[第二轮审查](review.md#round2-evidence)。只执行本节，旧授权暂停。

### 基线和学习来源

分支 `main`，HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290`。新根 `experiments/ros2-diagnostics/20261026-p3-r3/` 接单时仅有 `config/codex_dispatch_baseline.json`，覆盖上一轮相同 692 路径的当前状态，SHA256 `437fc663ca078a93e76184a1ea4f64bd1d304e43756eee1ede35fcdbcc63e05d`。四个交接可变文件仍排除。规格/Runbook 已由 Codex 更新；快照不表示验收旧实现。接单和结束均核对基线/差异；未知变化停止，不能更新基线掩盖。

先读本机 `/opt/ros/jazzy/lib/python3.12/site-packages/ros2run/api/__init__.py` 的 `run_executable()`：它另建 Popen 子进程。对照本机 Python subprocess 的 `start_new_session=True`、`wait(timeout=...)` 和超时后 terminate/kill 再 wait 的标准机制。发现配置仍参考 [Jazzy 官方说明](https://docs.ros.org/en/jazzy/Tutorials/Advanced/Improved-Dynamic-Discovery.html)。不猜测新配置。

### 白名单

- 新根下 `config/`、`log/`、`report/`、`scripts/`；保留实际诊断脚本，派工基线不可修改。临时文件/ROS_HOME 用 `/tmp/agc-p3-r3-*`，ROS_LOG_DIR 为本轮独有目录。
- report.md 仅追加第 3 轮、CURRENT 按协议更新；不写 request/review。
- 三个 P3 spec/tasks/checklist 仅追加结果、证据和勾选，不改要求；Runbook 由 Codex 维护。
- 新归档/侧车 `experiments/_archive/ros2-diagnostics/20261026-p3-r3*` 及独立取回临时目录；归档输出放 `/tmp/agc-p3-r3-*`，不得写入待打包目录。

第二轮日志、元数据、manifest、tar 和回报原样保留。不得修改工程源码/现有脚本/系统配置，不构建、不安装、不切换 RMW/transport、不设新 XML、不清理 shm、不停 daemon/他人进程，不启动项目节点或仿真/GUI/headless。仅回收本轮创建且身份可核验的官方 demo 进程。

### 步骤

1. 领取并设执行中，记录实际工具/宿主环境、UTC 与单调时钟开始时间；核查已有进程和专用 domain 冲突，冲突则阻塞。只保存相关 ROS/RMW/库路径变量，不导出全环境或凭据。
2. 新更正侧车列出第二轮三组过期 listener 哈希与最终哈希/字节数、真实/包装器 PID、可证明的存活时长下界及退出码口径限制。Python listener 的确切退出时间无法还原则写未知。区分最终归档完整与内部 case 元数据过期；不改历史。
3. 保存独立诊断脚本。仅 source `/opt/ros/jazzy/setup.bash`，直接执行已安装 `/opt/ros/jazzy/lib/demo_nodes_cpp/{listener,talker}`，不使用 ros2 run/timeout 包装端点，不加载项目 overlay。若用 shell 加载环境，须 exec 实际 binary，确保 Popen PID 即端点 PID。双方使用相同默认 RMW、LOCALHOST、未占用专用 domain、唯一 namespace/topic，记录实际路径、库路径和配置。
4. 最多一次 C++→C++ case。两端各自独立会话/进程组，记录真实 PID/PGID/启动时间与归属，持有 Popen 句柄。自首端启动用单调时钟计时，建议 listener 先启 2 秒；最迟第 12 秒开始停止两端，只向已核验的自有进程组发终止信号。限时 wait，必要时仅 kill 该组并再次 wait；完整启动到全部回收不得超过 20 秒。异常同样 finally 清理，占本次预算，不重试。不能保证时不启动并回报阻塞。
5. 保存两端真正 returncode、信号/自然退出、wait 完成时间、匹配接收文本和清场清单；不能以包装器 -15 或 timeout 124 充当端点退出码。无接收也如实交回，不增等待或配置矩阵。
6. 两端退出、进程组无残留且输出文件关闭后，才统计接收、字节数和哈希；随后生成最终元数据/manifest/归档。现有归档工具先只读确认用法，不改工具；封存后不再修改日志。追加报告与证据，设待审查；受阻则阻塞，不自行启动下一轮。

### 预算和验收

- 通信 case **≤1**、重试 **0**；首端启动至全部端点回收 **≤20 秒**；从领取后开始取证到清场的诊断墙钟 **≤8 分钟**，包含环境/脚本准备，不能用运行时长之和代替；归档与撰写回报另记起止。预算不足不启动，保留未执行记录。工程/仿真 attempts **0**。
- 验收看更正侧车、实际脚本、时间/PID/PGID/环境/真实退出码、双端日志、清场和最终哈希。收到匹配文本才记通信成功；一次成功不证明全面修复，一次失败不能定位 DDS 根因。
- 目标是取证流程正确，不要求定位根因，不恢复项目验证。超时、权限受限、未知进程、保护文件变化或需超范围操作时停止，保存偏离，不绕过工具权限、不清共享资源，由 Codex 独立裁定。

<a id="round4"></a>
## 第 4 轮：官方示例默认 / UDPv4 传输判别

- 任务 ID：`20261026-002-w8-measurement-p3`；轮次 **4**；派工 Codex；执行 Trae / DeepSeek；日期 2026-10-26。
- 新授权：只执行本节，前 1–3 轮均耗尽且不可重领；原工程任务仍未验收，不结档。用户已要求先完成离线比较再派工，本轮 [分析与决策](../../../experiments/ros2-diagnostics/20261026-p3-r4/report/offline_comparison.md#analysis) 已完成，必须先读。
- 规格：[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round4-transport)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round4)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round4)。只使用通用官方 demo，不涉及业务节点/仿真。

### 学习与接单基线

先按项目入口顺序阅读，再实际阅读离线报告所列官方 listener 0.33.11、Fast DDS **2.14.7** 环境变量/SHM 文档和 Jazzy discovery；URL、已下载快照及哈希在本轮 `config/sources/index.json`。这是可复用的官方配置做法，不是本机故障已被他人修复的证据。官方仅 UDPv4 设置有 `use_builtin_transports=TRUE` 前提；不忽略隐式 XML。进程管理参照本机 ros2run 源码、Python subprocess 官方语义和第 3 轮审查，不能原样复用存在异常清场缺口的脚本。

- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290`，分支 `main`。
- 新基线：`experiments/ros2-diagnostics/20261026-p3-r4/config/codex_dispatch_baseline.json`，SHA256 **`2e991da6d58d32d05cf4a47551f28c7eac1b07dd25f3dd7a14edc82f40b1633a`**，共 755 个路径（前轮 692 路径 + 历史证据/离线报告）。先核对基线自身与逐文件哈希、HEAD/branch、已有 dirty/untracked；既有修改保留，不代表工程验收。
- AGENTS.md 已有来源未明变化继续列待裁定，不恢复/覆盖；其当前哈希包含在基线。新未知相关变化、无法读关键证据或异常参与者一律停止回报，不能清场后继续。
- 接单把 CURRENT 改执行中、填写实际身份和时间。本轮总诊断计时从**首次接单核对/预检**开始，不能后移到写 CURRENT 成功或第一次启动进程；工具故障/等待计入预算。

### 写入白名单与产物

只新增本轮根 `experiments/ros2-diagnostics/20261026-p3-r4/` 下的 `scripts/`、`log/`、`report/transport_result.*`、`config/` 中新的运行环境/元数据/manifest 文件；不得修改已存在的离线报告、sources、基线。只可追加本任务 report 第 4 轮、更新 CURRENT、勾选对应 tasks/checklist 并追加事实，不改 request/review/spec/Runbook。允许本轮专属 `/tmp/agc-p3-r4-*` 临时工作目录，以及首次创建 `experiments/_archive/ros2-diagnostics/20261026-p3-r4.tar`。禁止复用或覆盖已有产物路径，冲突即停止。

不修改 src/、公共 scripts/、build/install/toolchain、系统文件、配置或时钟；不构建/安装/运行工程节点、测试、GUI、headless、daemon 或 graph 观察者。工程/仿真 attempts **0**。不清理 `/dev/shm`、不 kill 他人/历史进程，不切换 RMW、不新建 XML、不添加额外 participant、不做 packet capture 或提权。无 git 提交/推送/切换/清理。

### 对照与预算（完整运行前先保存脚本）

1. 只读预检进程、库/包版本、二进制哈希、UID、namespace（net/ipc/mnt/user）和 CWD；确认没有相关现存 demo/daemon 或 domain 冲突。不能证明专用 domain 可用就停止，不换号试探。使用 **domain 39**、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`，不调整网络/主机隔离。
2. 从白名单环境在 `bash --noprofile --norc` 下仅 source `/opt/ros/jazzy/setup.bash`，不 source project overlay，不继承 LD_PRELOAD 或其它非基线注入。只保留必要 HOME/USER/LOGNAME/LANG/LC_ALL/PATH/SHELL 与明确 ROS 配置。检查 source 后最终环境，包括 RMW、Fast DDS/FastRTPS、XML、discovery/static peers/data-sharing 相关变量；使用两个端点相同的纯 underlay 环境。
3. 为本轮新建固定空 CWD（`/tmp/agc-p3-r4-work`），所有 case 共用，确认不存在 `DEFAULT_FASTRTPS_PROFILES.xml` 或其他已知默认 profiles 文件，无 profiles 环境覆盖。不要添加 SKIP_DEFAULT_XML 作为第二变量。ROS_HOME 本轮专用；ROS_LOG_DIR 分 case。任何发现的隐藏配置先记录并停止，不能临时消除后继续。
4. 固定 **A1→B1→B2→A2**，最多 **4 cases，0 retry**。A 两端不设置 `FASTDDS_BUILTIN_TRANSPORTS`；B 两端只设置 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`。其余环境/端点/启动时序/路径相同，仅 case namespace/topic/logdir 必要区分；每例唯一 topic。不中途改变语言、domain、RMW、QoS、发现范围或等待时长。不根据中途结果改矩阵。
5. 两端直接执行 `/opt/ros/jazzy/lib/demo_nodes_cpp/{listener,talker}`，无 ros2 run/timeout 包装器。核对 R3 二进制 SHA：listener `f9c3d9c26887c516bedc7f4b2f4c108769047ecf3c9624a0a0d7a536d959ae2e`，talker `63c40ad0122424603a37a50adffbbb14a9a36ffedbae40e07b67012f558cf533`，变化即停止。独立进程组：listener t=0、talker t=2 s；t=12 s 向自有组 SIGTERM，t=15 s 仍存活则 SIGKILL 并停止整批，最迟 **t=20 s** 确认全部回收。所有时间用 monotonic；finally 与正常路径共享同一绝对 deadline，不叠加 5 秒 wait。Popen 成功即注册 PID/PGID，再读 /proc，避免快照失败失去清场句柄。异常必须清理自有端点并停止，不能启动下一例。全回收并核对无残留后固定间隔 2 s 再下一例，该等待计入总预算。
6. 每例运行中（两端已启动后固定时点、如 t≈4 s）保存真实 PID/PGID/session/starttime、cmdline/exe/cwd、必要最终环境、UID、上述 namespace inode，以及 `/proc/PID/maps` 中实际 RMW/Fast DDS/相关加载库路径和文件哈希。两端及所有例保持相同库/隔离条件。必须能确认加载 `rmw_fastrtps_cpp` 与当前 Fast DDS；不可读、不同库、非预期 XML/配置或映射缺失则停止，记无效，不猜测 RMW。不读取/输出无关凭据。
7. 运行中固定周期（约 1 s）由 runner 成对记录 time.time_ns 与 monotonic_ns（记录采样先后/间隔），仅观察时钟，不修改系统设置。保存双端 console/ROS 日志，最终回收后关闭句柄，再计算 bytes/SHA256、唯一发布/接收消息编号与对应日志行。SIGTERM 后 returncode 0 写“响应 SIGTERM 正常退出”，不得写无干预自然结束。记录 signal、退出码与接收结果，不只报 wrapper 状态。
8. **总诊断墙钟预算 12 min**（用连续 monotonic 衡量；含阅读/预检/脚本/工具等待/运行/清场）。用尽即停止新增诊断；启动一例前必须预留整例上限与清场时间。不因工具故障重置起点。停止后允许纯离线写报告、哈希与封存，另记时长；预算紧张可少跑，如实标未执行，不补跑。4 例是上限而非必须凑齐。

### 可审查交付与判读

- 脚本、各例命令/最终环境/映射/隔离快照、启动与清场时间轴、实际 returncode/signal、双端日志及最终 bytes/SHA、paired clock 样本、逐例前后进程清场证据；明确从哪个时刻计总预算。
- 每例按同 topic 中唯一编号对照，console/ROS log 不重复计数：≥3 条匹配接收=成功，0=失败，1–2=部分。发布不足 3、提前退出、关键快照缺失、超限或残留=无效，停止整批；不能把无效当通信失败。不做长期可靠率推断。
- [离线决策表](../../../experiments/ros2-diagnostics/20261026-p3-r4/report/offline_comparison.md#decision) 是唯一结果解释口径。A 两次失败/B 两次成功也只支持传输配置依赖，不证明残留 SHM、权限、discovery 或数据通路中的具体根因。其他组合照表报告，不能凭一次成功宣布修复。运行成功不会自动恢复工程工作。
- 回报基线核查前后差异，区分已存在 dirty 与本轮修改，列明未执行/偏离/待裁定。tasks/checklist 勾选只代表执行者回报，验收由 Codex 决定。
- 所有文件定稿且日志关闭后仅封存一次，使用现有 evidence_archive 工具（先读帮助/源码，学习既有成功用法），输出写归档目录外；**不用 --force、不覆盖 tar/manifest**。归档后独立读取核验文件数量/内容哈希并记录 tar SHA256。若封存后发现错误，仅新版本侧车记录，不改已封存输入/输出；旧档保留。归档/复核日志写 `/tmp/agc-p3-r4-*`，报告如需追加封存结果须明确为封存外记录，不反复重打包。
- 完成或预算停止后写 report 第 4 轮与 CURRENT `待审查`；条件阻塞写 `阻塞`。不开始后续任务、不归档整个交接任务。

<a id="round5"></a>
## 第 5 轮：通用诊断 runner 离线修复与故障注入

任务 `20261026-002-w8-measurement-p3`，**第 5 轮**；日期 2026-10-26；Codex 派工、Trae / DeepSeek 执行。当前唯一本轮授权，前 1–4 轮不可重领；**0 ROS demo/通信 attempts、0 工程/仿真 attempts**，不运行 ABBA、不 source ROS 环境。原任务仍未验收，不结档。

### 依据与基线

先读共同入口/角色/协议、[Runbook](../../../docs/ROS2迁移步骤.md#status)、[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round5-offline-runner)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round5)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round5)，再实际阅读 [R4 独立审查](review.md#round4-evidence) 与原脚本。学习本机 Python 3.12 `contextlib.ExitStack.__exit__`、`subprocess.Popen` 回收与 remaining-time 做法，以及项目 evidence_archive.py 临时输出+os.replace 模式；来源及 SHA 见新根 `config/reference_notes.json`。不照抄标准库无界 wait，不引入新依赖，不凭假设补一个 except 就结束。

- HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290`，分支 `main`。
- `experiments/ros2-diagnostics/20261026-p3-r5/config/codex_dispatch_baseline.json`，SHA256 **`cffb005dcc48ccd322db358cbcff3c03f909a29c5596a8ebe8ff019bca83b57e`**，772 路径；接单与结束逐项重算，报告已存在 dirty/untracked。允许本轮文档勾选差异，其它未知相关变化停止。
- 原 R4 脚本、失败日志、19 文件归档及侧车只读，不修补历史，不变更 AGENTS 或工程代码。

### 文件与运行边界

只在新根 `experiments/ros2-diagnostics/20261026-p3-r5/` 的 scripts/、tests/、log/、report/ 与新增 config 文件实现/留证；已存在 baseline/reference_notes 不改。只追加本任务 report 第 5 轮、更新 CURRENT、勾选 P3 tasks/checklist 并追加事实；不改 request/review/spec/Runbook。临时产物仅 `/tmp/agc-p3-r5-*`。可以读取旧 runner 作为待修对象，在新根复制后重构；不引入共享工程模块。

允许 Python 标准库/已安装 pytest 的**离线单元测试**；不得通过测试触发真实 ROS/系统工具/网络调用。资源/超时模拟优先用假进程与可控时钟；允许最多 **8 次无业务 Python helper 进程启动**，每个独立 PGID，生命周期含清理 ≤3 s；只用于真实 SIGTERM/SIGKILL/reap/句柄验证，不连接 ROS 或业务系统。不使用 shell 包装器/ros2/subprocess 命令注入，不修改系统配置/共享内存，不终止他人进程。

总离线实施/验证预算 **20 min**，从首次接单核对起用 monotonic 记起止，工具等待计入；测试子进程阶段累计 ≤60 s，helper 不自动重试，最多 8 次在一轮中累计，不因重跑 pytest 重置。测试最多 2 次全套（首跑+一次修复验证）；编译/静态检查不产生 helper。预算不足停止回报，不启动 ROS 来验证修复。接单先写 CURRENT 执行中及实际模型/时刻。

### 必须修复的行为

1. 生命周期核心与 ROS 适配配置分离，可无副作用导入；直接运行默认拒绝启动 ROS。本轮交付的是候选 runner，通信运行入口即使保留也必须显式授权开关且本轮不用。只对自己成功启动并登记的进程发信号，Popen 成功立刻保留 proc/已知 session PGID 归属，再做易失败快照；Popen/getpgid/读取 /proc 任一步失败仍可清理。
2. 日志释放幂等；重复关闭不因 flush 已关闭文件失败；flush/close 出错记录真实错误、仍清理其它资源，不能 blanket except 静默伪成功。primary error、cleanup errors、persist errors 区分。SIGTERM 退出明确标响应信号，不能叫无干预 natural。
3. 保存阶段证据而非最后一次才写：case 初始化、启动登记、快照、时钟采样、清场、最终结果都按已采集内容落盘/追加事件；异常时保留最近完整版本、写 primary traceback 与 partial/invalid 状态。使用临时文件+发布或追加事件；这是同一次未封存 case 的受控更新，不允许覆盖旧 attempt。持久化失败必须停止并以非零状态报告到独立 stderr；写盘完全不可用不能承诺完整证据。case/batch 两级异常都不跳过自有资源清理和可行的最后记录，异常不启动下一例。
4. 全路径共用一次绝对单调 deadline：normal/finally 的 wait 只用剩余时间，不追加固定 3 s；提前预留终止/强杀/回收时间。注册/快照/校验失败立刻进入清场，停止批次。预算起点由首次预检显式传入并核验，不能只从 main 计时；新 case 前检查剩余预算。修复 `clock_sample` 秒/ns 混用。同步阻塞操作不能自称有严格超时保证，须说明限制并用设计降低超时风险。
5. 新 attempt 输出必须拒绝任何目录/文件冲突；不得 exist_ok+wb 覆盖旧证据，路径不可猜测复用。源配置/快照敏感内容仅白名单，不输出无关环境。
6. 快照校验包含 UID/net/ipc/mnt/user/CWD、端点身份/实际 RMW、**真正 libfastrtps/libfastdds 的加载证据（不能用 rmw_fastrtps 文件名代替）**、库文件哈希成功且跨端点/跨例相等。对 A/B 最终环境差异只允许规定 builtin transport 与 namespace/topic/log 路径差异，未预期 RMW/XML/注入或关键不可读记 invalid 立即停止。预检结果保留必要扫描明细与执行范围/错误，null 不当作“无进程/无占用”。本轮只用 fixture/假快照验证这些逻辑，不运行扫描/ROS 端点。
7. 接收分类基于同 topic、匹配 published 的唯一编号交集；不重复计算 console/ROS logs；未知/超出发布集合编号显式报异常。首条接收时间只取接收事件，0 接收= null；少于3发布/提前退出/关键快照缺失/超限/残留均 invalid，不混成 failure。ABBA 方案与原阈值不变，本轮不验证传输结论。

### 验证矩阵（必须测生产候选核心，而非复制实现）

测试应验证落盘 JSON/事件/实际存活状态等结果，并对旧缺陷形成回归保护：

- 正常双端清理+重复关闭；flush/close 人为失败时其它句柄/进程仍被处理，已有快照与主错误保留。
- Popen 失败、Popen 成功后 getpgid/快照异常、第二端点启动失败；无已启动句柄遗失、无下一例启动。
- 正常 SIGTERM 回收、忽略 SIGTERM 需强杀、early exit、两端等待共用绝对 deadline；模拟时钟覆盖截止前/截止后/finally，不能靠缩短断言掩盖超时。真实 helper 仅覆盖必要资源语义，记录 PID/PGID/真实 returncode/信号/回收时间与无残留。
- case 或 batch 持久化/序列化失败，已落盘证据不消失，错误从独立出口可见且无下一例；整盘不可写不伪造“保证已记录”。
- 配置/UID/ns/CWD/库哈希差异、maps 无真实 Fast DDS 或哈希失败、A/B 传输变量错误均拒绝；同输入唯一合法差异可通过。
- 正确计时单位、预算不足拒绝启动、0/部分/成功消息与重复/不匹配编号、0 接收时间 null；导入不启动子进程，默认命令不启动 ROS；旧 attempt 目录冲突拒绝且文件字节不变。

本轮验收目标是**runner 异常时能保留证据并正确停止**。py_compile/所有 mock 已调用不能单独满足；未覆盖的风险写明。

### 回报与交接

保存测试命令、stdout/stderr/退出码、实际次数/monotonic 起止/helper 台账、基线差异、候选设计及每项缺陷对应测试证据，注明 ROS 配置仅 fixture 验证、无真实通信结论。报告追加第 5 轮；完成设 CURRENT 待审查，阻塞如实写阻塞；只有 Codex 可决定后续 ROS 对照授权。

本轮允许在测试/报告定稿后**首次**新建 `experiments/_archive/ros2-diagnostics/20261026-p3-r5.tar`，沿用通用 evidence_archive 工具，先读用法、输出写 `/tmp/agc-p3-r5-*`，不用 --force；日志关闭后哈希，封存后独立取回核验。PYTHONDONTWRITEBYTECODE=1 或 pycache 放专属临时目录；不为移除意外 pyc 重打包。封存后修正只新侧车，历史不改；报告封存摘要放交接 report，避免改封存内报告后重新打包。禁止提交/推送/切分支/清理或恢复工程任务。

<a id="round6"></a>
## 第 6 轮：关闭 runner 失败路径与测试缺口（离线）

任务 `20261026-002-w8-measurement-p3`，第 6 轮，2026-10-26；Codex 派工、Trae / DeepSeek 实施。只做通用 Python runner 可靠性修复，**0 ROS/通信/工程/仿真 attempts**；不 source ROS、不运行历史命令、不实现 live ROS 运行入口。不改原工程代码或门槛，不结档 P3。

### 接单与学习

依角色入口读 [协议](../../README.md#workflow)、[Runbook](../../../docs/ROS2迁移步骤.md#status)、[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round6-offline-rework)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round6)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round6)，逐项阅读 [R5 独立审查](review.md#round5-evidence)。重新学习 R5 `config/reference_notes.json` 所列标准库/通用归档实现，重点是剩余回调、绝对期限、失败发布语义；将具体吸收点与代码/测试对应。不能只修改报告口径或放宽断言。

HEAD/分支沿用 `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`。接单、结束均逐项重算新根 `experiments/ros2-diagnostics/20261026-p3-r6/config/codex_dispatch_baseline.json`（指纹见 CURRENT）；包含 R5 原脚本/测试/日志/tar/侧车保护。允许本轮 tasks/checklist 的指定变化，未知相关变化停止；不重置既有 dirty/untracked。接单先记首次核对的 monotonic_ns 与 epoch，将 CURRENT 设执行中并填模型身份。

### 白名单与预算

- 从 R5 候选复制到新根 `experiments/ros2-diagnostics/20261026-p3-r6/` 的 scripts/、tests/；只在该根新增 config/log/report。已有派工 baseline 不改。旧根、历史归档与侧车全部只读。
- 可追加本轮 report、更新 CURRENT；tasks/checklist 只勾选本轮并追加事实。不改 request/review/spec/Runbook/AGENTS 或共享工程模块。临时路径 `/tmp/agc-p3-r6-*`；PYTHONDONTWRITEBYTECODE=1，避免 pycache 污染证据根。
- 首次接单核对至完成 **30 min**，工具等待计入，保存起止 monotonic_ns；最多 **2 次全套离线测试**，不另加反复局部测试规避上限。静态检查不启动 helper。
- 全轮最多 **4 次无业务 Python helper 启动**（失败也占），每个独立 session/PGID，含启动/就绪/清场的生命周期 ≤3 s；子进程测试阶段累计 ≤60 s。启动前追加账目，finally 追加结果，即使测试失败也保留。仅验证通用进程/句柄核心，不调用 ROS/系统工具/网络，不发信号给非自有进程。
- helper 用就绪握手，不能固定 sleep 猜处理器安装时间；生产候选的清理/终止函数必须实际参与，不能另写一套 kill/wait 冒充。其余分支用假进程与同一个可控时钟，不为每个矩阵格启动真实进程。

### 修复与可判定验收（每项须主路径回归证据）

1. **失败闭合**：case/batch 的写入或序列化失败均经独立 stderr 报错并使 batch 返回非零；拒绝启动下一例。case 创建/运行意外异常也尽可能保存 batch 最终记录且回收自有资源。测试初始/中途/最终 case persist、batch persist、序列化失败及目录冲突；断言返回码、已落盘文件内容与后续未启动，而非只断言 mock 调用。持久化失败保留上次完整版本；记录清楚已提交版本与失败尝试，不把内存 persisted 值当磁盘已写成功。
2. **一次绝对期限**：所有 wait 只用非负剩余时间，截止后不追加 0.05 s、不再启动端点；启动前/等待后/耗时 provider 返回后检查期限，finally 统一判越限 invalid 并停批。预留终止/回收时间；预算起点必须有效且不在未来，非有限/负预算拒绝。用同一假时钟覆盖双端、启动登记延迟、快照/消息慢返回、截止已过与 finally；断言完整时间线与启动数。同步 I/O 的不可抢占限制如实记录，不宣称绝对实时保证。
3. **资源归属与清理裁定**：成功 Popen 立即登记独立 session 的已知 PGID，后续 getpgid 失败不丢归属；实际 PGID 不符禁止误杀未知组。leader 已退出也须核实自有组残留，不能只看 poll。异常及强杀路径保留实际 returncode/信号/回收/残留结果；非预期退出、残留、清理错误均 invalid、非零批状态、停批。测试 getpgid/第二端启动/快照失败、leader 退出但组仍存活、SIGTERM/SIGKILL、flush 和 close 分别失败且其余资源继续处理；未关闭句柄不可丢失后宣称清理完成。
4. **校验接入**：实际 case/variant 的两端最终环境严格符合预期，A 默认、B UDPv4，单例两端不得不同；跨例只允许约定差异。UID/四类 namespace/CWD 必须非空且与预检预期绑定；二进制身份/hash 与预期绑定。必要库以稳定身份对应完整必需集合、路径/hash，不靠 basename 交集跳过缺失/版本变化；跨例检查全部端点。主路径用 fixtures 证明双端均缺 UID/ns/CWD、库缺失/换版本或路径/hash 不同、A/B 同配置、B 快照仍默认等均 invalid 且停批；正确配置可通过。预检 null 不当作无冲突。
5. **分类正确**：发布门槛使用唯一编号，`[1,1,1]` 不构成 3 条发布；保留 topic 匹配、未知接收拒绝、重复去重与 0 接收首时刻 null。测试经 run_case 的最终分类/落盘；有效零接收可以是通信 failure，须与 runner invalid 分开。
6. **真实核心证据**：至少两个 helper 分别验证响应 SIGTERM、忽略后 SIGKILL，调用候选清理核心，台账含所有成功/失败启动、PID/已知及实际 PGID、起止 monotonic_ns、信号、实际 returncode、最终无残留。测试清理用 finally，不因断言失败泄漏。默认 CLI/导入不得启动进程；不新增 ROS 适配功能。

先完成静态实现和自审，再使用有限测试预算。出现无权限/未知进程归属/不可安全回收/超时或不足预算时立即停止，尽可能保全记录并回报阻塞；不得为凑通过值调整要求、增加 attempts 或扫杀共享资源。

### 留证与交接

report 逐项列出修复、测试名、可定位断言/原始输出/退出码、实际全套和 helper 次数、完整单调时间、基线变化、尚未覆盖限制；0 ROS/工程/仿真明确写出。R5 helper 更正为可核实 4 次，仅后两次有 ledger；不编造缺失 PID/时钟，不改旧证据，不重跑历史。

日志关闭、报告定稿后只首次新建 `experiments/_archive/ros2-diagnostics/20261026-p3-r6.tar`，先读通用归档工具用法，输出写临时目录，不用 --force，独立取回核验。封存摘要写交接 report，后续更正仅新侧车；不重封存。结束设待审查/阻塞，等 Codex 独立审查；不自行恢复 ABBA、提交/推送/切分支或清理仓库。

<a id="round7"></a>
## 第 7 轮：只闭合已复现缺口（假进程离线回归）

任务 `20261026-002-w8-measurement-p3`，第 7 轮，2026-10-26；Codex 主导/审查，Trae / DeepSeek 实施。本轮冻结功能扩展，只修 [R6 独立审查](review.md#round6-evidence) 的已复现与相邻失败路径；**0 ROS/通信/真实 helper/工程/仿真 attempts**。不 source ROS，不启动任何被测真实进程，不实现 live ROS 适配器，不扩展诊断矩阵，不改工程代码。

### 接单、依据与白名单

依角色入口/协议恢复，读取 [Runbook](../../../docs/ROS2迁移步骤.md#status)、[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round7-offline-rework)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round7)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round7)，逐项读 R6 审查表及其静态缺口。复核并学习 R5 reference_notes 所列标准库 ExitStack、subprocess 和通用 evidence_archive，实现“资源先登记再取证、单个清理失败仍处理其它资源、剩余时间不延长”；报告具体吸收位置。不要凭通过数量代替逐项验收。

HEAD/分支为 `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`。新基线在 `experiments/ros2-diagnostics/20261026-p3-r7/config/codex_dispatch_baseline.json`，SHA/路径数见 CURRENT；接单与结束逐项核对，允许 tasks/checklist 的指定本轮追加，其它未知相关变化停止。历史 dirty/untracked 保留，旧轮候选、日志、归档和侧车全部只读，不补造/回写。

只从 R6 复制到新根 `experiments/ros2-diagnostics/20261026-p3-r7/` 的 scripts/tests，在此新增 config/log/report；既有 baseline 不改。可追加 task/report、本轮更新 CURRENT，tasks/checklist 仅勾选本轮并追加事实。不改 request/review/spec/Runbook/AGENTS 或共享工程。临时路径 `/tmp/agc-p3-r7-*`；禁止改动旧 pytest/helper 台账。PYTHONDONTWRITEBYTECODE=1，不在证据根写 pyc。

### 有限实施与验证

首次接单核对就记录 epoch/monotonic_ns，CURRENT 设执行中并填实际模型；全程 **25 min**，包含核对/工具等待/报告/封存，结束保存配对时间。最多 **2 次完整离线测试命令**（首跑及一次修复验证），不以额外局部运行规避上限；静态检查不算测试。测试命令明确排除/移除真实 helper 测试，启动被测真实子进程总数为 0。允许 Python/pytest 工具自身运行，资源语义全部用假进程/同一可控时钟；禁止导入时运行旧测试。

先为反例写回归断言，再修对应分支；不重构成另一个框架。所有异常场景必须检查 case/batch 返回与磁盘证据、启动数、残留状态、下一例是否未启动。具体闭合标准：

1. **失败即停**：after_init 提交失败必须 0 启动、invalid、批非零、后续例不启动；其它 case 必需提交/必需事件写盘失败同样停当前例和批次，stderr 可见，已采集证据尽可能保留。注入 endpoint_popen、确认 PGID、采样事件等关键写盘失败，不能用 best_effort 静默吞掉。可选诊断失败必须明确标注，不能充当必需证据已提交。测试序列化/事件/提交失败以及成功路径，断言最近成功版本的内容而非只检查 exists。
2. **启动前门禁**：任何初始化写盘/阶段等待返回后，先检查剩余绝对期限，再启动 listener/talker；after_init 推进 30 s 的反例必须 0 启动。同步 I/O 仍不可抢占，返回后立即 invalid/停批；结束时间覆盖最后必要提交与校验。不得在 deadline 后追加等待。测试慢初始化、慢最终提交、双端剩余期限；不要宣称硬实时。
3. **最早登记与独立清理**：独立 session 的自有 PGID 在 Popen 成功后、任何 event/快照之前登记且可清理；event 失败仍能杀自有组及记录实际 rc，不遗漏 endpoints。测试假 leader 被杀但组有后代时组最终清空，未知 PGID 不误杀。Popen 失败后的 close 错误必须归入真实结果并保留未释放状态；组扫描/信号/回收/flush/close 任一步抛异常仍尝试其它可清理资源，不把句柄或错误写入临时对象后丢弃。
4. **退出码门禁**：默认只接受已定义的正常响应（本候选 normal rc=0）；rc=7、负信号退出、未知/未回收均 invalid、批非零、停批，保留真实 rc/信号与残留结果。保留成功、有效零接收 failure 与 runner invalid 的区别。双端 rc=7 的已复现反例必须不能成功。
5. **身份与库绑定**：关键 UID/ns/CWD 使用类型及缺失检查，不能用 str(None) 充当非空；完整必需 RMW 与真实 Fast DDS 库身份/规范路径/hash 必须绑定预检期望。拒绝两端同名同 hash 但路径改为 /unexpected/path/、库集合缺真实 Fast DDS、重复 basename/冲突映射、null 身份；未知 variant 拒绝。expected_binary 与配置/快照一致，不能传入后未使用。正确 A/B、双端与跨例完整 fixture 可通过。只做离线夹具校验，不运行真实扫描或库加载。
6. **磁盘与提交回执一致**：保留已提交快照和失败尝试的明确语义，最终 case/batch 的磁盘 status/errors/时钟与返回结果不互相矛盾。不要要求文件包含自己的最终 SHA 或提交回执；可用独立回执/批摘要表达已提交版本。测试成功、最终提交失败、提交后校验失败/慢返回：读回 JSON/事件和回执，证明没有把内存置真当已落盘，也没有将越限结果写作成功。读回失败经 stderr/批非零，不能无说明漏出异常。

### 证据与停止条件

第 6 轮 helper 可核实共 4 次，最终 ledger 仅第二轮两次；只在新报告更正，不补造首轮 PID/时钟、不重跑旧轮、不修改旧封存。报告将原始命令/退出码、实际测试次数、0 被测真实进程、完整接单至结束时间、每项反例修复前后/测试断言与证据路径、保护基线差异、未覆盖限制分清。

预算不足、发现超范围实现需求或无法安全闭合，停止并回报阻塞，不能增加次数/降低断言。完成后日志关闭、报告定稿，首次新建 `experiments/_archive/ros2-diagnostics/20261026-p3-r7.tar`，先读归档用法，不用 --force，独立取回核验；封存摘要写交接 report，后续更正仅新侧车。CURRENT 设待审查/阻塞；不自动恢复 ABBA/工程、不提交/推送/切分支/重置/清理仓库。

<a id="round8"></a>
## 第 8 轮：确定缺口的有限离线返工

任务 `20261026-002-w8-measurement-p3`，第 8 轮，2026-10-27（Asia/Shanghai）。Codex 主导/审查，Trae / DeepSeek 实施。依据 [R7 独立审查](review.md#round7-evidence)，仅修下列既有验收缺口；**0 ROS/通信/真实 helper/工程/仿真 attempts**。不 source ROS、不运行任何被测真实子进程、不做真实环境扫描或实现 live ROS adapter，不扩充 runner 功能或重构框架。

### 接单、来源、保护与白名单

按入口顺序恢复，再读 [spec](../../../.trae/specs/w8-measurement-p3/spec.md#round8-offline-rework)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round8)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round8) 与 R7 审查中的输入/实际输出。先对照 R5 `config/reference_notes.json` 所列 Python 3.12 ExitStack 独立释放、subprocess 剩余时间、项目 evidence_archive 临时发布，报告具体采用处；不可直接复制无界 wait。

HEAD/分支仍为 `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`。本轮 baseline：`experiments/ros2-diagnostics/20261027-p3-r8/config/codex_dispatch_baseline.json`，SHA256/路径数只见 CURRENT；接单与结束逐项重算。覆盖此前保护清单及 R7 当前所有文件，四个可变交接文件除外，不宣称全文件系统覆盖。未知差异停止；结束只允许 tasks/checklist 本轮追加的预期变化。历史 dirty/untracked 保留，不重置/覆盖。

仅允许从 R7 复制候选/假进程测试到新根 `experiments/ros2-diagnostics/20261027-p3-r8/{scripts,tests}`，以及在此新增 config/log/report。允许新建该根的测试入口/本地 conftest 以落实真实进程禁止，不改共享测试设施。本轮 baseline 不改。执行者可追加 task/report、更新 CURRENT，仅在 P3 tasks/checklist 本轮段记录事实；不改 request/review/spec/Runbook/AGENTS、工程/共享脚本、R1–R7 根/归档/台账。临时路径 `/tmp/agc-p3-r8-*`，`PYTHONDONTWRITEBYTECODE=1`，不用 py_compile 向证据根写 pyc。

### 有限步骤与验收

首次接单核对即记录 epoch/monotonic_ns、实际模型，状态设执行中。全程 **25 min**（包括核对/工具等待/报告/封存），结束再保存配对时间；最多 **2 次完整离线测试命令**（首跑和一次修复验证），不以其它局部运行或单独 collect-only 规避预算。静态阅读/语法解析不算测试，不执行候选 main。

1. **先封住真实启动**：在导入候选及测试收集之前安装本轮本地阻断，至少覆盖 subprocess/Popen、shell/system、posix_spawn 与 fork；移除真实 helper 测试。可以使用 Python audit hook 配合本地测试入口，禁止 ctypes/外部命令绕过。阻断必须覆盖整个测试进程，保留安装时刻、拦截计数/事件；计数即使异常被测试捕获也不得归零或被 ledger 重建吞掉。测试结束若拦截次数非零，整次测试不得报纯离线通过，立即停止/回报；不为验证 guard 启动一个真实 helper。Python/pytest/归档工具自身运行允许，不属于被测子进程。
2. **端点与资源归属**：将最小端点记录与清场资源在任何易失败事件之前一并登记；endpoint_popen/pgid_confirmed 失败仍保留 PID/已知与实际 PGID/实际 rc/信号/回收/残留结果，批非零、后例未启动。Popen 失败且 close 再失败，不将句柄丢入临时对象；应有持续可见的未释放归属/状态并独立尝试其余可清理资源。poll/组扫描/信号/reap/flush/close 抛异常不能跳过同端日志及另一端清理。以 FakeHandle/FakeProc 注入；不要求在磁盘序列化 Python handle，也不能把“错误字符串存在”当资源已释放。
3. **期限覆盖最后必要操作**：case/batch 的最终读回、receipt 提交与必要校验均受原绝对期限约束。慢返回后立即 invalid/非零、停批；报告完整结束跨度，不能用回执前的 12 s 冒充 42 s/82 s。回归 R7 表中 case receipt +30 s、batch receipt +70 s，并覆盖读回慢返回。结束核对不得引入无穷重写回执；使用有限收尾和明确“最近成功快照/失败或越限提交/最终返回”语义，同步 I/O 不可抢占，不宣称硬实时。若越限后修正也无法提交，返回/独立 stderr 必须明确磁盘只是旧版本，不得仍把成功 receipt 当最终有效结果。
4. **身份确实绑定**：expected_binary 与 config/两端快照一致，错传 `/wrong/listener`、`/wrong/talker` 时在启动前拒绝（0 launches、非零/明确异常、后例未启动），不得继续传入后忽略。预检实际必需库必须是 `librmw_fastrtps_cpp.so` 的合法库名及真实 `libfastrtps.so` 或 `libfastdds.so` 的合法版本库名，路径为绝对规范路径且末项与 basename 一致，hash 为非空字符串；不只检查语义键。拒绝任意文件冒充、相对/带上级的非规范路径、basename/path 冲突、缺失/重复/null；保留正确 A/B、双端/跨例夹具可通过。仅检查离线记录，不运行库加载或扫描。
5. **所有终态可解释**：未知 variant 必须 0 launches，返回 invalid 且可写的最终 case.json 为 invalid；经 batch 时非零/停批。所有上述反例检查启动数、完整元数据、磁盘 JSON/回执、stderr、批返回及后例未执行。保持原有 after_init 失败/越限 0 启动、rc=7 拒绝、库路径替换拒绝、有效零接收 failure 等回归。新增断言必须先对照失败路径，不仅检查文件 exists 或通过总数。

测试覆盖最终精确候选/测试/guard 文件；最后一次成功测试后若又改这些文件，必须明确未重新验证，不能宣告最终套件通过。两次命令/所有代码变化如实记录，预算耗尽不追加第三跑。R7 4 次 helper 越界、仅后两次有 ledger、最终 33 项未重跑、无封存均保留，不追认、不补造、不重跑旧轮。

### 交付与停止

新报告 `report/offline_rework.md` 列明每个缺口的代码/测试位置、原始命令/退出码、测试次数、guard 拦截统计、真实被测进程数、完整起止配对时间、baseline 差异、磁盘与返回语义、未覆盖限制。接单 processes 若未扫描应诚实标未采集，不用 null 支持“无相关进程”。不为此新增真实环境诊断。

任何真实被测启动/guard 拦截、超范围需求、预算不足或无法安全闭合即停止/回报阻塞，不删日志、不降低断言。只有完成范围内修复和最终验证，才在日志关闭/报告定稿后首次创建 `experiments/_archive/ros2-diagnostics/20261027-p3-r8.tar`，依通用工具用法取回核验，不用 --force；R7 不补封存。封存摘要追加交接 report，后续仅新侧车更正。CURRENT 设待审查/阻塞，交回 Codex；不自动恢复 ABBA/工程、不提交/推送/切分支/清理。原 P3 不结档，通信原因未定位，gate 不变。

<a id="round9"></a>
## 第 9 轮：三个确定失败分支的闭合

任务 `20261026-002-w8-measurement-p3`，第 9 轮，2026-10-27（Asia/Shanghai）。Codex 主导/审查，Trae / DeepSeek 实施。只修 [R8 独立审查](review.md#round8-evidence) 表中三个缺口；**0 ROS/通信/被测真实进程/真实 helper/工程/仿真 attempts**。不 source ROS、不扫描真实环境、不实现 live adapter、不扩功能、不改框架。R8 已通过的离线路径作为回归保留，不能倒退；R1–R8 均不重领。

### 开工、来源与文件边界

按入口顺序读 [spec](../../../.trae/specs/w8-measurement-p3/spec.md#round9-offline-rework)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round9)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round9)。先对照 R5 reference_notes 的 Python 3.12 ExitStack 独立释放/subprocess 剩余时间，以及 R8 EvidenceSink 的临时发布，报告采用的具体位置；不引入新依赖或复制无界 wait。

HEAD/分支 `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，保留已有 dirty/untracked。领取和结束逐项重算 `experiments/ros2-diagnostics/20261027-p3-r9/config/codex_dispatch_baseline.json`，SHA256/路径数见 CURRENT；包含此前保护清单、R8 全部输入/manifest/tar/两侧车，四个可变交接文件除外，不称全文件系统覆盖。未知变化停止；结束只允许 P3 tasks/checklist 的本轮事实追加。

只可从 R8 复制候选、假进程测试、conftest 到新根 `experiments/ros2-diagnostics/20261027-p3-r9/{scripts,tests}`，并新增该根 config/log/report；Codex baseline 不改。允许追加 task/report、更新 CURRENT、在 P3 tasks/checklist 本轮段记录事实。禁止改 request/review/spec/Runbook/AGENTS、共享脚本/工程/R1–R8 根/旧归档及侧车。临时路径 `/tmp/agc-p3-r9-*`，`PYTHONDONTWRITEBYTECODE=1`，不向证据根写 pyc。

### 必须闭合的三个分支

1. **真实资源仍有归属**：Popen 失败、close 再失败时，实际 handle 必须仍归属一个可达的运行时 owner，不能只留下 `unreleased` 字符串/布尔记录。登记先于易失败操作；独立尝试其余资源。采用局部小改（例如显式交给调用者的资源 owner），不造新框架；允许有界重试，重试后仍失败则保留归属/未释放状态并 invalid/非零，不能依赖 GC。磁盘仅序列化元数据，不写 Python handle。测试不能用外部 handles 强引用替被测代码持有资源；用 weakref/GC 检查实际归属，另测一次 close 失败后恢复与持续失败，以及另一端清理继续。
2. **四个最终读回都归入持久化失败收尾**：case.json、case_receipt.json、batch.json、batch_receipt.json 的真实读取/JSON 解码异常须在首次与修正阶段受到保护。直接调用不出现未解释的读回异常逃逸；返回 invalid/非零、persist error 与独立 stderr，适用时后例 not_executed。可写时将 case/receipt 或 batch/receipt 修正成失败结果；无法安全提交/读回时明确磁盘只是最近成功快照、原成功回执不能作为最终有效结果。归类不能落为 outer_exception/primary 而漏掉 persist。用真实 read_text 调用处的 OSError/JSONDecodeError 注入验证瞬时失败与持续失败，不以 post_hook 延迟冒充读回错误。不能吞错、无穷修正或绕过绝对期限。
3. **batch receipt 首次写失败后码一致**：单个正确 A1，首次 batch_receipt 提交抛 OSError，下一次恢复。最终返回应为 BATCH_PERSIST，磁盘 batch.json 和可写最终 receipt 同码且不能 verified=true/exit_code=0。须在修正提交前确定失败码，保留原错误。再覆盖修正提交/回执也失败：返回仍非零、明确 stderr 说明磁盘旧版本；不得以重试成功擦掉本次失败事实。不用先失败的 B 例掩盖 3/0/0 反例。

逐项检查实际启动数、运行时 owner、所有错误分类、磁盘 JSON/回执/stderr、批返回/后例状态；批级最终收尾发生在执行完案例后，不伪造“后例未执行”，只在 case 阶段失败时要求停后例。保留正常 A/B、事件失败完整端点、after_init 失败/超期 0 启动、rc=7、库身份、expected_binary、未知 variant、有效零接收 failure、42/82 s 慢回执/真正慢读回的已通过回归。完整结束跨度须覆盖必要收尾；I/O 不可抢占，如实限定。

### 预算、证据、封存与停止

首次核对即记录配对 epoch/monotonic、实际模型，CURRENT 设执行中。全程 **25 min**（含核对/等待/报告/封存），最多 **2 次完整离线测试命令**，不靠局部运行/collect-only 增加次数。先读静态路径和 R8 反例，设计能捕获它们的断言后统一运行；最多一次修复复跑。最后一次验证后改 candidate/test/conftest 则必须标未重新验证，不能宣称精确交付已通过。

保留 R8 的收集前阻断，在候选导入/收集前覆盖 subprocess/Popen、system/shell、posix_spawn/fork/exec、ctypes 绕过；不启动 helper 验证 guard。每次测试分别使用不可覆盖的 `guard_run1.json`/`guard_run2.json` 和各自拦截日志/原始输出，计数先记再抛、不能重置或吞掉，任一次拦截即停止/回报阻塞，不能报纯离线通过。Python/pytest/归档工具自身允许，不是被测子进程。

新报告 `report/offline_rework.md` 写清三个反例修复前后、代码/测试位置、真实命令/退出码/次数、每跑 guard、0 被测真实进程、起止配对时间（验证结束与交接结束分开）、baseline 差异、未覆盖限制。未扫描 processes 就写未采集；不补历史 PID/首轮 guard/时钟，不重跑旧轮。时间用 monotonic 差算预算，墙钟差不等时分列，不编造原因。

完成修复及精确验证后，报告定稿、日志关闭，首次新建 `experiments/_archive/ros2-diagnostics/20261027-p3-r9.tar`；先读通用归档工具用法，不用 --force，取回核验；归档摘要/全轮结束配对时间追加交接 report，不能为补时间回改封存输入。预算不足、范围不符、真实被测启动/guard 拦截或无法闭合即停止/如实回报，不追加第三跑、不删日志/降断言。CURRENT 设待审查/阻塞，交回 Codex；不提交/推送/切分支/重置/清理，不自动恢复 ROS/ABBA/工程。原任务不结档，通信根因及工程验收继续阻塞，gate/headless/P1/P2 结论不变。

<a id="round10"></a>
## 第 10 轮：把未释放资源交给批调用者

任务 `20261026-002-w8-measurement-p3`，第 10 轮，2026-10-27（Asia/Shanghai）。仅闭合 [R9 独立审查](review.md#round9-evidence) 的一个阻断：直接 run_case 有 owner，但 run_batch 丢弃 owner，GC 后实际失败 handle 消失。R9 读回异常与 batch 失败码修复保留；不再重复开发已通过项。R1–R9 不可重领；本轮 **0 ROS/通信/被测真实进程/helper/工程/仿真 attempts**。

### 依据、基线与白名单

按入口恢复 [spec](../../../.trae/specs/w8-measurement-p3/spec.md#round10-offline-rework)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round10)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round10)。实施前对照 Python 3.12 `/usr/lib/python3.12/contextlib.py` L484 `pop_all` 的实际容器转交/返回 owner、`ExitStack.__exit__` 的独立释放；SHA256 `8b7a477f978a8532852fd81e241c78182516bc4975d672d580a5848a76e11eb6`。采用其归属转交原则即可，不要求引入 ExitStack。既有 subprocess 绝对剩余时间、EvidenceSink 临时发布做法不变；不读 reference/、不引入依赖或框架。

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290`，分支 `main`，保留既有 dirty/untracked。领取/结束逐项重算 `experiments/ros2-diagnostics/20261027-p3-r10/config/codex_dispatch_baseline.json`，SHA256 与路径数见 CURRENT；保护此前 819 路径加 R9 全部 13 输入/manifest、tar 与两侧车。四个交接文件除外，不是全文件系统覆盖；未知变化停止，结束仅允许 P3 tasks/checklist 本轮事实追加。

只可复制 R9 candidate/test/conftest 到新根 `experiments/ros2-diagnostics/20261027-p3-r10/{scripts,tests}` 做局部修改，并新增本根 config/log/report，Codex baseline 不改。允许追加 task/report、更新 CURRENT、P3 tasks/checklist 第 10 轮事实。禁止改 request/review/spec/Runbook/AGENTS、共享脚本/工程/R1–R9 根/旧归档与侧车。允许新建本轮 tar/两侧车，不用 --force。临时路径 `/tmp/agc-p3-r10-*`，禁写证据根 pyc。不 source ROS、不扫描真实环境、不开发 live adapter。

### 实现及可判定验收

1. 实际仍未关闭的失败 Popen handle 必须从 case 运行时 owner 转交到 **run_batch 调用者可达的 owner**；可返回 runtime 字段或明确使用调用者提供的 owner，选择最小改动并文档化。返回 summary/code 后、局部 result/traceback 不再可达且 GC 已执行时，仍有明确的 owner 持有实际 handle。不能只复制元数据、依靠测试/adapter 的外部强引用、全局容器或 GC 析构。保持有界 close 重试、错误与 invalid/非零，成功释放则清空实际 handle。
2. runtime owner 与磁盘数据分离。所有 case/batch JSON 提交（包括首次/修正/回执）只序列化元数据；不能把 handle/owner 直接交给 json.dumps 而引入新的 persist 失败。磁盘保留失败端标识/未释放状态，返回 owner 与记录相符；原成功路径与失败码不倒退。
3. 新测试必须调用真实 **run_batch 核心路径**，仅 FakeAdapter/FakeHandle/FakeClock。覆盖 listener 第一次 Popen 失败+持续 close 失败、talker 第二次 Popen 失败+持续 close 失败（listener 仍完成独立回收/关闭），以及一次 close 失败后恢复。log_open 只在创建时登记 weakref，不在夹具/adapter/闭包/异常对象保留 handle 强引用；GC 后断言持续失败 handle 非空且与调用者 owner 相同，恢复后 owner 释放。持续失败批返回非零、后例 not_executed，读取盘面与回执确认失败结果且无序列化错误。原直接 case weakref 回归保留。
4. 保留 R9 的全部 52 项和读回/回执失败码、42/82 s 慢返回、启动前门禁、身份/variant、消息分类等回归。先静态对照本次反例并设计断言，再统一验证；不扩大诊断矩阵或重写编排。批最终收尾不伪造已执行案例为未执行。

### 预算、证据与停止

首次核对即记录配对 epoch/monotonic 和实际模型、CURRENT 设执行中。领取至交接结束 **25 min**（含核对/报告/封存/等待）；最多 **2 次完整离线测试命令**，不通过局部测试/collect-only 增加次数。最后验证后修改 candidate/test/conftest 须如实标记未验证，不追加第三跑。每次导入/收集前安装 R9 同等真实启动 guard，独立 `guard_run1.json`/`guard_run2.json` 与各自原始日志/intercepts 文件；计数不能重置/覆盖/吞掉。任一次拦截或真实被测启动立即停止并回报，不用 helper 验证 guard。Python/pytest/归档工具自身允许。

`report/offline_rework.md` 记录调用链归属改动、三种批路径的 weakref/GC 与端点/盘面结果、实际命令/次数/退出码、每跑 guard、最终文件指纹、配对时钟、baseline 差异和未覆盖限制。不采集真实进程就写未采集；不补历史 guard/PID/时钟。epoch 与 mono 差分列，预算用 mono。同步 I/O 不可抢占，保持有界收尾。

报告定稿/日志关闭后，先读通用归档工具用法，首次新建 `experiments/_archive/ros2-diagnostics/20261027-p3-r10.tar` 并取回核验；不 --force、不回改已封存输入。摘要与完整交接结束配对时间追加交接 report，CURRENT 待审查/阻塞后交回。预算耗尽、范围不符或无法闭合立即停；不提交/推送/切分支/重置/清理、不自动恢复 ROS/ABBA/工程。通信根因未知，P3 原工程继续阻塞，gate/headless/P1/P2 不变，原任务不结档。

<a id="round11"></a>
## 第 11 轮：真实运行适配候选，仅离线实施与验证

任务 `20261026-002-w8-measurement-p3`，第 **11** 轮，2026-10-27（Asia/Shanghai）。这是 R10 离线验收后的**新实施阶段**，不是继续返工已通过 owner 分支。唯一当前授权为本节；R1–R10 不可重领。目标是在新根将预检、系统快照及日志解析接到已通过核心上，交回可审查的运行适配候选。**本轮不启动真实运行：0 ROS/通信/被测真实进程/真实 helper/工程/仿真 attempts；CLI 即使带 --authorize-ros-run 仍须拒绝。**

### 依据与已学习做法

按入口顺序读 [spec](../../../.trae/specs/w8-measurement-p3/spec.md#round11-adapter)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round11)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round11)、[R10 审查](review.md#round10-evidence) 及 [R4 离线分析](../../../experiments/ros2-diagnostics/20261026-p3-r4/report/offline_comparison.md#references)。R10 核心/55 项回归为项目内已经验证的参照；不再重写生命周期。R4 脚本只作字段/缺陷对照，不继承吞错为空、简单 stat.split、双关闭等做法，不运行它。

实施前实际阅读本机官方手册 `/usr/share/man/man5/proc_pid_{stat,maps,environ,cmdline,status}.5.gz`（gzip 解压读取不是运行实验），记录文件 SHA256 与吸收点。Codex 已核实 stat 的括号 comm、field 22 starttime，maps 的多段映射/pathname，以及 environ/cmdline 的 NUL 分隔和可观测限制；stat/maps/environ 压缩文件 SHA256 分别 `7f52df6374c8ad43bc6f348f0f831dfc22c710b45aed9fb04d06eaf992ad1d80` / `1d4b340b1e90680d6378c42be225bb37e593d104c8315f36919e48de7d9d7422` / `288c0256ed5c5a8bce9cc3c2be224db43484eb39fe55ba6d495a1ab6570991f7`。对照 Python 3.12 pathlib.readlink/resolve、subprocess._remaining_time 和 start_new_session 语义。沿用 R4 sources/index.json 的 demo 0.33.11 / Fast DDS 2.14.7 / Jazzy 官方配置快照；本轮不下载、不引入依赖、不读 reference/。

### 基线、白名单与产物

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290`，分支 `main`；保留全部既有 dirty/untracked。接单/结束逐项重算：
`experiments/ros2-diagnostics/20261027-p3-r11/config/codex_dispatch_baseline.json`，
**851 路径**，SHA256 **`90d8b99504f19d074ef6017db53dab2ddd60706e6203563a8c86d3452bdb42d7`**。保护原 835 路径及 R10 全部 13 文件、tar/两侧车；四个可变交接文件除外，不是全文件系统覆盖。结束只允许 P3 tasks/checklist 本轮事实更新，其余未知变化停止，不改基线掩盖。

唯一新增根 `experiments/ros2-diagnostics/20261027-p3-r11/`：
- 复制 R10 `scripts/runner_candidate.py`、`tests/test_runner_candidate.py`、`tests/conftest.py` 到同名路径；核心原则上保持，只允许适配接线所必需的小改，逐处说明。既有 55 项不能删除/弱化。
- 新增 `scripts/runtime_adapter.py`、`tests/test_runtime_adapter.py`、`tests/fixtures/`（明确标注 synthetic 或原始来源，禁止伪作实测）、新的 config/log/report；Codex 基线只读。允许局部必要辅助函数，不造新 runner/插件/泛化框架。
- 允许追加 task/report、更新 CURRENT、P3 tasks/checklist 的 R11 事实。禁止写 request/review/spec/Runbook/AGENTS、工程/共享 scripts、旧证据/manifest/tar/侧车。
- 临时路径 `/tmp/agc-p3-r11-*`；可首次新建 `experiments/_archive/ros2-diagnostics/20261027-p3-r11.tar` 及两侧车。禁止 --force 或回改封存输入。禁写证据根 pyc/pytest cache。

**不 source ROS、不扫描活动 /proc、端口/进程或真实运行环境、不调用 ldd/ss/ps/ros2 等系统命令，不 bind/socket 探测，不发信号。** 允许读取指定本地文档、既有证据/日志、受保护文件做指纹；所有采集器验证只针对隔离文件夹具/注入读接口。未来真实采集所需代码可实现，本轮不调用真实后端。Python/pytest/归档工具自身允许。

### 必须交付及验收

1. **小型适配层与明确入口。** 无副作用导入；提供真实 clock、preflight/snapshot/message provider 及调用原 run_batch 的接线函数。文件读取/readlink/身份/时钟接口可用最少依赖注入，生产逻辑与夹具走相同解析路径；不能把现成 make_snap/messages_for 字典直接返回后称适配通过。默认参数不能在导入时读系统。本轮两个 CLI 入口（如新增 main）都先拒绝真实运行，授权开关也不能触发采集/启动；未来启用需新派工。接线必须把 runtime resource_owner 原样交给调用者，不能整份 summary 再 JSON 序列化。
2. **完整预检、失败明确。** 从读接口形成核心 validate_preflight 所需全部字段，并保存明细来源/采集错误：目标 work_dir（不是 runner 自己 cwd）、目录项/XML、UID/四类 ns、相关 demo/daemon 清单、domain 39 端口扫描范围与结果、profiles/必要配置、固定二进制和必需库 path/hash、最初 claim 时间/预算/执行范围。清单仅在扫描完整且确实为空时为空；权限错误、格式坏、无法确定为空必须拒绝，不能复制 R4 的 processes=null/domain_ports=null 或伪填 []。进程/端口扫描实现只读、无工具子进程；domain 39 保守检查 UDP/UDP6 的 17150–17399 区间并记录此范围，不声称扫描等于长期独占。库预期来自明确配置和读取的文件身份，不能从待校验快照倒填。预检不合格时 0 启动，不创建/覆盖已有 attempt。固定二进制路径同 R10，历史 SHA 只读引用 R4 派工；不随夹具/活动值自动改 pin。未来工作目录/ROS_HOME 用新轮路径，不沿用 R6 的默认旧目录。
3. **快照忠实且完整。** 按核心字段生成 PID/PGID、stat（ppid/pgrp/session/starttime_ticks）、exe 与 SHA、cwd、UID、net/ipc/mnt/user、NUL cmdline、允许列表内环境和 maps 原始相关行/去重文件 path/hash。stat 正确处理 comm 中空格和括号；同一库多段映射去重，不把两个不同路径同 basename 合并。不可读、删除库、缺库、错 hash/path、PID 消失或采集前后 starttime 改变必须保留错误并导致 invalid；不能伪装为可比快照。只处理传入的自有端点 PID；不采集整机无关环境/凭据。environ 标注为 exec 时可观测环境，不夸称进程任意后续修改也可见。最终 source 后环境由端点快照核对，不为“证明 source”额外启动探针进程。
4. **最终日志解析与来源。** 读取已关闭的本例 listener/talker console 及本例 ROS 日志，不越过 case 根、跟随链接读取外部或混入其他 case。按官方 Publishing/I heard 格式提取唯一编号；console/ROS 重复不重复计数，timestamp 必须来自匹配接收行，0 接收 first_heard 为 null。未知接收编号继续由核心拒绝；缺必需日志、读取错误/明显损坏与真实“完整日志但零接收”区分。日志本身未给 topic 时，标明 topic 来自本例已记录的命令 remap，不声称从日志直接观测 topic。已有 classify_messages 是唯一分类逻辑，不另写阈值。最终文件 bytes/hash 与读取内容一致，不能提前对仍写日志定稿。
5. **核心接线验证。** 用原始格式文件夹具、FakeClock/FakeAdapter 验证 A1→B1→B2→A2 有效路径：预检由生产采集器形成，端点 snapshots 由生产解析器读取，消息由最终日志解析形成；两端环境/库一致、A/B 唯一 transport 差、实际核心分类/磁盘/回执一致。夹具时钟给足明确总预算，不能改生产截止规则。覆盖至少：预检扫描失败/冲突 0 启动；snapshot 缺库/权限错误导致 invalid/非零并清理/停止后例；解析零接收/部分/重复/未知编号/缺日志；stat 复杂 comm 与多段 maps；R10 owner 转交回归。断言实际返回/磁盘/端点清理，不只断言 helper 调用。范围内成功与失败至少各一条完整接线，禁止真实被测进程。
6. **回归与结论限定。** 保留 R10 全 55 项，新增测试聚焦上述适配行为；不无关扫测、不改配置/放宽核心来迁就夹具。报告区分已实现、文件夹具证明、未来真实运行尚未证明；本轮通过也不证明 ROS 通信恢复、传输根因或原工程通过。

### 预算、回报与停止

首次基线核对起记录配对 epoch_ns/monotonic_ns、实际模型和 CURRENT 执行中；**领取到交接结束 35 min**，包括阅读/实现/等待/测试/报告/归档。最多 **2 次完整离线测试命令**，每次包含本轮全部两个 test 文件；不以局部测试/collect-only/额外脚本测试扩大次数。静态审读/编译不启动 helper；不另跑旧轮测试。最终一次验证后改变 candidate/adapter/tests/guard 必须标未验证，不能追加第三跑。

在任一候选/适配器导入、测试收集前安装 R10 同等 guard；每跑独立 guard_run1/2.json、原始日志及 intercepts，不覆盖/清零/吞错。允许测试注入 FakeAdapter/文件读取，**不允许把真实启动 API 解封**；不用 helper 验 guard。任一次拦截/真实启动立即停止回报，不消耗第二跑继续。guard 局限与同步 I/O 不可抢占如实记录。

在 `report/offline_adapter.md` 说明来源/接口/必需小改、夹具来源、成功与失败接线结果、全部测试命令/次数/退出码、每跑 guard、精确文件 hash、基线前后差异、配对时间、未覆盖的真实运行限制。不采集真实进程就明确写未采集，不补历史 PID/guard/时钟。报告/日志定稿关闭后按通用归档工具用法首次封存/取回；输出放根外，不用 --force。最终归档摘要与完整交接结束配对时间写封存外 task/report；CURRENT 待审查或阻塞。

缺关键前置、预算不足、未知保护变化、需扩大核心改动/权限/安装或无法满足验收则停止并具体回报，允许部分交付，不临时换设计试跑。无 commit/push/merge/reset/clean/切分支，无共享资源清理/停他人进程。**原 P3 工程继续阻塞、通信根因未知；gate/headless/P1/P2 不变，任务不结档。** 审查通过后由 Codex 另派真实通信预算，本轮不执行下一步。

<a id="round12"></a>
## 第 12 轮：预检、固定 pin 与日志证据定点返工（仅离线）

任务 `20261026-002-w8-measurement-p3`，第 **12** 轮，2026-10-27（Asia/Shanghai），Codex 派发、Trae / DeepSeek 实施。只执行本节，旧轮不可重领。R11 部分交付成立、整轮未验收，具体反例见 [独立审查](review.md#round11-evidence)。R10 资源归属修复已通过，不重开该返工。目标是修复适配层把无效证据当有效结果的问题；**0 ROS/通信/真实被测进程/真实 helper/工程/仿真 attempts**，两个 CLI 包括旧授权开关继续拒绝真实运行。

### 依据、学习与基线

按共同入口顺序、角色与交接规则，读 [Runbook](../../../docs/ROS2迁移步骤.md#status)、[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round12-adapter-rework)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round12)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round12)，逐项对照 R11 独立反例。先实际学习本机 proc_net/proc_pid 官方手册的 UDP 表头/记录格式；沿用 R11 proc 手册与 R4 已封存同版本官方快照，不下载。日志格式对照 R4 `log/A1/talker.console.log` 及 `log/A1/ros_log/`，其 logger 含 namespace 与 talker；读取 R11 核心实际记录的 endpoints.cmd / namespace / topic，按其事实校验日志，不凭空规定官方未输出的结束标记。以 R10/R11 EvidenceSink 的元数据提交方式做最少接线，不重写生命周期；在新报告记录实际来源与吸收点。

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，既有 dirty/untracked 全部保留。新根 `experiments/ros2-diagnostics/20261027-p3-r12/`，领取时仅有 Codex 基线 `config/codex_dispatch_baseline.json`：**878 路径，SHA256 `24da978400660e85fc3d08f769c95836e5b5b444d3c33d08b6fc89be04d10877`**。包含此前 851 路径及 R11 全部 24 文件、tar/两侧车；四个可变交接文件除外，不是全文件系统覆盖。领取/结束逐项重算；结束仅允许 tasks/checklist 的本轮事实变化，其他未知变化停止，不改基线掩盖。

### 白名单与边界

只从 R11 复制 candidate、runtime_adapter、两个 test 文件、conftest 与明确 synthetic 的 fixtures 到新根 `scripts/`、`tests/`，并在本根新增 config/log/report。保留原 79 项；可以为明确的预期 pin、生产 argv、日志来源契约更新夹具/新增断言，不能删除或弱化回归以迁就失败。核心优先保持，仅允许为传入已记录命令/保存解析来源元数据所必需的局部接线，逐处列出；实际 owner 不得进入 JSON，R10 归属/释放语义不改。

允许追加 task/report、更新 CURRENT、在 P3 tasks/checklist R12 段追加事实/勾选；禁止改 request/review/spec/Runbook/AGENTS、工程/共享 scripts、旧证据/归档/侧车和本轮 Codex 基线。临时输出 `/tmp/agc-p3-r12-*`；只允许首次新建 `experiments/_archive/ros2-diagnostics/20261027-p3-r12.tar` 与两侧车，不用 --force，不改封存输入。PYTHONDONTWRITEBYTECODE=1，不向证据根写 pyc/cache。

**不 source ROS、不扫描活动 /proc/真实端口/进程/环境，不运行 ldd/ss/ps/ros2 等工具、不 bind/socket 探测、不发真实信号**。指定文档/历史证据及受保护文件哈希可读；采集器只能读取隔离的原始文件夹具/注入读接口。Python/完整 pytest/通用归档工具自身允许，不启动 helper 验证 guard，不另建通用框架。

### 必须修复与验收

1. **端口表完整性。** 两份 UDP/UDP6 必须独立识别合法表头和记录；零字节、缺/坏表头、截断或格式坏不得返回“扫描完整、busy=[]”。无表头首行 port `4300`（17152）必须拒绝，不能跳过。合法仅表头确无记录可为空；正确处理有效空表、有效区外记录、17150/17399 边界及区内占用。空/坏/冲突经实际接线应在 0 launches、无 attempt 时拒绝。记录协议、扫描范围/结果和明确错误；不要求新工具或持锁。
2. **固定二进制期望独立。** 默认固定路径和历史 SHA 只读引用 [R4 派工](#round4)：listener `/opt/ros/jazzy/lib/demo_nodes_cpp/listener` SHA `f9c3d9c26887c516bedc7f4b2f4c108769047ecf3c9624a0a0d7a536d959ae2e`；talker 同目录/talker SHA `63c40ad0122424603a37a50adffbbb14a9a36ffedbae40e07b67012f558cf533`。expected 不得取自本次 observed/preflight/snapshot。合成测试可显式注入独立的受信期望配置，标注 synthetic；生产默认 pin 不随注入后端读值变化。缺/错期望、固定路径上 bytes 变化、预检后 snapshot 身份变化均拒绝；前置错 pin 0 launches/无 attempt，后置错身份 invalid/非零并清理停批。库预期继续来自明确配置和独立文件读取。
3. **日志有效性与归属。** listener/talker console 与本例 ROS 日志必须来自已关闭文件并识别真实格式；两份 listener 全部为 `TRUNCATED AND CORRUPT` 要 invalid/非零并停后例，不能作有效 failure。允许真实格式的零接收（如合法 rclcpp 信号行）及完全空的接收输出：空文件本身不证明损坏，必须结合所需文件集、所属端点/实际命令/进程收尾事实，明确为何可判完整；不要发明官方结束标记。缺必需日志/不可读/NUL/坏编码/畸形消息行继续拒绝。按已记录端点命令的 namespace/节点角色校验命中行，不把 `agc_r6_OTHER_OTHER` 或 listener 日志内伪 talker 发布当作当前结果；不能单纯为所有事件补当前 topic 以通过分类。topic/namespace 从本例实际记录的 remap 取得并交叉核对，不依赖硬编码 case 拼接；topic_source 明示 command_remap。保留唯一编号、重复去重、匹配接收行首时刻、未知 ID 拒绝、真实零接收 first=null；分类只用原 classify_messages。
4. **最终来源可追溯。** parser 返回的相对日志路径/角色、bytes/hash、topic_source、所依据命令/remap 要在实际 run_batch 返回及最终 case 证据中保留（可用专用已提交 JSON 并由 case 引用，或 case 内少量字段），不能只在临时 provider 返回后丢弃。JSON 只含元数据，最终读回/回执一致，实际 runtime owner 原样返回。路径限本例、不跟随越界链接、不混入其他 case；hash/bytes 对应关闭后的最终文件。必要小改沿用 EvidenceSink 异常/预算/提交语义，不添加无界 I/O 重试或绕过收尾。
5. **原始夹具集成与回归。** 保留 79 项并新增上述反例，至少一条完整有效 ABBA、端口/pin 前置失败 0 launches/无 attempt、损坏/其他 case 日志失败 invalid/非零/清理/停后例；断言实际返回、盘面、回执、来源字段与最终日志哈希。保留缺库/权限失败、未知 ID、stat/maps、CLI 拒绝及 R10 weakref/GC owner 回归。夹具仍走生产采集/解析，不直接注入预期 snapshot/messages；FakeClock 给足明确总预算，不改 deadline/阈值。本轮新 work_dir/ROS_HOME 用 R12 路径。

### 预算、证据与停止

从首次基线核对/领取到交接结束 **35 min**，包含阅读/实现/等待/测试/报告/归档，起止保存配对 epoch_ns/monotonic_ns，分列差值。最多 **2 次完整离线测试命令**，每次同时包含全部两个 test 文件；不跑局部/collect-only/额外脚本验证绕过次数，不另跑旧轮测试。任何候选导入/收集前安装 R10/R11 同等 guard；每跑独立 guard_run1/2.json、原始日志和 intercepts，不覆盖或清零；任一拦截/真实启动立即停止，不能继续第二跑。最终验证后 candidate/adapter/tests/guard 有改动必须标未验证，不能第三跑。

`report/offline_adapter_rework.md` 列来源、逐项反例修复/未完成、核心小改、全部命令/退出码/次数、每跑 guard、精确指纹、基线前后差异与配对时间、真实运行未证明事项。更正进度文字的历史计数错误：R11 实数 851→849+2，不回改 R11 封存报告或旧回报。报告/日志关闭后首建归档并取回核验；归档摘要和完整交接结束配对时间写封存外 task/report，CURRENT 待审查或阻塞。禁止为赶验收补造历史证据。

缺关键参照、保护路径未知变化、预算不足、需扩大白名单/权限/安装/真实实验即停止并具体回报；允许部分交付，不自行试跑替代方案。不 commit/push/merge/reset/clean/切分支，不清理共享资源或停他人进程。**原 P3 工程继续阻塞、通信根因未知，gate/headless/P1/P2 不变，任务不结档；本轮不启动下一轮。**

<a id="round13"></a>
## 第 13 轮：UDP/UDP6 表头与记录格式收口（仅离线）

任务 `20261026-002-w8-measurement-p3`，第 **13** 轮，2026-10-27（Asia/Shanghai），Codex 派发、Trae / DeepSeek 实施。只执行本节，旧轮授权失效。R12 部分通过、整轮未验收，反例见 [审查](review.md#round12-evidence)。本轮只修端口表有效性并更正新报告中的历史时间算术；R12 pin/日志/来源及 R10 owner 不重开。**0 ROS/通信/活动扫描/被测真实进程/真实 helper/工程/仿真 attempts**，两个 CLI 即使带旧授权开关也继续拒绝真实运行。

### 依据与基线

按共同入口/角色/交接协议读 [Runbook](../../../docs/ROS2迁移步骤.md#status)、[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round13-udp-rework)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round13)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round13)。先实际学习本机 proc_net 官方手册及既有同版本格式来源，按协议解释 UDP/UDP6 的表头列和地址/端口表示，在报告列明来源与吸收点。不能以 R12 合成夹具当官方格式依据，尤其不能因 UDP6 夹具照搬 UDP 就假设两者完全相同；有效表头拼写与可选尾字段须依据来源明确记录。缺必要来源则停止回报，不下载/安装或读活动 /proc 来替代。本轮不造通用框架，不读 reference/ 或复制旧树。

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main`，保留既有 dirty/untracked。新根 `experiments/ros2-diagnostics/20261027-p3-r13/`，领取时仅有 Codex 基线 `config/codex_dispatch_baseline.json`：**902 路径，SHA256 `5c4decf796ae7bb9ed25e6b5795d316870847c8980de98e59a07cc4985f3679a`**。保护此前 878 路径及 R12 全部 21 文件、tar/两侧车；四个可变交接文件除外，不是全文件系统覆盖。领取/结束逐项重算；结束仅 tasks/checklist 本轮事实允许变化，其余未知变化停止，不更新基线掩盖。

### 白名单

从 R12 复制 candidate/adapter、两个 test 文件、conftest 和 synthetic fixtures 到 R13 的 scripts/tests；本根新增 config/log/report。**runner_candidate.py、test_runner_candidate.py、conftest.py 必须与 R12 逐字节相同**。runtime_adapter.py 仅改 UDP 表解析/必要错误信息和本轮新 work_dir/ROS_HOME；test_runtime_adapter.py/fixtures 可补格式反例、修正有官方依据的协议夹具及本轮路径，不删除/弱化原 94 项。pin、日志解析/来源、owner、deadline、分类阈值、核心生命周期不改。若需要白名单外改动，停止交回。

允许追加 task/report、更新 CURRENT、在 tasks/checklist R13 段写事实/勾选；禁止改 request/review/spec/Runbook/AGENTS、工程/共享脚本、旧证据/归档/侧车、Codex 基线。临时文件 `/tmp/agc-p3-r13-*`。只首次新建 `experiments/_archive/ros2-diagnostics/20261027-p3-r13.tar` 及两侧车，不用 --force，不改封存输入；禁止 pyc/cache 写入证据根。

不得 source ROS、读活动 /proc/进程/端口/环境、运行 ldd/ss/ps/ros2、socket/bind 探测或发真实信号。采集器仅读隔离原始文件夹具/注入读接口；指定文档/历史证据及保护路径哈希可读。Python/完整 pytest/通用归档工具自身允许，真实 helper 0，不启动子进程测试 guard。

### 实施与验收

1. **表头完整列结构。** 两协议各自验证实际支持的合法列名/顺序，不用三个子串 all-in 判断。仅含 `local_address rem_address st` 三个词及末尾换行的残缺表头，在 udp、udp6 必须独立拒绝；缺列、错序、重复列、用包含关键子串的非列名替代也拒绝。记录所支持的真实表头差异，保留合理空白和有依据的内核尾列兼容；不能通过限制成合成夹具特有格式拒绝真实合法表。合法仅表头可判完整空表，零字节/缺头/坏表仍拒绝。
2. **记录字段按协议校验。** local/remote IPv4 地址完整 8 位 hex，IPv6 地址完整 32 位 hex；两端 port 均恰为 4 位 hex（16-bit）。坏字段、超长/截短/非 hex、截断记录拒绝，不能变成扫描完整的区外记录。保留其余已有必需字段校验和有依据尾字段；不另造网络探测。至少复现 R12 行 `0: F:10000 F:0 07 00000000:00000000 00:00000000 0 1000 0 1`，并分别隔离 local/remote 地址、端口错误测试，避免仅一个正则分支掩盖其他缺口。
3. **实际生产接线。** 上述 UDP/UDP6 残缺表头和各协议坏字段代表反例通过 run_runtime_batch，在 **0 fake launches、无 attempt** 时明确 PreflightError/RunnerError。合法两协议仅表头、完整区外记录、17150/17399 边界和区内占用保持；保留一条完整有效 ABBA，核对返回/盘面/回执/来源 bytes/hash/已回收事实。只读原始文件，经 collect_preflight/snapshot_process/parse_final_logs/核心，不直接注入预期快照或消息。
4. **回归与精确交付。** 保留全部 94 项含 owner weakref/GC、pin、日志/来源回归；guard 在候选导入/收集前安装，每跑独立记录。核心及 guard 不改，允许适配测试增加新断言或有依据修正夹具。报告逐处列明 adapter 差异，最终完整验证后改候选/测试/guard 必须标未验证，不得第三跑。
5. **纠正时间与完整性。** 新报告明确 R12 claim epoch `1793072155878662171`→handoff `1793072984358802420`，差 **828.480140249 s**；mono `12649481583932`→`13407783075526`，差 **758.301491594 s**。旧报 928.480140249 s 多算 100 s，不更改任何旧回报/封存。新轮起止配对 epoch_ns/monotonic_ns，分别用整数差计算、分列；验证结束如另记时刻同样保留配对原值，不补造。

### 预算、证据、停止

首次基线核对/领取至完整交接结束 **25 min**，含学习/实施/等待/测试/报告/封存。最多 **2 次完整离线命令**，每次同时运行 `tests/test_runner_candidate.py tests/test_runtime_adapter.py` 全集；不跑局部/collect-only/额外验证脚本绕过预算，不另跑旧轮测试。使用 `PYTHONDONTWRITEBYTECODE=1`、`python3 -B -m pytest -p no:cacheprovider`；沿用 guard 的 `AGC_R8_GUARD_REPORT` 指向本轮独立 log/guard_run1.json、guard_run2.json，原始 stdout/stderr 分别保存，不覆盖或清零。每次记录完整命令/退出码/用时/最终指纹，沿用 R9 标签可如实说明。任何 guard 拦截/真实被测启动立即停止，不能继续第二跑。

`report/udp_format_rework.md` 记录来源、每项输入/修复前后结果、代码/测试定位、未完成限制、全部测试命令/次数/退出码、每跑 guard、精确 SHA、前后基线、原始配对时钟/重算值与 R12 更正。日志关闭/报告定稿后仅首次归档并取回核验；归档摘要与完整交接结束配对时钟写封存外 task/report。CURRENT 置待审查或阻塞，禁止自行进入下一轮。

缺必要参照/未知保护变化/预算不足/需要扩大范围或真实运行即停止并具体回报。允许部分交付，不补造历史、不 commit/push/merge/reset/clean/切分支、不清理共享资源或停他人进程。原 P3 工程继续阻塞、通信根因未知，gate/headless/P1/P2 不变，任务不结档。


<a id="round14"></a>
## 第 14 轮：真实运行入口准备与离线验证

任务 20261026-002-w8-measurement-p3，第 **14** 轮，2026-10-27（Asia/Shanghai），Codex 派发、Trae / DeepSeek 实施。R13 既定端口格式离线修复已验收，见 [审查](review.md#round13-evidence)。本轮完成后续真实运行所需入口，**只离线实现/验证，不执行真实授权 CLI、不启动 ROS 或活动扫描**。不重开 UDP/core/pin/日志/owner 返工，不恢复 R4 旧预算；原工程任务不结档。

### 依据、学习与基线

按共同入口/角色/协议读 [Runbook](../../../docs/ROS2迁移步骤.md#status)、[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round14-entry)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round14)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round14)。先实读 R13 runtime_adapter.py 的 main/run_runtime_batch/collect_preflight、核心 SystemProcAdapter/_base_env/run_batch/exclusive_dir 与现有 ABBA 文件夹具；学习本机 Python 3.12 argparse 的 parse_args、main/__name__ 模式和 pathlib 独占创建，不下载。既有解析协议不重新设计；官方内核补证见本轮 config/sources/index.json 和五份只读快照，不复制为工程代码。沿用 R4 ROS 2 Jazzy/Fast DDS 同版本来源。新报告列实际来源/定位及吸收点；Nav2 无新增组件，不读 reference/或复制旧树，不造框架。

HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290 / main，保留既有 dirty/untracked（包括 AGENTS 既有差异）。新根 experiments/ros2-diagnostics/20261027-p3-r14/，领取时只有 Codex 基线和只读来源：config/codex_dispatch_baseline.json，**932 路径，SHA256 151066330f948c331bf8413271ab23d30e40dc36f61e5cfd22aee61cf0cfeebe**。保护此前 902 路径、R13 全部 21 文件、tar/两侧车、本轮 6 个来源文件；四个可变交接文件除外，不是全文件系统覆盖。Codex 审查前重算 R13 基线仅 tasks/checklist 改变，随后由 Codex 明确更新 Runbook/spec/tasks/checklist，四项新字节均纳入 R14 基线。领取/结束逐项重算，仅 tasks/checklist 的本轮事实更新允许变化，其他未知变化停止，不改基线掩盖。

### 白名单与边界

从 R13 复制 scripts/runner_candidate.py、runtime_adapter.py、tests/test_runner_candidate.py、test_runtime_adapter.py、conftest.py 及必要 synthetic 夹具到 R14 新根；本根可新增 config/log/report。**核心、核心测试、conftest 必须与 R13 逐字节相同**；保留全部 115 项，不删/弱化回归。adapter 只改入口编排、延迟依赖构造、必要 Python 测试注入 seam 及本轮配置路径；UDP/pin/日志解析/来源/快照与 run_runtime_batch 既有语义不改。入口复用现有核心/adapter，不另写调度/收尾/分类逻辑。新增入口测试放现有 test_runtime_adapter.py；既有测试仅为明确路径/入口契约修正断言，guard 不改。

可追加 task/report、更新 CURRENT、在 tasks/checklist R14 段写事实/勾选；不改 request/review/spec/Runbook/AGENTS、工程/共享脚本、旧证据/归档/侧车、Codex 基线/本轮来源。临时文件 /tmp/agc-p3-r14-*。只首次新建 experiments/_archive/ros2-diagnostics/20261027-p3-r14.tar 与两侧车，不用 --force、不改封存输入；不写 pyc/cache。

**ROS/通信/活动 /proc 或真实端口/进程/环境扫描/被测真实进程/helper/工程/构建/仿真均为 0**；不 source ROS、不运行 ldd/ss/ps/ros2、不 socket/bind、不发真实信号。本轮不得以实际 shell 执行 adapter 的 --authorize-ros-run，即使认为只做预检也不允许。Python/完整 pytest/通用归档工具自身允许；入口验证只在当前 pytest 进程调用 main、注入原始文件/假依赖，不用子进程测 CLI/guard。

### 实施与验收

1. **先校验再构造。** main 保留 --authorize-ros-run 为显式门；缺授权返回非零，且无扫描/系统依赖构造/启动/attempt。必要 out-root、attempt-id 参数与合法值在构造前校验；拒绝缺参、未知参数、不安全 attempt-id（不能逃出输出根）、已有 attempt/冲突私有目录，不覆盖历史数据。导入和 --help 不执行系统采集/构造/启动。可提供输出根/单次标识参数，不把 synthetic pin、proc-root、任意 plan/config/二进制路径作为生产 CLI 开关。核心 CLI 保持拒绝。

2. **最小实际接线。** 有效授权路径延迟构造 RuntimeClock、SystemBackend、核心 SystemProcAdapter，调用原 run_runtime_batch；固定 underlay-only、domain 39/LOCALHOST、默认 stock 二进制/可信 SHA、ABBA、原时序/端口范围。入口传明示 runtime execution_scope、有限预算（沿用 600 s，不扩大）；调用者环境只读取既有 profiles 检查白名单，不整份保存环境/凭据；子进程仍走 _base_env 和 underlay source 后快照核对。准备本轮专用 work_dir/ROS_HOME，独占新建，不清理旧目录或停他人进程；离线测试可显式注入私有路径。不因 work_dir 尚未创建使预检必然失败；后续真实运行输出不能写入本轮已封存证据根。拒绝/异常非零，已有批返回码原样交回，不吞异常变成功，保留实际 owner 归属语义。配对时钟如实标覆盖起点：现有核心预算从 collect_preflight 起算，不虚称含全部入口同步 I/O 或可抢占阻塞。

3. **入口级实际调用链，离线替身。** 可用 main 的 Python-only keyword seam/依赖工厂注入假 clock/adapter/backend、proc-root、synthetic 独立可信 pin/私有配置，生产 CLI 无此覆盖；默认分支实际连到系统依赖/固定默认 pin。测试不能只 mock run_runtime_batch：至少一条 main→run_runtime_batch→生产采集/快照/最终解析→实际核心完整 ABBA，使用原始 proc/log 文件夹具和假进程，核对返回/盘面、case+batch receipt、来源 bytes/hash/topic_source、四例顺序及全部回收。另用入口核实坏预检 0 launches/无 attempt、缺库或日志损坏等运行中 invalid 非零/清理/停止后例。导入/无授权/缺参/非法参数用可计数或故障工厂证明无提前构造/扫描/启动；已有 attempt 不覆盖。argparse 可按惯例抛 SystemExit，测试捕获核对码。默认生产配置选择可用 spy factory 检查，但不能替代完整集成路径。

4. **有限回归。** 原 115 项含 owner weakref/GC、UDP/pin/日志/来源保留；新增仅聚焦入口拒绝、固定接线与代表成功/失败，不重测系统现场，不改生产阈值迁就夹具。guard 在导入/收集前保持有效，任何真实启动/拦截立即停止。若需要改核心/guard/已验收解析语义，停止交回 Codex，不临时扩大方案。

### 预算、证据与停止

首次基线核对/领取至完整交接结束 **25 min**，包含学习/实现/等待/测试/报告/封存。最多 **2 次完整离线测试命令**，每次同时运行全部 tests/test_runner_candidate.py tests/test_runtime_adapter.py；不跑局部/collect-only/额外验证脚本绕过次数，不另跑旧轮测试。使用 PYTHONDONTWRITEBYTECODE=1、python3 -B -m pytest -p no:cacheprovider；沿用 AGC_R8_GUARD_REPORT 分别输出 log/guard_run1.json、guard_run2.json，原始 stdout/stderr 独立保存，不覆盖/清零/吞错，旧 R9 标签如实说明。任何 guard 拦截/真实被测启动立即停止，不继续第二跑。最后完整验证后改候选/测试/guard 必须标未验证，不追加第三跑。

report/runtime_entry.md 写实际来源、各入口契约/实现定位、生产默认与 synthetic 边界、成功/失败接线、全部命令/次数/退出码、每跑 guard、精确文件 SHA、领取/结束基线差异及真实运行未证明事项。首次领取与完整交接结束均保存配对 epoch_ns/monotonic_ns、整数差分列；不以验证结束代替交接结束、不补造历史。报告/日志关闭后首建归档并取回核验；归档摘要/完整交接结束配对时间写封存外 task/report，CURRENT 置待审查或阻塞。

缺必要来源/未知保护变化/预算不足/需白名单外改动、安装/权限或真实运行即停止并具体回报，允许部分交付。不 commit/push/merge/reset/clean/切分支、不清理共享资源/停他人进程。**实现能力不构成实际运行授权；入口独立审查通过后另派真实官方 demo 通信预算。原 P3 工程/设计继续阻塞、通信根因未知，gate/headless/P1/P2 不变，任务不结档，不自行开始下一轮。**

<a id="round15"></a>
## 第 15 轮：入口修复与完整离线验证

任务 `20261026-002-w8-measurement-p3`，第 **15** 轮，2026-10-27（Asia/Shanghai），Codex 派发、**DSH（dsh）**实施。R14 独立裁定见 [审查](review.md#round14-evidence)：不验收、不追认真实运行。保留 R13 已通过部分，补齐入口，不重做工程或通信实验。**实现有真实运行能力，本轮执行授权仍为零。**

### 依据、学习与保护基线

按共同入口/角色/协议读 [Runbook](../../../docs/ROS2迁移步骤.md#status)、[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round15-entry-rework)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round15)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round15)。先读 R13 已验证的核心 run_batch/owner 与 R14 入口差异、现有文件夹具/FakeClock/LoggingAdapter/conftest；Python 3.12 argparse/pathlib 独占创建仍是入口参照。生产库依据为新根 `config/sources/library_identity.json`（Codex 独立只读文件身份），R14 两份原始快照仅作为违规现场旁证。R14 的手动冒烟不构成可复用成功验证。既有内核/ROS 同版本来源只读沿用；报告写实际定位与吸收点，无新增组件/框架，不读 reference/或复制旧树，不下载依赖。

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main，既有 dirty/untracked 保留。新根 `experiments/ros2-diagnostics/20261027-p3-r15/`；领取时只有 Codex 基线及一份库身份来源。基线 `config/codex_dispatch_baseline.json`：**961 路径，SHA256 06e65e82cf68b022ae0963787622ac3ea72f4af6cb40948e8badc58704820279**。保护 R14 原有 932 路径、R14 全部 34 文件（6 个来源原已计入）及本轮新来源；四个可变交接文件除外，不是全文件系统覆盖。旧基线四份协调文档及后续根 override/Runbook 用法行更名已由 Codex 审读接受；Codex 随后/同期更新 Runbook/spec/tasks/checklist，最终相对 R14 共 9 路径变化，逐项写在新基线，历史指纹不改。领取/结束重算所有保护路径，仅 tasks/checklist 本轮段事实允许改变；其他未知变化立即停止，不更新基线掩盖。

### 修改白名单与执行边界

从 R14 向 R15 复制 scripts/runner_candidate.py、runtime_adapter.py、tests/test_runner_candidate.py、test_runtime_adapter.py、conftest.py 和原 synthetic 夹具。**core、核心测试、conftest 与 R13/R14 逐字节相同**，原 115 项全部保留。只改本轮 runtime_adapter.py 的入口编排/工厂/私有路径/固定配置，以及现有 test_runtime_adapter.py 的入口测试；UDP/pin 解析/快照/日志/来源/run_runtime_batch/核心生命周期/期限不改。允许改固定 required_libs.fastrtps 的 path/basename，以精确 canonical 身份修正默认配置；不增加模糊匹配、动态自认 pin 或新的采集器。

本根可新增 config/log/report（Codex 的基线和来源只读）；可追加 task/report、更新 CURRENT、在 tasks/checklist R15 段写事实/勾选。不得改 request/review/spec/Runbook/AGENTS/角色规则、共享工程/脚本、R1–R14 证据/归档/侧车。临时文件限 `/tmp/agc-p3-r15-*`；不触碰 R14 专用 /tmp 或 `/dev/shm`，不清理任何共享资源。仅首次新建本轮 tar/两侧车，命令限定 `python3 -B scripts/evidence_archive.py --campaign ros2-diagnostics --run-id 20261027-p3-r15`（项目根运行），禁止 --force/全 campaign 归档/改旧输入。

**ROS、通信、source ROS、活动 /proc/环境/真实端口/进程扫描、真实被测进程、helper、信号、socket/bind、工程、构建、仿真均为 0。** 不运行 ldd/ps/ss/ros2。**禁止在 shell/临时脚本直接导入候选或调用 main/run_entry，也禁止“只做预检”的实际 --authorize-ros-run。** 候选导入和所有行为验证仅在下述完整 pytest 命令的当前进程内、收集前 guard 已安装、显式假依赖注入条件下进行；不以 subprocess 测 CLI/guard，不直接调用测试函数。纯文本/AST 阅读、文件 hash/清单/配对时钟、通用归档工具自身允许，不能借此执行候选或绕过测试次数。生产工厂的固定选择用 monkeypatch/spy 的假系统类核对，不能真实构造/采集/启动。

### 实施与可判定验收

1. **修固定配置和来源接线。** 默认 fastrtps 固定 `/opt/ros/jazzy/lib/libfastrtps.so.2.14.7` / `libfastrtps.so.2.14.7`；保留既有独立文件读 hash 与精确 path/hash 校验，文件依据 SHA 为 `2b80489f57d87ce4832766371c5e9f4b0c6b035dc850b284b9f6afcad4962929`，不从 maps/observed 自动生成 expected。二进制 pin 值不变；默认工厂向既有 run_runtime_batch 保留 trusted_binary=None，来源为 r4_dispatch_pin，显式 Python 夹具注入仍标 synthetic_injection；不改 run_runtime_batch 来源判定。R15 专用私有路径。保持 domain 39/LOCALHOST、underlay-only、stock 二进制、ABBA/原时序/端口范围、600 s 和 execution_scope 的固定选择；生产 CLI 不开放 synthetic pin/proc-root/plan/config/二进制覆盖。

2. **完成已有入口契约。** 导入、--help、无授权、缺参/未知参数/非法 attempt-id/无效输出根、已有 attempt 或冲突私有目录，均非运行路径：无系统依赖构造/扫描/启动/attempt，不覆盖旧数据；--help 可按 argparse 返回 0。参数拒绝在构造前；路径解析后不能逃出根。生产输出拒绝写入既有封存证据、本轮证据根及 `_archive`（含软链别名）；离线 fixture 输出放独立测试临时根。私有 work/ROS_HOME 独占创建，核心独占创建 attempt；若准备部分失败，报告已创建的专用路径，不删历史/共享目录。拒绝/异常非零、批返回码原样交回，错误消息不能虚称任何运行中异常都发生在启动之前。核心 CLI 继续拒绝。

3. **入口层不丢 owner。** run_entry 继续直接返回核心 summary；main 对 runtime-only owner 有明确接收/保留方，不能仅返回整数后丢弃最后强引用。采用最小入口级持有/转交方式，说明默认入口和 Python 调用者各自归属及后续显式释放方式；不序列化 owner/handle、不改核心收尾/调度、不靠 __del__ 或自动清场隐藏问题。至少一条 main 经过真实批核心、假 Popen 失败+句柄持续 close 失败的路径，返回/GC 后 weakref 非空且等于 owner 实际句柄，恢复后可释放。批/盘面/回执非零一致，后例不启动。

4. **补齐入口级集成。** 保留 115 项；新增入口拒绝/碰撞/默认配置选择及代表成功/失败。至少一条 main→run_entry→实际 run_runtime_batch→生产 preflight/snapshot/final-log parser→实际核心完整 ABBA：只用原始 proc/log 文件夹具、假时钟/假进程、显式 synthetic 独立 pin；不能只 mock run_runtime_batch、替换消息或快照结论。核对四例顺序、返回/盘面、case+batch receipt hash/状态、message_source bytes/hash/topic_source、全部回收。入口坏预检 0 launches/无 attempt；运行中缺库或日志损坏 invalid/非零、清理、后例 not_executed。导入/--help/无授权/非法参数和碰撞用可计数/故障工厂证明无提前构造/扫描/启动。默认配置工厂用假系统类 spy 检查精确库名、固定 pin 来源与预算；不代表真实系统运行通过。

5. **范围不扩张。** R13 UDP 与已有 pin/日志/来源/owner/期限核心回归保留；本轮只修入口丢 owner，不能据此重开核心。必要变更若超出 adapter 入口/固定配置与测试，停下交回 Codex。guard 拦截或任何真实动作立即停止，不继续测试/修复/封存来争取通过，保存事件和现有日志并回报。

### 预算、原始证据与交接

首次基线核对/领取至最初完整技术交接结束 **35 min**，包括学习/实现/等待/测试/报告/封存；不把验证结束当交接结束。最多 **2 次完整离线测试命令**，每次同时运行 tests/test_runner_candidate.py 和 tests/test_runtime_adapter.py；不跑局部/collect-only/额外验证脚本/手动 main。命令使用 `PYTHONDONTWRITEBYTECODE=1 AGC_R8_GUARD_REPORT=<本轮绝对 log/guard_runN.json> python3 -B -m pytest -p no:cacheprovider <本轮两个测试文件>`，每跑完整 stdout/stderr、退出码独立保存 log/pytest_runN.log，不覆盖首跑；原 conftest 在候选导入/收集前安装。旧 R8/R9 标签如实说明；count=0、collected 与实数相符、write_errors=[] 才是有效 guard。最后完整验证后改候选/测试/guard 必须标未验证，不准第三跑。

`report/runtime_entry_rework.md` 写实际来源/实现定位、各契约证据、固定配置/默认与 synthetic 来源边界、owner 接收与释放、所有行为命令/次数/退出码、每跑 guard、精确最终 SHA、领取/结束基线差异及未证明事项。完整技术交接起止均保存配对 epoch_ns/monotonic_ns，整数差分列；以 monotonic 算持续时间，不用墙钟漂移冒充实际超时。预算覆盖边界如实说明：核心从 collect_preflight 起算，不包含此前全部同步 I/O，不保证可抢占。文件/日志关闭后首次归档与跨路径取回核验；归档摘要和技术交接结束样本写封存外 task/report。其后若有协调附记，另记样本，**不得覆写已保存的 baseline_end/guard 或原始结束记录**。

缺来源/未知保护变化/时间不足/需白名单外实现/权限安装或任何真实动作均停止，部分交付如实报。R14 原件全部保护、仍未封存，本轮不补造/补写或归档 R14，不清 /tmp/shm、不 kill。无 commit/push/merge/reset/clean/切分支，不自行开始下一轮。完成将 CURRENT 置待审查或阻塞；**入口独立验收后才另派真实官方 demo 新预算。原 P3 工程/设计继续阻塞，通信根因未知，gate/headless/P1/P2 不变，任务不结档。**

<a id="round16"></a>
## 第 16 轮：入口 owner 两处定点修复（允许自主离线排障）

任务 `20261026-002-w8-measurement-p3`，第 **16** 轮，2026-10-27（Asia/Shanghai），Codex 派发、DSH 实施。R15 **部分通过、入口整体未验收**，见 [审查](review.md#round15-evidence)。本轮只闭合持续关闭失败的显式释放与跨 main 调用 owner 归属，已通过配置/pin/UDP/日志/来源/ABBA 保留。用户要求适度提高 DSH 自主性，本轮按 [日常自主权限](../../README.md#executor-autonomy) 自主安排局部诊断、修复、重跑，不再限制为两次全套。真实执行预算仍为零。

### 依据、学习与基线

按共同开工顺序及 DSH 角色读取 [Runbook](../../../docs/ROS2迁移步骤.md#status)、[spec](../../../.trae/specs/w8-measurement-p3/spec.md#round16-entry-owner)、[tasks](../../../.trae/specs/w8-measurement-p3/tasks.md#round16)、[checklist](../../../.trae/specs/w8-measurement-p3/checklist.md#round16)。先学已通过的核心 `release_owner_handle`/`close_log` 错误容器、R10 资源归属及现有 FakeHandle/weakref/GC 夹具。独立反例脚本和观察在新根 `config/sources/codex_r15_review.{py,json}`，只读作为诊断来源，不把它另跑成未记录行为验证。无新增框架/组件，Nav2 无新增吸收点，不读 reference/、不复制旧树、不下载依赖。

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main，已有 dirty/untracked 保留。新根 `experiments/ros2-diagnostics/20261027-p3-r16/`，领取时仅 Codex 的基线与两份审查来源。基线 `config/codex_dispatch_baseline.json`：**988 路径，SHA256 7287975cc11cc1df246318a89e1444445a8e5a76319f85fe8d6bd7090b774aaf**。继承 R15 的 961 路径，补齐 R15 全根当前字节、tar/两侧车与本轮两份来源；四个可变交接文件不保护，不是全文件系统覆盖。Codex 本次协议/角色自主权限和 Runbook/spec/tasks/checklist 改动逐项登记在新基线，旧指纹不改。领取/结束核对全部路径；仅 tasks/checklist 的 R16 事实更新允许变化，其他未知变化停止，不能更新基线掩盖。

### 修改与执行权限

从 R15 复制 scripts、tests 及原 synthetic fixtures 到新根；**runner_candidate.py、test_runner_candidate.py、conftest.py 保持 R13/R15 逐字节相同，原 146 项保留**。只改本轮 runtime_adapter.py 的 EntryResult/main 归属与释放、必要私有路径/轮次说明，以及 test_runtime_adapter.py 的相关测试/夹具；可在本轮 tests 下增加小型专用测试/夹具。入口范围内的实现选择、同根因相邻修复、局部重构与测试夹具修正自行决定，不必等待 Codex；UDP/pin/日志解析/采集器/run_runtime_batch/核心生命周期/期限不改。CLI 与固定生产 pin、canonical 库、ABBA、domain39/LOCALHOST、underlay-only、600s 均保留。

本根可新增 config/log/report，Codex 基线与 sources 只读。可追加 task/report、更新 CURRENT、在 tasks/checklist R16 段更新事实。request/review/协议/角色/spec/Runbook/AGENTS、工程/共享脚本、R1–R15 所有证据/归档/侧车不得修改。临时目录限 `/tmp/agc-p3-r16-*`；pytest tmp 根也用该前缀并为每跑独占新目录，不触碰旧轮 /tmp 或 /dev/shm、不清共享资源。

**不启动 ROS/通信、真实被测进程/helper、活动 /proc/环境/端口/进程扫描、socket/bind、真实信号、构建/工程/仿真；不 source ROS、不运行 ldd/ps/ss/ros2。** 保留此隔离是因为本轮验收只需要假资源，且 R14 曾实际越界；它不限制正常编辑和带 guard 的局部测试。候选导入/行为诊断在 pytest 当前进程内进行，沿用 conftest 收集前 guard 和显式假依赖；可跑 `-k`/指定测试，无须批准。不在 shell 直接导入/冒烟候选、不绕过 guard、不调用现有测试函数。不安装依赖或调整系统。纯文本/AST/语法检查、hash/清单/配对时钟、归档工具允许；语法检查不得向只读旧根产生 pyc。

### 可判定验收（实现方案由 DSH 选择）

1. **显式释放失败也正常返回。** 入口适配 `rc.release_owner_handle` 既有错误容器，保留现有 release 结果字段或清楚说明最小兼容变化。保持假句柄 close 持续失败时，调用有限 attempts 的释放不抛 TypeError/KeyError，返回错误及准确 remaining；后续资源仍尝试处理，未释放 handle 留在 owner，返回/GC 后 weakref 可达。flush 失败也正常记错、不妨碍其它 close。实际计数证明有界；恢复后可 released/remaining=0。用实际 main→批核心、假 Popen 失败的 owner 路径证明，不只人工构造 EntryResult。盘面/回执非零且后例不启动，owner/handle 仍 runtime-only。
2. **跨 main 不丢未释放归属。** 同进程第一次 main 产生持续失败 owner，不由测试另外持有 result/handle 强引用，第二次 main 之后 GC 旧句柄仍可达。可以选择：存在 pending 时在创建路径/工厂/launch 前拒绝新批且保持旧 result，显式释放后再允许；或保留可枚举的多个未释放 owner 并能全部后续释放。不得无条件覆盖唯一 last，不隐式关闭/丢弃 pending。拒绝方案证明第二调用 0 工厂/0 launches/无新私有路径/无 attempt；保留方案证明旧、新 owner 均可枚举且可释放。参数/--help/拒绝也不能清掉原 owner。
3. **测试接线与既有回归。** 修正原 main_refusals 测试，确实传入可计数/故障工厂。原 146 项全保留；相关断言可随归属方案加强，不能删 owner 覆盖或伪造成功。保留实际入口 ABBA/文件采集解析/回执与来源校验、前置拒绝/运行中 invalid 等完整回归。新测试覆盖上述真实缺口，有意义即可，不追求数量。核心/核心测试/guard SHA 不变。
4. **逐次留痕与最终验证。** 每次全套/局部使用唯一 runNN 编号和独占 stdout/stderr、exit-code、guard 文件，记录命令/选择项/起止。`PYTHONDONTWRITEBYTECODE=1 AGC_R8_GUARD_REPORT=<本轮绝对log/guard_runNN.json> python3 -B -m pytest -p no:cacheprovider --basetemp=/tmp/agc-p3-r16-pytest-runNN <测试文件/可选-k>`。保留失败记录；最终完整回归运行本轮 tests/（包括两个保留文件及新增测试），不带 -k，guard count=0、collected 与日志相符、write_errors=[]。旧 R8/R9 标签如实保留。guard 触发立刻停止报告，不继续争取通过。最终验证后若改受测代码，预算内可再验，无次数障碍；来不及则明确未验证。

### 总预算、封存与停止

从首次基线核对/领取至完整技术交接 **45 min**，包括学习/修复/局部与全套/报告/封存。时间内自主决定离线命令次数；遇失败先读根因和参照，避免无证据重复。源报告定稿后首次新建归档，仅用 `python3 -B scripts/evidence_archive.py --campaign ros2-diagnostics --run-id 20261027-p3-r16`，不得 --force/重打包旧轮。日志/源报告/manifest 封存后不再改，归档后纠错写 task/report 的新附记；若缺封存则如实部分交付，不能补造。

报告 `report/entry_owner_rework.md` 写实际来源、选定 owner 策略、两个反例与恢复证据、命令序列/各退出码/guard、最终 SHA、基线差异及限制。领取、验证结束、源报告定稿时各保存唯一配对 epoch_ns/monotonic_ns；最后完整技术交接结束配对样本和归档摘要写封存外 task/report。归档前的基线样本命名 `baseline_before_archive.json`，不冒充最终结束；交接结束另存外部记录，不覆盖任何样本。时差用整数重算、mono/epoch 分列，明确同步 I/O 不可抢占等既有限制。R15 原始日志缺失/样本重建/报告与 tar 不同的结论只引用审查，不修补旧证据。

需白名单外改动/更改规格或验收/增加真实动作、缺来源、未知保护变化、guard 触发、时间不足即保留现场并回报；可部分交付。无 commit/push/merge/reset/clean/切分支，不动他人进程/共享资源。完成置待审查，阻塞置阻塞，不自行验收或开始下一轮。**入口独立验收后才另派真实官方 demo 新预算；原 P3 工程/设计阻塞，通信根因未知，gate/headless/P1/P2 不变，任务不结档。**

<a id="round17"></a>
## 第 17 轮：flush 错误后的 owner 注册表收敛

R16 独立审查发现：`EntryResult.release_failed_resources()` 在 `flush()` 抛错而 `close()` 成功时返回 `released=1/remaining=0`，但因 `errors['cleanup']` 非空跳过 `_forget()`，已完成结果残留在 `EntryResult.owners`。本轮只修该入口缺陷。

### 范围与白名单

- 只允许修改 `experiments/ros2-diagnostics/20261027-p3-r16/scripts/runtime_adapter.py`、`experiments/ros2-diagnostics/20261027-p3-r16/tests/test_runtime_adapter.py`，以及本轮新增 `experiments/ros2-diagnostics/20261027-p3-r17/` 证据根。
- 不改 `runner_candidate.py`、核心测试、既有 R16/R15 证据、归档、工程、ROS 或共享资源；不启动真实进程、ROS、活动扫描、构建或仿真。
- 当 `pending_failed_resources()==[]` 时，无论 cleanup 错误列表是否为空，均注销 owner；flush 错误仍原样返回，不能吞错。

### 验收

- flush 失败/close 成功路径断言 `released=1`、`remaining=0`、错误保留且 `EntryResult.pending_results()==[]`；`release_all()` 后注册表为空。
- 保留持续 close 失败、跨 main owner、拒绝路径、ABBA 与原 150 项回归；最终完整测试、独立 guard/日志、基线/指纹与新归档取回可复核。
- 真实运行预算为零；完成后 CURRENT 置待审查，未通过则如实返工或阻塞。
