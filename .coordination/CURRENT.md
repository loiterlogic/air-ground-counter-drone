<a id="current"></a>
# 当前交接

- 任务 ID：**20261031-011-p2-1-deliverables**
- 轮次：**round-5 完成（N=6 已用 5，余 1 / K=4）**
- 状态：**执行中**（round-5 完成：85 m 重取三图 + 统一尺寸 + GIF 十进制口径达标）
- 当前派工：[round-1 request](task/20261031-011-p2-1-deliverables/round-1/request.md#p2-1-r1-request)（Leader）
  · round-2…round-5 request 由 Worker 自写（round-5 继承 [round-4 审查](task/20261031-011-p2-1-deliverables/round-4/review.md#p2-1-r4-review) 第 4 节）
- 回报：[round-1](task/20261031-011-p2-1-deliverables/round-1/report.md#p2-1-r1-report) · [round-2](task/20261031-011-p2-1-deliverables/round-2/report.md#p2-1-r2-report) · [round-3](task/20261031-011-p2-1-deliverables/round-3/report.md#p2-1-r3-report) · [round-4](task/20261031-011-p2-1-deliverables/round-4/report.md#p2-1-r4-report)
- **Leader 裁定（round-4 审查）**：
  ① **里程碑达成**：三图 + GIF 达标（我复核 md5 / 自算 skyband 全 **0.0000** / 自跑几何核查 PASS / 断链 0）。
  ② **三处更正**：**"用户拖相机"不能取代 H-C**（两变量独立，round-2 三帧 3 s 内仅差 0.5% 像素）；`camera_pose` 118→85 的**来源待用户追认**（否则回退）；GIF **5,095,380 B** 单位口径未写死 → 须重压 **≤5,000,000 B** 或写明 `5 MiB`（离线，不占 T2）。
  ③ **顺序**：round-5 先用 85 m 重取三图/GIF 并**统一尺寸**；round-6 再做干净环境验证（必须审"照 README 从零走通"，故放最后）。
  ④ 预算 **T2 +2 次 / +1200 s**（累计上限 **12 次 / 7800 s**）；round-5 ≤2、round-6 ≤2。
- **机制定案（我复核过日志）**：`--gui-config` → gz-gui **加载两层**，`~/.gz/sim/8/gui.config` **后加载覆盖**位姿 → 斜视 0.2848（H-C）；**自然运行**走 SDF `<gui>`，位姿为正俯视但 9 插件无 Screenshot → 0 帧（H-D）。H-A/H-B/H5 均证伪。
- **Screenshot 取的是 GUI 实时视图相机** → 用户拖拽/缩放窗口会改变截图内容与尺寸（round-4 实测）。取帧期间**请勿拖动或缩放 Gazebo 窗口**。
- **用户裁定（2026-10-31）**：① 默认运行所见 = **正俯视平面图**（与实测一致）；② **完整演示视频由用户自录**，不装工具、不合成。
- **相机事实**：world SDF `<gui>` `camera_pose = 0 0 85 0 1.5708 1.5708`（**118→85**，纯 GUI 视觉）；
  **用户已追认 85 m**（来源闭合，不回退 118）。skyband：俯视 ≈0.00–0.06、斜视 0.20–0.36。
- **已交付（round-5 定稿）**：`docs/plan/assets/demo-start|tracking|terminal.png`（**统一 831×952**，
  skyband 全 **0.0000**，t≈43.0/55.4/59.5 s；md5 `cd04e0cb…` / `29a552ce…` / `8e7260a4…`）
  + `demo.gif`（9 帧 / 800×916 / **14.4 s** / **2,661,003 B**，十进制 5,000,000 B 口径）+ `demo-manifest.json`；
  SDF `<gui>` 自带 Screenshot（10 插件）；`AGC_GUI_CONFIG` 机制已移除。
  **收尾崩溃已修**（`stable_detail` 使用早于赋值）+ 回归 `test_capture_run_closeout.py`（6 用例，反向对照会变红）。
  报告：[round-5](task/20261031-011-p2-1-deliverables/round-5/report.md#p2-1-r5-report)
- **追加自查更正**：round-1…4 报告把 Worker 子会话 ID 与父会话 ID 写成同一值；真实 Worker =
  `7eb40b67-31c3-4a50-b313-e084cf01bdd7`，父 = `session-c1423390…`（仅记录层，未误投）。
- **剩余计划**：round-6 = **干净环境验证**（清 `build/install/log` → `colcon build` → 照 README 走通 ≥1 轮，
  记耗时/卡点/回改），T2 ≤2（累计 9/12 余 3）；视频等用户自录文件。
- 上一任务（已结档）：[20261030-010 P1-4 baseline closure](archive/20261030-010-p1-4-baseline-closure/round-3/review.md#p1-4-baseline-final-review)，结论 **PASS_WITH_NOTE**；P1-4 缺口已在 README「已知边界」登记。
- **基线事实**：HEAD `bf115f9`；P1-1…P1-4 全部产物已入库（`07eda37`）。
- **演示口径**：`full + yard + s04 + observe_yaw_mode=target`；target 是显式 oracle 指向臂，不等于真实视觉识别。

**迁移 workstream 暂停，W8 不再接单**（[PAUSED](../docs/plan/PAUSED.md#paused)）。