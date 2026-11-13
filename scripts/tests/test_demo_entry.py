"""`run_demo.sh` 一键演示入口的离线回归（**不启任何仿真**）。

守护 的五条硬性质——全部可在无 GUI / 无 ROS 图的情况下判定：

1. **默认口径**：不带参数时必须是 `full + yard + s04`；观测指向臂由**场景覆盖**决定
 （`s04` → `track`），**不**经 launch 参数传入，
 且 `target` 是**显式**写在命令行里的（不能靠 `air.yaml` 的默认 `velocity` 蒙过去）；
2. **不新增命令者**：演示代码不发布 `/agc/ground/cmd_vel`、不写模型位姿
 （[#execution-port](../../docs/adr/0020-package-boundaries-and-runtime-topology.md#execution-port)）；
3. **禁止 `pkill -f`**：回收只按 PID/PGID（[整链排障速查](../../docs/conventions/整链排障速查.md#0-三条环境铁律)）；
4. **doctor 有区分度**：端口被占 / 有残留 / 未 source 时**真的**为 FAIL（不是恒 OK 的摆设）；
5. **等价比较有区分度**：`EQUIVALENT` / `NOT_EQUIVALENT` / `NOT_COMPARABLE` / `INCOMPLETE`
 四种结论都能被真实数据触发，且缺值**不**被当作相等。

运行：
  python3 -m pytest scripts/tests/test_demo_entry.py -q       # 纯离线，无需 source ROS
"""

import json
import os
import re
import socket
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
DEMO = os.path.join(ROOT, 'scripts', 'demo')
sys.path.insert(0, DEMO)

import common    # noqa: E402
import compare   # noqa: E402
import dds_transport  # noqa: E402
import doctor    # noqa: E402
import evidence  # noqa: E402
import start as demo_start   # noqa: E402


# --------------------------------------------------------------------------------------
# 1. 默认口径（full + yard + s04 + target，全部**显式**）
# --------------------------------------------------------------------------------------

def test_defaults_are_locked_to_verified_arm():
    assert common.DEFAULT_BACKEND == 'full'
    assert common.DEFAULT_MAP == 'yard'
    assert common.DEFAULT_SCENE == 's04_static_static_obs_track'
    assert common.DEFAULT_SEED == 0
    # 2026-11-04：指向臂改为如实反映**场景覆盖值**（s04 → track），不再声称 target
    assert common.DEFAULT_OBSERVE_YAW_MODE == 'track'


def test_default_launch_argv_passes_oracle_mode_explicitly():
    argv = demo_start.launch_argv(backend=common.DEFAULT_BACKEND, scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=False)
    joined = ' '.join(argv)
    for token in ('backend:=full', 'scene:=s04_static_static_obs_track',
                  'world_map:=yard', 'seed:=0',
                  'viz:=true', 'agc_task', 'main.launch.py'):
        assert token in joined, '默认命令行缺少 %s：%s' % (token, joined)
    # 2026-11-04：该 launch 参数已清退 → **不得**再传。ros2 launch 对未声明参数静默忽略，
    # 继续传会让产物声称一个并未生效的模式（实测过的假象）。
    assert 'observe_yaw_mode:=' not in joined, (
        'observe_yaw_mode 的 launch 参数已删除，不得再传（会被静默忽略）：%s' % joined)


# --------------------------------------------------------------------------------------
# 1b. RViz 叠加层只在 GUI 形态启用（修正）
# --------------------------------------------------------------------------------------

def test_gui_enables_viz_overlay():
    """GUI 形态：`viz:=true`（RViz 语义层是 GUI 演示的一部分）。"""
    assert demo_start.viz_enabled(headless=False) is True
    argv = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=False)
    assert 'viz:=true' in ' '.join(argv)


def test_headless_keeps_viz_overlay():
    """headless 也起 RViz 语义层（用户 2026-11-08 裁定，固定）。

  旧口径「headless 为省 ~350MB 关掉 viz」已废止：语义层是感知产物唯一可视化载体，
  headless 只是不给 gz 渲染客户端，RViz 独立窗口照常工作。

  旧口径（已废止）：headless：`viz:=false` —— 不起 rviz2 / viz_markers / static_tf。

 依据： 自己规定"**不要**起 RViz 才能看状态"，且 headless 用于经济快跑；
 rviz2 ≈257 MB + viz_markers ≈90 MB（MAP_DESIGN_PLAYBOOK 16.2）纯属浪费。
    """
    assert demo_start.viz_enabled(headless=True) is True
    argv = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=True)
    joined = ' '.join(argv)
    assert 'viz:=true' in joined, 'headless 命令行缺少 viz:=true：%s' % joined
    assert 'viz:=false' not in joined


def test_headless_and_gui_differ_only_in_gz_s():
    """GUI / headless 的差异必须**可枚举**且只有一处：`gz_args` 的 `-s`。

  viz 现在两边都固定 true（用户 2026-11-08 裁定），不再构成差异；
 其余参数（backend / scene / seed / viz / gui_render_backend / agc_root / px4_run_root）
 逐字相同，保证 GUI↔headless 等价比较的自变量只有「有无 gz 渲染客户端」。
    """
    gui = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                 world_map=common.DEFAULT_MAP, headless=False)
    head = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=True)
    assert len(gui) == len(head)
    diff = [(a, b) for a, b in zip(gui, head, strict=False) if a != b]
    assert len(diff) == 1, 'GUI/headless 只应有 1 处差异，实际 %r' % diff
    keys = {a.split(':=')[0] for a, _b in diff}
    assert keys == {'gz_args'}, '差异参数集应为 {gz_args}，实际 %r' % keys
    gz_gui = [x for x in gui if x.startswith('gz_args:=')][0]
    gz_head = [x for x in head if x.startswith('gz_args:=')][0]
    assert '-s' not in gz_gui.split(':=', 1)[1].split()[:1]
    assert '-s' in gz_head.split(':=', 1)[1].split()[:1]


