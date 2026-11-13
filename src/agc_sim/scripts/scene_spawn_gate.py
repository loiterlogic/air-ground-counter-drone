#!/usr/bin/env python3
"""scene_spawn_gate —— 世界就绪门 + 车/目标的**事务式**创建（ADR-0038）。

## 为什么需要它

原实现由 `world_bringup` 的 `TimerAction(period=15.0)` 盲等 15 s 后调
`ros_gz_sim create`：Gazebo 2 s 就绪时白等 13 s，20 s 才就绪时 spawn 直接失败，
且失败**无人重试、无人上报**。固定秒数不是就绪判据，只是把竞态窗口换了个数字。

本脚本把「世界就绪 → 创建 → 确认存在」做成**可判定的事务**：

    create 服务可用（gz-transport 发现）
      → 世界时钟推进（≥2 帧且单调增，排除暂停/未启动）
      → spawn 实体 1 → 校验 scene/info 中出现 → spawn 实体 2 → 校验 → …
      → 发布 /agc/sim/entities_ready = true（latched）
      → 退出码 0

任一步超时或失败 → 有界重试 → 仍失败则发布 `false` + **非零退出**，
让上层（`startup_gate` + launch 事件）看到显式失败，而不是静默半启动。

## 边界

* 只**创建**实体，不改世界物理、不写位姿（复位归 `scenario_reset`，ADR-0014）。
* 直接走 gz-transport（不经 `ros_gz_sim create` 子进程）：需要的是**服务应答**与
  **实体存在**这两个事实，不是"某个子进程退出码"。
* 时间语义：本门用**墙钟**超时（启动阶段判「进程/服务是否就绪」）；仿真时间只用于
  判断时钟是否真的在推进（ADR-0038 (f)）。

用法（由 `world_bringup.launch.py` 单一注入，人工一般不需要直接调）：

    scene_spawn_gate --world agc_world --timeout-s 120 \\
      --entity agc_car --pose "-4,-3,0.01,0,0,0" --sdf "<sdf…>" \\
      --entity intruder_uav --pose "6.5,2.5,0.12,0,0,0" --sdf "<sdf…>"
"""

import argparse
import sys
import time

import gz.msgs10.boolean_pb2 as boolean_pb
import gz.msgs10.empty_pb2 as empty_pb
import gz.msgs10.entity_factory_pb2 as entity_factory_pb
import gz.msgs10.scene_pb2 as scene_pb
import gz.transport13 as gz_transport


_T0 = time.monotonic()


def log(msg):
    """带**墙钟相对时刻**的日志：启动阶段的可诊断性要求"卡在哪一段、花了多久"可直接读，
    而不是靠外部时间戳反推（ADR-0038 (h)）。"""
    print('[scene_spawn_gate +%.2fs] %s' % (time.monotonic() - _T0, msg), flush=True)


