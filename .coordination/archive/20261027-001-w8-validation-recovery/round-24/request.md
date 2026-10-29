<a id="round24"></a>
# 第24轮：修复 discovery 日志机制并完成发送接收观测

任务ID 20261027-001-w8-validation-recovery；轮次24；来源Leader，2026-10-28；**必须由新Worker会话执行**。

第23轮结论：B address-only static peer为有效阴性，但port==0语义未闭合；A的XSD通过profile在Fast DDS运行时`XMLPARSER Error`，没有日志证据。本轮不重复第22轮默认样本，先解决日志机制。

## T0

- 读取第23轮 `t0-disco-log.txt`、`t0-static-peers.txt`、`xsd-validation.txt`与A stderr；从本机安装文件确定运行时XML错误的具体元素/版本原因，或找到另一种可证明启用Fast DDS discovery日志的方法。
- 任何新XML必须用本机XSD校验，并做“仅log、无transport/peer/range/profile语义变更”静态守卫；若无法得到运行时可接受的log机制，T0阻断，**不跑T1**。
- 同时闭合static peer port==0的消费语义；若无法闭合，static-peer分支保持未知，不重跑。

## T1

仅在T0通过后执行一个最小日志观测用例：pub-first、domain0/LOCALHOST/default、topic `/agc_r24/chatter`、RELIABLE/VOLATILE/KEEP_LAST10，先起pub约29s、后起sub约25s，最多2 participant。唯一变量为已证明运行时生效的discovery日志机制。保存双侧events/result/graph/matched/heard、完整discovery日志、真实RC/环境/maps/端口双时点。

T1最多2次，仅允许日志机制在启动前0 participant失败时修复一次；每次≤30s、累计≤60s、整轮45min。日志为空不能解释为“无通告”，必须判为观测不足。

## 边界与交付

禁止静态peer、UDPv4、构建、抓包、读`/dev/shm`、永久配置、GZ/PX4/GUI/headless、共享清理、daemon/root。旧证据只读；新Worker只写第24轮新根、report、CURRENT、tasks/checklist。完成后首次封存、独立取回核验、CURRENT待审查并通知Leader；不自行开下一轮。
