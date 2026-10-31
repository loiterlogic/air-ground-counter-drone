# P1-3 · Leader 验收报告

<a id="p1-3-acceptance"></a>

## 结论

**P1-3 已验收。** round-1 的 6 项实现与证据，加上 round-2 的目标视觉返工，7 条出口判据全部通过。

## 独立核查

- `status_map.py` 为唯一状态/原因映射，C8 禁词守卫有效。
- 2 Hz 面板、状态跳变 timeline、summary 驱动终态解释均有 headless、GUI 和真实 PTY 证据。
- round-2 controlled `intruder_uav` 的高亮在模型实体本身，不依赖 RViz；headless run 的 `viz:=false` 且无 `rviz2` / `viz_markers`。
- 高亮为独立 fixed link，无 collision，不改变原 x500 `base_link` 的碰撞、惯量、插件和 PX4 接口；新增 link 采用极小质量以满足 SDF/物理引擎合法性，作为已记录的渲染辅助边界，不改变任务动力学判定。
- GUI/headless 两次真实 run 均为 `TRACKING_SUCCESS`，C9 指标和复位字段符合要求。
- 186 项脚本回归通过；geometry 三图通过；活跃文档断链 0。
- `true_shield_infeasible` 的一次波动已与历史同场景记录对照，未归因于本轮视觉改动，也未修改指标口径。

## 诚实边界

- 没有像素级截图；证据为模型展开、材质/颜色采样、真实 run 加载同一模型及 GUI renderer 证据，不声称有截图。
- round-1 首次失败 attempt 已保留并记录；修复后加入呈现层降级回归。
- 默认 `observe_yaw_mode=target` 仍只是显式 oracle 指向臂，不等于默认 velocity 或真实视觉识别。

P1-4 可以发布。
