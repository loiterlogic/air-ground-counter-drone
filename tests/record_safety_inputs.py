#!/usr/bin/env python3
"""地面安全层**输入序列录制器**（L4；需整链仿真，独占 GZ）。

## 为什么需要它

[ADR-0045](../docs/adr/0045-ground-safety-layer-self-owned.md#top) 的配套规范要求：
> **可重放**：标定必须能以**录制的输入序列**（命令 + 地图快照 + 车体状态 + 任务状态）
> 离线重跑判定类，且**逐拍输出与在线一致**。做不到就不是标定，是"这一次看起来没事"。

只记"速度轨迹"不满足这条：轨迹是**结果**，重放需要的是**输入**。本脚本录
`SafetyInputs` 的每一个字段（含地图快照），产出可直接喂给
[`safety_replay.cpp`](../src/agc_ground/test/safety_replay.cpp) 的 JSONL。

## 录什么（与 `safety_policy.hpp` 的 `SafetyInputs` 逐字段对应）

| JSONL 字段 | 对应 `SafetyInputs` | 说明 |
|---|---|---|
| `now_s` | `now_s` | 拍时刻（安全层本地时钟，s） |
| `cmd` | `has_command` + `command.{v,w,frame_ok,finite,holonomic_ok,stamp_s}` | 原始速度意图 |
| `body` | `has_body` + `body.{x,y,yaw,valid,finite,stamp_s}` | 车体状态 |
| `map` | `has_map` + `map.{width,height,resolution,origin_x,origin_y,frame_ok,stamp_s}` + `data` | **整幅快照**（每次地图变化才重存，用 `map_id` 引用） |
| `map_valid` | `map_valid_flag` | `/agc/map/valid` |
| `permit` | `has_permit` + `permit.{state,stamp_s}` | 任务许可 |
| `expect` | — | **在线**判定结果（状态字符串），供离线逐拍对拍 |

## 为什么地图要按 `map_id` 去重

地图 2 Hz、判定 20 Hz ⇒ 同一幅图会被重复引用 ~10 次。整幅 `200×200` 的 int8 是 40 KB，
逐拍存会让 60 s 的录制膨胀到 ~50 MB。去重后只存"变化的那几幅"。

## 用法

    # 1) 另开终端起整链（必须 backend:=full，见 ADR-0045：无相机 ⇒ 无地图 ⇒ 车不动）
    ros2 launch agc_task main.launch.py backend:=full ...

    # 2) 录一段（含任务启动）
    python3 tests/record_safety_inputs.py --out /tmp/safety_trace.jsonl --duration 60

    # 3) 离线重放并对拍（不需要 ROS、不需要仿真）
    ./build/agc_ground/safety_replay /tmp/safety_trace.jsonl

退出码：0 = 录制完成且样本数足够；1 = 地图未就绪 / 样本不足。
"""

