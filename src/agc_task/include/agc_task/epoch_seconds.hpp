// epoch_seconds.hpp —— summary.json 中 UNIX 时间戳字段的格式化（ P0 / T2）
//
// 背景：`run_logger` 原先直接 `<< double`（默认 6 位有效数字），实测
// `wall_start_unix_s` 被写成 `1.79291e+09`，时间分辨率退化到约 2 分钟。
// 这里只提高精度，不改 JSON number / double 语义：
// * 17 位有效数字 = double 的最小往返精度；
// * 默认浮点格式（非 `std::fixed`），整数秒不会被写成 `123.000000`。

#pragma once

#include <iomanip>
#include <sstream>
#include <string>

namespace agc_task
{

inline std::string formatEpochSeconds(double seconds)
{
  std::ostringstream out;
  out << std::setprecision(17) << seconds;
  return out.str();
}

}  // namespace agc_task
