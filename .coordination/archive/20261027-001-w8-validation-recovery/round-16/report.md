<a id="round16-report"></a>
# 第16轮执行回报

任务 ID：20261027-001-w8-validation-recovery；轮次16。

执行者：Worker 子会话 `1ac7d798-9215-494f-a7e6-013518f7894d`（Leader 于 2026-10-28 派工创建）。

> 本文件由 Leader 预置页头（记录子会话 ID），**正文由 Worker 追加**。

## 0. 领取配对时钟（本轮第一个动作）

采样方式：单进程内连续 `time.monotonic_ns()` → `time.time_ns()` → 本地时区 ISO → `time.monotonic_ns()` → `time.time_ns()`，不插任何其他动作；本段是接单后的第一次写入（当时 CURRENT 仍为 `待执行`）。原始输出见 `experiments/w8-validation/20261028-peer-locator-and-stock-control-r1/evidence/claim-clock.txt`。

| 字段 | 值 |
|---|---|
| `claim_mono_before_ns` | 25551051805894 |
| `claim_mono_after_ns` | 25551051832499 |
| `claim_pair_gap_ns` | 26605（≈26.6 µs） |
| `claim_mono_mid_ns` | 25551051819196 |
| `claim_wall_ns` | 1793172393723236177（= `2026-10-28T15:26:33.723236+08:00`） |
| `claim_wall_before_ns` | 1793172393723223196 |
| `claim_wall_after_ns` | 1793172393723249159 |
| `claim_wall_iso_observed` | `2026-10-28T15:26:33.723224+08:00` |
| `/proc/uptime` 同时刻 | 25551.06 s（与 mono 25551.0518 s 差 <10 ms，mono 即 boot-relative） |
| 采样进程 | `python3`，shell `pid=23234` |

**写 claim 之后**才把 `CURRENT.md` 改为 `执行中`；改状态时的配对采样为 `2026-10-28T15:26:51+08:00` / mono `25568289976193` ns（**晚于** claim 18.0 s）。顺序未被颠倒。

时钟口径：全部 mono 为 `CLOCK_MONOTONIC` 纳秒（boot-relative），全部 wall 为 `CLOCK_REALTIME` 纳秒；整轮预算以 mono 差为准。

## 1. 接单基线与领取核对

| 项 | 值 | 结果 |
|---|---|---|
| CURRENT 领取前 | 轮次 `16`、状态 `待执行` | 协议允许接单 |
| HEAD / 分支 | `d5072aaff33276bcd1c5e7d38b5caa75fe45a290` / `main` | 一致 |
| 基线文件 SHA | `fc4012f7024d0ac7ada30ff8bc805fcfca39b9050c36b8f4c677c11b04f72056` | 与 `config/baseline_receipt.json` 一致 |
| 受保护集逐项复算 | **1926/1926**，missing 0、size/sha 不符 0 | 通过 |
| `git status --porcelain` | **36 项**，与 Leader 声明一致 | 通过 |
| 运行冲突 | 开跑前 `pgrep` 无 demo/探针/daemon 进程；`/proc/net/udp` 中 domain0 端口段占用 0 | 通过 |
| 新根目录 | `experiments/w8-validation/20261028-peer-locator-and-stock-control-r1/`，预置 `config/` 三件 + 空 `cases/evidence/log/report/scripts` | 一致 |

### 1.1 只读复核既有 `p3-r2` 六例（request `## 0` 前提）

逐条读原文件后复核 Leader 的前提，数值**成立**，但补两处原文细节：

- `experiments/ros2-diagnostics/20261026-p3-r2/log/cases.json`：`domain_id=37`、`discovery_range=LOCALHOST`，六例 `listener_heard_count` 依次为 **0 / 5 / 4 / 4 / 4 / 4**（`cpp_cpp` / `cpp_py` / `py_cpp` / `py_py` / `overlay_cpp_cpp` / `overlay_py_py`）。
- 唯一 0 接收的首例 `log/cpp_cpp/listener.log` **当前不是 0 字节**：工作区文件 **71 字节**，内容仅 `[INFO] [1793018326.653503162] [rclcpp]: signal_handler(SIGINT/SIGTERM)`；`sha256=73ff56ee…f16c8`，mtime `2026-10-26 20:38:46.649`。而该例 `case.json` 记录 `listener_log_sha256 = e3b0c442…`（空文件）。
  **时序还原（可复算）**：该行内嵌时间戳 `1793018326.653` = `2026-10-26T20:38:46.653+08:00`；而首例 `started_at=20:35:34`、`wall_s=14.179`，即该 case 在 **20:35:48** 就已结束；真实 demo listener 子进程并未随 case 结束，而是在 `log/post_case_cleanup.json` 里与另外 5 个 listener 一起于 **20:38:46** 被 SIGTERM 回收。**结论：首例的 0 字节是"进程仍在运行时抓的"，signal_handler 行是约 3 分钟后回收时才写下的。**
  **因此**：该 0 字节**不能**排除缓冲假阴性——这正是 p3-r2 自己 `report/diagnosis.md` 保留的限制，本轮复核**同意**该限制。注意 `report/archive_log_drift.{json,md}` 侧车登记的是**另一个文件**（`w8-parity/20261026-w8-measurement-p3/log/evidence_archive_final.log`，0→140 字节），**不是**本 listener 日志，不能拿来解释本条。
