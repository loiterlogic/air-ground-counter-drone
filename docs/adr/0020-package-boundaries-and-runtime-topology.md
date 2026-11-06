<a id="top"></a>
# 包边界、语言选型与运行拓扑

## Status

accepted（2026-11-02 由 ADR-0011 / 0059 / 0061 合并；结论未变）

## 背景

三件事曾被当成同一条规则，导致「边界」既说不清也守不住：

1. **语言划分沿袭自旧树**——《目录与命名规范》隐含「节点包用 `ament_cmake`（C++）、RL / 工具用
   `ament_python`」，但**未经显式论证**。
2. **依赖类别混成一条规则**—— 早期 [包边界](../conventions/包边界.md) 的规则 1「`agc_msgs` 是唯一公共
   依赖」与规则 2「其余包之间不得互相依赖对方的库」照字面会**禁止必要的运行依赖**（如 `agc_task` 在
   launch 中起 `agc_air` / `agc_ground` / `agc_perception`），或促使这些真实运行依赖被隐藏、未在
   manifest 声明；依赖方向图也解释不了现状。
3. **多入口重复组装**——`m0_skeleton` / `w6_task_eval` / `w6_full` 各自内联一份**完全相同**的场景配置
   解析（base / registry / carriers 加载、carrier 校验、参数合并、轴断言、manifest 生成），参数路径
   分叉（`full` 另用 `air.yaml`），`backend` 未贯穿 summary，launch 身份字段与**入口名**分离，关键段
   启动依赖由**绝对时间 `TimerAction`**（12 / 25 / 35 s）承载 ⇒ 配置漂移不易发现，拓扑不是可审查实体。

## 决策

### (a) 语言按域固定
- **C++（`ament_cmake`）**：性能 / 实时敏感域—— 空中链路（高频 uORB）、感知融合（高频点云 / 图像）、
  地面安全层（硬约束的实时逃逸能力）。理由：低延迟、可控内存、无 GIL、可给实时保证。
- **Python（`ament_python`）**：RL 与工具脚本—— 依赖 PyTorch / Stable-Baselines 生态。
- **语言不构成接口耦合**：跨域通信只经 `agc_msgs`（topic / service / action），与实现语言无关。
- 若某域后续需换语言，须先复核本篇与其性能假设。

### (b) 依赖按类别分层
| 类别 | 规则 |
|---|---|
| ① 消息 / 接口 | 跨域一律经 `agc_msgs`（叶依赖） |
| ② 库链接 | 仅 `agc_control` 共享库允许被空中 / 地面两侧链接同一实现；除此禁止业务库互链 |
| ③ 运行组合 / launch | 编排者以 `exec_depend` 声明所起进程之包，**不**据此链接其实现库 |
| ④ 外部设备 / 第三方 | `px4_msgs` / uXRCE-DDS、Nav2、`ros_gz` / gz vendor |

**保留**：禁止环形依赖；禁止包间业务库互链。取证依据：同版本 Nav2 的 `nav2_bringup` 对仅被 launch
起进程的包（`navigation2` / `nav2_minimal_tb3_sim` / `ros_gz_sim` / `ros_gz_bridge`）用
`<exec_depend>` 而**不** `find_package` 链接其库，对编译期使用的库（`nav2_costmap_2d` / `nav2_util`）
用 `<depend>`—— 即 Nav2 自身已把「链接库」与「起进程」分开声明。

现状（`agc_task` 起各域 + 承载 PX4 驱动 / 干扰注入、跨域合理使用 `nav_msgs` / `geometry_msgs`）在新
规则下**合规**，**不**迁包。

### (c) 内部库的公共性：承诺必须与安装产物一致
对照同版本 Nav2：公共库包 `nav2_util` / `nav2_costmap_2d` **同时** `ament_export_include_directories`
（`nav2_util` 另导出库目标 `nav2_util_core`）**与** `install(DIRECTORY include/ ...)`，导出 == 产物；
而纯 launch / config 包 `nav2_bringup` 的生成 CMake **无任何** `ament_cmake_export_*`。

