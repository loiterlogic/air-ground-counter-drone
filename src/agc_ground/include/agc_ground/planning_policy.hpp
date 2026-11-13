// planning_policy —— 未知空间规划策略的**纯逻辑**判定（不 include ROS 消息包）
//
// 按《测试分层与可测性》：判定逻辑必须能脱离 ROS 单测。
//
// **为什么需要它**（2026-11-08 用户裁定 Q9/Q11/Q21）：
// 改造前 `costmap.yaml` 写的是 `track_unknown_space: true`（未知→255），
// 看起来是"未知区不可走"；但 Navfn 的 `allow_unknown` **默认 true** —— 两者互相抵消，
// 实际行为是"未知区随便穿"。更糟的是当时的地图**事实上没有 free 空间**
// （decayMiss 守卫让未知格永不衰减），于是"全图 unknown、规划器随便走"，
// 语义完全落空且无法解释。
//
// **本文件的口径**：不依赖任何 Navfn 私有参数（项目正与 Nav2 解绑，
// 见 ADR-0003）。"未知不可走"由我们自己的判据表达：
// 规划前检查起点/终点所在格是否为**已知自由**，不是就明确拒绝并给出理由。
//
// 为什么检查端点而不是整条路径：整条路径的可通行性由规划器在栅格上保证；
// 我们额外要守的是"**不要从没看过的地方起步、也不要奔着没看过的地方去**"——
// 那两类失败在规划器里表现为"静默穿行"（allow_unknown=true）或"莫名失败"（false），
// 都不如显式理由可诊断。

#ifndef AGC_GROUND__PLANNING_POLICY_HPP_
#define AGC_GROUND__PLANNING_POLICY_HPP_

namespace agc_ground
{

// 栅格格的语义分类（对齐 nav_msgs/OccupancyGrid 的 data 语义）。
//
// 注意 1..99 的**过渡带**：批次 1 起 `/agc/map` 输出 0–100 的占据概率×100
// （不再是三态）。过渡带表示"有证据但不足以判定"——按**未知**处理是安全方向：
// 放行它等于让规划器穿过证据不足的区域。
enum class CellClass
{
  kFree,      // 0：已知自由
  kUnknown,   // -1 或 1..99：未知 / 证据不足
  kOccupied,  // 100：已知占据
};

// 栅格值 → 语义分类。越界值按未知处理（不放行）。
inline CellClass classifyCell(int value)
{
  if (value == 0) {return CellClass::kFree;}          // 0 = 已知自由（OccupancyGrid 约定）
  if (value < 0) {return CellClass::kUnknown;}        // -1 与任何负值 = 未知
  if (value >= 100) {return CellClass::kOccupied;}    // 100 与任何溢出值
  return CellClass::kUnknown;                         // 1..99 过渡带 = 证据不足
}

enum class PlanRejection
{
  kNone,            // 可以规划
  kStartNotFree,    // 起点在未知区（"从没看过的地方起步"）
  kStartOccupied,   // 起点在占据格（车被卡住 / 地图与真值不一致）
  kGoalNotFree,     // 终点在未知区（Q12 的边缘直连要处理的场景）
  kGoalOccupied,    // 终点在占据格（目标点落在障碍里）
};

// 端点分类 → 拒绝理由。起点问题优先于终点问题（先能出发才谈到达）。
inline PlanRejection planRejectionReason(CellClass start, CellClass goal)
{
  if (start == CellClass::kOccupied) {return PlanRejection::kStartOccupied;}
  if (start == CellClass::kUnknown) {return PlanRejection::kStartNotFree;}
  if (goal == CellClass::kOccupied) {return PlanRejection::kGoalOccupied;}
  if (goal == CellClass::kUnknown) {return PlanRejection::kGoalNotFree;}
  return PlanRejection::kNone;
}

// 可读字符串（进日志 / 诊断话题；不用裸枚举，避免"失败但不知道为什么"）。
inline const char * toString(PlanRejection r)
{
  switch (r) {
    case PlanRejection::kNone: return "none";
    case PlanRejection::kStartNotFree: return "start_not_free";
    case PlanRejection::kStartOccupied: return "start_occupied";
    case PlanRejection::kGoalNotFree: return "goal_not_free";
    case PlanRejection::kGoalOccupied: return "goal_occupied";
  }
  return "unknown";
}

}  // namespace agc_ground

#endif  // AGC_GROUND__PLANNING_POLICY_HPP_

namespace agc_ground
{

// ---------------------------------------------------------------------------------
// 边缘直连兜底（2026-11-08 用户裁定 Q12）
// ---------------------------------------------------------------------------------
//
// **用户原话**："如果没覆盖到目标点就从已知区域边缘直接连一条直线到目标点，
// 这一步本来就是生成粗糙路径"。
//
// 背景：地图覆盖半径 30.5 m（Q22 扩覆盖后），但 yard 有 100×100 m，UAV 只在目标
// standoff 环附近。车到 goal 的 27.7 m 里仍可能有 2 m 落在覆盖外（实测最优方向
// 92.8% 覆盖）。此时"未知不可走"会让整条路径规划不出来 —— 而这一步只是**粗路径**，
// 不是最终轨迹，所以"从已知区边缘直连过去"是可接受且必要的。
//
// **判据（三条，缺一不可）**：
//   1. 直连段不得穿过**已知占据**格（否则这条粗糙路径是错的，不是粗糙）；
//   2. 直连段的两端必须**都在已知自由区**（起点侧是边缘点，终点侧要求 goal 本身已知）；
//   3. 直连段在 costmap 里按**可通行**处理（若标成不可通行，规划器根本走不出来，
//      兜底就失效了）。
//
// 本文件只做**纯几何**判定（第 1 条），第 2/3 条由调用方（ground_baseline）落实。

// 射线-栅格遍历时"这一格是否挡住直连"。返回 true 表示被挡。
// 只有**已知占据**算挡；未知不挡（未知正是要穿过去的部分）、自由不挡。
inline bool blocksDirectLink(int cell_value)
{
  return cell_value >= 100;
}

// 端点是否允许作为直连的两端：必须是已知自由（0）。
// 未知端不允许 —— 从没看过的地方连出去，等于凭空造一条路。
inline bool canAnchorDirectLink(int cell_value)
{
  return cell_value == 0;
}

}  // namespace agc_ground
