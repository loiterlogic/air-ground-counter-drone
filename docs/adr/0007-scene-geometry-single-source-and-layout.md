<a id="top"></a>
# 场景几何单一真源、布局范式与物理驱动

## Status

accepted（2026-11-02 由 ADR-0010 / 0055 / 0062 / 0106 / 0112 合并；结论未变）；
**部分 superseded by [ADR-0035](0035-perception-map-representation-and-unknown-policy.md#top)（2026-11-09）**

> **被取代的部分**：本篇 (e) 末句「数据契约不变：`0=free / 100=occupied / -1=unknown`」——
> `/agc/map` 自 2026-11-09 起输出**量化概率**（`-1=unknown / 0=free / 1–99=概率×100 / 100=occupied`）。
> **仍有效的部分**：内容身份 hash、单调更新序号、逐字节等价比较、静态先验永不被空观测清除、
> 动态轨按 `dynamic_max_age_s` 过期，(f) 的作业区与布局范式。

## 背景

同一几何事实曾存在**五份独立副本**：物理世界（`agc_world.sdf` 的 `pole_1/pole_2` pose / size）、
空中安全列表（`air.yaml` 的 `safety.obstacle_names/x/y`）、感知障碍先验（`obstacles.yaml`）、感知地图
栅格（`map.yaml`）、`scenario_reset` 出生校验（`base.yaml` + `scenario_reset.cpp` 默认值）。无单一
真源、无版本哈希 ⇒ 移动一根立柱可能只改某一域，造成「地图安全但物理碰撞」。

地面车早期用 `kinematic_sim`（对 `cmd_vel` 做运动学积分再 `set_model_state` 写位姿），无质量 / 惯性 /
轮速约束，动力学不可信；而硬约束的「真实逃逸能力」要求安全层有真实对标对象。

作业区放大到 100×100 后，首版 `yard` 的「手工堆出来的多样性」（13 种离散 yaw）不像现实场站；且
规格写了「障碍占作业区 5%–12%」却**没有任何检查在算它**。最后，飞行高度散在 `air.yaml` 三个互不相干
的键里（`takeoff_altitude_m` / `traj.height` / `standoff_follower.height`，碰巧都是 2.5），改一个不带
动另两个，在 `yard` 上出现「两机比 10.55 m 的楼低 8 m」。

## 决策

### (a) 地面车用真实物理驱动（GZ DiffDrive）
`agc_car` 重设为差速两驱动轮 + 2 caster，挂 `gz::sim::systems::DiffDrive`；`wheel_separation` /
`wheel_radius` / `max_wheel_torque` / `max_wheel_accel` 落 `agc_sim/config`，由 launch 单一设置。
`/agc/ground/cmd_vel`（`TwistStamped`，车体系）经 `agc_ground` 的中继节点转 GZ
`/model/agc_car/cmd_vel`（`gz.msgs.Twist`，无戳、模型系）。odom 取 DiffDrive 插件输出（带轮速），
同时保留世界位姿**真值旁路**供感知与评估对照。唯一执行口语义由「唯一写车体位姿者」重述为
「**唯一命令车体运动者**」，唯一例外是场景复位的位姿写入（受运行期门控）。旧门禁判据
`drive_backend == kinematic_sim` 作废；新旧对照中车体轨迹数值差异按新基线放宽。

### (b) 几何单一真源：`world_geometry.yaml`
静态障碍实体 `id/x/y/z/yaw/size`（+ `color`，仅视觉保真、**非几何**）与作业区
`resolution/size_x/size_y/origin_x/origin_y` 落在 `agc_sim/config/world_geometry.yaml`；三张图
（`minimal` = 该文件、`maps/yard.yaml`、`maps/open_field.yaml`）同 schema。几何值逐值与历史一致
（`pole_1` @ (0,-6,1.5)、`pole_2` @ (6,6,1.5)，`0.3×0.3×3`）。

### (c) 按域派生（派生链集中，不内联重复）
- **物理世界**：`agc_world.sdf` 移除硬编码 `pole` 块、降为 base world；`world_bringup.launch.py`
  改 `_inject_static_obstacles(src, dst, geometry)`——`world_obstacles: static` 注入 pole 生成临时世界、
  `none` 直接用 base world。生成世界几何 == 真源逐值一致。
- **composition 集中派生**：`composition.py` 读真源（`load_geometry`）并派生—— 感知障碍先验
  （`write_derived_obstacles`）、感知地图几何（`write_derived_map`）、`scenario_reset` 障碍 / 边界
  （`compose_params` 注入）、空中安全列表（`apply_air_geometry` 注入
  `trajectory_tracker.safety.obstacle_names/x/y`）。`air.yaml` / `base.yaml` / `scenario_reset.cpp`
  默认值中的障碍坐标与边界改派生入口 + 标注，**不**保留第二份硬编码几何；`obstacle_safety_radius` /
  margin 等**安全余量**仍留 `air.yaml`（属安全参数，非几何）。
- **standalone 回退副本**：`obstacles.yaml` / `obstacles_none.yaml` / `map.yaml` 保留给不经
  composition 的 `perception_bringup` / `air_bringup`，文件头注明「几何真源 = `world_geometry.yaml`，
  本文件须与其一致」；一致性由 `tests/check_scene_geometry.py` 保（长期可统一改为派生）。
- **权限成文**：真源是**物理 / 真值**事实，**不等于**「所有算法都可读真值」；感知静态先验仍受
  [ADR-0009](0009-perception-truth-derived-and-vision-path.md#top) 约束（不受空观测清除）。

### (d) 几何版本身份
`geometry_sha256`（真源文件**字节** sha256）+ 真源路径记入 `scene_manifest` 的 `geometry` 块
（`source` / `sha256` / `work_area` / 障碍 `id/pose/size`）；`assertions` 增「派生几何 == 真源」
断言，不符即**拒绝运行**。

### (e) 地图内容身份与单调更新序号
- `/agc/map/version_hash`（`std_msgs/String`，latched）话题名保持，内容改为**内容身份 hash**：
  `FNV-1a(frame_id, obstacles_source, scenario_version, resolution, width, height, origin_x, origin_y,
  data)`，组装顺序须与核查脚本逐字节一致（字符串 + NUL，`double`/`uint64` 用 8 字节本机
  IEEE-754 binary64 / little-endian 内存字节，**不**用文本格式化）。`scenario_version`（string，默认
  `""`）与 `obstacles_source` 由 launch 单一注入。
- 新增 `update_seq_`（`uint64_t`）与 latched 诊断话题 `/agc/map/update_seq`（`std_msgs/UInt64`，参数
  `update_seq_topic`）：仅在**实质重建**（栅格内容或身份改变）时 +1；与内容 hash 分别可查询。
- 等价判定改为**真实 raster 逐字节比较**：`rebuild` 对候选有效障碍集合（含 static 覆盖 / 动态新鲜 /
  unknown 覆盖逻辑）实际栅格化出候选 `data`，与当前 `grid_.data` 逐字节比较—— 相同即内容等价
  （不重建、不发布、序号不变），不同才采用。**废弃**分辨率分箱 + 固定 yaw `0.1` 容差。
- 数据契约不变：`0=free / 100=occupied / -1=unknown`；`/agc/map/valid = geometry_ok_ &&
  knowledge_current`；静态先验永不被空观测清除；动态轨按 `dynamic_max_age_s` 过期覆盖为 unknown。

### (f) 作业区 100×100 与场站式布局范式
作业区 80×80 → **100×100** m（origin −50,−50），三张图统一，栅格 200×200 @0.5 m；`minimal` 的障碍
几何逐值不变（只放大作业区，保核查基线）。`scenario_reset.cpp` 的 standalone 回退默认边界由 ±40 改
±50（该默认值**不是**几何真源）。**8 字轨迹不改**：`rx=15 / ry=9 / h=2.5 / v=2.0` 属飞行包线，放大
的是作业区。`yard` 按现实场站范式整体重做：**功能分区 + 网格对齐 + 道路留白 + 尺寸长尾 + 中央空场
保留**（中央装卸 / 操纵场坪留给 8 字飞行区），周界为 30–34 m **分段长墙**（段间即门洞）。
覆盖口径成文为**并集**（并集投影面积 / 作业区面积，目标 5%–12%），旧 `7.36%` 作废；实体数上限由
≤20 放宽到 ≤32（视觉保真轮再放宽到 40）。视觉保真轮后规模为 36 实体 / 186 图元 / 19 小型件，并集
覆盖 10.89%（仍在 5%–12%）。

### (g) 材质与视觉保真（`finish`）
几何真源新增**可选**字段 `finish` ∈ {`concrete`,`steel`,`paint`,`glass`,`rust`,`asphalt`,`rubber`}
（逐 part 可覆盖实体级；非法值**拒绝运行**；缺省不写 = 旧行为，保证 `minimal` / `open_field` 与历史
证据逐字节不漂移）。`world_bringup._material_sdf` 由 `finish` 生成 `<ambient>/<diffuse>/<specular>` +
`<pbr><metal>`（`sdformat 1.11` 的 `metalness` / `roughness` 是**标量**，不需要贴图）。**材质只进物理
世界 `<material>`**，不进感知先验 / 占位栅格。地面分层（基层混凝土 + 沥青环路 + 支路 + 中央作业坪，
抬升 2–6 mm 避免 z-fighting）写在 `agc_world.sdf`、**不是**障碍、不进几何真源。

### (h) 飞行高度随地图派生
高度是**地图属性**，写在几何真源顶层（三张图同键），**不新建**独立高度文件：

```yaml
flight_altitude:
  own_track_m: 14.0 # 己方机跟踪高度
  own_takeoff_m: 14.0 # 己方机起飞高度
  target_cruise_m: 12.0 # 目标机巡航高度
  own_clearance_min_m: 0.5 # 垂直净空下限
  derived: {h_max_map_m: 10.55, h_max_env_m: 7.975, rule_version: 1}
```

派生注入：`apply_flight_altitude_params`（`intruder_driver.cruise_alt_m` + 同值别名 `alt_m`、
`task_manager.air_hover_climb_m = own_takeoff_m − 0.2`、网弹道条件派生、`jam_envelope_max_alt_m` =
目标高度 + 0.5，**只升不降**）与 `apply_flight_altitude_air`（`standoff_follower.height`、
`takeoff_controller.takeoff_altitude_m`），时序在 `compose_params` 之后、`apply_spawn_layout` /
`assertions` 之前。`air.yaml` / `base.yaml` 同名键保留作 standalone / 单测兜底并注明「运行期由
地图派生覆盖」。网弹道**条件派生**：`target_cruise_m ≤ (v0·sinθ)²/(2g)` 时逐值不变（`minimal` /
`open_field` 的历史证据基线不被改写），否则按「解析顶点 = 目标高度 + 0.65 m、θ=85°、timeout = 落地
时刻 + 0.3 s」重标定（`yard`：`v0=15.81 / θ=85° / timeout=3.51 s`，apex 12.643 m）。
capture 场景 goal 必须与目标保持水平偏移（`minimal` / `open_field` 1.0 m、`yard` 2.5 m）。
四条启动断言并入 `assertions`、误配即拒绝运行：`flight_altitude_derived_matches_source`、
`own_height_covers_h_max_env`、`dz_within_perception_range`、`target_within_capture_envelope`；
四条与 backend 无关（lightweight 用地图声明值 + `air.yaml` 基线做判据，如实降级、不伪造通过）。
视觉平面来源白名单由 `{scene}` 扩为 `{map, scene}`，`base` 仍拒绝。

<a id="spawn-layout"></a>
### (i) 出生布局单一真源与坐标（F1，2026-10-31）

**用户裁定**：「双方放在相对两条短边附近，己方车机初始位置相近」。
中央空旷区是 `agc_world.sdf` 的 `apron_center`（混凝土作业坪，**40 × 20 m**，中心 (0,0)），
两条**短边** = x = −20（西）/ x = +20（东）。实测可用矩形是 40 × 18.75 m
（北侧被 `sign_a`(−11, 9.5) 与 `tower_n`(−6, 11.5) 的图元侵入约 1.25 m）。

**坐标（单一真源 = `src/agc_task/config/spawn_layout.yaml`）**：

| 实体 | 坐标 |
|---|---|
| 车 `agc_car` | **(−15, 1)** |
| 目标 `intruder_uav` | **(15, −2)**（世界放置 `z=2.0`，PX4 attach 前瞬态） |
| 己方机 | **(−11, 1)**（`z=0.2`） |

**三组设计距离**：车↔目标 **30.15 m**（判据 ≥30）、己方机↔目标 **26.17 m**（判据 ≥25）、
车↔己方机 **4.00 m**（判据 3–8）。出生净空下限只增不减（由旧 11.85 m 提升到 30.15 m）。

**为什么"坐标不随地图变"**：三图同坐标保证 s04 / 对照场景可直接比较；
三图核查最小裕度 yard 3.19 / minimal 11.62 / open_field 8.65 m，安全层待机环带在三图均存在
≥90° 连续可行弧，且**西侧（己方机来向）恒为可行**。

**派生规则**：`spawn_layout.yaml` 同时喂三处—— 世界 spawn、复位位置（`/agc/scenario/reset`）、
己方机起飞参考（`PX4_GZ_MODEL_POSE` / `origin_pose`），三处取**同一组坐标**，不可能漂移。
固定任务目标的默认 goal = 目标出生位 + `goal_dx_m`（取 −2.5，落在目标以西 2.5 m）。

**已知边界（如实登记）**：仓库核查口径 (g)（`_obb_clearance − footprint_radius`）对 yard 两侧
30–34 m 分段围墙极为保守（footprint 取实体水平外接圆 ≈ 半长 15 m），故该口径下 min 3.19 m；
**真实几何净空**（点到图元表面距离）同点位为 car 8.85 / target 10.36 / own 8.34 m，仍 > 0。

## 不做什么（边界）
- **不**让各域运行时直读物理世界几何（会静默引入真值优势、破坏感知通道建模口径）。
- **不**把真源放 `air.yaml` / `base.yaml` 内（会加剧「谁是真源」的歧义）。
- **不**重写地图算法、**不**改 `/agc/map` 的 `OccupancyGrid` 契约与三态语义。
- **不**用一根通长围墙闭合 100×100（100 m 墙的二维静态圆盘会吃掉全部空域、把 8 字轨迹判为不可行）。
- **不**引入贴图 / mesh：材质只有标量 PBR + 纯色，出不了砖缝、锈斑、标线等纹理细节。
- **不**新增第二 ROS 命令者；**不**改冻结 9 消息 / 服务 ABI；**不**改 `/agc/ground/cmd_vel` 的
  「唯一执行口语义」。几何真源与派生链一律遵守[契约](0020-package-boundaries-and-runtime-topology.md#hard-constraints)，
  本篇不复述约束内容。
- 与 [硬约束 hc-10](0020-package-boundaries-and-runtime-topology.md#hc-10) 的**分野**：跟踪冻结（`freeze`）归跟踪常开约束，本篇管几何与高度派生；
  两者都在本 ADR 边界之外互不替代—— 高度派生只喂参数，不改变的 `freeze` 语义。

## Considered Options
- **保留 `kinematic_sim`** —— 被否：动力学不可信，与真实逃逸口径不符。
- **仅文档标注、仍各自硬编码几何** —— 被否：移动立柱仍可能只改一域。
- **保留仅 `hashBytes(data)` 作地图身份** —— 被否：同 `data` 不同几何仍判「未变」。
- **保留分箱 + 固定 yaw 容差、仅调大阈值** —— 被否：无法证明不欠包，边缘跨格必漏报。
- **用内容 hash 同时充当更新序号** —— 被否：hash 表内容等价、序号表更新计数，语义不同。
- **随机撒点 + 手工调朝向做多样性 / 照抄 Nav2 warehouse 资产** —— 被否：前者是伪多样性，后者是
  室内仓库（28×45 m），可迁移的是分布范式不是资产。
- **把覆盖目标改成「图元和」口径** —— 被否：多图元堆叠被重复计数，不是真实占地。
- **新建 `flight_altitudes.yaml`** —— 被否：引入「几何文件 ↔ 高度文件」两处需同步的清单。

## Consequences
- **正面**：单点修改只改真源、各域随之派生、几何版本可复核；地图身份含几何元数据 + 源版本，
  「内容等价」与「实质重建」分别可查且不欠包；车体动力学可对标安全层；`yard` 抬到 12 / 14 m 后净空
  3.45 m、`dz=2.0` ⇒ 水平预算 11.83 ≥ 10.2、三维斜距 10.39 ≤ 12、俯仰角 11.1° ≤ 35°，全部通过；
  视觉平面误差放大从 2.0× 降到 1.25×。
- **代价 / 限制**：内容身份 hash 的字节序依赖**同机同架构**（本项目全链满足，跨架构须复核）；
  `rebuild` 每次候选都做完整栅格化（地图规模小、可接受）；`minimal` / `open_field` 除真源位置外
  行为等价（`static` 仍含两根立柱、`none` 仍无立柱，净空校验与 `safety_shield` 语义不变）。
- **取证**（，先学后做 + 实测）：`experiments/w6-task-eval/<run_id>/r040/bench.json`（同 `data` 不同
  `origin_x` ⇒ data-only hash 相同而内容身份 hash 不同；跨格 ⇒ `update_seq` 递增；同内容反复输入 ⇒ 两者不变）；
  三图核查 `tests/check_scene_geometry.py` 整体 PASS（含 `coverage_union_in_5_12`、`all_maps_uniform`、
  `is_100x100_origin_-50`、`material_finish_match`）。
- **未决**：① standalone 回退副本现由检查器保一致，长期可统一改派生以彻底消除副本；② 长围墙在
  二维静态圆盘安全层下仍是**降级表达**（分段），安全层升级为多边形 / 线障碍后可改回通长围墙；
  ③ 覆盖目标只对 `yard` 断言（`open_field` 是稀疏对照图，故意不达标）；④ 测绘相机正俯视**未实施、也未立项**：机载俯视须改 xacro 加 −90° 俯角，不能只改参数；
  且单目正俯视拿不到障碍高度 Z（需双视差）。该需求**当前无承载者**；⑤ GUI 窗口截图仍未取得（本机
  Wayland 无可用截屏工具），视觉取证改用同姿态相机传感器渲染并标注 `backend=gz-offscreen-camera`。

## 参考
- [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)（地面控制栈：RL 主控 / Nav2 安全层）
- [ADR-0009](0009-perception-truth-derived-and-vision-path.md#top)（感知真值派生与视觉路径）
- [ADR-0011](0011-interception-and-fire-control.md#top)（网弹道与交战包络）
- [ADR-0012](0012-spawn-clearance-and-reset-transaction.md#top)（出生净空：用派生几何）
- [ADR-0006](0006-experiment-artifacts-and-evidence-discipline.md#top)（产物与证据纪律）
