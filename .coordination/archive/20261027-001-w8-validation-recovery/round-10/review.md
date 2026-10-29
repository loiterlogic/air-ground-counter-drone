<a id="round10-review"></a>
# 第10轮独立审查

任务ID：20261027-001-w8-validation-recovery；轮次10；来源Leader，2026-10-28。

亲自读完整驱动、15例回归记录、11项探针检查、回报与CURRENT。独立逐项复算1322保护项无漂移；14 artifact size/SHA相符，tar与源根15文件逐字节相等，tar SHA 277e7c7b49f42e142c3bae32c0536d19cd8d7999b8e83bf008f9df6757baa959与checksum/retrieval一致。未运行ROS/构建/仿真。

## 已通过子项

A/B/C引入有限poll等待、统一收尾框架；新增门控后PID/starttime/Z检查；默认真实运行拒绝路径；event_name修复的真实Recorder/pub/sub/destroy调用离线检查。15例结果支持其各自已断言的行为，不扩展为未测边界通过。

## 未通过与独立反例

1. validate_side在进程已结束后仍容忍坏末行（369行parse_events partial只记录不拒绝），result缺少invalid_reasons时get得到None并放行。Leader用临时目录构造“合法probe_end后追加{broken，result只有pid/exit_code，stdout/stderr存在”，真实validate_side返回problems=[]。完成日志应完整解析，必填字段应显式存在且类型合法；不能把缺失当空列表。
2. send_signal在read_stat=None时仍调用os.kill(pid,sig)（151–164行），身份未建立不得降级盲发单PID；reclaim组清扫213–216行直接killpg也绕过身份检查。Leader使用mock拦截真实函数：read_stat=None时确实请求kill(123,SIGTERM)。本审查未向真实PID发信号。组leader退出后的成员归属需基于已记录的自有组/成员证据，不凭可复用数字盲杀。
3. 门控helper subprocess.run timeout固定5s（702–703行），未min到stage截止/回收预留；gate可在截止附近成功后继续运行helper并启动第二方。所有等待及第二方启动必须检查共同剩余预算，增加helper卡住/迟到标记测试。
4. 门控失败/存活失败/超时路径validate_side传None（638/688/719/742等），即使reclaim已获得returncode仍丢弃；回归b_no_marker/b_ended证明wait_rc=None与实际0构成伪冲突。须回收后读取真实poll RC写入证据；回收失败要在最终invalid体现。finish_attempt排除procs PID的扫描不能掩盖尚活自有leader或group_alive_after=true。
5. 回归完整证据主要留/tmp：封存suite保留部分tail和检查摘要，但不是每例完整命令/时钟/stdout/stderr/drive.json。下轮将必要原件纳入新根封存，不能只封指向/tmp的路径。

领取时钟：report按mtime反推mono并声称与后次偏移相差-9ns，无法独立证明领取时偏移相同（本机已观察偏移漂移），不得称真实配对领取时钟或精确实测6.52min。该数为估计；本轮无实际同期mono领取证据。下轮任何动作前先保存配对claim到mutable report，再执行；历史封存不回改。

结论：部分修复通过，第10轮整体未验收；同链第11轮离线定点返工，T1=0。以上问题未闭合前不放行真实A/B/C。旧证据只读，不改变S2/S3/S4、gate/headless/科研结论。
