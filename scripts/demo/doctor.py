#!/usr/bin/env python3
"""`run_demo.sh doctor` —— 环境预检（**不启动任何仿真**，≤30 s，逐行 OK/FAIL）。

检查单落地自 [整链排障速查 启动前检查](../../docs/conventions/整链排障速查.md#preflight)。
每条检查返回 `(id, status, title, detail, hint)`：

 * `status` ∈ `OK` / `FAIL` / `WARN` / `SKIP`；
 * `FAIL` 决定退出码（非 0），并在末尾给出**人话**处置建议；
 * `WARN` 不影响退出码，但**必须**打印（例如 `/dev/shm` 段偏多——不阻塞，但值得知道）。

纪律：
 * **不启动** GZ / PX4 / GUI / headless / full 链（只读文件、绑一个 socket 再立刻释放）；
 * **不清理**别人的进程、不改环境、不删产物；
 * 每项都要给出**判据**（测得什么、阈值是什么），不写"看起来正常"。
"""

import os
import shutil
import subprocess
import time

import common
import dds_transport

OK, FAIL, WARN, SKIP = 'OK', 'FAIL', 'WARN', 'SKIP'

# ROS 环境与工作区（ plan 的 8 包口径 = 实际 colcon 包集合）。
ROS_SETUP = '/opt/ros/jazzy/setup.bash'
WORKSPACE_PACKAGES = (
    'agc_sim', 'agc_perception', 'agc_ground', 'agc_air',
    'agc_task', 'agc_rl', 'agc_msgs', 'px4_msgs',
)
TOOLCHAIN_BINS = (
    'toolchain/bin/MicroXRCEAgent',
    'toolchain/PX4-Autopilot/build/px4_sitl_default/bin/px4',
)
AGENT_PORTS = (8888, 8889)
SHM_WARN_THRESHOLD = 200
DOCTOR_BUDGET_S = 30.0


def _which(name):
    return shutil.which(name)


def check_ros():
    if not os.path.exists(ROS_SETUP):
        return (FAIL, 'ROS 2 Jazzy 已安装',
                '缺少 %s' % ROS_SETUP,
                ['先装 ROS 2 Jazzy（Ubuntu 24.04）：https://docs.ros.org/en/jazzy/'])
    amb = os.environ.get('AMENT_PREFIX_PATH', '')
    if ROS_SETUP.split('/setup.')[0] not in amb:
        return (FAIL, 'ROS 环境已 source',
                '当前 shell 没有 source ROS 2 Jazzy（AMENT_PREFIX_PATH 不含 /opt/ros/jazzy）',
                ['source /opt/ros/jazzy/setup.bash 后重试（run_demo.sh 会自动 source）'])
    return (OK, 'ROS 2 Jazzy 环境', '已 source（AMENT_PREFIX_PATH 含 /opt/ros/jazzy）', [])


def check_ros2_cli():
    path = _which('ros2')
    if not path:
        return (FAIL, 'ros2 命令可用', 'PATH 中找不到 ros2',
                ['source /opt/ros/jazzy/setup.bash 后重试'])
    return (OK, 'ros2 命令行', path, [])


def check_workspace():
    missing = [p for p in WORKSPACE_PACKAGES if not os.path.isdir(os.path.join(common.ROOT, 'install', p))]
    if missing:
        return (FAIL, '工作区已构建',
                '缺少 %d/%d 个包：%s' % (len(missing), len(WORKSPACE_PACKAGES), ', '.join(missing)),
                ['先构建：cd %s && colcon build --symlink-install' % common.ROOT])
    return (OK, '工作区已构建（%d 包）' % len(WORKSPACE_PACKAGES),
            'install/{agc_sim,agc_perception,agc_ground,agc_air,agc_task,agc_rl,agc_msgs,px4_msgs} 均在位', [])


