<a id="round3-review"></a>
# 第 3 轮独立审查

任务 ID：20261027-001-w8-validation-recovery；轮次：3；审查日期：2026-10-27；审查者：Codex。

## 核查依据

- 读取本轮 `request.md`、`report.md`、`CURRENT.md`、第2轮审查和协调协议；未启动 ROS、构建或仿真。
- 独立复算本轮 `config/evidence_manifest.json` 的 15 个 artifact：源根 size/SHA 全部相符；归档 tar 对应 15 个成员全部相符，另有归档生成的 manifest 成员；`.tar.sha256` 与 retrieval sidecar 的 `ee1beb75a5a0805d10b731abc6c7700d0ab4e24bfd08d81079e313d9f4a05c3d` 相符，16 文件、0 mismatch。
- 核对 A/B 三份 result JSON、两份运行日志和追加式 events：A 正对照 `heard=6/matched=1`，neg1 QoS 不兼容事件=1 且 matched=0，neg2 不同 topic 双侧不可见；B sub 侧 `matched=1/graph_pub=1/heard=0`，pub 侧全程 `matched=0/graph_sub=0/heard=0`。结果与报告一致。
- 检查探针源码：仅使用 rclpy/std_msgs；无 `subprocess`、进程杀除、`/dev/shm` 读取、共享资源清理；`py_compile` 通过。运行日志记录 3 个 PID/PGID、退出码 0、残留 0；T1 总墙钟 14.138 s，2/2 次均在单次 30 s、总 90 s 内。
- 第2轮结论和本轮状态边界保持：没有把 B 混合形态解释为通信根因、通信恢复或 S2 通过。

## 验收结果

| 条件 | 结果 |
|---|---|
| 领取基线、1138 路径核对、白名单与预算 | 通过；无未知漂移，6.50 min < 45 min，T1 2/2 合规 |
| A 正/负控制有效 | 通过；证明观测器能区分同进程匹配、QoS 不兼容和不同 topic |
| B 跨进程观测与原始证据 | 通过；单向发现/匹配/零消费由双方独立计数和事件支持 |
| 结果判读是否克制 | 通过；报告明确指出不落既有表格、保留启动时序和单次运行限制，未强行归因 |
| 过程边界、进程回收、封存与取回 | 通过；无构建/仿真/抓包/共享清理，归档与 retrieval 0 mismatch |
| 协议状态与叫醒守卫 | 通过；CURRENT 为待审查，DSH 未重跑、未扩诊断；链达到 4/4 后未绕过守卫 |

## 结论

**第 3 轮分层证据已验收。** B 的混合形态不是本轮失败，而是需要下一轮控制变量的有效发现；它只能说明在一次 sub 先启动 1.017 s 的跨进程运行中出现单向 graph/matched 与零消费，不能区分启动时序和结构性发现不对称，也不能定位 SHM、UDP、权限或 QoS 根因。通信仍未恢复，S2/S3/S4、gate、headless 授权和科研结论不变。

下一轮保持同一任务 ID，执行 pub-first 与 sub-first 的启动顺序对照，其他配置、topic、QoS 和探针固定；以双侧 matched/graph/heard 判读是否随顺序翻转或保持同侧。该返工派工见 `round-4/request.md`。任务链仍未到整链结档条件。
