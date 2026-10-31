<a id="p1-3-r2-report"></a>
# P1-3 · round-2 报告（目标视觉可辨识返工）

- 任务 ID：`20261030-008-p1-3-observability`
- 轮次：round-2（返工；批次 N=6 / K=4；本轮预算 T2 ≤2 次 / 600 s、T1 = 0）
- 执行者：Worker（DeepSeek Harness）
- 领取时间：2026-10-30T18:24+08:00；完成时间：2026-10-30T18:47+08:00

## 审查摘要（≤30 行）

**结论：判据 5 达成，round-1 的全部结论保留，7 条出口判据现全部勾选。**

- **改动范围极小**：`intruder_uav.sdf.xacro` 的 controlled 分支**纯新增 52 行、删除 0 行**
  （`git diff --stat` 与 `grep '^-'` 双向核对）；另加 1 个离线守卫测试与 1 份计划文档章节。
- **做法**：新增 `target_highlight` link（1.2 m 半透明橙色自发光球，**无 collision**，质量 1e-6 kg）
  + 一个 fixed joint 挂到 `base_link`。与 RViz 目标球同尺寸，GUI 两种标注口径一致。
- **为什么不是"往 base_link 里加 visual"**：本机 `gz sdf -p` 实测——
  merge 的 `<include>` **只**收 `uri/pose/plugin/name/static/placement_frame`，塞 `<link>` 会被**静默丢弃**；
  写同名 `<link name="base_link">` 直接 `Error Code 2: link already exists`。详见报告正文的表。
- **物理零影响（机械可证）**：展开式剥掉高亮元素后与改动前**逐字节一致**；
  collision 仍 9、x500 全部 inertial/mass/plugin/PX4 接口不变；**两次反向对照实证守卫会红**。
- **两次真实 run 均 `TRACKING_SUCCESS`**：`b1` headless（`viz:=false`、无任何 RViz 进程）、
  `b2` GUI（四类 GUI 证据齐）；两者 C9 指标 `shield_infeasible_rate=0` / `reset_failure_rate=0`、复位无失败。
- **回归**：`scripts/tests/` **186 passed**（原 176 + 新 10）；`tests/w6_geometry_check.py`
  三图全 PASS；`tests/docs_link_check.py` **活跃断链 0**。
- **一处需要 Leader 知道的口径**：`b2` 的 `true_shield_infeasible=true`，`b1` 为 false。
  查历史 **33** 次同场景 run，该字段 `true` 出现 **5** 次（最早在**本单改动之前**），属既有波动；
  且本轮模型只加了无碰撞的视觉球，不可能影响接触真值判断。**未据此调整任何指标口径。**

## 接单基线

| 项 | 值 |
|---|---|
| HEAD | `b627043` |
| 分支 | `main` |
| 脏文件 | 52 项（P1-1/P1-2/P1-3round-1 遗留） |
| 目标模型改动前状态 | **干净**（`git status --porcelain` 无输出，故 `git show HEAD:` 可作展开基线） |

## 实际改动

| 文件 | 性质 | 说明 |
|---|---|---|
| `src/agc_sim/models/intruder_uav/intruder_uav.sdf.xacro` | **修改（纯新增 52 行 / 删 0）** | controlled 分支加 `target_highlight` link + fixed joint；含"为何这样写"的实测依据注释 |
| `scripts/tests/test_intruder_visual_highlight.py` | 新增 | 10 个离线守卫用例（正面证据 + 物理零变更 + 反向对照） |
| `docs/plan/p1-3-任务可观测与演示呈现.md` | 修改 | 判据 5 勾选 + 重写「目标视觉可辨识」章节（含实测表与诚实性口径） |
| `.coordination/task/.../round-2/report.md` | 新增 | 本报告 |
| `.coordination/CURRENT.md` | 修改 | 置 `待审查` |

**未改动**：`run_demo.sh`、`scripts/demo/**`（round-1 成果原样）、`src/agc_task/**`、消息、
C++、其他契约文件、`agc_car` 模型、`maps/*.yaml`、`worlds/*.sdf`。

## 命令、退出码与结果

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `pytest scripts/tests/test_intruder_visual_highlight.py -q` | 0 | 10 passed |
| 2 | 同上，注入 `<collision>` 后（**反向对照 1**） | 1 | **3 failed**（守卫真的会红），随后恢复 |
| 3 | 同上，把质量改成 5 kg 后（**反向对照 2**） | 1 | **2 failed**，随后恢复 |
| 4 | `pytest scripts/tests/ -q`（全套） | 0 | **186 passed** |
| 5 | `tests/w6_geometry_check.py` | 0 | **PASS (maps=minimal,yard,open_field)** |
| 6 | `tests/docs_link_check.py` | 0 | **活跃断链 0** |
| 7 | `xacro ... controlled:=true \| gz sdf -p` | 0 | 解析无错；links 6 / visuals 17 / collisions 9 |
| 8 | `./run_demo.sh --headless`（b1） | 0 | `TRACKING_SUCCESS` |
| 9 | `./run_demo.sh`（b2，GUI） | 0 | `TRACKING_SUCCESS` + GUI 四类证据 |

