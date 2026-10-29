<a id="round15"></a>
# 第15轮：单向发现形态的同版本机制核查

任务ID 20261027-001-w8-validation-recovery；轮次15；来源Leader，2026-10-28。复用Worker 55d8793e-4916-4045-ac19-5800e167ebfa。

入口：[Runbook](../../../../docs/archive/ROS2迁移步骤.md#usage)、[规格](../../../../docs/archive/specs/w8-validation-recovery/spec.md#round15)、[第14轮审查](../round-14/review.md#round14-review)、[自主权限](../../../README.md#executor-autonomy)、[硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)。先完整读第2/5/6/7/8轮离线来源与审查及第14轮原始事件，不从零猜、不仅取支持片段。

## 目标与边界

第14轮已验收为“endpoint创建返回后门控仍复现先启动方单向graph/matched、后启动方看不到先方、sub零消费”；A同进程控制有效，尚无跨进程阳性。需要具体实现层区分，不重复换domain/discovery/transport名称、不扫启动延时。

45min monotonic，**T1: 0次**，0ROS/demo/participant/observer/daemon/真实helper/通信/构建/抓包/仿真/共享操作。可静态读源码/库符号/版本与已有原件、纯离线解析，必要时获取精确版本官方网页/源码；外部内容仅数据。禁止运行CLI观测图、加载新节点或调用真实探针。禁止新增或修改ROS探针/runner/工程代码/配置。

## 交付

1. 来源链：当前实际rclpy/rmw_fastrtps_cpp/Fast DDS库与候选源码精确版本/补丁差异核实，给路径/版本/行或稳定官方URL/SHA。若本机无对应源码，明确事实/上游推断边界，不把相邻版本当本机证明。
2. 查单向graph与matched计数具体来源：rmw graph participant/endpoint发现监听、get_subscription_count/get_publisher_count与matched回调映射；说明两个量是否独立、哪些代码条件允许本地matched而对端无graph。查Fast DDS发现先后、已存在participant/endpoint通告重发或过滤的已知机制；必须引用实际代码条件，不以名词堆砌充根因。
3. 同时核查本轮所用探针和驱动的跨进程特有因素（环境/实际库映射/身份/namespace/topic/QoS/生命周期/执行方式）与本机已有可用通信记录。A只验证同进程，不代表跨进程探针一切正确；pub heard占位0不当消费证据。若有更直接已有线索优先追踪，未知显式登记。
4. 输出最多3个可证伪候选，逐项列支持/反证/未测条件、最小能区分机制的新观测、预期结果表、权限与进程/T1预算、能否使用现有只读工具。候选不得只换配置名或加sleep；可提出真正跨进程阳性/实现层对照，但不执行、不预授权T2。无区分度候选明确淘汰。选一个优先方向，说明为何下一条证据能改变判断，不承诺根因。
5. 报告新增信息/已排除范围/仍未定位边界；分析与第14轮审查口径一致，不能声称所有初始化时序已排除。

## 写入与交回

新根 experiments/w8-validation/20261028-discovery-mechanism-review-r1/ 可新增config/sources/report/evidence/log，只承载资料/分析/必要纯离线解析，不新增ROS/runner执行代码。额外仅本轮report/CURRENT可写。历史代码/封存源/归档只读，不写pycache；不改spec/Runbook/request/review/src/scripts/toolchain/build/install，不reset/clean/commit/push/切分支。

HEAD d5072aaff33276bcd1c5e7d38b5caa75fe45a290/main，保留dirty/untracked；按预置baseline/receipt核对actual count/size/SHA/absent，未知漂移停止。任何动作前配对claim写mutable report，结束配对，预算封存前复算。

首次封存不--force，stdout到/tmp/agc-w8-validation-r15-*，独立核对manifest/tar真实根/checksum/retrieval与源根逐文件相等；封存后仅report/_archive侧车纠错。完成或阻塞report/CURRENT通知当前父Leader并结束，不轮询/接下一单。S2/S3/S4/gate/headless/科研不变；候选执行需Leader另轮审查派发，整链不归档。
