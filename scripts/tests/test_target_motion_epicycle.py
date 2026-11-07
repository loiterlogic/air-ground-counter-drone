"""目标机 `epicycle`（漂移轨道）运动学闸门 —— ADR-0031。

**为什么存在**：`epicycle` 是目标机新增的运动种类（`intruder_driver.motion` 的新取值）。
它要同时满足四条互相拉扯的约束，任何一条写错都会**静默**破坏下游：

 ① **越界安全**：水平位移恒 ≤ `drift_amplitude_m + radius_m`，且远小于 `run_region_radius_m`。
 写错成 `A·r` 或漏掉漂移项，会让 `_apply_region` 的夹持把轨迹"剪平"——目标机看起来在动，
 实际被钉在边界上，而**没有任何错误日志**（`terminated_` 只在第一次夹持时记一条）。
  ② **起点连续**：`_target(0)` 必须与 `_start_pose()` **逐位相等**。不等 ⇒ `_maybe_start` 的
     `dist(pos, start) <= start_tol_m` 永不成立 ⇒ `t0_` 恒 None ⇒ **目标机停在起始点不动**
 （这正是 H0 回归里"目标未起飞"那类故障的形状）。
  ③ **起点保持是常量**：`_start_pose()` 对 t 必须是常量。它当前实现是 `_target(0.0)`，
     但**若将来有人改成 `_target(now)`**，episode 开始前 setpoint 会随时间漂走 ⇒ 机体永远追不上 ⇒
 同样的静默停摆。本测试把这个不变量**锁死**。
 ④ **峰值速度上界**：`≤ A·ω_c + r·ω_o`（三角不等式）。该上界必须 ≤ 火控提前量给出的
 `1.206 m/s`（ADR-0031 推导），否则网瞄准点被 `target_max_lead_m` 截断、开始吃网半径余量。

**为什么放在 `scripts/tests/`（不是 `src/agc_task/test/`）**：本单白名单不含 `CMakeLists.txt`，
无法 `ament_add_pytest_test` 注册；而 `scripts/tests/` 被 `run_smoke` 的 `offline` 组
**按目录扫描**执行，不需要改构建脚本。测试本身仍是纯静态 + 纯数值（不启 ROS / 不启仿真）。

**怎么导入被测代码**：`intruder_driver.py` 在模块顶层 import `rclpy` / `px4_msgs`。
本测试在 import 前注入**最小桩模块**，从而在没有 ROS 环境时也能测到**真实源码**的数学部分
——不是复制一份公式来测自己（那种测试只能证明"两份副本一致"）。
"""

from __future__ import annotations

import importlib.util
import math
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / 'src' / 'agc_task' / 'scripts' / 'intruder_driver.py'

# ---- 被测参数（与 `base.yaml` / `s18` 场景同值；改配置必须同步改这里并说明）----
V_MPS = 1.0          # speed_mps
RADIUS_M = 1.8       # radius_m（轨道半径）
DRIFT_A_M = 0.6      # drift_amplitude_m（**圆心**漂移幅度，不是半径）
DRIFT_T_S = 30.0     # drift_period_s
RUN_REGION_R_M = 15.0
D_TRACK_M = 3.0
GOAL_TOL_M = 0.3     # RL 路径消费的 `path.goal_tol_m`
LEAD_BOUND_MPS = 1.206   # ADR-0031：火控提前量反解出的目标速度上界

ORIGIN = (3.0, -4.0, -2.0)   # 任取一个非零 episode 原点（NED）


# ------------------------------------------------------------------------------
# 最小桩模块：让被测源码能在无 ROS 环境下 import
# ------------------------------------------------------------------------------
class _Stub:
    """任意属性都返回另一个 `_Stub`，且可被调用 / 下标访问。

    足够让 `class IntruderDriver(Node)` 的定义、`QoSProfile(...)` 的调用、
 `VehicleCommand.VEHICLE_CMD_*` 的常量访问都通过——本测试只调用 `_target`，
 不构造节点实例（那需要 ROS 运行时）。
    """

    def __getattr__(self, name):
        return _Stub()

    def __call__(self, *a, **k):
        return _Stub()

    def __getitem__(self, k):
        return _Stub()


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        return _Stub()