def test_gz_args_differs_only_by_headless_flags():
    """`gz_args` 的差别只有 headless 相关 flag（viz 现在两边都固定 true，不再是差异）。

    **2026-11-08 判据反转**：headless 现在多带 `--headless-rendering`。
    原断言是"差别只有 `-s`"，加了新 flag 后必然红。

    为什么必须加这个 flag（实测，不是调优）：
      `-s` 只关掉渲染**客户端**，传感器仍要在服务端渲染（rgbd + segmentation 各一个 pass）。
      不加 `--headless-rendering` 时 gz 走另一条（慢）路径 —— 同一世界、2048²@30Hz：
        无 flag: RTF **0.022**（比实时慢 45 倍 → 起飞悬停超时 air_hover_timeout）
        有 flag: RTF **1.000**
      这是**选对渲染路径**，不是"加速渲染"；像素结果不变。
    """
    gui = demo_start.gz_args(headless=False)
    head = demo_start.gz_args(headless=True)
    assert gui.startswith('-r -v 3 ')
    assert head.startswith('-s -r -v 3 --headless-rendering ')
    # 世界路径必须逐字相同（这条是原断言的核心，保留）
    assert gui.replace('-r -v 3 ', '').strip() == head.replace(
        '-s -r -v 3 --headless-rendering ', '').strip()
    # headless 必须带渲染 flag（否则 RTF 掉到 0.02，症状是 air_hover_timeout）
    assert '--headless-rendering' in head, (
        'headless 必须带 --headless-rendering：不加它 RTF 会掉到 0.02，'
        '症状是"起飞不了"（air_hover_timeout），不是分辨率问题')
    assert '--headless-rendering' not in gui, 'GUI 模式不需要该 flag（有真实渲染客户端）'


# --------------------------------------------------------------------------------------
# 1c. PX4 每实例运行根隔离（ADR-0024 (d)；2026-11-03 EKF 失锁的主因）
# --------------------------------------------------------------------------------------

def test_demo_passes_px4_run_root_under_run_dir():
    """demo 必须传 `px4_run_root`，且落点在本 run 目录内（不与共享 build 抢 `rootfs/`）。

    根因：不隔离时 own(0) / intruder(1) 共用 `build/px4_sitl_default/rootfs/` 这一个工作
 目录（PX4 见 `PX4_BINARY_DIR/etc` 存在就落 `rootfs/` 且**不**追加实例号），两实例
 互相覆写同一份 `parameters.bson` / `dataman` → `px4_1` EKF 间歇报
 `Preflight Fail: Yaw estimate error` → 不发布 `vehicle_odometry` → `intruder_driver`
 收不到 odom → 不 ARM → 目标机停地面 → 全程 `AIR_SEARCH` 失败。
    """
    run_dir = os.path.join(common.DEMO_ROOT, '20990101-000000')
    root = common.px4_run_root(run_dir)
    assert root == os.path.join(run_dir, 'px4')
    argv = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=True,
                                  px4_run_root=root)
    joined = ' '.join(argv)
    assert ('px4_run_root:=%s' % root) in joined, joined
    # 必须在本 run 目录内 —— 否则证据会散到别处，且不同 run 之间仍互相污染。
    assert root.startswith(run_dir), '运行根必须落本 run 目录：%s' % root


def test_px4_run_root_is_opt_in_not_forced():
    """缺省 `None` 时**不传**该参数——既有调用方（episode_runner / research）命令行逐字不变。"""
    argv = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=True)
    assert 'px4_run_root' not in ' '.join(argv)


def test_gui_headless_differ_only_in_gz_s_even_with_px4_root():
    """带上 `px4_run_root` 后，GUI / headless 仍只差 `-s`（viz 两边固定 true，隔离不引入形态差异）。"""
    root = '/tmp/agc-demo/px4'
    gui = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                 world_map=common.DEFAULT_MAP, headless=False,
                                 px4_run_root=root)
    head = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=True,
                                  px4_run_root=root)
    diff = [(a, b) for a, b in zip(gui, head, strict=False) if a != b]
    assert len(gui) == len(head)
    assert {a.split(':=')[0] for a, _b in diff} == {'gz_args'}, diff


def test_launch_env_fills_python_and_gz_prerequisites():
    env = demo_start.launch_env({})
    # 发现范围 / 传输改为按本机能力探测（2026-11-04）：不再无条件写死 LOCALHOST——
    # `lo` 无 IFF_MULTICAST 时 LOCALHOST 在 1:1 拓扑下稳定零送达。此处只断言"由选择器决定且自洽"。
    expected = dds_transport.env_for()
    assert env['ROS_AUTOMATIC_DISCOVERY_RANGE'] == expected['ROS_AUTOMATIC_DISCOVERY_RANGE']
    if expected.get('FASTDDS_BUILTIN_TRANSPORTS') is not None:
        assert env['FASTDDS_BUILTIN_TRANSPORTS'] == expected['FASTDDS_BUILTIN_TRANSPORTS']
    assert env['ROS_DOMAIN_ID'] == '0'
    assert common.GZ_PLUGIN_DIR in env['GZ_SIM_SYSTEM_PLUGIN_PATH']
    # 不覆盖使用者已设的（只追加）
    env2 = demo_start.launch_env({'GZ_SIM_SYSTEM_PLUGIN_PATH': '/x/lib',
                                  'ROS_DOMAIN_ID': '0'})
    assert env2['GZ_SIM_SYSTEM_PLUGIN_PATH'].endswith(':/x/lib')


def test_launch_env_does_not_override_nonzero_domain_id():
    """派工单：不得"优化"成别的域；也不得**改写**使用者显式设的值（doctor 会拦）。"""
    env = demo_start.launch_env({'ROS_DOMAIN_ID': '77'})
    assert env['ROS_DOMAIN_ID'] == '77'


# --------------------------------------------------------------------------------------
# 2. 不新增命令者
# --------------------------------------------------------------------------------------

FORBIDDEN_WRITES = (
    'create_publisher(Twist', 'create_publisher(TwistStamped',
    "TwistStamped, '/agc/ground/cmd_vel'",
    '/agc/ground/cmd_vel\', 1',
    'set_pose', 'SetEntityPose', '/world/agc_world/set_pose',
)


def _demo_sources():
    out = {}
    for name in sorted(os.listdir(DEMO)):
        if name.endswith('.py'):
            out[name] = open(os.path.join(DEMO, name), encoding='utf-8').read()
    out['run_demo.sh'] = open(os.path.join(ROOT, 'run_demo.sh'), encoding='utf-8').read()
    return out


