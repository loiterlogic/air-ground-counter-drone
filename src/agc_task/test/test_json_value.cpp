// test_json_value.cpp —— JSON 标量序列化：转义正确性与数值可往返
//
// 为什么这些断言值得写：`run_logger` 的 summary / mission_fco 证据是**论文与验收的核验对象**，
// 它们由手工拼字符串产生。一个未转义的换行或引号会让整份 JSON 解析失败（而失败发生在
// 归档之后、复盘之时）；一个被默认精度截断的 double 会让时间戳退化（本仓真发生过：
// 6 位有效数字把 `1792912345.123` 写成 `1.79291e+09`，分辨率约 2 分钟）。

#include <cmath>
#include <string>

#include <gtest/gtest.h>

#include "agc_task/json_value.hpp"

TEST(JsonValue, EscapesQuoteAndBackslash)
{
  EXPECT_EQ(agc_task::jsonString("a\"b"), "\"a\\\"b\"");
  EXPECT_EQ(agc_task::jsonString("a\\b"), "\"a\\\\b\"");
}

TEST(JsonValue, EscapesControlCharactersSoOutputStaysOneLine)
{
  // 旧实现只转义 \ 与 "，遇到换行会写出跨行字符串 → 解析器直接报错。
  const std::string out = agc_task::jsonString("a\nb\tc\rd");
  EXPECT_EQ(out.find('\n'), std::string::npos);
  EXPECT_EQ(out.find('\t'), std::string::npos);
  EXPECT_EQ(out.find('\r'), std::string::npos);
  EXPECT_EQ(out, "\"a\\nb\\tc\\rd\"");
}

TEST(JsonValue, EscapesRemainingControlCharsAsUnicode)
{
  const std::string out = agc_task::jsonString(std::string("x\x01y", 3));
  EXPECT_NE(out.find("\\u0001"), std::string::npos);
}

TEST(JsonValue, NonFiniteBecomesNullNotQuotedString)
{
  const double nan = std::nan("");
  EXPECT_EQ(agc_task::jsonNumber(nan), "null");
  EXPECT_EQ(agc_task::jsonNumber(HUGE_VAL), "null");
  EXPECT_EQ(agc_task::jsonNumber(-HUGE_VAL), "null");
}

TEST(JsonValue, DoubleRoundTripsAtSeventeenSignificantDigits)
{
  const double v = 1792912345.1234567;
  const std::string out = agc_task::jsonNumber(v);
  EXPECT_LT(std::fabs(std::stod(out) - v), 1e-6);
  // 不得退化成科学计数法之外的截断表示
  EXPECT_EQ(out.find('e'), std::string::npos);
  EXPECT_EQ(out.find('E'), std::string::npos);
}

TEST(JsonValue, IntegerValuedDoubleHasNoTrailingGarbage)
{
  EXPECT_EQ(agc_task::jsonNumber(0.0), "0");
  EXPECT_EQ(agc_task::jsonNumber(12.0), "12");
}

TEST(JsonValue, BoolIsLowerCaseBare)
{
  EXPECT_EQ(agc_task::jsonBool(true), "true");
  EXPECT_EQ(agc_task::jsonBool(false), "false");
}
