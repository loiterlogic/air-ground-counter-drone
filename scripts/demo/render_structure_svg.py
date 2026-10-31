#!/usr/bin/env python3
"""`render_structure_svg.py` —— 从**声明式包表**渲染系统结构图 SVG（不手绘）。

## 为什么不用 mermaid-cli

本机没有 `mmdc`（`@mermaid-js/mermaid-cli` 未安装），也不该为一个图去装 Node 包。
但"手绘 PNG"更糟：手绘必然与真源漂移，而且漂移在 diff 里看不出来。折中方案是**脚本渲染**：

- 输入是下面 `PACKAGES` / `EDGES` 两张**声明式表**（内容抄自
  [包边界](../../docs/conventions/包边界.md#1-包清单)，逐行对应）；
- 输出是确定性 SVG（同样的输入永远得到逐字节相同的输出，可进 git、可 diff）；
- 改图 = 改表，**不是**改像素。

`docs/conventions/系统结构图.md` 里保留 Mermaid 版本（GitHub 原生渲染、可读性最好）；
本脚本产出的是**离线可用的 SVG**，供 README 内嵌与本地查看。两者内容必须一致，
不一致时**以包边界为准**并同时改两处。

## 一致性守卫

`scripts/tests/test_structure_diagram.py` 断言：
1. `PACKAGES` 的包名集合 == `colcon list` 的 8 包 + `px4_msgs`；
2. `EDGES` 的②库链接边**只有** `agc_air→agc_control` 与 `agc_ground→agc_control`
   （ADR-0018 的唯一例外，别的业务库互链一律非法）；
3. `agc_msgs` 是叶依赖（无出边）；
4. 渲染结果幂等（跑两次 sha256 相同）。

## 用法

```bash
python3 scripts/demo/render_structure_svg.py --out docs/plan/assets/system-structure.svg
```

退出码：`0` 已写出；`1` 表自检失败（如出现非法库链接边）；`2` 用法错误。
"""

import argparse
import os
import sys

# --------------------------------------------------------------------------------------
# 声明式真源（抄自 docs/conventions/包边界.md#1-包清单，逐行对应）
# --------------------------------------------------------------------------------------

# (包名, 职责域, 构建, 一句话职责, 行位置 lane, 列位置 col)
PACKAGES = [
    ('agc_msgs', '接口与消息', 'ament_cmake + rosidl',
     '9 条消息 / 服务定义（唯一公共接口、叶依赖）', 0, 1),
    ('agc_sim', '仿真世界与模型', 'ament_cmake',
     '世界 · 车/UAV/目标模型 · ros_gz 桥 · 传感器链路', 1, 0),
    ('agc_perception', '感知与融合', 'ament_cmake',
     'odom / gt / perception / fusion / map 适配', 1, 1),
    ('agc_task', '任务与评估', 'ament_cmake',
     'task_manager · run_logger · 场景 · 捕获裁决', 1, 2),
    ('agc_control', '通用控制层（共享库）', 'ament_cmake',
     'pluginlib 轨迹生成 + LQR 插件（air/ground 共用）', 2, 1),
    ('agc_air', '空中链路', 'ament_cmake',
     'PX4 uXRCE-DDS · 起飞/悬停/LQR 跟踪', 3, 0),
    ('agc_ground', '地面导航与安全层', 'ament_cmake',
     'RL 主控 · Nav2 collision_monitor · 唯一执行口上游', 3, 2),
    ('agc_rl', 'RL 平台', 'ament_python',
     'obs/action 接口 · 策略加载与推理', 3, 3),
]

# 第三方（内联，不算第 9 个业务包）
THIRD_PARTY = [
    ('px4_msgs', 'PX4 消息定义（内联 src/，pin a1045ec / release/1.15，不改造）'),
]

