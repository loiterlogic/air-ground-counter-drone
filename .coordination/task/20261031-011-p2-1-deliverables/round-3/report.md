# P2-1 · round-3 报告（结构性阻断，停止并唤醒）

<a id="p2-1-r3-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-3（批次续跑）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- Worker 子会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`
- 父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`
- 起止：2026-10-31T10:13 → 10:33（Asia/Shanghai）
- 状态：**执行中**（批次内）
- 派工：[round-3 request](request.md#p2-1-r3-request)（**Worker 自写**，已按 10:19 阈值修正 + 用户两条裁定补正）
- **唤醒原因：阻塞**（不是预算耗尽）——自然运行**无法取帧**，取帧**必然斜视**，二者互斥。

<a id="p2-1-r3-summary"></a>
## 审查摘要（≤30 行）

1. **结论：本轮目标不可达，属结构性矛盾**，不是"再跑一次就能成"。请求裁定，不空转。
2. **自然运行实测：0 帧**。`argv` **无** `--gui-config` → 日志**无** `Loading config` → 走 SDF `<gui>` 块
   → 该块**不含** `Screenshot` 插件 → `/gui/screenshot` 服务**不出现** → 取帧不可能。
   但**任务本身跑通**：`TRACKING_SUCCESS` / `tracking_milestone`，回收 36 进程 / 残留 0。
3. **SDF `<gui>` 块的相机姿态确为 `0 0 118 0 1.5708 1.5708`（正俯视）** —— 与用户所见一致，
   佐证用户裁定 ①"平时看到的就是正俯视平面图"。**自然运行路径的视角是对的，只是取不到帧。**
4. **取帧路径实测必斜视**：`--gui-config` 会让 gz-gui 加载**两层**配置——
   round-2 的 launch.log 逐字有**两行** `Loading config`：
   `Loading config [/home/chen/AGC/experiments/p2-1/round-2/gui.config]`（我的派生配置，含 Screenshot + 正俯视）
   → `Loading config [/home/chen/.gz/sim/8/gui.config]`（**用户配置，后加载，覆盖**）。
   用户配置第 44 行 `camera_pose=-6 0 6 0 0.5 0`（3/4 视角）→ 这就是 round-2 三帧 **skyband=0.2848** 的来源。
5. **因此**：**视角正确 ⇔ 取不到帧**；**能取帧 ⇔ 视角被覆盖成斜视**。两条路径互斥，
   在当前授权下（禁改 SDF / 禁加传感器 / 禁写 `~/.gz`）**无解**。
6. **skyband 数值（预登记口径，已按 10:19 阈值修正为 ≤0.10 / ≥0.20）**：
   round-2 三帧 = **0.2848**（tilted）；本轮**无帧可测**。
   我的实现与 Leader 复算逐位吻合（0.28），口径已对齐，可独立复核。
7. **阈值与判读逻辑已按你 10:19 修正并 T0 自测**：`classify(0.06)=top_down`、`classify(0.15)=ambiguous`、
   `classify(0.28)=tilted`；`classify_pair` 两帧同侧才下结论（0.06+0.08→top_down；0.06+0.28→ambiguous）。
8. **预算**：T2 **1 次**（自然运行，无效样本——服务未上线，未进入取帧阶段）；T1 **0 次**；
   离线只读约 14 次。**未动 `/dev/shm`、未写 `~/.gz`、未改 SDF、未加传感器**（逐条遵守）。
9. **未唤醒过早**：第 1 次 T2 后即判定结构性阻断，不再开第 2 次（开了也一样 0 帧）。

<a id="p2-1-r3-evidence"></a>
## 1. 本轮 T2 实测（自然运行）

| 项 | 值 |
|---|---|
| 命令 | `capture_run.py --out experiments/p2-1/round-3 --duration 110 --interval 1.0 --no-gui-config --probe-topdown` |
| 真实 argv | `ros2 launch agc_task w6.launch.py backend:=full scene:=s04_static_static_obs_track seed:=0 world_map:=yard gz_args:=-r -v 3 <world> observe_yaw_mode:=target viz:=true gui_render_backend:=auto agc_root=...`（**无 `--gui-config`**） |
| demo 目录 | `experiments/demo/20261031-102028/` |
| 任务结果 | ✅ **`TRACKING_SUCCESS` / `tracking_milestone`**（`experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-102047-8660/metrics/summary.json`） |
| 回收 | ✅ 36 进程 / 残留 0（10.4 s） |
| **取帧** | ❌ **0 帧**（服务未上线） |
| `/gui/screenshot` | **不出现**（日志无 `Screenshot service on`） |

**日志证据**（`experiments/demo/20261031-102028/launch.log`）：

- **无** `Loading config` 行 → 走 SDF `<gui>`；
- GUI 插件加载顺序：`MinimalScene` → `GzSceneManager` → `InteractiveViewControl` → `CameraTracking`
  → `MarkerManager` → …（**无 Screenshot**）；
- 世界 SDF `<gui>` 块插件清单（T0 解析）：`['MinimalScene','GzSceneManager','InteractiveViewControl',
  'CameraTracking','MarkerManager','SelectEntities','VisualizationCapabilities','Spawn','EntityContextMenuPlugin']`
  —— **9 个，不含 Screenshot**；
- 同一块的 `camera_pose = 0 0 118 0 1.5708 1.5708`（**正俯视**）。

<a id="p2-1-r3-contradiction"></a>
## 2. 结构性矛盾（本轮核心发现）

```text
                     ┌─────────────────────────────────────────────┐
  自然运行（默认）───▶ │ SDF <gui> 块：正俯视 camera_pose ✅          │
                     │               但**没有** Screenshot 插件 ❌   │──▶ 取不到帧
                     └─────────────────────────────────────────────┘

                     ┌─────────────────────────────────────────────┐
  设 --gui-config ───▶ │ ① 我的派生配置（Screenshot + 正俯视）       │
                     │ ② ~/.gz/sim/8/gui.config（**后加载覆盖**）    │──▶ 能取帧但斜视(0.28)
                     │    其 camera_pose=-6 0 6 0 0.5 0            │
                     └─────────────────────────────────────────────┘
