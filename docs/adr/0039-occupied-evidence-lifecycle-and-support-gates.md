<a id="top"></a>
# 占据证据的生命周期、空间支持与遮挡置信度

## Status

accepted（2026-11-10，用户裁定「完全按这里做优化」并指定 `temp.md` 的审查结论为实施依据）

**修订**：[ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top) 的
(b)（log-odds 累积口径）、(j) 的时间同步手段（新增错位**补偿**，不只是配对容差）、
(k)（时间衰减的**下限**语义）、(m)(n)（carve 的遮挡判据）、(o)（证据单位之上再加空间支持门槛）。
ADR-0035 的正文与历史行**逐字保留**，演进记录见其 Consequences。

**相关**：[ADR-0007](0007-scene-geometry-single-source-and-layout.md#top)（几何单一真源）、
[ADR-0036](0036-dense-obstacle-map-and-per-map-spawn.md#top) / [ADR-0037](0037-dense-map-random-layout-and-plain-ground.md#top)
（`dense_map` 小障碍高密度图）、[ADR-0030](0030-nadir-camera-capability.md#top)（相机能力）、
[契约真源](0020-package-boundaries-and-runtime-topology.md#hard-constraints)。

## 背景

`dense_map`（小障碍高密度图）实测六项指标：

| 指标 | 实测 | 判据 |
|---|---:|---|
| 面积覆盖率 | 0.882 | ≥ 0.55 |
| 误覆盖率 | 0.727 | ≤ 0.35 |
| IoU | 0.264 | ≥ 0.45 |
| 面积比 | 1.801 | ≤ 1.60 |
| 稳定性 p99 | 377 | ≤ 50 |
| 形状抖动 p95 | 0 | ≤ 0.25 |

覆盖率已高，说明**不能靠更激进地过滤点**解决（会同时牺牲覆盖率）；而误覆盖、面积比、
稳定性三项同时失效，指向**错误 occupied 太多、且清不掉**。逐条读代码定位到四个结构性问题，
它们不是参数问题：

1. **occupied 没有退出机制**。`markStale` 对 `logodds >= occupied_threshold` 的格直接
   `continue`，理由是"建筑物不会因为 3 秒没被看到就消失"。该理由对**真实**障碍成立，
   但它把"误 hit 建起来的 occupied"一起保护了；而误 hit 恰恰最容易落在**画幅外 / 遮挡区 /
   射线没穿过的位置** —— carving 够不到、时间不削弱，于是永久驻留。
2. **标签↔深度时间错位对小障碍过大**。容差 0.15 s，UAV 2 m/s ⇒ 最坏 0.30 m 的**系统性**
   错位；而 `dense_map` 的障碍只有 0.6–1.2 m 宽、栅格 0.5 m。错位每帧同向、可算，
   不该当成随机噪声靠过滤吸收。
3. **hit 判据对密集小目标过于"点状"**。一个格只要有一个投影点落进就算一次 hit，跨两帧
   即成 occupied；而大建筑同格内有成百上千点。两者证据强度完全不同，却走同一条判据。
4. **carving 不感知置信度**。任何历史 occupied 都算"墙"并终止射线；`dense_map` 里"每箱
   最近障碍点"会因投影误差逐帧变化 ⇒ 这一帧的墙挡住射线、下一帧换一堵墙，各自把对方
   后面的区域标 free，occupied 集合大幅互换。

另外，`publish_deadband` 曾被当成稳定性手段，而它只量化 1–99 的中间概率
（`perception_quality.py` 把 1–99 一律算 unknown），对跨门限翻转无效 —— 稳定性需要
**状态级**防抖，不是消息级。

## 决策

### (a) occupied 有生命周期：长期没有正向 hit ⇒ 退出到 **unknown**

`LogOddsParams::occupied_expire_frames`（`occupied_expire_s`，按实测帧率换算）：
某格进入 occupied 后，若连续超过该时长**没有被任何正向 hit**，则按 `p_decay` 逐步削弱，
降到 `occupied_exit_threshold` 以下即退出 occupied。

- 用 `last_hit_frame_`（**只记正向 hit**），不是 `last_seen_frame_`（含射线穿过）：
  射线穿过只证明"这格是空的"，不能刷新"我还看到这里有障碍"的生命周期。
- **降 unknown，不降 free**。我们只是"很久没再看到它"，并没有"看到它是空的"；
  降 free 是对规划器的过度承诺。**只有真实射线穿过**才允许到 free。
- 分多拍走（每拍一次 `p_decay`），不一次清零 —— "刚过期"与"过期很久"仍可区分，
  且不会让 occupied 集合出现整批同时消失的台阶。

### (b) 时间衰减的下限 = `unknown_floor_p`，高于 `free_threshold`

`decayMiss` / `markStale` / 弱 carve 的削弱下限从 `p_min`(0.12，**低于** free 门限 0.20)
改为 `unknown_floor_p`(0.22，**高于**它)。

理由：时间流逝的语义是"这格本帧没被看到"，几乎不携带信息（可能只是被画幅边缘切掉、
被遮挡、或相机飞走了）。让它把格子推到 free，等于把"没看见"当成"确认是空的" ——
与 [ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top) (g) 的三态纪律
直接冲突，实测后果是真实障碍被自己的时间衰减擦成 free（覆盖率因此有与算法无关的损耗）。

**这反转了 ADR-0035 时期的一条判据**：旧 `LogOdds.DecayReachesFreeFromUnknown` 断言
"长期不看的格必须衰减到 free"，目的是修"卡在 p=0.50 冻结"的 bug。那个 bug 是真的，
但修成"衰减到 free"引入了更严重的语义错误。新判据 `DecayStopsAtUnknownNotFree`。

### (c) 小障碍需要**空间支持**：单格点数 + z 展布

`min_hit_points_per_cell`（缺省 3）：一个格本帧至少有这么多独立足迹点才进 hit 证据。
`max_hit_z_spread_m`（缺省 1.5）：单格内足迹点 z 极差超限即判"混了两种表面"
（屋顶 + 侧墙、障碍 + 地面），整格不进 hit 证据。

- **为什么点数**：它是唯一与像素采样密度无关、又能反映"这块地面真的被多个像素看到"的量。
  小障碍 0.6×0.6 m 在 GSD 5.3 cm/px 下约 128 px，远超 3；孤立错位点通常只有 1–2 个。
  这个门槛**不改变"大建筑容易确认"的既有行为**。
- **为什么用 z 而不是 XY 散布**：0.5 m 格内的 XY 散布天然被格宽限住（≤0.71 m），
  判不出任何东西；z 才反映"这些点是不是同一个平面"。
- 实现上由 `LogOddsGrid` 持有帧内累加状态（`addFramePoint` / `framePoints` /
  `frameZSpread`），用**帧号惰性重置**，不必每帧清零整张缓冲。
- **不调大 `min_obstacle_side_m`**：它确实能降噪，但会直接损失 `dense_map` 的小障碍
  覆盖率 —— 而覆盖率已 0.882，这个杠杆代价很大。

### (d) 进入 occupied 需要**跨帧确认**

`min_hits_for_occupied`（缺省 2）：除概率过门限外，还必须累计够跨帧 hit 次数。

写成**独立的门**而不是只靠概率门限，是因为概率门限与 `p_hit` 耦合 —— 有人为了"更容易
建图"调高 `p_hit` 或调低 `occupied_threshold`，就会**静默**变成"单帧即画"，而那种改动
在代码里看不出来。

### (e) carving 感知置信度：遮挡体必须够可信

`occluder_min_confidence`（缺省 = `occupied_threshold`）：只有置信度 ≥ 此值的格才是
遮挡体并终止射线。低于它的格（候选 / 刚过期）射线**可以穿过**，但只施加**弱**负证据
（`p_decay`，且不降到 free 以下）—— 那里很可能就是这个方向的小障碍，我们没有足够证据
说它是空的。

### (f) 标签↔深度错位：**补偿**，不只是配对容差

`depth_pair_tolerance_s` 只回答"允许配对"，不回答"错位是否无害"。现在按
**深度时刻与标签时刻的机体位移**把点平移补偿（同一台相机、≤0.15 s，两帧只差一个平移；
姿态已按标签时刻 slerp 插值）。

深度时刻查不到 odom 时**不补偿**并计数 —— 不拿猜的位置去平移，那会把一个已知的小错位
换成未知的大错位。补偿量与被跳过次数进 `帧统计` 日志（「补偿位移」字段）。

### (g) P0 诊断：误覆盖按**距真值格距**分档

`perception_quality.py` 新增（**不参与判定**）：`0–1 格` / `1–3 格` / `>3 格` 三档 +
FP 到真值距离的 p50/p90。三档对应三种**不同**根因：

- `0–1 格`：栅格量化 / 边界误差（改判据或加膨胀就能消，不是地图画错）；
- `1–3 格`：投影误差 / 时间错位 / 形态外扩；
- `>3 格`：明显错误投影 / 残影 / 错误 carving。

混在一起只会得出"误覆盖高"这一个无用结论。

### (h) 确认门挂**地图帧**时钟，不挂感知帧

感知回调 10 Hz、`/agc/map` 2 Hz，迟滞状态只在发布拍推进。若确认门槛按感知帧计数，
"K=2 帧确认"在对外地图上实际只要 0.2 s —— 语义比设计意图弱 5 倍，且随感知帧率漂移。

新增 `map_frame_hits_`（`beginMapFrame` / `mapFrameHitsAt`），只在 `rebuild()`
（发布拍）推进一次，与 `occupied_now_` 同一个时钟。`hit_count_`（感知帧）保留 ——
两者是不同口径：前者是"确认门槛"，后者是"证据单位"。

### (i) 错位不确定度：**帧内相关**，只能靠跨帧抵消

投影端按位移补偿掉主体错位后，`map_adapter` 处理**残余**：用相邻 odom 样本估速度，
`不确定度 = 速度 × 时间残差`（`bodySpeedBetween` / `timeMisalignmentRadius`）。
两者与补偿位移**同源**，不出现"速度取自 twist、位移取自位置"的口径分裂。

**关键性质**：错位在一个帧内是**同向、相关**的误差 —— 整帧点一起平移，
所以**帧内点数再多也抵不掉它**（点都在一起偏）。因此不折成逐点权重
（那要改消息契约，而 `ObstacleFootprintArray.confidence` 是批次级标量、被 golden
文件钉死），而是：**不确定度 ≥ 半格时本帧不给正证据**，把确认让给后续地图帧。
阈值取 `res/2`，**不设参数** —— 它是"点可能整体偏出本格"的几何分界，不是可调旋钮。

### (j) 深度一致性：IQR 主判 + 多数点兜底（**不用 MAD 当主判据**）

极差只能抓"混了两种表面"，抓不到"整片偏移但局部连续"，且对单个离群点过于敏感。

**实测踩到的坑（必须记下来，否则下一轮会再踩）**：最初用 MAD 当主判据，在**双峰**
数据（同格一半屋顶 z=1、一半地面 z=6）上**自我失效** —— 中位数落在两簇中间、
各点到它的距离相同，于是 MAD 等于两簇间距的一半，任何 `tol ∝ MAD` 的判据都被
自身撑大到恒真。最终判据：

1. **IQR 主判**：`q3 − q1 ≤ 2·floor` ⇒ 一致（双峰时 IQR 必然大、对少数离群点稳健）；
2. IQR 大时，数**落在 floor 内的点数是否过半** —— 多数点正常、少数离群 ⇒ 放行。

**另一个实测 bug**：`addFramePoint` 首次碰到某格时 `return` 掉了，导致**每格恒定少
一个样本**，双峰用例因此漏判。这类"每格少一个"的错误在生产里会静默削弱判据。

`depth_sample_cap`（16）给单格样本缓冲上界，满员后按 2 的幂降采样 —— 目的只是拿
稳健位置估计，不需要全部样本。

## 不做什么

- **不**把"没看到"当 free（弱衰减一律停在 unknown）；
- **不**改预登记判据阈值（`GATES`），不新增路线分支开关（`xxx_mode` / `xxx_backend`）；
- **不**调大 `min_obstacle_side_m` 来换误覆盖（会直接损失小障碍覆盖率）；
- **不**把 `publish_deadband` 当稳定性手段（口径边界见 ADR-0035 (o)）；
- **不**做物体级跟踪语义升级，不引入 Nav2 私有参数。

## Considered Options

- **只调 `p_hit` / 门限 / stale 时间** —— 被否：误 hit 与真 hit 走同一条判据，
  任何单向调参都只是"用覆盖率换误覆盖"或反之。四个根因都是结构性的。
- **occupied 过期时直接降 free** —— 被否：那是把"很久没看到"当成"确认是空的"，
  与三态纪律冲突，且会让规划器过度承诺。
- **靠 `publish_deadband` 压稳定性 p99** —— 被否：它只量化 1–99，而指标把 1–99 算 unknown，
  对跨门限翻转无效。
- **对每个 footprint 点加空间不确定度并按不确定度加权** —— 部分采纳（时间错位用平移补偿），
  其余不做：`dense_map` 的误覆盖主要由"证据生命周期"与"遮挡置信度"主导，
  逐点加权会先增加一个需要标定的量，再掩盖真正的问题。

## Consequences

- **可回滚**：新增参数都有"关闭"值（`occupied_expire_s: 0`、`min_hit_points_per_cell: 1`、
  `max_hit_z_spread_m: 0`、`min_hits_for_occupied: 1`、`depth_mad_k: 0` 配合
  `depth_consistency_floor_m` 放大），置为关闭值即退回 ADR-0035 口径。
  `unknown_floor_p` 无关闭值 —— 它修的是语义错误（把"没看见"当"确认是空的"），不是开关。
- **代价**：occupied 退出需要多拍衰减，收敛比"立即清"慢；`unknown_floor_p` 让"很久没复查的
  空"停留 unknown 而不是 free，`free` 面积会变小（规划器仍可走，只是不享受"已确认安全"）。
- **防复活闸门**：`test_log_odds_grid.cpp` 的 `OccupiedExpiresWhenNeverHitAgain` /
  `OccupiedSurvivesWhenContinuouslyHit` / `DecayStopsAtUnknownNotFree` /
  `SparseSinglePointIsRejected` / `MixedSurfacesInOneCellAreRejected` /
  `OccupiedRequiresCrossFrameConfirmation` / `WeakCellIsNotAnOccluder` /
  `ConfirmedCellStopsTheRay` / `ConfirmationCountsMapFramesNotSensorFrames`（(h)）/
  `DepthConsistencyToleratesFewOutliers` / `DepthConsistencyRejectsTwoSurfaces` /
  `DepthConsistencyFallsBackOnSmallSamples` / `DepthSampleBufferIsBounded`（(j)）；
  脚本侧 `test_perception_map_consistency.py` 的
  `test_evidence_unit_is_one_per_cell_per_frame`（判据升级为"每格每帧只判一次 + 必须走
  带空间支持的记账入口"）与 `test_confirmation_gate_counts_map_frames_not_sensor_frames`（(h)）。
- **待实测登记**：本节的结构性修复效果以 `perception_quality.py --map dense_map` 的实跑
  数字为准，**不得**据设计推导宣称达标。

### 实测结果（2026-11-10，`dense_map` + `dense_scene`）

**两轮：第一轮只做 (a)–(g)，第二轮补上 (h)–(j)（用户裁定「b」= 三条缺口全补）。**

| 指标 | 改造前 | 第一轮 | 第二轮（全补） | 判据 | 判定 |
|---|---:|---:|---:|---|---|
| 面积覆盖率 | 0.882 | 0.921 | **0.951** | ≥ 0.55 | ✅ |
| 误覆盖率 | 0.727 | 0.679 | **0.668** | ≤ 0.35 | ❌ |
| IoU | 0.264 | 0.313 | **0.326** | ≥ 0.45 | ❌ |
| 面积比 | 1.801 | 1.237 | **1.230** | ≤ 1.60 | ✅（**由不通过转为通过**）|
| 稳定性 p99 | 377 | **79** | **104** | ≤ 50 | ❌（改善 72%，未达标）|
| 形状抖动 p95 | 0 | 0.000 | 0.000 | ≤ 0.25 | ✅ |

**结论：仍未达标，如实登记为「待整改」。** 五项改善（面积比转通过），三项未通过；
稳定性在第二轮**从 79 回升到 104**，见下面的归因。

#### (h) 确认门挂**地图帧**时钟，不挂感知帧

感知回调 10 Hz、`/agc/map` 2 Hz。改造前 `min_hits_for_occupied` 读的是 `hit_count_`
（感知帧），于是"K=2 帧确认"在对外地图上实际只要 0.2 s —— 语义比设计意图**弱 5 倍**，
且随感知帧率漂移（实测 6–10 Hz）。现在新增 `map_frame_hits_`，只在 `rebuild()`
（发布拍）由 `beginMapFrame()` 推进一次，与 `occupied_now_` **同一个时钟**。

`hit_count_` 保留不动：它仍是"证据单位"的计数（感知帧），两者是不同口径，都要在。

#### (i) 错位不确定度：**帧内相关**，只能靠跨帧抵消

投影端已按位移补偿掉主体错位，`map_adapter` 处理**残余**：用相邻 odom 样本估速度，
`不确定度 = 速度 × 时间残差`（`bodySpeedBetween` / `timeMisalignmentRadius`，
两者与补偿位移**同源**，不出现"速度取自 twist、位移取自位置"的口径分裂）。

**关键性质（决定了它该用在哪）**：错位在一个帧内是**同向、相关**的误差 ——
整帧点一起平移，所以**帧内点数再多也抵不掉它**。因此没有把它折成逐点权重
（那要改消息契约，而 `ObstacleFootprintArray.confidence` 是批次级标量、且被 golden
文件钉死），而是：**不确定度 ≥ 半格时本帧不给正证据**，把确认让给后续地图帧。

#### (j) 深度一致性：IQR 主判 + 多数点兜底（**不用 MAD 当主判据**）

极差只能抓"混了两种表面"，抓不到"整片偏移但局部连续"，且对单个离群点过于敏感。

**实测踩到的坑（必须记下来）**：最初用 MAD 当主判据，在**双峰**数据（同格一半屋顶
z=1、一半地面 z=6）上**自我失效** —— 中位数落在两簇中间、各点到它的距离相同，
于是 MAD 等于两簇间距的一半，任何 `tol ∝ MAD` 的判据都被自身撑大到恒真。
最终判据：**IQR 主判**（双峰时必然大、对少数离群点稳健），IQR 大时再数
"落在 floor 内的点数是否过半"（多数点正常、少数离群 ⇒ 放行）。

**另一个实测 bug**：`addFramePoint` 首次碰到某格时 `return` 掉了，导致**每格恒定
少一个样本**，双峰用例因此漏判。这类"每格少一个"的错误在生产里会静默削弱判据，
`DepthSampleBufferIsBounded` 与双峰用例是它的闸门。

#### 未达标的根因（**新诊断给出的证据，不是推测**）

**(p) 误覆盖率 0.668 的空间分解（`perception_quality.py` 新增分档）**：

```text
FP 分档（距真值格距）：0–1 格 66.1%  1–3 格 33.2%  >3 格 0.7%
FP 到真值距离 p50 = 1.0 格（0.5 m）  p90 ≈ 2.0 格（1.0 m）
```

**99.3% 的误覆盖紧贴真值 1 格以内** —— 这**不是**"明显错误投影 / 残影"
（那会落在 `>3 格`，实测仅 0.7%）。`(a)–(j)` 修的是**"凭空多出来的障碍"**，
剩下的是**"真实障碍的边缘被量化/外扩"**。同一批数据、只把真值口径从
"格中心在形状内"换成"格与形状任意接触"（与地图侧"点落在格内"同语义）：

| 真值口径 | 误覆盖率 | IoU | 覆盖率 |
|---|---:|---:|---:|
| 中心内（现判据） | 0.668 | 0.326 | 0.951 |
| 任意接触（地图侧语义） | **约 0.31** | **约 0.68** | 0.951 |

**⇒ 当前误覆盖率中约一半是口径差异，不是地图画错。** 与
[ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top) (p) 实验 B
方向一致（yard 上当时测得约 60%），`dense_map` 的小障碍更多，口径差异更显著。
**但换口径等于改判据**，按预登记纪律**不得由实现方自行决定** —— 待用户裁定，本轮不改 `GATES`。

**(q) 稳定性 p99 的残余是"净增长台阶"，不是互换**：

```text
|Δocc| p50=15 p90=48 p99=104 max=159
离开 p99=71  进入 p99=109  集合 IoU p50=0.985  互换率 p50=0.008
```

最大 |Δocc| 的帧对**几乎全是净增长**（如 frame 59→60：exit=3 / enter=162）。
逐格追踪证明是**振荡**（1572 个格翻转 ≥2 次，231 个格 ≥6 次，单格最多 13 次），
且进入格中**约 85% 是误覆盖**（frame 59→60 的 162 个进入格里 139 个不在真值上）。

**第二轮为什么稳定性从 79 回升到 104**（如实归因，不掩饰）：`(i)` 让"残余不确定度
≥ 半格"的帧不给正证据，于是确认被推到后续帧 —— 单帧的增量更集中、更大，净增长台阶
因此变高。这是**用稳定性换诚实性**（不再让可疑帧直接落证据），但代价是该项指标变差。
`(j)` 的深度一致性同样会**延迟**确认（先拒后收）。

相关性排查（**结论是"不是这些"**，写下来避免下一轮重复试）：

- 与足迹面积变化的相关系数仅 **0.111**；面积变化 0–2% 时 |Δocc| p99 仍是 102
  ⇒ **不是"画幅/足迹突变"**；
- 与 `rays_hit` 的相关系数为 **−0.222** ⇒ 不是"射线数突增"；
- `画幅异常帧` 累计 38（全程 1300+ 证据帧，约 3%）⇒ 不是"画幅几何失控"；
- `弱支持格` 每帧仅约 85 个（相对 2000+ 候选格）⇒ **支持门槛不是主导机制**。

**最可能的残余根因（待下一轮验证，不在本轮下结论）**：`min_hit_points_per_cell=3`
是**全局常数**，而小障碍（0.5 m 直径 → 约 90 px → 约 4 格）在 GSD 边缘只落在 1–2 格，
每格点数随分割边缘抖动在 2↔4 之间 ⇒ **恰好卡在门槛两侧**，整片小障碍整批进出。

**下一轮候选手段**（**未实施，不得据本文宣称已修**）：把支持门槛改成
"点数按格面积/距离归一"而不是绝对计数；或对已确认过的格改用**更低的再入门槛**
（迟滞式的支持门槛），让"回来"比"首次确认"容易。两者都需要新的实跑取证。

### 三条缺口与 temp.md 的对应（自查表）

| temp.md 要求 | 落地 |
|---|---|
| 二、occupied 有条件过期 → unknown | (a) |
| 二、occupied→free 只能由射线确认 | (a) + (b) |
| 三、让标签和深度同一时间基准 | 投影端位移补偿 + (i) |
| 三、按运动速度给点加空间误差半径 | (i)（`timeMisalignmentRadius` 实际生效）|
| 三、不要单点当确定 hit | (c) + (i) |
| 三、每格统计点数/深度中位数/MAD/XY 散布/重复命中 | (c) + (j)：点数、z 展布、中位数/IQR、重复命中；**XY 散布未做**（0.5 m 格内被格宽限住，判不出东西 —— 已在 (c) 登记理由）|
| 四、空间支持门槛 | (c) |
| 四、时间支持门槛（K 帧确认）| (d) + (h) |
| 四、位置漂移超不确定度→拆分/降置信 | (i)（按帧让位，不做逐格拆分）|
| 五、carving 两阶段 A/B | (e) 的置信度分级 + 既有阴影区；**未拆成显式两阶段** |
| 五、遮挡区维护 unknown | 既有（阴影区），(e) 强化 |
| 六、状态级防抖 K/L | (a) + (d) + (h) |
| 六、K/L 按地图帧率定义 | **(h)** |
| 七 P0 诊断分档 | (g) |
| 七 P0 每格首次/最近 hit、连续命中、miss 时间、是否进过视野、点数与散布 | `last_hit_frame_` / `hit_count_` / `map_frame_hits_` / `framePoints` / `frameZSpread` 已具备；**未做成对外诊断话题**（无消费者，按 ADR-0035 的"不留僵尸话题"纪律不做）|
| 七 P1–P4 | (a)–(e) |

## 参考

- [ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top)（被本篇修订的感知地图口径）
- [ADR-0003](0003-nav2-paradigm-absorption.md#top)（与 Nav2 解绑的边界）
- `src/agc_perception/include/agc_perception/log_odds_grid.hpp`（证据累积与生命周期）
- `src/agc_perception/src/map_adapter.cpp`（空间支持门槛与 carve）
- `src/agc_perception/src/nadir_projection.cpp`（时间错位补偿）
- `scripts/tests/perception_quality.py`（六项指标 + FP 分档诊断）

## 演进记录

**2026-11-10 补充 by [ADR-0040](0040-perception-multi-resolution-evidence-and-planning-layers.md#top)（非取代）**：
本篇的全部决策（证据生命周期、空间支持门槛、遮挡置信度、证据单位"每格每帧一次"）
**逐条保留且仍生效**。ADR-0040 只改一件事：这些机制所作用的**栅格分辨率**从 0.5 m
改为 0.25 m 的证据层，而 0.5 m 降为**由证据层派生的规划层**。

因此本篇正文里"栅格 / 格"的措辞此后读作**证据格**；`map_adapter` 的
`occupied_expire_s` / `min_hit_points_per_cell` / `max_hit_z_spread_m` /
`depth_consistency_floor_m` / `min_hits_for_occupied` / `occluder_min_confidence`
等参数语义不变，但作用对象变细一倍（0.25 m 下 `min_hit_points_per_cell=3` 覆盖的
物理面积是原来的 1/4 —— 这是**已知的语义漂移**，本轮未重新标定，不得据此宣称
"小障碍支持门槛已按新分辨率重新标定"）。

本篇记录的 `shape_jitter = 0`"已失去区分能力"的判断，在 ADR-0040 里得到了解释：
该指标统计 OBB 形状，而地图早已由 footprint 逐点累积产生，**形状稳定不等于足迹稳定**。