# 外部依赖（④ 外部设备 / 第三方边界）
EXTERNAL = [
    ('PX4 SITL', 'toolchain/ 外部依赖（pin v1.15.4）'),
    ('uXRCE-DDS Agent', 'MicroXRCEAgent（toolchain/bin）'),
    ('Gazebo Harmonic', 'gz-sim 8 + ros_gz 桥'),
    ('Nav2 组件', 'collision_monitor / lifecycle_manager'),
]

# 边：(源, 目标, 类别)。类别 1=消息(①) 2=库链接(②) 3=运行组合(③) 4=外部(④)
EDGES = [
    ('agc_sim', 'agc_msgs', 1),
    ('agc_perception', 'agc_msgs', 1),
    ('agc_air', 'agc_msgs', 1),
    ('agc_ground', 'agc_msgs', 1),
    ('agc_rl', 'agc_msgs', 1),
    ('agc_task', 'agc_msgs', 1),
    # ② 库链接：**仅** agc_control 这一处例外（ADR-0018）
    ('agc_air', 'agc_control', 2),
    ('agc_ground', 'agc_control', 2),
    # ③ 运行组合：agc_task 起进程，不链接实现库
    ('agc_task', 'agc_sim', 3),
    ('agc_task', 'agc_perception', 3),
    ('agc_task', 'agc_air', 3),
    ('agc_task', 'agc_ground', 3),
    ('agc_task', 'Nav2 组件', 3),
    # ④ 外部边界
    ('agc_sim', 'Gazebo Harmonic', 4),
    ('agc_perception', 'Gazebo Harmonic', 4),
    ('agc_air', 'uXRCE-DDS Agent', 4),
    ('uXRCE-DDS Agent', 'PX4 SITL', 4),
    ('agc_air', 'px4_msgs', 4),
    ('agc_ground', 'Nav2 组件', 4),
]

# ② 的唯一合法例外（ADR-0018）；出现别的库链接边即自检失败
LEGAL_LINK_TARGET = 'agc_control'

STYLE = {
    1: dict(stroke='#7a8fa6', dash='6,4', label='① 消息'),
    2: dict(stroke='#2f6f4e', dash='', label='② 链接'),
    3: dict(stroke='#8a6d3b', dash='10,3,2,3', label='③ 运行组合'),
    4: dict(stroke='#8a4b8a', dash='3,3', label='④ 外部'),
}

# 画布布局（单位 px）
BOX_W, BOX_H = 300, 80
GAP_X, GAP_Y = 56, 100
MARGIN_X, MARGIN_TOP = 60, 120

# 文本预算（px）：正文 12px 字号；CJK 字宽≈字号，ASCII≈0.55×字号。
# 换行按"宽度预算"算而不是按字符数猜——否则中文行会溢出框外（实测踩过）。
DESC_FONT = 12.0
DESC_INNER = BOX_W - 24


def validate_layout():
    """**几何自检**：每个框内的每一行都必须放得下，且整块文字不得超出框高。

    这是"SVG 不用肉眼也能验"的关键：框宽、字号、行距、行数都是本文件里的常量，
    所以"文字会不会溢出"是**可计算**的，不是审美问题。
    """
    errors = []
    max_lines = 3
    line_h = 14
    # 正文首行基线 y+60（业务包）/ y+46（外部节点），末行再加 line_h 仍须在框内
    for label, desc, first_baseline in (
            *((p[0], p[3], 60) for p in PACKAGES),
            *((e[0], e[1], 46) for e in EXTERNAL + THIRD_PARTY)):
        for line in _wrap(desc):
            if _text_px(line) > DESC_INNER:
                errors.append('%s 的一行文字超宽（%.0f px > %d px）：%r'
                              % (label, _text_px(line), DESC_INNER, line))
        n = len(_wrap(desc))
        if first_baseline + (n - 1) * line_h + 4 > BOX_H:
            errors.append('%s 的文字超出框高（%d 行，末基线 %d > 框高 %d）'
                          % (label, n, first_baseline + (n - 1) * line_h, BOX_H))
    if max_lines > 3:
        errors.append('行数上限 %d 与几何自检假设不一致' % max_lines)
    return errors


