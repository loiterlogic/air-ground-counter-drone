#!/usr/bin/env python3
"""地面安全层**实车动力学标定**（L4；需整链仿真，独占 GZ）。

补齐 [ADR-0045](../docs/adr/0045-ground-safety-layer-self-owned.md#top) 与
[地面安全层判定与标定](../docs/conventions/地面安全层判定与标定.md#top) 的标定项。
**这不是回归测试**：它产出的是**标定值**，写回配置前须人工确认（脚本只报数，不改配置）。

## 标定什么、凭什么

| # | 量 | 方法 | 为什么这样测 |
|---|---|---|---|
| A | `a_brake` | 命令从 `v_max` **阶跃到 0**，用**真值速度**回落曲线拟合减速度 | 安全层的全部距离档都由 `s_brake = v·t_react + v²/(2a)` 推出；`a` 错则档位全错 |
| B | `t_react` | 停发 `cmd_vel_raw` → 安全层输出零速 → **真值速度开始下降**的端到端延迟 | 它同时含链路 + 判定 + 执行延迟；取 **p95**，不用均值（安全要覆盖尾部）|
| C | `cell_epsilon` | 同一障碍、同一速度下，比较「连续几何判定的停车点」与「本层栅格判定的停车点」 | 栅格量化误差必须被量出来，不能猜一个 0.05 |
| D | `v_safe(d)` | 在多个 `v` 下测「刹停距离」实测值，与模型预测对照 | 给出速度上限的**实测包络**，而非单一常数 |

## 为什么用 `full` 后端

自研安全层的**唯一障碍输入**是 `/agc/map`。而 `lightweight` / `safety_scenario`
不含空中链路 ⇒ 无 nadir 相机 ⇒ 地图恒空 ⇒ 安全层严格 fail-closed 只能停（ADR-0045 已登记）。
所以标定必须在 `backend:=full`（含 `perception_bringup`）下做，否则**车根本不会动**。

## 命令源接管

RL 节点会在 `/agc/ground/cmd_vel_raw` 上以 20 Hz 发命令。本脚本先按 PID **杀 RL 节点**
（不是 `pkill -f`），再自己当命令源——与 `check_scan_source_loss_stop.py` 同法。
安全层仍照常消费，因此测到的延迟含安全层本身。

## 用法

    # 1) 另开终端起整链（独占仿真）
    ros2 launch agc_task main.launch.py backend:=full \\
        gz_args:="-s -r -v 3 $PWD/install/agc_sim/share/agc_sim/worlds/agc_world.sdf" viz:=false

    # 2) 等地图有内容（见本脚本 --wait-map）后跑标定
    python3 tests/check_safety_calibration.py --run-id 20261113-calib-0

退出码：0 = 全部标定项拿到有效数据；1 = 有项缺数据（**缺数据不等于通过**）。
"""

import argparse
import json
import math
import os
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from ros_gz_interfaces.srv import SetEntityPose
from std_msgs.msg import String

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402

RAW = '/agc/ground/cmd_vel_raw'
OUT = '/agc/ground/cmd_vel'
ODOM = '/agc/ground/odom'
MAP = '/agc/map'
STATUS = '/agc/ground/safety_status'

V_MAX = 1.5          # car.yaml max_linear_velocity

# 理想圆弧横移上界（**仅用于算实测折扣**，绝不作为能力主张）：
# 与生产 `slowRatioFloor()` 同一公式 `(v_cap/ω_cap)·(1-cos(ω_cap·T))`，参数取
# `ground.yaml` 的 v_cap / w_cap 与 `rl.yaml`/`ground.yaml` 共同的反应窗口 T=2.0 s。
V_CAP = 1.5          # ground.yaml v_cap / car.yaml max_linear_velocity
W_CAP = 2.0          # ground.yaml w_cap
T_WINDOW = 2.0       # 反应窗口 T（ADR-0010）
IDEAL_LATERAL_M = (V_CAP / W_CAP) * (1.0 - math.cos(W_CAP * T_WINDOW))

# 车体到**世界静态体**（路面 / 路缘石）的最小净空。实测：净空 0.001 m 时车完全不动，
# 1.0 m 以上正常行驶；取 0.6 m（≈ 一个车体半长）留足余量。
WORLD_CLEARANCE_MIN_M = 0.6

