<a id="current"></a>
# 当前交接

- 任务 ID：**20261031-011-p2-1-deliverables**
- 轮次：**round-3（批次续跑；N=6 已用 3，余 3 / K=4）**
- 状态：**执行中**（**阻塞唤醒**：自然运行无法取帧 / 取帧必斜视，结构性互斥，待裁定 α/β/δ/ε）
- 本轮回报：[round-3 report](task/20261031-011-p2-1-deliverables/round-3/report.md#p2-1-r3-report)
- 当前派工：[round-1 request](task/20261031-011-p2-1-deliverables/round-1/request.md#p2-1-r1-request)（Leader）
  · [round-2 request](task/20261031-011-p2-1-deliverables/round-2/request.md#p2-1-r2-request)（Worker 自写）
  · round-3 request 由 Worker 自写（继承 [中途审查](task/20261031-011-p2-1-deliverables/round-2/review.md#p2-1-mid-review) 第 4/5 节的新边界与目标）
- 回报：[round-1](task/20261031-011-p2-1-deliverables/round-1/report.md#p2-1-r1-report) · [round-2](task/20261031-011-p2-1-deliverables/round-2/report.md#p2-1-r2-report) · [中途审查](task/20261031-011-p2-1-deliverables/round-2/review.md#p2-1-mid-review)
- **Leader 裁定要点**：① T2 超支 1 次**追认**（无效样本重试）；本批次允许无效样本重试 1 次并留痕。
  ② `rm -f /dev/shm/*` **违规**（清理共享状态；无外部损害 + 主动披露）→ 记档、**禁止再犯**，不判阻塞。
  ③ **不**为俯视改世界 SDF / 加传感器；round-3 改走"自然运行取三图 + skyband 判视角"。
  ④ **追加授权 T2 +3 次 / +1800 s**（累计上限 8 次 / 5400 s），本轮 ≤2 次。
- **待 Leader 裁定（阻塞）**：取帧与正俯视**互斥**，四方案 α（给 SDF `<gui>` 追加 Screenshot 插件，需扩白名单）/
  β（临时 `HOME`/`XDG_CONFIG_HOME` 隔离用户配置）/ δ（用户手动点 Screenshot）/ ε（登记为已知缺口）。
  建议 **α**（最小改动、与用户所见一致）；详见 [round-3 报告第 3 节](task/20261031-011-p2-1-deliverables/round-3/report.md#p2-1-r3-options)。
- **用户裁定（2026-10-31）**：① 用户确认默认运行所见=**正俯视平面图**；`AGC_GUI_CONFIG` 保留为取证可选开关，
  **不**设默认、**不**改 `run_demo.sh` 默认行为。② **完整演示视频由用户自己录**，本轮不碰、不装工具。
- **相机事实（round-3 已定机制）**：`--gui-config` 会加载**两层**配置——派生配置先、`~/.gz/sim/8/gui.config` 后
  并**覆盖**视角（其 `camera_pose=-6 0 6 0 0.5 0`）→ 三帧 skyband **0.2848** 由此而来（H-C 已证实）。
  **自然运行**（不设 `--gui-config`）走 SDF `<gui>` 块：`camera_pose` 确为**正俯视** `0 0 118 0 1.5708 1.5708`，
  但该块**不含 Screenshot 插件** → `/gui/screenshot` 不出现 → **0 帧**（H-D 已证实）。
  **H-A / H-B / H5（命中机载相机）均已证伪**。
- 上一任务（已结档）：[20261030-010 P1-4 baseline closure](archive/20261030-010-p1-4-baseline-closure/round-3/review.md#p1-4-baseline-final-review)，结论 **PASS_WITH_NOTE**。
- **2026-10-31 用户裁定（选 1「认账收口」）**：P1-4 判为**完成（带已知缺口）**；缺口（换相机机型对跟踪动力学的量化影响未知）已在 README「已知边界」登记。
- **基线事实**：HEAD `07eda37`（步骤 0 已把 P1-1…P1-4 全部产物入库，工作树已干净）。
- **演示口径**：`full + yard + s04 + observe_yaw_mode=target`；target 是显式 oracle 指向臂，不等于真实视觉识别。

**迁移 workstream 暂停，W8 不再接单**（[PAUSED](../docs/plan/PAUSED.md#paused)）。