<a id="round9"></a>
# W8 验证恢复 · 第9轮：endpoint 标记与受控启动顺序

任务 ID：20261027-001-w8-validation-recovery；轮次9；2026-10-28；来源：Leader，依据用户本次明确授权。第8轮[独立审查](../round-8/review.md#round8-review)通过，domain配置分支关闭；本轮新增独立小型诊断探针，旧探针和历史证据不改。

## 入口、学习与目标

遵循 [Runbook](../../../../docs/ROS2迁移步骤.md#usage)、[规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round9)、[任务](../../../../.trae/specs/w8-validation-recovery/tasks.md#round9)、[验收](../../../../.trae/specs/w8-validation-recovery/checklist.md#round9)、[观测分级](../../../README.md#run-tiers)及[契约](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。

先读已验收第3轮 probe_layered.py 的同进程正负控制及本机 Jazzy rclpy init/Node/create_publisher/create_subscription 实现，再新增独立探针；允许吸收同类实现，不另造框架。必须记录所读来源、版本与 SHA。新增 post_init、node_created、endpoint_created 事件，均紧邻相应 API 成功返回之后写出并 flush；endpoint 标记含 attempt唯一ID、PID、role、topic、QoS及配对 wall/monotonic。init 返回不等于participant已完成发现，endpoint_created只说明创建API已返回，不叫DDS就绪。

目的：区分旧脚本启动标记之前的初始化时序与 endpoint 创建后的发现/匹配/消费形态；无权直接宣称工程恢复。

## 预授权与步骤

显式 **T1: 3次**，每次从首个被测进程启动到全部回收≤30s，累计≤90s，每次最多2个ROS participant（驱动不建立participant）、普通用户，独占 `/tmp/agc-w8-validation-r9-*`。整轮领取至交接≤45min monotonic。无额外重跑预算；有效失败不重跑；无效/异常/必要证据缺失立即停止余下步骤。禁止构建、抓包、仿真、GZ/PX4/GUI/headless、额外observer/daemon、读取/dev/shm、共享资源清理、系统/网络/库/时钟改动。

固定继承第8轮：domain0、LOCALHOST、RELIABLE depth10、std_msgs/String，env -i，仅source /opt/ros/jazzy；不设FASTDDS_BUILTIN_TRANSPORTS/ROS_STATIC_PEERS/RMW_IMPLEMENTATION/LD_PRELOAD/profiles；ROS_HOME/ROS_LOG_DIR独占。跨进程沿用 topic `/agc_probe_domain0/chatter`，同进程负控制用本轮独立topic。

1. **A 同进程控制，一次T1**：一个Node依次正控制（同topic、RELIABLE/RELIABLE）、QoS负控制（BEST_EFFORT pub/RELIABLE sub）、不同topic负控制；可沿用3s+2s+2s观测。各endpoint都有创建返回标记。正控制必须双侧匹配且heard>0；QoS负控制必须heard=0、matched=0并观察incompatible QoS；不同topic必须heard=0、matched=0。标记顺序/身份/事件与实际创建及消费一致。任何一项不符即停止，不归因整体环境。
2. **B pub-first，一次T1**：pub创建endpoint后运行8s，sub运行6s。驱动读取本次先启动方完整 endpoint_created JSON，校验attempt/PID/role/topic且其前有post_init/node_created，记录观察时钟，成功后立即启动sub，不额外固定sleep。
3. **C sub-first，一次T1**：sub创建endpoint后运行8s，pub运行6s，门控同B。仅A通过且B完整有效后执行。后启动方必须在先启动方endpoint_created之后；必须有足够共同运行窗口，记录实际重叠，不以probe_start替代。标记等待设有限超时并纳入30s预算；超时/先方退出/破损身份记invalid并停止，不fallback。

允许新根内实现小驱动及必要纯离线校验；离线测试不得启动ROS或偷消耗T1。用独立PGID、真实wait RC与result/probe_end互证，正常自行结束；超时仅回收本单自有PID并保留信号记录，不能触碰他人进程。

## 判读与证据

- A不满足预期：探针/控制未验证，B/C未执行；不得据此判环境整体失效。
- B/C双向graph/matched且heard>0：仅本次endpoint门控下通信成立，初始化时序成为候选解释；新旧探针存在实现差异，不宣称唯一根因或恢复S2。
- B/C仍随先启动者翻转的单向匹配且零消费：形态在endpoint API返回门控后仍存在，未定位根因；关闭仅以脚本启动过早解释的简单假设，不声称DDS已完全就绪。
- 双向匹配但零消费、方向不翻转、部分成功或无效分别据实报告；峰值与退出后final分开，不追加样本或换配置。

逐次保留完整命令/输出/事件/result、运行探针与驱动的最终SHA、PID/PGID/starttime、环境/实际库版本、配对时钟、所有标记及门控观察/后方启动时钟、graph/matched/incompatible QoS/heard、真实退出码、信号及残留。记录API调用前后耗时可帮助分解初始化阶段，但不引入额外进程。报告原始值与推断分开。

## 基线、白名单与封存

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main，保留全部dirty/untracked，不reset/clean/commit/push/切分支。

新根 `experiments/w8-validation/20261028-endpoint-ready-probe-r1/`，可新增 scripts/config/log/report，预置 `config/codex_dispatch_baseline.json` 与 `baseline_receipt.json` 只读。Leader派工前冻结第8轮保护集、当前链/规格/历史证据与归档的超集；领取逐项核对实际条目数/size/SHA/absent，未知漂移立即停止。历史旧探针以及所有封存源根只读。

额外可写：本轮report、CURRENT，及tasks/checklist中round9执行勾选；后两文件的预期勾选差异必须交回。禁止改spec/request/review/Runbook/契约/src/scripts/toolchain/build/install和其他协调文档。实现只能落本轮新根。

定稿后用现有 scripts/evidence_archive.py 首次封存，不用--force；stdout写/tmp。独立核对manifest条目size/SHA、tar真实根、checksum/retrieval及源根逐文件一致；封存后不写源根，更正/结束时钟只写本轮report或_archive侧车。

完成或阻塞后更新本轮report和CURRENT，send_message通知Leader后结束，不轮询、不接下一单。S2/S3/S4未开放，整链不归档；gate/headless/P1/P2/W7-c/W8-E2状态不变。
