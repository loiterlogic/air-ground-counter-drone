# tests/ 验收核查（acceptance checks）

> 本目录是**验收 / 回归核查**：每个脚本针对一个风险项 / 能力项**断言行为**，**退出码 0 = PASS、非 0 = FAIL**。
> 多为只读核查或自包含 harness；部分需拉起完整链路 / SITL，故**不接 CI**，手动按需运行。

从 `scripts/` 迁入（2026-10-18 curation）：**只改路径、不改名**。历史文档（ADR / checklist / 评审）中出现的 `scripts/<name>_check.py` 即本目录同名文件。

## 运行

```bash
python3 tests/run_all.py                       # 列出全部核查
python3 tests/run_all.py --run w6_r034_check.py
python3 tests/run_all.py --all --timeout 600   # 全跑（带超时）
```

## 文档护栏（P0-3 起）

下面两个是**纯静态、秒级、无副作用**的护栏，改文档后应当跑一遍：

| 脚本 | 断言 | 用法 |
|---|---|---|
| [`docs_link_check.py`](./docs_link_check.py) | 活跃范围 markdown 的**本地链接可解析、锚点存在**（显式 `<a id>` / 标题 slug / `#L<n>` / `.md:<line>`） | `python3 tests/docs_link_check.py`；`--include GLOB` 追加范围；`--strict-history` 把历史断链也算失败 |
| [`../scripts/adr_index.py`](../scripts/adr_index.py) | `docs/adr/README.md` 与 `docs/adr/*.md` 的**编号/标题/Status/结论一致** | `python3 scripts/adr_index.py --check` |
| [`docs_tooling_check.py`](./docs_tooling_check.py) | 上面两个工具**自身的口径**（断链/锚点/代码块排除/历史范围/索引幂等/漂移检测） | `python3 tests/docs_tooling_check.py`；不碰真实仓库，临时目录造最小项目 |

`docs_link_check.py` 的排除边界是**刻意的**，不是忽略：

- 围栏代码块与行内代码里的"链接"是示例/模板，不解析；
- 绝对路径（`/home/...`、`/opt/ros/...`）与 `experiments/` 内路径是**取证记录**，指向本机源码树或本地保留的证据，计入"证据引用"而不判断链；
- `docs/archive/`、`.coordination/archive/` 属**历史范围**：断链逐条列名、不计入退出码（历史路径是当时事实，改写即伪造记录，见 [ADR-0066](../docs/adr/0066-decision-applicability-and-reference-discipline.md)）。
- **指向本机保留路径的链接**（`docs/archive/specs/`、`experiments/`、`reference/`、`toolchain/` 等被 `.gitignore` 排除的目标）：
  本地完整检出里可解析，公开 clone 中必然缺失。单独统计为"本地可解析 N 条 / 本地也缺失 M 条"，
  **既不计入通过、也不计入断链**；`M > 0` 时逐条列出（那才是真断链）。
  （`reference/` 旧树已于 2026-10-31 退役删除，见 [ADR-0107](../docs/adr/0107-retire-old-tree-paused-switch-and-legacy-backlog.md#top)；排除项**保留**，以备用户从备份恢复后仍适用。）
- 扫描范围含 `.agents/**/*.md`（技能资源自身）与 `scripts/archive`、`docs/**` 下的 README 索引，
  因此"别人指向技能"和"技能内部链接"都会被检查。

退出码：`0` = 活跃范围无断链；`1` = 有断链；`2` = 用法/环境错误。

## 纪律：测试基线**不得跟随 `HEAD`**

写"改动前 vs 改动后"的回归时，基线**必须钉成常量 rev**，不能取 `HEAD`：

```python
BASELINE_REV = 'b627043'   # 改动入库前的最后一次提交
r = sub('git -C %s show %s:%s > %s' % (ROOT, BASELINE_REV, REL_PATH, tmp))
if r.returncode != 0:
    pytest.skip('git 里取不到基线 %s' % BASELINE_REV)   # 跳过要**说明**，不静默通过
```

**为什么**（2026-10-31 P2-1 实测踩到）：`test_intruder_visual_highlight.py` 曾用
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
