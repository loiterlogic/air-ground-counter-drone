# P1-1 地图与场景资产 · 批次第 1 轮

<a id="request"></a>
## 来源与目标
来源：用户 2026-10-29 指定 Leader 完成 P1-1～P1-4；本单仅 P1-1，Leader 派工。
目标：按 [P1-1 规格](../../../../docs/plan/p1-1-地图与场景资产.md#p1-1-goal) 完成地图 schema、派生链、minimal/yard/open_field、world_map 选择及核查，并以 GUI 真实仿真验收主场景。用户明确要求所有真实仿真含 Gazebo/RViz/图像均以可观看 GUI 运行。

## 真源与必学参照
- [契约硬约束](../../../../docs/ROS2迁移交接文档.md#hard-constraints)，尤其 C3/C7/C8/C10；不得改变 9 消息 ABI、唯一执行口。
- [ADR-0062 几何派生](../../../../docs/adr/0062-scene-geometry-single-source-and-derivation.md)、[ADR-0023 净空](../../../../docs/adr/0023-spawn-clearance-recalibration.md)、[ADR-0052 能力边界](../../../../docs/adr/0052-sensor-and-vehicle-model-limitation-and-capability-calibration.md)。
- 先学习项目内已验证同版实现：当前 `w6.launch.py`、`world_bringup.launch.py`、`w6_composition.py`、`w6_geometry_check.py`、Nav2 参数分层惯例。只读 `reference/`，禁复制旧代码。
- [主场景定义](../../../../docs/plan/p0-1-项目完成定义.md#p0-1-main-scenario)：主场景 s04，backend full，GUI。

## 基线
- 日期：2026-10-29；分支 `main`；HEAD `b627043423de25e61c9ed3fb0ec8f4dd39c44d18`。
- Leader 已核对 `git diff --name-only HEAD` 为 0。开工再次核对，出现未知保护变化立即停止回报。
- 8 个 AGC install 包、PX4、MicroXRCEAgent 存在；`DISPLAY=:0`、`WAYLAND_DISPLAY=wayland-0`。未观察到 Gazebo/RViz/ros2 launch 进程（再次启动前复核）。

## 修改白名单与产物
- `src/agc_sim/**`（本任务相机桥/Rviz/PX4 不在本单范围）
- `src/agc_air/config/air.yaml`、`src/agc_air/launch/**`
- `src/agc_perception/config/**`、`src/agc_perception/launch/**`
- `src/agc_task/config/**`、`src/agc_task/launch/**`
- `tests/w6_geometry_check.py`，必要相邻几何测试可放 `src/agc_task/test/`
- `docs/plan/p1-1-地图与场景资产.md`、`docs/plan/p0-1-项目完成定义.md` 仅实测回填相关项
- `.coordination/**` 本任务记录；`experiments/demo/` 真实 GUI 证据；构建产物 `build/`、`install/`、`log/`；临时文件 `/tmp/agc-p1-1-*`
- 不改 git 提交/分支，不重置或清理既有改动，不引入外部资产。

## 范围决定（Leader，规格内）
1. 默认主场景采用 yard 和 s04，允许在场景登记/几何配置内为新地图配置合理出生点，但必须保持 s04 声明轴与期望终态，不能靠改终态判据造成功。
2. `minimal` 保持原 pole 几何不变；standalone 回退副本仅支持 minimal，非 minimal 走派生路径。
3. yard 障碍控制在 15 个以内；box/cylinder 采用真实碰撞，视觉和碰撞一致。
4. RViz 已属用户整体要求；本单可先为地图真实验收开 RViz，但 P1-3 正式配置留后续单。

## 批次预算
- `N=6`，`K=4`；每轮留 request/report，里程碑/阻塞/预算耗尽/契约风险才通知 Leader。
- 离线/静态检查：批次总墙钟 ≤1200 s，单次 ≤30 s；次数记账不作硬限。
- `T1: 8 次 / 240 s`（仅满足 T1 定义）。
- `T2: 1 次全量 colcon 构建 + 必要局部重构建；GUI 主场景 full 真实仿真最多 2 attempts，每次墙钟 ≤420 s；如只需世界静态冒烟，最多另加 2 次 GUI 世界启动，每次 ≤45 s。`
- 不得 headless 真实仿真。每个 T2 attempt 留完整日志、PID/退出码、截图（GUI）和产物路径。
- 同机仿真串行，不终止他人进程。构建/仿真使用上述预算，不以离线名义绕过。

## 可判定验收
1. schema 支持 box/cylinder，minimal 旧字段向后兼容；世界与派生障碍/地图/air safety/reset 几何一致，安全半径按障碍派生。
2. world_map 可选 minimal/yard/open_field；static/none 语义保持；minimal 回退一致。
3. `python3 tests/w6_geometry_check.py` 与扩展三地图核查通过，C7 净空可静态复核。
4. yard × s04 × full × seed0 的 **GUI** 仿真启动、显式 start 后达 `TRACKING_SUCCESS/tracking_milestone`；空中安全层存在可行解；产物含 summary/C9 和几何哈希。
5. 清理仅本单进程，无残留；GUI 截图证明实际可视；文档如实回填。
6. 无硬约束违规；若现有系统自身导致 yard 主场景无法闭环，保留证据并回报，不得修改任务终态或安全语义掩盖。

## 预登记停止条件
若 3 个工程轮内未完成实现和静态派生核查，或 2 次 GUI full attempt 后仍未得到 yard 主场景终态，则判定当前授权内不可测/不可完成，停止 T2 并提交假设台账与最小追加授权；不得空转。