_STUB_NAMES = (
    'rclpy', 'rclpy.node', 'rclpy.qos',
    'px4_msgs', 'px4_msgs.msg',
    'std_msgs', 'std_msgs.msg',
)


def _install_stubs():
    """注入桩模块；已存在（真有 ROS 环境）则**不覆盖**。"""
    for name in _STUB_NAMES:
        if name in sys.modules:
            continue
        mod = _StubModule(name)
        if name == 'rclpy.node':
            mod.Node = type('Node', (), {'__init__': lambda self, *a, **k: None})
        sys.modules[name] = mod


def _load_driver():
    """导入 `intruder_driver` 源码模块（只用于取 `IntruderDriver._target`）。"""
    _install_stubs()
    spec = importlib.util.spec_from_file_location('_idr_under_test', DRIVER)
    assert spec is not None and spec.loader is not None, '无法加载 %s' % DRIVER
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def driver_mod():
    return _load_driver()


_DRIVER_MOD = None


def _driver(motion, **over):
    """构造一个**未调用 `__init__`** 的 driver 实例，只填 `_target` 需要的属性。

 不走 `IntruderDriver.__init__`（那会 `declare_parameter` / 建 publisher，需要 ROS 运行时）。
 这样测到的是**真实源码里的 `_target` 实现**，只是绕开了 I/O 外壳。
    """
    global _DRIVER_MOD
    if _DRIVER_MOD is None:
        _DRIVER_MOD = _load_driver()
    obj = _DRIVER_MOD.IntruderDriver.__new__(_DRIVER_MOD.IntruderDriver)
    obj.motion_ = motion
    obj.origins_ = ORIGIN
    obj.alt_m_ = 12.0
    obj.v_ = over.get('v', V_MPS)
    obj.radius_ = over.get('radius', RADIUS_M)
    obj.drift_amplitude_m_ = over.get('drift_a', DRIFT_A_M)
    obj.drift_period_s_ = over.get('drift_t', DRIFT_T_S)
    obj.run_region_radius_m_ = RUN_REGION_R_M
    obj.terminated_ = False
    obj.get_logger = lambda: _Stub()
    return obj


# ------------------------------------------------------------------------------
# ① 越界安全 + ② 起点连续 + ③ 起点保持是常量
# ------------------------------------------------------------------------------
def test_epicycle_displacement_within_drift_plus_radius():
    """水平位移恒 ≤ A + r（三角不等式），且远小于运行区半径。

 这条同时是 `run_region_radius_m` 夹持**永不触发**的证明：若上界 > R_run，
 轨迹会被 `_apply_region` 剪平，而日志只有一条 error——静默退化。
    """
    d = _driver('epicycle')
    ox, oy, _ = ORIGIN
    bound = DRIFT_A_M + RADIUS_M
    worst = 0.0
    for i in range(20001):
        t = i * 0.02                      # 0 … 400 s，覆盖 >6 个漂移周期
        x, y, _z = d._target(t)
        worst = max(worst, math.hypot(x - ox, y - oy))
    # 严格上界 + 浮点容差
    assert worst <= bound + 1e-9, (
        'epicycle 位移上界被突破：实测 %.6f > A+r=%.6f（A=%.2f, r=%.2f）'
        % (worst, bound, DRIFT_A_M, RADIUS_M))
    # 且必须**真的接近**上界（否则说明参数没生效，例如漂移项被漏写）
    assert worst >= bound * 0.9, (
        'epicycle 位移从未接近上界（实测 %.6f，上界 %.6f）——漂移项可能未生效' % (worst, bound))
    # 夹持永不触发：上界必须**严格小于**运行区半径
    assert bound < RUN_REGION_R_M, (
        'A+r=%.2f 不小于 run_region_radius_m=%.2f ⇒ _apply_region 会剪平轨迹'
        % (bound, RUN_REGION_R_M))


