// agc_perception α-β 滤波器（W4 共享头；2026-11-04 从 gt_adapter.cpp 抽出）
//
// ## 为什么抽出来
//
// 原实现是 `gt_adapter.cpp` 里的匿名 `struct AlphaBeta`：**不可被任何测试引用**，
// 于是"速度噪声被抑制 40–100 倍"这个结论只能写在 ADR 里，无法由可执行判据复核
// （N4 出口判据 3 要求"产物含 σ_v 对照"，仓内当时既无脚本也无单测）。
// 抽到公共头后：C++ 单测（`test_alpha_beta.cpp`）可直接跑蒙特卡洛，
// `scripts/alpha_beta_mc.py` 用同一组解析增益产出对照产物。
//
// ## 口径（不得改动，改动即改行为）
//
// 状态 [p, v]，匀速预测 + 新息加权：
//     p̂ = p + v·Δt；  r = z − p̂
//     p ← p̂ + α·r；    v ← v + β·r/Δt
//
// 增益**不手调**：由跟踪指数 Λ = σ_w·Δt²/σ_p 解析给出（Kalata 稳态 α-β 关系），
// 其中 σ_w 为目标机动过程噪声（m/s²），σ_p 为量测噪声标准差（m）。
// 物理含义：目标越机动 / 量测越准 → Λ 越大 → α、β 越大 → 越信新观测。
//
// ## 退化保护（必须保留，由调用方实施）
//
// σ_p → 0 时 Λ → ∞，解析增益趋于 α=1, β=2，滤波器退化为**二阶振荡**
// （实测速度序列在 1.00 / 0.00 之间逐拍翻转）。故调用方在 `σ_p ≤ 1e-6 m` 时
// **旁路滤波器**，回落短窗差分（零噪声下差分精确）。
// 本头只提供 `gains()` 与 `update()`；是否旁路由使用方判定并记录（gt_adapter 的
// `filterActive()`），旁路判据阈值 `kFilterBypassSigmaM` 在此单点定义。

#pragma once

#include <algorithm>
#include <cmath>

namespace agc
{

/// 滤波器旁路阈值（m）：σ_p ≤ 本值时**不得**启用 α-β（α→1, β→2 会退化振荡）。
inline constexpr double kFilterBypassSigmaM = 1e-6;

/// α-β 滤波器（单轴）。状态 [p, v]。
struct AlphaBeta
{
  double p{0.0};
  double v{0.0};
  bool init{false};

  void reset()
  {
    p = 0.0;
    v = 0.0;
    init = false;
  }

  /// 由跟踪指数解析增益。
  /// Λ→0（量测极准 / 目标不机动）→ α,β 小（强平滑）；
  /// Λ→∞（量测极差 / 目标剧烈机动）→ α→1（全信新观测）。
  static void gains(double sigma_w, double sigma_p, double dt, double * alpha, double * beta)
  {
    const double sp = std::max(sigma_p, 1e-9);
    const double d = std::max(dt, 1e-9);
    const double lam = std::max(0.0, sigma_w) * d * d / sp;
    // r 为稳态极点（0..1）：Λ=0 → r=1（α=0）；Λ→∞ → r→0（α→1）
    const double r = (4.0 + lam - std::sqrt(8.0 * lam + lam * lam)) / 4.0;
    const double a = 1.0 - r * r;
    *alpha = std::min(1.0, std::max(0.0, a));
    // β = 2(2−α) − 4√(1−α)（Kalata 关系式）；α=1 时 β=2
    *beta = 2.0 * (2.0 - *alpha) - 4.0 * std::sqrt(std::max(0.0, 1.0 - *alpha));
    *beta = std::min(2.0, std::max(0.0, *beta));
  }

  void update(double z, double dt, double alpha, double beta)
  {
    if (!init) {
      p = z;
      v = 0.0;
      init = true;
      return;
    }
    const double p_pred = p + v * dt;   // 匀速预测
    const double innov = z - p_pred;    // 新息
    p = p_pred + alpha * innov;
    v = v + (beta * innov) / std::max(dt, 1e-9);
  }
};

/// 差分速度的噪声放大系数：σ_v = ratio · σ_p。
///
/// 由 `σ_v = σ_p·√2/Δt` 直接得出（两个独立同分布位置观测之差）。参数 `window_s`
/// 是**差分窗长**（`diff_window_s`），不是发布周期——旧实现用 0.15 s 窗，
/// 同刻两帧相减时窗长退化为单拍周期，故两种口径都要能算（见 `scripts/alpha_beta_mc.py`）。
inline double diffVelocityNoiseRatio(double window_s)
{
  return std::sqrt(2.0) / std::max(window_s, 1e-9);
}

}  // namespace agc
