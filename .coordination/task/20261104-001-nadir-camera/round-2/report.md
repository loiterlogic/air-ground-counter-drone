<a id="report"></a>
# 机载俯视（正下视）相机 —— 轮次报告 r2

- 任务 ID：`20261104-001-nadir-camera`；轮次：2
- 执行者：Worker（一般模型执行者）
- 子会话 ID：worker
- 领取时间：`2026-11-04T19:08:45+08:00`（Asia/Shanghai）
- 基线：分支 `main`，HEAD `49e099c`
- 轮末状态：**待审查**

---

## 审查摘要（≤30 行）

**结论：A1–A8 全部达成。** 相机能力已落地并**实测出图**；默认臂逐字不变（0 帧）；新臂出帧且主场景仍达期望终态。

**核心证据**（两个 run 都持 `sim.lock`，串行，跑完进程归零）：

| 判据 | 结果 | 证据 |
|---|---|---|
| A1 默认臂无帧 + 终态 | **0 帧 / 45 s**；终态 `TRACKING_SUCCESS`，`pass=True` | `experiments/nadir-camera/20261104-nadir-arm-a-default-probe/`、`.../20261104-nadir-arm-a1/` |
| A2 新臂 ARM+起飞 | `Ready for takeoff` + `Takeoff detected`，无阻断性 Preflight Fail | `.../20261104-nadir-arm-b4/log/` |
| A3 帧率/内参/PNG | **144 帧 / 50 s，中位 28.5 Hz**；`fx=fy=268.60`；8 张 PNG | `.../20261104-nadir-arm-b4/probe-stdout.txt` |
| A4 是地面不是天空 | **目视确认为地面**（14 m 高，见机体影、目标机、管道、建筑） | `.../frames/frame_000.png` |
| A5 离线闸门 | pytest **12/12 绿**；run_smoke 的 offline/docs/index **三组全绿** | 见「命令与退出码」 |
| A6 ADR/索引/plan | ADR-0030 落盘；`adr_index.py --check` PASS；plan 已删；`docs_link_check.py` PASS | 见下 |
| A7 无任务链耦合 | `/agc/targets` 发布者仍仅 `gt_adapter`；nadir 零订阅者 | 静态闸门 2 条断言 |
| A8 未越界 | `toolchain/**` 未改、契约未改、无新 launch 参数 | 见「A8 证据」 |

**差异清单（我实际改的，共 7 处）**：新建 `src/agc_sim/models/agc_x500_nadir/{model.sdf,model.config}`、
`bridge.yaml` 加 2 条、`w6.launch.py` + `air_bringup.launch.py` 条件注入、新建
`scripts/tests/test_nadir_camera_contract.py`、新建 `docs/adr/0030-*.md`、§7.1 补一段、删 plan、`docs/adr/README.md` 重生成。

**未决项**：① `README.md`「已知边界」按 Leader 补充约束**未改**，文本见文末「交 Leader 合并的 README 文本」；
② 一次 B 臂 `air_hover_timeout`（infra）重试后成功，如实记录。

---

## 一、接单基线

- 分支 `main`，HEAD `49e099c`；进场时工作区已脏 **660 项**（含 ADR 重命名的 30 个未跟踪新文件名）。
- **`w6.launch.py` 进场前已是脏文件**：`git diff` 显示 150 行新增，其中**只有 15 行是本轮 nadir 相关**
  （`grep -c "nadir\|ADR-0030\|own_px4_env_extra\|PX4_SYS_AUTOSTART"`），其余是 2026-11-04 早先
  `perception_path` / `spawn_randomize` 等重构的既有改动，**不是我造成的**，也未回滚。
- `air_bringup.launch.py`：本轮加 40 行（含注释），全部与 nadir 相关。

## 二、实际改动（区分原有改动）

