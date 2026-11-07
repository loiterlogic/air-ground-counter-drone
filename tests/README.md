# tests/ 验收核查（acceptance checks）

> 本目录是**验收 / 回归核查**：每个脚本针对一个风险项 / 能力项**断言行为**，**退出码 0 = PASS、非 0 = FAIL**。
> 多为只读核查或自包含 harness；部分需拉起完整链路 / SITL，故**不接 CI**，手动按需运行。

从 `scripts/` 迁入（2026-10-18 curation）：**只改路径、不改名**。历史文档（ADR / checklist / 评审）中出现的 `scripts/<name>_check.py` 即本目录同名文件。

## 两个入口（职责不重叠）

| 入口 | 何时跑 | 是否启仿真 | 耗时 |
|---|---|---|---|
| [`run_smoke.py`](./run_smoke.py) | **每次提交**（离线冒烟，含 DDS 契约闸门与 toolchain pin 一致性） | 否 | ~40 s |
| [`run_full_regression.py`](./run_full_regression.py) | **定时**（`full` 整链回归，3 场景） | **是**（独占 GZ/PX4/DDS） | ~240 s |
| [`run_n3_matrix.py`](./run_n3_matrix.py) | **里程碑**（回归矩阵：四类要求，4 格） | **是** | ~580 s |

```bash
./run_demo.sh test # 离线冒烟（8 组）
python3 tests/run_full_regression.py --list # 整链回归：先看要跑什么
python3 tests/run_full_regression.py # 整链回归（定时任务用这个）
python3 tests/run_n3_matrix.py --list # 回归矩阵：四类要求
python3 tests/run_n3_matrix.py # 回归矩阵（4 格；无目标负例与 vision 臂均已无承载者）
```

**无目标负例已退役**（2026-11-06）：`s17` 原本靠 `air_perception` 的 FOV 收窄制造"看不见"，
但 `air_fusion` 退役后 `/agc/air/obs` 无人订阅，`gt_adapter` 又无几何门控 ⇒ 该前置条件
**无法构造**。用户裁定「彻底删」后，`perception` 场景轴、`air_perception` 节点、
`perception_sensors*.yaml` 与 `s17` 场景号一并删除，防复活闸门见
`scripts/tests/test_retirement_ledger.py`。加严判据（`visibility_rate==0` / `reason==TIMEOUT` /
无 `fco_exposure_s>0`）**保留**在代码里，作为将来重新立项后的判据模板。

**GUI 留证**：`python3 scripts/demo/capture_run.py --out <dir> --scene <场景>`。
**必须给可达终态的场景**：默认场景在 GUI 下偶发 `air_hover_timeout`，那时时间线无状态跳变，
三张代表帧取不到（实跑验证过）。已知局限：固定俯视机位下"启动/跟踪"两图可能几乎相同，
工具会在 `capture-manifest.json` 的 `notes` 里如实标注，不伪装成三张不同时刻。

整链回归**按 `episode_runner` 的 `report.json` 判定**，不解析日志；并把 `INFRA`
（`ready=false` / `air_hover_timeout` / watchdog）与 `FAIL`（任务没打成）分开标注——
`air_hover_timeout` 是已知**偶发** infra，先重跑一次再判定。

## 运行

```bash
python3 tests/run_all.py # 列出全部核查
python3 tests/run_all.py --run check_lifecycle_resource_state.py
python3 tests/run_all.py --all --timeout 600 # 全跑（带超时）
```

<a id="categories"></a>
## 三分类：哪些能进默认冒烟，哪些不能

59 个 `check_*.py` 按**运行前提**分三类。口径不是约定俗成，而是**机械可判**、
由 `checklib.check_categories()` 单一实现；`check_doc_counts.py` 判据 e 拿它与本表逐项对账，
所以"表里写 22、实际 21"会让冒烟变红。

