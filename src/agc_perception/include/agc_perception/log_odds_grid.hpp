// log_odds_grid —— 逐格占据证据的增量累积（纯逻辑，不 include ROS 消息包）
//
// **为什么需要它**（2026-11-08 用户裁定，替代"每帧重算 OBB 再栅格化"）：
// 项目场景不确定，不可能每次都把地图扫描清楚。实测：14 m 高度、100° 视场看 100×100 m 场地时，
// 42 个障碍里 0 个能拍全、38 个完全在视场外，每个连通域只是"某个大建筑的一个角 + 侧墙斜带"。
// 这种碎片的外接框形状取决于**画幅边缘恰好切在哪里**，而 UAV 在跟踪目标、一直在动 ⇒
// 单帧估计再稳也稳不住"本来就在变的碎片"，表现为形状一直变、偶尔大幅跳再回归。
//
// **解法**：不假设"能看清一个物体"，只累积"这一格被反复观测为占据"的证据。
// 参照 ego-planner `plan_env/src/grid_map.cpp`（p_hit=0.70 / p_miss=0.35，log-odds 累加后 clamp）：
//   * 被观测为占据 → +hit
//   * 本帧未被观测 → 缓慢 −miss（**不清零**，给"这帧被画幅边缘切掉"留余地）
//   * clamp 到 [min, max]，避免无限累积后无法翻转
// FOV 边缘那种"这帧有、下帧没有"的格子累积置信度上不去，不会画出来；
// 建筑本体被反复观测，稳定显示 —— 形状随证据累积慢慢长出来，而不是逐帧跳。
//
// 与旧实现的关键差异：旧版每帧把 `eff` 障碍集合**整体重算**成栅格（单帧噪声 1:1 传导）；
// 本类**增量更新**，单帧异常只贡献一次 hit/miss，不会瞬间改变地图。