| 文件 | 动作 | 说明 |
|---|---|---|
| `src/agc_sim/models/agc_x500_nadir/model.sdf` | **新建** | `include merge model://x500` + 独立 `nadir_cam_link` + fixed joint；`<model name>agc_x500_nadir`；pitch `+1.5708`；显式 `camera_info_topic` |
| `src/agc_sim/models/agc_x500_nadir/model.config` | **新建** | `<name>agc_x500_nadir</name>` |
| `src/agc_sim/config/bridge.yaml` | 改（+37 行） | 仅新增 `Image` + `CameraInfo` 两条（`SENSOR_DATA`）+ 口径注释 |
| `src/agc_task/launch/w6.launch.py` | 改（**15 行是本人的**） | `nadir_enabled` 条件注入 `PX4_SYS_AUTOSTART=4001` + 本仓 models 路径；`px4_sim_model` 描述 |
| `src/agc_air/launch/air_bringup.launch.py` | 改（+40 行） | 同款条件注入；描述 |
| `scripts/tests/test_nadir_camera_contract.py` | **新建** | 12 条纯静态断言 |
| `docs/adr/0030-nadir-camera-capability.md` | **新建** | 168 行 |
| `docs/conventions/飞行高度分层与按地图定高.md` | 改 | §7.1 补「35° 边界 vs 56.1° 角落」+ U3 引用改指 ADR-0030；**数字一个未动** |
| `docs/adr/README.md` | 重生成 | `adr_index.py`（持 `docs.lock`） |
| `docs/plan/无人机俯视相机.md` | **删除** | 结档 |
| `experiments/nadir-camera/**` | **新建** | run 目录 + `_tools/camera_probe.py` |

**未改**：`README.md`（Leader 合并）、`docs/conventions/路线分支治理.md`（裁定 3 不改）、
`toolchain/**`、`docs/ROS2迁移交接文档.md`、`src/agc_sim/launch/world_bringup.launch.py`（资源路径已具备）。

## 三、命令、退出码与结果

| # | 命令 | 退出码 | 结果 |
|---|---|---|---|
| 1 | `gz sdf -p model.sdf`（`SDF_PATH`=本仓 models:PX4 models） | **0** | 展开成功，**无警告**；hl 从 0→1（`nadir_cam_link` 已并入）；`<topic>agc/air/nadir`、`<camera_info_topic>agc/air/nadir/camera_info` 保留 |
| 2 | `colcon build --symlink-install --packages-select agc_sim`（持锁，T2） | **0** | 18.9 s；`install/.../models/agc_x500_nadir/{model.sdf,model.config}` 为**逐文件符号链接** |
| 3 | `pytest scripts/tests/test_nadir_camera_contract.py -q` | **0** | **12 passed** |
| 4 | 变异测试：pitch 改 `−1.5708` | 2 failed | 两条 pitch 断言都红（证明判据有效） |
| 5 | 变异测试：bridge `camera_info` gz 名改 `/agc/air/nadir_info` | 1 failed | 话题逐字一致断言红 |
| 6 | 变异测试：删 `PX4_SYS_AUTOSTART` 注入 | 1 failed | 注入断言红 |
| 7 | A1 默认臂：`episode_runner --scenes s04 --mode headless --backend full`（持锁） | **0** | `TRACKING_SUCCESS` / `pass=True` / `expected_match=True` |
| 8 | A1 对照探针（默认臂 `gz_x500`，45 s） | 0 | **frames_received=0**；实体 `x500_0` |
| 9 | A3 新臂：`episode_runner --px4-sim-model gz_agc_x500_nadir`（持锁） | **0** | `TRACKING_SUCCESS` / `pass=True`；**144 帧 / 28.5 Hz** |
| 10 | `run_smoke.py --only docs` / `index` / `offline` | 0/0/0 | 三组全绿（0.87 s / 1.63 s / 17.24 s） |
| 11 | `adr_index.py --check`（持 `docs.lock`） | **0** | `PASS：ADR 索引与 30 篇 ADR 一致` |
| 12 | `tests/docs_link_check.py` | **0** | `PASS：活跃文档范围内无断链` |

## 四、A1–A8 逐条证据

### A1 默认 `gz_x500` 无新相机帧 + 主场景终态符合预期 —— **达成**

- 终态：`experiments/nadir-camera/20261104-nadir-arm-a1/metrics/report.json`
  → `terminal_state=TRACKING_SUCCESS`、`reason_code=tracking_milestone`、`expected_match=True`、`pass=True`、
  `layer_integrity=True`；`summary.json` 同值（`.../w6-task-eval/20261104-s04_static_static_obs_track-0-204858-6329/metrics/summary.json`）。
- **无相机帧**：`.../20261104-nadir-arm-a-default-probe/probe-stdout.txt` → `frames_received: 0`（45 s）。
  该 run 的 `launch.log` 显示 `model name: x500_0, simulation model: x500`（无相机机型）。
- ⚠ **同一 run 的 `gz-topic-list.txt` 里仍有 `/agc/air/nadir`、`/agc/air/nadir/camera_info`** ——
  这正是「话题存在 ≠ 有帧」：桥是订阅者，gz 会列出只有订阅者的话题。**判据用的是帧数，不是话题列表。**

