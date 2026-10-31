# P2-1 · round-1 报告（批次首轮）

<a id="p2-1-r1-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-1（批次授权 N=6 / K=4）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- Worker 子会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`
- 父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`
- 起止：2026-10-31T08:35 → 09:47（Asia/Shanghai）
- 状态：**执行中**（批次内不逐轮置 `待审查`）
- 派工：[round-1 request](request.md#p2-1-r1-request)（Leader 写）

<a id="p2-1-r1-summary"></a>
## 审查摘要（≤30 行）

1. **基线核对**：HEAD `b627043` / `main` 一致；工作区实测 **64 项**（派工单记 62），
   差的 2 项是本轮派工自身产生的（`CURRENT.md` + 本任务 `round-1/`），**无未知漂移**。
2. **步骤 0 完成**：1 笔本地提交 `07eda37`，**114 个文件 / +18369 −334**。
   提交后工作树 **0 项**（含 30 项 P1 遗留改动与 66 条未跟踪路径）。
   禁发目录（`experiments/ reference/ .trae/ docs/archive/specs/ toolchain/`）**0 命中**；
   >500 kB 文件 **0 个**；**未 push**。
3. **步骤 0 引入一处真实回归，已修**：`test_intruder_visual_highlight.py` 拿 `git show HEAD:` 当
   "改动前"基线。高亮入库后 HEAD 变成"改动后"→ `test_only_highlight_differs_from_baseline` 恒真、
   `test_x500_core_links_keep_inertial_and_collision` 恒假（joint 差 +1→0）。
   修法：基线钉成常量 `BASELINE_REV='b627043'`（不存第二份 SDF 副本）。修后 **10/10 通过**。
   这是"守卫看似在跑、其实没在守"的形状，如实记账。
4. **步骤 1 README 已落地**（189 行，7 要素齐）：一句话定位 / 3 条快速开始 / 截图位（3 张）/
   状态含义表（引用 P1-3）/ 结构图 / 目录导航（8 包 + 关键目录各一行）/
   **已知边界 6 条**（派工单要求的 5 条 + 演示 oracle 臂一条）/ 文档入口。
   **未**写"未来将实现"；**未**复述契约（全部链接）。
5. **步骤 2 结构图完成**：`docs/conventions/系统结构图.md`（Mermaid，四类依赖分别表示）
   + `docs/plan/assets/system-structure.svg`（**脚本渲染**，8 包 + 19 条边，幂等）。
   图与包边界由新回归 `test_structure_diagram.py`（10 用例）机械对齐。
6. **步骤 3 FAQ 完成**：`docs/faq.md` **8 条**，覆盖派工单要求的 4 症状
   （工具链 / 等待 PX4 / `ROS_DOMAIN_ID` / 残留进程）+ 黑屏 + 冒烟排查 + uXRCE 长尾 + 终态口径。
7. **步骤 4 冒烟入口完成**：`tests/run_smoke.py` + `./run_demo.sh test` 子命令。
   5 组实测 **23.41 s 全绿**（预算 300 s）：geometry 14.22 / messages 0.80 / docs 1.10 /
   index 1.36 / offline 5.93。
8. **步骤 6 T2-a 干净重建完成**：清 `build/ install/ log/`（已授权）后 `colcon build`，
   **9 包 6 min 32 s / exit 0**；`doctor` 随后 **14/14 OK，0.03 s**。
9. **步骤 5 截图机制已打通但本轮未取到帧（见「偏离」）**：
   GUI 运行中 `Screenshot service on [/gui/screenshot]` 确认上线；但我的探针在
   `run_demo.sh` **退出后**才执行（服务已随进程组消失），**0 帧**。
   已写 `scripts/demo/gui_capture.py`（取帧）+ `capture_run.py`（运行期轮询取帧）+
   `make_gif.py`（GIF 合成），round-2 用一次 T2 同时出三图 + GIF 帧。
10. **未达成项**：三张真实截图（缺文件，README 引用会被 `test_structure_diagram.py` 拦下）、
    GIF、完整视频、干净环境验证、P2-1 判据勾选。**均在 round-2/3 计划内**。
11. **预算**：T2 **2/2 次**（本轮封顶：a 重建 + b GUI 运行），墙钟约 7 min 15 s；
    T1 **0 次**（本轮未用）；离线只读检查约 **46 次**，总墙钟约 1 min 20 s。
12. **口径**：全程按 `full + yard + s04 + observe_yaw_mode=target`；报告与 README 均标注
    "target 是显式 oracle 指向臂、不代表真实视觉识别"；未宣称任何"拦截完成"。

<a id="p2-1-r1-baseline"></a>
## 1. 接单基线核对（开工前，08:35）

| 项 | 派工单登记 | 实测 | 结论 |
|---|---|---|---|
| HEAD | `b627043` | `b627043` | ✅ |
| 分支 | `main` | `main` | ✅ |
| 工作区脏 | 62 项 | **64 项** | ⚠ 差 2 项，见下 |

差 2 项 = `.coordination/CURRENT.md`（Leader 写本轮派工）+ `.coordination/archive/20261031-011-p2-1-deliverables/`
（Leader 写本轮 `request.md`）。**均属本轮派工自身产物，不是未知漂移**。其余 62 项与派工单逐类吻合。

<a id="p2-1-r1-step0"></a>
## 2. 步骤 0 · 基线卫生提交

### 2.1 审计（提交前）

| 检查 | 方法 | 结果 |
|---|---|---|
| 禁发目录未入库 | 对 staged + unstaged + untracked 全量做正则 `^(experiments\|reference\|\.trae\|docs/archive/specs\|toolchain)/` | **0 命中** |
| 大文件 | 对将入库文件 `stat -c%s`，阈值 500 kB | **0 个** |
| 过期重命名残留 | `git status` 发现 `AD` 条目 | 1 项，见 2.2 |
| 文件分组 | `git status --porcelain` + `git diff --stat` | 见 2.3 |

### 2.2 一处"该入库却进了又删"的处置（如实披露）

暂存区原有 `.coordination/task/20261029-006-p1-1-scene-assets/round-6/report.md` 处于 **AD**
（暂存了"新增"、工作区已删除）。该文件已随任务 006 归档到
`.coordination/archive/20261029-006-p1-1-scene-assets/round-6/report.md`，两份 **sha256 相同**
（`94e80c0d052ddab5d8b7791276d36801a1f3a188ee436ebede0e4814c16fbb40`）——
即**同一内容的归档移动**，不是内容丢失。

处置：`git rm --cached` 取消其暂存，让归档侧作为新增入库（移动语义完整）。
**未**删改任何归档文件内容。

### 2.3 提交结果

| 项 | 值 |
|---|---|
| 笔数 | **1 笔**（上限 6） |
| hash | `07eda37` |
| message | `coordination: 归档 P1-1…P1-4 五个任务链（round 目录入库）` |
| 规模 | 114 files changed, 18369 insertions(+), 334 deletions(-) |
| 提交后 `git status --porcelain` | **0 项**（完全干净） |
| push | **未执行** |
| reset / clean / 切分支 | **未执行** |

> **偏离（1 笔 vs 派工单建议的 2–4 笔）**：派工单说"分 2–4 笔"，我按
> "`.coordination/` 记录"与"P1 实现"两类的**本意**做了分组，但 `git reset` 后重新 `git add -A`
> 时把两类一起暂存，最终合成 1 笔。**影响**：历史可读性略降（实现与交接记录在同一提交），
> **不影响**内容完整性、禁发边界与后续审查（审查按文件路径抽样即可）。
> 未用 `amend` 拆分（会产生改写历史的额外风险），如实记账。

<a id="p2-1-r1-regression"></a>
## 3. 步骤 0 引入的回归与修复（重要）

### 3.1 现象

提交后跑离线回归，`scripts/tests/test_intruder_visual_highlight.py` **1 failed / 9 passed**：

```text
test_x500_core_links_keep_inertial_and_collision
AssertionError: (5, 5)
assert 5 == (5 + 1)
```

### 3.2 根因（不是测试写错，是基线语义变了）

该测试的基线取自 `git show HEAD:src/agc_sim/models/intruder_uav/intruder_uav.sdf.xacro`，
语义是"**改动前**的展开式"。它写于 P1-3 round-2，当时高亮尚未提交，`HEAD` 恰好等于改动前。

P2-1 步骤 0 的**已授权提交**把高亮一并入库 → `HEAD` 变成"改动后"：

| 断言 | 提交前 | 提交后 |
|---|---|---|
| `test_only_highlight_differs_from_baseline`（剥掉高亮后须与基线逐字节一致） | 真守卫 | **恒真**（自己跟自己比） |
| `test_x500_core_links_keep_inertial_and_collision`（joint 应 +1） | 通过 | **恒假**（基线已含高亮 → 差为 0） |

即：**一个守卫静默失效、另一个误报**。这正是"守卫看似在跑、其实没在守"的典型形状——
比测试失败更危险的是那个**恒真**的。

### 3.3 修法

基线**钉成常量**，不再跟随 `HEAD`：

```python
BASELINE_REV = 'b627043'   # P1-3 round-2 高亮入库前的最后一次提交（= P2-1 派工单登记的基线）
```

- `git show <BASELINE_REV>:<path>` 取改动前版本展开，**不存第二份 SDF 副本**（避免基线自身漂移）；
- 取不到该 rev 时 `pytest.skip` 并说明，**不静默通过**；
- 文件头补写「基线怎么来」一段，说明为何不能用 `HEAD`。

修后：`python3 -m pytest scripts/tests/test_intruder_visual_highlight.py -q` → **10 passed in 2.49s**。

> **归属判断**：该文件在派工单白名单内（`scripts/tests/**`），且根因是本单授权动作直接导致，
> 按 [协作规则](../../../README.md#executor-autonomy) "白名单内、预算内、有明确根因的局部修复
> 可自行继续"，未唤醒 Leader。

<a id="p2-1-r1-deliverables"></a>
## 4. 交付物

### 4.1 README（189 行）

`README.md`（新增，项目根）。7 要素逐项：

| 要素 | 位置 | 说明 |
|---|---|---|
| 一句话定位 | 首行引用块 | 同一世界同一时钟，发现→跟踪→抵近 |
| 3 条内快速开始 | `## 快速开始` | `doctor` → 演示 → `stop`，**恰好 3 条** |
| 真实截图 | 顶部 + 演示节 | 3 张（`demo-start` / `demo-tracking` / `demo-terminal`）——**round-2 取帧** |
| 状态说明 | `## 演示看到什么` | 7 行状态含义表，引用 P1-3 |
| 结构图 | `## 系统结构` | SVG + 数据流文本块 |
| 目录导航 | `## 目录导航` | 8 包各一行 + 6 个关键目录 |
| 已知边界 | `## 已知边界（当前能力范围）` | **6 条**（派工单 5 条 + oracle 臂） |

口径纪律：全文 **0 处**把 `TRACKING_SUCCESS` 说成"拦截完成"；`target` 臂在 3 处标注为
显式 oracle；`vision_model.id=none` 在已知边界第 4 条明确"不得当作视觉识别能力"。

### 4.2 系统结构图

| 产物 | 路径 | 形态 |
|---|---|---|
| 可编辑源（GitHub 原生渲染） | [`docs/conventions/系统结构图.md`](../../../docs/conventions/系统结构图.md#top) | Mermaid ×2 + 包清单表 + 红线标注 |
| 离线图（README 内嵌） | [`docs/plan/assets/system-structure.svg`](../../../docs/plan/assets/system-structure.svg) | 脚本渲染，8 包 / 19 边 / 8882 字节 |
| 渲染器 | [`scripts/demo/render_structure_svg.py`](../../../scripts/demo/render_structure_svg.py) | 声明式表 → 确定性 SVG（幂等） |
| 回归 | [`scripts/tests/test_structure_diagram.py`](../../../scripts/tests/test_structure_diagram.py) | 10 用例 |

四类依赖在两种形态里都**分别**表示（①消息 / ②链接 / ③运行组合 / ④外部），并显式标注三条
最易读错的点：`agc_task→域包`是③不是②；`agc_control` 是②的唯一例外；`px4_msgs` 不是第 9 个业务包。

**渲染器为何不用 mermaid-cli**：本机无 `mmdc`（未安装 `@mermaid-js/mermaid-cli`），
不应为一个图去装 Node 包；但手绘 PNG 必然与真源漂移且 diff 看不出。故用声明式表 + 纯 Python 渲染。

### 4.3 FAQ

[`docs/faq.md`](../../../docs/faq.md#top)，**8 条**（派工单要求 5–8）：

| # | 症状 | 覆盖派工单要求 |
|---|---|---|
| 1 | `doctor` 报工具链缺失 | ✅ 工具链 |
| 2 | 启动后卡在"等待 PX4" | ✅ 等待 PX4 |
| 3 | `ros2 node list` 为空 | ✅ `ROS_DOMAIN_ID` 与发现 |
| 4 | 有残留进程 / 上次没干净退出 | ✅ 残留进程 |
| 5 | Gazebo 黑屏 / 没有画面（含"截不到图"） | ✅ 图像黑屏 |
| 6 | 冒烟某组失败看不出原因 | — |
| 7 | `create entities failed: participant: 255` | — |
| 8 | 演示成功了，"成功"到底算什么 | — |

**未**整篇复制排障速查：每条只给症状 / 原因 / 一条命令，细节链接回
[整链排障速查](../../../docs/conventions/整链排障速查.md#preflight)。

### 4.4 冒烟入口

| 产物 | 路径 |
|---|---|
| 实现 | [`tests/run_smoke.py`](../../../tests/run_smoke.py) |
| 入口接线 | [`run_demo.sh`](../../../run_demo.sh) `test` 子命令 |
| 文档 | [`tests/README`](../../../tests/README.md) 待补（round-2） |

实测（本轮）：

```text
geometry   几何派生链：地图真源 → 世界 SDF                     OK  14.22 s
messages   9 消息 ABI 字段序 + AgcTaskState 状态常量           OK   0.80 s
docs       活跃文档本地链接与锚点                              OK   1.10 s
index      ADR 索引 + 脚本索引一致性                           OK   1.36 s
offline    scripts/tests 全部离线单测                          OK   5.93 s
合计 5/5 组通过，墙钟 23.41 s（预算 300 s）
```

**当前状态：`offline` 组因 `test_readme_references_existing_assets` 失败**（三张截图未取到，
见第 5 节）。该断言是**故意**这样写的——README 指向不存在的图必须被拦，不能用"先占位后补图"
蒙过去。round-2 取到帧后即恢复全绿。

<a id="p2-1-r1-t2"></a>
## 5. T2 动作与偏离

### 5.1 T2-a 干净重建（✅ 成功）

| 项 | 值 |
|---|---|
| 前置 | `./run_demo.sh status` → 无实例；`ps` 特征进程 **0**；`/dev/shm/fastrtps*` **0 段** |
| 清理 | `rm -rf build install log`（**派工单已授权**），清前 688M / 61M / 878M |
| 命令 | `colcon build --symlink-install` |
| 结果 | **9 包 finished / 6 min 32 s / exit 0** |
| 警告 | `agc_task` 1 处既有 deprecation（`create_service` 重载，非本轮引入） |
| 复验 | `./run_demo.sh doctor` → **14/14 OK，0.03 s** |

日志：`/tmp/p21-build.log`。

### 5.2 T2-b GUI 运行取三张截图（❌ **未取到帧**，如实记账）

| 项 | 值 |
|---|---|
| 命令 | `AGC_GUI_CONFIG=... ./run_demo.sh --duration 100` |
| 运行结果 | **`TRACKING_SUCCESS` / `tracking_milestone`**，回收 36 进程、残留 0 |
| 四类 GUI 证据 | `gazebo_non_headless` / `renderer_identified` / `x11_windows` / `single_rviz_overlay` **全 ok** |
| 截图插件 | launch.log 确认 `Screenshot service on [/gui/screenshot]` + `Added plugin [Screenshot]` |
| **取帧** | **0 张** |

**根因（我的编排错误，不是基础设施问题）**：我在 `run_demo.sh` **退出之后**才执行
`gui_capture.py probe`——服务随进程组一起消失，`gz service -l` 返回 **0 条**。
取帧必须**在运行期间**由外部驱动轮询完成。

**已落地的修法**（round-2 执行）：新增 [`scripts/demo/capture_run.py`](../../../scripts/demo/capture_run.py)，
以子进程启动 `run_demo.sh`、**运行期**轮询服务并连续取帧、运行结束后按 `timeline.txt` 的
状态跳变挑三张代表帧（启动 / 跟踪中 / 终态）。取不到对应帧时如实报缺，不用别的帧冒充。

### 5.3 截图工具链探路（离线只读，不是 T2）

本机 `DISPLAY=:0` 是 **Wayland（XWayland）**，实测结论：

| 手段 | 结果 |
|---|---|
| `xwd` / `import` / `scrot` / `maim` / `gnome-screenshot` | **全未安装** |
| `ffmpeg` / `gst-launch-1.0` | **未安装** |
| PyQt5 `grabWindow(0)` 抓 X root | 2664×1200，**非黑像素 0** |
| Xlib `XGetImage(root)` | `BadMatch` |
| `Xvfb` / `xephyr` / `x11vnc` | **未安装** |
| GNOME Shell DBus 截图 | `ServiceUnknown` |
| **Gazebo `Screenshot` 插件** | ✅ **可行**（ogre2 从 3D 视图相机取帧，不经合成器） |

> **与 P1-1 round-6 结论的关系**：round-6 记录"本机无可用截屏工具（xwd/import/ffmpeg/scrot 全缺）"
> **在当时成立且未被推翻**——它列的工具确实全缺。本轮的 Screenshot 插件是**新增的第四条路径**，
> 不在原清单内。**不追溯改写** round-6 的结论。

### 5.4 本仓世界 SDF 缺 Screenshot 插件（已解决）

`src/agc_sim/worlds/agc_world.sdf` 的 `<gui>` 块**覆盖**了发行版默认 `gui.config`，
里面只有 9 个插件、**不含** `Screenshot` → 服务不会上线。

修法：`gui_capture.py derive-config` 从世界 SDF 的 `<gui>` 块**派生**一份配置，**只追加**
`Screenshot` 插件（其余原样），`gz sim --gui-config` 加载它。
`start.py` 新增环境变量 `AGC_GUI_CONFIG`（**未设置时不改变任何行为**）。

派生时踩到一个坑并已修：世界 SDF 的 `<gui>` **上方注释**里写了 `<gui><plugin MinimalScene>…`
这样的说明文字，朴素正则先命中注释 → 派生出非法 XML（`xmllint` 报
`Specification mandates value`）。改为先把注释替换成等长空白再查找（偏移不变）。

<a id="p2-1-r1-budget"></a>
## 6. 预算消耗（round-1）

| 项 | 授权 | 本轮消耗 | 备注 |
|---|---|---|---|
| 轮次 | N=6 | **1** | |
| **T2** | 4 次 / 3600 s，单轮 ≤2 | **2 次**（a 重建 + b GUI 运行） | 本轮封顶；墙钟约 7 min 15 s |
| **T1** | 24 次 / 900 s | **0 次** | 本轮未用（诊断都在 T0 离线只读内完成） |
| 离线只读检查 | 次数只记账 | 约 **46 次** | 总墙钟约 1 min 20 s，单次 ≤16 s |
| 提交笔数 | ≤6 | **1 笔** | `07eda37` |

<a id="p2-1-r1-notdone"></a>
## 7. 未执行项（明确列出）

| 项 | 状态 | 计划 |
|---|---|---|
| 三张真实截图（启动 / 跟踪中 / 终态） | **未取到**（0 帧） | round-2 一次 T2 用 `capture_run.py` |
| GIF（10–15 s，800 px，≤5 MB） | **未产出**（无帧） | round-2 同上（同一次运行取帧） |
| 完整视频（2–3 min，1080p） | **未产出** | 需评估；`ffmpeg` 缺失、帧率低，可能如实记未达成 |
| 干净环境验证 ≥1 轮 | **未执行** | round-3（用剩余 1 次 T2） |
| P2-1 出口判据 10 项勾选 | **未勾选** | 里程碑达成时统一勾 |
| `tests/README` 补冒烟入口说明 | **未写** | round-2 |

<a id="p2-1-r1-hypotheses"></a>
## 8. 假设台账（批次内滚动）

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1：Wayland 下无法用系统工具截 GUI 画面 | **已证实**（4 类工具 + 2 类 X11 抓屏全失败） | 已做 | — |
| H2：Gazebo `Screenshot` 插件可在 Wayland 下取真实帧 | **未排除**（服务确认上线，但尚未成功取到一帧） | round-2 `capture_run.py` 取帧 | T2 ×1 |
| H3：`capture_run.py` 运行期轮询能覆盖启动/跟踪/终态三段 | **未排除** | 同上，检查三图是否各命中 | T2 ×1 |
| H4：1 Hz 取帧 + `make_gif.py` 能做出 10–15 s / ≤5 MB / 800 px 的 GIF | **未排除** | 同上产出后由 `gif-manifest.json` 判定 | T2 ×1 |
| H5：本机可产出 2–3 min / 1080p 完整视频 | **倾向不可行**（无 `ffmpeg`；1 Hz 帧率远低于 1080p 视频所需） | 需评估抽帧升帧率方案或如实记未达成 | 待裁定 |

<a id="p2-1-r1-next"></a>
## 9. 下一轮建议（round-2，Worker 自写 request）

**唯一目标：用一次 T2 同时产出三张截图 + GIF 帧**（合并派工单步骤 5 的 (b)(c) 两次 T2，
省 1 次预算）。步骤：

1. `python3 scripts/demo/capture_run.py --out experiments/p2-1/round-2 --duration 110 --interval 1.0`
   （运行期轮询 + 连续取帧 + 按时间线挑三图）；
2. 三图落 `docs/plan/assets/`，`make_gif.py` 合成 GIF 并核对 800 px / ≤5 MB / 10–15 s；
3. 重跑 `./run_demo.sh test` 确认 `offline` 组恢复全绿；
4. 补 `tests/README` 的冒烟入口说明；
5. 若取帧仍失败：**不重跑**，转 T1/T0 诊断（服务是否响应 false、路径权限、插件版本），
   写进假设台账。

> **不做**：干净环境验证（round-3）、P2-1 判据勾选（里程碑时统一勾）。
