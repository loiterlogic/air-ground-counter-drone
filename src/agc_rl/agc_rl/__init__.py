"""agc_rl —— 地面 RL 接口。

- `interface`：obs / action 空间冻结（配置文件）。
- `policy`：策略加载（确定性策略，可加载 JSON 参数）。
- `inference_node`：推理节点（`ground_policy_rl`），只写 `cmd_vel_raw`。

训练产线整体留 （[ADR-0001](../../../docs/adr/0001-project-positioning-and-execution-scope.md#top)）。
"""
