// task_fsm —— 任务状态机的**纯判定**部分（无 ROS 依赖，可单测）。
//
// 为什么单独抽出来：`task_manager` 的转移条件与 dwell 判据是全仓最容易"顺手改坏"的地方
// （任何一处放宽都会让 TIMEOUT 被当成成功），但它原先只存在于一个 911 行的节点类里，
// 零单元测试——只能靠 60 个外部验收脚本捞，而那些脚本大半需要活仿真。
//
// 本类只做**判定**，不做副作用：
//   * 输入 = 一拍的全部观测（新鲜度 / 车 odom / 距离 / epoch / 事件原因）；
//   * 输出 = 本拍要做什么（是否转移 / 是否进终态 / dwell 起停 / 里程碑）。
// 发话题、锁存、打日志仍归节点——这样判定逻辑可以在 gtest 里逐条穷举。
//
// 判据来源：ADR-0014（FSM 与终态锁存）、ADR-0016（episode 窗口）。

#ifndef AGC_TASK__TASK_FSM_HPP_
#define AGC_TASK__TASK_FSM_HPP_

#include <cmath>
#include <cstdint>
#include <limits>
#include <string>

namespace agc_task
{

// 任务状态常量（与 `agc_msgs/msg/AgcTaskState.msg` 的 `uint8` 常量**逐值一致**）。
// 为什么不直接 include 消息头：本类刻意**不依赖 ROS**——依赖消息包会让它无法在
// 纯 gtest 里编译（既有 `test_dynamic_fire_control` 等也不链接 agc_msgs）。
// 值的一致性由 `test_task_fsm.cpp` 的 `StateConstantsMatchMsg` 断言守护。
namespace task_state
{
constexpr uint8_t IDLE = 0;
constexpr uint8_t AIR_SEARCH = 1;
constexpr uint8_t TARGET_ACQUIRED = 2;
constexpr uint8_t GROUND_APPROACH = 3;
constexpr uint8_t TRACKING_SUCCESS = 4;
constexpr uint8_t MISSION_FAILED = 5;
constexpr uint8_t ABORTED = 6;
constexpr uint8_t INTERCEPT_CONFIRMED = 7;
constexpr uint8_t INFRA_FAILURE = 8;
}  // namespace task_state

// 一拍的全部输入。**默认值即"什么都还没有"**：不新鲜、无目标、无车 odom、无命令。
struct TaskFsmInputs
{
  // 时间（仿真秒）
  double now_s{0.0};
  double start_s{0.0};
  double t_max_s{120.0};

  // 目标（新鲜度已由调用方算好：age 与 conf 的门限判定在 targetFresh 里）
  bool fresh{false};
  bool have_target{false};
  double target_conf{0.0};
  double confidence_min{0.5};
  int current_epoch{0};
  std::string target_id;
  double target_x{0.0};
  double target_y{0.0};

  // 车
  bool have_car{false};
  double car_age_s{std::numeric_limits<double>::infinity()};
  double car_x{0.0};
  double car_y{0.0};

  // 命令（GROUND_APPROACH 的进入条件）
  bool have_cmd{false};
  double cmd_age_s{std::numeric_limits<double>::infinity()};
  double cmd_fresh_s{0.5};

  // 判据参数
  double d_track_m{3.0};
  double t_dwell_s{3.0};
  double car_odom_max_age_s{1.0};
  bool tracking_milestone_is_terminal{true};

  // 本 episode 的结算事件（capture 与 jam 各自独立，先到者胜）
  std::string capture_reason;
  std::string jam_reason;
  double capture_rx_s{0.0};
  double jam_rx_s{0.0};
};

// 本拍的判定结果。多个动作可在同一拍同时发生（如"中断旧 dwell + 起新 dwell"），
// 故用**独立布尔**而非互斥枚举——互斥枚举会逼调用方丢掉其中一件事。
struct TaskFsmDecision
{
  bool state_changed{false};
  uint8_t next_state{0};
  std::string reason;

  // 进入终态（锁存由节点负责）
  bool terminal{false};

  // dwell 生命周期
  bool dwell_started{false};
  bool dwell_interrupted{false};
  std::string dwell_interrupt_reason;
  double dwell_segment_s{0.0};

  // 连续跟踪达阈值（本拍首次达成）
  bool milestone_met_now{false};
};

class TaskFsm
{
public:
  TaskFsm() = default;

  uint8_t state() const {return state_;}
  bool tracking_milestone_met() const {return tracking_milestone_met_;}

  // 外部直接置状态（start / abort / reset 路径用）；不触发 dwell 副作用。
  void force_state(uint8_t s)
  {
    state_ = s;
    if (!is_active(s)) {reset_dwell();}
  }

  // 复位 dwell 计时（新 episode / 显式中断时由节点调用）。
  void reset_dwell()
  {
    dwell_active_ = false;
    dwell_start_s_ = 0.0;
    dwell_segment_start_s_ = 0.0;
    dwell_target_id_.clear();
    dwell_epoch_ = -1;
  }

  bool dwell_active() const {return dwell_active_;}
  double dwell_segment_start_s() const {return dwell_segment_start_s_;}
  const std::string & dwell_target_id() const {return dwell_target_id_;}

  static bool is_active(uint8_t s)
  {
    return s == task_state::AIR_SEARCH || s == task_state::TARGET_ACQUIRED ||
           s == task_state::GROUND_APPROACH;
  }

  static bool is_terminal(uint8_t s)
  {
    return s == task_state::TRACKING_SUCCESS || s == task_state::INTERCEPT_CONFIRMED ||
           s == task_state::MISSION_FAILED || s == task_state::ABORTED ||
           s == task_state::INFRA_FAILURE;
  }

