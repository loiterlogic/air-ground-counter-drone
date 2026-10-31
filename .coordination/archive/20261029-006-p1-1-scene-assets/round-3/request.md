# P1-1 · round-3 追加授权与返工

<a id="request"></a>
## 来源与裁定
来源：Leader 2026-10-29 独立审查 round-2 差异、原始日志、截图与进程后裁定。用户观看GUI后的布局意见保持有效，但 P1-1 **尚不能验收**：主场景终态未达成。

## 已核实发现
1. 三图几何检查由 Leader 独立执行 PASS；yard 配置无 pole，minimal 保留双柱；中央 19 实体/44图元；`<scene><grid>false</grid>`。
2. 原截图只有偏斜一角，不能证明地图整体呈现。需固定 world `<gui>` 相机预设或查同版官方可复现方式，取得整体标准俯视/斜视截图；不再用累积 `/gui/move_to/pose`。
3. 原 full 日志 141–143 行：`air_perception` 因 `seed` 参数由 LaunchConfiguration 字符串注入、节点要求 integer 而退出。先按项目内 launch 已有整数参数注入方式修复（如 ParameterValue），不得忽略该错误。
4. 原日志多个节点有 FastDDS SHM `open_and_lock_file failed`；有两组 yard 世界 launch（PGID 31819、33567）和桥，第一组未完全退出。禁止继续叠加实例。
5. round-2 实际 GUI 世界冒烟 5 次，超过首轮 2+round2 2 次的预算；本轮先记录偏离，不重跑无必要的世界冒烟。

## 白名单（在既有基础上明确）
- 继承 round-1/2 白名单。
- 允许 `src/agc_sim/worlds/agc_world.sdf` 的 GUI 相机/显示配置（不改物理、光照、传感器系统、spherical coordinates）。
- 允许 `src/agc_perception/launch/**` 修复 seed 参数类型这一同根因相邻问题。
- 允许 `.coordination/**`、`experiments/demo/`、`/tmp/agc-p1-1-*`。
- 不改状态机、安全阈值、终态判据、9消息ABI、唯一执行口，不git commit。

## 执行顺序与预算（本追加轮）
1. **先只清理本任务已核实的遗留进程**：round-2 报告的 PGID 31819/33567 及其后代，按 PID/PGID 验证归属后 SIGINT→必要时SIGKILL；不得终止未知进程。确认无本项目 GZ/桥/launch/PX4/Agent残留。仅在无ROS进程后，记录并按已验证的 `/dev/shm/fastrtps_*` 归属清理本任务DDS残留；不得无差别清他人资源。
2. 修复 air_perception 的 seed 类型，增加最小离线回归；局部构建 agc_perception/agc_sim/agc_task（最多1次）。
3. **GUI full attempt A**：`world_map:=minimal`、s04、full、seed0、`px4_run_root:=/tmp/agc-p1-1-px4-minimal-<unique>`，隔离PX4状态，等待air odom新鲜再显式start，墙钟≤360s。
4. 仅当A完成并清理后，**GUI full attempt B**：`world_map:=yard`，同参数、独立`px4_run_root`，墙钟≤360s。
5. 两次均保留launch/start/state/odom/summary/PID和截图；按本任务PID完整清理。GUI必须可见。
6. 报告区分：代码故障、残留污染、PX4/EKF、地图几何，不得再仅凭一次失败说“与地图无关”。

## 验收
- seed 参数类型错误消失，无遗留进程污染；两次隔离对照有明确结果。
- yard 达 `TRACKING_SUCCESS/tracking_milestone`，C9与几何manifest存在；才可继续验收P1-1。
- 若 yard 仍失败，完整证据保留，P1-1不通过，不得改写完成标准。

## 停止条件
最多上述 2 次 GUI full attempt、1次局部构建。A/B均失败或 yard 未成功即停止T2，提交假设台账与最小下一步授权，不继续空转。
