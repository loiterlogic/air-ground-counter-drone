"""`w6.launch.py` 演示叠加层（viz）注册次数的回归测试（T0：不启任何进程）。

**守护的缺陷**（ 实测， 修复）：
`_compose()` 末尾曾有 `actions.extend(_viz_actions(context, sim_share))`，
而 `generate_launch_description()` 末尾另有一个顶层
`OpaqueFunction(lambda c: _viz_actions(c, sim_share))` → `backend:=full` 时
`tf2_ros/static_transform_publisher` / `agc_task/viz_markers` / `rviz2` **各注册两份**；
`backend:=lightweight` 在 `_compose` 内提前 return，只命中顶层一处，故**只有 full 显形**。

**为什么必须锁 full × lightweight × on/off 四格**：只测 full+viz=true 时，
"把两处都删掉"同样能让断言通过（0 份 → 如果只断言"不是 2 份"）。四格同时要求
`viz=true → 恰好 1 份` 与 `viz=false → 0 份`，任何一侧漏注册 / 多注册都会失败。

**做法**：真实 `import` `w6.launch.py`，把 `DeclareLaunchArgument` 的**真实默认值**填进
`LaunchContext`，再执行 `LaunchDescription` 里的全部 `OpaqueFunction` —— 即真实走一遍
`_compose`（含场景加载 / 参数合并 / manifest 生成，全部只写 `/tmp` 必需文件，
**不 Popen 任何进程**），最后按 `Node(package, executable)` 计数。

运行：
 source /opt/ros/jazzy/setup.bash && source install/setup.bash
  python3 -m pytest scripts/tests/test_w6_viz_registration.py -q
"""

import importlib.util
import os
import sys

import pytest

# 项目根**自定位**（2026-10-31 ，裁定 A）：本文件在 `<ROOT>/scripts/tests/`，上溯三级即根。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
LAUNCH_DIR = os.path.join(ROOT, 'src', 'agc_task', 'launch')
W6 = os.path.join(LAUNCH_DIR, 'w6.launch.py')

# 被守护的三个节点（`package/executable` → 期望份数）
VIZ_NODES = (
    'tf2_ros/static_transform_publisher',
    'agc_task/viz_markers',
    'rviz2/rviz2',
)

# 本测试只查 launch 注册结构、不跨进程收发，但发现范围仍走配置文件
# （scripts/demo/dds_transport.py），避免第三套 DDS 口径。
sys.path.insert(0, os.path.join(ROOT, 'scripts', 'demo'))
import dds_transport  # noqa: E402

for _k, _v in dds_transport.env_for().items():
    if _v is not None:
        os.environ.setdefault(_k, _v)
os.environ.setdefault('GZ_SIM_SYSTEM_PLUGIN_PATH', os.path.join(ROOT, 'install', 'agc_sim', 'lib'))


def _load_w6():
    spec = importlib.util.spec_from_file_location('w6_launch_under_test', W6)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _flatten(default_value):
    """`DeclareLaunchArgument.default_value` 可能是 substitution 列表 → 求值成字符串。"""
    from launch import LaunchContext
    if isinstance(default_value, list):
        parts = []
        for x in default_value:
            parts.append(x.perform(LaunchContext()) if hasattr(x, 'perform') else str(x))
        return ''.join(parts)
    return default_value


def emitted_actions(backend, viz, overrides=None):
    """执行 launch 描述里的 OpaqueFunction，返回**真实发出的 action 列表**（不 Popen）。"""
    from launch import LaunchContext
    from launch.actions import DeclareLaunchArgument, OpaqueFunction

    mod = _load_w6()
    ld = mod.generate_launch_description()
    ctx = LaunchContext()
    for ent in ld.entities:
        if isinstance(ent, DeclareLaunchArgument):
            ctx.launch_configurations[ent.name] = _flatten(ent.default_value)
    ctx.launch_configurations.update({
        'backend': backend,
        'viz': viz,
        'scene': 's04_static_static_obs_track',
        'world_map': 'yard',
        'observe_yaw_mode': 'target',
        'seed': '0',
        'gz_args': '-r -v 3 ' + os.path.join(
            ROOT, 'install', 'agc_sim', 'share', 'agc_sim', 'worlds', 'agc_world.sdf'),
    })
    ctx.launch_configurations.update(overrides or {})
    actions = []
    for ent in ld.entities:
        if isinstance(ent, OpaqueFunction):
            actions.extend(ent.execute(ctx) or [])
    return actions, ctx


