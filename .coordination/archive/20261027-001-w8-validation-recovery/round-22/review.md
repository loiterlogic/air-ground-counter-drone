<a id="round22-review"></a>
# 第22轮独立审查

任务 ID 20261027-001-w8-validation-recovery；来源 Leader，2026-10-28。

## 1. 独立核验

亲自读取round-22 report/analysis、A/B双侧events/result、端口双时点观测、离线研究与守卫、基线与归档。独立重算tar SHA `2669ec6d3b22cde0d16a4a64158cd8bf75d57506e27c9a1a58b207141d76266c`，55成员与源根逐文件一致；43671项受保护文件漂移0。

双侧事件重算均seq连续、result存在、RC均0：
- A sub-first：先起sub graph/endpoint-info/matched=1、heard=0；后起pub 0/0/0、应用层发送8；
- B pub-first延长：先起pub 1/1/1、发送29；后起sub 0/0/0、**98样本heard=0**。
窗口独立重算：A 12.33/8.36s、B **29.33/25.38s**，后起窗口均完整包含于先起窗口，均未触硬上限。

端口T0缺口已修复：闸门等双侧endpoint_created fsync，每例early+late两时点，逐PID归属完整——p0=7410+7411、p1=7412+7413，各2 socket/11 inode，绑`0.0.0.0`，两时点inode不变，无7400。**端口绑定层无不对称**。T0交接点已定位：`rmw_discovery_options_t`经librcl→librmw→librmw_fastrtps_shared_cpp::create_participant结构体传入。离线守卫8/8，其中Q3b首轮失败暴露"1.5s余量让探针先退出"的真实缺陷并已修。

**第22轮取证验收通过。** 两顺序各n≥2；**25秒窗口内后起方一次都未出现先起方，慢发现在≤25s尺度排除**；端口绑定层排除；交接点从"未定位"变为"已定位"。仍限定为单boot、socket层无7400不等于无multicast流量、不是根因或工程恢复。

## 2. 三项裁定

1. **授权进入发现通告/locator机制诊断**：前置条件（两序n≥2、慢发现排除、端口对称、交接点定位）已全部满足。第23轮是本链首次机制级干预，必须是单变量、可证伪。
2. **不"优先locator而非日志"，两者互补同轮做**：locator注入回答"显式给出先起方locator后后起方能否发现"（修复方向信号）；discovery日志回答"通告实际是否发出/收到/被拒"（机制信号）。二者答案不同，单独任一都留半边未知。
3. **不扩展>25s时间尺度**：25s已覆盖Fast DDS多个lease/通告周期，继续延长信息量低。只有机制测试提示存在长周期心跳时才延长。

## 3. 第23轮边界

新根`experiments/w8-validation/20261028-discovery-mechanism-probe-r1/`。T0先定位discovery日志启用机制（env或仅log的最小XML profile）并证明profile无传输变更；定位`ROS_STATIC_PEERS`→`static_peers`语义及其与LOCALHOST range的交互。T1两次均pub-first：A仅加discovery日志（观测）；B仅给后起方sub显式initial peer指向先起方p0 metatraffic unicast。判读区分"发出未收到/收到被拒/未发出"与"注入locator后可发现/仍不可发现"。

S2/S3/S4、gate/headless/科研结论不变，整链不归档。