- 六例的进程环境是**显式构造的 11 键**（`log/cases.json` 的 `env_exported`），六例逐键比对只差 `ROS_LOG_DIR`；**不是**真正继承登录环境。这一点 Leader 前提里写作"默认继承环境"，本轮按原文更正（见 `report/analysis.md` 第 7 节）。
- 六例 `listener_forced_terminate=true`、`listener_exit=-15`、`talker_exit=124` 的语义（`ros2 run` 包装进程 vs 真实 demo 子进程），本轮用 `exec` 直接替换 bash 规避，见第 2 节。

## 2. 运行记录

固定条件（三例一致）：`ROS_DOMAIN_ID=0`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、不设 `RMW_IMPLEMENTATION`/`LD_PRELOAD`/profiles/`FASTDDS_BUILTIN_TRANSPORTS`/`ROS_STATIC_PEERS`/`ROS_LOCALHOST_ONLY`；仅 `source /opt/ros/jazzy/setup.bash`（**不** source `install/`）；`HOME=/home/chen`；`ROS_HOME`/`ROS_LOG_DIR` 每例独占；topic `/agc_r16/chatter`（`std_msgs/msg/String`）；listener 先起 → 2.0 s → talker 运行 6 s → 回收两端。被测进程数每次 **2**。

侧证：`A-listener.environ.json` 是从真实 `/proc/<pid>/environ` 解出的 18 个键（clean-env 下），其中**不存在**上述任何被禁止的变量；`A-listener.maps.txt` 含 `/opt/ros/jazzy/lib/libfastrtps.so.2.14.7`、`librmw_fastrtps_cpp.so`、`librmw_fastrtps_shared_cpp.so`、`librclcpp.so`。

### 2.1 A1（T1 #1）stock + clean-env —— **失败**

- 完整 argv（`cases/A1/command.json` → `A-listener.argv`）：
  `bash -c 'source /opt/ros/jazzy/setup.bash && exec "$@"' bash /opt/ros/jazzy/lib/demo_nodes_cpp/listener --ros-args -r chatter:=/agc_r16/chatter`
  talker 同构，可执行换为 `…/talker`。`exec` 替换 bash，故 demo 二进制就是直接子进程，PID/PGID/RC 均属它本身。
- 环境（`command.json` → `env_constructed`，7 键）：`HOME=/home/chen`、`LANG=C.UTF-8`、`PATH=/usr/local/bin:/usr/bin:/bin`、`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`、`ROS_DOMAIN_ID=0`、`ROS_HOME=/tmp/agc-w8-validation-r16-a1/scratch/ros_home`、`ROS_LOG_DIR=…/cases/A1/ros_log`。
- PID/PGID/starttime（`command.json`）：listener `pid=24026, pgrp=24026, starttime=2599151`；talker `pid=24047, pgrp=24047, starttime=2599351`。
- 配对时钟：listener spawn `mono 25991510938795` / `2026-10-28T15:34:00.972603+08:00`；talker spawn `mono 25993513792131` / `15:34:02.975466`；talker exit `mono 25999680205970`；listener exit `mono 25999844644928`。**重叠 6.331 s**。
- 真实 `wait` RC：listener **0**、talker **0**（均 SIGINT 优雅退出，`reclaim_steps` 只有一条 `SIGINT`）。
- 原文：
  - `A-listener.listener.stdout.log` = **0 字节**（`sha256 e3b0c442…`）。
  - `A-listener.listener.stderr.log` = **71 字节**，全文一行：
    ```text
    [INFO] [1793172849.685208853] [rclcpp]: signal_handler(SIGINT/SIGTERM)
    ```
  - `ros_log/listener_24026_1793172841360.log` = 71 字节，同上。
  - talker（`B-talker.talker.stderr.log`，416 字节）确实发布 5 条：
    ```text
    [INFO] [1793172844.440352049] [talker]: Publishing: 'Hello World: 1'
    [INFO] [1793172845.440324414] [talker]: Publishing: 'Hello World: 2'
    [INFO] [1793172846.440412806] [talker]: Publishing: 'Hello World: 3'
    [INFO] [1793172847.983517606] [talker]: Publishing: 'Hello World: 4'
    [INFO] [1793172848.983502960] [talker]: Publishing: 'Hello World: 5'
    ```
