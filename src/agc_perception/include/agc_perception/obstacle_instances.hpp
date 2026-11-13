// obstacle_instances —— 障碍**实例**的几何模型与生命周期（纯逻辑，不 include ROS）
//
// **为什么需要实例层**（temp.md 点名的第三类结构性问题）：
// 当前 `LogOddsGrid` 只知道"格 index 12345 被 hit"，不知道：
//   * 这个 hit 属于哪个障碍；
//   * 与旁边格是否属于同一个障碍；
//   * 它是障碍中心、边界还是错误外溢；
//   * 该障碍的几何形状是什么。
// 于是 dense_map 的小障碍（0.5 m 格下只有 1–3 格宽）出现：
//   * 一个小障碍在多个相邻格之间跳动；
//   * 相邻障碍互相"借格"；
//   * 边界点在不同帧落入不同格；
//   * 稳定性 p99 仍有 104 格。
// 而 `shape_jitter=0` 之所以"失去区分能力"，是因为该指标统计的是 OBB 形状，
// 而地图早已主要由 footprint 逐点累积产生 —— **形状稳定 ≠ 足迹稳定**。
//
// **解法**：把"格证据"升级成"实例几何 + 实例级生命周期"。
// 观测点集 → 实例拟合（圆/矩形）→ 实例级时间跟踪 → 稳定几何模型 → 栅格化。
//
// **参照结论（决定了下面对生命周期的取舍）**：
//   RACER 的 `GridInfo` 用**两个正交布尔**表达区域状态 —— `active_`（结构上存在）
//   与 `is_cur_relevant_`（内容上值得上报），并用 `is_prev_relevant_` / `is_cur_relevant_`
//   的**上升沿**表示"重新发现"事件。本文件照此形状：
//   * `alive`       —— 实例还在（有观测支撑）；
//   * `confirmed`   —— 实例已跨过确认门槛（可以进地图）；
//   * 二者的**上升沿**（`justConfirmed` / `revived`）才是事件，不是状态本身。
//
//   不采用 RACER 的 `frontier_num_` / `frontier_cell_nums_`：那两个字段在参照实现里
//   声明后从未被写入，是死字段（活跃判定实际用 `contained_frontier_ids_.empty()`）。
//   照抄死字段等于照抄一个不存在的行为。
//
// **本文件不做的**：不分配 id 给"格"（那是栅格层的事）、不做数据关联的启发式
// 调参（门限由调用方给，本文件只保证语义正确）、不碰 ROS 消息。

#ifndef AGC_PERCEPTION__OBSTACLE_INSTANCES_HPP_
#define AGC_PERCEPTION__OBSTACLE_INSTANCES_HPP_

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <limits>
#include <string>
#include <vector>

namespace agc_perception
{

// 实例的几何形状。只保留本仓场景需要的两种（dense_map 是 box + cylinder）；
// 不确定轮廓用"椭圆/置信度膨胀圆"表达，见 `ObstacleInstance::radius_m` 的注释。
enum class InstanceShape : uint8_t
{
  kUnknown = 0,   // 拟合尚未定形（点数不足 / 两轴尺度接近时无法判 box vs cylinder）
  kCircle = 1,    // 圆柱 / 球形：单一半径
  kBox = 2,       // 矩形（含正方形）：中心 + 半长 + 朝向
};

// 轨迹历史中的一个点（位置 + 观测时刻）。
//
// **为什么只存 x/y/t 不存完整几何**：历史要回答的是"它从哪来、动了多少"，
// 那是**位置**问题。把尺寸/朝向也存进来会让内存 ×3，而没有任何判据需要它
// （尺寸抖动已有 `shape_jitter` 与实例面积抖动两个独立指标）。
struct InstanceTrackPoint
{
  double stamp_s{0.0};
  double x{0.0}, y{0.0};
};

// 一个障碍实例的几何模型（**连续**，不是格）。
//
// 与"格"的根本区别：格是离散决策（这一格算不算占），实例是连续几何（中心在哪、
// 半径多少）。前者在 0.5 m 下只有 1–3 格宽、边界点一偏就翻格；后者的小数位移
// 不会改变"还是同一个障碍"这个判断。
struct ObstacleInstance
{
  int id{-1};                       // 稳定标识（跨帧不变，直到实例被回收）
  InstanceShape shape{InstanceShape::kUnknown};
  double cx{0.0}, cy{0.0};          // 中心（world，m）
  // 半径：kCircle 时是半径；kBox 时是**外接半径**（保守，用于规划侧的圆近似）。
  // 不确定轮廓也用它：`radius_m` 加上 `radius_sigma_m` 就是"置信度膨胀圆"。
  double radius_m{0.0};
  // 半长（仅 kBox 有意义）：沿 `yaw` 方向的半长 `half_x_m`、垂直方向 `half_y_m`。
  double half_x_m{0.0}, half_y_m{0.0};
  double yaw{0.0};                  // 朝向（rad，world）
  double z_min{0.0}, z_max{0.0};     // 高度包络（m）—— 供阴影/垂直门控用
  // 位置不确定度（m）：实例中心的 1σ 半径。用于"置信度膨胀圆"与评价口径
  // （中心误差应与此同量级；远大于它说明关联/拟合有问题）。
  double radius_sigma_m{0.0};
  // 拟合用到的观测点数（本帧或累计，由调用方决定语义；这里只存数）
  int support_points{0};
  // 置信度 [0,1]：**声明值**，由调用方按观测次数/一致性给出。
  // 不得把它当成"识别置信度" —— 本仓不训练检测器（见 confidence.hpp 的同一纪律）。
  double confidence{0.0};