**预算**：T2 **2/2** 次（b1 + b2），总墙钟约 `61 + 71 ≈ 132 s`（预算 600 s）；T1 **0/0**；
离线检查约 25 次、< 90 s。

## 证据路径

证据根 `experiments/p1-3/round-2/`：

- `evidence/index.json` —— 机器可读索引
- `evidence/target-highlight.json` —— 高亮几何/颜色/质量采样（含基线与现值对照）
- `evidence/model-controlled.expanded.sdf` —— 从 **install 路径**展开（与 launch 用的是同一 symlink 目标）
- `evidence/model-controlled.sha256` —— 展开产物哈希
- `evidence/b1-headless/`、`evidence/b2-gui/` —— 两次 run 的 `result.json` / `timeline.txt` / `panel.txt` /
  `terminal_explanation.txt` / `progress.log`
- `t2/attempt-b{1,2}-*.console.log` —— 完整控制台原始输出

真实 run 主场：`experiments/demo/20261030-184153`（b1）、`experiments/demo/20261030-184302`（b2）。

### 逐项验收对照（派工单「证据与验收」）

| # | 要求 | 结果 |
|---|---|---|
| 1 | controlled 分支 visual 存在、醒目；passive 不回退 | ✅ `test_controlled_model_has_highlight_link` / `test_highlight_is_visually_conspicuous`（球半径 ≥0.5 m、橙红档、有 emissive）/ `test_passive_branch_unchanged` |
| 2 | collision/inertial/plugin 等禁止字段 diff 守卫 | ✅ `test_only_highlight_differs_from_baseline`（逐字节）等 4 条；两次反向对照实证有效 |
| 3 | GUI + headless 各一次，均 `TRACKING_SUCCESS`，C9 无异常 | ✅ b1 / b2；两 run `shield_infeasible_rate=0`、`reset_failure_rate=0`、`reset_failed=false` |
| 3a | headless 证明 `viz=false` 时不依赖 RViz | ✅ b1：`viz:=false`、`gz_args` 含 `-s`、进程证据里 `rviz2=[]` / `viz_markers=[]` |
| 4 | 重跑 geometry + 完整脚本回归 | ✅ 三图 PASS；186 passed |
| 5 | 更新出口勾选与目标视觉章节，明确"可控版实体目标" | ✅ 文档已重写，明写"Gazebo 实体 visual，不是仅 RViz marker" |

## 未执行 / 已知边界

| 项 | 原因 |
|---|---|
| GUI **像素级截图**证明橙色球可见 | 本机无截屏工具（`xwd`/`import`/`ffmpeg`/`scrot`/`grim` 全缺，与 P1-1 round-6 结论一致）；且 T2 预算已用尽。本项证据链为"模型展开 + 颜色采样 + 两次 run 加载同一文件 + GUI 渲染器正常"，**不宣称有截图**。 |
| 高亮球在 GUI 里是否**遮挡**机架影响判读 | 已用 `transparency=0.45` + `cast_shadows=false` 降低遮挡；未做主观观感评审（需人看）。 |

## 偏离与待裁定

**无偏离。** 唯一需要知会的是 `true_shield_infeasible` 的波动（见审查摘要末条）：
该字段在历史同场景 33 次里 `true` 出现 5 次，最早出现在本单改动之前的 run
（`20261030-s04_static_static_obs_track-0-170425-7057` 等），本轮只新增无碰撞的视觉 link，
不可能影响接触真值；**未据此修改任何指标口径或判定逻辑**。

## 假设台账与下一轮建议

| 假设 | 状态 | 依据 |
|---|---|---|
| H1 往 merge 后的 `base_link` 里加 visual 可行 | **已排除** | `gz sdf -p` 实测：include 内 `<link>` 被静默丢弃；同名 sibling link 直接 `Error Code 2` |
| H2 新增独立 link + fixed joint 会改变物理 | **已排除** | 展开式剥壳后逐字节一致；collision/inertial/mass/plugin 计数与取值全同；两次真实 run 均正常达终态 |
| H3 高亮只在 GUI（靠 RViz）可见 | **已排除** | b1 headless `viz:=false`、无 rviz2 进程，目标视觉属性仍在模型 SDF 内 |
| H4 `true_shield_infeasible` 波动由本单引入 | **已排除** | 本单改动前已有 5/33 次为 `true`；本轮改动无碰撞几何 |
| H5 GUI 中橙色球主观可见度足够 | **未验证（不可在本单测）** | 需人眼在 GUI 里看；本机无截屏工具。属展示效果问题，不影响判据 5 的机械判定 |

**下一轮建议**：**无需再开轮**。P1-3 七条判据已全部达成并可机械复核；若 Leader 希望补主观观感，
可用一次 GUI 现场演示人工确认（不需要 Worker 再改代码）。

**累计预算消耗（本任务全批次）**：round-1 用 2 轮 / T2 4 次；
round-2 用 1 轮 / T2 2 次；合计 **3 轮（N=6 内）**、T2 **6 次**、K=4 未触发。