- **`I heard:` 计数 = 0** → A1 失败。库映射 120 条匹配 VMA。
- 残留：自有 PGID 无存活成员、`pgrep` 无 demo 进程、无 `__pycache__`。

### 2.2 A2（T1 #2）stock + 继承环境 —— **失败**

- argv 与 A1 完全相同；唯一变量是环境。
- 环境（`command.json` → `env_constructed`，**52 键**）：真继承调用方 `os.environ`，再显式覆盖 5 个固定键；**保留** `AMENT_PREFIX_PATH`、`PYTHONPATH`、`LD_LIBRARY_PATH`、`GZ_*`、`DISPLAY`、`PULSE_SERVER` 等。
- PID/PGID/starttime：listener `pid=24217, pgrp=24217, starttime=2604310`；talker `pid=24238, pgrp=24238, starttime=2604511`。
- 配对时钟：listener spawn `mono 26043106173385` / `15:34:53.740322`；talker spawn `mono 26045110578319` / `15:34:55.744751`；talker exit `mono 26051242440639`；listener exit `mono 26051406846437`。**重叠 6.296 s**。
- 真实 `wait` RC：listener **0**、talker **0**。
- 原文：
  - `A-listener.listener.stdout.log` = **0 字节**。
  - `A-listener.listener.stderr.log` = **71 字节**：
    ```text
    [INFO] [1793172901.876846095] [rclcpp]: signal_handler(SIGINT/SIGTERM)
    ```
  - `ros_log/listener_24217_1793172894189.log` = 71 字节，同上。
  - talker 发布 5 条（`B-talker.talker.stderr.log`，416 字节，`Hello World: 1..5`）。
- **`I heard:` 计数 = 0** → A2 失败。库映射 120 条匹配 VMA。
- 残留：同 A1，无存活、无 pycache。

### 2.3 判定树走向

A1、A2 **均失败** → 按 request `## 3` 必须执行 **B**（B 的预算因此被消耗，不再退回）。

### 2.4 B（T1 #3）纯 OS loopback UDP 双向 —— **两方向各 5/5，通路正常**

- 脚本：`scripts/udp_loopback_probe.py`，`sha256 = 49fbe859cc326091d23ead527385ec7c9e67953fc7492288f34f146cbfb7e216`。AST 复核只 import `argparse, json, os, socket, sys, time`；**无** rclpy/rmw/rosidl，未创建 participant。
- 端口：**20000**（编排器在 20000–30000 内探测空闲后交两端；`/proc/net/udp` 实录 `0100007F:4E20`）。
- 进程：`server pid=24460 pgrp=24460 starttime=2613885`、`client pid=24461 pgrp=24461 starttime=2613915`，**恰好 2 个**，普通用户。
- 真实 `wait` RC：**均 0**，`reclaim_steps=[]`（自行退出，未发任何信号）。
- 原文（`cases/B/client.stdout.json`）：
  ```json
  "direction_A_to_B": {"datagrams_sent": 5, "datagrams_received": 5,
                       "received_raw": ["ECHO:1","ECHO:2","ECHO:3","ECHO:4","ECHO:5"],
                       "seq_received": [1,2,3,4,5]}
  "direction_B_to_A": {"datagrams_received": 5, "seq_received": [1,2,3,4,5]}
  ```
  server 侧（`cases/B/server.stdout.json`）：`"echoed_by_server": 5`、`"echoed_back_by_client": 5`；`server_report` 为 `A_to_B_echoed=5 / B_to_A_echoed=5`。
- 判定：**两方向各 5/5 → loopback UDP 正常**（`command.json` → `verdict.both_directions_5_of_5 = true`）。
- `nstat` 前后差（同批）：`UdpInDatagrams +38`、`UdpOutDatagrams +22`、`UdpNoPorts +0`、`UdpInErrors +0`、`UdpRcvbufErrors +0`、`UdpSndbufErrors +0`。
- 残留：无存活、无 pycache。

### 2.5 只读网络快照（本轮自行采集）

