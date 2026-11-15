// planner_interface —— 规划器抽象（纯虚基类 + 固定工厂，**不用 pluginlib**）
//
// ## 为什么抽接口
//
// 用户 2026-11-14 裁定：以后还会有别的规划算法，所以要留可替换接口。
//
// ## 为什么**不用** pluginlib（尽管 `agc_control` 是那样做的）
//
// `agc_control` 用 pluginlib 是因为它**真的**要在运行期按名字加载不同实现
// （LQR 控制器、多种轨迹生成器），且两者都有当前消费者。
//
// 而本规划器现在**只有一个实现**。pluginlib 的存在理由就是「按名字选实现」——
// 只有一个实现时，它是一个未被使用的选择机制，而
// [路线分支治理 2.1](../../../docs/conventions/路线分支治理.md#rule) 明确把
// 「同一功能位置 ≥2 个实现，由参数/开关选择」定义为路线分支，2.2 的四项准入里
// ②「两条路径都有当前消费者」与 ④「明确退役条件」现在都满足不了。
//
// 所以这里只做**接口抽象**（零开关、零注册表、零第二实现），工厂是一个**固定**函数。
// 将来接第二个算法时，才需要另立决策去定义「怎么选」。
//
// ## 接口为什么算法无关
//
// `plan()` 的入参是 `PlannerSnapshot`（地图视图 + 车位 + 目标 + 参数），
// 出参是 `PathResult`。两者都不含 Hybrid A* 的痕迹 —— 换一个算法（RRT*、D* Lite、
// 甚至外部的规划服务）也能实现这个接口。

#ifndef AGC_GROUND__PLANNER_INTERFACE_HPP_
#define AGC_GROUND__PLANNER_INTERFACE_HPP_

#include <memory>
#include <string>

#include "agc_ground/occupancy_grid_view.hpp"
#include "agc_ground/planner_types.hpp"

namespace agc_ground
{
namespace planner
{

// 一拍规划的全部输入（**算法无关**）。
//
// `grid.cells` 的生命周期由调用方保证（单线程节点里就是本拍缓存的地图数据）。
struct PlannerSnapshot
{
  GridView grid;
  Pose2D start;
  Pose2D goal;
  bool goal_valid{false};
  bool authorized{false};
  PlannerParams params;
  // 当前车速（m/s，从 odom 来）。时间参数化的**起点速度**，不是路径上限。
  // 缺省 0 = 从静止起步（保守方向）。
  double start_speed{0.0};
  std::string replan_reason;   // 首规划 / 目标变 / 地图变 / 超时 / 周期
};

// 规划器抽象。
class IPlanner
{
public:
  using Ptr = std::unique_ptr<IPlanner>;

  virtual ~IPlanner() = default;

  // 算法名（进诊断，用于区分「本 run 用了哪个算法」——这是可观测性，不是开关）。
  virtual std::string name() const = 0;

  // 跑一次完整规划（四阶段）。失败必须返回显式 `PlanFailure`，不得返回「空成功」。
  virtual PathResult plan(const PlannerSnapshot & snapshot) = 0;
};

// 工厂：返回**当前唯一**的实现。
//
// 注意它是**无参**函数，不接受算法名 —— 有参数就是「按名字选实现」，就是路线分支。
// 将来要支持多算法时，那是一个需要用户明确允许 + 退役条件的独立决策。
IPlanner::Ptr createPlanner();

}  // namespace planner
}  // namespace agc_ground

#endif  // AGC_GROUND__PLANNER_INTERFACE_HPP_