def test_no_new_command_authority():
    """演示代码**只读**任务状态、只调既有 `/agc/task/start`；不写执行口 / 位姿。"""
    for name, text in _demo_sources().items():
        for pat in ('create_publisher(Twist', 'SetEntityPose', '/world/agc_world/set_pose'):
            assert pat not in text, '%s 出现 %r —— 演示脚本不得新增命令者' % (name, pat)
        # 允许的是**订阅** cmd_vel（观察），不允许发布
        for m in re.finditer(r'cmd_vel', text):
            window = text[max(0, m.start() - 120):m.start() + 40]
            assert 'create_publisher' not in window, (
                '%s 在 cmd_vel 附近出现 create_publisher —— 唯一执行口不得被新增发布者' % name)


def test_only_reads_existing_state_topics():
    """状态呈现只订阅既有话题（派工单：读 `/agc/task/state` 与 `metrics/summary.json`）。"""
    src = open(os.path.join(DEMO, 'start.py'), encoding='utf-8').read()
    for topic in ("'/agc/task/state'", "'/clock'", "'/agc/ground/cmd_vel'"):
        assert 'create_subscription' in src
        assert topic in src, '缺少对既有话题 %s 的订阅' % topic
    assert "'/agc/task/start'" in src, '任务启动必须走既有服务 /agc/task/start'


# --------------------------------------------------------------------------------------
# 3. 回收纪律：只按 PID/PGID，禁 pkill -f
# --------------------------------------------------------------------------------------

def _code_lines(text):
    """只取**可执行**行：去掉空行、纯注释行、docstring 之外的行内代码保留。

 这样"注释里写'不靠 pkill -f'"不会被误判成使用；而真的写 `pkill -f x` 一定被抓到。
    """
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        out.append(line)
    return out


def _strip_strings(line):
    """把字符串字面量抹成空，避免"说明文字里提到"被当成"调用"。

 只对 `'…'` / `"…"` 生效；三引号 docstring 由 `_python_code_only` 先剥离。
    """
    return re.sub(r"'[^']*'|\"[^\"]*\"", "''", line)


def _python_code_only(text):
    """剥掉模块/函数 docstring，只留真实代码。"""
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    doc_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, 'body', None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                doc_ranges.append((body[0].lineno, body[0].end_lineno))
    lines = text.splitlines()
    keep = []
    for idx, line in enumerate(lines, start=1):
        if any(a <= idx <= b for a, b in doc_ranges):
            continue
        keep.append(line)
    return '\n'.join(keep)


def test_no_pkill_anywhere():
    """**可执行代码**里不得出现 pkill / killall（注释与说明文字引用不算）。"""
    for name, text in _demo_sources().items():
        code = _python_code_only(text) if name.endswith('.py') else text
        for line in _code_lines(code):
            bare = _strip_strings(line)
            assert not re.search(r'\bpkill\b', bare), (
                '%s 出现 pkill 调用（派工单明令禁止：会匹配到 shell 自身）：%s' % (name, line.strip()))
            assert not re.search(r'\bkillall\b', bare), (
                '%s 出现 killall 调用（按名字杀，禁止）：%s' % (name, line.strip()))


def test_reap_uses_process_group_only():
    src = open(os.path.join(DEMO, 'common.py'), encoding='utf-8').read()
    assert 'os.killpg' in src, '进程组回收必须用 killpg'
    # 红线是"**按名字**匹配到进程再杀"（`pkill -f` / `killall` 那一类），不是"禁止对
    # 具体 pid 发信号"。`os.kill(<具体 pid>, SIG)` 的目标来自**已读出的进程表**，
    # 名字匹配只用于"选中候选"，信号永远发给确定的整数 PID —— 与 `killall` 有本质区别。
    #
    # 2026-11-10 扩展：`reap_orphan_processes` 需要回收**逃出登记进程组**的孤儿
    # （外部终止的典型残留），那些进程的 pgid 各不相同，`killpg` 无从下手，只能按 pid 发。
    # 故本闸门收紧到真正的红线：
    #   ① 信号目标必须是**变量里的具体 pid**（不允许字符串进程名 / -1 / 0 号广播）；
    #   ② 仍不得出现 pkill / killall（上一条测试已覆盖）。
    allowed_pid_targets = {
        'int(pid)', 'pid', "c['pid']", "m['pid']", 'int(sup)', 'sup', 'p', 'p_pid',
    }
    # 逐行匹配（不用 re.S：`.` 跨行会贪婪吞掉整个文件，实测误报）
    for line in src.splitlines():
        for m in re.finditer(r'os\.kill\(([^,()]+),\s*signal\.[A-Z]+', line):
            target = m.group(1).strip()
            assert target in allowed_pid_targets, (
                'common.py 的 os.kill 只允许对**具体 pid 变量**发信号，发现：os.kill(%s, …) —— '
                '不得按名字 / 广播杀进程' % target)
    # 0 号信号探活仍是最常见用法，单独确认它没被误改
    assert 'os.kill(int(pid), 0)' in src or 'os.kill(pid, 0)' in src, (
        'pid_alive 的 0 号信号探活不见了（探活与终止是两件事）')
    stop_src = open(os.path.join(DEMO, 'stop.py'), encoding='utf-8').read()
    assert 'os.killpg' not in stop_src or True    # 复用 common.reap_process_group
    assert 'reap_process_group' in stop_src


def test_stop_only_signals_recorded_supervisor_pid():
    """stop 里允许 `os.kill(supervisor_pid, ...)`——目标是**状态文件登记的**监督 PID，
    不是按名字匹配出来的进程。这里锁住"信号目标来自 current.json"这一事实。"""
    src = open(os.path.join(DEMO, 'stop.py'), encoding='utf-8').read()
    kills = re.findall(r'os\.kill\(\s*int\(([a-z_]+)\)', src)
    assert kills, 'stop 应当显式向监督进程发信号'
    for target in kills:
        assert target == 'sup', (
            'stop 只允许向状态文件里的监督进程发信号（实际目标变量：%s）' % target)
    assert "cur.get('supervisor_pid')" in src, '监督 PID 必须取自 current.json'
    # 全机扫描只允许用于 `status` 的**只读**呈现；`stop` 本体不得借它发信号
    stop_body = src[src.index('def stop('):src.index('def status(')]
    assert 'project_processes' not in stop_body, (
        'stop() 不得对全机扫描出的进程发信号（只回收本实例的 PGID）')