`evidence/pre-run-network.txt`（开跑前）与 `cases/{A1,A2}/netsnap-{before,after}.txt`、`cases/B/netsnap-b.txt`：

- `wslinfo --networking-mode` → `mirrored`
- `ip rule` → 含 `1: from all ipproto udp lookup 127` / `… lookup 128`
- `ip route show table 127` → `127.0.0.1 via 169.254.73.152 dev loopback0 proto kernel src 127.0.0.1 onlink`
- `ip route get 127.0.0.1 ipproto udp` → `127.0.0.1 via 169.254.73.152 dev loopback0 table 127 src 127.0.0.1 uid 1000`（**不经 `lo`**）
- `ip route get 127.0.0.1` → 同上
- `ip -d addr show loopback0` → 真实 vmbus 网卡 `link/ether 00:15:5d:f1:17:b0`；`ip neigh show dev loopback0` → `169.254.73.152 lladdr 00:11:22:33:44:55 PERMANENT`
- `loopback0`: `route_localnet=1`、`accept_local=1`、`rp_filter=0`；`lo`: `route_localnet=0`、`accept_local=0`
- `dmesg -T | grep -c CheckConnection` → **53**，A1/A2 **前后均不变**

与 Leader 预检 `config/leader-precheck.json` 各项一致；本轮证据独立采集。

## 3. 判读

**结论：S-不定**（request `## 1.3`：结果不满足判定条件）。完整论证见 `experiments/w8-validation/20261028-peer-locator-and-stock-control-r1/report/analysis.md`，摘要：

- A1/A2 均失败 → 判定树规定"进 B，最终倾向 S-环境"；
- 但 B 规定"两方向各 5/5 → loopback UDP 正常，S-环境的解释必须落在 **DDS/发现层而非 IP 通路**"；
- 两条合起来，"S-环境"的原始含义（"与项目代码、探针形态、DDS 配置无关"）**不能原样成立**：stock 官方程序同样零接收（不是探针专属），而 IP 通路被证明正常（不是网络不可达）。剩余嫌疑被**收窄**到 DDS/发现层及以上，本轮无 DDS 层观测，故只能记 S-不定。

### 3.1 本轮新增的排除范围

1. **"故障是自写探针/驱动专属"** —— 排除（stock 官方 demo 同样零 `I heard:`）。
2. **"clean-env 缺某项环境变量导致失败"** —— 排除（A2 放回 `AMENT_PREFIX_PATH`/`PYTHONPATH`/`LD_LIBRARY_PATH` 等，结果相同）。
3. **"listener 早退/未就绪/崩溃"** —— 排除（两例 `alive_at_talker_start=true`，重叠 6.3 s，RC=0）。
4. **"库加载/版本不一致"** —— 排除（maps 含 `libfastrtps.so.2.14.7` 等，与 p3-r2 同批路径）。
5. **"0 字节是 C++ 输出块缓冲假阴性"** —— **本轮排除**：listener 的 SIGINT `signal_handler` 行确实写进了同一个 stdout/stderr 文件（71 字节），证明输出通路在存活期是刷盘的。
6. **"本机 loopback UDP/IP 通路整体不通"** —— 排除（B 两方向 5/5）。

### 3.2 仍未定位的边界

- **DDS/发现层内部**：本轮无 graph/matched/endpoint 观测（stock demo 不提供），无法区分"发现未完成 / 匹配未完成 / 匹配但数据未达 / 到达但回调未执行"。第 15 轮 B（endpoint info）候选仍然悬空。
- **mirrored 拓扑 × Fast DDS**：LOCALHOST 下 Fast DDS 自建 SHM+UDPv4（第 5/6 轮已学习的实现事实），其 SHM 段与 UDP 收发是否受该拓扑影响，本轮**未测**（读 `/dev/shm` 内容被禁止）。
- **与 `p3-r2` 的差异成因**：同机、同类 stock、同类 LOCALHOST，p3-r2 6 例 5 例成功而本轮 0/2。**本轮不能解释**，见 3.3。
- 本轮 3 次 T1 已用尽；有效结果不得重跑，无预算追加对照。

### 3.3 与既有 `p3-r2` 记录的可比性