def validate():
    """表自检。返回错误列表（空 = 通过）。"""
    errors = []
    # 合法节点 = 8 业务包 + 内联第三方 + 外部依赖（④ 的端点允许落在外部节点上）
    names = ([p[0] for p in PACKAGES] + [t[0] for t in THIRD_PARTY]
             + [e[0] for e in EXTERNAL])
    for src, dst, kind in EDGES:
        if src not in names:
            errors.append('边的源不在包表里：%s' % src)
        if dst not in names:
            errors.append('边的目标不在包表里：%s' % dst)
        if kind == 4:
            continue
        if kind == 2 and dst != LEGAL_LINK_TARGET:
            errors.append('非法②库链接：%s → %s（只允许 → agc_control，ADR-0018）'
                          % (src, dst))
    for src, _dst, kind in EDGES:
        if kind == 1 and src == 'agc_msgs':
            errors.append('agc_msgs 是叶依赖，不得有①消息出边')
    return errors


def _box_positions():
    pos = {}
    for name, _domain, _build, _desc, lane, col in PACKAGES:
        x = MARGIN_X + col * (BOX_W + GAP_X)
        y = MARGIN_TOP + lane * (BOX_H + GAP_Y)
        pos[name] = (x, y)
    # 第三方与外部依赖放在最右一列、最上一行（示意"边界之外"）
    ext_x = MARGIN_X + 4 * (BOX_W + GAP_X)
    for i, (name, _desc) in enumerate(EXTERNAL):
        pos[name] = (ext_x, MARGIN_TOP + i * (BOX_H + GAP_Y))
    for i, (name, _desc) in enumerate(THIRD_PARTY):
        pos[name] = (ext_x, MARGIN_TOP + (len(EXTERNAL) + i) * (BOX_H + GAP_Y))
    return pos


def _esc(text):
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def _char_px(ch):
    """单字符宽度估算（px）：CJK 全角≈字号，ASCII≈0.55×字号。"""
    return DESC_FONT if ord(ch) > 0x2e80 else DESC_FONT * 0.55


def _text_px(text):
    return sum(_char_px(ch) for ch in text)


def _wrap(text, max_px=DESC_INNER, max_lines=3):
    """按**像素预算**换行，返回最多 `max_lines` 行（超出部分省略号收尾）。

    之前按"字符数"换行：中文行按 2 计，但 12px 中文实际就是 12px 宽，ASCII 只有 ~6.6px，
    混排时估算偏差能到 1.8 倍 → 行冲出框外。改成按像素预算后，`validate_layout()`
    可以**机械证明**每行都放得下。
    """
    lines, cur = [], ''
    for ch in text:
        if _text_px(cur + ch) > max_px and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines and _text_px(lines[-1] + '…') > max_px:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1] + '…'
    return lines


