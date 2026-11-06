#!/usr/bin/env python3
"""run_demo 的共享底层：进程组 / 运行状态文件 / 人话错误 / 证据落点。

定位：[演示可观测性与产物语义](../../docs/conventions/演示可观测性与产物语义.md#top) 的**薄封装**基础层。
本模块只提供四类机械能力，**不含**任何启动编排 / launch 参数语义 / 任务状态解释：

 1. **运行状态文件**（`experiments/demo/.run/`）—— 让 `stop` 能在**另一个终端**里按
 PID / PGID 找到并回收本次启动，而不靠 `pkill -f`（[整链排障速查](../../docs/conventions/整链排障速查.md#0-三条环境铁律)）。
 2. **进程组回收** —— SIGINT（优雅）→ 轮询 → SIGKILL（清理游离子进程）→ 轮询确认。
 纪律与 [`scripts/episode_runner.py`](../episode_runner.py) 的 `_reap_process_group` 同源：
 **只**回收本 run 的进程组（`start_new_session=True`），不按裸名匹配、不杀其它会话。
 3. **人话错误** —— 统一的 `[run_demo] 错误：…` + 建议行，绝不把 Python 栈丢给使用者。
 4. **证据落点** —— `experiments/demo/<timestamp>/`（ADR-0006 campaign=demo）。

不做：不 source 环境（由 `run_demo.sh` 负责）、不写 `/agc/ground/cmd_vel`、不写模型位姿
（[唯一执行口](../../docs/adr/0020-package-boundaries-and-runtime-topology.md#execution-port)）。
"""

import json
import os
import re
import signal
import socket
import subprocess
import time
import uuid

# 项目根**自定位**（2026-10-31 ，裁定 A）：
# 原来写死 `/home/chen/AGC` —— 在别处 clone 后跑 `run_demo.sh` 会操作**原仓库**
# （实测：克隆目录 `doctor` 误报 PASS 14/14、产物落原仓库、启动的是原仓库的仿真）。
# 本文件在 `<ROOT>/scripts/demo/common.py`，故上溯三级即为项目根。
# `start.py` 已把 `agc_root:=common.ROOT` 显式透传给 launch → 修这一处，整链即用克隆自己的根。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
DEMO_ROOT = os.path.join(ROOT, 'experiments', 'demo')
STATE_DIR = os.path.join(DEMO_ROOT, '.run')
CURRENT_JSON = os.path.join(STATE_DIR, 'current.json')
PIDS_FILE = os.path.join(STATE_DIR, 'pids')
LOCK_FILE = os.path.join(STATE_DIR, 'instance.lock')

# 主场景口径（用户 2026-10-29 裁定； 验收口径）——**脚本固定**，不对外暴露。
DEFAULT_SCENE = 's04_static_static_obs_track'
DEFAULT_MAP = 'yard'
DEFAULT_BACKEND = 'full'
DEFAULT_SEED = 0
# 观测指向臂的**实际生效值**（仅供展示 / 记录，**不**作为 launch 参数传递）。
#
# 2026-11-04 修正：`observe_yaw_mode` 的 launch 参数已清退（ 对照臂结档），
# 现只有「场景覆盖 > `air.yaml` 配置文件」两级，**没有** run 级 CLI 覆盖口。
# 主场景 `s04` 在 `scenarios.yaml` 覆盖为 `track`（机头对准 `/agc/targets` 感知航迹，
# **非** oracle）；`air.yaml` 缺省 `velocity`。
# ⚠ 此前 demo 仍传 `observe_yaw_mode:=target`，而 ros2 launch 对**未声明**的
# `name:=value` 是**静默忽略**（实测：加 `totally_bogus:=1` 也不报错），
# 故产物里报告的 `target` 与实际生效的 `track` **不一致**。本值改为如实反映实际生效档。
DEFAULT_OBSERVE_YAW_MODE = 'track'

WORLD_SDF = os.path.join(ROOT, 'install', 'agc_sim', 'share', 'agc_sim', 'worlds', 'agc_world.sdf')
GZ_PLUGIN_DIR = os.path.join(ROOT, 'install', 'agc_sim', 'lib')

