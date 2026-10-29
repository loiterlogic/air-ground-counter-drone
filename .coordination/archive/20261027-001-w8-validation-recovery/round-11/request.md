<a id="round11"></a>
# 第11轮：驱动离线定点返工

任务ID 20261027-001-w8-validation-recovery；轮次11；来源Leader，2026-10-28。复用Worker 55d8793e-4916-4045-ac19-5800e167ebfa。

入口：[Runbook](../../../../docs/ROS2迁移步骤.md#usage)、[规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round11)、[上轮审查](../round-10/review.md#round10-review)、[权限](../../../README.md#executor-autonomy)、[契约](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。先读完整审查和对应代码/原始回归，从既有已验证回收实现学习，不重复换domain/discovery配置。

## 授权与基线

45min monotonic，**T1: 0次**。仅纯假进程/假模块离线验证；0ROS init/Node/participant/真实helper/构建/仿真/抓包/共享资源操作。任何动作之前配对采样mono-before/wall/mono-after写本轮report，再领取，结束同样采样；不得以mtime反推冒充实测。

新根 experiments/w8-validation/20261028-endpoint-driver-offline-r2/ 可新增scripts/config/log/report；可吸收第10轮最终代码，记录来源与SHA；第10轮及更早全部封存源只读。额外仅本轮report和CURRENT可写。禁止改规格/Runbook/request/review/全局scripts/src/toolchain/build/install/历史归档，不reset/clean/commit/push/切分支。

HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290/main，保留既有dirty/untracked；Leader预置config基线/receipt只读，领取与交回逐项核对实际条目数/SHA/size，未知漂移停止。

## 收口目标

1. 完成进程事件流不得容忍破损末行；result/probe_end必填pid/attempt/role（按实际schema）、exit_code、invalid_reasons等字段存在且类型正确，不能missing视为空。活跃门控抓拍允许partial的语义与完成验收区分。增加真实validate_side反例：坏尾、字段缺失、类型错误、身份冲突，均拒绝。
2. 身份缺失/变化时禁止盲发PID或PGID信号；修掉send_signal与group sweep绕过检查。自有leader退出后的group清扫必须用可核实的组成员归属证据，身份不明停止信号并记录残留失败，不触他人。离线mock记录“不应发信号”以及真实自有假进程树测试“应回收”；不实际对未知PID/组发信号。
3. helper超时及所有等待min到共同monotonic截止并保留回收额度；第二方启动前也检查剩余预算。不仅事后span标invalid。短时限测试标记迟到、helper卡住、helper消耗预算后不得起第二方及有界回收；固定sleep不作门控。
4. 回收后以真实poll返回码写所有失败路径，不能把已获RC丢成None；若仍未回收/组存活/leader存活，最终一定invalid，不得因scan排除PID放过。记录回收完成时钟、真实RC、残留/组状态与失败原因。保留A/B/C正常与第10轮已有有效覆盖。
5. 每例完整命令、配对起止、driver退出码、stdout/stderr、drive.json与probe原始事件/result（产生则保留；未产生显式记缺失）应纳入新根封存，不能只留/tmp引用或tail。过程失败/修复重跑用唯一编号，不覆盖失败证据。

先完成局部故障注入，再对最终代码完成全套指定离线回归，之后修改受测代码须重验。真实入口默认拒绝仍保留；本轮不得用allow-real-ros启动真实探针。不得扩成新runner框架或加入无关功能。

完成首次封存，不--force，stdout写/tmp/agc-w8-validation-r11-*；核对manifest/tar真实根/checksum/retrieval/源根逐文件一致，封存后仅report或_archive侧车纠错。完成或阻塞后写report/CURRENT并send_message通知当前父Leader，结束、不轮询/接下一单。验收仅离线子范围；S2/S3/S4/gate/headless/科研状态不变。未知漂移/guard/越界需求/证据缺失/预算不足停止回报。
