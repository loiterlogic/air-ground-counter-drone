<a id="round23"></a>
# 第23轮：发现通告机制判别（discovery日志 + locator注入）

任务ID 20261027-001-w8-validation-recovery；轮次23；来源Leader，2026-10-28；复用Worker `47a2651c-e420-4218-b4c6-454837cd33fd`。

入口：[Runbook](../../../../docs/ROS2迁移步骤.md#usage)、[规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round23)、[第22轮审查](../round-22/review.md#round22-review)、[自主权限](../../../README.md#executor-autonomy)、[观测分级](../../../README.md#run-tiers)。

## 1. 目标与裁定

第22轮已满足全部前置：两顺序各n≥2、25s窗口排除慢发现、端口绑定对称（p0=7410/7411、p1=7412/7413、无7400）、rcl→rmw交接点已定位。单向失败不能用端口未建解释，嫌疑落在通告的**发出或接收**。

本轮是本链首次机制级干预，回答两个互补问题：
1. **discovery日志**：先起方的通告是否实际发出？后起方是否收到？收到后是否被拒？（机制信号）
2. **locator注入**：显式把先起方metatraffic unicast给后起方后，后起方能否发现先起方？（修复方向信号）

二者单独任一都留半边未知，故同轮做，均为单变量、可证伪。

## 2. T0：先定位启用机制，再真实运行

1. **discovery日志**：从本机rmw_fastrtps/Fast DDS 2.14.7定位启用discovery类日志的机制（环境变量，或仅含log配置的最小XML profile）。若用XML profile，必须离线断言该profile**只含log配置**，不含任何transport/peer/discovery range变更；证明无副作用后才可用于真实运行。记录启用方式与实际生效的日志类别/级别。
2. **locator注入语义**：定位`ROS_STATIC_PEERS`→`rmw_discovery_options_t.static_peers`的解析与格式（本机源码/头文件，不凭记忆）；确认它与`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`的交互——是否被LOCALHOST覆盖、是否需要额外开关。离线fake守卫验证构造环境与真实`/proc/<pid>/environ`均含预期键值。
3. 修复后的运行中maps/stat、回收锚定、BaseException落盘、双endpoint fsync端口闸门全部沿用，不改语义。

## 3. T1预算与固定条件

整轮45min monotonic；T1最多2次、每次≤30s、累计≤60s；最多2个ROS participant；普通用户；独占`/tmp/agc-w8-validation-r23-*`。

固定：当前boot、`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`，不设`FASTDDS_BUILTIN_TRANSPORTS`/RMW/LD_PRELOAD；只source Jazzy；topic `/agc_r23/chatter`，RELIABLE/VOLATILE/KEEP_LAST depth10；两例均**pub-first**（与第20/21/22轮pub-first基线可比）。

- **A（T1#1）**：唯一变量=discovery日志启用（观测性，不改语义）。pub先建endpoint、sub后起，窗口沿用第22轮B（pub约29s、sub约25s）。
- **B（T1#2）**：唯一变量=后起方sub获显式initial peer指向先起方p0 metatraffic unicast（domain0即`127.0.0.1:7410`，以T0确认的格式为准）。**不加discovery日志**，窗口同A。
- 有效结果不得重跑；仅启动前0 participant异常可按协议修复一次并保留原件。

## 4. 每例必存与判读

保存claim/end时钟、boot、双侧argv/env、events/result、graph/matched/endpoint info/GID/type/hash/QoS/heard、运行中maps/stat、真实RC/回收、双时点逐PID端口、以及**discovery日志原文**（A例）与**注入后端观测**（B例，含后起方graph/matched变化时序）。

判读：
- **A**：日志显示先起方通告发出但后起方从未收到→路径/接收层；后起方收到但拒绝/丢弃→处理层；先起方根本未发出→发送层。任何一种都是新机制证据，不得直接等于根因。
- **B**：注入后后起方matched=1/graph=1且heard>0→locator传播失败是充分解释，通信在注入条件下恢复（**不是工程恢复，是诊断条件下的恢复**）；注入后仍0/0/0→locator注入不充分，需回退到处理层或SHM发现。
- **A/B窗口内均须完整**；invalid只报invalid，不解释为形态变化。

## 5. 交付与边界

新根：`experiments/w8-validation/20261028-discovery-mechanism-probe-r1/`。旧证据/归档/探针只读；探针sha保持`baaece49…`或记录任何必要修改的完整理由。Worker只写新根、本轮report、CURRENT、tasks/checklist round23勾选。Leader将在所有文档写入后刷新baseline/receipt；领取逐项复核，未知漂移停止。

禁止构建、GZ/PX4/GUI/headless、抓包、读`/dev/shm`内容、共享清理、系统/网络/库/时钟配置、root、daemon。本轮**允许且仅允许**两个显式诊断变量：discovery日志启用、ROS_STATIC_PEERS注入；均不得写入项目配置或永久文件。封存后源根零写入。完成后CURRENT待审查并通知Leader；不自行开下一轮。S2/S3/S4、gate/headless/科研结论不变，整链不归档。
