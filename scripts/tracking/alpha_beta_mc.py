#!/usr/bin/env python3
"""alpha_beta_mc —— 可复跑产物：位置差分 vs α-β 滤波的 σ_v 对照。

## 为什么需要它

N4 把"给真值链路加噪声"变成主线后，速度**不能**再用位置差分：位置带 σ_p 时差分速度
噪声是 `σ_v = σ_p·√2/Δt`。当时这个结论只写在 ADR-0009 里，**没有任何可复跑的产物**，
且文档里那组数字（42.8× / 65.2× / 110.9×）与两种口径都对不上——因为把"差分窗长"
和"发布周期"混用了。

本脚本用与 C++ 实现**同一组解析增益**（`AlphaBeta::gains`，Kalata 关系式）跑蒙特卡洛，
把两种口径**分开列**，使后续引用只能引对：

    σ_v(diff, 窗长 W)        = σ_p·√2/W        ← 旧实现 diff_window_s=0.15
    σ_v(diff, 单拍 Δt)       = σ_p·√2/Δt        ← 同刻两帧相减
    σ_v(α-β, 稳态)           = 蒙特卡洛实测      ← 本节点实际输出

## 口径纪律

* **固定 seed** → 结果可复现；不把某一次抽样的具体倍数当回归判据（那是脆弱判据）。
* 每个数字都标出它属于哪一列，**禁止**跨口径混用比值。
* 产物落 `experiments/<campaign>/<run_id>/metrics/alpha_beta_mc.json`（ADR-0006）。

用法：
  python3 scripts/tracking/alpha_beta_mc.py \
      --out experiments/n4-tracking-metrics/20261104-alpha-beta-0/metrics/alpha_beta_mc.json
"""

import argparse
import json
import math
import os
import random
import statistics
import sys

# 与 perception.yaml / air.yaml 同值（**不复制**参数的唯一来源原则在此破例：
# 这是纯离线数值实验，不读 ROS 参数；改配置文件时须同步本文件的 DEFAULTS 并重跑）。
DEFAULTS = {
    'sigma_w_mps2': 0.5,     # filter_sigma_w_mps2
    'dt_s': 0.1,             # 发布周期（gt_adapter rate_hz=10）
    'diff_window_s': 0.15,   # diff_window_s（旧差分口径）
    'samples': 2000,         # 蒙特卡洛样本数
    'steps': 600,            # 每样本步数（足够进入稳态）
    'seed': 12345,
}


def gains(sigma_w, sigma_p, dt):
    """与 `agc/include/agc_perception/alpha_beta.hpp::AlphaBeta::gains` 逐字同式。"""
    sp = max(sigma_p, 1e-9)
    d = max(dt, 1e-9)
    lam = max(0.0, sigma_w) * d * d / sp
    r = (4.0 + lam - math.sqrt(8.0 * lam + lam * lam)) / 4.0
    alpha = 1.0 - r * r
    alpha = min(1.0, max(0.0, alpha))
    beta = 2.0 * (2.0 - alpha) - 4.0 * math.sqrt(max(0.0, 1.0 - alpha))
    beta = min(2.0, max(0.0, beta))
    return alpha, beta


def sigma_v_alpha_beta(sigma_p, cfg):
    """静止目标 + 高斯位置噪声 → 稳态速度估计标准差（蒙特卡洛）。"""
    alpha, beta = gains(cfg['sigma_w_mps2'], sigma_p, cfg['dt_s'])
    rnd = random.Random(cfg['seed'])
    dt = cfg['dt_s']
    vs = []
    for _ in range(cfg['samples']):
        p = 0.0
        v = 0.0
        for _k in range(cfg['steps']):
            z = rnd.gauss(0.0, sigma_p)
            p_pred = p + v * dt
            innov = z - p_pred
            p = p_pred + alpha * innov
            v = v + beta * innov / dt
        vs.append(v)
    return statistics.stdev(vs), alpha, beta