本仓事实：`agc_air` 的 `agc_air_lib` 为 `STATIC`、仅本包节点 / 测试使用；`agc_air` 只
`install(TARGETS <node>)` + `install(DIRECTORY launch config)`、**不**安装 `include/`，却曾
`ament_export_include_directories(include)` + `ament_export_dependencies` + `$<INSTALL_INTERFACE:include>`
⇒ 生成的 extras 指向**不存在**的 `install/include`（下游 `find_package(agc_air)` 会报 "exports the
include directory … which doesn't exist" 警告），而全仓**无** `find_package(agc_air)` 消费者。

裁定：`agc_air_lib` 为**纯内部实现**，`agc_air` **不**对外承诺公共接口—— 移除上述导出与
`$<INSTALL_INTERFACE:include>`、不安装 `include/`（对齐「内部 / 仅 launch 包零导出」）。共享通用控制
继续以 `agc_control`（`INTERFACE` + 安装 `include/` + `ament_export_*`）为**唯一**公共库家
（见 [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)）。**未**为修 export 新建任何
跨域链接；将来某 helper 若需**真正公共**，须经包边界批准并**同时**安装头文件与正确导出。

### (d) 单一参数化入口与 backend 能力表
`agc_task` 顶层入口**统一为** `main.launch.py`（`backend` ∈ `lightweight` | `full`，默认
`lightweight`）。原 `w6_task_eval.launch.py` / `w6_full.launch.py` **退役**；`skeleton.launch.py`
**保留**为骨架基座（被 `backend:=lightweight` include）。共享配置解析抽取为单一真源
`composition.py`（`load_scene` / `carrier_entry` / `coverage_status` / `compose_params` /
`assertions` / `build_manifest` / `write_temp_params` / `write_manifest`），入口**不复述**解析逻辑；
约束类信息只引用不复述。

`BACKENDS` 能力表为每 backend 声明 `air_link` / `px4` / `target_source` / `required_nodes`（完整展开
节点）/ `supported_axes`；`not_carried` 状态由能力表**派生**（`entry.requires_air_link and not
BACKENDS[backend].air_link`），**不再**逐文件硬编码「轻量栈无空中链路」。

| backend | air_link / px4 | target_source | 支持轴 |
|---|---|---|---|
| `lightweight` | `false` / `false` | `gt_adapter` | 仅 `obstacle` / `outcome` |
| `full` | `true` / `true` | `gt_adapter` ⚠ | 全部 4 轴（含空中链路 4 节点与 `intruder_driver`） |

