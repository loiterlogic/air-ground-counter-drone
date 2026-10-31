# P1-2 · round-2 阻塞裁定与续作派工

<a id="p1-2-r2-request"></a>

## 裁定

1. **viz 重复注册属实**：`full` 路径 `_compose()` 末尾 `_viz_actions()` 与顶层第二个 `OpaqueFunction` 同时生效。
   采用**根因修复**，不允许 `run_demo.sh` 旁路复制 RViz 编排。
2. **扩大白名单**：允许修改 `src/agc_task/launch/w6.launch.py`，删除 `_compose()` 末尾的
   `actions.extend(_viz_actions(...))`，保留顶层唯一 `_viz_actions` 注册；必须加 full/lightweight × viz on/off
   的 T0 动作计数回归，保证三节点各 0/1 份。
3. **GUI 证据口径**：P1-2 不要求通用桌面截图工具。必须同时取得：
   - 本 run Gazebo GUI 非 headless 的进程/launch 证据；
   - 本 run OGRE renderer 证据（复用 `gui_renderer_evidence.snapshot/probe/combine`）；
   - 本 run X11 窗口存在证据（`xdpyinfo` + `xwininfo -root -tree`，绑定启动窗口名称/时间并保存原始输出）；
   - 单个 RViz2 + viz_markers + world_frame_tf 的进程/launch 证据。
   若能由 Gazebo Screenshot 插件取得真实帧则附；不能取得不因此判 FAIL，但不得称有截图。
4. round-1 因工具轮耗尽没有报告、没有真实运行，不能算出口进展；本轮直接续作，预算沿用原批次余额。

## 继续交付

- 完成 `run_demo.sh` 与必要的 `scripts/demo/**`，实现原派工单全部入口与证据闭环。
- **先写并落地 GUI↔headless 等价预登记**：同 scene/seed/backend/map/observe mode；终态与 reason 必须完全一致，
  C9 两指标必须一致且为数值，`reset_failed` 均 false，关键任务轨迹判据可比。
  duration_s 是含启动/关闭的进程墙钟，不应当作仿真任务时长强行等值；若要比时长，使用同 run 的
  `sim_end_s-sim_start_s` 或明确任务窗口，预登记相对容差 **≤20%**，RTF 仅报告不设等价硬门。
  不接受只写“终态相同”就宣称 C3 全指标等价。
- doctor 故意少 source 的故障测试应通过隔离 env 调底层模块；`run_demo.sh` 自身负责自动 source，
  不能把“脚本自动 source 成功”误写成故障提示已验证。
- stop 必须能回收另一个终端启动的实例；Ctrl-C 测试必须向监督进程真实发 SIGINT，而非直接调用 stop 代替。

## 白名单补充

在原白名单基础上仅增加：
- `src/agc_task/launch/w6.launch.py`
- `src/agc_task/test/**`（仅 viz 注册回归，如选择放此处）
- `scripts/gui_renderer_evidence.py` 及其既有测试（仅复用时发现确定性缺陷才改，须登记）

其他边界、契约、预算、停止条件不变。T2 余额 **2400 秒 / 8 次**（round-1 消耗 0）。
完成后必须写 round-2/report.md、更新 CURRENT 为待审查并通知 Leader。
