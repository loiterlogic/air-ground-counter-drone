<a id="report"></a>
# F4 · 地图设计技能 · round-1 报告

- 任务 ID：`20261031-015-map-design-skill`；轮次 1；日期 2026-10-31。
- 执行者：Worker（DSH 子会话 `d5924bc2-305d-4bd5-b6af-f6bb998381da`，`deepseek-v4.1-flash`）。
- 状态：**待审查**（Worker 不代写验收；`CURRENT.md` 由 Leader 统一写，本单未动）。
- 派工：[request.md](./request.md#request)；计划：[F4 目标](../../../../docs/plan/f4-map-design-skill.md#impl-facts)。

## 审查摘要（≤30 行）

**结论**：`map-design` 技能已落地、可**真实加载**；根目录 Playbook 已迁入技能资源后移走，正文可逐字符复核、无第二入口。

**给 Leader 的可调用信息**（必须走 `skill` 工具）：技能名 **`map-design`**；主入口
`.agents/skills/map-design/SKILL.md`；按需资源 `GATES.md` / `SCHEMA-AND-DERIVATION.md` / `EVIDENCE.md` / `references/MAP_DESIGN_PLAYBOOK.md`。

- **静态格式验证**：frontmatter `name=map-design`（kebab-case 正则通过）、`description` 105 字，与 Harness 校验规则一致（`name`/`description` 必填 + `^[a-z0-9]+(-[a-z0-9]+)*$`）。
- **真实加载证据**：本会话用 `skill` 按名加载成功，返回 `skill_content name="map-design"` 与 base dir；会话技能目录已出现该技能（5 个）。**这两种证据层次不同，不能互相替代。**
- **链接**：`python3 tests/docs_link_check.py` → **PASS**（活跃断链 0）；技能目录 5 个 md 逐文件复核，问题 0。

**差异**（全部在白名单内）：新增 `.agents/skills/map-design/`（4 个现行资源 + 1 个迁移件）；**删除** `MAP_DESIGN_PLAYBOOK.md`（迁入后移走根入口）；`.agents/README.md` +4 行（清单/资源说明/维护原则）；`docs/plan/f4-map-design-skill.md` 追加"实施事实"节（不含验收结论）。

**未执行**：未 commit/push/reset/clean；未启动仿真、未构建；未改地图、`tests/`、配置、其它技能、`CURRENT.md`。

**待裁定（不计入本单验收）**：8 字净空仍无正式断言（历史缺口），本单只把它写成可复算口径 + 只读探针，**没有**改 `tests/`；`minimal` 基线按圆盘口径对 8 字带为负（观察，非断言）——要不要正式断言、基线怎么处理，属 Leader 裁量。

## 1. 接单基线

| 项 | 值 |
|---|---|
| HEAD | `cedbc0e6c1e0e23aaf5b0effbf42ed9bf405def6`（与派工单一致） |
| 分支 | `main` |
| 工作区 | 脏 30 项（含派工单声明的 Leader 归档移动、F1–F3 并行改动）；`?? .coordination/task/` |
| 本单相关指纹 | `MAP_DESIGN_PLAYBOOK.md` sha256 `343ee368…6240f5`（工作区）、blob@HEAD `22c94abb`；`.agents/README.md` sha256 `ef3df3ba…bda3` |
| 领取时间 | 2026-10-31T14:43+08:00（读单）→ 14:45 记录基线 → 15:16 收尾 |

完整基线快照：[evidence/baseline.json](./evidence/baseline.json)。派工单已声明四单并行与 Leader
归档改动为预期，未覆盖、未回滚任何他人改动。

## 2. 学习与设计依据（先学后做）

1. **格式学习**：读 `.agents/README.md`（技能格式与维护原则）与 4 个既有技能；
   再从本机 Harness 包 `@deepseek-ai/dsh-skill-filesystem` / `@deepseek-ai/dsh-skill` 读到**实际**
   校验规则（`name`+`description` 必填、`SKILL_NAME = /^[a-z0-9]+(?:-[a-z0-9]+)*$/`、
   只发现直属 `<name>/SKILL.md`、坏 frontmatter 只 warn 不报错）——这条决定了"静态验证"与"真实加载"
   必须分开取证。
2. **内容来源**：完整读 772 行 Playbook + 交叉核对代码，不照抄结论：
   - `world_map.py`（schema 出口、启动期守卫、`FINISHES/FINISH_PBR`）；
   - `tests/w6_geometry_check.py`（断言实现、阈值、覆盖并集口径、环带采样）；
   - `w6_composition.py`（5 条派生路径、`load_scene` 两级地图优先级）；
   - `world_bringup.launch.py`（注入模型、运行期世界生成到 `/tmp`、`plugin_dir` 现状）；
   - `safety_shield.cpp`（圆盘半径公式）、`air.yaml`（余量参数与 8 字 rx/ry）、
     `Figure8Trajectory`（Gerono 公式）；
   - `materials/README.md` + `manifest.json`（贴图乘法、sRGB、UV 限制）；
   - 本机 `sdformat14/1.11/material.sdf`（`metalness`/`roughness` 确为标量）；
   - `scripts/demo/gui_capture.py`（`/gui/screenshot` 三条真实语义）、当前环境实际缺哪些抓屏工具（已复验）。
3. **设计取舍**：
   - **短主入口 + 4 个按需资源**：主入口只留"三条铁律 + 工作循环 + 判断表 + 失败处理索引"；
     公式与陷阱下沉，避免"每次都读 772 行"。
   - **现行资源不写易漂移数字**：实测值改为"跑哪条命令读哪个产物"，因为本次核对就发现
     Playbook 里的实体数（29 vs 实际 42）、函数名、`shape` 取值已漂移。
   - **历史与现行分离**：Playbook 原样迁入 `references/`，加"历史快照"声明；主入口只在
     "要追溯为什么"时指向它。
   - **把"没有正式断言"的判据写成可复算口径**，而不是编一条"应该没问题"。

## 3. 实际改动（全部写操作）

| # | 文件 | 动作 |
|---|---|---|
| 1 | `.agents/skills/map-design/SKILL.md` | 新建（91 行）：frontmatter + 三条铁律 + 工作循环 + 判断表 + 失败处理 + 边界 |
| 2 | `.agents/skills/map-design/GATES.md` | 新建（181 行）：圆盘/环带公式、7 道闸门口径（含 8 字净空）、闸门互相踩、布局范式 |
| 3 | `.agents/skills/map-design/SCHEMA-AND-DERIVATION.md` | 新建（176 行）：yaml schema、3 条启动期守卫、`safety_radius` 推导、5 条派生链、加图步骤、材质/地面/贴图 |
| 4 | `.agents/skills/map-design/EVIDENCE.md` | 新建（144 行）：证据分层、先学后做顺序、GUI 相机与截图路径、RViz 语义层、运行与内存陷阱 |
| 5 | `.agents/skills/map-design/references/MAP_DESIGN_PLAYBOOK.md` | 新建（786 行）：Playbook 迁移件 |
| 6 | `MAP_DESIGN_PLAYBOOK.md` | **删除**（先 `cp -p` 到技能资源、校验 sha256 相同后再删；见 §5） |
| 7 | `.agents/README.md` | 技能清单加 `map-design` 一行、加资源说明段、维护原则加"不钉死会漂移的事实" |
| 8 | `docs/plan/f4-map-design-skill.md` | 追加 `#impl-facts` 节（实施事实，**非**验收结论） |
| 9 | `.coordination/task/…/round-1/evidence/` | 新建基线/验证/探针证据（下述） |

**未改动**：`src/**`（含地图 yaml、`world_map.py`、SDF）、`tests/**`、`config`、其它 4 个技能、
`.coordination/CURRENT.md`、`.coordination/README.md`、`docs/adr/**`、`docs/plan/README.md`。

**写入范围内的中间产物**（如实登记）：迁移时先在目标位置放**未改链接的原样副本**做 sha256 比对，
随后用脚本就地改写为已迁移版本（同一路径，一次覆盖）；改前 3 处数字表述（C7 阈值/环带采样数/
激光面高度、覆盖率与明度带阈值、断言条数）在自查中删改为"以代码为准"，属**同一文件内的修订**，
最终内容见哈希表。`/tmp` 下仅有 `agc-f4-geom.json`、`agc-f4-fig8-20k*`（过程副本）。

## 4. 命令、退出码与证据

| 命令 | 退出码 | 结果 |
|---|---|---|
| `python3 tests/docs_link_check.py` | **0** | 扫描 434 文件 / 5403 链接 / 锚点校验 2358 / **活跃断链 0**；历史断链 63 条只列名（既有） |
| 同上（技能目录逐文件复核，复用其 `Doc`/`check_anchor`） | 0 | 5 个 md、0 处问题 |
| `python3 tests/docs_tooling_check.py` | **0** | PASS：全部用例通过 |
| `python3 scripts/adr_index.py --check` | **0** | PASS：与 106 篇 ADR 一致 |
| `python3 -c` frontmatter 解析（YAML + 与 Harness 同款正则） | 0 | `name=map-design` 合法、`description` 非空、目录名一致 |
| `skill(name="map-design")`（真实加载） | — | 返回该技能正文 + base dir；会话技能目录可见 |
| `python3 tests/w6_geometry_check.py --out /tmp/agc-f4-geom.json` | **0** | `PASS (maps=minimal,yard,open_field)`（**只读核对现网**，未改地图） |
| `python3 <evidence>/fig8_clearance_probe.py --json …` | **0** | 20.32 s；三图的 8 字净空两条口径（下述） |
| `git status --porcelain` | 0 | 本单范围内只有上述改动（见 §7） |

**迁移可追溯性证明**（这是"原内容可追溯"的硬证据）：

- 删除前：`sha256(MAP_DESIGN_PLAYBOOK.md)` == `sha256(references/…/MAP_DESIGN_PLAYBOOK.md)`
  == `343ee368586d5d5ee96987337947293171c70c8aca91af598601c4566f6240f5`（`cp -p` 后实测相同）；
- 改写后：把正文里的 `](../../../../` 还原成 `](`，与**删除前文本逐字符相等**
  （Python 字符串比较 `True`，27303 字符对 27303 字符）→ 迁移只改了链接前缀，**一字未改正文**；
- 最终迁移件 sha256 `ad069595…d1adc1`；根目录路径 `ls` 已不存在。

**8 字净空探针结果**（观察，非断言；单位 m）：

| 地图 | 圆盘口径（安全层同口径） | 最近实体 | 足迹口径（纯几何） | 最近实体 |
|---|---|---|---|---|
| minimal | **−2.708** | `pole_2` | +2.086 | `pole_2` |
| yard | **+1.305** | `sign_a` | +1.811 | `wall_e` |
| open_field | +4.198 | `cyl_1` | +6.198 | `cyl_1` |

`yard` 与历史核验器的 `+1.31 m` / `sign_a` 一致（复现了当时结论）；两条口径**不等价**，
报告时必须写清用的是哪一条（技能里已写成纪律）。

证据文件：
[baseline.json](./evidence/baseline.json)、
[verification.json](./evidence/verification.json)、
[w6_geometry_summary.json](./evidence/w6_geometry_summary.json)、
[fig8_clearance_probe.py](./evidence/fig8_clearance_probe.py)、
[fig8_clearance_probe.json](./evidence/fig8_clearance_probe.json)、
[fig8_clearance_probe_run.json](./evidence/fig8_clearance_probe_run.json)、
[final_manifest.json](./evidence/final_manifest.json)（改动文件逐字节哈希与行数）。

## 5. 安全动作留痕（移动/删除）

1. `mkdir -p $(pwd)/.agents/skills/map-design/references`；
2. `cp -p $(pwd)/MAP_DESIGN_PLAYBOOK.md <上述目录>/` → `sha256sum` 两者**相同**；
3. 校验通过后才 `rm -v $(pwd)/MAP_DESIGN_PLAYBOOK.md`；
4. `ls` 确认根路径不存在；`git status` 显示 ` D MAP_DESIGN_PLAYBOOK.md`（删除已可审）。

绝对目标在执行前显式打印核对过（`/home/chen/AGC/.agents/skills/map-design/references`）。

## 6. 预算

- 授权：`T1=0`、`T2=0`；离线文档/格式检查**累计 600 s、单次 ≤30 s、次数只记账**。
- 实际：**T1=0、T2=0**；未起任何仿真/构建/GUI/headless 进程，未碰共享状态。
- 离线检查与只读命令**约 36 次**（含 read/grep/链接核查/核查脚本/探针），逐次留痕见 §4 与 evidence。
  墙钟主要花在：`w6_geometry_check` ≈15 s × 2；8 字探针 3 次运行（20 000 采样 20.3 s / 19.5 s + 一次
  **40 000 采样 35.6 s**，该次按"单次 ≤30 s"记为**预算越界 1 次**，原因是先跑到 40 000 才降采样；
  结论逐值相同，超时发生在设计侧探针、非正式核查，如实登记不隐藏。
- **结论：单次 ≤30 s 有 1 次越界**（已记入偏离），累计墙钟仍 **< 600 s**。
- 轮次：批次内第 1 轮；无"无区分性空转"（K=4 未触发）。

## 7. 偏离、未执行与未决

**偏离**：
1. **写入范围**（派工单已授权，仅记录）：`docs/plan/f4-map-design-skill.md` 的"实施事实"节——
   派工单允许"本单计划的实施事实（不能代写验收）"，追加时未改目标/边界/出口判据，也未写验收结果。
2. **单次离线检查越界 1 次**：8 字探针首跑用 40 000 采样、墙钟 **35.6 s**（限值 30 s）。
   发现后改为 20 000 采样（20.3 s / 19.5 s，结论逐值相同），已把探针脚本入库到 evidence。
   越界发生在设计侧只读探针，**不是**正式核查；按"如实计入、不隐藏失败"登记，不申请追加预算。

**未执行**（明确不做）：
- 未 commit/push/reset/clean/切分支；未 `git add`。
- 未启动仿真、未构建、未渲染取证（本单 T2=0）。
- 未改地图 yaml、`world_map.py`、`tests/w6_geometry_check.py`、`agc_world.sdf`、`scenarios.yaml`。
- 未改 `CURRENT.md`、归档、共享索引、ADR 索引。
- 未给 8 字净空新增正式断言（属 `tests/`，不在白名单）。

**未决（交 Leader）**：
1. **8 字净空是否升为正式断言**：现只在技能里给可复算口径 + 只读探针；
   若要入库断言，需批准改 `tests/w6_geometry_check.py`，并裁定 `minimal` 基线（当前圆盘口径为负）的处置。
2. **`minimal` 基线与"演示主地图"判据的张力**：技能按"只在演示主地图要求为正"表述，
   该口径是否成文进 ADR，请 Leader 定；本单未写 ADR。
3. **已知文档漂移未修**（白名单外）：`world_geometry.yaml` 头部仍有"29 实体 / 107 图元"与
   已不存在的 `w6_composition.resolve_geometry_file`；`tests/w6_geometry_check.py` docstring 仍写
   `shape ∈ {box, cylinder}`。技能改用"以代码为准"，未改这两处。
4. **`tests/docs_link_check.py` 的瞬时红**：并发单（F3）在 `docs/adr/0104-…` 里引用了
   尚未出现的 `.coordination/task/20261031-014-worker-autonomy/round-2/review.md`，我最后一次全量跑时
   活跃断链为 1（随后其路径出现即恢复 0）。**不是本单造成**，但会让全量核查在并行窗口内变红，
   建议 Leader 在并行收尾时统一跑一次再判。

**假设台账**（批次内本轮）：无未排除假设——本单是文档/结构改造，判据可静态判定；
唯一"未验证"项已单列为未决 1（需要白名单外的 `tests/` 改动）。

## 8. 下一轮建议

本单已达本轮出口判据（可加载、链接有效、可追溯、无根目录入口）。建议 Leader：
先独立审查 §2 的"数字不抄"口径与 §7-1/2 两项裁定，再决定是否需要第 2 轮；
若需要，最小改动集是"批准 `tests/` 内新增 8 字净空断言 + 基线处置"。
