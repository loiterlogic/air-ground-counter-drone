# P2-1 · round-4 request（Worker 自写，批次续跑）

<a id="p2-1-r4-request"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · round-4 · 2026-10-31
- 来源：**Worker 自写**，继承 [round-3 审查](../round-3/review.md#p2-1-r3-review) 第 3/4 节（裁定 **α**）
- 承接：[round-3 report](../round-3/report.md#p2-1-r3-report)（结构性阻断 + 机制定案 H-C/H-D）

## 本轮目标

**α 落地 + 一次自然运行取齐「启动 / 跟踪中 / 终态」三图 + GIF 序列，README 换真图。**

## 步骤

1. **α**：给 `src/agc_sim/worlds/agc_world.sdf` 的 `<gui>` 块**追加** `Screenshot` 插件
   （照抄本机已验证可用那份，浮动小面板）。
   - 注释写明"**GUI 取证用；不进入仿真、不改变任何物理/感知口径**"；
   - **禁触** `<scene>` / `physics` / `ground_plane` / 传感器 / `world_geometry.yaml` / `maps/**`；
   - 改后必须：`python3 tests/w6_geometry_check.py` **PASS**（含断言 (n)）、
     `./run_demo.sh test` 全绿、`scripts/tests` 全绿。
2. **移除 `AGC_GUI_CONFIG` 机制**：`scripts/demo/start.py` 的环境变量分支、
   `gui_capture.py` 的 `derive-config`、`capture_run.py` 的 `--no-gui-config` 与配套测试一并清掉。
   - 理由（写进报告）：α 之后它只会**静默把视角换成斜视**，产出不代表用户所见 → **脚枪，不是能力**；
   - 若移除中发现会影响其它已验证路径 → 改为"显式拒绝 + FAQ 说明"并**立即报告**，不擅自扩大范围。
   - 本条**取代**先前"保留为可选开关"的口径（那时未定案 H-C）。
3. **交付图只允许来自自然运行**（不设 `AGC_GUI_CONFIG`）：运行期 1 Hz 取帧，按 `timeline.txt`
   取齐**启动 / 跟踪中 / 终态**三张 + **≥20 帧** GIF 序列；`make_gif.py` 出 GIF
   （800 px / 10–15 s / ≤5 MB）落 `docs/plan/assets/`；README 三图位换真图。
   **通过线：首帧 skyband ≤0.10**（预期 ≈0.06）；若 ≥0.20 → **立即唤醒**，不得自行换视角或改交付口径。
4. `docs/faq.md` 补一条（≤3 行）：带 `--gui-config` 时 gz-gui 会**再加载**
   `~/.gz/sim/<ver>/gui.config` 并**覆盖**相机位姿 → 视角变了、图不代表用户所见。
5. 补 `tests/README.md` 纪律条：**测试基线不得跟随 `HEAD`**（round-3 步骤 6 无完成证据，本轮补齐）。
6. 三图/GIF 的**路径 + md5 + skyband** 写进报告；**不许**用旧图/示意图/黑帧。

## 预算

- **T2：≤2 次**（批次累计上限 **10 次 / 6600 s**，已用 6）。
- **T1**：沿用批次余量。
- 离线只读检查：次数只记账。

## 禁止（红线）

- **禁止**清 `/dev/shm`、**禁止**处置他人进程；
- **禁止**改 `<scene>` / `physics` / `ground_plane` / 传感器 / `world_geometry.yaml` / `maps/**`；
- **禁止**写 `~/.gz`（只读允许）；
- **禁止**设 `AGC_GUI_CONFIG` 取交付图（自然运行才代表用户所见）；
- **禁止**用旧图 / 示意图 / 黑帧冒充截图；
- **禁止**碰完整视频（用户自录）。

## 停止条件

- 本轮若 **2 次 T2 内仍取不到三图 + GIF** → 停止并交假设台账；
- 若首帧 skyband **≥0.20** → **立即唤醒**（不得自行换视角或改交付口径）；
- 无效样本可重试 **1 次**并留痕。

## 不做

- 干净环境验证（round-5）；
- 完整视频（用户自录）；
- P2-1 出口判据勾选（里程碑时统一勾）。