def test_epicycle_start_pose_equals_target_at_zero_bitwise():
    """`_target(0)` 与 `_start_pose()` **逐位相等**（起点协议的前提）。

    `_start_pose()` 的实现是 `_apply_region(_target(0.0))`；对 epicycle 而言上界 < R_run，
 故夹持是恒等映射 ⇒ 两者必须逐位相同。若不等，`_maybe_start` 的
    `dist(pos, start) <= start_tol_m` 会永不满足，目标机停在起始点不动且无报错。
    """
    d = _driver('epicycle')
    t0 = d._target(0.0)
    sp = d._start_pose()
    assert t0 == sp, '_target(0)=%r 与 _start_pose()=%r 不逐位相等' % (t0, sp)
    # 且等于解析定义点 (ox + r, oy + A)：sin(0)=0 → 圆心在 (ox, oy+A)；cos(0)=1 → 轨道在 +r
    ox, oy, _ = ORIGIN
    assert t0[0] == pytest.approx(ox + RADIUS_M, abs=1e-12)
    assert t0[1] == pytest.approx(oy + DRIFT_A_M, abs=1e-12)


def test_start_pose_is_constant_in_time():
    """`_start_pose()` **对 t 是常量**——锁死"起点保持"不变量。

    当前实现 `_target(0.0)` 天然满足。本测试防的是将来有人把它改成依赖时间
    （例如 `_target(self._episode_elapsed())`）：那样 episode 开始前 setpoint 会漂走，
 机体永远追不上，表现为"目标机不动"，而**日志里没有任何异常**。
    """
    for motion in ('static', 'linear', 'maneuver', 'epicycle'):
        d = _driver(motion)
        first = d._start_pose()
        for _ in range(5):
            assert d._start_pose() == first, (
                '%s 的 _start_pose() 不是常量（第二次调用得到 %r，首次 %r）'
                % (motion, d._start_pose(), first))


def test_epicycle_velocity_is_finite_and_nonzero_at_t0():
    """`dp/dt(0)` 有限且非零——"切线速度非零"是**已知且无害**的。

    起点协议不靠"轨迹在 t=0 静止"，而靠 `t0_ is None` 期间发**常量** `_start_pose()`：
 机体收敛到该点后 `speed → 0`，`start_vel_eps_mps` 得以满足。本测试确认切线速度
 确实非零（否则说明公式退化成静止），从而把"为什么仍然能起步"的推理链钉在证据上。
    """
    d = _driver('epicycle')
    h = 1e-7
    p0 = d._target(0.0)
    p1 = d._target(h)
    vx, vy = (p1[0] - p0[0]) / h, (p1[1] - p0[1]) / h
    speed = math.hypot(vx, vy)
    assert math.isfinite(speed), 'dp/dt(0) 非有限：%r' % speed
    assert speed > 1e-3, (
        'dp/dt(0)=%.6f 近似为零 —— 公式可能退化为静止（与 epicycle 语义不符）' % speed)
    # 解析值：dp/dt(0) = (A·ω_c, 0) + (0, r·ω_o) = (A·2π/T, v)
    wc = 2.0 * math.pi / DRIFT_T_S
    assert vx == pytest.approx(DRIFT_A_M * wc, rel=1e-5)
    assert vy == pytest.approx(V_MPS, rel=1e-5)


# ------------------------------------------------------------------------------
# ④ 峰值速度上界 ≤ 火控提前量反解出的 1.206 m/s
# ------------------------------------------------------------------------------
def test_epicycle_peak_speed_within_lead_bound():
    """数值峰值速度 ≤ `A·ω_c + r·ω_o`，且该上界 ≤ 火控给出的 1.206 m/s。

    上界超过 1.206 ⇒ `TargetMotionFilter.predicted()` 的 `target_max_lead_m=1.5` 截断提前量，
 瞄准点开始落后目标，网半径余量被逐步吃掉（ADR-0031 的推导链）。
    """
    d = _driver('epicycle')
    wc = 2.0 * math.pi / DRIFT_T_S
    wo = V_MPS / RADIUS_M
    analytic_bound = DRIFT_A_M * wc + RADIUS_M * wo
    assert analytic_bound <= LEAD_BOUND_MPS + 1e-12, (
        '解析上界 A·ω_c + r·ω_o = %.6f 超过火控上界 %.3f m/s' % (analytic_bound, LEAD_BOUND_MPS))

    h = 1e-6
    worst = 0.0
    for i in range(20001):
        t = i * 0.02
        p, q = d._target(t), d._target(t + h)
        worst = max(worst, math.hypot((q[0] - p[0]) / h, (q[1] - p[1]) / h))
    assert worst <= analytic_bound + 1e-4, (
        '数值峰值速度 %.6f 超过解析上界 %.6f（三角不等式被破坏）' % (worst, analytic_bound))
    assert worst <= LEAD_BOUND_MPS, (
        '数值峰值速度 %.6f 超过火控上界 %.3f m/s' % (worst, LEAD_BOUND_MPS))