def main():
    ap = argparse.ArgumentParser(description='N4 σ_v 对照（差分 vs α-β）')
    ap.add_argument('--out', required=True, help='产物 JSON 路径（ADR-0006 落点）')
    ap.add_argument('--sigma-w', type=float, default=DEFAULTS['sigma_w_mps2'])
    ap.add_argument('--dt', type=float, default=DEFAULTS['dt_s'])
    ap.add_argument('--diff-window', type=float, default=DEFAULTS['diff_window_s'])
    ap.add_argument('--samples', type=int, default=DEFAULTS['samples'])
    ap.add_argument('--steps', type=int, default=DEFAULTS['steps'])
    ap.add_argument('--seed', type=int, default=DEFAULTS['seed'])
    args = ap.parse_args()

    cfg = {
        'sigma_w_mps2': args.sigma_w, 'dt_s': args.dt,
        'diff_window_s': args.diff_window, 'samples': args.samples,
        'steps': args.steps, 'seed': args.seed,
    }

    rows = []
    for sigma_p in (0.25, 0.50, 1.00):
        sv_ab, alpha, beta = sigma_v_alpha_beta(sigma_p, cfg)
        sv_diff_window = sigma_p * math.sqrt(2.0) / cfg['diff_window_s']
        sv_diff_dt = sigma_p * math.sqrt(2.0) / cfg['dt_s']
        rows.append({
            'sigma_p_m': sigma_p,
            'gains': {'alpha': round(alpha, 6), 'beta': round(beta, 6)},
            # 三种口径**分开列**，禁止跨列比
            'sigma_v_diff_window_mps': round(sv_diff_window, 4),
            'sigma_v_diff_per_frame_mps': round(sv_diff_dt, 4),
            'sigma_v_alpha_beta_mps': round(sv_ab, 4),
            'improvement_vs_window': round(sv_diff_window / sv_ab, 1),
            'improvement_vs_per_frame': round(sv_diff_dt / sv_ab, 1),
        })

    doc = {
        'tool': 'scripts/tracking/alpha_beta_mc.py',
        'definition_version': 'n4_alpha_beta_mc_v1',
        'purpose': '证明 α-β 滤波器确实抑制了位置差分对噪声的放大',
        'not_a_summary_field': True,
        'config': cfg,
        'gains_formula': 'Λ = σ_w·Δt²/σ_p; α = 1−r²; β = 2(2−α)−4√(1−α)（Kalata）',
        'rows': rows,
        'reading': {
            'sigma_v_diff_window_mps':
                '旧实现口径：σ_p·√2/diff_window_s（diff_window_s=0.15）',
            'sigma_v_diff_per_frame_mps':
                '同刻两帧相减口径：σ_p·√2/Δt（Δt=0.1）',
            'sigma_v_alpha_beta_mps':
                '本节点实际输出：蒙特卡洛稳态 σ_v',
            'warning': '三列**不可跨列混用比值**；引用时必须写明用的哪一列',
        },
        'cross_check': {
            'cpp_test': 'src/agc_perception/test/test_alpha_beta.cpp',
            'note': 'C++ 单测用同一组增益跑蒙特卡洛，阈值取宽松下界（≥10×），不钉死具体倍数',
        },
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, args.out)

    print('sigma_p | α      β      | σ_v(窗0.15) | σ_v(单拍) | σ_v(α-β) | 改善(窗/单拍)')
    for r in rows:
        print('%7.2f | %.3f %.3f | %11.3f | %9.3f | %8.3f | %5.1f× / %5.1f×' % (
            r['sigma_p_m'], r['gains']['alpha'], r['gains']['beta'],
            r['sigma_v_diff_window_mps'], r['sigma_v_diff_per_frame_mps'],
            r['sigma_v_alpha_beta_mps'],
            r['improvement_vs_window'], r['improvement_vs_per_frame']))
    print('\n落盘：%s' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