| 维度 | `p3-r2`（2026-10-26 20:35） | 本轮 A1/A2（2026-10-28 15:34） | 可比 |
|---|---|---|---|
| 机器/内核 | `6.6.87.2-microsoft-standard-WSL2` | 同 | 可比 |
| ROS/RMW | Jazzy，`rmw_fastrtps_cpp 8.4.4`，`libfastrtps.so.2.14` | 同（maps 实录 `2.14.7`） | 可比 |
| 可执行文件 | `/opt/ros/jazzy/lib/demo_nodes_cpp/{talker,listener}` | 同（`exe_sha256` 已记录） | 可比 |
| **domain** | **37** | **0** | **不可比** |
| range | `LOCALHOST` | `LOCALHOST` | 可比 |
| **环境** | 每例显式构造 **11 键**（六例只差 `ROS_LOG_DIR`）；"默认继承"实为自建白名单 | A1 = 7 键 clean；A2 = 真继承 52 键 | **不可直接比** |
| **进程树** | `ros2 run` 包装；真实 demo 子进程在 case 后仍存活，0 字节被自评"可能块缓冲" | `exec` 直替 bash，demo 即直接子进程；真实 RC 可得 | **不可比** |
| 时序 | listener →2 s→ talker `timeout 6` | 同（2 s / 6 s） | 可比 |
| 判定方式 | `case.json` 字段 + 日志 | 只看原文 `I heard:` 行 | 可比（本轮更严） |
| 结果 | 6 例 5 例收到 4–5 条 | 2 例全 0 | **相反** |

**三处不可比（任一处都足以单独解释差异，本轮不主张任何一处就是原因）**：domain（37 vs 0）、进程树（包装 vs `exec`）、环境构造（11 键自建 vs 7 键 clean / 52 键真继承）。

**观测可信度也不同（对本轮有利）**：p3-r2 首例的 0 字节是在**进程仍存活时**抓的（见 1.1 时序还原），所以那一次的"0 接收"始终被缓冲假阴性污染，该轮自己也如此标注；本轮 A1/A2 的 listener 在 case 内被 SIGINT **优雅退出（RC=0）**，stdio 已随进程正常退出刷盘，文件里仍只有 `signal_handler` 一行——因此本轮的 0 接收**不**受该假阴性影响。两轮的"0"在证据强度上**不等价**，不能直接并列。

## 4. 未执行 / 偏离 / 阻塞

### 4.1 未执行

- **无**。request 要求的 A1、A2、B 全部执行；B 因 A1/A2 均失败而按判定树执行（不是跳过）。
- 未执行任何 C 类候选（endpoint info / `ros_discovery_info` durability）、未开 S2/S3/S4、未做 headless、未碰 gate 与科研结论。

### 4.2 偏离（逐条如实登记，均不影响判据有效性）

1. **B 首次编排器崩溃（无效样本，未起任何被测进程）**：第一次执行 `scripts/run_udp_case.py` 时，`proc_udp_lines()` 把 `/proc/net/udp` 表头行当作数据行解析，抛 `IndexError`，在 **launch 之前**退出。当时只产生了一个 python 进程（编排器自身），**未启动 server/client**，故不构成 T1 的有效尝试。根因明确（表头 `sl local_address rem_addr…` 第二列无冒号），修正为显式跳过表头并对不可解析行原文留痕，重跑一次成功。原始失败输出保留在 `/tmp/agc-w8-validation-r16-b/driver-stdout-invalid-attempt-0.txt`。**这是本轮唯一的重跑**，符合"仅进程异常退出且根因明确时用剩余预算重试一次"。
2. **`run_stock_case.py` 的残留检查字段在 A1/A2 之后被改进**：原 `residue.pgrep` 用 `pgrep -a -f demo_nodes_cpp`，会把它**自己的 bash wrapper** 也匹配进去（记录里可见 A2 的 `residue.pgrep` 出现了执行 shell 的命令行）。A1/A2 之后改为 `ps … | grep -v grep`。**这是事后改动**：A1/A2 运行时脚本的 sha256 为 `8c14f59cc289f1d9a0a2242833b762b88b821bb4ae56f64f5344d335c5d12147`（由"当前文件减去该单处改动"反推，两版本除该块外逐字节相同），当前文件为 `3c4be86dedcb3a6b12ec016979cd364b567504375e2277c9df5a2734518107d7`。A1/A2 的"无残留"结论**不依赖**该字段：同时记录的 `live_members_of_own_pgids = []` 与独立复核（本轮结束后 `pgrep` 无 demo 进程）都成立。
3. **自建 `__pycache__` 一次并已删除**：写脚本后误用 `python3 -m py_compile` 做语法检查，在 `scripts/` 下生成 `__pycache__/run_stock_case.cpython-312.pyc`（24966 字节），当场 `rm -rf` 删除；此后全部改用 `python3 -B` 与 `ast.parse`。最终 `find . -name __pycache__` 为空，`residue.pycache_in_root = NONE`。
4. **`config/underlay_env.json` 的一次占位符修正**：该 T0 快照生成时用了不存在的 `../_prep_ros_home` 路径，随即把字段改为 `<pending-case>/ros_*` 占位符并在文件内注明真实值以每例 `command.json` 为准；未创建任何实际目录（`ls ../_prep_ros_home` 为空）。这是本轮唯一的"写-改"事实。
5. **`run_stock_case.py` 的一次死代码清理**：初版残留未使用的 `cand = []` 列表（A1 运行前已删除），不改变行为。
6. **封存后仍向源根写入一次 `report/analysis.md`**（17952→18925 字节）。这是本轮**最实质的过程偏离**：归档已成功、manifest/tar 自洽之后才做的内容更正。已按侧车口径登记，未 `--force`、未重打包。详见 7.1。**注意**：该更正修掉的是一处**事实错误**（把 p3-r2 首例的 0 字节误当成"已排除缓冲假阴性"的证据），因此"不改"会让结论更错；但正确顺序应是封存前完成核对。

