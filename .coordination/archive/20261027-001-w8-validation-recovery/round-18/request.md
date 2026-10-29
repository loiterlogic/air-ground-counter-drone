<a id="round18"></a>
# 第18轮：当前 boot 的 stock↔rclpy 混合端点分层观测

任务ID 20261027-001-w8-validation-recovery；轮次18；来源Leader，2026-10-28；复用Worker `47a2651c-e420-4218-b4c6-454837cd33fd`。

入口：[Runbook](../../../../docs/archive/ROS2迁移步骤.md#usage)、[规格](../../../../docs/archive/specs/w8-validation-recovery/spec.md#round18)、[第17轮审查](../round-17/review.md#round17-review)、[自主权限](../../../README.md#executor-autonomy)、[观测分级](../../../README.md#run-tiers)、[硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。先读第14–17轮完整回报/审查与相关原始证据。

## 1. 目标：让失败也产生新分层信息

第17轮证明当前boot/domain37 stock仍阴性，且第16/17轮之间发生boot切换。不再单测domain数字，不再原样重复rclpy↔rclpy。固定当前boot、domain0、LOCALHOST，用官方stock C++与仪表化rclpy端点交叉：

- A：stock talker → rclpy subscription（rclpy先创建endpoint，stock后起）；
- B：rclpy publisher → stock listener（rclpy先创建endpoint，stock后起）。

同步记录rclpy侧 graph count、matched事件/计数、incompatible QoS、`get_publishers_info_by_topic`/`get_subscriptions_info_by_topic` 的node/GID/topic type/type hash/QoS，以及heard；stock侧原始publish/I heard日志。区分发现视图、DDS匹配、用户数据回调，不把API返回当发现就绪。

## 2. 已学习的实现与复用边界

- 第16/17轮已验收stock直接exec驱动：官方二进制、真实环境/maps/RC/原文/回收齐全，复用其控制语义。
- 第14轮已验收 `probe_endpoint_ready.py` 的event callback、graph/matched/heard、生命周期事件与门控语义；只在新根派生最小rclpy单端探针，旧探针/driver/gate只读。
- 本机Jazzy rclpy `Node.get_publishers_info_by_topic`/`get_subscriptions_info_by_topic` 返回 `TopicEndpointInfo`，字段含node name/namespace、topic type/type hash、endpoint type、GID、QoS。先静态读取本机API定义，按实际字段序列化，不凭记忆。
- 同进程正/负控制与纯fake驱动测试用于验证新探针/编排，不冒充跨进程通信阳性。

## 3. 预算与运行边界

整轮45min monotonic。显式 **T1: 3次**：
1. C0同进程rclpy正/负控制一次（1 participant，≤15s）；
2. A stock→rclpy一次（2 participant，≤30s）；
3. B rclpy→stock一次（2 participant，≤30s）。

累计≤75s且≤90s，普通用户，独占 `/tmp/agc-w8-validation-r18-*`。C0控制失败或invalid则A/B不得执行；A invalid则B停止；A有效阴性仍可执行B以观测反向。

禁止构建、GZ/PX4/GUI/headless/全链、抓包、读 `/dev/shm` 内容、共享清理、系统/网络/库/时钟改变、root、常驻daemon/observer。有效结果不重跑；仅明确的启动前编排异常且0被测进程可按协议修复一次，保留原件并如实计数。

## 4. 离线前置（T1=0阶段，同轮完成）

在新根派生最小rclpy单端探针和混合驱动，不改项目代码/旧证据。必须：
- 复用事件flush/fsync、endpoint_created、真实heard、matched/incompatible回调与配对时钟；增加graph/endpoint-info采样，原始API异常逐字段记录，禁止异常被静默转为空列表。
- stock话题 `/agc_r18/chatter`，类型 `std_msgs/msg/String`；rclpy QoS取stock默认兼容配置：depth10、RELIABLE、VOLATILE、KEEP_LAST，显式记录。
- rclpy endpoint创建返回并flush/fsync后才允许启动stock；核对PID/PGID/starttime、存活和重叠。stock→rclpy时stock发布6s；rclpy→stock时rclpy以约1Hz发布至少6条并保持spin，总观测≤15s；两端优雅回收。
- 用纯fake进程/事件验证门控拒绝缺失/错位事件、超时回收、真实RC传播、stock原文判据和rclpy结果解析。不得用fake结果充当真实样本。
- C0同进程含：同topic兼容QoS正控制（matched且heard>0）、不同topic负控制（无匹配/无heard）、BEST_EFFORT pub→RELIABLE sub不兼容QoS负控制（有incompatible事件、无heard）。保持≤15s。

## 5. A/B判读

A=stock talker→rclpy sub；B=rclpy pub→stock listener。rclpy均先启动，消除上一轮跨boot/domain混杂，集中检验混合端点和同一启动方向。

- rclpy看不到对端endpoint info且graph=0/matched=0：发现/通告层分支上升；endpoint info为空本身不能区分类型问题。
- endpoint info可见、type hash相同且QoS兼容但matched=0：通告可见与DDS匹配之间分裂，不能把graph当匹配。
- matched>0但heard=0：匹配后数据面/回调分支上升；stock原文和rclpy事件缺一不可。
- A/B heard>0：当前混合方向可通信，仅是该方向/该boot阳性，不宣称工程恢复。
- A/B结果不对称：保留方向差异，下一轮再决定反向或重复，不在本轮加尝试。

endpoint info须保留自身与对端实体，按node/GID区分；空结果与API异常分开。type hash/QoS相同或兼容只在实际字段支持时判定，不做字符串猜测。

## 6. 必存证据与交付

新根 `experiments/w8-validation/20261028-stock-rclpy-mixed-r1/`，可新增config/cases/evidence/log/report/scripts。每例保存完整argv、实际环境、maps、配对mono/wall、PID/PGID/starttime、真实wait RC、信号/回收、stdout/stderr/ROS日志、残留；rclpy保存完整events/result及endpoint info原始序列化，stock保存发布/接收原文。保存boot btime/uptime作为本轮上下文，不作归因。

`report/analysis.md` 给C0有效性、A/B分层判读、跳过原因、与第14轮rclpy↔rclpy和第16/17轮stock↔stock的可比性、尚未定位项。离线fake单独标`offline`，不计T1。

定稿首次封存不 `--force`；独立核对manifest/tar真实根/checksum/retrieval/源根逐文件一致，封存后只写report/_archive侧车。

## 7. 基线与写入白名单

HEAD `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / main，保留现有dirty/untracked，不reset/clean/commit/push/切分支。Leader在新根预置刷新后的baseline/receipt，须在完成所有Leader文档写入后生成；Worker领取逐项复核，未知漂移停止。

Worker只写新根、本轮report、CURRENT、`.trae/specs/w8-validation-recovery/{tasks,checklist}.md` round18执行勾选。禁止改src、项目scripts、toolchain、build/install、spec/Runbook/request/历史review、旧探针/驱动、历史源根/归档；用python3 -B/AST，无__pycache__。

## 8. 停止与交回

硬约束问题、未知保护漂移、guard、预算/进程超限、需要共享资源或白名单外改动、C0无效、关键原件缺失即停止。完成写report并更新CURRENT待审查，send_message通知Leader后结束，不轮询、不接下一单。S2/S3/S4、gate/headless/科研不变，整链不归档。