  // ---- 生命周期（两个正交布尔，照 RACER 的 active_ / is_cur_relevant_ 形状）----
  bool alive{false};        // 结构上存在（还有观测支撑）
  bool confirmed{false};    // 内容上可信（已跨过确认门槛，可以进地图）
  // 本拍**是否被看到**（ADR-0042，temp.md 方向三"可见性状态"）。
  //
  // **与 `alive` 的区别**：`alive` 是"结构上还在"（miss 少于 expire 门槛就仍为真），
  // 而 `visible` 是"这一拍真的观测到了"。两者正交：
  //   * alive=true,  visible=true  → 正常跟踪中；
  //   * alive=true,  visible=false → 暂时被遮挡 / 出了画幅，实例仍在（靠几何模型撑着）；
  //   * alive=false                → 连续 miss 到门槛，已被回收。
  // 把两者合成一个布尔会让"暂时看不见"和"消失了"无法区分 ——
  // 前者不该撤销地图上的障碍，后者该。这正是 temp.md 要的"可见性状态"。
  bool visible{false};
  // 上一拍的两个布尔（用于**上升沿**检测："重新发现"是事件，不是状态）
  bool prev_alive{false};
  bool prev_confirmed{false};
  int hits{0};              // 累计被观测到的帧数
  int misses{0};            // 连续未被观测到的帧数

  // ---- 轨迹历史（ADR-0042，temp.md 方向三"实例轨迹历史"）----
  //
  // **为什么需要**：此前只存**当前**几何。于是无法回答"这个实例是从哪来的、
  // 移动了多少、是不是同一个物体被重新发现"。密集小障碍场景下这恰恰是关键：
  // 一个 0.6 m 的 box 在 0.5 m 格上抖动 1 格就等于"整个障碍挪了位置"，
  // 而"它其实没动"这个判断只能由历史给出。
  //
  // **参照结论**：RACER 的 `ObjHistory`（`obj_predictor.cpp`）用 `list<Vector4d>`
  // 存 `x,y,z,t`，`push_back` 后 `if (size > queue_size) pop_front()` ——
  // **有界、只增尾部、超界丢头部**。本仓照此形状（`std::deque` 前端淘汰），
  // 但不采用它的**用途**：RACER 用历史做多项式外推预测，本仓**不预测** ——
  // 小障碍的真实运动学未知，外推出来的位置是编的。历史只用于回答
  // "它动过多少"（诊断 / 稳定性）与"是不是重新发现"（生命周期）。
  //
  // **历史绝不参与栅格化**：栅格化用的是当前几何（`cx/cy/half_x/half_y`）。
  // 让历史影响栅格等于让"它曾经在哪"决定"现在哪格被占"，那是把记忆当观测。
  std::deque<InstanceTrackPoint> track;

  // 记录本拍的位置（由 `InstanceTracker` 在 absorb/spawn 后调用）。
  void pushTrackPoint(double stamp_s)
  {
    track.push_back(InstanceTrackPoint{stamp_s, cx, cy});
  }

