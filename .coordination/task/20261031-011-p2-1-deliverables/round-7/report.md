# P2-1 · round-7 报告（新批次首轮：A + D 落地，doctor 误报已修并实测取证）

<a id="p2-1-r7-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-7（**新批次首轮 N=4 / K=4**）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- **Worker 子会话 ID：`7eb40b67-31c3-4a50-b313-e084cf01bdd7`**
- **父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`**
- 起止：2026-10-31T11:55 → 12:05（Asia/Shanghai）
- 状态：**执行中**（批次内）
- 派工：[round-7 request](request.md#p2-1-r7-request)（**Worker 自写**，继承 [round-6 审查](../round-6/review.md#p2-1-r6-review) 裁定 A + D）

<a id="p2-1-r7-summary"></a>
## 审查摘要（≤30 行）

1. **A 落地**：4 处运行期解析类位置改为**自定位**（`run_demo.sh` 用 `BASH_SOURCE`；
   `common.py` / `w6_geometry_check.py` / `test_w6_viz_registration.py` 用 `__file__`）。
2. **D 落地**：新增 [`test_root_self_location.py`](../../../scripts/tests/test_root_self_location.py)
   **10 用例**，含**白名单逐条理由**；**反向对照验证过**（重注入 bug → **4 failed**）。
3. **`doctor` 误报已修，且**实测取证**（不是推理）：
   - **修复前**（round-6）：`/tmp` 克隆 → `doctor` **PASS 14/14**，路径 `/home/chen/AGC/install`（**误报**）；
   - **修复后**（本轮）：`/tmp/agc-r7-verify` 克隆 → **`exit=1`**，报
     **`缺少 /tmp/agc-r7-verify/install/setup.bash`**（**克隆自己的路径**）。
4. **分类表**（第 3 节）：交付/验证路径 **4 处需修、4 处可保留**（契约默认值 / 注释 / 报错文字）；
   `scripts/tests/` **18 个文件里 17 个本就自定位**，仅 1 个需修
   （**修正 Leader 转述的"21 个"**——那是含 `.pyc` 的宽口径，见 §3.1）。
5. **契约默认值未动**：`air_bringup.launch.py` 的 `agc_root` 仍为 `/home/chen/AGC`，
   且 `toolchain_root_check.py` 的校验仍在（有回归断言，防"为可移植而改契约"）。
6. **回归**：`scripts/tests` **276 passed**；冒烟 **5/5（23.80 s）**；断链 **0**。
7. **预算**：**T2 = 0 次**（纯离线）；T1 0；离线约 22 次。提交 `7fe7814`。
8. **未做**（按裁定）：`scripts/research/**`、`scripts/archive/**`、`docs/**`、`.coordination/**`、
   冒烟未调用的 `tests/**` → **忠实登记为"开发/历史工具不可移植"**，未假装修好。

<a id="p2-1-r7-classification"></a>
## 1. 分类表（按"是否用于运行期解析文件"判定）

### 1.1 需修（运行期解析类，**已修**）

| 文件 | 用途 | 原值 | 改为 | 证据 |
|---|---|---|---|---|
| `run_demo.sh:32` | 定位工作区 / 产物 / 脚本目录 | `ROOT="/home/chen/AGC"` | `ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"` | `bash -n` 通过；克隆实测见 §2 |
| `scripts/demo/common.py:28` | `WORLD_SDF` / `GZ_PLUGIN_DIR` / 产物目录 / **`agc_root` 透传** | `ROOT = '/home/chen/AGC'` | `ROOT = dirname(dirname(dirname(realpath(__file__))))` | `common.ROOT == 本仓实际位置`（有回归断言） |
| `tests/w6_geometry_check.py:50` | 冒烟 `geometry` 组的几何真源解析 | `ROOT = '/home/chen/AGC'` | 上溯两级 `__file__` | 冒烟 `geometry` OK |
| `scripts/tests/test_w6_viz_registration.py:29` | 冒烟 `offline` 组读 `w6.launch.py` | `ROOT = '/home/chen/AGC'` | 上溯三级 `__file__` | 冒烟 `offline` OK |

### 1.2 可保留（白名单，**每条有理由**）

| 位置 | 理由 |
|---|---|
| `src/agc_air/launch/air_bringup.launch.py`（3 处：1 默认值 + 2 注释/报错） | **契约默认值**：`agc_root` 的 launch 默认值，受 [`toolchain_root_check.py`](../../../scripts/toolchain_root_check.py) 断言保护；round-6 审查明令**不得改**（改它等于改契约口径）。另两处是注释与报错提示文字，不参与解析 |
| `src/agc_task/launch/w6.launch.py`（3 处：1 默认值 + 2 注释/报错） | 同上。**运行期**由 `start.py` 显式传 `agc_root:=common.ROOT` 覆盖，故默认值只是兜底声明 |
| `scripts/toolchain_root_check.py`（1 处） | 工具本身要**校验**这个默认值，故必须知道该字面量 |
| `tests/run_smoke.py` | **已是自定位**（`realpath(__file__)`），只核验不改 |

### 1.3 不做（**忠实登记为不可移植**，非"已修"）

| 范围 | 文件数（含该串） | 处置 |
|---|---|---|
| `scripts/research/**` | 19 | 研究期工具，不在交付/验证路径；**不可移植** |
| `scripts/archive/**` | 64 | 一次性探针，证据归档后冻结；**不可移植** |
| `docs/**` | 30 | 历史文档/取证记录，**改写即伪造记录**；**不移植** |
| `.coordination/**` | 21 | 交接历史记录；**不移植** |
| `tests/**`（冒烟未调用者） | ~104 文件含该串（多数是历史核查） | 需完整 SITL 才有意义，不在"陌生人跑起来"路径；**不可移植** |

### 1.4 一处口径更正（**Leader 转述的"21 个"**）

Leader 在 round-6 审查里写 `scripts/tests/**` **21 个文件**含该串。我逐文件核过：

- `scripts/tests/*.py` 实际 **18 个文件**；
- 其中 **17 个已用 `realpath(__file__)` / `abspath(__file__)` 自定位**；
- **仅 1 个**（`test_w6_viz_registration.py`）写死；
- 差异来源：**21** 应是把 `__pycache__/*.pyc`（含该串的编译产物）一并计入的宽口径。

> 这是**口径差异而非谁错**，但影响"要改多少"的判断，故记明。

<a id="p2-1-r7-doctor"></a>
## 2. `doctor` 误报：修复前后实测取证

### 2.1 修复前（round-6 记录，Leader 已复核）

```text
git clone /home/chen/AGC /tmp/agc-clone-test   →  ls install/ 不存在
/tmp/agc-clone-test/run_demo.sh doctor          →  PASS 14/14  ← 误报
  GZ_SIM_SYSTEM_PLUGIN_PATH = /home/chen/AGC/install/agc_sim/lib   ← 原仓库
```

### 2.2 修复后（本轮实测）

```text
git clone /home/chen/AGC /tmp/agc-r7-verify
  grep BASH_SOURCE run_demo.sh        → 第 36 行（新代码已进克隆）
  ls install/                          → 不存在（预期）
/tmp/agc-r7-verify/run_demo.sh doctor  →  exit=1
  错误：工作区未构建
    缺少 /tmp/agc-r7-verify/install/setup.bash        ← 克隆自己的路径 ✅
    先构建：cd /tmp/agc-r7-verify && colcon build --symlink-install
```

**判据**：① 非零退出码 ✅；② 报的路径是**克隆自己的** ✅；③ 给出**可执行的下一步**（在克隆目录构建）✅。

> **踩到的一个坑（值得记）**：我第一次克隆验证时 `doctor` **仍 PASS**——因为改动**尚未提交**，
> `git clone` 取的是 HEAD（旧代码）。**"实测取证"必须先把改动提交**，否则测的是旧版。

<a id="p2-1-r7-regression"></a>
## 3. D 回归（防复发）

[`scripts/tests/test_root_self_location.py`](../../../scripts/tests/test_root_self_location.py)，**10 用例**：

| 用例 | 断言 |
|---|---|
| `test_no_literal_root_in_self_locating_files[4 个文件]` | 运行期解析类文件的**代码行**不得含字面量根（注释里提到不算） |
| `test_run_demo_root_uses_bash_source` | `ROOT=` 赋值必须含 `BASH_SOURCE` |
| `test_common_root_uses_dunder_file` | `ROOT=` 赋值必须含 `__file__` |
| `test_smoke_entry_self_locates` | 冒烟入口自定位 |
| `test_contract_default_still_intact` | **契约默认值必须仍在**（防为"可移植"改契约） |
| `test_allowed_entries_have_reason` | 白名单每条有 ≥8 字理由，且文件存在 |
| `test_doctor_reports_clone_path_not_hardcoded` | `common.ROOT == 本仓实际位置` |

**反向对照（证明回归不是摆设）**：把 `run_demo.sh` 与 `common.py` 改回字面量 →
**4 failed**（`[run_demo.sh]` / `[common.py]` / `test_run_demo_root_uses_bash_source` /
`test_common_root_uses_dunder_file`）；恢复后 **10 passed**。

<a id="p2-1-r7-budget"></a>
## 4. 预算消耗

| 项 | 授权 | 本轮 | 说明 |
|---|---|---|---|
| 轮次 | **N=4（新批次）** | **1** | 余 3 |
| **T2** | 累计上限 **15** | **0** | 纯离线（按裁定） |
| T1 | 批次余量 | 0 | |
| 离线只读 | 记账 | ~22 | 单次 ≤16 s |
| 提交 | — | 1 笔 | `7fe7814` |

**红线自检**：未改契约默认值 ✅ · 未碰 `/dev/shm` ✅ · 未处置他人进程 ✅ · 未写 `~/.gz` ✅ ·
未碰 `research/`、`archive/`、`docs/`、`.coordination/` ✅ · 未用旧图/示意图 ✅ · 未碰视频 ✅。

<a id="p2-1-r7-next"></a>
## 5. 下一轮建议（round-8，克隆实测）

1. `git clone /home/chen/AGC /tmp/<新目录>`；
2. **负向取证**：未构建时 `doctor` 必须 **FAIL** 且报克隆自己的路径 —— **本轮已提前完成**
   （§2.2），round-8 可复现一次作为独立证据；
3. 克隆内 `colcon build`（记耗时）；
4. `doctor` **PASS**；
5. 按 README **默认形态（GUI）** 跑到终态；**产物必须落克隆自己的 `experiments/`**，
   且**不得**启动原仓库仿真（用路径 + md5 取证）。

**预计需 T2 1 次**（克隆内跑一次演示）；预算累计 10/15，充足。
