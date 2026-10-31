# P1-2 · Leader 验收报告

<a id="p1-2-acceptance"></a>

## 结论

**P1-2 已验收。**

## 独立核查

- round-2 GUI 原始产物确认：`TRACKING_SUCCESS` / `tracking_milestone`，GUI 非 headless、OGRE renderer、X11 窗口、单份 RViz 叠加均有证据。
- round-2 headless 原始产物确认：同场景/seed/backend/map/target 指向臂，终态一致；预登记 primary 6/6、secondary 3/3，通过 `EQUIVALENT`。
- round-3 修正确认：headless `viz:=false`，不再启动 RViz / viz_markers；完整脚本回归 136 passed。
- round-4 原始切片确认：`--duration 8` 在 `GROUND_APPROACH`、`terminal_reached=false`、`duration_branch_taken=true`、`exit_reason=duration_limit`、退出码 3；summary `terminal_state_latched=false`；进程组 confirmed、33 个进程回收、无残留。
- `tests/docs_link_check.py`：活跃范围 0 断链。

## 偏离与边界裁定

1. round-2 T2 attempt 超过派工单上限：如实保留为程序偏离，不抹除；墙钟预算未耗尽，证据未被覆盖。
2. `status` / `compare` 保留为只读辅助命令，不改变唯一执行口或 launch 单一入口。
3. GUI↔headless 的 20% 预登记容差不重开；ticks 指标余量较小，作为已知边界，不外推为稳定性统计。
4. 未取得通用 Gazebo 截图；已在产物中明确标注，不作为本 P1-2 失败项。
5. 默认演示固定 `observe_yaw_mode=target`，仍须标注为显式 oracle 指向臂，不得宣称默认 velocity 或真实视觉识别已通过。

## 验收范围

P1-2 的核心目标“一条命令起、一条命令停、失败可解释、退出无残留、产物可复核”已达成；`--duration` 主动停止分支也已闭环。

**P1-3 可发布。**