#ifndef AGC_PERCEPTION__LOG_ODDS_GRID_HPP_
#define AGC_PERCEPTION__LOG_ODDS_GRID_HPP_

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace agc_perception
{

// log-odds 参数与判据（默认值取自 ego-planner 的工程经验，本仓按其含义重新推导见注释）。
struct LogOddsParams
{
  // p_hit / p_miss：单次观测把该格推向占据 / 空闲的力度。
  // ego-planner 取 0.70 / 0.35；本仓沿用——0.7 意味着"一次命中就相当可信"，
  // 0.35 意味着"一次漏观测只是弱证据"，正好符合"FOV 边缘可能被切掉"的现实。
  double p_hit{0.70};
  // **2026-11-09 用户裁定 Q18**：0.35 → 0.25。
  //
  // 理由（实测动力学，不是猜）：从 p_init 打满到 p_max 需 6 次 hit，
  // 而**从饱和擦回 occupied 门限**在 p_miss=0.35 时需要 **5 次 miss**。
  // 相机一直在移动，同一格很难连续 5 帧落在同一条射线上 ⇒ 误 hit 一旦打满
  // 就基本擦不掉，这正是用户看到的"飞过建筑群突然跳变、悬停时看着还行但旧的都留着"。
  //
  // 取 0.25 ⇒ 擦回门限需 **3 帧**，是"相机移动下能追上"的临界值。
  // 不再更低（0.15 只需 2 帧）：那会让**真实的动态障碍**在 2 帧内消失，反而危险。
  // 仍低于 p_hit（0.70），保持"确认障碍比确认空闲更容易"的不对称性。
  double p_miss{0.25};
  // 置信度上下界（概率）。超过上界即稳定占据，低于下界即稳定空闲。
  double p_min{0.12};
  double p_max{0.97};
  // 判为 occupied 的门限：累积置信度 ≥ 此值才写 100。
  // 取 0.6：需要约 2 次连续命中（0.5 → 0.74）才跨过，单帧毛刺画不出来。
  double occupied_threshold{0.60};
  // 退出 occupied 的门限（迟滞）。必须 < occupied_threshold，否则退化成单门限。
  // 取 0.45：与 0.60 之间留 0.15 的抖动带，足以吸收 log-odds 在门限附近的随机游走。
  double occupied_exit_threshold{0.45};
  // 判为 free 的门限：≤ 此值才写 0；介于两者之间写 -1（unknown）。
  // 必须 < p_init（否则初始格会被判成 free）。取 0.20：
  // 需要约 3 次连续 miss（0.30→0.13）才从初始掉到 free，即"明确看到空"才写 0。
  double free_threshold{0.20};
  // **全局时间衰减**的力度（与 p_miss 分开）。
  // 为什么必须分开：ego-planner 的 p_miss 是"射线穿过该格"的**真实负证据**（含信息量）；
  // 我们的 decayMiss() 是"本帧没看到"的**时间流逝**（几乎无信息量，可能只是被画幅边缘切掉）。
  // 若沿用 p_miss=0.35（logit −0.62），维持占据需要 **42% 的观测占空比**（实测推导），
  // 障碍边缘的格子达不到，就忽明忽暗 → 框边界以 0.5 m 步长漂移（实测 sx 跨度 2.5 m）。
  // 取 0.48（logit −0.08）：维持占据只需 9% 占空比，纯衰减掉一次 hit 需 11 帧（0.37 s@30Hz）。
  double p_decay{0.48};
  // **未知格的初始置信度**。必须 < free_threshold 与 occupied_threshold 之间、
  // 且满足"一次 hit 推不到 occupied"。推导（p_hit=0.70 ⇒ logit=0.847）：
  //   p_init=0.30 ⇒ 1 次 p=0.50（仍 unknown）、2 次 p=0.70（occupied）、3 次 p=0.85。
  // 这正是要的：**单帧毛刺画不出来，连续两帧才画**（FOV 边缘的"这帧有下帧没有"被自然滤掉）。
  // 若取 0.50（"中性"直觉值），一次命中就到 0.70 直接越过门限 —— 毛刺会立刻画进地图。
  double p_init{0.30};

  // ---- 小障碍的**空间支持门槛**（ADR-0039）----
  //
  // 一个格要在**单帧内**成为候选 hit，必须至少有这么多**独立足迹点**落在它里面。
  // 0 或 1 = 关闭（旧口径：一个点就够）。
  //
  // **为什么需要**：dense_map 的小障碍（box 0.6–1.2 m、cylinder r 0.25–0.40 m）
  // 在 0.5 m 栅格下只有 1–3 格宽。单个错误投影点（标签↔深度错位、深度噪声、
  // 相邻障碍边缘）落在某格就能算一次 hit，跨两帧就成了 occupied —— 而大建筑
  // 一个格内有成百上千个点，同样两帧才是 occupied，两者的**证据强度完全不同**。
  // 要求"多个独立点"正是把两者区分开的唯一单帧依据（点数是唯一与像素采样密度
  // 无关、又能反映"这块地面真的被多个像素看到"的量）。
  //
  // 取 3：小障碍 0.6×0.6 m 在 GSD 5.3 cm/px 下有约 128 px，远超 3；而孤立错位点
  // 通常只有 1–2 个。这个门槛不改变"大建筑容易确认"的既有行为。
  int min_hit_points_per_cell{3};

  // ---- 逐点不确定度的**门控**（ADR-0042）----
  //
  // 一个格本帧要成为候选 hit，其**最大**逐点主方向 1σ 不得超过
  // `sigma_reject_ratio × 证据层格宽`。0 = 关闭门控（旧口径）。
  //
  // **为什么按格宽而不是固定米数**：不确定度的意义是"这个点可能落到隔壁格去"，
  // 而"隔壁"由格宽定义。写死 0.25 m 会在换分辨率时静默改变严格程度
  // （与 `min_hit_points_per_cell` 按格宽定、`inflation` 按米定的分工一致：
  // 与格相关的用格，与物理相关的用米）。
  //
  // 取 0.5：σ 超过半个格宽时，该点自身的位置误差已能把占据判到相邻格，
  // 单帧不足以确认 —— 与 ADR-0039 的"错位超半格则本帧不给正证据"同一条纪律，
  // 只是那条用的是**帧级**错位量，这条用的是**逐点**误差。
  double sigma_reject_ratio{0.5};

  // 证据层格宽（m）。门控按它换算成米 —— 由调用方在 `reset()` 前填好。
  // 0 = 未知（门控自动关闭，不做静默收紧）。
  double cell_size_m{0.0};

  // ---- 进入 occupied 的**跨帧确认次数**（ADR-0039）----
  //
  // 一个格要被判为 occupied，除了概率过门限，还必须累计这么多次**跨帧** hit。
  // 1 = 只靠概率门限（旧口径）。取 2：与 `p_init`/`p_hit` 推导出的"两帧才画"一致。
  //
  // **为什么显式写成一道门而不是只靠概率**：概率门限与 `p_hit` 耦合 —— 有人为了
  // "更容易建图"把 p_hit 调高或把 occupied_threshold 调低，就会**静默**变成
  // "单帧即画"，而那种改动在代码里看不出来。把"至少两帧"写成独立的门，
  // 参数标定就无法绕过它。
  //
  // **计数单位 = 地图帧，不是感知帧**（ADR-0039 补正）。
  // 感知回调 10 Hz、`/agc/map` 发布 2 Hz，迟滞状态（`occupied_now_`）只在发布拍推进。
  // 若按感知帧计数，"K=2 帧确认"在 2 Hz 的地图上看实际只要 0.2 s —— 语义比设计意图
  // 弱 5 倍，且随感知帧率漂移。现在 `map_frame_hits_` 只在**快照拍**推进一次，
  // 与 `occupied_now_` 同一个时钟，K 的语义因此与对外地图一致。
  int min_hits_for_occupied{2};

  // **深度一致性门槛**（ADR-0039 补正）：一帧内同一格的 z 样本，用**中位数 + MAD**
  // 判"这些点是不是同一个平面"，而不是只看极差。
  //
  // **为什么极差不够**：极差对单个离群点极其敏感（一个错位点就能让整格被拒），
  // 又抓不到"整片系统性偏移但局部连续"—— 后者正是 temp.md 点名的场景
  // （"整片深度偏移 / 标签与深度错位但局部深度连续"）。中位数与 MAD 都是**稳健**量：
  // 少数离群点既不拉偏中位数，也只会抬高 MAD 一点点。
  //
  // 判据：`max(|z − 中位数|) > max(floor_m, mad_k · 1.4826 · MAD)` ⇒ 判为混了两种表面。
  // 取 mad_k=3.0（与 nadir_projection 的形状稳健估计同一口径）、floor=0.30 m
  // （薄板/矮台的正常厚度起伏）。
  double depth_mad_k{3.0};
  double depth_consistency_floor_m{0.30};
  // 每格保留的 z 样本上限（用于中位数/MAD）。超过则按"均匀抽样"丢弃后续样本 ——
  // 目的只是拿到一个稳健的位置估计，不需要全部样本。
  int depth_sample_cap{16};

  // 单格 z 展布上限（m）：一帧内落进同一格的足迹点，z 极差超过它即判"混了两种表面"
  // （屋顶 + 侧墙、障碍 + 地面），整格不进 hit 证据。0 = 关闭。
  //
  // **为什么用 z 而不是 XY 散布**：0.5 m 格内的 XY 散布天然被格宽限住（≤0.71 m），
  // 判不出任何东西；而 z 反映的是"这些点是不是同一个平面"。侧墙点与屋顶点的 XY
  // 可能落在同一格，z 却差几米 —— 这正是 temp.md 所说"标签与深度错位但局部深度连续"
  // 之外的另一类错误归属，且它可在一帧内单格判出，不需要跨帧。
  double max_hit_z_spread_m{1.5};

  // **时间衰减的下限**（概率）：纯时间流逝（`decayMiss` / `markStale`）最多把证据
  // 削弱到这个概率，**不得再往下**。低于 `free_threshold` 的 free 只能由**真实射线
  // 穿过**（`observeMiss` / carve）给出。
  //
  // **为什么必须区分**：时间衰减的语义是"这格本帧没被看到"，它几乎不携带信息
  // （可能只是被画幅边缘切掉、被遮挡、或相机飞走了）。让它把格子推到 free，等于把
  // "没看见"当成"确认是空的" —— 与 ADR-0035 (g) 的三态纪律直接冲突，且实测后果是
  // 真实障碍被自己的时间衰减擦成 free（覆盖率因此有与算法无关的损耗）。
  //
  // 取 0.22：略高于 `free_threshold`(0.20)，落在 unknown 带内 —— 消费者（含
  // `perception_quality.py` 的 `classifyCell` 同口径实现）把它读作 unknown，
  // 规划器仍可通行，只是不再享受"已确认安全"的待遇。
  double unknown_floor_p{0.22};

  // ---- occupied 的**生命周期**（ADR-0039，temp.md 的 P1 根因）----
  //
  // 一个格进入 occupied 后，若连续这么多帧**没有被任何正向 hit**，则把它降为
  // unknown（**不是 free**）。0 = 关闭（旧口径：occupied 永不因"没再看"而退出）。
  //
  // **为什么必须**：`markStale` 此前对 `logodds >= occupied_threshold` 的格直接
  // `continue` —— 已确认的占据**永不因时间退出**，只能靠射线 carving 擦。而 dense_map
  // 的误 hit 大量落在画幅外 / 遮挡区 / 射线没穿过的位置，carving 根本够不到，
  // 于是错误 occupied 长期驻留：误覆盖 0.727、面积比 1.801 的直接来源。
  //
  // **为什么降 unknown 而不是 free**：我们只是"很久没再看到它"，并没有"看到它是空的"。
  // 降 free 等于对规划器承诺"这条路我确认过"，那是过度承诺（与 ADR-0035 (g) 同一纪律）。
  // **只有真实射线穿过**（`observeMiss` / 强 carve）才允许降到 free。
  //
  // 取 30 帧（≈3 s @10 Hz）：与 `stale_after_s` 同量级。相机 3 s 至少移动 6 m，
  // 真实障碍应被重新看到；看不到说明它已在视野外，旧证据不该无限保鲜。
  int occupied_expire_frames{30};

  // 过期**分多拍走**（不是一次清零）：每拍只按 `p_decay` 力度削弱一次。
  // 这样"刚过期"与"过期很久"仍可区分，且不会让 occupied 集合出现整批同时消失的台阶。
  // 过期判定用帧数（与 `occupied_expire_frames` 同口径），削弱用 `p_decay`（弱证据）。
  //
  // ---- 遮挡体的**最低置信度**（ADR-0039，temp.md 的 P3）----
  //
  // carving 射线遇到一个格时，只有该格置信度 ≥ 此值才把它当作**遮挡体**并终止射线。
  // 低于此值的格（候选 / 弱证据）射线可以穿过，但只施加**弱**负证据。
  //
  // **为什么需要**：dense_map 里每箱取"最近障碍点"做射线终点，小障碍的最近点会因
  // 投影误差逐帧变化。旧口径下任何历史 occupied（哪怕只靠两次可疑 hit 建起来）
  // 都会挡住射线，于是"这一帧的墙"与"上一帧的墙"轮流把对方后面的区域标 free，
  // 造成 occupied 集合大幅互换（稳定性 p99 的主要来源）。
  //
  // 取 0.60 = `occupied_threshold`：与"什么叫已确认占据"保持同一把尺子。
  double occluder_min_confidence{0.60};
};

// 概率 → log-odds（自然对数）
inline double toLogOdds(double p)
{
  const double eps = 1e-9;
  const double q = std::min(1.0 - eps, std::max(eps, p));
  return std::log(q / (1.0 - q));
}

// log-odds → 概率
inline double fromLogOdds(double l)
{
  return 1.0 - 1.0 / (1.0 + std::exp(l));
}

// 增量 log-odds 占据栅格。
//
// 用法（每帧）：
//   1. beginFrame(frame_idx) 声明"这是第几帧"（**证据单位按帧计**，见下）
//   2. 对该帧**观测到**的格调用 observeHit(idx)
//   3. 用 observeMiss / decayMissMasked 施加负证据
//   4. **只在地图发布拍**调用 snapshot() 取 int8 栅格（0 / 100 / -1）
//
// **证据单位 = 每格每帧一次**（2026-11-09 用户裁定，本次的稳定性根因修复）：
// 调用方（`map_adapter`）的一帧里有**成千上万个足迹点**，而一个 0.5 m 格通常覆盖
// 大量像素 —— 若每个点各算一次 hit，证据强度就取决于**像素采样密度**而不是时序观测：
// 栅格中心一帧打满、障碍边缘只命中一两次，边缘格于是在 100 与中间值之间反复翻转。
// 实测 |Δoccupied| p99 = 140 格（判据 ≤50）正是这么来的。
// 现在同一格在同一帧内**最多贡献一次 hit、一次 miss**，且**同帧 hit 优先于 miss**
// （本帧看到的障碍不得被本帧的射线擦掉）。
//
// 为什么 miss 要分两种：
//   * `decayMiss()`：时间流逝使旧证据变弱（力度 p_decay）。
//   * `observeMiss(idx)`：明确观测到该格空闲（射线穿过），力度 p_miss。
// 两者共用同一个"每帧一次"的负证据槽位 —— 同一帧不会被 carve + 衰减 + 空窗衰减
// 三重叠加（那正是过渡带栅格被反复推移的直接原因）。
class LogOddsGrid
{
public:
  LogOddsGrid() = default;

  // 初始化 / 几何变更时重置（尺寸或分辨率变了必须重建）。
  void reset(int width, int height, const LogOddsParams & params)
  {
    params_ = params;
    width_ = std::max(0, width);
    height_ = std::max(0, height);
    const size_t n = static_cast<size_t>(width_) * static_cast<size_t>(height_);
    init_lo_ = toLogOdds(params_.p_init);
    // 初始为"未知"：从 p_init 起步（不是 0.5，理由见 LogOddsParams::p_init 注释）。
    logodds_.assign(n, init_lo_);
    hit_count_.assign(n, 0);
    last_seen_frame_.assign(n, 0);
    // **最后被正向 hit 的帧号**（与 last_seen_frame_ 不同：后者含射线穿过的帧）。
    // occupied 生命周期用它判"多久没被重新命中"（ADR-0039）。
    last_hit_frame_.assign(n, 0);
    // 地图帧口径的确认计数（ADR-0039 补正）：与 hit_count_ 分开，因为两者时钟不同。
    map_hit_frame_.assign(n, -1);
    map_frame_hits_.assign(n, 0);
    // 本帧的**独立点数**与 z 展布（空间支持门槛，ADR-0039）
    point_frame_.assign(n, -1);
    frame_points_.assign(n, 0);
    frame_zs_.clear();
    frame_zs_.resize(n);
    frame_zmin_.assign(n, 0.0);
    frame_zmax_.assign(n, 0.0);
    // 本帧该格的最大主方向 1σ（ADR-0042）：-1 = 本帧无该信息。
    frame_sigma_max_.assign(n, -1.0);
    occupied_now_.assign(n, 0);
    // 每帧去重槽位（**证据单位 = 每格每帧一次**）：-1 = 本帧尚未记账。
    hit_frame_.assign(n, -1);
    neg_frame_.assign(n, -1);
    // 快照缓冲**预分配并复用**：发布拍只改写内容，不再每拍新建整张 vector。
    snapshot_.assign(n, -1);
    // 有证据格索引（hit 过 / 被 carve 成 free）。markStale 与衰减只遍历它，
    // 不再每帧扫全图。**只增不减**：hit_count 单调不减，被 carve 的格也需要
    // 继续衰减回 unknown，故不做删除（上界 = 整图格数，不会无界增长）。
    evidence_.clear();
    evidence_.reserve(std::max<size_t>(64, n / 8));
    in_evidence_.assign(n, 0);
    current_frame_ = 0;
    current_map_frame_ = 0;
    const double lo = toLogOdds(params_.p_min);
    const double hi = toLogOdds(params_.p_max);
    lo_ = lo;
    hi_ = hi;
    hit_inc_ = toLogOdds(params_.p_hit);
    miss_inc_ = toLogOdds(params_.p_miss);   // 真实负证据（射线穿过），力度大
    decay_inc_ = toLogOdds(params_.p_decay);  // 时间流逝，力度小（p_decay<0.5 ⇒ 该值 < 0）
  }

  bool empty() const {return logodds_.empty();}
  int width() const {return width_;}
  int height() const {return height_;}
  size_t size() const {return logodds_.size();}

  bool inRange(size_t idx) const {return idx < logodds_.size();}

  // 观测到占据：log-odds 加 hit，clamp 上界。
  //
  // **同一格同一帧只记账一次**（2026-11-09 用户裁定）：重复调用是幂等的。
  // 这是"证据强度不依赖像素采样密度"的实现点 —— 调用方不必先自己建唯一格集合，
  // 但**仍然应该**在诊断里区分"原始点数 / 唯一格数 / 重复点数"（map_adapter 有报）。
  void observeHit(size_t idx)
  {
    if (!inRange(idx)) {return;}
    if (hit_frame_[idx] == current_frame_) {return;}   // 本帧已记过 → 幂等
    hit_frame_[idx] = current_frame_;
    logodds_[idx] = std::min(hi_, logodds_[idx] + hit_inc_);
    ++hit_count_[idx];
    last_seen_frame_[idx] = current_frame_;
    last_hit_frame_[idx] = current_frame_;
    // **地图帧口径的确认计数**：同一地图帧内多拍命中只算一次（见 min_hits_for_occupied 注释）。
    if (map_hit_frame_[idx] != current_map_frame_) {
      map_hit_frame_[idx] = current_map_frame_;
      ++map_frame_hits_[idx];
    }
    markEvidence(idx);
  }

  // ---- 带**空间支持**的 hit（ADR-0039）----
  //
  // 与 `observeHit` 的区别：只有**通过空间支持门槛**的格才记账。调用方在一帧内
  // 先把该格的独立点数与 z 展布攒出来，再调这里判一次（**一帧一次**，与
  // `observeHit` 的幂等语义一致）。
  //
  // 门槛（任一不满足 → 本帧该格不进 hit 证据）：
  //   * 独立点数 ≥ `min_hit_points_per_cell`（0/1 = 关闭）—— 排除孤立错位点；
  //   * z 展布 ≤ `max_hit_z_spread_m`（0 = 关闭）—— 排除"同格混了两种表面"；
  //   * 逐点最大 1σ ≤ `sigma_reject_ratio × cell_size_m`（ADR-0042；ratio=0 关闭）
  //     —— 排除"这个点自己就可能落到隔壁格"的观测。
  //
  // 返回 true 表示本次记账成功（调用方据此统计"被支持门槛拒掉的格数"）。
  bool observeHitWithSupport(size_t idx, int n_points, double z_spread_m)
  {
    if (!inRange(idx)) {return false;}
    if (hit_frame_[idx] == current_frame_) {return false;}   // 本帧已记过
    if (params_.min_hit_points_per_cell > 1 && n_points < params_.min_hit_points_per_cell) {
      return false;
    }
    if (params_.max_hit_z_spread_m > 0.0 && z_spread_m > params_.max_hit_z_spread_m) {
      return false;
    }
    // 逐点不确定度门控（ADR-0042）。`frameSigmaMax` 返回 -1 表示"本帧无该信息"
    // ⇒ **不拦**（发布端未提供协方差时行为与旧口径逐字相同，不做静默收紧）。
    if (params_.sigma_reject_ratio > 0.0 && params_.cell_size_m > 0.0) {
      const double s = frameSigmaMax(idx);
      if (s >= 0.0 && s > params_.sigma_reject_ratio * params_.cell_size_m) {
        return false;
      }
    }
    observeHit(idx);
    return true;
  }

  // 本帧该格的独立点数（诊断 / 调用方判定用；未记账时为 0）。
  int framePointCount(size_t idx) const
  {
    return inRange(idx) ? frame_points_[idx] : 0;
  }

  // ---- 帧内空间支持累加（ADR-0039）----
  //
  // 调用方在一帧内对每个足迹点调一次 `addFramePoint`（**必须在同一帧号内**），
  // 累加出该格的独立点数与 z 极值；本帧记账时调 `observeHitWithSupport` 一次。
  //
  // **为什么由本类持有这份状态**：`map_adapter` 若自己维护一张 4 万格的
  // points/zmin/zmax 缓冲，每帧都要清零（实测 1152² 场景下那是纯浪费），
  // 而且"哪些格本帧被碰过"与"证据记账"会分处两套数据结构，容易不同步。
  // 这里用**帧号惰性重置**：`point_frame_[idx] != current_frame_` 即视为本帧未碰过。
  void addFramePoint(size_t idx, double z_m)
  {
    addFramePoint(idx, z_m, -1.0);
  }

  // 带**逐点不确定度**的版本（ADR-0042）：`sigma_m` < 0 表示"无该信息"。
  //
  // 记录本帧该格**最大**的主方向 1σ（最坏的那个点决定这一格可不可信 ——
  // 与 `frameZSpread` 取极值同一纪律：一格里只要有一个很糊的点，
  // 就不能说"这一格看得准"）。
  void addFramePoint(size_t idx, double z_m, double sigma_m)
  {
    if (!inRange(idx)) {return;}
    const bool has_sigma = std::isfinite(sigma_m) && sigma_m >= 0.0;
    if (point_frame_[idx] != current_frame_) {
      // 本帧第一次碰到该格：初始化计数与 z 极值。
      // **注意不能 `return`** —— 该点也是深度一致性样本的第一个样本，
      // 早期版本在这里 return，导致每格恒定少一个样本（双峰用例因此漏判）。
      point_frame_[idx] = current_frame_;
      frame_points_[idx] = 1;
      frame_zmin_[idx] = z_m;
      frame_zmax_[idx] = z_m;
      frame_sigma_max_[idx] = has_sigma ? sigma_m : -1.0;
      frame_zs_[idx].clear();
      frame_zs_[idx].push_back(z_m);
      return;
    }
    ++frame_points_[idx];
    if (z_m < frame_zmin_[idx]) {frame_zmin_[idx] = z_m;}
    if (z_m > frame_zmax_[idx]) {frame_zmax_[idx] = z_m;}
    if (has_sigma) {
      // -1（无信息）不参与取最大：否则"有一点无信息 + 一点很准"会被判成无信息。
      frame_sigma_max_[idx] = (frame_sigma_max_[idx] < 0.0)
        ? sigma_m : std::max(frame_sigma_max_[idx], sigma_m);
    }
    // 深度一致性用**稳健统计**（中位数/MAD）需要的样本（见 depth_mad_k 注释）。
    // 达到上限后按 2 的幂均匀降采样：既保留分布形状，又不让单格缓冲无界增长。
    auto & samples = frame_zs_[idx];
    if (static_cast<int>(samples.size()) < params_.depth_sample_cap) {
      samples.push_back(z_m);
    } else if (!samples.empty()) {
      // 满员后隔一个丢一个（保留前半段），再把新样本追加到末尾空间
      const size_t keep = samples.size() / 2;
      for (size_t k = 0; k < keep; ++k) {samples[k] = samples[k * 2];}
      samples.resize(keep);
      samples.push_back(z_m);
    }
  }

  // 本帧该格的 **z 稳健一致性**判定（中位数 + MAD）。
  //
  // 返回 true = 这些点看起来是**同一个平面**；false = 混了两种表面，整格不该进 hit。
  // 样本不足 3 个时无法算 MAD，退回"极差 ≤ floor" 的弱判据（不因样本少而放行无上限的离群）。
  bool frameDepthConsistent(size_t idx) const
  {
    if (!inRange(idx) || point_frame_[idx] != current_frame_) {return true;}
    const std::vector<double> & zs = frame_zs_[idx];
    const double floor_m = params_.depth_consistency_floor_m;
    if (zs.size() < 3) {
      return frameZSpread(idx) <= std::max(floor_m, 1e-9);
    }
    std::vector<double> sorted(zs);
    std::sort(sorted.begin(), sorted.end());
    const size_t n = sorted.size();

    // **主判据 = IQR（四分位距）**，不是 MAD。实测理由：
    // 双峰数据（同格一半屋顶 z=1、一半地面 z=6）上 **MAD 会自我失效** ——
    // 中位数落在两簇中间，各点到它的距离都相同，MAD 因此等于"两簇间距的一半"，
    // 于是 `tol` 被自身撑大到把两簇都收进来，判据恒真。IQR 是分位数差，
    // 双峰时必然大、对少数离群点稳健，两个性质同时满足。
    const double q1 = sorted[n / 4];
    const double q3 = sorted[(3 * n) / 4];
    if ((q3 - q1) <= 2.0 * floor_m) {return true;}

    // IQR 大 ⇒ 要么双峰（该拒），要么多数点正常、少数离群把 q3 拉高（该过）。
    //
    // **区分方式必须直接、不能再借 MAD**：实测证明 MAD 在双峰上会自我失效 ——
    // 两簇各半时中位数落在中间，各点到它的距离相同，MAD 因此等于两簇间距的一半，
    // 于是任何"tol ∝ MAD"的判据都被自身撑大到恒真。这里直接数**落在 floor 内的点数**：
    //   * 多数点在同一平面上（少数离群）→ 多数派在 floor 内 ⇒ 一致；
    //   * 两簇各半 → 中位数落在两簇中间的空档，几乎没有点落在 floor 内 ⇒ 不一致。
    const double med = (n % 2 == 1) ? sorted[n / 2]
      : 0.5 * (sorted[n / 2 - 1] + sorted[n / 2]);
    size_t inliers = 0;
    for (size_t k = 0; k < n; ++k) {
      if (std::fabs(sorted[k] - med) <= floor_m) {++inliers;}
    }
    return inliers * 2 > n;
  }

  // 本帧该格的独立点数（本帧未碰过 → 0）。
  int framePoints(size_t idx) const
  {
    if (!inRange(idx) || point_frame_[idx] != current_frame_) {return 0;}
    return frame_points_[idx];
  }

  // 本帧该格的 z 展布（米；本帧未碰过 → 0）。
  double frameZSpread(size_t idx) const
  {
    if (!inRange(idx) || point_frame_[idx] != current_frame_) {return 0.0;}
    return frame_zmax_[idx] - frame_zmin_[idx];
  }

  // 本帧该格**最大**逐点主方向 1σ（m）；-1 = 本帧无该信息（发布端未提供）。
  //
  // **为什么取最大而不是平均**：一格里只要有一个点很糊，就不能说"这一格看得准"。
  // 平均会让"99 个准点 + 1 个糊点"看起来很好，而那个糊点正是能把整格推错位置的那个。
  double frameSigmaMax(size_t idx) const
  {
    if (!inRange(idx) || point_frame_[idx] != current_frame_) {return -1.0;}
    return frame_sigma_max_[idx];
  }

  // 本帧该格是否已被 hit 记过（调用方可用于"hit 优先于 miss"的判定与诊断）。
  bool hitThisFrame(size_t idx) const
  {
    return inRange(idx) && hit_frame_[idx] == current_frame_;
  }

  // 明确观测到空闲（射线穿过）：加 miss，clamp 下界。
  //
  // **每格每帧最多一次负证据**，且**同帧已被 hit 的格不再吃 miss**：
  // 本帧看到的障碍不得被本帧的射线擦掉（否则 hit 与 miss 在同一帧里互相抵消，
  // 边缘格就在门限附近随机游走）。
  void observeMiss(size_t idx)
  {
    if (!inRange(idx)) {return;}
    if (!takeNegativeSlot(idx)) {return;}
    logodds_[idx] = std::max(lo_, logodds_[idx] + miss_inc_);
    last_seen_frame_[idx] = current_frame_;
    markEvidence(idx);
  }

  // 全局轻衰减：**已被观测过**的格按 p_decay 力度缓慢变弱（**不清零**）。
  // 这是"FOV 边缘被切掉"的容错：一次漏观测只是弱负证据，不会把已确认的障碍抹掉。
  //
  // **2026-11-08 修复（用户裁定 Q3/Q35）**：守卫从 `if (v > 0.0)` 改成 `hit_count > 0`。
  //
  // 原守卫 `v > 0.0` 的实测后果（编译实测，非推算）：logit ≤ 0 的格子永远不再衰减，
  // 而 p_init=0.30 的 logit 恰为 −0.847 < 0 ⇒ **所有未知格从第一帧起就被冻结**。
  // 于是地图事实上**不存在 free 空间**，只有 unknown + occupied：
  //   * "障碍形状只增不减" —— 用户反馈"形状面积一直在变"的根因之一；
  //   * 规划器无法区分"看过是空的"与"从没看过"。
  //
  // **为什么守卫是 `hit_count > 0` 而不是"对所有格衰减"**：本函数每帧对**全图**调用，
  // 与"该格是否在视场内"无关。若无差别衰减，**从没被看过的格子也会慢慢变成 free** ——
  // 那是比原 bug 更危险的错误（把未知当自由）。只有"确实观测过、之后没再观测到"的格，
  // "没再看到"才构成弱负证据。真正的自由空间由射线穿透（observeMiss）给出。
  void decayMiss()
  {
    decayMissMasked(nullptr);
  }

  // **只在给定掩码内衰减**（2026-11-09 用户裁定）。
  //
  // **为什么必须区分视野内外**：`decayMiss()` 的语义是"本帧没看到，所以证据弱一点"。
  // 但对**画幅之外**的格，"本帧没看到"是必然的、不携带任何信息 —— 相机根本没朝那里看。
  // 每帧对它们衰减等于"只要不盯着看，障碍就会消失"，于是：
  //   * 视野外的真实障碍持续被削弱；
  //   * 相机移动后旧障碍按"没被看到"消退；
  //   * 障碍重新进入画面时又被 hit；
  //   ⇒ 形成用户看到的"消失—重新出现"周期。
  //
  // `inside` 为 null ⇒ 退回全图衰减（旧口径，单测与对照用）。
  // 掩码为真 = 该格**本帧在有效视野内**（画幅内且未被遮挡），才允许施加时间衰减。
  //
  // **2026-11-09 性能修复**：不再遍历整张 log-odds 数组，只遍历**有证据格索引**。
  // 改造前每帧都要扫全图（200×200=4 万格）并把整张 `inside` 掩码传进来，
  // 而真正有证据的格通常只有几千 —— 那是纯浪费的 cache 流量。
  // 现在调用方可以直接给**画幅包围盒 + 内联判定**（见 bbox 重载），连掩码都不必建。
  void decayMissMasked(const std::vector<char> * inside)
  {
    const double free_hi = toLogOdds(params_.free_threshold);
    for (size_t i : evidence_) {
      if (inside != nullptr && (i >= inside->size() || (*inside)[i] == 0)) {
        continue;                      // 视野外：保持原状（不衰减、不清除）
      }
      applyDecay(i, free_hi);
    }
  }

  // 同上，但视野判定用**画幅包围盒 + 调用方的内联判据**（不再构造整张 `inside`）。
  //
  // `in_view(idx, x, y)` 由调用方给：地图端传的是"多边形内 + 可信半径内"，
  // 与 `footprintContains` / `trustedRadius` 同一口径。包围盒先剪枝，
  // 只有落在盒内的格才调它 —— 判定次数与画幅面积成正比，与整图面积无关。
  template<typename InView>
  void decayMissInBox(int x0, int y0, int x1, int y1, InView && in_view)
  {
    const double free_hi = toLogOdds(params_.free_threshold);
    for (size_t i : evidence_) {
      const int x = static_cast<int>(i % static_cast<size_t>(width_));
      const int y = static_cast<int>(i / static_cast<size_t>(width_));
      if (x < x0 || x > x1 || y < y0 || y > y1) {continue;}
      if (!in_view(i, x, y)) {continue;}
      applyDecay(i, free_hi);
    }
  }

  // ---- 观测空窗衰减（2026-11-09 用户裁定 Q19）----
  //
  // **为什么需要它**：`decayMiss()` 每帧对所有观测过的格一视同仁地轻衰减，
  // 但它无法区分"刚刚还在看"与"已经飞出视野很久了"。实测（520 帧离线数据）：
  // **35% 的误覆盖格在相机当前画幅之外** —— 那是飞过去之后留下的陈旧残留，
  // 相机再也不会去修正它们，而 `p_decay` 太弱（0.48），衰减到 free 门限要几十秒。
  //
  // **判据**：某格**超过 `stale_after_frames` 帧没有被任何射线扫到** ⇒ 按 `p_decay`
  // 持续衰减；衰减到 `free_threshold` 以下就**清成 unknown**（不是 free —— 我们
  // 并没有看到它是空的，只是很久没看了）。
  //
  // 取 3 s：3 s 内相机至少移动 6 m、画幅挪动 6 m，正常应该扫到；扫不到说明
  // 它已在视野外，旧证据不该无限保鲜。
  //
  // 实现：`last_seen_frame_` 记每格最后被 hit 或被射线穿过的帧号；
  // `markStale()` 每帧调一次，只处理超窗且仍有证据的格（`hit_count>0`），
  // **未观测过的格不受影响**（与 `decayMiss` 同一纪律：绝不把未知当自由）。
  //
  // **2026-11-10 语义修正（ADR-0039）：已确认占据**不再永久保鲜**。**
  // 旧实现在这里对 `logodds >= occupied_threshold` 的格直接 `continue`，理由是
  // "建筑物不会因为 3 秒没被看到就消失"。那个理由对**真实**障碍成立，但它把
  // "误 hit 建起来的 occupied" 也一起保护了，而误 hit 恰恰最容易落在**画幅外 /
  // 遮挡区 / 射线没穿过的位置** —— carving 够不到，时间也不削弱，于是永久驻留。
  // 实测（dense_map）：误覆盖 0.727、面积比 1.801，且误覆盖格中大量是"从首帧就在、
  // 每帧都出现"的稳定锁死格，不是随机噪声。
  //
  // 现在的三段语义（与 temp.md 的建议逐条对应）：
  //   * occupied + 最近有正向 hit            → 保持 occupied（不变）
  //   * occupied + 超过 `occupied_expire_frames` 没有正向 hit → 按 `p_decay` 削弱，
  //     降到 `occupied_exit_threshold` 以下就**退出 occupied**，一路降到
  //     `unknown_floor_p` 为止（**unknown，不是 free**）
  //   * 射线明确穿过（`observeMiss` / 强 carve）→ 才允许继续降到 free
  //
  // 用 `last_hit_frame_`（**只记正向 hit**）而不是 `last_seen_frame_`（含射线穿过）：
  // 射线穿过只证明"这格是空的"，不能刷新"我还看到这里有障碍"的生命周期。
  void markStale(long frame_idx, long stale_after_frames)
  {
    if (stale_after_frames <= 0) {return;}
    const double occ_lo = toLogOdds(params_.occupied_threshold);
    const double floor_lo = toLogOdds(params_.unknown_floor_p);
    const long expire = params_.occupied_expire_frames;
    // **只遍历有证据格索引**（2026-11-09 性能修复）：改造前每帧扫全图，
    // 而真正有证据的格只是其中一小部分。
    for (size_t i : evidence_) {
      if (hit_count_[i] <= 0) {continue;}                 // 从没观测过 → 不动
      if (frame_idx - last_seen_frame_[i] <= stale_after_frames) {continue;}
      if (logodds_[i] >= occ_lo) {
        // ---- occupied 的生命周期（ADR-0039）----
        if (expire <= 0) {continue;}                      // 关闭：旧口径
        if (frame_idx - last_hit_frame_[i] <= expire) {continue;}   // 仍在有效期内
        // 已过期：按弱证据削弱，但**只降到 unknown_floor_p**，绝不降到 free。
        if (!takeNegativeSlot(i)) {continue;}
        if (logodds_[i] <= floor_lo) {continue;}
        logodds_[i] = std::max(floor_lo, logodds_[i] + decay_inc_);
        continue;
      }
      // **与 carve / 时间衰减共用"每帧一次负证据"槽位**（2026-11-09）：
      // 同一帧里 stale + decay + carving 三套负证据叠加，会把过渡带格直接推出门限，
      // 那是"边缘格反复跨门限"的直接来源之一。
      if (!takeNegativeSlot(i)) {continue;}
      if (logodds_[i] <= floor_lo) {continue;}
      logodds_[i] = std::max(floor_lo, logodds_[i] + decay_inc_);
    }
  }

  long framesSinceSeen(size_t idx) const
  {
    return inRange(idx) ? (current_frame_ - last_seen_frame_[idx]) : -1;
  }

  // 距最后一次**正向 hit** 的帧数（occupied 生命周期判据；诊断与单测用）。
  long framesSinceHit(size_t idx) const
  {
    return inRange(idx) ? (current_frame_ - last_hit_frame_[idx]) : -1;
  }

  void beginFrame(long frame_idx) {current_frame_ = frame_idx;}

  // **地图帧**（发布拍）推进：`min_hits_for_occupied` 的计数单位是它，不是感知帧。
  //
  // 感知回调 10 Hz、`/agc/map` 2 Hz，迟滞状态只在发布拍推进。若确认门槛按感知帧
  // 计数，"K=2" 在对外地图上实际只用了 0.2 s，语义弱 5 倍且随感知帧率漂移。
  // 调用方（`map_adapter`）只在快照拍调它 —— 与 `occupied_now_` 同一个时钟。
  void beginMapFrame(long map_frame_idx) {current_map_frame_ = map_frame_idx;}

  // 当前地图帧号（诊断 / 单测用）。
  long currentMapFrame() const {return current_map_frame_;}

  // 某格累计被命中的**地图帧数**（不是感知帧数）—— `min_hits_for_occupied` 的判据量。
  int mapFrameHitsAt(size_t idx) const {return inRange(idx) ? map_frame_hits_[idx] : 0;}

  // 当前帧号（诊断 / 单测用）。
  long currentFrame() const {return current_frame_;}

  double probAt(size_t idx) const
  {
    return inRange(idx) ? fromLogOdds(logodds_[idx]) : 0.0;
  }

  int hitsAt(size_t idx) const {return inRange(idx) ? hit_count_[idx] : 0;}

  // 逐格元数据（ADR-0042，temp.md 方向一 / 方向四 A+B）。
  //
  // **为什么置信度不能直接复用 `probAt`**：`probAt` 是"这一格是障碍的概率"，
  // 它同时受"证据方向"（高/低）与"证据量"（多/少）影响。
  // 一个被看过 50 次、确认是空的格，`probAt` 很低，但它的**判断很可靠**。
  // 而 temp.md 要的"置信度"问的是后者：这个判断有多可信。
  //
  // 口径：证据离中性的距离，按观测次数归一 —— 观测次数越多越接近 1。
  // 0 次观测 ⇒ 0（没有任何证据，判断不可信）。
  double confidenceAt(size_t idx) const
  {
    if (!inRange(idx)) {return 0.0;}
    const int n = hit_count_[idx];
    if (n <= 0) {return 0.0;}
    // 饱和曲线：1 次 ≈ 0.4、2 次 ≈ 0.55、5 次 ≈ 0.80、10 次 ≈ 0.93。
    // 与 `ObstacleInstance::confidence` 同一形状，避免两处给出互相矛盾的说法。
    return std::min(1.0, 1.0 - std::exp(-0.3 * static_cast<double>(n)));
  }

  // 该格最近一次**被观测到**的帧号；-1 = 从未被观测。
  //
  // **为什么不用 `framesSinceSeen` 的返回值反推**：那个返回值是"距现在多少帧"，
  // 而发布端需要的是"那次观测是**什么时候**"。时间戳由调用方按帧号换算，
  // 换算比例必须是**实测帧率**（帧率在 6–10 Hz 之间变），不能写死。
  long lastSeenFrameAt(size_t idx) const
  {
    if (!inRange(idx)) {return -1;}
    return (hit_count_[idx] > 0) ? last_seen_frame_[idx] : -1;
  }

  // 有证据的格数（hit 过或被 carve 过）。诊断用：它是衰减/空窗的遍历规模。
  size_t evidenceCount() const {return evidence_.size();}

  // 快照为 int8 栅格：**-1=unknown / 0..100 = 占据概率×100**（对齐 OccupancyGrid 约定）。
  //
  // **2026-11-08 修复（用户裁定 Q19/Q25）**：原实现把内部 double 概率压成三态
  // （0 / 100 / -1），把已经算出来的置信度**对外丢掉了**。
  // `nav_msgs/OccupancyGrid.data` 的语义本来就是"占据概率×100"，三态是对该消息的浪费；
  // 连续值让 RViz 的 costmap 着色直接显示梯度（"看到的就是车看到的"），
  // 也让消费者能按自己的阈值判"算不算障碍"，而不是被迫接受 100 这个二值。
  //
  // 两个门限仍然保留，但只用来**保证两端语义**：
  //   * ≥ occupied_threshold → 饱和为 100（稳定占据，不因 97/98 抖动）；
  //   * ≤ free_threshold     → 0（稳定空闲）；
  //   * 其余 → 量化到 1..99 的连续值。
  // unknown 恒为 -1（未观测 / 证据不足且不接近自由），**绝不量化成 0**：
  // 把没看过的地方当成自由空间是规划安全性的直接威胁。
  std::vector<int8_t> snapshot() const
  {
    std::vector<int8_t> out(logodds_.size(), -1);
    // **迟滞（2026-11-09 用户裁定）**：进入 occupied 用 `occupied_threshold`（0.60），
    // 退出用更低的 `occupied_exit_threshold`（0.45）。
    //
    // **为什么需要**：单门限下，概率在 0.60 附近抖动的格会在 100 与 1–99 之间反复翻转，
    // 实测 |Δoccupied| p99 = 343 格（判据 ≤50），这是"形状一直在变"的主要来源。
    // 迟滞把"进"和"出"分开，抖动带内的格保持原状态不变。
    //
    // 用 `occupied_now_`（上一次快照的结果）判定是否已在 occupied 态 ——
    // 所以本重载**更新**该缓存。为保持既有调用方兼容，保留 const 语义（缓存是 mutable），
    // 但**推进时机的责任在调用方**：地图端只在发布拍调用它，证据更新拍不调用。
    // 单测里连续调用是合法的（等价于"每次都发布"）。
    const double enter = params_.occupied_threshold;
    const double exit = params_.occupied_exit_threshold;
    // **跨帧确认门槛**（ADR-0039）：进入 occupied 除了概率过门限，还要累计够
    // `min_hits_for_occupied` 次**跨帧** hit。把"至少两帧"写成独立的门，参数标定
    // 就无法通过调 p_hit / 门限把它静默绕成"单帧即画"。
    const int need_hits = std::max(1, params_.min_hits_for_occupied);
    for (size_t i = 0; i < logodds_.size(); ++i) {
      const double p = fromLogOdds(logodds_[i]);
      const bool was_occ = occupied_now_[i] != 0;
      const bool enough_hits = map_frame_hits_[i] >= need_hits;
      const bool is_occ = enough_hits && (was_occ ? (p >= exit) : (p >= enter));
      occupied_now_[i] = is_occ ? 1 : 0;
      if (is_occ) {
        out[i] = 100;
      } else if (p <= params_.free_threshold) {
        out[i] = 0;
      } else if (hit_count_[i] > 0 || logodds_[i] < init_lo_) {
        // 有证据但未跨门限：输出量化概率（1..99），保留"比中性更可能/更不可能"的信息。
        // 判据用 hit_count>0 或低于初始值，保证"从没观测过"的格仍是 -1。
        int q = static_cast<int>(std::lround(p * 100.0));
        out[i] = static_cast<int8_t>(std::min(99, std::max(1, q)));
      } else {
        out[i] = -1;
      }
    }
    return out;
  }

  // **复用缓冲的快照**（发布热路径用）：内容写入内部的 `snapshot_` 并返回它的 const 引用。
  //
  // 为什么单独一个重载而不是让 `snapshot()` 返回引用：`snapshot()` 的既有调用方
  // （单测、一次性查询）按值取用、可自由持有；发布端每拍都要一整张栅格，
  // 按值返回等于每拍分配 4 万字节。这里让发布端零分配，语义不变。
  //
  // **注意**：返回的引用在下一次调用本函数或 `reset()` 后失效 —— 调用方必须
  // 在拍内用完（地图端就是 `std::copy` 进消息）。
  const std::vector<int8_t> & snapshotIntoBuffer() const
  {
    const double enter = params_.occupied_threshold;
    const double exit = params_.occupied_exit_threshold;
    const int need_hits = std::max(1, params_.min_hits_for_occupied);
    const size_t n = logodds_.size();
    if (snapshot_.size() != n) {snapshot_.assign(n, -1);}
    for (size_t i = 0; i < n; ++i) {
      const double p = fromLogOdds(logodds_[i]);
      const bool was_occ = occupied_now_[i] != 0;
      const bool enough_hits = map_frame_hits_[i] >= need_hits;
      const bool is_occ = enough_hits && (was_occ ? (p >= exit) : (p >= enter));
      occupied_now_[i] = is_occ ? 1 : 0;
      if (is_occ) {
        snapshot_[i] = 100;
      } else if (p <= params_.free_threshold) {
        snapshot_[i] = 0;
      } else if (hit_count_[i] > 0 || logodds_[i] < init_lo_) {
        int q = static_cast<int>(std::lround(p * 100.0));
        snapshot_[i] = static_cast<int8_t>(std::min(99, std::max(1, q)));
      } else {
        snapshot_[i] = -1;
      }
    }
    return snapshot_;
  }

  // 已确认占据的格数（供诊断与"内容是否变化"判定）。
  long occupiedCount() const
  {
    long n = 0;
    for (double v : logodds_) {
      if (fromLogOdds(v) >= params_.occupied_threshold) {++n;}
    }
    return n;
  }

  const LogOddsParams & params() const {return params_;}

  // -------------------------------------------------------------------------------
  // free-space carving（射线穿透）：2026-11-08 用户裁定 Q3 —— 本次的**根因修复**
  // -------------------------------------------------------------------------------
  //
  // **为什么必须有它**：`decayMiss()` 只能表达"这格曾经被看到、现在没再看到"，
  // 表达不了"**明确看到这格是空的**"。没有负证据，地图就只会单调生长：
  // 障碍的旧形状永远不会被擦除，物体移动/视角变化留下的残影会永久驻留。
  //
  // 做法（与 ego-planner `plan_env/src/raycast.cpp` 同一思路，只是 2D）：
  // 从观测点（相机地面投影）到障碍落点做 Bresenham 遍历，**途经的格**调用 observeMiss，
  // **终点格**不 carve（那是障碍本身）。
  //
  // 坐标系：栅格坐标（列 ix、行 iy），与 `snapshot()` 的索引 `iy*width + ix` 一致。
  // 返回途经格数（供诊断）；越界自动裁剪，不会抛错。
  int carveRay(int x0, int y0, int x1, int y1)
  {
    return carveRay(x0, y0, x1, y1, false);
  }

  // -------------------------------------------------------------------------------
  // 带**阴影远边**的射线：2026-11-09 用户裁定 Q13/Q14/Q16 —— 补上"看不见"与"安全"的区别
  // -------------------------------------------------------------------------------
  //
  // **原实现的缺口（用户实测发现）**：`observeMiss` 只在射线打到障碍时被调用，
  // 而射线终点**只能是障碍点** ⇒ **没有障碍的方向永远不会产生任何负证据**，
  // 那片区域永远是 unknown（灰色）。而 yard 的障碍只占作业区 11.5%，
  // 绝大多数方向没有障碍 —— 于是整张图基本是灰的，规划被大幅限制。
  // 用户原话："到边缘都没检测到障碍物那就是安全啊"。
  //
  // **但"射到边界就全标自由"也是错的**（我第一版的错，用户当场否掉）：
  // 沿一条射线，遮挡是**三段**的（相机高 H、障碍高 h、障碍距 d_o）：
  //   ① 相机 → d_o          ：可见（障碍前面）
  //   ② d_o → d_o·H/(H−h)   ：**真看不见**（阴影区，楼后）
  //   ③ d_o·H/(H−h) → 边界  ：**又可见了**（视线从楼顶掠过）
  // 矮障碍（路缘 0.2 m、矮台 0.5 m）的阴影只有 0.2–0.5 m，后面**应该**标安全；
  // 高楼（admin_block 10.55 m）在 15 m 处的阴影到 57.9 m，已超出 30.5 m 边界。
  // ⇒ 必须**按实际高度精确算**阴影远边，不能一刀切。
  //
  // **阴影区（②）标什么**：不标自由、也不标障碍 —— 保持 unknown。
  // 语义依据是 `agc_ground/planning_policy.hpp` 的三态：unknown **不是障碍**
  // （规划器可以走，直连兜底就是为此设的），只是不享受"已确认安全"的待遇。
  // 把它标成 free 会让规划器以为"这条路我确认过"，那是过度承诺。
  //
  // **参数**：
  //   * `shadow_end_cells`：阴影区结束的格距离（= ③ 的起点）。0 表示无阴影。
  //     传入时 `x1,y1` 是**可见边界**的格坐标（不是障碍点）。
  //   * `weak`：弱负证据（用 `p_decay` 而非 `p_miss`）。用于画幅边缘 10% ——
  //     那里 GSD 恶化 1/cos²（65° 时 5.6×），"没看到"确实不如中心可信。
  //
  // 返回途经（打了 miss 的）格数，供诊断。
  // `obstacle_cells`（可选）：本帧被观测为**障碍**的格索引集合。
  // 途经格若在其中则**不打 miss** —— 否则宽障碍会被自己的 carve 擦掉：
  // 14.5 m 宽的楼在 15 m 处占 51.6°（512 箱里 73 个），而每箱只射一条到**最近点**，
  // 楼宽方向上的其余格会被射线穿过 ⇒ 实测 **69.6% 的可见真值障碍被标成 free**。
  int carveRay(int x0, int y0, int x1, int y1, bool weak, double shadow_end_cells = 0.0,
               const std::vector<char> * obstacle_cells = nullptr)
  {
    if (width_ <= 0 || height_ <= 0) {return 0;}
    int n = 0;
    int dx = std::abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
    int dy = -std::abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;
    int x = x0, y = y0;
    // 起点到终点的总格距（用于与 shadow_end 比较）
    const double total = std::hypot(static_cast<double>(x1 - x0),
                                    static_cast<double>(y1 - y0));
    const double shadow_end = std::max(0.0, std::min(shadow_end_cells, total));
    // **增量距离**（2026-11-09 性能修复）：Bresenham 每步只动一个坐标（或两者），
    // 距离可增量更新，不必每格调一次 `hypot`。改造前每条射线每格一次 hypot，
    // 512 条 × 30 格 = 每帧 1.5 万次开方，纯属浪费（方向与步长都已知）。
    //
    // 用"沿轴累计步数"表达距离：Bresenham 的格距与欧氏格距在 8 连通下
    // 最多差 √2 倍，而 shadow_end 本身就是**格数量级**的粗判据（阴影远边来自
    // 高度比，误差以米计）—— 用轴向步数近似不改变任何可见行为，却省掉全部开方。
    double dist_here = 0.0;
    // 终点格（障碍落点 / 边界格）**不** carve：前者是占据证据本身，
    // 后者已在边界上（再往外就越界了）。
    while (!(x == x1 && y == y1)) {
      // 阴影区内（距起点 < shadow_end）**不**打 miss：那是真看不见，不是看到空的
      const bool in_shadow = shadow_end > 0.0 && dist_here < shadow_end;
      if (!in_shadow && x >= 0 && y >= 0 && x < width_ && y < height_) {
        const size_t idx = static_cast<size_t>(y) * width_ + x;
        // **射线被障碍挡住**（2026-11-09 修复，本次覆盖率的最大杀手）：
        // 途经格若**当前已被判为 occupied**，射线到此为止，后面不再打 miss。
        //
        // **为什么不能只靠外部传的 `obstacle_cells`**：那个掩码只含**本帧**的障碍点，
        // 而 carve 沿途擦的是**历史累积**的障碍格 —— 历史障碍不在本帧掩码里，仍被擦掉。
        // 实测后果：65.6% 的可见真值障碍被标成 free，覆盖率只有 0.325；
        // 覆盖率曲线在 3 s 达峰 0.29 后一路下滑（地图先建后毁）。
        // 物理上正确：射线撞到墙就停，不能"穿过"墙去擦它后面的东西。
        //
        // **2026-11-09 追加**：本帧已被 hit 的格同样算"墙"（`hitThisFrame`）。
        // 射线终点是**本帧障碍点的最近者**，但宽障碍的其余格不在射线上 ——
        // 它们靠本帧 hit 保护，不再依赖外部掩码的完整覆盖。
        //
        // **2026-11-10（ADR-0039）：遮挡体必须够可信。**
        // 旧口径把"历史 occupied"一律当墙，而 dense_map 里小障碍的"最近点"会因
        // 投影误差逐帧变化 ⇒ 这一帧的墙挡住射线、下一帧换了一堵墙，各自把对方
        // 后面的区域标 free，occupied 集合大幅互换（稳定性 p99 的主要来源）。
        // 现在只有**置信度 ≥ `occluder_min_confidence`** 的格才算墙；弱证据格
        // （候选 / 刚过期）射线可以穿过，但只施加**弱**负证据，不给强 miss。
        const double p_here = fromLogOdds(logodds_[idx]);
        const bool confirmed_occluder = p_here >= params_.occluder_min_confidence;
        if (confirmed_occluder || hitThisFrame(idx) ||
          (obstacle_cells != nullptr && idx < obstacle_cells->size() &&
          (*obstacle_cells)[idx]))
        {
          // 障碍格本身**不打 miss**（那是占据证据），并且射线**到此终止**
          break;
        }
        // 弱证据格（p < 遮挡门限）：射线穿过它，但**只削弱、不判 free** ——
        // 那里很可能就是这个方向的小障碍，我们没有足够证据说它是空的。
        const bool treat_weak = weak || (p_here >= params_.occupied_exit_threshold);
        if (treat_weak) {
          // 弱负证据：与 decayMiss 同力度（p_decay），但**只作用于这一格**
          if (takeNegativeSlot(idx)) {
            const double floor_lo = toLogOdds(params_.unknown_floor_p);
            if (logodds_[idx] > floor_lo) {
              logodds_[idx] = std::max(floor_lo, logodds_[idx] + decay_inc_);
            }
            last_seen_frame_[idx] = current_frame_;
            markEvidence(idx);
          }
        } else {
          observeMiss(idx);
        }
        ++n;
      }
      const int e2 = 2 * err;
      const bool moved_x = (e2 >= dy), moved_y = (e2 <= dx);
      if (moved_x) {err += dy; x += sx;}
      if (moved_y) {err += dx; y += sy;}
      // 8 连通下对角步长是 √2：按"实际走了几步"累计，与 `hypot` 的差异 < 1 格。
      dist_here += (moved_x && moved_y) ? 1.4142135623730951 : 1.0;
      // 防御：起终点相同时 while 条件已在入口排除；这里再防一次不收敛
      if (n > width_ + height_ + 2) {break;}
    }
    return n;
  }

private:
  // 记入"有证据格索引"（只加一次）。索引用于 markStale / 衰减的稀疏遍历。
  void markEvidence(size_t idx)
  {
    if (in_evidence_[idx] != 0) {return;}
    in_evidence_[idx] = 1;
    evidence_.push_back(idx);
  }

  // 取本帧的**负证据槽位**：每格每帧最多一次，且**同帧已被 hit 的格不再吃负证据**。
  //
  // 返回 false 表示本帧该格已经用过（或已被 hit 保护），调用方应跳过这次负证据。
  // 这是"同一帧 hit 与 miss 不得互相抵消"与"stale/decay/carve 不得三重叠加"的
  // 同一个实现点 —— 三者共用这一个槽位。
  bool takeNegativeSlot(size_t idx)
  {
    if (hit_frame_[idx] == current_frame_) {return false;}   // 本帧看到障碍 → 负证据作废
    if (neg_frame_[idx] == current_frame_) {return false;}   // 本帧已用过负证据
    neg_frame_[idx] = current_frame_;
    return true;
  }

  // 单格时间衰减（两条路径共用，语义见 decayMissMasked 的注释）。
  //
  // **2026-11-10（ADR-0039）**：削弱下限从 `lo_`(p_min=0.12，**低于 free_threshold**)
  // 改成 `unknown_floor_p`(0.22，**高于 free_threshold**)。理由：纯时间流逝不该把格子
  // 推成 free —— 那等于把"没看见"当成"确认是空的"（ADR-0035 (g) 的三态纪律）。
  // free 只由真实射线穿过给出（`observeMiss` / 强 carve）。
  void applyDecay(size_t i, double free_hi)
  {
    const double floor_lo = toLogOdds(params_.unknown_floor_p);
    if (hit_count_[i] > 0) {
      if (!takeNegativeSlot(i)) {return;}
      if (logodds_[i] <= floor_lo) {return;}
      logodds_[i] = std::max(floor_lo, logodds_[i] + decay_inc_);
      return;
    }
    // **只被 carve 成 free 的格也要能回到 unknown**（2026-11-09 修复）。
    //
    // 原实现只衰减 `hit_count>0` 的格，于是被 carve 标成 free 的格**永不衰减**
    // ⇒ free 具有粘滞性。实测：`free ∩ 真值` 从 239 格单调涨到 2600 格并锁死，
    // 其中 **92.4% 在当前画幅之外**（中位距相机 44.3 m，画幅仅 30.5 m）——
    // 那是相机早期靠近时边界射线误穿障碍留下的，飞远后再无机会修正。
    //
    // 语义：**"很久没复查的空"不该永远等于"空"**。衰减回 unknown（不是变成障碍）
    // 是正确的保守方向：规划器仍然可以走（unknown 不是障碍），只是不再享受
    // "已确认安全"的待遇。与 `markStale` 的纪律一致。
    if (logodds_[i] <= free_hi) {
      if (!takeNegativeSlot(i)) {return;}
      logodds_[i] = std::min(free_hi, logodds_[i] + decay_inc_);
    }
  }

  LogOddsParams params_;
  int width_{0};
  int height_{0};
  std::vector<double> logodds_;
  std::vector<int> hit_count_;
  // 每格最后被观测（hit 或射线穿过）的帧号；用于"观测空窗衰减"（Q19）
  std::vector<long> last_seen_frame_;
  // 每格最后被**正向 hit** 的帧号（不含射线穿过）：occupied 生命周期判据（ADR-0039）
  std::vector<long> last_hit_frame_;
  // 地图帧口径的确认计数（ADR-0039 补正）：`min_hits_for_occupied` 判据量。
  // 与 `hit_count_`（感知帧）分开——迟滞状态按发布拍推进，门槛必须挂同一个时钟。
  std::vector<long> map_hit_frame_;
  std::vector<int> map_frame_hits_;
  // 本帧该格的独立点数与 z 展布（空间支持门槛，ADR-0039）。用帧号惰性重置，
  // 不必每帧清零整张缓冲（见 addFramePoint 注释）。
  std::vector<int> point_frame_;
  std::vector<int> frame_points_;
  std::vector<double> frame_zmin_;
  // 本帧该格的最大逐点 1σ（m）。-1 = 无信息（发布端未提供）。
  std::vector<double> frame_sigma_max_;
  std::vector<double> frame_zmax_;
  // 每格本帧的 z 样本（稳健深度一致性用，见 depth_mad_k）。帧号惰性重置。
  std::vector<std::vector<double>> frame_zs_;
  // 上一次快照的 occupied 态（迟滞用）：1=occupied, 0=其它
  mutable std::vector<char> occupied_now_;
  // 每帧去重槽位：某格在本帧是否已被 hit / 已被负证据用过（-1 = 尚未记账）
  std::vector<long> hit_frame_;
  std::vector<long> neg_frame_;
  // 有证据格索引（hit 过 / 被 carve 过），供 markStale 与衰减稀疏遍历
  std::vector<size_t> evidence_;
  std::vector<char> in_evidence_;
  // 复用快照缓冲（发布热路径零分配）
  mutable std::vector<int8_t> snapshot_;
  long current_frame_{0};
  long current_map_frame_{0};
  double lo_{0.0};
  double hi_{0.0};
  double hit_inc_{0.0};
  double miss_inc_{0.0};
  double decay_inc_{0.0};
  double init_lo_{0.0};   // p_init 的 logit（快照判"是否观测过"用）
};



// ---------------------------------------------------------------------------------
// 栅格后处理：闭运算（填 1 格缝）+ 连通域标记（纯逻辑，可单测）
// ---------------------------------------------------------------------------------
//
// **为什么需要**（2026-11-08 实测）：log-odds 累积后，同一障碍的格子置信度不均匀 ——
// 被反复看到的格过了门限，边缘/偶尔被遮挡的格没过，整片就被切成碎块。
// 实测 `tank_pair_n` 被拆成 5 个框、`planter_row` 6 个、`container_yard_b` 4 个。
// 闭运算（先膨胀后腐蚀，3×3）填掉"1 格缝"，碎块合回一个；
// 同时不会合并真有间隔的障碍（yard 里间隙 <1 格的只有 1 对）。
//
// 连通域用 **8 邻域**：闭运算后碎块常只剩对角相接，4 邻域仍会分开它们。

// 形态学操作：dilate=true 为膨胀，false 为腐蚀（3×3 方形核，越界视为 0）。
inline std::vector<uint8_t> morph3x3(
  const std::vector<uint8_t> & src, int w, int h, bool dilate)
{
  std::vector<uint8_t> dst(src.size(), 0);
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      bool any = false, all = true;
      for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
          const int nx = x + dx, ny = y + dy;
          const uint8_t v = (nx < 0 || ny < 0 || nx >= w || ny >= h) ? 0
            : src[static_cast<size_t>(ny) * w + nx];
          if (v) {any = true;} else {all = false;}
        }
      }
      dst[static_cast<size_t>(y) * w + x] = dilate ? (any ? 1 : 0) : (all ? 1 : 0);
    }
  }
  return dst;
}

