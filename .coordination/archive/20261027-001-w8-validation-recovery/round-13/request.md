<a id="round13"></a>
# 第13轮：endpoint门控真实A/B/C微观测

任务ID 20261027-001-w8-validation-recovery；轮次13；来源Leader，2026-10-28。复用Worker 55d8793e-4916-4045-ac19-5800e167ebfa。第12轮[审查](../round-12/review.md#round12-review)已验收，仅结束离线驱动返工。

入口：[Runbook](../../../../docs/archive/ROS2迁移步骤.md#usage)、[规格](../../../../docs/archive/specs/w8-validation-recovery/spec.md#round13)、[原第9轮控制语义](../round-9/request.md#round9)、[观测分级](../../../README.md#run-tiers)、[硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。已学本机同版本rclpy/第3轮正负控制/第12轮离线成功实现，本轮复用不重写。

## 授权

**T1: 3次**，A一次、条件B一次、条件C一次。每次首被测进程启动至全回收≤30s，总≤90s、最多2ROS participant；本地不建participant的身份/门控helper不计ROS participant。整轮45min monotonic，普通用户，独占 `/tmp/agc-w8-validation-r13-*`。无额外重跑预算，旧轮预算不滚存。真实异常/invalid/控制不符/必要证据缺失停止后例，不现场修改代码或换配置重试。

固定domain0/LOCALHOST、std_msgs/String、RELIABLE depth10（QoS负控制除外），env-i语义，HOME=/home/chen，仅source /opt/ros/jazzy/setup.bash，ROS_HOME/ROS_LOG_DIR独占；不设FASTDDS_BUILTIN_TRANSPORTS/ROS_STATIC_PEERS/RMW_IMPLEMENTATION/LD_PRELOAD/profiles。跨进程topic `/agc_probe_domain0/chatter`，负控制topic沿用第12轮探针。禁止构建/抓包/GZ/PX4/GUI/headless/额外observer/daemon/读dev-shm/共享清理/系统配置变更或停止他人进程。

## 实施边界与步骤

只读使用 `experiments/w8-validation/20261028-endpoint-helper-offline-r1/scripts/{run_attempt_driver,probe_endpoint_ready,validate_gate}.py`，执行前记录完整SHA，与封存manifest一致。生产入口本轮明确允许 `--allow-real-ros --t1-grant 3`；不允许--allow-fake或修改脚本规避边界。驱动通过--run指向本轮新根、--scratch指向上述r13独占路径，--probe-cmd引用第12轮真实探针绝对路径及既有模板；--clean-env、--wrap-source=/opt/ros/jazzy/setup.bash、两个--dataset分别设置domain0/LOCALHOST。默认26s budget/3s reserve/30s hard limit不变。不得向第12轮源根输出或编译缓存。

1. 领取前先配对claim写mutable report，核对HEAD/分支/冻结size/SHA/absent/已有运行，冲突停止不清场。保存完整最终命令，静态检查参数指向新根及独占临时目录后再执行。
2. **A1** mode=a：正控制3s、QoS负控制2s、不同topic负控制2s。正控制双侧matched且heard>0；QoS负控制零matched/零heard且有incompatible QoS；不同topic零matched/零heard。所有endpoint_created应位于post_init/node_created之后，身份/事件/真实RC完整。任一不符或invalid，停止B/C，区分探针控制失败与环境结论。
3. **B1** pub_first：先pub8s、后sub6s。A有效通过才执行。后方只在本次先方endpoint_created身份/QoS/时序校验通过且先方实时存活、预算足够后启动；不fallback、不加固定sleep。
4. **C1** sub_first：先sub8s、后pub6s。B完整有效（即使零消费仍可为有效诊断失败）才执行。其余同B。

## 判读与原件

endpoint_created只表示API返回，不代表DDS发现就绪。运行期峰值与退出后final分列。B/C均双向graph/matched且heard>0仅说明当前门控条件通信成立；实现变化与时序变化不能拆成唯一根因。若旧随启动顺序翻转的单向匹配+零消费仍在，则说明endpoint创建返回门控仍未消除该形态。其他/不一致/invalid如实分类，不追加样本。无论结果如何不自动恢复S2。

保留每次完整命令/起止配对、驱动/探针/helper实际SHA、PID/PGID/starttime、环境/实际库、post_init/node/endpoint事件、门控/后方启动mono与重叠窗口、双侧graph/matched/incompatible/heard、真实RC/result/probe_end、信号/残留与完整stdout/stderr；驱动自动产物外，人工独立核对A控制与B/C判读，缺原件不可当零。所有失败原件保留，唯一编号不覆盖。wall/mono漂移如实报告、不假设原因、不改时钟。

## 白名单/基线/封存

新根 `experiments/w8-validation/20261028-endpoint-gated-probe-r1/` 可新增config/log/report/cases/evidence，允许新增仅编排上述命令的简单shell入口及离线分析（不可新增ROS探针/修改驱动）。额外仅本轮report/CURRENT可写。预置baseline/receipt只读；旧探针/历史源根/归档只读。禁止改src/scripts/toolchain/build/install/spec/Runbook/request/review或其他协调文件，不reset/clean/commit/push/切分支。

HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290/main，保留全部dirty/untracked；领取与交回按本轮基线逐项核对，未知漂移停止。结束时钟直接配对，预算算术封存前复算。定稿首次封存不--force，stdout写r13独占/tmp；核对manifest/tar真实根/checksum/retrieval与源根逐文件相等。封存后只在report/_archive侧车更正。

完成或阻塞写report/CURRENT，send_message通知当前父Leader后结束，不轮询/接下一单。本轮仅通信诊断；S2/S3/S4/gate/headless/科研不变，整链不归档。
