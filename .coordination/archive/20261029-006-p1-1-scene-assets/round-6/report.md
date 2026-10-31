# P1-1 · round-6 报告（区分度 / 屋顶 / 地面语义层 / 尺度参照物 / 贴图 / RViz 语义层）

- 执行者：Worker（DSH 会话，`codearts/deepseek-v4.1-flash`）
- **授权来源：用户**（2026-10-30 直接对话）。本轮**没有** Leader 书面 `request.md`，
  与 round-4/round-5 同例，请 Leader 据此补认。
- 状态：**待审查**（自查全绿；含 **3 项口径变更** 与 **1 项白名单偏离** 需追认，见 §5/§6）
- 上游：[round-5 报告](../round-5/report.md#p1-1-r5-user)
- **上游状态提示**：`CURRENT.md` 仍停在 round-3「待执行」，与实际（已到 round-6）不符，
  请 Leader 一并纠正。

<a id="p1-1-r6-user"></a>
## 1. 用户裁定（原文）

> 「我觉得已经非常非常好了，还有什么可优化的方向，我知道的有现在建筑物和地面的区分度还是有点低，只给方向」
> → 「区分度：1 采纳，2 不采纳（我怕阴影太明显影响视觉），屋顶优化采纳，4 采纳，5 采纳；
>    材质：6 采纳，但只要贴图；画面解读：…怎么选」
> → 「先只设计方案」→「ok，按之前设计好的方案开始干，干完了按实际经历修改你刚刚创建的文件」

**采纳**：明度分层 / 屋顶优化 / 地面语义层 / 尺度参照物 / 只做贴图 / GUI 纯场景 + RViz 叠加。
**不采纳**：阴影强化。

<a id="p1-1-r6-files"></a>
## 2. 实际落盘

| 文件 | 改动 | 性质 |
|---|---|---|
| `src/agc_sim/config/maps/yard.yaml` | 屋面重做（檐 + 下沉金属屋面 + 屋脊/天窗/空调）；+6 个可碰撞参照物；头部补明度带与 `roofpanel` | 几何真源 |
| `src/agc_sim/worlds/agc_world.sdf` | 基层/场坪配色；**地面语义层 29 块**（路缘石/车位线/排水沟/碎石带/绿化带）；10 处 `<albedo_map>` | 视觉层 |
| `src/agc_sim/materials/` | **新增**：`gen_textures.py`（自产程序化贴图）+ 4 张 512² albedo + `manifest.json` + `README.md` | 自产资产 |
| `src/agc_sim/launch/world_map.py` | 新增 `roofpanel`；`steel` 0.75/0.35 → **0.35/0.42** | schema 唯一出口 |
| `src/agc_sim/CMakeLists.txt` | `install(DIRECTORY … materials)` | 构建 |
| `src/agc_task/scripts/viz_markers.py` | **新增**：RViz 语义层节点（障碍几何/安全圆盘/8 字参考/作业区 + 目标/障碍） | 新节点 |
| `src/agc_task/config/agc_demo.rviz` | **新增**：固定布局（Fixed Frame `map`，Orbit 正俯视） | 配置 |
| `src/agc_task/launch/w6.launch.py` | 新增 `viz` 参数 + `_viz_actions()`（viz_markers + rviz2 + `map→world` 静态 TF） | 入口 |
| `src/agc_task/CMakeLists.txt` | 安装 viz_markers 与 rviz 配置 | 构建 |
| `tests/w6_geometry_check.py` | 实体上限 40→**46**；**新增断言 (q)**；贴图地面时从 manifest 取基色 | 核查（**口径变更**） |
| `docs/plan/p1-1-地图与场景资产.md` | 新增 `#p1-1-r6` 节（含口径变更与已知限制） | 文档 |
| `MAP_DESIGN_PLAYBOOK.md` | **新建**（用户要求）：技术流程参考，含 R6 实做记录与 16 个坑 | 文档 |

**未动**：9 消息 ABI、唯一执行口、状态机、安全阈值、终态判据、8 字轨迹（契约 C1）、
空中安全层参数（`air.yaml` 的 margin/reaction/reachability 未改）。
**未 git commit**（仅 `git add`，见 §4）。

<a id="p1-1-r6-evidence"></a>
## 3. 证据

| 命令 | 结果 |
|---|---|
| `python3 tests/w6_geometry_check.py` | **PASS (maps=minimal,yard,open_field)** |
| 同上 `--out` | 实体 **42** / 图元 **234** / 覆盖 **11.48%** / 小型件 19 / 材料档 5；ring yard 81.53% / 293.5°；C7 车 8.67 / 目标 6.48 / 己方机 9.07 m |
| 断言 (q) | 地面 albedo L **0.396** / 屋面 **0.877** / gap **0.481**（判据 ≥0.30）PASS |
| 渲染（`backend=gz-offscreen-camera`，118 m 俯视） | sRGB：沥青 ~93 / 基层 **135** / 场坪 **150** / 屋面 **202**（R5 时屋面与地面仅差 6 级，现差 67 级） |
| 贴图方差 | 场坪 σ **0.00 → 4.20**；基色亮度保持（150.1 → 148.7） |
| 参照物重叠 | 逐图元检测 **none** |
| GUI 演示 | `w6.launch.py backend:=lightweight scene:=s04… viz:=true` 起 Gazebo GUI + RViz，全话题在线 |
| 内存对照实验 | 8 GB WSL：仅 GUI ~2.0 GB、GUI+RViz ~2.3 GB；**minimal 与 yard 均以 ~1.8–2.1 MB/s 线性增长**（与地图无关，见 §7） |

产物：`/tmp/agc-r6/render_*.png`（渲染帧，含贴图前后对照）、`/tmp/agc-r6/*.json`（核查摘要）。
**注意**：`/tmp` 会在 WSL 重启后清空，**这些证据未被归档到 `experiments/`**——如需长期保留，
请在审查时指定落点（本轮未擅自新建目录）。

<a id="p1-1-r6-git"></a>
## 4. Git 状态

按用户 2026-10-30 指示「gitadd 也要」，已 `git add` **21 个文件 / +5945 −210**，覆盖：
`src/agc_sim/config/maps/`、`src/agc_sim/launch/world_map.py`、`src/agc_sim/materials/`、
`src/agc_sim/worlds/agc_world.sdf`、`src/agc_sim/CMakeLists.txt`、`src/agc_task/**`（新增 viz 与 rviz 配置）、
`tests/w6_geometry_check.py`、`docs/adr/0106…`、`docs/plan/p1-1…`、`MAP_DESIGN_PLAYBOOK.md`。

> **`src/agc_sim/config/maps/` 与 `world_map.py` 自 R4 起未跟踪的风险已消除**
> （`git ls-files` 可验证）。**未 commit**。

<a id="p1-1-r6-criteria"></a>
## 5. 口径变更（**需 Leader 追认**，不得由执行者自行定案）

1. **实体上限 40 → 46**（断言 (o) `n_obstacles_le_46`）。理由：尺度参照物若做"无碰撞装饰"，
   会出现"看着撞了却穿过去"的演示事故 → 只能进几何真源、计入实体数。现 42，余量 4。
2. **新增断言 (q) `q_luma_bands`**：屋面 albedo L − 基层地面 albedo L **≥ 0.30**，且屋面必须用
   `roofpanel` 档。这是"区分度"第一次可自动判定（此前只在文档里写目标）。
3. **材质档变更**：新增 `roofpanel`(0.06/0.40)；`steel` 由 **0.75/0.35 → 0.35/0.42**。
   依据（实测）：无环境贴图时 **metalness 才是渲染亮度杠杆**——metalness=0.75 的金属屋面
   渲染只有 **83/255**，旁边 metalness=0 的混凝土檐 **161/255**；即"提亮 albedo 对金属件无效"。

<a id="p1-1-r6-deviations"></a>
## 6. 偏离 / 需裁定项（**如实登记**）

1. **超出 round-3 白名单** ⚠：本轮改动了 `agc_task`（新节点/launch/config/CMake）、`agc_sim`
   的 `CMakeLists.txt` 与 `worlds`、`tests/w6_geometry_check.py`、`docs/plan`。
   round-3 白名单只覆盖 `src/agc_perception/launch/**` 等。**这属白名单偏离，交 Leader 裁定**。
2. **测试口径变更**（§5 三项）。
3. **参照物落位**：`trailer_a` 首版压到 `container_yard_a`，已移到 `(-8,-40)`；重叠检测现为 none。
4. **`/tmp` 证据未归档**（§3 末）。
5. **RViz 占位栅格在本机显示不出来**：RViz 的 `OccupancyGrid` 着色器链接失败
   （`indexed_8bit_image`：active samplers … same texture image unit），且 `/agc/map` 以 2 Hz 重发。
   已把该显示**缺省关闭**并在配置里注明；marker 层不受影响。
6. **内存增长与地图无关**（§7），但**演示纪律需要写进流程**（单次 ≤30–40 分钟）。

<a id="p1-1-r6-mem"></a>
## 7. 本轮的唯一"环境级"发现（非本任务缺陷）

用户报告演示时 WSL 卡死、内存 2 GB → 10 GB。**对照实验**（同一 lightweight 栈，只换地图）：

| 地图 | 客机 used 增长 | gz RSS 增长 |
|---|---|---|
| minimal（2 根柱子） | +362 MB / 135 s | +245 MB / 135 s |
| yard（42 实体 / 234 link） | +191 MB / 60 s | +128 MB / 60 s |

→ **两种地图同斜率（~1.8–2.1 MB/s）**，故与障碍物数量无关；增长来自 **Gazebo GUI（OGRE2）自身**。
放大因素是：8 GB 的 `.wslconfig` 上限 + 未开 `autoMemoryReclaim` + 本轮取证时**与 GUI 并存**的
无头 `gz sim --headless-rendering`（每次 +1–1.5 GB）。

已做降载：`viz_markers` 静态层改为**只发一次**；占位栅格缺省关闭。

<a id="p1-1-r6-exit"></a>
## 8. 出口判据核对（**本轮不能让 P1-1 通过**）

| 判据 | 状态 |
|---|---|
| 2 张地图可启动、派生链核查通过 | ✅ |
| 三图几何核查 PASS（含新地图） | ✅ |
| C7 出生净空重算并核查 | ✅ |
| 空中安全层存在可行解（静态） | ✅ |
| 文档写明障碍族边界 | ✅ |
| **yard 上主场景（s04）跑通一次，终态 `TRACKING_SUCCESS`** | ❌ **未达成** |

该项自 round-2 起就未取得（上次失败为 `start rejected: air_hover_timeout`，PX4 EKF 侧）。
**本轮只跑了 `backend:=lightweight`，未跑 `full`**，所以 P1-1 的验收仍缺这一条。
**结论：请 Leader 按「待审查」处理，不要按「已验收」处理。**

<a id="p1-1-r6-next"></a>
## 9. 请求 Leader 的最小下一步

1. **补认** round-4 / round-5 / round-6 三轮的"用户授权、无书面 request"这一形态。
2. **追认 §5 三项口径变更**，并裁定 §6.1 的白名单偏离。
3. 指定 §3 证据的归档落点（`experiments/` 下哪个目录）。
4. 裁定是否需要为"**8 字轨迹净空无正式断言**"这件事单独立项
   （当前只有"待机环带 ≥90°"是自动判据；8 字净空仅靠已丢失的 `/tmp` 核验器算过）。
5. 若后续要推进 `full` 链：先解决 PX4 EKF 发散（`px4_run_root` 隔离 + 预热），
   否则该出口判据无法取得。
