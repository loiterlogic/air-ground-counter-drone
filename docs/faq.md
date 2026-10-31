# FAQ · 常见问题

> 面向**第一次跑本项目的人**。开发者的完整判别表（含 uXRCE participant 长尾、终态语义陷阱、
> 一批跑完后的收尾）见 [整链排障速查](conventions/整链排障速查.md#preflight)，本文只摘高频项，
> **不**复制整篇。
> 每条都对应真实症状；处置优先给**一条命令**，而不是一串排查步骤。

## 1. `./run_demo.sh doctor` 报工具链缺失

**症状**：`doctor` 的「工具链二进制」一项 FAIL，提示 `MicroXRCEAgent` 或 `px4_sitl_default/bin/px4` 不在位。

**原因**：`toolchain/` 是**外部依赖**，不进 git（[ADR-0012](adr/0012-px4-body-as-toolchain-dependency.md)），
新 clone 的仓里它是空的。

**处置**：按 [`toolchain/README`](../toolchain/README.md) 构建 PX4 + MicroXRCEAgent。
`doctor` 会打印**具体缺失的路径**，照它补即可。

```bash
./run_demo.sh doctor          # 看具体缺哪一项
```

## 2. 启动后卡在"等待 PX4"，以为卡死

**症状**：终端停在 `[00:17] PX4 己方实例 ... 等待中 (错峰 25s)` 十几秒不动。

**原因**：**这是正常行为**。`backend:=full` 有 PX4 己方 25 s / 入侵者 35 s 的**错峰延时**，
用于规避 uXRCE participant 创建长尾（[ADR-0094](adr/0094-uxrce-participant-warmup-and-px4-stagger.md)）。
从启动到任务开始约 **45–60 s**。

**处置**：**等**。进度提示会分段打印，不是死循环。超过 60 s 仍无进展才按第 4 条查残留。
想快速看效果用 `./run_demo.sh --backend lightweight`（几秒起，但无空中链路）。

## 3. `ros2 node list` 为空，但节点确实在跑

**症状**：另开终端 `ros2 node list` 输出空，但 `ps` 里节点在。

**原因**：环境域/发现范围不对。本仓**铁律**是 `ROS_DOMAIN_ID` 保持默认 `0`；
自设非 0 域会让 lifecycle **服务数据面不通**（话题却正常，极难判）。
本机 `SUBNET` 发现范围 + WSL2 上行还会间歇性全失效。

**处置**：

```bash
echo $ROS_DOMAIN_ID                    # 应为空或 0
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
```

`run_demo.sh` 已自动设 `LOCALHOST` 并在 `ROS_DOMAIN_ID` 未设时补 `0`——所以**用脚本起的实例**
不受影响；受影响的是你**另开终端**手敲 `ros2` 命令的时候。

> 注意：graph 查询在本机**不可靠**，不要用 `ros2 node list` 当门禁；用首个服务调用探活
> （见排障速查 §3）。

## 4. 有残留进程 / 上次没干净退出

**症状**：再次启动报端口被占、`Publisher already registered for node name`，或 `doctor` 的
「无本项目残留进程」FAIL。

**原因**：`Ctrl-C` 被打断、或外部终止（断网 / 只杀了 leader）会让 `gz sim` / `px4` /
`MicroXRCEAgent` / 桥 / `tf` 逃逸成孤儿。

**处置**：

```bash
./run_demo.sh stop      # 幂等；按记录的 PID/PGID 回收，不碰别人的进程
./run_demo.sh status    # 只读查看现状与残留
```

`stop` 收不掉的极端情况，按 **PID** 清理：

```bash
ps -eo pid,cmd | grep -E "[i]nstall/agc_|[M]icroXRCEAgent|[p]x4_sitl|gz sim|[p]arameter_bridge"
kill <PID>
```

> **禁止** `pkill -f "<名字>"`：模式会匹配到该 shell 自身命令行，把自己杀掉（Exit -1）。
> 这也是本仓[三条环境铁律](conventions/整链排障速查.md#preflight)之一。

## 5. Gazebo 窗口黑屏 / 没有画面

**症状**：GUI 起来了但 3D 视图全黑，或干脆没窗口。

**原因**：渲染后端与当前图形环境不匹配（WSL2 + D3D12、或纯软件渲染）。
也可能是在 **Wayland** 会话下窗口存在但抓屏取不到内容（这与"黑屏"不同，见下）。

**处置**：脚本已自动 `gui_render_backend:=auto` 探测，通常无需干预。仍黑屏时依次试：

```bash
./run_demo.sh                        # auto（默认）
ros2 launch agc_task w6.launch.py backend:=full gui_render_backend:=d3d12
ros2 launch agc_task w6.launch.py backend:=full gui_render_backend:=software
```

**关于"截不到图"**：本机 `DISPLAY=:0` 是 **Wayland（XWayland）**，`xwd`/`import`/`scrot`/`ffmpeg`
全未安装，X11 抓根窗口只会得到**全黑**（合成器不暴露窗口像素）。取真实画面请用 Gazebo
**自己的** Screenshot 插件（`/gui/screenshot` 服务，从 3D 视图相机取帧，不经过合成器）：

```bash
# 世界 SDF 的 <gui> 块覆盖了发行版默认 gui.config，不含 Screenshot 插件 → 先派生一份
python3 scripts/demo/gui_capture.py derive-config \
    --world install/agc_sim/share/agc_sim/worlds/agc_world.sdf --out /tmp/gui.config
AGC_GUI_CONFIG=/tmp/gui.config ./run_demo.sh      # 运行期间才能取帧
python3 scripts/demo/gui_capture.py snap --out /tmp/shot.png
```

> **headless 截不了图**：`gz -s` 不启动渲染客户端，**不生成画面**。截图必须带 GUI。

## 6. 冒烟测试某组失败，但看不出原因

**症状**：`./run_demo.sh test` 报某组 FAIL，默认只打最后 30 行。

**处置**：

```bash
./run_demo.sh test --list                 # 看有哪些组
./run_demo.sh test --verbose --only docs  # 只跑一组、打完整输出
```

组名：`geometry`（几何派生链）/ `messages`（9 消息 ABI）/ `docs`（文档断链）/
`index`（ADR + 脚本索引）/ `offline`（`scripts/tests` 离线单测）。

> 冒烟门槛**只读、不启仿真**。需要整链环境的 57 个核查是**验收**，语义不同，
> 见 [tests/README](../tests/README.md)。

## 7. `create entities failed: participant: 255` / `air_odom=0`

**症状**：日志里 PX4 侧报 `create entities failed: participant: 255`，随后
`start rejected: air_hover_timeout` 或 `air_odom=0`。

**原因**：启动期 DDS 发现图繁忙，该 agent 的**首个** participant 创建超过 PX4 硬编码的 1 s 预算。
`air_odom=0` 是它的**下游后果**，不是 EKF / 起飞时序问题——**不要**先去查 EKF。

**处置**：按[启动前检查](conventions/整链排障速查.md#preflight)清场（含桥 / tf 孤儿）后重跑。
默认 25/35 错峰已是主修复（[ADR-0094](adr/0094-uxrce-participant-warmup-and-px4-stagger.md)），
**不要**把 own PX4 改回 12 s、也不要用 runner 重试代替修复。

## 8. 演示成功了，但这个"成功"到底算什么

**症状**：终态 `TRACKING_SUCCESS`，想确认能不能说"拦截成功"。

**答案**：**不能**。`TRACKING_SUCCESS` = **"抵近并持续跟踪"**（阶段 A），
**不得**表述为"拦截完成"（[契约 C8](ROS2迁移交接文档.md#hard-constraints) 与
[终态语义](ROS2迁移交接文档.md#terminal-semantics)）。
阶段 B 的拦截另有终态 `INTERCEPT_CONFIRMED`（`CAPTURE_NET` 物理捕获 / `JAM_*` 行为级干扰）。

另外两个口径也要一起说清，否则结论会被误读：

- 默认 `observe_yaw_mode=target` 是**显式 oracle 指向臂**（机头对准真值方位），
  **不代表**真实视觉识别（[P1-2 观测指向臂](plan/p1-2-一键演示入口.md#p1-2-oracle-arm)）；
- 默认 `perception_path=truth`，感知是**真值派生**，不是从像素识别出来的
  （[ADR-0020](adr/0020-perception-as-truth-derived-simulation.md)）。

完整的能力边界见 [README 的「已知边界」](../README.md#已知边界当前能力范围)。
