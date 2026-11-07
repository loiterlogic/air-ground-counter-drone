<a id="top"></a>
# PX4 工具链：uXRCE-DDS 链路、本体依赖与 pin 清单

<a id="status"></a>

## Status

accepted（2026-11-02 由 0005 / 0012 / 0065 / 0067 / 0068 合并；链路协议、本体形态与 pin 纪律结论未变，agent 版本适用值统一为 v2.4.3）

## 背景

空中链路必须先定协议与本体形态，否则节点无法处理 uORB 语义，工作空间也无法界定「什么进 colcon、什么进 git」。`toolchain/` 内容不入 git（仅放行 `toolchain/README.md`），一旦 pin 值只记 tag，新机器可能拿不到必要兼容输入或产出不同 DDS / PX4 行为，而「已有机器构建成功」不等于可从空目录重建。两处 launch 入口曾用包 share 目录深度上溯推断项目根，merge-install / overlay 布局下会取到不同的根且不校验存在性。第三方 mesh 的来源与许可只有注释断言，交付时难以说明哪些资产原创 / 来源 / 修改 / 许可。

## 决策

### (a) 链路协议：uXRCE-DDS + `px4_msgs`，弃用 MAVROS

空中链路以 Micro-XRCE-DDS Agent + `px4_msgs`（`release/1.15`，与固件 v1.15.4 同版）直连 PX4 uORB，弃用 MAVROS / MAVLink 中间层。节点需自行处理 uORB 语义：微秒时间戳、NED/FRD 与 ENU 的换算、QoS 配置。`px4_ros_com` 仅作示例参考。

### (b) 本体形态：`toolchain/` 外部依赖 + `px4_msgs` 内联

