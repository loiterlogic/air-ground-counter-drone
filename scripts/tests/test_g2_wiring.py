"""G2 静态判据：占位规划器/消费者的接线边界（不启动任何节点）。

对应 [ADR-0013 (k)(l)](../../docs/adr/0013-ground-planning-path-contract.md#top) 中可离线判定的部分：

* 占位规划器**不是** Navfn / planner_server / costmap（不链接 nav2_*、不建 Costmap2DROS）；
* 占位规划器**不发速度**（源码里没有 Twist 发布），因此不构成第二命令者；
* `command_source` 互斥：规划器只在 `rl` 分支起，`baseline`/`train`/`rl_high` 分支不起；
* 消费者的 `path.enabled` 是显式开关，默认 true；关闭时才是纯 goal 参考（对照模式）；
* `interface.py` 的 obs/action 空间未被改动（路径不进 obs）。
"""

import os
import re
import xml.etree.ElementTree as ET

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
GROUND = os.path.join(ROOT, 'src', 'agc_ground')
RL = os.path.join(ROOT, 'src', 'agc_rl')

PLANNER_SRC = os.path.join(GROUND, 'src', 'hybrid_astar_se2_planner.cpp')
PLANNER_NAME = 'hybrid_astar_se2_planner'
GROUND_CMAKE = os.path.join(GROUND, 'CMakeLists.txt')
GROUND_LAUNCH = os.path.join(GROUND, 'launch', 'ground_bringup.launch.py')
GROUND_YAML = os.path.join(GROUND, 'config', 'ground.yaml')
RL_YAML = os.path.join(RL, 'config', 'rl.yaml')
RL_NODE = os.path.join(RL, 'agc_rl', 'inference_node.py')
RL_INTERFACE = os.path.join(RL, 'agc_rl', 'interface.py')


def _read(p):
    with open(p, encoding='utf-8') as fh:
        return fh.read()


def _code_only(src):
    """去掉 // 行注释与 /* */ 块注释，只留代码——注释里提到的东西不算实现。"""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'//[^\n]*', '', src)


def test_planner_does_not_link_nav2():
    """占位规划器不得链接 nav2_*：Navfn/costmap 都属离线基线，不是本链。"""
    cmake = _read(GROUND_CMAKE)
    block = re.search(
        r'add_executable\(hybrid_astar_se2_planner[^)]*\)(.*?)(?=\nadd_executable|\ninstall\()',
        cmake, flags=re.S)
    assert block, '找不到 hybrid_astar_se2_planner 的构建块'
    body = block.group(0)
    for banned in ('nav2_core', 'nav2_costmap_2d', 'nav2_planner',
                   'nav2_navfn_planner', 'nav2_util', 'planner_server'):
        assert banned not in body, '占位规划器不得依赖 %s' % banned


def test_planner_source_has_no_velocity_publisher():
    """规划器只发路径：源码里不得出现 Twist 发布（否则就是第二命令者）。"""
    code = _code_only(_read(PLANNER_SRC))
    assert 'Twist' not in code, '占位规划器不得发布速度（Twist/TwistStamped）'
    assert 'cmd_vel_raw' not in code, '占位规划器不得写 cmd_vel_raw'
    # 必须是路径发布者
    assert 'Publisher<nav_msgs::msg::Path>' in code
    assert 'path_pub_->publish' in code


def test_planner_has_no_nav2_plugin_or_costmap():
    """源码层面确证：不加载 planner 插件、不自建 costmap（ADR-0048）。"""
    code = _code_only(_read(PLANNER_SRC))
    assert 'pluginlib' not in code
    assert 'NavfnPlanner' not in code
    assert 'Costmap2DROS' not in code
    assert 'planner_server' not in code
    # 唯一障碍输入是 /agc/map：不得订阅 scan / 点云 / costmap（ADR-0045 同源纪律）。
    # 按**消息类型与话题**判，不按裸子串（`corridor_max_scan_m` 里有 "scan" 但那是距离参数）。
    assert 'LaserScan' not in code
    assert 'PointCloud2' not in code
    assert 'scan_topic' not in code
    assert '"/agc/ground/scan' not in code
    # 必须走纯算法引擎（算法与 ROS 编排分离）
    assert 'planner::createPlanner' in code or 'createPlanner()' in code


