<a id="round14"></a>
# 第14轮：参数契约预检后执行真实A/B/C

任务ID 20261027-001-w8-validation-recovery；轮次14；来源Leader，2026-10-28；复用Worker 55d8793e-4916-4045-ac19-5800e167ebfa。

先读[第13轮审查](../round-13/review.md#round13-review)、[第13轮完整执行规格](../round-13/request.md#round13)、[本轮规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round14)、[Runbook](../../../../docs/ROS2迁移步骤.md#usage)及[观测分级](../../../README.md#run-tiers)。本轮继承第13轮全部配置、A正负控制、门控、判读、证据和停止条件；以下显式替换新根/预算/前置，不复活旧轮预算。

## 预算与写入

45min monotonic，显式 **T1: 3次**：A一次，A通过后B pub-first一次，B完整有效后C sub-first一次；每次≤30s、总≤90s、最多2ROS participant，普通用户，无额外重跑。任何invalid/控制不符/关键证据缺失停止后例，不改被调用脚本/换配置重跑。

新根 experiments/w8-validation/20261028-endpoint-gated-probe-r2/，可新增config/log/report/cases/evidence；独占/tmp/agc-w8-validation-r14-*。额外仅本轮report/CURRENT可写。第12轮已验收driver/probe/gate及所有历史源根/归档只读；不写pycache。HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290/main，保留既有dirty/untracked，按新根预置baseline/receipt逐项核对，未知漂移停止。不改全局scripts/src/toolchain/build/install/spec/Runbook/request/review，不reset/clean/commit/push/切分支。

## 新增必须前置（同轮完成，不另交离线轮）

1. claim先配对写report，再核对基线/来源及当前运行冲突。新根编排器吸收第13轮修正模板，**不含--second**。禁止从fake_probe模板抄参数。记录原始来源SHA，--run和--scratch都指新根/r14。
2. 直接read真实 probe_endpoint_ready.py 源码，经AST仅提取main中ArgumentParser构造、add_argument和parse_args语句，在argparse/sys/DEFAULT_TOPIC最小纯标准库环境中执行。不得执行其import rclpy或main后续；不得通过真实探针--help命令冒充零运行。用实际最终--probe-cmd经驱动同等shlex/format展开的a/pub/sub三种argv，喂给**提取的真实parser** parse_args，全部接受。额外把--second添加到有效argv，必须明确拒绝；留完整输入/结果/源SHA。这样验证真实参数契约，不仅是手写白名单或字符串检查。
3. 静态复核driver完整argv：只读第12轮代码绝对路径、--clean-env、仅jazzy wrap-source、domain0/LOCALHOST两个dataset、--allow-real-ros --t1-grant 3、无--allow-fake；默认26s/3s reserve/30s hard limit不变；真实topic与时长同第13轮。全部通过才执行T1。

## 执行与交回

A mode=a，3+2+2s，同topic正控制/不兼容QoS负控制/不同topic负控制判据同第13轮。A通过后B pub8/sub6，B完整有效后C sub8/pub6；endpoint_created身份/时序/实时存活门控，不fallback/固定sleep。允许的本地门控helper不计ROS participant。有效零接收可继续C，不能把缺日志/异常当零接收。

明确禁止构建/抓包/GZ/PX4/GUI/headless/observer/daemon/dev-shm读取/共享清理/系统配置改变/他人进程操作。只读执行第12轮driver时本轮允许--allow-real-ros --t1-grant 3。不因预检通过宣称真实控制有效。

保留完整每例命令/事件/result/stdout/stderr/身份/环境/库/门控/启动与重叠mono/真实RC/信号/残留及SHA；正负控制人工独立重算，峰值/final分开。任何失败唯一编号不覆盖。结束直接配对时钟，封存前复算预算，wall漂移只报告不归因。

定稿首次封存不--force，stdout到r14/tmp；核对manifest/tar真实根/checksum/retrieval/源根逐文件一致。封存后更正只report/_archive侧车。完成或阻塞report/CURRENT通知当前父Leader后结束，不轮询/接下一单。S2/S3/S4、gate/headless/科研不变，整链不归档。