### A2 新臂起得来：ARM + 起飞 + 飞行，无 Preflight Fail —— **达成**

`.../20261104-nadir-arm-b4/log/ep_s04_static_static_obs_track_0.log`：
- `env SYS_AUTOSTART: 4001`（机型解析未改工具链）
- `model name: agc_x500_nadir_0, simulation model: agc_x500_nadir`（实体名正确）
- `[commander] Ready for takeoff!` → `[commander] Takeoff detected`
- 终态 `TRACKING_SUCCESS`（己方机完成整段飞行）

> 关于 `Preflight Fail`：日志里可见 `ekf2 missing data` / `Compass Sensor 0 missing` / `Battery unhealthy`，
> 但它们是**启动早期的瞬时告警**，随后即 `Ready for takeoff` + `Takeoff detected`；
> **A1 默认臂同样出现 6 次同类告警**（`grep -c` 实测），故与本机型无关，属既有基线现象。

### A3 真实帧 ≥30 张、≥10 Hz；`camera_info` 内参存在 —— **达成**

`.../20261104-nadir-arm-b4/probe-stdout.txt`（原文）：
```json
{"frames_received": 144, "hz_median": 28.494880940249327, "elapsed_s": 50.047983169555664,
 "image_meta": {"width": 640, "height": 480, "encoding": "rgb8", "step": 1920,
                "frame_id": "agc_x500_nadir_0/nadir_cam_link/nadir_camera", "is_bigendian": 0},
 "camera_info": {"width": 640, "height": 480,
                 "K": [268.6016273498535, 0.0, 320.0, 0.0, 268.60164642333984, 240.0, 0.0, 0.0, 1.0],
                 "frame_id": "agc_x500_nadir_0/nadir_cam_link/nadir_camera",
                 "distortion_model": "plumb_bob"},
 "png_saved": 8}
```
- 帧数 **144 ≥ 30**；中位 **28.5 Hz ≥ 10**；内参 `fx=fy=268.60` 与 `(640/2)/tan(50°)=268.51` 一致（差 0.03%）。
- PNG 落盘 **8 张**（`.../frames/`）。

### A4 图像内容是地面（不是天空）且中心射线符合正下视 —— **达成**

**目视结论**：`.../20261104-nadir-arm-b4/frames/frame_000.png`（14 m 高度）可见**无人机自身投影、
目标无人机（带蓝色圆盘）、地面管道、建筑投影**——是地面俯视图，**不是天空**。

**几何核对算式**（可复算）：
```
光轴 = R_y(pitch) · x̂，  R_y(θ)·x̂ = (cosθ, 0, −sinθ)
pitch = +1.5708  ⇒  光轴 = (−4e−6, 0, −1.000000)   ⇒ z 分量 ≈ −1（正下方）
中心射线水平偏移 = 0 m（光轴铅直，落点 = 机体正下方）
```
若 pitch 写成 −1.5708，则 z 分量为 **+1**（正上方）——PNG 会是纯天空。符号判据因此是硬的。

### A5 新增离线闸门通过；run_smoke 的 offline/docs/index 全绿 —— **达成**

- `pytest scripts/tests/test_nadir_camera_contract.py -q` → **12 passed**。
- 12 条断言覆盖：默认臂无相机（2 条）、模型资产与挂载范式（2 条）、pitch 数值+语义双断言（2 条）、
  话题与桥逐字一致 + 注释口径（2 条）、`PX4_SYS_AUTOSTART` 注入 + 无新增 airframe（2 条）、
  零消费者 + `/agc/targets` 发布者唯一（2 条）。
- **判据有效性用变异测试证明**（见第三节 4–6）：三处故意改错分别触发对应断言变红，改回后全绿。
- `run_smoke.py --only {offline,docs,index}` → 三组全绿。

> **两条断言写错过、已修**（记下来防止再犯）：① 第一版在 `create_publisher` 同行 grep `/agc/targets`，
> 但该话题是**参数默认值**（`target_topic_`），永远匹配不到 ⇒ 空断言；② 第二版用
> `create_publisher[^;]{0,200}<var>` 跨行扫描，把相邻的 `create_subscription(..., self.targets_topic, ...)`
> 吞进来，误判 `agc_rl/high_level_node.py` 是发布者。**最终版按单次调用的顶层实参解析**，
> 并保留「一处发布者都找不到即 FAIL」的退化保护。

