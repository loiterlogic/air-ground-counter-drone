# P0-1 项目完成定义 · 第 1 轮回报

- 任务 ID：`20261029-001-p0-1-completion-definition`
- 轮次：`1`
- 执行者：Worker（DSH 子会话，workbuddy / `deepseek-v4.1-flash` / `max`）
- Worker 子会话 ID：`cbd221f0-a615-4ac4-a7c3-f749f31bb56e`（Leader 于首次派工后登记）
- 领取时间：2026-10-29T09:48:50+08:00　结束时间：2026-10-29T10:12:47+08:00（约 24 分钟墙钟）
- 状态流转：`待执行` → `执行中` → `待审查`（本轮为里程碑达成，按协议置 `待审查` 并唤醒 Leader）

<a id="p0-1-report-summary"></a>
## 审查摘要

**结论**：P0-1 书面完成定义已写完并通过 6 条出口判据自检；**项目本身远未完成**（完成清单 10 条中 6 条 FAIL、2 条部分 PASS、1 条未建立、1 条未执行）。T1 = 0、T2 = 0，全程零进程零构建。

**差异清单**（仅 1 个白名单内产品文件 + 交接记录）：

1. `docs/plan/p0-1-项目完成定义.md` 重写（106 → 260 行），新增稳定锚点 `#p0-1-main-scenario` / `#p0-1-selected` / `#p0-1-demo-loop` / `#p0-1-checklist` / `#p0-1-gaps` / `#p0-1-definition` / `#p0-1-exit`；`#p0-1-goal` 保留，故 P0-1 既有 3 处入链未破。
2. 本报告 + `CURRENT.md` 状态位（结档时由 Leader 置已验收并归档）。
3. 无代码、launch、配置、契约、其他计划文档改动；无 `/tmp` 产物。

**相对草案修正的 6 处事实错误**（均有静态证据）：

- 启动命令的 `<world>` 占位符 → 明确为 `install/agc_sim/share/agc_sim/worlds/agc_world.sdf`（`world_bringup` 按 **basename** 替换注入障碍世界）。
- 演示闭环 ⑤/⑥ 顺序颠倒 → `summary.json` 由 `run_logger` 在 SIGINT 后 `finalize()` 写出，"结果"必在"停止"之后。
- 缺 `GZ_SIM_SYSTEM_PLUGIN_PATH` 导出前置（未导出则 launch 直接 substitution 失败）。
- 未提 `start` 必须显式调用（launch 不调 `/agc/task/start`；2 条 `IDLE` 的 s04 run 即此形态）。
- 选场理由"目标需运动"与 s04 的 `target_motion: static` 矛盾 → 改为口径澄清，场景不变（用户裁定不动）。
- 场景数"15"→ **16**；地图数、README、`run_demo.sh` 均按现状标 FAIL。

**关键新事实**：全仓 **1030** 个 `config/scene_manifest.json` 中 `scene=s04 ∧ backend=full` 的记录为 **0** —— 主场景闭环从未在用户裁定的 `backend:=full` 下跑过；既有 10 条 s04 全是 `lightweight`（7 成功 / 2 IDLE / 1 TIMEOUT）。

**未决项**：`backend:=full` 的墙钟上限无实测依据（已在文档中标"待实测 / 待 P1-2 预登记"，未编造）。

## 接单基线（独立记录）

