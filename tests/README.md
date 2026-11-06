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
./run_demo.sh test # 离线冒烟（6 组）
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

沿用原风险项编号：`w<ws>_r<nnn>_check.py`、`w<ws>_<name>_check.py`。
描述性改名留待**单独一轮**（避免与历史文档引用一次性大改；ADR 史料不重写）。
