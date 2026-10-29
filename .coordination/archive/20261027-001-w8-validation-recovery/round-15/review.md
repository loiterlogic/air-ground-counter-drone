<a id="round15-review"></a>
# 第15轮独立审查

任务ID：20261027-001-w8-validation-recovery；来源Leader，2026-10-28。

## 1. 验收结论

**第15轮验收通过（静态机制核查交付）。**本轮属于 T1=0 的只读机制核查，不是通信恢复验收，也没有新增实测排除。

独立核对结果：

- 回报、来源链、事实 JSON、两份原始证据日志与分析报告相互一致；
- 本机版本与库身份记录完整，graph 计数符号、GraphCache 符号、`ros_discovery_info` 字符串归属及第14轮五端环境均可由原始日志复核；
- 报告正确区分 graph/matched 两层实现入口，但没有把符号/字符串升级为唯一数据来源或根因证明；
- typehash、`ros_discovery_info` durability/history、GraphCache 拒收条件及“未送达/未接受”仍明确标为未知；
- domain37 已与 ADR-0077 的 domain0 整链话题成功记录合并判读，A“仅换 domain 数字”淘汰理由成立；
- endpoint-info API 当前调用数为0，报告正确承认 B 必须先授权修改/扩展探针；后启动方 endpoint info 为空时无区分度的限制已写明；
- 未执行候选，未启动 ROS，未修改旧探针、runner、工程代码或配置。

封存独立核对：manifest 声称 7 个 artifact、8 个归档成员，源根 glob 得到对应 8 个文件；tar checksum 为 `d3045dfa019c354c4f6015eb83ef186a559134c1980cf554ec48f6306e52205f`，retrieval 记录 `verified=true`、`files_checked=8`、`mismatches=[]`。round15 基线 receipt 为 1927 项，HEAD/branch 与派工一致。未发现封存后源根写入证据。

## 2. 过程偏离与影响

Worker 如实披露领取状态曾漏更新：实际核查开始时 CURRENT 仍为“待执行/尚未领取”，之后按原 claim 补记为“执行中→待审查”。这违反交接顺序，但未发现重复派发或证据篡改；不影响已落盘静态事实的可复核性，保留为过程偏离，不追溯修饰。

两次精确版本源码网络获取失败已记录，且没有以邻近版本或记忆补造。该缺口限制机制结论，但不构成阻塞，因为本轮交付目标允许明确登记未知并提出可证伪观测。

## 3. 裁定边界

- **A：淘汰。** 仅改变 domain 数字，相对第8轮 domain0/39 结果没有新增区分证据；不得以 p3-r2 的混合冷启动矩阵把 domain37 当可靠阳性。
- **B：授权进入下一轮，但仅授权离线探针扩展。** 允许在新根复制/扩展现有探针以采集 `get_publishers_info_by_topic` 与 `get_subscriptions_info_by_topic` 返回的 topic type、type hash、QoS 实配及缺失/空结果状态；允许纯离线参数/契约测试和报告，不授权 ROS 启动、真实 T1、旧探针/历史证据修改或任何配置切换。后续真实执行必须另轮审查派发。
- **C：本阶段不开发新工具。** 该候选机制上与方向翻转形态相容，但 durability/history、GraphCache 接受条件及可用内省路径均未知；先获得 B 的区分结果。若 B 结果为无区分度或排除类型层，再以新轮静态可行性评估决定是否为 C 开发最小工具；不能把 C 当前记为已验证根因。

## 4. 未改变事项

S2/S3/S4 继续关闭；gate 仍为 `not_evaluable_as_specified`；headless 与科研结论不变；整条四步任务不归档。第15轮结论仅表示机制核查交付通过，不表示通信恢复或工程可用配置成立。

## 5. 下一步

下一轮应先完成 B 的离线探针扩展与契约验证，明确 API 返回字段、空结果/异常路径、跨进程两端身份与事件关联方式，以及真实运行前的判读表。离线轮通过后，才考虑另轮 T1 实测；C 保持 deferred。
