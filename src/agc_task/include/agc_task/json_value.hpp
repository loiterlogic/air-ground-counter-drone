// json_value.hpp —— JSON **标量值**的序列化（无 ROS 依赖、可单测）
//
// 为什么单独成文件：`run_logger` 的 summary / mission_fco 证据全靠手工拼 JSON，
// 原先三个 `static` 帮助函数埋在 1674 行的节点类里，无法在不启 ROS 的情况下验证。
// 这里只做"把一个值写成合法 JSON 标量"这一件事：
// * 字符串按 RFC 8259 转义（含控制字符）——原实现只转义 `\` 与 `"`，
//   遇到换行会写出跨行字符串，JSON 解析器直接报错；
// * 非有限浮点写 `null`（JSON 没有 NaN/Inf），不加引号；
// * 浮点用 17 位有效数字（double 的最小往返精度），与 `epoch_seconds.hpp` 同口径。

#pragma once

#include <cmath>
#include <iomanip>
#include <sstream>
#include <string>

namespace agc_task
{

inline std::string jsonString(const std::string & s)
{
  std::string out;
  out.reserve(s.size() + 2);
  out += '"';
  for (char c : s) {
    switch (c) {
      case '"': out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\b': out += "\\b"; break;
      case '\f': out += "\\f"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (static_cast<unsigned char>(c) < 0x20) {
          // 其余控制字符走 \u00XX（JSON 不接受裸控制字符）
          char buf[8];
          std::snprintf(buf, sizeof(buf), "\\u%04x", static_cast<unsigned>(c) & 0xFFu);
          out += buf;
        } else {
          out += c;
        }
    }
  }
  out += '"';
  return out;
}

inline std::string jsonNumber(double v)
{
  if (!std::isfinite(v)) {
    return "null";
  }
  std::ostringstream os;
  os << std::setprecision(17) << v;
  return os.str();
}

inline std::string jsonBool(bool v)
{
  return v ? "true" : "false";
}

}  // namespace agc_task