> ⚠ **2026-11-04 修正**：原表 `full` 行的 `target_source` 写作 `air_fusion`，该节点已退役
> （[ADR-0009](0009-perception-truth-derived-and-vision-path.md#top) (b)），两 backend 现均为 `gt_adapter`。
> 同时 `air_perception` 虽仍在 `full` 链中启动，但 `/agc/air/obs` **无订阅者**，
> 故 `perception` 轴在运行期**不再有区分力**（见 [ADR-0018](0018-acceptance-and-coverage-matrix.md#top) (g)）。

### (e) 入口名 == 报告身份
manifest 记 `launch='main.launch.py'` + 实际 `backend` + `nodes`（完整展开节点名）+ 生效参数（`scene` /
`seed` / `support_status` / `declared_axes` / `expected_terminal` / `expected_reason` / `carriers` /
`effective_params` / `assertions`）；runner / probe 报告的 `launch` 字段同步为 `main.launch.py`。
临时参数 / manifest 文件名含 backend 与唯一性（`w6_<backend>_<scene>_<seed>.yaml` /
`w6_<backend>_manifest_<scene>_<seed>.json`）。

### (f) 就绪依赖替代盲计时
`intruder_driver` 由 **`OnProcessStart(target_action=<入侵者 PX4 ExecuteProcess>)`** 事件驱动（其自身
已有就绪门控：无 odom 先 no-op），**移除** 35 s `TimerAction`。己方 PX4 与入侵者 PX4 的延时**保留**
`TimerAction` 并在代码旁注明理由—— 二者属 **gz 引擎 spawn 时序**（世界 / 入侵者模型于 gz+3 s spawn，
PX4 才具 gz 资源与时钟 / 可 attach 模型），本层**无可达就绪信号**，故保留最小计时。

## 不做什么（边界）
- **不**允许任意包互依赖（无类别区分即退化为无架构）。
- **不**把 `agc_air_lib` 升格为公共库、**不**为修 export 新建跨域链接。
- **不**引入 `bt_navigator` / 行为树；**不**新增第二 ROS 命令者。
- **不**把启动依赖全部改成就绪等待（`launch_ros` **无**内置「等话题 / 服务」wait 动作，PX4 与 gz
  引擎 spawn 属引擎侧时序，强行等待只会引入伪信号）。
- **不**把 `backend` 只作顶层变量而不落能力表（否则覆盖状态退回逐文件硬编码）。
- **不**改冻结 9 消息 / 服务 ABI、唯一执行口语义、硬约束–。

## Considered Options
- **全域 Python / 全域 C++** —— 被否：前者点云处理与安全层实时性 / 吞吐不足，后者 RL 生态在 Python、
  重写代价高。
- **维持单一依赖规则（「唯一公共依赖」）** —— 被否：与真实运行拓扑不符，会误禁必要运行依赖或催生
  隐藏依赖。
- **只按 build / exec / test 三分** —— 被否：不解释「起进程 vs 链接库」的本质差异。
- **保留多入口、仅各自抽共享 helper** —— 被否：仍有第二份入口组装与 `backend` 身份分叉。
- **继续用绝对时间承载 `intruder_driver`** —— 被否：该依赖有**可达就绪信号**，盲计时引入不必要的
  时序脆弱。

## Consequences
- **正面**：语言选型有据可依；依赖方向图区分「链接」与「运行组合」，真实运行依赖不再被隐藏；
  导出承诺与安装产物一致；拓扑成为单一可审查实体，`backend` 贯穿身份与报告，`intruder_driver`
  随实际就绪启动（不早于入侵者 PX4 ≈25 s，与旧 35 s 相比**不晚**）。
- **代价 / 限制**：`lightweight` / `full` 除入口名 / 身份 / 就绪改动外**等价**；gz 引擎 spawn 段
  （12 / 25 s）仍是计时而非就绪信号；引用旧入口名的脚本与核查器（`scripts/run_w6_*.sh` /
  `episode_runner.py` / `w6_r0*_check.py` / `w6_r025_full_probe.py` / `check_full_chain_dual_px4.py`）与 config
  注释须同步更新。
- **未决**：① `intruder_driver` / `jammer` 是否应归入独立「设备域」—— 本轮**不**迁移，后续若迁按
  ③关系调整 `exec_depend`、**不**引入库链接；② gz 引擎 spawn 段若将来由引擎侧提供可达事件，须回归
  就绪依赖；③ `intruder_driver` 事件驱动的实跑时序以整链实跑证据复核。

## 参考
- [ADR-0003](0003-nav2-paradigm-absorption.md#top)（Nav2 范式吸收：模式全覆盖、按命令源裁剪）
- [ADR-0004](0004-ground-control-rl-primary-and-nav2-safety.md#top)（共享控制库 `agc_control`）
- [ADR-0019](0019-lifecycle-and-startup-robustness.md#top)（生命周期可重建与启动健壮性）
- [ADR-0021](0021-w8-gui-headless-equivalence.md#top)（backend 与 GUI / headless 等价）
- 规范真源：[包边界](../conventions/包边界.md)、[目录与命名规范](../conventions/目录与命名规范.md#10-产物分类与生命周期)
