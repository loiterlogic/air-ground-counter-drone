# P1-3 · round-2 目标视觉可辨识返工派工

<a id="p1-3-r2-request"></a>

## 返工结论

round-1 不验收。状态/面板/时间线/终态解释均保留；仅补出口判据 5：演示实际使用的
`controlled:=true` `intruder_uav` 在 Gazebo 中必须有醒目的视觉颜色或尺寸。

## 最小范围

允许修改：

- `src/agc_sim/models/intruder_uav/intruder_uav.sdf.xacro`：仅 controlled 分支新增/修改 `<visual>`；
- `docs/plan/p1-3-任务可观测与演示呈现.md`；
- `.coordination/task/20261030-008-p1-3-observability/round-2/**`；
- `experiments/p1-3/round-2/**` 与对应 demo 证据；
- 必要的离线模型/渲染回归测试。

## 严格禁止

不得修改 controlled 模型的 collision、inertial、mass、plugin、pose、关节、PX4 接口；
不得改话题、ABI、命令者、状态机、终态、C10、安全阈值；不得修改 P1-2 起停语义。

建议：给 controlled 分支新增一个小型橙色/红色高亮 `<visual>`，不引入新碰撞几何；
若使用 mesh 或材质，先对照本机 x500 模型写法，保持渲染兼容和可复核来源。

## 证据与验收

1. xacro/SDF 展开静态检查：controlled 分支 visual 存在、醒目颜色或尺寸；passive 行为不回退。
2. collision/inertial/plugin 等禁止字段 diff 守卫通过。
3. 在 `yard/s04/full/observe_yaw_mode=target` 的 GUI 和 headless 各取得一次证据：
   - GUI 目标可辨识证据（renderer/GUI 产物或模型展开与颜色采样）；
   - headless 证明 `viz=false` 时不依赖 RViz，目标视觉属性仍在 world/model SDF；
   - 两次均 `TRACKING_SUCCESS`，且 summary C9 指标/复位无异常。
4. 重新跑 `tests/w6_geometry_check.py`，确保 3 图派生链与静态判据不受影响；完整脚本回归必须通过。
5. 更新 P1-3 出口勾选和目标视觉章节，明确“可控版实体目标”而非仅 RViz marker。

## 预算与停止

- 批次 N=6/K=4；本返工最多 2 轮，T2 最多 2 次（GUI 1 + headless 1），总墙钟 600 秒；T1 0。
- 若模型视觉无法在不改物理字段下落地，或任一运行不达终态，停止并提交台账，不再扩大范围。
- 不 commit/reset/clean，不开始 P1-4；完成后报告并置待审查。