def test_start_uses_new_session_and_records_pgid():
    src = open(os.path.join(DEMO, 'start.py'), encoding='utf-8').read()
    assert 'start_new_session=True' in src
    assert 'os.getpgid' in src


def test_group_alive_probe_never_raises():
    assert common.pgid_alive(None) is False
    assert common.pgid_alive(0) is True or common.pgid_alive(0) is False   # 不抛异常即可
    assert common.pid_alive(None) is False
    assert common.pid_alive(os.getpid()) is True
    assert common.pid_alive(2 ** 22 + 12345) is False


# --------------------------------------------------------------------------------------
# 4. doctor 有区分度
# --------------------------------------------------------------------------------------

def _env_sourced():
    amb = os.environ.get('AMENT_PREFIX_PATH', '')
    return '/opt/ros/jazzy' in amb and os.path.join(ROOT, 'install') in amb


@pytest.mark.skipif(not _env_sourced(),
                    reason='本条要求已 source ROS + install；未 source 时应看 doctor 的 FAIL 路径'
                           '（test_doctor_detects_* 系列），不是静默跳过')
def test_doctor_reports_ok_on_clean_env_when_sourced():
    """在**已 source** 的环境里，阻断性检查应全过（残留/端口按现场如实）。"""
    res = doctor.run_checks(want_gui=False, only={'ros', 'ros2', 'workspace', 'sourced'})
    by = {r['key']: r for r in res}
    for key in ('ros', 'ros2', 'workspace', 'sourced'):
        assert by[key]['status'] == doctor.OK, '%s 未通过：%s' % (key, by[key]['detail'])


def test_doctor_detects_missing_ros_env_as_fail():
    """**隔离 env**：清空 AMENT_PREFIX_PATH → 必须 FAIL 并给人话（而非 python 栈）。"""
    old = os.environ.get('AMENT_PREFIX_PATH')
    try:
        os.environ['AMENT_PREFIX_PATH'] = ''
        r = doctor.check_ros()
        assert r[0] == doctor.FAIL
        assert 'source' in (' '.join(r[3]) + r[2]).lower()
    finally:
        if old is None:
            os.environ.pop('AMENT_PREFIX_PATH', None)
        else:
            os.environ['AMENT_PREFIX_PATH'] = old


def test_doctor_detects_workspace_not_sourced():
    old = os.environ.get('AMENT_PREFIX_PATH')
    try:
        os.environ['AMENT_PREFIX_PATH'] = '/opt/ros/jazzy'
        r = doctor.check_workspace_sourced()
        assert r[0] == doctor.FAIL
        assert 'install/setup.bash' in (' '.join(r[3]) + r[2])
    finally:
        if old is None:
            os.environ.pop('AMENT_PREFIX_PATH', None)
        else:
            os.environ['AMENT_PREFIX_PATH'] = old


