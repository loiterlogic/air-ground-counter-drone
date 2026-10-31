#!/usr/bin/env python3
"""`render_structure_svg.py` —— 从**声明式包表**渲染两张图：概览图 + 明细图。

## 为什么不用 mermaid-cli / 不手绘

- 本机没有 `mmdc`，不该为一个图去装 Node 包；手绘 PNG 必然与真源漂移，且漂移在 diff 里看不出来。
- 折中：输入是下面的声明式表（抄自 [包边界](../../docs/conventions/包边界.md#1-包清单) 与各包
  `package.xml` / `CMakeLists.txt` / `launch`），输出是**确定性 SVG**（同输入 → 逐字节相同）。
  改图 = 改表，不是改像素。

## 两张图，各回答一个问题（round-2 按审查意见拆分）

| 资产 | 回答的问题 | 内容 |
|---|---|---|
| `system-structure.svg` | **谁在哪一层、靠什么相连** | 8 包 × 四类依赖的**概览**；每包 1 句职责 + ④ 短标签 |
| `system-structure-detail.svg` | **每一类到底有哪几条边** | 四类各自的规则 + **完整边清单**（逐条，含源包与依据） |

拆开的动因：把「概览」和「25 条边清单」塞进一张图，只能靠缩字号或把图拉长——两者都是
用版面换信息量，读者反而读不了（round-1 实测：正文 10 px 在 820 px 宽下仍偏小）。

## 字号纪律（不靠改测试阈值来「通过」）

概览图的**所有文字 ≥ 12 px**，包名 **15 px**；明细图正文 12 px。这些量与版面耦合：
字号一旦上调，行高、框高、行距全部随 `line_step()` 重算，放不下就在 `validate_layout()` 报错，
**不允许**通过调低阈值或加省略号来绕过。

## 版面纪律（可计算，不靠肉眼）

1. **画布宽度 = 显示宽度**：`width="820"` 与 README 的 `width="820"` 一致。浏览器仍可能因
   缩放 / DPI 让实际观感变化，本脚本**只能**保证 1 SVG px = 1 CSS px 这个前提成立，
   不能保证任何客户端都清晰（round-1 的「无缩放损失」措辞过强，已删）。
2. **正交布线**：所有线段轴对齐，拐点落在行间隙 / 列间隙 / 侧轨里。`validate_routes()` 检查
   「不穿框」「跨类别不交叉」，`validate_labels()` 检查「不压框、不互压、不被线穿过」。
3. **文字容量**：按 DejaVu Sans 的**实测逐字符字宽**（`_EM`）累加，与 Qt 实测偏差 < 6%
   （有专门用例）。所以「这行放不放得下」是可以算出来的，不需要等渲染出来才发现溢出。

## 一致性守卫（`scripts/tests/test_structure_diagram.py`）

1. 包集合 == 包边界#1-包清单 的 8 个业务包 ∪ 内联第三方 `px4_msgs`，可用时再与 `colcon list` 对齐；
2. ② 库链接边**只有** `agc_air→agc_control` 与 `agc_ground→agc_control`（ADR-0018 唯一例外）；
3. `agc_msgs` 是叶依赖（无出边、不被 ②/③ 指向）；
4. `agc_task` 对域包只能 ③（起进程），不得 ②（链接库）；
5. 图里每条边都必须在 `src/*/package.xml` 有声明（图不得凭空多画依赖）；
6. 概览与明细的边集合**必须相等**（拆成两张图后最容易发生的漂移）；
7. 渲染幂等，且磁盘 SVG == 当前表渲染结果。

## 用法

```bash
python3 scripts/demo/render_structure_svg.py \
    --out         docs/plan/assets/system-structure.svg \
    --png         docs/plan/assets/system-structure.png \
    --detail      docs/plan/assets/system-structure-detail.svg \
    --detail-png  docs/plan/assets/system-structure-detail.png --scale 2
python3 scripts/demo/render_structure_svg.py --check-only     # 只自检，不写盘
```

退出码：`0` 通过并写出；`1` 表 / 几何自检失败；`2` 用法错误；`3` 请求 PNG 但环境缺 PyQt5。
"""

import argparse
import os
import sys

# ======================================================================================
# 1. 文本度量：DejaVu Sans 的实测字宽表（Qt QFontMetricsF @ 100 px，见 tests 对照）
# ======================================================================================
# 为什么是表而不是「CJK=字号、ASCII=0.55×字号」：旧脚本用后者，混排偏差可达 1.8 倍，
# 「按像素预算换行」也照样溢出。这里逐字符取实测 advance（单位 em）。
_EM = {
    ' ': 0.318, '!': 0.401, '"': 0.460, '#': 0.838, '$': 0.636, '%': 0.950,
    '&': 0.780, "'": 0.275, '(': 0.390, ')': 0.390, '*': 0.500, '+': 0.838,
    ',': 0.318, '-': 0.361, '.': 0.318, '/': 0.337, '0': 0.636, '1': 0.636,
    '2': 0.636, '3': 0.636, '4': 0.636, '5': 0.636, '6': 0.636, '7': 0.636,
    '8': 0.636, '9': 0.636, ':': 0.337, ';': 0.337, '<': 0.838, '=': 0.838,
    '>': 0.838, '?': 0.531, '@': 1.000, 'A': 0.684, 'B': 0.686, 'C': 0.698,
    'D': 0.770, 'E': 0.632, 'F': 0.575, 'G': 0.775, 'H': 0.752, 'I': 0.295,
    'J': 0.295, 'K': 0.656, 'L': 0.557, 'M': 0.863, 'N': 0.748, 'O': 0.787,
    'P': 0.603, 'Q': 0.787, 'R': 0.695, 'S': 0.635, 'T': 0.611, 'U': 0.732,
    'V': 0.684, 'W': 0.989, 'X': 0.685, 'Y': 0.611, 'Z': 0.685, '[': 0.390,
    '\\': 0.337, ']': 0.390, '^': 0.838, '_': 0.500, '`': 0.500, 'a': 0.613,
    'b': 0.635, 'c': 0.550, 'd': 0.635, 'e': 0.615, 'f': 0.352, 'g': 0.635,
    'h': 0.634, 'i': 0.278, 'j': 0.278, 'k': 0.579, 'l': 0.278, 'm': 0.974,
    'n': 0.634, 'o': 0.612, 'p': 0.635, 'q': 0.635, 'r': 0.411, 's': 0.521,
    't': 0.392, 'u': 0.634, 'v': 0.592, 'w': 0.818, 'x': 0.592, 'y': 0.592,
    'z': 0.525, '{': 0.636, '|': 0.337, '}': 0.636, '~': 0.838,
    # 中文标点 / 圈码 / 箭头：DejaVu 有字形，按实测；其余 CJK 一律 1.0 em
    '·': 0.318, '、': 1.0, '，': 1.0, '。': 1.0, '：': 1.0, '；': 1.0,
    '（': 1.0, '）': 1.0, '【': 1.0, '】': 1.0, '“': 0.518, '”': 0.518,
    '‘': 0.318, '’': 0.318, '—': 1.0, '…': 1.0,
    '①': 0.896, '②': 0.896, '③': 0.896, '④': 0.896, '⑤': 0.896,
    '→': 0.838, '←': 0.838, '↑': 0.838, '↓': 0.838, '⇢': 0.838,
    '▲': 0.769, '▶': 0.769, '●': 0.873, '○': 0.873, '◆': 0.769,
}
BOLD_FACTOR = 1.10        # 实测 bold / regular = 1.10–1.12
CHAR_FALLBACK = 1.0       # 未知 CJK 按全角（只会高估，不会低估）


