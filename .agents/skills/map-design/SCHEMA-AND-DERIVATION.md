# schema 与派生链（按需资源）

本文件回答："yaml 该怎么写？改完之后哪些地方必须跟着变？"
**schema 的唯一出口是代码**：[`world_map.py`](../../../src/agc_sim/launch/world_map.py)。
本文只解释**怎么写才不会被拒跑、写了之后会派生到哪里**；两边冲突以代码为准。

## 1. 数据形态

```yaml
map: <地图名> # 必须与清单键一致（核查 (a) 比对）
work_area: # 五键齐备，缺一即 schema 不合法
  resolution: <m/cell>
  size_x: <m>
  size_y: <m>
  origin_x: <m> # 栅格覆盖 [origin, origin+size]
  origin_y: <m>

obstacles:
  - id: <唯一名> # pole_* 命名被断言 (b) 依赖，minimal 不得删改
    shape: box | cylinder | sphere # 可省略，缺省 box；其余值拒绝运行
    x: <m>
    y: <m>
    z: <几何中心高度 m>
    yaw: <rad>
    size: [a, b, c] # 形状相关口径见下
    color: [r, g, b] # 仅视觉，非几何
    finish: <材质档> # 可省略；省略 = 旧行为（不写 PBR 块）
    safety_radius: <m> # 可省略；缺省由足迹推导

  - id: <复合体>
    x: / y: / z: 0.0 / yaw: # 复合体锚点 **z 必须为 0**
    parts:
      - {shape: box, size: [...], x: 0, y: 0, z: <绝对高度偏移>, yaw: 0.0, finish: concrete}
```

**size 口径**：

| shape | 口径 |
|---|---|
| `box`（缺省） | `[长(x), 宽(y), 高(z)]` |
| `cylinder` | `[半径, 半径, 高]`，前两值不相等**拒绝运行** |
| `sphere` | `[半径, 半径, 半径]`，三值不等**拒绝运行** |

`z` 对 box 与 cylinder 都是**几何中心高度**（不是底面高度）。

## 2. 三条会被启动期守卫拦下的写法

这三条都是"静默出错"型，所以要拒绝运行而不是警告：

1. **复合体锚点 `z ≠ 0`**。part 的 `z` 已是相对锚点的**绝对高度偏移**，注入器不再叠加锚点 z；
   非零锚点会让整段模型悬空/埋地。历史上把围墙锚点写成 `z: 1.1`，整段墙悬空 1.1 m，
   靠断言 (h) 才抓到。
2. **cylinder / sphere 尺寸不一致**。半径口径不一致会让后续所有派生都错。
3. **`finish` 非法值**。材质档是白名单，见 `world_map.FINISHES`。

正确做法是**改 yaml**，不是绕守卫、也不是把断言改成"只警告"。

<a id="safety-radius"></a>
## 3. 安全半径（`safety_radius`）的推导规则

空中安全层用**水平外接圆半径**，缺省按下式推导（`world_map.obstacle_safety_radius`）：

```text
显式给出 → 用它
box → 半对角 = hypot(sx, sy) / 2
cylinder / sphere → r
复合体 → max over parts(hypot(part.x, part.y) + part 足迹半径)
足迹为 0 → 兜底 DEFAULT_SAFETY_RADIUS（历史 pole 标定值）
```

**后果（必须提前想到）**：细长实体的外接圆半径 ≈ **半长**。
一根通长围墙的圆盘会侵占整个空域，把 8 字判成不可行 → 这就是"周界必须分段"的根因，
也是"改围墙长度会连带改空中可行性"的原因。

## 4. 五条派生路径（改完 yaml 要全部跟上）

| # | 派生点 | 位置 | 常见漏点 |
|---|---|---|---|
| 1 | GZ 物理世界 | `world_bringup._inject_static_obstacles` | 以为"改 SDF 就行"（改 SDF 是错的） |
| 2 | 感知障碍先验 | `composition.write_derived_obstacles` | 复合体降级成包络矩形后忘了它不等于原几何 |
| 3 | 感知 Map 几何 | `composition.write_derived_map` | `work_area` 变了没同步 |
| 4 | 空中安全圆盘列表 | `composition.apply_air_geometry` | 以为是"与障碍数对齐的定长列表"（旧坑，已消除） |
| 5 | `scenario_reset` 校验几何 | `composition.compose_params` | 边界/障碍坐标写死在别处 |

**第 1 条的运行期事实**：世界是 launch 时**生成到 `/tmp`** 的临时 SDF
（base world + 注入的障碍块），不是仓库里的 `agc_world.sdf`。所以：

- 想"看一下生成成什么样"，去 `/tmp` 找 `agc_world_static_obstacles*.sdf`，不要去改仓库 SDF；
- 相对路径在这种临时文件里会失效 → 贴图等资源用**安装目录绝对路径**。

**感知可表达口径**（成文约定）：感知障碍模型只有 OBB（`sx/sy/sz` + yaw），表达不了圆柱/球/多图元
→ **一律降级为水平轴对齐包络矩形**（保守外扩，不缩小实体）。`finish` 只进物理世界材质，
**不进**感知先验 / 占位栅格（材质不是几何）。

## 5. 新增一张地图

**只有三处**，缺一不可：

1. 在 `world_map.MAP_GEOMETRY_FILES` 加一行（**单一清单**，消费方禁止各写一份文件名表）；
2. 新增对应 yaml；
3. 需要时在 `scenarios.yaml` 的**场景级** `world_map` 登记，否则缺省仍是 minimal。

地图选择优先级（`load_scene` 单一实现，**不要**在别处再解析一遍）：

