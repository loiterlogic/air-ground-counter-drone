// agc_perception 置信度模型（共享头，；2026-11-03 语义解耦）
//
// ## 为什么改（本次改动的全部理由）
//
// 旧口径把**精度**与**可信度**混成一个数：
//
// conf = 1 - exp(-tol² / (2σ²)) // P(|err| <= tol)，由 σ 解析派生
//
// 后果（实测）：`tol=0.25 m` 时 σ 只要超过 **0.2123 m**，conf 就跌破下游的
// `confidence_min=0.5`，**整条航迹被拒收**。于是"给真值链路加 0.5 m 噪声"这个
// 完全合理的需求，会直接把链路打断——噪声档位实际被 `tol` 反向锁死在 0.21 m 以下，
// 而目标机体本身就有 0.32 m。**这不是模型不准，是两个语义被塞进一个字段。**
//
// ## 解耦后的口径
//
// | 字段 | 回答的问题 | 来源 | 消费者 |
// |---|---|---|---|
// | `TargetTrack.confidence` | **这条航迹是不是真的**（链路可信度 / 检出可信度） | 通道配置显式声明 | `confidence_min` 门 |
// | `TargetTrack.pose.covariance` | **这条航迹有多准**（精度） | σ_xy / σ_z | 融合加权、误差评估 |
//
// 两者**不再互相派生**。σ 变大只影响协方差与融合权重，**不再**导致航迹被拒。
//
// ## 诚实边界（不得误读）
//
// 1. `confidence` 现在是**配置声明的常数**（每通道一个），不是从数据估计出来的。
// 真实系统里它应由检测器输出（分类分数 / 跟踪确认次数）给出；本项目不训练检测器，
// 故只能声明。**不得**把"conf=1.0"写成"识别置信度高"——它只表示"本通道的航迹按定义
// 为真"（真值通道）或"本通道按配置可信"（仿真通道）。
// 2. 需要检验 `confidence_min` 门本身时，把某通道的 `confidence` 配到 0.5 以下即可
// （活跃配置见 `config/perception.yaml` 的 gt_adapter 段），**不再**靠"把 σ 调大"
// 来触发拒绝——那是在用精度问题冒充可信度问题。
// 3. 旧函数 `coverageConfidence` 保留但**不再用于产生 `confidence` 字段**；它仍有
// 独立的诊断价值（"给定 σ，误差落在 tol 内的概率是多少"），调用点须显式说明用途。

#pragma once

#include <algorithm>
#include <cmath>

namespace agc
{

/// 旧口径：2D 径向（Rayleigh）覆盖 P(|err| <= tol) = 1 - exp(-tol²/(2σ²))。
///
/// **不再用于生成 `TargetTrack.confidence`**（见文件头「为什么改」）。
/// 保留用途：给定通道 σ 与任务容差，评估"该通道的精度是否够用"——属**诊断量**，
/// 不是航迹可信度。任何调用点必须在注释里写明它算的是精度覆盖、不是可信度。
inline double coverageProbability(double sigma_xy_m, double tol_m)
{
  const double s2 = sigma_xy_m * sigma_xy_m;
  if (s2 <= 1e-12) {return 1.0;}
  const double c = 1.0 - std::exp(-(tol_m * tol_m) / (2.0 * s2));
  return std::min(1.0, std::max(0.0, c));
}

/// 旧名保留（避免下游 include 断裂）；语义同 `coverageProbability`，**不是** confidence。
inline double coverageConfidence(double sigma_xy_m, double tol_m)
{
  return coverageProbability(sigma_xy_m, tol_m);
}

/// 航迹可信度：由**通道配置显式声明**，不从 σ 派生。
/// 缺省 1.0 = "本通道的航迹按定义为真"（真值通道 / 理想基线）。
inline double declaredConfidence(double configured)
{
  return std::min(1.0, std::max(0.0, configured));
}

}  // namespace agc
