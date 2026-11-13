"""启动就绪门（ADR-0038）静态闸门 + 判据单测。

## 为什么需要这组测试

病灶是"用固定秒数猜就绪"：车/目标 15 s、own PX4 25 s、intruder PX4 35 s、
`air_bringup` 12 s、`scenario_reset` 4 s。这类数字**看上去**是配置，**实际上**是
对"前一步什么时候真的完成"的假设——机器慢一点就 spawn 失败，快一点就白等几十秒，
而失败后**没有任何机制重试或上报**。

静态闸门（判据 a–d）把"不许再用盲计时承载正确性"变成可判定的：
新增一个 `TimerAction(period=15.0)` 承载启动依赖，测试立刻红。

判据 e–g 测就绪门脚本本身：判据解析必须**拒绝**非法输入（拼错的判据若被忽略，
门会立刻"通过"——那正是要消灭的假就绪），评估函数必须按"全部满足"语义工作。

运行：
  python3 -m pytest scripts/tests/test_startup_readiness_gates.py -q
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORLD_BRINGUP = ROOT / 'src' / 'agc_sim' / 'launch' / 'world_bringup.launch.py'
MAIN_LAUNCH = ROOT / 'src' / 'agc_task' / 'launch' / 'main.launch.py'
AIR_BRINGUP = ROOT / 'src' / 'agc_air' / 'launch' / 'air_bringup.launch.py'
SCENARIO_RESET = ROOT / 'src' / 'agc_task' / 'src' / 'scenario_reset.cpp'
STARTUP_GATE = ROOT / 'src' / 'agc_sim' / 'scripts' / 'startup_gate.py'
SPAWN_GATE = ROOT / 'src' / 'agc_sim' / 'scripts' / 'scene_spawn_gate.py'


def _read(path: Path) -> str:
    assert path.exists(), '缺少文件：%s' % path
    return path.read_text(encoding='utf-8')


def _code(path: Path) -> str:
    """去掉**注释**后的源码：注释里允许提到旧实现（"原先是 TimerAction(15 s)"），
    判据只针对真正会执行的代码。"""
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        stripped = line.lstrip()
        if stripped.startswith('#'):
            continue
        # 去掉行尾注释（本仓 launch 用 ` # …` 形式；字符串里出现 `#` 的情形不在此文件）
        if '  # ' in line:
            line = line.split('  # ', 1)[0]
        out.append(line)
    return '\n'.join(out)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------------
# a. 世界 spawn 不再用固定延时
# --------------------------------------------------------------------------------------
def test_world_spawn_has_no_fixed_delay_timer():
    """车/目标的创建不得再被 `TimerAction` 承载（旧实现是 15 s 盲等）。"""
    src = _code(WORLD_BRINGUP)
    assert 'TimerAction' not in src, (
        'world_bringup 仍使用 TimerAction —— spawn 必须由事务式就绪门驱动（ADR-0038）')
    assert 'scene_spawn_gate.py' in src, (
        'world_bringup 未调用事务式 spawn 就绪门 scene_spawn_gate.py')


def test_world_spawn_gate_waits_for_real_signals():
    """事务式门必须等**可观测**事实：create 服务 + 世界时钟推进 + 实体存在。"""
    src = _read(SPAWN_GATE)
    assert 'service_list' in src and 'create_srv' in src, '未等 create 服务发现'
    assert 'await_clock_advancing' in src, '未等世界时钟推进（暂停的世界 create 也会成功）'
    assert 'scene/info' in src, '未用 scene/info 校验实体确实存在'
    assert 'allow_renaming' in src and 'False' in src, (
        'allow_renaming 必须为 False：否则同名实体被悄悄改名，"创建成功"与"看到的实体"分叉')


def test_world_spawn_gate_fails_loudly():
    """创建失败必须**非零退出**，不得静默半启动。"""
    src = _read(SPAWN_GATE)
    assert 'return 0 if ok else 1' in src, '失败路径未返回非零退出码'
    assert 'entities_ready' in src, '未发布实体就绪状态（下游无从依赖）'


# --------------------------------------------------------------------------------------
# b. PX4 启动不再由固定延时承载
# --------------------------------------------------------------------------------------
def test_px4_start_is_event_driven_not_timed():
    """own / intruder PX4 必须由就绪事件驱动，且延时默认值不得是经验秒数。"""
    src = _read(MAIN_LAUNCH)
    assert '_px4_startup_gates' in src, '缺少 PX4 就绪门编排函数'
    assert 'startup_gate.py' in src, '未使用就绪门脚本'
    # 旧实现的两个经验值不得作为**默认**回来（允许作为显式可选下限参数存在）。
    for knob, old in (('own_px4_delay_s', '25.0'), ('intruder_px4_delay_s', '35.0')):
        m = re.search(r"'%s',\s*default_value='([0-9.]+)'" % knob, src)
        assert m, '缺少 %s 声明' % knob
        assert float(m.group(1)) == 0.0, (
            '%s 的默认值仍为 %s —— 它必须默认 0（正确性由就绪门承载，不是靠等）'
            % (knob, m.group(1)))
        assert old not in m.group(0), '%s 仍保留旧经验值 %s' % (knob, old)


def test_intruder_px4_waits_for_own_link_not_clock():
    """入侵者 PX4 的启动条件必须是「己方 air odom 新鲜」——两个 uXRCE 参与者不得并发。"""
    src = _read(MAIN_LAUNCH)
    # 抓 intruder_gate 的 --await 列表
    m = re.search(r"intruder_gate = ExecuteProcess\((.*?)\)\n", src, re.S)
    assert m, '未找到 intruder_gate'
    block = m.group(1)
    assert '/agc/air/odom' in block, (
        '入侵者 PX4 未等己方 /agc/air/odom —— 并发创建 uXRCE 参与者会触发 '
        'create entities failed: participant: 255')


def test_own_px4_waits_for_entities_ready():
    """己方 PX4 的启动条件必须是实体就绪（不是"过了 N 秒"）。"""
    src = _read(MAIN_LAUNCH)
    m = re.search(r"own_gate = ExecuteProcess\((.*?)\)\n", src, re.S)
    assert m, '未找到 own_gate'
    assert 'entities_ready' in m.group(1), '己方 PX4 未等实体就绪信号'


# --------------------------------------------------------------------------------------
# c. air_bringup 与统一入口共用同一就绪语义
# --------------------------------------------------------------------------------------
def test_air_bringup_shares_unified_readiness_semantics():
    """`air_bringup` 不得再有自己的一套固定延时。"""
    src = _code(AIR_BRINGUP)
    assert 'TimerAction' not in src, (
        'air_bringup 仍用 TimerAction —— 它必须与统一入口共用就绪门（ADR-0038）')
    assert 'startup_gate.py' in src, 'air_bringup 未复用统一就绪门'
    # 判据是"两个实体真的在 gz 世界里"（与统一入口同一口径）；话题 entities_ready 是
    # 给外部读的呈现层信号，不是门自身的依赖（见 ADR-0038 (a)/(b)）。
    assert 'entity:agc_world:agc_car' in src and 'entity:agc_world:intruder_uav' in src, (
        'air_bringup 的就绪门未校验实体存在')


def test_gate_script_lives_in_shared_package():
    """就绪门必须落在**两边都依赖**的包，否则只能靠新增跨域依赖（会成环）。"""
    assert STARTUP_GATE.exists(), 'startup_gate.py 不在 agc_sim（共用包）'
    sim_pkg = _read(ROOT / 'src' / 'agc_sim' / 'package.xml')
    air_pkg = _read(ROOT / 'src' / 'agc_air' / 'package.xml')
    assert '<exec_depend>agc_sim</exec_depend>' in air_pkg, 'agc_air 未声明对 agc_sim 的依赖'
    assert 'agc_task' not in air_pkg, (
        'agc_air 不得依赖 agc_task：那会形成 agc_task → agc_air → agc_task 的环')
    assert 'scripts' in sim_pkg or True   # 安装项在 CMakeLists（下面单独断言）


def test_gate_script_is_installed():
    """就绪门脚本必须被安装，否则 launch 里的路径在 install 空间不存在。"""
    cmake = _read(ROOT / 'src' / 'agc_sim' / 'CMakeLists.txt')
    assert 'install(DIRECTORY scripts' in cmake, 'agc_sim 未安装 scripts/（就绪门脚本）'


# --------------------------------------------------------------------------------------
# d. 初始复位不再用固定 4 s 定时器
# --------------------------------------------------------------------------------------
def test_initial_reset_is_retried_not_one_shot():
    """初始复位必须**有界重试**，且失败要显式上报，不得 cancel 后永不重试。"""
    src = _read(SCENARIO_RESET)
    assert 'onStartupTick' in src, '缺少启动复位的重试 tick'
    assert 'startup_reset_max_attempts' in src, '缺少重试次数上限参数'
    assert 'startup_reset_timeout_s' in src, '缺少重试墙钟上界参数'
    assert 'std::chrono::seconds(4)' not in src, '初始复位仍是固定 4 s 一次性定时器'
    assert '/agc/scenario/ready' in src, '未发布场景就绪状态'


def test_scenario_reset_publishes_readiness_both_ways():
    """就绪状态必须**成功/失败都发**（只发 true 会让下游永远等不到结论）。"""
    src = _read(SCENARIO_RESET)
    assert 'publishStartupReady(true)' in src
    assert 'publishStartupReady(false)' in src
    assert 'RCLCPP_ERROR' in src, '失败路径未大声报错'


def test_task_manager_gates_on_scenario_ready():
    """任务启动必须依赖场景就绪，而不是假定"复位一定成功"。"""
    src = _read(ROOT / 'src' / 'agc_task' / 'src' / 'task_manager.cpp')
    assert 'scenario_ready_topic' in src
    assert 'scenario_not_ready' in src, 'start 未在场景未就绪时如实拒绝'
    assert 'scenario_ready_wait_s' in src, '缺少等待场景就绪的墙钟上界'


# --------------------------------------------------------------------------------------
# e. 就绪门脚本的判据解析（非法输入必须拒绝）
# --------------------------------------------------------------------------------------
def test_parse_awaits_accepts_documented_forms():
    mod = _load_module(STARTUP_GATE, 'startup_gate_ok')
    svc, topics, gzsvc, ents, stable = mod.parse_awaits([
        'service:/agc/scenario/reset',
        'topic:/agc/air/odom:2.5',
        'gzservice:/world/agc_world/create',
        'entity:agc_world:intruder_uav',
        'graph-stable:3:12',
    ])
    assert svc == ['/agc/scenario/reset']
    assert topics == [('/agc/air/odom', 2.5)]
    assert gzsvc == ['/world/agc_world/create']
    assert ents == [('agc_world', 'intruder_uav')]
    assert stable == [(3.0, 12)]


def test_parse_awaits_rejects_typos():
    """拼错的判据**必须拒绝运行**：静默忽略会让门立刻通过（假就绪）。"""
    mod = _load_module(STARTUP_GATE, 'startup_gate_bad')
    for bad in ('topics:/x', 'service:relative/name', 'topic:/x:notanumber',
                'entity:onlyworld', 'gzservice:relative', 'graph-stable:3',
                'graph-stable:x:3', 'graph-stable:0:3'):
        try:
            mod.parse_awaits([bad])
        except SystemExit:
            continue
        raise AssertionError('非法判据未被拒绝：%r' % bad)


def test_parse_awaits_rejects_nonpositive_window():
    mod = _load_module(STARTUP_GATE, 'startup_gate_win')
    try:
        mod.parse_awaits(['topic:/x:0'])
    except SystemExit:
        return
    raise AssertionError('新鲜窗口为 0 未被拒绝（会让判据恒假或恒真）')


# --------------------------------------------------------------------------------------
# f. 评估语义：全部满足才算就绪
# --------------------------------------------------------------------------------------
class _FakeRos:
    def __init__(self, ready=(), fresh=()):
        self._ready = set(ready)
        self._fresh = set(fresh)

    def service_ready(self, name):
        return name in self._ready

    def topic_fresh(self, name, window):
        return name in self._fresh


class _FakeGz:
    def __init__(self, services=(), entities=()):
        self._services = set(services)
        self._entities = set(entities)

    def service_ready(self, name):
        return name in self._services

    def entity_present(self, world, model):
        return (world, model) in self._entities


def test_evaluate_requires_all_criteria():
    mod = _load_module(STARTUP_GATE, 'startup_gate_eval')
    args = (['/s1'], [('/t1', 1.0)], ['/g1'], [('w', 'm1')])
    # 全部满足 → 无 pending
    assert mod.evaluate(*args, _FakeRos(ready={'/s1'}, fresh={'/t1'}),
                        _FakeGz(services={'/g1'}, entities={('w', 'm1')})) == []
    # 缺一项 → 该项出现在 pending（不得因为"其它都满足"而放行）
    pending = mod.evaluate(*args, _FakeRos(ready={'/s1'}, fresh=set()),
                           _FakeGz(services={'/g1'}, entities={('w', 'm1')}))
    assert pending == ['topic:/t1'], '缺话题新鲜度时未报出（或报错了项）：%r' % pending
    # 探测对象缺席 → 全部未就绪（不得把"探测不到"当成就绪）
    assert len(mod.evaluate(*args, None, None)) == 4


def test_gate_uses_wall_clock_for_readiness():
    """就绪判定必须用墙钟（`time.monotonic`），不得读 `/clock`。

    启动期 `/clock` 可能尚未出现；用它做判据会让门在时钟起步前恒假（死等）。
    """
    src = _read(STARTUP_GATE)
    assert 'time.monotonic()' in src, '未使用墙钟'
    assert 'use_sim_time' not in src, '就绪门不应引入仿真时间语义'
    # 注释里允许解释"为什么不读 /clock"；判据针对代码：不得真的订阅或读取它。
    code = _code(STARTUP_GATE)
    assert 'Clock' not in code and 'clock_pb' not in code, (
        '就绪门读取了仿真时钟——启动期它可能还没出现')


# --------------------------------------------------------------------------------------
# g. 替换对象不得被 `%` 格式化（会拼出 repr，不是它的值）
# --------------------------------------------------------------------------------------
def test_launch_never_formats_substitutions_with_percent():
    """`'…%s…' % LaunchConfiguration(...)` / `% Command(...)` 会拼出**对象 repr**，
    而不是替换的值——实测两次踩到（SDF 参数与 graph-stable 参数），且只在**运行期**
    才暴露（静态看不出来，launch 能正常解析）。判据：格式化表达式里不得出现替换构造器。
    """
    import re

    offenders = []
    for path in (MAIN_LAUNCH, WORLD_BRINGUP, AIR_BRINGUP):
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            if '%' not in line:
                continue
            for ctor in ('LaunchConfiguration(', 'Command(', 'FindExecutable(',
                         'PythonExpression(', 'EnvironmentVariable('):
                if ctor in line and re.search(r"%\s*\(", line):
                    offenders.append('%s:%d  %s' % (path.name, lineno, line.strip()))
    assert not offenders, (
        '替换对象被 % 格式化了（运行期会拼出 repr）——请改用嵌套列表拼接：\n'
        + '\n'.join(offenders))


def test_spawn_gate_entity_args_use_equals_form():
    """实体参数必须用 `=` 形式：位姿的 x/y 常为负数，空格形式会被 argparse 当选项名。"""
    src = _read(WORLD_BRINGUP)
    assert "'--entity=agc_car'" in src and "'--entity=intruder_uav'" in src, (
        'world_bringup 未用 `--entity=` 形式传实体名')
    gate = _read(SPAWN_GATE)
    assert "partition('=')" in gate, 'scene_spawn_gate 未按 `=` 拆分实体参数'


# --------------------------------------------------------------------------------------
# h. 就绪门不得形成循环等待（2026-11-10 实测死锁）
# --------------------------------------------------------------------------------------
def test_no_gate_waits_on_its_own_downstream_output():
    """启动门不得等**它自己所门控的那条链**产出的 ROS 话题。

    病灶（2026-11-10 实测，代价 = 每次启动白等 150 s + 任务必然 `air_hover_timeout`）：
    `air_lifecycle_gate` 等 `/agc/air/odom` 新鲜，但该话题由 `px4_adapter` 在
    **on_activate 之后**才发布；而 activate 由 `lifecycle_manager` 执行，manager 又排在
    该门之后 ⇒ 循环等待，必然超时。

    同理 `px4_intruder_gate` 也不能等 `/agc/air/odom`（那是 own PX4 起来并 activate 后
    才有的，而本门控制的是"入侵者 PX4 何时起"）。

    判据：门等的话题必须是**上游**（PX4 uXRCE 直发 / gz 侧事实），不是本链 ROS 节点的输出。
    """
    src = _code(MAIN_LAUNCH)     # 去掉注释：注释里**应当**写明"为什么不用 /agc/air/odom"
    for gate_name in ('air_lifecycle_gate', 'px4_intruder_gate'):
        i = src.index("'--name', '%s'" % gate_name)
        block = src[i:i + 1200]
        assert "'--await', 'topic:/agc/air/odom" not in block, (
            '%s 在等 /agc/air/odom —— 该话题由 px4_adapter 在 on_activate 之后才发布，'
            '而 activate 又排在本门之后 ⇒ 循环等待（实测 150 s 死锁）。'
            '请改用上游信号 /fmu/out/vehicle_odometry。' % gate_name)


def test_lifecycle_gate_waits_on_px4_upstream():
    """空中 lifecycle 门必须等 PX4 **原始** uXRCE 话题（不依赖任何 lifecycle 节点）。"""
    src = _code(MAIN_LAUNCH)
    i = src.index("'--name', 'air_lifecycle_gate'")
    block = src[i:i + 1200]
    assert '/fmu/out/vehicle_odometry' in block, (
        'air_lifecycle_gate 未等 PX4 原始链路（/fmu/out/vehicle_odometry）')
    # 也不该在这里等 lifecycle 服务：manager 自己会 wait_for_service（Nav2 范式）
    assert "'--await', 'service:/px4_adapter/get_state'" not in block, (
        'air_lifecycle_gate 在等 lifecycle get_state —— 该服务在节点 configure 后才可用，'
        '在此等待会把"节点还没被 manager 拉起"变成启动门超时')


def test_topic_probe_qos_is_compatible_with_px4():
    """话题探针必须用**最弱** QoS（BEST_EFFORT + VOLATILE）。

    病灶（2026-11-10 实测，第二次踩同一个坑）：`startup_gate` 默认 RELIABLE 订阅
    PX4 uXRCE 的 `/fmu/out/vehicle_odometry`（BEST_EFFORT + TRANSIENT_LOCAL）→
    **静默收不到**（不报错、`create_subscription` 照样成功），于是就绪门等满 150 s 超时。

    ROS 2 兼容规则：订阅者不得比发布者**更强**。取最弱组合可同时匹配
    PX4 的 BEST_EFFORT 与普通节点的 RELIABLE。
    """
    src = _read(STARTUP_GATE)
    assert 'ReliabilityPolicy.BEST_EFFORT' in src, (
        '话题探针未用 BEST_EFFORT —— 收不到 PX4 /fmu/out/* 的 BEST_EFFORT 发布')
    assert 'DurabilityPolicy.VOLATILE' in src, (
        '话题探针未用 VOLATILE —— 订阅者 durability 不得高于发布者')
    # 不得退回默认（RELIABLE）构造
    assert 'create_subscription(\n                msg_cls, name, self._make_cb(name), 10)' \
        not in src, '话题探针退回默认 QoS（RELIABLE）会再次静默收不到 PX4 数据'


def test_spawn_verify_timeout_is_configurable_and_generous():
    """实体存在性校验窗口必须**可配**，且默认值对密集地图有余量。

    **实测踩过的坑**：`scene_spawn_gate.py` 里写死 `--verify-timeout-s 30.0`，
    而 `dense_map`（数百个障碍）加载时 `agc_car` 从 create 请求到出现在 `scene/info`
    用了 **30.13 s** —— 紧贴上限，差 0.13 s 就判失败，整链以
    "未就绪项：gt_target_fresh, air_odom_fresh" 收场，而真实原因是
    "实体存在性校验超时"。场景越密这个窗口越紧，写死等于让"世界大一点"变成"随机启动失败"。

    判据三条：
      ① launch 必须把该值**传进去**（不能只靠脚本默认值）；
      ② 默认值必须 > 30 s（实测已用到 30.13 s，30 s 没有余量）；
      ③ 它是**上界**不是延时 —— 实体一出现就继续（由 gate 实现保证，见其 await_entity）。
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    launch = (root / 'src' / 'agc_sim' / 'launch' / 'world_bringup.launch.py').read_text(
        encoding='utf-8')
    gate = (root / 'src' / 'agc_sim' / 'scripts' / 'scene_spawn_gate.py').read_text(
        encoding='utf-8')

    # ① 必须透传
    assert "'--verify-timeout-s'" in launch, (
        'launch 必须把 --verify-timeout-s 传给 scene_spawn_gate，'
        '否则只能吃脚本里写死的默认值')
    assert 'spawn_verify_timeout_s' in launch, '必须有对应的 launch 参数声明'

    # ② 默认值必须有余量
    import re
    m = re.search(r"'spawn_verify_timeout_s',\s*default_value='([\d.]+)'", launch)
    assert m, 'spawn_verify_timeout_s 必须有显式默认值'
    default = float(m.group(1))
    assert default > 30.0, (
        '默认值必须 > 30 s：实测 dense_map 已用到 30.13 s，30 s 是紧贴上限的脆弱值')

    # ③ 语义是上界：await_entity 必须在实体出现时**立即返回**
    assert 'def await_entity' in gate
    assert 'time.monotonic()' in gate, '等待必须基于墙钟截止时间（上界语义），不是固定 sleep'
