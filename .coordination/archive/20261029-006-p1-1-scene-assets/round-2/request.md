# P1-1 地图与场景资产 · 批次第 2 轮（用户返工要求）

<a id="request"></a>
## 来源与目标

来源：**用户** 2026-10-29 15:39 观看 yard GUI 后提出（经 Leader 转达，Worker 记录）。
范围判定：**P1-1 内的视觉布局返工**，不放宽任何功能验收判据；不另开任务，仍属 `20261029-006-p1-1-scene-assets` 批次。

用户要求三条：

1. **yard 中删除原 `pole_1`/`pole_2`**；`minimal` 仍原样保留两柱（核查基线不破）。
2. **yard 中央大块空区重做布局**，增加**障碍尺寸 / 形状 / 方向**的多样性（box / cylinder / 围墙组合），
   使中央有**可见内容**；但必须保留**地面与空中可行通道**、**C7 净空**、**碰撞 / 视觉一致**。
3. **GUI 中间的网格不需要**——查明是否 Gazebo `ground_plane` / grid visual，**只关闭网格视觉显示**，
   **不改物理 / 几何真源**。

附加：重新打开 Gazebo GUI 让用户直接观看，并保留改后截图。

## 真源与必学参照（继承第 1 轮）

- 契约硬约束（[#hard-constraints](../../../../docs/ROS2迁移交接文档.md#hard-constraints)）C3/C7/C8/C10 不变；
  9 消息 ABI、唯一执行口不变。
- [ADR-0062](../../../../docs/adr/0062-scene-geometry-single-source-and-derivation.md) 单一真源 + 按域派生（**不放松**）。
- [ADR-0023](../../../../docs/adr/0023-spawn-clearance-recalibration.md) C7 出生净空（下限 6.0 m 口径不变）。
- [ADR-0052](../../../../docs/adr/0052-sensor-and-vehicle-model-limitation-and-capability-calibration.md)
  障碍族可见性边界（新增障碍须在 z=0.48 有水平截面，否则须成文标注不可见）。
- P1-1 规格：[p1-1-地图与场景资产.md](../../../../docs/plan/p1-1-地图与场景资产.md#p1-1-goal)（yard ≤15 实体、覆盖 5%–12%）。

## 基线

- 分支 `main`；HEAD `b627043423de25e61c9ed3fb0ec8f4dd39c44d18`（**未提交**；本轮全部改动仍是工作区未提交状态）。
- 第 1 轮工作区改动见 [round-1 report](../round-1/report.md#p1-1-r1-claim)（本轮在其上继续，不重置）。

## 修改白名单（**继承** round-1，不扩大）

- `src/agc_sim/**`（本次重点是 `config/maps/yard.yaml`、`config/world_geometry.yaml`、
  `worlds/agc_world.sdf` 的**视觉**字段、`launch/world_bringup.launch.py`、`launch/world_map.py`）
- `src/agc_task/config/scenarios.yaml`、`src/agc_task/launch/**`
- `src/agc_air/config/air.yaml`、`src/agc_air/launch/**`
- `src/agc_perception/config/**`、`src/agc_perception/launch/**`
- `tests/w6_geometry_check.py`
- `docs/plan/p1-1-地图与场景资产.md`、`docs/plan/p0-1-项目完成定义.md`（仅实测回填）
- `.coordination/**` 本任务记录；`experiments/demo/` GUI 证据；`build/`、`install/`、`log/`；`/tmp/agc-p1-1-*`
- **仍不改** git 提交 / 分支；不引入外部资产；不动 `src/agc_task/src/*.cpp`（第 1 轮曾误改一处
  `scenario_reset.cpp` 注释，已回退，见 round-1 report）。

## 步骤

1. 查明 GUI 网格来源（`<scene><grid>` / `ground_plane` 的 visual），在**世界 SDF 视觉层**关闭；
   物理 / 几何真源不动，`w6_geometry_check` 的断言不受影响（新增断言验证网格关闭只影响视觉）。
2. 重做 `yard.yaml`：删 pole，中央布置高塔（cylinder）、双罐（cylinder，不同径高）、
   斜置薄板（box，薄长）、斜置块（box，厚短）、三段不同朝向围墙 + 两栋大建筑 + 东侧仓库/罐；
   **形状 ≥2 类、尺寸跨度 ≥4×、朝向 ≥3 种**。
3. 用离线几何核验（与安全层同口径）验证：八字轨迹净空 ≥0、地面走廊净空 ≥2 m、
   C7 出生净空、实体互不重叠、空中待机环带可行弧足够长。
4. 重跑 `tests/w6_geometry_check.py`（三图）；更新断言以适配 yard 无 pole（(b) 的 pole 基线只在 minimal）。
5. GUI 真实仿真复验：重开 Gazebo GUI 供用户观看；留改后截图（`/gui/screenshot`）+ 日志。
6. 文档回填；报告。

## 预算

- 批次总量（N=6 / K=4）与第 1 轮共用；本**轮**消耗：
  - 离线静态检查：单次 ≤30 s，逐次留痕（次数不作硬限）。
  - `T1`：本轮 **0 次**（不需要微观测；几何核验属离线静态计算，不创建进程）。
  - `T2`：**局部重构建 ≤1 次**（仅 agc_sim / agc_task 若需）+ **GUI 世界冒烟 ≤2 次 × 45 s** +
    **GUI 主场景 full ≤1 attempt**（若第 1 轮未用掉；第 1 轮实际只用 2 次世界冒烟、0 次 full）。
  - 第 1 轮已用：colcon 全量 1 次（39.7 s，成功）、GUI 世界冒烟 2 次（各 40 s / 55 s，均人为 SIGINT 收尾）。
- 不得 headless 真实仿真。每个 T2 attempt 留日志、PID/退出码、截图、产物路径。

## 可判定验收（本轮追加，不改第 1 轮判据）

1. `yard.yaml` **不含** `pole_1`/`pole_2`；`world_geometry.yaml`（minimal）两柱**逐值不变**。
2. `yard` 满足：形状 ≥2 类、`size` 最长/最短边比 ≥3、朝向 ≥3 个不同 `yaw`；实体数 ≤15；覆盖 5%–12%（若实测略低，须如实登记并说明）。
3. 离线核验通过：八字轨迹全程净空 ≥0 m；车→目标走廊足迹净空 ≥2 m；车/目标/己方机 C7 净空
   ≥ 各实体外伸之和；实体足迹互不重叠；待机环带最长可行弧 ≥90°。
4. `python3 tests/w6_geometry_check.py` 三图 **PASS**（含新增视觉网格断言）。
5. GUI 世界冒烟：Gazebo GUI 可启动、窗口可见、无网格、中央有障碍；留截图（PNG 真实画面）。
6. 无硬约束违规；不新增外部资产；碰撞 / 视觉同源（同一 `<geometry>` 片段）。

## 预登记停止条件（继承第 1 轮）

若 **3 个工程轮内**未完成实现和静态派生核查，或 **2 次 GUI full attempt** 后仍未得到 yard 主场景终态，
则判定当前授权内不可测 / 不可完成，停止 T2 并提交假设台账与最小追加授权；不得空转。
本轮（第 2 轮）属其中的第 2 个工程轮。
