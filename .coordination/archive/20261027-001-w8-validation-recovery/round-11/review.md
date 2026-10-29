<a id="round11-review"></a>
# 第11轮独立审查

任务ID 20261027-001-w8-validation-recovery；来源Leader，2026-10-28。

亲自读取完整回报、驱动信号/成员枚举/统一收尾/helper/门控路径，独立复算1343保护项、212 artifact size/SHA全部相符；tar与源根213文件逐字节一致，SHA 74c3709129f21b28074f412f061378ff515786fc60c39aac4f0cafc96affc2c1与checksum/retrieval相符。配对claim/end复算mono267.503145843s，45min合规；wall漂移不归因。无ROS/构建/仿真。

通过子项：完成流strict解析/必填字段、失败路径真实poll RC、共同截止helper等待、第二方前预算检查、最终残留失败传播、完整最终回归原件封存。20/16/6/11既有回归支持对应已测路径。it-01失败原件被覆盖是留痕偏离，已如实披露，片段不能冒充原件；不否定最终回归但不宣称过程全量留存。

剩余可达缺陷：helper launch后未捕获starttime/pgid，887行reclaim(hp,hp.pid,None,None,...)；send_signal162行仅在starttime is not None时比对，因此“预期身份缺失”仍发信号。Leader对真实send_signal函数mock read_stat={starttime:999,state:S,pgrp:123}，调用send_signal(123,None,SIGTERM)，os.kill(123,SIGTERM)被请求。零真实信号。helper reclaim返回记录又被丢弃，hp未进入procs/统一最终回收核对。这不满足上轮“身份缺失禁止信号、helper回收有证据”。

裁定：第11轮部分通过、整体未验收；仅同链第12轮收口helper自有身份与回收记录、缺预期身份拒绝信号。T1=0，不增加其他诊断方向。PGID/starttime成员推断保留已披露局限，不能宣称谱系证明；本次不将极端复用假设扩成额外工程。真实A/B/C继续不放行。

第12轮验收时重点检查helper超时真实路径和missing expected starttime mock；完成后再裁定A/B/C。旧证据只读，S2/S3/S4/gate/headless/科研不变。
