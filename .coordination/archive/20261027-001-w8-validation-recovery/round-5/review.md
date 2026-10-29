<a id="round5-review"></a>
# 第 5 轮独立审查

任务 ID：20261027-001-w8-validation-recovery；轮次：5；审查日期：2026-10-28；审查者：Leader。

## 核查依据

- 读取本轮派工、完整回报、分析、E1/F1 驱动日志、E1 更正 JSON、最终驱动、四端结果与四端事件流、run identity、manifest、tar/checksum/retrieval、封存后侧车、规格勾选与 CURRENT。未构建、未启动 ROS/GZ/PX4/仿真/GUI。
- 独立逐行解析四份事件流：E1 pub 158 次采样、sub 119 次；F1 pub 119 次、sub 158 次。四端 `graph` 均只见自身，对端计数峰值均为 0；四端 matched 峰值均 0、零 matched/incompatible 事件；pub sent 为 E1=158、F1=119，所有 heard=0。四份 `result.json` 与 `probe_end` 均 exit 0、invalid 为空。
- 独立核对 `rmw_fastrtps 8.4.4 participant.cpp`：OFF 分支不写 `initialPeersList`；静态 peer 注入只在 LOCALHOST/SUBNET 条件内。第 5 轮派工把 OFF 与静态 peer 组合，未实现其宣称的“静态单播发现”检验。
- 独立复算 16 个 manifest artifact 的 size/SHA，无不符；实际 tar 根目录为 `20261028-unicast-discovery-probe-r1/`，解包后 17 文件与源根逐文件 SHA 全等；tar SHA `b5a52c97047b1b7488b9517ca174096cbf5144482a4640e702f14c82918749f8` 与 checksum/retrieval 一致，retrieval verified=true、17 files、0 mismatch。
- 独立复算 1204 个基线条目：领取时基线 SHA 与回执相符；当前仅 `.trae/specs/w8-validation-recovery/{tasks,checklist}.md` 因本轮授权勾选而变化，9 个 absent 项未重现。回执 `files_count=1203`，基线实际 1204，属 Leader 元数据计数错误。

## 验收结果

| 条件 | 结果 |
|---|---|
| 任务/轮次、HEAD/branch、基线与预算 | 通过；实际 1204/1204 全核对，领取至交接 875.976 s，两次 attempt 合计按更正为 18.530 s |
| E1/F1 双端原始证据与克制判读 | 通过；两次均为对称性完全隔离，不落在预设行，Worker 未强行归因 |
| T1 范围与未执行项 | 通过；2/2、无有效例重跑，无构建/抓包/仿真/共享清理/永久配置改变 |
| E1 驱动缺陷处置 | 接受更正但保留缺陷记录；`setsid` 父 PID 导致原始 RC=127/RESIDUE=2 不可作权威值，探针自身 result/probe_end 互证 exit 0，后续扫描无残留；F1 驱动可 wait 且 RC 交叉一致 |
| 封存与取回 | 通过；manifest/tar/checksum/retrieval/源根独立复算一致，封存后源根未改写 |
| 技术目标 | 未实现“UDPv4 单播发现”检验；OFF 不消费静态 peer，故本轮只构成该配置语义的负对照，不支持 UDPv4 无效或 SHM 根因 |

## 对偏离与错误的裁定

1. **D1 规格勾选保留**：派工白名单明确允许仅勾选本轮执行事实，故这两个冻结文件的变化是已授权预期变化，不回退；下一轮基线须显式接纳。
2. **D2 回执计数**：封存回执保持原样，不改历史；审查认定正确实际数为 **1204**，回执 1203 是 Leader 元数据错误，不影响实际文件完整性。后续基线从文件实际条目生成并复核计数。
3. **E1 驱动与启动间隔**：原始驱动日志保留，权威值以探针产物与更正 JSON 为准；E1 实际参与者间隔 0.223 s 而非约 1 s，但两端有超过 6.2 s 完整重叠，且发现始终未建立，不改变本轮负对照结论。后续驱动须等待先启动方 `probe_start` 后再计时，不能用 wrapper 启动时刻代替 participant 启动。
4. **封存算术更正**：`run_identity.total_attempt_wall_s=17.137` 和封存 `analysis.md` 的 17.137 均为错误；以封存外侧车及回报的正确 **18.530 s** 为准，不重封存、不改源根。其余 graph/matched/heard 结论不受影响。
5. **Leader 派工错误**：OFF+静态 peer 的机制语义本应在派工前由已读源码识别。第 5 轮不得计为 UDPv4 单播配置验证，也不得重复同类配置包。

## 结论

**第 5 轮“受限配置语义诊断取证”验收通过。** 验收范围是原始证据、执行合规与负对照解释；**不验收 UDPv4 单播配置有效性，不证明通信恢复，不定位第 3/4 轮根因，不开放 S2/S3/S4，不结档整链**。`gate`、headless 授权和 P1/P2 科研结论不变。

下一轮应先在完整同版本实现基础上选择真正生效的发现配置，再派最小对照；不得把第 5 轮结果外推为 UDPv4 无效。
