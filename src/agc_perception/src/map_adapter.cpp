// map_adapter —— 场景地图适配器（修订 2026-10-15）
//
// 发布 /agc/map（nav_msgs/OccupancyGrid，world 系，latched）：
// 0 = free / 100 = occupied / 1–99 = 量化占据概率 / -1 = unknown（ADR-0035 (c)）。
// 另发布 /agc/map/version_hash（std_msgs/String，latched）、/agc/map/update_seq（std_msgs/UInt64，latched）
// 与 /agc/map/valid（Bool，latched）。
//
// 地图内容身份与单调更新序号（评审风险 ；见 ADR-0007）：
// * **内容身份 hash**（agc/map/version_hash 的内容）= FNV-1a(frame_id, 障碍源版本, 场景版本,
// resolution, width, height, origin_x, origin_y, data) —— **不只** data 字节串：相同 data 在
// 不同几何 / 源版本下身份**不同**（消除「同 data 可代表不同地图」）。
// * **单调更新序号** update_seq_（agc/map/update_seq）：初始 0，**仅**在实质重建（栅格内容或身份
// 改变）时 +1；与内容 hash **分别**可查询（诊断，非 ABI）。
// * **等价判定**按**真实 raster**：把候选有效障碍集合**实际栅格化**，与当前栅格**逐字节比较**；
// 相等即内容等价（不重建、不发布、序号不变），不同即采用 + 序号递增。真实 raster 相等是
// **精确等价**、天然**不欠包**（边缘跨格必被捕获），**弃用**原 `sameObstacles` 的分辨率分箱 +
// 固定 0.1 yaw 容差（不保证边缘跨格后栅格相同）。
//
// 障碍内容（感知地图模式）：/agc/map 内容**完全来自** `/agc/obstacle_footprints`
// 的足迹点经 log-odds 累积的证据（ADR-0035 (b)），不加载静态先验，不设两源回退分支。
// * 静态先验与动态轨集合（`static_prior_` / `live_` / `unknown_idx_`）已**整体退役**：
//   它们在改成 log-odds 累积后不再决定任何栅格内容，只余诊断计数。
// * 证据单位 = **每格每帧一次**（同一格在同一帧内最多一次 hit、一次 miss）：
//   否则证据强度取决于像素采样密度而不是时序观测，边缘格会在门限两侧反复翻转。
// * 空数组 = 本拍无新观测（契约），仍刷新源时效。
//
// /agc/map/valid = geometry_ok_ && knowledge_current()：
// 只有「收到过 /agc/obstacles 且源静默 ≤ source_max_age_s_」才为 true；
// 知识不新鲜时照常发布当前栅格（可能开洞），只是 valid=false（不恒 true、不静默陈旧）。
//
// 分层语义（ADR-0003 落点）：本节点承载 costmap 的 **static / obstacle** 语义（数据契约）；
// **inflation / voxel** 层与 costmap 组装归 ****。 **不引入** nav2_map_server /
// nav2_costmap_2d 运行时进程（仅对齐其数据/格式约定）。相同障碍去重，避免融合噪声引发重规划风暴。

#include <yaml-cpp/yaml.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <deque>
#include <limits>
#include <cstdint>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/occupancy_grid.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/u_int64.hpp>

#include <sensor_msgs/msg/camera_info.hpp>

#include <agc_msgs/msg/obstacle_track_array.hpp>
#include <agc_msgs/msg/obstacle_footprint_array.hpp>
#include <agc_msgs/msg/perception_cell_meta.hpp>

#include "agc_perception/camera_geometry.hpp"
#include "agc_perception/log_odds_grid.hpp"
#include "agc_perception/footprint_geometry.hpp"
#include "agc_perception/multi_res_grid.hpp"
#include "agc_perception/point_uncertainty.hpp"
#include "agc_perception/obstacle_instances.hpp"
#include "agc_perception/inflation_field.hpp"

namespace
{

// FNV-1a 64 位字节哈希（对 int8_t 字节序列），输出 16 进制串。
// 保留为**底层字节哈希工具**——内容身份 hash 由它 + 几何/源版本元数据组装后喂入（见
// contentIdentityHash），故本函数仍被复用。
std::string hashBytes(const std::vector<int8_t> & data)
{
  uint64_t h = 1469598103934665603ULL;
  for (int8_t v : data) {
    h ^= static_cast<uint8_t>(v);
    h *= 1099511628211ULL;
  }
  char buf[17];
  std::snprintf(buf, sizeof(buf), "%016llx", static_cast<unsigned long long>(h));
  return std::string(buf);
}

}  // namespace

