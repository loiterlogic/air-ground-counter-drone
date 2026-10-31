#!/usr/bin/env python3
"""`run_demo.sh` 的启动编排：组装 `ros2 launch` → 独立进程组 → 进度呈现 → 跟到终态 → 落 summary。

**薄封装**：不复制任何 launch 编排，参数一律透传给
[`w6.launch.py`](../../src/agc_task/launch/w6.launch.py)（[ADR-0061](../../docs/adr/0061-w6-runtime-topology-backend-identity-and-single-parameterized-entry.md) 的唯一参数化入口）。

对外只映射 5 个参数（[P1-2 参数收敛](../../docs/plan/p1-2-一键演示入口.md#p1-2-goal)）：

  | 对外 | 内部 launch 参数 | 默认 |
  |---|---|---|
  | `--map` | `world_map` | `yard` |
  | `--scene` | `scene` | `s04_static_static_obs_track` |
  | `--headless` | `gz_args` 去 GUI（加 `-s`） | GUI |
  | `--duration` | 到时触发 stop | 不限（跟终态） |
  | `--backend` | `backend` | `full` |

**脚本固定**（不暴露）：`seed=0`、`observe_yaw_mode=target`、`viz:=true`、`command_source=rl`、
`shield=true`、`agent0_port=8888` / `agent1_port=8889`、PX4 错峰默认值。

⚠ `observe_yaw_mode:=target` 是 **P1-1 round-7 已验收的显式 oracle 指向臂**（机头对准真值方位），
不是默认 `velocity`，也不代表真实视觉识别。启动横幅必须显式打出这一行。

**P1-3 呈现层**（[可观测与演示呈现](../../docs/plan/p1-3-任务可观测与演示呈现.md#p1-3-goal)）：

  | 产物 | 谁写 | 内容 |
  |---|---|---|
  | 终端 2 Hz 面板 | [`panel.Panel`](panel.py) | 状态 / 说明 / 原因 / 目标距离 / 观测年龄 / 控制者 / 已用时 |
  | `panel.txt` | 同上（同一渲染） | 终端被关掉后的复核副本 |
  | `timeline.txt` | [`timeline.Timeline`](timeline.py) | 状态跳变 + 生命周期节点（人读，不替代 summary） |
  | `terminal_explanation.txt` | [`verdict.explain`](verdict.py) | 终态判定说明（指标只来自 summary，阈值只来自 params_applied） |

三者**只读**既有数据：`/agc/task/state`、`metrics/summary.json`、`config/params_applied.yaml`。
文案统一走 [`status_map`](status_map.py)（唯一映射，C8 表述红线在此实现并自检）。

**不做**：不写 `/agc/ground/cmd_vel`、不写模型位姿、不发任务目标
（唯一执行口 [execution-port](../../docs/ROS2迁移交接文档.md#execution-port)）。任务启动只用
`/agc/task/start`（既有服务）与 `/agc/task/state`（既有话题）。
"""

import json
import os
import re
import signal
import subprocess
import time

import common
import panel
import status_map
import timeline as timeline_mod
import verdict

# 预检门槛（与 episode_runner 同源的现场经验，见 docs/conventions/整链排障速查.md#uxrce-participant-long-tail）
GT_FRESH_S = 1.0
AIR_FRESH_S = 1.0
CMD_FRESH_S = 1.0
# 任务终态：**单一来源** `status_map.TERMINAL_NAMES`（与 `agc_rl.termination.TERMINALS` 同口径）。
# P1-3 前这里是本文件自己的一份副本；现在收敛到映射模块，避免"两处终态集合"漂移。
TERMINALS = status_map.TERMINAL_NAMES

# 期望终态（主场景）——与 scenarios.yaml 的 expected_terminal 一致；演示只做**呈现**与**核对**，
# 不改判定口径（判定真源仍是 `agc_rl.termination` + `episode_runner`）。
EXPECTED_TERMINAL = 'TRACKING_SUCCESS'

# PX4 错峰窗口（w6.launch.py 默认值；进度提示必须覆盖，否则使用者以为卡死）
PX4_OWN_DELAY_S = 25.0
PX4_INTRUDER_DELAY_S = 35.0


def gz_args(headless):
    """`gz_args`：GUI = `-r -v 3 <world>`；headless = `-s -r -v 3 <world>`。

    `-s` 是 gz sim 的**服务端（无渲染客户端）**开关——这是 GUI / headless 的**唯一**结构性区别。
    """
    prefix = '-s -r -v 3 ' if headless else '-r -v 3 '
    return prefix + common.WORLD_SDF


def viz_enabled(headless):
    """RViz 叠加层是否该起：**只有 GUI 形态需要**。

    依据 [P1-2 §3 状态呈现](../../docs/plan/p1-2-一键演示入口.md#p1-2-goal)：
    "脚本用 `ros2 topic echo --once` 或轻量 Python 订阅（**不要**起 RViz 才能看状态）"。
    headless 用于经济快跑 / 服务器，本来就没有窗口可看，再起 `viz_markers` + `rviz2` +
    `static_tf`（[`w6.launch.py::_viz_actions`](../../src/agc_task/launch/w6.launch.py)）
    只是白烧内存与 CPU（rviz2 ≈257 MB + viz_markers ≈90 MB，见 MAP_DESIGN_PLAYBOOK 16.2）。

    P1-2 round-3 修正：原实现无条件 `viz:=true`，导致 `--headless` 也起 RViz。
    """
    return not headless


def launch_argv(*, backend, scene, world_map, headless, extra=()):
    """组装 `ros2 launch agc_task w6.launch.py …`（**不改**任何参数语义，只透传）。"""
    argv = ['ros2', 'launch', 'agc_task', 'w6.launch.py',
            'backend:=%s' % backend,
            'scene:=%s' % scene,
            'seed:=%d' % common.DEFAULT_SEED,
            'world_map:=%s' % world_map,
            'gz_args:=%s' % gz_args(headless),
            # 显式 oracle 指向臂（不得依赖 air.yaml 默认 velocity）
            'observe_yaw_mode:=%s' % common.DEFAULT_OBSERVE_YAW_MODE,
            # P1-1 的 RViz 叠加能力（GUI 纯场景 + RViz 语义层）；headless 不需要 → false
            'viz:=%s' % ('true' if viz_enabled(headless) else 'false'),
            'gui_render_backend:=auto',
            'agc_root:=%s' % common.ROOT]
    argv.extend(extra)
    return argv


