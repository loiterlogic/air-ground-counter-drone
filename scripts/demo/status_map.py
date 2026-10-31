#!/usr/bin/env python3
"""状态语义映射——**全项目唯一**的"开发词汇 → 观众人话"实现（P1-3）。

真源：[P1-3 状态语义映射](../../docs/archive/completion-20261031/p1-3-任务可观测与演示呈现.md#p1-3-goal)。
输入是 [`AgcTaskState.msg`](../../src/agc_msgs/msg/AgcTaskState.msg) 的 `state` 枚举与
`reason_code` 字符串；本模块**只翻译、不判定**——不改状态机、不改终态判据、不新增字段。

## 契约 C8（表述红线，写进代码防止手滑改坏）

`TRACKING_SUCCESS` 的语义是**"抵近并持续跟踪"**，**不得**表述为"拦截完成"（[#hard-constraints]）。
阶段 B 的"拦截"另有终态 `INTERCEPT_CONFIRMED`（网捕获 / 行为级干扰），两者不可混用。
`TRACKING_SUCCESS` 的**任何展示文案**都不含"拦截"二字；本模块用
[`assert_display_safe`](#status_map.py) 在导入期与回归测试里双向把关。

> 改文案前先读 [终态语义](../../docs/ROS2迁移交接文档.md#terminal-semantics)；
> 想加"拦截完成"之类的措辞，请先改契约——不要在这里偷偷改。

[#hard-constraints]: ../../docs/ROS2迁移交接文档.md#hard-constraints
"""

import re

# --------------------------------------------------------------------------------------
# 1. 状态枚举 → 人话（单一实现；panel / timeline / verdict 全部从这里取字）
# --------------------------------------------------------------------------------------

# (state, 内部名, 演示文案, 观众该理解什么)
# 文案表与 P1-3 计划第 1 节的表**逐行对应**，任何改动都要同步那一节。
STATE_ROWS = (
    (0, 'IDLE', '系统待命', '还没开始'),
    (1, 'AIR_SEARCH', '无人机搜索中', '在找目标'),
    (2, 'TARGET_ACQUIRED', '已发现目标', '看见了'),
    (3, 'GROUND_APPROACH', '地面车前往目标', '正在靠近'),
    (4, 'TRACKING_SUCCESS', '抵近并持续跟踪成功', '完成（阶段 A 跟踪，不是击落）'),
    (5, 'MISSION_FAILED', '未能在时限内达成', '失败 + 原因'),
    (6, 'ABORTED', '任务被中止', '外部中断'),
    (7, 'INTERCEPT_CONFIRMED', '拦截确认（网捕获/干扰）', '阶段 B：拦截达成'),
    (8, 'INFRA_FAILURE', '系统故障（非任务失败）', '环境问题，不算任务失败'),
)

# 任务终态（与 `agc_rl.termination.TERMINALS` 同口径：状态机锁存后不再变化）
TERMINAL_NAMES = frozenset({'TRACKING_SUCCESS', 'INTERCEPT_CONFIRMED', 'MISSION_FAILED',
                            'ABORTED', 'INFRA_FAILURE'})

_BY_NAME = {name: {'state': n, 'name': name, 'text': text, 'audience': audience}
            for n, name, text, audience in STATE_ROWS}
_BY_CODE = {n: _BY_NAME[name] for n, name, _t, _a in STATE_ROWS}

# 阶段 A 的"成功"= 跟踪成功；不得被读成拦截成功（C8）
PHASE_A_SUCCESS = 'TRACKING_SUCCESS'
PHASE_B_INTERCEPT = 'INTERCEPT_CONFIRMED'

# C8 表述红线：TRACKING_SUCCESS 的展示文案**一个"拦截/捕获"都不许出现**。
FORBIDDEN_IN_TRACKING = ('拦截', '捕获', '击落', '网捕')

# 任何展示文案都不得出现的措辞（会把"跟踪成功"读成"打下来了"）。
# ⚠ 这几个字面量**只允许出现在这里**：其它模块一律引用本表 / `PHASE_A_CAVEAT`，
#   不得再写一遍（否则静态禁词检查会失效——"到处都是例外"等于没有红线）。
FORBIDDEN_ANYWHERE = ('拦截完成', '拦截成功', '已经击落', '成功击落')

