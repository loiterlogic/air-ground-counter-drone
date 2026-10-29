<a id="round17"></a>
# 第17轮：历史 stock 阳性复现、受控 domain 对照与同域探针检查

任务 ID 20261027-001-w8-validation-recovery；轮次17；来源 Leader，2026-10-28。原 Worker `1ac7d798-9215-494f-a7e6-013518f7894d` 因父会话边界无法复用；**用户于2026-10-28明确授权当前Leader新建Worker接续同一任务链**，新子会话ID由Leader写入本轮report。

入口：[Runbook](../../../../docs/archive/ROS2迁移步骤.md#usage)、[本轮规格](../../../../docs/archive/specs/w8-validation-recovery/spec.md#round17)、[第16轮审查](../round-16/review.md#round16-review)、[自主权限](../../../README.md#executor-autonomy)、[观测分级](../../../README.md#run-tiers)、[硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。先读第14/15/16轮完整回报、审查及原始证据，不摘取支持单一假设的片段。

## 1. 目标与不再重复的分支

历史 `experiments/ros2-diagnostics/20261026-p3-r2/` 的 stock 有5例阳性（domain37/LOCALHOST/构造11键）；第16轮 stock 两例阴性为 domain0、clean/继承环境。先消除这个受控比较缺口，再决定是否值得扩写 endpoint-info 工具。

本轮回答：
1. 历史 stock 阳性能否在其 domain37 条件下复现；
2. 同一直接 `exec` 驱动、同一 clean-env、同一 topic/时序下，仅改 domain0 是否仍为阴性；
3. 若 stock 阳性成立，既有 endpoint 探针在同一 domain37 下是否仍呈单向 graph/matched 与零消费，还是也恢复。

不重新扫描 domain，不换传输/peer 配置，不新造 DDS 框架。第15轮 endpoint-info 扩展本轮不执行。

## 2. 已学习的同版本实现与历史锚点

- 第16轮已验收直接 `exec` 官方 `/opt/ros/jazzy/lib/demo_nodes_cpp/{listener,talker}` 驱动：真实 RC、环境、库映射、回收及原文日志均可得，复用该驱动，不改项目代码。
- 历史 `p3-r2/log/cases.json`：stock 阳性 domain37/LOCALHOST，listener先起2s、talker约6s，构造11键。第16轮报告已核实它并非继承环境。
- 第14轮已验收既有 endpoint 探针在 domain0 的双向顺序形态；其代码、驱动和门控只读复用，不重做离线驱动返工。
- 官方 stock 作为系统行为锚点，自写探针只作为条件 C 的对照，不用探针异常替代 stock 判据。

## 3. 预算与边界

- 整轮 **45 min monotonic**；显式 **T1: 3次**，每次起被测进程至全回收≤30s，累计≤90s，每次最多2个ROS participant；普通用户；独占 `/tmp/agc-w8-validation-r17-*`。
- 允许官方 stock 和已验收 rclpy endpoint 探针/驱动；禁止构建、GZ/PX4/GUI/headless/全链、抓包、读 `/dev/shm` 内容、共享资源清理、系统/网络/库/时钟改变、root、常驻 daemon/observer。
- 每例条件不满足、invalid、关键原件缺失或回收异常即停止后例，不追加预算、不换配置重试。有效结果不重跑。
- 开跑前只读核对既有 demo/探针/daemon 冲突；不得终止他人进程。

## 4. 三次 T1（顺序与停止门）

固定除显式变量外：只 source `/opt/ros/jazzy/setup.bash`，不 source 项目 install；`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`；不设 RMW/LD_PRELOAD/profiles/builtin transports/static peers/ROS_LOCALHOST_ONLY；HOME=/home/chen；每例独立 ROS_HOME/ROS_LOG_DIR。stock 直接 `exec`，listener先起2s、talker运行6s，随后优雅回收两端；topic `/agc_r17/chatter`。

### A（T1 #1）：domain37 stock 历史阳性条件复现

使用第16轮直接 `exec` stock 驱动，clean-env 采用历史11键集合（HOME/LANG/LC_ALL/LOGNAME/PATH/ROS_AUTOMATIC_DISCOVERY_RANGE/ROS_DOMAIN_ID/ROS_HOME/ROS_LOG_DIR/SHELL/USER），`ROS_DOMAIN_ID=37`。记录真实环境；source 注入的库键与真实 maps 另列，不把它伪称为11键最终环境。

成功=listener自身 stdout/stderr 原文至少1条 `I heard: [Hello World: N]`。否则为有效阴性，不作缺日志/异常解释。

- A成功 → 执行B。
- A有效阴性 → **跳过B和C**，本轮结论为“历史阳性未复现，当前 stock 在37/0均失败”；停止，不把单次结果升级为永久环境损坏。

### B（T1 #2，条件执行）：domain0 stock 单变量对照

除 `ROS_DOMAIN_ID=0` 外，完整复用A的可执行文件、环境构造、topic、直接exec、时序与判据。其意义是只控制domain，不承担进程树/env对照。

判读：
- A阳性+B阴性：domain相关分支获得新实测支持，但不单凭一例宣称根因；继续C，优先检查同域既有探针。
- A/B均阳性：当前 stock 通信在0/37均可，支持“第16轮阴性具有时变性/未控因素”，不得称仅domain0故障；继续C。
- A/B均阴性或B invalid：停止C；保留证据，不扩写工具。

### C（T1 #3，条件执行）：同 domain37 既有探针 pub-first

仅在A阳性且B有效后执行。只读复用第14轮最终 probe/driver/gate，采用其 pub-first 参数、topic、QoS、endpoint_created 身份门控、run时长和clean-env语义，唯一显式变化为 `ROS_DOMAIN_ID=37`。不修改探针源码，不新增endpoint-info调用，不重跑同进程A或sub-first。

记录双端 graph/matched/heard、incompatible QoS、事件顺序、真实RC与回收。判读：
- stock37阳性而探针37仍单向/零消费：在相同domain下重新建立“stock可通信、既有探针失败”的分裂证据，下一轮才剖探针/endpoint观测。
- 探针37双向匹配且订阅 heard>0：探针并非持续失效；不能宣称工程恢复，下一轮先用受控重复和domain0同构对照区分时变与domain因素。
- 探针37双向发现但 heard=0：数据面/回调分支上升，下一轮做endpoint/QoS与数据面观测。
- C invalid：只报invalid，不解释为通信阴性。

## 5. 必存证据与交付

新根 `experiments/w8-validation/20261028-stock-domain37-control-r1/`，可新增 `config/cases/evidence/log/report/scripts`。复用第16轮 stock 驱动时先复制到新根scripts并记录来源SHA；除为本轮domain/11键/产物路径做明确参数化外不改变其控制语义。第14轮探针/driver/gate保持原路径只读，不复制改写。

每例保存完整argv、构造与实际环境、库maps、配对mono/wall、PID/PGID/starttime、真实wait RC、信号与回收、stdout/stderr/ROS日志原文、残留核对；stock保存talker发布原文与listener `I heard:` 原文。C另存完整事件/result/gate证据。记录跳过项及原因，不把跳过写成失败。

`report/analysis.md` 给逐例判据、A/B/C或跳过原因、相对第16轮新增的信息、仍未排除项；特别区分“历史阳性复现失败”与“domain0不可用”，不把C的探针结果等同stock结果。

定稿后首次封存，不 `--force`；独立核对manifest/tar真实根/checksum/retrieval及源根逐文件一致。封存后只写report和_archive侧车，不改源根。

## 6. 基线与写入白名单

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main，保留全部36项dirty/untracked，不reset/clean/commit/push/切分支。Leader在新根预置 baseline/receipt：保护新根之外全部现有文件；预期变化仅 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 的round17执行勾选，CURRENT、本轮report/review及第16轮review/Runbook/spec由Leader管理。

Worker只写新根、本轮report、CURRENT及上述round17执行勾选；禁止改src、项目scripts、toolchain、build/install、spec、Runbook、request、历史review、旧探针/驱动、历史源根/归档。不得写__pycache__，使用 `python3 -B`/AST。

## 7. 停止与交回

出现硬约束问题、未知保护漂移、guard拦截、进程/预算超限、需要共享资源或白名单外修改、关键证据缺失，立即停止并回报。结束时写report、更新CURRENT为待审查，send_message通知Leader后结束，不轮询、不接下一单。S2/S3/S4、gate/headless/科研不变，整链不归档。