| 项 | 值 |
|---|---|
| 项目根 | `/home/chen/AGC` |
| 分支 | `main` |
| HEAD | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290`（与派工单一致） |
| `git status --short` | **39** 条（与派工单"大量修改及未跟踪文件"一致；未重置、未清理、未提交） |
| 其中与本任务相关 | `?? docs/plan/`、`?? .coordination/` 均为既有未跟踪目录（本次只改其中 1 个文件） |
| 状态核对 | `CURRENT.md` = `待执行`、轮次 `1`、指向本轮 `request.md` —— 三项与派工单一致，允许接单 |

交付后 `git status --short` 仍为 **39** 条；本任务未新增任何 git 可见的文件增删（改的是已被 `??` 覆盖的未跟踪目录内文件）。

## 实际改动

### 1）`docs/plan/p0-1-项目完成定义.md`（唯一产品文件）

sha256（交付态）：`fdfbfb68aad30fecfcff649331ca2a709fc5df6b6aa2e33d92acc02e398512ed`，260 行。

结构（按派工验收项映射）：

| 派工验收项 | 落点 |
|---|---|
| 1. 主场景 ID / 期望终态 / 启动命令 / 关键参数 / 时长口径 | 一、已选定（1.1 身份轴、1.2 口径澄清、1.3 三条命令 + world 参数规则、1.4 参数表、1.5 `start` 显式调用、1.6 终态判据、1.7 三套时钟时长口径） |
| 2. 6 段闭环 + 外部观察 + PASS/FAIL，且不混淆三种"成功" | 二、演示闭环（6 行表 + "命令启动成功 / 任务成功 / 清理成功"三行对照表） |
| 3. 完成清单 ≥8 条、命令化或静态可判、未来项标回填且不虚报 | 三、完成清单 **D1–D10**（10 条，每条：判定方法 / PASS 条件 / 当前状态 / 责任阶段） |
| 4. 已知缺口 ≥4 条、现状 + 处置 | 四、已知缺口 **G1–G8**（8 条） |
| 5. 记录用户范围裁定、不动契约与场景决定 | "范围与已定决策"表 + 非目标节 |
| — | 五、一句话完成定义；六、本文件出口判据 6 条自检表 |

主要增补要点：

1. **1.3 命令可执行化**：给出 GUI / headless 两条完整 `ros2 launch`，`gz_args` 用 install 绝对路径；写明 `agc_world.sdf` 的 basename 替换规则（不匹配则追加、不写则用默认）与"`<world>` 是占位符不是命令"。
2. **1.5**：`start` 必须显式调用 + 整链悬停等待（`air_hover_timeout_s=45`，实测悬停 start 后约 10–14 s）→ 该调用会阻塞十余秒；超时落 `INFRA_FAILURE`。
3. **1.6 几何自洽**：任务目标 `(4.0,3.0)` 距目标初始位 `2.55 m < d_track_m=3.0`，故终态 = `target_xy_distance_m` 由 `11.85 m` 收敛到 ≤3.0 并保持 3 s（数值可静态复核）。
4. **1.7 三套时钟**：`t_max_s=120` 仿真秒（C4 超时算失败，硬上限）/ `t_dwell_s=3` / 启动等待 45–60 s 墙钟（**标待实测**）/ 墙钟看门狗（待 P1-2 预登记）/ `duration_s`（进程墙钟，≠ 任务时长）。
5. **1.8 既有证据**：10 条 lightweight s04 逐条统计 + s04×full = 0 + `summary.json` 无 `backend` 字段（归属须看 `config/scene_manifest.json`）+ 两条可复制的只读判定命令。
6. **G6 避障证据薄弱**：两柱到车→任务目标直线的垂距 `4.80 m` / `3.61 m`（静态可算），主场景不得当避障展示。

### 2）本报告（`.coordination/task/.../round-1/report.md`）

### 3）`.coordination/CURRENT.md`

状态 `待执行` → `待审查`；"当前派工"改为指向本轮 `review` 待 Leader 填写。除状态与指针文本外未改其他字段（主场景 / 后端 / 视觉三项已定决策原样保留）。

## 命令、退出码与结果（全部 T0：只读、零进程）

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `git rev-parse HEAD` / `git branch --show-current` / `git status --short` | 0 | HEAD 与分支同派工单；39 条脏/未跟踪 |
| 2 | `grep -l '"scene": "s04_static_static_obs_track"' experiments/*/*/config/scene_manifest.json \| xargs -r grep -l '"backend": "full"' \| wc -l` | 0 | **0**（s04 × full 无任何 run） |
| 3 | 同上换 `"backend": "lightweight"` | 0 | **10** |
| 4 | `python3 -c` 遍历 `experiments/w6-task-eval/*s04*/metrics/summary.json` 打印终态/时长/RTF | 0 | 7 `TRACKING_SUCCESS`(16.00–17.57 s, RTF 0.836–0.916) / 2 `IDLE` / 1 `MISSION_FAILED`(TIMEOUT, 123.45 s) |
| 5 | `python3 -c` 校验 s04 `summary.json` 的 C9 三字段非 null | 0 | 10/10 有 `shield_infeasible_rate`/`reset_failure_rate`；9/10 有 `definition_version`（最旧 `20261016-s04-0` 无） |
| 6 | `python3 -c` 校验 s04 `config/scene_manifest.json` 的 `assertions` 全为 true | 0 | 10/10 全 true（早期 run 4 键、其后 7 键） |
| 7 | `python3 -c` 全局统计 1030 个 manifest 的 `(backend, scene)` 组合 | 0 | s04 仅 lightweight；`full` 集中在 s08/s15 等 capture 场景 |
| 8 | 同上统计 `effective_params.world_obstacles` | 0 | `full` × `none` = 962；**`full` × `static` = 0** |
| 9 | `ls run_demo.sh README.md` | **2** | 两者均不存在（文档标 D5/D7/D10 = FAIL 的依据） |
| 10 | `ls src/agc_sim/worlds/` | 0 | 仅 `agc_world.sdf` 一张（D6 = FAIL 依据） |
| 11 | `python3 -c "import yaml;print(len(...scenarios.yaml...['scenes']))"` | 0 | **16**（草案"15"有误） |
| 12 | `grep -rn perception_path src/ scripts/` | 1（无匹配） | 0 命中 → ADR-0103 的字段尚未实现，写入 G1 |
| 13 | `grep -n camera src/agc_sim/config/bridge.yaml src/agc_perception/config/perception_sensors.yaml` | 1（无匹配） | 0 命中 → 无相机链路，写入 G1 |
| 14 | `python3 -c` 计算两柱到车→目标直线的垂距 | 0 | `pole_1` 4.80 m、`pole_2` 3.61 m（写入 G6） |
| 15 | `python3 -c` 计算 goal→target / car→target 距离 | 0 | 2.550 m / 11.853 m（写入 1.6） |
| 16 | 自写链接检查（正则抽全部 markdown 链接，本地文件存在性 + 锚点存在性） | **0** | 41 条链接，**0 条坏链/坏锚点** |
| 17 | `grep -n "§"` 文档 | 1（无匹配） | 无 `§` 章节号引用（遵守稳定锚点纪律） |
| 18 | `env \| grep GZ_SIM_SYSTEM_PLUGIN_PATH`（source ROS 后） | 0 | **未导出** → 列入 1.3 环境前置（`world_bringup` 用 `EnvironmentVariable` 无默认值，缺失即抛 substitution 失败） |
| 19 | `python3 -m pytest scripts/tests --collect-only -q`（**未 source 工作区**） | 2 | `ModuleNotFoundError: agc_msgs` 收集中断 → D8 判定命令补"须先 source"前置 |
| 20 | `python3 -m pytest src/agc_task/test/test_scene_config_invariants.py --collect-only -q` | 0 | 3 个用例可收集（**未执行**） |
| 21 | `sha256sum docs/plan/p0-1-项目完成定义.md` | 0 | `fdfbfb68…8512ed` |

**命令尝试次数**：21 条只读检查，全部成功产出结论（无失败重试）；**成功产物数**：1 个文档文件（+ 2 个交接记录）。二者不混用。

## 证据路径

| 证据 | 路径 |
|---|---|
| 交付文档 | [p0-1-项目完成定义.md](../../../../docs/plan/p0-1-项目完成定义.md#p0-1-goal) |
| s04 既有 run（10 条） | `experiments/w6-task-eval/*s04_static_static_obs_track*/{config/scene_manifest.json,metrics/summary.json}` |
| 代表性成功 run | `experiments/w6-task-eval/20261019-s04_static_static_obs_track-0-170952-1843/` |
| 代表性 TIMEOUT run | `experiments/w6-task-eval/20261019-s04_static_static_obs_track-0-205112-3213/`（123.45 s，对应 120 仿真秒预算） |
| `full` 后端跟踪类 run（非 s04） | `experiments/w6-task-eval/20261019-s01_static_none_nominal_track-0-191113-5557/`（`TRACKING_SUCCESS`，duration 19.87 s） |
| 场景真源 | [scenarios.yaml](../../../../src/agc_task/config/scenarios.yaml)、[scenario_carriers.yaml](../../../../src/agc_task/config/scenario_carriers.yaml) |
| 入口真源 | [w6.launch.py](../../../../src/agc_task/launch/w6.launch.py)、[w6_composition.py](../../../../src/agc_task/launch/w6_composition.py)、[world_bringup.launch.py](../../../../src/agc_sim/launch/world_bringup.launch.py) |
| 基参 | [w6_base.yaml](../../../../src/agc_task/config/w6_base.yaml) |
| 日志 / 临时产物 | **无**（本轮未写 `/tmp/agc-p0-1-*`；无长日志可留） |

## 未执行项（明确标记）

1. **未启动任何仿真 / GUI / headless / 构建 / ROS 图查询**（T1=0、T2=0）。故 `backend:=full` 的主场景闭环**本次零实测**，文档中所有 full 相关数值均标"待实测 / 待 P1-2 回填"。
2. **未运行 D8 的两条测试命令**（`pytest` 会创建进程；`tests/run_all.py` 还会拉起链路）。D8 状态记为 `未执行`，未写 PASS。
3. **未跑 `python3 tests/w6_geometry_check.py`**（同属执行类核查）——D6 的该项判定方法与 PASS 条件已给出，状态按"仅 1 张地图"直接判 FAIL，不依赖该核查。
4. **未改 `docs/plan/README.md`**：其 P0-1 行与"已定决策"表已与本文一致，无需回填；且不在白名单。

## 偏离 / 待裁定

1. **白名单内的小幅结构重排**（非违规，报备）：把草案"要做什么 / 已选定（回填）"两段合并为"一、已选定"，并新增 6 个稳定锚点。原 `#p0-1-goal` 保留，`docs/plan/README.md`、`p0-2`、`p1-1` 三处既有入链全部仍可解析（命令 16 已验证 41/41 链接与锚点均有效）。若 Leader 要求保留旧小节顺序，属可改的格式问题，非事实问题。
2. **`Worker 子会话 ID`**：沿用 Leader 已回填的值 `cbd221f0-a615-4ac4-a7c3-f749f31bb56e`，未改写。
3. **需要 Leader 注意的事实（非本任务可解）**：`s04 × backend:=full` 的 run 数为 **0**，且全仓 `full` 后端的 `world_obstacles` 也从未是 `static`。这意味着"主场景 + 用户裁定后端 + 静态障碍"这一组合**从未被任何一次真实运行覆盖**；D1 的 FAIL 不是文档保守，是事实缺口。是否需要为此单开一轮 T2 验证，属 Leader 裁定（本任务预算 T2=0，不申请）。
4. **无阻塞**：未触碰硬约束红线，未越白名单，未改用户已裁定事项。

## 批次与预算

- 批次授权 `N=6` / 熔断 `K=4`：本任务第 **1** 轮即达成里程碑，未触发熔断。
- 累计消耗：**T1 = 0 次 / 0 s；T2 = 0 attempt**；实际只读检查 21 条；墙钟约 24 分钟。
- 预登记停止条件（"若第 2 轮结束仍无法确定有效启动命令或无法把全部完成清单写成可判定项 → 停止"）：**未触发**，第 1 轮即完成。

## 建议下一步（供 Leader 裁定，非自行开轮）

1. 先审查本文 6 条出口判据与 D1/D3 两条 FAIL 的定性是否接受。
2. 若接受，P0-1 可验收归档；下一任务按路线应为 P0-2（暂停迁移与基线固定），或 P1-2（一键入口）——后者是解 D1/D5 的直接手段。
3. 若要闭合"主场景 × full 后端"这一从未跑过的组合，需要一次 T2 派工（干净启动、`start` 显式调用、SIGINT 收尾、`summary.json` 复核）；本次零运行授权内**不可做**，故只作为建议提出，未自行启动。
