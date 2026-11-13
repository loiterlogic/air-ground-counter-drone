#!/usr/bin/env python3
"""startup_gate —— 启动期就绪门（ADR-0038）：等**可观测判据**，不猜秒数。

## 为什么需要它

`launch` 的 `TimerAction(period=N)` 表达的是"过了 N 秒"，不是"前一步已就绪"。
本仓实测后果：车/目标被无条件延迟 15 s；己方 PX4 延迟 25 s、入侵者 35 s；
`air_bringup` 又是另一套 12 s。低性能机器上这些秒数不够（spawn 失败、PX4 找不到模型），
高性能机器上则白等几十秒。**固定秒数不是就绪判据。**

本脚本把"等什么"变成显式条件：全部 `--await` 条件满足 → 退出 0；
超时 → 非零退出，让上层看到显式失败，而不是让后续节点对着空气跑。

## 支持的判据（可任意组合，全部满足才算就绪）

| 判据 | 含义 |
|---|---|
| `service:/abs/name` | ROS 服务已被发现 |
| `topic:/abs/name:sec` | ROS 话题在 `sec` 秒内**收到过消息**（墙钟） |
| `entity:<gz 世界>:<模型名>` | gz 世界里该模型存在（`scene/info`） |
| `gzservice:/world/x/create` | gz 服务已被发现 |
| `graph-stable:<sec>:<min_nodes>` | ROS 节点数 ≥ `min_nodes` 且**连续 `sec` 秒不再变化**（发现风暴已平息） |

## 时间语义（ADR-0038 (f)）

* 就绪判定与超时一律用**墙钟**：启动阶段问的是"进程/服务/实体是否已就绪"，
  与仿真时间是否推进无关（仿真可能还没起步）。
* `topic:` 的新鲜度同样按**墙钟**算（收到消息的墙钟时刻），不读 `/clock`：
  启动期 `/clock` 可能尚未出现，用仿真时间会让判据在时钟起步前恒假。

## 话题类型

`topic:` 判据需要真实订阅才能判断"有没有消息"。话题类型从 ROS graph
（`get_topic_names_and_types`）**动态解析**后建订阅——不在此写死类型表，
否则换一个消息类型就静默收不到（那正是本仓踩过的坑）。

用法示例（由 launch 单一注入）：

    startup_gate --await service:/agc/scenario/reset \\
                 --await topic:/agc/air/odom:2.0 --timeout-s 180
"""

import argparse
import sys
import time


_T0 = time.monotonic()


def log(msg):
    """带**墙钟相对时刻**的日志：启动阶段的可诊断性要求"卡在哪一段、花了多久"可直接读。"""
    print('[startup_gate +%.2fs] %s' % (time.monotonic() - _T0, msg), flush=True)


def _import_msg(type_str):
    """`'geometry_msgs/msg/PoseStamped'` → 消息类；未知类型返回 None（不猜）。"""
    try:
        from rosidl_runtime_py.utilities import get_message
        return get_message(type_str)
    except Exception:                                    # noqa: BLE001 —— 类型未安装按"不可判"处理
        return None


