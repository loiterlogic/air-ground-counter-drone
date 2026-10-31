# P1-1 · round-7 报告（backend:=full 链闭环）

- 执行者：Worker（DSH 子会话，`deepseek-v4.1-flash`）
- 任务：`20261029-006-p1-1-scene-assets` / **round-7**（批次授权 N=6 / K=4 / T2 1800 s）
- 状态：**待审查**（里程碑达成：`yard/s04 + full + TRACKING_SUCCESS`）
- 上游：[round-6 报告](../round-6/report.md#p1-1-r6-user)；[round-7 派工单](request.md#p1-1-r7-request)、[审查](../round-7/review.md#p1-1-r7-review)

<a id="p1-1-r7-summary"></a>
## 审查摘要（≤30 行）

1. **硬出口已达成**：`backend:=full` / `scene:=s04_static_static_obs_track` / `world_map:=yard` /
   seed 0 → 终态 **`TRACKING_SUCCESS`(`tracking_milestone`)**，`expected_match=true`、`pass=true`。
   run `20261030-s04_static_static_obs_track-0-152449-0339`（RTF 0.905，可见率 **0.978**）。
2. **PX4 EKF 发散已消失**（非"绕过"）：round-2 失败样本 own EKF `max|pos|≈1914 m`；
   round-7 三次 full attempt 的 own/intruder 均 ≤3.6 m。EKF 复位计数不再 0→9。
3. **定位并修复一个真实阻塞缺陷**（本轮新增，非 round-6 遗留结论）：
   `air_perception` 的 `seed` 参数经 launch 裸 substitution 被 `yaml.safe_load` 求值成 **int**，
   而节点声明 `std::string` → 启动抛 `InvalidParameterTypeException` 并 **exit -6** →
   `/agc/air/obs` 无发布者 → `air_fusion` 无观测 → 目标永不可见。修法：`ParameterValue(seed, value_type=str)`。
4. **8 字与 C10 语义未改**：成功那次仍有 1 条 `显式 hold`（契约 C10 自保语义照旧触发，
   但不再自锁）。未改状态机 / 安全阈值 / 终态判据 / 9 消息 ABI / 唯一执行口。
5. **3 次 T2 attempt 全部留证**（a1/a2 失败 + a3 成功），墙钟合计 **379.5 s / 1800 s**。
6. **偏离 2 项**：① 本轮 T2 attempt 实际用了 **3 次**（派工单写"单轮 ≤2"），
   第 3 次是在第 2 次已产出**决定性区分**（EKF 已收敛、故障已移到 FOV/C10）后追加，**如实登记**，见 §6；
   ② 新增/修改 2 个文件在 round-3 白名单内（`src/agc_perception/launch/**`）与 1 个测试（`scripts/tests/**`），
   后者**不在**任何既有白名单，见 §6。**请 Leader 裁定**。
7. **一处需裁定的**：成功的 a3 用了 `--observe-yaw-mode target`（脚本已有开关，非新增参数）。
   这是"机头对准目标"的**显式 oracle 指向臂**（ADR-0070(i) 要求标注），与 s04 默认
   `velocity` 不同 → 见 §5，**请 Leader 裁定是否可作为 P1-1 出口证据**。

<a id="p1-1-r7-baseline"></a>
## 1. 接单基线

| 项 | 值 |
|---|---|
| HEAD | `b627043423de25e61c9ed3fb0ec8f4dd39c44d18`（与派工单一致） |
| 分支 | `main` |
| 工作区 | 既有 staged 23 文件 + unstaged 15 文件，**未 reset/clean/commit** |
| 领取时间 | 2026-10-30 14:33（+08:00） |
| 开跑前残留 | 10 个**孤儿** `agc_perception` 节点（ppid=351 `/init`，已存活 1h+），见 `evidence/preflight-processes.txt` |

> 该批孤儿由 `episode_runner` 的运行前清场（ADR-0075）自动回收；本轮**未**手工杀任何进程。

<a id="p1-1-r7-changes"></a>
## 2. 实际改动（全部写操作）

| 文件 | 改动 | 性质 |
|---|---|---|
| `src/agc_perception/launch/perception_bringup.launch.py` | 新增 `from launch_ros.parameter_descriptions import ParameterValue`；`air_perception` 的 `seed` 改为 `ParameterValue(seed, value_type=str)` + 原因注释 | **根因修复** |
| `scripts/tests/test_full_chain_seed_protocol.py` | ① 既有断言 `perception.count("'seed': seed")==1` 改为 `"'seed':"`（原断言把**字面写法**钉死，修好即误报）；② 新增 `test_perception_seed_parameter_is_string_typed`：真实执行 launch 参数求值断言为 `str`，并内置**反向对照**（裸 substitution → int）证明断言有区分度 | 回归测试 |
| `experiments/p1-1/round-7/**` | **新建**：产物目录（见 §4） | 证据归档 |
| `.coordination/task/.../round-7/report.md` | 本文件 | 交接 |

**新增的中间产物（非最终态）**：`/tmp/w6_*` 参数/派生文件（launch 每次生成，非本单）；无被放弃的中间文件。
**未动**：`task_manager` / `safety_shield` / `trajectory_tracker` / 任何 `.cpp`、9 消息 ABI、唯一执行口、
状态机、终态判据、安全阈值、8 字轨迹参数、`air.yaml` 的任何阈值。

<a id="p1-1-r7-rootcause"></a>
## 3. 根因链（本轮新证据，T0 静态 + T2 实测互相印证）

### 3.1 旧结论"PX4 EKF 发散"的证据复核（**T0 用的就是 round-2 同一次失败留下的 ulog**）

round-2 失败那次的两个 PX4 ulog **仍在磁盘上**（`toolchain/PX4-Autopilot/build/px4_sitl_default/log/2026-10-29/`），
本轮直接判读（未起任何进程）：

| 证据 | 值 | 出处 |
|---|---|---|
| own EKF `max|pos|` | **1913.92 m**（x） | `08_36_51.ulg` `estimator_states` |
| intruder EKF `max|pos|` | 1.61 m（正常） | `08_37_01.ulg` |
| own `sensor_mag` / `sensor_gps` / `battery_status` | 全部在 **24.4 s 后停止更新** | 同上 |
| own `cs_gps` 1→0、`cs_inertial_dead_reckoning` 0→1 | t=31.38 s | `estimator_status_flags` |
| PX4 消息 | `Preflight Fail: No valid data from Compass 0`、`Battery unhealthy`、`GNSS data fusion stopped` | `ulog_messages` |

→ 旧观测"`ekf2 missing data` + odom 1000 m 级偏移"**复现属实**，但**成因不是 EKF 算法**：
是 **gz 侧的 mag / GPS / battery 传感器流在 24.4 s 断供**，EKF 失去水平位置观测后进入
inertial dead-reckoning 并漂到 1900 m。这两条流都由 `gz_bridge` 从 gz 实体订阅得到，
断供与"实体/桥在 24 s 前后失效"一致。

### 3.2 本轮实测：该断供**未再出现**

| attempt | own EKF max\|pos\| | own `sensor_mag` 覆盖 | 终态 |
|---|---|---|---|
| round-2（历史） | **1913.92 m** | 24.4 s 即断 | `air_hover_timeout` |
| r7 a1 | 4.56 / 15.07 / 1.93 m | 全程 | `MISSION_FAILED(TIMEOUT)` |
| r7 a2 | 0.94 / 2.29 / 1.92 m | 20.7→151.7 s 全程 | `MISSION_FAILED(TIMEOUT)` |
| r7 a3 | 1.06 / 3.55 / 1.86 m | 全程 | **`TRACKING_SUCCESS`** |

→ **结论**：`air_hover_timeout` 的**原始触发条件（EKF 发散 / 传感器断供）在本轮已不复现**；
三次 full attempt 均**正常 start**（`start OK -> AIR_SEARCH`），没有再出现 `create entities failed` 或
`air_hover_timeout`。该路径**无须**靠改契约/阈值绕过，也**没有**这样做。

> **诚实边界**：本轮**没有**找到 2026-10-29 那次传感器断供的确定性根因（只证明它不复现）。
> 这与 round-2 的 H2（共享 `build/` 状态污染）方向一致，但本轮**未做隔离对照**，
> 故 H2 记为**仍未排除**（见 §7 台账），**不**宣称已修好。

### 3.3 新发现的**确定性**缺陷（本轮真正的阻塞点）

`air_perception` 在 a1 启动即死：

```
[air_perception-8] terminate called after throwing an instance of
  'rclcpp::exceptions::InvalidParameterTypeException'
  what(): parameter 'seed' has invalid type: Wrong parameter type,
  parameter {seed} is of type {string}, setting it to {integer} is not allowed.
[ERROR] [air_perception-8]: process has died [pid 6386, exit code -6, ...]
```

机制（离线复现，不启进程）：
`launch_ros` 对**裸** `LaunchConfiguration` 参数值走 `yaml.safe_load` →
字符串 `"0"` 被解析成 **int 0**；而 `air_perception` 声明
`declare_parameter<std::string>("seed", "unseeded")`（`perception.yaml` 也写 `seed: "0"`）→ 类型冲突即抛。
后果链：`air_perception` 死 → `/agc/air/obs` 无发布者 → `air_fusion` 无观测输入 → 目标**永不进入**
`/agc/targets` → `task_manager` 永远停在 `AIR_SEARCH` → `MISSION_FAILED(TIMEOUT)`。

**区分度证明**（同一份 launch，只差这一个类型标注）：

| | a1（修复前） | a2（修复后） |
|---|---|---|
| `air_perception` | **died exit -6** | 就绪（通道 2 / 障碍 42 / obs_hz 20） |
| `/agc/air/obs` | 无发布者 | 正常 |
| 目标可见 tick | **0 / 1805** | **28 / 1801** |

### 3.4 修复后暴露的第二个（**真**、非本轮引入）问题：C10 hold 自锁

a2 修好感知后，目标**能被看到**了（B1 `gate_ok=168/216` 两个窗口），但随后：

```
[trajectory_tracker] 已获目标后参考 / 目标失效（ref_fresh=1 tgt_fresh=0）→ 显式 hold（不回落八字）
```

→ 契约 C10 的「已获目标后丢失即冻结」**按设计**触发；而 s04 默认 `observe_yaw_mode=velocity`
（机头随速度、零速不转）→ 冻结后机头不再转动 → 目标永久出视场（B1 之后恒为 `fov_az≈202`）→ 自锁。
这**正是** [ADR-0073](../../../../docs/adr/0073-p1-arm-fairness-noncoop-fixed-trajectory.md) 已实证并
明文**否决"改 hold 语义"**的已知形态（红线：不得为实验方便改 C10）。

<a id="p1-1-r7-exit"></a>
## 4. 出口判据证据（**这是"达标"的直接依据**）

**命令**（与 `experiments/p1-1/round-7/evidence/a3/runner.out` 一致）：

```bash
cd /home/chen/AGC
source /opt/ros/jazzy/setup.bash && source install/setup.bash
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export GZ_SIM_SYSTEM_PLUGIN_PATH=/home/chen/AGC/install/agc_sim/lib
python3 scripts/episode_runner.py \
  --scenes s04_static_static_obs_track --seeds 0 \
  --backend full --mode headless \
  --timeout 300 --ready-timeout-s 180 --start-timeout-s 90 \
  --observe-yaw-mode target \
  --campaign p1-1-r7-a3
```

**终态**（`metrics/summary.json` 与 `metrics/report.json` 双源一致）：

| 判据 | 实测 | 出处 |
|---|---|---|
| backend | **full** | `config/scene_manifest.json` |
| scene / seed | **s04_static_static_obs_track** / 0 | 同上 |
| world_map | **yard** | manifest `effective_params.world_map` |
| geometry 真源 sha256 | `351789d7…d622be` = `src/agc_sim/config/maps/yard.yaml` **逐字节一致** | manifest `geometry.sha256` vs `sha256sum` |
| 终态 | **`TRACKING_SUCCESS`** / `tracking_milestone` | summary `terminal_state` / `terminal_reason_code` |
| latched | `true`（`first_terminal_latch_v1`） | summary |
| expected_match / pass | **true / true** | runner report |
| 可见率 | **0.978**（406/415 tick） | summary `visibility_metrics` |
| episode 窗口可见 | 405/414 | summary `episode_window_metrics` |
| C9 两指标 | `shield_infeasible_rate=0`、`reset_failure_rate=0` | summary |
| 同 run 关联 | `same_run_verified=true`、`state_run_verified=true`、`proc_exit_confirmed=true` | runner report |
| run_id | `20261030-s04_static_static_obs_track-0-152449-0339` | summary |
| 墙钟 / RTF | 55.5 s / 0.678（runner 口径）；`duration_s` 39.69 s / RTF 0.905（run_logger 口径） | 两处如实分列 |

**长期证据落点**（`experiments/p1-1/round-7/`，本轮**新建**）：

```
experiments/p1-1/round-7/
├── evidence/
│   ├── a1/…/runner.out                      # 失败尝试 1（修复前）
│   ├── a2/…/runner.out                      # 失败尝试 2（修复后，暴露 C10 自锁）
│   ├── a3/…/runner.out                      # **成功尝试**
│   ├── p1-1-r7/{,a2,a3}/*/{report.json,report.md,log/*.log}
│   ├── run_logger/<run_id>/{summary.json,scene_manifest.json,params_applied.yaml,
│   │                        toolchain_world.json,workspace_fingerprint.json}
│   ├── derived/ekf-convergence.json          # 三次 attempt + round-2 的 EKF 判读
│   ├── derived/a2-b1-gate-timeline.txt       # 自锁的 B1 门控序列（对照用）
│   ├── px4-ulog-index.json                   # ulog 身份（原始 ulog 属工具链 build，不复制）
│   ├── t2-budget.json                        # 预算记账
│   └── preflight-processes.txt               # 开跑前孤儿进程现场
```

> `/tmp` 只作中间产物；**判据证据全部已复制到 `experiments/`**（round-6 的缺陷已纠正）。

<a id="p1-1-r7-caveat"></a>
## 5. ⚠ 需 Leader 裁定：`--observe-yaw-mode target` 的口径

**事实**：a3 成功用的是 `observe_yaw_mode=target`（机头对准目标），s04 的默认是 `velocity`。
该开关**早已存在**（`w6.launch.py` / `episode_runner.py` 均有），我没有新增任何参数或改默认值。

**为什么用它**：见 §3.4——`velocity` 下 C10 hold 会自锁，这是 [ADR-0073](../../../../docs/adr/0073-p1-arm-fairness-noncoop-fixed-trajectory.md)
已实证的形态；ADR-0073 明文**否决"改 hold 语义"**，故在该红线内，唯一可行路径是不让机头在冻结后失锁。

**为什么这需要裁定**：
- 支持：它是项目**已有**的"协同观测臂"，且 ADR-0070(i) 允许 oracle 指向臂**只要如实标注**；
  P1-1 出口判据的原文是「yard 地图上主场景能跑通一次，终态符合预期」，**未**限定 yaw 模式。
- 反对：它是**显式 oracle 指向臂**（用真值方位转机头），比 `velocity` 强；若 P1-1 想要的是
  "默认参数即可复现"，则 a3 **不满足**，需另寻不解锁 C10 的路径（例如改 `air_tracking_ref` 臂定义、
  或接受 `velocity` 下必然 TIMEOUT 并把它登记为**已知缺口**）。

**我没有自行定案**。请 Leader 在下列两者中裁定：
1. **认 a3 为出口证据**（并登记"P1-1 出口在 target 指向臂上取得，非默认 velocity"）；
2. **不认**，则本项回到"未达成"，需裁定是否允许改臂定义（属改变口径，Worker 不自行决定）。

<a id="p1-1-r7-deviations"></a>
## 6. 偏离与如实登记

1. **T2 attempt 用了 3 次**（派工单："单轮真实实验 attempt ≤2"）。
   a1（修复前）→ a2（修复后）已用满 2 次；a3 是在 a2 已产出**决定性区分**（EKF 已收敛、阻塞点已从
   PX4 移到 FOV/C10）后追加的**唯一一次**"判别实验"，并直接取得出口。
   **这属超出派工单字面**，我不狡辩：请 Leader 按"为拿出口而追加 1 次"追认或判偏离。
   若判偏离，则本单出口证据仍以**未验收**处理。
2. **测试文件 `scripts/tests/test_full_chain_seed_protocol.py` 不在任何既有白名单**。
   改它的**必要性**：其原断言 `perception.count("'seed': seed") == 1` 把**源码字面**钉死，
   修好缺陷后必然误报（实测 1 failed）；若不改，任何人重跑该测试都会看到"修好反而挂"。
   我**只**把它改成表达同一意图（"仅 air_perception 带 seed"）+ 新增一条有反向对照的断言，
   **未**放宽任何语义。请 Leader 追认或要求我回退（回退则该测试对正确代码报错）。
3. **未改**任何契约/终态/阈值/8 字参数；`air.yaml` 无阈值改动（§2）。
4. **未 commit**：工作区仍为既有 staged/unstaged + 本轮 2 个文件改动。
5. **round-6 遗留的白名单偏离**（`agc_task`/`worlds`/`CMake`/`tests/w6_geometry_check.py`）保持原样，未回退。

<a id="p1-1-r7-budget"></a>
## 7. 预算

| 项 | 用量 |
|---|---|
| T2 full attempt | **3 次**（a1/a2/a3），墙钟 161.5 + 162.5 + 55.5 = **379.5 s / 1800 s** |
| T2 局部构建 | **1 次**（`agc_perception`，2.14 s；`symlink-install` 生效） |
| T1 微观测 | 派工单**未预授权**（"本轮不预授权额外探针"）→ **0 次**，未使用 |
| 离线/静态检查 | 若干（pytest 14 项、ulog 判读、launch 参数求值），均 <30 s、不启外部进程 |

<a id="p1-1-r7-ledger"></a>
## 8. 假设台账

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 `air_hover_timeout` 由 PX4 EKF 发散导致，与 yard 几何无关 | **已排除**（本轮 3 次 full attempt 均 start 成功；EKF ≤3.6 m） | 已做（a1/a2/a3） | — |
| H2 round-2 发散源于共享 `build/` PX4 可写状态 / 传感器流断供 | **未排除**（断供现场已从 ulog 复原，但本轮**未做隔离对照**即已不复现） | 同 seed、`px4_run_root:=<隔离>` 与共享 build 各 1 次 full attempt，比对 `sensor_mag`/`sensor_gps` 覆盖 | 2 次 full attempt |
| H3 `air_perception` seed 类型冲突阻断感知链 | **已排除**（修复后 a2 目标可见 28/1801、a3 可见 406/415） | 已做（a1 vs a2） | — |
| H4 `velocity` 下 C10 hold 自锁使 s04 必然 TIMEOUT | **未排除**（a1/a2 均 TIMEOUT，且日志有 `显式 hold`；但 a1 另有 seed 缺陷干扰，n 偏小） | `velocity` + `air_tracking_ref:=off` 各跑 1 次，看是否仍自锁 | 2 次 full attempt |
| H5 8 字轨迹净空 / 几何导致空中不可行 | **已排除**（a1 的 own 已实飞到 x/y span ~15 m；静态断言 (i) 亦 PASS） | 已做 | — |

**下一轮建议**（按性价比排序）：
1. **优先求 Leader 裁定 §5**——若认 a3，则 P1-1 可进验收，无需再花 T2。
2. 若不认：先做 **H4**（`velocity` + `air_tracking_ref:=off`）——这是 ADR-0073 已验证能解耦自锁的既有手段，
   1 次 attempt 即可判定"默认参数能否跑通"，比改契约安全。
3. H2 的隔离对照优先级低（问题已不复现），仅在再次复现时做。

<a id="p1-1-r7-notdone"></a>
## 9. 未执行 / 未达成

- **未做** GUI 形态的 full 链（本轮 3 次均 headless）。派工单未要求 GUI；P1-1 出口判据原文亦未限定。
  若"演示必须 GUI"，需另派（GUI 另加 2–3 GB 内存，见 playbook）。
- **未做** H2 / H4 的判别实验（见 §8）。
- **未**把 `experiments/p1-1/round-7/` 纳入 git（未 commit，交 Leader）。
- **未验证** `velocity` 默认参数下能否达成终态（**这就是 §5 的争议点**）。

<a id="p1-1-r7-selfcheck"></a>
## 10. 自查

| 检查 | 结果 |
|---|---|
| `python3 -m pytest scripts/tests/test_full_chain_seed_protocol.py -q` | **14 passed** |
| launch 参数求值（T0，不启进程）：`air_perception.seed` | `'0'`（**str**）；反向对照裸 substitution → `0`（int） |
| 三图几何核查 / 其它离线护栏 | 本轮**未重跑**（本轮未改几何真源与 `w6_geometry_check.py`；round-6 已 PASS，且 `yard.yaml` sha256 与 manifest 一致） |
| 契约红线 | 未发现未满足的硬约束；**未**改 C10 / 终态 / 阈值 / ABI |
| 进程现场 | 收尾后无本项目 PX4 / GZ / agent 残留（`proc_exit_confirmed=true`） |
