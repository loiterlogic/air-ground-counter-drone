// test_alpha_beta.cpp —— 速度滤波有效性（可执行判据）
//
// ## 为什么这条测试存在
//
// 真值链路加噪声成为主线之后，速度**不能**再用位置差分：位置带 σ_p 时
// 差分速度噪声是 `σ_v = σ_p·√2/Δt ≈ 9.43·σ_p`（Δt=0.15 s），σ_p=0.5 m 时就有 4.7 m/s，
// 比目标自身速度（0.5 m/s）还大一个量级，会直接驱动 `standoff_follower` 的速度前馈。
// 当时这个结论只写在 ADR-0009 里，`AlphaBeta` 还藏在 `gt_adapter.cpp` 的匿名命名空间中，
// **没有任何可执行判据**。本测试把它钉死：
//
// 1. 增益公式（Kalata 关系式）在代表性指数上的解析值；
// 2. 蒙特卡洛：静止目标 + 高斯位置噪声 → 滤波器速度标准差显著低于差分（≥ 10 倍）；
// 3. 退化点：σ_p→0 时 α→1、β→2（**必须由调用方旁路**，阈值由头文件单点定义）；
// 4. 匀速目标 → 速度估计无偏（滤波器不能把真速度吃掉）。
//
// 蒙特卡洛用固定 seed → 结果可复现；阈值取宽松下界（≥10×），不把某一次抽样的
// 具体倍数钉死成回归（那是脆弱判据）。

#include <cmath>
#include <random>
#include <vector>

#include <gtest/gtest.h>

#include "agc_perception/alpha_beta.hpp"

namespace
{
constexpr double kDt = 0.1;          // 10 Hz 观测
constexpr double kSigmaW = 0.5;      // 目标机动强度（m/s²），与 perception.yaml 同值
constexpr int kSamples = 400;        // 蒙特卡洛样本数（够稳、单测仍在 1 s 内）
constexpr int kSteps = 400;          // 每样本步数（足够进入稳态）
constexpr double kTargetV = 0.5;     // 目标自身速度量级（m/s）

/// 静止目标：位置 ~ N(0, σ_p)，返回末拍速度估计的标准差。
double sigmaVelocity(double sigma_p, bool filtered, unsigned seed = 12345)
{
  agc::AlphaBeta f;
  double alpha = 0.0, beta = 0.0;
  agc::AlphaBeta::gains(kSigmaW, sigma_p, kDt, &alpha, &beta);
  std::mt19937 gen(seed);
  std::normal_distribution<double> noise(0.0, sigma_p);
  std::vector<double> v_hat;
  v_hat.reserve(kSamples);
  for (int n = 0; n < kSamples; ++n) {
    f.reset();
    double prev_z = noise(gen);
    double last_v = 0.0;
    for (int k = 1; k < kSteps; ++k) {
      const double z = noise(gen);
      if (filtered) {
        f.update(z, kDt, alpha, beta);
        last_v = f.v;
      } else {
        last_v = (z - prev_z) / kDt;   // 单拍差分（旧口径）
      }
      prev_z = z;
    }
    v_hat.push_back(last_v);
  }
  double mean = 0.0;
  for (double v : v_hat) {mean += v;}
  mean /= static_cast<double>(v_hat.size());
  double var = 0.0;
  for (double v : v_hat) {var += (v - mean) * (v - mean);}
  var /= static_cast<double>(v_hat.size() - 1);
  return std::sqrt(var);
}
}  // namespace

/// ① 增益解析值：Λ = σ_w·Δt²/σ_p，α = 1−r²，β = 2(2−α) − 4√(1−α)。
TEST(AlphaBeta, GainFormulaMatchesKalata)
{
  struct Case {double sigma_p; double alpha; double beta;};
  // 期望值由 Λ 公式独立算出（σ_w=0.5, Δt=0.1）：见 ADR-0009 的档位表。
  const Case cases[] = {
    {0.25, 0.181, 0.018},
    {0.50, 0.132, 0.009},
    {1.00, 0.095, 0.005},
  };
  for (const auto & c : cases) {
    double a = 0.0, b = 0.0;
    agc::AlphaBeta::gains(kSigmaW, c.sigma_p, kDt, &a, &b);
    EXPECT_NEAR(a, c.alpha, 2e-3) << "sigma_p=" << c.sigma_p;
    EXPECT_NEAR(b, c.beta, 2e-3) << "sigma_p=" << c.sigma_p;
  }
}

