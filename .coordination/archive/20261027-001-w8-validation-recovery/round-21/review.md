<a id="round21-review"></a>
# 第21轮独立审查

任务 ID 20261027-001-w8-validation-recovery；来源 Leader，2026-10-28。

## 1. 独立核验

亲自读取round-21 report/analysis、A/B双侧events/result、端口观测、离线研究、基线与归档。独立重算tar SHA `419a01cbb8c1a0bf39604e3bd65311820d3d76a3c05882e23d903df0c48e5fbe`，55成员与源根逐文件一致；43610项受保护文件漂移0。

双侧事件重算均seq连续、result存在、真实RC均0：
- A pub-first：先起pub graph/endpoint-info/matched=1，发布12；后起sub graph/endpoint-info/matched=0，32样本heard=0；
- B sub-first：先起sub graph/endpoint-info/matched=1但heard=0；后起pub graph/endpoint-info/matched=0，应用层调用发送8但无DDS匹配。
两例后起窗口均完整包含于先起窗口，均未被硬上限截断，故结论不是回收竞态、不是角色固定方向。

T1 2/2、累计25.367s；离线守卫9/9。端口T0存在闸门缺陷：快照早于后起方endpoint_created 543ms，逐PID只覆盖先起方，因此端口数据不支撑方向性结论；Worker已修复但未重跑。离线研究正确纠正7411是同一participant的user端口，不是第二participant；确认默认BuiltinTransports为UDPv4+SHM，LOCALHOST环境解析位置及具体交接仍部分未知。

**第21轮取证验收通过，但端口T0交付不完整**。A pub-first与B sub-first共同证明：在当前boot、domain0、LOCALHOST、默认传输下，**不对称跟随启动顺序而非pub/sub角色：后启动参与者看不到先启动参与者**。这是稳定性/方向性事实（各顺序当前n=1；pub-first另有第20轮同结果，合计n=2），不是根因，不是发生率，不是UDPv4/SHM结论。

## 2. 三项裁定

1. **下一轮先重复并补端口，不立即进locator/Fast DDS日志分支**：pub-first已有第20/21轮2/2；sub-first仍n=1。第22轮做一次干净sub-first重复，并做一次pub-first延长窗口测试，既补sub-first n=2，又检验8秒后是否只是慢发现。若延长窗口仍完整单向且两顺序复现，第23轮再开发现通告/locator日志分支；不再无信息重复相同8秒样本。
2. **端口观测必须重采**：采用已修复的endpoint_created fsync闸门，快照覆盖双PID；每例至少保留endpoint创建后一次、结束前一次的逐PID归属。端口观测是诊断证据，不能回填第21轮方向结论。
3. **端口解释固定**：domain0/participant0中7410为metatraffic unicast、7411为同participant user端口（不是第二participant）；7400才是multicast metatraffic。任何端口结论必须按PID/endpoint创建时点归属，缺失即记missing。

## 3. 第22轮边界

不改UDPv4、RMW、profiles、系统网络或SHM；保持当前干净默认条件。T1#1为sub-first同窗重复；T1#2为pub-first延长后起sub窗口（约25s、先起pub约29s且不超过单例30s），仅改变窗口长度。T0补全双PID端口采样及LOCALHOST交接静态证据。若延长窗口仍无后起方发现，下一轮才显式授权发现通告/locator层诊断。

S2/S3/S4、gate/headless/科研结论不变，整链不归档。
