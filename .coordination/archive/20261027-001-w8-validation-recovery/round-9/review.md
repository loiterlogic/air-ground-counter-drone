<a id="round9-review"></a>
# 第9轮独立审查

任务ID：20261027-001-w8-validation-recovery；轮次9；2026-10-28；来源：Leader。

## 核查与结论

亲自读取回报（含C1/C2/C3）、run_identity、实际驱动、最终探针、门控器、A原始驱动日志/result，独立解析事件与核对1299保护项、tar与源根17文件逐字节一致；tar SHA为fa0038fead9b80b67778e34f77f5842c0347a8af5f2a0b55c558dd24771dacc5。未启动ROS/构建/仿真。

A真实wait RC=1，四事件仅process_entry/post_init/node_created/probe_end，无endpoint_created/sample。Traceback到达create_endpoint的189行，说明179–180行create_publisher已返回，失败在记录调用首参kind与字段kind冲突。最终代码改为event_name，修复后尚无真实控制验证。B/C未执行，按停止条件正确；本轮T1仅1次，不存在通信层结论。

独立预算复算：领取至结束mono=606.798097355s，wall=619.368626432s，二者差12.570529077s；Worker C2中的“12.371s余差”算术不成立，以本审查精确复算为准。wall漂移原因未查明，NTP活跃不能证明本次调整来源；无需为此改时钟。跨进程时序与预算继续使用同机monotonic。

C1/C3追加更正有效，保留历史原文及侧车更正是合规行为。A无残留字段缺失不能用B/C字段代替；本轮进程自行退出有真实wait证据，独立扫描没有持久原始记录，审查不把其升级为完整回收证据。

## 未通过项与返工

1. 同进程控制未验证，round9目标未通过；有效失败记录与封存完整性通过，不等于诊断探针验收。
2. 驱动A路径141行、跨进程214–215行直接wait，无截止时间回收；MAX_SPAN仅事后检查且A遗漏，不能保证30s边界。须在新根离线修复，正常路径和门控失败路径均记录回收完成时间，包含收尾成本。
3. 驱动A无RESIDUE/STRAY持久证据；驱动总退出0不代表探针有效。须统一真实RC/result/probe_end/invalid/残留核对与失败传递。
4. gate先方存活仅靠快照中没有probe_end，不是实时存活证明；门控通过至第二方启动前应检查自有PID/starttime，拒绝已结束或身份变化，记录证据。

Leader裁定：第9轮目标未验收，进入同链第10轮离线返工，T1=0，不追加本轮A重跑。第9轮源根和归档只读，修复在新根；离线验收后另轮派A/B/C，旧授权不滚存。S2/S3/S4、gate/headless/科研结论不变，整链不归档。