def render():
    """返回 SVG 文本（确定性：不含时间戳 / 随机 / 绝对路径）。"""
    pos = _box_positions()
    # 画布尺寸**由实际节点位置算出**，不靠猜：之前按"业务包行数"估高，
    # 而外部依赖列有 5 个框（4 外部 + 1 第三方），最后一个会被裁到画布外。
    max_x = max(x for x, _y in pos.values())
    max_y = max(y for _x, y in pos.values())
    width = max_x + BOX_W + MARGIN_X
    height = max_y + BOX_H + MARGIN_X

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d" font-family="DejaVu Sans, Droid Sans Fallback, '
           'Noto Sans CJK SC, sans-serif">'
           % (width, height, width, height),
           '  <rect width="100%" height="100%" fill="#fbfcfd"/>',
           '  <text x="%d" y="46" font-size="26" font-weight="bold" fill="#1f2933">'
           'AGC 系统结构（8 包 + 四类依赖）</text>' % MARGIN_X,
           '  <text x="%d" y="76" font-size="14" fill="#52606d">'
           '真源：docs/conventions/包边界.md（图是它的投影，冲突以真源为准）</text>'
           % MARGIN_X]

    # 图例
    lx = MARGIN_X + 520
    for kind in (1, 2, 3, 4):
        st = STYLE[kind]
        out.append('  <line x1="%d" y1="40" x2="%d" y2="40" stroke="%s" stroke-width="2" '
                   'stroke-dasharray="%s"/>' % (lx, lx + 34, st['stroke'], st['dash']))
        out.append('  <text x="%d" y="45" font-size="13" fill="#3e4c59">%s</text>'
                   % (lx + 40, _esc(st['label'])))
        lx += 118

    # 边（先画线，后画节点，避免线压在框上）
    for src, dst, kind in EDGES:
        if src not in pos or dst not in pos:
            continue
        sx, sy = pos[src]
        dx, dy = pos[dst]
        x1, y1 = sx + BOX_W // 2, sy + BOX_H // 2
        x2, y2 = dx + BOX_W // 2, dy + BOX_H // 2
        st = STYLE[kind]
        out.append('  <line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2" '
                   'stroke-dasharray="%s" opacity="0.85"/>'
                   % (x1, y1, x2, y2, st['stroke'], st['dash']))

    # 节点
    for name, domain, build, desc, _lane, _col in PACKAGES:
        x, y = pos[name]
        fill = '#eef4fb' if name != 'agc_control' else '#eaf5ee'
        stroke = '#9db4cd' if name != 'agc_control' else '#8cc0a0'
        out.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="8" fill="%s" '
                   'stroke="%s" stroke-width="1.5"/>' % (x, y, BOX_W, BOX_H, fill, stroke))
        out.append('  <text x="%d" y="%d" font-size="17" font-weight="bold" fill="#1f2933">'
                   '%s</text>' % (x + 12, y + 24, _esc(name)))
        out.append('  <text x="%d" y="%d" font-size="12" fill="#52606d">%s · %s</text>'
                   % (x + 12, y + 44, _esc(domain), _esc(build)))
        for i, line in enumerate(_wrap(desc)):
            out.append('  <text x="%d" y="%d" font-size="12" fill="#616e7c">%s</text>'
                       % (x + 12, y + 60 + i * 14, _esc(line)))

    for name, desc in EXTERNAL + THIRD_PARTY:
        x, y = pos[name]
        out.append('  <rect x="%d" y="%d" width="%d" height="%d" rx="8" fill="#f6f1f8" '
                   'stroke="#c3a9cf" stroke-width="1.5"/>'
                   % (x, y, BOX_W, BOX_H, ))
        out.append('  <text x="%d" y="%d" font-size="15" font-weight="bold" fill="#1f2933">'
                   '%s</text>' % (x + 12, y + 24, _esc(name)))
        for i, line in enumerate(_wrap(desc)):
            out.append('  <text x="%d" y="%d" font-size="12" fill="#616e7c">%s</text>'
                       % (x + 12, y + 44 + i * 14, _esc(line)))

    out.append('  <text x="%d" y="%d" font-size="13" fill="#52606d">'
               '读图要点：agc_task 对其它域包是③运行组合（起进程，exec_depend），'
               '不是②库链接；agc_control 是②的唯一例外（ADR-0018）；'
               'px4_msgs 是内联第三方，不是第 9 个业务包。</text>'
               % (MARGIN_X, height - 26))
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True, description='渲染系统结构图 SVG')
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)

    errors = validate() + validate_layout()
    if errors:
        for e in errors:
            print('[structure] 自检失败：%s' % e, file=sys.stderr)
        return 1

    svg = render()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(svg)
    print('[structure] 已写出 %s（%d 字节，%d 个包节点，%d 条边）'
          % (args.out, len(svg.encode('utf-8')), len(PACKAGES), len(EDGES)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
