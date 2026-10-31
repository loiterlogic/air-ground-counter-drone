# P2-1 · round-5 报告（85 m 重取图 + 统一尺寸 + GIF 十进制口径）

<a id="p2-1-r5-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-5（批次续跑）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- **Worker 子会话 ID：`7eb40b67-31c3-4a50-b313-e084cf01bdd7`**（取自 `DSH_SESSION_ID`）
- **父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`**
- 起止：2026-10-31T11:10 → 11:40（Asia/Shanghai）
- 状态：**执行中**（批次内）
- 派工：[round-5 request](request.md#p2-1-r5-request)（**Worker 自写**，继承 [round-4 审查](../round-4/review.md#p2-1-r4-review)）

<a id="p2-1-r5-summary"></a>
## 审查摘要（≤30 行）

1. **结论：三图 + GIF 全部重出，三图尺寸统一（831×952），GIF 压到十进制口径 2,661,003 B。**
2. **三图**（`docs/plan/assets/`，同一次自然运行 `experiments/demo/20261031-111216`，`TRACKING_SUCCESS`）：

   | 图 | 尺寸 | 时刻 | skyband | md5 |
   |---|---|---|---|---|
   | `demo-start.png` | **831×952** | t≈43.0 s | **0.0000** | `cd04e0cb056aa90731a8af50d7237844` |
   | `demo-tracking.png` | **831×952** | t≈55.4 s | **0.0000** | `29a552ce160e850bb409813f29b38a1f` |
   | `demo-terminal.png` | **831×952** | t≈59.5 s | **0.0000** | `8e7260a49ddbce462ed26101bc5dd1f4` |

3. **GIF** `docs/plan/assets/demo.gif`：9 帧 / **800×916** / **14.4 s** / **2,661,003 B**
   （md5 `5a9055bbdc3973bbb62248946e14dd67`）→ 三项规格达标，且**按十进制 5,000,000 B 有 2.34 MB 余量**。
4. **85 m 已生效**：运行期世界文件与 install/src 三处 `camera_pose` 均为 `0 0 85`；
   实测构图与 118 m 明显不同（中心行边缘位置 118 m：305/529/272 → 85 m：418/411/288）。
5. **本轮 T2 = 1 次**（22 帧已落盘、任务成功），但**收尾崩溃**（我的 bug，见 §4）；
   **帧已全部落盘**，三图与 GIF **全部离线生成，未再消耗 T2**。
6. **修了收尾崩溃的根因**：`stable_median, stable_detail = stable_skyband(...)` 被写在**使用之后**
   → `UnboundLocalError`。已调正顺序，并新增回归 `test_capture_run_closeout.py`（6 用例，
   **反向对照验证过：重注入 bug 后立刻变红**）。
7. **三处更正已落实**：① H-C 与"拖相机"分开表述（见 §3）；② 85 m 来源**已闭合**（用户追认，见 §2）；
   ③ GIF 口径写死十进制字节并写入 manifest（`size_unit` / `max_bytes_limit` / `max_bytes_note`）。
8. **追加自查更正（我自己的事实错误）**：round-1…4 报告把 Worker 子会话 ID 与父会话 ID
   **写成了同一个值**（`session-c1423390…`），来源链不可核。本轮已更正（见抬头），
   并在 §7 记档。
9. **如实记录的局限**：85 m 俯视下车辆位移仅几个像素（三图两两差异 0.02–0.04%），
   "三阶段"靠**时刻**而非画面位移区分；终端 `timeline.txt` 才是阶段证据。
10. **预算**：T2 **1 次**（批次累计 **9/12**）；T1 **0**；离线约 24 次（含 GIF 重压与反向对照）。

<a id="p2-1-r5-corrections"></a>
## 1. 三处更正的落实

### 1.1 ① H-C 与"拖相机"分开（不再过度归并）

round-4 报告写"不是机制不同，而是有没有人在拖相机"——**这是过度归并，本轮改正**：

| 变量 | 证据 | 独立性 |
|---|---|---|
| **H-C：`--gui-config` 触发两层配置、用户配置后加载覆盖 `camera_pose`** | round-2 `launch.log` 第 88/89 行**两行** `Loading config`；覆盖后的位姿与 `~/.gz/sim/8/gui.config` 第 44 行 `-6 0 6 0 0.5 0` 一致 | **独立成立**，不依赖"是否有人拖相机" |
| **H-H：`Screenshot` 取 GUI 实时视图相机 → 拖动/缩放即变** | round-4b 第 3 帧作业区 84.7%→99.9%、平均灰度差 41.4；第 21–22 帧窗口变 1539×999 | **新增的第二个变量**，不改写 H-C |

round-2 那三帧在 3 s 内**近乎相同**（差异像素 0.5%），更像"未被拖动的默认位姿"——
即 H-C 单独就能解释 0.2848，**不需要**引入拖动假设。本轮据此改正表述。

### 1.2 ② 85 m 来源已闭合

- 来源路径（写清，便于复核）：**用户原话（2026-10-31，大意"85 m 合适"）→ 父会话
  `session-c1423390-f175-44e8-a382-fa1b564f7ab5`（Leader 直接确认）→ 本 Worker 会话
  `7eb40b67-31c3-4a50-b313-e084cf01bdd7`**。
- 状态：**已闭合**（round-4 审查 §2.2 的"待用户追认"结案），**不回退 118 m**。
- 生效证据：`/tmp/agc_world_static_obstacles_yard.sdf`、`install/`、`src/` 三处
  `<camera_pose>0 0 85 0 1.5708 1.5708</camera_pose>` 一致。

### 1.3 ③ GIF 口径写死

| 项 | 值 |
|---|---|
| 上限口径 | **十进制 5,000,000 B**（`MAX_BYTES = 5 * 1000 * 1000`） |
| 本次体积 | **2,661,003 B**（2.66 MB），余量 **2,338,997 B** |
| manifest 字段 | `size_unit: "decimal_bytes"`、`max_bytes_limit: 5000000`、`max_bytes_note: "上限按十进制字节计（5000000 B = 5.000 MB），不是 MiB"` |

> round-4 的 5,095,380 B 按 MiB 达标、按十进制 MB **超出**；本轮统一到更严的十进制值，
> 并**不靠模糊口径**宣称达标。

<a id="p2-1-r5-delivered"></a>
## 2. 交付证据

### 2.1 三图（**同一尺寸**，无需缩放）

| 图 | 源帧 | 时刻 | 尺寸 | skyband | md5 |
|---|---|---|---|---|---|
| 启动 | `f-0009.png` | 43.0 s | 831×952 | 0.0000 | `cd04e0cb056aa90731a8af50d7237844` |
| 跟踪中 | `f-0018.png` | 55.4 s | 831×952 | 0.0000 | `29a552ce160e850bb409813f29b38a1f` |
| 终态 | `f-0021.png` | 59.5 s | 831×952 | 0.0000 | `8e7260a49ddbce462ed26101bc5dd1f4` |

- 22 帧**全部 831×952**（Leader 抽查已确认），故**无需缩放**即达标；
  **未生成** `orig/` 备份（不适用：没有发生缩放）。
- 稳定帧统计：`in_main=22 / kept=22 / dropped=0`，中位数 **0.0000 → top_down**。
- 时刻基准：用 `result.json` 的 `started_at` 换算（round-4 修的坑）。

### 2.2 GIF

| 项 | 值 | 规格 | 达标 |
|---|---|---|---|
| 路径 | `docs/plan/assets/demo.gif` | — | — |
| md5 | `5a9055bbdc3973bbb62248946e14dd67` | — | — |
| 帧数 | 9（stride=2 抽自 18 帧窗口） | — | — |
| 尺寸 | **800×916** | 800 px | ✅ |
| 时长 | **14.4 s** | 10–15 s | ✅ |
| 体积 | **2,661,003 B** | ≤5,000,000 B（十进制） | ✅ |
| manifest | `docs/plan/assets/demo-manifest.json` | 含单位口径 | ✅ |

### 2.3 真实 argv（自然运行，**无任何 GUI 配置开关**）

```text
ros2 launch agc_task w6.launch.py backend:=full scene:=s04_static_static_obs_track \
  seed:=0 world_map:=yard gz_args:=-r -v 3 <install>/share/agc_sim/worlds/agc_world.sdf \
  observe_yaw_mode:=target viz:=true gui_render_backend:=auto agc_root:=/home/chen/AGC