def char_em(ch):
    """单字符宽度（em）。"""
    if ch in _EM:
        return _EM[ch]
    return CHAR_FALLBACK if ord(ch) > 0x2e80 else 0.6


def text_px(text, size, bold=False):
    """文本宽度（px），用于换行与几何自检。"""
    return sum(char_em(ch) for ch in text) * size * (BOLD_FACTOR if bold else 1.0)


SEP = ' · '


def _atoms(text):
    """切成语义原子：` · ` 与括号都是不可再分的边界。

    `Nav2 collision_monitor` / `（ADR-0018 唯一例外）` 一旦被拆到两行，读者会把一对概念读成两个，
    或让一对括号跨行——所以原子内部不允许自动换行。
    """
    parts, buf, depth, i = [], '', 0, 0
    while i < len(text):
        ch = text[i]
        if ch in '（(':
            depth += 1
        elif ch in '）)':
            depth = max(0, depth - 1)
        if depth == 0 and text.startswith(SEP, i):
            parts.append(buf)
            buf = ''
            i += len(SEP)
            continue
        buf += ch
        i += 1
    parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def wrap_text(text, inner_px, size, bold=False, max_lines=8):
    """按像素预算换行：先装语义原子，原子超宽才按空格 / 字符硬断。"""
    lines, line = [], ''
    for atom in _atoms(text):
        cand = (line + SEP + atom) if line else atom
        if text_px(cand, size, bold) <= inner_px:
            line = cand
            continue
        if line:
            lines.append(line)
            line = ''
        if text_px(atom, size, bold) <= inner_px:
            line = atom
            continue
        for word in atom.split(' '):
            cand2 = (line + ' ' + word) if line else word
            if text_px(cand2, size, bold) <= inner_px:
                line = cand2
                continue
            if line:
                lines.append(line)
                line = ''
            for ch in word:
                if text_px(line + ch, size, bold) > inner_px and line:
                    lines.append(line)
                    line = ch
                else:
                    line += ch
    if line.strip():
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines and text_px(lines[-1] + '…', size, bold) > inner_px:
            lines[-1] = lines[-1][:-1]
        lines[-1] += '…'
    return [ln for ln in (l.strip() for l in lines) if ln]


# ======================================================================================
# 2. 声明式真源（抄自 包边界#1-包清单 与各包 package.xml / CMakeLists / launch）
# ======================================================================================
# 概览图每包只保留：包名 + 角色行 + 1 句职责 + ④ 短标签。完整职责与边清单在明细图与
# docs/conventions/系统结构图.md，概览不重复。
PACKAGES = [
    dict(id='agc_task', name='agc_task', layer=0,
         role='任务与评估 · ament_cmake',
         desc='状态机 · 指标 · 场景复位 · 捕获裁决',
         ext='④ PX4 / Agent / px4_msgs / Nav2'),
    dict(id='agc_sim', name='agc_sim', layer=1,
         role='仿真世界与模型 · ament_cmake',
         desc='世界几何 · 车/机/目标模型 · ros_gz 桥',
         ext='④ Gazebo（gz-sim 8）'),
    dict(id='agc_perception', name='agc_perception', layer=1,
         role='感知与融合 · ament_cmake',
         desc='适配 · 融合 · 真值旁路直读 gz',
         ext='④ Gazebo（gz-transport）'),
    dict(id='agc_air', name='agc_air', layer=2,
         role='空中链路 · ament_cmake',
         desc='PX4 uXRCE 链路 · LQR 跟踪',
         ext='④ PX4 / Agent / Nav2 / px4_msgs'),
    dict(id='agc_ground', name='agc_ground', layer=2,
         role='地面导航与安全层 · ament_cmake',
         desc='RL 主控 · Nav2 安全层 · 执行口',
         ext='④ Nav2（链接 + 起进程）'),
    dict(id='agc_rl', name='agc_rl', layer=2,
         role='RL 平台 · ament_python',
         desc='obs/action · 策略推理',
         ext=''),
    dict(id='agc_control', name='agc_control', layer=3,
         role='通用控制层（共享库）· ament_cmake',
         desc='pluginlib 轨迹 + LQR 插件',
         ext=''),
    dict(id='agc_msgs', name='agc_msgs', layer=4,
         role='接口与消息 · ament_cmake + rosidl',
         desc='9 条 msg · ① 接口层 · 叶依赖（无出边）',
         ext=''),
]
NODE_BY_ID = {p['id']: p for p in PACKAGES}

# 外部边界项（④）：(id, 单行显示名)
EXTERNAL = [
    ('Gazebo Harmonic', 'Gazebo Harmonic（gz-sim 8）'),
    ('PX4 SITL', 'PX4 SITL v1.15.4'),
    ('uXRCE-DDS Agent', 'uXRCE-DDS Agent（MicroXRCEAgent）'),
    ('px4_msgs', 'px4_msgs（内联第三方，不改造）'),
    ('Nav2 组件', 'Nav2 组件'),
]

# 包间边：类别 1=①消息 2=②库链接 3=③运行组合。④ 走 EXT_RELATIONS（出界项）。
PACKAGE_EDGES = [
    # ① 消息 / 接口。agc_sim **不在**其中：它只经 ros_gz 桥发标准消息（package.xml 无 agc_msgs）。
    ('agc_perception', 'agc_msgs', 1),
    ('agc_air', 'agc_msgs', 1),
    ('agc_ground', 'agc_msgs', 1),
    ('agc_rl', 'agc_msgs', 1),
    ('agc_task', 'agc_msgs', 1),
    # ② 库链接：仅 agc_control 这一处例外（ADR-0018）
    ('agc_air', 'agc_control', 2),
    ('agc_ground', 'agc_control', 2),
    # ③ 运行组合（launch 起进程，exec_depend，不链接实现库）
    ('agc_task', 'agc_sim', 3),
    ('agc_task', 'agc_perception', 3),
    ('agc_task', 'agc_air', 3),
    ('agc_task', 'agc_ground', 3),
    ('agc_air', 'agc_sim', 3),        # air_bringup 起 world_bringup（唯一世界 / 唯一时钟）
    ('agc_ground', 'agc_rl', 3),      # ground_bringup 在 command_source=rl 时 include
]

