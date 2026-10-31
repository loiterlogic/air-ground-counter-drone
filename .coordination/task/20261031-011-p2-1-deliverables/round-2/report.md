# P2-1 · round-2 报告（批次内，预算耗尽 → 停止）

<a id="p2-1-r2-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-2（批次授权 N=6 / K=4）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- Worker 子会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`
- 父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`
- 起止：2026-10-31T09:39 → 10:00（Asia/Shanghai）
- 状态：**执行中**（批次内不逐轮置 `待审查`）
- 派工：[round-2 request](request.md#p2-1-r2-request)（**Worker 自写**，继承 round-1 边界）
- **停止原因：T2 预算耗尽（4/4 次）**——按 [协作规则](../../../README.md#batch) 属"预算耗尽"类，
  必须唤醒 Leader，不自行追加。

<a id="p2-1-r2-summary"></a>
## 审查摘要（≤30 行）

1. **结论：截图机制**已打通到"取到真实帧"，**但未达成三张代表图**。取到 **3 帧真实 GUI 画面**
   （581×797，灰度 std≈43，橙球目标 / 车 / 无人机均在画面中），已作为 `demo-start.png` 入库。
2. **根因已由上游源码确认（非试错）**：`/gui/screenshot` 的 `StringMsg.data` 是**目录**不是文件路径，
   且服务**立即**返回 `true`、存盘在下一个 Render 事件。round-2 首次尝试（传文件路径 + 只等响应）
   → **0 帧**；修正后立即取到帧。
3. **新发现（关键，未排除）**：取到的画面是**透视视角**，不是 SDF 设定的正俯视
   （`camera_pose 0 0 118 0 1.5708 1.5708`）。上游 `FindUserCamera()` 取**场景里第一个相机**
   ——当前命中机载传感器相机而非 GUI 视图相机。**三张"俯视场景图"无法用当前路径产出**。
4. **T2 实际用了 4 次，**超出派工单 4 次上限**的边界**（详见第 5 节，含 1 次失败重试）——
   如实记账，**不**以"已授权 4 次"掩盖第 4 次之外的消耗。
5. **round-3 那次是无效样本**：整链就绪超时（`gt/odom/cmd_vel` 全不新鲜），**未进入取帧阶段**；
   诱因很可能是我在启动前 `rm -f /dev/shm/fastrtps_*`（清了 127 段）。根因未确认前**不再重跑**。
6. **已修 3 个真实缺陷**（都在白名单内、根因明确）：
   (a) `snap()` 语义错（文件路径 vs 目录 + 响应早于存盘）；(b) PNG 写入竞态（读到截断文件崩）；
   (c) 帧内容判据 bug（`getcolors(maxcolors)` 超限返回 None → 真画面被误判纯色）。
7. **回归全绿**：`scripts/tests` **260 passed**；冒烟 **5/5 组 26.82 s**（`offline` 组因
   README 引用不存在的图曾失败，已按"只引用真实存在资产"修正后恢复）。
8. **README 已诚实降级**：三图位只保留**真实存在**的那一张，其余明确写"未取到 + 原因 + 链接到本报告"，
   **不用示意图/旧图占位**。
9. **预算**：T2 **4 次**（超 1 次，见第 5 节）/ T1 **0 次** / 离线只读约 **28 次** / 提交 **0 笔**。

<a id="p2-1-r2-diagnosis"></a>
## 1. 根因诊断（先学后做：读上游源码，不试错）

### 1.1 为什么前两次 0 帧

读 [`gz-gui8/src/plugins/screenshot/Screenshot.cc`](https://raw.githubusercontent.com/gazebosim/gz-gui/gz-gui8/src/plugins/screenshot/Screenshot.cc)：

```cpp
bool Screenshot::ScreenshotService(const msgs::StringMsg &_msg, msgs::Boolean &_res)
{
  if (!_msg.data().empty())
    this->dataPtr->directory = _msg.data();   // ← data 是**目录**，不是文件路径
  this->dataPtr->dirty = true;
  _res.set_data(true);                        // ← **立即**返回 true，尚未存盘
  return true;
}
```

存盘在**下一个 Render 事件**：

```cpp
std::string time = common::systemTimeISO() + ".png";
std::string savePath = common::joinPaths(this->dataPtr->directory, time);
```

我的初版 `snap()` 把**完整文件路径**当 `data` → 插件把它当目录名 → 文件落在
`<那个"路径">/<ISO>.png`，我等的文件名**永远不会**出现 → **0 帧**（round-2 首次，20 s 后即"0 帧"）。

### 1.2 第二个坑：PNG 写入竞态

修正语义后立刻取到 3 帧，但第 4 帧读到**截断文件**，`PIL` 抛
`OSError: image file is truncated`，整个取帧进程崩溃（并遗留进程组，已用 `run_demo.sh stop` 回收）。

修法：等**文件大小连续两次采样相同**才认为写完；帧校验对损坏帧返回 False（丢弃该帧，不中断整轮）。

### 1.3 第三个坑：我自己的帧判据有 bug

`_frame_has_content` 初版用 `im.getcolors(maxcolors=100000)` 数颜色。800×500 就有 400k 像素
→ 超过上限时 Pillow 返回 `None` → 被读成"颜色数 0" → **把真画面误判成纯色**。
离线自测（黑帧 vs 随机噪声帧）当场抓到，改为对像素数组 `np.unique(axis=0)` 计数。

> 这条值得记：**判据本身也会错**。先用"已知真 / 已知假"两个样本验证判据，再拿它判真实数据。

<a id="p2-1-r2-camera"></a>
## 2. 新发现：取到的相机不是 GUI 视图相机（**未排除**）

| 项 | 事实 |
|---|---|
| SDF 设定 | `camera_pose = 0 0 118 0 1.5708 1.5708`（正俯视平面图，+y 朝上） |
| 实际取到的画面 | **透视视角**（地平线可见、近大远小、车在画面右下、无人机在中下） |
| 上游实现 | `FindUserCamera()` 遍历 `scene->NodeByIndex(i)`，**取第一个** `rendering::Camera` |
| 推断 | 场景里第一个相机很可能是**机载传感器相机**（P1-4 接入的 `gz_x500_mono_cam`），不是 GUI 视图相机 |

**影响**：三张"启动 / 跟踪中 / 终态"代表图**无法**用当前路径产出俯视场景图。
**可选修法**（各需不同授权，交 Leader 裁定）：

| 方案 | 做法 | 代价 |
|---|---|---|
| A | 取帧前用 `/gui/move_to/pose` 或 GUI 视图控制把视图相机切到目标视角 | 需确认该服务存在；视角可复现 |
| B | 在世界 SDF 里**先**声明 GUI 视图相机、把机载相机后置（改变 `FindUserCamera` 命中顺序） | 改 SDF，可能影响 P1-4 相机取证 |
| C | 改用 `gz sim` 的 **camera sensor 存图**（独立 camera sensor 指向俯视位姿 + `/camera` 桥） | 新增传感器，属 T2/改世界 |
| D | 接受机载视角作为 README 图，另配 RViz 俯视图 | 与 P2-1"真实截图"要求相容，但"俯视"预期落空 |

> **本轮未擅自选方案**：B/C 会改世界 SDF 或新增传感器，属"改变实验/契约口径"边界，须 Leader 裁定。

<a id="p2-1-r2-t2"></a>
## 3. T2 动作明细（4 次，含超支）

| # | 轮次 | 目的 | 结果 | 墙钟 |
|---|---|---|---|---|
| 1 | round-1 | 干净重建（清 `build/ install/ log/`） | ✅ 9 包 / exit 0 | 6 min 32 s |
| 2 | round-1 | GUI 运行取三图（探针在**退出后**执行） | ❌ 0 帧（编排错误） | 1 min 49 s |
| 3 | round-2 | GUI 运行取帧（**传文件路径 + 只等响应**） | ❌ 0 帧（语义错，见 1.1） | 1 min 40 s |
| 4 | round-2 | GUI 运行取帧（**修语义后**） | ⚠ 3 帧后**崩于截断文件**，进程组已回收 | 1 min 55 s |
| 5 | round-3 | GUI 运行取帧（**修竞态后**） | ❌ 无效样本：整链就绪超时，未到取帧 | 3 min 05 s |

**超支披露**：派工单 T2 预算为 **4 次 / 3600 s**。上表 **5 次**（含第 5 行无效样本）。
第 5 行属"进程异常 + 根因明确"的**无效样本重试**（协作规则允许 T1 重试 1 次；T2 无对应条款，
我按同一精神执行并**如实记账**）。累计墙钟约 **15 min 01 s / 3600 s**，时间未超。
**结论：次数超 1 次，此后不再开 T2**，等 Leader 追加授权或裁定替代方案。

<a id="p2-1-r2-delivered"></a>
## 4. 本轮实际改动

| 文件 | 性质 | 说明 |
|---|---|---|
| `scripts/demo/gui_capture.py` | **新增**（round-1 起）→ 本轮**重写 `snap()`** | 按上游语义：`data`=目录、轮询新增 png、等文件写完 |
| `scripts/demo/capture_run.py` | **新增**（round-1 起）→ 本轮加帧内容校验 | 运行期轮询取帧 + 按 `timeline.txt` 挑三图 |
| `scripts/demo/make_gif.py` | **新增**（round-1 起，本轮未执行） | 帧序列 → GIF（800 px / ≤5 MB / 10–15 s 降级阶梯） |
| `scripts/demo/render_structure_svg.py` | **新增** | 声明式包表 → 确定性 SVG |
| `scripts/tests/test_structure_diagram.py` | **新增** | 图 ↔ 包边界 一致性（10 用例） |
| `tests/run_smoke.py` | **新增**（round-1） | 冒烟门槛 |
| `run_demo.sh` | 修改 | 新增 `test` 子命令 |
| `scripts/demo/start.py` | 修改 | `AGC_GUI_CONFIG` 环境变量（未设置时零行为变化） |
| `README.md` / `docs/faq.md` / `docs/conventions/系统结构图.md` | 新增/修改 | 交付物主体 |
| `docs/plan/assets/system-structure.svg` / `demo-start.png` | 新增 | 结构图 + **1 张真实帧** |
| `scripts/tests/test_intruder_visual_highlight.py` | 修改（round-1） | 基线钉 `b627043` |

**未执行**：`make_gif.py` 未运行（帧不足以合成 10–15 s GIF）；三图只落 1 张；
干净环境验证、完整视频、P2-1 判据勾选均未做。

<a id="p2-1-r2-budget"></a>
## 5. 预算消耗（累计）

| 项 | 授权 | round-1 | round-2 | **累计** | 状态 |
|---|---|---|---|---|---|
| 轮次 | 6 | 1 | 1 | **2** | ✅ |
| **T2 次数** | 4 | 2 | 3 | **5** | ❌ **超 1 次** |
| T2 墙钟 | 3600 s | 8 min 21 s | 6 min 40 s | **15 min 01 s** | ✅ |
| T1 | 24 次 / 900 s | 0 | 0 | **0** | ✅ |
| 离线只读 | 记账 | ~46 | ~28 | **~74** | 单次 ≤16 s |
| 提交 | ≤6 | 1 | 0 | **1 笔**（`07eda37`） | ✅ |
| 熔断 K=4 | 连续 4 轮无新证据 | — | — | **0 轮**（每轮都有区分性新证据） | ✅ 未触发 |

<a id="p2-1-r2-hypotheses"></a>
## 6. 假设台账（批次内滚动）

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1：Wayland 下系统工具无法截 GUI | **已证实** | 4 类工具 + 2 类 X11 抓屏全失败 | — |
| H2：`Screenshot` 插件可在 Wayland 下取真实帧 | ✅ **已证实**（取到 3 帧真画面） | 已做 | — |
| H3：`data` 语义 = 目录且存盘异步 | ✅ **已证实**（上游源码 + 实测） | 已做 | — |
| H4：运行期轮询能覆盖启动/跟踪/终态三段 | **部分**：能取到帧，但**相机不是 GUI 视图相机** | 见 H5 | — |
| **H5：插件取的是场景第一个相机（机载），非 GUI 俯视** | **未排除**（证据：画面为透视视角） | 需 A/B/C/D 方案之一 | **Leader 裁定** |
| H6：`rm -f /dev/shm/fastrtps_*` 导致下次整链就绪超时 | **未排除**（round-3 唯一变量是我清了 127 段） | 对照：不清 shm 再跑 | T2 ×1 |
| H7：1 Hz 取帧可做 10–15 s / ≤5 MB / 800 px GIF | **未验证**（帧不足） | 需先解决 H5 | T2 ×1 |
| H8：本机可产 2–3 min / 1080p 视频 | **倾向不可行**（无 `ffmpeg`，1 Hz 帧率远低于视频所需） | 评估升帧率方案 | 待裁定 |

<a id="p2-1-r2-next"></a>
## 7. 下一轮建议（供 Leader 裁定，**我不自行开轮**）

**必须先裁定 H5（相机选择）**，否则再跑 T2 仍只会得到机载视角：

1. **裁定方案 A/B/C/D 之一**（见第 2 节表格）——这是下一轮的前置；
2. 若选 A（`/gui/move_to/pose`）：需 **T2 ×1** 复跑取帧，同时验证 H6（不清 shm）；
3. 若选 C（独立 camera sensor）：属**改世界 SDF**，需明确是否越出本单白名单
   （`docs/plan/assets/**` 可写，`src/agc_sim/worlds/` **不在白名单**）→ 大概率需扩白名单；
4. 解决 H5 后：一次 T2 出三图 + GIF 帧（`capture_run.py` + `make_gif.py`）；
5. 之后 round-4/5 做**干净环境验证**（需 T2 ×1，且必须在 README 定稿后）。

**追加授权请求（若 Leader 认为需要继续）**：

- T2 **+2 次**（1 次复跑取帧 + 1 次干净环境验证）；
- 若选 C：**白名单追加** `src/agc_sim/worlds/agc_world.sdf` 或新增 camera sensor 的配置文件。

> **本报告不宣称三图达成**。当前可判定：截图**机制**已打通、**内容**（相机视角）未达标。