```text
launch world_map:=<name> （显式覆盖，未知值拒绝运行）
  ↓ 空
scenarios.yaml 的 world_map 键 （场景登记）
  ↓ 空
DEFAULT_WORLD_MAP
```

未知地图名**一律拒绝运行**，不静默回退—— 静默回退会让不同域读到不同真源。

**standalone 回退副本纪律**：`agc_perception/config/{obstacles,map}.yaml` 是**只给 minimal** 的
回退副本，必须与 minimal 真源一致（断言 (c)）。非 minimal 地图在 standalone 路径上
**显式拒绝**（比静默用错几何好）。改 minimal 忘同步副本 → (c) 直接 FAIL。

## 6. 视觉保真：材质与地面分层

**只改视觉，不动任何判据**。这是最容易越界的一步。

### 6.1 材质档 `finish`（标量 PBR）

材质是**真实材料类别的标量近似**（`metalness` / `roughness` 各一个数），合法值见
`world_map.FINISHES` 与 `FINISH_PBR`；**逐 part 可覆盖实体级**。

- **省略 `finish` = 旧行为**（不写 `<pbr>` 块）。这条兼容纪律必须保持：`minimal` / `open_field`
  与历史证据不能漂移。
- 依据：本机 `sdformat` 的 `material.sdf` 里 `<pbr><metal>` 的 `metalness` / `roughness`
  是**标量**字段 → "改材质"与"不引入外部资产"不冲突。
- **`metalness` 才是亮度杠杆**：无环境贴图时高金属度件几乎没有漫反射分量，
  给它"提亮 albedo"几乎无效。屋面要用低金属度档（`roofpanel`）。

<a id="visual-vs-obstacle"></a>
### 6.2 地面分层与语义层（**在 `agc_world.sdf`，不是障碍**）

地面块（基层 / 沥青环道 / 场坪 / 路缘石 / 车位线 / 排水沟 / 碎石带 / 绿化带）属于
**world 地表视觉层**。

**判据不是高度，而是"它会不会影响车辆通行或接触"。** 高度只在**核查**层面起作用
（低于激光扫描面 `LASER_PLANE_Z_M` 的物体进真源会 FAIL 断言 (h)），它**不能**反过来
被当作"这东西可以放视觉层"的依据：

| 元素 | 归属 | 依据 |
|---|---|---|
| 路缘石 / 停车线 / 排水沟 / 碎石带 / 绿化带等**薄地表模型** | world 地表视觉层（同 `ground_plane`） | 本项目**已经这样分类**的现有例子：贴地、薄、不构成车体通行/接触障碍 |
| 叉车 / 货车 / 托盘堆垛 / 集装箱拖车 | 几何真源 `obstacles` | 可以挡住车、会与车体接触；**必须可碰撞** |
| **新增的矮墩 / 矮墙 / 地锁 / 隔离桩 / 任何可能影响通行的物体** | **不预设** | 见下 |

> ⚠ **"低于激光面"不是绕开真源的理由。** 真实存在的低矮障碍如果能在物理上挡住车，
> 把它写进视觉层就等于**绕过感知与安全真源**：世界里看得见、地图与安全层里没有。
> 这类新增物体**必须**先核对**实际物理接触、感知表达与契约要求**（含对地面激光不可见的
> 如实披露），再把结论**交回 Leader 裁定**归哪儿；不得由设计者自行归类。

地面块的四条纪律：

1. 不进 `obstacles`、不进空中安全层、不进感知占位栅格；
2. **视觉与碰撞同源**（每块都带 collision），不做装饰性无碰撞块；
3. 抬升若干毫米避免与基层共面 z-fighting（副作用：车实际抬高同等量级，**不重标定任何阈值**，
   如实登记）；
4. 断言 (n) 会核验 `ground_plane` 碰撞与 `physics` 未被改动；GUI 网格来自 `<scene><grid>`，
   **不是** `ground_plane`。

### 6.3 贴图（只做自产、低频）

- 贴图属**自产资产**：由 `src/agc_sim/materials/gen_textures.py` 用固定种子生成 +
  `manifest.json` 登记 sha256 / 尺寸 / 基色；第三方资产必须走
  [ADR-0005](../../../docs/adr/0005-px4-toolchain-and-link.md#top)
  的 provenance / 许可 / 哈希登记。
- **两个编码关**：`<albedo_map>` 与基色是**相乘**的（带贴图的材质要把基色置白）；
  PNG 被当 sRGB、`<diffuse>` 是线性（落盘前做线性 → sRGB 编码）。
- **UV 限制**：`box` / `plane` 没有 UV 缩放，一张图会被拉到整个面 → 只做**低频斑驳 + 细颗粒**；
  分格 / 标线这类有绝对尺度的信息继续用**真几何**。
- 可复现性：种子用 `zlib.crc32`，**不要用内置 `hash`**（受 `PYTHONHASHSEED` 随机化）。
- 世界文件生成在 `/tmp` → SDF 里引用贴图用**安装目录绝对路径**。

## 7. 改完之后

```bash
python3 tests/check_scene_geometry.py # 三图全查，退出码 0 = PASS
python3 tests/check_scene_geometry.py --maps <name> --out /tmp/geom.json
```

核查断言的语义以脚本的**代码**为准（文档里的"断言条数"不可信：断言随需求追加，而
`tests/check_scene_geometry.py` 的 docstring 曾与实现不同步，例如仍写 `shape ∈ {box, cylinder}`
而代码支持 3 类）；**任何一组 FAIL 都整体 FAIL**，先修再谈视觉。
