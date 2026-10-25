// test_epoch_seconds.cpp —— W8 P0 / T2：epoch 秒格式化精度回归

#include <cmath>
#include <string>

#include <gtest/gtest.h>

#include "agc_task/epoch_seconds.hpp"

TEST(EpochSeconds, FractionalSecondsRoundTripAndNotScientific)
{
  const double v = 1792912345.1234567;
  const std::string out = agc_task::formatEpochSeconds(v);

  // 朴素 `<< double`（6 位有效数字）会把小数秒丢掉；17 位有效数字必须往返一致。
  EXPECT_LT(std::fabs(std::stod(out) - v), 1e-3);
  // 不得被截断成科学计数法。
  EXPECT_EQ(out.find('e'), std::string::npos);
  EXPECT_EQ(out.find('E'), std::string::npos);
  EXPECT_NE(out.find('.'), std::string::npos);
}

TEST(EpochSeconds, IntegerSecondsNotSixSignificantDigits)
{
  const double v = 1792912345.0;
  const std::string out = agc_task::formatEpochSeconds(v);

  // 6 位有效数字只能写成 `1.79291e+09`；整数秒必须精确、且以十进制整数形式输出。
  EXPECT_EQ(out.find('e'), std::string::npos);
  EXPECT_EQ(out.find('E'), std::string::npos);
  EXPECT_GE(out.size(), 10u);
  EXPECT_EQ(std::stod(out), v);
}