class Gate:
    def __init__(self, world, timeout_s, poll_s=0.2):
        self.world = world
        self.timeout_s = float(timeout_s)
        self.poll_s = float(poll_s)
        self.node = gz_transport.Node()
        self.create_srv = '/world/%s/create' % world
        self.scene_srv = '/world/%s/scene/info' % world
        self.clock_topic = '/world/%s/clock' % world
        self.clock_samples = []

    # ---- 世界就绪 ----------------------------------------------------------
    def await_create_service(self):
        """等 create 服务被**发现**（gz 服务器已起且已注册 UserCommands 服务）。"""
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            try:
                if self.create_srv in self.node.service_list():
                    return True
            except Exception as exc:                     # noqa: BLE001 —— 发现层异常按未就绪处理
                log('service discovery error: %s' % exc)
            time.sleep(self.poll_s)
        log('create 服务 %.1f s 内未出现（%s）' % (self.timeout_s, self.create_srv))
        return False

    def await_clock_advancing(self):
        """等仿真时钟**推进**（≥2 帧且 sim 时间严格增大）。

        只判"时钟话题有帧"不够：gz 以 `-r` 之外的方式启动时世界是**暂停**的，
        此时 create 能成功但物理不推进，实体永远不动 —— 那是另一种失败。
        """
        import gz.msgs10.clock_pb2 as clock_pb

        def _cb(msg):
            # `gz.msgs.Clock` 的字段是 `sim` / `real`（不是 `clock`）：仿真时间在 `sim`。
            # 取 sim 而非 real：要判的是**仿真**是否在推进（暂停的世界 real 照样走）。
            self.clock_samples.append((msg.sim.sec, msg.sim.nsec))

        self.node.subscribe(clock_pb.Clock, self.clock_topic, _cb)
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            if len(self.clock_samples) >= 2:
                first, last = self.clock_samples[0], self.clock_samples[-1]
                if last > first:
                    return True
            time.sleep(self.poll_s)
        log('世界时钟 %.1f s 内未推进（%s，样本 %d）'
            % (self.timeout_s, self.clock_topic, len(self.clock_samples)))
        return False

    # ---- 实体存在 ----------------------------------------------------------
    def model_names(self):
        ok, reply = self.node.request(
            self.scene_srv, empty_pb.Empty(), empty_pb.Empty, scene_pb.Scene, 3000)
        if not ok:
            return None
        return {m.name for m in reply.model}

    def await_entity(self, name, timeout_s=30.0):
        deadline = time.monotonic() + float(timeout_s)
        while time.monotonic() < deadline:
            names = self.model_names()
            if names is not None and name in names:
                return True
            time.sleep(self.poll_s)
        return False

    # ---- 创建 --------------------------------------------------------------
    def spawn(self, entity, pose, sdf, attempts=20, per_try_ms=4000):
        """创建实体，**有界重试**。

        为什么必须重试：`create` 服务**被发现**不等于服务端**能立刻应答**——世界还在加载
        几何 / 物理 / 渲染资源时，服务已在网络上注册，但请求会超时（实测：`create` 服务
        出现后 0.1 s 内的请求 10 s 超时，而同一请求在服务稳定后 0.3 s 内成功）。
        这不是"重试掩盖错误"：重试的是**瞬时**不可用，最终结论仍由 `await_entity` 的
        存在性校验给出——只有实体真的出现在 `scene/info` 里才算成功。
        """
        req = entity_factory_pb.EntityFactory()
        req.sdf = sdf
        req.name = entity
        # allow_renaming=False：同名实体已存在时**失败**而不是悄悄变成 `name_1`，
        # 否则"创建成功"与"我们看到的那个实体"会分叉（事务语义要求可判定）。
        req.allow_renaming = False
        req.pose.position.x = pose[0]
        req.pose.position.y = pose[1]
        req.pose.position.z = pose[2]
        req.pose.orientation.x = pose[3]
        req.pose.orientation.y = pose[4]
        req.pose.orientation.z = pose[5]
        req.pose.orientation.w = pose[6]
        for attempt in range(1, attempts + 1):
            ok, reply = self.node.request(
                self.create_srv, req, entity_factory_pb.EntityFactory, boolean_pb.Boolean,
                per_try_ms)
            if ok and reply.data:
                return True
            if ok and not reply.data:
                # 服务端**明确拒绝**（同名已存在 / SDF 非法）：重试不会改变结论。
                log('create 被拒绝：%s（同名实体可能已存在或 SDF 非法）' % entity)
                return False
            log('create 第 %d/%d 次未应答（服务端可能仍在加载世界），重试…'
                % (attempt, attempts))
            # 短退避：世界加载完成后第一个应答通常在 1 s 内（实测 0.3 s），
            # 长退避只会把"就绪后还要再等一轮"的时间拉长。
            time.sleep(0.5)
        log('create 请求 %d 次均未应答：%s' % (attempts, entity))
        return False


def parse_pose(text):
    """`x,y,z,roll,pitch,yaw` → 位置 + 四元数；非法值**拒绝运行**（不猜）。"""
    parts = [p.strip() for p in str(text).split(',')]
    if len(parts) < 6:
        raise SystemExit('pose %r 需要 6 个分量（x,y,z,roll,pitch,yaw）' % (text,))
    try:
        vals = [float(p) for p in parts[:6]]
    except ValueError:
        raise SystemExit('pose %r 含非数值分量' % (text,))
    import math
    if not all(math.isfinite(v) for v in vals):
        raise SystemExit('pose %r 含非有限值（NaN/±Inf）' % (text,))
    x, y, z, roll, pitch, yaw = vals
    # 只支持绕 z 的偏航（世界 ENU 平面位姿）；roll/pitch 非零则明确拒绝，
    # 不静默丢弃——那会让"声明的位姿"与"实际创建"分叉。
    if abs(roll) > 1e-9 or abs(pitch) > 1e-9:
        raise SystemExit('pose %r 的 roll/pitch 非零（本仓只创建平面位姿）' % (text,))
    return [x, y, z, 0.0, 0.0, math.sin(yaw * 0.5), math.cos(yaw * 0.5)]