| 类 | 数量 | 判据 | 能否进**默认**冒烟 | 跑法 |
|---|---|---|---|---|
| `static` | **4** | 不 import `rclpy`，且不涉及 `experiments/` | **能**（默认 8 组里的静态核查全属此类） | `./run_demo.sh test` |
| `evidence` | **22** | 不 import `rclpy`，但接受 `--experiments-root` | **不能** | `--with-evidence` 可选组 |
| `needs_sim` | **33** | `import rclpy`：判定要活着的 ROS 图 / 仿真 | 不能 | `run_all.py --run <name>` |

另有 **2** 个 `docs_*_check.py`（`docs_link_check.py` / `docs_tooling_check.py`）是文档护栏，
命名上不属于 `check_*.py`，分别进冒烟 `docs` 组与离线单测。合计 **59 + 2 = 61** 个验收脚本。

**为什么 `evidence` 不能进默认冒烟**（2026-11-06 实测，不是推测）：

用空证据根 `--experiments-root /tmp/emptyexp` 跑这 22 个，**21 个 FAIL**（唯一 PASS 的是
`check_obs_versioning`，见下）。默认冒烟承诺两件事——"**只读**"与"**无产物也全绿**"——
而证据核查两条都破：它们读 `experiments/` 的历史 run，并把本次结果写成新的证据目录。
硬塞进去的结果是门槛天天红、然后被人忽略，比没有门槛更糟。

**唯一的例外**：`check_obs_versioning.py` 判的是"obs v1 逐位可回放 / v2 维度正确"，
**纯内存计算**，不读任何历史证据——它在空证据根下**如实 PASS**（只把 `e4.json` 写进去）。
这属于"如实通过"而不是"静默跳过"：它把自己那 11 条断言逐条打印出来。分类仍归 `evidence`
是因为它**写**证据目录（破坏"只读"），而不是因为它**读**证据。

```bash
python3 tests/run_smoke.py --list # 8 组（默认）
python3 tests/run_smoke.py --list --with-evidence # 9 组（多出 evidence）
python3 tests/run_smoke.py --with-evidence # 跑 8+1 组
python3 tests/run_smoke.py --with-evidence --experiments-root /tmp/emptyexp # 如实 FAIL（rc=1）
python3 tests/run_evidence_checks.py --list # 单独看这 22 项
```

证据根默认 `<repo>/experiments`；`--experiments-root` 只改**读/写的位置**，
不改任何核查的判定逻辑。没给 `--report` 的那几项（`check_rl_command_attribution` /
`check_visibility_active_window`）取该根下**最新 run** 的 `report.json`——
"取最新"是显式规则（`checklib.latest_report`），不是随便挑一个。

## 文档护栏（起）

下面两个是**纯静态、秒级、无副作用**的护栏，改文档后应当跑一遍：

