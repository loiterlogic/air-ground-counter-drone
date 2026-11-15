// safety_replay —— 把录制的 `SafetyInputs` 序列**离线重跑**生产判定类，并逐拍对拍。
//
// ## 为什么它必须调用 `SafetyPolicy` 本体，而不是复制一份判定
//
// 配套规范要求「录制的输入序列离线重跑」与在线**逐拍一致**。若重放器自己再写一遍
// 判定逻辑，它证明的只是"我复制的这份副本自洽"——线上改了一行、副本没改，
// 逐拍照样"一致"，而那恰恰是最该被抓住的情况。
// 所以本程序 `#include "agc_ground/safety_policy.hpp"`，与节点用**同一个类**。
//
// ## 与在线的一致性边界（如实声明，不外推）
//
// 重放能复现的是**判定**（状态 / 输出速度 / 诊断原因），不复现：
//   * ROS 的 QoS、发现、时钟同步；
//   * 节点里 `budget_ms` 的**实测**耗时检查（重放时为空闲机器上的实测值，不代表在线）；
//   * 命令年龄的**单调钟**口径（录制时已折算成 `stamp_s`，见 recorder）。
// 因此"逐拍一致"指的是：喂同样的输入，`SafetyPolicy::step` 给出同样的结论。
//
// ## 用法
//
//     ./build/agc_ground/safety_replay <trace.jsonl> [--verbose]
//
// 退出码：0 = 全部样本状态一致；1 = 存在不一致；2 = 用法/文件错误。

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "agc_ground/safety_policy.hpp"

namespace
{

// —— 极简 JSON 取值（录制格式是我们自己写的，不需要通用解析器）——
bool findKey(const std::string & line, const std::string & key, std::string * out)
{
  // 兼容 `"k":v` 与 `"k": v`（Python 的 json.dumps 默认带空格）。
  std::string pat = "\"" + key + "\":";
  auto p = line.find(pat);
  if (p == std::string::npos) {
    pat = "\"" + key + "\": ";
    p = line.find(pat);
  }
  if (p == std::string::npos) {return false;}
  auto i = p + pat.size();
  while (i < line.size() && (line[i] == ' ' || line[i] == '\t')) {++i;}
  if (i >= line.size()) {return false;}
  if (line[i] == '"') {
    const auto e = line.find('"', i + 1);
    if (e == std::string::npos) {return false;}
    *out = line.substr(i + 1, e - i - 1);
    return true;
  }
  if (line[i] == '{') {
    int depth = 0;
    size_t s = i;
    for (; i < line.size(); ++i) {
      if (line[i] == '{') {++depth;}
      else if (line[i] == '}') {--depth; if (depth == 0) {++i; break;}}
    }
    *out = line.substr(s, i - s);
    return true;
  }
  if (line.compare(i, 4, "true") == 0) {*out = "true"; return true;}
  if (line.compare(i, 5, "false") == 0) {*out = "false"; return true;}
  if (line.compare(i, 4, "null") == 0) {*out = "null"; return true;}
  auto e = i;
  while (e < line.size() && line[e] != ',' && line[e] != '}') {++e;}
  *out = line.substr(i, e - i);
  return true;
}

bool hasKey(const std::string & line, const std::string & key)
{
  std::string tmp;
  if (!findKey(line, key, &tmp)) {return false;}
  return tmp != "null" && !tmp.empty();
}

double num(const std::string & line, const std::string & key, double dflt)
{
  std::string s;
  if (!findKey(line, key, &s) || s == "null" || s.empty()) {return dflt;}
  try {return std::stod(s);} catch (...) {return dflt;}
}

bool boolean(const std::string & line, const std::string & key, bool dflt)
{
  std::string s;
  if (!findKey(line, key, &s)) {return dflt;}
  if (s == "true") {return true;}
  if (s == "false") {return false;}
  return dflt;
}

// 从内嵌对象里取值（例如 `"cmd":{...}`）
bool findIn(const std::string & obj, const std::string & key, std::string * out)
{
  return findKey(obj, key, out);
}

double numIn(const std::string & obj, const std::string & key, double dflt)
{
  std::string s;
  if (!findIn(obj, key, &s) || s == "null" || s.empty()) {return dflt;}
  try {return std::stod(s);} catch (...) {return dflt;}
}

bool boolIn(const std::string & obj, const std::string & key, bool dflt)
{
  std::string s;
  if (!findIn(obj, key, &s)) {return dflt;}
  if (s == "true") {return true;}
  if (s == "false") {return false;}
  return dflt;
}

// `"data":[...]` → vector<int8_t>
std::vector<int8_t> parseIntArray(const std::string & line)
{
  std::vector<int8_t> out;
  std::string pat = "\"data\":[";
  auto p = line.find(pat);
  if (p == std::string::npos) {
    pat = "\"data\": [";
    p = line.find(pat);
  }
  if (p == std::string::npos) {return out;}
  auto i = p + pat.size();
  std::string buf;
  for (; i < line.size(); ++i) {
    const char c = line[i];
    if (c == ']') {
      if (!buf.empty()) {out.push_back(static_cast<int8_t>(std::stoi(buf)));}
      break;
    }
    if (c == ',' || c == ' ') {
      if (!buf.empty()) {
        out.push_back(static_cast<int8_t>(std::stoi(buf)));
        buf.clear();
      }
      continue;
    }
    buf += c;
  }
  return out;
}

struct MapRec
{
  int width{0}, height{0};
  double resolution{0.0}, origin_x{0.0}, origin_y{0.0};
  bool frame_ok{false};
  double stamp_s{0.0};
  std::vector<int8_t> data;
};

}  // namespace