import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import checklib  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True, help='输出 JSONL 路径')
    ap.add_argument('--duration', type=float, default=60.0)
    ap.add_argument('--rate-hz', type=float, default=20.0)
    ap.add_argument('--map-timeout', type=float, default=150.0)
    ap.add_argument('--no-start', action='store_true', help='不自动调 /agc/task/start')
    args = ap.parse_args()

    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from geometry_msgs.msg import TwistStamped
    from nav_msgs.msg import OccupancyGrid, Odometry
    from std_msgs.msg import Bool, String
    from agc_msgs.msg import AgcTaskState
    from std_srvs.srv import Trigger

    latched = QoSProfile(
        depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
        reliability=ReliabilityPolicy.RELIABLE)

    rclpy.init()
    n = Node('safety_input_recorder')
    # **必须与节点同一时基**：`/agc/map` 与 `/agc/task/state` 的 stamp 是**仿真时间**
    # （`use_sim_time:=true`），而 `n.get_clock()` 在 use_sim_time=false 时返回系统时间。
    # 改造前靠 `now_s = max(各输入 stamp)` 掩盖了这一点；一旦某拍没有任何输入
    # （启动早期），那一拍就会写成 1.79e9 的墙钟值，重放映成 `MAP_STALE`/`CLOCK_ANOMALY`。
    # 这里显式声明 `use_sim_time`，让"没有输入时的兜底时钟"与输入同域。
    n.set_parameters([rclpy.parameter.Parameter(
        'use_sim_time', rclpy.Parameter.Type.BOOL, True)])

    st = {
        'cmd': None, 'body': None, 'map': None, 'map_valid': None,
        'permit': None, 'status': None,
    }
    n.create_subscription(
        TwistStamped, '/agc/ground/cmd_vel_raw',
        lambda m: st.update(cmd=m), 20)
    n.create_subscription(
        Odometry, '/agc/ground/odom', lambda m: st.update(body=m), 20)
    n.create_subscription(
        OccupancyGrid, '/agc/map', lambda m: st.update(map=m), latched)
    n.create_subscription(
        Bool, '/agc/map/valid', lambda m: st.update(map_valid=m), latched)
    n.create_subscription(
        AgcTaskState, '/agc/task/state', lambda m: st.update(permit=m), 20)
    n.create_subscription(
        String, '/agc/ground/safety_status', lambda m: st.update(status=m), latched)

    def spin(secs):
        t0 = time.monotonic()
        while time.monotonic() - t0 < secs:
            rclpy.spin_once(n, timeout_sec=0.01)

    # 等地图有观测内容：无地图时安全层正确地零速，录下来全是 NO_COMMAND 没价值
    t0 = time.monotonic()
    occ = 0
    while time.monotonic() - t0 < args.map_timeout:
        spin(0.5)
        if st['map'] is not None:
            occ = sum(1 for v in st['map'].data if v >= 100)
            if occ > 200:
                break
    if occ <= 200:
        print('FAIL：地图无观测内容（occupied=%s）—— 请用 backend:=full 起整链' % occ)
        n.destroy_node()
        rclpy.shutdown()
        return 1
    print('地图就绪：occupied=%d' % occ)

    if not args.no_start:
        cli = n.create_client(Trigger, '/agc/task/start')
        if cli.wait_for_service(timeout_sec=10.0):
            fut = cli.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(n, fut, timeout_sec=20.0)
            msg = fut.result().message if (fut.done() and fut.result()) else ''
            print('task/start:', msg[:100])
            spin(3.0)

    # ---- 录制 ----
    out_path = args.out
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    maps = []          # 去重后的地图快照列表
    map_index = {}     # 内容 hash -> id
    period = 1.0 / max(1.0, args.rate_hz)
    samples = 0
    t_start = time.monotonic()
    last_map_id = -1

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps({
            'kind': 'header',
            'version': 1,
            'note': 'safety_policy SafetyInputs 序列；由 tests/record_safety_inputs.py 录制',
        }, ensure_ascii=False) + '\n')

        # **按安全层的状态心跳对齐采样**，而不是自由跑 20 Hz。
        # 安全层自己按 20 Hz 定时器发布 `/agc/ground/safety_status`；若录制器也自由跑 20 Hz，
        # 两者相位不同步 ⇒ 同一拍输入会被录成两条、同一条 expect 被复用 ⇒ 重放对拍必然错位
        # （实测：1097 拍里 937 拍不一致，其中大量是"同一 expect 对应两个不同 now_s"）。
        # 正确做法：**每收到一条新的 safety_status 就录一拍**，`now_s` 取该拍时刻。
        last_status_key = None
        while time.monotonic() - t_start < args.duration:
            tick_t0 = time.monotonic()
            rclpy.spin_once(n, timeout_sec=0.001)
            if st['status'] is not None:
                # `safety_status` 是 `std_msgs/String`（无 header）⇒ 只能按**内容变化**判新拍。
                # 这不是缺陷：内容里已带 `budget_ms`（每拍都不同），所以每拍内容必然不同。
                cur_key = st['status'].data
                if cur_key == last_status_key:
                    continue          # 状态还没更新：这一拍不录
                last_status_key = cur_key

            rec = {'kind': 'sample', 'now_s': None, 'cmd': None, 'body': None,
                   'map_id': None, 'map_valid': None, 'permit': None, 'expect': None}

            # **`now_s` 必须与各输入的 stamp 同一时基，且不得早于任何一个 stamp**。
            #
            # 踩过两个坑：
            # ① `n.get_clock()` 在 `use_sim_time=false` 时返回**系统时间**（1.79e9），
            #    而消息 stamp 是仿真时间（~200 s）⇒ 年龄 1.79e9 ⇒ 重放全 MAP_STALE。
            # ② 只用命令 stamp 当 now_s：地图（2 Hz）与任务状态（1 Hz）的 stamp 可能比
            #    **这一拍的命令**更晚（实测最多超前 0.26 s）⇒ 重放判 CLOCK_ANOMALY（future stamp），
            #    而线上 `now()` 是"当前时刻"，永远 ≥ 已收到的任何 stamp。
            # 正确做法：`now_s = max(本拍所有**已收到**输入的 stamp)` —— 这正是线上 `now()`
            # 与各输入 stamp 的真实关系（stamp 是过去收的消息，now 是现在）。
            stamps = []
            if st['cmd'] is not None:
                c = st['cmd'].header.stamp
                stamps.append(c.sec + c.nanosec * 1e-9)
            if st['body'] is not None:
                b = st['body'].header.stamp
                stamps.append(b.sec + b.nanosec * 1e-9)
            if st['map'] is not None:
                mp = st['map'].header.stamp
                stamps.append(mp.sec + mp.nanosec * 1e-9)
            if st['permit'] is not None:
                pm = st['permit'].header.stamp
                stamps.append(pm.sec + pm.nanosec * 1e-9)
            # `now_s` 取 `max(所有已收到输入 stamp)`：
            # 线上安全层的 `now()` 恒 ≥ 任何**已经收到**的消息 stamp（消息的 stamp 是过去），
            # 而 ≤ 任何尚未到达的消息。用 max 是这一关系的忠实近似；
            # 用单一消息的 stamp 会走进"另一些输入比它新"⇒ 重放判 CLOCK_ANOMALY（实测过）。
            rec['now_s'] = max(stamps) if stamps else (
                n.get_clock().now().nanoseconds * 1e-9)

            if st['cmd'] is not None:
                m = st['cmd']
                t = m.twist
                rec['cmd'] = {
                    'v': t.linear.x, 'w': t.angular.z,
                    'frame_ok': m.header.frame_id == 'car/base_link',
                    'finite': all(isinstance(x, float) and x == x and abs(x) != float('inf')
                                  for x in (t.linear.x, t.linear.y, t.linear.z,
                                            t.angular.x, t.angular.y, t.angular.z)),
                    'holonomic_ok': abs(t.linear.y) <= 1e-6,
                    'stamp_s': m.header.stamp.sec + m.header.stamp.nanosec * 1e-9,
                }

            if st['body'] is not None:
                m = st['body']
                q = m.pose.pose.orientation
                yaw = math.atan2(
                    2.0 * (q.w * q.z + q.x * q.y),
                    1.0 - 2.0 * (q.y * q.y + q.z * q.z))
                rec['body'] = {
                    'x': m.pose.pose.position.x, 'y': m.pose.pose.position.y,
                    'yaw': yaw, 'valid': True, 'finite': True,
                    'stamp_s': m.header.stamp.sec + m.header.stamp.nanosec * 1e-9,
                }

            if st['map'] is not None:
                m = st['map']
                data = list(m.data)
                h = hash(tuple(data))
                if h not in map_index:
                    map_index[h] = len(maps)
                    maps.append({
                        'kind': 'map',
                        'width': m.info.width, 'height': m.info.height,
                        'resolution': m.info.resolution,
                        'origin_x': m.info.origin.position.x,
                        'origin_y': m.info.origin.position.y,
                        'frame_ok': m.header.frame_id == 'world',
                        'stamp_s': m.header.stamp.sec + m.header.stamp.nanosec * 1e-9,
                        'data': data,
                    })
                rec['map_id'] = map_index[h]
                last_map_id = map_index[h]

            rec['map_valid'] = bool(st['map_valid'].data) if st['map_valid'] else True

            if st['permit'] is not None:
                m = st['permit']
                rec['permit'] = {
                    'state': int(m.state),
                    'stamp_s': m.header.stamp.sec + m.header.stamp.nanosec * 1e-9,
                }

            if st['status'] is not None:
                # **整份状态 JSON 都存下来**，尤其是 online 已经算好的四个 inpux 年龄。
                # 为什么：重放若用"消息 stamp + 自算 now_s" 重新推年龄，必然与在线差一个
                # 采样相位（实测出现 body age=0.508 而在线是 NO_PERMIT 的错配）。
                # 对拍要证明的是"**判定逻辑**在同样输入下给同样结论"，年龄属于**输入**，
                # 应当原样喂回去，而不是让重放自己再算一遍。
                try:
                    full = json.loads(st['status'].data)
                    rec['expect'] = full.get('state')
                    rec['online_diag'] = {
                        k: full.get(k) for k in
                        ('map_age_s', 'cmd_age_s', 'body_age_s', 'permit_age_s')
                    }
                except ValueError:
                    rec['expect'] = None
                    rec['online_diag'] = None

            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            samples += 1

            dt = period - (time.monotonic() - tick_t0)
            if dt > 0:
                time.sleep(dt)

        # 地图块写在末尾：读取端先读 header，遇到 map 再遇到下一块 sample 也无所谓，
        # 因为 replay 会先把全部块读进内存再跑。
        f.write(json.dumps({'kind': 'footer', 'samples': samples,
                            'maps': len(maps)}, ensure_ascii=False) + '\n')
        for i, mp in enumerate(maps):
            mp['id'] = i
            f.write(json.dumps(mp, ensure_ascii=False) + '\n')

    n.destroy_node()
    rclpy.shutdown()
    size_mb = os.path.getsize(out_path) / 1e6
    print('录制完成：%d 拍 / %d 幅地图去重 / %.1f MB → %s'
          % (samples, len(maps), size_mb, out_path))
    if samples < 50:
        print('FAIL：样本过少（<%d），不足以重放' % 50)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
