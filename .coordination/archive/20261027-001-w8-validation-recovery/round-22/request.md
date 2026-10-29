<a id="round22"></a>
# 第22轮：sub-first 重复与延长窗口发现判别

任务ID 20261027-001-w8-validation-recovery；轮次22；来源Leader，2026-10-28；复用Worker `47a2651c-e420-4218-b4c6-454837cd33fd`。

入口：[Runbook](../../../../docs/ROS2迁移步骤.md#usage)、[规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round22)、[第21轮审查](../round-21/review.md#round21-review)、[自主权限](../../../README.md#executor-autonomy)、[观测分级](../../../README.md#run-tiers)。

## 1. 目标与裁定

第21轮A/B证明不对称跟随启动顺序而非角色：后启动方看不到先启动方，各顺序当前n=1；pub-first另有第20轮同结果，合计n=2。sub-first仍不足n=2；8s窗口尚未排除慢发现；第21轮端口T0覆盖后起方过早，端口数据不可支撑方向性。

本轮回答三个问题：
1. sub-first在同一boot内是否重复；
2. 将后起sub窗口延长到约25s后，是否只是发现慢；
3. 双participant真实endpoint创建后的发现端口/绑定状态是什么。

第23轮只有在延长窗口仍复现单向且两顺序n≥2后，才考虑显式授权发现通告/locator层诊断。

## 2. 预算、固定条件与允许变量

整轮45min monotonic；T1最多2次、每次≤30s、累计≤60s；最多2个ROS participant；普通用户；独占`/tmp/agc-w8-validation-r22-*`。

固定：当前boot、`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`，不设`FASTDDS_BUILTIN_TRANSPORTS`/RMW/LD_PRELOAD/profiles/static peers；只source Jazzy；topic `/agc_r22/chatter`，RELIABLE/VOLATILE/KEEP_LAST depth10；复用第20/21轮探针/驱动语义，不改变回收锚定、BaseException落盘、运行中maps/stat采集。

- **A（T1#1）**：sub-first重复，窗口同第21轮B（先起sub 12s、后起pub 8s）。
- **B（T1#2）**：pub-first；唯一变量为窗口，先起pub约29s、后起sub约25s，后起窗口必须完整位于先起窗口内且单例≤30s。其余条件不变。
- 有效结果不得重跑；仅启动前0 participant异常可按协议修复一次并保留原件。

## 3. T0端口采集修复与执行

必须使用已修复的闸门：两侧`endpoint_created`均已flush/fsync后才采快照；不得在后起方endpoint创建前拍逐PID端口。每例至少两次采样：双endpoint建立后、结束回收前。记录每个PID的7399–7600段UDP socket、inode、local address/port和绑定地址；保留原始`/proc/net/udp`、`/proc/net/udp6`。按域端口公式归属：7410=metatraffic unicast、7411=同一participant user端口、7400=multicast metatraffic；不得把7411读成第二participant。无法归属即missing，不外推。

同轮继续T0静态研究：从本机已安装文件定位`ROS_AUTOMATIC_DISCOVERY_RANGE`从rcl到rmw_fastrtps的交接线索；无法定位则列未知，不使用外部记忆补结论。

## 4. 每例必存与判读

保存claim/end时钟、boot、双侧argv/env/events/result/graph/matched/endpoint info/GID/type/hash/QoS/heard、运行中maps/stat、真实RC/回收、端口原始快照和归属。A/B只允许预期单变量差异；其余差异必须披露。

判读：
- A复现单向、B延长窗口仍后起方不可见：慢发现排除，两顺序n≥2；下一轮才进入发现通告/locator诊断。
- B后起方在延迟后看到先起方或heard>0：当前形态含慢发现/lease因素，必须重估时序窗口。
- A/B任一invalid：只报invalid，不解释为形态变化。
- 端口快照异常：保留为诊断缺口，不回填graph/matched结论。

## 5. 交付与边界

新根：`experiments/w8-validation/20261028-order-repeat-window-r1/`。保存封存manifest/tar/retrieval；旧证据/归档/探针只读。Worker只写新根、本轮report、CURRENT、tasks/checklist round22勾选。Leader将在所有文档写入后刷新baseline/receipt；领取逐项复核，未知漂移停止。

禁止UDPv4/传输/profiles/system/network/library/clock、构建、GZ/PX4/GUI/headless、抓包、读`/dev/shm`内容、共享清理、root、daemon。封存后源根零写入。完成后CURRENT待审查并通知Leader；不自行开下一轮。S2/S3/S4、gate/headless/科研结论不变，整链不归档。