class RosProbe:
    """ROS 侧判据：服务发现 + 话题新鲜度（墙钟）。"""

    def __init__(self, service_specs, topic_specs):
        import rclpy
        from rclpy.qos import (
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )
        from std_srvs.srv import Trigger

        self.rclpy = rclpy
        rclpy.init()
        self.node = rclpy.create_node('startup_gate')
        self.services = {s: self.node.create_client(Trigger, s) for s in service_specs}
        self.topic_specs = list(topic_specs)
        self.subs = {}
        self.last_rx = {}
        self.unresolved = set()
        self._last_graph = set()
        self._graph_changed_at = time.monotonic()

    def _ensure_subscriptions(self):
        """话题出现后才建订阅（类型由 graph 动态解析；解析不到就保持未就绪）。"""
        if not self.topic_specs:
            return
        graph = dict(self.node.get_topic_names_and_types())
        for name, _ in self.topic_specs:
            if name in self.subs or name in self.unresolved:
                continue
            types = graph.get(name) or []
            msg_cls = _import_msg(types[0]) if types else None
            if msg_cls is None:
                continue
            self.unresolved.discard(name)
            # QoS 必须**同时兼容**两类发布者，否则会静默收不到（本仓踩过两次）：
            #  * PX4 uXRCE 的 `/fmu/out/*`：BEST_EFFORT + TRANSIENT_LOCAL；
            #  * 普通 ROS 节点：RELIABLE + VOLATILE。
            # ROS 2 的兼容规则是"订阅者不得比发布者更强"：RELIABLE 订阅者收不到
            # BEST_EFFORT 发布者的数据（不报错、不告警，`create_subscription` 照样成功）。
            # 判据只需要"有没有消息"，故取**最弱**组合：BEST_EFFORT + VOLATILE，
            # 这样两类发布者都能匹配上。
            qos = QoSProfile(depth=10)
            qos.reliability = ReliabilityPolicy.BEST_EFFORT
            qos.durability = DurabilityPolicy.VOLATILE
            qos.history = HistoryPolicy.KEEP_LAST
            self.subs[name] = self.node.create_subscription(
                msg_cls, name, self._make_cb(name), qos)

    def _make_cb(self, name):
        def _cb(_msg):
            self.last_rx[name] = time.monotonic()
        return _cb

    def service_ready(self, name):
        cli = self.services.get(name)
        return bool(cli is not None and cli.service_is_ready())

    def topic_fresh(self, name, window_s):
        t = self.last_rx.get(name)
        return t is not None and (time.monotonic() - t) <= window_s

    def graph_stable(self, hold_s, min_nodes):
        """ROS 图是否**已稳定**：节点数 ≥ min_nodes，且连续 hold_s 秒不再变化。

        为什么需要这条判据（实测，2026-11-10）：本仓整链启动时十几个节点 + 两个 uXRCE Agent
        同时上线，DDS 发现图在头十几秒持续变动。此时启动 PX4，其 `uxrce_dds_client` 的
        participant 创建会撞上**发现风暴**——agent 侧 `establish_session` 落入长尾，
        而 PX4 侧预算是**硬编码 1 s**（ADR-0027 背景），于是
        `ERROR [uxrce_dds_client] create entities failed: participant: 255`，之后无 odom、
        不 arm、整链 infra。旧的 25 s 延时保护的正是这件事。

        本判据把"发现风暴已平息"变成可观测事实：节点集合连续 hold_s 秒不变。
        """
        names = set(self.node.get_node_names())
        now = time.monotonic()
        if names != self._last_graph:
            self._last_graph = names
            self._graph_changed_at = now
        if len(names) < min_nodes:
            return False, 'nodes=%d<%d' % (len(names), min_nodes)
        quiet = now - self._graph_changed_at
        return quiet >= hold_s, 'nodes=%d quiet=%.1fs/%.1fs' % (len(names), quiet, hold_s)

    def spin(self, seconds=0.1):
        self._ensure_subscriptions()
        self.rclpy.spin_once(self.node, timeout_sec=seconds)

    def destroy(self):
        try:
            self.node.destroy_node()
            self.rclpy.shutdown()
        except Exception:                                # noqa: BLE001
            pass


class GzProbe:
    """gz 侧判据：服务发现 + 模型存在（`scene/info`）。"""

    def __init__(self):
        self.node = None
        try:
            import gz.transport13 as gz_transport
            self.node = gz_transport.Node()
        except Exception as exc:                         # noqa: BLE001
            log('gz-transport 不可用（entity/gzservice 判据将恒未就绪）：%s' % exc)

    def service_ready(self, name):
        if self.node is None:
            return False
        try:
            return name in self.node.service_list()
        except Exception:                                # noqa: BLE001
            return False

    def entity_present(self, world, model):
        if self.node is None:
            return False
        try:
            import gz.msgs10.empty_pb2 as empty_pb
            import gz.msgs10.scene_pb2 as scene_pb

            ok, reply = self.node.request(
                '/world/%s/scene/info' % world, empty_pb.Empty(), empty_pb.Empty,
                scene_pb.Scene, 2000)
        except Exception:                                # noqa: BLE001
            return False
        if not ok:
            return False
        return any(m.name == model for m in reply.model)