  // 淘汰超过 `max_points` 的**头部**（保留最近的）。0 或负 ⇒ 不淘汰（调用方保证有界）。
  void trimTrack(size_t max_points)
  {
    if (max_points == 0) {return;}
    while (track.size() > max_points) {track.pop_front();}
  }

  // 历史位移总量（m）：沿轨迹**逐段累加**，不是首尾直线距离。
  //
  // **为什么不用首尾距离**：来回抖动 10 次又回到原点，首尾距离是 0，
  // 而实际"动了 10 次"——那正是要观测的抖动。逐段累加才反映真实运动量。
  double trackPathLength() const
  {
    double sum = 0.0;
    for (size_t i = 1; i < track.size(); ++i) {
      sum += std::hypot(track[i].x - track[i - 1].x, track[i].y - track[i - 1].y);
    }
    return sum;
  }

  // 历史时间跨度（s）：首尾时间差。空/单点 → 0。
  double trackSpanSeconds() const
  {
    if (track.size() < 2) {return 0.0;}
    return track.back().stamp_s - track.front().stamp_s;
  }

  // 上升沿：本拍刚被确认（prev_confirmed=false → confirmed=true）
  bool justConfirmed() const {return confirmed && !prev_confirmed;}
  // 上升沿：本拍刚被重新发现（prev_alive=false → alive=true）
  bool revived() const {return alive && !prev_alive;}
  // 下降沿：本拍刚失去结构存在性（alive=false 且上一拍还在）
  bool justDied() const {return !alive && prev_alive;}

  // 实例的**保守外接半径**：kBox 用对角半径，kCircle 用半径。
  //
  // **为什么规划侧用外接圆而不是矩形**：矩形栅格化会引入朝向依赖的量化误差
  // （同一障碍转 45° 覆盖的格数不同），而外接圆与朝向无关、且方向安全（只会高估）。
  // 代价是 box 被放大 —— 这是"规划层不代表真实几何"的又一处，评价不得在规划层做。
  double boundingRadius() const
  {
    if (shape == InstanceShape::kBox) {
      return std::hypot(half_x_m, half_y_m);
    }
    return radius_m;
  }
};

// 实例层参数（门限是**数值**，不是路线分支）。
struct InstanceParams
{
  // 一个实例至少被观测到这么多帧才算 confirmed。
  // 取 2：与 `LogOddsParams::min_hits_for_occupied` 同一"至少两帧"纪律 ——
  // 单帧毛刺不得变成地图上的障碍。
  int confirm_hits{2};
  // 连续这么多帧没被观测到 ⇒ alive=false（实例死亡）。
  // 取 3：与 `LogOddsParams::occupied_expire_frames` 的"3 秒 @10Hz≈30 帧"不同量级 ——
  // 实例级比格级更稳（实例有几何模型支撑，不该因一两帧漏检就消失），
  // 但也不能永不消失。3 帧 ≈ 0.3 s @10 Hz，是"确实连续丢了"的量级。
  int expire_misses{3};
  // 关联门（m）：观测与既有实例中心的距离超过它就不匹配（新建实例）。
  // 取 1.5：dense_map 的最小障碍间距是 2.3 m，取 1.5 m 不会把相邻障碍并成一个。
  double associate_gate_m{1.5};
  // 判 kCircle vs kBox 的尺度比容差：|half_x − half_y| / max ≤ 它即视为圆/方。
  // 取 0.25：0.6×0.6 m 的方 box 与 r=0.3 m 的圆柱在几何上本来就接近，
  // 强行区分没有信息增益（且会随噪声在两者间翻）。
  double shape_roundness_tolerance{0.25};

