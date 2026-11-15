// planner_replay —— 离线回放器：把一份栅格喂给**生产规划器**，输出路径与诊断。
//
// 这是**可执行工具**，不是测试（与 `safety_replay` 同一定位）。它不订阅任何话题、
// 不发布任何话题，因此不构成命令者。
//
// 用途：在**真实地图**（`dense_map` / `yard`）的规划层上验证可达性与失败分类，
// 而不需要启动仿真。`tests/check_planner_real_map.py` 就是驱动它的核查器。
//
// 输入格式（纯文本，便于 Python 侧生成，避免引入 yaml/json 依赖）：
//
// ```text
// <resolution> <origin_x> <origin_y> <width> <height>
// <v00> <v01> ... <vN>            # width*height 个 int8，行主序
// <start_x> <start_y> <start_yaw>
// <goal_x> <goal_y>
// ```
//
// 输出（stdout，单行 key=value，便于脚本解析）：
//
// ```text
// success=1 failure=none outcome=optimized_path points=93 raw=93 length=41.2
// expanded=27629 time_ms=29400 clearance=1.23 curvature=0.42 signature=abcd
// poses=x0,y0,yaw0;x1,y1,yaw1;...
// ```

#include <cmath>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "agc_ground/planner_engine.hpp"
#include "agc_ground/planner_interface.hpp"
#include "agc_ground/planner_types.hpp"

namespace
{

int fail(const std::string & msg)
{
  std::fprintf(stderr, "planner_replay: %s\n", msg.c_str());
  return 2;
}

}  // namespace

int main(int argc, char ** argv)
{
  using namespace agc_ground::planner;

  if (argc < 2) {
    std::fprintf(
      stderr,
      "usage: %s <grid.txt> [--no-corridor] [--no-optimization] [--budget <s>]\n"
      "       [--smooth-window <m>] [--kappa-max <1/m>] [--w-acc-max <rad/s2>]\n", argv[0]);
    return 2;
  }

  PlannerParams params;
  for (int i = 2; i < argc; ++i) {
    const std::string a = argv[i];
    if (a == "--no-corridor") {
      params.corridor_enabled = false;
    } else if (a == "--no-optimization") {
      params.optimization_enabled = false;
    } else if (a == "--budget" && i + 1 < argc) {
      params.search_time_budget_s = std::atof(argv[++i]);
    } else if (a == "--smooth-window" && i + 1 < argc) {
      params.smoothing_window_m = std::atof(argv[++i]);
    } else if (a == "--kappa-max" && i + 1 < argc) {
      params.kappa_max = std::atof(argv[++i]);
    } else if (a == "--w-acc-max" && i + 1 < argc) {
      params.w_acc_max = std::atof(argv[++i]);
    }
  }

  std::ifstream f(argv[1]);
  if (!f) {return fail(std::string("cannot open ") + argv[1]);}

  GridView grid;
  int w = 0, h = 0;
  if (!(f >> grid.resolution >> grid.origin_x >> grid.origin_y >> w >> h)) {
    return fail("bad header");
  }
  grid.width = w;
  grid.height = h;
  grid.frame = "world";
  grid.stamp_s = 0.0;
  std::vector<int8_t> data(static_cast<size_t>(w) * static_cast<size_t>(h), 0);
  for (auto & c : data) {
    int v = 0;
    if (!(f >> v)) {return fail("bad grid data");}
    c = static_cast<int8_t>(v);
  }
  grid.cells = data.data();

  PlannerSnapshot snap;
  snap.grid = grid;
  if (!(f >> snap.start.x >> snap.start.y >> snap.start.yaw)) {
    return fail("bad start pose");
  }
  if (!(f >> snap.goal.x >> snap.goal.y)) {return fail("bad goal pose");}
  snap.goal.yaw = 0.0;
  snap.goal_valid = true;
  snap.authorized = true;
  snap.replan_reason = "replay";
  snap.params = params;

  auto planner = createPlanner();
  const PathResult r = planner->plan(snap);

  std::printf("success=%d failure=%s outcome=%s points=%zu raw=%d length=%.3f\n",
    r.success ? 1 : 0, toString(r.failure), toString(r.outcome),
    r.poses.size(), r.raw_path_points, r.path_length_m);
  std::printf("expanded=%d time_ms=%.1f clearance=%.3f curvature=%.4f signature=%s\n",
    r.expanded_nodes, r.planning_time_s * 1e3, r.clearance_min_m,
    r.max_curvature, r.map_signature.c_str());
  if (!r.detail.empty()) {std::printf("detail=%s\n", r.detail.c_str());}

  std::printf("poses=");
  for (size_t i = 0; i < r.poses.size(); ++i) {
    if (i > 0) {std::printf(";");}
    std::printf("%.4f,%.4f,%.4f", r.poses[i].x, r.poses[i].y, r.poses[i].yaw);
  }
  std::printf("\n");
  return r.success ? 0 : 1;
}
