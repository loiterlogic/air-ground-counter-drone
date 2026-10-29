<a id="round12-review"></a>
# 第12轮独立审查

任务ID 20261027-001-w8-validation-recovery；来源Leader，2026-10-28。

亲自读取完整回报、helper原语、最终收尾核对及helper原始回归，独立复算1562保护项无漂移、274 artifact size/SHA相符，tar与源根275文件逐字节一致；tar SHA 785a424c651cd6cfac0261e22adf9d2f464395e22f3d35e786cabcf5507f2139与checksum/retrieval相符。配对claim/end复算mono243.734607927s，45min合规。

独立调用真实send_signal并mock read_stat成功返回当前身份，对expected starttime=None/0/-1/3.5/abc/True均拒绝，os.kill零调用，未向真实PID发信号。helper启动已捕获预期身份，超时回收返回值进入helper块及reclaim，helper纳入procs与最终invalid核对；正常/卡住/异常/身份失败对应离线证据支持本轮目标。未运行ROS/构建/仿真。

结论：第12轮定点离线返工验收通过，关闭本段驱动离线返工。接受短注入时限和mock的证据范围，不将其称真实通信验证。保留组成员判据局限及历史测试中间产物覆盖披露；后者不追认完整原始过程留存，不否定最终定稿回归。

下一轮仅授权同进程控制+endpoint门控跨进程双向顺序真实T1，不改最终探针/驱动。若真实异常/invalid则停止剩余例并回报；不得现场扩改已验收代码或追加运行。工程S2/S3/S4未开放，gate/headless/科研结论不变，整链不归档。
