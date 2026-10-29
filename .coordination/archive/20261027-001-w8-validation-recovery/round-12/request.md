<a id="round12"></a>
# 第12轮：helper身份与回收证据离线收口

任务ID 20261027-001-w8-validation-recovery；轮次12；来源Leader，2026-10-28。复用Worker 55d8793e-4916-4045-ac19-5800e167ebfa。

入口：[Runbook](../../../../docs/archive/ROS2迁移步骤.md#usage)、[规格](../../../../docs/archive/specs/w8-validation-recovery/spec.md#round12)、[上轮审查](../round-11/review.md#round11-review)、[自主权限](../../../README.md#executor-autonomy)、[契约](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。先读审查与第11轮对应helper/信号/回收实现，从既有自有子进程snapshot方法吸收，不扩新框架。

预算45min monotonic，**T1: 0次**，0ROS init/Node/participant/真实helper/构建/仿真/抓包/共享资源操作。仅纯假进程/mock离线验证。任何动作前配对claim写本轮report，结束同样配对；既有dirty/untracked不动。

新根 experiments/w8-validation/20261028-endpoint-helper-offline-r1/ 可新增scripts/config/log/report/cases/evidence；只允许吸收第11轮最终代码并作以下定点修复，记录来源SHA。额外仅本轮report/CURRENT可写。旧封存源/归档只读，禁止改规格/Runbook/request/review/全局scripts/src/toolchain/build/install，不reset/clean/commit/push/切分支。

HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290/main；以Leader预置config baseline/receipt核对实际条目数/SHA/size，未知漂移停止。

## 必交付

1. send_signal缺失/非法expected starttime必须拒绝，即使read_stat取得当前身份；不能以当前观察值替代启动时身份。保留read_stat缺失、starttime变化拒绝。mock直接调用真实函数验证None/非法expected starttime时零kill/killpg。
2. helper启动即记录自有PID/PGID/starttime及配对时钟；捕获失败记invalid，不得盲发信号。helper超时与正常退出均保留真实RC、完整回收记录、stdout/stderr和最终存活/组状态；纳入统一最终核对，不丢弃reclaim返回值。不将helper计为ROS participant。
3. 短限假helper正常/卡住超时/身份捕获失败/身份变化/回收未完成路径，验证缺身份零信号且最终invalid、有身份的自有假进程可有界回收；无界wait不得恢复，第二方仍不在helper失败后启动。测试所有真实调用路径，不另写镜像函数。身份失效拒绝信号测试用mock，不向未知真实PID发信号。
4. 对最终代码完成第11轮既有离线全套加新增针对性回归；保留完整每例命令/时钟/RC/原件与缺失声明。失败迭代唯一目录不覆盖；拒绝入口也保留命令尝试记录。代码后改须重验。不另加无关功能、不因极端PID/PGID复用扩大工程。

首次封存不--force，stdout写/tmp/agc-w8-validation-r12-*；manifest/tar真实根/checksum/retrieval/源根逐文件核验。封存后只在report/_archive侧车更正。完成置待审查并通知当前父Leader后结束，不轮询/接下一单。真实A/B/C本轮未授权，S2/S3/S4/gate/headless/科研不变。未知漂移/guard/越界/证据缺失/预算不足停止回报。
