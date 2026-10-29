<a id="round8-review"></a>
# 第 8 轮独立审查

任务 ID：20261027-001-w8-validation-recovery；轮次：8；审查日期：2026-10-28；审查者：Leader。

## 核查依据

- 读取本轮派工、完整回报、分析、run identity、最终驱动、四端结果/事件、manifest、tar/checksum/retrieval、CURRENT与规格勾选。未构建、未启动ROS/GZ/PX4/仿真/GUI。
- 独立逐行解析四份事件流：L1 pub matched=1/sub=0，M1 sub matched=1/pub=0；后启动方对先启动方graph恒不可见；L1/M1 pub sent=158/118，四端heard=0、零incompatible QoS、exit 0、invalid为空。
- 独立核对环境：domain0、LOCALHOST、FASTDDS_BUILTIN_TRANSPORTS未设；探针env与/proc证据一致。报告已正确区分ADR-0077的非0 domain service异常与本轮domain0 topic探针，未互相外推。
- 独立复算15个manifest artifact size/SHA全符；tar实际根正确，解包后16文件与源根逐文件SHA全等；tar SHA `4035da92369a0f998a0aafda6a4e558e0c44393b7edd7418316479217e0af63d` 与checksum/retrieval一致。
- 独立复算基线：实际/回执均1276、SHA相符；当前仅授权tasks/checklist round8勾选变化，无缺失或absent重现。

## 验收结果

| 条件 | 结果 |
|---|---|
| 基线、预算与范围 | 通过；1276/1276，领取至交接113.920 s，T1 2/2，无重跑，两种时长口径均合规 |
| domain配置与时序口径 | 通过；domain0+LOCALHOST执行，probe_start只称脚本启动标记，未冒充participant就绪 |
| 原始结果与判读 | 通过；domain0下旧形态复现，未把domain或服务异常外推为话题根因 |
| 回收、封存与取回 | 通过；真实RC互证、无残留，manifest/tar/checksum/retrieval/root逐文件一致 |
| 授权规格变化 | 通过；round8执行勾选保留并纳入后续基线 |

## 技术裁定

1. **第8轮domain配置诊断取证验收通过**。可支持domain0下仍出现该探针形态，故该形态不局限于非0 domain；不主张domain0与39统计严格等价，不否证ADR-0077的service异常。
2. **关闭继续替换domain/discovery/transport名称的配置分支**。现有观测已覆盖domain0/39与LOCALHOST/SUBNET，继续换名没有新增区分度。
3. 第3–8轮共同关键缺口是探针缺少post-rclpy-init与post-endpoint标记。下一轮允许新增独立诊断探针，先做同进程正负控制，再以先启动方endpoint创建后事件控制跨进程时序；旧探针与历史证据不改。
4. S2/S3/S4继续关闭，整链不归档，gate/headless/P1/P2科研结论不变。