def check_workspace_sourced():
    """`install/setup.bash` 是否已 source（只查变量，不执行它）。"""
    prefix = os.path.join(common.ROOT, 'install')
    amb = os.environ.get('AMENT_PREFIX_PATH', '')
    if prefix not in amb:
        return (FAIL, '工作区环境已 source',
                '当前 shell 没有 source 工作区（AMENT_PREFIX_PATH 不含 %s）' % prefix,
                ['source install/setup.bash 后重试（run_demo.sh 会自动 source）'])
    return (OK, '工作区环境已 source', 'AMENT_PREFIX_PATH 含 install/', [])


def check_toolchain():
    missing = [p for p in TOOLCHAIN_BINS if not os.path.exists(os.path.join(common.ROOT, p))]
    if missing:
        return (FAIL, '工具链二进制在位',
                '缺少：%s' % ', '.join(missing),
                ['工具链未构建，见 toolchain/README.md',
                 '若只需要轻量栈快跑：./run_demo.sh --backend lightweight'])
    return (OK, '工具链二进制', 'MicroXRCEAgent + px4_sitl_default/bin/px4 在位', [])


def check_domain_id():
    raw = os.environ.get('ROS_DOMAIN_ID', '')
    if raw.strip() in ('', '0'):
        return (OK, 'ROS_DOMAIN_ID', '未设置或 0（脚本保持默认 0）', [])
    return (FAIL, 'ROS_DOMAIN_ID 为 0 或未设',
            'ROS_DOMAIN_ID=%s（应为空或 0）' % raw,
            ['自设非 0 域会导致 lifecycle 服务数据面不通（话题却正常）',
             'unset ROS_DOMAIN_ID 后重试'])


def check_discovery_range():
    """发现范围 / 传输：按本机 **能力探测** 给结论，不再断言"必须 LOCALHOST"。

 判据见 docs/conventions/整链排障速查.md#dds-transport：`lo` 无 `IFF_MULTICAST` 时
 `LOCALHOST` 在 1:1 拓扑下稳定零送达（多进程偶通），须改 `SUBNET`+`SHM`。
    """
    try:
        resolved = dds_transport.resolve()
        summary = dds_transport.describe()
    except ValueError as exc:
        return (FAIL, 'DDS 传输策略非法', str(exc),
                ['改用 AGC_DDS_TRANSPORT_POLICY=auto（按能力探测）或 unset 后重试'])
    lo_mc = dds_transport.lo_has_multicast()
    val = os.environ.get('ROS_AUTOMATIC_DISCOVERY_RANGE', '')
    note = 'lo multicast=%s → 生效 %s' % ('yes' if lo_mc else 'no', resolved)
    if val and val != dds_transport.env_for(resolved)['ROS_AUTOMATIC_DISCOVERY_RANGE']:
        return (WARN, 'ROS_AUTOMATIC_DISCOVERY_RANGE 与探测不一致',
                '%s（脚本启动时会覆盖）' % val, [summary])
    return (OK, 'ROS_AUTOMATIC_DISCOVERY_RANGE', note, [summary])


def check_plugin_path():
    """`GZ_SIM_SYSTEM_PLUGIN_PATH` 未定义会让 world_bringup 抛异常（MAP_DESIGN_PLAYBOOK 14.2）。"""
    val = os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')
    if val:
        return (OK, 'GZ_SIM_SYSTEM_PLUGIN_PATH', val, [])
    return (OK, 'GZ_SIM_SYSTEM_PLUGIN_PATH',
            '未设置（脚本启动时补 %s）' % common.GZ_PLUGIN_DIR, [])


def check_world_sdf():
    if not os.path.exists(common.WORLD_SDF):
        return (FAIL, '世界文件在位', common.WORLD_SDF, ['先 colcon build 生成 install/agc_sim'])
    size = os.path.getsize(common.WORLD_SDF)
    return (OK, '世界文件', '%s（%d 字节）' % (os.path.relpath(common.WORLD_SDF, common.ROOT), size), [])


