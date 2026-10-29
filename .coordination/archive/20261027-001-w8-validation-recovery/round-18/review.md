<a id="round18-review"></a>
# 第18轮独立审查

任务 ID 20261027-001-w8-validation-recovery；来源 Leader，2026-10-28。

## 1. 独立核验

亲自读取完整report/analysis、A/B/C0原始events、stock日志、command/env/maps、离线守卫、基线与归档。独立重算tar SHA为 `cd441c3729c6e7ad0abcdca8680d6105a4fb15d23c431db13420f80fc6472c00`，66成员与源根逐文件一致；43448项受保护文件无漂移。

原始events独立重算：
- C0兼容同进程相位有matched且heard为正；不同topic和不兼容QoS负控制符合预期。
- A/B事件流seq完整、单PID，均有`matched_event`；graph_sample持续出现matched=1；所有heard计数为0。
- endpoint info原文含对端类型、type hash、RELIABLE/VOLATILE及实际GID；两方向无incompatible事件。
- stock侧A发布5条；B的rclpy发送12条而listener无`I heard:`。配对时钟支持匹配窗口内仍有多条发布。

预算T1 3次、32.718s、整轮701.094s，合规。两次失败C0尝试均保留；一次启动前无participant，一次新代码API错误，未隐瞒。派生计数格式化缺陷已从append-only原始events重算，没有追加T1。

**第18轮取证验收通过。** 它首次把故障从“发现/匹配”下移为“匹配后的跨进程数据面/回调路径”，但“数据面”仍是层不是根因。

## 2. 三项裁定

1. **maps缺陷**：本轮maps在exec前采集，不能作为运行时库加载证据；静态`DT_NEEDED`只作补偿。验收原始通信判据不依赖它。下一轮把“exec后/运行中maps与stat”列为必存证据。
2. **C0尝试口径**：保守按request计3次用尽，不追溯追加额度；启动前0 participant异常允许的修复已实际用过，新代码错误计尝试。离线8/8与45/45守卫认可，但不能替代真实控制。
3. **下一分层**：rclpy↔rclpy同boot默认跨进程对照解决“任何进程间数据面”与“mixed pair专属”之分；随后纯UDPv4是数据面单变量，检验SHM路径。纯UDPv4改变进程可见配置，需显式授权，本轮不擅自执行。

## 3. 第19轮方向

固定当前boot/domain0，先以同boot rclpy↔rclpy默认传输建立跨进程基线；条件执行stock→rclpy纯UDPv4单变量及必要反向。不得把恢复解释为工程验证；S2/S3/S4、gate/headless/科研不变，整链不归档。

详见 [第19轮派工](../round-19/request.md#round19)。