def test_planner_does_not_republish_when_unauthorized():
    """无授权/无目标时必须 return，不得重发旧路径刷新 stamp（ADR-0013）。"""
    code = _code_only(_read(PLANNER_SRC))
    tick = re.search(r'void tick\(\)(.*?)\n  \}', code, flags=re.S)
    assert tick, '找不到 tick()'
    body = tick.group(1)
    assert 'authorized()' in body and 'return;' in body
    # 授权/新鲜度检查之前不得发布路径
    guard = body.split('publishPath')[0]
    assert 'publishPath' not in guard, '授权/新鲜度检查之前不得发布路径'


def test_launch_starts_planner_only_in_rl_branch():
    """`command_source` 互斥：规划器只挂在 rl 分支，其它分支不得起。"""
    src = _read(GROUND_LAUNCH)
    # rl 分支（else）是最后一个 `else:`，规划器装配必须出现在它之后
    idx_else = src.rindex('\n    else:')
    before, after = src[:idx_else], src[idx_else:]
    assert "executable='hybrid_astar_se2_planner'" not in before
    assert "executable='hybrid_astar_se2_planner'" in after


def test_launch_has_no_path_planner_switch():
    """必须**没有** launch 级路径开关：对照只能用节点本地 path.enabled。"""
    src = _read(GROUND_LAUNCH)
    assert 'path_planner' not in src.replace('hybrid_astar_se2_planner', ''), \
        '不应存在 path_planner launch 参数'
    assert 'planner_enabled' not in src


def test_ground_yaml_has_planner_section_matching_node_name():
    import yaml
    data = yaml.safe_load(_read(GROUND_YAML))
    assert 'hybrid_astar_se2_planner' in data
    p = data['hybrid_astar_se2_planner']['ros__parameters']
    assert p['path_topic'] == '/agc/ground/path'
    assert p['world_frame'] == 'world'
    # 安全层段已改为自研节点（ADR-0045）；`collision_monitor` 不再存在于主链配置。
    # 断言改为**正向**：必须有 ground_safety_filter 段，且它的输入/输出与契约一致。
    assert 'ground_safety_filter' in data
    safety = data['ground_safety_filter']['ros__parameters']
    assert safety['cmd_in_topic'] == '/agc/ground/cmd_vel_raw'
    assert safety['cmd_out_topic'] == '/agc/ground/cmd_vel'
    assert safety['map_topic'] == '/agc/map'
    # 安全层的唯一障碍输入是地图：不得把 scan 接回来（那会是第二份障碍表示）。
    assert 'scan_topic' not in safety, '安全层不得订阅 scan（ADR-0045 的 #inputs）'
    # 档位顺序不变量（ADR-0010）：紧急 < 碰撞 < 安全，且恢复门槛严格更高。
    assert safety['d_emergency'] < safety['d_collision'] < safety['d_safety']
    assert safety['d_recover_pass'] > safety['d_safety']


def test_search_dist_default_is_bounded_and_consistent():
    """B1：默认限界必须是正数，且节点默认与 YAML 一致（不得一方 0 一方正）。"""
    import re
    src = _read(RL_NODE)
    m = re.search(r"'path.search_dist_m',\s*([^)\n]+)\)", src)
    assert m, '找不到 path.search_dist_m 的节点默认值'
    default_expr = m.group(1).strip()
    # 节点默认是 lookahead*2 的表达式，或显式正数
    assert 'lookahead' in default_expr or (
        re.match(r'^[0-9.]+$', default_expr) and float(default_expr) > 0.0), \
        '节点默认必须是正的限界，实际为 %r' % default_expr
    import yaml
    data = yaml.safe_load(_read(RL_YAML))
    v = data['ground_policy_rl']['ros__parameters']['path']['search_dist_m']
    assert float(v) > 0.0, 'YAML 默认 search_dist_m 必须是正的限界，实际 %r' % v


