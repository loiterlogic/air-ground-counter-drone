<a id="round19"></a>
# 第19轮：跨进程数据面与 UDPv4 单变量对照

任务ID 20261027-001-w8-validation-recovery；轮次19；来源Leader，2026-10-28；复用Worker `47a2651c-e420-4218-b4c6-454837cd33fd`。

入口：[Runbook](../../../../docs/ROS2迁移步骤.md#usage)、[规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round19)、[第18轮审查](../round-18/review.md#round18-review)、[自主权限](../../../README.md#executor-autonomy)、[观测分级](../../../README.md#run-tiers)。先读第14–18轮完整报告、审查及原始证据。

## 1. 目标与判别逻辑

第18轮已在当前boot/domain0/LOCALHOST证明：stock↔rclpy两方向均发现、endpoint info可见、matched=1持续，但零消息送达；同进程C0 heard=59。因此本轮不再重复发现层或 domain 扫描，回答两个更窄的问题：

1. 当前boot下，**纯rclpy跨进程**默认传输是否也出现 matched后零送达？
2. 将Fast DDS传输从默认LOCALHOST的SHM+UDPv4切换为**UDPv4-only**后，stock→rclpy数据面是否恢复？若恢复，强支持SHM数据路径；若仍零送达，SHM不是充分解释。

纯UDPv4是本轮显式授权的诊断配置变量，不是永久修复或工程配置裁定。不得把任何单方向阳性称为通信整体恢复。

## 2. 实验条件与T1预算

固定：当前boot、`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、topic `/agc_r19/chatter`、std_msgs/msg/String、RELIABLE/VOLATILE/KEEP_LAST depth10；只source `/opt/ros/jazzy/setup.bash`，不source项目install；rclpy endpoint先创建并fsync，再启动后方进程。每例独立ROS_HOME/ROS_LOG_DIR和/tmp前缀。

显式T1 **3次**，总≤90s、整轮45min、每次≤30s、最多2个ROS participant、普通用户：

- **A（T1#1，必做）**：rclpy publisher→rclpy subscription，默认传输（不设`FASTDDS_BUILTIN_TRANSPORTS`），两端跨进程，rclpy pub先创建，随后启动sub，运行约8s；记录两端matched/graph/heard和endpoint info。
- **B（T1#2，条件执行）**：stock talker→rclpy subscription，唯一新增变量为已学习的Fast DDS UDPv4-only配置`FASTDDS_BUILTIN_TRANSPORTS=UDPv4`；其余沿用第18轮A，rclpy sub先创建、stock talker后起、运行约8s。记录同样分层证据及stock发布原文。
- **C（T1#3，条件执行）**：仅当B有效（进程/证据完整，无invalid）时执行rclpy publisher→stock listener，仍只使用UDPv4-only，复用B的环境和topic，记录rclpy matched/graph/heard与stock原文。B有效阴性仍执行C；B invalid停止C。不得追加反向默认传输或重跑。

A有效阴性不跳过B：阴性本身是“纯rclpy跨进程数据面”有效观测。A invalid才停止B。有效结果不重跑；仅启动前编排异常且0被测进程时可按协议修复一次，保留原件并计入尝试。

## 3. 探针与证据要求

在新根派生第18轮探针/驱动，不改旧源根、旧探针或项目代码；先做T0离线fake/API/行为守卫。保留C0已通过的事件格式、fsync、真实RC传播、matched/incompatible回调、graph和endpoint-info采样；原始API异常与空结果必须区分。

**修正第18轮已知缺陷**：stock wrapper不能在spawn后立即采maps/stat；必须在`exec`后或运行窗口内轮询采集真实demo PID的`/proc/<pid>/maps`与`/proc/<pid>/stat`，并在原始件中记录采样时刻、comm、PID、starttime。若无法可靠识别exec后的PID，标记runtime maps缺失，不得以bash maps替代；`DT_NEEDED`只能作为静态补偿。

每例必须保存：完整argv和实际环境（含`FASTDDS_BUILTIN_TRANSPORTS`显式存在/不存在）、boot btime/uptime、库maps（运行中）、PID/PGID/starttime、配对mono/wall、事件原文、endpoint node/GID/type/type hash/QoS、graph/matched/heard、stock stdout/stderr/ROS日志、真实wait RC、回收与残留。保存UDPv4配置前后差异；不读`/dev/shm`内容、不抓包。

## 4. 判读表

- A matched=1且heard>0：纯rclpy跨进程默认数据面可用，mixed pair专属/stock参与路径上升；继续看B。
- A matched=1且heard=0：当前boot一般跨进程数据面异常；B/C结果用于判断UDPv4是否绕开该异常，不把问题归给stock。
- B在UDPv4-only下heard>0而第18轮默认A为0：强支持SHM路径是必要嫌疑；不得称已完成永久修复。
- B仍matched=1/heard=0：UDPv4-only未恢复，SHM不是充分解释，继续查序列化/共享数据面/回调或更底层环境。
- C与B不对称：保留方向差异，不能外推另一方向。
- 任一endpoint info API异常：记录`api_error`，不得当作空endpoint列表或“未发现”。

## 5. 停止条件与白名单

遇硬约束、未知保护漂移、预算/进程超限、共享资源冲突、需要root/系统改动/抓包/读dev_shm内容、C0/离线守卫不通过或关键原件缺失，立即停止并回报。允许本轮显式的Fast DDS进程环境变量变化；不得写入永久配置。不得启动GZ/PX4/GUI/headless/全链、构建、daemon或项目节点。

新根：`experiments/w8-validation/20261028-transport-data-plane-r1/`。Worker只写新根、本轮report、CURRENT、tasks/checklist的round19勾选；旧证据和归档只读。Leader已在所有文档写入后刷新baseline/receipt；领取时逐项复核，未知漂移停止。使用`python3 -B`/AST，禁止`__pycache__`。

## 6. 交回

完成后写`report.md`与`report/analysis.md`，独立重算判据和预算，首次封存不`--force`，核对manifest/tar/checksum/retrieval及源根逐文件一致；封存后只写report和archive侧车。CURRENT置待审查并send_message通知Leader；不轮询、不接下一轮。S2/S3/S4、gate/headless/科研结论不变，整链不归档。
