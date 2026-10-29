<a id="round14-review"></a>
# 第14轮独立审查

任务ID 20261027-001-w8-validation-recovery；来源Leader，2026-10-28。

亲自读完整回报、分析、参数契约证据，逐行解析五端事件/result，核对三份drive与门控/存活证据。A正控制sent14318/heard14316、matched1/1，负控制均零matched/零heard，QoS负控制有incompatible；6个endpoint标记位于init/node之后。B先pub matched峰1/graph1:1，后sub matched0/graph_pub恒0；C先sub matched峰1/graph1:1，后pub matched0/graph_sub恒0。接收端heard均0。每次真实RC/result/probe_end为0、invalid/problems空；后方process_entry均晚于先方endpoint_created，门控checker0、实时存活成立。

独立复算1865保护项无漂移，55 artifact size/SHA正确；tar与源根56文件逐字节相等，SHA 9c6b4bda754f8e0c2f54b19c17c230d292a1b7e3e0652595450d107b7cf2d082与checksum/retrieval相符。T1三次span总25.814489s，mono整轮143.440378481s合规。未构建/启动ROS/仿真。

裁定：第14轮A/B/C探针级诊断取证验收通过。旧单向形态在endpoint创建返回门控后仍复现，通信未恢复；不升级S2。

判读修正：回报“只是启动太早被排除”“等待条件强于脚本后1s”过宽。事件条件语义更明确，不保证实际延迟更长，更不证明DDS发现完成。精确结论是：不能用“后方启动时先方endpoint尚未创建”解释本轮；更广义participant发现/SPDP/SEDP时序仍未排除。同进程A有效不排除所有跨进程专属探针/环境差异，不能称B/C绝非探针失效。pub不执行消费回调，零消费以sub heard=0为证，不将pub heard占位0当独立消费观测。旧封存分析不回改，本审查限定其读法。

过程pycache发生于新根且封存前删除已披露，属于指令偏离；无旧源根污染证据，不因此否定真实结果。保留披露，不追溯掩盖。

下一步第15轮仅同版本实现/既有证据机制分析，T1=0/45min；把单向发现、matched、零数据三层联系到具体代码条件，给出最小可区分候选方案，不再盲换配置名/扫延时。新真实执行需另轮授权。S2/S3/S4/gate/headless/科研不变，整链不归档。