  // ---- 轨迹历史（ADR-0042）----
  // 每个实例最多保留这么多历史点。0 = **不记录**（退回"只存当前几何"的旧行为）。
  //
  // 取 50：@10 Hz 约 5 s。够看出"抖了几次、动了多少"，又不至于让 620 个障碍的
  // 历史吃光内存（50 × 24 B × 620 ≈ 0.75 MB）。参照实现 RACER 的 `queue_size_`
  // 也是同量级（按帧数而非秒数定）。
  size_t max_track_points{50};
  // 相邻历史点的**最小时间间隔**（s）。小于它就不记新点。
  //
  // **为什么需要**：同一拍内一个实例可能被 absorb 多次（多个观测落到同一实例）。
  // 不设间隔会让历史里堆满同一时刻的重复点，"位移总量"被同一拍的抖动重复计入。
  // 取 0 = 不限制（每拍都记）。
  double min_track_interval_s{0.0};
};

// 一个观测（本帧拟合出的候选实例，尚未分配 id）。
struct InstanceObservation
{
  double cx{0.0}, cy{0.0};
  double radius_m{0.0};
  double half_x_m{0.0}, half_y_m{0.0};
  double yaw{0.0};
  double z_min{0.0}, z_max{0.0};
  double radius_sigma_m{0.0};
  int support_points{0};
  InstanceShape shape{InstanceShape::kUnknown};
};

// 由观测的形状尺度判形状（不猜：两轴接近就报 kCircle，而不是硬报 kBox）。
//
// **为什么不默认 kBox**：矩形栅格化是朝向敏感的，而圆柱/近方的小障碍在 0.5 m 格上
// 判不出朝向；强行按 box 处理会让同一障碍的覆盖格数随 yaw 抖动 —— 那正是要修的抖动。
inline InstanceShape classifyShape(
  double half_x_m, double half_y_m, const InstanceParams & params)
{
  const double hx = std::fabs(half_x_m);
  const double hy = std::fabs(half_y_m);
  const double mx = std::max(hx, hy);
  if (mx <= 0.0) {return InstanceShape::kUnknown;}
  const double ratio = std::fabs(hx - hy) / mx;
  if (ratio <= params.shape_roundness_tolerance) {return InstanceShape::kCircle;}
  return InstanceShape::kBox;
}

// 实例层的**状态机**：吸收观测 → 关联 → 更新生命周期 → 回收死亡实例。
//
// 用法（每帧）：
//   1. `beginFrame()` 把 confirmed/alive 存进 prev_*（上升沿检测的前提）
//   2. 对每个观测调 `associate()` 找到匹配的实例下标（-1 = 新建）
//   3. 对匹配到的实例调 `absorb()`；对未匹配的实例调 `miss()`
//   4. 对未匹配的观测调 `spawn()`
//   5. 调 `expire()` 回收死亡实例
//
// **为什么 prev_* 必须在"更新前"整体快照**：上升沿的定义是"这一拍刚变"，
// 若在 absorb 里就地覆盖 prev_*，同一个实例在本拍内被更新两次（例如同一实例
// 吸收了多个观测）时，第二次会把 prev 覆盖成本拍的值，上升沿永久丢失。
class InstanceTracker
{
public:
  explicit InstanceTracker(const InstanceParams & params = InstanceParams{})
  : params_(params) {}

  void setParams(const InstanceParams & params) {params_ = params;}
  const InstanceParams & params() const {return params_;}

  // 注入本拍时刻（秒）。纯逻辑类不持时钟，由调用方在 `beginFrame()` 前设。
  // NaN = 未注入 ⇒ 不记录轨迹（见 `recordTrack`）。
  void setClock(double stamp_s) {clock_s_ = stamp_s;}

  const std::vector<ObstacleInstance> & instances() const {return instances_;}
  std::vector<ObstacleInstance> & mutableInstances() {return instances_;}

  void clear()
  {
    instances_.clear();
    next_id_ = 0;
  }

  // 拍首快照：把当前 alive/confirmed 存进 prev_*（上升沿判据的前提）。
  void beginFrame()
  {
    for (auto & inst : instances_) {
      inst.prev_alive = inst.alive;
      inst.prev_confirmed = inst.confirmed;
      // 可见性是**每拍**状态，必须先清掉再让 absorb 置位。
      // 忘了清会让"上一拍看见过"永远为真 —— 可见性退化成 alive 的同义词。
      inst.visible = false;
    }
  }

  // 最近邻关联：返回 instances_ 中的下标，-1 = 没有匹配。
  //
  // **只与 alive 的实例关联**：已死亡实例不该"抢走"新观测（否则 id 会复活到
  // 一个已经不在原处的目标上）。死亡实例由 `expire()` 物理移除。
  int associate(double x, double y) const
  {
    int best = -1;
    double best_d2 = params_.associate_gate_m * params_.associate_gate_m;
    for (size_t i = 0; i < instances_.size(); ++i) {
      const auto & inst = instances_[i];
      if (!inst.alive) {continue;}
      const double dx = x - inst.cx;
      const double dy = y - inst.cy;
      const double d2 = dx * dx + dy * dy;
      if (d2 <= best_d2) {
        best_d2 = d2;
        best = static_cast<int>(i);
      }
    }
    return best;
  }