| 脚本 | 断言 | 用法 |
|---|---|---|
| [`docs_link_check.py`](./docs_link_check.py) | 活跃范围 markdown 的**本地链接可解析、锚点存在**（显式 `<a id>` / 标题 slug / `#L<n>` / `.md:<line>`） | `python3 tests/docs_link_check.py`；`--include GLOB` 追加范围；`--strict-history` 把历史断链也算失败 |
| [`../scripts/adr_index.py`](../scripts/adr_index.py) | `docs/adr/README.md` 与 `docs/adr/*.md` 的**编号/标题/Status/结论一致** | `python3 scripts/adr_index.py --check` |
| [`docs_tooling_check.py`](./docs_tooling_check.py) | 上面两个工具**自身的口径**（断链/锚点/代码块排除/历史范围/索引幂等/漂移检测） | `python3 tests/docs_tooling_check.py`；不碰真实仓库，临时目录造最小项目 |
| [`check_dds_contract.py`](./check_dds_contract.py) | DDS 契约（含 **case e：活跃代码不得写死 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`**） | `python3 tests/check_dds_contract.py`；已进默认冒烟组 `dds`，见 [ADR-0028](../docs/adr/0028-dds-discovery-range-and-transport.md#guard) |

`docs_link_check.py` 的排除边界是**刻意的**，不是忽略：

- 围栏代码块与行内代码里的"链接"是示例/模板，不解析；
- 绝对路径（`/home/...`、`/opt/ros/...`）与 `experiments/` 内路径是**取证记录**，指向本机源码树或本地保留的证据，计入"证据引用"而不判断链；
- `docs/archive/` 属**历史范围**：断链逐条列名、不计入退出码（历史路径是当时事实，改写即伪造记录，见 [ADR-0002](../docs/adr/0002-docs-source-of-truth-and-reference-discipline.md#top)）。
- **指向本机保留路径的链接**（`experiments/`、`toolchain/`、`reference/` 等被 `.gitignore` 排除的目标）：
  本地完整检出里可解析，公开 clone 中必然缺失。单独统计为"本地可解析 N 条 / 本地也缺失 M 条"，
  **既不计入通过、也不计入断链**；`M > 0` 时逐条列出（那才是真断链）。
  （`reference/` 旧树已于 2026-10-31 退役删除，见 [ADR-0025](../docs/adr/0025-publishing-boundary-and-retirement.md#top)；排除项**保留**，以备用户从备份恢复后仍适用。）
- 扫描范围含 `.agents/**/*.md`（技能资源自身）与 `scripts/archive`、`docs/**` 下的 README 索引，
  因此"别人指向技能"和"技能内部链接"都会被检查。

退出码：`0` = 活跃范围无断链；`1` = 有断链；`2` = 用法/环境错误。

## 纪律：测试基线**不得跟随 `HEAD`**

写"改动前 vs 改动后"的回归时，基线**必须钉成常量 rev**，不能取 `HEAD`：

```python
BASELINE_REV = 'b627043' # 改动入库前的最后一次提交
r = sub('git -C %s show %s:%s > %s' % (ROOT, BASELINE_REV, REL_PATH, tmp))
if r.returncode != 0:
    pytest.skip('git 里取不到基线 %s' % BASELINE_REV) # 跳过要**说明**，不静默通过
```

**为什么**（2026-10-31实测踩到）：`test_intruder_visual_highlight.py` 曾用
`git show HEAD:<path>` 取"改动前"基线。当时改动尚未提交，`HEAD` 恰好等于改动前——
但一次**正常入库**之后，`HEAD` 就变成了"改动后"，于是：

| 断言 | 后果 |
|---|---|
| "剥掉新增元素后与基线逐字节一致" | **恒真**（自己跟自己比）→ 守卫静默失效 |
| "原有 joint 数应 +1" | **恒假**（基线已含新增）→ 误报 |

**恒真的守卫比失败的守卫更危险**：它看起来一直在跑，其实什么都没守。
基线钉常量后，入库不再改变基线语义；取不到 rev 时 `skip` 并打印原因，而不是静默通过。

## 命名

按**被测能力**命名：`check_<能力>.py`（`run_*` 是入口，不是核查）。

## 共用脚手架 `checklib.py`

`check_*.py` 历史上各自抄了一份 `_read` / `_load` / `_code_only` / `dump`，且已漂移。
[`checklib.py`](./checklib.py) 收编**实现逐字相同**的那些纯函数：

| 函数 | 用途 | 与旧副本的区别 |
|---|---|---|
| `read_text` | 读文本，缺失返回 `None` | 老的"严格版"用 `read_text_strict`（缺失即抛） |
| `load_json` | 读 JSON，缺失返回 `None` | 不吞解析错误 |
| `code_only` | 剥整行注释 | 用于"注释里提到 `rm -rf` 不算违规" |
| `strip_code` / `section_number_hits` | markdown 去代码块 + 扫章节号引用 | 文档门禁专用，示例写法不算违规 |

新增核查**直接 import**；有状态的 harness（起节点、抓话题）仍各写各的——那些差异是真实的，
不该被"统一"伪装掉。