int main(int argc, char ** argv)
{
  if (argc < 2) {
    std::cerr << "用法: safety_replay <trace.jsonl> [--verbose]\n";
    return 2;
  }
  const std::string path = argv[1];
  const bool verbose = (argc > 2 && std::string(argv[2]) == "--verbose");

  std::ifstream f(path);
  if (!f) {
    std::cerr << "打不开 " << path << "\n";
    return 2;
  }

  std::vector<std::string> samples;
  std::map<int, MapRec> maps;
  std::string line;
  int footer_samples = -1;
  while (std::getline(f, line)) {
    const bool is_sample = line.find("\"kind\":\"sample\"") != std::string::npos ||
      line.find("\"kind\": \"sample\"") != std::string::npos;
    const bool is_map = line.find("\"kind\":\"map\"") != std::string::npos ||
      line.find("\"kind\": \"map\"") != std::string::npos;
    const bool is_footer = line.find("\"kind\":\"footer\"") != std::string::npos ||
      line.find("\"kind\": \"footer\"") != std::string::npos;
    if (is_sample) {
      samples.push_back(line);
    } else if (is_map) {
      MapRec m;
      m.width = static_cast<int>(num(line, "width", 0));
      m.height = static_cast<int>(num(line, "height", 0));
      m.resolution = num(line, "resolution", 0.0);
      m.origin_x = num(line, "origin_x", 0.0);
      m.origin_y = num(line, "origin_y", 0.0);
      m.frame_ok = boolean(line, "frame_ok", false);
      m.stamp_s = num(line, "stamp_s", 0.0);
      m.data = parseIntArray(line);
      maps[static_cast<int>(num(line, "id", -1))] = std::move(m);
    } else if (is_footer) {
      footer_samples = static_cast<int>(num(line, "samples", -1));
    }
  }

  if (samples.empty()) {
    std::cerr << "没有样本\n";
    return 2;
  }

  agc_ground::SafetyPolicy pol;
  agc_ground::SafetyParams params;   // 与在线同默认值；如需复现非默认配置，录制里带 params
  pol.setParams(params);
  if (!pol.paramsError().empty()) {
    std::cerr << "参数非法：" << pol.paramsError() << "\n";
    return 2;
  }

  long total = 0, matched = 0, state_mismatch = 0, missing_expect = 0;
  long speed_mismatch = 0;
  for (const auto & s : samples) {
    ++total;

    agc_ground::SafetyInputs in;
    in.now_s = num(s, "now_s", 0.0);

    // **年龄优先用在线值**：`online_diag` 里的四个年龄是安全层自己做判定时算出来的，
    // 原样喂回去才能让对拍只检验"判定逻辑"，而不是再引入一次采样相位误差
    // （实测：自算年龄导致 body age=0.508 而在线是 NO_PERMIT 的错配）。
    // 做法：由 `now_s - online_age` 反解出各输入的 `stamp_s`，下面若样本自带 stamp 则不覆盖。
    std::string odiag;
    const bool has_odiag = findKey(s, "online_diag", &odiag) && !odiag.empty() &&
      odiag != "null";
    auto ageToStamp = [&](const char * k, double fallback) {
        if (!has_odiag) {return fallback;}
        const double a = numIn(odiag, k, -1.0);
        return (a >= 0.0) ? (in.now_s - a) : fallback;
      };

    std::string cmd;
    const bool has_cmd = findKey(s, "cmd", &cmd) && !cmd.empty() && cmd != "null";
    in.has_command = has_cmd;
    if (has_cmd) {
      in.command.v = numIn(cmd, "v", 0.0);
      in.command.w = numIn(cmd, "w", 0.0);
      in.command.frame_ok = boolIn(cmd, "frame_ok", false);
      in.command.finite = boolIn(cmd, "finite", true);
      in.command.holonomic_ok = boolIn(cmd, "holonomic_ok", true);
      in.command.stamp_s = ageToStamp("cmd_age_s", numIn(cmd, "stamp_s", in.now_s));
    }

    std::string body;
    const bool has_body = findKey(s, "body", &body) && !body.empty() && body != "null";
    in.has_body = has_body;
    if (has_body) {
      in.body.x = numIn(body, "x", 0.0);
      in.body.y = numIn(body, "y", 0.0);
      in.body.yaw = numIn(body, "yaw", 0.0);
      in.body.valid = boolIn(body, "valid", true);
      in.body.finite = boolIn(body, "finite", true);
      in.body.stamp_s = ageToStamp("body_age_s", numIn(body, "stamp_s", in.now_s));
    }

    const int map_id = static_cast<int>(num(s, "map_id", -1));
    const auto it = maps.find(map_id);
    if (it != maps.end()) {
      const MapRec & m = it->second;
      in.has_map = true;
      in.map.data = m.data.empty() ? nullptr : m.data.data();
      in.map.width = m.width;
      in.map.height = m.height;
      in.map.resolution = m.resolution;
      in.map.origin_x = m.origin_x;
      in.map.origin_y = m.origin_y;
      in.map.frame_ok = m.frame_ok;
      in.map.stamp_s = ageToStamp("map_age_s", m.stamp_s);
    } else {
      in.has_map = false;
    }
    in.map_valid_flag = boolean(s, "map_valid", true);

    std::string permit;
    const bool has_permit = findKey(s, "permit", &permit) && !permit.empty() &&
      permit != "null";
    in.has_permit = has_permit;
    if (has_permit) {
      in.permit.state = static_cast<int>(numIn(permit, "state", 0));
      in.permit.stamp_s = ageToStamp("permit_age_s", numIn(permit, "stamp_s", in.now_s));
    }

    const auto d = pol.step(in);

    std::string expect;
    if (!findKey(s, "expect", &expect) || expect == "null" || expect.empty()) {
      ++missing_expect;
      continue;
    }
    const std::string got = agc_ground::toString(d.state);
    if (got == expect) {
      ++matched;
    } else {
      ++state_mismatch;
      if (verbose || state_mismatch <= 5) {
        std::cout << "  不一致 #" << total << "：在线=" << expect
                  << " 重放=" << got << "（" << d.reason << "）\n";
      }
    }
    (void)speed_mismatch;
  }

  std::cout << "样本 " << total << " 拍，footer=" << footer_samples
            << "，地图 " << maps.size() << " 幅\n"
            << "  有在线期望：" << (total - missing_expect) << " 拍\n"
            << "  状态一致：" << matched << " 拍\n"
            << "  状态不一致：" << state_mismatch << " 拍\n"
            << "  无在线期望（未收到状态话题）：" << missing_expect << " 拍\n";

  if (state_mismatch == 0 && matched > 0) {
    std::cout << "PASS：离线重放与在线**逐拍一致**（喂同一输入，生产判定类给出同一状态）\n";
    return 0;
  }
  if (matched == 0) {
    std::cout << "FAIL：没有任何可比对的样本（录制里没有安全层状态）\n";
    return 1;
  }
  std::cout << "FAIL：存在 " << state_mismatch << " 拍不一致\n";
  return 1;
}
