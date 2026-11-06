<a id="request"></a>
# N1 · round-6 GUI 证据与检测指标补证

- 任务 ID：`20261102-002-n1-vision-minimal-loop`；轮次：6；Leader 派发时间 `2026-11-02T16:20:00+08:00`（Asia/Shanghai）。
- 沿用同一 Worker 会话 `18d8e00b-995d-413c-93a5-21e5418e2ab2`（返工，不新建 Worker）。
- 依据：[round-5 Leader 审查](../round-5/review.md#review)。**主体链路已实证通过**；本轮只补三项未达。

## 一、本轮只做三件事

### A. GUI 证据（唯一硬出口缺口）

round-5 环境无 X display。**本轮开工第一步必须先做 GUI 可行性前置检查**，避免再浪费一整轮：

```bash
# 1) socket 是否存在
ls -A /mnt/wslg/.X11-unix; ls -A /tmp/.X11-unix
# 2) 能否真的连上（不要只看 DISPLAY 变量）
command -v xdpyinfo && xdpyinfo -display :0 >/dev/null 2>&1 && echo "X OK" || echo "X UNAVAILABLE"
```

- **若 `X OK`**：跑一次 `full + GUI`、seed 0、`s02`、`perception_path=vision`、`detector_backend=synthetic_color`。保存 GUI 原始帧，**帧数与采集退出码如实记录**（H0 曾出现"8 帧采集冒充完整"，不重演）。若采集脚本返回非零，必须写明；不得只报"目录存在"。
- **若 `X UNAVAILABLE`**：**立即停**，在 report 头部记 `阻塞`，附上述三条命令原文输出与时间戳，通知 Leader。**不要**尝试 headless 代替、不要尝试安装 X server、不要耗时间绕（round-5 与 Leader 均已尝试 `apt-get download` + `dpkg-deb -x` + `unshare` 全部失败；`/usr/bin/xkbcomp` 是 Xvfb 内部硬路径，无 root 越不过）。

### B. 检测指标（N1 出口判据明确要求）

在**同一次**运行里让探针多采三样东西（**只加采集，不改任何决策代码**）：

1. `/agc/gt/intruder_uav` 的 `(stamp, x, y, z)` 样本序列 —— **仅落盘供离线评估**，不得进入任何决策节点。这一点必须在 report 与探针代码注释里写明：采集侧读 GT 是 ADR-0009 允许的离线评估用途，决策侧仍无 GT 订阅。
2. 配对链：`(image_stamp → detection_stamp → track_stamp → goal src_stamp)`。
3. 探针把 `/agc/task/state` 改用 `agc_msgs/AgcTaskState`（round-5 已修未验，本轮验证）。

产出数值：`recall`/`precision`、3D 误差 `p50`/`p95`、图像到航迹延迟 `p50`/`p95`。用离线脚本从证据 JSON 计算，脚本放 `scripts/vision/`。

**3D 误差的诚实口径**：本实现是 `z=plane_z` 单平面相交，目标真实高度偏离 2.0 m 时会有系统性径向误差。报告须把误差按"目标高度偏差"分档或注明该项残差来源，**不得**把单平面假设的误差说成检测器精度。

### C. `detector_backend` 入 summary

契约 `docs/ROS2迁移交接文档.md#perception-path` 要求产物记录 `perception_path` **与视觉模型标识**；当前 `vision_model={id:"none",...}` 使本 run 在路径比较时**不可区分**为视觉后端。

**Leader 授权**：本轮可改 `src/agc_task/src/run_logger.cpp`（**仅**新增键）与 `run_logger` 对应 launch 注入：

- 新增 `detector_backend` 字段写入 `summary.json`；
- **不改**既有 `perception_path` / `vision_model` 字段语义；
- **不改**任何终态、安全、评估逻辑；
- 新增一个聚焦测试守护该字段（truth 模式下写 `none`）。

若你判断该改动会波及评估口径，先停报，不要自行扩大。

## 二、资源

- **N1 原批次墙钟已于 `2026-11-02T16:28:41+08:00` 耗尽**，本轮为**用户新授权**（见 CURRENT），额度：

| 项 | 额度 |
|---|---|
| 总墙钟 | **7,200 s**，自本轮领取时间起算 |
| T2 | **3,600 s**，单次构建/运行 ≤900 s |
| T1 | 0 |
| 静态/离线 | 600 s，单次 ≤30 s |

- GUI 运行是唯一必须占用 T2 的项。**若 GUI 不可用，最多只花 300 s 确认环境后立即阻塞**，不要消耗全部额度。
- 独占构建/ROS/GZ/PX4/GUI；启动前 `ps` 核查，冲突即停报。

## 三、边界（与 round-5 相同，不放松）

- 不改 `src/agc_msgs/`、9 消息 ABI、`task_manager.cpp`、控制器、规划器、PX4 模型、地图几何、`scenarios.yaml`。
- 不改 `scenario_reset.cpp`。
- 保留四个 H0 文件既有语义（`w6.launch.py`、`w6_composition.py`、`w6_base.yaml`、`scenarios.yaml`）。
- 视觉决策节点仍**不得**订阅 `/agc/gt/*`；GT 只允许在**探针/离线评估脚本**侧读取。
- **禁止** `git stash` / `reset` / `clean` / `checkout` / `commit` / 切分支（round-5 已犯一次，本轮再犯按未授权破坏处理）。
- 不改 `round-1..5` 记录、不改 CURRENT、不归档、不派 N2/N3、不轮询、不建提醒。

## 四、交回

- 只写 `round-6/report.md` 与 `round-6/evidence/`。
- report 头部写领取时间、执行者、子会话 ID、预算起点、轮末状态（`待审查` 或 `阻塞`）。
- 正文给：三项未达的逐条结果（含 GUI 帧数与采集退出码）、检测指标数值与分档口径、`run_logger` 差异、命令与退出码、证据路径与哈希、T1/T2/墙钟账目、未达项。
- 完成后 `send_message` 通知 Leader，结束本轮。