```

**两层加载是 gz-gui 的既有行为，不是缺陷**：`--gui-config` 只指定"起始配置"，
随后 `~/.gz/sim/8/gui.config` 作为**用户持久化配置**总会再加载并覆盖同名属性。
round-2 的 launch.log 有**逐字两行** `Loading config` 可证。

**因此**在当前三条禁令下（禁改 SDF / 禁加传感器 / 禁写 `~/.gz`），
"取到帧"与"正俯视"**无法同时满足**。这不是执行不力，是授权边界与目标互斥。

<a id="p2-1-r3-options"></a>
## 3. 可选解法（**需你裁定**，我不擅自做）

| 方案 | 做法 | 触碰哪条禁令 | 风险/代价 |
|---|---|---|---|
| **α** | 给 SDF `<gui>` 块**追加** `Screenshot` 插件（1 行 plugin） | **改 `src/agc_sim/worlds/**`**（禁） | 最小改动；正俯视 + 可取帧**同时成立**；需扩白名单 |
| **β** | 取帧时用 `XDG_CONFIG_HOME`/`HOME` 指向**临时目录**，使 `~/.gz/sim/8/gui.config` 不存在 | 不碰 `~/.gz`（只改**本进程环境变量**） | 干净、可复现；但属"改运行环境"，需你确认是否越界 |
| **γ** | 接受**斜视**画面作为交付图（skyband 0.28，如实标注） | 无需改任何东西 | 与用户所见不符；**与你裁定 ①"若 ≥0.20 立即唤醒"直接冲突**，故不可取 |
| **δ** | 由**用户**在自己 GUI 里点一次 Screenshot 按钮存图（人工介入） | 无 | 最省事；但截图时刻/视角由人控制，可复现性弱 |
| **ε** | 认定"当前授权下不可达成"，登记为**已知缺口**，README 只放 1 张 round-2 真帧 + 说明 | 无 | 满足"真实画面"最低要求；GIF 与三图缺 |

**我的建议**：**α**（改 SDF 加 1 个插件）最干净——正俯视与可取帧同时成立，且与你裁定
"用户所见=正俯视"完全一致；代价仅需白名单扩 1 个文件。若你坚持不动 SDF，则 **β** 次优
（不碰任何持久化文件，只改本次运行的 `HOME`/`XDG_CONFIG_HOME`）。

> 我不选 γ：它与你"≥0.20 立即唤醒、照实用自然运行画面"的裁定**逻辑冲突**——
> 自然运行根本取不到帧，所谓"照实用自然运行画面"没有画面可用。

<a id="p2-1-r3-budget"></a>
## 4. 预算消耗（累计）

| 项 | 授权 | r1 | r2 | r3 | **累计** | 状态 |
|---|---|---|---|---|---|---|
| 轮次 | 6 | 1 | 1 | 1 | **3** | ✅ 余 3 |
| **T2 次数** | **8**（r2 追加 +3） | 2 | 3 | **1** | **6** | ✅ 余 2 |
| T2 墙钟 | 5400 s | 8'21" | 6'40" | 1'45" | **16'46"** | ✅ |
| T1 | 24 / 900 s | 0 | 0 | 0 | **0** | ✅ |
| 离线只读 | 记账 | ~46 | ~28 | ~14 | **~88** | 单次 ≤16 s |

**禁令遵守自检**（逐条）：未清 `/dev/shm` ✅ · 未处置他人进程 ✅ · 未改 `src/agc_sim/worlds/**` ✅ ·
未加传感器 ✅ · 未写 `~/.gz`（仅只读） ✅ · 未开第 2 次 T2 ✅ · 未用旧图/示意图 ✅。

<a id="p2-1-r3-hypotheses"></a>
## 5. 假设台账（更新）

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H2 Screenshot 插件可在 Wayland 取真实帧 | ✅ 已证实（round-2 取到 3 帧） | — | — |
| H3 `data`=目录、存盘异步 | ✅ 已证实（上游源码 + 实测） | — | — |
| H5 取的是"场景第一个相机"而非 GUI 视图相机 | ❌ **已排除**（见下） | round-3 自然运行 | — |
| **H-A `--gui-config` 在位置参数后未被解析** | ❌ **已排除** | round-2 log 有 `Loading config [<derived>]` 两行之一 | — |
| **H-B 开关生效但"第一个相机"非配置相机** | ❌ **已排除** | 视角与 `~/.gz/sim/8/gui.config` 位姿**一致**（0.28），非相机选择问题 | — |
| **H-C 用户配置 `~/.gz/sim/8/gui.config` 后加载覆盖派生配置** | ✅ **已证实**（round-3 新增） | 两行 `Loading config` + 位姿一致 | — |
| **H-D 自然运行不含 Screenshot 插件 → 无法取帧** | ✅ **已证实**（round-3 新增） | 本轮 0 帧 + 无 `Loading config` + SDF 9 插件清单 | — |
| H6 `rm -f /dev/shm/*` 致整链就绪超时 | **未排除**（但已禁清 shm，不再测试） | — | — |
| H7 1 Hz 帧可做 10–15 s GIF | **未验证**（无帧） | 需先解 H-C/H-D | — |

> **H5 自我更正**：round-2 我推断"命中机载相机"，本轮**证伪**。真实机制是
> **用户配置覆盖**（H-C），与相机选择无关。你的独立核查（"不采信也不否定"）是对的。

<a id="p2-1-r3-next"></a>
## 6. 下一轮建议（待裁定后执行）

**先裁定 α / β / δ / ε**，再派 round-4：

- 若 **α**：需**白名单追加** `src/agc_sim/worlds/agc_world.sdf`（+1 个 plugin 块，纯视觉）；
  round-4 用 **T2 ×1** 自然运行取三图 + GIF 帧，skyband 预期 ≤0.10。
- 若 **β**：不改白名单；`capture_run.py` 增 `--isolate-user-config`（临时 `HOME`/`XDG_CONFIG_HOME`）；
  round-4 用 **T2 ×1**。需你确认"改本进程环境变量"不算越界。
- 若 **δ**：我给出**操作清单**（在哪点、点完图存哪），由用户产出；我不消耗 T2。
- 若 **ε**：round-4 收尾（README 用 round-2 真帧 + 已知缺口登记 + 干净环境验证 T2 ×1）。

**停止条件已触发**：round-3/4 两轮内未取到"三图 + GIF"→ 但本轮根因是**结构性互斥**而非
"没试够"，故提前判定并请求裁定，避免 round-4 空转（[协作规则](../../../README.md#batch) 熔断精神）。
