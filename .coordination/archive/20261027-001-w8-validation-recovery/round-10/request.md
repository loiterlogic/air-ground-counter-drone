<a id="round10"></a>
# 第10轮：诊断探针驱动离线返工

任务ID：20261027-001-w8-validation-recovery；轮次10；2026-10-28；来源Leader。复用Worker 55d8793e-4916-4045-ac19-5800e167ebfa。

入口：[Runbook](../../../../docs/ROS2迁移步骤.md#usage)、[规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round10)、[上轮独立审查](../round-9/review.md#round9-review)、[自主权限](../../../README.md#executor-autonomy)、[硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。沿用同链目标与原验收语义，不改变通信配置。

## 预算与白名单

整轮45min monotonic，**T1: 0次**。禁止ROS init/Node/participant/demo/observer/daemon/真实helper/构建/仿真/抓包/共享操作。本轮可运行纯假依赖/假进程，必须显式注入，测试入口不得落入真实ROS命令。先读本机已验证的历史runner超时回收实现和第9轮代码/离线自检，保留来源引用及SHA。

新根 `experiments/w8-validation/20261028-endpoint-driver-offline-r1/` 可新增scripts/config/log/report。允许吸收第9轮最终探针/门控/驱动，在新根保留来源路径及原SHA；第9轮与此前全部封存源只读。禁止改全局scripts/src/toolchain/build/install/旧证据/旧归档/规格/Runbook/request/review。额外仅本轮report与CURRENT可写。

HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290/main，保留既有dirty/untracked；Leader冻结的config/codex_dispatch_baseline.json与baseline_receipt.json只读，领取逐项核对，未知漂移停止。

## 必须交付

1. 保留第9轮event_name修复，纯离线覆盖真实Recorder写出、pub/sub创建返回标记调用与销毁/phase_end路径的参数兼容，不启动ROS；不要只测镜像函数或AST。
2. 驱动对A/B/C及门控失败所有路径统一monotonic截止时间、轮询/有限等待与自有PID/starttime回收，收尾留出余量，使“首方启动→全部回收”≤30s可执行。禁止无限wait；超时invalid且停止后例。仅信号本单自有PID，保留真实wait RC、信号、回收结束时钟和残留。计时涵盖snapshot/gate/reclaim，失败span不得在回收之前截断。
3. A/B/C统一完整保存stdout/stderr、PID/PGID/starttime、真实RC与result/probe_end/invalid一致性；缺失/冲突/非零探针RC/残留必须失败，不能仅因驱动exit0误判通过。完整回收状态可与无效诊断结果分开。
4. 门控通过后、第二方启动前再次检查先方自有PID/starttime存活；拒绝probe_end/已退出/身份变化，不fallback。保持endpoint事件身份/QoS/顺序校验，不增加固定sleep。
5. 纯假进程/假事件离线验证：A正常、A探针异常、A卡住超时、B/C正常门控、缺标记、错误身份、门控后先方退出、后方异常/卡住、结果/日志缺失或RC冲突、残留检测；用较短注入时限测试真实驱动路径和真实清理，不额外搭一个镜像runner。记录每次命令/起止/退出码/完整输出及假依赖边界。故障注入的预期失败不等于测试失败。明确生产默认入口拒绝未经授权的真实运行，后续授权由Leader另轮给出。

最终提交前完成指定离线回归；之后改受测代码须重验。准确区分运行SHA与最终SHA；不写估算时长冒充实测。wall/mono配对保存，偏移漂移如实报告但不改系统时钟、不假设原因。

定稿首次封存，新根只封一次、不--force；stdout写/tmp/agc-w8-validation-r10-*。核对manifest size/SHA、tar根、checksum/retrieval、源根逐文件一致；封存后仅本轮report/_archive侧车可追加更正。完成置待审查并send_message通知当前父Leader后结束，不轮询、不接下一单。

验收仅离线驱动/记录修复，不执行A/B/C真实通信、不恢复S2/S3/S4，不改变gate/headless/科研结论。若范围不足、未知漂移、guard、必要来源缺失或预算不足，停止回报。