# 判定说明里给观众看的口径句：**不复制禁词**，只说清"跟踪 ≠ 阶段 B 拦截"。
PHASE_A_CAVEAT = ('口径      阶段 A「抵近并持续跟踪」成功；跟踪 ≠ 阶段 B 的拦截达成'
                  '（后者另有终态 INTERCEPT_CONFIRMED：CAPTURE_NET 物理捕获 / JAM_* 行为级干扰）。')
PHASE_B_CAVEAT = ('口径      阶段 B 拦截达成；具体方式由 reason_code 区分'
                  '（CAPTURE_NET 物理捕获 / JAM_* 行为级干扰）。')

# C8 提示语：**不是展示文案**（不代表观众看到的字），只供代码注释 / 文档 / 回归引用。
C8_NOTICE = ('C8：TRACKING_SUCCESS 的语义是「抵近并持续跟踪」，'
             '阶段 B 的拦截另有终态 INTERCEPT_CONFIRMED。')


# --------------------------------------------------------------------------------------
# 2. reason_code → 人话（"为什么成功 / 失败"）
# --------------------------------------------------------------------------------------

# 取值真源：`src/agc_task/src/task_manager.cpp` 的 setState / enterTerminal / fail 调用点，
# 以及 capture_adjudicator / jammer 的配套事件首 token。
REASON_ROWS = (
    # —— 常态推进 ——
    ('ok', '任务启动成功，进入空中搜索'),
    ('target_acquired', '目标观测新鲜且置信度达标，确认已发现目标'),
    ('ground_approach', '地面命令回路已闭环，地面车开始接近'),
    ('tracking_milestone', '目标在跟踪距离内连续驻留达到判定时长（跟踪里程碑）'),
    # —— 终态：成功 / 拦截 ——
    ('CAPTURE_NET', '物理捕获：发射网命中目标（阶段 B）'),
    ('JAM_RTL', '行为级干扰生效：目标返航（阶段 B）'),
    ('JAM_LAND', '行为级干扰生效：目标降落（阶段 B）'),
    ('JAM_HOLD', '行为级干扰生效：目标原地保持（阶段 B）'),
    ('JAM_LOST', '行为级干扰生效：目标失联（阶段 B）'),
    ('JAM_NONE', '未触发干扰'),
    # —— 终态：失败 / 中止 ——
    ('TIMEOUT', '任务时限（t_max_s，C4：超时一律算失败）内未达成判定条件'),
    ('abort', '收到外部中止请求'),
    # —— 非任务窗口的原因码：`/agc/ground/goal_info` 与 `/agc/task/dwell_event` 携带 ——
    #    （面板只显示 `/agc/task/state` 的 reason_code；这一段保证"看到也能翻译"，不冒充任务原因）
    ('FIXED_GOAL', '地面目标采用任务固定点（`goal_follow_target=false`）'),
    ('TARGET_FRESH', '地面目标取自新鲜的目标观测（含源时刻与 target_id）'),
    ('HOLD_LAST_VALID', '目标短时失效：在 `goal_hold_valid_s` 窗口内保持最后有效目标'),
    ('EXPIRED', '目标失效已超窗：显式判无效（地面安全停车）'),
    ('TARGET_LOST', '目标从未有效或已丢失：显式判无效（地面安全停车）'),
    ('TARGET_STALE', '目标观测超龄（新鲜度门限未过）'),
    ('TARGET_LOW_CONF', '目标置信度低于门限'),
    ('CAR_ODOM_STALE', '车地面里程计超龄（驻留判据不成立）'),
    ('CAR_ODOM_MISSING', '车地面里程计缺失（驻留判据不成立）'),
    ('TARGET_ID_CHANGED', '目标身份变化（驻留段重新计时）'),
    ('RANGE_EXCEEDED', '离开跟踪距离（驻留段重新计时）'),
    ('EPOCH_CHANGED', 'episode 变化（驻留段清零，不跨回合累计）'),
    ('TASK_PAUSED', '任务离开 active（中场/终态）导致驻留段中断'),
    # —— 终态：基础设施失败（门禁 / 链路，不是任务失败）——
    ('air_hover_timeout', '等待起飞完成超时：空中里程计在时限内未达悬停高度'),
    ('reset_failed', '场景复位确定性失败（重试仍失败）'),
    ('phase_reset_failed', '空中相位复位失败（C5 门禁）'),
    ('release_control_failed', '空中控制权交接（release_control）失败'),
    ('clock_not_synced', '仿真时钟未同步（/clock 未就绪）'),
    ('clock_not_progressing', '仿真时钟未推进（冻结时钟）'),
    ('single_world_mismatch', '世界名不是 agc_world（单世界约束不满足）'),
    ('odom_valid_stale', '地面里程计有效位复位后不新鲜'),
    ('odom_invalid', '地面里程计无效（odom_valid=false）'),
    ('ground_odom_stale', '地面里程计数据超龄'),
    ('cmd_vel_loopback_missing', '地面命令回路缺失（/agc/ground/cmd_vel 未回环）'),
)

