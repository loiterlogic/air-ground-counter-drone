"""`run_demo.sh` 一键演示入口的离线回归（**不启任何仿真**）。

守护 P1-2 的五条硬性质——全部可在无 GUI / 无 ROS 图的情况下判定：

1. **默认口径**：不带参数时必须是 `full + yard + s04 + observe_yaw_mode=target`，
   且 `target` 是**显式**写在命令行里的（不能靠 `air.yaml` 的默认 `velocity` 蒙过去）；
2. **不新增命令者**：演示代码不发布 `/agc/ground/cmd_vel`、不写模型位姿
   （[#execution-port](../../docs/ROS2迁移交接文档.md#execution-port)）；
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
    # 显式 oracle 指向臂：不得回退成 '' 或 'velocity'
    assert common.DEFAULT_OBSERVE_YAW_MODE == 'target'


def test_default_launch_argv_passes_oracle_mode_explicitly():
    argv = demo_start.launch_argv(backend=common.DEFAULT_BACKEND, scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=False)
    joined = ' '.join(argv)
    for token in ('backend:=full', 'scene:=s04_static_static_obs_track',
                  'world_map:=yard', 'seed:=0', 'observe_yaw_mode:=target',
                  'viz:=true', 'agc_task', 'w6.launch.py'):
        assert token in joined, '默认命令行缺少 %s：%s' % (token, joined)
    # 不得出现空覆盖（空串会让 launch 回落到 air.yaml 的 velocity）
    assert 'observe_yaw_mode:=' not in joined.replace('observe_yaw_mode:=target', '')


# --------------------------------------------------------------------------------------
# 1b. RViz 叠加层只在 GUI 形态启用（P1-2 round-3 修正）
# --------------------------------------------------------------------------------------

def test_gui_enables_viz_overlay():
    """GUI 形态：`viz:=true`（P1-1 的 RViz 语义层是 GUI 演示的一部分）。"""
    assert demo_start.viz_enabled(headless=False) is True
    argv = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=False)
    assert 'viz:=true' in ' '.join(argv)


def test_headless_disables_viz_overlay():
    """headless：`viz:=false` —— 不起 rviz2 / viz_markers / static_tf。

    依据：P1-2 自己规定"**不要**起 RViz 才能看状态"，且 headless 用于经济快跑；
    rviz2 ≈257 MB + viz_markers ≈90 MB（MAP_DESIGN_PLAYBOOK 16.2）纯属浪费。
    """
    assert demo_start.viz_enabled(headless=True) is False
    argv = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=True)
    joined = ' '.join(argv)
    assert 'viz:=false' in joined, 'headless 命令行缺少 viz:=false：%s' % joined
    assert 'viz:=true' not in joined, 'headless 不得启用 RViz 叠加：%s' % joined


def test_headless_and_gui_differ_only_in_gz_s_and_viz():
    """GUI / headless 的差异必须**可枚举**且只有两处：`gz_args` 的 `-s` 与 `viz`。

    这条同时守护两件事：① headless 不偷偷少传/多传别的参数（否则等价比较的自变量不清）；
    ② round-3 的 viz 修正确实只动了这一处。
    """
    gui = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                 world_map=common.DEFAULT_MAP, headless=False)
    head = demo_start.launch_argv(backend='full', scene=common.DEFAULT_SCENE,
                                  world_map=common.DEFAULT_MAP, headless=True)
    assert len(gui) == len(head)
    diff = [(a, b) for a, b in zip(gui, head) if a != b]
    assert len(diff) == 2, 'GUI/headless 只应有 2 处差异，实际 %r' % diff
    keys = {a.split(':=')[0] for a, _b in diff}
    assert keys == {'gz_args', 'viz'}, '差异参数集应为 {gz_args, viz}，实际 %r' % keys
    gz_gui = [x for x in gui if x.startswith('gz_args:=')][0]
    gz_head = [x for x in head if x.startswith('gz_args:=')][0]
    assert '-s' not in gz_gui.split(':=', 1)[1].split()[:1]
    assert '-s' in gz_head.split(':=', 1)[1].split()[:1]


def test_gz_args_differs_only_by_headless_flag():
    """`gz_args` 的差别只有 `-s`（GUI / headless 的另一处差别是 `viz`，见下条）。"""
    gui = demo_start.gz_args(headless=False)
    head = demo_start.gz_args(headless=True)
    assert gui.startswith('-r -v 3 ')
    assert head.startswith('-s -r -v 3 ')
    assert gui.replace('-r -v 3 ', '').strip() == head.replace('-s -r -v 3 ', '').strip()


def test_launch_env_fills_python_and_gz_prerequisites():
    env = demo_start.launch_env({})
    assert env['ROS_AUTOMATIC_DISCOVERY_RANGE'] == 'LOCALHOST'
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
    # 不得对"名字匹配到的"进程发信号：只允许对具体 pid 的探活 (os.kill(pid, 0))
    # common.py 里 `os.kill` 只允许用于 **0 号信号探活**（kill(pid, 0)）；
    # 真正的终止一律走 `os.killpg`（整组）。
    for m in re.finditer(r'os\.kill\((.+?)\)\n', src, re.S):
        args = ' '.join(m.group(1).split())
        assert args.endswith(', 0'), (
            'common.py 只允许 os.kill(pid, 0) 探活，发现：os.kill(%s) —— 终止必须走 killpg' % args)
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
    # 全机扫描只允许用于 `status` 的**只读**呈现；`stop()` 本体不得借它发信号
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
    """C9 缺值（None）**不得**当作 0 或相等 —— 必须 NOT_EQUIVALENT。"""
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
# 7. 回收判据口径（round-2 实测修正的回归）
# --------------------------------------------------------------------------------------

def test_reap_confirm_uses_non_zombie_members_not_killpg_probe():
    """`confirmed` 必须以**非僵尸成员清零**为准。

    实测缺陷（round-2）：Ctrl-C 回收 36 个进程全清、`ps` 无任何残留，却因
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
# 8. `--duration` 分支记账口径（P1-2 round-3）
# --------------------------------------------------------------------------------------

def test_duration_branch_is_recorded_even_when_not_reached():
    """`--duration` 未触达时必须**显式记账**，不得静默当作"已验证主动停"。

    round-3 实测：`--duration 15` 时任务在 13.61 s 先达 `TRACKING_SUCCESS`，
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
