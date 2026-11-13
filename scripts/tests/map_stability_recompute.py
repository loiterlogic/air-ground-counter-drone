"""地图稳定性离线复算 —— 把「|Δoccupied| p99 ≤ 50 格」判据变成可复跑的数字。

**为什么需要它**：2026-11-08 用户反馈"障碍物形状面积一直在变"，而当时唯一的量化证据
是**一次实跑日志**里数出来的（`experiments/demo/20261108-185640/launch.log`：
651 次重建、单次最大 Δ=2291 格）。一次实跑不可复现、也不能在改参数后立刻复验。

本脚本按 `log_odds_grid.hpp` 的**同一套参数与语义**离线复刻一遍：
  * 真值障碍栅格化（读 `yard.yaml`，0.5 m 格）
  * UAV 沿 standoff 环连续移动（每步位移 ≤ 1.0 m，对应 2 m/s × 2 Hz 地图更新）
  * 每帧：可见障碍格 +hit → 相机到障碍近边射线 carve → 全局 decay
  * 统计稳态 |Δoccupied|

**判据**：稳态 p99 ≤ 50 格（冷启动帧不计：那是初始填充，不是抖动）。

**边界（不得外推）**：本脚本用的是**完美感知**（真值栅格），不含分割/深度噪声、
不含 FOV 边缘截断、不含标签碎片。真实链路的抖动只会**大于**这里的数字，
所以它是**下界**证据 —— 通过不代表实跑一定稳，但**不通过就肯定不稳**。

**⚠ 2026-11-09 保真度修正后本判据未通过（p99=112），如实登记**：

改造前本脚本**没有**建模 `carveRay()` 的"射线遇到已判 occupied 的格即停"
（`log_odds_grid.hpp` 的现行语义，2026-11-09 为修覆盖率而加）。缺这一条时，
carve 可以一路穿过历史障碍去擦它后面的格 —— 于是 occupied 长期被压在 ~505 格
（真值 4590 格，覆盖率仅 11%），抖动自然小。补上之后 occupied 稳定在 ~1600 格
（TP 1514 / FP 0），**覆盖率高 3.4 倍且误覆盖仍为 0**，代价是增长期更长、
p99 从 48 升到 112。

因此 48 这个数字是**模型失真**的产物，不是系统改善：它对真实链路的 140 不构成
有效下界（48 ≪ 140），而 112 是（112 < 140）。**判据阈值不得据此事后调整**
（预登记纪律）。

**2026-11-09 口径细化（用户裁定）**：统计窗口从"仅排除冷启动帧"细化为
"排除冷启动帧 **+** 增长期"。增长期 = occupied 首次达到本圈峰值
`GROWTH_SETTLE_RATIO`（90%）之前的帧 —— 那里每帧新进入画幅的障碍是**合法增长**，
不是用户反馈的"形状面积一直在变"。边界由 occupied 序列**推出**，不是手填帧数
（手填数字换轨迹/场景后静默失效）。阈值 `≤ 50` **未改**。

细化后：p99 **112 → 54**（增长期 frame 0..41，occupied 峰值 1796）。**仍未达标**
（54 > 50），本脚本如实返回非 0。剩余 4 格差距的来源是饱和段仍缓慢爬升
（seq 从 1599 继续涨到 1796），属"新进入画幅的障碍"而非门限抖动 ——
**不得**据此再放宽阈值。

用法：`python3 scripts/tests/map_stability_recompute.py`
退出码：0 = 判据通过；1 = 未通过。
"""
import math, json, random, subprocess, sys

# 直接调用 C++ 版语义太重；这里按 log_odds_grid.hpp 的参数逐条复刻（数值必须一致）
P_INIT, P_HIT, P_MISS, P_DECAY = 0.30, 0.70, 0.25, 0.48
P_MIN, P_MAX, OCC, FREE = 0.12, 0.97, 0.60, 0.20
def lo(p): return math.log(p/(1-p))
def pr(l): return 1-1/(1+math.exp(l))
HI, LO_ = lo(P_MAX), lo(P_MIN)
HIT, MISS, DECAY = lo(P_HIT), lo(P_MISS), lo(P_DECAY)