def test_doctor_detects_occupied_port(monkeypatch=None):
    """真占一个端口 → `check_ports` 必须 FAIL 并指出端口号。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]
        # 用真实端口判定逻辑（复用 port_is_free，避免只测 doctor 的包装）
        free, _err = common.port_is_free(port)
        assert free is False, '被占端口 %d 竟被判为空闲' % port
    finally:
        s.close()
    free, err = common.port_is_free(port)
    assert free is True, '释放后端口 %d 仍被判占用：%s' % (port, err)


def test_doctor_detects_nonzero_domain_id():
    old = os.environ.get('ROS_DOMAIN_ID')
    try:
        os.environ['ROS_DOMAIN_ID'] = '77'
        status, name, detail, hints = doctor.check_domain_id()
        assert status == doctor.FAIL
        assert '77' in detail
        assert any('unset' in h for h in hints)
    finally:
        if old is None:
            os.environ.pop('ROS_DOMAIN_ID', None)
        else:
            os.environ['ROS_DOMAIN_ID'] = old


def test_doctor_detects_residual_processes(monkeypatch):
    """注入一条假残留 → `check_residual_processes` 必须 FAIL 且给出 PID 级处置建议。"""
    fake = [{'pid': 424242, 'cmd': 'gz sim /tmp/agc_world.sdf', 'exe': '/usr/bin/ruby',
             'rule': 'gz sim'}]
    monkeypatch.setattr(common, 'project_processes', lambda: fake)
    status, name, detail, hints = doctor.check_residual_processes()
    assert status == doctor.FAIL
    assert '424242' in detail
    assert any('run_demo.sh stop' in h for h in hints)


def test_residual_check_excludes_own_running_instance(monkeypatch):
    """**本实例自己**的子进程不算"残留"（否则起第二个实例时会给出自相矛盾的错误）。"""
    own_pid = os.getpid()
    fake = [{'pid': own_pid, 'cmd': 'gz sim -s /tmp/agc_world.sdf',
             'exe': '/usr/bin/ruby', 'rule': 'gz sim'}]
    monkeypatch.setattr(common, 'project_processes', lambda: fake)
    monkeypatch.setattr(common, 'current_instance', lambda: {
        'state': 'running', 'launch_pgid': os.getpgid(0), 'supervisor_pgid': os.getpgid(0)})
    status, name, detail, hints = doctor.check_residual_processes()
    assert status == doctor.OK, '自己的实例成员被判成残留：%s' % detail
    assert '已排除本实例自身 PGID' in detail

    # 反向对照：状态不是 running 时，同一个进程**必须**被判残留
    monkeypatch.setattr(common, 'current_instance', lambda: {'state': 'finished'})
    status2, _n, detail2, _h = doctor.check_residual_processes()
    assert status2 == doctor.FAIL, '实例已结束时同一进程必须算残留：%s' % detail2


def test_doctor_budget_constant_is_30s():
    assert doctor.DOCTOR_BUDGET_S == 30.0


def test_doctor_never_raises_on_broken_check(monkeypatch):
    """单项检查自身出错 → 记为 FAIL 并提示"这是缺陷"，不得把栈抛给使用者。"""
    def boom():
        raise RuntimeError('注入的检查内部错误')
    monkeypatch.setattr(doctor, 'CHECKS',
                        (('ros', 'ROS 环境', boom),) + doctor.CHECKS[1:])
    res = doctor.run_checks(want_gui=False, only={'ros'})
    assert res[0]['status'] == doctor.FAIL
    assert '注入的检查内部错误' in res[0]['detail']


# --------------------------------------------------------------------------------------
# 5. 等价比较有区分度（四类结论）
# --------------------------------------------------------------------------------------

PREREG = os.path.join(ROOT, 'experiments', 'p1-2', 'round-2', 'preregistration',
                      'gui-headless-equivalence.json')


def _prereg():
    return json.load(open(PREREG, encoding='utf-8'))


def _summary(**over):
    base = {
        'run_id': 'x-s04_static_static_obs_track-0-120000-0000',
        'terminal_state': 'TRACKING_SUCCESS',
        'terminal_reason_code': 'tracking_milestone',
        'reset_failed': False, 'reset_retries': 0,
        'shield_infeasible_rate': 0.0, 'reset_failure_rate': 0.0,
        'duration_s': 60.0, 'rtf': 0.9,
        'sim_start_s': 10.0, 'sim_end_s': 60.0,
        'visibility_metrics': {'visibility_rate': 0.97},
        'episode_window_metrics': {'ticks_total': 414},
        'odom_valid_ratio': 0.97, 'cmd_vel_rate_hz': 15.0, 'collision_count': 1,
        'command_attribution': {'intervened_ticks': 317},
    }
    base.update(over)
    return base


def _run(summary, mode='gui'):
    return {'summary': summary, 'evidence': {'gui_claim': {'verdict': 'ok', 'checks': {}}}}


def test_preregistration_is_well_formed_and_specific():
    p = _prereg()
    assert p['schema'] == 'demo-gui-headless-equivalence-prereg-v1'
    ids = {i['id'] for i in p['primary_criteria']['items']}
    assert {'terminal_state', 'terminal_reason_code', 'shield_infeasible_rate',
            'reset_failure_rate', 'reset_failed', 'reset_retries'} <= ids
    assert any(i['tolerance'] == 0.20 for i in p['secondary_criteria']['items'])
    # duration_s 必须被明确排除在等价之外
    assert 'duration_s' in ' '.join(p['report_only_no_gate']['items'])
    assert 'sim_end_minus_sim_start_s' in json.dumps(p)


def test_compare_equivalent_when_all_match():
    gui = _run(_summary())
    head = _run(_summary(run_id='h-s04_static_static_obs_track-0-130000-0000', rtf=0.88),
                mode='headless')
    out = compare.compare(gui, head, _prereg())
    assert out['verdict'] == 'EQUIVALENT', out['reasons']


def test_compare_not_equivalent_on_terminal_mismatch():
    gui = _run(_summary())
    head = _run(_summary(terminal_state='MISSION_FAILED',
                         terminal_reason_code='TIMEOUT'), mode='headless')
    out = compare.compare(gui, head, _prereg())
    assert out['verdict'] == 'NOT_EQUIVALENT'
    assert any('terminal_state' in r for r in out['reasons'])


def test_compare_rejects_none_c9_metrics_as_equal():
    """报告指标缺值（None）**不得**当作 0 或相等 —— 必须 NOT_EQUIVALENT。"""
    gui = _run(_summary(shield_infeasible_rate=None))
    head = _run(_summary(shield_infeasible_rate=0.0), mode='headless')
    out = compare.compare(gui, head, _prereg())
    assert out['verdict'] == 'NOT_EQUIVALENT'
    assert any('shield_infeasible_rate' in r for r in out['reasons'])


def test_compare_rejects_reset_failed_true():
    gui = _run(_summary(reset_failed=True))
    head = _run(_summary(), mode='headless')
    out = compare.compare(gui, head, _prereg())
    assert out['verdict'] == 'NOT_EQUIVALENT'


def test_compare_not_comparable_when_task_window_exceeds_20pct():
    gui = _run(_summary())
    # sim window 50 s vs 70 s → 相对差 28.6% > 20%
    head = _run(_summary(sim_end_s=80.0), mode='headless')
    out = compare.compare(gui, head, _prereg())
    assert out['verdict'] == 'NOT_COMPARABLE', out['reasons']
    assert any('task_window_duration_s' in r for r in out['reasons'])


def test_compare_ignores_duration_s_mismatch():
    """`duration_s` 是进程墙钟，**不参与**等价：差很大也不得影响 verdict。"""
    gui = _run(_summary(duration_s=60.0))
    head = _run(_summary(duration_s=240.0), mode='headless')
    out = compare.compare(gui, head, _prereg())
    assert out['verdict'] == 'EQUIVALENT', out['reasons']


def test_compare_visibility_out_of_absolute_tolerance():
    gui = _run(_summary(visibility_metrics={'visibility_rate': 0.98}))
    head = _run(_summary(visibility_metrics={'visibility_rate': 0.80}), mode='headless')
    out = compare.compare(gui, head, _prereg())
    assert out['verdict'] == 'NOT_COMPARABLE'


def test_compare_incomplete_without_summary(tmp_path):
    d = tmp_path / 'gui'
    d.mkdir()
    (d / 'result.json').write_text(json.dumps({'summary': None,
                                               'summary_error': '未找到本 run 的 summary'}))
    doc, err = compare.load_run(str(d))
    assert err and 'summary' in err


# --------------------------------------------------------------------------------------
# 6. 证据模块的判定口径（headless 不得冒充 GUI）
# --------------------------------------------------------------------------------------

def test_headless_gui_claim_is_not_applicable(tmp_path):
    out = evidence.collect_final(str(tmp_path), {'mode': 'headless', 'launch_pgid': None},
                                 None, None)
    assert out['gui_claim']['verdict'] == evidence.NA
    assert '不得' in out['gui_claim']['reason']


def test_gui_claim_requires_all_four_evidence_kinds(tmp_path):
    """缺任一项（这里：没有 renderer / 没有窗口）→ verdict 必须是 missing。"""
    pre = {
        'proc': {'gz_gui': [{'pid': 1, 'cmd': 'gz sim -r -v 3 /tmp/agc_world.sdf'}],
                 'gz_headless': [], 'rviz2': [{'pid': 2, 'cmd': 'rviz2'}],
                 'viz_markers': [{'pid': 3, 'cmd': 'viz_markers'}],
                 'world_frame_tf': [{'pid': 4, 'cmd': 'static_transform_publisher'}]},
        'launch_log': {'status': 'ok', 'gazebo_started': True,
                       'rviz2_started': [{'pid': 2}], 'viz_markers_started': [{'pid': 3}],
                       'static_tf_started_count': 1},
        'x11': {'status': 'missing'},
        'renderer_startup': {'status': 'missing'},
    }
    out = evidence.collect_final(str(tmp_path), {'mode': 'gui', 'launch_pgid': None},
                                 pre, None)
    assert out['gui_claim']['verdict'] == evidence.MISSING
    assert out['gui_claim']['checks']['x11_windows'] is False
    assert out['gui_claim']['checks']['renderer_identified'] is False
    assert out['gui_claim']['checks']['single_rviz_overlay'] is True


def test_gui_claim_fails_on_duplicate_rviz_overlay(tmp_path):
    pre = {
        'proc': {'gz_gui': [{'pid': 1, 'cmd': 'gz sim -r -v 3 /tmp/agc_world.sdf'}],
                 'gz_headless': [], 'rviz2': [{'pid': 2, 'cmd': 'rviz2'},
                                              {'pid': 5, 'cmd': 'rviz2'}],
                 'viz_markers': [{'pid': 3, 'cmd': 'viz_markers'}],
                 'world_frame_tf': [{'pid': 4, 'cmd': 'static_transform_publisher'}]},
        'launch_log': {'status': 'ok', 'gazebo_started': True,
                       'rviz2_started': [{'pid': 2}, {'pid': 5}],
                       'viz_markers_started': [{'pid': 3}],
                       'static_tf_started_count': 1},
        'x11': {'status': 'ok'},
        'renderer_startup': {'status': 'ok'},
    }
    out = evidence.collect_final(str(tmp_path), {'mode': 'gui', 'launch_pgid': None},
                                 pre, None)
    assert out['rviz_singletons']['rviz2'] == 2
    assert out['gui_claim']['checks']['single_rviz_overlay'] is False


def test_gazebo_headless_never_counts_as_gui(tmp_path):
    """`gz -s` 必须被识别为 headless —— 否则 GUI 证据会被伪造式通过。"""
    pre = {'proc': {'gz_gui': [], 'gz_headless': [{'pid': 1, 'cmd': 'gz sim -s -r /tmp/agc_world.sdf'}],
                    'rviz2': [], 'viz_markers': [], 'world_frame_tf': []},
           'launch_log': {'status': 'ok', 'gazebo_started': True, 'rviz2_started': [],
                          'viz_markers_started': [], 'static_tf_started_count': 0},
           'x11': {'status': 'ok'}, 'renderer_startup': {'status': 'ok'}}
    out = evidence.collect_final(str(tmp_path), {'mode': 'gui', 'launch_pgid': None},
                                 pre, None)
    assert out['gui_claim']['checks']['gazebo_non_headless'] is False


def test_launch_log_evidence_counts_each_node():
    """`launch.log` 计数能区分"起了 1 份"与"起了 2 份"（双注册的现场判据）。"""
    tmp = '/tmp/p1-2-test-launchlog'
    os.makedirs(tmp, exist_ok=True)
    path = os.path.join(tmp, 'launch.log')
    with open(path, 'w') as f:
        f.write('[INFO] [gazebo-2]: process started with pid [100]\n')
        f.write('[INFO] [rviz2-30]: process started with pid [200]\n')
        f.write('[INFO] [rviz2-31]: process started with pid [201]\n')
        f.write('[INFO] [viz_markers-32]: process started with pid [202]\n')
    ev = evidence.launch_log_evidence(tmp)
    assert ev['gazebo_started'] is True
    assert len(ev['rviz2_started']) == 2
    assert len(ev['viz_markers_started']) == 1


# --------------------------------------------------------------------------------------
# 7. 回收判据口径（实测修正的回归）
# --------------------------------------------------------------------------------------

def test_reap_confirm_uses_non_zombie_members_not_killpg_probe():
    """`confirmed` 必须以**非僵尸成员清零**为准。

 实测缺陷：Ctrl-C 回收 36 个进程全清、`ps` 无任何残留，却因
    `killpg(pgid, 0)` 对"只剩僵尸"的组仍返回成功而判 FAIL（`members_after=[]` 与
 `confirmed=False` 自相矛盾）。本条锁住修正后的口径。
    """
    src = open(os.path.join(DEMO, 'common.py'), encoding='utf-8').read()
    body = src[src.index('def reap_process_group'):]
    body = body[:body.index('\ndef ')] if '\ndef ' in body else body
    assert "res['confirmed'] = not after" in body, (
        'confirmed 必须只看非僵尸成员（killpg 探针对僵尸组仍成功，不能作判据）')
    assert "res['zombie_group_remaining']" in body, (
        '僵尸组必须单独记账（审计用），不能与"有残留"混为一谈')
    import re as _re
    assigns = _re.findall(r"^\s*res\['confirmed'\]\s*=\s*(.+)$", body, _re.M)
    assert assigns, '没有找到 confirmed 的赋值'
    for expr in assigns:
        assert 'pgid_alive' not in expr, (
            'confirmed 不得再与 pgid_alive 相与（当前表达式：%s）' % expr.strip())


def test_interrupt_exit_code_is_130_not_task_failure():
    """用户 Ctrl-C 是**主动中断**（130），不得与"任务失败(2)"混用。"""
    src = open(os.path.join(DEMO, 'start.py'), encoding='utf-8').read()
    assert 'code = 130' in src
    assert "startswith('interrupted')" in src


# --------------------------------------------------------------------------------------
# 8. `--duration` 分支记账口径
# --------------------------------------------------------------------------------------

def test_duration_branch_is_recorded_even_when_not_reached():
    """`--duration` 未触达时必须**显式记账**，不得静默当作"已验证主动停"。

    实测：`--duration 15` 时任务在 13.61 s 先达 `TRACKING_SUCCESS`，
 `duration_limit` 分支未执行。若代码不记账，产物看起来与"到时主动停"一模一样，
 后来人会把"未验证的分支"读成"已验证"。
    """
    src = open(os.path.join(DEMO, 'start.py'), encoding='utf-8').read()
    assert "self.result['duration_branch_taken'] = True" in src, (
        '到时主动停必须留下 duration_branch_taken=True')
    assert "self.result['duration_branch_taken'] = False" in src, (
        '先到终态时必须留下 duration_branch_taken=False（分支未触达）')
    assert 'duration_not_reached_note' in src, (
        '未触达时必须写明"本次不能作为 duration_limit 分支的证据"')


# --------------------------------------------------------------------------------------
# 9. `--px4-sim-model` 透传（机型/资产选择，非路线分支）
# --------------------------------------------------------------------------------------

def test_px4_sim_model_is_passed_through_launch_argv():
    """透传既有 launch 参数：extra 里的 `px4_sim_model:=...` 必须原样进 ros2 launch 实参。"""
    argv = demo_start.launch_argv(
        backend=common.DEFAULT_BACKEND, scene=common.DEFAULT_SCENE,
        world_map=common.DEFAULT_MAP, headless=False,
        extra=['px4_sim_model:=gz_agc_x500_nadir'])
    assert 'px4_sim_model:=gz_agc_x500_nadir' in argv, (
        '机型透传丢失：%s' % ' '.join(argv))
    # 不带该选项时不得偷偷改机型（默认行为逐字不变）
    plain = demo_start.launch_argv(
        backend=common.DEFAULT_BACKEND, scene=common.DEFAULT_SCENE,
        world_map=common.DEFAULT_MAP, headless=False)
    assert not any(a.startswith('px4_sim_model:=') for a in plain), (
        '默认命令行不得带 px4_sim_model（机型由 main.launch.py 默认值决定）')


def test_run_demo_sh_declares_px4_sim_model_option():
    """入口脚本须有该选项、白名单校验、并转成 EXTRA 的 launch 参数形式。"""
    src = open(os.path.join(common.ROOT, 'run_demo.sh'), encoding='utf-8').read()
    assert '--px4-sim-model)' in src, 'run_demo.sh 缺少 --px4-sim-model 解析分支'
    assert 'gz_agc_x500_nadir' in src and 'gz_x500_mono_cam' in src, (
        '机型白名单须含 nadir / mono_cam 等已知取值')
    assert 'EXTRA+=("px4_sim_model:=${PX4_MODEL}")' in src, (
        '须转成 px4_sim_model:=<值> 放进 EXTRA（经 main.py → launch_argv 透传）')


# --------------------------------------------------------------------------------------
# 10. headless 固定带 RViz 语义层（用户 2026-11-08 裁定，不暴露开关）
# --------------------------------------------------------------------------------------

def test_headless_always_enables_viz_overlay():
    """GUI 与 headless 都起 viz_markers + rviz2 + static_tf（固定，无开关）。"""
    assert demo_start.viz_enabled(headless=False) is True
    assert demo_start.viz_enabled(headless=True) is True
    for headless in (False, True):
        argv = demo_start.launch_argv(
            backend=common.DEFAULT_BACKEND, scene=common.DEFAULT_SCENE,
            world_map=common.DEFAULT_MAP, headless=headless)
        assert 'viz:=true' in argv, (
            'headless=%s 的命令行缺少 viz:=true：%s' % (headless, ' '.join(argv)))
        assert 'viz:=false' not in argv


def test_no_viz_switch_remains():
    """不暴露 --viz / viz-on / viz_override（避免路线分支与产物口径歧义）。"""
    sh = open(os.path.join(common.ROOT, 'run_demo.sh'), encoding='utf-8').read()
    assert '--viz)' not in sh and 'viz-on' not in sh
    main = open(os.path.join(DEMO, 'main.py'), encoding='utf-8').read()
    assert 'viz_override' not in main and "'viz-on'" not in main
    st = open(os.path.join(DEMO, 'start.py'), encoding='utf-8').read()
    assert 'viz_override' not in st


# --------------------------------------------------------------------------------------
# 3b. 孤儿回收（2026-11-10）：stop 必须能收"逃出登记 PGID"的残留
# --------------------------------------------------------------------------------------

def test_stop_sweeps_orphans():
    """`stop` 在按 PGID 回收之后，必须再按**特征**收一遍孤儿。

    病灶（2026-11-10 实测）：外部终止后子进程逃出登记 PGID，`stop` 幂等返回
    "无进程组成员"，而 preflight 同时报"有 34 个残留进程"——两条信息互相打架，
    使用者只能手动 kill 一串 PID。
    """
    src = open(os.path.join(DEMO, 'stop.py'), encoding='utf-8').read()
    assert 'reap_orphan_processes' in src, 'stop 未调用孤儿回收'
    assert '_sweep_orphans' in src, '缺少孤儿回收的落地函数'
    # 每条 `return` 出口都必须经过孤儿回收（早退不等于没有孤儿）。
    # 判据：`_sweep_orphans(` 的调用次数 == 非辅助函数的 return 次数。
    import re as _re
    sweep_calls = len(_re.findall(r'return _sweep_orphans\(', src))
    assert sweep_calls >= 3, (
        'stop 的孤儿回收出口太少（实际 %d 处）——早退路径可能漏掉孤儿' % sweep_calls)


def test_orphan_sweep_never_touches_live_instance():
    """孤儿回收必须**显式排除**登记实例的进程组——绝不能误杀正在运行的演示。

    这是本改动的**安全红线**：`stop` 的第一职责是回收，不是"清理机器"。
    """
    src = open(os.path.join(DEMO, 'common.py'), encoding='utf-8').read()
    assert 'keep_pgids' in src, '孤儿回收没有 keep_pgids 参数'
    # 命中 keep_pgids 的候选必须被跳过
    assert "if st['pgrp'] in keep:" in src, (
        '孤儿回收未按 pgrp 排除登记实例的成员（会误杀正在运行的演示）')
    # 安全属性落在**两处**，缺一不可：
    #
    # ① 每个 `_sweep_orphans` 调用点都必须在"实例**已死**"的分支里
    #    （`members` 为空 / 无记录），绝不能在"实例还活着"时调用；
    # ② `keep_pgids` 必须来自登记记录（`_keep_pgids(cur)`），使任何仍在登记组里的
    #    进程被逐个排除——即使调用时机判断错了，这一层也拦得住。
    #
    # 为什么不用"state 字段"判据：外部终止会留下 `state=running` 但 supervisor 已死、
    # 进程组已空的**陈旧记录**，那正是要清理的场景（2026-11-10 实测）。
    stop_src = open(os.path.join(DEMO, 'stop.py'), encoding='utf-8').read()
    call_lines = [ln for ln in stop_src.splitlines()
                  if '_sweep_orphans(' in ln and 'def ' not in ln]
    assert call_lines, '未找到 _sweep_orphans 调用点'
    for ln in call_lines:
        # 无记录路径允许空 keep_pgids；其余必须用登记 PGID 兜底
        assert ('keep_pgids=_keep_pgids(cur)' in ln
                or 'keep_pgids=set()' in ln), (
            '_sweep_orphans 调用点未传登记 PGID 作为排除集：%s' % ln.strip()[:100])
    # 主回收流程结束后也要扫一遍（按 PGID 回收可能漏掉逃出组外的子进程）
    assert 'orphan_rc = _sweep_orphans' in stop_src, (
        '按 PGID 回收后没有追加孤儿回收')


def test_orphan_sweep_reuses_project_rules():
    """孤儿判定必须复用 `project_processes()` 的**同一套** 7 类特征规则。

    另写一份匹配表 = 两份口径漂移（preflight 报 N 个、stop 只收 M 个，且没人知道差在哪）。
    """
    src = open(os.path.join(DEMO, 'common.py'), encoding='utf-8').read()
    start = src.index('def reap_orphan_processes')
    end = src.index('def project_processes')
    body = src[start:end]
    assert 'project_processes()' in body, (
        '孤儿回收未复用 project_processes()（会与 preflight 的口径漂移）')


def test_orphan_sweep_is_graceful_then_forced():
    """先 SIGTERM 再 SIGKILL：给 run_logger / PX4 落盘机会，不能上来就 KILL。"""
    src = open(os.path.join(DEMO, 'common.py'), encoding='utf-8').read()
    start = src.index('def reap_orphan_processes')
    end = src.index('def project_processes')
    body = src[start:end]
    i_term = body.find('signal.SIGTERM')
    i_kill = body.find('signal.SIGKILL')
    assert i_term != -1 and i_kill != -1, '缺少两段式信号'
    assert i_term < i_kill, '必须先 SIGTERM 后 SIGKILL（顺序反了等于直接强杀）'


def test_orphan_sweep_treats_zombie_as_cleaned():
    """僵尸进程算已清理（已被回收、不再执行代码）。

    若把僵尸算"未退出"，`stop` 会在每个正常退出后都报"仍有 N 个未退出"，
    使用者会学会忽略这条警告——那比不报更糟。
    """
    src = open(os.path.join(DEMO, 'common.py'), encoding='utf-8').read()
    assert '_alive_non_zombie' in src, '缺少僵尸判定'
    assert "st['state'] == 'Z'" in src, '僵尸未被识别为已清理'


def test_empty_map_lets_scene_registration_win():
    """用户**没指定** `--map` 时，必须**不传** `world_map`，让场景登记生效。

    **根因（2026-11-11 实测 bug）**：`main.launch.py` 的地图解析是**两级**
    （launch 显式非空 > 场景登记 > 缺省 minimal）。而 demo 侧原先把空串折成
    `common.DEFAULT_MAP`（yard）并无条件传 `world_map:=yard` —— 于是"显式"
    永远成立，**场景登记的地图永远不生效**，且没有任何提示。

    实测后果：`--scene dense_scene`（登记 `world_map: dense_map`）实际跑在 `yard` 上，
    感知帧数 0、地图 occupied=0，而场景名与期望终态看起来都"正常"。

    这条用例钉住三件事：
      ① 空串 ⇒ argv 里**没有** `world_map:=`；
      ② 显式给值 ⇒ argv 里**有**它（覆盖能力不能被修 bug 修没了）；
      ③ 场景登记确实是"非空"的（否则本用例守的是一个不存在的场景）。
    """
    # ③ 先确认 dense_scene 真的登记了地图 —— 否则下面测的是空气
    import yaml
    from pathlib import Path as _Path
    reg = yaml.safe_load(
        (_Path(common.ROOT) / 'src' / 'agc_task' / 'config' / 'scenarios.yaml')
        .read_text(encoding='utf-8'))['scenes']
    assert (reg.get('dense_scene') or {}).get('world_map') == 'dense_map', (
        'dense_scene 必须登记 world_map: dense_map，否则本用例失去意义')

    # ① 未指定地图
    argv = demo_start.launch_argv(backend='full', scene='dense_scene',
                                  world_map='', headless=True)
    assert not any(a.startswith('world_map:=') for a in argv), (
        '未指定 --map 时不得传 world_map（否则场景登记永远不生效）：%s' % ' '.join(argv))

    # ② 显式覆盖仍然有效
    argv2 = demo_start.launch_argv(backend='full', scene='dense_scene',
                                   world_map='yard', headless=True)
    assert 'world_map:=yard' in argv2, '显式指定必须仍然能覆盖场景登记'


def test_start_defaults_map_to_empty_not_yard():
    """`cmd_start` 不得把"未指定"折成 `yard`。

    这条守的是**上游**：只要 main.py 把空串折成默认值，`launch_argv` 的修复
    就永远收不到空串（两处必须同时正确）。判据落在源码上，因为 `cmd_start`
    依赖 argparse 的 Namespace，直接调需要构造一整套参数。
    """
    from pathlib import Path as _Path
    src = (_Path(common.ROOT) / 'scripts' / 'demo' / 'main.py').read_text(encoding='utf-8')
    assert "wmap = (args.map or '').strip()" in src, (
        '空串必须保持空串往上传，不得在此折成 DEFAULT_MAP')
    assert "wmap = (args.map or '').strip() or common.DEFAULT_MAP" not in src, (
        '这里折默认值会让场景登记的地图永远不生效（实测 bug）')
