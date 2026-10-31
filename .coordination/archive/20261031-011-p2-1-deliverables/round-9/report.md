# P2-1 · round-9 报告（α+ 整类修：launch + YAML + 守护扩容 + 污染迁移）

<a id="p2-1-r9-report"></a>

- 任务 ID：`20261031-011-p2-1-deliverables`，round-9（新批次第 3 轮）
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- **Worker 子会话 ID：`7eb40b67-31c3-4a50-b313-e084cf01bdd7`**
- **父（Leader）会话 ID：`session-c1423390-f175-44e8-a382-fa1b564f7ab5`**
- 起止：2026-10-31T12:19 → 12:35（Asia/Shanghai）
- 状态：**执行中**（批次内）
- 派工：[round-9 request](request.md#p2-1-r9-request)（**Worker 自写**，继承 [round-8 审查](../round-8/review.md#p2-1-r8-review) 裁定 α+）

<a id="p2-1-r9-summary"></a>
## 审查摘要（≤30 行）

1. **α+ 落地（三类来源一次清）**：launch 显式派生 + YAML 删键 **16 处** + C++ 默认值**保留**。
2. **`w6.launch.py` 给 `run_logger` 显式传** `experiments_root=<agc_root>/experiments` 与
   `git_root=<agc_root>`（**`git_root` 未漏**，否则 summary 里 git 身份仍读主仓）。
   值由 `LaunchConfiguration('agc_root')` 派生 → launch 参数在 yaml 之后生效，**覆盖**两者。
3. **YAML 删键 16 处**（8 个文件 × `experiments_root`/`git_root`）：`w6_base` / `m0` /
   `w5_scenario` / `w6_r6_random` / `w6_safety_trigger` / `w6_c4_timeout` /
   `w6_c9_resetfail` / `w6_c9_infeasible`。**删键而非占位**（留不可解析占位会在运行期炸）。
4. **C++ 默认值保留**（`run_logger.cpp:85/86`）：作为**契约式缺省**——`m0_skeleton` / 研究 runner /
   无 `agc_root` 的入口仍会落到它；删了它等于把"写回主仓"的脚枪留在这些入口。
5. **守护扩容**（`test_root_self_location.py` **10 → 13 用例**）：
   + `test_yaml_configs_have_no_absolute_root`（YAML 不得有字面量）
   + `test_cpp_defaults_are_preserved`（**反向守护**：C++ 默认值必须仍在）
   + `test_delivery_launch_overrides_both_keys`（交付 launch 必须覆盖两键，且由 `agc_root` 派生）。
   **三条反向对照全部生效**（各自单独导致 1 failed）。
6. **一处误报已修（不改守卫）**：`test_w6_fix_does_not_touch_task_params` 断言
   "`w6.launch.py` 文本里没有 `declare_parameter` 子串"——我在**注释**里写了这个词触发它。
   **保留守卫、改注释**（改为"C++ 节点默认声明"），未删真正的参数注入。
7. **回归全绿**：`scripts/tests` **279 passed**；冒烟 **5/5（25.63 s）**；断链 **0**。
8. **污染目录已迁移（不是删除）**：13 文件 → `experiments/p2-1/round-8/relocated-eval-…/`，
   逐文件**相对路径 + size + md5** 全一致（diff 无差异）→ 回显两绝对路径核对 → 删原目录；
   同日 **11:44 / 11:46** 两次合法 run **未触碰**（已复核仍在）。
9. **预算**：**T2 = 0**（纯离线）；T1 0；离线约 25 次。提交待本报告后。

<a id="p2-1-r9-launch"></a>
## 1. launch 显式派生

```python
_agc_root = LaunchConfiguration('agc_root').perform(context)
extra = extra + [{
    'experiments_root': os.path.join(_agc_root, 'experiments'),
    'git_root': _agc_root,
}]
```

**离线验证**（不启 ROS，模拟派生逻辑）：

| `agc_root` | `experiments_root` | `git_root` |
|---|---|---|
| `/home/chen/AGC` | `/home/chen/AGC/experiments` | `/home/chen/AGC` |
| `/tmp/agc-clone-x` | `/tmp/agc-clone-x/experiments` | `/tmp/agc-clone-x` |

**轻量栈核对**：`m0_skeleton.launch.py` **无 `agc_root` 参数**（它是 W5/M0 的独立入口，
由 `m0.yaml` / `w5_scenario.yaml` 驱动）。删键后它落到 C++ 默认值（行为不变）——
**这是刻意保留 C++ 默认值的原因**（见 §3）。

<a id="p2-1-r9-yaml"></a>
## 2. YAML 删键（16 处）

| 文件 | 删除的键 | 消费方 |
|---|---|---|
| `w6_base.yaml` | `experiments_root` / `git_root` | `w6.launch.py`（**交付路径**，已由 launch 覆盖） |
| `m0.yaml` | 同上 | `m0_skeleton.launch.py`（独立入口 → 落 C++ 默认值） |
| `w5_scenario.yaml` | 同上 | `w5_safety_scenario.launch.py`（同上） |
| `w6_r6_random.yaml` | 同上 | `scripts/archive/run_w6_r6.sh`（历史脚本） |
| `w6_safety_trigger.yaml` | 同上 | 无脚本引用（场景配置） |
| `w6_c4_timeout.yaml` | 同上 | `scripts/archive/run_w6_fsm.sh` |
| `w6_c9_resetfail.yaml` | 同上 | `scripts/archive/run_w6_r030.sh` |
| `w6_c9_infeasible.yaml` | 同上 | 无脚本引用 |

**选择"删键"而非"改占位"的理由**：
- 留 `""` 或 `"${...}"` 这类占位 → 运行期要么被当成相对路径（写到 CWD，更难查），
  要么 `declare_parameter` 拿到空串后行为未定义；
- 删键后，`declare_parameter` 的**默认值**接管，行为**确定且与删前一致**（对独立入口）；
- 交付路径由 launch 显式覆盖，**与 yaml 是否含该键无关**。

**YAML 仍可解析**（8 个文件逐个 `yaml.safe_load` 通过，`run_logger` 段键数不变或按预期减少）。

<a id="p2-1-r9-cpp"></a>
## 3. C++ 默认值保留（**不删**）

`src/agc_task/src/run_logger.cpp:85/86` 两行**原样保留**：

```cpp
experiments_root_ = declare_parameter<std::string>("experiments_root", "/home/chen/AGC/experiments");
git_root_ = declare_parameter<std::string>("git_root", "/home/chen/AGC");
```

**为什么保留**（Leader round-8 审查 §3.4 的裁定，我执行）：
YAML 删键后，`w6` 之外的独立启动仍会直接落到这两行。**若删 YAML 又删 C++ 默认值**，
这些入口就失去缺省 → "写回主仓"的脚枪被移到更难发现的地方。正确做法是
**默认值作为契约式缺省保留 + 交付 launch 统一覆盖**，并由测试**双向**断言：
① 默认值仍在；② 交付 launch 已覆盖。

<a id="p2-1-r9-guard"></a>
## 4. 守护扩容与反向对照

| 新增用例 | 断言 |
|---|---|
| `test_yaml_configs_have_no_absolute_root` | `src/agc_task/config/*.yaml` 不得含 `/home/chen/AGC` |
| `test_cpp_defaults_are_preserved` | **反向**：`run_logger.cpp` 的两行默认声明**必须仍在**且值未变 |
| `test_delivery_launch_overrides_both_keys` | `w6.launch.py` 必须传两键，且值由 `agc_root` 派生 |

**反向对照（三个独立实验，各只注入一种退化）**：

| 实验 | 注入 | 结果 |
|---|---|---|
| A | `w6_base.yaml` 回注 `experiments_root: "/home/chen/AGC/experiments"` | **`test_yaml_configs_have_no_absolute_root` FAILED** ✅ |
| B | 删掉 launch 的两键注入 | **`test_delivery_launch_overrides_both_keys` FAILED** ✅ |
| C | 把 C++ `experiments_root` 默认值改成 `""` | **`test_cpp_defaults_are_preserved` FAILED** ✅ |

三次均恢复后 **13 passed**。

<a id="p2-1-r9-falsepositive"></a>
## 5. 一处过宽守卫的误报（**保留守卫、改注释**）

### 5.1 现象

`scripts/tests/test_p1_4_baseline_closure.py::test_w6_fix_does_not_touch_task_params` FAILED：

```text
assert 'declare_parameter' not in '#!/usr/bin/...'
  'declare_parameter' is contained here:
    # `declare_parameter` 默认值也是同一字面量 → 克隆到别处跑时评测产物**写回原仓库**
```

### 5.2 判定

该守卫的意图是"**`w6.launch.py` 是 launch 文件，不该出现节点参数声明**"，
实现方式是**纯文本子串匹配**——因此**注释里提到这个词也会触发**。

**我的处置（按 Leader 指示）**：
- **保留守卫不动**（它的意图正确，放宽它会削弱真守卫）；
- **只改我 round-9 新增的注释**：`declare_parameter` → **"C++ 节点默认声明"**；
- **未删**任何真正的 launch 参数注入（`experiments_root` / `git_root` 两键仍在，
  空中控制链节点列表不变）。

**结论**：注释触发了过宽文本守卫；**保留守卫，改注释消除误报**。

<a id="p2-1-r9-pollution"></a>
## 6. 污染目录迁移（复制 → 核对 → 删原）

| 步骤 | 结果 |
|---|---|
| 源绝对路径 | `/home/chen/AGC/experiments/w6-task-eval/20261031-s04_static_static_obs_track-0-121023-3528` |
| 目标绝对路径 | `/home/chen/AGC/experiments/p2-1/round-8/relocated-eval-20261031-121023-3528` |
| 文件数 | **13 → 13** |
| 逐文件核对 | **相对路径 + size + md5 全一致**（`diff` 两份清单**无差异**） |
| 删除前 | **回显两绝对路径 + 安全检查**（源须匹配该时间戳目录、目标须存在） |
| 删除 | `rm -rf` 源目录；复核**已不存在** |
| 合法 run | **11:44（`-114406-7202`）/ 11:46（`-114624-4681`）未触碰**，复核仍在 |

**迁移证据保留**：`experiments/p2-1/round-8/relocated-eval-…/`（含 `config/` + `metrics/`），
属本地证据区，**不入 git**。

<a id="p2-1-r9-budget"></a>
## 7. 预算消耗

| 项 | 授权 | 本轮 | 累计 |
|---|---|---|---|
| 轮次 | N=4 | 3 | 余 1 |
| **T2** | 上限 15 | **0** | 11（余 4） |
| T1 | 批次余量 | 0 | |
| 离线只读 | 记账 | ~25 | |

**红线自检**：未改 C++ 默认声明 ✅ · 未改契约默认值 ✅ · 未碰 `/dev/shm` ✅ ·
未处置他人进程 ✅ · 未写 `~/.gz` ✅ · **未碰 11:44/11:46 合法 run** ✅ ·
未用旧图/示意图 ✅ · 未包装未达成项 ✅ · 删目录前**回显绝对路径确认** ✅。

<a id="p2-1-r9-next"></a>
## 8. 下一轮（round-10，T2 ≤2）：克隆复验

1. 重新从含本轮修复的 HEAD 克隆到新目录；
2. 构建 → `doctor` → **默认 GUI 演示到终态**；
3. 验证四件事：
   - `metrics/summary.json` 落**克隆自己的** `experiments/w6-task-eval/`；
   - `config/params.yaml` 里的 `experiments_root` 指向**克隆**；
   - summary 的 **git 身份指向克隆**（`git_commit` 来自克隆仓库）；
   - **终态解释正常**（不再报"未取得本轮 summary"）；
4. **原仓库 `experiments/demo/` 与 `w6-task-eval/` 均零新增**（前后清单 + md5 取证）。

**预计 T2 1 次**（累计将达 12/15，余 3，充足）。