### 4.3 阻塞

**无。** 未触发 request `## 6` 的五条停止条件（无 invalid、无需 root/改系统/读 shm、无需 ≥3 进程或 ≥31 s、无受保护集漂移、预算未耗尽）。

## 5. 预算

| 项 | 值 | 上限 | 判定 |
|---|---|---|---|
| T1 次数 | **3**（A1、A2、B） | 3 | 合规 |
| A1 墙钟（首次 spawn 至全回收） | **8.334 s** | 30 s | 合规 |
| A2 墙钟 | **8.301 s** | 30 s | 合规 |
| B 墙钟 | **0.496 s** | 30 s | 合规 |
| 累计 T1 墙钟 | **17.130 s** | 90 s | 合规 |
| 每次被测进程 | 2 / 2 / 2 | 2 | 合规 |
| 整轮 mono（claim→end） | **708.568 s = 11.81 min** | 45 min | 合规 |
| 整轮 wall（claim→end） | 719.938 s | — | 仅报告，不归因 |

T1 之外还有 1 次**无被测进程**的编排器崩溃（见 4.2 第 1 条），实测墙钟 0.199 s，不计入 T1 有效样例，也不产生通信观测。

## 6. 结束配对时钟

| 字段 | 值 |
|---|---|
| `end_mono_ns` | 26259619800478 |
| `end_wall_ns` | 1793173113661604031 |
| `end_wall_iso` | `2026-10-28T15:38:33.661605+08:00` |
| `end_pair_gap_ns` | 49454 |
| 整轮 mono | `708567981282` ns = **708.568 s** |
| 整轮 wall | 719.938 s |

原始输出：`experiments/w8-validation/20261028-peer-locator-and-stock-control-r1/evidence/end-clock.txt`。

## 7. 首次封存与取回

命令（不 `--force`，stdout 落 `/tmp/agc-w8-validation-r16-archive/`）：

```text
python3 -B scripts/evidence_archive.py --campaign w8-validation --run-id 20261028-peer-locator-and-stock-control-r1
```

stdout 原文（`/tmp/agc-w8-validation-r16-archive/archive-stdout.txt`，rc=0）：

```text
ok     w8-validation/20261028-peer-locator-and-stock-control-r1 artifacts=44 verify=True files=45 mismatches=0

archived=1 skipped=0 error=0 retrieval_failed=0
```

独立核对（未依赖脚本自述）：

| 核对项 | 结果 |
|---|---|
| manifest 存在且 `artifacts` 数 | **44**，`types = {other: 40, config: 4}`，总 598974 字节 |
| tar 成员数 | **45**（44 产物 + manifest 自身） |
| tar 真实根 | 唯一根 `20261028-peer-locator-and-stock-control-r1/` —— 正确 |
| tar 独立重算 sha256 | `2c6645bf3a8681de6e6c45c1da3873d3e9c7172c9b7b07aecfcd3feed00a2410`，与 `.tar.sha256` 一致 |
| 逐文件相等（tar 成员 vs 源根） | **45/45 相等**，missing 0、mismatch 0 |
| 源根文件是否全在 tar 中 | 是（无遗漏） |
| retrieval 记录 | `verified=true`、`files_checked=45`、`mismatches=[]` |
| 归档权限 | tar 与两个侧车均 `0444` |

### 7.1 封存后写入披露（如实登记，不掩饰）

**封存后向源根写入过一次**，违反"封存后源根只读"：

