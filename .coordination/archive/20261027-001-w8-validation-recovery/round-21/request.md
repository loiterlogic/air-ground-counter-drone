<a id="round21"></a>
# 第21轮：单向发现形态的稳定性与方向性对照（含发现端口 T0 观测）

任务ID 20261027-001-w8-validation-recovery；轮次21；来源Leader，2026-10-28；复用Worker `47a2651c-e420-4218-b4c6-454837cd33fd`。

入口：[Runbook](../../../../docs/ROS2迁移步骤.md#usage)、[规格](../../../../.trae/specs/w8-validation-recovery/spec.md#round21)、[第20轮审查](../round-20/review.md#round20-review)、[自主权限](../../../README.md#executor-autonomy)、[观测分级](../../../README.md#run-tiers)。

## 1. 目标与裁定

第20轮在完整窗口下正式复现单向发现形态：pub-first时pub看到sub而sub看不到pub。Leader裁定本轮**不进UDPv4**——UDPv4只影响数据面，断点在发现通告的单向性，发现不通则任何数据面配置都无法送达。

本轮回答两个问题：
1. 该形态在同一boot内是否**稳定复现**（重复pub-first）；
2. 该形态是否**随启动顺序翻转**（sub-first时sub看到pub而pub看不到sub）。

若B翻转，"后启动者看不到先启动者"规则在当前boot成立；若B双侧匹配，形态具时变性，须重新评估。

## 2. T1预算与条件

整轮45min monotonic；T1最多2次、每次≤30s、累计≤60s；最多2个ROS participant；普通用户；独占`/tmp/agc-w8-validation-r21-*`。

固定条件（除显式变量外）：当前boot、`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`，不设`FASTDDS_BUILTIN_TRANSPORTS`/RMW/LD_PRELOAD/profiles/static peers；只source Jazzy，不source项目install；topic `/agc_r21/chatter`，RELIABLE/VOLATILE/KEEP_LAST depth10；沿用第20轮已验收的回收锚定（anchor+budget+1.5s）、BaseException落盘、运行中maps/stat采集。

- **A（T1#1，必做）**：复用第20轮A形态——pub先建endpoint、sub后起，各8s观测窗。判据同第20轮。
- **B（T1#2，必做）**：唯一变量为启动顺序——sub先建endpoint、pub后起，其余与A完全一致。

有效结果不重跑；仅启动前0 participant异常且根因明确时按协议修复一次（保留原件、计入尝试）。

## 3. 每例必存

完整argv/环境/双侧events/result/graph/matched/endpoint info/GID/type/hash/QoS/heard、运行中maps/stat、真实RC/回收、窗口配对时钟。另在**每例双侧进程存活期间**用T0只读方式采集`/proc/net/udp`与`/proc/net/udp6`中本进程监听的发现端口（domain0预期段7400±），记录PID/端口/绑定地址，不读`/dev/shm`内容、不抓包、不改系统配置。保存boot btime/uptime确认同boot。

## 4. 离线研究（T0，同轮交付）

用本机Fast DDS 2.14.7与Jazzy rmw实现（`strings`/`nm`/只读源码/本地文档）回答：LOCALHOST范围下participant发现通告走哪个传输（UDPv4 multicast/unicast还是SHM）、默认发现端口如何由domain决定、通告是否单播回执。给出有来源的判读边界，不凭记忆；若无法确定，明确标注未知，不阻塞A/B。

## 5. 判读

- A复现单向且B翻转：规则"后启动者看不到先启动者"成立，下一轮进入发现通告/locator分支。
- A复现单向且B仍pub可见sub：形态与顺序无关，指向固定方向性（如通告路由/端口绑定），需locator观测下钻。
- A或B双侧匹配/送达：形态具时变性或A为偶发，须增加重复次数评估发生率，不得单例升级。
- 任一例invalid：只报invalid，不解释为形态变化。

## 6. 交付与边界

新根：`experiments/w8-validation/20261028-one-way-discovery-recheck-r1/`。保存claim/end配对时钟、离线研究来源索引、端口观测原文。partial/invalid/valid分开标注。

Worker只写新根、本轮report、CURRENT、tasks/checklist round21勾选；旧证据/归档只读；第20轮探针/驱动复用不改。Leader将在所有文档写入后刷新baseline/receipt；领取逐项复核，未知漂移停止。禁止构建、GZ/PX4/GUI/headless、抓包、读dev-shm内容、共享清理、系统/网络/库/时钟配置、root、daemon、UDPv4/传输配置变更。

首次封存不`--force`，独立核对manifest/tar/retrieval/源根逐文件一致。完成后CURRENT待审查并通知Leader；不自行开下一轮。S2/S3/S4、gate/headless/科研结论不变，整链不归档。