def _own_instance_pgids():
    """本脚本**自己**实例的进程组（正在跑的那个演示）—— 这不是"残留"。

 实测：起第二个实例时，preflight 把第一个实例的 22 个子进程报成
 "有残留进程"，同时又报"已有一个演示实例在运行" —— 两条信息自相矛盾、互相打架，
 使用者会被误导到去 `stop` 一个其实正常运行的演示。
    残留 = 本项目特征进程 **减去** current.json 登记的那个实例的 PGID 成员。
    """
    cur = common.current_instance()
    if cur.get('state') not in ('starting', 'running', 'terminating'):
        return set()
    pgids = set()
    for key in ('launch_pgid', 'supervisor_pgid'):
        pgid = cur.get(key)
        if pgid:
            try:
                pgids.add(int(pgid))
            except (TypeError, ValueError):
                continue
    return pgids


def check_residual_processes():
    procs = common.project_processes()
    own = _own_instance_pgids()
    if own:
        kept = []
        for p in procs:
            st = common.read_stat(p['pid'])
            if st is not None and st['pgrp'] in own:
                continue        # 本实例自己的成员：不是残留
            kept.append(p)
        procs = kept
    note = '（已排除本实例自身 PGID %s）' % sorted(own) if own else ''
    if not procs:
        return (OK, '无本项目残留进程',
                'ps 扫描（argv[0]/exe 匹配 7 类特征）0 命中%s' % note, [])
    detail = '；'.join('pid %d %s' % (p['pid'], p['cmd'][:90]) for p in procs[:4])
    more = '' if len(procs) <= 4 else ' …（共 %d 个）' % len(procs)
    return (FAIL, '无本项目残留进程',
            '有 %d 个本项目残留进程：%s%s' % (len(procs), detail + more, note),
            ['先 ./run_demo.sh stop',
             '若是外部终止留下的孤儿，按 PID 清理：kill <pid>（禁止 pkill -f）'])


def check_ports():
    busy = []
    for port in AGENT_PORTS:
        free, err = common.port_is_free(port)
        if not free:
            busy.append((port, err))
    if busy:
        return (FAIL, 'Agent 端口空闲',
                '；'.join('%d: %s' % (p, e) for p, e in busy),
                ['找出占用者：ss -lntp | grep -E "%s"' % '|'.join(str(p) for p in AGENT_PORTS),
                 '停掉占用进程后重试（端口 8888/8889 由 main.launch.py 固定）'])
    return (OK, 'Agent 端口空闲', '8888 / 8889 可绑定', [])


def check_shm():
    n = common.shm_segment_count()
    if n is None:
        return (SKIP, '/dev/shm 不可读', '无法列目录', [])
    if n >= SHM_WARN_THRESHOLD:
        return (WARN, '/dev/shm 残留段偏多',
                'fastrtps 段 %d ≥ 阈值 %d' % (n, SHM_WARN_THRESHOLD),
                ['确认无 ROS 进程后可清理：rm -f /dev/shm/fastrtps_*',
                 '（脚本不代你清：会误删同机其它 DDS 系统的段）'])
    return (OK, '/dev/shm 残留段', 'fastrtps 段 %d < 阈值 %d' % (n, SHM_WARN_THRESHOLD), [])