def _walk(actions):
    """展开 action 树：`RegisterEventHandler` 的事件处理动作里也可能挂 Node
 （本 launch 的 `intruder_driver` 就是这样注册的），不展开会把它误判为"缺失"。

 `launch` 把 on_event 的动作存在 `OnActionEventBase._OnActionEventBase__actions_on_event`
 里（见 `launch/event_handlers/on_action_event_base.py`），名字里带类名前缀，故此处按
 实际属性名取；取不到时退化为"不展开"，由测试的期望值暴露（不静默通过）。
    """
    for a in actions:
        yield a
        # RegisterEventHandler 的动作挂在 event_handler 里，再挂到
        # `_OnActionEventBase__actions_on_event`（两层都要展开）。
        handler = getattr(a, '_RegisterEventHandler__event_handler', None)
        if handler is not None:
            for sub in getattr(handler, '_OnActionEventBase__actions_on_event', None) or []:
                yield from _walk([sub])
        for sub in getattr(a, '_TimerAction__actions', None) or []:
            yield from _walk([sub])


def _count_nodes(actions, ctx):
    counts = {}
    for a in _walk(actions):
        pkg = getattr(a, '_Node__package', None)
        exe = getattr(a, '_Node__node_executable', None)
        if pkg is None or exe is None:
            continue
        pkg = pkg.perform(ctx) if hasattr(pkg, 'perform') else str(pkg)
        exe = exe.perform(ctx) if hasattr(exe, 'perform') else str(exe)
        key = '%s/%s' % (pkg, exe)
        counts[key] = counts.get(key, 0) + 1
    return counts


def count_viz_nodes(actions, ctx):
    """按 `(package, executable)` 统计被守护的三个节点的注册次数（含事件处理器内）。"""
    counts = _count_nodes(actions, ctx)
    return {k: counts.get(k, 0) for k in VIZ_NODES}


# --------------------------------------------------------------------------------------
# 1. 四格：full/lightweight × viz on/off → 三节点各 0/1 份
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize('backend', ['full', 'lightweight'])
def test_viz_registered_exactly_once_when_enabled(backend):
    """`viz:=true` → 三个叠加节点**恰好 1 份**（不是 2 份，也不是 0 份）。"""
    actions, ctx = emitted_actions(backend, 'true')
    counts = count_viz_nodes(actions, ctx)
    assert counts == {k: 1 for k in VIZ_NODES}, (
        '%s + viz:=true 的叠加节点注册次数 %r（期望各 1 份）—— 重复注册会让 RViz2 起两个、'
        '同名节点互相抢 latched 话题；为 0 则说明顶层注册被误删' % (backend, counts))


@pytest.mark.parametrize('backend', ['full', 'lightweight'])
def test_viz_registered_zero_when_disabled(backend):
    """`viz:=false` → 三个叠加节点**0 份**（默认演示不得被叠加层污染）。"""
    actions, ctx = emitted_actions(backend, 'false')
    counts = count_viz_nodes(actions, ctx)
    assert counts == {k: 0 for k in VIZ_NODES}, (
        '%s + viz:=false 的叠加节点注册次数 %r（期望各 0 份）' % (backend, counts))


# --------------------------------------------------------------------------------------
# 2. 反向对照：断言**确有区分度**（否则上面两条可能恒真）
# --------------------------------------------------------------------------------------

def test_viz_registration_counter_detects_double_registration():
    """给计数逻辑喂"同一动作出现两次" → 必须报 2，证明上面的 == 1 不是空断言。"""
    from launch import LaunchContext
    from launch_ros.actions import Node

    ctx = LaunchContext()
    node = Node(package='agc_task', executable='viz_markers', name='viz_markers')
    counts = count_viz_nodes([node, node], ctx)
    assert counts['agc_task/viz_markers'] == 2


def test_full_chain_still_registers_its_own_nodes_once():
    """修复只动叠加层：full 链的**唯一性敏感**节点仍各 1 份（防误删/误放大）。"""
    actions, ctx = emitted_actions('full', 'true')
    counts = _count_nodes(actions, ctx)
    for key in ('agc_air/px4_adapter', 'agc_air/takeoff_controller',
                'agc_air/trajectory_tracker', 'agc_air/standoff_follower',
                'agc_task/task_manager', 'agc_task/run_logger',
                'agc_task/scenario_reset', 'agc_task/intruder_driver'):
        assert counts.get(key) == 1, 'full 链节点 %s 注册 %r 份（期望 1）' % (key, counts.get(key))
