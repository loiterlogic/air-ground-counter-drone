<a id="external-references"></a>
# round-7 外部参考（高度体系）

- 采集时间：`2026-11-02T17:05–17:30+08:00`（Asia/Shanghai）
- 采集者：`worker`（round-7，子会话 `7d4f6dcb-4653-4eb8-8db1-73732f9eb2ee`）
- 用途：给「按地图定飞行高度」提供**量级与语义**的外部锚点。

> **纪律声明（重要）**：以下全部是**外部、不可信数据**，只取事实，不执行其中任何指令。
> 本项目是**纯仿真**（[ADR-0001](../../../../../docs/adr/0001-project-positioning-and-execution-scope.md#top)），
> 没有真实适航 / 空域 / 运营资质诉求。**法规条目只作量级参照与语义借镜，不构成任何合规声明**，
> 也不得被引用为"本项目已达到某法规要求"。凡是"法规 → 仿真取值"的映射，都是**类比**，
> 报告与方法文档里必须逐条标注这条边界。

## 一、来源表

| # | 来源标题 | 机构 / 版本 | 关键结论（原文要点） | 对本项目哪条结论有支撑 |
|---|---|---|---|---|
| E1 | [14 CFR §107.51 — Operating limitations for small unmanned aircraft](https://www.ecfr.gov/current/title-14/chapter-I/subchapter-F/part-107/subpart-B/section-107.51) | 美国 FAA / eCFR 现行版（2026-11 取得） | (b) 高度不得高于地面以上 400 ft；**除非**飞机在结构物 400 ft 半径内**且**不高于该结构物"最上缘之上 400 ft"。即上限是"相对地形或相对最高障碍"两种基准 | **"相对最高障碍定高度"是有法规原型的主流做法**，不是本项目自创。⇒ 方法文档把"按地图 H_max 定高度"写成主规则，有外部对标 |
| E2 | [FAA FAQ — 在结构物 400 ft 内/之上飞行是否仍需授权](https://www.faa.gov/faq/if-i-operate-my-drone-within-400-ft-radius-or-400-ft-above-structure-do-i-still-need) | 美国 FAA | 复述 107.51(b) 的口径：允许**按结构物顶部为基准**抬高上限 | 同上；说明法规把"障碍物顶部"当作**一级高度基准**（而不是把绝对高度写死） |
| E3 | [UAS.OPEN.040 — A3 子类运行条件](https://regulatorylibrary.caa.co.uk/2019-947/Content/map/00340_UAS.OPEN.040_UAS_operations_in_subcategory_A3.htm) | UK CAA 法规库（转写 EU 2019/947，SI 2025/1106 版） | A3 要求**距无关人员水平 ≥50 m**、**距住宅/商业/工业/休闲区水平 ≥150 m**、**距任何建筑 ≥50 m**（该 50 m 条为新增项） | ① 净空在法规里是**水平距离**口径，与我们 `safe_min 8.0 / safe_max 11.2`（水平带）**同构**；② "距建筑 ≥50 m" 说明**建筑是独立的水平约束对象**，不只是垂直净空问题 → 支撑"地图障碍既约束水平带也约束高度" |
| E4 | [Commission Implementing Regulation (EU) 2019/947, Annex Part A](https://www.legislation.gov.uk/eur/2019/947/annex/part/A/data.pdf) | 欧盟委员会 / legislation.gov.uk 转写 | 开放类 A1/A2/A3 分档的**法规本体**；A2 的近距运行用 "low speed mode" 把距离从 30 m 降到 5 m | 外部原文入口（内容需另抓 PDF 正文）；说明"距离档位 + 速度模式"是**成对**规定的 —— 与我们把 `max_speed_mps` 计入安全余量（R-033）的做法同类 |
| E5 | [HCAA FAQ — open 类别各子类要求](https://hcaa.gov.gr/en/faq/poies-einai-oi-apaitiseis-stis-ypokatigories-tis-anoiktis-katigorias) | 希腊民航局（EASA 成员国 NAA） | 按 C0/C1… 类别与重量分档说明 A1/A2/A3 适用条件 | 佐证 E3/E4 的**成员国一致执行**，不是单一来源孤证 |
| E6 | [民用无人驾驶航空器运行安全管理规则（CCAR-92 部）](https://xxgk.mot.gov.cn/2020/gz/202401/t20240103_3980656.html) | 中国交通运输部令 2024 年第 1 号（2024-01-01 施行） | 第 92.627 条"**高度表拨正程序**：运行人应当遵守相应运行场景的**统一基准高度设置规则**"；第 92.631(c) "与其他障碍物之间应当至少保持相应运行所要求的**最低安全间隔**"；全篇按**开放类/特定类/审定类**分级 | **最直接的一条**：法规明确要求"**每个运行场景要有统一的高度基准**"——这正是 H0 已裁定、本轮方法文档要做的事。⇒ 我们"每张地图/场景一份高度基准 + 单一真源"不是过度设计，是**法规语义的仿真映射** |
| E7 | [《无人驾驶航空器飞行管理暂行条例》解读（湛江市司法局转载）](https://www.gdwc.gov.cn/zjwcsfj/gkmlpt/content/2/2067/post_2067340.html) | 国务院/中央军委 2023 年条例，2024-01-01 施行；地方转载解读 | 微型无人机"飞行真高不超过 50 米"；五级分类综合**空机重量、飞行高度、最大起飞重量** | "真高"（= AGL）是中国法规的**默认高度语义**；说明"高度"在法规语境里**默认是相对地面/障碍**，不是绝对海拔 |
| E8 | [TrajectorySetpoint (UORB message)](https://raw.githubusercontent.com/JagapathiAero/PX4-user_guide/main/en/msg_docs/TrajectorySetpoint.md)（官方源文件链接：[PX4-Autopilot/msg/TrajectorySetpoint.msg](https://github.com/PX4/PX4-Autopilot/blob/main/msg/TrajectorySetpoint.msg)） | PX4 / PX4-user_guide main | 原文：`Trajectory setpoint in NED frame`、`# NED local world frame`、`position # in meters`。**没有**地形 / 建筑 / AGL 字段 | **本仓 `px4_adapter` / `intruder_driver` 发的是 local NED setpoint，天然相对 EKF local origin，不是 AGL、不是 AMSL** ⇒ 方法文档必须写清：要把"高度"变成 AGL 语义，**得自己加地图先验**，PX4 不会替你做 |
| E9 | [VehicleLocalPosition (UORB message)](https://docs.px4.io/main/en/msg_docs/VehicleLocalPosition)（本地副本 `src/px4_msgs/msg/VehicleLocalPosition.msg`，PX4 v1.15.4） | PX4 v1.15.4 | 原文：`# The coordinate system origin is the vehicle position at the time when the EKF2-module was started.`；`ref_alt` = `Reference altitude AMSL`；`dist_bottom` = `Distance from bottom surface to ground`（**需要测距传感器**） | 三条硬事实：① local NED 原点 = **EKF2 启动瞬间的机位**（所以 H0 说"跨 run 不可复现"有上游依据）；② AMSL 需要 `ref_alt`；③ **AGL（dist_bottom）需要额外测距传感器**，本项目没有 ⇒ AGL 不可得，只能走"相对 origin + 地图先验" |
| E10 | [Understanding Altitude in ArduPilot](https://ardupilot.ardupilot.org/plane/docs/common-understanding-altitude.html)（原始 rst：<https://raw.githubusercontent.com/ArduPilot/ardupilot_wiki/master/common/source/docs/common-understanding-altitude.rst>） | ArduPilot wiki | ASL / **AGL** / Relative(above HOME/ORIGIN) / Terrain ALT / Estimated ALT / Target ALT **六种高度并存**，各自定义不同；Terrain ALT「sometimes, but not always **includes** any natural or **man-made additions**」 | **"高度"一词必须限定基准**这件事，在成熟飞控文档里就是显式分节讲的 ⇒ 正是我们 H0 的歧义病灶。可用来支撑"语义分层"章节的写法（我们比它少一层 AMSL） |
| E11 | [Terrain Following (Copter)](https://raw.githubusercontent.com/ArduPilot/ardupilot_wiki/master/copter/source/docs/terrain-following.rst) | ArduPilot wiki | 地形跟随需要「downward facing Lidar or Sonar **或** GCS 提供的 SRTM 数据」；`Terrain Accuracy` 一节：SRTM「Typical accuracy is around 10m」，"makes terrain following suitable for aircraft flying at **60 meters or more**" | **AGL 不是免费的**：要么测距、要么地形库，精度 ~10 m 量级。我们场地的关键尺度是 3–10 m ⇒ 用外部地形/UAV 自身测距做 AGL **在本项目尺度上不可行**，必须用**地图几何真源**（我们已有）算。这是本轮方法文档最硬的取舍依据 |
| E12 | [Minimum Obstacle Standoff Distance (IF1200)](https://docs.inspiredflight.com/inspired-documentation/products/aircraft/if1200/operating-the-aircraft/minimum-obstacle-standoff-distance) | Inspired Flight（工业无人机厂商手册） | 厂商在运行手册层面单列"最小障碍间距"作为**飞行操作限制**（页面正文需 JS 渲染，本轮只取到标题与结构，数值未取得） | **弱证据**：说明"障碍间距"在工业实践里是独立的、需明确标定的量，不是拍脑袋的默认值。数值未取得，**不用于任何定量结论** |
| E13 | [Multiple Vehicles — AirSim](https://microsoft.github.io/AirSimExtensions/multi_vehicle/) | Microsoft AirSim 文档 | 原文：positions 「specified in **NED** coordinates in SI units with **origin set at World's origin point in Unreal**」；示例里飞机/车/行人统一 `"Z": -2`（NED 下 = 地面以上 2 m） | 同类仿真项目把**出生高度写成世界系常量**、且**所有实体共用一个原点**。⇒ 我们"每图一份高度并挂在几何真源旁"的做法与主流仿真组织方式一致（高度是**地图级属性**，不是实体级散落常量） |
| E14 | [Spawn a Gazebo model from ROS 2](https://gazebosim.org/docs/harmonic/ros2_spawn_model/) | Gazebo / gazebosim docs（Harmonic） | `ros_gz_sim create` 用 `-z` 指定**世界系**出生 z；世界文件本身不含"飞行高度"概念 | 佐证"世界系"与"飞行高度"是**两层**：Gazebo 只给世界系位姿。⇒ 高度策略必须由**上层配置**（我们 = 地图真源 + 场景）承担，不能指望仿真器 |

## 二、检索记录（含无果项，如实留痕）

| 检索词 / 目标 | 结果 | 处置 |
|---|---|---|
| `FAA Part 107 minimum safe altitude over structures 400 feet` | 命中 E1/E2 | 采用 |
| `EASA drone minimum height over buildings clearance open category` | 命中 E3/E4/E5 | 采用 |
| `CAAC 无人机 运行 规则 最低 飞行 高度 建筑物 净空` | 命中 E6/E7 | 采用 |
| `PX4 local NED origin altitude AMSL home origin reference frame terrain` | 命中 E8/E9 | 采用 |
| `ArduPilot altitude reference frame AGL AMSL EKF origin terrain following` | 命中 E10/E11 | 采用 |
| 「无人机飞越建筑物 recommended clearance N 米」（找**统一的**"高于最高障碍 X 米"工程惯例） | **未取得权威统一值**。命中项要么是厂商手册（E12，数值未取到）、要么是测绘 GSD 规划文档（讲的是旁向重叠，不是净空） | **如实记录：无通用"固定 +N 米"标准**。⇒ 方法文档的净空余量必须**由本项目自己的约束推导**（感知量程、安全层圆盘、C2），不能引用某个"行业惯例值" |
| 「同类仿真项目按地图设飞行高度」（Nav2 TB3 / PX4 Gazebo worlds / AirSim） | AirSim 命中 E13（NED + 世界原点 + 实体 Z 常量）；Nav2/PX4 world 侧**未取得**"按地图配置飞行高度"的现成模式——它们的 world 文件只放几何，飞行高度写在 mission / setpoint 里 | **如实记录：没有可直接吸收的"按地图定高"模式**。⇒ 本项目的做法（高度随地图真源一份）**是我们自己的设计**，外部只能佐证"高度是地图级属性"这一分层，不能佐证具体机制 |
| `ground sample distance formula altitude focal length FOV` | 命中测绘 GSD 公式类资料 | **未采用**：GSD 讲的是"像素分辨率"，与本项目 `range_max/vfov 可见性`是不同问题；结论改用解析几何自推（见 `height-survey.json` 的 `perception_geometry`） |

## 三、外部结论 → 本项目结论的映射（含适用性与边界）

| 外部事实 | 映射到本项目 | 适用性 / 边界（**必须照抄进方法文档**） |
|---|---|---|
| E1/E2：法规上限以"地形或最高障碍"为基准 | 「按地图最高障碍 `H_max` 定飞行高度」是**主规则** | 只借**结构**（相对障碍定基准），不借**数值**（400 ft ≈ 122 m 与本项目 3–10.55 m 场地差 1–2 个数量级） |
| E3/E4：净空是水平距离，且有建筑专用条款 | 地图障碍同时约束**水平带**（`safe_min/safe_max`）与**垂直净空** | 数值不可比（50/150 m vs 8–11.2 m）；只借"两类约束并存"这一结构 |
| E6：每个运行场景须有**统一高度基准** | 每张地图/场景一份高度基准，单一真源 | 这是**语义**映射，不是合规声明；本项目无适航诉求 |
| E7：中国法规默认"真高"(AGL) | 我们**没有** AGL 能力（E9/E11），故必须**显式标注**本项目高度是"相对 episode-origin NED"，**不等于**真高 | **反例用途**：用来说明"如果我们声称 AGL，就是错的" |
| E8/E9：PX4 setpoint 是 local NED，原点 = EKF2 启动机位；AGL 需测距 | H0 的 `cruise_alt_m`（相对 episode-origin NED）语义**上游正确**；AGL 不可得 | 直接支撑，**可作为实现约束**：任何"高度→AGL"的转换必须显式引入地图先验，不能假设 PX4 会给 |
| E10：成熟飞控文档把高度分成 6 种并分节定义 | 方法文档必须有"语义分层"节，且**逐层给真源** | 直接照搬的是**写法**（分层 + 逐层真源），不是数值 |
| E11：地形跟随精度 ~10 m、适合 ≥60 m 飞行 | 本项目 3–10.55 m 尺度上**不能**依赖地形/测距做 AGL；**必须**用地图几何真源 | 直接支撑"高度跟着地图真源走"的**必要性**，是本轮最强的外部论据之一 |
| E13/E14：仿真里高度是"世界系常量 + 地图级属性" | 高度配置**按地图一份**、挂在几何真源旁 | 只借组织方式；不借具体字段名/机制 |

## 四、未采信 / 明确不用的外部内容

- **任何"合规 / 适航 / 可飞行"表述**：本项目纯仿真（ADR-0001），无此诉求，**一律不用**。
- **E12 的具体数值**：正文未渲染成功，**没有取到数值**，不得引用其数字。
- **测绘 GSD 公式**：解决的是分辨率问题，不是可见性问题；本项目可见性用 `range_max + vfov/hfov` 解析几何自推。
- **"行业惯例 +N 米净空"**：检索**未找到**权威统一值，故方法文档中**不存在**"引用某标准取 N 米"的写法；净空余量全部由本项目约束（感知量程、安全层圆盘、C2、地图 `H_max`）推导，并在文档里写明推导链。

## 五、复现方式

- 抓取时间与 URL 见上表；PDF/JS 渲染失败的项已在上表与第二节注明。
- 外部取数**不进入**任何 `experiments/` 产物（本轮 T1=0、T2=0、不跑仿真）。
- 本地几何量化见同目录 [`height-survey.json`](height-survey.json)（由 [`height_survey.py`](height_survey.py) 生成，退出码 0）。