def parse_awaits(specs):
    """把 `--await` 串解析成 (ros_services, ros_topics, gz_services, gz_entities)。

    非法判据**拒绝运行**（不静默忽略）：一条拼错的判据若被忽略，门会立刻"通过"，
    正是要消灭的那类假就绪。
    """
    ros_services, ros_topics, gz_services, gz_entities, graph_stable = [], [], [], [], []
    for spec in specs:
        kind, _, rest = spec.partition(':')
        if kind == 'service':
            if not rest.startswith('/'):
                raise SystemExit('service 判据需要绝对名：%r' % spec)
            ros_services.append(rest)
        elif kind == 'topic':
            name, _, win = rest.rpartition(':')
            if not name.startswith('/'):
                raise SystemExit('topic 判据需要绝对名：%r' % spec)
            try:
                window = float(win) if win else 1.0
            except ValueError:
                raise SystemExit('topic 判据的新鲜窗口非数值：%r' % spec)
            if window <= 0:
                raise SystemExit('topic 判据的新鲜窗口必须为正：%r' % spec)
            ros_topics.append((name, window))
        elif kind == 'entity':
            world, _, model = rest.partition(':')
            if not world or not model:
                raise SystemExit('entity 判据需要 <world>:<model>：%r' % spec)
            gz_entities.append((world, model))
        elif kind == 'gzservice':
            if not rest.startswith('/'):
                raise SystemExit('gzservice 判据需要绝对名：%r' % spec)
            gz_services.append(rest)
        elif kind == 'graph-stable':
            hold, _, min_nodes = rest.partition(':')
            try:
                hold_s = float(hold)
                need = int(min_nodes)
            except ValueError:
                raise SystemExit('graph-stable 判据需要 <sec>:<min_nodes>：%r' % spec)
            if hold_s <= 0 or need < 0:
                raise SystemExit('graph-stable 判据参数必须为正：%r' % spec)
            graph_stable.append((hold_s, need))
        else:
            raise SystemExit(
                '未知判据类型 %r（可用：service | topic | entity | gzservice）' % spec)
    return ros_services, ros_topics, gz_services, gz_entities, graph_stable


def evaluate(ros_services, ros_topics, gz_services, gz_entities, probe, gz,
             graph_stable=()):
    """返回仍未就绪的判据列表（空 = 全部就绪）。纯函数式判定，便于单测。"""
    pending = []
    for name in ros_services:
        if probe is None or not probe.service_ready(name):
            pending.append('service:%s' % name)
    for name, window in ros_topics:
        if probe is None or not probe.topic_fresh(name, window):
            pending.append('topic:%s' % name)
    for name in gz_services:
        if gz is None or not gz.service_ready(name):
            pending.append('gzservice:%s' % name)
    for world, model in gz_entities:
        if gz is None or not gz.entity_present(world, model):
            pending.append('entity:%s:%s' % (world, model))
    for hold_s, min_nodes in graph_stable:
        ok, detail = (False, 'no probe') if probe is None else probe.graph_stable(
            hold_s, min_nodes)
        if not ok:
            pending.append('graph-stable:%gs:%d(%s)' % (hold_s, min_nodes, detail))
    return pending


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--await', dest='await_', action='append', default=[], metavar='SPEC',
                    help='就绪判据（可重复）：service:/abs | topic:/abs:sec | '
                         'entity:<world>:<model> | gzservice:/abs')
    ap.add_argument('--timeout-s', type=float, default=180.0)
    ap.add_argument('--poll-s', type=float, default=0.2)
    ap.add_argument('--name', default='startup_gate', help='日志标识（哪一段门）')
    args = ap.parse_args(argv)

    ros_services, ros_topics, gz_services, gz_entities, graph_stable = parse_awaits(
        args.await_)
    if not (ros_services or ros_topics or gz_services or gz_entities or graph_stable):
        log('%s：没有判据（--await 未给出）→ 立即就绪' % args.name)
        return 0

    log('%s：等待 %d 服务 / %d 话题 / %d gz 服务 / %d 实体 / %d 图稳定判据（上界 %.0f s）'
        % (args.name, len(ros_services), len(ros_topics), len(gz_services),
           len(gz_entities), len(graph_stable), args.timeout_s))

    probe = (RosProbe(ros_services, ros_topics)
             if (ros_services or ros_topics or graph_stable) else None)
    gz = GzProbe() if (gz_services or gz_entities) else None

    deadline = time.monotonic() + args.timeout_s
    last_report = 0.0
    pending = []
    while time.monotonic() < deadline:
        pending = evaluate(ros_services, ros_topics, gz_services, gz_entities, probe, gz,
                           graph_stable)
        if not pending:
            if probe is not None:
                probe.destroy()
            log('%s：就绪' % args.name)
            return 0
        if probe is not None:
            probe.spin(0.05)
        now = time.monotonic()
        if now - last_report >= 5.0:
            last_report = now
            log('%s：未就绪 %s' % (args.name, ', '.join(pending)))
        time.sleep(args.poll_s)

    if probe is not None:
        probe.destroy()
    log('%s：超时 %.0f s，未就绪 %s' % (args.name, args.timeout_s, ', '.join(pending)))
    return 1


if __name__ == '__main__':
    sys.exit(main())
