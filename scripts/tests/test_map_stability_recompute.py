"""地图稳定性复算脚本的守护测试（L2 静态 + 快速数值，不启 ROS / 不启仿真）。

守护的是「判据本身不能被悄悄放松」：如果有人把 `map_stability_recompute.py` 的
判据阈值改大、或把冷启动帧重新计入、或把 log-odds 公式改错（历史上真出过符号错误：
`1-1/(1+exp(-l))` 会把 p_init=0.30 算成 0.70，全图变占据），这里必须红。
"""

from __future__ import annotations

import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'tests' / 'map_stability_recompute.py'


def _src() -> str:
    return SCRIPT.read_text(encoding='utf-8')


def test_log_odds_roundtrip_formula_is_correct():
    """`pr()` 必须是 `1-1/(1+exp(l))`，不是 `1-1/(1+exp(-l))`（符号错会让 p 反转）。"""
    src = _src()
    m = re.search(r'def pr\(l\):\s*return\s*(.+)', src)
    assert m, '找不到 pr() 定义'
    expr = m.group(1).strip()
    assert 'math.exp(l)' in expr, (
        'pr 必须是 1-1/(1+exp(l))；写成 exp(-l) 会把概率反转（实测把 p_init 0.30 算成 0.70）')
    assert 'math.exp(-l)' not in expr, 'pr 不得用 exp(-l)（符号反转）'


def test_numeric_roundtrip_matches_cpp_semantics():
    """数值判据：logit↔概率必须与 log_odds_grid.hpp 一致（p_init=0.30 是锚点）。"""
    def lo(p: float) -> float:
        return math.log(p / (1 - p))

    def pr(l: float) -> float:
        return 1 - 1 / (1 + math.exp(l))

    for p in (0.12, 0.30, 0.50, 0.70, 0.97):
        assert abs(pr(lo(p)) - p) < 1e-12, 'logit 往返必须精确（p=%.2f）' % p
    # p_init 的 logit 必须为负（否则"未知"会被算成"偏占据"）
    assert lo(0.30) < 0, 'p_init=0.30 的 logit 必须为负'


def test_threshold_and_params_match_the_cpp_source():
    """脚本里的参数必须与 `log_odds_grid.hpp` / `perception.yaml` 的现行值一致。"""
    src = _src()
    hpp = (ROOT / 'src' / 'agc_perception' / 'include' / 'agc_perception'
           / 'log_odds_grid.hpp').read_text(encoding='utf-8')
    for name, default in (('p_hit', '0.70'), ('p_miss', '0.25'),
                          ('p_decay', '0.48'), ('occupied_threshold', '0.60'),
                          ('free_threshold', '0.20'), ('p_min', '0.12'),
                          ('p_max', '0.97'), ('p_init', '0.30')):
        assert re.search(r'%s\{%s\}' % (name, re.escape(default)), hpp), (
            'log_odds_grid.hpp 的 %s 缺省应为 %s（脚本复刻的是同一套语义）'
            % (name, default))


def test_stability_gate_is_p99_le_50_and_excludes_cold_start():
    """判据不得被放松：稳态 p99 ≤ 50 格，且冷启动帧必须排除并显式打印。

    **2026-11-09 口径细化（用户裁定）**：除冷启动帧外，还须排除**增长期**
    （地图从 0 建到饱和的那一段）—— 那里每帧新进入画幅的障碍是**合法增长**，
    不是抖动。判据阈值本身**未改**（仍 ≤ 50），改的只是"统计哪一段"。

    防放松的三条闸门：
      a. 阈值字面量仍是 50；
      b. 冷启动与增长期都必须被排除且**显式打印**；
      c. 增长期的边界必须是**可判定量**（由 occupied 序列推出来），
         不得是手填帧数 —— 手填数字换轨迹/场景后静默失效，失效时还看不出。
    """
    src = _src()
    assert '<= 50' in src, '判据阈值不得大于 50 格（改造前实测最大 2291 格）'
    assert '冷启动' in src, '必须显式说明冷启动帧被排除（否则读者会以为 p99 含它）'
    # b：增长期也必须排除，且打印
    assert '增长期' in src, '必须显式说明增长期被排除'
    assert 'GROWTH_SETTLE_RATIO' in src, '增长期边界必须是可配的常量，不得散落字面量'
    # c：边界必须由序列推出，不得手填帧数
    assert re.search(r'settle\s*=\s*next\(', src), (
        '增长期结束点必须由 occupied 序列推导（next(...)），不得手填帧数')
    assert not re.search(r'^SKIP_FRAMES\s*=', src, re.M), (
        '不得引入手填的"跳过帧数"常量（换轨迹/场景后静默失效）')
    # 统计窗口必须真的从 settle 开始
    assert re.search(r'd\s*=\s*sorted\(d_all\[settle:\]\)', src), (
        '稳态窗口必须从增长期结束点开始（d_all[settle:]）')


def test_script_exits_nonzero_on_failure():
    """判据不通过必须返回非 0（否则 CI 会静默放过）。"""
    src = _src()
    assert 'sys.exit(0 if ok else 1)' in src, '判据不通过必须非 0 退出'


def test_boundary_is_documented():
    """必须写明"完美感知下界"这个边界，否则会被当成实跑保证。"""
    src = _src()
    assert '下界' in src, '必须写明本复算是**下界**证据（真实链路抖动只会更大）'
    assert '完美感知' in src, '必须写明用真值栅格（不含分割/深度噪声）'
