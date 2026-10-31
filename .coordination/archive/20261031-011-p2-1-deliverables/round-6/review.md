# P2-1 · round-6 审查（批次末轮）——干净环境通过，但"陌生人能跑"实质不成立

<a id="p2-1-r6-review"></a>

- 任务 ID：`20261031-011-p2-1-deliverables` · 审查人：Leader（DSH） · 2026-10-31
- 被审：[round-6 report](report.md#p2-1-r6-report)
- 裁定：**干净环境验证通过**；**路径硬编码是真实阻塞** → 批准 **A + D**（扩展到交付/验证路径），开新批次执行

## 1. 我亲自复核

| 项 | 手段 | 结果 |
|---|---|---|
| 提交与工作树 | `git log` / `git status` | `32c35f2`（6 文件）、工作树干净 ✅ |
| 判据勾选 | 读 `docs/plan/p2-1-项目交付物.md` | **9/10**；第 3 项（完整视频）**如实留空**并注明"由用户自录，路径待提供" ✅ 未包装 |
| 干净环境证据 | 读 `experiments/p2-1/round-6/` | `build.log` / `walkthrough-demo.log` / `clean-start.txt` 齐 ✅ |
| 硬编码分布 | 我自己 grep 全仓 | `run_demo.sh` 1 处、`scripts/demo` 1 处；另 `scripts/research` 19、`scripts/archive` 64、`tests`（104 文件含该串）、`docs` 30、`src` 13、`.coordination` 21 —— **与报告量级一致** |

**关键补充（我查的，Worker 未列全）**：

- `tests/run_smoke.py` **已经**用 `realpath(__file__)` 自定位 → 冒烟入口本身可移植 ✅；
- `scripts/demo/start.py:114` 已把 `agc_root:=<common.ROOT>` 显式传给 launch → **修 `common.py` 即可让整链用克隆自己的根**；
- 冒烟 5 组里只有 `tests/w6_geometry_check.py` 带 1 处硬编码；`docs_link_check` / `adr_index` / `test_scripts_index` 均 **0**；
- `scripts/tests/**` **21 个文件**含该串（冒烟 `offline` 组要跑它们）；
- `src/agc_air/launch/air_bringup.launch.py` 的 `agc_root` 默认值 `/home/chen/AGC` 是**声明式契约默认值**（受 `scripts/toolchain_root_check.py` 断言保护）→ **不得改**；
  `src/agc_task/config/w6_*.yaml` 6 处的 `experiments_root`/`git_root` 不在 s04 主路径上（`scenarios.yaml` 无这两个键）。

## 2. 裁定：A + D，且范围扩到"交付/验证路径"

**纳入修复（按"是否用于运行期解析文件"判定，不是按字面）**：

| 范围 | 要求 |
|---|---|
| `run_demo.sh` | `ROOT` 用 `BASH_SOURCE` 自定位 |
| `scripts/demo/**` | `common.ROOT` 用 `__file__` 自定位；其余脚本一律经 `common.ROOT` |
| `tests/run_smoke.py` | 已是自定位（只核验，不改） |
| `tests/w6_geometry_check.py` | 该 1 处自定位化（它在冒烟 `geometry` 组里） |
| `scripts/tests/**`（21 个含该串） | **逐个分类**：用于运行期解析文件的 → 自定位；仅出现在注释/文档串/对"规范部署根"的期望值里的 → 可保留。分类表写进报告 |
| `src/agc_task/launch/w6.launch.py`（3 处） | 同样分类；仅默认值声明可保留 |
| **不做** | `scripts/research/**`、`scripts/archive/**`、`docs/**`、`.coordination/**`、`tests/**`（冒烟未调用者）、`src/**` 的契约默认值 —— 忠实登记为"开发/历史工具不可移植" |

**D（防复发）**：新增回归，断言**运行期解析类**的位置不再出现硬编码根；允许显式白名单（契约默认值 / 注释 / 历史文档），白名单要写清理由。
**同时修 `doctor` 的误报**：克隆里没有 `install/` 时必须 **FAIL**（根因是 `common.ROOT` 硬编码，随 A 一并解决，但**必须实测取证**）。

## 3. 新批次授权（N=4 / K=4）

| 轮次 | 目标 | 预算 |
|---|---|---|
| **round-7** | A + D 落地（离线；含 doctor 误报修复 + 归因分类表） | T2 0 |
| **round-8** | **克隆实测**：`git clone` 到 `/tmp/<新目录>` → 先证 `doctor` 在未构建时 **FAIL**（负向取证）→ `colcon build` → `doctor` PASS → 按 README 默认形态跑到终态；产物必须落**克隆自己的** `experiments/` | T2 ≤2 |
| **round-9** | 用户视频接入 + 判据全勾 + 结档准备（**等用户文件**） | T2 0 |

- **追加 T2 +3 次 / +1800 s**（累计上限 **15 次 / 9000 s**）。
- 预登记停止条件：**round-7/8 两轮内克隆仍不能"`doctor` 真实 + 跑到终态" → 判不可达成，停止交台账**；
  达 N=4 或预算耗尽必须唤醒 Leader。
- 红线不变：不碰 `/dev/shm`、不处置他人进程、不写 `~/.gz`、不改契约默认值、不用旧图/示意图、不包装未达成项。

## 4. 我认可的两点

1. **"陌生人克隆"实测是自发的、超出派工单的实验** —— 正是它把"判据实质不成立"挖了出来。这条主动性记一次正面。
2. **README 回改抓到了经典盲点**：`toolchain/` 不纳入版本控制、新 clone 里是空的（"自己写的 README 自己永远看得懂"）。

## 5. 出口判据现状

| 判据 | 状态 |
|---|---|
| 9/10 项 | ✅（含干净环境验证 6.5 min） |
| "陌生人照 README 能跑起来" | ⏳ **round-7/8 修复并实测后才真成立** |
| 完整演示视频 | ⏳ 等用户自录文件 |