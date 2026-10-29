<a id="round6-review"></a>
# 第 6 轮独立审查

任务 ID：20261027-001-w8-validation-recovery；轮次：6；审查日期：2026-10-28；审查者：Leader。

## 核查依据

- 读取本轮派工、完整回报、分析、run identity、最终驱动、六端结果/事件、三份运行日志、manifest、tar/checksum/retrieval、CURRENT 与规格勾选。未构建、未启动 ROS/GZ/PX4/仿真/GUI。
- 独立逐行解析六份事件流并重算峰值：G1 pub matched=1/sub=0，H1 pub matched=1/sub=0，G2 sub matched=1/pub=0；后启动方对先启动方 graph 恒不可见，六端 heard=0、零 incompatible QoS。G1/H1/G2 pub sent 分别 158/159/119，六端 exit 0、invalid 为空；matched 事件的出现/解除方向与回报一致。
- 独立核对 probe_start 环境：G1/H1 唯一实质变量是 FASTDDS_BUILTIN_TRANSPORTS=null/UDPv4，G1/G2 均未设；domain39、LOCALHOST、RMW/profiles 条件一致。驱动的 READY_BASIS、参与者启动间隔、set-m 回收、result/probe_end 和 PIDS_MATCH 交叉证据与回报相符。
- 独立复算 manifest 20 artifact size/SHA 全符；tar 实际根 `20261028-localhost-udp-abba-r1/`，解包后 21 文件与源根逐文件 SHA 全等；tar SHA `d9f53a9bca443fe808ce8d21dfbe40048d5dfcba14e55cc032bfbdf2f5503d2b` 与 checksum/retrieval 一致。
- 独立复算基线：实际/回执均 1227，基线 SHA 相符；当前仅授权 tasks/checklist round6 勾选发生变化，无缺失或 absent 重现。

## 验收结果

| 条件 | 结果 |
|---|---|
| 基线、预算、单变量与范围 | 通过；1227/1227，领取至交接194.915 s，T1 3/3，无重跑，单次与两种总时长口径均合规 |
| 正确启动就绪与完整回收 | 通过；三次先读 probe_start 再延时启动，参与者间隔1.524–1.599 s，真实RC与探针产物一致、无残留 |
| 原始证据与判读 | 通过；G/H同形，G复现第4轮两种启动方向，所有heard=0，未把变量名当实配回读、未归因SHM |
| 封存与取回 | 通过；manifest/tar/checksum/retrieval/root逐文件一致，封存后源根未改写 |
| 授权规格变化 | 通过；仅round6执行事实勾选，保留并纳入后续基线 |

## 技术裁定

1. **本轮诊断取证验收通过**。可支持：LOCALHOST 下设置 FASTDDS_BUILTIN_TRANSPORTS=UDPv4 未显示可观测改善；G 的 pub-first/sub-first 再次复现第4轮方向性发现/匹配不对称。
2. **结束“在 LOCALHOST 下切换该环境变量”这一候选分支**，无需补 H2 sub-first 来重复一个已由源码解释、且已有 G/H 同向观测的无效变量。H仅一次、无transport实配回读仍是明确限制，不能声称严格统计等价或UDP机制本身无效。
3. 该结果**不定位先启动方匹配、后启动方不可见与零消费的根因**，不证明SHM、QoS、权限或executor问题，不恢复通信或工程节点。
4. 下一步应改变真正影响rmw分支的 discovery range，检验 SUBNET 下 builtin UDPv4 与静态peer，而非继续在LOCALHOST内重复同名变量。只作进程级候选配置诊断，不修改项目默认配置。

## 结论

**第 6 轮 LOCALHOST 传输单变量诊断取证验收通过。** 不开放 S2/S3/S4、不结档整链，不改变 `gate`、headless 授权或 P1/P2 科研结论。下一轮沿用同一任务 ID 与 Worker。