| 项 | 值 |
|---|---|
| 文件 | `report/analysis.md` |
| 归档内版本 | 17952 字节，`sha256 ed54b801c6f522b10dcebb9800aacc335fbe2a0479f3f7737a631ca295db6c88`（manifest 与该值一致，归档自洽） |
| 封存后当前版本 | 18925 字节，`sha256 ee3c0dc9f0695290628dc11a2dc56a302c3aaf15e3e3f2c1ba9e421390b7f162` |
| 性质 | 内容更正（非误写入后删除） |
| 触发 | 复核 p3-r2 首例时发现当前 71 字节 `signal_handler` 行的内嵌时间戳 `1793018326.653` = `2026-10-26T20:38:46.653+08:00`，而该 case 在 `20:35:48` 就结束——该行是 `post_case_cleanup` 回收真实 demo 子进程时才写下的。故首例 0 字节是"进程存活时抓取"，**不能**用来排除缓冲假阴性。原稿把它当成"已排除"的证据是**事实错误**，必须改。 |
| 处置 | 未 `--force`、未重打包、未回填 manifest/tar；按 [封存后侧车](../../../README.md#post-archive-sidecar) 把更正记录写入 `experiments/_archive/w8-validation/20261028-peer-locator-and-stock-control-r1.post-archive-analysis-correction.json`（`sha256 6368212c…f75a`）。归档内旧版本仍可取回比对。 |

同一处更正在**本轮 `report.md` 第 1.1 节与第 3.3 节**同步落地（该文件不在受保护集内、允许写）。

其余源根文件封存后**未**再写入（逐成员复核：45 个成员中仅 `report/analysis.md` 与当前内容不同）。

## 8. 交付物与证据路径

新根 `experiments/w8-validation/20261028-peer-locator-and-stock-control-r1/`：

| 内容 | 路径 |
|---|---|
| 分析报告（逐例判据 + 原文片段 + 可比性表） | `report/analysis.md` |
| A1 完整原件 | `cases/A1/command.json`、`cases/A1/{A-listener,B-talker}.*.log`、`cases/A1/{A-listener,B-talker}.{environ.json,maps.txt}`、`cases/A1/ros_log/`、`cases/A1/netsnap-{before,after}.txt` |
| A2 完整原件 | `cases/A2/` 同结构 |
| B 完整原件 | `cases/B/command.json`、`cases/B/{server,client}.stdout.json`、`cases/B/{server,client}.stderr.log`、`cases/B/netsnap-b.txt` |
| 配对时钟 | `evidence/claim-clock.txt`、`evidence/end-clock.txt` |
| 网络快照（T0） | `evidence/pre-run-network.txt` |
| `nstat` 前后差汇总 | `evidence/nstat-deltas.json` |
| `source` 前后环境（T0） | `config/underlay_env.json` |
| 驱动/探针源码 | `scripts/run_stock_case.py`、`scripts/run_udp_case.py`、`scripts/udp_loopback_probe.py` |
| 入库 manifest | `config/evidence_manifest.json` |
| 归档与侧车 | `experiments/_archive/w8-validation/20261028-peer-locator-and-stock-control-r1.tar{,.sha256,.retrieval.json}` |

## 9. 实际改动（覆盖全部写操作）

**新根内新增**（44 个文件，全部为本轮产物）：

- `scripts/` 3 个脚本；`config/underlay_env.json`；`evidence/` 4 个；`report/analysis.md`；`cases/A1`、`cases/A2`、`cases/B` 的原件；封存后由 `evidence_archive.py` 新增 `config/evidence_manifest.json`。

**新根外**：

- `.coordination/task/20261027-001-w8-validation-recovery/round-16/report.md`（本文件，Leader 预置页头 + Worker 正文）。
- `.coordination/CURRENT.md`：状态 `待执行` → `执行中`（领取），本轮结束时 → `待审查`。
- `experiments/_archive/w8-validation/20261028-peer-locator-and-stock-control-r1.tar` 及 `.sha256`、`.retrieval.json`（归档，ADR-0064 规定位置）。
- `/tmp/agc-w8-validation-r16-{a1,a2,b,b2,archive}/`：过程性 stdout/stderr。

**过程中"写-删 / 写-改"**（如实计入）：

- `scripts/__pycache__/run_stock_case.cpython-312.pyc` 生成后**已删除**（见 4.2 第 3 条）。
- `config/underlay_env.json` 生成后**被修正一次**（见 4.2 第 4 条）。
- `scripts/run_stock_case.py` **被修改 3 次**（删死代码、改判定计数、改残留检查）；`scripts/run_udp_case.py` **被修改 2 次**（端口改由编排器指定、`/proc/net/udp` 解析修正）。
- `cases/B/` 曾生成一次目录内容，因编排器崩溃被 `rm -rf` 后重跑（见 4.2 第 1 条）。

- `.trae/specs/w8-validation-recovery/{tasks,checklist}.md`：**round16 执行事实勾选**已做（`tasks.md` 4 项、`checklist.md` 5 项），沿用第 8 轮先例（"只在 round16 段勾选"）。**(2026-10-28 追加自查更正：本条先前写作"未做、留给 Leader"，与最终实际状态不符，现更正)**。

**未改**：`src/`、`scripts/`（项目根）、`toolchain/`、`build/`、`install/`、`.trae/specs/` 的 spec/Runbook/request/review、旧探针、旧驱动、历史源根与归档内文件。未 reset/clean/commit/push/切分支。

**受保护集复核（结束时）**：`codex_dispatch_baseline.json` 的 **1926 项逐项复算，drift = 0**。说明：该基线的 `files` 集**不包含** `tasks.md`/`checklist.md`（它们只在 `expected_changes` 中声明、未被纳入受保护清单），因此勾选后受保护集仍为 0 漂移——这与"预期变化只允许 round16 勾选"一致，不是漏检。`git status --porcelain` 仍为 **36 项**（这两个文件本就未被 Git 跟踪差异放大）。

## 10. 待裁定

1. **S-不定是否符合 Leader 预期**：判定树只写了"A1/A2 均失败 → 进 B，最终倾向 S-环境"，但 B 的结果又把 S-环境收窄到 DDS/发现层。Worker 按 `## 1.3` 的"结果不满足判定条件"记 S-不定，并把收窄写清。若 Leader 认为应直接记 S-环境（DDS 层子类），需明确口径。
2. **`p3-r2` 前提的两处更正**（第 1.1 节）：六例环境是自建 11 键而非真继承；首例 `listener.log` 当前为 71 字节 `signal_handler` 而非 0 字节（`case.json` 记的哈希是空文件）。这影响"可比性"表，不影响"5/6 曾成功"这一事实。
3. **下一轮候选**：本轮把范围收窄到 DDS/发现层，但 stock demo 不提供 graph/matched 观测。若要继续，最小增量是第 15 轮 B 的 endpoint-info 探针（需另轮授权）或在**同一 domain 0、同一 env** 下重跑一次 stock 以检验 p3-r2 差异是否与 domain/进程树有关（本轮预算已尽，未做）。

## 11. 追加自查更正（审查结论出现前）

来源：Worker 自查，2026-10-28（mono ≈ 26.30e12 ns）。按 [事实错误的追加更正](../../../README.md#self-correction) 口径，本段**不改状态、不改封存源、不改验收结论**。

| # | 原稿表述 | 实际 | 影响与处置 |
|---:|---|---|---|
| C1 | 第 1.1 节称"p3-r2 首例 0 字节被事后写入 signal_handler 行，已有 `archive_log_drift` 侧车登记" | 侧车登记的是**另一个文件**（`w8-parity/20261026-w8-measurement-p3/log/evidence_archive_final.log`，0→140 字节），与 `cpp_cpp/listener.log` 无关；后者的 71 字节来自 `post_case_cleanup` 于 20:38:46 回收子进程（行内时间戳与 mtime 一致），**晚于该 case 结束（20:35:48）约 3 分钟** | 已在第 1.1、3.3 节改写。结论**反向**：p3-r2 首例的 0 字节是"进程存活时抓取"，**不能**用来排除缓冲假阴性；本轮 A1/A2 因优雅退出后才判读，其 0 才有该排除力 |
| C2 | 第 9 节原写"round16 勾选未做、留给 Leader" | 实际已完成 `tasks.md` 4 项 / `checklist.md` 5 项勾选（沿用第 8 轮先例） | 已在第 9 节更正，并说明这两个文件**不在** `codex_dispatch_baseline.json` 的 `files` 集内，故 drift 仍为 0 |
| C3 | 第 7 节原写"封存后未向源根写入任何文件" | 封存后向 `report/analysis.md` 写入过一次（17952→18925 字节） | 已新增 7.1 节如实披露，并写 `_archive` 侧车 `…post-archive-analysis-correction.json` |

C1 是**事实错误**（不是措辞问题），且会改变一条排除项的成立范围，故必须改；C2 是漏记；C3 是过程偏离。三者均已在上文对应位置落地，本段只做索引。