def test_rl_yaml_path_block_defaults():
    import yaml
    data = yaml.safe_load(_read(RL_YAML))
    p = data['ground_policy_rl']['ros__parameters']
    assert p['path']['enabled'] is True, '路径默认必须启用（否则新链等于没接）'
    assert p['path']['topic'] == '/agc/ground/path'
    assert p['path']['frame_id'] == 'world'
    assert p['path']['max_age_s'] > 0


def test_interface_obs_action_space_unchanged():
    """路径**不进** obs：`interface.py` 的维度与动作数不得因本单改变。"""
    sys_path = os.path.join(RL)
    import sys
    sys.path.insert(0, sys_path)
    try:
        import importlib
        import agc_rl.interface as iface
        importlib.reload(iface)
        assert iface.N_ACTIONS == 5
        assert iface.obs_dim(12) == 12 + 3 + 5
        assert set(iface.ACTION_NAMES) == {0, 1, 2, 3, 4}
        # 路径相关字样不得出现在接口配置文件里（传输缝 ≠ 观测缝）
        assert 'path' not in _read(RL_INTERFACE).lower().split('along_path')[0]
    finally:
        sys.path.pop(0)


def test_consumer_keeps_goal_distance_in_obs():
    """obs 的"到目标距离"必须仍是 goal 距离，不得换成到参考点距离。"""
    src = _read(RL_NODE)
    assert 'build_observation(' in src
    # 传参处必须用 goal 距离变量 dist，而不是 aim 距离
    m = re.search(r'build_observation\(\s*self\.sectors, self\.x, self\.y, (\w+),', src)
    assert m and m.group(1) == 'dist', 'obs 距离维已被改成非 goal 距离'
    assert 'math.hypot(self.goal_x - self.x, self.goal_y - self.y)' in src


def test_consumer_path_is_required_input_when_enabled():
    """path.enabled 时路径是必要输入：无路径必须零速，不得 fallback 到 goal。"""
    src = _read(RL_NODE)
    # `_tick` 是类内最后一个方法（其后是模块级 main），故终止锚点用"去缩进的 def/main"。
    tick = re.search(r'def _tick\(self\):(.*?)(?=\ndef main\()', src, flags=re.S)
    assert tick, '找不到 _tick 方法体'
    body = tick.group(1)
    assert 'self.path_enabled' in body
    assert '_path_reference()' in body
    # 参考为 None → _stop 且 return
    assert re.search(r'if ref is None:\s*\n\s*self\._stop\(\)\s*\n\s*return', body)


def test_planner_rejects_negative_age():
    """B3：`fresh()` 必须拒绝负年龄（clock 回跳 / reset 前旧输入不得被重新包装）。"""
    code = _code_only(_read(PLANNER_SRC))
    m = re.search(r'bool fresh\([^)]*\)\s*const\s*\{(.*?)\n  \}', code, flags=re.S)
    assert m, '找不到 fresh()'
    body = m.group(1)
    assert 'age' in body, 'fresh() 应显式计算 age'
    assert 'age >= 0.0' in body, '必须显式拒绝负年龄（age >= 0.0）'


def test_package_xml_has_nav_msgs_dependency():
    """消费者用 nav_msgs/Path，依赖必须显式声明（否则干净构建会漏）。"""
    pkg = ET.parse(os.path.join(RL, 'package.xml')).getroot()
    deps = set()
    for tag in ('depend', 'build_depend', 'exec_depend', 'build_export_depend'):
        for el in pkg.findall(tag):
            deps.add((el.text or '').strip())
    assert 'nav_msgs' in deps
