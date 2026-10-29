<a id="round17-review"></a>
# 第17轮独立审查

任务 ID 20261027-001-w8-validation-recovery；来源 Leader，2026-10-28。

## 1. 核验与验收

亲自读取完整report/analysis、A例command与双端日志、环境/maps、独立重数、boot证据、驱动派生diff、基线复核及归档retrieval。独立重算tar SHA为 `2048fc4b37ab8050419742f919dab52411343481851f7fed877baff4d98c3435`，35个成员与当前源根逐文件一致；除已裁定的request/Runbook两项Leader快照后修改外，其余 **43405项新增漂移0**。

A真实环境为domain37/LOCALHOST，stock listener在talker期间持续存活，双方真实RC=0，talker发布5条，listener原始输出无 `I heard:`；独立重数一致。T1一次8.231s、整轮571.734s，无重跑；B/C按派工停止门跳过，不是遗漏。封存后源根零写入。

**第17轮诊断取证验收通过。** 历史stock阳性在domain37、11键构造和直接exec下未复现，第16轮阴性不能仅由domain0解释。构造11键与实际source后22键区分清楚，驱动参数化及原文证据充分。报告对8.342s mono与8.906s wall的追加口径更正保留，不改预算判定。

## 2. 重启证据与判读边界

`btime=2026-10-28T17:18:11+08:00`、本轮领取uptime约4972s，而第16轮同日15:26已记录uptime25551s，证明第16/17轮之间发生boot切换。后续不得把跨boot结果当成同一持久环境状态的简单重复；但重启不是根因证据，也不能推出domain或SHM结论。

本轮没有domain0或探针的新实测，B/C未执行不得改写为失败。当前只确认：在本boot、domain37、stock直接exec条件下仍无接收；DDS discovery/matching/delivery断点仍未分层。

## 3. 下一步设计裁定

不再单独消耗一轮补做stock domain0：即使再次阴性，也只增加一个零接收样本，不能解决当前真正缺口。改为当前boot、固定domain0/LOCALHOST的 **stock↔rclpy混合端点交叉对照**，同时采集rclpy侧graph/matched/endpoint info/QoS/heard及stock侧发布/接收原文。

该设计直接检验官方C++与自写rclpy端点能否互操作，并把第15轮endpoint-info候选落到有实际对照价值的场景；不再只重复rclpy↔rclpy旧失败。下一次只派 [第18轮混合端点分层观测](../round-18/request.md#round18)，T1三次、45min，新探针先以同进程正负控制和离线fake验证门控，真实双向顺序仅两次。

S2/S3/S4继续关闭；gate/headless/科研结论不变，整链不归档。