class Grid:
    """按 `log_odds_grid.hpp` 的现行语义复刻。

    **证据单位 = 每格每帧一次**（2026-11-09 用户裁定）：同一格在同一帧内最多贡献
    一次 hit、一次负证据，且**同帧 hit 优先于 miss**。改造前按 footprint 点计数，
    证据强度取决于像素采样密度 —— 那是 `|Δoccupied| p99` 虚高的直接来源。
    本脚本按帧号记账，与 C++ 侧的 `hit_frame_` / `neg_frame_` 槽位一一对应。
    """
    def __init__(s, w, h):
        s.w, s.h = w, h
        s.v = [lo(P_INIT)]*(w*h)
        s.hits = [0]*(w*h)
        s.frame = 0
        s.hit_frame = [-1]*(w*h)
        s.neg_frame = [-1]*(w*h)
    def begin(s, f):
        s.frame = f
    def hit(s, i):
        if s.hit_frame[i] == s.frame: return      # 帧内幂等
        s.hit_frame[i] = s.frame
        s.v[i] = min(HI, s.v[i]+HIT); s.hits[i] += 1
    def _take_neg(s, i):
        if s.hit_frame[i] == s.frame: return False   # 本帧看到障碍 → 负证据作废
        if s.neg_frame[i] == s.frame: return False   # 本帧已用过负证据
        s.neg_frame[i] = s.frame
        return True
    def miss(s, i):
        if not s._take_neg(i): return
        s.v[i] = max(LO_, s.v[i]+MISS)
    def decay(s):
        for i in range(len(s.v)):
            if s.hits[i] > 0 and s._take_neg(i):
                s.v[i] = max(LO_, s.v[i]+DECAY)
    def carve(s, x0,y0,x1,y1):
        dx,dy = abs(x1-x0), -abs(y1-y0)
        sx = 1 if x0<x1 else -1; sy = 1 if y0<y1 else -1
        err = dx+dy; x,y = x0,y0; n=0
        while not (x==x1 and y==y1):
            if 0<=x<s.w and 0<=y<s.h:
                idx = y*s.w+x
                # 射线遇 occupied 即停（与 C++ 的 carveRay 同语义）
                if pr(s.v[idx]) >= OCC: break
                s.miss(idx); n+=1
            e2 = 2*err
            if e2>=dy: err+=dy; x+=sx
            if e2<=dx: err+=dx; y+=sy
            if n > s.w+s.h+2: break
        return n
    def snap(s):
        out=[]
        for i,v in enumerate(s.v):
            p = pr(v)
            if p >= OCC: out.append(100)
            elif p <= FREE: out.append(0)
            elif s.hits[i]>0 or v < lo(P_INIT): out.append(max(1,min(99,round(p*100))))
            else: out.append(-1)
        return out
    def occ(s): return sum(1 for v in s.snap() if v==100)

# yard 真值栅格（复用之前的栅格化逻辑）
import yaml
d=yaml.safe_load(open('src/agc_sim/config/maps/yard.yaml'))
RES, OX, OY, W, H = 0.5, -50.0, -50.0, 200, 200
def parts(o):
    ps=o.get('parts')
    if not ps: return [(0.0,0.0,float(o.get('yaw',0)),o)]
    a=float(o.get('yaw',0))
    return [(float(p.get('x',0)),float(p.get('y',0)),float(p.get('yaw',0))+a,p) for p in ps]
def inside(px,py,o):
    a=float(o.get('yaw',0))
    for lx,ly,pyaw,p in parts(o):
        wx=o['x']+lx*math.cos(a)-ly*math.sin(a); wy=o['y']+lx*math.sin(a)+ly*math.cos(a)
        dx,dy=px-wx,py-wy; c,si=math.cos(-pyaw),math.sin(-pyaw)
        u=dx*c-dy*si; v=dx*si+dy*c
        sz=p.get('size') or [0,0,0]; sh=(p.get('shape') or 'box').lower()
        if sh in ('cylinder','sphere'):
            if u*u+v*v<=sz[0]*sz[0]: return True
        elif abs(u)<=sz[0]/2 and abs(v)<=sz[1]/2: return True
    return False
def corners(o):
    a=float(o.get('yaw',0)); xs=[];ys=[]
    for lx,ly,pyaw,p in parts(o):
        wx=o['x']+lx*math.cos(a)-ly*math.sin(a); wy=o['y']+lx*math.sin(a)+ly*math.cos(a)
        sz=p.get('size') or [0,0,0]; sh=(p.get('shape') or 'box').lower()
        hx,hy=(sz[0],sz[0]) if sh in ('cylinder','sphere') else (sz[0]/2,sz[1]/2)
        c,s=math.cos(pyaw),math.sin(pyaw)
        for dx,dy in ((-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)):
            xs.append(wx+dx*c-dy*s); ys.append(wy+dx*s+dy*c)
    return min(xs),max(xs),min(ys),max(ys)