# 进程组回收时间预算（与 episode_runner 的同名常量口径一致：优雅 → 强杀各一段）。
REAP_SIGINT_S = 12.0
REAP_SIGKILL_S = 6.0


# --------------------------------------------------------------------------------------
# 人话错误
# --------------------------------------------------------------------------------------

class DemoError(Exception):
    """可预期的失败（预检不过 / 已实例在跑 / 端口占用…）——由入口打印**人话**而非栈。"""

    def __init__(self, message, hint=None, exit_code=1, detail=None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.exit_code = exit_code
        self.detail = detail or {}


def human_block(title, lines):
    """统一的人话错误块（供 shell 侧复用同一外观）。"""
    width = 74
    out = ['', '=' * width, '[run_demo] 错误：%s' % title, '-' * width]
    for ln in lines:
        out.append('  ' + ln if ln else '')
    out.append('=' * width)
    return '\n'.join(out)


def fail(title, lines=(), exit_code=1, stream=None):
    import sys
    stream = stream or sys.stderr
    print(human_block(title, list(lines)), file=stream, flush=True)
    return exit_code


# --------------------------------------------------------------------------------------
# 时间 / 文件
# --------------------------------------------------------------------------------------

def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime())


def stamp_dir():
    """`YYYYmmdd-HHMMSS`（本地时区）——演示产物目录名（ADR-0006 的 <timestamp>）。"""
    return time.strftime('%Y%m%d-%H%M%S', time.localtime())


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------------------
# PX4 每实例可写运行根（ADR-0024 (d) 的 demo 默认开关）
# --------------------------------------------------------------------------------------