```

运行期世界 `/tmp/agc_world_static_obstacles_yard.sdf` 的 `<gui>` 块含 Screenshot 插件、
`camera_pose = 0 0 85`。

<a id="p2-1-r5-crash"></a>
## 3. 收尾崩溃（本轮唯一的失败，已修 + 已加回归）

### 3.1 现象

T2 运行本身**成功**（22 帧落盘、`TRACKING_SUCCESS`、回收正常），但脚本在**收尾**抛：

```text
File "scripts/demo/capture_run.py", line 596, in main
    prefer_size = tuple(stable_detail.get('main_size')) if stable_detail.get('main_size') else None
UnboundLocalError: cannot access local variable 'stable_detail' where it is not associated with a value
```

### 3.2 根因（我的实现顺序错）

我把 `stable_median, stable_detail = stable_skyband(frame_skybands)` 写在了
**使用它的那行之后**（上一轮为加"稳定帧过滤"而插入时放错了位置）。
**这个错只在真实 T2 收尾时才走到**，所以每轮都要付一次昂贵运行才暴露。

### 3.3 修法与回归

- **修**：把赋值移到使用之前（`stable_skyband` → `main_size`/`prefer_size` → `pick_frames`）。
- **回归**：新增 [`scripts/tests/test_capture_run_closeout.py`](../../../scripts/tests/test_capture_run_closeout.py)
  （**6 用例**，T0 静态解析，不执行 `main()`）：
  - `test_used_after_assigned[stable_detail|stable_median|prefer_size]`：用 `ast` 找首次**赋值**行与首次**使用**行，断言赋值在前；
  - `test_module_imports` / `test_stable_skyband_classification` / `test_pick_frames_returns_three_keys`。
- **反向对照（证明回归不是摆设）**：故意把赋值挪回使用之后 → 回归**立即 2 failed**
  （`stable_median`、`prefer_size` 两项变红）；恢复后 6 passed。

> 教训与 round-4 那条同源：**"取到帧"不等于"收尾成功"**。报告必须区分
> "运行阶段成功"与"脚本整体退出码"，否则会把崩溃读成成功。

<a id="p2-1-r5-limits"></a>
## 4. 如实记录的局限

| 项 | 事实 | 处置 |
|---|---|---|
| 三图画面差异极小 | 两两差异像素 **0.02–0.04%**（85 m 俯视下车辆位移仅几个像素） | **不**用放大/裁剪伪造差异；README 已写明"细节可放大、逐秒状态看终端产物" |
| "三阶段"的判据 | 靠**时刻**（43.0 / 55.4 / 59.5 s）与 `timeline.txt` 的状态跳变，**不是**靠画面位移 | 报告与 README 均如实标注 |
| GIF 帧率低 | 0.625 fps（9 帧 / 14.4 s） | 规格内（未规定帧率）；动感弱属俯视视角固有 |
| 帧数 | 22（`--interval 0.8`） | 满足 GIF ≥20 帧要求（GIF 用其中 18 帧窗口抽 9 帧） |

<a id="p2-1-r5-budget"></a>
## 5. 预算消耗（累计）

| 项 | 授权 | r1 | r2 | r3 | r4 | r5 | **累计** | 状态 |
|---|---|---|---|---|---|---|---|---|
| 轮次 | 6 | 1 | 1 | 1 | 1 | 1 | **5** | 余 1 |
| **T2 次数** | **12** | 2 | 3 | 1 | 2 | **1** | **9** | 余 3 |
| T2 墙钟 | 7800 s | 8'21" | 6'40" | 1'45" | 4'30" | 2'10" | **23'26"** | ✅ |
| T1 | 24 / 900 s | 0 | 0 | 0 | 0 | 0 | **0** | ✅ |
| 离线只读 | 记账 | ~46 | ~28 | ~14 | ~31 | ~24 | **~143** | 单次 ≤16 s |

**禁令遵守自检**：未清 `/dev/shm` ✅ · 未处置他人进程 ✅ · 未改 SDF（本轮**只取图**，SDF 未动）✅ ·
未写 `~/.gz` ✅ · 未设任何 GUI 配置开关（自然运行）✅ · 未用旧图/缩放伪造 ✅ · 未碰视频 ✅。

<a id="p2-1-r5-selfcorrection"></a>
## 6. 追加自查更正（会话 ID 记错）

| 项 | 事实 |
|---|---|
| 触发来源 | Leader round-4 审查 §2.2 指出"你的会话 id 与父会话 id 写成同一个，来源链不可核" |
| 实际错误 | round-1…4 四份报告均把 `Worker 子会话 ID` 与 `父（Leader）会话 ID` 写成同一个值 `session-c1423390…` |
| 真实值 | Worker = **`7eb40b67-31c3-4a50-b313-e084cf01bdd7`**（`DSH_SESSION_ID`）；父 = `session-c1423390-f175-44e8-a382-fa1b564f7ab5` |
| 影响 | **仅记录层**：交接消息实际都投到了正确父会话（Leader 确实收到并回信），**未发生误投**；但报告里的来源链无法自证 |
| 处置 | 本轮报告抬头已用真实 ID；**不追溯改写** round-1…4 报告（历史记录不改写），在此记档 |
| 时间 | 2026-10-31T11:36（Asia/Shanghai） |

<a id="p2-1-r5-hypotheses"></a>
## 7. 假设台账（更新）

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H-C 两层配置覆盖视角 | ✅ 已证实（独立成立，**与拖相机无关**） | r3 两行 `Loading config` | — |
| H-E α 后自然运行可取帧 | ✅ 已证实 | r4 / r5 | — |
| H-H `Screenshot` 取 GUI 实时视图相机 | ✅ 已证实（跳变帧差 41.4） | r4 | — |
| **H-I 相机 118 m 偏远** | ✅ 已证实（用户反馈 + 构图实测） | r4 | — |
| **H-J z=85 让作业区更满** | ✅ **已证实生效**（中心行边缘位置 118→85 明显位移） | r5 | — |
| **H-K 85 m 下三图可区分三阶段** | ⚠ **部分**：时刻可区分、画面差异仅 0.02–0.04% | r5 | — |
| **H-L 收尾崩溃可被静态回归拦住** | ✅ 已证实（反向对照 2 failed → 恢复 6 passed） | r5 | — |

<a id="p2-1-r5-next"></a>
## 8. 下一轮建议（round-6）

**round-6 = 干净环境验证**（Leader 已定）：清 `build/install/log` → `colcon build` →
**照 README 从零走通 ≥1 轮**，记耗时/卡点/回改 README。

- 预算：T2 **≤2 次**（累计 9/12，余 3，够用）；轮次余 **1**。
- 前置已就绪：README 与三图 + GIF **均已定稿**（本轮完成），符合"图定稿后再验证 README"的顺序要求。
- 建议记录：`git clone` 或清理后 → 看到画面的**总耗时**、卡在哪一步、README 哪句不清楚 → 回改。
- **完整演示视频**：等用户自录文件路径（本轮未碰）。