class MapAdapter : public rclcpp::Node
{
public:
  MapAdapter()
  : Node("map_adapter")
  {
    world_frame_ = declare_parameter<std::string>("world_frame", "world");
    map_file_ = declare_parameter<std::string>("map_file", "");
    // `obstacles_file` / `dynamic_max_age_s` 已随静态先验与动态轨集合退役（ADR-0035 (b)）：
    // 栅格内容只来自累积层，这两个参数不再有消费者。launch 仍可传（向后兼容），
    // 但节点**不声明**它们 —— 未声明的参数被 ROS 忽略，不会静默改变行为。
    obstacle_source_ = declare_parameter<std::string>("obstacles_source", "config");
    rate_hz_ = declare_parameter<double>("rate_hz", 2.0);
    map_topic_ = declare_parameter<std::string>("map_topic", "/agc/map");
    evidence_topic_ = declare_parameter<std::string>(
      "evidence_map_topic", "/agc/map/evidence");
    cell_meta_topic_ = declare_parameter<std::string>(
      "cell_meta_topic", "/agc/map/cell_meta");
    // 场景 / 源版本（折入内容身份 hash）；单调更新序号诊断话题
    scenario_version_ = declare_parameter<std::string>("scenario_version", "");
    update_seq_topic_ = declare_parameter<std::string>("update_seq_topic", "/agc/map/update_seq");
    // /agc/obstacles 源静默期限（s）：`/agc/map/valid` 的时效判据
    source_max_age_s_ = declare_parameter<double>("source_max_age_s", 1.0);

    auto latched = rclcpp::QoS(rclcpp::KeepLast(1)).transient_local().reliable();
    pub_ = create_publisher<nav_msgs::msg::OccupancyGrid>(map_topic_, latched);
    hash_pub_ = create_publisher<std_msgs::msg::String>("/agc/map/version_hash", latched);
    seq_pub_ = create_publisher<std_msgs::msg::UInt64>(update_seq_topic_, latched);
    valid_pub_ = create_publisher<std_msgs::msg::Bool>("/agc/map/valid", latched);
    // 证据层地图（ADR-0042）：与 `/agc/map`（规划层）**并行**发布。
    //
    // **为什么必须发出来**：改造前证据层（0.25 m）只存在于节点内部，外部能看到的
    // 只有 0.5 m 的派生结果 —— 于是 temp.md 要的"0.1 m 评价地图"无从做起，
    // 评价器只能在规划层上量几何精度，而那正是"拿膨胀图评价感知"的错误口径。
    // 证据层是**几何重建的权威表达**，评价必须在它上面做。
    //
    // 语义与 `/agc/map` **不同**：这里是裸 log-odds 四态（-1/0/1–99/100），
    // **不含**风险分档、**不含**实例并集、**不含**规划层 max-pool。
    // 换句话说：`/agc/map` 回答"能不能走"，`/agc/map/evidence` 回答"看到多少"。
    evidence_pub_ = create_publisher<nav_msgs::msg::OccupancyGrid>(
      evidence_topic_, latched);
    // 逐格元数据（ADR-0042）：把 `OccupancyGrid.data` 一个 int8 装不下的
    // 五个量（占据比例 / 置信度 / 最近观测 / 来源实例 / 完整可见）分开表达。
    // 这是 temp.md 方向一与方向四 A+B 的落地。
    cell_meta_pub_ = create_publisher<agc_msgs::msg::PerceptionCellMeta>(
      cell_meta_topic_, latched);

    // ---- 多分辨率：证据层 / 规划层（ADR-0040）----
    // **为什么要分两层**：`dense_map` 的障碍是 box 0.6–1.2 m、cylinder r 0.25–0.40 m，
    // 而 `/agc/map` 只有 0.5 m 格 ⇒ 一个小圆柱只覆盖 1–2 格，边界点稍微偏移就让
    // 相邻格被占据。面积比已从 1.801 降到 1.230，误覆盖率却仍是 0.668 —— 剩余误差
    // 不是"地图整体膨胀"，而是**一个格只能回答 0 或 100，回答不了"只占 31%"**。
    //
    // 现在 0.5 m 只做**规划消费格式**：证据累积在 `perception_resolution`（默认 0.25 m），
    // 规划层由它**派生**（max-pool + 保守四态合并）。`/agc/map` 的契约（话题、消息、
    // 几何、四态语义）**完全不变**，下游无需改动。
    //
    // **为什么取 0.25 而不是 0.20**：`0.5/0.2 = 2.5` 是非整数倍，两个参照实现
    // （Nav2 的 `downsampling_factor` 是 unsigned int、RACER 的 `resolution *= 0.5`）
    // 都只能表达整数倍；非整数倍会引入随坐标漂移的半格错位。0.25 让 2×2 子格与
    // 0.5 m 格**格点严格对齐**，聚合不需要重采样。
    perception_resolution_ = declare_parameter<double>("perception_resolution", 0.25);
    // 规划层安全膨胀（**米**，不是格）。与 `agc_ground/config/costmap.yaml` 的
    // `robot_radius: 0.6` / `inflation_radius: 1.0` 同值 —— 两个消费者对"车多大、
    // 让多远"必须同口径，否则规划与安全层的净空不一致。
    // ---- 障碍实例层（ADR-0041，temp.md 方向三）----
    // 实例层与逐点累积**取并集**：逐点累积能跨帧合并被画幅切碎的大建筑，
    // 实例层能稳定 1–3 格宽的小障碍。两者各补对方拿不到的那一半。
    instances_enabled_ = declare_parameter<bool>("instances_enabled", true);
    instance_confirm_hits_ = declare_parameter<int>("instance_confirm_hits", 2);
    instance_expire_misses_ = declare_parameter<int>("instance_expire_misses", 3);
    instance_associate_gate_m_ = declare_parameter<double>("instance_associate_gate_m", 1.5);
    // 轨迹历史上限（ADR-0042）：0 = 不记录（退回"只存当前几何"的旧行为）。
    instance_track_points_ = declare_parameter<int>("instance_track_points", 50);
    // 实例参数**必须真正生效**（2026-11-11 实测 bug）：改造前这三个参数只被
    // `declare_parameter` 读了、从未传给 `InstanceTracker` —— 于是 `InstanceTracker`
    // 一直用它自己的默认值（恰好与配置默认值相同），改配置**毫无效果**且无任何提示。
    // 这类"参数存在即完成"的假象比缺参数更危险：它让调参变成自我安慰。
    // 现在在参数声明之后**立即**构造并注入，两边不可能再分叉。
    {
      agc_perception::InstanceParams ip;
      ip.confirm_hits = std::max(1, instance_confirm_hits_);
      ip.expire_misses = std::max(0, instance_expire_misses_);
      ip.associate_gate_m = std::max(0.0, instance_associate_gate_m_);
      ip.max_track_points = static_cast<size_t>(std::max(0, instance_track_points_));
      instances_.setParams(ip);
    }
    // ---- 规划风险图（ADR-0041，temp.md 方向四 C）----
    // `/agc/map` 输出风险分档而不是裸占据：几何占据 + 米制膨胀共同决定通行性。
    // 关掉它（false）就退回 ADR-0040 的裸占据输出 —— 仅用于对照，主链默认开启。
    // 逐点不确定度门控（ADR-0042）：σ 超过 ratio×格宽的点不进 hit 证据。
    // 0 = 关闭（退回"所有点一视同仁"的旧口径，仅用于对照）。
    sigma_reject_ratio_ = declare_parameter<double>("sigma_reject_ratio", 0.5);
    risk_enabled_ = declare_parameter<bool>("risk_enabled", true);
    risk_cost_scaling_ = declare_parameter<double>("risk_cost_scaling", 3.0);
    inflation_robot_radius_m_ = declare_parameter<double>("inflation_robot_radius_m", 0.6);
    inflation_radius_m_ = declare_parameter<double>("inflation_radius_m", 1.0);
    // 启动期拒绝"膨胀半径 < 车半径"：那会让 `kInflated` 带为空，车半径内只剩
    // `kInscribed`（依赖判定顺序才安全），配置意图与实际行为脱节。
    if (inflation_radius_m_ < inflation_robot_radius_m_) {
      throw std::runtime_error(
        "map_adapter 非法配置：inflation_radius_m (" + std::to_string(inflation_radius_m_) +
        ") < inflation_robot_radius_m (" + std::to_string(inflation_robot_radius_m_) +
        ")；膨胀外半径必须不小于车半径，否则安全膨胀带为空。");
    }

    loadMapGeometry();
    // 感知地图链：/agc/map 内容**完全来自** `/agc/obstacles` 的感知观测，不再加载静态先验。
    // world_geometry.yaml 只提供 resolution / size / origin，不产地图内容。
    // 不设「感知失效回退静态先验」的两源分支；丢包 / 遮挡时地图开洞为已登记边界。
    // （见 ADR-0009）：地图几何 / 角度**启动期合法性校验**，非法即**拒绝启动**。
    validateStartupOrThrow();
    // **2026-11-08（批次 3）**：碎片合并门 `merge_gate_m` 已随框层退役。
    // 同帧碎片在栅格层天然合并（落在同一个连通证据里），不需要物体级打包；
    // 留一个没有消费者的参数等于留一个"顺手接回来"的入口。
    // ---- log-odds 增量累积参数（2026-11-08）----
    // p_hit=0.70 / p_miss=0.35 沿用 ego-planner 的工程经验（plan_env/src/grid_map.cpp）。
    // occupied 门限 0.60：从 p_init=0.30 起步，需约 2 次连续命中才跨过 ⇒ 单帧毛刺画不出来。
    log_odds_p_hit_ = declare_parameter<double>("log_odds_p_hit", 0.70);
    log_odds_p_miss_ = declare_parameter<double>("log_odds_p_miss", 0.25);
    log_odds_occ_thr_ = declare_parameter<double>("log_odds_occupied_threshold", 0.60);
    // 全局时间衰减（与 p_miss 分开，理由见 LogOddsParams::p_decay 注释）。
    log_odds_p_decay_ = declare_parameter<double>("log_odds_p_decay", 0.48);
    // 发布值量化步长（2026-11-09）：中间概率按此步长量化后再比较/发布。
    // 取 5：一格从 48 变 47 不再触发整图重发；5% 是"看不出差异"的量级。
    // 1 = 不量化（逐字节比较，与改造前等价）。
    publish_deadband_ = declare_parameter<int>("publish_deadband", 5);
    // 视野外栅格的时间衰减（2026-11-09 用户裁定）：decayMiss() 此前每帧对**全图**
    // 曾命中过的格衰减，与"是否在视场内"无关 —— 视野外的真实障碍也被持续削弱，
    // 于是"消失—重新出现"成周期。现在只对**本帧被画幅覆盖**的格衰减；
    // 视野外保持原状（不衰减也不清除），由 stale_after_s 单独处理"很久没看"。
    decay_inside_footprint_only_ = declare_parameter<bool>("decay_inside_footprint_only", true);
    // ---- 观测空窗衰减（2026-11-09 用户裁定 Q19）----
    // 某格超过该时长没被任何射线扫到 ⇒ 按 p_decay 持续衰减（清成 unknown，不是 free）。
    // 实测：35% 的误覆盖格在相机当前画幅之外 —— 那是飞过去后留下的陈旧残留。
    // 取 3 s：3 s 内相机至少移动 6 m、画幅挪动 6 m，正常应该扫到。
    stale_after_s_ = declare_parameter<double>("stale_after_s", 3.0);
    // ---- occupied 的生命周期（2026-11-10，ADR-0039）----
    // 已确认占据的格超过该时长没有被**正向 hit** 就按 p_decay 削弱，降到退出门限
    // 以下即退出 occupied；一路削到 unknown_floor_p 为止（**unknown，不是 free**）。
    // 0 = 关闭（旧口径：occupied 只能被射线 carve 擦掉）。
    occupied_expire_s_ = declare_parameter<double>("occupied_expire_s", 3.0);
    // 纯时间流逝削弱的下限（概率）：低于它只能由**真实射线穿过**给出 free。
    unknown_floor_p_ = declare_parameter<double>("unknown_floor_p", 0.22);
    // ---- 小障碍的空间/时间支持门槛（2026-11-10，ADR-0039）----
    // 单帧内一个格至少要有这么多独立足迹点，才允许进 hit 证据（1 = 关闭）。
    min_hit_points_per_cell_ = declare_parameter<int>("min_hit_points_per_cell", 3);
    // 单格内足迹点 z 极差上限（m）：超过即判"混了两种表面"，整格不进 hit 证据。0 = 关闭。
    max_hit_z_spread_m_ = declare_parameter<double>("max_hit_z_spread_m", 1.5);
    // 深度一致性（中位数 + MAD）：稳健判"同格是不是同一个平面"（ADR-0039 补正）
    depth_mad_k_ = declare_parameter<double>("depth_mad_k", 3.0);
    depth_consistency_floor_m_ = declare_parameter<double>("depth_consistency_floor_m", 0.30);
    // 进入 occupied 需要累计的**跨帧** hit 次数（1 = 只靠概率门限）。
    min_hits_for_occupied_ = declare_parameter<int>("min_hits_for_occupied", 2);
    // 遮挡体最低置信度：carving 只被这么可信的格终止（低于它的格射线穿过、只弱衰减）。
    occluder_min_confidence_ = declare_parameter<double>("occluder_min_confidence", 0.60);
    // ---- free-space carving（2026-11-08 用户裁定 Q3：本次的根因修复）----
    // 只有"障碍点"观测时，地图只能单调生长（旧形状永不擦除）。有了相机地面投影，
    // 就能对「相机 → 障碍落点」的射线途经格打**真实负证据**，把残影擦掉。
    // 开关留作对照（0 = 关闭），但主链默认开启。
    carve_enabled_ = declare_parameter<bool>("carve_enabled", true);
    // 射程上限（m）：0 = 不限。UAV 在 14 m 高、覆盖 30 m 时，远处格子的深度误差
    // 已大于格宽（0.5 m），射线方向不可信 —— 用 0 表示"当前配置下不做限制"，
    // 需要收紧时由 config 给正值。
    carve_max_range_m_ = declare_parameter<double>("carve_max_range_m", 0.0);
    // 相机位姿来源：/agc/air/odom（与 nadir_projection 同源）。
    //
    // **2026-11-09 修正（用户裁定的 P0 根因）**：此前只存 odom 的 x/y/z，把相机当成
    // "位于机体位置、画幅轴与 world 轴对齐、永远正下视无旋转"。而投影端按**实际姿态**
    // 反投影出障碍点的 world 坐标 —— 两边各算一套相机几何，相机一转向/倾斜就错位：
    // 障碍点落在一处、carving 射线从另一处出发、画幅边界与真实视场不符。
    // 现在保存**完整位姿**（含四元数）并按时间戳查询，与投影端共用
    // `camera_geometry.hpp` 与 `footprint_geometry.hpp`。
    odom_topic_ = declare_parameter<std::string>("odom_topic", "/agc/air/odom");
    odom_tol_s_ = declare_parameter<double>("odom_pair_tolerance_s", 0.15);
    odom_buffer_n_ = declare_parameter<int>("odom_buffer_n", 120);
    sub_odom_ = create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, rclcpp::QoS(10),
      [this](nav_msgs::msg::Odometry::SharedPtr m) {
        agc_perception::PoseSample s;
        s.stamp_s = rclcpp::Time(m->header.stamp).seconds();
        s.pose.body_pos = {
          m->pose.pose.position.x, m->pose.pose.position.y, m->pose.pose.position.z};
        const auto & q = m->pose.pose.orientation;
        s.pose.body_q = {q.x, q.y, q.z, q.w};
        // 非法姿态**不进缓冲**：NaN 会污染插值，比丢一帧危险得多。
        if (!agc_perception::quatFinite(s.pose.body_q)) {return;}
        if (!std::isfinite(s.pose.body_pos.x) || !std::isfinite(s.pose.body_pos.y) ||
          !std::isfinite(s.pose.body_pos.z))
        {
          return;
        }
        odom_buf_.push_back(s);
        while (odom_buf_.size() > static_cast<size_t>(std::max(2, odom_buffer_n_))) {
          odom_buf_.pop_front();
        }
        have_odom_ = true;
      });
    // ---- 相机内参（2026-11-09 用户裁定 Q7/Q15）----
    // **为什么订阅它**：地面画幅必须从 `camera_info` 的 width/height/fx/fy **推导**，
    // 不能写死 hfov —— 写死会与 SDF 静默漂移（地图边界悄悄变错，没人发现）。
    // 内参是相机自己报的，换机型/改分辨率自动跟随。
    cam_info_topic_ = declare_parameter<std::string>(
      "cam_info_topic", "/agc/air/nadir/seg/camera_info");
    sub_cam_info_ = create_subscription<sensor_msgs::msg::CameraInfo>(
      cam_info_topic_, rclcpp::SensorDataQoS(),
      [this](sensor_msgs::msg::CameraInfo::SharedPtr m) {
        if (m->k.size() < 9) {return;}
        const double fx = m->k[0], fy = m->k[4];
        const double cx = m->k[2], cy = m->k[5];
        const int w = static_cast<int>(m->width), h = static_cast<int>(m->height);
        if (!(fx > 0.0) || !(fy > 0.0) || w <= 0 || h <= 0) {return;}
        if (!std::isfinite(cx) || !std::isfinite(cy)) {return;}
        // 画幅四角由**主点 ± 半幅**推出，因此 cx/cy 必须一起存 ——
        // 只存 fx/fy 会默认主点在图像中心，与实际内参不符时画幅整体平移。
        cam_intrinsics_ = {fx, fy, cx, cy};
        cam_w_ = w;
        cam_h_ = h;
        have_cam_info_ = true;
      });
    // **2026-11-08 用户裁定 Q7（批次 3）**：`/agc/map/obstacles`（合并后的障碍框）已退役。
    // 障碍表示改为足迹点，viz 直接显示 `/agc/map` 栅格 —— "看到的"就是"车看到的"，
    // 不再有第二份表示需要保持同源。
    sub_obstacles_ = create_subscription<agc_msgs::msg::ObstacleTrackArray>(
      "/agc/obstacles", rclcpp::QoS(10),
      std::bind(&MapAdapter::onObstacles, this, std::placeholders::_1));
    // ---- 足迹点订阅（2026-11-08 用户裁定 Q7/Q28）----
    // **为什么需要它**：`/agc/obstacles` 传的是"连通域 → 旋转外接矩形"，
    // 地面侧再把框栅格化 = 用更差的表示覆盖更好的表示（框面积/真实足迹实测 1.65×）。
    // 有了足迹点，栅格化就是"点落在哪个格"——表示误差归零。
    //
    // **为什么与 OBB 并行而不是替换**：批次 3 才会删框（那时 OBB 话题一并退役）；
    // 现在替换会让批次 2 与批次 3 耦合。并行期两者都喂 accum，靠 log-odds 去重
    // （同一格被两路观测到只是多一次 hit，不会产生两倍障碍）。
    footprint_topic_ = declare_parameter<std::string>(
      "footprint_topic", "/agc/obstacle_footprints");
    sub_footprints_ = create_subscription<agc_msgs::msg::ObstacleFootprintArray>(
      footprint_topic_, rclcpp::QoS(10),
      std::bind(&MapAdapter::onFootprints, this, std::placeholders::_1));
    RCLCPP_INFO(get_logger(),
      "map_adapter：感知地图模式，障碍唯一来源 /agc/obstacles（静态先验已停用，源时效 %.2fs）",
      source_max_age_s_);
    rebuild();
    publishMap();

    const auto period = std::chrono::duration<double>(1.0 / std::max(rate_hz_, 1e-3));
    timer_ = create_wall_timer(
      std::chrono::duration_cast<std::chrono::nanoseconds>(period),
      std::bind(&MapAdapter::tick, this));
  }