  // 新建实例（id 单调递增，不复用 —— 复用会让下游按 id 键控的状态串台）。
  int spawn(const InstanceObservation & obs)
  {
    ObstacleInstance inst;
    inst.id = next_id_++;
    applyObservation(inst, obs);
    inst.alive = true;
    inst.visible = true;           // 刚出生 ⇒ 本拍必然被看到了
    inst.confirmed = false;
    inst.prev_alive = false;       // 本拍刚出生：prev 为 false
    inst.prev_confirmed = false;
    inst.hits = 1;
    inst.misses = 0;
    instances_.push_back(inst);
    recordTrack(instances_.back());
    refreshConfirmed(instances_.back());
    return instances_.back().id;
  }

  // 吸收一个观测到既有实例（几何用**指数滑动**而非直接覆盖，抑制单帧抖动）。
  void absorb(int index, const InstanceObservation & obs)
  {
    if (index < 0 || static_cast<size_t>(index) >= instances_.size()) {return;}
    auto & inst = instances_[static_cast<size_t>(index)];
    applyObservation(inst, obs);
    inst.alive = true;
    inst.visible = true;           // 本拍有观测支撑
    inst.misses = 0;
    ++inst.hits;
    recordTrack(inst);
    refreshConfirmed(inst);
  }

  // 本拍没有观测支撑（连续 miss 到阈值即 alive=false）。
  void miss(int index)
  {
    if (index < 0 || static_cast<size_t>(index) >= instances_.size()) {return;}
    auto & inst = instances_[static_cast<size_t>(index)];
    ++inst.misses;
    if (params_.expire_misses > 0 && inst.misses >= params_.expire_misses) {
      inst.alive = false;
      inst.confirmed = false;
    }
  }

  // 回收死亡实例（物理移除）。**必须在关联/吸收全部完成之后调** ——
  // 中途移除会让已返回的下标失效。
  size_t expire()
  {
    const size_t before = instances_.size();
    instances_.erase(
      std::remove_if(
        instances_.begin(), instances_.end(),
        [](const ObstacleInstance & i) {return !i.alive;}),
      instances_.end());
    return before - instances_.size();
  }

  // 已确认实例数（诊断 / 单测）。
  size_t confirmedCount() const
  {
    size_t n = 0;
    for (const auto & i : instances_) {
      if (i.confirmed) {++n;}
    }
    return n;
  }

private:
  // 记录一拍轨迹（ADR-0042）。
  //
  // **时间戳从哪来**：`InstanceTracker` 不持有时钟（它是纯逻辑，必须能脱离 ROS 单测）。
  // 故由调用方在 `beginFrame()` 之前用 `setClock()` 注入本拍时刻。
  // 未注入（clock 保持 NaN）时**不记录** —— 没有时刻的历史无法算跨度，
  // 也无法判断"两次记录是不是同一拍"，宁可空着也不写一堆无时间的点。
  void recordTrack(ObstacleInstance & inst)
  {
    if (params_.max_track_points == 0) {return;}   // 关闭
    if (!std::isfinite(clock_s_)) {return;}        // 无时钟
    if (params_.min_track_interval_s > 0.0 && !inst.track.empty()) {
      const double dt = clock_s_ - inst.track.back().stamp_s;
      if (dt >= 0.0 && dt < params_.min_track_interval_s) {return;}
    }
    inst.pushTrackPoint(clock_s_);
    inst.trimTrack(params_.max_track_points);
  }