# ④ 外部边界关系：(外部项, 源包, 方式, 说明)。方式 ∈ {'link' 依赖库, 'start' 起进程}。
EXT_RELATIONS = [
    ('Gazebo Harmonic', 'agc_sim', 'start', '起 gz server（ros_gz_sim）；链接 gz_* vendor 库'),
    ('Gazebo Harmonic', 'agc_perception', 'link', 'gz_transport_vendor / gz_msgs_vendor 直读真值'),
    ('PX4 SITL', 'agc_air', 'link', 'uXRCE-DDS 链路（toolchain/ 外部依赖，pin v1.15.4）'),
    ('PX4 SITL', 'agc_task', 'link', 'intruder_driver / jammer 发 px4_msgs/VehicleCommand'),
    ('uXRCE-DDS Agent', 'agc_air', 'start', '起 MicroXRCEAgent（udp4 / agent_port）'),
    ('uXRCE-DDS Agent', 'agc_task', 'start', '起 2 个 Agent（own + intruder 端口，w6.launch）'),
    ('px4_msgs', 'agc_air', 'link', '编译期 depend，pin a1045ec / release/1.15，不改造'),
    ('px4_msgs', 'agc_task', 'link', 'exec_depend：jammer / intruder_driver 导入'),
    ('Nav2 组件', 'agc_ground', 'link', '链接 nav2_core / nav2_costmap_2d / nav2_util'),
    ('Nav2 组件', 'agc_ground', 'start', '起 collision_monitor / lifecycle_manager / navfn'),
    ('Nav2 组件', 'agc_air', 'start', '起 lifecycle_manager（空中节点 configure→activate）'),
    ('Nav2 组件', 'agc_task', 'start', 'exec_depend：lifecycle_manager 编排'),
]

LEGAL_LINK_TARGET = 'agc_control'   # ② 的唯一合法例外（ADR-0018）

# ======================================================================================
# 3. 版式常量
# ======================================================================================
CANVAS_W = 820
MARGIN_L = 24
GUTTER_R = 82                             # 左侧层名右对齐位置（在系统边界之外）
FRAME_X0, FRAME_X1 = 94, 794              # 系统边界（src/ 下 8 个 ament 包）
NODE_X0, NODE_X1 = 118, 770               # 节点横向范围
RAIL_L, RAIL_R = 106, 782                 # ① 总线侧轨（帧内、节点带外）
FRAME_Y0 = 124

# 字号：概览图正文 ≥ 12 px，包名 15 px（round-2 审查要求；与版面耦合，见 docstring）
FS_TITLE, FS_SUB = 20.0, 12.5
FS_NODE, FS_ROLE, FS_DESC, FS_EXT = 15.0, 12.0, 12.0, 12.0
FS_LAYER, FS_PANEL, FS_FOOT = 12.0, 13.5, 11.0
FS_CARD_T, FS_CARD = 14.0, 12.0
PAD_X, PAD_TOP, BOTTOM_PAD = 12, 21, 14
MIN_FONT = 11.0                           # 只有页脚脚注允许到 11 px

ROWS = [
    (0, '编排 · ③', [('agc_task', 1.0)], 0, 34),
    # sim 在左、perception 在右：sim 没有①出边，右半边①竖线才能直达总线
    (1, '仿真 / 感知', [('agc_sim', 0.48), ('agc_perception', 0.48)], 40, 34),
    (2, '执行 / 策略', [('agc_air', 0.35), ('agc_ground', 0.34), ('agc_rl', 0.24)], 28, 38),
]
ROW_SHARED_LIB = 3
ROW_IFACE = 4

STYLE = {
    1: dict(stroke='#5b6b7c', dash='5,4', width=1.3, label='① 消息 / 接口'),
    2: dict(stroke='#2f6f4e', dash='', width=2.0, label='② 库链接'),
    3: dict(stroke='#9a6b16', dash='7,3', width=1.6, label='③ 运行组合'),
    4: dict(stroke='#8a4b8a', dash='2,3', width=1.3, label='④ 外部边界'),
}
COLOR = dict(
    ink='#1f2933', body='#3d4b59', muted='#64758a', faint='#94a3b1',
    node_fill='#f3f7fb', node_stroke='#9db4cd',
    lib_fill='#eef7f1', lib_stroke='#7fb295',
    iface_fill='#f4f4f8', iface_stroke='#9d9db5',
    ext='#7d4f86', bg='#ffffff', card='#fcfcfd', frame='#b9c4d0',
)


def line_step(size):
    """行距：随字号缩放（字号上调时版面自动变高，不靠手工改像素）。"""
    return round(size * 1.42, 1)


# ======================================================================================
# 4. 概览图：布局
# ======================================================================================


def node_lines(node, width):
    """概览节点内的文本行：(text, size, bold, fill)。"""
    inner = width - 2 * PAD_X
    out = [(node['name'], FS_NODE, True, COLOR['ink'])]
    for ln in wrap_text(node['role'], inner, FS_ROLE):
        out.append((ln, FS_ROLE, False, COLOR['muted']))
    for ln in wrap_text(node['desc'], inner, FS_DESC):
        out.append((ln, FS_DESC, False, COLOR['body']))
    if node['ext']:
        for ln in wrap_text(node['ext'], inner, FS_EXT):
            out.append((ln, FS_EXT, False, COLOR['ext']))
    return out


def node_height(node, width):
    h = PAD_TOP
    for i, (_t, size, _b, _c) in enumerate(node_lines(node, width)):
        if i:
            h += line_step(size)
    return round(h + BOTTOM_PAD, 1)


