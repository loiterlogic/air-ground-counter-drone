# scripts/ 索引

> 本目录**只放当前阶段会用到的长期工具**。研究期工具在 [research/](research/README.md#research)，一次性驱动 / 台架 / 探针在 [archive/](archive/README.md#archive)，验收 / 回归核查在 [../tests/](../tests)。
> 规则与家的划分见 [目录与命名规范](../docs/conventions/目录与命名规范.md#10-产物分类与生命周期)。
> **本索引由 [`scripts/tests/test_scripts_index.py`](tests/test_scripts_index.py) 自动核对**：顶层实际文件集合、本表、[research/README](research/README.md#research) 与 [archive/README](archive/README.md#archive) 任一处漂移即测试失败。

<a id="top-tools"></a>
## 长期工具（顶层 10 个）

| 文件 | 用途 |
|---|---|
| [`episode_runner.py`](episode_runner.py) | 批量跑 episode、三层验收判定、唯一 run 关联、完整性硬门 |
| [`evidence_archive.py`](evidence_archive.py) | 证据不可变归档 + intake manifest（ADR-0006） |
| [`dep_audit.py`](dep_audit.py) | 包依赖审计 |
| [`toolchain_pin_check.py`](toolchain_pin_check.py) | 工具链 pin 清单核对（只读、退出码语义，ADR-0005） |
| [`toolchain_root_check.py`](toolchain_root_check.py) | 工具链根注入 / preflight 校验（ADR-0005） |
| [`third_party_asset_check.py`](third_party_asset_check.py) | 第三方资产 provenance / 许可 / 哈希核对（ADR-0005） |
| [`lock_px4_failsafe_params.sh`](lock_px4_failsafe_params.sh) | 注入 PX4 失效安全参数锁定（ADR-0015） |
| [`w3_target_driver.py`](w3_target_driver.py) | 目标驱动（直线 / 圆周）运行时驱动 |
| [`adr_index.py`](adr_index.py) | 从 `docs/adr/*.md` 生成 ADR 索引；`--check` 校验漂移（纯静态、无副作用，ADR-0025） |
| [`gui_renderer_evidence.py`](gui_renderer_evidence.py) | GUI 渲染后端证据（snapshot + probe，纯 stdlib 库，**无 `__main__`**）；由 `episode_runner.py` 与 `scripts/tests/test_gui_renderer_evidence.py` 导入（ADR-0021/0097） |

跨进程交接叫醒脚本（原 `.coordination/scripts/`）随机制退役已删除（[ADR-0026](../docs/adr/0026-leader-worker-collaboration-and-batch-authorization.md#top)），不属于本目录的长期工程工具索引；现行 Leader / Worker 交接见 [.coordination/README.md](../.coordination/README.md#auto-wake)。

<a id="subdirs"></a>
## 子目录

| 目录 | 放什么 | 索引 |
|---|---|---|
| `research/` | **暂停但未废弃**的研究期工具（W7 / W8 跑批、判定、诊断、取证的脚本）。当前阶段不用，但可复跑、可复核，**不删** | [research/README.md](research/README.md#research) |
| `archive/` | **一次性**驱动 / 台架 / 探针：跑完即归档、证据归档后不再改动，保留供复核 | [archive/README.md](archive/README.md#archive) |
| `tracking/` | 空中跟踪误差取证工具（只读订阅、只落盘；**不是**控制链一部分） | 见下节 |
| `tests/` | 脚本自身的离线单测（不启仿真、不读 ROS 产物），含本索引的自动核对 | [tests/](../tests/README.md)（验收核查在项目根 `tests/`） |

<a id="tracking"></a>
### `scripts/tracking/`

- [`track_err_probe.py`](tracking/track_err_probe.py) —— 空中跟踪误差取证：按仿真时间戳配对
  `/agc/air/tracking_ref`（生效参考）与 `/agc/air/odom`，落 `err_eff` / `err_base` 的 p50/p95。
  **不得**表述为契约 C1 口径；产物标 `not_a_summary_field`。

> 该工具原先在 `scripts/vision/`，2026-11-04 视觉定位路径退役时**迁出并保留**——
> 它与视觉无关，N4 出口判据 1 的跟踪误差对照依赖它（[ADR-0009](../docs/adr/0009-perception-truth-derived-and-vision-path.md#b)）。

> **`research/` 与 `archive/` 的区别**：`archive/` 的语义是"证据归档后冻结"，`research/` 的语义是"研究暂停、脚本仍可重跑"。混在一起会稀释 `archive/` 的冻结语义，故分列。

<a id="new-script"></a>
## 新增脚本前先问一句

1. 它是**当前阶段会用到的长期工具**吗？→ 留 `scripts/` 顶层，并加进上面的表。
2. 它是**研究期工具**（为某次 W7/W8 判定或诊断服务，暂停但未废弃）吗？→ `scripts/research/`，并登记 [research/README](research/README.md#research)。
3. 它是**一次性**（跑完即归档）吗？→ `scripts/archive/`，并登记 [archive/README](archive/README.md#archive)。
4. 它在**断言行为、有退出码语义**吗？→ `../tests/`（项目根，非本目录）。

不要往 `scripts/` 顶层平铺一次性脚本 —— 这正是 P0-4 curation 要根治的问题。**索引漂移靠测试拦，不靠纪律**：新增/移动脚本后跑

```bash
python3 -m pytest scripts/tests/test_scripts_index.py -q
```

<a id="migration"></a>
## 迁移导航（P0-4，2026-10-29）

顶层脚本 33 → **10**：20 个移入 [`research/`](research/README.md#research)，3 个移入 [`archive/`](archive/README.md#archive)，全部用 `git mv`（`git log --follow` 可追溯）。

- **活跃调用改新路径**：本仓脚本、`scripts/tests/**`、活跃文档与 ADR 中的调用/导入路径已改为 `scripts/research/...` / `scripts/archive/...`。
- **历史命令证据不改写**：`experiments/` 内的既有命令串、历史规格、归档报告**保留旧路径**，按 [目录与命名规范](../docs/conventions/目录与命名规范.md#10-产物分类与生命周期) 不重写历史；查旧路径对应关系见 [research 迁移表](research/README.md#migration) 与 [archive 迁移表](archive/README.md#migration)。
- **产物字段里的 `generated_by` / `runner` 随脚本更新**（重新生成时会写新路径）；**既有** run 的产物保留旧值，属历史记录。