def check_display(want_gui=True):
    if not want_gui:
        return (SKIP, '图形显示（headless 不需要）', '--headless：只用 gz -s，无渲染客户端', [])
    display = os.environ.get('DISPLAY', '')
    if not display:
        return (FAIL, '图形显示可用',
                '没有图形显示（DISPLAY 未设置）',
                ['GUI 演示需要 X11/Wayland 显示；无显示时改用：./run_demo.sh --headless'])
    xdpyinfo = shutil.which('xdpyinfo')
    if xdpyinfo:
        try:
            r = subprocess.run([xdpyinfo, '-display', display], capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            r = None
        if r is not None and r.returncode != 0:
            return (FAIL, '图形显示可用', 'xdpyinfo %s 失败（rc=%d）' % (display, r.returncode),
                    ['检查 X server / WSLg 是否在运行；或改用 --headless'])
    return (OK, '图形显示', 'DISPLAY=%s%s' % (display, '（xdpyinfo 可用）' if xdpyinfo else ''), [])


def check_previous_instance():
    cur = common.current_instance()
    state = cur.get('state')
    sup = cur.get('supervisor_pid')
    if state == 'running' and common.pid_alive(sup):
        return (FAIL, '无遗留演示实例',
                '已有一个演示实例在运行（pid=%s dir=%s）' % (sup, cur.get('run_dir')),
                ['停止它：./run_demo.sh stop'])
    if state == 'running' and not common.pid_alive(sup):
        return (WARN, '上次演示残留了状态文件',
                'pid=%s 已不存在（state=running）' % sup,
                ['./run_demo.sh stop 会按记录的 PGID 回收残留'])
    return (OK, '无遗留演示实例', 'state=%s' % (state or 'none'), [])


CHECKS = (
    ('ros', 'ROS 环境', check_ros),
    ('ros2', 'ros2 CLI', check_ros2_cli),
    ('workspace', '工作区已构建', check_workspace),
    ('sourced', '工作区已 source', check_workspace_sourced),
    ('toolchain', '工具链二进制', check_toolchain),
    ('domain', 'ROS_DOMAIN_ID', check_domain_id),
    ('discovery', '发现范围', check_discovery_range),
    ('plugin', 'GZ 插件路径', check_plugin_path),
    ('world', '世界文件', check_world_sdf),
    ('residual', '残留进程', check_residual_processes),
    ('ports', 'Agent 端口', check_ports),
    ('shm', 'DDS 共享内存', check_shm),
    ('display', '图形显示', check_display),
    ('instance', '遗留实例', check_previous_instance),
)


def run_checks(want_gui=True, only=None):
    results = []
    for key, title, fn in CHECKS:
        if only and key not in only:
            continue
        t0 = time.monotonic()
        try:
            if key == 'display':
                status, name, detail, hints = fn(want_gui=want_gui)
            else:
                status, name, detail, hints = fn()
        except Exception as e:                     # noqa: BLE001 —— 预检本身不得抛栈给使用者
            status, name, detail, hints = FAIL, title, '检查本身出错：%s' % e, [
                '这是 run_demo 的缺陷，请把本行连同上下文反馈给维护者']
        results.append({'key': key, 'title': title, 'name': name, 'status': status,
                        'detail': detail, 'hints': hints,
                        'elapsed_s': round(time.monotonic() - t0, 3)})
    return results


def summarize(results):
    counts = {}
    for r in results:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    return {
        'counts': counts,
        'ok': counts.get(FAIL, 0) == 0,
        'failed_keys': [r['key'] for r in results if r['status'] == FAIL],
        'warned_keys': [r['key'] for r in results if r['status'] == WARN],
    }


def render(results, elapsed_s, stream=None, prefix=''):
    import sys
    stream = stream or sys.stdout
    width = 26
    for r in results:
        line = '[doctor] %-6s %-*s %s' % (r['status'], width, r['name'], r['detail'])
        print(prefix + line, file=stream, flush=True)
    s = summarize(results)
    verdict = 'PASS' if s['ok'] else 'FAIL'
    print('[doctor] ------ %s（%.2f s / 预算 %.0f s）/ %s' % (
        verdict, elapsed_s, DOCTOR_BUDGET_S,
        ' '.join('%s=%d' % (k, v) for k, v in sorted(s['counts'].items()))), file=stream, flush=True)
    if not s['ok']:
        print('', file=stream)
        for r in results:
            if r['status'] != FAIL:
                continue
            print('[doctor] %s 失败：%s' % (r['name'], r['detail']), file=stream)
            for h in r['hints']:
                print('[doctor]   → %s' % h, file=stream)
    elif s['warned_keys']:
        for r in results:
            if r['status'] != WARN:
                continue
            print('[doctor] 注意 %s：%s' % (r['name'], r['detail']), file=stream)
            for h in r['hints']:
                print('[doctor]   → %s' % h, file=stream)
    return s