def layout():
    """概览图布局：返回 nodes{id: rect}、bands{layer: (y0, y1)}、frame(x0,y0,x1,y1)。"""
    row_w = NODE_X1 - NODE_X0
    nodes, bands = {}, {}
    y = FRAME_Y0 + 30
    for layer, _label, cols, gap, after in ROWS:
        widths = [int(round(row_w * frac)) for _id, frac in cols]
        widths[-1] = row_w - sum(widths[:-1]) - gap * (len(cols) - 1)
        h = max(node_height(NODE_BY_ID[nid], w) for (nid, _f), w in zip(cols, widths))
        x = NODE_X0
        for (nid, _f), w in zip(cols, widths):
            nodes[nid] = (x, y, w, h)
            x += w + gap
        bands[layer] = (y, y + h)
        y += h + after

    air, gnd = nodes['agc_air'], nodes['agc_ground']
    ctl_x0 = air[0] + air[2] // 2 - 36
    ctl_x1 = gnd[0] + gnd[2] // 2 + 36
    h = node_height(NODE_BY_ID['agc_control'], ctl_x1 - ctl_x0)
    nodes['agc_control'] = (ctl_x0, y, ctl_x1 - ctl_x0, h)
    bands[ROW_SHARED_LIB] = (y, y + h)
    y += h + 38

    h = node_height(NODE_BY_ID['agc_msgs'], NODE_X1 - NODE_X0)
    nodes['agc_msgs'] = (NODE_X0, y, NODE_X1 - NODE_X0, h)
    bands[ROW_IFACE] = (y, y + h)

    return nodes, bands, (FRAME_X0, FRAME_Y0, FRAME_X1, y + h + 22)