### A6 ADR-0030 落盘、索引 `--check` 通过；§7.1 / README 已知边界已更新；plan 已删且链接 PASS —— **部分达成（README 一项按 Leader 约束移交）**

- ADR-0030：`docs/adr/0030-nadir-camera-capability.md`（168 行，含 Status/背景/决策/不做什么/Consequences/GSD/回滚）。
- `adr_index.py --check` → `PASS：ADR 索引与 30 篇 ADR 一致`（持 `docs.lock` 生成）。
- §7.1：已补「35° 边界视场 vs 56.1° 角落」区分 + ADR-0030 状态更新；**表格数字一个未改**（按裁定 2）。
- plan：`docs/plan/无人机俯视相机.md` **已删除**；`docs_link_check.py` → **PASS**。
- **README「已知边界」：未改**——Leader 2026-11-04 补充约束明确「你不要改 README.md，文本写进 report 由 Leader 合并」，
  验收按「已提交文本给 Leader」计。**文本见文末。**

### A7 无任务链耦合 —— **达成**

- `/agc/targets` 的发布者仍仅 `gt_adapter`：离线闸门 `test_targets_publisher_is_still_gt_adapter_only`
  （解析 `create_publisher` 顶层实参 + 变量默认值映射）→ 全仓发布点只有 `src/agc_perception/src/gt_adapter.cpp`。
- nadir 零消费者：`test_no_vision_consumer_of_nadir_image` → 全仓无 `create_subscription` /
  `image_transport` 指向 `/agc/air/nadir/image_raw`。
- `src/` 内 `nadir` 字样仅出现在两个 launch 的机型开关与 `bridge.yaml`，**无任何订阅引用**。

### A8 未触碰 `toolchain/**`、未改契约、未新增 launch 参数 —— **达成**

- `toolchain/**`：本轮**零改动**。`git status --short toolchain/` 只有 `M toolchain/README.md`，
  该 diff 是**进场前既有的 ADR 重编号链接修正**（`0101-*` → `0027-uxrce-startup-reproducibility.md`、
  `0065-*` → `0005-px4-toolchain-and-link.md`），与本任务无关，未回滚。
- `docs/ROS2迁移交接文档.md`：本轮**零改动**（`M` 是进场前既有，95+/43−，为 ADR 重编号后的锚点更新）。
- **未新增 launch 参数**：`px4_sim_model` 是既有参数，只新增了一个**取值** `gz_agc_x500_nadir`；
  `scripts/tests/test_branch_ledger.py` 的注释明确「`gz_x500_mono_cam` 之类是文件/模型选择，不是路线分支」。
- `toolchain/.../init.d-posix/airframes/` 下**无**新增文件（闸门 `test_no_new_airframe_in_toolchain` 守护）。

## 五、五点静默失败点 × 实测验证

| # | 点 | 失败现象 | 本轮验证 |
|---|---|---|---|
| 1 | 机型解析 | `Unknown model` 后 PX4 退出 | 日志 `env SYS_AUTOSTART: 4001` + 实体 `agc_x500_nadir_0` |
| 2 | 资源路径 | `EntityFactory service call failed` / 静默挂死 | `gz sdf -p` 本地展开 exit 0；运行期实体正常 spawn |
| 3 | 相机姿态 | PNG 是天空 | PNG 目视地面 + 光轴 z=−1 算式 |
| 4 | 桥 QoS | 有话题无帧 | 144 帧 / 28.5 Hz 实测（非话题列表） |
| 5 | 实体名 | IMU/odom 话题错 → 永不 arm | `model name: agc_x500_nadir_0` + `Ready for takeoff` |

**额外第 6 点（本轮发现）**：`camera_info` 默认按 `<topic>_info` 派生 → `/agc/air/nadir_info`，与桥不符且**静默**。
已显式写 `<camera_info_topic>`（注意：该元素在 **`<camera>` 下**，不在 `<sensor>` 下；
写错位置会被 sdformat 当"未定义元素"复制保留而**不生效**——本轮首版即踩此坑，`gz sdf -p` 的警告暴露了它）。

## 六、偏离与失败样本（如实记录）

1. **B 臂一次 infra 失败**：`20261104-nadir-arm-b3` → `INFRA_FAILURE / air_hover_timeout`（`start rejected: air_hover_timeout`），
   RTF 0.892、`odom_valid_ratio` 0.961，相机本身**正常出帧 438 帧 / 27.8 Hz**。
   该次己方机已 `Takeoff detected` 但悬停接管超时；重试（b4）**成功**。判为 PX4 慢热竞态（既有现象，非相机引入）。