  // 判定一拍。**无副作用**（除自身 dwell 计时状态）。
  TaskFsmDecision step(const TaskFsmInputs & in)
  {
    TaskFsmDecision out;
    if (!is_active(state_)) {return out;}

    // 超时一律算失败（ADR-0017 的 #budget）
    if (in.now_s - in.start_s > in.t_max_s) {
      return enter_terminal(task_state::MISSION_FAILED, "TIMEOUT");
    }

    switch (state_) {
      case task_state::AIR_SEARCH:
        if (in.fresh) {return transition(task_state::TARGET_ACQUIRED, "target_acquired");}
        break;

      case task_state::TARGET_ACQUIRED:
        if (in.have_cmd && in.cmd_age_s < in.cmd_fresh_s) {
          return transition(task_state::GROUND_APPROACH, "ground_approach");
        }
        break;

      case task_state::GROUND_APPROACH:
        return step_ground_approach(in);

      default:
        break;
    }
    return out;
  }

private:
  static TaskFsmDecision transition(uint8_t s, const std::string & reason)
  {
    TaskFsmDecision d;
    d.state_changed = true;
    d.next_state = s;
    d.reason = reason;
    return d;
  }

  TaskFsmDecision enter_terminal(uint8_t s, const std::string & reason)
  {
    TaskFsmDecision d;
    d.state_changed = true;
    d.next_state = s;
    d.reason = reason;
    d.terminal = true;
    return d;
  }

  bool car_ok(const TaskFsmInputs & in) const
  {
    return in.have_car && in.car_age_s >= 0.0 && in.car_age_s <= in.car_odom_max_age_s;
  }

  double range_m(const TaskFsmInputs & in) const
  {
    return std::hypot(in.target_x - in.car_x, in.target_y - in.car_y);
  }

  TaskFsmDecision step_ground_approach(const TaskFsmInputs & in)
  {
    TaskFsmDecision out;

    // 1) 捕获 / 干扰命中 → INTERCEPT_CONFIRMED。
    //    jam 只认**已确认事件**（jam_confirm）；授权 / 发送不结算。
    //    先命中者胜按**事件到达时刻**定序（不固定 capture 优先）。
    const bool have_cap = !in.capture_reason.empty();
    const bool have_jam = !in.jam_reason.empty() && in.jam_reason != "JAM_NONE";
    if (have_cap && have_jam) {
      return enter_terminal(
        task_state::INTERCEPT_CONFIRMED,
        (in.capture_rx_s <= in.jam_rx_s) ? in.capture_reason : in.jam_reason);
    }
    if (have_cap) {return enter_terminal(task_state::INTERCEPT_CONFIRMED, in.capture_reason);}
    if (have_jam) {return enter_terminal(task_state::INTERCEPT_CONFIRMED, in.jam_reason);}

    // 2) dwell 逐拍连续性：任一条件不满足即中断清零，**不**把失联段累计进 dwell。
    const bool car_valid = car_ok(in);
    const bool range_ok = in.have_target && car_valid && range_m(in) <= in.d_track_m;

    if (dwell_active_) {
      std::string ir;
      if (in.current_epoch != dwell_epoch_) {
        ir = "EPOCH_CHANGED";
      } else if (!in.have_target) {
        ir = "TARGET_LOST";
      } else if (!in.fresh) {
        ir = (in.target_conf < in.confidence_min) ? "TARGET_LOW_CONF" : "TARGET_STALE";
      } else if (!car_valid) {
        ir = in.have_car ? "CAR_ODOM_STALE" : "CAR_ODOM_MISSING";
      } else if (in.target_id != dwell_target_id_) {
        ir = "TARGET_ID_CHANGED";
      } else if (range_m(in) > in.d_track_m) {
        ir = "RANGE_EXCEEDED";
      }
      if (!ir.empty()) {
        out.dwell_interrupted = true;
        out.dwell_interrupt_reason = ir;
        out.dwell_segment_s = in.now_s - dwell_segment_start_s_;
        reset_dwell();
      }
    }

    // 3) 无活跃 dwell 且本拍合法 → 起新 dwell（换 id / epoch 变化后从 0 重算，杜绝跨段累计）。
    if (!dwell_active_ && range_ok && in.fresh && in.have_target) {
      dwell_active_ = true;
      dwell_start_s_ = in.now_s;
      dwell_segment_start_s_ = in.now_s;
      dwell_target_id_ = in.target_id;
      dwell_epoch_ = in.current_epoch;
      out.dwell_started = true;
    }

    // 4) 连续达阈值才成功（不降级为累计接近时长）。
    if (dwell_active_ && (in.now_s - dwell_start_s_) >= in.t_dwell_s) {
      if (!tracking_milestone_met_) {out.milestone_met_now = true;}
      tracking_milestone_met_ = true;
      // capture 场景不锁存 TRACKING_SUCCESS——否则 capture_adjudicator 的交火窗口会被提前
      // 关闭，捕获永不发生（ADR-0014）。里程碑仍如实记录，供指标使用。
      if (in.tracking_milestone_is_terminal && !out.state_changed) {
        out.state_changed = true;
        out.next_state = task_state::TRACKING_SUCCESS;
        out.reason = "tracking_milestone";
        out.terminal = true;
      }
    }
    return out;
  }

  uint8_t state_{task_state::IDLE};
  bool tracking_milestone_met_{false};

  bool dwell_active_{false};
  double dwell_start_s_{0.0};
  double dwell_segment_start_s_{0.0};
  std::string dwell_target_id_;
  int dwell_epoch_{-1};
};

}  // namespace agc_task

#endif  // AGC_TASK__TASK_FSM_HPP_
