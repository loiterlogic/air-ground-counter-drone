<a id="top"></a>
# DDS 发现范围与传输：按 `lo` 能力探测，禁止写死 `LOCALHOST`

## Status

accepted（2026-11-04）

## 背景

项目原先有一条"环境铁律"：`ROS_AUTOMATIC_DISCOVERY_RANGE` 必须设成 `LOCALHOST`
（理由：本机 `SUBNET` + WSL2 `eth3` 上行会"间歇性全失效"）。该规则被写进了
排障速查、入口脚本与多处测试。

2026-11-04 追查 `test_run_logger_mission_fco` 的间歇失败（症状：`publisher matches` 全 0、
`mission_count == 0`）时，确认**这条铁律本身失效**，且它隐含了一个从未写出的前提。

### 实测事实（同一台机、`rmw_fastrtps_cpp`）

1. **`lo` 没有组播能力**：`/sys/class/net/lo/flags == 0x9`，只有 `UP|LOOPBACK`，
   无 `IFF_MULTICAST(0x1000)`。`ip link set lo multicast on` 回报 `Operation not permitted`。
2. **成员资格规则**（UDP 组播逐层对照）：凭 `0.0.0.0`（任意接口，= Fast DDS 内置发现的用法）
   加入的组套接字**收不到 `lo` 上的任何组播包**；显式按 `lo` 加入才能收到。`eth3` 正常。
3. **矩阵**（两进程 pub/sub 对拍，数字 = 订阅端收到条数）：

   | 发现范围 | 传输 | 送达 |
   |---|---|---|
   | `SUBNET` | 默认（UDPv4+SHM） | **0**（发现能配对，用户数据走 UDP 被丢） |
   | `SUBNET` | 仅 `SHM` | **238 ✅** |
   | `SUBNET` | 仅 `UDPv4` | 0 |
   | `LOCALHOST` | `SHM` / `UDPv4` / 默认 | **0 / 0 / 0** |

4. **`LOCALHOST` 是"按拓扑不可靠"，不是"恒废"**（这一点曾误导排查）：1 发布 ↔ 1 订阅时
   稳定零送达；1 订阅 ↔ N≥2 发布时偶通（实测 2/2、5–6/6）。多 participant 并存时，
   被丢弃的组播通告会被其它 participant 的侧信道补上。**这正是历史上"忽好忽坏"的来源**，
   也解释了为什么用多进程脚本探活会得到"能通"的假阳性。

## 决策

<a id="single-source"></a>
### (a) 单一真源

DDS 发现范围与传输的**唯一决定点**是 `scripts/demo/dds_transport.py`。
禁止在任何其它位置写死 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`。

- `lo` 有 `IFF_MULTICAST` → `LOCALHOST` + 默认传输（原生 Linux 行为**不变**）；
- `lo` 无组播 → `SUBNET` + `FASTDDS_BUILTIN_TRANSPORTS=SHM`（本机唯一稳定组合）；
- 未知（读不到 flags）→ 按"无组播"处理，不得假设有。

显式覆盖：`AGC_DDS_TRANSPORT_POLICY=auto|localhost-udp|subnet-shm|subnet-udp`。

已接入：`run_demo.sh`、`scripts/demo/start.py`、`scripts/demo/doctor.py`、
`scripts/episode_runner.py`、`scripts/research/w7c_worker_run.py`、
`tests/run_smoke.py`、`tests/w7b_fire_control_lifecycle_check.py`、
`src/agc_task/test/test_run_logger_mission_fco.py`。

<a id="no-trial"></a>
### (b) 判据不得靠"试发一条"

选择器**禁止**引入 `rclpy` / `socket` / `subprocess` / `publish`：任何"探活试探"
在多 participant 拓扑下都可能给出假阳性（已实测）。只允许读可核验的内核标志。
由 `scripts/tests/test_dds_transport.py` 静态断言守护。

<a id="guard"></a>
### (c) 用会失败的测试防复发，不用文档

新增 `tests/w6_dds_contract_check.py::case_e_no_hardcoded_localhost`：扫描全仓活跃代码
（`.py/.sh/.bash/.xml/.yaml/.yml`），发现写死即 FAIL；并已加入默认冒烟组 `dds`，
即 `./run_demo.sh test` 每次都跑。

豁免范围仅：`scripts/archive/`（历史事实不改写）、`experiments/`（运行证据）、
`build/`/`install/`、策略表自身与其契约测试。断言语境与反引号文档引用不误报。

> **理由**：本项目已为同一问题两次付出整轮定位代价，且两次都留下了"文档说明"。
> 文档劝告没有挡住复发，因此改为机制拦截。

<a id="worker"></a>
### (d) worker 隔离与连通性解耦

ADR-0024 要求 W7-c worker **禁 SHM**（`/dev/shm` 不随 netns 隔离）。该要求被误实现成
"同时写死 `LOCALHOST`"。现修正：worker 只覆盖 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`，
**发现范围沿用探测结果**。隔离要求成立，且不再在无 `lo` 组播的机器上整链零送达。

## 不做什么

- **不**改 `lo` 的组播标志：本内核回报 `Operation not permitted`，属宿主/内核层，不是项目能修的。
- **不**把 `SHM` 当通用修复：它只在**同主机**多进程间有效，跨机器仍须 UDP。
- **不**用 `pytest.skip` 绕过受影响的测试：其断言本身正确，失败源于本节环境缺陷。
- **不**把 `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` 当本机修复：实测零送达。
- **不**在本次引入"UDP 绑定具体网卡"的 XML profile 方案：已验证可行（`SUBNET` + 绑定 `eth3`
  的 UDP 白名单，1:1 拓扑 3/3 通过、且不产生 SHM 段），但它要求精确配置
  （`useBuiltinTransports=false`，改回 `true` 即失败），且绑定 DHCP 地址、多网卡选路规则未定。
  留作将来需要**跨机器 UDP** 时的候选，届时新增策略 `nic-udp`。

## Consequences

- **原生 Linux（`lo` 有组播）行为完全不变**——策略探测会选回 `LOCALHOST` + 默认传输。
- 本机（WSL2）从"按文档做必挂"变为"默认就能跑"：`agc_task` ctest 6/6、
  全量 pytest 414 passed、该测试连跑 8/8。
- **`SHM` 选中的代价**：本机默认失去跨机器 UDP 能力。跨机器场景需显式覆盖或用将来的 `nic-udp`。
- 排障速查 §0 与环境铁律①相应修订；判据与实测矩阵见
  [整链排障速查 2d-2](../conventions/整链排障速查.md#dds-transport)。
- 排查纪律：**判定 DDS 通不通必须用与目标同构的 1:1 拓扑**，多进程探活会骗人。
