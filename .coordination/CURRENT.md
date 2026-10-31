<a id="current"></a>
# 当前交接

- 任务 ID：**20261031-011-p2-1-deliverables**
- 轮次：**round-4（批次续跑；N=6 已用 3，余 3 / K=4）**
- 状态：**执行中**（round-3 阻塞已裁定：**α**；[round-3 审查](task/20261031-011-p2-1-deliverables/round-3/review.md#p2-1-r3-review)）
- 当前派工：[round-1 request](task/20261031-011-p2-1-deliverables/round-1/request.md#p2-1-r1-request)（Leader）
  · round-2 / round-3 request 由 Worker 自写 · round-4 request 由 Worker 自写（继承 [round-3 审查](task/20261031-011-p2-1-deliverables/round-3/review.md#p2-1-r3-review) 第 3/4 节）
- 回报：[round-1](task/20261031-011-p2-1-deliverables/round-1/report.md#p2-1-r1-report) · [round-2](task/20261031-011-p2-1-deliverables/round-2/report.md#p2-1-r2-report) · [round-3](task/20261031-011-p2-1-deliverables/round-3/report.md#p2-1-r3-report)
- **Leader 裁定（round-3 审查）**：
  ① **选 α**：给 `src/agc_sim/worlds/agc_world.sdf` 的 `<gui>` 块追加 `Screenshot` 插件（**白名单追加该文件**；禁触 `<scene>`/`physics`/传感器/几何真源；须过 (n) 与全部回归）。
  ② **移除 `AGC_GUI_CONFIG` 机制**（start.py 环境变量 + `gui_capture.py derive-config` 及配套测试）——α 落地后它只会静默把视角换成斜视；**取代**先前"保留为可选开关"的口径。移除受阻则改"显式拒绝 + FAQ 说明"并报告。
  ③ 交付图**只允许**来自**自然运行**；通过线 **skyband ≤0.10**。
  ④ 预算 **T2 +2 次 / +1200 s**（累计上限 **10 次 / 6600 s**）；round-4 ≤2 次。
  ⑤ 早前账目：T2 超支 1 次**追认**；`rm -f /dev/shm/*` **违规记档、禁止再犯**、不判阻塞。
- **机制定案（我复核过日志）**：`--gui-config` → gz-gui **加载两层**配置，`~/.gz/sim/8/gui.config` **后加载并覆盖**相机位姿 → 斜视 skyband 0.2848（H-C）；**自然运行**走 SDF `<gui>` 块，位姿确为**正俯视**，但该块 9 插件**不含 Screenshot** → 0 帧（H-D）。H-A/H-B/H5（命中机载相机）**均证伪**。
- **用户裁定（2026-10-31）**：① 用户确认默认运行所见 = **正俯视平面图**（与实测一致）；② **完整演示视频由用户自录**，不装工具、不合成。
- **相机事实**：world SDF `<gui>` `camera_pose = 0 0 118 0 1.5708 1.5708`（正俯视，北朝上）；skyband 标定：俯视 ≈0.06、斜视 0.20–0.36、离屏正俯视渲染 0.00。
- **剩余计划**：round-4 = α 落地 + 自然运行取三图/GIF + README 换真图（T2 ≤2）；round-5 = 干净环境验证 ≥1 轮（T2 ≤2）；视频等用户文件。
- 上一任务（已结档）：[20261030-010 P1-4 baseline closure](archive/20261030-010-p1-4-baseline-closure/round-3/review.md#p1-4-baseline-final-review)，结论 **PASS_WITH_NOTE**；P1-4 缺口已在 README「已知边界」登记。
- **基线事实**：HEAD `f3e88f6`；P1-1…P1-4 全部产物已入库（`07eda37`）。
- **演示口径**：`full + yard + s04 + observe_yaw_mode=target`；target 是显式 oracle 指向臂，不等于真实视觉识别。

**迁移 workstream 暂停，W8 不再接单**（[PAUSED](../docs/plan/PAUSED.md#paused)）。