/// ② 滤波器必须真的抑制噪声放大：同一噪声序列，σ_v 至少改善 10 倍。
TEST(AlphaBeta, FilterSuppressesNoiseAmplification)
{
  for (double sigma_p : {0.25, 0.50, 1.00}) {
    const double s_diff = sigmaVelocity(sigma_p, false);
    const double s_ab = sigmaVelocity(sigma_p, true);
    EXPECT_GT(s_diff, 0.0);
    EXPECT_GT(s_ab, 0.0);
    EXPECT_GT(s_diff / s_ab, 10.0)
      << "sigma_p=" << sigma_p << " diff=" << s_diff << " ab=" << s_ab;
    // 绝对量级：滤波器速度噪声必须显著小于目标自身速度（否则前馈仍被噪声驱动）。
    // 实测（本测试）：σ_p=0.25/0.5/1.0 → σ_v=0.079/0.095/0.108 m/s，
    // 即最大档也仅为目标速度 0.5 m/s 的 **21.6%**；差分在同档是 3.54/7.07/14.14 m/s
    // （28× 目标速度）。阈值取 30% 作宽松上界——不把某一次抽样的具体倍数钉成脆弱回归。
    EXPECT_LT(s_ab, 0.3 * kTargetV)
      << "sigma_p=" << sigma_p << " ab=" << s_ab << " (目标速度 " << kTargetV << ")";
  }
}

/// ③ 退化点：σ_p→0 时解析增益趋于 α=1、β=2 —— 这正是**必须旁路**的原因。
TEST(AlphaBeta, ZeroNoiseDegeneratesAndMustBeBypassed)
{
  double a = 0.0, b = 0.0;
  agc::AlphaBeta::gains(kSigmaW, 1e-9, kDt, &a, &b);
  EXPECT_GT(a, 0.999);
  EXPECT_GT(b, 1.99);
  // 旁路判据（调用方口径）：enabled ⟺ σ_p > kFilterBypassSigmaM。
  // 阈值是本仓**单点定义**（alpha_beta.hpp），不得在各节点散落魔数。
  const auto enabled = [](double sigma_p) {return sigma_p > agc::kFilterBypassSigmaM;};
  EXPECT_FALSE(enabled(0.0))   << "理想基线（σ=0）必须旁路";
  EXPECT_FALSE(enabled(1e-9))  << "退化点必须旁路";
  EXPECT_FALSE(enabled(1e-6))  << "阈值本身仍属旁路区（闭区间口径）";
  EXPECT_TRUE(enabled(1e-3))   << "1 mm 及以上一律启用滤波器";
  EXPECT_TRUE(enabled(0.25))   << "nominal 档必须启用";
  EXPECT_TRUE(enabled(1.0))    << "stress 档必须启用";
}

/// ④ 匀速目标：滤波器速度估计无偏（不得把真实速度吃掉）。
TEST(AlphaBeta, ConstantVelocityRemainsUnbiased)
{
  agc::AlphaBeta f;
  double a = 0.0, b = 0.0;
  agc::AlphaBeta::gains(kSigmaW, 0.3, kDt, &a, &b);
  std::mt19937 gen(7);
  std::normal_distribution<double> noise(0.0, 0.3);
  double p_true = 0.0;
  for (int k = 0; k < 500; ++k) {
    p_true += kTargetV * kDt;
    f.update(p_true + noise(gen), kDt, a, b);
  }
  EXPECT_NEAR(f.v, kTargetV, 0.1);
}

/// ⑤ 差分放大系数 `√2/Δt` 与实现同源（供产物与文档引用，不再手写 9.43）。
TEST(AlphaBeta, DiffNoiseRatioMatchesFormula)
{
  EXPECT_NEAR(agc::diffVelocityNoiseRatio(0.15), std::sqrt(2.0) / 0.15, 1e-12);
  EXPECT_NEAR(agc::diffVelocityNoiseRatio(0.10), std::sqrt(2.0) / 0.10, 1e-12);
}