  // 把观测写进实例：**位置与尺寸用指数滑动平均**，朝向用最短角差滑动。
  //
  // 为什么不用"直接覆盖"：单帧拟合的质心会随可见像素集合变化而抖动
  // （参照实现里同一物体的尺寸跨度实测可达 3 m），直接覆盖等于把单帧噪声
  // 1:1 传导给实例；滑动平均让"稳定几何模型"名副其实。
  // 取 alpha=0.5：两帧等效，与 `confirm_hits=2` 同一时间尺度，不会让实例
  // 反应迟钝到跟不上真实移动。
  static constexpr double kAlpha = 0.5;
  void applyObservation(ObstacleInstance & inst, const InstanceObservation & obs)
  {
    const bool first = (inst.hits == 0) && (inst.support_points == 0);
    if (first) {
      inst.cx = obs.cx;
      inst.cy = obs.cy;
      inst.radius_m = obs.radius_m;
      inst.half_x_m = obs.half_x_m;
      inst.half_y_m = obs.half_y_m;
      inst.yaw = obs.yaw;
      inst.z_min = obs.z_min;
      inst.z_max = obs.z_max;
      inst.radius_sigma_m = obs.radius_sigma_m;
    } else {
      inst.cx = kAlpha * obs.cx + (1.0 - kAlpha) * inst.cx;
      inst.cy = kAlpha * obs.cy + (1.0 - kAlpha) * inst.cy;
      inst.radius_m = kAlpha * obs.radius_m + (1.0 - kAlpha) * inst.radius_m;
      inst.half_x_m = kAlpha * obs.half_x_m + (1.0 - kAlpha) * inst.half_x_m;
      inst.half_y_m = kAlpha * obs.half_y_m + (1.0 - kAlpha) * inst.half_y_m;
      inst.yaw = shortestAngleLerp(inst.yaw, obs.yaw, kAlpha);
      inst.z_min = kAlpha * obs.z_min + (1.0 - kAlpha) * inst.z_min;
      inst.z_max = kAlpha * obs.z_max + (1.0 - kAlpha) * inst.z_max;
      inst.radius_sigma_m = kAlpha * obs.radius_sigma_m + (1.0 - kAlpha) * inst.radius_sigma_m;
    }
    inst.shape = obs.shape;
    inst.support_points = obs.support_points;
    // 置信度：**按观测次数单调升、封顶 1**。不是识别置信度，只表达"这个实例
    // 被反复看到过"（见 confidence.hpp 的同一纪律）。
    inst.confidence = std::min(1.0, 0.5 + 0.5 * (1.0 - std::exp(-0.5 * inst.hits)));
  }

  void refreshConfirmed(ObstacleInstance & inst) const
  {
    if (!inst.alive) {
      inst.confirmed = false;
      return;
    }
    // 迟滞：进入看 hits，退出看 alive —— 中间不因为一次 miss 就撤销确认。
    // 这与 `LogOddsParams` 的"进入/退出双门限"同一纪律：单门限会让实例
    // 在门槛附近反复确认/撤销。
    if (!inst.confirmed && inst.hits >= params_.confirm_hits) {
      inst.confirmed = true;
    }
  }

  // 最短角差插值：跨 ±π 时不能直接线性插值（179° 与 −179° 的中点是 180° 而非 0°）。
  static double shortestAngleLerp(double from, double to, double alpha)
  {
    double d = to - from;
    while (d > M_PI) {d -= 2.0 * M_PI;}
    while (d < -M_PI) {d += 2.0 * M_PI;}
    return from + alpha * d;
  }