def px4_run_root(run_dir):
    """本 run 的 PX4 可写运行根：`<run_dir>/px4`。

 **为什么 demo 必须隔离**（2026-11-03 实测）：
 不隔离时 own（实例 0）/ intruder（实例 1）**共用** `build/px4_sitl_default/rootfs/`
 这一个工作目录——PX4 以 `cwd=<build>` 启动，看到 `PX4_BINARY_DIR/etc` 存在就落回
 `rootfs/` 且**不追加实例号**（日志 `assuming working directory is rootfs, no symlinks
 needed.`；`rootfs/` 下确实没有 `0/`、`1/`）。两个实例于是共用同一份 `parameters.bson`
 与 `dataman`，`MAV_SYS_ID` / `UXRCE_DDS_KEY` 每次启动互相覆写。

 实测后果：`px4_1` 的 EKF 间歇性报 `Preflight Fail: Yaw estimate error` + `ekf2 missing
 data` → `ekf2` 不发布 `vehicle_odometry` → `intruder_driver` 收不到 odom → 不 ARM →
 目标机停在地面 → 全程 `AIR_SEARCH` 失败。对照证据：目视成功的探针轮 0 次
 `Yaw estimate error`，两次 `run_demo.sh` 失败轮各 3–5 次。

 2026-11-03 更正：旧注释以"3D 距离 ≥14 m > 感知量程 12 m ⇒ 感知恒盲"为**诊断特征**。
 量程改为 30.0 后 √(26.17²+14²)=29.68 m 仍在量程内（余量 0.32 m），该特征**已失效**：
 目标停地面时感知照样有航迹。⇒ 判定"目标没起飞"**只能**靠 `intruder_driver` 的
 `have_odom` 错误日志与 `target_takeoff_guard`，**不得**依赖感知致盲。

 隔离后每实例独占 `instance_<n>/{dataman,parameters*.bson,log/,eeprom/}`，共享 build
 只读（ADR-0024 (d) 的既有机制，此处只是把 opt-in 打开并固定落点）。
    """
    return os.path.join(run_dir, 'px4')


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, doc):
    """原子写（tmp + rename）：避免 `stop` 读到半截 JSON。"""
    ensure_dir(os.path.dirname(path))
    tmp = '%s.tmp.%d' % (path, os.getpid())
    with open(tmp, 'w') as f:
        json.dump(doc, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


# --------------------------------------------------------------------------------------
# 进程 / 进程组（只按 PID / PGID 操作，绝不按名字匹配）
# --------------------------------------------------------------------------------------

def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_stat(pid):
    """返回 `/proc/<pid>/stat` 的 (state, ppid, pgrp, ...)；读不到 → None。

 解析注意：`comm` 可含空格与括号，故按**最后一个** `)` 切分。
    """
    try:
        with open('/proc/%d/stat' % int(pid)) as f:
            data = f.read()
    except (OSError, ValueError):
        return None
    cut = data.rfind(')')
    if cut < 0:
        return None
    fields = data[cut + 2:].split()
    if len(fields) < 3:
        return None
    try:
        return {'state': fields[0], 'ppid': int(fields[1]), 'pgrp': int(fields[2])}
    except ValueError:
        return None


def proc_pgid(pid):
    st = read_stat(pid)
    return st['pgrp'] if st else None


def proc_cmdline(pid):
    try:
        with open('/proc/%d/cmdline' % int(pid), 'rb') as f:
            raw = f.read().decode('utf-8', 'replace').split('\x00')
    except (OSError, ValueError):
        return ''
    return ' '.join(x for x in raw if x).strip()


def proc_argv0(pid):
    try:
        with open('/proc/%d/cmdline' % int(pid), 'rb') as f:
            raw = f.read().decode('utf-8', 'replace').split('\x00')
    except (OSError, ValueError):
        return ''
    return raw[0].strip() if raw else ''


def proc_exe(pid):
    try:
        return os.readlink('/proc/%d/exe' % int(pid))
    except OSError:
        return ''


def pgid_members(pgid, uid_only=True):
    """该进程组的全部存活成员 `[(pid, cmdline), ...]`（默认只看本用户）。"""
    if not pgid:
        return []
    me = os.getpid()
    my_uid = os.getuid()
    out = []
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == me:
            continue
        if uid_only:
            try:
                if os.stat('/proc/%d' % pid).st_uid != my_uid:
                    continue
            except OSError:
                continue
        st = read_stat(pid)
        if st is None or st['state'] == 'Z':
            continue
        if st['pgrp'] != int(pgid):
            continue
        out.append((pid, proc_cmdline(pid)))
    return out


def pgid_alive(pgid):
    """进程组是否仍存活（`killpg(pgid, 0)`；与 episode_runner `_group_alive` 同口径）。"""
    if not pgid:
        return False
    try:
        os.killpg(int(pgid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def signal_group(pgid, sig):
    if not pgid:
        return False
    try:
        os.killpg(int(pgid), sig)
        return True
    except ProcessLookupError:
        return False


def reap_process_group(pgid, sigint_s=REAP_SIGINT_S, sigkill_s=REAP_SIGKILL_S,
                       on_tick=None, proc=None):
    """受限进程组回收：SIGINT → 等待 → SIGKILL → 轮询确认整组退出。

 与 `episode_runner._reap_process_group` 的纪律一致（**只**动本 run 的进程组）；
 本实现额外**计数**被回收的成员并支持进度回调，因为演示过程要把"已清理 N 个进程"
 如实告诉使用者。

 返回 `{confirmed, members_before, members_after, sigint_sent, sigkill_sent,
 returncode, wall_s}`。
    """
    t0 = time.monotonic()
    before = pgid_members(pgid)
    res = {'pgid': pgid, 'members_before': [{'pid': p, 'cmd': c} for p, c in before],
           'cleaned_count': len(before), 'sigint_sent': False, 'sigkill_sent': False,
           'confirmed': True, 'returncode': None, 'wall_s': 0.0}
    if not pgid or not before:
        # 进程组已空：仍需确认 leader 已回收（Popen 可能尚未 wait）
        if proc is not None:
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
            res['returncode'] = proc.returncode
        res['wall_s'] = round(time.monotonic() - t0, 2)
        res['members_after'] = []
        return res

    res['sigint_sent'] = signal_group(pgid, signal.SIGINT)
    deadline = time.monotonic() + sigint_s
    last_tick = 0.0
    while pgid_members(pgid) and time.monotonic() < deadline:
        if proc is not None and proc.poll() is None:
            try:
                proc.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
        else:
            time.sleep(0.2)
        if on_tick is not None:
            t = time.monotonic() - t0
            if t - last_tick >= 2.0:
                last_tick = t
                on_tick(len(pgid_members(pgid)), t)

    if pgid_members(pgid):
        res['sigkill_sent'] = signal_group(pgid, signal.SIGKILL)
        deadline = time.monotonic() + sigkill_s
        while pgid_members(pgid) and time.monotonic() < deadline:
            time.sleep(0.2)

    if proc is not None:
        try:
            proc.wait(timeout=max(1.0, sigkill_s))
        except subprocess.TimeoutExpired:
            pass
        res['returncode'] = proc.returncode

    after = pgid_members(pgid)
    res['members_after'] = [{'pid': p, 'cmd': c} for p, c in after]
    # **判据口径**（ 实测修正）：`pgid_members` 只看**非僵尸**活进程，而
    # `killpg(pgid, 0)` 对"只剩僵尸"的组仍返回成功（僵尸已被回收、不再执行任何代码）。
    # 若用 `and not pgid_alive(pgid)`，会出现"members_after=[] 但 confirmed=False"的自相矛盾
    # （实测于 Ctrl-C 回收：36 个进程全清、无任何残留进程，却被判 FAIL）。
    # → 以**非僵尸成员清零**为判据；僵尸组单独记 `zombie_group_remaining` 供审计。
    res['confirmed'] = not after
    res['pgid_still_visible'] = pgid_alive(pgid)
    res['zombie_group_remaining'] = bool(not after and res['pgid_still_visible'])
    res['wall_s'] = round(time.monotonic() - t0, 2)
    return res


# --------------------------------------------------------------------------------------
# 本项目的进程特征（只用于**检测**残留 / 统计，不用于杀进程）
# --------------------------------------------------------------------------------------

# 与 `episode_runner.sweep_stale_processes` 同源的匹配口径：以 argv[0] 为准，`gz sim` 例外
# （其 argv[0] 是 ruby，改按命令行 + 守卫匹配，并排除 shell 自身）。
SHELL_EXES = ('/bin/bash', '/bin/sh', '/bin/dash', '/usr/bin/bash', '/usr/bin/sh')
STALE_RULES = (
    ('/install/agc_', ()),
    ('MicroXRCEAgent', ()),
    ('px4_sitl_default/bin/px4', ()),
    ('ros_gz_bridge/parameter_bridge', ('agc_world',)),
    ('tf2_ros/static_transform_publisher', ('agc_car', 'car/')),
    ('rviz2', ('agc_demo.rviz',)),
    ('gz sim', ('agc_world.sdf',)),
)


def project_processes():
    """本项目的仿真相关进程 `[{pid, cmd, exe, rule}]`（**只读**扫描，不杀）。"""
    me = os.getpid()
    my_uid = os.getuid()
    out = []
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == me:
            continue
        try:
            if os.stat('/proc/%d' % pid).st_uid != my_uid:
                continue
        except OSError:
            continue
        st = read_stat(pid)
        if st is None or st['state'] == 'Z':
            continue
        argv0 = proc_argv0(pid)
        if not argv0:
            continue
        cmd = proc_cmdline(pid)
        exe = proc_exe(pid)
        for pat, guard in STALE_RULES:
            if guard and pat == 'gz sim':
                if 'gz sim' in cmd and any(g in cmd for g in guard) and \
                        exe not in SHELL_EXES and argv0 not in SHELL_EXES:
                    out.append({'pid': pid, 'cmd': cmd, 'exe': exe, 'rule': pat})
                    break
                continue
            if pat in argv0 or pat in exe:
                if not guard or any(g in cmd for g in guard):
                    out.append({'pid': pid, 'cmd': cmd, 'exe': exe, 'rule': pat})
                    break
    return out


def gz_processes():
    """`gz sim` 进程（GUI 与 headless 的**结构性**区别：命令行是否含 `-s`）。"""
    out = []
    for p in project_processes():
        if p['rule'] == 'gz sim':
            argv = p['cmd']
            out.append({'pid': p['pid'], 'headless_flag': bool(re.search(r'(^|\s)-s(\s|$)', argv)),
                        'cmd': argv})
    return out


def rviz_processes():
    return [p for p in project_processes() if p['rule'] == 'rviz2']


# --------------------------------------------------------------------------------------
# 端口 / /dev/shm
# --------------------------------------------------------------------------------------

def port_is_free(port, host='127.0.0.1'):
    """尝试独占绑定（不监听外部），立刻释放 —— 与"端口空闲"判据等价，且不启动仿真。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s.bind((host, int(port)))
        return True, ''
    except OSError as e:
        return False, '%s' % e
    finally:
        s.close()


def shm_segment_count(pattern='fastrtps'):
    try:
        names = os.listdir('/dev/shm')
    except OSError:
        return None
    return sum(1 for n in names if pattern in n)


# --------------------------------------------------------------------------------------
# 运行状态文件（`stop` 的唯一定位依据）
# --------------------------------------------------------------------------------------

def _try_lock():
    """独占实例锁；已有活实例 → 返回已占用（读 current.json 供人话提示）。"""
    ensure_dir(STATE_DIR)
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd, None
    except OSError:
        cur = read_json(CURRENT_JSON, {}) or {}
        os.close(fd)
        return None, cur


def acquire_instance(run_dir, **meta):
    """登记本次启动的唯一身份。已有活实例 → 抛 `DemoError`（exit 4，不抢占）。"""
    fd, cur = _try_lock()
    if fd is None:
        sup = (cur or {}).get('supervisor_pid')
        alive = pid_alive(sup) and (cur or {}).get('state') == 'running'
        if alive:
            raise DemoError(
                '已有一个演示实例在运行（pid=%s，目录=%s）' % (cur.get('supervisor_pid'),
                                                              cur.get('run_dir')),
                ['同一时刻只允许一个演示实例（同机仿真必须串行）。',
                 '停止它：./run_demo.sh stop',
                 '查看它：tail -f %s' % os.path.join(cur.get('run_dir') or '?', 'progress.log')],
                exit_code=4, detail={'existing': cur})
        # 陈旧状态文件（上一个实例被硬杀）：接管，但把它如实记进新实例的证据。
        stale = dict(cur or {})
        with open(fd, 'w') as f:
            f.write('%d\n' % os.getpid())
    else:
        stale = None
        with open(fd, 'w') as f:
            f.write('%d\n' % os.getpid())

    doc = {
        'schema': 'demo-instance-v1',
        'instance_id': uuid.uuid4().hex[:12],
        'state': 'starting',
        'run_dir': run_dir,
        'supervisor_pid': os.getpid(),
        'supervisor_pgid': os.getpgid(0),
        'launch_pid': None,
        'launch_pgid': None,
        'started_at': now_iso(),
        'stale_previous': stale,
    }
    doc.update(meta)
    write_json(CURRENT_JSON, doc)
    _write_pids(doc)
    return fd, doc


def update_instance(patch):
    """更新运行状态（read-modify-write；字段级合并）。"""
    cur = read_json(CURRENT_JSON, {}) or {}
    cur.update(patch)
    write_json(CURRENT_JSON, cur)
    _write_pids(cur)
    return cur


def release_instance(fd, final_state='finished', keep_record=True):
    """退出时释放锁；`current.json` 置终态（保留为证据，`stop` 见非 running 即幂等返回）。"""
    cur = read_json(CURRENT_JSON, {}) or {}
    cur['state'] = final_state
    cur['released_at'] = now_iso()
    write_json(CURRENT_JSON, cur)
    _write_pids(cur)
    try:
        if fd is not None:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except OSError:
        pass
    return cur


def _write_pids(doc):
    """人可读的 PID 清单（派工单"记录 PID"；机器可读的是 current.json）。"""
    lines = ['# run_demo 运行状态（机器可读版：current.json；本文件供人看）',
             'state=%s' % doc.get('state'),
             'instance=%s' % doc.get('instance_id'),
             'run_dir=%s' % doc.get('run_dir'),
             'supervisor_pid=%s' % doc.get('supervisor_pid'),
             'supervisor_pgid=%s' % doc.get('supervisor_pgid'),
             'launch_pid=%s' % doc.get('launch_pid'),
             'launch_pgid=%s' % doc.get('launch_pgid'),
             'started_at=%s' % doc.get('started_at')]
    tmp = '%s.tmp.%d' % (PIDS_FILE, os.getpid())
    try:
        with open(tmp, 'w') as f:
            f.write('\n'.join(lines) + '\n')
        os.replace(tmp, PIDS_FILE)
    except OSError:
        pass


def current_instance():
    return read_json(CURRENT_JSON, {}) or {}