def parse_entities(argv):
    """`--entity=NAME --pose=… --sdf=…` 可重复；顺序即创建顺序（车先、目标后）。

    **必须用 `=` 形式**：位姿的 x/y 常为负数（如 `-15.0,1.0,…`），argparse 会把
    `-15.0,…` 当成选项名而报 `unrecognized arguments`（实测踩过）。
    带 `=` 时 argparse 一律按"值"处理，负坐标与多行 SDF 都能原样通过。
    """
    out = []
    cur = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        key, sep, val = a.partition('=')
        if key not in ('--entity', '--pose', '--sdf'):
            # 其它选项（--world / --timeout-s …）已由 argparse 处理，这里只跳过。
            i += 1
            continue
        if not sep:
            raise SystemExit(
                '实体参数须写成 --entity=NAME / --pose=… / --sdf=…（实际：%r）' % a)
        i += 1
        if key == '--entity':
            if cur:
                out.append(cur)
            cur = {'name': val}
        else:
            if not cur:
                raise SystemExit('%s 出现在 --entity 之前' % key)
            cur['pose' if key == '--pose' else 'sdf'] = val
    if cur:
        out.append(cur)
    for e in out:
        missing = [k for k in ('name', 'pose', 'sdf') if k not in e]
        if missing:
            raise SystemExit('实体 %r 缺少 %s' % (e.get('name'), ', '.join(missing)))
        e['pose'] = parse_pose(e['pose'])
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--world', default='agc_world')
    ap.add_argument('--timeout-s', type=float, default=120.0,
                    help='世界就绪（create 服务 + 时钟推进）的墙钟上界')
    ap.add_argument('--verify-timeout-s', type=float, default=30.0,
                    help='单个实体"创建后确认存在"的墙钟上界')
    ap.add_argument('--ready-topic', default='/agc/sim/entities_ready',
                    help='就绪状态话题（std_msgs/Bool，latched）')
    # 只解析本脚本自己的选项；实体参数走 `--entity=` / `--pose=` / `--sdf=` 的 `=` 形式，
    # 由 parse_entities 处理（负坐标不能被 argparse 当选项，见其 docstring）。
    own = [a for a in argv if not a.startswith('--entity=') and
           not a.startswith('--pose=') and not a.startswith('--sdf=')]
    args = ap.parse_args(own)
    entities = parse_entities(argv)
    if not entities:
        log('没有要创建的实体（--entity 未给出）→ 只做世界就绪门')

    gate = Gate(args.world, args.timeout_s)
    log('等待 create 服务 %s（上界 %.0f s）' % (gate.create_srv, args.timeout_s))
    if not gate.await_create_service():
        return publish_and_exit(args.ready_topic, False, 'create_service_unavailable')
    log('create 服务已可用')
    log('等待世界时钟推进 %s' % gate.clock_topic)
    if not gate.await_clock_advancing():
        return publish_and_exit(args.ready_topic, False, 'world_clock_not_advancing')

    for ent in entities:
        name = ent['name']
        log('创建实体 %s pose=(%g,%g,%g)' % (name, ent['pose'][0], ent['pose'][1], ent['pose'][2]))
        if not gate.spawn(name, ent['pose'], ent['sdf']):
            return publish_and_exit(args.ready_topic, False, 'spawn_failed:' + name)
        if not gate.await_entity(name, args.verify_timeout_s):
            log('实体 %s 创建后 %.0f s 内未出现在 scene/info' % (name, args.verify_timeout_s))
            return publish_and_exit(args.ready_topic, False, 'entity_missing:' + name)
        log('实体 %s 已确认存在于世界中' % name)

    return publish_and_exit(args.ready_topic, True, 'ok')


def publish_and_exit(topic, ok, reason):
    """发布就绪状态（latched）后按结果退出：失败必须非零退出，不静默半启动。"""
    try:
        import rclpy
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from std_msgs.msg import Bool

        rclpy.init()
        node = rclpy.create_node('scene_spawn_gate')
        qos = QoSProfile(depth=1)
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        qos.reliability = ReliabilityPolicy.RELIABLE
        pub = node.create_publisher(Bool, topic, qos)
        # **立刻发**（不等订阅者）：等订阅者会把"发布结果"变成启动路径上的额外延时。
        # 然后**保活一小段**：`TRANSIENT_LOCAL` 的 latched 语义依附于**活着的发布者**——
        # 发布者一销毁，晚到的订阅者就查不到这条历史（实测：进程退出后 `ros2 topic echo`
        # 报 "does not appear to be published yet"）。保活窗口远小于就绪门预算，可接受。
        msg = Bool(data=bool(ok))
        keepalive_s = 5.0
        deadline = time.monotonic() + keepalive_s
        while time.monotonic() < deadline:
            pub.publish(msg)
            rclpy.spin_once(node, timeout_sec=0.2)
        node.destroy_node()
        rclpy.shutdown()
    except Exception as exc:                             # noqa: BLE001 —— 发布失败不得掩盖结论
        log('发布 %s 失败（结论仍以退出码为准）：%s' % (topic, exc))
    log('结果 %s（%s）' % ('READY' if ok else 'FAILED', reason))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
