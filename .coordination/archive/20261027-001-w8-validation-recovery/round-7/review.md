<a id="round7-review"></a>
# 第 7 轮独立审查

任务 ID：20261027-001-w8-validation-recovery；轮次：7；审查日期：2026-10-28；审查者：Leader。

## 核查依据

- 读取本轮派工、完整回报、分析、run identity、J1/K1 驱动日志、四端结果/事件、manifest、tar/checksum/retrieval、CURRENT 与规格勾选。未构建、未启动 ROS/GZ/PX4/仿真/GUI。
- 独立逐行解析四份事件流：J1 pub matched=1/sub=0，K1 sub matched=1/pub=0；后启动方对先启动方 graph 恒不可见；J1/K1 pub sent=158/119，四端 heard=0、零 incompatible QoS、exit 0、invalid 为空。matched 事件出现/解除及方向与回报一致。
- 独立核对 probe_start 环境与 `/proc` 日志：SUBNET、UDPv4 和静态peer证据相符；探针env缺ROS_STATIC_PEERS是已知采集键限制，权威来源为驱动快照，不解释为未设置。
- 独立复算15个manifest artifact size/SHA全符；tar实际根正确，解包后16文件与源根逐文件SHA全等；tar SHA `aac4341e2d4736a59fa47b81320067035e21ab715f3cec942cac5a9eb2e7421d` 与checksum/retrieval一致。
- 独立复算基线：实际/回执均1254、SHA相符；当前仅授权tasks/checklist round7勾选变化，无缺失或absent重现。
- 追加阅读项目内既有线索：ADR-0077 已记录本机非0 domain lifecycle服务数据面异常，正常整链使用domain0；本轮及此前诊断沿用39，尚未检验项目实际domain。另确认 `probe_start` 写入发生在 `rclpy.init()` 之前，只能称脚本启动标记，不能称participant已创建。

## 验收结果

| 条件 | 结果 |
|---|---|
| 基线、预算、范围 | 通过；1254/1254，领取至交接130.895 s，T1 2/2，无重跑，两种时长口径均合规 |
| 配置与启动/回收证据 | 通过；SUBNET+静态peer+UDPv4一致，脚本启动标记后延时、完整重叠、真实RC、无残留 |
| 原始结果与克制判读 | 通过；J1/K1完整复现旧形态，故障不局限于LOCALHOST分支，未强行归因 |
| 封存与取回 | 通过；manifest/tar/checksum/retrieval/root逐文件一致 |
| 授权规格变化 | 通过；round7执行勾选保留并纳入后续基线 |

## 技术裁定

1. **第7轮SUBNET候选配置诊断取证验收通过**。可排除“该形态仅由LOCALHOST自定义SHM+UDPv4分支造成”；仍不证明UDP、SHM、QoS、权限或executor根因，不恢复通信。
2. 不继续无依据地替换discovery/transport名称。项目既有记录显示非0 domain存在服务数据面异常且工程默认domain0，下一轮应优先检验domain0这一已知配置因子。
3. 后续时序口径更正：现探针 `probe_start` 在rclpy.init之前，只能作为进程脚本起点，不是DDS participant就绪证明。若需要真正participant/endpoint就绪，须另写带显式post-init/post-endpoint标记的探针；不得继续沿用“participant就绪”表述。
4. S2/S3/S4继续关闭，整链不归档，gate/headless/P1/P2科研结论不变。
