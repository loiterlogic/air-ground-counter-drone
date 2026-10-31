# P1-4 · baseline closure round-3 报告（最后 A 臂补证）

<a id="p1-4-baseline-r3-report"></a>

- 任务 ID：`20261030-010-p1-4-baseline-closure`，round-3
- 执行者：Worker（workbuddy / `deepseek-v4.1-flash` / max）
- 父会话 ID：`session-fd998168-60d9-42ef-a7df-834b0457b88f`
- 起止：2026-10-30T22:46:28 → 22:52（T2 起 22:46:59，墙钟 69 s）
- 状态：**待审查（收口）**
- 派工：[round-3 request](request.md#p1-4-baseline-r3-request)（Leader 写，本轮未重写预登记）

<a id="p1-4-baseline-r3-summary"></a>
## 审查摘要（≤30 行）

1. **结论：数据缺口已补齐 → `PASS_WITH_NOTE`**。A 臂取得 `err_eff` p95 = **0.100946 m**（n=2682，`final=true`）。
2. **G1–G9 全部 PASS**：非 IDLE、`/agc/task/start` 已调用（11.409 s）、summary 完整、
   `TRACKING_SUCCESS`/`tracking_milestone`、机型 `x500_0`、lifecycle 到 `Managed nodes are active`、
   prewarm `done ok=True`、无残留。
3. **Primary 全部相等**（6/6）：含 `shield_infeasible_rate` A=0 / B=0。
4. **Secondary 全在容差内**：窗口 −8.28%、拍数 +18.78%、可见率 +0.0024。
5. **预登记判据 PASS**：`err_eff p95` A=0.100946 vs B=0.100939，相对差 **−0.01%** ≤ 20%。
6. **但该判据判别力不足（关键）**：`standoff_follower.max_step_m = 0.1`（20 Hz 步进上限）
   把 **p75–p95 整段饱和在 ≈0.1 m**，两臂 p95 几乎必然相等 —— 这是**参数上限**，不是跟踪动力学。
7. **真正能区分的是中位数与尾部**：p50 **−42.41%**、p99 **−22.62%**，**均超 20% 容差**；
   `>0.1001 m` 样本占比 A 15.88% / B 12.48%。
8. **因此不得宣称"换机后飞行跟踪行为实测不变"**。只能写：预登记 p95 判据通过，但判据饱和、需 Leader 裁定口径。
9. **纪律**：本轮**零改动**（`find src scripts docs -newermt 22:46` → 空；代码哈希与 round-2 一致）；
   只跑 A 臂，未跑 B/vision，未重写预登记。
10. **预算**：T2 **1/1 次**，69 s / 450 s，**0 重试**；T1 0 次；离线约 5 次。
11. **任务累计 T2 = 5 次**（round-1 2 + round-2 2 + round-3 1），超出原始 4 次上限 1 次，属 Leader 追加授权，如实记账。
12. **下一步（供 Leader 裁定）**：p95 饱和是预登记时的判据设计问题；若要下"等价/不等价"的结论，
    需改用 p50/p99 或"剔除饱和样本后的误差"作为判据并**更新预登记**——我不自行改口径。

<a id="p1-4-baseline-r3-result"></a>
## 1. A 臂结果（唯一一次 T2）

| 项 | 值 |
|---|---|
| demo 目录 | `experiments/demo/20261030-224700` |
| summary | `experiments/w6-task-eval/20261030-s04_static_static_obs_track-0-224717-2953/metrics/summary.json` |
| 机型 | `x500_0` / `simulation model: x500` |
| `/agc/task/start` | ok，11.409 s |
| 终态 | `TRACKING_SUCCESS` / `tracking_milestone` |
| episode ticks | 410 |
| visibility_rate | 0.982036 |
| task window | 37.092 s（sim 11.45 → 48.54） |
| C9 `shield_infeasible_rate` | 0 |
| reset | `reset_failed=false` / `reset_retries=0` / `reset_failure_rate=0` |
| rtf | 0.904115 |
| odom_valid_ratio | 0.990252 |
| collision_count | 1 |
| **`err_eff` p95** | **0.100946 m**（n=2682） |
| `err_eff` mean / p50 / max | 0.0462 / 0.003049 / 0.9496 m |
| 采集器 | `final=true`，`paired_samples=2682`，`ref_msgs=1401`，`tracking_ref_msgs=560`，`odom_msgs=2682` |
| mode 分布 | `tracking` 2676 / `base` 6 |

详见 [`evidence/comparison.md`](../../../../experiments/p1-4-baseline/round-3/evidence/comparison.md)、
[`evidence/index.json`](../../../../experiments/p1-4-baseline/round-3/evidence/index.json)。

<a id="p1-4-baseline-r3-compare"></a>
## 2. 与 round-2 B 臂同口径对比

### Primary（`exact_equal`）—— 全部相等

| 字段 | A | B | 结果 |
|---|---|---|---|
| `terminal_state` | `TRACKING_SUCCESS` | `TRACKING_SUCCESS` | PASS |
| `terminal_reason_code` | `tracking_milestone` | `tracking_milestone` | PASS |
| `reset_failed` | false | false | PASS |
| `reset_retries` | 0 | 0 | PASS |
| `shield_infeasible_rate` | 0 | 0 | PASS |
| `reset_failure_rate` | 0 | 0 | PASS |

### Secondary（容差）

| 字段 | A | B | 差 | 容差 | 结果 |
|---|---|---|---|---|---|
| `task_window_s` | 37.092 | 34.020 | −8.28% | 20% | PASS |
| `episode_window_metrics.ticks_total` | 410 | 487 | +18.78% | 20% | PASS |
| `visibility_rate` | 0.982036 | 0.984429 | +0.002393 | 0.10 | PASS |

### 跟踪误差（`err_eff`，生效参考口径）

| 统计 | A（n=2682） | B（n=2500） | 相对差 | ≤20%? |
|---|---|---|---|---|
| mean | 0.0462 | 0.0412 | −10.82% | 是 |
| **p50** | 0.003049 | 0.001756 | **−42.41%** | **否** |
| p75 | 0.100000 | 0.099769 | −0.23% | 是 |
| p90 | 0.100405 | 0.100293 | −0.11% | 是 |
| **p95（预登记判据）** | **0.100946** | **0.100939** | **−0.01%** | **是** |
| **p99** | 0.187706 | 0.145241 | **−22.62%** | **否** |
| max | 0.9496 | 0.8089 | −14.82% | 是 |

<a id="p1-4-baseline-r3-caveat"></a>
## 3. 判据判别力不足（本轮最重要的发现）

`air.yaml` 的 `standoff_follower.max_step_m = 0.1`，`standoff_follower.cpp:173` 对每拍参考位移限幅
（20 Hz → 最大 0.1 m/拍）。因此 `tracking_ref` 与机体之间一旦出现"追不上"的状态，
误差就会**稳定停在 ≈0.1 m**，而不是继续增长。

实测印证：两臂 **p75 = 0.100000 / 0.099769**、**p90 = 0.100405 / 0.100293** ——
整段被钉在 0.1 m 附近。**在这种分布下，p95 必然 ≈0.1 m，两臂必然"相等"**，与机型无关。

真正携带机型信息的量：

- **p50**：0.003049 vs 0.001756（−42.41%）—— 稳态精度差一个量级方向；
- **p99**：0.187706 vs 0.145241（−22.62%）—— 尾部偏差不同；
- `>0.1001 m` 占比：15.88% vs 12.48%。

**结论**：预登记 p95 判据 **PASS**，但它**不能**支撑"跟踪行为实测不变"。本轮**不**据此宣称等价。

<a id="p1-4-baseline-r3-budget"></a>
## 4. 预算与纪律

| 项 | 用量 / 授权 |
|---|---|
| T2（本轮） | **1 / 1 次**；**69 s / 450 s** |
| 重试 | **0** |
| T1 | **0 次** |
| 离线 | 约 5 次（预登记指针、summary 解析、分位数复核、索引交叉校验、残留检查），均 ≤30 s |
| 任务累计 T2 | **5 次**（2+2+1）—— 超原始上限 4 次 **1 次**，属 Leader 追加授权 |
| 代码/配置改动 | **零**（`find src scripts docs -newermt 22:46` → 空；`w6.launch.py`/`track_err_probe.py` 哈希与 round-2 一致） |
| 预登记 | Leader 派工单即预登记，sha256 `918f6210…670a`，mtime 22:44:17 **早于** T2；本轮**未重写** |
| 未跑 | B 臂、vision、V4/V5/V6 |
| 残留 | 无（run_demo 回收 33→0；事后 `ps` 空） |

<a id="p1-4-baseline-r3-next"></a>
## 5. 需 Leader 裁定

1. **是否接受"p95 判据 PASS 但判别力不足"作为出口第 4 项的收口状态**；
2. 若要下"等价 / 不等价"的明确结论，需**更新预登记**改用：
   - p50 + p99 双判据，或
   - "剔除 `err ≥ 0.099` 饱和样本后的误差"，或
   - 直接比较机体速度跟踪（C1 口径的 `body_speed_p95` / `height_err_p95`，`air.yaml` 已有 `c1` 阈值）
   
   以上任一都**改变判据**，按纪律须由 Leader 裁定并重登记，**我不自行改**。
3. 不建议再追加 T2：两臂数据已齐，缺的是判据而非数据。

## 6. 状态

- **待审查（收口）**；未 commit（派工单未授权提交）；不开始其他任务。