def routes(nodes, bands):
    """返回 [dict(kind, pts, head)]；坐标全部由矩形派生，移动框即移动线。

    `head=True` 表示最后一点落在**目标框的边上**（画箭头）；落在总线 / 通道上的 T 形汇合点
    `head=False`——在汇合处画箭头会假装「那里是终点」。

    ① 的竖线必须绕开 `agc_control` 的横向跨度：左轨收 task，air 在 control 左边界外直落，
    右轨收 perception；ground / rl 在 control 右边界外直落。
    """
    out = []
    task, sim, per = nodes['agc_task'], nodes['agc_sim'], nodes['agc_perception']
    air, gnd, rl = nodes['agc_air'], nodes['agc_ground'], nodes['agc_rl']
    ctl, msg = nodes['agc_control'], nodes['agc_msgs']

    def cx(r):
        return int(r[0] + r[2] // 2)

    def add(kind, pts, head):
        out.append(dict(kind=kind, pts=[(int(x), int(y)) for x, y in pts], head=head))

    gap12 = int((bands[1][0] + bands[0][1]) // 2)
    gap23 = int((bands[2][0] + bands[1][1]) // 2)
    trunk_x = int((sim[0] + sim[2] + per[0]) // 2)

    # ③ 分发：一条主干贯穿两条横向通道（中途不断开）→ 通道 → 各自落框
    add(3, [(cx(task), task[1] + task[3]), (trunk_x, task[1] + task[3]),
            (trunk_x, gap23)], False)
    add(3, [(cx(per), gap12), (cx(sim), gap12), (cx(sim), sim[1])], True)
    add(3, [(cx(per), gap12), (cx(per), per[1])], True)
    add(3, [(cx(gnd), gap23), (cx(air), gap23), (cx(air), air[1])], True)
    add(3, [(cx(gnd), gap23), (cx(gnd), gnd[1])], True)

    # ③ air → sim：同列竖直（air 顶边 → sim 底边）
    add(3, [(air[0] + 22, air[1]), (air[0] + 22, sim[1] + sim[3])], True)
    # ③ ground → rl：同层短横连
    add(3, [(gnd[0] + gnd[2], gnd[1] + gnd[3] // 2), (rl[0], rl[1] + rl[3] // 2)], True)

    # ② air / ground → control：竖线只走行间隙，落 control 顶边
    add(2, [(cx(air), air[1] + air[3]), (cx(air), ctl[1])], True)
    add(2, [(cx(gnd), gnd[1] + gnd[3]), (cx(gnd), ctl[1])], True)

    # ① 总线：单箭头落 agc_msgs
    bus_y = int((ctl[1] + ctl[3] + msg[1]) // 2)
    add(1, [(RAIL_L, bus_y), (RAIL_R, bus_y)], False)
    add(1, [(cx(msg), bus_y), (cx(msg), msg[1])], True)
    add(1, [(task[0], task[1] + task[3] - 20), (RAIL_L, task[1] + task[3] - 20),
            (RAIL_L, bus_y)], False)
    add(1, [(air[0] + 38, air[1] + air[3]), (air[0] + 38, bus_y)], False)
    add(1, [(per[0] + per[2], per[1] + 40), (RAIL_R, per[1] + 40), (RAIL_R, bus_y)], False)
    add(1, [(gnd[0] + gnd[2] - 24, gnd[1] + gnd[3]),
            (gnd[0] + gnd[2] - 24, bus_y)], False)
    add(1, [(rl[0] + 30, rl[1] + rl[3]), (rl[0] + 30, bus_y)], False)
    return out


# ======================================================================================
# 5. 概览图：标签与自检
# ======================================================================================


def text_box(x, y, text, size, anchor=None, bold=False):
    """文本包围盒（近似：上升 0.80×字号，下降 0.19×字号）。"""
    w = text_px(text, size, bold)
    x0 = x - w if anchor == 'end' else (x - w / 2 if anchor == 'middle' else x)
    return (x0, y - size * 0.80, w, size * 0.99)


def label_specs(nodes, bands):
    """所有非节点文字的候选位置：(name, x, y, text, size, anchor)。"""
    air = nodes['agc_air']
    sim = nodes['agc_sim']
    ctl, msg = nodes['agc_control'], nodes['agc_msgs']
    gap12 = int((bands[1][0] + bands[0][1]) // 2)
    bus_y = int((ctl[1] + ctl[3] + msg[1]) // 2)
    specs = [
        ('bus', NODE_X0 + 4, bus_y - 7,
         '① 消息总线：5 条支线汇入，单箭头落 agc_msgs', FS_LAYER, None),
        ('dispatch', NODE_X0 + 4, gap12 - 7,
         '③ 起进程（exec_depend，不链接库）', FS_LAYER, None),
        ('link', air[0] + air[2] // 2 + 10,
         int((air[1] + air[3] + ctl[1]) // 2 + 5), '② 链接 agc_control', FS_LAYER, None),
        ('air_sim', air[0] + 28,
         int((air[1] + sim[1] + sim[3]) // 2 + 5), '③ air→sim', FS_LAYER, None),
    ]
    for layer, label in {0: '编排 ③', 1: '仿真/感知', 2: '执行/策略',
                         3: '共享库 ②', 4: '接口 ①'}.items():
        y0, y1 = bands[layer]
        specs.append(('layer%d' % layer, GUTTER_R, int((y0 + y1) // 2 + 5), label,
                      FS_LAYER, 'end'))
    return specs


def _seg_hits_rect(p, q, rect, pad=0):
    """轴对齐线段是否穿过矩形内部（贴边不算）。"""
    x0, y0, w, h = rect
    rx0, ry0, rx1, ry1 = x0 - pad, y0 - pad, x0 + w + pad, y0 + h + pad
    (x1, y1), (x2, y2) = p, q
    if y1 == y2:
        if not (ry0 < y1 < ry1):
            return False
        lo, hi = sorted((x1, x2))
        return lo < rx1 and hi > rx0
    if x1 == x2:
        if not (rx0 < x1 < rx1):
            return False
        lo, hi = sorted((y1, y2))
        return lo < ry1 and hi > ry0
    raise AssertionError('非轴对齐线段：%r → %r' % (p, q))


def _cross(p1, p2, p3, p4):
    """两轴对齐线段的交点（端点不算）。"""
    if p1[1] == p2[1] and p3[0] == p4[0]:
        y, x = p1[1], p3[0]
        if min(p1[0], p2[0]) < x < max(p1[0], p2[0]) and \
                min(p3[1], p4[1]) < y < max(p3[1], p4[1]):
            return (x, y)
    if p1[0] == p2[0] and p3[1] == p4[1]:
        y, x = p3[1], p1[0]
        if min(p1[1], p2[1]) < y < max(p1[1], p2[1]) and \
                min(p3[0], p4[0]) < x < max(p3[0], p4[0]):
            return (x, y)
    return None


def _on_border(pt, rect):
    x, y, w, h = rect
    px, py = pt
    return ((px in (x, x + w) and y <= py <= y + h)
            or (py in (y, y + h) and x <= px <= x + w))


def _label_free(bx, nodes, segs, boxes):
    if bx[0] < MARGIN_L - 1 or bx[0] + bx[2] > CANVAS_W - MARGIN_L + 1 or bx[1] < 0:
        return False
    for rect in nodes.values():
        if (bx[0] < rect[0] + rect[2] and rect[0] < bx[0] + bx[2]
                and bx[1] < rect[1] + rect[3] and rect[1] < bx[1] + bx[3]):
            return False
    for _n, b, _t in boxes:
        if (bx[0] < b[0] + b[2] and b[0] < bx[0] + bx[2]
                and bx[1] < b[1] + b[3] and b[1] < bx[1] + bx[3]):
            return False
    for seg in segs:
        for p, q in zip(seg['pts'], seg['pts'][1:]):
            if _seg_hits_rect(p, q, bx, pad=1):
                return False
    return True


def place_labels(nodes, segs, specs):
    """确定性避让：首选位置冲突时按固定顺序挪位；挪不动就保留并让 validate 报错。"""
    boxes, placed = [], []
    for name, x, y, text, size, anchor in specs:
        chosen = None
        offsets = [(0, 0)] + [(dx, dy) for d in (7, 14, 21, 30, 40)
                              for dx, dy in ((0, -d), (0, d), (-d, 0), (d, 0))]
        for dx, dy in offsets:
            bx = text_box(x + dx, y + dy, text, size, anchor)
            if _label_free(bx, nodes, segs, boxes):
                chosen = (x + dx, y + dy, bx)
                break
        if chosen is None:
            chosen = (x, y, text_box(x, y, text, size, anchor))
        placed.append((name, chosen[0], chosen[1], text, size, anchor))
        boxes.append((name, chosen[2], text))
    return placed, boxes


def validate():
    """表自检。"""
    errors = []
    ids = [p['id'] for p in PACKAGES]
    if len(set(ids)) != len(ids):
        errors.append('包表里有重复 id')
    names = set(ids) | {e[0] for e in EXTERNAL}
    for src, dst, kind in PACKAGE_EDGES:
        if src not in names:
            errors.append('边的源不在包表里：%s' % src)
        if dst not in names:
            errors.append('边的目标不在包表里：%s' % dst)
        if kind == 2 and dst != LEGAL_LINK_TARGET:
            errors.append('非法②库链接：%s → %s（只允许 → agc_control，ADR-0018）' % (src, dst))
        if kind == 1 and src == 'agc_msgs':
            errors.append('agc_msgs 是叶依赖，不得有①消息出边')
        if kind == 3 and src == 'agc_msgs':
            errors.append('agc_msgs 是叶依赖，不得起别人进程')
    seen = set()
    for src, dst, kind in PACKAGE_EDGES:
        if (src, dst, kind) in seen:
            errors.append('重复边：%s→%s（类 %d）' % (src, dst, kind))
        seen.add((src, dst, kind))
    ext_ids = {e[0] for e in EXTERNAL}
    for ext, src, way, note in EXT_RELATIONS:
        if ext not in ext_ids:
            errors.append('④关系指向未登记的外部项：%s' % ext)
        if src not in set(ids):
            errors.append('④关系的源不是已登记的包：%s' % src)
        if way not in ('link', 'start'):
            errors.append('④关系方式只能是 link / start，实际 %r' % (way,))
        if not note:
            errors.append('④关系 %s←%s 缺少说明' % (ext, src))
    for e in EXTERNAL:
        if not any(r[0] == e[0] for r in EXT_RELATIONS):
            errors.append('外部项 %s 没有任何④关系（要么删，要么补）' % e[0])
    return errors


def validate_layout(nodes, frame):
    """几何自检：文字不溢出框、不出现省略号、框不出画布、框不重叠、字号不低于下限。"""
    errors = []
    for nid, (x, y, w, h) in nodes.items():
        node = NODE_BY_ID[nid]
        inner = w - 2 * PAD_X
        yy = y + PAD_TOP
        for i, (txt, size, bold, _c) in enumerate(node_lines(node, w)):
            if i:
                yy += line_step(size)
            need = text_px(txt, size, bold)
            if need > inner + 0.5:
                errors.append('%s 第 %d 行超宽：%.1f px > %.1f px（%r）'
                              % (nid, i + 1, need, inner, txt))
            if txt.endswith('…'):
                errors.append('%s 第 %d 行被省略号截断（不允许省略）' % (nid, i + 1))
            if yy + 6 > y + h:
                errors.append('%s 第 %d 行跌出框底（基线 %.0f > 框底 %.0f）'
                              % (nid, i + 1, yy, y + h))
            if size < MIN_FONT:
                errors.append('%s 的字号 %.1f px 低于 %.1f px' % (nid, size, MIN_FONT))
        if x < MARGIN_L or y < 0 or x + w > CANVAS_W - MARGIN_L:
            errors.append('%s 超出画布横向范围（x=%.0f..%.0f）' % (nid, x, x + w))
    items = list(nodes.items())
    for i, (a, ra) in enumerate(items):
        for b, rb in items[i + 1:]:
            if (ra[0] < rb[0] + rb[2] and rb[0] < ra[0] + ra[2]
                    and ra[1] < rb[1] + rb[3] and rb[1] < ra[1] + ra[3]):
                errors.append('节点重叠：%s 与 %s' % (a, b))
    if frame[3] < frame[1] + 100:
        errors.append('系统边界异常（过矮）：%r' % (frame,))
    return errors


def validate_routes(nodes, segs):
    """布线自检：轴对齐、不穿框、跨类别不交叉。"""
    errors = []
    for seg in segs:
        kind, pts = seg['kind'], seg['pts']
        for p, q in zip(pts, pts[1:]):
            if p[0] != q[0] and p[1] != q[1]:
                errors.append('非轴对齐线段：%r → %r' % (p, q))
                continue
            if p == q:
                errors.append('零长线段：%r' % (p,))
                continue
            for nid, rect in nodes.items():
                if not _seg_hits_rect(p, q, rect):
                    continue
                if _on_border(p, rect) or _on_border(q, rect):
                    continue
                errors.append('类 %d 线段穿过 %s 框体：%r → %r' % (kind, nid, p, q))
    flat = [(seg['kind'], a, b) for seg in segs for a, b in zip(seg['pts'], seg['pts'][1:])]
    for i, (k1, a1, b1) in enumerate(flat):
        for k2, a2, b2 in flat[i + 1:]:
            hit = _cross(a1, b1, a2, b2)
            if hit is not None and k1 != k2:
                errors.append('类 %d / 类 %d 线段在 %r 交叉（不同类别必须走不同通道）'
                              % (k1, k2, hit))
    return errors


def validate_labels(nodes, segs, boxes):
    """标签自检：不压框、不互压、不被线穿过。"""
    errors = []
    for _name, bx, text in boxes:
        if bx[0] < MARGIN_L - 1 or bx[0] + bx[2] > CANVAS_W - MARGIN_L + 1:
            errors.append('标签 %r 超出画布横向范围' % text)
        if bx[1] < 0:
            errors.append('标签 %r 超出画布顶部' % text)
        for nid, rect in nodes.items():
            if (bx[0] < rect[0] + rect[2] and rect[0] < bx[0] + bx[2]
                    and bx[1] < rect[1] + rect[3] and rect[1] < bx[1] + bx[3]):
                errors.append('标签 %r 压在节点 %s 上' % (text, nid))
    for i, (n1, b1, t1) in enumerate(boxes):
        for n2, b2, t2 in boxes[i + 1:]:
            if (b1[0] < b2[0] + b2[2] and b2[0] < b1[0] + b1[2]
                    and b1[1] < b2[1] + b2[3] and b2[1] < b1[1] + b1[3]):
                errors.append('标签互相重叠：%r / %r' % (t1, t2))
    for seg in segs:
        kind, pts = seg['kind'], seg['pts']
        for p, q in zip(pts, pts[1:]):
            for _name, bx, text in boxes:
                if _seg_hits_rect(p, q, bx):
                    errors.append('类 %d 线段压住标签 %r（%r → %r）' % (kind, text, p, q))
    return errors


# ======================================================================================
# 6. SVG 基础部件
# ======================================================================================


def _esc(text):
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def _t(x, y, text, size, fill, bold=False, anchor=None):
    a = 'x="%d" y="%d" font-size="%g" fill="%s"' % (x, y, size, fill)
    if bold:
        a += ' font-weight="bold"'
    if anchor:
        a += ' text-anchor="%s"' % anchor
    return '  <text %s>%s</text>' % (a, _esc(text))


def _r(x, y, w, h, fill, stroke, rx=7, sw=1.2, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ''
    return ('  <rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="%s" '
            'stroke="%s" stroke-width="%g"%s/>' % (x, y, w, h, rx, fill, stroke, sw, d))


def _poly(pts, st):
    d = 'M ' + ' L '.join('%d %d' % p for p in pts)
    return ('  <path d="%s" fill="none" stroke="%s" stroke-width="%g" '
            'stroke-dasharray="%s" stroke-linejoin="round"/>'
            % (d, st['stroke'], st['width'], st['dash']))


def _arrow(p, q, st):
    """端点 q 处的实心箭头，方向 p→q。"""
    (x1, y1), (x2, y2) = p, q
    s = 6.5
    if x1 == x2:
        dy = -1 if y2 < y1 else 1
        pts = [(x2, y2), (x2 - s * 0.60, y2 - s * dy), (x2 + s * 0.60, y2 - s * dy)]
    else:
        dx = -1 if x2 < x1 else 1
        pts = [(x2, y2), (x2 - s * dx, y2 - s * 0.60), (x2 - s * dx, y2 + s * 0.60)]
    return ('  <polygon points="%s" fill="%s"/>'
            % (' '.join('%.1f,%.1f' % p for p in pts), st['stroke']))


def _svg_open(w, h, bg=COLOR['bg']):
    return ['<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d" font-family="DejaVu Sans, Droid Sans Fallback, sans-serif">'
            % (w, h, w, h),
            '  <rect width="100%%" height="100%%" fill="%s"/>' % bg]


# ======================================================================================
# 7. 概览图渲染
# ======================================================================================


def _legend(out, lx, ly, kinds):
    """图例只画**实际存在的线型**（图例里出现一条不存在的线是误导）。"""
    for kind in kinds:
        st = STYLE[kind]
        out.append('  <line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="%g" '
                   'stroke-dasharray="%s"/>' % (lx, ly, lx + 26, ly, st['stroke'],
                                                st['width'], st['dash']))
        out.append(_t(lx + 32, ly + 4, st['label'], FS_SUB, COLOR['body']))
        lx += 32 + int(text_px(st['label'], FS_SUB)) + 18
    return lx


FOOT_STEP = 15.0


def _overview_footer():
    return [
        '读图：① 一条总线 + 5 段支线；② 仅 2 条直连；③ agc_task 分发主干 + 两条横向通道；'
        '④ 是出界依赖，短标签在框内。',
        '易错：agc_task → 域包是 ③ 不是 ②；agc_control 是 ② 唯一例外；'
        'px4_msgs 是内联第三方、不是第 9 个包；agc_sim 不依赖 agc_msgs。',
        '完整边清单见 system-structure-detail.svg 与 系统结构图.md#detail',
    ]


def render_overview():
    """返回概览图 SVG 文本（确定性：无时间戳 / 无随机 / 无绝对路径）。"""
    nodes, bands, frame = layout()
    segs = routes(nodes, bands)
    labels, _boxes = place_labels(nodes, segs, label_specs(nodes, bands))
    notes = _overview_footer()

    footer_y = frame[3] + 36
    canvas_h = int(footer_y + (len(notes) - 1) * FOOT_STEP + 22)

    out = _svg_open(CANVAS_W, canvas_h)

    # 页眉
    out.append(_t(MARGIN_L, 38, 'AGC 系统结构（概览）', FS_TITLE, COLOR['ink'], True))
    out.append(_t(MARGIN_L, 62,
                  '8 包 · 四类依赖 · 画布 820 px = README 显示宽 · 真源见包边界',
                  FS_SUB, COLOR['muted']))

    # 图例（只有 ①②③ 是线；④ 是框内标签）
    lx = _legend(out, MARGIN_L, 92, (1, 2, 3))
    out.append(_r(lx, 85, 16, 15, 'none', COLOR['frame'], rx=3, sw=1.1))
    out.append(_t(lx + 22, 97, '系统边界', FS_SUB, COLOR['body']))
    lx += 22 + int(text_px('系统边界', FS_SUB)) + 16
    out.append(_t(lx, 97, '④ 外部边界 = 框内紫色行', FS_SUB, COLOR['ext']))

    # 面板标题 + 系统边界
    out.append(_t(MARGIN_L, FRAME_Y0 - 12,
                  '按依赖方向分层；框内紫色行为 ④ 出界依赖（清单见明细图）',
                  FS_PANEL, COLOR['ink'], True))
    out.append(_r(frame[0], frame[1], frame[2] - frame[0], frame[3] - frame[1],
                  'none', COLOR['frame'], rx=8, sw=1.1))
    out.append(_t(frame[0] + 10, frame[1] + 17,
                  '系统边界：src/ 下 8 个 ament 包', FS_SUB, COLOR['faint']))

    # 层名
    for name, x, y, text, size, anchor in labels:
        if name.startswith('layer'):
            out.append(_t(x, y, text, size, COLOR['muted'], anchor=anchor))

    # 线（先线后框）
    for seg in segs:
        st = STYLE[seg['kind']]
        out.append(_poly(seg['pts'], st))
        if seg.get('head'):
            out.append(_arrow(seg['pts'][-2], seg['pts'][-1], st))

    kind_of = {'bus': 1, 'link': 2, 'dispatch': 3, 'air_sim': 3}
    for name, x, y, text, size, anchor in labels:
        if name.startswith('layer'):
            continue
        k = kind_of.get(name)
        out.append(_t(x, y, text, size, STYLE[k]['stroke'] if k else COLOR['muted'],
                      anchor=anchor))

    # 节点
    for p in PACKAGES:
        x, y, w, h = nodes[p['id']]
        if p['id'] == 'agc_control':
            fill, stroke = COLOR['lib_fill'], COLOR['lib_stroke']
        elif p['id'] == 'agc_msgs':
            fill, stroke = COLOR['iface_fill'], COLOR['iface_stroke']
        else:
            fill, stroke = COLOR['node_fill'], COLOR['node_stroke']
        out.append(_r(x, y, w, h, fill, stroke, rx=7, sw=1.4))
        yy = y + PAD_TOP
        for i, (txt, size, bold, color) in enumerate(node_lines(p, w)):
            if i:
                yy += line_step(size)
            out.append(_t(x + PAD_X, yy, txt, size, color, bold=bold))

    # 页脚
    yy = footer_y
    for n in notes:
        out.append(_t(MARGIN_L, yy, n, FS_FOOT, COLOR['muted']))
        yy += FOOT_STEP
    out.append('</svg>')
    return '\n'.join(out) + '\n'


# ======================================================================================
# 8. 明细图：完整边清单（独立资产，正文 12 px）
# ======================================================================================


def detail_sections():
    """四段：标题 / 规则 / 逐条边。④ 段由 EXT_RELATIONS 生成，不手写。"""
    kinds = {1: [], 2: [], 3: []}
    for src, dst, kind in PACKAGE_EDGES:
        kinds[kind].append((src, dst))
    by_ext = {}
    for ext, src, way, note in EXT_RELATIONS:
        by_ext.setdefault(ext, []).append((src, way, note))

    sections = [
        dict(no=1, title='① 消息 / 接口依赖（%d 条）' % len(kinds[1]),
             rule='跨域通信一律经 agc_msgs；它为叶依赖、无出边，不依赖任何兄弟包。',
             items=['%s  →  agc_msgs' % s for s, _d in kinds[1]]
             + ['不在此列（易错）：agc_sim 只经 ros_gz 桥发标准消息；agc_control 是纯实现库。']),
        dict(no=2, title='② 库链接依赖（%d 条 · 唯一例外）' % len(kinds[2]),
             rule='编译期链接实现库：仅 agc_control 允许被 air / ground 链接同一实现'
                  '（ADR-0018）；除此禁止业务库互链。',
             items=['%s  →  agc_control（INTERFACE 共享库 + pluginlib 插件）' % s
                    for s, _d in kinds[2]]
             + ['两侧 CMakeLists 均 find_package(agc_control)。']),
        dict(no=3, title='③ 运行组合依赖（%d 条 · exec_depend）' % len(kinds[3]),
             rule='起进程 ≠ 链接库：只以 exec_depend 声明被起进程所属包，不据此链接其实现库。',
             items=['%s  →  %s（起进程）' % (s, d) for s, d in kinds[3]]
             + ['出界 ③（起 lifecycle_manager / collision_monitor / uXRCE Agent）见 ④ 段。']),
        dict(no=4, title='④ 外部设备 / 第三方边界（%d 条关系）' % len(EXT_RELATIONS),
             rule='外部项按包边界原文归入 ④；「依赖 / 起进程」的区分同 ② / ③，不新造第五类。',
             items=[]),
    ]
    for eid, label in EXTERNAL:
        for src, way, note in by_ext.get(eid, []):
            sections[3]['items'].append(
                '%s  ←  %s（%s：%s）' % (label, src,
                                        '起进程' if way == 'start' else '依赖', note))
    sections[3]['items'].append(
        'uXRCE-DDS Agent ↔ PX4 SITL 是 XRCE-DDS ↔ uORB 桥接（外部↔外部），不构成包依赖。')
    return sections


def detail_lines():
    """明细图文本行：(kind, text, size, bold, color, indent)。测试与渲染共用。"""
    inner = CANVAS_W - 2 * MARGIN_L - 2 * 14
    lines = []
    for sec in detail_sections():
        lines.append(('t', sec['title'], FS_CARD_T, True, COLOR['ink'], 0))
        for ln in wrap_text(sec['rule'], inner, FS_CARD):
            lines.append(('r', ln, FS_CARD, False, COLOR['body'], 0))
        for it in sec['items']:
            for j, ln in enumerate(wrap_text(it, inner - 16, FS_CARD)):
                lines.append(('i', ln, FS_CARD, False, COLOR['body'], 16 if j == 0 else 34))
        lines.append(('g', '', FS_CARD, False, COLOR['body'], 0))
    return lines


def render_detail():
    """返回明细图 SVG 文本（确定性）。"""
    lines = detail_lines()
    title_h = 86
    body = sum(line_step(FS_CARD) for k, *_ in lines if k != 'g') + len(lines) * 2
    canvas_h = int(title_h + body + 42)

    out = _svg_open(CANVAS_W, canvas_h)
    out.append(_t(MARGIN_L, 38, 'AGC 系统结构（明细）：四类依赖的完整边清单', FS_TITLE,
                  COLOR['ink'], True))
    out.append(_t(MARGIN_L, 62,
                  '与概览图同表生成（同一份 PACKAGE_EDGES / EXT_RELATIONS）；'
                  '两图边集合由回归断言相等', FS_SUB, COLOR['muted']))
    out.append(_r(MARGIN_L, title_h - 24, CANVAS_W - 2 * MARGIN_L, canvas_h - title_h + 8,
                  COLOR['card'], COLOR['node_stroke'], rx=8, sw=1.1))

    y = title_h + 4
    for kind, text, size, bold, color, indent in lines:
        if kind == 'g':
            y += 12
            continue
        y += line_step(size)
        out.append(_t(MARGIN_L + 14 + indent, int(y), text, size, color, bold=bold))
    out.append('</svg>')
    return '\n'.join(out) + '\n'


# ======================================================================================
# 9. 自检总入口
# ======================================================================================


def _edge_set():
    """概览与明细**共用**的边集合定义（两图必须相等，见 run_checks）。"""
    s = {(a, b, k) for a, b, k in PACKAGE_EDGES}
    s |= {(ext, src, way) for ext, src, way, _n in EXT_RELATIONS}
    return s


def run_checks():
    """全部自检；返回错误列表（空 = 通过）。测试与本脚本共用这一个入口。"""
    nodes, bands, frame = layout()
    segs = routes(nodes, bands)
    _labels, boxes = place_labels(nodes, segs, label_specs(nodes, bands))
    errors = (validate() + validate_layout(nodes, frame) + validate_routes(nodes, segs)
              + validate_labels(nodes, segs, boxes))

    # 明细图：每行都要放得下，且不允许省略号
    inner = CANVAS_W - 2 * MARGIN_L - 2 * 14
    for kind, txt, _s, _b, _c, _i in detail_lines():
        if kind == 'g':
            continue
        if text_px(txt, FS_CARD) > inner:
            errors.append('明细图行超宽：%r' % txt)
        if txt.endswith('…'):
            errors.append('明细图行被省略号截断：%r' % txt)

    # 字号下限：概览与明细正文都不得低于审查要求
    if FS_DESC < 12 or FS_ROLE < 12 or FS_EXT < 12:
        errors.append('概览正文/角色/④ 标签字号低于 12 px')
    if FS_NODE < 15:
        errors.append('包名字号低于 15 px')
    if FS_CARD < 12:
        errors.append('明细正文低于 12 px')

    # 两图边集合必须相等（等价性由同一 _edge_set 定义保证；此处防未来被改坏）
    if _edge_set() != {(a, b, k) for a, b, k in PACKAGE_EDGES} | \
            {(e, s, w) for e, s, w, _n in EXT_RELATIONS}:
        errors.append('概览/明细边集合定义漂移')
    return errors


# ======================================================================================
# 10. PNG 预览（可选；渲染器本身不依赖 Qt）
# ======================================================================================


def rasterize(svg_path, png_path, scale=2):
    """用 Qt SVG 渲染器把 SVG 光栅化成 PNG。返回 0 / 1 / 3（缺 PyQt5）。"""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    try:
        from PyQt5 import QtCore, QtGui, QtSvg
    except Exception as exc:                       # noqa: BLE001
        print('[structure] 跳过 PNG：PyQt5 不可用（%s）' % exc, file=sys.stderr)
        return 3
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    assert app is not None
    r = QtSvg.QSvgRenderer(svg_path)
    if not r.isValid():
        print('[structure] PNG 失败：Qt 无法解析 %s' % svg_path, file=sys.stderr)
        return 1
    size = r.defaultSize()
    img = QtGui.QImage(size.width() * scale, size.height() * scale,
                       QtGui.QImage.Format_RGB32)
    img.fill(QtCore.Qt.white)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    r.render(p)
    p.end()
    os.makedirs(os.path.dirname(os.path.abspath(png_path)), exist_ok=True)
    if not img.save(png_path):
        print('[structure] PNG 写出失败：%s' % png_path, file=sys.stderr)
        return 1
    print('[structure] 已写出 %s（%d×%d，scale=%d）'
          % (png_path, size.width() * scale, size.height() * scale, scale))
    return 0


def _write(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print('[structure] 已写出 %s（%d 字节）' % (path, len(text.encode('utf-8'))))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=True, description='渲染系统结构图（概览 / 明细）')
    ap.add_argument('--out', help='概览图 SVG 输出路径')
    ap.add_argument('--png', dest='png_overview', help='概览图 PNG（需 PyQt5）')
    ap.add_argument('--detail', help='明细图 SVG 输出路径')
    ap.add_argument('--detail-png', dest='png_detail', help='明细图 PNG（需 PyQt5）')
    ap.add_argument('--scale', type=int, default=2, help='PNG 缩放倍数（默认 2）')
    ap.add_argument('--check-only', action='store_true', help='只跑自检，不写文件')
    args = ap.parse_args(argv)

    errors = run_checks()
    if errors:
        for e in errors:
            print('[structure] 自检失败：%s' % e, file=sys.stderr)
        return 1
    if args.check_only:
        print('[structure] 自检通过：%d 包 / %d 条包间边 / %d 条④关系 / 概览+明细 2 张图'
              % (len(PACKAGES), len(PACKAGE_EDGES), len(EXT_RELATIONS)))
        return 0
    if not (args.out or args.detail):
        ap.error('需要 --out 和/或 --detail（或 --check-only）')

    rc = 0
    if args.out:
        _write(args.out, render_overview())
        if args.png_overview:
            rc = rasterize(args.out, args.png_overview, args.scale) or rc
    if args.detail:
        _write(args.detail, render_detail())
        if args.png_detail:
            rc = rasterize(args.detail, args.png_detail, args.scale) or rc
    return rc


if __name__ == '__main__':
    sys.exit(main())
