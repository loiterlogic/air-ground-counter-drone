<a id="goal"></a>
# F1 · 出生布局

来源：用户 2026-10-31 新增要求；[批次入口](README.md#plan-index)。

核对中央长方形空旷区的实际边界，双方放在相对两条短边附近，己方车机初始位置相近。先读现有 spawn/复位/PX4 启动与 standoff 实现，设计坐标和距离表，再实施。建议车/目标平面距离 ≥30 m，己方机/目标 ≥25 m，己方车机约 3–8 m；这是本批次设计目标，若中央净空无法兼容须举证回报。不得削弱 C7。

<a id="scope"></a>
## 实施边界

src/agc_task/config/、src/agc_task/launch/、src/agc_sim/launch/、src/agc_air/launch/ 内必要出生布局接线；相关场景不变量/出生核查测试。仅确有必要才改 src/agc_task/src/scenario_reset.cpp。不改地图障碍、契约与其它控制逻辑。

<a id="exit"></a>
## 出口判据

实际生效的世界 spawn、复位位置、己方机起飞参考一致；列出前后坐标/三组距离与障碍净空；三图几何核查及相关回归通过；默认 yard+s04+full GUI 到 TRACKING_SUCCESS，保留真实出生截图与终态、C9、清理证据，不能仅配置看起来正确。

验收结果：**已验收，附已知边界**（Leader，2026-10-31）。出生链、几何核查、默认配置三次有限复现、H3 最小干预与完整冒烟均通过；失败样本、共享内存越界记录和精确终态截图缺失均如实保留。见[独立验收](../../../.coordination/task/20261031-012-spawn-layout/round-3/review.md#review)。
