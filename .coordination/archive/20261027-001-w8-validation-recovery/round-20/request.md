<a id="round20"></a>
# 第20轮：修复回收竞态并重做 rclpy 跨进程基线

任务ID 20261027-001-w8-validation-recovery；轮次20；来源Leader，2026-10-28；复用Worker `47a2651c-e420-4218-b4c6-454837cd33fd`。

入口：[Runbook](../../../../docs/archive/ROS2迁移步骤.md#usage)、[规格](../../../../docs/archive/specs/w8-validation-recovery/spec.md#round20)、[第19轮审查](../round-19/review.md#round19-review)、[自主权限](../../../README.md#executor-autonomy)、[观测分级](../../../README.md#run-tiers)。

## 1. 目标与裁定

第19轮A因Worker驱动缺陷invalid：driver按spawn时刻计8s，probe按自身启动计8s，source开销170.5ms导致SIGINT打在spin_once窗口，result未写；B/C按门未执行。Leader已验收该流程处置并裁定：本轮只修回收语义并重做A，不把非权威partial观测升级为结论，不重开UDPv4分支。

目标：在**同一当前boot/domain0/LOCALHOST/默认传输**下，取得完整的rclpy publisher→rclpy subscription跨进程样本，判断第19轮非权威单向形态是否在完整窗口中复现。

## 2. 允许范围与T1预算

整轮45min monotonic；T1最多2次、每次≤30s、累计≤60s；最多2个ROS participant；普通用户；独占`/tmp/agc-w8-validation-r20-*`。允许新根派生第19轮rclpy probe/driver并修复回收与退出记录；禁止改旧探针、项目代码、永久配置、构建、GZ/PX4/GUI/headless、抓包、读`/dev/shm`内容、共享清理、daemon/observer。

默认条件：`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`，不设`FASTDDS_BUILTIN_TRANSPORTS`/RMW/LD_PRELOAD/profiles/static peers；只source Jazzy，不source项目install；topic `/agc_r20/chatter`，RELIABLE/VOLATILE/KEEP_LAST depth10。

## 3. 必须先完成的离线修复与守卫（T1=0）

1. 驱动回收期限不能按shell spawn计时。必须以probe自身`process_entry`或`endpoint_created`的已flush/fsync事件作为起点，再给完整probe预算（约8s）加≥1s安全余量；不得在probe应写result前发送SIGINT。
2. probe必须捕获`BaseException`，记录`probe_interrupted`并在finally/退出路径写入result；修复前守卫应失败，修复后守卫通过。
3. 离线fake必须验证：source启动延迟不截断窗口；result缺失但events存在分类为`partial`而非静默当作empty/invalid；真实RC与SIGINT保留；错误启动顺序/缺失endpoint/伪造fake均拒绝。
4. 复核第19轮已修复的运行中maps/stat采样守卫（真实exec后PID；无法识别则`runtime_maps: missing`，绝不使用bash maps冒充）。

保存所有离线守卫原文与SHA；未通过即停止，不启动ROS。

## 4. 真实T1执行与停止门

- **A（T1#1）**：rclpy pub先创建endpoint并flush/fsync，再启动sub；两端跨进程默认传输，观测约8s。记录双方完整graph/matched/endpoint info/GID/type/type hash/QoS/heard/events，比较pub/sub是否都看到对端。
- 只有A因**启动前编排异常且0被测进程**invalid时，才允许修复并使用T1#2一次；若A因运行中、回收、probe或证据缺陷invalid，停止，不重跑。A valid后结束本轮，不执行UDPv4 B/C。
- 不能把A的partial观测当有效测量。`result`缺失但events完整时，case状态=`partial`，primary仍invalid；报告必须同时给出partial摘要及限制。

## 5. 判读

- 双侧matched=1且heard>0：当前boot的rclpy跨进程默认数据面可用；第19轮单向partial不复现。
- 双侧matched=1但heard=0：完整窗口下数据面异常，SHM/回调/序列化候选上升；仍不是根因。
- 完整窗口下pub侧看到sub而sub侧graph/matched=0：正式复现历史rclpy↔rclpy单向发现形态；下一轮再决定UDPv4或发现层分支。
- 双侧graph/matched=0：记录为发现层失败，不把缺少match解释成数据面失败。

## 6. 交付与基线

新根：`experiments/w8-validation/20261028-rclpy-cross-process-recheck-r1/`。保存claim/end配对时钟、boot、完整argv/env/maps/stat、events/result/stdout/stderr、真实RC/回收、残留及守卫原文。partial与invalid分开标注。

Worker只写新根、本轮report、CURRENT、tasks/checklist round20勾选；旧证据/归档只读。Leader将在所有文档写入完成后刷新baseline/receipt；领取时未知漂移即停止。首次封存不`--force`，独立核对manifest/tar/retrieval/源根逐文件一致。

完成后CURRENT待审查并通知Leader；不自行开下一轮。S2/S3/S4、gate/headless/科研结论不变，整链不归档。
