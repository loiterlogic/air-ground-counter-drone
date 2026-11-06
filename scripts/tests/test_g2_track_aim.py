"""（ADR-0009）`observe_yaw_mode=track` 的静态/语义判据。

判据全部可从**源码文本**判定（不启 ROS），覆盖 request「必做验证 A」中可静态化的部分：

1. `track` 分支**只**用感知航迹（`target_pos_`），**不读** GT（`yaw_aim_pos_`）；
2. `/agc/gt/*` 指向订阅**仅在** `observe_yaw_mode == "target"` 时创建；
3. 无 fresh 航迹时有**确定性搜索**（三角波扫掠，含折返），且**不使用真值播种**
 （相位基准取接管机头 `search_center_yaw_`）；
4. 搜索**只改偏航**：不触碰轨迹/平移/高度基准；
5. reset 同时重置搜索相位基准与"已指向/已搜索"日志锁（不沿用上一集）；
6. `velocity`（默认）与 oracle `target` 分支语义未被改动；
7. NaN/Inf 航迹被拒（不得进入 `atan2`）。
"""

import os
import re

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TT = os.path.join(ROOT, 'src', 'agc_air', 'src', 'trajectory_tracker.cpp')
ER = os.path.join(ROOT, 'scripts', 'episode_runner.py')


def _read(p):
    with open(p, encoding='utf-8') as fh:
        return fh.read()


def _code_only(src):
    """去注释，只留代码——注释里提到 GT 不算读取 GT。"""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'//[^\n]*', '', src)


@pytest.fixture(scope='module')
def src():
    return _read(TT)


@pytest.fixture(scope='module')
def code(src):
    return _code_only(src)


def test_track_branch_uses_percept_track_not_gt(code):
    """`track` 分支的成功路径必须读 `target_pos_`，且该分支内不出现 `yaw_aim_pos_`。"""
    m = re.search(
        r'if \(observe_yaw_mode_ == "track" && track_aim_fresh\(\)\) \{(.*?)\n    \} else if',
        code, flags=re.S)
    assert m, '找不到 track 指向分支'
    body = m.group(1)
    assert 'target_pos_' in body, 'track 分支必须用感知航迹 target_pos_'
    assert 'yaw_aim_pos_' not in body, 'track 分支不得读 GT（yaw_aim_pos_）'


def test_gt_subscription_is_target_mode_only(code):
    """`/agc/gt` 订阅必须在 `observe_yaw_mode == "target"` 守卫内创建。"""
    m = re.search(
        r'if \(observe_yaw_mode_ == "target"\) \{(.*?)\n    \}\n',
        code, flags=re.S)
    assert m, '找不到 target 模式的 GT 订阅守卫'
    guarded = m.group(1)
    assert 'yaw_aim_sub_ = create_subscription' in guarded
    # 全文件里 `yaw_aim_sub_ = create_subscription` 只应出现一次（即守卫内）
    assert code.count('yaw_aim_sub_ = create_subscription') == 1


def test_search_is_deterministic_triangle_wave(code):
    """无 fresh 航迹时走确定性三角波扫掠（fmod + 折返），不是随机、不是朝真值。"""
    m = re.search(
        r'\} else if \(observe_yaw_mode_ == "track"\) \{(.*?)\n    \}\n    if \(observe_yaw_mode_ == "target"',
        code, flags=re.S)
    assert m, '找不到 track 搜索分支'
    body = m.group(1)
    assert 'std::fmod' in body, '搜索相位必须由 fmod 确定（可复现）'
    assert '2.0 * span - u' in body, '必须有折返（三角波）'
    assert 'search_center_yaw_' in body, '搜索基准必须取接管机头'
    assert 'yaw_aim_pos_' not in body, '搜索不得用真值播种'
    assert 'rand' not in body.lower(), '搜索不得含随机数'


def test_search_center_initialized_at_takeover_and_reset(src):
    """接管与相位复位都把搜索基准设为当时机头（不沿用上一集）。"""
    assert src.count('search_center_yaw_ = last_yaw_;') == 2, \
        '接管与 reset 各须重置一次搜索基准'
    # reset 处同时清日志锁
    reset_block = src[src.index('相位复位（/agc/air/reset_phase）') - 400:
                      src.index('相位复位（/agc/air/reset_phase）')]
    assert 'track_aim_logged_ = false' in reset_block
    assert 'track_search_logged_ = false' in reset_block


def test_search_changes_yaw_only(code):
    """搜索分支内不得出现轨迹/平移/高度基准的写入。"""
    m = re.search(
        r'\} else if \(observe_yaw_mode_ == "track"\) \{(.*?)\n    \}\n    if \(observe_yaw_mode_ == "target"',
        code, flags=re.S)
    body = m.group(1)
    for banned in ('trajectory_->', 'z_offset_', 'effective.pos', 'effective =', 'base_ref'):
        assert banned not in body, '搜索只许改偏航，禁止触碰 %s' % banned


def test_nan_track_rejected(code):
    """NaN/Inf 航迹必须在进入 atan2 前被拒。"""
    assert 'std::isfinite(dx) && std::isfinite(dy)' in code
    assert 'track_aim_fresh' in code
    m = re.search(r'bool track_aim_fresh\(\) const\s*\{(.*?)\n  \}', code, flags=re.S)
    assert m, '找不到 track_aim_fresh()'
    assert 'std::isfinite(target_pos_.x())' in m.group(1)


def test_velocity_default_and_target_branch_preserved(code, src):
    """默认仍是 velocity；target 分支的 GT 新鲜门与"退回随速度"语义保留。"""
    assert 'declare_param_idempotent<std::string>("observe_yaw_mode", "velocity")' in code
    assert 'if (observe_yaw_mode_ == "target" && aim_fresh)' in code
    assert 'const bool aim_fresh = yawAimFresh();' in code


def test_episode_runner_offers_track():
    s = _read(ER)
    assert "choices=['', 'velocity', 'target', 'track']" in s
    # 默认必须是空（= 用 air.yaml 缺省 velocity），不得把默认改成 track
    assert "--observe-yaw-mode', default=''" in s


def test_no_gt_subscription_or_read_for_track(code):
    """`track` 不得新建 GT 订阅、也不得读 GT 变量。

 注意：日志文本里出现 "/agc/gt" 字样是**免责声明**（"未使用 /agc/gt"），不是订阅行为；
 因此判据只查**代码行为**：`create_subscription` 与 `yaw_aim_` 变量。
    """
    track_block = code[code.index('observe_yaw_mode_ == "track"'):
                       code.index('if (observe_yaw_mode_ == "target" && aim_fresh)')]
    assert 'create_subscription' not in track_block, 'track 分支不得新建任何订阅'
    assert 'yaw_aim_' not in track_block, 'track 分支不得读 GT 变量 yaw_aim_*'