- **PX4 本体（固件 / SITL）**：作为 `toolchain/` 外部依赖，**不入 colcon、不入 git**（`toolchain/COLCON_IGNORE` + `.gitignore` 仅放行 `/toolchain/README.md`），以 **v1.15.4 + 子模块 SHA** pin 住。
- **`px4_msgs`**：**内联入库**于 `src/`—— 接口包必须在工作空间内编译才能被 `ros2 interface show` 与其它包依赖发现（对照：Nav2 是运行时栈，走 apt + `<depend>`，见 [ADR-0003](0003-nav2-paradigm-absorption.md#top)）。
- **版本同步**：PX4 版本与 `px4_msgs` 必须同步（v1.15.4 对 `release/1.15`），升级须连同本篇复核。
- **agent 版本适用值**：现行 **v2.4.3**（对系统 Fast DDS 2.14 / fastcdr 2.2 构建，与 ROS 2 Jazzy 同源）；v2.4.2 是早期适用值，其自建 DDS 2.11 与 ROS 侧跨版本不互通，**不回退**。

### (c) `toolchain/README.md` = 唯一入库的可重建 pin 清单

`toolchain/` 其余内容被忽略，pin 值**只能**写在该 README 内（写到别处即随忽略丢失）。除人读摘要表外，含一个 fenced YAML 机器可读块（`agc_toolchain_pins:`，`schema: 1`），键：

| 键 | 内容 |
|---|---|
| `git_repos` | PX4（`tag` `v1.15.4` + `head` + **9 个 SITL(gz) 必需子模块逐条 SHA**）、uXRCE-DDS-Agent（`tag` `v2.4.3` + `head`） |
| `artifacts` | 逐条 `sha256`：`bin/MicroXRCEAgent`（包装脚本）/ `build_ros/MicroXRCEAgent`（真实二进制）/ `build/px4_sitl_default/bin/px4`（SITL）/ `microxrce_compat/fmt_compat.hpp`（AGC 自研兼容头，非上游文件） |
| `build_options` | PX4 `config=px4_sitl_default` + `config_file=boards/px4/sitl/default.px4board` + `RelWithDebInfo`；Agent `build_ros` + 系统 FastDDS/FastCDR/Logger、`Release`、`-include` 兼容头 |
| `dds_versions` | ROS 侧 `fastrtps` / `fastcdr`；host `spdlog` / `fmt`；`localdeps/sysroot` 的 `spdlog` / `fmt` |
| `localdeps_debs` | `localdeps/debs/` 逐包 `sha256`（离线 `.deb` 的来源与哈希） |

README 另含「从空目录恢复（配方）」节（克隆 tag + 初始化 9 子模块 → PX4 SITL 构建 → agent 构建 → 入口包装脚本 → 离线 `.deb` → 运行期环境 `PX4_GZ_STANDALONE` / `PX4_GZ_WORLD=agc_world` / `PX4_SIM_MODEL=gz_x500` / `GZ_SIM_RESOURCE_PATH` → 校验脚本）与「离线包访问方式」节（GitHub 极慢走 Gitee 镜像；pip 走清华源；`localdeps/debs` 为 Ubuntu 24.04 noble amd64 离线包；ROS 侧 DDS 直接来自 `/opt/ros/jazzy`，无需自建）。

### (d) 一致性校验：`scripts/toolchain_pin_check.py`

只读脚本，解析上述 yaml 块并**逐项比对实测**：产物 `sha256`、仓库 `HEAD` / `tag`、子模块 SHA（区分 `missing` / `not_initialized`）、依赖版本（`dpkg-query` + sysroot 头文件宏）、离线包哈希**集合**双向差集。**缺失即 FAIL**（不静默忽略）；`dpkg-query` 不可用记 **SKIP** 而非 PASS；`ok=false` 即退出码 1。任何不一致必须显式报出，不得以「环境差异」放行。实测 25 项全 PASS。

### (e) 工具链根显式注入与启动前校验

- 两入口（`main.launch.py`、`air_bringup.launch.py`）**声明** launch 参数 `agc_root`（默认 = 固定项目根 `/home/chen/AGC`，可覆盖），工具链路径由该参数派生；**移除** `parents[3]` 式深度上溯。所有 `DeclareLaunchArgument` 仍在顶层声明，保证 `--show-args` 可内省（`air_bringup` 经 `OpaqueFunction` 读参数）。
- **启动前校验**：两入口校验 `toolchain/bin/MicroXRCEAgent` 与 `toolchain/PX4-Autopilot/build/px4_sitl_default/bin/px4` 存在，任一缺失即 `raise RuntimeError`（含缺失路径与 `agc_root:=<path>` 提示），不静默。
- **ROS 资产仍经 ament index**：世界 / 邻包配置仍用 `get_package_share_directory`，不改为全仓相对化。
- **固定根约束维持**：不引入任意搬迁假设；如需可搬迁，另提根路径约束挑战与成本。
- `scripts/toolchain_root_check.py`（只读、退出码语义）：静态断言两入口无 `parents[` 式上溯且均声明 `agc_root`，功能断言两工具链二进制存在；`ok=false` 退出码 1。实测 6 项全 PASS。

### (f) 第三方资产来源、许可与哈希清单

- `docs/conventions/第三方资产与许可.md` = 政策 + 人读表 + fenced YAML 块（`agc_third_party_assets:`，`schema: 1`），逐资产记 **id / 上游来源（模型名 / owner / 资源 id / 取得方式）/ 下载版本 / 上游许可 / 署名 / `sha256`**。
- **许可分列、不外推**：自有包（`agc_*`）的 `Proprietary` **仅**适用自有代码，**不得**外推到第三方资产；第三方逐资产独立登记且**不得**标 `Proprietary`；**不**改包版本号。
- **据实登记、未核实即未决**：许可无法当场核实时登记候选许可 + `license_status: unresolved` + 理由（`license_note`），**禁止**未经验证地断言。现行：候选 `BSD`（上游 Husky ROS 资产族口径），Fuel 资源 id / 下载版本 / 随附 LICENSE 文本未取回 → 未决。
- **署名随资产入库**：`src/agc_sim/models/agc_car/meshes/NOTICE` 承载来源 / 署名 / 许可状态（含显式未决）；`agc_car.sdf.xacro` 顶部注释**去掉**未验证的 `CC0` 断言，改**引用**清单；**不改** mesh 内容与物理 / 惯性 / 传感器 / 几何参数。
- `scripts/third_party_asset_check.py`（只读、退出码语义）：清单与实测 `sha256` 一致、无未列出 mesh（双向集合）、第三方未标 `Proprietary`、`unresolved` 须有理由；实测 26 项全 PASS。

### (g) 空目录重建未实测（显式未决）

pin 校验只证明「**现值**与记录一致」，**不**证明「空目录可恢复」。**deferred**：干净环境 / 独立目录的端到端重建实测，原因是本轮无独立干净机器且禁止复制现有 `build/` 当重建证明；归属工具链复现出口，须在对照与冻结前实测一次。实测完成前，任何「环境已可重建」的结论**不成立**。

## 不做什么（边界）

- 不回退 agent 2.4.2，不引入 MAVROS / MAVLink 中间层。
- 不把 PX4 源码 / agent 源码 vendor 进 `src/` 或 git；不把 pin 清单拆成独立入库文件。
- 不「只记 tag、不记 HEAD / submodule / 产物哈希」；不复制现有 `build/` 当重建证明。
- 不引入任意搬迁假设，不用 `AGC` 环境变量做隐式根来源。
- 不改冻结消息 ABI、不改参数单一注入语义、不改包版本号；本轮不实建 tag、不实建全量 artifact manifest。

## Considered Options

- **MAVROS(2) 桥接** —— 被否：多一层序列化、延迟更高，且非 PX4 + ROS 2 官方主推方向。
- **PX4 源码 vendor 进 `src/`** —— 被否：体积大、非 ROS 包、构建重，污染 colcon 工作空间。
- **系统级 apt PX4** —— 被否：无合适发行包，且需自定义 SITL 机型 / 世界。
- **pin 清单入库为独立文件（JSON / 单独 md）** —— 被否：`toolchain/` 内容被忽略，独立文件不入库即丢失。
- **`parents[3]` 深度上溯推断根 / 只硬编码绝对路径** —— 被否：前者依赖 install 布局且无存在性校验，后者不可覆盖、不便测试。
- **沿用注释里的 `CC0` 断言 / 把 `Proprietary` 覆盖所有资产** —— 被否：未核实且与上游 `BSD` 口径不一致；错置第三方许可、违署名要求。

## Consequences

- **正面**：链路协议与本体形态唯一；任一 pin 漂移可当场报出（25 项 PASS）；根来源唯一显式、缺失即拒启动（6 项 PASS）；资产来源 / 许可 / 哈希独立可核（26 项 PASS）；agent 版本适用关系显式化（2.4.2 → 2.4.3）。
- **代价 / 限制**：pin 清单与实机深度耦合，产物哈希随重新构建而变，须显式更新 README 并重跑校验，不得静默接受漂移；默认根写死与固定根约束耦合，变更固定根须同步默认值；`unresolved` 字段需后续回填。
- **未决 / 后续**：干净环境端到端重建（冻结前）；Fuel 资源材料取回后置 `license_status: resolved`；多机 / CI 的工具链校验接入属后续。

## 参考

- [ADR-0002](0002-docs-source-of-truth-and-reference-discipline.md#top) 文档真源分层与引用纪律
- [ADR-0003](0003-nav2-paradigm-absorption.md#top) Nav2 走 apt + `<depend>` 的对照
- [ADR-0020](0020-package-boundaries-and-runtime-topology.md#top) 包边界与运行拓扑
- [ADR-0027](0027-uxrce-startup-reproducibility.md#top) uXRCE 启动可复现性
- 实现：`toolchain/README.md`、`scripts/toolchain_pin_check.py`、`scripts/toolchain_root_check.py`、`scripts/third_party_asset_check.py`、`docs/conventions/第三方资产与许可.md`、`src/agc_sim/models/agc_car/meshes/NOTICE`