def launch_env(base=None):
    """启动环境：显式补齐两处**会直接抛异常**的前置（不覆盖使用者已设的值）。"""
    env = dict(base or os.environ)
    env['ROS_AUTOMATIC_DISCOVERY_RANGE'] = 'LOCALHOST'
    if 'ROS_DOMAIN_ID' not in env:
        env['ROS_DOMAIN_ID'] = '0'
    # world_bringup 用 `EnvironmentVariable('GZ_SIM_SYSTEM_PLUGIN_PATH')` 做追加，未定义即抛错
    # （MAP_DESIGN_PLAYBOOK 14.2）。脚本先补正确路径，避免"必须记得 export"。
    cur = env.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')
    if common.GZ_PLUGIN_DIR not in cur:
        env['GZ_SIM_SYSTEM_PLUGIN_PATH'] = (
            common.GZ_PLUGIN_DIR + (':' + cur if cur else ''))
    return env


# --------------------------------------------------------------------------------------
# 进度呈现
# --------------------------------------------------------------------------------------

class Progress:
    """分段进度 + 同时写 `progress.log`（证据）与终端（给人看）。

    P1-3：与 2 Hz 面板**共用终端**。面板用 `\\r` 原地重绘方框，进度行若直接 `print`，
    会插在框中间把版面撕开 —— 故 `Progress` 持一个可选的 `panel` 引用，写终端前先
    `panel.erase()`，写完由下一帧面板自己重画（`progress.log` 内容不受影响）。
    """

    def __init__(self, log_path, stream=None, panel=None):
        import sys
        self.log_path = log_path
        self.stream = stream or sys.stdout
        self.panel = panel
        self.t0 = time.monotonic()
        common.ensure_dir(os.path.dirname(log_path))
        self.fh = open(log_path, 'a', buffering=1)

    def elapsed(self):
        return time.monotonic() - self.t0

    def line(self, text):
        stamp = '%02d:%02d' % (int(self.elapsed()) // 60, int(self.elapsed()) % 60)
        s = '[%s] %s' % (stamp, text)
        if self.panel is not None:
            self.panel.erase()
        try:
            print(s, file=self.stream, flush=True)
        except (OSError, ValueError):
            pass
        self.fh.write(s + '\n')

    def step(self, title, status, note=''):
        """`[00:05] 启动仿真世界 ......... OK` 形式的对齐行。"""
        dots = '.' * max(3, 30 - len(title) - len(status))
        self.line('%s %s %s%s' % (title, dots, status,
                                  (' (%s)' % note) if note else ''))

    def block(self, lines):
        """整块输出（终态判定说明这种**有对齐**的文本），不加时间戳前缀。"""
        if self.panel is not None:
            self.panel.erase()
        text = '\n'.join(lines)
        try:
            print(text, file=self.stream, flush=True)
        except (OSError, ValueError):
            pass
        self.fh.write(text + '\n')

    def raw(self, text):
        """只写日志（供长输出，不刷屏）。"""
        self.fh.write(text.rstrip('\n') + '\n')

    def close(self):
        try:
            self.fh.close()
        except OSError:
            pass


# --------------------------------------------------------------------------------------
# 启动
# --------------------------------------------------------------------------------------

def start(argv, env, log_path):
    """`start_new_session=True` → 独立进程组；Popen 后**立即**取 PGID（防 leader 先死）。"""
    common.ensure_dir(os.path.dirname(log_path))
    fh = open(log_path, 'w')
    fh.write('# run_demo start %s\n' % common.now_iso())
    fh.write('# argv: %s\n' % ' '.join(argv))
    fh.write('# cwd: %s\n' % common.ROOT)
    fh.flush()
    proc = subprocess.Popen(argv, cwd=common.ROOT, env=env,
                            stdout=fh, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        pgid = None
    return proc, pgid, fh


def launch_log_path(run_dir):
    return os.path.join(run_dir, 'launch.log')


# --------------------------------------------------------------------------------------
# 状态跟随（只读既有话题，不造状态）
# --------------------------------------------------------------------------------------

class TaskMonitor:
    """轻量订阅：`/agc/task/state` + 就绪所需的新鲜度信号 + `/clock`。

    数据源全部是**既有**话题（[P1-2 状态呈现数据源](../../docs/plan/p1-2-一键演示入口.md#p1-2-goal)）：
    `/agc/task/state`（`AgcTaskState`）、`/clock`、真值旁路、`/agc/ground/cmd_vel`、
    `/agc/ground/odom_valid`、`/agc/air/odom`。**不**用 `ros2 topic echo` 起子进程（省一次 DDS 发现）。
    """

    def __init__(self):
        import rclpy
        from rclpy.node import Node
        from agc_msgs.msg import AgcTaskState
        from rosgraph_msgs.msg import Clock
        from geometry_msgs.msg import PoseStamped, TwistStamped
        from nav_msgs.msg import Odometry
        from std_msgs.msg import Bool
        from std_srvs.srv import Trigger

        self.rclpy = rclpy
        self.node = Node('run_demo_monitor')
        self.state = None
        self.state_name = ''
        self.reason = ''
        self.dist_m = None
        # P1-3 面板直接呈现的**既有** `AgcTaskState` 字段（不新增任何字段 / 话题）
        self.obs_age_s = None
        self.air_controller = ''
        self.ground_controller = ''
        self.milestone = False
        self.sim = None
        self.gt_car = None
        self.gt_tgt = None
        self.cmd = None
        self.odom_valid = None
        self.odom_valid_rx = None
        self.air = None
        self.terminal_wall = None
        self.node.create_subscription(AgcTaskState, '/agc/task/state', self._on_state, 20)
        self.node.create_subscription(Clock, '/clock', self._on_clock, 1)
        self.node.create_subscription(PoseStamped, '/agc/gt/agc_car', self._on_gt_car, 10)
        self.node.create_subscription(PoseStamped, '/agc/gt/intruder_uav', self._on_gt_tgt, 10)
        self.node.create_subscription(TwistStamped, '/agc/ground/cmd_vel', self._on_cmd, 20)
        self.node.create_subscription(Bool, '/agc/ground/odom_valid', self._on_odom_valid, 10)
        self.node.create_subscription(Odometry, '/agc/air/odom', self._on_air, 10)
        self.cli = self.node.create_client(Trigger, '/agc/task/start')

    # -- 回调 --
    def _on_state(self, m):
        self.state = m.state
        self.state_name = m.state_name
        self.reason = m.reason_code
        try:
            d = float(m.target_xy_distance_m)
            self.dist_m = d if d == d else None           # NaN → None
        except (TypeError, ValueError):
            self.dist_m = None
        try:
            a = float(m.target_obs_age_s)
            self.obs_age_s = a if a == a else None        # NaN → None（无观测）
        except (TypeError, ValueError):
            self.obs_age_s = None
        self.air_controller = m.air_controller or ''
        self.ground_controller = m.ground_controller or ''
        self.milestone = bool(m.tracking_milestone_met)
        if m.state_name in TERMINALS and self.terminal_wall is None:
            self.terminal_wall = time.monotonic()

    def _on_clock(self, m):
        self.sim = m.clock.sec + m.clock.nanosec * 1e-9

    def _on_gt_car(self, _m):
        self.gt_car = time.monotonic()

    def _on_gt_tgt(self, _m):
        self.gt_tgt = time.monotonic()

    def _on_cmd(self, _m):
        self.cmd = time.monotonic()

    def _on_odom_valid(self, m):
        self.odom_valid = bool(m.data)
        self.odom_valid_rx = time.monotonic()

    def _on_air(self, _m):
        self.air = time.monotonic()

    # -- 就绪判据（与 episode_runner.wait_ready 同口径） --
    def _fresh(self, t):
        return t is not None and (time.monotonic() - t) < GT_FRESH_S

    def ready_report(self, require_air):
        checks = {
            'start_service': self.cli.service_is_ready(),
            'gt_car_fresh': self._fresh(self.gt_car),
            'gt_target_fresh': self._fresh(self.gt_tgt),
            'cmd_vel_fresh': self.cmd is not None and (time.monotonic() - self.cmd) < CMD_FRESH_S,
            'odom_valid': bool(self.odom_valid) and self._fresh(self.odom_valid_rx),
        }
        if require_air:
            checks['air_odom_fresh'] = (self.air is not None
                                       and (time.monotonic() - self.air) < AIR_FRESH_S)
        return checks

    def spin(self, timeout=0.1):
        self.rclpy.spin_once(self.node, timeout_sec=timeout)

    def wait_ready(self, timeout_s, require_air, progress, on_wait=None):
        t0 = time.monotonic()
        last = None
        while time.monotonic() - t0 < timeout_s:
            self.spin()
            rep = self.ready_report(require_air)
            ok = all(rep.values())
            if ok:
                return True, rep
            key = tuple(sorted(rep.items()))
            if key != last and on_wait is not None:
                last = key
                on_wait(rep)
        return False, self.ready_report(require_air)

    def start_task(self, timeout=90.0):
        """调 `/agc/task/start`（**既有**服务；不新增命令者）。返回 `(ok, message)`。"""
        from std_srvs.srv import Trigger
        if not self.cli.wait_for_service(timeout_sec=timeout):
            return False, 'service unavailable'
        fut = self.cli.call_async(Trigger.Request())
        self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=timeout)
        if not fut.done():
            return False, 'timeout'
        res = fut.result()
        return bool(res.success), res.message

    def wait_terminal(self, timeout_s, on_state=None):
        t0 = time.monotonic()
        last_name = None
        while time.monotonic() - t0 < timeout_s:
            self.spin()
            if self.state_name != last_name:
                last_name = self.state_name
                if on_state is not None:
                    on_state(self)
            if self.state_name in TERMINALS:
                return True
        return self.state_name in TERMINALS

    def destroy(self):
        try:
            self.node.destroy_node()
        except Exception:      # noqa: BLE001
            pass


# --------------------------------------------------------------------------------------
# summary / run_id 校验
# --------------------------------------------------------------------------------------

def find_summary(campaign_root, scenario, seed, not_before_unix):
    """按 `-<scenario>-<seed>-` 子串 + mtime ≥ 起始时刻定位**本 run** 的 summary。

    与 `episode_runner` 的同 run 关联同口径（suffix 容忍，不猜固定路径）；额外要求
    `run_id` 里含 `-<scenario>-<seed>-`，命不中即如实报"未找到"，不拿旧 summary 冒充。
    """
    import glob
    pat = os.path.join(campaign_root, '*-%s-%d*/metrics/summary.json' % (scenario, seed))
    cands = []
    for p in glob.glob(pat):
        try:
            if os.path.getmtime(p) >= not_before_unix - 1.0:
                cands.append(p)
        except OSError:
            continue
    if not cands:
        return None, None, '未找到本 run 的 metrics/summary.json（模式 %s）' % pat
    path = max(cands, key=os.path.getmtime)
    doc = common.read_json(path)
    if doc is None:
        return path, None, 'summary.json 存在但无法解析：%s' % path
    rid = doc.get('run_id') or ''
    if ('-%s-%d-' % (scenario, seed)) not in rid:
        return path, doc, 'run_id 与本 episode 不符：%r（期望含 -%s-%d-）' % (rid, scenario, seed)
    return path, doc, ''


# 演示关心的 summary 字段（不做第二套判定，只做**呈现 + 一致性核对**）
SUMMARY_KEYS = (
    'run_id', 'episode_id', 'seed', 'scenario', 'terminal_state',
    'terminal_state_latched', 'terminal_reason_code', 'reason_code',
    'duration_s', 'duration_kind', 'sim_start_s', 'sim_end_s', 'rtf',
    'odom_valid_ratio', 'cmd_vel_rate_hz', 'reset_retries', 'reset_failed',
    'shield_infeasible_rate', 'reset_failure_rate', 'ticks_total', 'ticks_triggered',
    'collision_count', 'visibility_metrics', 'episode_window_metrics',
    'command_attribution', 'git_commit', 'not_applicable', 'evaluation_applicable',
)


def summary_slice(doc):
    return {k: doc.get(k) for k in SUMMARY_KEYS if k in (doc or {})}


# --------------------------------------------------------------------------------------
# 单个演示回合（start 子命令的主体）
# --------------------------------------------------------------------------------------

class DemoRun:
    """一次完整演示：预检 → 启动 → 等待 → 呈现 → 终态 → 收尾 → 证据。

    生命周期与 `run_demo.sh stop` / `Ctrl-C` 解耦：本对象只在**前台监督进程**里存在，
    `stop` 通过 `experiments/demo/.run/current.json` 的 PGID 在另一个终端回收它。
    """

    def __init__(self, opts, stream=None):
        import sys
        self.opts = opts
        self.stream = stream or sys.stdout
        self.stamp = common.stamp_dir()
        self.run_dir = os.path.join(common.DEMO_ROOT, self.stamp)
        self.progress = None
        self.proc = None
        self.pgid = None
        self.log_fh = None
        self.lock_fd = None
        self.monitor = None
        # P1-3 呈现层三件套（`panel` 只画、`timeline` 只记、`verdict` 只解释，均不造数据）
        self.panel = None
        self.timeline = None
        self._last_panel_state = None
        self.result = {
            'schema': 'demo-run-v1',
            'stamp': self.stamp,
            'run_dir': self.run_dir,
            'started_at': common.now_iso(),
            'options': dict(opts),
            'mode': 'headless' if opts.get('headless') else 'gui',
            'backend': opts.get('backend'),
            'scene': opts.get('scene'),
            'world_map': opts.get('map'),
            'seed': common.DEFAULT_SEED,
            'observe_yaw_mode': common.DEFAULT_OBSERVE_YAW_MODE,
            'oracle_arm_note': ('observe_yaw_mode=target 是显式 oracle 指向臂（机头对准真值方位），'
                                '非默认 velocity，也不代表真实视觉识别；目标测量仍走 air_fusion'),
            'exit_reason': None,
            'phases': {},
        }
        self._stop_signal = None
        self._renderer_snapshot = None
        self._ev_running = None
        self._disabled = set()

    # -- P1-3 呈现层 --
    def _open_presentation(self):
        """开面板 + 时间线（**只读**呈现，不改任何起停语义；**失败只降级不终止**）。"""
        self._safe('timeline_open', self._open_timeline)
        self._safe('panel_open', self._open_panel)

    def _open_timeline(self):
        self.timeline = timeline_mod.Timeline(
            os.path.join(self.run_dir, 'timeline.txt'))     # 只落盘：终端已有面板 + 进度行
        self.timeline.note('run_demo 启动：%s' % ' '.join(self.opts.get('_argv') or []))
        self.timeline.note('形态 %s / 后端 %s / 场景 %s / 地图 %s / seed %s / observe_yaw_mode=%s'
                           % ('headless' if self.opts.get('headless') else 'GUI',
                              self.opts.get('backend'), self.opts.get('scene'),
                              self.opts.get('map'), common.DEFAULT_SEED,
                              common.DEFAULT_OBSERVE_YAW_MODE))
        self.timeline.note('观测指向臂：observe_yaw_mode=%s 是显式 oracle 指向臂'
                           '（机头对准真值方位），非默认 velocity，也不代表真实视觉识别'
                           % common.DEFAULT_OBSERVE_YAW_MODE)

    def _open_panel(self):
        self.panel = panel.Panel(self.stream,
                                 snapshot_path=os.path.join(self.run_dir, 'panel.txt'))

    def _panel_fields(self, monitor=None):
        """面板 / 时间线共同的数据视图——**全部来自** `/agc/task/state` 与跟随计时。"""
        mon = monitor if monitor is not None else self.monitor
        if mon is None:
            return {'state_name': 'IDLE', 'reason_code': '', 'distance_m': None,
                    'obs_age_s': None, 'elapsed_s': self._follow_elapsed()}
        return {
            'state_name': mon.state_name or 'IDLE',
            'reason_code': mon.reason,
            'distance_m': mon.dist_m,
            'obs_age_s': mon.obs_age_s,
            'air_controller': mon.air_controller,
            'ground_controller': mon.ground_controller,
            'tracking_milestone_met': mon.milestone,
            'elapsed_s': self._follow_elapsed(),
        }

    def _follow_elapsed(self):
        """「已用时」= 自演示启动（时间线起点）的墙钟秒数；无起点返回 0.0（不猜）。"""
        t0 = getattr(self.timeline, 't0', None)
        return 0.0 if t0 is None else max(0.0, time.monotonic() - t0)

    def _paint(self, monitor=None, force=False):
        """到 2 Hz 节拍画一帧面板（未到节拍直接返回，不阻塞跟随循环）。"""
        if self.panel is None:
            return False
        return bool(self._safe('panel', lambda: self.panel.render(
            self._panel_fields(monitor), force=force)))

    def _timeline(self, text):
        """时间线写入的统一入口（降级 + 单点实现），避免各处裸调再漏 try。"""
        if self.timeline is None:
            return
        self._safe('timeline', lambda: self.timeline.event(text))

    def _safe(self, what, fn):
        """呈现层降级执行：异常记进 `result['presentation_errors']` 并**继续运行**。

        为什么不 `raise`：面板 / 时间线 / 判定说明都是**旁路**产物，它们的缺陷不该
        让一次已经跑起来的真实实验白跑（round-1 实测踩过）。错误如实记账，不静默吞掉。
        """
        try:
            return fn()
        except Exception as e:                     # noqa: BLE001 —— 旁路失败必须降级
            err = {'component': what, 'error': '%s: %s' % (type(e).__name__, e),
                   'at': common.now_iso()}
            self.result.setdefault('presentation_errors', []).append(err)
            if what not in self._disabled:
                self._disabled.add(what)
                self.progress and self.progress.line(
                    '呈现层降级（%s 出错，演示继续）：%s: %s' % (what, type(e).__name__, e))
            return None

    # -- 生命周期 --
    def install_signal_handlers(self):
        """Ctrl-C 走**与 stop 相同的回收路径**（进程组 SIGINT → 轮询 → SIGKILL），不靠 shell 默认行为。"""
        def _handler(signum, _frame):
            self._stop_signal = signal.Signals(signum).name
            self.progress and self.progress.line(
                '收到 %s → 回收进程组（与 ./run_demo.sh stop 同一路径）' % self._stop_signal)
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def run(self):
        self.result['wall_start_unix'] = time.time()
        self.install_signal_handlers()
        self._open_presentation()
        self.progress = Progress(os.path.join(self.run_dir, 'progress.log'), self.stream,
                                 panel=self.panel)
        self.progress.line('run_demo 启动：%s' % ' '.join(self.opts.get('_argv') or []))
        try:
            self.progress.step('环境预检', 'OK', '由 run_demo.sh doctor 项复用，详见 doctor.log')
            self._timeline('环境预检 OK（阻断性检查由 run_demo.sh doctor 项复用）')
            self._phase_launch()
            self._phase_wait_ready()
            self._phase_start_task()
            self._phase_follow()
            self._phase_collect()
        except common.DemoError as e:
            self.result['exit_reason'] = 'demo_error'
            self.result['error'] = {'message': e.message, 'hint': e.hint}
            self.progress.line('失败：%s' % e.message)
            for h in (e.hint or []):
                self.progress.line('  → %s' % h)
            if self.timeline is not None:
                self._timeline('演示失败（未达终态）：%s' % e.message)
            self._teardown('error')
            self._finalize(exit_code=e.exit_code)
            return e.exit_code
        finally:
            if self.monitor is not None:
                self.monitor.destroy()
                self.monitor = None
        if (self.result.get('exit_reason') or '').startswith('interrupted'):
            code = 130          # 128 + SIGINT：用户主动中断，**不是**任务失败
        elif self.result.get('exit_reason') == 'duration_limit':
            code = 0 if self.result.get('terminal_state') in TERMINALS else 3
        else:
            code = 0 if self.result.get('terminal_state') == EXPECTED_TERMINAL else 2
        self._finalize(exit_code=code)
        return code

    # -- 各阶段 --
    def _phase_launch(self):
        # GUI 形态：**启动之前**拍 renderer 日志快照（逐 run 有界证据的起点）
        if not self.opts['headless']:
            try:
                import evidence
                self._renderer_snapshot = evidence.snapshot_renderer_log()
            except Exception:                       # noqa: BLE001
                self._renderer_snapshot = None
        argv = launch_argv(backend=self.opts['backend'], scene=self.opts['scene'],
                          world_map=self.opts['map'], headless=self.opts['headless'],
                          extra=self.opts.get('extra') or ())
        self.result['launch_argv'] = argv
        self.result['launch_env'] = {
            k: v for k, v in launch_env().items()
            if k in ('ROS_AUTOMATIC_DISCOVERY_RANGE', 'ROS_DOMAIN_ID',
                     'GZ_SIM_SYSTEM_PLUGIN_PATH', 'DISPLAY')}
        # 先登记实例（含运行目录 / 监督 PID），再 Popen —— 保证 stop / Ctrl-C 一定能按 PGID 找到
        self.lock_fd, _doc = common.acquire_instance(
            self.run_dir, mode=self.result['mode'], backend=self.opts['backend'],
            scene=self.opts['scene'], world_map=self.opts['map'],
            seed=common.DEFAULT_SEED, observe_yaw_mode=common.DEFAULT_OBSERVE_YAW_MODE)
        t0 = time.monotonic()
        # 预览模式（--dry-run / 故障注入用）：只写证据，不起进程
        if self.opts.get('dry_run'):
            self.progress.step('启动仿真世界', 'SKIP', 'dry-run：只落参数与证据')
            self.result['phases']['launch'] = {'dry_run': True, 'wall_s': 0.0,
                                               'argv': argv}
            raise common.DemoError('dry-run 完成（未启动任何进程）',
                                   ['去掉 --dry-run 即为真实演示'], exit_code=0)
        self.proc, self.pgid, self.log_fh = start(
            argv, launch_env(), launch_log_path(self.run_dir))
        common.update_instance({'state': 'running', 'launch_pid': self.proc.pid,
                                'launch_pgid': self.pgid})
        self.result['launch_pid'] = self.proc.pid
        self.result['launch_pgid'] = self.pgid
        self.result['phases']['launch'] = {'argv': argv, 'pid': self.proc.pid,
                                          'pgid': self.pgid, 'wall_s': round(time.monotonic() - t0, 3)}
        self.progress.step('启动仿真世界', 'OK', 'pgid %s' % self.pgid)
        if self.timeline is not None:
            self._timeline('启动仿真世界（后端 %s / 场景 %s / 地图 %s，pgid %s）'
                           % (self.opts['backend'], self.opts['scene'],
                              self.opts['map'], self.pgid))
        if self.opts['backend'] == 'full':
            self.progress.raw('# PX4 错峰：own %.0fs / intruder %.0fs（ADR-0094）'
                              % (PX4_OWN_DELAY_S, PX4_INTRUDER_DELAY_S))

    def _phase_wait_ready(self):
        import rclpy
        self.monitor = TaskMonitor()
        require_air = self.opts['backend'] == 'full'
        t0 = time.monotonic()
        announced = {'px4_own': False, 'px4_intruder': False}

        def on_wait(rep):
            el = time.monotonic() - t0
            # PX4 错峰窗口必须**显式提示**，否则使用者以为卡死
            if require_air and el > 3 and not announced['px4_own']:
                announced['px4_own'] = True
                self.progress.step('PX4 己方实例', '等待中', '错峰 %.0fs' % PX4_OWN_DELAY_S)
            if require_air and el > PX4_OWN_DELAY_S and not announced['px4_intruder']:
                announced['px4_intruder'] = True
                self.progress.step('PX4 入侵者实例', '等待中',
                                   '错峰 %.0fs，仍在等 air odom / gt 新鲜' % PX4_INTRUDER_DELAY_S)
            pending = [k for k, v in rep.items() if not v]
            if pending:
                self.progress.raw('  [%.1fs] 未就绪：%s' % (el, ', '.join(pending)))

        ok, rep = self.monitor.wait_ready(self.opts['ready_timeout_s'], require_air,
                                          self.progress, on_wait)
        self.result['phases']['ready'] = {'ok': ok, 'checks': rep,
                                         'wall_s': round(time.monotonic() - t0, 3),
                                         'ready_timeout_s': self.opts['ready_timeout_s']}
        if not ok:
            missing = [k for k, v in rep.items() if not v]
            raise common.DemoError(
                '整链就绪超时（%.0f s）' % self.opts['ready_timeout_s'],
                ['未就绪项：%s' % ', '.join(missing),
                 'PX4 错峰 25/35 s 是正常的；若超 90 s 仍未就绪，看日志：%s'
                 % launch_log_path(self.run_dir),
                 '常见原因：残留进程 / DDS 段过多 / 端口被占 → ./run_demo.sh doctor'],
                exit_code=5, detail={'ready': rep})
        if require_air:
            self.progress.step('PX4 己方实例', 'OK', 'air odom 新鲜（错峰 %.0fs）' % PX4_OWN_DELAY_S)
            self.progress.step('PX4 入侵者实例', 'OK', '错峰 %.0fs' % PX4_INTRUDER_DELAY_S)
        self.progress.step('任务层就绪', 'OK', '/agc/task/start 可用且 gt/cmd/odom 新鲜')
        if self.timeline is not None:
            self._timeline('整链就绪：%s' % ', '.join(
                k for k, v in rep.items() if v))

    def _phase_start_task(self):
        t0 = time.monotonic()
        ok, msg = self.monitor.start_task(timeout=self.opts['start_timeout_s'])
        self.result['phases']['start'] = {'ok': ok, 'message': msg,
                                          'wall_s': round(time.monotonic() - t0, 3)}
        if not ok:
            raise common.DemoError(
                '/agc/task/start 被拒绝：%s' % msg,
                ['该服务是既有入口，拒绝原因来自 task_manager 的门控（例如 air_hover_timeout）',
                 '看日志：%s' % launch_log_path(self.run_dir)],
                exit_code=6, detail={'start_message': msg})
        self.progress.step('任务启动', 'OK', msg or '/agc/task/start')
        if self.timeline is not None:
            self._timeline('任务启动（既有服务 /agc/task/start）：%s'
                           % (msg or 'success'))

    def _phase_follow(self):
        duration = self.opts.get('duration')
        limit = float(duration) if duration else self.opts['follow_timeout_s']
        t0 = time.monotonic()
        states = []

        def on_state(mon):
            states.append({'t_s': round(time.monotonic() - t0, 2),
                           'state': mon.state_name, 'reason': mon.reason,
                           'dist_m': None if mon.dist_m is None else round(mon.dist_m, 3)})
            dist = '' if mon.dist_m is None else '  目标距离 %.1f m' % mon.dist_m
            if self.panel is not None:
                self.panel.erase()                 # 进度行不能插进方框里
            self.progress.line('当前状态：%s（%s）%s'
                               % (mon.state_name or '?',
                                  status_map.state_by_name(mon.state_name)['text'], dist))
            # 时间线：只在**状态跳变**时记（同一状态刷新不记，避免刷屏）
            # P1-3 round-1 实测教训：呈现层缺陷曾把整场演示打断（TypeError 冒到 run() 外，
            # 进程组仍在跑）。呈现是**旁路**，失败只允许"该产物缺失"，绝不允许终止任务。
            self._safe('timeline', lambda: self.timeline.state(
                mon.state_name, mon.reason, mon.dist_m,
                at=time.monotonic() - self.timeline.t0))
            self._paint(mon, force=True)           # 跳变当帧立刻刷新面板

        def _deadline_hit():
            return duration is not None and (time.monotonic() - t0) >= float(duration)

        while not _deadline_hit():
            self.monitor.spin(0.1)
            if self.monitor.state_name != (states[-1]['state'] if states else None):
                on_state(self.monitor)
            self._paint()                          # 2 Hz 节拍；未到节拍为空操作
            if self._stop_signal:
                break
            if self.monitor.state_name in TERMINALS:
                break
            if time.monotonic() - t0 >= limit:
                break
        reached = self.monitor.state_name in TERMINALS
        self.result['terminal_state'] = self.monitor.state_name or 'ACTIVE'
        self.result['terminal_reason_code'] = self.monitor.reason
        self.result['terminal_reached'] = reached
        self.result['phase1_states'] = states
        self.result['phases']['follow'] = {
            'wall_s': round(time.monotonic() - t0, 3),
            'duration_limit_s': duration,
            'follow_timeout_s': self.opts['follow_timeout_s'],
            'terminal_reached': reached,
            'states_observed': len(states)}
        if self._stop_signal:
            self.result['exit_reason'] = 'interrupted(%s)' % self._stop_signal
            self.progress.line('已被 %s 中断（非终态退出）' % self._stop_signal)
            if self.timeline is not None:
                self._timeline('用户中断（%s）—— 非终态退出，本次不作为成功证据'
                               % self._stop_signal)
            return
        if _deadline_hit():
            self.result['exit_reason'] = 'duration_limit'
            self.result['duration_branch_taken'] = True
            self.progress.line('已到 --duration %.1fs，主动停止' % float(duration))
            if self.timeline is not None:
                self._timeline('已到 --duration %.1fs 主动停止（exit_reason=duration_limit，'
                               '当前状态 %s，**非终态**）'
                               % (float(duration), self.monitor.state_name or '?'))
            return
        if duration is not None:
            # 终态先于 --duration 到达：**duration_limit 分支未触达**，如实记账
            self.result['duration_branch_taken'] = False
            self.result['duration_not_reached_note'] = (
                '--duration %.1fs 未触达：任务在 %.2fs 先达终态（%s）；'
                '本次**不能**作为 duration_limit 分支的证据'
                % (float(duration), time.monotonic() - t0, self.monitor.state_name))
        if not reached:
            self.result['exit_reason'] = 'follow_timeout'
            raise common.DemoError(
                '等待终态超时（%.0f s），当前状态 %s' % (limit, self.monitor.state_name),
                ['--duration 未设置时的跟随上限是 %.0f s；可用 --duration 延长或 --follow-timeout 调整'
                 % limit,
                 '看日志：%s' % launch_log_path(self.run_dir)],
                exit_code=7)
        self.result['exit_reason'] = 'terminal'
        self.progress.step('终态', self.monitor.state_name,
                           self.monitor.reason or '-')
        self._paint(self.monitor, force=True)

    def _phase_collect(self):
        """终态后：**先**在进程组还活着时拍证据，**再**回收进程组。"""
        t0 = time.monotonic()
        common.update_instance({'state': 'terminating'})
        # 给 run_logger 一小段落 summary + 让 renderer 日志写完（不改变任何判定）
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and self.monitor is not None:
            self.monitor.spin(0.1)
        try:
            import evidence
            self._ev_running = evidence.collect_running(
                self.run_dir, self.result, self.pgid, self._renderer_snapshot)
        except Exception as e:                      # noqa: BLE001 —— 取证不得掩盖主结论
            self._ev_running = {'error': '%s: %s' % (type(e).__name__, e)}
        reap = self._teardown('terminal')
        self.result['phases']['collect'] = {'reap': reap,
                                            'wall_s': round(time.monotonic() - t0, 3)}

    def _teardown(self, reason):
        if self.proc is None:
            return None
        # 失败 / 中断路径也要**先**在进程组还活着时拍证据（否则只剩 launch.log）
        if self._ev_running is None:
            try:
                import evidence
                self._ev_running = evidence.collect_running(
                    self.run_dir, self.result, self.pgid, self._renderer_snapshot)
            except Exception as e:                  # noqa: BLE001
                self._ev_running = {'error': '%s: %s' % (type(e).__name__, e)}
        if self.progress is not None:
            self.progress.line('回收进程组 %s（SIGINT → 轮询 → SIGKILL）' % self.pgid)

        def on_tick(n, t):
            self.progress and self.progress.line(
                '  仍在退出：%d 个进程（%.1fs）' % (n, t))

        reap = common.reap_process_group(self.pgid, on_tick=on_tick, proc=self.proc)
        self.result['reap'] = reap
        if self.log_fh is not None:
            self.log_fh.flush()
            self.log_fh.close()
            self.log_fh = None
        common.update_instance({'state': 'reaped' if reap['confirmed'] else 'leaked',
                                'reap_confirmed': reap['confirmed']})
        if self.progress is not None:
            self.progress.step('回收进程组', 'OK' if reap['confirmed'] else 'FAIL',
                               '已清理 %d 个进程，剩余 %d 个（%.1fs）'
                               % (reap['cleaned_count'], len(reap['members_after']),
                                  reap['wall_s']))
        return reap

    # -- 证据落盘 --
    def _finalize(self, exit_code):
        code = exit_code
        # 1) 进程/渲染/窗口证据（GUI 形态必须齐；headless 如实标 not_applicable）
        try:
            import evidence
            ev = evidence.collect_final(self.run_dir, self.result,
                                        getattr(self, '_ev_running', None),
                                        getattr(self, '_renderer_snapshot', None))
            self.result['evidence'] = ev
        except Exception as e:                     # noqa: BLE001 —— 取证不得掩盖主结论
            self.result['evidence'] = {'error': '%s: %s' % (type(e).__name__, e)}
        # 2) summary
        camp = os.path.join(common.ROOT, 'experiments', 'w6-task-eval')
        path, doc, why = find_summary(camp, self.opts['scene'], common.DEFAULT_SEED,
                                      self.result.get('wall_start_unix') or 0)
        self.result['summary_path'] = path
        self.result['summary_error'] = why or None
        if doc is not None:
            self.result['summary'] = summary_slice(doc)
            src = os.path.join(self.run_dir, 'run-artifacts')
            common.ensure_dir(src)
            import shutil
            for sub in ('metrics', 'config'):
                s = os.path.join(os.path.dirname(os.path.dirname(path)), sub)
                d = os.path.join(src, sub)
                if os.path.isdir(s) and not os.path.isdir(d):
                    shutil.copytree(s, d)
            self.result['run_artifacts'] = os.path.join(self.run_dir, 'run-artifacts')
        # 3) 复现信息 + 结果（先落退出码，判定说明的脚注要引用它）
        self.result['finished_at'] = common.now_iso()
        self.result['exit_code'] = code
        # 4) P1-3 终态判定说明（**指标只来自 summary，阈值只来自本 run 的 params_applied.yaml**）
        self._final_explanation(path, doc, code)
        self.result['verdict'] = (EXPECTED_TERMINAL
                                  if self.result.get('terminal_state') == EXPECTED_TERMINAL
                                  else 'not_met')
        common.write_json(os.path.join(self.run_dir, 'result.json'), self.result)
        self._write_markdown(code)
        if self.lock_fd is not None:
            common.release_instance(self.lock_fd,
                                    final_state='finished' if code == 0 else 'failed')
            self.lock_fd = None
        if self.progress is not None:
            if self.result.get('summary_path'):
                self.progress.line('结果：%s' % os.path.relpath(
                    self.result['summary_path'], common.ROOT))
            self.progress.line('证据：%s' % os.path.relpath(self.run_dir, common.ROOT))
            self.progress.close()

    def _final_explanation(self, summary_path, summary_doc, exit_code=None):
        """打印 + 落盘终态判定说明；并把时间线的摘要补充说明与面板收尾一次做完。"""
        config_path = None
        if summary_path:
            config_path = os.path.join(os.path.dirname(os.path.dirname(summary_path)),
                                       'config', 'params_applied.yaml')
        try:
            thresholds = verdict.load_thresholds(config_path)
            explained = verdict.explain(
                summary_doc, thresholds,
                terminal_state=self.result.get('terminal_state'),
                terminal_reason=self.result.get('terminal_reason_code'),
                summary_path=summary_path, expected_terminal=EXPECTED_TERMINAL)
            text = '\n'.join(explained['lines'])
            with open(os.path.join(self.run_dir, 'terminal_explanation.txt'), 'w',
                      encoding='utf-8') as f:
                f.write(text + '\n')
            self.result['terminal_explanation'] = {
                'path': os.path.join(self.run_dir, 'terminal_explanation.txt'),
                'fields': explained['fields']}
            self.progress.block(explained['lines'])
            if self.timeline is not None:
                for note in timeline_mod.summary_notes(summary_doc):
                    self._safe('timeline', lambda n=note: self.timeline.summary_note(n))
        except Exception as e:                     # noqa: BLE001 —— 解释失败不得掩盖主结论
            self.result['terminal_explanation'] = {
                'error': '%s: %s' % (type(e).__name__, e),
                'note': '判定说明生成失败（如实记账，不伪造解释）'}
            self.progress.line('判定说明生成失败：%s: %s'
                               % (type(e).__name__, e))
        finally:
            if self.timeline is not None:
                self.result['timeline'] = self._safe('timeline', lambda: self.timeline.close(extra={
                    '终态': self.result.get('terminal_state') or '-',
                    '退出码': exit_code if exit_code is not None
                    else self.result.get('exit_code', '待定'),
                    'summary': os.path.relpath(summary_path, common.ROOT) if summary_path else '无',
                }))
            if self.panel is not None:
                self.result['panel'] = self._safe('panel', lambda: self.panel.finish(extra={
                    '终态': self.result.get('terminal_state') or '-',
                }))

    def _write_markdown(self, code):
        r = self.result
        lines = ['# run_demo 演示结果 · %s' % r['stamp'], '',
                 '- 退出码：`%d`' % code,
                 '- 形态：`%s` · 后端：`%s` · 场景：`%s` · 地图：`%s` · seed `%d`' % (
                     r['mode'], r.get('backend'), r.get('scene'), r.get('world_map'),
                     r.get('seed')),
                 '- **观测指向臂**：`observe_yaw_mode=%s`（显式 oracle 指向臂，非默认 velocity；'
                 '目标测量仍走 `air_fusion`）' % r.get('observe_yaw_mode'),
                 '- 终态：`%s` / `%s`（期望 `%s`）' % (
                     r.get('terminal_state'), r.get('terminal_reason_code') or '-',
                     EXPECTED_TERMINAL),
                 '- 退出原因：`%s`' % (r.get('exit_reason') or '-'),
                 '', '## 启动命令', '', '```bash', ' '.join(r.get('launch_argv') or []),
                 '```', '']
        if r.get('summary'):
            s = r['summary']
            lines += ['## summary 关键字段', '', '| 字段 | 值 |', '|---|---|']
            for k in ('run_id', 'terminal_state', 'terminal_reason_code', 'duration_s',
                      'sim_start_s', 'sim_end_s', 'rtf', 'reset_failed', 'reset_retries',
                      'shield_infeasible_rate', 'reset_failure_rate', 'odom_valid_ratio',
                      'cmd_vel_rate_hz', 'collision_count'):
                if k in s:
                    lines.append('| `%s` | `%s` |' % (k, s[k]))
            vis = (s.get('visibility_metrics') or {})
            if vis:
                lines.append('| `visibility_rate` | `%s`（%s/%s tick） |' % (
                    vis.get('visibility_rate'), vis.get('ticks_visible'), vis.get('ticks_total')))
        # P1-3：呈现层产物索引（人读件；机器可读件仍是 summary.json）
        tl = r.get('timeline') or {}
        pn = r.get('panel') or {}
        ex = r.get('terminal_explanation') or {}
        if tl or pn or ex:
            lines += ['', '## 可观测产物（P1-3）', '']
            if tl:
                lines.append('- `timeline.txt`：关键节点 **%s** 个（状态跳变 %s + 生命周期 %s，'
                             '判据 ≥%s）' % (tl.get('key_nodes'), tl.get('state_nodes'),
                                            tl.get('lifecycle_nodes'), tl.get('min_required')))
            if pn:
                lines.append('- `panel.txt`：2 Hz 面板快照，节拍渲染 **%s** 帧（外观 `%s`，'
                             '单行 %s 行）' % (pn.get('renders'), pn.get('mode'), pn.get('lines')))
            if ex and not ex.get('error'):
                fields = ex.get('fields') or {}
                lines.append('- `terminal_explanation.txt`：判定说明（阈值源 `%s`，'
                             '终态 `%s`）' % (
                                 os.path.basename(str(fields.get('threshold_source') or '（缺失）')),
                                 fields.get('terminal_state')))
            elif ex.get('error'):
                lines.append('- `terminal_explanation.txt`：**生成失败** `%s`' % ex['error'])
        ev = r.get('evidence') or {}
        if ev:
            lines += ['', '## 证据', '']
            for k, v in ev.items():
                if isinstance(v, dict):
                    lines.append('- `%s`: %s' % (k, {kk: vv for kk, vv in v.items()
                                                    if kk in ('status', 'ok', 'note', 'path')}))
            lines.append('')
            lines.append('详见 `evidence/` 目录（原始输出未改写）。')
        with open(os.path.join(r['run_dir'], 'result.md'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