_REASON = {code: text for code, text in REASON_ROWS}

# 配套事件串形如 `CAPTURE_NET ep=3 t=12.3 target=intruder_uav`：取首 token 再翻译。
_FIRST_TOKEN = re.compile(r'^\s*([A-Za-z0-9_\-]+)')


# --------------------------------------------------------------------------------------
# 3. 查询接口（panel / timeline / verdict 共用；**不要**在别处再写一份映射）
# --------------------------------------------------------------------------------------

def state_by_name(name):
    """内部名（`GROUND_APPROACH`）→ 映射条目；未知名**如实**返回 unknown 条目。"""
    key = (name or '').strip()
    if key in _BY_NAME:
        return _BY_NAME[key]
    return {'state': None, 'name': key or 'UNKNOWN', 'text': '未识别的状态名',
            'audience': '未收录（展示层如实标注，不猜语义）'}


def state_by_code(code):
    """`AgcTaskState.state` 数值 → 映射条目；非 0–8 **如实**返回 unknown 条目。"""
    try:
        return _BY_CODE.get(int(code)) or {'state': None, 'name': 'UNKNOWN',
                                           'text': '未识别的状态码', 'audience': '未收录'}
    except (TypeError, ValueError):
        return {'state': None, 'name': 'UNKNOWN', 'text': '未识别的状态码', 'audience': '未收录'}


def reason_text(code):
    """`reason_code` → 人话；空 → 无；未收录 → 原样回显并明确标注未收录。"""
    raw = (code or '').strip()
    if not raw:
        return '无'
    token = raw
    m = _FIRST_TOKEN.match(raw)
    if m:
        token = m.group(1)
    if token in _REASON:
        return _REASON[token]
    return '未收录的原因码（原样显示：%s）' % raw


def is_terminal(name):
    return (name or '') in TERMINAL_NAMES


def display_texts():
    """**全部**会出现在终端 / 时间线 / 判定说明里的状态文案（供 C8 静态检查）。"""
    out = []
    for _n, _name, text, audience in STATE_ROWS:
        out.append(text)
        out.append(audience)
    out.extend(_REASON.values())
    return out


def assert_display_safe(texts=None):
    """导入期与回归双用的 C8 守卫；违规抛 `AssertionError`（**不**静默降级）。"""
    texts = list(display_texts() if texts is None else texts)
    for text in texts:
        for bad in FORBIDDEN_ANYWHERE:
            assert bad not in text, 'C8 违规：展示文案出现 %r —— %s' % (bad, text)
    tracking = state_by_name(PHASE_A_SUCCESS)
    for bad in FORBIDDEN_IN_TRACKING:
        assert bad not in tracking['text'], (
            'C8 违规：TRACKING_SUCCESS 文案不得含 %r（实际：%r）' % (bad, tracking['text']))
    return True


def coverage_report():
    """映射完备性自检：9 个枚举 + 全部已收录 reason_code 都有人话。"""
    problems = []
    for code in range(9):
        entry = state_by_code(code)
        if entry['state'] is None:
            problems.append('state=%d 无映射' % code)
        elif not entry['text']:
            problems.append('state=%d 无文案' % code)
    for name in ('IDLE', 'AIR_SEARCH', 'TARGET_ACQUIRED', 'GROUND_APPROACH',
                 'TRACKING_SUCCESS', 'MISSION_FAILED', 'ABORTED',
                 'INTERCEPT_CONFIRMED', 'INFRA_FAILURE'):
        if state_by_name(name)['state'] is None:
            problems.append('state_name=%s 无映射' % name)
    for code, text in REASON_ROWS:
        if not text:
            problems.append('reason_code=%s 无文案' % code)
    return {'ok': not problems, 'problems': problems,
            'states': len(STATE_ROWS), 'reasons': len(REASON_ROWS)}


assert_display_safe()


if __name__ == '__main__':      # 纯静态自检（不启任何进程；T0）
    import json
    import sys
    print(json.dumps(coverage_report(), ensure_ascii=False, indent=2))
    sys.exit(0 if coverage_report()['ok'] else 1)