private:
  // （见 ADR-0009）：启动期几何 / 角度合法性校验，非法**明确拒绝**（抛错使节点 configure 失败；
  // **不**静默以默认值运行）。既有 rebuild 的 `res_<=0 || width<=0 || height<=0` 运行期守卫保留。
  void validateStartupOrThrow() const
  {
    std::ostringstream bad;
    if (map_file_.empty()) {bad << "map_file 未设置 ";}
    if (!std::isfinite(res_) || res_ <= 0.0) {bad << "resolution=" << res_ << " ";}
    if (!std::isfinite(sx_) || sx_ <= 0.0) {bad << "size_x=" << sx_ << " ";}
    if (!std::isfinite(sy_) || sy_ <= 0.0) {bad << "size_y=" << sy_ << " ";}
    if (!std::isfinite(ox_)) {bad << "origin_x=" << ox_ << " ";}
    if (!std::isfinite(oy_)) {bad << "origin_y=" << oy_ << " ";}
    // **多分辨率整数倍**（ADR-0040）：证据层分辨率必须是规划层的整数分之一。
    // 非整数倍（如 0.5/0.2 = 2.5）会让聚合重复计入或漏计，且错位随坐标漂移 ——
    // 那种错误在指标上只表现为"偶发边界误差"，极难归因。宁可拒绝启动。
    if (std::isfinite(res_) && res_ > 0.0 && std::isfinite(perception_resolution_) &&
      perception_resolution_ > 0.0)
    {
      const double ratio = res_ / perception_resolution_;
      const int f = static_cast<int>(std::lround(ratio));
      if (f < 1 || std::fabs(ratio - static_cast<double>(f)) > 1e-6) {
        bad << "perception_resolution=" << perception_resolution_
            << " 不是 resolution=" << res_ << " 的整数分之一 ";
      }
    }
    if (!bad.str().empty()) {
      throw std::runtime_error(
        "map_adapter 非法配置（拒绝启动，非静默以默认值运行）：" + bad.str() +
        "；要求 resolution/size_x/size_y > 0 且有限，origin 有限。");
    }
  }

  void loadMapGeometry()
  {
    if (map_file_.empty()) {RCLCPP_ERROR(get_logger(), "map_file 未设置"); return;}
    YAML::Node r;
    try {
      r = YAML::LoadFile(map_file_);
    } catch (const std::exception & e) {
      RCLCPP_ERROR(get_logger(), "读取 %s 失败: %s", map_file_.c_str(), e.what());
      return;
    }
    if (r["resolution"]) {res_ = r["resolution"].as<double>();}
    if (r["size_x"]) {sx_ = r["size_x"].as<double>();}
    if (r["size_y"]) {sy_ = r["size_y"].as<double>();}
    if (r["origin_x"]) {ox_ = r["origin_x"].as<double>();}
    if (r["origin_y"]) {oy_ = r["origin_y"].as<double>();}
  }

  // ---- 足迹点消费（2026-11-08 用户裁定 Q7/Q28）----
  //
  // 与 `onObstacles` 的**关键差异**：这里不做"连通域 → 框 → 栅格化"，
  // 而是**逐点落到格**——表示误差归零（不再有 AABB 包大、不再有框边界跳变）。
  //
  // 为什么仍然保留 `decayMiss` 与 carving：点只给"哪里有东西"，
  // 不给"哪里确定是空的"；负证据仍来自射线穿透。
  void onFootprints(const agc_msgs::msg::ObstacleFootprintArray & msg)
  {
    have_source_ = true;
    last_source_s_ = now().seconds();
    // 实测帧率（指数滑动平均）：供"空窗 3 秒"换算成帧数用。
    // 不写死帧数 —— 帧率随分辨率/负载在 8.9–10.3 Hz 之间变（实测）。
    if (last_fp_arrival_s_ > 0.0) {
      const double dt = last_source_s_ - last_fp_arrival_s_;
      if (dt > 1e-3 && dt < 1.0) {
        const double inst = 1.0 / dt;
        observed_frame_hz_ = 0.9 * observed_frame_hz_ + 0.1 * inst;
      }
    }
    last_fp_arrival_s_ = last_source_s_;
    ensureAccum();
    if (accum_.empty() || res_ <= 0.0) {return;}
    // **帧号先推进，再记账**（2026-11-09）：hit / carve / 空窗衰减必须落在**同一个**帧号上，
    // 否则"每格每帧一次"的去重槽位会跨帧错位（hit 记在上一帧、负证据记在本帧，
    // 同帧互斥就失效了）。`markStale` 仍在本帧末尾调用 —— 它用同一个 frame_idx。
    accum_.beginFrame(++frame_idx_);

    // **证据层尺寸**（ADR-0040）：hit/carve/衰减全部在证据分辨率上记账，
    // 规划层的尺寸只在 `rebuild()` 里出现。
    if (!perceptionGeometry()) {return;}
    const int width = perception_geo_.fine_width;
    const int height = perception_geo_.fine_height;
    if (width <= 0 || height <= 0) {return;}
    // 证据层格宽（下面的落格、包围盒、射线分箱、阴影长度都用它，不用 `res_`）。
    const double fres = perception_resolution_;

    // ---- 先取**足迹帧时刻**的位姿：hit 与 carve 都要用它 ----
    // 点来自那一帧的相机，用"最新 odom"会让射线起点与障碍点来自不同时刻 ——
    // 相机移动 2 m/s 时 100 ms 就差 0.2 m，足以把障碍边缘标成 free。
    // 位姿查询**与 carve 开关无关**：hit 的可信半径、视野内衰减都要用它。
    agc_perception::CamPose pose;
    bool have_pose = false;
    const double t_fp = rclcpp::Time(msg.header.stamp).seconds();
    if (have_odom_) {
      double used_dt = 0.0;
      have_pose = agc_perception::poseAtTime(
        std::vector<agc_perception::PoseSample>(odom_buf_.begin(), odom_buf_.end()),
        t_fp, odom_tol_s_, pose, &used_dt);
      if (have_pose) {
        last_odom_dt_s_ = used_dt;
        if (used_dt > 0.0) {++odom_extrapolated_frames_;}
      } else {
        ++odom_missing_frames_;
      }
    }

    // ---- 可信测量半径：hit 与 carve **同一道闸**（2026-11-09 修正）----
    //
    // **上一轮的缺陷**：只给 carve（负证据）加了可信半径，忘了 hit（正证据）。
    // 后果实测：1502 个真值格被标成 occupied 却**从未进入过任何一帧画幅**；
    // 过渡段大前倾时画幅算出 123.9×188.2 m（甚至 0.0×0.0），而 occupied 反而
    // 单帧涨 719 格 —— hit 只做越界检查，对"这点是否测得到"完全不设防。
    //
    // 没有位姿就没有可信半径 ⇒ 无法判断这些点是否可测 ⇒ **整帧不写 hit**。
    // 宁可少画（unknown 不是障碍，规划器可以走），也不要把测不到的地方画成障碍。
    if (!have_pose) {
      ++hit_skipped_frames_;
      // 无有效观测时刻位姿：hit 与 carve 都拒绝，不能用默认 pose 猜测相机位置。
      accum_.markStale(frame_idx_, stale_after_frames());
      // **不 rebuild**：证据更新拍不推进迟滞状态（见本函数末尾说明）。
      ++evidence_frames_;
      return;
    }

    // ---- 单帧**错位不确定度**：超过半格时本帧点不足以单独确认栅格（ADR-0039 补正）----
    //
    // 标签与深度的配对容差只回答"允许配对"，不回答"错位是否无害"：0.15 s × 2 m/s
    // = 0.30 m，而栅格 0.5 m、`dense_map` 的小障碍只有 1–3 格宽。
    //
    // **关键性质（决定它该用在哪）**：错位在一个帧内是**同向、相关**的误差 ——
    // 整帧点一起平移，所以**帧内点数再多也抵不掉它**（点都在一起偏）。
    // 只有**跨帧**才能发现并抵消。因此这里不把不确定度折成逐点权重
    // （那需要改消息契约，而 `ObstacleFootprintArray.confidence` 是批次级标量），
    // 而是让**本帧的 hit 强度**随不确定度衰减：不确定度 ≥ 半格时本帧不给正证据，
    // 让确认完全依赖"多个地图帧看到同一个位置"。
    //
    // 估计方式：用位姿缓冲里相邻两样本的水平位移/时间差 —— 与补偿用的位移**同源**，
    // 不会出现"速度取自 twist、位移取自位置"的口径分裂。
    double misalign_m = 0.0;
    {
      const agc_perception::PoseSample * prev = nullptr;
      for (const auto & s : odom_buf_) {
        if (s.stamp_s >= t_fp) {break;}
        prev = &s;
      }
      if (prev != nullptr && t_fp - prev->stamp_s < 0.5) {
        const double speed = agc_perception::bodySpeedBetween(
          prev->pose.body_pos, prev->stamp_s, pose.body_pos, t_fp);
        misalign_m = agc_perception::timeMisalignmentRadius(speed, last_odom_dt_s_);
      }
    }
    last_misalign_m_ = misalign_m;
    // 半格以上 ⇒ 本帧点集体可能整体偏移超过半格，不足以单独确认任何格。
    // 注意 `last_odom_dt_s_` 是"足迹帧时刻到最近 odom 样本的插值残差"，不是
    // 标签↔深度错位本身 —— 后者已在投影端按位移补偿掉，这里剩下的是**残余**错位。
    const bool frame_uncertain = misalign_m >= 0.5 * fres;


    agc_perception::Vec3 cam_origin;
    if (!agc_perception::cameraGroundPoint(pose, cam_origin)) {
      // 光轴不落地面（姿态异常）：本帧既不能 hit 也不能 carve。
      ++hit_skipped_frames_;
      accum_.markStale(frame_idx_, stale_after_frames());
      // **不 rebuild**：证据更新拍不推进迟滞状态（见本函数末尾说明）。
      ++evidence_frames_;
      return;
    }
    const agc_perception::Vec3 cam_world = agc_perception::cameraWorldOrigin(pose);
    const double trusted_r = agc_perception::trustedRadius(
      cam_world.z, cam_intrinsics_.fx, cam_w_);
    last_trusted_r_ = trusted_r;

    // 逐点 → 格索引（点落在哪个格就 hit 哪个格）。
    // 越界点直接丢弃（视野边缘/数值噪声），不裁剪到边界——裁剪会在边界堆出一圈假障碍。
    //
    // **2026-11-09 用户裁定：footprint 点先映射到格并去重，每格每帧最多一次 hit。**
    // 改造前对每个 footprint 点直接 `observeHit(idx)`：一个 0.5 m 格通常覆盖大量像素，
    // 同一格一帧内被 hit 几十次 ⇒ 证据强度取决于**像素采样密度**而不是时序观测，
    // 栅格中心一帧打满、边缘只命中一两次，边缘格于是在 100 与中间值之间反复翻转。
    // 实测 |Δoccupied| p99 = 140 格（判据 ≤50）正是这么来的。
    //
    // 去重不改变"落格"几何：`hit_cells_` 是唯一格索引集合，hit 只对它做一次。
    long hit_raw = 0;          // 原始 footprint 点数（可信半径 + 越界过滤之后）
    long hit_dup = 0;          // 落在已见过的格上的重复点数
    long hit_rejected = 0;     // 被可信半径拒掉的点数
    long hit_weak = 0;         // 被空间支持门槛拒掉的**格**数
    long sigma_rejected_cells = 0;   // 其中被逐点 σ 门控拒掉的（ADR-0042）
    // **2026-11-10（ADR-0039）：先攒本帧的空间支持，再判是否进 hit 证据。**
    //
    // 旧实现"点落格即 hit"，于是 dense_map 的小障碍（0.6–1.2 m，0.5 m 格下只有
    // 1–3 格宽）只要有一个错误投影点落进某格，跨两帧就成了 occupied。而大建筑
    // 一个格内有成百上千个点，同样两帧才是 occupied —— 两者的证据强度完全不同，
    // 却走同一条判据。现在按"该格本帧有几个独立点 + z 展布是否一致"分档：
    // 小障碍仍能确认（0.6×0.6 m 在 GSD 5.3 cm/px 下约 128 px），孤立错位点被拒。
    const size_t n_cells = static_cast<size_t>(width) * height;
    if (obstacle_mask_.size() != n_cells) {
      obstacle_mask_.assign(n_cells, 0);
    } else {
      std::fill(obstacle_mask_.begin(), obstacle_mask_.end(), static_cast<char>(0));
    }
    hit_cells_.clear();
    // **单遍完成"攒支持 + 记账"**，且**每格每帧只判一次**（证据单位纪律）。
    //
    // 为什么分两段而不是一遍到底：`min_hit_points_per_cell` 需要**该格本帧的总点数**，
    // 而扫到某个点时还不知道后面还有几个点（首次遇到时 `framePoints(idx)` 只是 1）。
    // 所以先扫一遍只累加点数（不记账、不判），再对"被碰过的格"判一次。
    // 第二段只遍历 `candidate_cells_`（本帧碰过的格索引），不再扫一遍全部点 ——
    // dense_map 单帧 15 万个点，重复做 `hypot` 是纯浪费。
    candidate_cells_.clear();
    // 逐点协方差（ADR-0042）：发布端给的是与 `points` 同下标的 2×2 上三角。
    // 三个数组**必须等长**才算可信；任一缺失就整体当"无该信息"（不做部分采信 ——
    // 混着读会让某些点拿到别人的协方差，而且错得很安静）。
    const size_t n_pts_msg = msg.points.size();
    const bool have_cov = msg.point_cov_xx.size() == n_pts_msg &&
      msg.point_cov_xy.size() == n_pts_msg && msg.point_cov_yy.size() == n_pts_msg;
    if (have_cov) {++frames_with_cov_;}
    // 第一段：逐点落格 + 累加本帧点数与 z 极值（**不记账**）。过滤口径不变。
    for (size_t pi = 0; pi < n_pts_msg; ++pi) {
      const auto & p = msg.points[pi];
      // 只接受**可信测量范围内**的点（与 carve 同口径）。
      // 超出它，单个像素对应的地面尺寸已大于格宽，点的落位不可信。
      if (trusted_r > 0.0 &&
        std::hypot(p.x - cam_origin.x, p.y - cam_origin.y) > trusted_r)
      {
        ++hit_rejected;
        continue;
      }
      const int ix = agc_perception::worldToGrid(p.x, ox_, fres);
      const int iy = agc_perception::worldToGrid(p.y, oy_, fres);
      if (ix < 0 || iy < 0 || ix >= width || iy >= height) {continue;}
      ++hit_raw;
      const size_t idx = static_cast<size_t>(iy) * width + ix;
      // 主方向 1σ：协方差最大特征值的平方根（见 `Cov2::sigmaMajor`）。
      // **-1 = 无该信息**，不是 0（0 会被读成"非常准"）。
      double sigma_m = -1.0;
      if (have_cov) {
        agc_perception::Cov2 c;
        c.xx = static_cast<double>(msg.point_cov_xx[pi]);
        c.xy = static_cast<double>(msg.point_cov_xy[pi]);
        c.yy = static_cast<double>(msg.point_cov_yy[pi]);
        sigma_m = c.sigmaMajor();
      }
      accum_.addFramePoint(idx, p.z, sigma_m);
      if (obstacle_mask_[idx]) {++hit_dup; continue;}   // 本帧该格已登记
      obstacle_mask_[idx] = 1;                          // 同时供 carve 保护障碍格
      candidate_cells_.push_back(idx);
    }
    // 第二段：对**本帧被碰过的格**判一次空间支持（每格每帧只判一次）。
    for (size_t idx : candidate_cells_) {
      // **错位不确定度超过半格 ⇒ 本帧整帧不给正证据**（ADR-0039 补正）。
      // 错位是帧内**相关**误差（整帧一起平移），帧内点数再多也抵不掉 ——
      // 只有跨帧才能抵消，所以这里退让、把确认让给后续地图帧。
      if (frame_uncertain) {
        ++hit_weak;
        continue;
      }
      const int n_pts = accum_.framePoints(idx);
      const double z_spread = accum_.frameZSpread(idx);
      // **深度一致性**（ADR-0039 补正，temp.md 点名的"深度中位数/MAD"）：
      // 极差只能抓"混了两种表面"，抓不到"整片偏移但局部连续"。这里再判一次
      // 稳健一致性（中位数 + MAD），少数离群点不再让整格被拒。
      if (!accum_.frameDepthConsistent(idx)) {
        ++hit_weak;
        continue;
      }
      // 逐点不确定度门控（ADR-0042）：与上面的帧级错位门控**分开计数**。
      // 两者根因不同（一个是整帧系统位移、一个是逐点随机误差），混成一个数
      // 就无法判断"该收紧哪一个"。这里先判、先计数，再交给 `observeHitWithSupport`
      // 判剩余门槛（那里也有一份同样判据，供不经此处的调用方使用）。
      if (sigma_reject_ratio_ > 0.0 && perception_resolution_ > 0.0) {
        const double s = accum_.frameSigmaMax(idx);
        if (s >= 0.0 && s > sigma_reject_ratio_ * perception_resolution_) {
          ++sigma_rejected_cells;
          ++hit_weak;
          continue;
        }
      }
      if (!accum_.observeHitWithSupport(idx, n_pts, z_spread)) {
        ++hit_weak;
        continue;
      }
      hit_cells_.push_back(idx);
    }
    // ---- 实例级累积（ADR-0041，temp.md 方向三）----
    //
    // **为什么还要实例层**：逐点累积能跨帧合并（画幅切碎的大建筑天然长回去），
    // 但小障碍（0.5 m 格下 1–3 格宽）的边界点会在相邻格之间跳 —— 逐点累积拿不到
    // "这些点属于同一个障碍"这个信息。实例层补的正是这一层：**跨帧一致的几何模型**。
    //
    // **为什么是并集而不是替换**：大建筑被画幅切成碎片时实例会分裂（每片各自成实例），
    // 而逐点累积天然把它们合并。所以规划占据 = 逐点证据 ∪ 已确认实例。
    // 实例层的作用是**稳定小障碍**，不是取代逐点累积。
    updateInstances(msg);
    const long hit_n = static_cast<long>(hit_cells_.size());
    // 诊断三量（**口径必须分开**，否则 carve/hit 的分母被重复点放大）：
    //   footprint_points = 原始点数；unique_hit_cells = 唯一格数；duplicate_points = 重复点数
    footprint_points_ += hit_raw;
    footprint_hits_ += hit_n;
    footprint_dups_ += hit_dup;
    hit_rejected_ = hit_rejected;
    hit_weak_cells_ = hit_weak;
    sigma_rejected_cells_ = sigma_rejected_cells;

    // ---- 负证据（2026-11-09 用户裁定 Q7-Q17）：按角度分箱 + 射到画幅边界 ----
    //
    // **可见性掩码每帧必须清空**（ADR-0042）：它是**本帧**的"看得见"集合，
    // 不是累积集合。忘了清会让"曾经看过"永远为真，`fully_visible` 退化成常量 1，
    // 而这个字段的全部价值就在于区分"这帧看到了"与"以前看过"。
    if (!visible_mask_.empty()) {
      std::fill(visible_mask_.begin(), visible_mask_.end(), static_cast<char>(0));
    }
    if (carve_enabled_) {
      carveNegativeEvidence(msg.points, pose);
    }
    accum_.markStale(frame_idx_, stale_after_frames());
    // **视野外不衰减**（2026-11-09 用户裁定）：只有本帧画幅覆盖的格才允许"时间流逝"
    // 作为弱负证据。画幅外的格，"本帧没看到"是必然的、不携带信息。
    // 画幅无效（内参未到 / 姿态异常）时退回全图衰减 —— 那是旧口径，比"完全不衰减"
    // 更保守（至少还能让陈旧证据变弱）。
    if (decay_inside_footprint_only_ && have_pose && have_cam_info_) {
      const auto fp = agc_perception::footprintFromCamera(
        pose, cam_intrinsics_, cam_w_, cam_h_);
      if (fp.valid) {
        // 可信测量半径与相机世界原点（与 carve 用同一口径）
        const agc_perception::Vec3 deco = agc_perception::cameraWorldOrigin(pose);
        const double trusted_r = agc_perception::trustedRadius(
          deco.z, cam_intrinsics_.fx, cam_w_);
        // 画幅包围盒（格坐标）：只在这个盒子里判内外，与整图面积无关。
        //
        // **2026-11-09 性能修复（用户裁定）**：改造前每帧 `std::vector<char> inside(w*h)`
        // 分配并清零整图、逐格算 `hypot`、再把整张掩码交给 `decayMissMasked`（那里又扫全图）。
        // 成本 = O(画幅包围盒) + O(整图面积) × 2，而真正该衰减的格只在画幅内。
        // 现在：包围盒剪枝 + 内联判定 + 只遍历**有证据格索引**，零分配。
        const int i0 = std::max(0, agc_perception::worldToGrid(
          std::min({fp.corners[0].x, fp.corners[1].x,
            fp.corners[2].x, fp.corners[3].x}), ox_, fres));
        const int i1 = std::min(width - 1, agc_perception::worldToGrid(
          std::max({fp.corners[0].x, fp.corners[1].x,
            fp.corners[2].x, fp.corners[3].x}), ox_, fres));
        const int j0 = std::max(0, agc_perception::worldToGrid(
          std::min({fp.corners[0].y, fp.corners[1].y,
            fp.corners[2].y, fp.corners[3].y}), oy_, fres));
        const int j1 = std::min(height - 1, agc_perception::worldToGrid(
          std::max({fp.corners[0].y, fp.corners[1].y,
            fp.corners[2].y, fp.corners[3].y}), oy_, fres));
        accum_.decayMissInBox(i0, j0, i1, j1,
          [&](size_t, int i, int j) {
            const double wx = ox_ + (i + 0.5) * fres;
            const double wy = oy_ + (j + 0.5) * fres;
            // **同时受可信半径约束**（2026-11-09）：几何画幅之外还有"测不准"的环带。
            // 只按多边形判会把这个环带也算作"看过"，于是那里的陈旧证据照样被衰减。
            if (!agc_perception::footprintContains(fp, wx, wy)) {return false;}
            if (trusted_r > 0.0 &&
              std::hypot(wx - deco.x, wy - deco.y) > trusted_r)
            {
              return false;
            }
            return true;
          });
      } else {
        // 画幅无效：**不衰减**。旧口径（全图衰减）正是本函数要修的行为 ——
        // "不知道看没看到"时什么都不做，比"假定没看到"安全。
        ++decay_skipped_frames_;
      }
    } else {
      ++decay_skipped_frames_;
    }
    // **证据更新与地图发布解耦**（2026-11-09 用户裁定）：感知帧 10 Hz 只更新内部
    // 累积层；`/agc/map` 由 `tick()` 按 `rate_hz`（2 Hz）生成快照并发布。
    // 改造前这里 `if (rebuild()) publishMap();`，地图实际按感知帧率重建与发布，
    // `rate_hz` 只控制 timer tick —— 配置与实际行为不一致，稳定性指标因此虚高。
    //
    // **2026-11-09 追加（用户裁定：迟滞状态的推进时机必须显式）**：这里**不再**
    // 调用 `rebuild()`。`rebuild()` 内含 `snapshot()`，而 `snapshot()` 会推进
    // `occupied_now_`（迟滞记忆）—— 于是"对外地图 2 Hz、内部迟滞 10 Hz"，
    // 两次发布之间的 occupied→non→occupied 翻转被内部吃掉、对外只留一个状态。
    // 现在迟滞状态**按地图帧（发布拍）推进**，与 `perception_quality.py`
    // 按 `/agc/map` 帧统计稳定性的口径一致。
    ++evidence_frames_;
  }

  // ---- 实例级累积（ADR-0041）----
  //
  // 把本帧足迹点按 `point_instance_id` 分组 → 每组拟合一个实例观测 →
  // 交给 `InstanceTracker` 做跨帧跟踪与生命周期。
  //
  // **没有 id 的点直接跳过**（不猜归属）：`point_instance_id` 为空串表示发布端
  // 未能把该点关联到任何实例（碎片被面积门限滤掉 / 关联失败）。给它编一个 id
  // 等于凭空造实例，比不处理更糟。
  void updateInstances(const agc_msgs::msg::ObstacleFootprintArray & msg)
  {
    // 本拍时刻注入（ADR-0042）：`InstanceTracker` 是纯逻辑类、不持时钟，
    // 轨迹历史的时间戳由调用方给。用**消息时间戳**而不是 `now()` ——
    // 历史跨度必须是"观测间隔"，不是"处理间隔"（两者在丢帧时差很多）。
    instances_.setClock(rclcpp::Time(msg.header.stamp).seconds());
    instances_.beginFrame();
    instance_group_xs_.clear();
    instance_group_ys_.clear();
    instance_group_zs_.clear();
    instance_ids_.clear();

    const size_t n = msg.points.size();
    const bool have_ids = (msg.point_instance_id.size() == n);
    if (!have_ids) {
      // 发布端没带 id（旧版本 / 空帧）：本拍不更新实例，但**要计入 miss**，
      // 否则实例会永远活着 —— 那比不更新更危险。
      for (size_t i = 0; i < instances_.instances().size(); ++i) {instances_.miss(static_cast<int>(i));}
      instance_tracked_ = 0;
      return;
    }

    // 按 id 分组（保持首次出现顺序，便于诊断复现）
    std::unordered_map<std::string, size_t> slot;
    for (size_t i = 0; i < n; ++i) {
      const std::string & id = msg.point_instance_id[i];
      if (id.empty()) {continue;}
      auto it = slot.find(id);
      size_t gi = 0;
      if (it == slot.end()) {
        gi = instance_ids_.size();
        slot.emplace(id, gi);
        instance_ids_.push_back(id);
        instance_group_xs_.emplace_back();
        instance_group_ys_.emplace_back();
        instance_group_zs_.emplace_back();
      } else {
        gi = it->second;
      }
      instance_group_xs_[gi].push_back(msg.points[i].x);
      instance_group_ys_[gi].push_back(msg.points[i].y);
      instance_group_zs_[gi].push_back(msg.points[i].z);
    }

    // 拟合 + 关联 + 吸收
    std::vector<int> matched(instances_.instances().size(), -1);
    agc_perception::InstanceFitParams fit;
    for (size_t gi = 0; gi < instance_ids_.size(); ++gi) {
      agc_perception::InstanceObservation obs;
      if (!agc_perception::fitInstanceObservation(
          instance_group_xs_[gi], instance_group_ys_[gi], instance_group_zs_[gi], fit, obs))
      {
        continue;   // 点数不足：连方向都定不了，不硬拟合
      }
      const int idx = instances_.associate(obs.cx, obs.cy);
      if (idx >= 0) {
        instances_.absorb(idx, obs);
        matched[static_cast<size_t>(idx)] = static_cast<int>(gi);
      } else {
        instances_.spawn(obs);
        // spawn 后新实例在末尾
        matched.push_back(static_cast<int>(gi));
      }
    }
    // 本拍没有观测支撑的实例计 miss（连续 miss 到阈值才死）
    for (size_t i = 0; i < matched.size(); ++i) {
      if (matched[i] < 0) {instances_.miss(static_cast<int>(i));}
    }
    instance_tracked_ = static_cast<long>(instance_ids_.size());
    instance_confirmed_ = static_cast<long>(instances_.confirmedCount());
  }

  // 已确认实例 → 证据层格集合（规划占据的并集项之一）。
  //
  // **用椭圆（按实例朝向与半长）而不是外接圆**。这是实测修正，不是口味：
  // 外接圆对长条 box 的膨胀是 2–3.3 倍（0.6×0.15 m 的 box：圆 1.202 m² vs 矩形 0.360 m²
  // = 3.34×），实测让整图 occupied 从 2230 涨到 4622（2.07×）—— 那已经不是
  // "稳定小障碍"，而是**凭空造障碍**，直接推高误覆盖率。
  //
  // 椭圆 `((u/hx)² + (v/hy)² ≤ 1)` 保留朝向、面积等于 `π·hx·hy`，与矩形同量级
  // （box 0.6×0.3：椭圆 0.565 m² vs 矩形 0.72 m²，甚至略小），不会虚增。
  // 圆（`hx == hy`）时椭圆退化成圆，语义不变。
  //
  // **仍偏保守**：椭圆外接于矩形之外的部分（四个角）会被多算，但量级与矩形相当，
  // 且方向安全（只会高估、不会漏掉真实占据）。
  void stampConfirmedInstances()
  {
    const double fres = perception_resolution_;
    if (!(fres > 0.0)) {return;}
    instance_cells_.clear();
    const int w = perception_geo_.fine_width;
    const int h = perception_geo_.fine_height;
    // 格 → 实例 id（ADR-0042，temp.md 方向一"来源实例"）。
    // **与 `instance_cells_` 同一次遍历填**：分两次遍历会让两者在边界格上分叉，
    // 而那种分叉的症状是"某格标着实例 17、但 17 的栅格化里没有它"，极难归因。
    if (instance_cell_owner_.size() != static_cast<size_t>(w) * h) {
      instance_cell_owner_.assign(static_cast<size_t>(w) * h, -1);
      instance_cell_confidence_.assign(static_cast<size_t>(w) * h, 0.0f);
    } else {
      std::fill(instance_cell_owner_.begin(), instance_cell_owner_.end(), -1);
      std::fill(instance_cell_confidence_.begin(), instance_cell_confidence_.end(), 0.0f);
    }
    for (const auto & inst : instances_.instances()) {
      if (!inst.confirmed) {continue;}
      // 半长取实例的半长；退化（0）时退回半径，保证小圆实例仍能被栅格化。
      double hx = inst.half_x_m;
      double hy = inst.half_y_m;
      if (!(hx > 0.0) || !(hy > 0.0)) {
        hx = hy = inst.radius_m;
      }
      if (!(hx > 0.0) || !(hy > 0.0)) {continue;}
      const double rmax = std::max(hx, hy);
      const int i0 = agc_perception::worldToGrid(inst.cx - rmax, ox_, fres);
      const int i1 = agc_perception::worldToGrid(inst.cx + rmax, ox_, fres);
      const int j0 = agc_perception::worldToGrid(inst.cy - rmax, oy_, fres);
      const int j1 = agc_perception::worldToGrid(inst.cy + rmax, oy_, fres);
      const double ca = std::cos(inst.yaw);
      const double sa = std::sin(inst.yaw);
      for (int j = std::max(0, j0); j <= std::min(h - 1, j1); ++j) {
        for (int i = std::max(0, i0); i <= std::min(w - 1, i1); ++i) {
          const double wx = ox_ + (i + 0.5) * fres;
          const double wy = oy_ + (j + 0.5) * fres;
          const double dx = wx - inst.cx;
          const double dy = wy - inst.cy;
          // 转到实例坐标系（沿 yaw 为 u、垂直为 v），再判椭圆内
          const double u = dx * ca + dy * sa;
          const double v = -dx * sa + dy * ca;
          if ((u * u) / (hx * hx) + (v * v) / (hy * hy) > 1.0) {continue;}
          const size_t cidx = static_cast<size_t>(j) * w + i;
          instance_cells_.push_back(cidx);
          instance_cell_owner_[cidx] = inst.id;
          instance_cell_confidence_[cidx] = static_cast<float>(inst.confidence);
        }
      }
    }
  }

  // 空窗帧数：由 `stale_after_s` 按实际帧率换算。
  // 用**实测帧率**而不是写死帧数 —— 帧率会随分辨率/负载变（实测 8.9–10.3 Hz），
  // 写死帧数会让"3 秒"这个语义随帧率漂移。
  long stale_after_frames() const
  {
    const double hz = std::max(1.0, observed_frame_hz_);
    return static_cast<long>(std::lround(stale_after_s_ * hz));
  }

  // occupied 生命周期（秒 → 帧）：与 `stale_after_frames` 同一换算口径。
  //
  // **为什么也按实测帧率换算**：`occupied_expire_s` 的语义是"多久没再看到它"，
  // 那是**时间**。写死帧数会让"3 秒"随帧率漂移（dense_map 实测帧率在 6–10 Hz
  // 之间变，同一份配置下有效期差 40%）。
  long expire_frames() const
  {
    const double hz = std::max(1.0, observed_frame_hz_);
    return static_cast<long>(std::lround(occupied_expire_s_ * hz));
  }

  // 负证据（free-space carving）：2026-11-09 用户裁定 Q7-Q17 的**根因修复**。
  //
  // **原实现的两个缺陷**（都是用户实测指出的）：
  //   ① `observeMiss` 只在射线打到障碍时调用 ⇒ **没有障碍的方向零负证据**，
  //      那片区域永远 unknown（灰色）。而 yard 障碍只占作业区 11.5%，绝大多数方向没障碍。
  //   ② 对**每个足迹点**各射一条（一帧 2 万条），既有冗余，又在"同角度近处有障碍"时
  //      还去射远处的（物理上被挡住，不该再射）。
  //
  // **现在的做法**（一次遍历完成"有障碍"与"无障碍"两种情况）：
  //   1. 按角度分箱（箱数 = 画幅周长/格宽，当前约 512），每箱记**最近**的障碍点及其 z；
  //   2. 对每个箱：有障碍 → 射到该点（终点不打 miss，那是占据证据本身）；
  //              无障碍 → 射到**画幅边界**（终点即边界，沿途全是"看到是空的"）；
  //   3. 阴影远边 `d_o·H/(H−h)` 之后的区域**仍要打 miss**（视线从楼顶掠过，又可见了），
  //      阴影**区间内**不打 miss（那是真看不见，保持 unknown）。
  //      这就是用户否掉的"一刀切截断"的替代：矮障碍后面立刻安全，高楼后面精确留阴影。
  //   4. 画幅边缘 10%（GSD 恶化 1/cos²）用**弱**负证据（p_decay），中心用强（p_miss）。
  //
  // **阴影区为什么标 unknown 而不是 free**（Q14）：unknown 在 `planning_policy.hpp` 里
  // **不是障碍**（规划器可以走，直连兜底就是为此设的），只是不享受"已确认安全"的待遇。
  // 标成 free 等于对规划器承诺"这条路我确认过"，那是过度承诺。
  void carveNegativeEvidence(
    const std::vector<geometry_msgs::msg::Point> & points, const agc_perception::CamPose & pose)
  {
    // 画幅必须有效才能算边界；内参未到时**只做障碍方向的射线**（退化为旧行为，
    // 不会误标自由）—— 宁可少标安全，也不要在不知道看多远时乱标。
    //
    // **2026-11-09 修正**：画幅与射线起点都来自**完整相机位姿**（与投影端同一套
    // `camera_geometry.hpp`）。此前把画幅当成"以相机地面投影为中心的轴对齐矩形"，
    // 相机一转向就整束射线偏转 —— 那是误覆盖随姿态周期变化的主要来源。
    // 相机世界原点与光轴落点：射线从**光轴落点**出发（不是机体位置、也不是安装点）。
    const agc_perception::Vec3 cam_origin = agc_perception::cameraWorldOrigin(pose);
    const double cam_h = cam_origin.z;
    last_cam_h_ = cam_h;

    const auto fp = agc_perception::footprintFromCamera(pose, cam_intrinsics_, cam_w_, cam_h_);
    // **画幅合理性**（2026-11-09）：大前倾时四角投影会发散（实测算出过 123.9x188.2 m），
    // 或退化成 0.0x0.0。此时几何已不可信，**不**拿它去圈定负证据/边缘区 ——
    // 否则射线会射到根本不存在的"边界"上。`have_fp=false` 时只做障碍方向射线。
    const bool have_fp = fp.valid && agc_perception::footprintPlausible(
      fp, cam_h, cam_intrinsics_.fx, cam_w_);
    if (fp.valid && !have_fp) {++implausible_fp_frames_;}
    last_fp_half_x_ = fp.half_x;
    last_fp_half_y_ = fp.half_y;
    agc_perception::Vec3 origin;
    if (!agc_perception::cameraGroundPoint(pose, origin)) {
      // 光轴不落在地面上（姿态异常 / 相机朝上）：本帧不做负证据。
      ++carve_calls_;
      last_rays_hit_ = 0;
      last_rays_edge_ = 0;
      last_shadow_skipped_ = 0;
      return;
    }
    const double cam_gx = origin.x, cam_gy = origin.y;

    // ---- 距离上限：**可信测量半径**，不是几何视场边界（2026-11-09 修正）----
    //
    // 画幅给出的是**几何**视场（四角投影的四边形）。它随姿态变化：悬停时约 1–2°
    // 倾斜就能把 bbox 半宽从 30.0 拉到 32.5 m、四角最远 46 m。若 carve 射到那个边界，
    // 射线会穿过"几何上在视场内、但实际测不准"的区域 —— 实测把 911 个真值障碍格
    // 打成 free，其中 86% 从未进入过任何一帧画幅（距相机 40–50 m）。
    //
    // 因此上限取**正下视 GSD 恒等式**给出的可信半径（与姿态无关），
    // 再与画幅边界、用户上限取最小。`carve_max_range_m` 仍可进一步收紧（0 = 不额外收紧）。
    const double trusted_r = agc_perception::trustedRadius(cam_h, cam_intrinsics_.fx, cam_w_);
    double user_max = trusted_r;
    if (carve_max_range_m_ > 0.0) {
      user_max = (user_max > 0.0) ? std::min(user_max, carve_max_range_m_) : carve_max_range_m_;
    }
    last_trusted_r_ = user_max;

    // **证据层格坐标**（ADR-0040）：射线在证据层上遍历，负证据落在证据格上。
    const double fres = perception_resolution_;
    const int cx = agc_perception::worldToGrid(cam_gx, ox_, fres);
    const int cy = agc_perception::worldToGrid(cam_gy, oy_, fres);

    // ---- 1. 角度分箱：每箱取最近障碍点 ----
    // 箱数按画幅周长/格宽自适应（Q8）：每条射线在边界处前进约 1 格，无空隙也不冗余。
    // 无画幅时退回固定 360（只用于"有障碍"方向，不会产生边界射线）。
    int n_bins = 360;
    if (have_fp) {
      const double perim = 2.0 * (fp.half_x + fp.half_y) * 2.0;
      n_bins = static_cast<int>(std::ceil(perim / std::max(fres, 1e-6)));
      n_bins = std::max(64, std::min(n_bins, 2048));
    }
    std::vector<double> best_d2(static_cast<size_t>(n_bins),
                                std::numeric_limits<double>::infinity());
    std::vector<double> best_x(static_cast<size_t>(n_bins), 0.0);
    std::vector<double> best_y(static_cast<size_t>(n_bins), 0.0);
    std::vector<double> best_z(static_cast<size_t>(n_bins), 0.0);
    // 每箱的 z 样本（**稳健高度**用）：单点 z 的噪声会直接变成阴影长度误差，
    // 而阴影长度对高度极敏感（`d_o·H/(H−h)` 在 h→H 时发散）。
    std::vector<std::vector<double>> bin_z(static_cast<size_t>(n_bins));
    const double two_pi = 2.0 * M_PI;
    for (const auto & p : points) {
      const double dx = p.x - cam_gx, dy = p.y - cam_gy;
      const double d2 = dx * dx + dy * dy;
      if (!(d2 > 0.0)) {continue;}
      double ang = std::atan2(dy, dx);
      if (ang < 0.0) {ang += two_pi;}
      int b = static_cast<int>(ang / two_pi * n_bins);
      b = std::max(0, std::min(b, n_bins - 1));
      const size_t bi = static_cast<size_t>(b);
      bin_z[bi].push_back(p.z);
      if (d2 < best_d2[bi]) {
        best_d2[bi] = d2;
        best_x[bi] = p.x;
        best_y[bi] = p.y;
        best_z[bi] = p.z;
      }
    }

    long rays_hit = 0, rays_edge = 0, shadow_skipped = 0;
    // ---- 2. 每个箱射一条 ----
    for (int b = 0; b < n_bins; ++b) {
      const size_t bi = static_cast<size_t>(b);
      const bool has_obs = std::isfinite(best_d2[bi]);
      // 该箱的方向（用箱中心角；有障碍时用真实方向，更准）
      double ux, uy, dist;
      if (has_obs) {
        ux = best_x[bi] - cam_gx;
        uy = best_y[bi] - cam_gy;
        dist = std::sqrt(best_d2[bi]);
      } else {
        const double ang = (b + 0.5) / n_bins * two_pi;
        ux = std::cos(ang);
        uy = std::sin(ang);
        dist = have_fp ? agc_perception::footprintEdgeDistance(fp, ux, uy) : 0.0;
        if (!(dist > 0.0)) {continue;}   // 无画幅且无障碍 → 没有可射的终点
      }
      if (user_max > 0.0) {dist = std::min(dist, user_max);}

      // 阴影远边：只在**有障碍**时存在
      double shadow_end = 0.0;
      if (has_obs) {
        // **稳健高度**（2026-11-09）：用该箱 z 样本的中位数，而不是单个最近点的 z。
        // 最近点可能落在女儿墙 / 屋顶设备 / 深度噪声上，高度差 1 m 就能让阴影远边
        // 变化数米 —— 那是"周期性 unknown/free/occupied 切换"的直接来源。
        const double obs_h = bin_robust_z(bin_z[bi], best_z[bi]);
        const double far = agc_perception::shadowFarEdge(cam_h, obs_h, dist);
        if (std::isfinite(far)) {
          // 阴影区 [dist, far)：不打 miss。射线总长取 min(far, 画幅边界)
          shadow_end = far;
        } else {
          // 障碍与相机同高或更高 ⇒ 后面全看不见：整条射线不产生负证据
          ++shadow_skipped;
          continue;
        }
        if (user_max > 0.0) {shadow_end = std::min(shadow_end, user_max);}
        if (shadow_end < dist) {shadow_end = dist;}
        ++rays_hit;
      } else {
        ++rays_edge;
      }

      // ---- 射线终点 ----
      //
      // **原 bug**：写成 `has_obs ? dist : dist` —— 两个分支一样，射线永远停在障碍点。
      // 于是"阴影远边之后射到画幅边界"这一段**根本没射**：障碍后面的整片区域
      // 既没 hit 也没 miss，保持上一次的状态 —— 包括更早累积的**误 hit，永远擦不掉**。
      //
      // **正确终点**：
      //   * 无障碍 → 画幅边界（沿途全是"看到是空的"）；
      //   * 有障碍 → **max(障碍距离, 阴影远边)**，但要被画幅边界封顶：
      //     - 矮障碍（阴影远边 < 边界）⇒ 射线穿过阴影区射到边界，阴影区间内不打 miss，
      //       之后重新打 miss —— 这正是用户要的"矮障碍后面标安全"；
      //     - 高楼（阴影远边 > 边界）⇒ 封顶到边界，整段都在阴影里 ⇒ 一格都不打 miss，
      //       后面保持 unknown（不是 free，也不是障碍）。
      double end_dist = dist;
      if (has_obs) {
        end_dist = std::max(dist, shadow_end);
      }
      if (have_fp) {
        const double edge = agc_perception::footprintEdgeDistance(fp, ux, uy);
        if (edge > 0.0) {end_dist = std::min(end_dist, edge);}
      }
      if (user_max > 0.0) {end_dist = std::min(end_dist, user_max);}
      if (end_dist <= 0.0) {continue;}
      const double ulen = std::max(1e-9, std::hypot(ux, uy));
      const double ex = cam_gx + ux / ulen * end_dist;
      const double ey = cam_gy + uy / ulen * end_dist;
      const int ix = agc_perception::worldToGrid(ex, ox_, fres);
      const int iy = agc_perception::worldToGrid(ey, oy_, fres);

      // 边缘区用弱负证据（Q17）。判据用射线**终点**是否落在画幅边缘带，
      // 不是"走了多远" —— 倾斜时画幅是梯形，同一距离在近边已到边界、在远边还早。
      const bool weak = have_fp && agc_perception::isFootprintEdgeAt(fp, ex, ey);
      const double shadow_cells = shadow_end / std::max(fres, 1e-6);
      carve_cells_ += accum_.carveRay(cx, cy, ix, iy, weak, shadow_cells, &obstacle_mask_);
      // ---- 可见性掩码（ADR-0042）：沿本帧射线标记"看得见的地面"----
      //
      // **为什么在这里标而不是另算一遍**：射线已经在遍历这条线上的格了，
      // 再算一遍等于把同一份几何算两次，且两次的阴影判据可能分叉。
      // 只有 `!weak` 的射线才标"完整可见" —— 画幅边缘带 GSD 恶化 1/cos²，
      // 那里的"看见"是弱证据，不该与正下方一视同仁。
      if (!weak) {
        markVisibleAlongRay(cx, cy, ix, iy, shadow_cells);
      }
    }

    ++carve_calls_;
    last_rays_hit_ = rays_hit;
    last_rays_edge_ = rays_edge;
    last_shadow_skipped_ = shadow_skipped;
  }

  // 沿一条射线把 [起点, 终点) 标为"完整可见"（ADR-0042）。
  //
  // **口径**：终点之前（不含终点本身，那是障碍）且不在遮挡阴影内的格，
  // 是本帧**确实看到了地面**的格。阴影内的格看得见"障碍后面"吗？看不见 ——
  // 所以 `shadow_cells` 之后的段不标。
  //
  // 用 Bresenham 而不是逐格重采样：射线端点已是格坐标，逐格走与
  // `carveRay` 的遍历口径一致，不会出现"负证据落在这格、可见性落在隔壁格"。
  void markVisibleAlongRay(int x0, int y0, int x1, int y1, double shadow_cells)
  {
    const int gw = perception_geo_.fine_width;
    const int gh = perception_geo_.fine_height;
    if (gw <= 0 || gh <= 0) {return;}
    if (visible_mask_.size() != static_cast<size_t>(gw) * gh) {
      visible_mask_.assign(static_cast<size_t>(gw) * gh, 0);
    }
    int dx = std::abs(x1 - x0), sx = (x0 < x1) ? 1 : -1;
    int dy = -std::abs(y1 - y0), sy = (y0 < y1) ? 1 : -1;
    int err = dx + dy;
    int x = x0, y = y0;
    long steps = 0;
    // 阴影起点（格数，从相机地面投影算起）：超过它就看不见了。
    const long shadow_from = static_cast<long>(std::ceil(shadow_cells));
    while (true) {
      if (x == x1 && y == y1) {break;}   // 终点是障碍本身，不算"看见地面"
      if (steps >= shadow_from && shadow_from > 0) {break;}   // 进阴影区
      if (x >= 0 && y >= 0 && x < gw && y < gh) {
        visible_mask_[static_cast<size_t>(y) * gw + x] = 1;
      }
      const int e2 = 2 * err;
      if (e2 >= dy) {err += dy; x += sx;}
      if (e2 <= dx) {err += dx; y += sy;}
      ++steps;
      // 防御：坐标跑飞时退出（Bresenham 理论上必然终止，但输入若含 NaN 转换值会跑飞）
      if (steps > 4L * (gw + gh)) {break;}
    }
  }

  // 一个角度箱内障碍高度的**稳健值**：取 z 的中位数（而非单个最近点）。
  // 样本太少（1 个）时退回该值本身；空样本退回 fallback。
  static double bin_robust_z(std::vector<double> & zs, double fallback)
  {
    if (zs.empty()) {return fallback;}
    const size_t mid = zs.size() / 2;
    std::nth_element(zs.begin(), zs.begin() + static_cast<std::ptrdiff_t>(mid), zs.end());
    return zs[mid];
  }

  // 证据层 → 规划层的几何关系（**整数倍**校验在这里集中做一次）。
  //
  // **为什么强制整除**：非整数倍（例如 0.5/0.2 = 2.5）会让聚合要么重复计入、
  // 要么漏计，且错位量随坐标漂移 —— 那种错误在指标上表现为"偶发的边界误差"，
  // 极难归因。参照实现（Nav2 的 `downsampling_factor`、RACER 的 `resolution *= 0.5`）
  // 都只能表达整数倍。这里宁可**拒绝启动**，也不静默用非整数倍跑。
  bool perceptionGeometry()
  {
    if (!(res_ > 0.0) || !(perception_resolution_ > 0.0)) {return false;}
    const double ratio = res_ / perception_resolution_;
    const int factor = static_cast<int>(std::lround(ratio));
    if (factor < 1 || std::fabs(ratio - static_cast<double>(factor)) > 1e-6) {return false;}
    const int fw = static_cast<int>(std::lround(sx_ / perception_resolution_));
    const int fh = static_cast<int>(std::lround(sy_ / perception_resolution_));
    if (fw <= 0 || fh <= 0) {return false;}
    perception_geo_.fine_resolution = perception_resolution_;
    perception_geo_.fine_width = fw;
    perception_geo_.fine_height = fh;
    perception_geo_.fine_origin_x = ox_;
    perception_geo_.fine_origin_y = oy_;
    perception_geo_.factor = factor;
    res_factor_ = factor;
    return perception_geo_.valid();
  }

  // 累积层的惰性初始化（两个订阅者共用；尺寸必须从**几何参数**算，
  // 不能用 grid_.width/height —— 首帧时它还是 0，会建成 0×0 空层）。
  //
  // **ADR-0040 起累积层建在证据分辨率上**（`perception_geo_`），不再是规划分辨率：
  // 0.5 m 只是规划消费格式，不再同时承担感知表达。
  void ensureAccum()
  {
    if (!perceptionGeometry()) {return;}
    const int gw = perception_geo_.fine_width;
    const int gh = perception_geo_.fine_height;
    if (gw <= 0 || gh <= 0) {return;}
    if (!accum_.empty() && accum_.width() == gw && accum_.height() == gh) {return;}
    agc_perception::LogOddsParams lp;
    lp.p_hit = log_odds_p_hit_;
    lp.p_miss = log_odds_p_miss_;
    lp.p_decay = log_odds_p_decay_;
    lp.occupied_threshold = log_odds_occ_thr_;
    lp.min_hit_points_per_cell = min_hit_points_per_cell_;
    lp.max_hit_z_spread_m = max_hit_z_spread_m_;
    lp.depth_mad_k = depth_mad_k_;
    lp.depth_consistency_floor_m = depth_consistency_floor_m_;
    lp.min_hits_for_occupied = min_hits_for_occupied_;
    lp.occluder_min_confidence = occluder_min_confidence_;
    lp.unknown_floor_p = unknown_floor_p_;
    lp.occupied_expire_frames = expire_frames();
    // 逐点不确定度门控（ADR-0042）：按证据层格宽换算，不写死米数。
    lp.cell_size_m = perception_resolution_;
    lp.sigma_reject_ratio = sigma_reject_ratio_;
    accum_.reset(gw, gh, lp);
  }

  // 旧 OBB 通道（/agc/obstacles）：**只刷新源时效，不再产生任何地图内容**。
  //
  // **2026-11-08 用户裁定 Q7（批次 3）**：障碍表示已由"连通域 → 外接框"改为"足迹点"。
  // 保留本订阅的唯一理由是**兼容性诊断**：`/agc/map/valid` 的时效判据仍看
  // "感知源是否活着"，而两条通道来自同一节点、同频发布，任一条到达即证明链路新鲜。
  //
  // 为什么不再用 OBB 栅格化：框对 L 形/多栋/斜置实体必然包大（实测 1.65×，
  // 最差 14×35.5 m、fill=0.30），且框边界随"连通域恰好切在哪"跳变。
  // 保留它同时栅格化等于**用更差的表示覆盖更好的表示**。
  void onObstacles(const agc_msgs::msg::ObstacleTrackArray & msg)
  {
    (void)msg;
    have_source_ = true;
    last_source_s_ = now().seconds();
  }

  // 知识时效：感知源是否仍支撑当前障碍内容。
  // 完全替代静态先验后，只有「收到过 /agc/obstacles 且源静默不超过 source_max_age_s_」才算新鲜；
  // 链路断供时 /agc/map/valid=false（不恒 true），地图开洞为已登记边界而非静默陈旧。
  bool knowledge_current()
  {
    return have_source_ && (now().seconds() - last_source_s_) <= source_max_age_s_;
  }

  // ---- 证据更新 → 状态快照 → 发布快照（2026-11-09 用户裁定：职责分离）----
  //
  // 改造前 `rebuild()` 同时承担五件事：生成 snapshot、推进 occupied 迟滞、
  // 比较发布数据、更新 hash、更新 update_seq —— 而它在**感知回调（10 Hz）**里也被调用，
  // 于是迟滞状态按 10 Hz 推进、对外地图按 2 Hz 发布：两次发布之间的
  // occupied→non→occupied 翻转被内部吃掉，对外只留一个状态。
  //
  // 现在明确成两拍：
  //   * 证据更新拍（感知回调）：只改累积层与诊断计数，**不生成快照、不推进迟滞**；
  //   * 地图拍（timer，`rate_hz`）：`rebuild()` 生成快照 → 比较 → 必要时发布。
  // 迟滞状态**按地图帧推进**，与 `perception_quality.py` 按 `/agc/map` 帧统计稳定性的口径一致。
  bool rebuild()
  {
    const int width = static_cast<int>(std::lround(sx_ / res_));
    const int height = static_cast<int>(std::lround(sy_ / res_));
    if (res_ <= 0.0 || width <= 0 || height <= 0) {
      geometry_ok_ = false;
      grid_.valid = false;
      RCLCPP_ERROR(get_logger(), "地图几何无效：res=%g size=(%g,%g)", res_, sx_, sy_);
      publishValid(false);
      return false;
    }
    geometry_ok_ = true;

    // 栅格内容**只来自累积层**（log-odds 证据）。静态先验 / 动态轨集合已随
    // ADR-0035 (b) 整体退役（它们曾只用于诊断计数，不再决定任何栅格内容，
    // 保留成员等于留一个"顺手接回来"的入口）。
    std::vector<int8_t> data;
    if (!accum_.empty() && perception_geo_.valid()) {
      // **地图帧推进**（ADR-0039 补正）：`min_hits_for_occupied` 的计数单位是地图帧，
      // 不是感知帧。这里（`rebuild()` = 发布拍）与 `occupied_now_` 是同一个时钟，
      // 确认门槛的语义因此与对外 `/agc/map` 一致（2 Hz 下的"K 帧"真的是 K 次发布）。
      accum_.beginMapFrame(++map_frame_idx_);
      // **复用缓冲的快照**：发布热路径不再每拍新建整张栅格（零分配）。
      // 这里是**证据层**快照（0.25 m），不是对外地图。
      const std::vector<int8_t> & snap = accum_.snapshotIntoBuffer();
      std::vector<int8_t> fine(snap.begin(), snap.end());
      // **发布值量化（deadband）**（2026-11-09 用户裁定）：中间概率按 `publish_deadband`
      // 的步长量化后再比较/发布。否则任一格从 48 变 47 就让整图"变化"并重新发布。
      // 两端语义不受影响：0 / 100 / -1 原样保留（量化只作用于 1–99）。
      //
      // **注意口径（用户裁定）**：deadband 只减少消息与 hash 的更新频率，
      // **不是**稳定性 p99 的手段 —— `perception_quality.py` 把 1–99 一律算 unknown，
      // 只有 99/中间值 ↔ 100 的跨门限翻转才影响该指标。
      //
      // **ADR-0040**：量化在**证据层**做（在派生之前）。理由：deadband 的作用是
      // 减少"同一概率附近来回微调"引起的消息更新；若放到派生之后，证据层的
      // 微调会先改变 max-pool 结果、再被量化，等于让量化无法抑制它。
      const int step = std::max(1, std::min(99, publish_deadband_));
      for (auto & v : fine) {
        if (v <= 0 || v >= 100) {continue;}     // free / unknown / occupied 原样
        v = static_cast<int8_t>(((v + step / 2) / step) * step);
        v = static_cast<int8_t>(std::min(99, std::max(1, static_cast<int>(v))));
      }
      // ---- 实例层并入证据层（ADR-0041）：并集，不是替换 ----
      //
      // 逐点累积能跨帧合并（画幅切碎的大建筑天然长回去），但拿不到"这些点属于
      // 同一个障碍"；实例层补的正是后者。取并集让两边各补对方缺的那一半。
      // 实例格直接写 100：它们**已过 `confirmed` 门槛**（至少被观测到 N 帧），
      // 与逐点证据的 `occupied_threshold` 是同一"已确认"语义。
      if (instances_enabled_) {
        stampConfirmedInstances();
        for (size_t idx : instance_cells_) {
          if (idx < fine.size()) {fine[idx] = 100;}
        }
      }
      // 证据层快照**留到发布**（ADR-0042）：`fine` 是几何重建的权威表达，
      // 评价必须能在它上面做，而不是永远只看 0.5 m 的派生结果。
      // 拷贝到成员缓冲（不 move）：下面派生还要读它。
      evidence_snapshot_ = fine;
      // **派生规划层**（ADR-0040）：max-pool + 保守四态合并，尺寸回到 0.5 m。
      std::vector<int8_t> occupied_grid =
        agc_perception::planningSnapshot(perception_geo_, fine);
      // ---- 规划风险图（ADR-0041，temp.md 方向四 C）----
      //
      // `/agc/map` 不再输出"裸占据"，而是**风险分档**：几何占据 + 米制安全膨胀
      // 共同决定这一格是否该禁止通行。理由（temp.md 原话）：`100 = occupied`
      // 同时承担"感知认为这里有障碍"与"规划器必须不可通行"两种语义，
      // 而对 0.5 m 格里的小障碍这两者不该等价。
      //
      // **未知格必须保持 -1**：距离场只对有占据的图有意义；把未观测区按距离
      // 判成 free 是对规划器的过度承诺（与 ADR-0035 的三态纪律一致）。
      data = occupied_grid;
      if (risk_enabled_ && occupied_grid.size() == static_cast<size_t>(width) * height) {
        std::vector<uint8_t> occupied_mask(occupied_grid.size(), 0);
        for (size_t i = 0; i < occupied_grid.size(); ++i) {
          occupied_mask[i] = (occupied_grid[i] >= 100) ? 1 : 0;
        }
        const std::vector<float> dist = agc_perception::distanceFieldMeters(
          width, height, res_, occupied_mask);
        agc_perception::InflationParams ip;
        ip.robot_radius_m = inflation_robot_radius_m_;
        ip.inflation_radius_m = inflation_radius_m_;
        for (size_t i = 0; i < data.size(); ++i) {
          const int8_t geom = occupied_grid[i];
          if (geom < 0) {data[i] = -1; continue;}   // 未知保持未知
          const agc_perception::PlanRisk r =
            agc_perception::classifyRisk(dist[i], ip);
          data[i] = agc_perception::riskToGridValue(r, dist[i], ip, risk_cost_scaling_);
        }
      }
      if (data.size() != static_cast<size_t>(width) * height) {
        // 证据层几何与规划层几何不一致（分辨率非整数倍等）：**不发布半张图**。
        RCLCPP_ERROR(get_logger(),
          "证据层 → 规划层派生失败（fine=%dx%d factor=%d coarse=%dx%d 期望=%dx%d）；"
          "perception_resolution=%.3f 必须是 resolution=%.3f 的整数分之一",
          perception_geo_.fine_width, perception_geo_.fine_height, res_factor_,
          perception_geo_.coarseWidth(), perception_geo_.coarseHeight(),
          width, height, perception_resolution_, res_);
        geometry_ok_ = false;
        publishValid(false);
        return false;
      }
    } else {
      // 累积层尚未初始化（首帧或几何无效）：退回"全 unknown"，不画任何障碍
      data.assign(static_cast<size_t>(width) * height, -1);
    }
    if (built_ && data == grid_.data) {
      // 栅格无实质变化 -> 不重建（`tick` 仍会按 rate_hz 发布当前内容）
      ++unchanged_rebuilds_;
      return false;
    }

    grid_.resolution = res_;
    grid_.width = width;
    grid_.height = height;
    grid_.origin_x = ox_;
    grid_.origin_y = oy_;
    grid_.data = std::move(data);
    grid_.occupied = std::count(grid_.data.begin(), grid_.data.end(), static_cast<int8_t>(100));
    grid_.hash = contentIdentityHash(grid_.data, width, height);
    grid_.valid = true;
    built_ = true;
    ++update_seq_;   // 实质重建 -> 单调更新序号 +1（ADR-0007）
    // **2026-11-09 诊断（用户裁定 Q4/Q5）**：把"负证据的量"与"翻转的量"直接报出来。
    // 归因用途（不再靠猜）：
    //   * `carve/unique_hit` 比值接近或超过 1 → carving 在啃障碍自身（误覆盖的候选根因 b）；
    //   * `up/down` 都大 → log-odds 门限附近的格在 100 与 1–99 间翻转（跳变根因 b）；
    //   * `up` 大而 `down` 小 → 新进入画幅的障碍（跳变根因 a，**合法增长**，不是缺陷）。
    //
    // **口径修正（2026-11-09 用户裁定）**：`hit` 的分母必须是**唯一栅格数**
    // （`unique_hit`），不是原始 footprint 点数 —— 后者随像素采样密度放大，
    // 会把 `carve/hit` 系统性低估。三量分开报：原始点数 / 唯一格数 / 重复点数。
    const long occ_now = static_cast<long>(grid_.occupied);
    const long occ_prev = last_logged_occupied_;
    const long d_up = (occ_prev >= 0) ? std::max(0L, occ_now - occ_prev) : 0;
    const long d_down = (occ_prev >= 0) ? std::max(0L, occ_prev - occ_now) : 0;
    const double carve_ratio = (footprint_hits_ > 0)
      ? static_cast<double>(carve_cells_) / static_cast<double>(footprint_hits_) : 0.0;
    RCLCPP_INFO(get_logger(),
      "map 重建：%dx%d @ %.3f m, occupied=%ld, seq=%llu, hash=%s（source=%s）"
      " | 诊断 unique_hit=%ld points=%ld dup=%ld carve=%ld carve/unique_hit=%.2f"
      " up=%ld down=%ld evidence=%zu"
      " rays[hit=%ld edge=%ld shadow_skip=%ld] cam_h=%.2f fp=%.1fx%.1f"
      " | 同步 dt_odom=%.3fs 缺位姿帧=%ld 可信半径=%.1fm"
      " | 拒点=%ld 弱支持格=%ld 跳过hit帧=%ld 画幅异常帧=%ld 证据帧=%ld"
      " | 协方差帧=%ld σ拒格=%ld",
      grid_.width, grid_.height, grid_.resolution, grid_.occupied,
      static_cast<unsigned long long>(update_seq_), grid_.hash.c_str(),
      obstacle_source_.c_str(),
      footprint_hits_, footprint_points_, footprint_dups_, carve_cells_, carve_ratio,
      d_up, d_down, accum_.evidenceCount(),
      last_rays_hit_, last_rays_edge_, last_shadow_skipped_, last_cam_h_,
      last_fp_half_x_, last_fp_half_y_, last_odom_dt_s_, odom_missing_frames_,
      last_trusted_r_, hit_rejected_, hit_weak_cells_, hit_skipped_frames_,
      implausible_fp_frames_, evidence_frames_,
      frames_with_cov_, sigma_rejected_cells_);
    last_logged_occupied_ = occ_now;
    return true;
  }

  // 内容身份 hash：把**几何元数据与源版本**与 data 字节一并折叠（**不只** data 字节串）。
  // 组装顺序（须与核查脚本一致，见 ADR-0007）：
  // frame_id/NUL, obstacles_source/NUL, scenario_version/NUL,
  // resolution(8B), width(8B), height(8B), origin_x(8B), origin_y(8B), data...
  // double/uint64 按**本机 IEEE-754 binary64 / little-endian 内存字节**直接喂入（本项目全链同机
  // 同架构，字节序稳定；避免文本格式化的精度 / 舍入歧义）。
  std::string contentIdentityHash(
    const std::vector<int8_t> & data, int width, int height) const
  {
    std::vector<int8_t> blob;
    blob.reserve(data.size() + 128);
    auto appendStr = [&blob](const std::string & s) {
        for (char c : s) {blob.push_back(static_cast<int8_t>(c));}
        blob.push_back(0);
      };
    auto appendRaw = [&blob](const void * p, size_t n) {
        const uint8_t * b = static_cast<const uint8_t *>(p);
        for (size_t i = 0; i < n; ++i) {blob.push_back(static_cast<int8_t>(b[i]));}
      };
    auto appendDouble = [&appendRaw](double v) {
        uint8_t b[8];
        std::memcpy(b, &v, sizeof(b));
        appendRaw(b, sizeof(b));
      };
    appendStr(world_frame_);       // frame_id
    appendStr(obstacle_source_);   // 障碍源版本（恒 config；参数保留仅为 hash 兼容）
    appendStr(scenario_version_);  // 场景版本（run config）
    appendDouble(res_);            // resolution
    const uint64_t w = static_cast<uint64_t>(width), h = static_cast<uint64_t>(height);
    appendRaw(&w, sizeof(w));
    appendRaw(&h, sizeof(h));
    appendDouble(ox_);             // origin_x
    appendDouble(oy_);             // origin_y
    for (int8_t v : data) {blob.push_back(v);}   // data 字节
    return hashBytes(blob);        // 复用底层字节哈希工具
  }

  void publishMap()
  {
    if (!grid_.valid) {publishValid(false); return;}
    const rclcpp::Time stamp = now();
    nav_msgs::msg::OccupancyGrid msg;
    msg.header.stamp = stamp;
    msg.header.frame_id = world_frame_;
    msg.info.resolution = grid_.resolution;
    msg.info.width = static_cast<uint32_t>(grid_.width);
    msg.info.height = static_cast<uint32_t>(grid_.height);
    msg.info.origin.position.x = grid_.origin_x;
    msg.info.origin.position.y = grid_.origin_y;
    msg.info.origin.position.z = 0.0;
    msg.info.origin.orientation.w = 1.0;
    msg.data = grid_.data;
    pub_->publish(msg);
    publishEvidenceLayer(stamp);
    publishCellMeta(stamp);
    if (grid_.hash != last_hash_) {
      last_hash_ = grid_.hash;
      std_msgs::msg::String h;
      h.data = grid_.hash;
      hash_pub_->publish(h);
    }
    // 单调更新序号（latched 诊断；与内容 hash 分别可查询）
    std_msgs::msg::UInt64 seq;
    seq.data = update_seq_;
    seq_pub_->publish(seq);
    publishValid(geometry_ok_ && knowledge_current());   // valid = 几何 && 知识时效（ADR-0007）
  }

  // 证据层地图（ADR-0042）：几何重建的权威表达，分辨率 = `perception_resolution`。
  //
  // **为什么不带风险分档 / 实例并集 / max-pool**：那些都属于"规划消费格式"。
  // 混进来的话，评价器量到的就不再是"感知重建得多准"，而是"安全膨胀得多保守"——
  // 而那正是 temp.md 指出的口径错误（把 FP 记在膨胀头上）。
  void publishEvidenceLayer(const rclcpp::Time & stamp)
  {
    if (evidence_snapshot_.empty() || !perception_geo_.valid()) {return;}
    nav_msgs::msg::OccupancyGrid msg;
    msg.header.stamp = stamp;
    msg.header.frame_id = world_frame_;
    msg.info.resolution = perception_geo_.fine_resolution;
    msg.info.width = static_cast<uint32_t>(perception_geo_.fine_width);
    msg.info.height = static_cast<uint32_t>(perception_geo_.fine_height);
    msg.info.origin.position.x = perception_geo_.fine_origin_x;
    msg.info.origin.position.y = perception_geo_.fine_origin_y;
    msg.info.origin.position.z = 0.0;
    msg.info.origin.orientation.w = 1.0;
    msg.data = evidence_snapshot_;
    evidence_pub_->publish(msg);
  }

  // 逐格元数据发布（ADR-0042；temp.md 方向一 + 方向四 A/B）。
  //
  // **它回答的是 `OccupancyGrid.data` 回答不了的问题**：
  //   * A 几何占据图：这一格**被占了多少**（0..1），不是"算不算占据"；
  //   * B 感知置信图：这个判断**有多可靠**（0..1），与"占了多少"正交；
  //   * 最近观测：多久没再看到它（时间，不是帧号 —— 帧率会漂）；
  //   * 来源实例：这一格的占据证据归谁；
  //   * 完整可见：`unknown` 是"没看过"还是"看到了但看不清"。
  //
  // **为什么用证据层几何而不是规划层**：这些量都是**几何/证据**属性。
  // 放到 0.5 m 上会先被 max-pool 抹平（一格只剩一个二值），
  // 那就又回到"表达不了 31%"的原点。
  void publishCellMeta(const rclcpp::Time & stamp)
  {
    if (!perception_geo_.valid() || evidence_snapshot_.empty()) {return;}
    const int w = perception_geo_.fine_width;
    const int h = perception_geo_.fine_height;
    const size_t n = static_cast<size_t>(w) * h;
    if (evidence_snapshot_.size() != n) {return;}

    agc_msgs::msg::PerceptionCellMeta msg;
    msg.header.stamp = stamp;
    msg.header.frame_id = world_frame_;
    msg.width = static_cast<uint32_t>(w);
    msg.height = static_cast<uint32_t>(h);
    msg.resolution = static_cast<float>(perception_geo_.fine_resolution);
    msg.origin_x = perception_geo_.fine_origin_x;
    msg.origin_y = perception_geo_.fine_origin_y;
    msg.occupancy_ratio.assign(n, 0.0f);
    msg.confidence.assign(n, 0.0f);
    msg.last_seen_s.assign(n, -1.0f);
    msg.source_instance_id.assign(n, -1);
    msg.fully_visible.assign(n, 0);

    // ---- A. 几何占据率：粗格内被占细格比例 ----
    // 这里直接对**证据层**逐格算"是否被占"，再用 `occupancyRatio` 在**规划层**聚合。
    // 注意 `occupancy_ratio` 数组是证据层尺寸，所以对证据层自己它就是 0/1；
    // 真正有信息量的是"这一格在它所属的 0.5 m 粗格里占了多少" —— 那才是
    // temp.md 要的"一个 0.5 m 格保存成占据比例 0.31"。
    auto fine_occupied = [this](size_t idx) {
        return evidence_snapshot_[idx] >= 100;
      };
    const int f = std::max(1, perception_geo_.factor);
    std::vector<float> coarse_ratio;
    if (f > 1) {
      coarse_ratio = agc_perception::occupancyRatioMap(perception_geo_, fine_occupied);
    }
    for (int y = 0; y < h; ++y) {
      for (int x = 0; x < w; ++x) {
        const size_t idx = static_cast<size_t>(y) * w + x;
        if (f > 1 && !coarse_ratio.empty()) {
          // 该细格所属粗格的占据率（同一粗格内所有细格共享这个值）
          const int cx = x / f, cy = y / f;
          const size_t cidx = static_cast<size_t>(cy) * perception_geo_.coarseWidth() + cx;
          if (cidx < coarse_ratio.size()) {msg.occupancy_ratio[idx] = coarse_ratio[cidx];}
        } else {
          msg.occupancy_ratio[idx] = fine_occupied(idx) ? 1.0f : 0.0f;
        }
        // ---- B. 感知置信度 ----
        //
        // **两条来源取较大者**：逐点累积（`confidenceAt`，按观测次数）与
        // 实例层（`instance_cell_confidence`，按实例确认次数）。
        // 取最大而不是相加：两者是**同一个量的两条证据路径**，
        // 相加会让"既有逐点命中、又有实例覆盖"的格得到 >1 的置信度。
        // 任一来源足够可信时，这一格的判断就是可信的。
        const double conf_lodds = accum_.confidenceAt(idx);
        const double conf_inst = (idx < instance_cell_confidence_.size())
          ? static_cast<double>(instance_cell_confidence_[idx]) : 0.0;
        msg.confidence[idx] = static_cast<float>(std::max(conf_lodds, conf_inst));
        // ---- 最近观测（帧号 → 秒，用实测帧率换算）----
        const long lf = accum_.lastSeenFrameAt(idx);
        if (lf >= 0 && observed_frame_hz_ > 0.0) {
          const double age_frames = static_cast<double>(accum_.currentFrame() - lf);
          msg.last_seen_s[idx] = static_cast<float>(age_frames / observed_frame_hz_);
        }
        // ---- 完整可见 ----
        const bool vis = (visible_mask_.size() == n) && (visible_mask_[idx] != 0);
        msg.fully_visible[idx] = vis ? 1 : 0;
        // ---- 来源实例：该格若被某个已确认实例覆盖，记它的 id ----
        msg.source_instance_id[idx] = instance_cell_owner_[idx];
      }
    }
    // ---- 实例可见性（temp.md 方向三）----
    for (const auto & inst : instances_.instances()) {
      if (inst.visible) {msg.visible_instance_id.push_back(inst.id);}
    }
    cell_meta_pub_->publish(msg);
  }

  void publishValid(bool ok)
  {
    std_msgs::msg::Bool m;
    m.data = ok;
    valid_pub_->publish(m);
  }

  // 每拍：重建 + 发布。
  //
  // **2026-11-08（批次 3）**：这里原本先调 `expireDynamic()`（动态轨过期→覆盖格置 unknown）。
  // 那条语义在改成 log-odds 累积后**已无任何作用**（rebuild 不再读 live_/unknown_idx_），
  // 属"看着有时效保证、实际没有"的死逻辑，随批次 3 一并删除。
  // 现在的地图时效由两件事表达：`log_odds_p_decay`（证据随时间变弱）与
  // `/agc/map/valid`（感知源是否新鲜）—— 两者都是真的在起作用。
  void tick()
  {
    // **地图拍**（2026-11-09 用户裁定）：证据更新在感知回调里做，快照生成与发布只在这里做。
    // 改造前感知回调里 `if (rebuild()) publishMap();` 让地图实际按感知帧率（10 Hz）
    // 重建与发布，而 `rate_hz=2.0` 只控制 timer —— 配置与实际行为不一致，
    // 消费者看到的地图更新频率是设计值的 5 倍。
    //
    // `rebuild()` 内含 `snapshot()`，而 `snapshot()` 推进 `occupied_now_`（迟滞记忆）。
    // 因此**迟滞状态按地图帧推进**：与 `perception_quality.py` 按 `/agc/map` 帧
    // 统计稳定性的口径一致，不会出现"内部 10 Hz 翻转、对外 2 Hz 只留一个状态"。
    const bool changed = rebuild();
    publishMap();
    if (changed) {++published_changes_;}
  }

  struct Grid
  {
    bool valid{false};
    std::vector<int8_t> data;
    int width{0}, height{0};
    double resolution{0.0}, origin_x{0.0}, origin_y{0.0};
    long occupied{0};
    std::string hash;
  };

  std::string world_frame_, map_file_, obstacle_source_, map_topic_;
  std::string evidence_topic_;
  std::string cell_meta_topic_;
  std::string scenario_version_, update_seq_topic_;   // 场景/源版本 与 单调更新序号话题（ADR-0007）
  agc_perception::LogOddsGrid accum_;
  double log_odds_p_hit_{0.70};
  double log_odds_p_miss_{0.25};   // 与 LogOddsParams::p_miss 缺省同值（见 perception.yaml）
  double log_odds_occ_thr_{0.60};
  double log_odds_p_decay_{0.48};
  int publish_deadband_{5};                 // 发布值量化步长（1 = 不量化）
  bool decay_inside_footprint_only_{true};  // 视野外不参与时间衰减
  long unchanged_rebuilds_{0};              // 无实质变化的重建次数（诊断）
  long decay_skipped_frames_{0};            // 画幅不可用而跳过衰减的帧数（诊断）
  long hit_skipped_frames_{0};              // 无位姿/姿态异常而跳过 hit 的帧数（诊断）
  long implausible_fp_frames_{0};           // 画幅不合理（大前倾/退化）的帧数（诊断）
  long hit_rejected_{0};                    // 被可信半径拒掉的足迹点数（诊断）
  long published_changes_{0};               // 实际发布次数（诊断）
  // free-space carving（2026-11-08 Q3）：相机地面投影 + 射程上限 + 诊断计数
  bool carve_enabled_{true};
  std::string odom_topic_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr sub_odom_;
  // 相机位姿与内参：**与投影端同一份定义**（`camera_geometry.hpp` 不依赖 OpenCV，
  // 因此 map_adapter 不需要为几何拉进 OpenCV 依赖，也就不再需要本地复制一份常量）。
  std::deque<agc_perception::PoseSample> odom_buf_;
  bool have_odom_{false};
  double odom_tol_s_{0.15};
  int odom_buffer_n_{120};
  double last_odom_dt_s_{0.0};
  long odom_missing_frames_{0};
  long odom_extrapolated_frames_{0};
  // 相机内参（画幅从它推导，不写死 hfov —— 避免与 SDF 静默漂移）
  std::string cam_info_topic_;
  agc_perception::CamIntrinsics cam_intrinsics_;
  int cam_w_{0}, cam_h_{0};
  bool have_cam_info_{false};
  rclcpp::Subscription<sensor_msgs::msg::CameraInfo>::SharedPtr sub_cam_info_;
  // 诊断（2026-11-09）：负证据射线统计，用于查"误覆盖"与"跳变"的归因
  long carve_calls_{0};
  long last_rays_hit_{0};
  long last_rays_edge_{0};
  long last_shadow_skipped_{0};
  long last_logged_occupied_{-1};   // 上一次日志时的 occupied（算 up/down）
  // 观测空窗衰减（Q19）
  double stale_after_s_{3.0};
  // occupied 生命周期（ADR-0039）：超过该时长没有正向 hit ⇒ 削弱并退出 occupied
  double occupied_expire_s_{3.0};
  double unknown_floor_p_{0.22};
  // 空间/时间支持门槛（ADR-0039）
  int min_hit_points_per_cell_{3};
  double max_hit_z_spread_m_{1.5};
  double depth_mad_k_{3.0};
  double depth_consistency_floor_m_{0.30};
  double last_misalign_m_{0.0};   // 上一帧的错位不确定度（诊断）
  int min_hits_for_occupied_{2};
  double occluder_min_confidence_{0.60};
  long hit_weak_cells_{0};   // 上一帧被空间支持门槛拒掉的**格**数（诊断）
  long frame_idx_{0};
  long map_frame_idx_{0};   // 地图帧（发布拍）序号：min_hits_for_occupied 的计数单位
  double observed_frame_hz_{10.0};   // 实测帧率（由时间戳算，不写死）
  double last_fp_arrival_s_{-1.0};
  // 本帧障碍格掩码（carve 时跳过，避免宽障碍被自己擦掉）。**复用同一块缓冲**。
  std::vector<char> obstacle_mask_;
  // 本帧命中过的**唯一格索引**（去重结果，供诊断与后续复用）
  std::vector<size_t> hit_cells_;
  // 本帧被足迹点碰过的**候选格索引**（空间支持门槛的判据对象；复用缓冲，不每帧分配）
  std::vector<size_t> candidate_cells_;
  double last_fp_half_x_{0.0}, last_fp_half_y_{0.0};   // 上一次画幅（诊断）
  double last_cam_h_{0.0};                             // 上一次相机离地高度（诊断）
  double last_trusted_r_{0.0};                         // 上一次可信测量半径（诊断）
  double carve_max_range_m_{0.0};   // 0 = 不限
  long carve_cells_{0};             // 累计 carve 格数（诊断）
  std::string footprint_topic_;
  rclcpp::Subscription<agc_msgs::msg::ObstacleFootprintArray>::SharedPtr sub_footprints_;
  // 三项诊断口径**必须分开**（2026-11-09 用户裁定）：合并成一个数会让
  // carve/hit 的分母随像素采样密度放大，把负证据强度系统性低估。
  long footprint_hits_{0};          // 累计**唯一格**命中数（carve/hit 的分母）
  long footprint_points_{0};        // 累计原始足迹点数（可信半径/越界过滤之后）
  long footprint_dups_{0};          // 累计落在已见过格上的重复点数
  long evidence_frames_{0};         // 证据更新拍数（与地图拍分离，诊断用）
  double rate_hz_{2.0};
  double source_max_age_s_{1.0};
  double res_{0.5}, sx_{0.0}, sy_{0.0}, ox_{0.0}, oy_{0.0};
  // ---- 多分辨率（ADR-0040）----
  // `res_` 是**规划层**分辨率（= 地图文件的 `resolution`，`/agc/map` 的
  // `info.resolution`，契约不变）。`perception_resolution_` 是**证据层**分辨率，
  // 累积与 carving 全部在它上面做；规划层由它派生。
  double perception_resolution_{0.25};
  // 证据层 → 规划层的整数倍关系（必须整除；见 `perceptionGeometry()`）。
  int res_factor_{2};
  double inflation_robot_radius_m_{0.6};
  double inflation_radius_m_{1.0};
  // 证据层几何（累积层尺寸从它算，**不用** grid_.width/height —— 见 ensureAccum）
  agc_perception::MultiResGeometry perception_geo_;
  // ---- 障碍实例层（ADR-0041）----
  bool instances_enabled_{true};
  int instance_confirm_hits_{2};
  int instance_expire_misses_{3};
  double instance_associate_gate_m_{1.5};
  int instance_track_points_{50};
  agc_perception::InstanceTracker instances_;
  // 本帧按 id 分组的点（复用缓冲，不每帧分配外层容器）
  std::vector<std::string> instance_ids_;
  std::vector<std::vector<double>> instance_group_xs_;
  std::vector<std::vector<double>> instance_group_ys_;
  std::vector<std::vector<double>> instance_group_zs_;
  // 已确认实例栅格化后的证据层格索引（复用缓冲）
  std::vector<size_t> instance_cells_;
  // ---- 规划风险图（ADR-0041）----
  bool risk_enabled_{true};
  double risk_cost_scaling_{3.0};
  // 逐点不确定度门控比例（ADR-0042）：σ > ratio×格宽 的点不进 hit 证据。0 = 关闭。
  double sigma_reject_ratio_{0.5};
  long frames_with_cov_{0};       // 带逐点协方差的帧数（诊断）
  long sigma_rejected_cells_{0};  // 被 σ 门控拒掉的格数（诊断）
  long instance_tracked_{0};      // 本帧参与跟踪的实例数（诊断）
  long instance_confirmed_{0};    // 其中已确认的（诊断）

  bool built_{false};
  bool geometry_ok_{false};
  bool have_source_{false};                        // 是否收到过 /agc/obstacles
  double last_source_s_{0.0};                      // 最近一次收到感知源的时刻
  uint64_t update_seq_{0};                         // 单调更新序号（实质重建 +1；ADR-0007）
  Grid grid_;
  // 证据层快照（ADR-0042）：`rebuild()` 里由 `fine` 拷贝而来，供 `/agc/map/evidence`
  // 发布。**不 move**：派生规划层还要读 `fine`。
  std::vector<int8_t> evidence_snapshot_;
  // 本帧"完整可见"掩码（ADR-0042）：证据层尺寸，1 = 看得见。
  // 每帧开头清空，由 `carveNegativeEvidence` 沿射线填。
  std::vector<char> visible_mask_;
  // 格 → 所属实例 id（-1 = 无归属）。证据层尺寸。
  std::vector<int> instance_cell_owner_;
  // 格 → 所属实例的**置信度**（ADR-0042）。
  //
  // **为什么需要它**：实例层直接往 `fine` 写 100，绕过了 `LogOddsGrid::observeHit`，
  // 于是那些格的 `hit_count_` 恒为 0 ⇒ `confidenceAt` 报 0。
  // 实测症状：`occupancy_ratio` 有 11040 个非零格，而 `confidence` 只有 220 个 ——
  // 占据率说"这里有障碍"、置信度说"我什么都不知道"，两者自相矛盾。
  // 实例格的可信度应当来自**实例自身**（它已过 confirm_hits 门槛）。
  std::vector<float> instance_cell_confidence_;
  // 每格最近一次观测的**帧号**（发布时按实测帧率换算成秒）。
  std::vector<long> last_seen_frame_;
  std::string last_hash_;

  rclcpp::Publisher<nav_msgs::msg::OccupancyGrid>::SharedPtr pub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr hash_pub_;
  rclcpp::Publisher<std_msgs::msg::UInt64>::SharedPtr seq_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr valid_pub_;
  rclcpp::Publisher<nav_msgs::msg::OccupancyGrid>::SharedPtr evidence_pub_;
  rclcpp::Publisher<agc_msgs::msg::PerceptionCellMeta>::SharedPtr cell_meta_pub_;
  rclcpp::Subscription<agc_msgs::msg::ObstacleTrackArray>::SharedPtr sub_obstacles_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<MapAdapter>());
  rclcpp::shutdown();
  return 0;
}