// 闭运算 = 先膨胀后腐蚀（填 1 格宽缝，保持整体外轮廓基本不变）。
inline std::vector<uint8_t> close3x3(const std::vector<uint8_t> & src, int w, int h)
{
  return morph3x3(morph3x3(src, w, h, true), w, h, false);
}

// 一个连通域的外接框（像素坐标，含端点）与格数。
struct GridBlob
{
  int x0{0}, y0{0}, x1{0}, y1{0};
  int cells{0};
};

// 8 邻域连通域标记，返回每个 blob 的外接框。min_cells 过滤残余噪声。
//
// `bbox_mask`（可选）：**连通性**用 mask 判定，但**外接框与格数**只统计 bbox_mask
// 为真的格。用途：闭运算后碎块能连成一片（用 closed 判连通），但膨胀会把边缘
// 1 格内的零散格子也算进来、撑大外框（实测 sx 因此以 0.5 m 步长漂移 7.0↔6.0）。
// 传入原始 occupied 掩码即可：分组靠闭运算，尺寸靠真实占据格。
inline std::vector<GridBlob> labelBlobs8(
  const std::vector<uint8_t> & mask, int w, int h, int min_cells,
  const std::vector<uint8_t> & bbox_mask = {})
{
  std::vector<GridBlob> out;
  if (w <= 0 || h <= 0 || mask.size() != static_cast<size_t>(w) * h) {return out;}
  std::vector<int> label(mask.size(), 0);
  int next = 0;
  std::vector<int> stack;
  for (int i = 0; i < w * h; ++i) {
    if (mask[i] == 0 || label[i] != 0) {continue;}
    ++next;
    const bool use_bbox = bbox_mask.size() == mask.size();
    auto counts = [&](int cx, int cy) {
        return !use_bbox || bbox_mask[static_cast<size_t>(cy) * w + cx] != 0;
      };
    // 用"反向初值"：x0 取最大、x1 取最小，只有真正参与外框的格才会把它撑开。
    // 这样若整个 blob 都由膨胀产物组成（cells==0），它会因 min_cells 被过滤。
    GridBlob b{w, h, -1, -1, 0};
    stack.assign(1, i);
    label[i] = next;
    while (!stack.empty()) {
      const int cur = stack.back(); stack.pop_back();
      const int cx = cur % w, cy = cur / w;
      if (counts(cx, cy)) {
        b.x0 = std::min(b.x0, cx); b.x1 = std::max(b.x1, cx);
        b.y0 = std::min(b.y0, cy); b.y1 = std::max(b.y1, cy);
        ++b.cells;
      }
      for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
          if (dx == 0 && dy == 0) {continue;}
          const int nx = cx + dx, ny = cy + dy;
          if (nx < 0 || ny < 0 || nx >= w || ny >= h) {continue;}
          const size_t ni = static_cast<size_t>(ny) * w + nx;
          if (mask[ni] == 0 || label[ni] != 0) {continue;}
          label[ni] = next;
          stack.push_back(static_cast<int>(ni));
        }
      }
    }
    if (b.cells >= min_cells) {out.push_back(b);}
  }
  return out;
}
}  // namespace agc_perception

#endif  // AGC_PERCEPTION__LOG_ODDS_GRID_HPP_