def test_epicycle_fits_inside_car_dwell_circle():
    """`A + r + goal_tol < d_track` ⇒ 目标机恒在车的 `d_track` 圆内。

 否则 `task_manager` 的 dwell 会以 `RANGE_EXCEEDED` 反复中断，
 `t_dwell_s=3.0` 永远攒不满 ⇒ 跟踪终态不可达（这不是"变难了"，是"结局不可达"）。
    """
    reach = DRIFT_A_M + RADIUS_M + GOAL_TOL_M
    assert reach < D_TRACK_M, (
        'A+r+goal_tol=%.2f 不小于 d_track=%.2f ⇒ RANGE_EXCEEDED 会中断 dwell'
        % (reach, D_TRACK_M))


# ------------------------------------------------------------------------------
# 确定性 / 可复现（同 seed 同配置必须逐位相同）
# ------------------------------------------------------------------------------
def test_epicycle_is_deterministic():
    """同一 `t` 两次求值**逐位相同**；且与求值顺序无关（无隐藏状态）。"""
    d1, d2 = _driver('epicycle'), _driver('epicycle')
    ts = [0.0, 0.37, 1.0, 7.25, 33.3, 119.9, 400.0]
    # 正向
    fwd = [d1._target(t) for t in ts]
    # 反向（若实现里藏了"上一帧"状态，顺序会改变结果）
    rev = [d2._target(t) for t in reversed(ts)]
    assert fwd == list(reversed(rev)), 'epicycle 求值依赖调用顺序（存在隐藏状态）'
    # 重复求值
    for t, p in zip(ts, fwd, strict=False):
        assert d1._target(t) == p, 't=%.3f 重复求值不一致' % t


# ------------------------------------------------------------------------------
# A2 回归：既有三种运动**逐值不变**
# ------------------------------------------------------------------------------
@pytest.mark.parametrize('motion,expected', [
    ('static', lambda t: (ORIGIN[0], ORIGIN[1], ORIGIN[2] - 12.0)),
    ('linear', lambda t: (ORIGIN[0], ORIGIN[1] + V_MPS * t, ORIGIN[2] - 12.0)),
    ('maneuver', lambda t: (
        ORIGIN[0] + RADIUS_M * math.cos((V_MPS / RADIUS_M) * t),
        ORIGIN[1] + RADIUS_M * math.sin((V_MPS / RADIUS_M) * t),
        ORIGIN[2] - 12.0)),
])
def test_legacy_motions_unchanged(motion, expected):
    """`static` / `linear` / `maneuver` 必须与历史公式**逐值相同**（A2 不回归）。

 注意 `maneuver` 的 t=0 是 `(ox+r, oy)` 而 epicycle 是 `(ox+r, oy+A)`——
 差异只来自新增的圆心漂移项，既有三支一个字符都没改。
    """
    d = _driver(motion)
    for i in range(0, 400):
        t = i * 0.1
        got, want = d._target(t), expected(t)
        assert got == pytest.approx(want, abs=1e-12), (
            '%s 在 t=%.2f 处偏离历史公式：got=%r want=%r' % (motion, t, got, want))


def test_unknown_motion_falls_back_to_static():
    """未知 `motion` 值仍回落 `static`（保持既有兜底行为，不新增隐式分支）。"""
    d = _driver('no_such_motion')
    assert d._target(5.0) == (ORIGIN[0], ORIGIN[1], ORIGIN[2] - 12.0)