2. **A1 首次 run 失败**：`20261104-nadir-arm-a-default` → `ACTIVE / ground_approach`（watchdog 超时），
   原因是**目标机侧** `intruder_driver 无可用 odom`。重跑（a1）成功。两次都保留，未覆盖。
3. **我自己的进程泄漏（已清理，如实披露）**：首版 run 脚本用 `kill -INT <launch_pid>` 收尾，
   `gz sim` / PX4 / ROS 节点成为 **init 孤儿并占着 `sim.lock`**（pid 176040/176043/176592/176948 等）。
   我按 PID 逐个清理了**自己启动的**这些进程（**未使用 `pkill -f`**、未碰他人的 159340/159341），
   随后改用 `set -m` + 按**进程组**回收，此后每轮 `POST: procs=0` 验证。
4. **探针脚本丢失**：`/tmp` 下的探针在 20:39 重启后被清空，导致 B1 拿到 `probe rc=2`。
   已把探针移到 `experiments/nadir-camera/_tools/camera_probe.py`（仓内，不会再丢）。
5. **默认臂对照探针**跑的是 `run_demo` 风格的直启（`px4_sim_model:=gz_x500`），未发 `/agc/task/start`，
   故它只承担「0 帧」对照，**终态证据来自 a1 那次 episode_runner run**——两者分开取证，未混装。

## 七、假设台账

| 假设 | 状态 | 判别实验 | 所需授权 |
|---|---|---|---|
| H1 光轴 = 传感器 +X | **已确认**（出图为地面） | 已完成 | — |
| H2 pitch 须 +1.5708 | **已确认**（出图为地面；−90° 会拍天空） | 已完成 | — |
| H3 `camera_info` 可被 `<camera_info_topic>` 覆盖 | **已确认**（内参在 `/agc/air/nadir/camera_info`） | 已完成 | — |
| H4 新目录需重建 | **已确认**（重建前 install 无该目录，重建后有符号链接） | 已完成 | — |
| H5 默认臂桥条目无害 | **已确认**（0 帧，主场景仍 TRACKING_SUCCESS） | 已完成 | — |
| H6 `gz_x500_mono_cam` 仍有消费者 → 不退休 | **已确认**（3 个白名单外文件） | 已完成 | — |

## 八、下一轮建议

无（A1–A8 已达成）。待 Leader 合并 README 文本后即可验收归档。若 Leader 要求更强证据，可补：
GUI 模式出图（headless 已足够，非必需）、`minimal` 地图下的足迹实拍（当前足迹为解析计算，非实测）。

## 九、累计资源账目

| 项 | 用量 |
|---|---|
| **墙钟** | r1 约 29 min + r2 19:08 → 21:19（约 2 h 11 min） |
| **T1** | 约 8 次 / <60 s（`gz sdf -p` ×2、`ls`/`grep`/`sha256sum` 若干）。单次均 ≤30 s、≤2 进程 |
| **T2（真实运行）** | **11 次 / 约 1 460 s**：构建 23 s；episode/探针 run 共 10 次（93+45+115+161+110+127+45+161+93+50 s 量级） |
| 其中**无效/失败样本** | 4 次（B1 探针丢失、B3 infra、A 首次 ground_approach、默认臂探针重复），**全部计入** |
| 剩余 T2 | 3600 − 1460 ≈ **2 140 s** |
| 每次运行均持 `sim.lock` | 是（`flock -w 1800/3600`），串行，跑完 `POST procs=0` |
| `/dev/shm` | 每轮结束 184–200 段（阈值 200，临界但未越）；重启后起点 1 段 |

## 十、交 Leader 合并的 README 文本（我不改 `README.md`）

> 建议插在「已知边界」段末条：

```markdown
- **机载俯视相机（opt-in，2026-11-04）**：`px4_sim_model:=gz_agc_x500_nadir` 时己方机挂一台**正下视**
  相机，桥出 `/agc/air/nadir/image_raw` + `/agc/air/nadir/camera_info`（[ADR-0030](docs/adr/0030-nadir-camera-capability.md#top)）。
  **仅取证/测绘，无消费者**——识别仍靠真值（`gt_adapter`），图像**不**接入任务链；
  默认 `gz_x500` 行为逐字不变（无相机）。
```