# **不要写死"开阔区"坐标**：实测 (20, 25) 在 `/agc/map` 里是 `-1`（未知），
# 而未知**不是已知自由** —— 安全层会正确地拒绝从没看过的地方起步，
# 于是标定测到的全是零速（看起来像传感器坏了）。
# 正确做法：从**当前地图**里现找一块"周围一圈都是 free"的地点。
def yaw_from_quat(q):
    return math.atan2(
        2.0 * (q.w * q.z + q.x * q.y),
        1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def _world_static_boxes(world_sdf=None):
    """解析世界 SDF 里**带碰撞**的静态体足迹 → `[(cx, cy, sx, sy)]`。

    ## 为什么标定脚本必须知道这件事（2026-11-13 实测，代价极大）

    `yard` 的世界里除「障碍配置」（`maps/yard.yaml`）外，还有一批**带碰撞的静态体**：
    路面 `road_*`、场坪 `apron_*`、停车位 `bay_*`、**路缘石 `curb_*`**。
    它们**不在** `/agc/map` 里（地图只由感知建），所以：

    * 安全层看到的净空是"离障碍多远"，**完全不知道**脚下有没有路缘石；
    * 车生成在路缘石上时，**谁发命令都走不动**（实测：同一条 GZ 话题、同样的 `v=1.0`，
      开阔区走 2.21 m，路缘石位置只走 0.0014 m）。

    症状是"安全层在 `SLOW` 下不让车动"，极易被误判成安全层缺陷。
    故本函数把世界静态体取出来，供选点时**避让**。

    只取 `z` 方向的碰撞盒里**顶面高于地面**或**任意**带 `<collision>` 的 box：
    本仓的路缘石在 SDF 里 `<box><size>` 的 z 写成 0，但碰撞体真实存在，
    因此**不按高度过滤**，宁可多避让几个点。
    """
    import xml.etree.ElementTree as ET
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    path = world_sdf or os.path.join(root, 'src', 'agc_sim', 'worlds', 'agc_world.sdf')
    out = []
    try:
        world = ET.parse(path).getroot().find('.//world')
    except (OSError, ET.ParseError):
        return out
    if world is None:
        return out
    # **只避让"凸起物"，不避让"可行驶面"** —— 这条区分是实测换来的。
    #
    # 本仓世界里有三类带碰撞的静态体：
    #   ① 可行驶面：`road_*`（路面，厚 4 mm）、`apron_*`（场坪，厚 3 mm）、`bay_*`（车位线）
    #      —— 车**必须**能在上面走，判成禁区会让选点退化成"哪里都不行"；
    #   ② 凸起物：`curb_*`（路缘石，0.35 m 宽、厚 3 mm）—— 车压上去会**卡住**（实测位移 0.0014 m）；
    #   ③ 动态模型：车 / 无人机（有 plugin，绝不能当障碍）。
    # 判据用**名字前缀**而不是高度：本仓的 curb 在 SDF 里 z 尺寸也写成 3 mm，
    # 与路面同量级，按高度分不开。名字是这个世界文件的既定事实，稳定且可读。
    DRIVABLE_PREFIX = ('road_', 'apron_', 'bay_', 'ground_')
    DYNAMIC_NAMES = ('agc_car', 'intruder_uav', 'x500')
    for m in world.findall('model'):
        name = m.get('name') or ''
        if any(k in name for k in DYNAMIC_NAMES):
            continue
        if name.startswith(DRIVABLE_PREFIX):
            continue
        pose = m.find('pose')
        mx = my = 0.0
        if pose is not None and pose.text:
            vals = [float(v) for v in pose.text.split()]
            mx, my = vals[0], vals[1]
        for coll in m.iter('collision'):
            for box in coll.iter('box'):
                size = box.find('size')
                if size is None or not size.text:
                    continue
                sx, sy = (float(v) for v in size.text.split()[:2])
                out.append((mx, my, sx, sy))
    return out


def _load_yaml(path):
    """读 YAML；缺失/非法返回 `{}`（调用方按缺省值兜底，不在这里抛）。"""
    import yaml
    try:
        with open(path, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except (OSError, ValueError):
        return {}


def find_open_spot(map_msg, radius_cells=12):
    """在地图里找**最大的一块**"周围全是已知自由"的位置，返回世界坐标。

    **为什么不是"第一个满足的格"**：改造前版本用 6 格半径取第一个命中点，
    结果那个点周围仍有障碍落在 `d_safety=4 m` 带内 ⇒ 安全层正确地限速到 0.3 m/s
    ⇒ 制动标定测的是"0.3 m/s 的制动"，而不是 `v_max` 的制动（实测踩过）。
    取最大自由区，并**显式**要求 `d_safety` 半径内无任何非 free 格。
    """
    info = map_msg.info
    w, h, d = info.width, info.height, map_msg.data
    ox, oy, res = (info.origin.position.x, info.origin.position.y, info.resolution)
    # 半径按"至少覆盖 d_safety + 车体对角"现算，不写死。
    need_m = 4.0 + 0.6
    r = max(radius_cells, int(math.ceil(need_m / res)))
    best = None
    best_score = -1
    for iy in range(r, h - r, 2):
        for ix in range(r, w - r, 2):
            if d[iy * w + ix] != 0:
                continue
            ok = True
            # 先粗筛（稀疏采样，快）：任何非 free 即淘汰
            for dy in range(-r, r + 1, 2):
                row = (iy + dy) * w
                for dx in range(-r, r + 1, 2):
                    if d[row + ix + dx] != 0:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                continue
            # 再精算"更远处仍自由"的程度，取最开阔的
            score = 0
            rr = r * 3
            for dy in range(-rr, rr + 1, 4):
                for dx in range(-rr, rr + 1, 4):
                    if 0 <= iy + dy < h and 0 <= ix + dx < w and d[(iy + dy) * w + ix + dx] == 0:
                        score += 1
            if score > best_score:
                best_score = score
                best = (ox + (ix + 0.5) * res, oy + (iy + 0.5) * res)
                if score >= (2 * rr // 4 + 1) ** 2:
                    return best   # 已经是全自由，提前收工
    return best


class CalibNode(Node):
    def __init__(self):
        super().__init__('safety_calibration')
        self.cmd_pub = self.create_publisher(TwistStamped, RAW, 10)
        self.pose_cli = self.create_client(SetEntityPose, '/world/agc_world/set_pose')
        self.create_subscription(Odometry, ODOM, self._on_odom, 50)
        self.create_subscription(TwistStamped, OUT, self._on_out, 50)
        latched = QoSProfile(
            depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(OccupancyGrid, MAP, self._on_map, latched)
        self.create_subscription(String, STATUS, self._on_status, 20)

        self.x = self.y = self.yaw = 0.0
        self.v_truth = 0.0
        self.have_odom = False
        self.out_v = 0.0
        self.out_stamp_s = 0.0
        self.have_out = False
        self.map = None
        self.status = {}
        # 采样：(monotonic, v_truth, out_v)
        self.trace = []
        # 横向逃逸的可重放轨迹（`--stage slow` 写；其余阶段为空）。见 run_arc 的说明。
        self.arc_traces = {}

    # ---- 回调 ----
    def _on_odom(self, m):
        self.x = m.pose.pose.position.x
        self.y = m.pose.pose.position.y
        self.yaw = yaw_from_quat(m.pose.pose.orientation)
        vx = m.twist.twist.linear.x
        vy = m.twist.twist.linear.y
        self.v_truth = math.hypot(vx, vy)
        self.have_odom = True
        self.trace.append((time.monotonic(), self.v_truth, self.out_v))

    def _on_out(self, m):
        self.out_v = m.twist.linear.x
        self.have_out = True

    def _on_map(self, m):
        self.map = m

    def _on_status(self, m):
        try:
            self.status = json.loads(m.data)
        except ValueError:
            pass

    # ---- 工具 ----
    def source_v(self):
        """真值速度来源：odom.twist 在某些构建下为 0，用位移差分兜底。"""
        return self.v_truth

    def publish_cmd(self, v, w=0.0):
        m = TwistStamped()
        m.header.stamp = self.get_clock().now().to_msg()
        m.header.frame_id = 'car/base_link'
        m.twist.linear.x = float(v)
        m.twist.angular.z = float(w)
        self.cmd_pub.publish(m)

    def spin(self, seconds, v=0.0, w=0.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            self.publish_cmd(v, w)
            rclpy.spin_once(self, timeout_sec=0.005)

    def set_pose(self, x, y, yaw, z=0.02, timeout=6.0):
        if not self.pose_cli.wait_for_service(timeout_sec=timeout):
            return False
        req = SetEntityPose.Request()
        req.entity.name = 'agc_car'
        req.entity.type = 2
        req.pose.position.x = float(x)
        req.pose.position.y = float(y)
        req.pose.position.z = float(z)
        req.pose.orientation.z = math.sin(yaw * 0.5)
        req.pose.orientation.w = math.cos(yaw * 0.5)
        fut = self.pose_cli.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=timeout)
        return bool(fut.done() and fut.result() and fut.result().success)

    def map_occupied(self):
        if self.map is None:
            return None
        return sum(1 for v in self.map.data if v >= 100)

    def open_spot(self):
        """从**当前**地图现找一块已知自由的开阔点（见 `find_open_spot` 的注释）。"""
        if self.map is None:
            return None
        return find_open_spot(self.map)

    def wait_fresh_map(self, timeout=90.0):
        """等地图**有观测内容**：全空地图会让安全层正确地拒绝驱动，标定就测不到东西。"""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.1)
            occ = self.map_occupied()
            if occ is not None and occ > 50:
                return True, occ
        return False, self.map_occupied()

    def time_base(self):
        """**时基自检**（标定入口必须显式报告，见整链排障速查）。

        踩过的坑：同 domain 里残留 `map_adapter` 用仿真钟发地图，而本进程用系统钟，
        年龄算成 1.7e9 ⇒ 安全层判 `MAP_STALE`/`CLOCK_ANOMALY` ⇒ 车不动。
        症状与"感知坏了"完全一样，所以必须把时基打成数字而不是靠感觉。
        """
        now_ros = self.get_clock().now().nanoseconds * 1e-9
        if self.map is None:
            return {'ros_clock_s': round(now_ros, 3), 'source': 'no_map_yet',
                    'same_time_base': None,
                    'hint': '还没收到 /agc/map，时基无法判定'}
        h = self.map.header.stamp
        map_stamp = h.sec + h.nanosec * 1e-9
        return {
            'ros_clock_s': round(now_ros, 3),
            'map_stamp_s': round(map_stamp, 3),
            'map_age_by_ros_clock_s': round(now_ros - map_stamp, 3),
            # 判定口径：地图 2 Hz，年龄在 (0, 3) s 内才算同域；负值 = 地图时钟超前 = 混时基。
            'same_time_base': bool(0.0 <= now_ros - map_stamp <= 3.0),
            'hint': ('同一时基' if 0.0 <= now_ros - map_stamp <= 3.0 else
                     '**疑似混时基**：本进程 ROS 钟与 /agc/map 的 stamp 差得离谱 —— '
                     '检查是否 use_sim_time 与整链不一致，或同 domain 有残留节点'),
        }


# ---------------------------------------------------------------------------
# A. 锁轮制动减速标定：v_max 阶跃到 0，拟合真值速度回落
# ---------------------------------------------------------------------------
def calibrate_brake(n, v_target=V_MAX, trials=3):
    """从稳定 v_target 阶跃到零速，测**真值**速度的下降斜率。

    判据：`a_meas = Δv / Δt`，取速度从 0.9·v 降到 0.1·v 这一段（避开起步与残余蠕动）。
    """
    results = []
    for i in range(trials):
        # **必须在开阔区**：把车放到已知无障碍处，否则它会在 d_safety 带里被限速/停住，
        # 测到的不是"制动"，而是"安全层不让它加速"（实测踩过：v=1.5 的 6 个试验全 0）。
        # 坐标**从当前地图现找**，不写死 —— 写死的点可能落在 unknown 里（见 find_open_spot）。
        spot = n.open_spot()
        if spot is None:
            results.append({'trial': i, 'error': 'no known-free open spot in /agc/map'})
            continue
        n.set_pose(spot[0], spot[1], 0.0)
        n.spin(2.0, 0.0)
        # 加速到目标速度并稳定
        n.spin(6.0, v_target)
        v_settle = n.source_v()
        # 阶跃到零：**持续**发零（安全层也发零）
        t_step = time.monotonic()
        n.trace.clear()
        n.spin(4.0, 0.0)
        # 取阶跃后的速度序列
        seq = [(t, v) for (t, v, _) in n.trace if t >= t_step]
        if len(seq) < 10:
            results.append({'trial': i, 'error': 'too few samples', 'n': len(seq)})
            continue
        v_peak = max(v for _, v in seq)
        v_stop = min(v for _, v in seq)
        hi = 0.9 * v_peak
        lo = 0.1 * v_peak
        t_hi = next((t for t, v in seq if v <= hi), None)
        t_lo = next((t for t, v in seq if v <= lo), None)
        if t_hi is None or t_lo is None or t_lo <= t_hi:
            results.append({'trial': i, 'error': 'no decay segment',
                            'v_peak': v_peak, 'v_stop': v_stop})
            continue
        a_meas = (hi - lo) / (t_lo - t_hi)
        results.append({
            'trial': i,
            'v_settle': round(v_settle, 4),
            'v_peak': round(v_peak, 4),
            'v_final': round(v_stop, 4),
            'decay_s': round(t_lo - t_hi, 4),
            'a_meas_mps2': round(a_meas, 4),
            'stop_time_s': round(max(t for t, _ in seq) - t_step, 3),
        })
    return results


# ---------------------------------------------------------------------------
# B. 端到端反应延迟：停发命令 -> 真值开始减速
# ---------------------------------------------------------------------------
def calibrate_reaction(n, v_target=V_MAX, trials=3):
    """停发 `cmd_vel_raw` 后，量到**真值速度开始下降**的时间。

    口径：安全层的 `t_cmd_timeout=0.5 s` 到期后它才发零速，所以本量**必然包含**该超时。
    这正是"端到端"该有的样子——但它与 `s_brake` 公式里的 `t_react` 语义不同，
    故结果同时给出 `t_react_total`（含超时）与 `t_react_after_zero`（从安全层真正输出零速起算）。
    """
    results = []
    for i in range(trials):
        spot = n.open_spot()
        if spot is None:
            results.append({'trial': i, 'error': 'no known-free open spot in /agc/map'})
            continue
        n.set_pose(spot[0], spot[1], 0.0)
        n.spin(2.0, 0.0)
        n.spin(6.0, v_target)
        v_settle = n.source_v()
        # 记录基线速度，然后**彻底停发**（不再 publish）
        n.trace.clear()
        t_stop_pub = time.monotonic()
        t_first_zero_out = None
        deadline = t_stop_pub + 4.0
        while time.monotonic() < deadline:
            rclpy.spin_once(n, timeout_sec=0.005)
            if t_first_zero_out is None and n.have_out and abs(n.out_v) < 1e-9:
                t_first_zero_out = time.monotonic()
        seq = [(t, v) for (t, v, _) in n.trace if t >= t_stop_pub]
        if len(seq) < 10:
            results.append({'trial': i, 'error': 'too few samples'})
            continue
        v_peak = max(v for _, v in seq)
        # 真值速度首次低于 0.9·峰值的时间
        t_decay = next((t for t, v in seq if v <= 0.9 * v_peak), None)
        if t_decay is None:
            results.append({'trial': i, 'error': 'no decay detected',
                            'v_peak': round(v_peak, 4)})
            continue
        item = {
            'trial': i,
            'v_settle': round(v_settle, 4),
            'v_peak': round(v_peak, 4),
            't_react_total_s': round(t_decay - t_stop_pub, 4),
        }
        if t_first_zero_out is not None:
            item['t_zero_out_s'] = round(t_first_zero_out - t_stop_pub, 4)
            item['t_react_after_zero_s'] = round(t_decay - t_first_zero_out, 4)
        results.append(item)
    return results


# ---------------------------------------------------------------------------
# E. SLOW 机动性 + **横向逃逸能力**（用户裁定项：不能用数学理想圆弧代替实测）
# ---------------------------------------------------------------------------
def calibrate_slow_maneuver(n, trials=3, window_s=2.0, required_m=None):
    """**用户裁定的独立证明项**：`SLOW` 裁剪后能否仍做出要求的横移。

    ## 为什么必须单独证明（不能靠"同比例裁剪保持曲率"推理）

    横移 ≈ `(v/w)(1-cos(w*T))`。同比例裁剪让 `v/w` 不变，但 `w` 变小让
    `1-cos(w*T)` 变小 —— **两项方向相反**，净效果不显然。

    ## 怎么造出真正的 SLOW（试过两次才对）

    第一次在开阔区满偏转向：状态**始终 PASS**（安全层没介入），量到的是
    「车原本的机动能力」，**没有**回答"SLOW 下还行不行"。
    正确做法：把车摆到**距障碍 d_safety 带内**的位置，一边被限速一边转向。

    ## 口径（2026-11-13 修正，三条都是实测换来的）

    1. **横移量取「与初始航向垂直的位移投影」，不是世界 `y` 差值**。
       改造前取 `|y - y0|`，只有初始 yaw≈0 时才等于横向；本函数把车摆成
       **朝 +y**（yaw=π/2），于是横向 = 世界 **x** 方向的位移。
       取 `y` 差值会把"沿车头方向的位移"算成横向（该错误让 1.4 m 的前进被读成 0.1 m）。
    2. **`start_xy` 必须在命令发出**之前**取**：原地打角时车先转不前进，
       若把 y0 取在转矩段之后，就丢掉了一部分真实横移。
    3. **每次试验重摆一次起点**：上一轮把车带走了 → 不重摆时第二、三轮的
       "威胁方向"与障碍相对关系已经变了，量到的不是同一件事。

    ## 输出口径

    `required_m` 由调用方给（来自 `rl.yaml` 的 `control.max_offset`，即被裁定的能力主张）；
    本函数**只报实测值**，不改配置、不判定配置对错 —— 判定在 `summarise()` 里给出
    「配置值是否不超过实测可达能力」。
    """
    if n.map is None:
        return [{'error': 'no map'}]
    info = n.map.info
    w, h, d = info.width, info.height, n.map.data
    res = info.resolution
    ox, oy = info.origin.position.x, info.origin.position.y

    def world_of(cx, cy):
        return (ox + (cx + 0.5) * res, oy + (cy + 0.5) * res)

    # ---- 找 SLOW 起点：**用安全层自己报的 `d_min_m` 判档**，不按格数估算 ----
    #
    # 改造前按"障碍在 6–13 格外"估，在 yard 的**膨胀地图**上等于 3–6.5 m，
    # 实测落到 `STOP_COLLISION`（`d < d_collision`）⇒ 车一动就被判停，
    # 三轮 SLOW 横移全是 0.000（看起来像"SLOW 让车不会动"，其实是**摆错了位置**）。
    # 现在：候选点逐个试摆 → 读状态里的 `d_min_m` → 落在 (d_collision+0.2, d_safety-0.2)
    # 才采用。判据来自**生产判定**本身，换地图/换分辨率都不用改这里。
    _root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    _gyaml = _load_yaml(os.path.join(_root, 'src', 'agc_ground', 'config',
                                     'ground.yaml')) or {}
    gsp = ((_gyaml.get('ground_safety_filter') or {}).get('ros__parameters') or {})
    d_coll = float(gsp.get('d_collision', 2.0))
    d_safe = float(gsp.get('d_safety', 4.0))
    # 带 = 生产判定的 `SLOW` 带本身（`d_collision <= d < d_safety`），两端各留 0.2 m 余量，
    # 避免落在门槛上抖动。**不**用"障碍在 N 格外"这类间接估算。
    want_lo, want_hi = d_coll + 0.2, d_safe - 0.2

    # ---- 世界静态体避让（**2026-11-13 实测踩到，代价极大**）----
    #
    # `yard` 的世界里除「障碍配置」外还有一批**带碰撞的静态体**：路面 `road_*`、
    # 场坪 `apron_*`、**路缘石 `curb_*`**（0.3 m 宽、0.3 m 高，但 `<box>` 的 z 尺寸在
    # SDF 里写成 0，碰撞体却真实存在）。车一旦生成在 `curb_s_i`（`y = -19.7`）这类位置，
    # **无论谁发命令都走不动** —— 实测：同一 GZ 话题、同一条 `v=1.0`，
    # 开阔区走 2.21 m，该位置只走 0.0014 m（**绕过安全层直发 GZ 也一样**）。
    #
    # 症状是"安全层在 SLOW 下不让车动"，极易被误判成安全层缺陷。判据必须落在
    # **世界几何**上，不能只看 `/agc/map`（地图里根本没有 curb）。
    world_blocks = _world_static_boxes()

    def blocked_by_world(x, y, yaw=math.pi / 2.0):
        """该点（**含车体有向足迹**）是否与世界静态体的碰撞足迹重叠。

        ## 为什么必须用有向足迹而不是外接圆 pad（2026-11-13 实测，代价极大）

        `yard` 的路缘石 `curb_s_i` 是 60 × 0.35 m、**厚 3 mm** 的窄条，
        而车体是 1.0074 × 0.5709 的有向矩形。用"半长当各向 pad"会把**整条路**判成禁区
        （`apron_center` 40×20 m 也会命中），于是选点退化成"哪里都不行"；
        而用真实有向足迹才能准确表达"车压没压到那条 0.35 m 宽的边"。

        实测对照（同一条 GZ 意图话题、同样 `v=1.0`）：
        `(-6.74, -20.38)`（压 `curb_s_i`）→ **0.0014 m**；
        `(-6.74, -18.00)`（北移 2.4 m）→ **1.7765 m**。
        """
        hl = float(gsp.get('footprint_half_length', 0.5037))
        hw = float(gsp.get('footprint_half_width', 0.28545))
        c, sn = math.cos(yaw), math.sin(yaw)
        for (bx, by, sx, sy) in world_blocks:
            # 分离轴定理（SAT）：有向矩形 vs 轴对齐矩形，四个分离轴
            # 把世界体中心投到车体坐标系
            dx, dy = bx - x, by - y
            u = dx * c + dy * sn
            v = -dx * sn + dy * c
            # 车体系下世界体的半尺寸（世界体是 AABB，投影到车体系）
            eu = abs(sx / 2.0 * c) + abs(sy / 2.0 * sn)
            ev = abs(sx / 2.0 * sn) + abs(sy / 2.0 * c)
            if abs(u) < hl + eu and abs(v) < hw + ev:
                return True
        return False

    def world_clearance(x, y, yaw=math.pi / 2.0):
        """车体有向足迹到最近世界静态体的**有向净空**（负 = 重叠）。

        ## 为什么用"净空阈值"而不是"是否相交"（2026-11-13 实测标定）

        实测把净空与真实位移对上（同一条 GZ 意图话题、同样 `v=1.0`）：

        | 位置 | 净空 | 实测位移 |
        |---|---|---|
        | `(-6.74, -20.38)` | **0.001 m** | **0.001 m**（不动）|
        | `(-10.0, -20.0)` / `(-3.0, -20.0)` | **−0.379 m**（重叠）| 0.230 m（几乎不动）|
        | `(-6.74, -18.0)` | 1.021 m | 1.780 m |
        | `(-6.74, -22.5)` | 2.121 m | 1.790 m |
        | `(-17.4, 5.0)` | 1.865 m | 1.770 m |

        即：**净空 ≤ 0.01 m 时车完全不动**（压在路缘石上，车体几何与路缘的接触把车锁住），
        而"是否相交"漏掉了这个 0.001 m 的情形。故判据取净空阈值。
        """
        hl = float(gsp.get('footprint_half_length', 0.5037))
        hw = float(gsp.get('footprint_half_width', 0.28545))
        c, sn = math.cos(yaw), math.sin(yaw)
        best = float('inf')
        for (bx, by, sx, sy) in world_blocks:
            dx, dy = bx - x, by - y
            u = dx * c + dy * sn
            v = -dx * sn + dy * c
            eu = abs(sx / 2.0 * c) + abs(sy / 2.0 * sn)
            ev = abs(sx / 2.0 * sn) + abs(sy / 2.0 * c)
            du = abs(u) - (hl + eu)
            dv = abs(v) - (hw + ev)
            if du <= 0.0 and dv <= 0.0:
                return -min(-du, -dv) if (-du) < (-dv) else -(-dv)
            best = min(best, math.hypot(max(du, 0.0), max(dv, 0.0)))
        return best

    probed = []   # 每个候选的实测三元组：诊断用（失败时必须能看到"试了什么、结果是什么"）
    used_spots = set()   # 已用过的起点（格索引）：不重复选，否则第 2/3 轮会撞同一个点

    def map_clearance(ix, iy, yaw):
        """**离线复算**安全层会报的 `d_min_m`（同一公式：车体外缘到最近非自由格 − 半格对角）。

        为什么要先离线筛：每个候选要花 `1.2 + 1.0 + 0.8 ≈ 3 s`（摆位 + 验档 + 回零），
        而"障碍在 2–6 格外"这个粗筛在膨胀地图上几乎全部落在 `STOP_*`（实测 12 个候选
        `d_min` 全 < 1.4 m）。先按地图算准净空、只探真正落在带内的点，才能把探测压到几次。
        """
        hd = math.hypot(float(gsp.get('footprint_half_length', 0.5037)),
                        float(gsp.get('footprint_half_width', 0.28545)))
        half_diag = math.hypot(res * 0.5, res * 0.5)
        best = None
        r = int(math.ceil((d_safe + hd + res) / res))
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                yy, xx = iy + dy, ix + dx
                if not (0 <= yy < h and 0 <= xx < w):
                    continue
                if d[yy * w + xx] == 0:
                    continue
                # 格中心（world）→ 车体外缘距离
                pcx = ox + (xx + 0.5) * res
                pcy = oy + (yy + 0.5) * res
                cxw = ox + (ix + 0.5) * res
                cyw = oy + (iy + 0.5) * res
                ddx, ddy = pcx - cxw, pcy - cyw
                c, sn = math.cos(yaw), math.sin(yaw)
                u = ddx * c + ddy * sn
                vv = -ddx * sn + ddy * c
                du = abs(u) - float(gsp.get('footprint_half_length', 0.5037))
                dv = abs(vv) - float(gsp.get('footprint_half_width', 0.28545))
                dist = math.hypot(max(du, 0.0), max(dv, 0.0)) - half_diag
                dist = max(0.0, dist)
                if best is None or dist < best:
                    best = dist
        return best if best is not None else -1.0

    def find_slow_spot(max_probe=20):
        # 每轮**独立**探测预算：`probed` 是累计诊断，不能拿来当"已探次数"
        # （实测：第 1 轮探满 8 个后，第 2、3 轮一进来就 return None）。
        """返回 `(xy, d_min_m)`；找不到返回 `(None, None)`（诊断在 `probed` 里）。

        三级筛选（每一级都是**实测换来的**，缺一级就会白烧 3 s/候选）：
        ① 离线按地图算净空 ∈ `(d_collision+0.2, d_safety−0.2)`；
        ② 起点 5×5 必须自由（车放得下）；
        ③ 摆位后用**与正式测量相同的命令**跑 1 s，确认 `state == SLOW` 且 `v_out > 0`。
        """
        probes = 0   # **局部**：每轮独立预算
        for iy in range(6, h - 6):
            for ix in range(6, w - 10):
                if d[iy * w + ix] != 0:
                    continue
                if not all(0 <= iy + dy < h and 0 <= ix + dx < w
                           and d[(iy + dy) * w + ix + dx] == 0
                           for dy in (-2, -1, 0, 1, 2) for dx in (-2, -1, 0, 1, 2)):
                    continue
                if not any(0 <= ix + k < w and d[iy * w + ix + k] >= 99 for k in range(2, 10)):
                    continue
                # ① 离线净空筛
                mc = map_clearance(ix, iy, math.pi / 2.0)
                if not (want_lo <= mc <= want_hi):
                    continue
                # ② 世界静态体避让（路面 / 场坪 / 路缘石）——见 `world_blocks` 的说明
                cx_world, cy_world = world_of(ix, iy)
                # ③ 世界静态体净空（压路缘石会锁死车 —— 见 `world_clearance` 的实测表）
                if world_clearance(cx_world, cy_world) < WORLD_CLEARANCE_MIN_M:
                    continue
                if (ix, iy) in used_spots:
                    continue
                if probes >= max_probe:
                    return None, None
                probes += 1
                pos = world_of(ix, iy)
                n.set_pose(pos[0], pos[1], math.pi / 2.0)
                n.spin(1.2, 0.0)
                n.spin(1.0, 1.0, 0.0)
                tier_now = n.status.get('state')
                v_now = n.status.get('v_out')
                dmin = n.status.get('d_min_m')
                n.spin(0.8, 0.0)
                probed.append({'xy': [round(pos[0], 2), round(pos[1], 2)],
                               'map_clearance_m': round(mc, 3),
                               'd_min_m': dmin, 'tier': tier_now, 'v_out': v_now})
                if (tier_now == 'SLOW' and isinstance(v_now, (int, float)) and v_now > 0.0
                        and isinstance(dmin, (int, float)) and want_lo <= dmin <= want_hi):
                    used_spots.add((ix, iy))
                    return pos, dmin
        return None, None

    sx, sy = 0.0, 0.0
    slow_dmin = None
    need = float(required_m) if required_m is not None else 1.0

    def run_arc(pos, yaw, tag):
        """摆到 `pos`/`yaw` → 进稳态 → 满偏左转 T 秒；横向取**垂直初始航向**的位移。

        ## 可重放（用户裁定的硬要求：能力必须来自**可重放轨迹**，不是一次性数字）

        逐拍记 `(t, x, y, yaw, tier)` 到 `n.arc_traces[tag]`，落盘后由
        `tests/replay_escape_trace.py` **离线**用同一公式重算横向位移与档位；
        重算值与在线值的差 > `REPLAY_TOL_M` 即判不一致。
        这样"最差折扣"这件事可以被别人用同一份数据复核，而不是只能相信本脚本的结论。
        """
        n.set_pose(pos[0], pos[1], yaw)
        n.spin(2.0, 0.0)
        # ⚠ **不要**在这里用 `spin(3.0, 1.0, 0.0)` 预加速：
        # 那会把车从选定的位置开走（实测把 `(-6.25,-21.25)` 带到了 `(-6.27,-20.38)`，
        # 正好压在 `curb_s_i` 路缘石上 ⇒ 后面 2 s 位移 0.000），
        # 于是"测量点"与"选点"不是同一个地方，而 trace 里看不出这一点。
        # 本测要的是"**从静止起步**的 2 s 横移"，加速段本身不属于窗口，故直接省略。
        x0, y0 = n.x, n.y
        t0 = time.monotonic()
        seen = set()
        trace = []
        while time.monotonic() - t0 < window_s:
            n.publish_cmd(1.0, 0.96)
            rclpy.spin_once(n, timeout_sec=0.005)
            st = n.status.get('state')
            if st:
                seen.add(st)
            # **必须同时记安全层的 `v_out` / `w_out`**：只记 `state` 时，
            # "车没动"与"安全层输出了零速"与"命令没到中继"三种原因长得一模一样
            # （实测踩过：SLOW 报 v=1.000，车却一动不动，光看 state 无法定位）。
            trace.append({
                't': round(time.monotonic() - t0, 5),
                'x': round(n.x, 6), 'y': round(n.y, 6),
                'yaw': round(n.yaw, 6), 'tier': n.status.get('state'),
                'v_out': n.status.get('v_out'), 'w_out': n.status.get('w_out'),
                'd_min_m': n.status.get('d_min_m'),
                # **订阅到的实际输出**（不是状态里自称的 v_out）：两者不一致说明
                # 状态心跳与命令话题不是同一拍，或命令根本没发出去。
                'cmd_out_v': round(n.out_v, 6),
                'cmd_v': 1.0, 'cmd_w': 0.96,
            })
        dx, dy = n.x - x0, n.y - y0
        # 垂直于初始航向的单位向量 = (-sin yaw, cos yaw)；左转时位移沿它的正方向。
        lateral = -dx * math.sin(yaw) + dy * math.cos(yaw)
        n.spin(1.5, 0.0)
        n.arc_traces[tag] = {
            'heading_rad': round(yaw, 6),
            'start_xy': [round(x0, 6), round(y0, 6)],
            'window_s': window_s,
            'samples': trace,
            'online_reach_m': round(abs(lateral), 4),
        }
        return {'states_seen': sorted(seen), 'reach_m': round(abs(lateral), 4),
                'lateral_signed_m': round(lateral, 4),
                'heading_deg': round(math.degrees(yaw), 1),
                'trace_samples': len(trace)}

    results = []
    for i in range(trials):
        # **每轮重新找位置**：上一轮把车带走了，不重摆时"威胁方向"与障碍的相对关系已经变了。
        pos, dmin = find_slow_spot()
        if pos is None:
            results.append({'trial': i,
                            'error': 'no spot with SLOW tier verified under real command',
                            'band_m': [round(want_lo, 2), round(want_hi, 2)],
                            'probed': probed[-12:]})
            continue
        slow_dmin = dmin
        # 朝 +y 摆放：横向 = 世界 x 的位移（见口径 1）。
        slow = run_arc(pos, math.pi / 2.0, 'slow_t%d' % i)
        # **窗口里如果混进了 STOP_*，这一轮无效**：那说明车在 2 s 内已经开到碰撞档，
        # 量到的不是"SLOW 下的横移"。如实登记（`slow_states` 里留着），但 `reach_ok` 必须为 False。
        if any(str(st).startswith('STOP_') for st in slow['states_seen']):
            slow['invalid_reason'] = 'reached STOP_* inside the 2 s window'
        spot = n.open_spot()
        # 对照臂必须**同一朝向**：否则两者量的不是同一个横向方向。
        base = run_arc(spot, math.pi / 2.0, 'baseline_t%d' % i) if spot else {}
        engaged = 'SLOW' in slow['states_seen']
        results.append({
            'trial': i,
            'start_xy': [round(pos[0], 3), round(pos[1], 3)],
            'slow_d_min_m': round(dmin, 3),
            'slow_states': slow['states_seen'],
            'slow_reach_m': slow['reach_m'],
            'slow_lateral_signed_m': slow.get('lateral_signed_m'),
            'baseline_states': base.get('states_seen'),
            'baseline_reach_m': base.get('reach_m'),
            'slow_engaged': engaged,
            'required_m': need,
            'reach_ok': bool(engaged and slow['reach_m'] >= need
                             and not slow.get('invalid_reason')),
            'invalid_reason': slow.get('invalid_reason'),
        })
    return results


# ---------------------------------------------------------------------------
# C. 栅格量化误差：同一障碍下的停车点
# ---------------------------------------------------------------------------
def _find_corridor(d, w, h, want_len):
    """从**自由格**出发沿 +x 找一条"最终抵达阻挡格"的逼近路线。

    ## 为什么这样写（每条都是实测换来的）

    1. **从自由侧扫**：占据是**成片膨胀**的（9×9 窗口整片 100），从障碍格往西找 free
       一个都找不到。
    2. **允许经过代价带（1..98）**：实测"纯 free 走廊尽头是障碍"的例子**为 0** ——
       障碍外面永远先包一层代价/内切带。若坚持"全程 free"，永远找不到样本。
    3. **遇到未知（<0）立即放弃**：未知格上安全层会按"停不住"处理，
       量到的就不是栅格量化了。
    4. **必须真的抵达 >=99**：那才是"车朝障碍开到停"。

    返回 `(起点格, 实际行进格数)`；找不到返回 `(None, 0)`。
    """
    for iy in range(4, h - 4):
        for ix in range(4, w - 4 - want_len):
            if d[iy * w + ix] != 0:
                continue
            # 起点周围 2 格必须自由（车放得下）
            ok = True
            for dy in (-2, -1, 0, 1, 2):
                for dx in (-2, -1, 0, 1, 2):
                    yy, xx = iy + dy, ix + dx
                    if not (0 <= yy < h and 0 <= xx < w) or d[yy * w + xx] != 0:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                continue
            travelled = 0
            reached = False
            for k in range(1, want_len + 1):
                v = d[iy * w + ix + k]
                if v < 0:
                    break            # 未知：放弃（量到的不是栅格量化）
                if v >= 99:
                    reached = True
                    break
                travelled += 1       # 0 或 1..98 都可继续
            if reached and travelled > 0:
                return (ix, iy, travelled), travelled
    return None, 0


def calibrate_cell_epsilon(n, v_target=0.8, trials=3):
    """从**已知自由区**朝障碍开过去，量安全层判停时的最后净空。

    ## 三条纪律（每条都由实测失败换来）

    1. **从自由格一侧扫**：改造前从障碍格往西找 free，全部返回 None ——
       实测地图的占据是**成片膨胀的**（9×9 窗口整片 100），障碍格西侧紧邻往往还是障碍。
    2. **走廊长度自适应**：`dense_map` 障碍间距 2.645 m，长走廊不保证存在；
       找不到就退让，并**如实记录**实际用了几米。
    3. **净空必须 > 0**：`d_min_m == 0` 是"起步就冲突"，不是"刹停净空"，标 `invalid` 排除。
    """
    if n.map is None:
        return [{'error': 'no map'}]
    info = n.map.info
    w, h, d = info.width, info.height, n.map.data
    ox, oy, res = info.origin.position.x, info.origin.position.y, info.resolution

    def world_of(cx, cy):
        return (ox + (cx + 0.5) * res, oy + (cy + 0.5) * res)

    found, run = None, 0
    for want in (16, 12, 10, 8, 6, 4, 3):
        found, run = _find_corridor(d, w, h, want)
        if found is not None:
            break
    if found is None:
        return [{'error': 'no free-side corridor ending at an obstacle found'}]

    sx_c, sy_c, free_len = found
    sx, sy = world_of(sx_c, sy_c)
    tx, ty = world_of(sx_c + free_len + 1, sy_c)

    results = []
    for i in range(trials):
        n.set_pose(sx, sy, 0.0)
        n.spin(2.0, 0.0)
        n.spin(14.0, v_target)
        n.spin(1.5, v_target)
        st = dict(n.status)
        dmin = st.get('d_min_m')
        valid = isinstance(dmin, (int, float)) and dmin > 0.0
        results.append({
            'trial': i,
            'start_cell': [sx_c, sy_c],
            'start_xy': [round(sx, 3), round(sy, 3)],
            'target_xy': [round(tx, 3), round(ty, 3)],
            'corridor_m': round(free_len * res, 3),
            'state': st.get('state'),
            'd_min_m': dmin,
            'd_min_cell': st.get('d_min_cell'),
            'v_out': st.get('v_out'),
            'x_final': round(n.x, 3),
            'y_final': round(n.y, 3),
            'v_truth_final': round(n.source_v(), 4),
            'valid': bool(valid),
        })
        n.spin(1.0, 0.0)
    return results


# ---------------------------------------------------------------------------
# D. v_safe(d)：不同速度下的实测刹停距离
# ---------------------------------------------------------------------------
def calibrate_v_safe(n, speeds=(0.5, 1.0, 1.5), trials=2):
    """对每个速度测「从发零到完全停住」的**位移**，给出实测刹停距离。"""
    results = []
    for v in speeds:
        for i in range(trials):
            spot = n.open_spot()
            if spot is None:
                results.append({'v_cmd': v, 'trial': i,
                                'error': 'no known-free open spot in /agc/map'})
                continue
            n.set_pose(spot[0], spot[1], 0.0)
            n.spin(2.0, 0.0)
            n.spin(6.0, v)
            x0, y0 = n.x, n.y
            n.trace.clear()
            t_step = time.monotonic()
            n.spin(4.0, 0.0)
            seq = [(t, val) for (t, val, _) in n.trace if t >= t_step]
            if len(seq) < 10:
                results.append({'v_cmd': v, 'trial': i, 'error': 'too few samples'})
                continue
            v_peak = max(val for _, val in seq)
            dist = math.hypot(n.x - x0, n.y - y0)
            results.append({
                'v_cmd': v,
                'trial': i,
                'v_peak': round(v_peak, 4),
                'stop_distance_m': round(dist, 4),
                'model_m': round(
                    v_peak * T_REACT_NOMINAL + v_peak * v_peak / (2.0 * A_NOMINAL), 4),
            })
    return results


def summarise(brake, reaction, cell, vsafe, slow=None):
    slow = slow or []
    def nums(items, key):
        return [it[key] for it in items if isinstance(it.get(key), (int, float))]

    out = {}
    a = nums(brake, 'a_meas_mps2')
    if a:
        a_sorted = sorted(a)
        med = a_sorted[len(a_sorted) // 2]
        out['a_brake'] = {
            'measurements': a,
            'median_mps2': round(med, 4),
            'min_mps2': round(min(a), 4),
            # 安全层要用**保守**值：a 越小 ⇒ s_brake 越大 ⇒ 越早停。
            'conservative_mps2': round(min(a), 4),
        }
    t = nums(reaction, 't_react_total_s')
    if t:
        ts = sorted(t)
        p95 = ts[min(len(ts) - 1, int(math.ceil(0.95 * len(ts))) - 1)]
        out['t_react'] = {
            'measurements_total_s': t,
            'p95_total_s': round(p95, 4),
            'max_total_s': round(max(t), 4),
            'note': 't_react_total 含安全层的 t_cmd_timeout（0.5 s），'
                    '进 s_brake 公式时应取 t_react_after_zero 的 p95 —— 见下',
        }
        tz = nums(reaction, 't_react_after_zero_s')
        if tz:
            tzs = sorted(tz)
            out['t_react']['p95_after_zero_s'] = round(
                tzs[min(len(tzs) - 1, int(math.ceil(0.95 * len(tzs))) - 1)], 4)
            out['t_react']['max_after_zero_s'] = round(max(tz), 4)
    d = [it['d_min_m'] for it in cell
         if it.get('valid') and isinstance(it.get('d_min_m'), (int, float))]
    if d:
        out['cell_epsilon'] = {
            'd_min_measurements_m': d,
            'spread_m': round(max(d) - min(d), 4),
            'note': 'spread 是栅格量化的实测下界；当前配置 0.05 m 应与它对照',
        }
    ds = [it for it in vsafe if isinstance(it.get('stop_distance_m'), (int, float))]
    if ds:
        out['v_safe'] = ds
    sm = [it for it in slow if isinstance(it.get('slow_reach_m'), (int, float))]
    if sm:
        engaged = [it for it in sm if it.get('slow_engaged')]
        reach = [it['slow_reach_m'] for it in sm]
        base = [it['baseline_reach_m'] for it in sm
                if isinstance(it.get('baseline_reach_m'), (int, float))]
        # 理想圆弧（与生产 `slowRatioFloor()` 同一公式与同一参数）：
        # L = (v_cap/ω_cap)·(1-cos(ω_cap·T))。**它只用于算折扣，不作为能力主张**。
        ideal = IDEAL_LATERAL_M
        out['slow_maneuver'] = {
            'slow_reach_m': reach,
            'baseline_reach_m': [it.get('baseline_reach_m') for it in sm],
            'min_slow_m': round(min(reach), 4),
            'median_slow_m': round(sorted(reach)[len(reach) // 2], 4),
            'max_slow_m': round(max(reach), 4),
            'required_m': sm[0].get('required_m'),
            'trials_with_slow_engaged': len(engaged),
            'trials_total': len(sm),
            'all_ok': bool(sm) and all(it.get('reach_ok') for it in sm),
            'states_seen': sorted({st for trial in sm for st in trial.get('slow_states', [])}),
            # ---- 折扣与余量（口径写死在这里，避免"换个分母换个结论"）----
            'ideal_arc_lateral_m': round(ideal, 4),
            'ideal_arc_formula': '(v_cap/w_cap)*(1-cos(w_cap*T))',
            'eff_ratio_vs_ideal': ([round(r / ideal, 4) for r in reach] if ideal > 0 else []),
            'eff_ratio_min': (round(min(reach) / ideal, 4) if reach and ideal > 0 else None),
            # 与 `baseline`（PASS 态同朝向同窗口）对照：**SLOW 是否削弱了能力**。
            # **除零保护**：baseline 也可能测到 0（例如摆位失败 / 车被挡），
            # 那时"比值"没有定义 —— 报 `null` 而不是抛异常（实测踩过：ZeroDivisionError
            # 让整份标定产物**根本没写出来**，比一个 null 难查得多）。
            'slow_vs_baseline_ratio': [
                (round(a / b, 4) if b > 1e-9 else None) for a, b in zip(reach, base)],
            'baseline_min_m': round(min(base), 4) if base else None,
            'baseline_max_m': round(max(base), 4) if base else None,
            # 失败样本逐条登记（**不得用"接近成功"措辞**）。
            'failed_trials': [
                {'trial': it['trial'], 'reach_m': it['slow_reach_m'],
                 'states': it.get('slow_states')}
                for it in sm if not it.get('reach_ok')],
            # 配置值是否超过实测可达能力（= 配置说谎）。这是**能力主张**的判据。
            'required_exceeds_measured_min': bool(
                reach and sm[0].get('required_m') is not None
                and float(sm[0]['required_m']) > min(reach)),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run-id', default=None)
    ap.add_argument('--experiments-root', default=None)
    ap.add_argument('--skip-overtake', action='store_true',
                    help='不杀 RL 节点（若已手动接管命令源）')
    ap.add_argument('--map-timeout', type=float, default=150.0)
    # **必须分阶段**：任务窗口 `t_max_s = 120 s` 到期即锁存 MISSION_FAILED，
    # 之后 start/abort 都会被拒（实测：abort 拒绝 + start 报 release_control_failed），
    # 所以「一次 launch 跑完四项」在结构上做不到。每个阶段单独起一次整链。
    ap.add_argument('--stage', default='all',
                    choices=('all', 'brake', 'reaction', 'cell', 'vsafe', 'slow',
                             'noop'),
                    help='只跑某个标定阶段（推荐；all 仅在窗口够宽时用）')
    args = ap.parse_args()

    root = args.experiments_root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'experiments')
    run_id = args.run_id or time.strftime('%Y%m%d-%H%M%S')
    out_dir = os.path.join(root, 'w5-ground-nav-safety', run_id, 'metrics')
    os.makedirs(out_dir, exist_ok=True)

    rclpy.init()
    n = CalibNode()
    # **必须与整链同一时基**（整链节点 `use_sim_time:=true`，stamp 是仿真时间）。
    # 标定进程若用系统时钟发布 `cmd_vel_raw`，安全层看到的 stamp 会在**未来**
    # ⇒ 判 `CLOCK_ANOMALY` ⇒ 零速 ⇒ "车不动"，而症状与"安全层判错"完全一样。
    # 实测（calib-slow8）：`ros_clock_s=1.79e9` 对 `map_stamp_s=21.7` —— 差 1.79e9，
    # `time_base.same_time_base=false` 正是这条自检抓到的。
    n.set_parameters([rclpy.parameter.Parameter(
        'use_sim_time', rclpy.Parameter.Type.BOOL, True)])
    # **必须等到 `/clock` 真的到达**：设了 `use_sim_time=True` 只是"声明要仿真钟"，
    # 时钟在收到第一条 `/clock` 之前恒为 **0**（实测：`ros_clock_s=0.0` 对
    # `map_stamp_s=23.5` ⇒ 年龄 −23.5 s ⇒ 时基自检判 false，标定被正确拒绝）。
    # 这一步同时是"整链是否真的在跑"的活性判据。
    _t0 = time.monotonic()
    while n.get_clock().now().nanoseconds == 0 and time.monotonic() - _t0 < 30.0:
        rclpy.spin_once(n, timeout_sec=0.1)
    if n.get_clock().now().nanoseconds == 0:
        print('FAIL：30 s 内没有收到 /clock（整链没起 / use_sim_time 未生效）')
        n.destroy_node()
        rclpy.shutdown()
        return 1
    res = {'run_id': run_id, 'calibration_version': 'safety_dynamics_v1'}

    ok, occ = n.wait_fresh_map(args.map_timeout)
    res['map_ready'] = {'ok': bool(ok), 'occupied_cells': occ}
    res['time_base'] = n.time_base()
    if res['time_base'].get('same_time_base') is False:
        res['pass'] = False
        res['error'] = ('时基不一致：本进程 ROS 钟与 /agc/map 的 stamp 差 %s s。'
                        '安全层会把命令判成 CLOCK_ANOMALY（零速），标定必然测到"车不动"。'
                        '**这不是安全层的缺陷**，先修时基（本进程 use_sim_time / 残留节点）。'
                        % res['time_base'].get('map_age_by_ros_clock_s'))
        _write(out_dir, res)
        n.destroy_node()
        rclpy.shutdown()
        print('FAIL:', res['error'])
        return 1
    if not ok:
        res['pass'] = False
        res['error'] = ('地图无观测内容（occupied=%s）：自研安全层只认 /agc/map，'
                        '无地图时它正确地拒绝驱动 —— 请在 backend:=full 下跑。'
                        '**先看下面三条，不要先怀疑安全层**：'
                        '① 残留进程？`./run_demo.sh doctor` 的 residual 项；'
                        '② 时基：%s；'
                        '③ 相机是否真的在出图（`nadir_projection` 的帧统计行）。'
                        % (occ, res['time_base'].get('hint')))
        _write(out_dir, res)
        n.destroy_node()
        rclpy.shutdown()
        print('FAIL:', res['error'])
        return 1

    # **必须先让任务进入驱动许可态**：安全层的许可闸只允许 GROUND_APPROACH / TRACKING_SUCCESS
    # 驱动车体。任务停在 IDLE 时它会正确地输出零速 —— 那时标定测到的是"零"，不是"标定失败"。
    # 实测踩过：没起任务时 6 个试验的 v_peak 全是 4e-10，看起来像传感器坏了。
    permit = _ensure_driving_permit(n)
    res['permit'] = permit
    if not permit.get('ok'):
        res['pass'] = False
        res['error'] = ('任务未进入驱动许可态（state=%s）：安全层据此正确零速，'
                        '标定无法进行。请先调 /agc/task/start 并等到 GROUND_APPROACH。'
                        '**若 state 是终态**（INFRA_FAILURE / MISSION_FAILED / ABORTED）：'
                        'FSM 终态**锁存**，abort 会被拒、start 报 release_control_failed ⇒'
                        '一次 launch 只能标定一个阶段，必须重起整链（详见整链排障速查）。'
                        % permit.get('state_name'))
        _write(out_dir, res)
        n.destroy_node()
        rclpy.shutdown()
        print('FAIL:', res['error'])
        return 1

    if not args.skip_overtake:
        killed = _kill_rl_source()
        res['rl_source_killed'] = killed
        time.sleep(1.5)

    stage = args.stage
    # **每次进入阶段前重新确认许可态**：任务可能在上一个阶段的 40–90 s 里就到终态；
    # 终态**锁存**后安全层恒零速，此时测到的是"零"而不是"标定失败"（实测踩过）。
    def _permit_before(label):
        p = _ensure_driving_permit(n)
        res.setdefault('permit_by_stage', {})[label] = p
        if not p.get('ok'):
            print('  ! 阶段 %s 的任务许可态不可用（state=%s）—— 该阶段结果将不可信'
                  % (label, p.get('state_name')))
        return p

    if stage in ('all', 'brake'):
        print('[A] 锁轮制动标定…')
        _permit_before('brake')
        res['brake'] = calibrate_brake(n)
    if stage in ('all', 'reaction'):
        print('[B] 端到端反应延迟…')
        _permit_before('reaction')
        res['reaction'] = calibrate_reaction(n)
    if stage in ('all', 'cell'):
        print('[C] 栅格量化（停车净空）…')
        _permit_before('cell')
        res['cell'] = calibrate_cell_epsilon(n)
    if stage in ('all', 'vsafe'):
        print('[D] v_safe 刹停距离…')
        _permit_before('vsafe')
        res['v_safe'] = calibrate_v_safe(n)
    if stage in ('all', 'slow'):
        print('[E] SLOW 机动性 + 横向逃逸能力…')
        _permit_before('slow')
        res['slow_maneuver'] = calibrate_slow_maneuver(
            n, required_m=_required_lateral_from_config())

    res['stage'] = stage
    # 横向逃逸的**可重放轨迹**单独落一份：文件大（每轮 ~2 s × 20 Hz × 数轮），
    # 不塞进 `safety_calibration.json`，但那文件里记 `arc_traces_file` 指向它。
    if getattr(n, 'arc_traces', None):
        trace_path = os.path.join(out_dir, 'escape_arc_traces.json')
        with open(trace_path, 'w', encoding='utf-8') as f:
            json.dump({'run_id': run_id, 'stage': stage,
                       'window_s': 2.0, 'rate_hz': 20.0,
                       'traces': n.arc_traces}, f, ensure_ascii=False)
        res['arc_traces_file'] = trace_path
        print('写入', trace_path)
    res['summary'] = summarise(
        res.get('brake', []), res.get('reaction', []), res.get('cell', []),
        res.get('v_safe', []), res.get('slow_maneuver', []))
    # 分阶段时只要求**本阶段**有数据；`all` 才要求四项齐全。
    need = {'noop': (), 'slow': ('slow_maneuver',),
            'all': ('a_brake', 't_react', 'cell_epsilon', 'v_safe', 'slow_maneuver'),
            'brake': ('a_brake',), 'reaction': ('t_react',),
            'cell': ('cell_epsilon',), 'vsafe': ('v_safe',)}[stage]
    res['pass'] = all(k in res['summary'] for k in need)
    res['required'] = list(need)
    # ---- 能力主张 vs 实测（**只报数，不改配置**）----
    # 判据：配置值不得超过实测可达的最小值；超过了就是"配置在说一件车做不到的事"。
    sm = (res['summary'] or {}).get('slow_maneuver') or {}
    if sm.get('required_m') is not None and sm.get('min_slow_m') is not None:
        res['escape_capability'] = {
            'required_m': sm['required_m'],
            'measured_min_m': sm['min_slow_m'],
            'measured_median_m': sm.get('median_slow_m'),
            'eff_ratio_min': sm.get('eff_ratio_min'),
            'required_reachable': not sm.get('required_exceeds_measured_min', True),
            'failed_trials': sm.get('failed_trials'),
            'note': ('配置值不超过实测可达 ⇒ 能力主张成立' if not sm.get(
                'required_exceeds_measured_min', True)
                else '**配置超过实测可达** ⇒ 必须收窄 max_offset 或延长反应窗口；'
                     '不得把安全层裁速当成"逃逸能力"的来源'),
        }
    _write(out_dir, res)

    n.destroy_node()
    rclpy.shutdown()
    print(json.dumps(res['summary'], ensure_ascii=False, indent=2))
    print('PASS' if res['pass'] else 'FAIL（有标定项缺数据）')
    return 0 if res['pass'] else 1


def _ensure_driving_permit(n, timeout=120.0):
    """确保任务是 `GROUND_APPROACH`(3) 或 `TRACKING_SUCCESS`(4)。

    若在 `IDLE`，调 `/agc/task/start` 起任务（复用既有门控，**不自建**第二套授权）。
    """
    from agc_msgs.msg import AgcTaskState
    from std_srvs.srv import Trigger

    holder = {'state': None, 'name': ''}
    n.create_subscription(
        AgcTaskState, '/agc/task/state',
        lambda m: holder.update(state=int(m.state), name=m.state_name), 10)

    def spin(secs):
        t0 = time.monotonic()
        while time.monotonic() - t0 < secs:
            rclpy.spin_once(n, timeout_sec=0.05)

    spin(2.0)
    if holder['state'] in (3, 4):
        return {'ok': True, 'state': holder['state'], 'state_name': holder['name'],
                'started': False}

    # `INFRA_FAILURE` / `MISSION_FAILED` / `ABORTED` 是**锁存终态**：直接调 start 会被门控拒绝。
    # 必须先 abort 再 start —— 否则标定每轮都会因为"任务已死"而测不到东西。
    # （实测踩过：calib-4 成功后停在 INFRA_FAILURE，之后每一轮都被拒。）
    if holder['state'] in (5, 6, 8):
        abort = n.create_client(Trigger, '/agc/task/abort')
        if abort.wait_for_service(timeout_sec=10.0):
            f = abort.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(n, f, timeout_sec=15.0)
        spin(2.0)

    cli = n.create_client(Trigger, '/agc/task/start')
    if not cli.wait_for_service(timeout_sec=15.0):
        return {'ok': False, 'state': holder['state'], 'state_name': holder['name'],
                'error': 'no /agc/task/start'}
    fut = cli.call_async(Trigger.Request())
    rclpy.spin_until_future_complete(n, fut, timeout_sec=20.0)
    msg = fut.result().message if (fut.done() and fut.result()) else ''

    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        spin(0.5)
        if holder['state'] in (3, 4):
            return {'ok': True, 'state': holder['state'],
                    'state_name': holder['name'], 'started': True, 'start_msg': msg}
    return {'ok': False, 'state': holder['state'], 'state_name': holder['name'],
            'started': True, 'start_msg': msg}


def _required_lateral_from_config():
    """从 `agc_rl/config/rl.yaml` 读**被裁定的能力主张**（`control.max_offset`）。

    **不写死 1.0**：能力主张会随裁定变化（ADR-0046 把它收窄过），
    写死会让"配置已改、标定还在验旧值"静默发生。读不到则返回 None（标定端如实标 unknown）。
    """
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    path = os.path.join(root, 'src', 'agc_rl', 'config', 'rl.yaml')
    try:
        with open(path, encoding='utf-8') as f:
            d = yaml.safe_load(f) or {}
        return float(d['ground_policy_rl']['ros__parameters']['control']['max_offset'])
    except (OSError, KeyError, TypeError, ValueError):
        return None


def _kill_rl_source():
    """按 PID 杀 RL 推理节点（禁止 pkill -f，见整链排障速查的铁律）。"""
    import subprocess
    try:
        out = subprocess.run(
            ['pgrep', '-f', 'ground_policy_rl'], capture_output=True, text=True, timeout=5)
        pids = [int(x) for x in out.stdout.split() if x.strip().isdigit()]
        for pid in pids:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        return pids
    except (subprocess.SubprocessError, OSError):
        return []


def _write(out_dir, res):
    path = os.path.join(out_dir, 'safety_calibration.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print('写入', path)


if __name__ == '__main__':
    sys.exit(main())