# 真值占据格
truth=[[0]*W for _ in range(H)]
centers=[]
for o in d['obstacles']:
    x0,x1,y0,y1=corners(o)
    centers.append((o['x'],o['y'],x1-x0,y1-y0))
    for j in range(max(0,int((y0-OY)//RES)), min(H-1,int((y1-OY)//RES))+1):
        for i in range(max(0,int((x0-OX)//RES)), min(W-1,int((x1-OX)//RES))+1):
            if not truth[j][i] and inside(OX+(i+0.5)*RES, OY+(j+0.5)*RES, o): truth[j][i]=1

def frame(g, uav_xy, radius=30.5):
    """模拟一帧：只看到视野圆内的障碍，并对可见障碍发射线 carve。

    **帧号先推进**：hit / carve / decay 必须落在同一个帧号上，
    否则"每格每帧一次"的去重槽位会跨帧错位。
    """
    g.begin(g.frame + 1)
    ux,uy = uav_xy
    ci,cj = int((ux-OX)//RES), int((uy-OY)//RES)
    visible=[]
    for j in range(H):
        for i in range(W):
            if not truth[j][i]: continue
            wx,wy = OX+(i+0.5)*RES, OY+(j+0.5)*RES
            if (wx-ux)**2+(wy-uy)**2 <= radius*radius:
                g.hit(j*W+i); visible.append((i,j))
    # carve：从相机到每个可见障碍近边
    for i,j in visible:
        wx,wy = OX+(i+0.5)*RES, OY+(j+0.5)*RES
        dx,dy = wx-ux, wy-uy; dist=math.hypot(dx,dy)
        if dist<1e-6: continue
        stop=max(0.0, dist-RES*1.5)
        ex,ey = ux+dx/dist*stop, uy+dy/dist*stop
        g.carve(ci,cj,int((ex-OX)//RES), int((ey-OY)//RES))
    g.decay()

random.seed(0)
g=Grid(W,H)
seq=[]
# UAV 沿 standoff 环**连续**移动（模拟真实 30 Hz 轨迹，非瞬间跳）
# 关键：真实 UAV 最大 2.0 m/s、地图 2 Hz 更新 ⇒ 每次更新最多移动 1.0 m。
# 环周长 2*pi*11.2 = 70.4 m，转一圈约 35 s；地图 2 Hz ⇒ 一圈约 70 次更新。
# 下面用 70 步模拟"一圈"，与真实更新节奏一致（原来 60 步跨度太大，等于瞬移）。
N_STEPS = 70
for k in range(N_STEPS):
    ang = 2*math.pi*k/N_STEPS
    uav=(15.0+11.2*math.cos(ang), -2.0+11.2*math.sin(ang))
    frame(g, uav)
    seq.append(g.occ())
# ---- 稳态窗口的判定（**可判定量，不是手填帧数**）----
#
# **为什么必须跳过增长期**：前若干帧是地图从 0 建到饱和的过程 —— 每帧新进入画幅的
# 障碍都是**合法增长**，不是抖动。用户反馈的"形状面积一直在变"针对的是**地图建好之后**
# 的相邻帧变化。把增长期算进 p99 等于拿"首次建图"当抖动，指标会被合法增长淹没。
#
# **为什么不用手填的帧数**：手填数字会在换轨迹 / 换场景 / 改帧率后静默失效，
# 而失效时它仍然是"一个数"，看不出已经不对。这里用**两条可判定的判据**：
#   ① 冷启动：第 0→1 帧（空地图→首次建图）恒排除；
#   ② 增长期：occupied 首次达到**本圈最大值的 kGrowthSettleRatio（90%）**之前的帧。
#      90% 的依据：地图从 0 长到饱和是单调爬升，达到峰值 9 成之后剩下的 10% 已是
#      边缘细调；而抖动发生在整个饱和段（实测饱和后仍缓慢爬升到 1796，见 seq）。
# 判据本身（p99 ≤ 50）**未改**，改的只是"统计哪一段"。
GROWTH_SETTLE_RATIO = 0.9
peak = max(seq)
settle = next((i for i, v in enumerate(seq) if v >= GROWTH_SETTLE_RATIO * peak), len(seq) - 1)

d_all = [abs(b - a) for a, b in zip(seq, seq[1:])]
# 稳态窗口：去掉冷启动那一次差分（下标 0）与增长期内的差分。
d = sorted(d_all[settle:])
print("离线复算（%d 帧，UAV 绕 standoff 环）：" % N_STEPS)
print("  occupied 序列 min/med/max = %d / %d / %d 格" % (
    min(seq), sorted(seq)[len(seq)//2], max(seq)))
print("  |Δoccupied| p50=%d p90=%d p99=%d max=%d 格" % (
    d[len(d)//2], d[int(.9*len(d))], d[min(int(.99*len(d)),len(d)-1)], d[-1]))
print("  真值占据格数 = %d" % sum(sum(r) for r in truth))
print("  （已排除冷启动帧 0->1：Δ=%d）" % d_all[0])
print("  （已排除增长期：frame 0..%d，occupied 首次达到峰值 %d 的 %d%%）" % (
    settle, peak, int(GROWTH_SETTLE_RATIO * 100)))
ok = d[min(int(.99*len(d)),len(d)-1)] <= 50
print("  判据（稳态 p99 ≤ 50 格）：%s" % ('✅ 通过' if ok else '❌ 未通过'))
sys.exit(0 if ok else 1)
