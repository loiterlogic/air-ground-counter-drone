# P2-1 · round-3 审查（阻塞唤醒）——裁定 α

<a id="p2-1-r3-review"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · 审查人：Leader（DSH） · 2026-10-31
- 被审：[round-3 report](report.md#p2-1-r3-report)
- 裁定：**α**（给 SDF `<gui>` 块追加 Screenshot 插件）+ **移除** `AGC_GUI_CONFIG` 机制；继续 round-4

## 1. 我亲自复核（不采信自述）

| 声明 | 手段 | 结果 |
|---|---|---|
| `--gui-config` 会加载**两层**配置、后者覆盖视角 | `grep "Loading config"` round-2 `launch.log` | **逐字两行**：`[round-2/gui.config]` → `[/home/chen/.gz/sim/8/gui.config]`（第 88/89 行）✅ |
| 自然运行 argv 无 `--gui-config` | round-3 run `launch.log` 的 `gz_args:=` | 无该开关（出现次数 0）✅ |
| 自然运行 `/gui/screenshot` 不上线 | 同 run 日志 | **0 处** Screenshot ✅（与 SDF `<gui>` 块 9 插件不含该插件一致） |
| 提交与工作树 | `git log` / `git status` | HEAD `f3e88f6`，工作树**干净** ✅ |
| skyband 口径与我的复算一致 | 读 `scripts/demo/skyband.py` + 复算 round-2 三帧 | 双方均 **0.2848** ✅ |
| 三帧不是旧图 | `md5sum` | 与 2026-10-29 各图**互异** ✅ |

## 2. 机制定案（结论）

```text
自然运行  → SDF <gui> 块：camera_pose=正俯视 ✅，但 9 插件无 Screenshot → 取不到帧 ❌
--gui-config → 先派生配置（Screenshot + 正俯视）→ 再加载 ~/.gz/sim/8/gui.config（camera_pose=-6 0 6 0 0.5 0）
               → 后加载覆盖 → 能取帧但斜视（0.2848）
```

- **H-C / H-D 证实**；**H-A / H-B / H5 证伪**。
- **H5 是 round-2 的错误推断**（"命中机载相机"），本轮由执行者**主动更正**，未污染任何结论 → 记档，不追责。
- **用户裁定 ①（默认所见=正俯视）与实测一致**：自然运行路径的**视角是对的**，缺的只是取帧能力。
- 因此"取到帧"与"正俯视"在当前三条禁令下互斥，属**授权边界问题**，不是执行不力；执行者提前停止、不空转 round-4，符合[熔断精神](../../../README.md#batch)。

## 3. 裁定：α（不做 β / δ / ε）

**α**：给 `src/agc_sim/worlds/agc_world.sdf` 的 `<gui>` 块追加 `Screenshot` 插件（照抄本机已验证可用的那份插件块，保持浮动小面板）。
理由：① 让"正俯视 + 可取帧"在**自然运行**下同时成立 → 交付图与用户所见一致；② 仓库自带、**任何人 clone 后都可复现**，不依赖本机 `~/.gz` 私有配置；③ 纯 GUI 插件，不触物理/光照/传感器/`<scene>`/几何真源。

**边界（按此执行）**：

- 白名单**追加** `src/agc_sim/worlds/agc_world.sdf`；**禁止**触 `<scene>` / `physics` / `ground_plane` / 传感器 / `world_geometry.yaml` / `maps/**`。
- 该块注释须写明"**GUI 取证用；不进入仿真、不改变任何物理/感知口径**"。
- 改后必须：`python3 tests/w6_geometry_check.py` **PASS**（尤其断言 (n)），`./run_demo.sh test` 全绿，`scripts/tests` 全绿。
- **必须移除 `AGC_GUI_CONFIG` 机制**（`scripts/demo/start.py` 的环境变量分支 + `gui_capture.py derive-config` 及配套测试）：
  它存在的唯一理由（SDF 无 Screenshot）已被 α 消除，留着就是"会静默把视角换成斜视、产出不代表用户所见的图"的脚枪。
  若移除中发现会影响其它已验证路径 → 改为"显式拒绝 + FAQ 说明"并**立即报告**，不擅自扩大范围。
- **交付图只允许来自自然运行**（不设 `AGC_GUI_CONFIG`）；判定通过线沿用 **skyband ≤0.10**。
- `docs/faq.md` 补一条（≤3 行）：取证时若带 `--gui-config`，gz-gui 会**再加载** `~/.gz/sim/<ver>/gui.config` 并**覆盖**相机位姿 → 视角变了、图不代表用户所见。

**不选** β（临时 HOME 隔离）：能达目的但把"可复现性"押在环境变量上，且 HOME 隔离会顺带影响 ROS/PX4 的其它本地状态，收益不如 α 干净。
**不选** δ（用户手动点）：时刻/视角由人控制，可复现性弱；且本轮已能自动取帧。
**不选** ε（登记缺口）：α 成本仅 1 个插件块 + 1 次 T2，没有理由把"图与用户所见不一致"留成缺口。

## 4. 预算与剩余计划

| 项 | 授权 | 已用 | 本次裁定后 |
|---|---|---|---|
| T2 次数 | 8 | 6 | **上限 10**（+2） |
| T2 墙钟 | 5400 s | 16'46" | **上限 6600 s** |
| 轮次 | 6 | 3 | 余 **3**（round-4/5/6） |

- **round-4**：α 落地 + 自然运行取"启动/跟踪中/终态"三图 + GIF 序列 + skyband 验证 + README 换真图（T2 ≤2）。
- **round-5**：干净环境验证（清 `build/install/log` → `colcon build` → 按 README 走通，≥1 轮，记录耗时与卡点，回改 README）（T2 ≤2）。
- **视频**：用户自录，等文件路径；不占 T2。

## 5. 出口判据现状

| 判据 | 状态 |
|---|---|
| README 7 要素 / 结构图 / FAQ / 冒烟入口 / 已知边界 / 禁发边界 / 第三方资产 | ✅ |
| 截图 + GIF（真实、正俯视、三时刻） | ⏳ round-4（α 后） |
| 干净环境验证 ≥1 轮 | ⏳ round-5 |
| 完整演示视频 | ⏳ 等用户自录文件 |

## 6. 未决 / 待办

- `tests/README.md` 的「测试基线不得跟随 `HEAD`」纪律条：round-3 request 列为步骤 6，报告未见完成证据 → round-4 一并核对补齐。
- 用户录制文件路径未到 → 收尾轮不阻塞其余工作。