  InstanceParams params_;
  std::vector<ObstacleInstance> instances_;
  // 本拍时刻（秒）；NaN = 未注入（不记录轨迹）。
  double clock_s_{std::numeric_limits<double>::quiet_NaN()};
  int next_id_{0};
};

// ---------------------------------------------------------------------------------
// 点集 → 实例观测（ADR-0041）
// ---------------------------------------------------------------------------------
//
// 把"一组属于同一个实例 id 的足迹点"拟合成一个 `InstanceObservation`。
//
// **为什么用点云统计而不是再跑一次 minAreaRect**：`nadir_projection` 已经用
// `cv::minAreaRect` 出了 OBB，但那是**像素连通域**的框；而实例层要的是
// "这些世界坐标点的几何"，两者在画幅边缘被切时会给出不同的形状。
// 本函数只做**统计量**（质心 / 半径 / 半长 / 朝向 / 高度 / 离散度），
// 不依赖 OpenCV —— `map_adapter` 刻意不拉 OpenCV（见 `footprint_geometry.hpp` 头注）。
//
// **半径取"到质心的 90% 分位距离"而不是最大值**：单个错位点就能把最大半径撑大，
// 而 90% 分位对少数离群点稳健；同时它**不会**把真实的大障碍算小（大障碍的点
// 本来就都远）。这是"保守但不脆弱"的折中，与 `roofReferenceHeight` 用 90% 分位同一思路。
//
// 点数不足 3 时返回 false：少于 3 个点连方向都定不了，硬拟合出来的形状是噪声。
struct InstanceFitParams
{
  // 半径取到质心距离的哪个分位（0.9 = 90%）。
  double radius_percentile{0.90};
  // 少于这么多点就不拟合（连朝向都定不了）。
  int min_points{3};
};

// 点集（世界坐标）→ 实例观测。返回 false 表示点数不足，调用方应跳过该实例。
//
// `ids` 与 `xs/ys/zs` 等长；本函数只消费**同一个 id 的那些点**（由调用方先分组）。
inline bool fitInstanceObservation(
  const std::vector<double> & xs, const std::vector<double> & ys,
  const std::vector<double> & zs, const InstanceFitParams & params,
  InstanceObservation & out)
{
  const size_t n = std::min({xs.size(), ys.size(), zs.size()});
  if (static_cast<int>(n) < params.min_points) {return false;}

  double sx = 0.0, sy = 0.0, sz = 0.0;
  for (size_t i = 0; i < n; ++i) {
    sx += xs[i];
    sy += ys[i];
    sz += zs[i];
  }
  const double inv = 1.0 / static_cast<double>(n);
  const double cx = sx * inv;
  const double cy = sy * inv;
  const double cz = sz * inv;

  // 半径分位 + 高度包络 + 离散度（一次遍历收齐）
  std::vector<double> dists;
  dists.reserve(n);
  double zlo = zs[0], zhi = zs[0];
  double var = 0.0;
  for (size_t i = 0; i < n; ++i) {
    dists.push_back(std::hypot(xs[i] - cx, ys[i] - cy));
    zlo = std::min(zlo, zs[i]);
    zhi = std::max(zhi, zs[i]);
    const double dx = xs[i] - cx, dy = ys[i] - cy;
    var += dx * dx + dy * dy;
  }
  std::sort(dists.begin(), dists.end());
  const double q = std::min(1.0, std::max(0.0, params.radius_percentile));
  const size_t k = std::min(dists.size() - 1, static_cast<size_t>(q * (dists.size() - 1)));
  const double radius = dists[k];

  // 半长：用二阶矩的主轴投影范围（比 minAreaRect 简单，但足以区分"方"与"长条"）
  //
  // 主轴方向由协方差矩阵的最大特征向量给出（2×2 闭式解，不需要 Eigen）。
  double sxx = 0.0, syy = 0.0, sxy = 0.0;
  for (size_t i = 0; i < n; ++i) {
    const double dx = xs[i] - cx, dy = ys[i] - cy;
    sxx += dx * dx;
    syy += dy * dy;
    sxy += dx * dy;
  }
  sxx *= inv;
  syy *= inv;
  sxy *= inv;
  // 2×2 对称阵的主方向角（标准闭式解）
  const double yaw = 0.5 * std::atan2(2.0 * sxy, sxx - syy);
  // 沿主轴 / 副轴投影的半长
  const double ca = std::cos(yaw), sa = std::sin(yaw);
  double hx = 0.0, hy = 0.0;
  for (size_t i = 0; i < n; ++i) {
    const double dx = xs[i] - cx, dy = ys[i] - cy;
    hx = std::max(hx, std::fabs(dx * ca + dy * sa));
    hy = std::max(hy, std::fabs(-dx * sa + dy * ca));
  }

  out.cx = cx;
  out.cy = cy;
  out.radius_m = radius;
  out.half_x_m = hx;
  out.half_y_m = hy;
  out.yaw = yaw;
  out.z_min = zlo;
  out.z_max = zhi;
  // 位置不确定度：质心的标准误（σ/√n），这才是"中心估计有多准"，不是点的散布。
  // 用点的散布当 σ 会把"大障碍"误判成"中心不确定" —— 两者是不同的事。
  out.radius_sigma_m = (n > 1) ? std::sqrt(var * inv / static_cast<double>(n)) : 0.0;
  out.support_points = static_cast<int>(n);
  out.shape = classifyShape(hx, hy, InstanceParams{});
  (void)cz;
  return true;
}

}  // namespace agc_perception

#endif  // AGC_PERCEPTION__OBSTACLE_INSTANCES_HPP_
